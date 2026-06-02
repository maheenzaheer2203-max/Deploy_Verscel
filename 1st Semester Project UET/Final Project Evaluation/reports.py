from flask import Blueprint, jsonify, request, session
import pyodbc
import json
from openai import OpenAI
import math

# products_json = json.dumps(products_list)

reports_bp = Blueprint("reports", __name__)

# ================= DB =================
def get_conn():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=ERPSystem;"
        "Trusted_Connection=yes;"
    )

# ================= SAFE SESSION CHECK =================
def get_company():
    if "company_code" not in session:
        return None
    return session["company_code"]

# ================= KPI =================
@reports_bp.route("/api/reports/kpi")
def kpi():

    company_code = get_company()
    if not company_code:
        return jsonify({})

    conn = get_conn()
    cursor = conn.cursor()

    # ORDERS
    cursor.execute("""
        SELECT COUNT(*) FROM Orders
        WHERE company_code=?
    """, company_code)
    orders = cursor.fetchone()[0]

    # REVENUE
    cursor.execute("""
        SELECT ISNULL(SUM(grand_total),0)
        FROM Orders
        WHERE company_code=?
    """, company_code)
    revenue = cursor.fetchone()[0]

    # LOW STOCK (< 10 ✔ FIX)
    cursor.execute("""
        SELECT COUNT(*)
        FROM Products
        WHERE company_code=? AND quantity < 10
    """, company_code)
    low_stock = cursor.fetchone()[0]

    # BEST PRODUCT (FIXED SAFE)
    cursor.execute("""
        SELECT TOP 1 name, sold
        FROM Products
        WHERE company_code=?
        ORDER BY sold DESC
    """, company_code)

    best = cursor.fetchone()

    conn.close()

    return jsonify({
        "orders": orders,
        "revenue": float(revenue),
        "low_stock": low_stock,
        "best_product": {
            "name": best[0] if best else "No Data",
            "sold": int(best[1]) if best else 0
        }
    })

# ================= CHART =================
@reports_bp.route("/api/reports/chart")
def chart():

    company_code = get_company()
    if not company_code:
        return jsonify({})

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            DATEPART(WEEKDAY, created_at) as day_no,
            ISNULL(SUM(grand_total),0) as total
        FROM Orders
        WHERE company_code=?
        GROUP BY DATEPART(WEEKDAY, created_at)
    """, company_code)

    rows = cursor.fetchall()
    conn.close()

    data = {r[0]: float(r[1]) for r in rows}

    return jsonify({
        "labels": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
        "values": [
            data.get(2,0),
            data.get(3,0),
            data.get(4,0),
            data.get(5,0),
            data.get(6,0),
            data.get(7,0),
            data.get(1,0)
        ]
    })

# ================= TOP PRODUCTS =================
@reports_bp.route("/api/reports/top_products")
def top_products():

    company_code = get_company()
    if not company_code:
        return jsonify([])

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT TOP 6 name, ISNULL(sold,0) as sold
        FROM Products
        WHERE company_code=?
        ORDER BY sold DESC
    """, company_code)

    rows = cursor.fetchall()
    conn.close()

    return jsonify([{"name": r[0], "sold": int(r[1])} for r in rows])

# ================= MONTHLY REVENUE =================
@reports_bp.route("/api/reports/monthly")
def monthly_revenue():

    company_code = get_company()
    if not company_code:
        return jsonify({})

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            MONTH(created_at) as mon,
            ISNULL(SUM(grand_total),0) as total
        FROM Orders
        WHERE company_code=?
        AND YEAR(created_at) = YEAR(GETDATE())
        GROUP BY MONTH(created_at)
    """, company_code)

    rows = cursor.fetchall()
    conn.close()

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    data = {r[0]: float(r[1]) for r in rows}

    return jsonify({
        "labels": months,
        "values": [data.get(i, 0) for i in range(1, 13)]
    })


@reports_bp.route("/api/reports/inventory")
def inventory():

    company_code = get_company()
    if not company_code:
        return jsonify([])

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, price, quantity, sold
        FROM Products
        WHERE company_code=?
    """, company_code)

    rows = cursor.fetchall()
    conn.close()

    result = []

    for r in rows:

        status = "OK"
        if r[3] <= 5:
            status = "LOW"
        if r[3] == 0:
            status = "OUT"

        result.append({
            "id": r[0],
            "name": r[1],
            "price": float(r[2]),
            "stock": r[3],
            "sold": r[4],
            "status": status
        })

    return jsonify(result)

# ================= AI =================

@reports_bp.route("/api/reports/ai", methods=["POST"])
def ai():

    company_code = get_company()
    if not company_code:
        return jsonify({"reply": "Session expired"}), 401

    data = request.get_json(silent=True) or {}
    msg = data.get("message", "").lower()

    conn = get_conn()
    cursor = conn.cursor()

    # ================= DATA =================
    cursor.execute("SELECT COUNT(*) FROM Orders WHERE company_code=?", company_code)
    orders = cursor.fetchone()[0]

    cursor.execute("SELECT ISNULL(SUM(grand_total),0) FROM Orders WHERE company_code=?", company_code)
    revenue = float(cursor.fetchone()[0])

    cursor.execute("SELECT ISNULL(AVG(grand_total),0) FROM Orders WHERE company_code=?", company_code)
    avg_order = float(cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM Products WHERE company_code=? AND quantity <= 5", company_code)
    low_stock = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Products WHERE company_code=? AND quantity = 0", company_code)
    out_stock = cursor.fetchone()[0]

    cursor.execute("SELECT ISNULL(SUM(sold),0) FROM Products WHERE company_code=?", company_code)
    sold = cursor.fetchone()[0]

    cursor.execute("""
        SELECT TOP 1 name, sold
        FROM Products
        WHERE company_code=?
        ORDER BY sold DESC
    """, company_code)

    best = cursor.fetchone()
    conn.close()

    best_name = best[0] if best else "No Data"

    # ================= AI HELPERS =================

    def predict_growth(value, rate):
        return round(value * (1 + rate))

    def health_score():
        return max(0, 100 - (low_stock * 2 + out_stock * 5))

    # ================= INTENT SYSTEM (SMART NLP) =================
    intents = [
        {
            "name": "sales",
            "keywords": ["sales", "sale", "sold", "orders", "kitni", "order"],
            "response": lambda: f"""📊 SALES REPORT
Orders: {orders}
Total Sold: {sold}
Best Product: {best_name}"""
        },
        {
            "name": "revenue",
            "keywords": ["revenue", "income", "profit", "paisa", "earning"],
            "response": lambda: f"""💰 REVENUE REPORT
Revenue: {round(revenue)}
Avg Order: {round(avg_order)}"""
        },
        {
            "name": "stock",
            "keywords": ["stock", "inventory", "maal", "quantity"],
            "response": lambda: f"""📦 STOCK REPORT
Low Stock: {low_stock}
Out of Stock: {out_stock}"""
        },
        {
            "name": "analysis",
            "keywords": ["analysis", "report", "insight", "business", "summary"],
            "response": lambda: f"""🧠 BUSINESS ANALYSIS
Orders: {orders}
Revenue: {round(revenue)}
Health Score: {health_score()}/100
Risk Items: {low_stock + out_stock}"""
        },
        {
            "name": "predict",
            "keywords": ["predict", "forecast", "future", "next", "agla", "andaza"],
            "response": lambda: f"""📈 AI PREDICTION REPORT

📊 Next Sales Estimate: {predict_growth(sold, 0.12)}
💰 Next Revenue Estimate: {predict_growth(revenue, 0.15)}
📦 Expected Stock Risk: {"HIGH ⚠️" if (low_stock + out_stock) > 20 else "NORMAL ✅"}

AI Model: Trend + Growth Simulation"""
        }
    ]

    # ================= SMART SCORING MATCH =================
    best_match = None
    best_score = 0

    for intent in intents:
        score = sum(1 for kw in intent["keywords"] if kw in msg)

        if score > best_score:
            best_score = score
            best_match = intent

    # ================= RESPONSE =================
    if best_match and best_score > 0:
        return jsonify({"reply": best_match["response"]()})

    # ================= DEFAULT SMART AI =================
    return jsonify({
        "reply": """🤖 ERP AI ASSISTANT

Main aapki help kar sakta hoon:

📊 Sales Report
💰 Revenue Analysis
📦 Stock Status
📈 Future Prediction

Try:
- "predict future sales"
- "revenue batao"
- "stock check karo"
"""
    })