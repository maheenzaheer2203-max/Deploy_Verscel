from flask import Blueprint, request, jsonify, session, render_template
import pyodbc

contact_bp = Blueprint("contact", __name__)

def get_conn():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=ERPSystem;"
        "Trusted_Connection=yes;"
    )

# ================= CONTACT PAGE =================
@contact_bp.route("/contact")
def contact_page():
    if "company_code" not in session:
        from flask import redirect
        return redirect("/")
    return render_template("contact.html")

# ================= SUBMIT MESSAGE =================
@contact_bp.route("/api/contact", methods=["POST"])
def submit_contact():
    if "company_code" not in session:
        return jsonify({"msg": "Unauthorized"}), 401
    company_code = session["company_code"]
    data = request.get_json(silent=True)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ContactMessages' AND xtype='U')
        CREATE TABLE ContactMessages (
            id INT IDENTITY(1,1) PRIMARY KEY,
            company_code VARCHAR(50),
            name VARCHAR(100),
            email VARCHAR(150),
            subject VARCHAR(200),
            message TEXT,
            status VARCHAR(20) DEFAULT 'Unread',
            created_at DATETIME DEFAULT GETDATE()
        )
    """)
    conn.commit()
    cursor.execute("""
        INSERT INTO ContactMessages(company_code, name, email, subject, message)
        VALUES (?,?,?,?,?)
    """, company_code, data.get("name"), data.get("email"),
         data.get("subject"), data.get("message"))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Message sent successfully"})

# ================= GET MESSAGES (admin view) =================
@contact_bp.route("/api/contact/messages", methods=["GET"])
def get_messages():
    if "company_code" not in session:
        return jsonify([])
    company_code = session["company_code"]
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, email, subject, message, status, created_at
        FROM ContactMessages WHERE company_code=? ORDER BY id DESC
    """, company_code)
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": r[0], "name": r[1], "email": r[2],
        "subject": r[3], "message": r[4],
        "status": r[5], "created_at": str(r[6])
    } for r in rows])
