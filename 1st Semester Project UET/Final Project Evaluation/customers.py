from flask import Blueprint, request, jsonify, session
import pyodbc
import json

# products_json = json.dumps(products_list) 

customers_bp = Blueprint("customers", __name__)

# ================= DB CONNECTION =================
def get_conn():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=ERPSystem;"
        "Trusted_Connection=yes;"
    )

# ================= GET CUSTOMERS =================
@customers_bp.route("/api/customers", methods=["GET"])
def get_customers():

    if "company_code" not in session:
        return jsonify([])

    company_code = session["company_code"]
    search = request.args.get("search", "")

    conn = get_conn()
    cursor = conn.cursor()

    # ================= SEARCH =================
    if search:
        cursor.execute("""
            SELECT id, name, email, phone, address, status
            FROM Customers
            WHERE company_code=?
            AND (
                name LIKE ?
                OR email LIKE ?
                OR phone LIKE ?
            )
            ORDER BY id DESC
        """,
        company_code,
        f"%{search}%",
        f"%{search}%",
        f"%{search}%"
        )
    else:
        cursor.execute("""
            SELECT id, name, email, phone, address, status
            FROM Customers
            WHERE company_code=?
            ORDER BY id DESC
        """, company_code)

    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "name": r[1],
            "email": r[2],
            "phone": r[3],
            "address": r[4],
            "status": r[5]
        }
        for r in rows
    ])


# ================= ADD CUSTOMER =================
@customers_bp.route("/api/customers", methods=["POST"])
def add_customer():

    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401

    company_code = session["company_code"]
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"msg": "Invalid request"}), 400

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO Customers(
            company_code,
            name,
            email,
            phone,
            address,
            status
        )
        VALUES (?,?,?,?,?,?)
    """,
    company_code,
    data.get("name"),
    data.get("email"),
    data.get("phone"),
    data.get("address", ""),
    data.get("status", "Active"))

    conn.commit()
    conn.close()

    return jsonify({"msg": "added"})


# ================= KPI =================
@customers_bp.route("/api/customers/kpi")
def kpi():

    if "company_code" not in session:
        return jsonify({})

    company_code = session["company_code"]

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM Customers
        WHERE company_code=?
    """, company_code)
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM Customers
        WHERE company_code=? AND status='Active'
    """, company_code)
    active = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM Customers
        WHERE company_code=? AND status!='Active'
    """, company_code)
    inactive = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM Customers
        WHERE company_code=? AND id > (
            SELECT ISNULL(MAX(id)-10,0)
            FROM Customers
            WHERE company_code=?
        )
    """, company_code, company_code)
    new = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "total": total,
        "active": active,
        "inactive": inactive,
        "new": new
    })