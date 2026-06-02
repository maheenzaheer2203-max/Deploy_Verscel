from flask import Flask, request, jsonify, render_template, session, redirect
import pyodbc
import os
import json
# products_json = json.dumps(products_list) 
from werkzeug.utils import secure_filename

from customers import customers_bp
from reports import reports_bp

# ================= APP =================
app = Flask(__name__) 
# app = Flask(__name__, template_folder="templates")
app.secret_key = "erp_secret_key"

# ================= BLUEPRINT =================
app.register_blueprint(customers_bp)
app.register_blueprint(reports_bp)

# ================= UPLOAD =================
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ================= DB CONNECTION =================
def get_conn():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=ERPSystem;"
        "Trusted_Connection=yes;"
    )


# ================= LOGIN PAGE =================
@app.route("/")
def login_page():
    return render_template("login.html")


# ================= REGISTER =================
@app.route("/register", methods=["POST"])
def register():

    data = request.get_json()

    company_name = data.get("company_name")
    company_code = data.get("company_code")
    email = data.get("email")
    password = data.get("password")

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM Users
        WHERE email=? OR company_code=?
    """, email, company_code)

    if cursor.fetchone():
        conn.close()
        return jsonify({"msg": "Account already exists"}), 400

    cursor.execute("""
        INSERT INTO Users(company_name, company_code, email, password)
        VALUES (?,?,?,?)
    """, company_name, company_code, email, password)

    conn.commit()
    conn.close()

    return jsonify({"msg": "registered"})


# ================= LOGIN =================
@app.route("/login", methods=["POST"])
def login():

    data = request.get_json()

    email = data.get("email")
    password = data.get("password")
    company_code = data.get("company_code")

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM Users
        WHERE email=? AND password=? AND company_code=?
    """, email, password, company_code)

    user = cursor.fetchone()
    conn.close()

    if user:
        session["company_code"] = company_code
        session["email"] = email

        return jsonify({
            "msg": "success",
            "redirect": "/dashboard"
        })

    return jsonify({"msg": "Invalid credentials"}), 401


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "company_code" not in session:
        return redirect("/")
    return render_template("dashboard.html")


# ================= PRODUCTS PAGE =================
@app.route("/products")
def products_page():
    if "company_code" not in session:
        return redirect("/")
    return render_template("products.html")


# ================= CUSTOMERS PAGE =================
@app.route("/customers")
def customers_page():
    if "company_code" not in session:
        return redirect("/")
    return render_template("customers.html")


# ================= REPORTS PAGE =================
@app.route("/reports")
def reports_page():
    if "company_code" not in session:
        return redirect("/")
    return render_template("reports.html")


@app.route("/api/reports/kpi")
def kpi():

    if "company_code" not in session:
        return jsonify({"orders": 0, "low_stock": 0, "revenue": 0})

    company_code = session["company_code"]

    conn = get_conn()
    cursor = conn.cursor()

    # TOTAL PRODUCTS
    cursor.execute("""
        SELECT COUNT(*)
        FROM Products
        WHERE company_code=?
    """, company_code)
    total_products = cursor.fetchone()[0]
    # LOW STOCK
    cursor.execute("""
        SELECT COUNT(*)
        FROM Products
        WHERE company_code=? AND ISNULL(quantity,0) < 10
    """, company_code)
    low_stock = cursor.fetchone()[0]

    # REVENUE
    cursor.execute("""
        SELECT ISNULL(SUM(ISNULL(price,0) * ISNULL(sold,0)),0)
        FROM Products
        WHERE company_code=?
    """, company_code)
    revenue = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "orders": total_products,
        "low_stock": low_stock,
        "revenue": revenue
    })

@app.route("/api/save_order", methods=["POST"])
def save_order():

    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401

    data = request.get_json()
    company_code = session["company_code"]

    conn = get_conn()
    cursor = conn.cursor()

    # ORDER
    cursor.execute("""
        INSERT INTO Orders(company_code, total, tax, grand_total)
        VALUES (?,?,?,?)
    """,
    company_code,
    data["total"],
    data["tax"],
    data["grand_total"])

    order_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]

    # ORDER ITEMS (FIXED)
    for item in data["items"]:
        cursor.execute("""
            INSERT INTO OrderItems(order_id, product_id, name, price, qty, subtotal, company_code)
            VALUES (?,?,?,?,?,?,?)
        """,
        order_id,
        item["id"],
        item["name"],
        item["price"],
        1,
        item["price"],
        company_code   # 🔥 IMPORTANT FIX
        )

    conn.commit()
    conn.close()

    return jsonify({"msg": "Order saved successfully"})
# ================= PRODUCTS API =================
# ================= PRODUCTS API =================
@app.route("/api/products")
def products():

    if "company_code" not in session:
        return jsonify([])

    company_code = session["company_code"]

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM Products
        WHERE company_code=?
    """, company_code)

    rows = cursor.fetchall()
    conn.close()

    data = []

    for r in rows:

        data.append({
            "id": r[0],
            "name": r[1],
            "price": float(r[2] or 0),
            "quantity": int(r[3] or 0),
            "category": r[4],
            "image": r[5],
            "sold": int(r[6] or 0),
            "company_code": r[7]
        })

    return jsonify(data)


# ================= ADD PRODUCT =================
@app.route("/api/add", methods=["POST"])
def add():

    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401

    company_code = session["company_code"]

    name = request.form.get("name")
    price = request.form.get("price")
    quantity = request.form.get("quantity")
    category = request.form.get("category")

    try:
        price = float(price)
        quantity = int(quantity)
    except:
        return jsonify({"msg": "Invalid data"}), 400

    file = request.files.get("image")

    image_path = ""

    if file and file.filename:
        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)
        image_path = "/static/uploads/" + filename

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO Products(company_code, name, price, quantity, category, image, sold)
        VALUES (?,?,?,?,?,?,0)
    """, company_code, name, price, quantity, category, image_path)

    conn.commit()
    conn.close()

    return jsonify({"msg": "added"})


# ================= BUY PRODUCT =================
@app.route("/api/buy/<int:id>", methods=["PUT"])
def buy(id):

    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401

    company_code = session["company_code"]

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Products
        SET quantity = CASE WHEN quantity > 0 THEN quantity - 1 ELSE 0 END,
            sold = ISNULL(sold,0) + 1
        WHERE id=? AND company_code=?
    """, id, company_code)

    conn.commit()
    conn.close()

    return jsonify({"msg": "sold"})


# ================= DELETE PRODUCT (FIXED) =================
@app.route("/api/delete/<int:id>", methods=["DELETE"])
def delete(id):

    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401

    company_code = session["company_code"]

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM Products
        WHERE id=? AND company_code=?
    """, id, company_code)

    conn.commit()
    conn.close()

    return jsonify({"msg": "deleted"})


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)