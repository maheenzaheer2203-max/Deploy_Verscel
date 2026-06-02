from flask import Blueprint, request, jsonify, session, render_template
import pyodbc

discount_bp = Blueprint("discount", __name__)

# ================= DB =================
def get_conn():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=ERPSystem;"
        "Trusted_Connection=yes;"
    )

# ================= DISCOUNT PAGE =================
@discount_bp.route("/discount")
def discount_page():
    if "company_code" not in session:
        from flask import redirect
        return redirect("/")
    return render_template("discount.html")

# ================= GET DISCOUNTS =================
@discount_bp.route("/api/discounts", methods=["GET"])
def get_discounts():
    if "company_code" not in session:
        return jsonify([])
    company_code = session["company_code"]
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Discounts' AND xtype='U')
        CREATE TABLE Discounts (
            id INT IDENTITY(1,1) PRIMARY KEY,
            company_code VARCHAR(50),
            name VARCHAR(100),
            type VARCHAR(20),
            value DECIMAL(10,2),
            min_order DECIMAL(10,2),
            status VARCHAR(20),
            created_at DATETIME DEFAULT GETDATE()
        )
    """)
    conn.commit()
    cursor.execute("""
        SELECT id, name, type, value, min_order, status, created_at
        FROM Discounts WHERE company_code=? ORDER BY id DESC
    """, company_code)
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": r[0], "name": r[1], "type": r[2],
        "value": float(r[3] or 0), "min_order": float(r[4] or 0),
        "status": r[5], "created_at": str(r[6])
    } for r in rows])

# ================= ADD DISCOUNT =================
@discount_bp.route("/api/discounts", methods=["POST"])
def add_discount():
    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401
    company_code = session["company_code"]
    data = request.get_json(silent=True)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Discounts(company_code, name, type, value, min_order, status)
        VALUES (?,?,?,?,?,?)
    """, company_code, data.get("name"), data.get("type"),
         data.get("value", 0), data.get("min_order", 0), data.get("status","Active"))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Discount added"})

# ================= DELETE DISCOUNT =================
@discount_bp.route("/api/discounts/<int:id>", methods=["DELETE"])
def delete_discount(id):
    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401
    company_code = session["company_code"]
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Discounts WHERE id=? AND company_code=?", id, company_code)
    conn.commit()
    conn.close()
    return jsonify({"msg": "Deleted"})

# ================= TOGGLE STATUS =================
@discount_bp.route("/api/discounts/<int:id>/toggle", methods=["PUT"])
def toggle_discount(id):
    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401
    company_code = session["company_code"]
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE Discounts
        SET status = CASE WHEN status='Active' THEN 'Inactive' ELSE 'Active' END
        WHERE id=? AND company_code=?
    """, id, company_code)
    conn.commit()
    conn.close()
    return jsonify({"msg": "Toggled"})
