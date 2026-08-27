from flask import (
    Flask,
    request,
    redirect,
    session,
    render_template_string,
    jsonify,
    url_for
)
import sqlite3
import os
import math
from datetime import datetime, timedelta
from functools import wraps


# =========================================================
# APP CONFIG
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "pizza-company-school-project-secret"
)

DB = os.environ.get("DB_PATH", "pizza_company.db")

# ---------------------------------------------------------
# GPS
# จุดอ้างอิงโรงเรียนสวนกุหลาบวิทยาลัย รังสิต
# ---------------------------------------------------------

SKR_LAT = 14.02303
SKR_LNG = 100.68763

# อนุญาตภายใน 300 เมตร
ALLOWED_DISTANCE_KM = 0.3

# เวลาเริ่มงาน
WORK_START = "08:00"

# รหัสเข้าสู่ระบบ
# สามารถเปลี่ยนบน Render ด้วย Environment Variables ได้
STAFF_PIN = os.environ.get("STAFF_PIN", "1234")
ACCOUNT_PIN = os.environ.get("ACCOUNT_PIN", "9999")


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            salary REAL NOT NULL DEFAULT 0,
            department TEXT DEFAULT 'พนักงาน',
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            date TEXT NOT NULL,
            time_in TEXT,
            time_out TEXT,
            work_hours REAL DEFAULT 0,
            ot_hours REAL DEFAULT 0,
            status TEXT DEFAULT '-',
            location TEXT DEFAULT '-',
            distance_km REAL DEFAULT 0,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            month TEXT NOT NULL,
            base_salary REAL DEFAULT 0,
            ot_hours REAL DEFAULT 0,
            ot_pay REAL DEFAULT 0,
            total REAL DEFAULT 0,
            created_at TEXT,
            UNIQUE(employee_id, month)
        )
    """)

    conn.commit()

    # เพิ่มข้อมูลตัวอย่างเฉพาะกรณีฐานข้อมูลยังว่าง
    count = cur.execute(
        "SELECT COUNT(*) FROM employees"
    ).fetchone()[0]

    if count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            INSERT INTO employees
            (id, name, salary, department, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "001",
            "พนักงานตัวอย่าง",
            15000,
            "ฝ่ายทั่วไป",
            1,
            now
        ))

        cur.execute("""
            INSERT INTO employees
            (id, name, salary, department, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "002",
            "จ๊ะจ๋า",
            15000,
            "ฝ่ายบัญชี",
            1,
            now
        ))

        conn.commit()

    conn.close()


# =========================================================
# LOGIN / PERMISSION
# =========================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def accounting_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))

        if session.get("role") != "accounting":
            return render_page(
                "ไม่มีสิทธิ์",
                """
                <div class="card">
                    <h2>🔒 ไม่มีสิทธิ์เข้าถึง</h2>
                    <p>
                        หน้านี้สามารถใช้งานได้เฉพาะฝ่ายบัญชีเท่านั้น
                    </p>
                    <a class="btn" href="/">กลับหน้าหลัก</a>
                </div>
                """
            )

        return view(*args, **kwargs)

    return wrapped


# =========================================================
# GPS FUNCTIONS
# =========================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    คำนวณระยะห่างระหว่างพิกัด 2 จุด
    ผลลัพธ์เป็นกิโลเมตร
    """

    radius = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return radius * c


def check_location(latitude, longitude):
    """
    ตรวจสอบว่าพิกัดอยู่ในพื้นที่โรงเรียนหรือไม่
    """

    if latitude is None or longitude is None:
        return False, "-", None

    try:
        latitude = float(latitude)
        longitude = float(longitude)

        distance = haversine_distance(
            SKR_LAT,
            SKR_LNG,
            latitude,
            longitude
        )

        if distance <= ALLOWED_DISTANCE_KM:
            location = "สวนกุหลาบวิทยาลัย รังสิต (อยู่ในพื้นที่)"
            return True, location, distance

        location = f"อยู่นอกพื้นที่ ({distance:.2f} กม.)"
        return False, location, distance

    except (ValueError, TypeError):
        return False, "-", None


# =========================================================
# TIME / PAY CALCULATION
# =========================================================

def calculate_work_hours(time_in, time_out):
    if not time_in or not time_out:
        return 0

    try:
        start = datetime.strptime(time_in, "%H:%M:%S")
        end = datetime.strptime(time_out, "%H:%M:%S")

        if end < start:
            end += timedelta(days=1)

        seconds = (end - start).total_seconds()

        return round(seconds / 3600, 2)

    except Exception:
        return 0


def calculate_ot(work_hours):
    if work_hours <= 8:
        return 0

    return round(work_hours - 8, 2)


def calculate_status(time_in):
    if not time_in:
        return "-"

    try:
        current = datetime.strptime(
            time_in,
            "%H:%M:%S"
        ).time()

        limit = datetime.strptime(
            WORK_START,
            "%H:%M"
        ).time()

        if current <= limit:
            return "ปกติ"

        return "มาสาย"

    except Exception:
        return "-"


# =========================================================
# HTML LAYOUT
# =========================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>{{ title }} - Pizza Company</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Tahoma,
        sans-serif;

    background: #f4f5f7;
    color: #222;
    padding-bottom: 90px;
}

.header {
    background: #c8102e;
    color: white;
    padding: 17px 20px;
    font-size: 22px;
    font-weight: bold;
}

.container {
    width: 94%;
    max-width: 1100px;
    margin: 20px auto;
}

.card {
    background: white;
    border-radius: 18px;
    padding: 20px;
    margin-bottom: 18px;
    box-shadow:
        0 3px 15px rgba(0,0,0,0.08);
}

.card h2 {
    margin-top: 0;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
}

.stat {
    background: white;
    border-radius: 18px;
    padding: 20px;
    box-shadow:
        0 3px 15px rgba(0,0,0,0.07);
}

.stat .number {
    font-size: 30px;
    font-weight: bold;
    color: #c8102e;
}

input,
select {
    width: 100%;
    padding: 13px;
    border: 1px solid #ddd;
    border-radius: 10px;
    font-size: 16px;
    margin: 6px 0 13px;
}

label {
    font-weight: 600;
}

.btn {
    display: inline-block;
    border: none;
    border-radius: 10px;
    padding: 12px 18px;
    background: #c8102e;
    color: white;
    text-decoration: none;
    cursor: pointer;
    font-size: 15px;
    margin: 3px;
}

.btn.blue {
    background: #1769e0;
}

.btn.green {
    background: #159447;
}

.btn.gray {
    background: #59636e;
}

.btn.orange {
    background: #e88a00;
}

.btn.danger {
    background: #b00020;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
}

th,
td {
    padding: 12px 8px;
    border-bottom: 1px solid #eee;
    text-align: left;
}

th {
    background: #f0f1f3;
}

.badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    background: #eee;
}

.badge.late {
    background: #ffe0e0;
    color: #a40000;
}

.badge.normal {
    background: #dff7e6;
    color: #08752d;
}

.badge.ok {
    background: #dcecff;
    color: #0758b8;
}

.gps-box {
    padding: 15px;
    background: #f6f7f9;
    border-radius: 14px;
    margin: 10px 0;
}

.notice {
    padding: 14px;
    border-radius: 12px;
    margin: 10px 0;
    background: #eef5ff;
}

.bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 70px;
    background: white;
    border-top: 1px solid #ddd;

    display: flex;
    justify-content: space-around;
    align-items: center;

    box-shadow: 0 -3px 15px rgba(0,0,0,0.08);
}

.bottom-nav a {
    color: #333;
    text-decoration: none;
    text-align: center;
    font-size: 12px;
}

.bottom-nav span {
    display: block;
    font-size: 22px;
}

.login {
    max-width: 420px;
    margin: 80px auto;
}

.center {
    text-align: center;
}

.small {
    font-size: 13px;
    color: #777;
}

@media(max-width: 700px) {

    .container {
        width: 92%;
    }

    table {
        font-size: 13px;
    }

    th,
    td {
        padding: 9px 5px;
    }

    .hide-mobile {
        display: none;
    }

}

</style>
</head>

<body>

<div class="header">
    🍕 Pizza Company
</div>

<div class="container">

{{ content|safe }}

</div>

{% if session.get("logged_in") %}
<div class="bottom-nav">

<a href="/">
    <span>🏠</span>
    หน้าหลัก
</a>

<a href="/attendance">
    <span>⏰</span>
    ลงเวลา
</a>

<a href="/payroll">
    <span>📅</span>
    บัญชี
</a>

<a href="/manual">
    <span>📖</span>
    คู่มือ
</a>

<a href="/logout">
    <span>🔐</span>
    ออก
</a>

</div>
{% endif %}

</body>
</html>
"""


def render_page(title, content, **context):
    return render_template_string(
        BASE_HTML,
        title=title,
        content=render_template_string(
            content,
            **context
        )
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        pin = request.form.get("pin", "").strip()

        if pin == ACCOUNT_PIN:
            session["logged_in"] = True
            session["role"] = "accounting"

            return redirect("/")

        if pin == STAFF_PIN:
            session["logged_in"] = True
            session["role"] = "staff"

            return redirect("/")

        return render_page(
            "เข้าสู่ระบบ",
            """
            <div class="login card">

                <div class="center">
                    <h1>🍕 Pizza Company</h1>
                    <p>เข้าสู่ระบบ</p>
                </div>

                <div class="notice">
                    ❌ รหัสไม่ถูกต้อง
                </div>

                <form method="POST">

                    <label>รหัสเข้าสู่ระบบ</label>

                    <input
                        type="password"
                        name="pin"
                        inputmode="numeric"
                        placeholder="กรอกรหัส"
                        required
                    >

                    <button class="btn" style="width:100%">
                        🔐 เข้าสู่ระบบ
                    </button>

                </form>

            </div>
            """
        )

    return render_page(
        "เข้าสู่ระบบ",
        """
        <div class="login card">

            <div class="center">
                <h1>🍕 Pizza Company</h1>
                <p>ระบบจัดการพนักงานและลงเวลาทำงาน</p>
            </div>

            <form method="POST">

                <label>รหัสเข้าสู่ระบบ</label>

                <input
                    type="password"
                    name="pin"
                    inputmode="numeric"
                    placeholder="กรอกรหัส"
                    required
                >

                <button class="btn" style="width:100%">
                    🔐 เข้าสู่ระบบ
                </button>

            </form>

            <p class="small center">
                ผู้ใช้งานต้องมีรหัสที่ได้รับจากผู้ดูแลระบบ
            </p>

        </div>
        """
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@login_required
def index():

    conn = get_db()

    employee_count = conn.execute("""
        SELECT COUNT(*)
        FROM employees
        WHERE active = 1
    """).fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")

    attendance_count = conn.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE date = ?
    """, (today,)).fetchone()[0]

    ot_total = conn.execute("""
        SELECT COALESCE(SUM(ot_hours), 0)
        FROM attendance
        WHERE date = ?
    """, (today,)).fetchone()[0]

    salary_total = conn.execute("""
        SELECT COALESCE(SUM(salary), 0)
        FROM employees
        WHERE active = 1
    """).fetchone()[0]

    conn.close()

    return render_page(
        "หน้าหลัก",
        """
        <h1>🏠 หน้าหลัก</h1>

        <div class="grid">

            <div class="stat">
                <div>👥 พนักงาน</div>
                <div class="number">
                    {{ employee_count }}
                </div>
                <div class="small">คน</div>
            </div>

            <div class="stat">
                <div>⏰ ลงเวลาวันนี้</div>
                <div class="number">
                    {{ attendance_count }}
                </div>
                <div class="small">รายการ</div>
            </div>

            <div class="stat">
                <div>⏱️ OT วันนี้</div>
                <div class="number">
                    {{ "%.2f"|format(ot_total) }}
                </div>
                <div class="small">ชั่วโมง</div>
            </div>

            <div class="stat">
                <div>💰 เงินเดือนรวม</div>
                <div class="number">
                    {{ "{:,.2f}".format(salary_total) }}
                </div>
                <div class="small">บาท / เดือน</div>
            </div>

        </div>

        <div class="card">

            <h2>เมนูหลัก</h2>

            <a class="btn" href="/attendance">
                ⏰ ลงเวลาเข้า–ออก
            </a>

            {% if session.get("role") == "accounting" %}
            <a class="btn blue" href="/employees">
                👥 จัดการพนักงาน
            </a>

            <a class="btn green" href="/payroll">
                💰 ฝ่ายบัญชี
            </a>
            {% endif %}

            <a class="btn gray" href="/manual">
                📖 คู่มือการใช้งาน
            </a>

        </div>

        <div class="card">

            <h2>📌 สถานะระบบ</h2>

            <p>
                ระบบลงเวลาและจัดการข้อมูลพนักงานพร้อมใช้งาน
            </p>

            <p class="small">
                ระบบจะตรวจสอบตำแหน่งก่อนลงเวลา
                เพื่อช่วยป้องกันการลงเวลาจากนอกพื้นที่
            </p>

        </div>
        """,
        employee_count=employee_count,
        attendance_count=attendance_count,
        ot_total=ot_total,
        salary_total=salary_total
    )


# =========================================================
# EMPLOYEES
# =========================================================

@app.route("/employees")
@accounting_required
def employees():

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM employees
        WHERE active = 1
        ORDER BY id
    """).fetchall()

    conn.close()

    return render_page(
        "พนักงาน",
        """
        <h1>👥 พนักงาน</h1>

        <div class="card">

            <a class="btn green" href="/employees/add">
                ➕ เพิ่มพนักงาน
            </a>

        </div>

        <div class="card">

            <div style="overflow-x:auto">

            <table>

                <tr>
                    <th>รหัส</th>
                    <th>ชื่อ</th>
                    <th>ฝ่าย</th>
                    <th>เงินเดือน</th>
                    <th>จัดการ</th>
                </tr>

                {% for r in rows %}

                <tr>

                    <td>{{ r["id"] }}</td>

                    <td>{{ r["name"] }}</td>

                    <td>{{ r["department"] or "-" }}</td>

                    <td>
                        {{ "{:,.2f}".format(r["salary"]) }}
                    </td>

                    <td>

                        <a
                            class="btn blue"
                            href="/employees/edit/{{ r['id'] }}"
                        >
                            แก้ไข
                        </a>

                        <a
                            class="btn danger"
                            href="/employees/delete/{{ r['id'] }}"
                            onclick="return confirm('ยืนยันการลบพนักงาน?')"
                        >
                            ลบ
                        </a>

                    </td>

                </tr>

                {% endfor %}

            </table>

            </div>

        </div>
        """,
        rows=rows
    )


@app.route("/employees/add", methods=["GET", "POST"])
@accounting_required
def add_employee():

    if request.method == "POST":

        employee_id = request.form.get("id", "").strip()
        name = request.form.get("name", "").strip()
        department = request.form.get(
            "department",
            "พนักงาน"
        ).strip()

        try:
            salary = float(
                request.form.get("salary", "0")
            )
        except ValueError:
            salary = 0

        if not employee_id or not name:
            return render_page(
                "เพิ่มพนักงาน",
                """
                <div class="card">
                    <h2>❌ กรุณากรอกข้อมูลให้ครบ</h2>
                    <a class="btn" href="/employees/add">
                        กลับ
                    </a>
                </div>
                """
            )

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO employees
                (id, name, salary, department, active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
            """, (
                employee_id,
                name,
                salary,
                department,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            return render_page(
                "เพิ่มพนักงาน",
                """
                <div class="card">
                    <h2>❌ รหัสพนักงานนี้มีอยู่แล้ว</h2>
                    <a class="btn" href="/employees/add">
                        กลับ
                    </a>
                </div>
                """
            )

        conn.close()

        return redirect("/employees")

    return render_page(
        "เพิ่มพนักงาน",
        """
        <h1>➕ เพิ่มพนักงาน</h1>

        <div class="card">

        <form method="POST">

            <label>รหัสพนักงาน</label>
            <input
                name="id"
                placeholder="เช่น 003"
                required
            >

            <label>ชื่อพนักงาน</label>
            <input
                name="name"
                placeholder="ชื่อ-นามสกุล"
                required
            >

            <label>ฝ่าย</label>
            <input
                name="department"
                placeholder="เช่น ฝ่ายบัญชี"
            >

            <label>เงินเดือน</label>
            <input
                name="salary"
                type="number"
                step="0.01"
                value="15000"
            >

            <button class="btn green">
                💾 บันทึก
            </button>

            <a class="btn gray" href="/employees">
                ยกเลิก
            </a>

        </form>

        </div>
        """
    )


@app.route("/employees/edit/<employee_id>", methods=["GET", "POST"])
@accounting_required
def edit_employee(employee_id):

    conn = get_db()

    employee = conn.execute("""
        SELECT *
        FROM employees
        WHERE id = ?
    """, (employee_id,)).fetchone()

    if not employee:
        conn.close()

        return render_page(
            "ไม่พบพนักงาน",
            """
            <div class="card">
                <h2>ไม่พบข้อมูลพนักงาน</h2>
            </div>
            """
        )

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        department = request.form.get(
            "department",
            "พนักงาน"
        ).strip()

        try:
            salary = float(
                request.form.get("salary", "0")
            )
        except ValueError:
            salary = 0

        conn.execute("""
            UPDATE employees
            SET name = ?,
                salary = ?,
                department = ?
            WHERE id = ?
        """, (
            name,
            salary,
            department,
            employee_id
        ))

        conn.commit()
        conn.close()

        return redirect("/employees")

    conn.close()

    return render_page(
        "แก้ไขพนักงาน",
        """
        <h1>✏️ แก้ไขพนักงาน</h1>

        <div class="card">

        <form method="POST">

            <label>รหัสพนักงาน</label>

            <input
                value="{{ employee['id'] }}"
                disabled
            >

            <label>ชื่อพนักงาน</label>

            <input
                name="name"
                value="{{ employee['name'] }}"
                required
            >

            <label>ฝ่าย</label>

            <input
                name="department"
                value="{{ employee['department'] or '' }}"
            >

            <label>เงินเดือน</label>

            <input
                name="salary"
                type="number"
                step="0.01"
                value="{{ employee['salary'] }}"
            >

            <button class="btn green">
                💾 บันทึกการแก้ไข
            </button>

        </form>

        </div>
        """,
        employee=employee
    )


@app.route("/employees/delete/<employee_id>")
@accounting_required
def delete_employee(employee_id):

    conn = get_db()

    conn.execute("""
        UPDATE employees
        SET active = 0
        WHERE id = ?
    """, (employee_id,))

    conn.commit()
    conn.close()

    return redirect("/employees")


# =========================================================
# ATTENDANCE
# =========================================================

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():

    conn = get_db()

    employees = conn.execute("""
        SELECT *
        FROM employees
        WHERE active = 1
        ORDER BY id
    """).fetchall()

    if request.method == "POST":

        employee_id = request.form.get(
            "employee_id",
            ""
        ).strip()

        action = request.form.get(
            "action",
            ""
        ).strip()

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        inside, location, distance = check_location(
            latitude,
            longitude
        )

        # ต้องตรวจ GPS ก่อนลงเวลา
        if not inside:

            conn.close()

            return render_page(
                "ตรวจสอบตำแหน่ง",
                """
                <div class="card">

                    <h2>📍 ไม่สามารถลงเวลาได้</h2>

                    {% if location == "-" %}

                    <div class="notice">
                        ❌ ไม่ได้รับตำแหน่ง GPS
                    </div>

                    <p>
                        กรุณากด "ตรวจตำแหน่ง"
                        และอนุญาตให้เบราว์เซอร์เข้าถึงตำแหน่ง
                    </p>

                    {% else %}

                    <div class="notice">
                        ❌ {{ location }}
                    </div>

                    <p>
                        ระบบอนุญาตให้ลงเวลา
                        เฉพาะบริเวณโรงเรียนภายใน 300 เมตร
                    </p>

                    {% endif %}

                    <a
                        class="btn"
                        href="/attendance"
                    >
                        กลับไปลงเวลา
                    </a>

                </div>
                """,
                location=location
            )

        employee = conn.execute("""
            SELECT *
            FROM employees
            WHERE id = ?
              AND active = 1
        """, (employee_id,)).fetchone()

        if not employee:

            conn.close()

            return render_page(
                "ข้อผิดพลาด",
                """
                <div class="card">
                    <h2>❌ ไม่พบพนักงาน</h2>
                    <a class="btn" href="/attendance">
                        กลับ
                    </a>
                </div>
                """
            )

        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%H:%M:%S")

        existing = conn.execute("""
            SELECT *
            FROM attendance
            WHERE employee_id = ?
              AND date = ?
            ORDER BY id DESC
            LIMIT 1
        """, (
            employee_id,
            today
        )).fetchone()

        if action == "in":

            if existing and existing["time_in"]:

                conn.close()

                return render_page(
                    "ลงเวลา",
                    """
                    <div class="card">
                        <h2>⚠️ ลงเวลาเข้าแล้ว</h2>
                        <p>
                            พนักงานคนนี้มีเวลาเข้า
                            ในวันนี้แล้ว
                        </p>
                        <a class="btn" href="/attendance">
                            กลับ
                        </a>
                    </div>
                    """
                )

            status = calculate_status(now)

            conn.execute("""
                INSERT INTO attendance
                (
                    employee_id,
                    date,
                    time_in,
                    status,
                    location,
                    distance_km
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                employee_id,
                today,
                now,
                status,
                location,
                distance or 0
            ))

            conn.commit()

        elif action == "out":

            if not existing or not existing["time_in"]:

                conn.close()

                return render_page(
                    "ลงเวลา",
                    """
                    <div class="card">
                        <h2>⚠️ ยังไม่มีเวลาเข้า</h2>
                        <p>
                            ต้องลงเวลาเข้าก่อน
                            จึงจะลงเวลาออกได้
                        </p>
                        <a class="btn" href="/attendance">
                            กลับ
                        </a>
                    </div>
                    """
                )

            if existing["time_out"]:

                conn.close()

                return render_page(
                    "ลงเวลา",
                    """
                    <div class="card">
                        <h2>⚠️ ลงเวลาออกแล้ว</h2>
                        <a class="btn" href="/attendance">
                            กลับ
                        </a>
                    </div>
                    """
                )

            work_hours = calculate_work_hours(
                existing["time_in"],
                now
            )

            ot_hours = calculate_ot(work_hours)

            conn.execute("""
                UPDATE attendance
                SET time_out = ?,
                    work_hours = ?,
                    ot_hours = ?
                WHERE id = ?
            """, (
                now,
                work_hours,
                ot_hours,
                existing["id"]
            ))

            conn.commit()

    today = datetime.now().strftime("%Y-%m-%d")

    records = conn.execute("""
        SELECT
            a.*,
            e.name AS employee_name
        FROM attendance a
        LEFT JOIN employees e
            ON a.employee_id = e.id
        WHERE a.date = ?
        ORDER BY a.id DESC
    """, (today,)).fetchall()

    conn.close()

    return render_page(
        "ลงเวลา",
        """
        <h1>⏰ ลงเวลาเข้า–ออก</h1>

        <div class="card">

            <h2>📝 ลงเวลาพนักงาน</h2>

            <form
                method="POST"
                id="attendanceForm"
            >

                <label>รหัสพนักงาน</label>

                <select
                    name="employee_id"
                    required
                >

                    <option value="">
                        -- เลือกพนักงาน --
                    </option>

                    {% for e in employees %}

                    <option value="{{ e['id'] }}">
                        {{ e['id'] }} - {{ e['name'] }}
                    </option>

                    {% endfor %}

                </select>

                <input
                    type="hidden"
                    name="latitude"
                    id="latitude"
                >

                <input
                    type="hidden"
                    name="longitude"
                    id="longitude"
                >

                <button
                    type="button"
                    class="btn blue"
                    onclick="getLocation()"
                >
                    📍 ตรวจตำแหน่ง
                </button>

                <div
                    id="gpsStatus"
                    class="gps-box"
                >
                    กด "ตรวจตำแหน่ง" ก่อนลงเวลา
                </div>

                <button
                    class="btn green"
                    name="action"
                    value="in"
                    type="submit"
                    onclick="return checkGPS()"
                >
                    🟢 เข้างาน
                </button>

                <button
                    class="btn gray"
                    name="action"
                    value="out"
                    type="submit"
                    onclick="return checkGPS()"
                >
                    🔴 ออกงาน
                </button>

            </form>

        </div>

        <div class="card">

            <h2>📋 การลงเวลาวันนี้</h2>

            <div style="overflow-x:auto">

            <table>

                <tr>
                    <th>พนักงาน</th>
                    <th>เข้า</th>
                    <th>ออก</th>
                    <th>สถานะ</th>
                    <th>ชั่วโมง</th>
                    <th>OT</th>
                    <th>สถานที่</th>
                </tr>

                {% for r in records %}

                <tr>

                    <td>
                        {{ r["employee_id"] }}
                        <br>
                        <span class="small">
                            {{ r["employee_name"] or "-" }}
                        </span>
                    </td>

                    <td>
                        {{ r["time_in"] or "-" }}
                    </td>

                    <td>
                        {{ r["time_out"] or "-" }}
                    </td>

                    <td>

                        {% if r["status"] == "มาสาย" %}

                        <span class="badge late">
                            มาสาย
                        </span>

                        {% elif r["status"] == "ปกติ" %}

                        <span class="badge normal">
                            ปกติ
                        </span>

                        {% else %}

                        <span class="badge">
                            -
                        </span>

                        {% endif %}

                    </td>

                    <td>
                        {{ "%.2f"|format(r["work_hours"] or 0) }}
                    </td>

                    <td>
                        {{ "%.2f"|format(r["ot_hours"] or 0) }}
                    </td>

                    <td>
                        {{ r["location"] or "-" }}
                    </td>

                </tr>

                {% endfor %}

            </table>

            </div>

        </div>

        <script>

        function getLocation() {

            const status =
                document.getElementById("gpsStatus");

            if (!navigator.geolocation) {

                status.innerHTML =
                    "❌ อุปกรณ์นี้ไม่รองรับ GPS";

                return;
            }

            status.innerHTML =
                "📍 กำลังตรวจตำแหน่ง...";

            navigator.geolocation.getCurrentPosition(

                function(position) {

                    document.getElementById(
                        "latitude"
                    ).value =
                        position.coords.latitude;

                    document.getElementById(
                        "longitude"
                    ).value =
                        position.coords.longitude;

                    const accuracy =
                        Math.round(
                            position.coords.accuracy
                        );

                    status.innerHTML =
                        "✅ ตรวจตำแหน่งสำเร็จ " +
                        "(ความแม่นยำประมาณ " +
                        accuracy +
                        " เมตร)";

                },

                function(error) {

                    status.innerHTML =
                        "❌ ไม่สามารถรับตำแหน่งได้ " +
                        "กรุณาเปิด Location";

                },

                {
                    enableHighAccuracy: true,
                    timeout: 15000,
                    maximumAge: 0
                }
            );
        }


        function checkGPS() {

            const lat =
                document.getElementById(
                    "latitude"
                ).value;

            const lng =
                document.getElementById(
                    "longitude"
                ).value;

            if (!lat || !lng) {

                alert(
                    "กรุณากดตรวจตำแหน่ง GPS ก่อน"
                );

                return false;
            }

            return true;
        }

        </script>
        """,
        employees=employees,
        records=records
    )


# =========================================================
# PAYROLL
# =========================================================

@app.route("/payroll")
@accounting_required
def payroll():

    month = request.args.get(
        "month",
        datetime.now().strftime("%Y-%m")
    )

    conn = get_db()

    employees = conn.execute("""
        SELECT *
        FROM employees
        WHERE active = 1
        ORDER BY id
    """).fetchall()

    payroll_rows = []

    for employee in employees:

        total_ot = conn.execute("""
            SELECT COALESCE(SUM(ot_hours), 0)
            FROM attendance
            WHERE employee_id = ?
              AND substr(date, 1, 7) = ?
        """, (
            employee["id"],
            month
        )).fetchone()[0]

        # คำนวณ OT แบบง่าย
        # เงินเดือน / 30 / 8 * 1.5
        hourly = (
            employee["salary"] / 30 / 8
            if employee["salary"]
            else 0
        )

        ot_pay = total_ot * hourly * 1.5

        total = employee["salary"] + ot_pay

        payroll_rows.append({
            "id": employee["id"],
            "name": employee["name"],
            "salary": employee["salary"],
            "ot_hours": total_ot,
            "ot_pay": ot_pay,
            "total": total
        })

    conn.close()

    return render_page(
        "ฝ่ายบัญชี",
        """
        <h1>💰 ฝ่ายบัญชี</h1>

        <div class="card">

            <form method="GET">

                <label>
                    เดือน
                </label>

                <input
                    type="month"
                    name="month"
                    value="{{ month }}"
                >

                <button class="btn blue">
                    🔎 ดูข้อมูล
                </button>

            </form>

        </div>

        <div class="card">

            <div style="overflow-x:auto">

            <table>

                <tr>
                    <th>รหัส</th>
                    <th>พนักงาน</th>
                    <th>เงินเดือน</th>
                    <th>OT</th>
                    <th>ค่า OT</th>
                    <th>รวม</th>
                </tr>

                {% for r in payroll_rows %}

                <tr>

                    <td>{{ r["id"] }}</td>

                    <td>{{ r["name"] }}</td>

                    <td>
                        {{ "{:,.2f}".format(r["salary"]) }}
                    </td>

                    <td>
                        {{ "%.2f"|format(r["ot_hours"]) }}
                    </td>

                    <td>
                        {{ "{:,.2f}".format(r["ot_pay"]) }}
                    </td>

                    <td>
                        <b>
                        {{ "{:,.2f}".format(r["total"]) }}
                        </b>
                    </td>

                </tr>

                {% endfor %}

            </table>

            </div>

        </div>

        <div class="card">

            <h2>ℹ️ การคำนวณ</h2>

            <p>
                ค่า OT คำนวณจากอัตราค่าจ้างต่อชั่วโมง
                × 1.5 × จำนวนชั่วโมง OT
            </p>

            <p class="small">
                ระบบนี้เป็นระบบโครงงานสำหรับการคำนวณ
                และจัดการข้อมูลเบื้องต้น
            </p>

        </div>
        """,
        month=month,
        payroll_rows=payroll_rows
    )


# =========================================================
# MANUAL / คู่มือ
# =========================================================

@app.route("/manual")
@login_required
def manual():

    return render_page(
        "คู่มือการใช้งาน",
        """
        <h1>📖 คู่มือการใช้งาน</h1>

        <div class="card">

            <h2>1. 🔐 การเข้าสู่ระบบ</h2>

            <p>
                ผู้ใช้งานต้องกรอกรหัสที่ได้รับจากผู้ดูแลระบบ
                เพื่อเข้าสู่ระบบ
            </p>

            <p>
                ระบบแบ่งสิทธิ์ออกเป็น
            </p>

            <ul>
                <li>
                    👤 พนักงานทั่วไป
                    สามารถใช้งานการลงเวลาได้
                </li>

                <li>
                    👑 ฝ่ายบัญชี
                    สามารถจัดการข้อมูลพนักงาน
                    และข้อมูลเงินเดือนได้
                </li>
            </ul>

        </div>


        <div class="card">

            <h2>2. ⏰ การลงเวลาเข้า–ออก</h2>

            <ol>

                <li>
                    เลือกรหัสพนักงาน
                </li>

                <li>
                    กด
                    <b>📍 ตรวจตำแหน่ง</b>
                </li>

                <li>
                    อนุญาตให้เว็บไซต์เข้าถึงตำแหน่ง
                </li>

                <li>
                    รอจนขึ้นว่า
                    <b>ตรวจตำแหน่งสำเร็จ</b>
                </li>

                <li>
                    กด
                    <b>🟢 เข้างาน</b>
                    หรือ
                    <b>🔴 ออกงาน</b>
                </li>

            </ol>

        </div>


        <div class="card">

            <h2>3. 📍 ระบบ GPS</h2>

            <p>
                ระบบมีการตรวจสอบตำแหน่งก่อนลงเวลา
                เพื่อช่วยป้องกันการลงเวลาจากนอกพื้นที่
            </p>

            <div class="gps-box">

                <b>🏫 พื้นที่อ้างอิง</b>

                <p>
                    โรงเรียนสวนกุหลาบวิทยาลัย รังสิต
                </p>

                <b>📏 รัศมีที่อนุญาต</b>

                <p>
                    300 เมตร
                </p>

            </div>

            <p>
                หากตำแหน่งอยู่ภายในรัศมีที่กำหนด
                ระบบจะแสดงว่า
            </p>

            <div class="notice">
                ✅ สวนกุหลาบวิทยาลัย รังสิต
                (อยู่ในพื้นที่)
            </div>

            <p>
                หากอยู่ไกลเกินพื้นที่
                ระบบจะแสดงระยะห่างโดยประมาณ เช่น
            </p>

            <div class="notice">
                ❌ อยู่นอกพื้นที่ (3.50 กม.)
            </div>

            <p>
                ระบบใช้การคำนวณระยะทางแบบ
                Haversine เพื่อให้เหมาะกับการคำนวณ
                ระยะห่างระหว่างพิกัดบนโลกมากกว่าสูตร
                แบบคำนวณตรง ๆ
            </p>

            <p class="small">
                หมายเหตุ:
                GPS ของโทรศัพท์หรือแท็บเล็ตอาจมีความคลาดเคลื่อน
                โดยเฉพาะเมื่ออยู่ภายในอาคาร
            </p>

        </div>


        <div class="card">

            <h2>4. 🚨 การเช็กมาสาย</h2>

            <p>
                ระบบกำหนดเวลาเริ่มงานเป็น
                <b>08:00 น.</b>
            </p>

            <ul>

                <li>
                    เข้าเวลาไม่เกิน 08:00
                    → <b>ปกติ</b>
                </li>

                <li>
                    หลัง 08:00
                    → <b>มาสาย</b>
                </li>

            </ul>

        </div>


        <div class="card">

            <h2>5. ⏱️ ชั่วโมงทำงานและ OT</h2>

            <p>
                เมื่อพนักงานลงเวลาออก
                ระบบจะคำนวณจำนวนชั่วโมงทำงานให้อัตโนมัติ
            </p>

            <p>
                หากทำงานเกิน 8 ชั่วโมง
                ส่วนที่เกินจะถูกนับเป็น OT
            </p>

        </div>


        <div class="card">

            <h2>6. 💰 ฝ่ายบัญชี</h2>

            <p>
                ฝ่ายบัญชีสามารถ
            </p>

            <ul>

                <li>
                    เพิ่มพนักงาน
                </li>

                <li>
                    แก้ไขข้อมูลพนักงาน
                </li>

                <li>
                    ลบ/ปิดใช้งานพนักงาน
                </li>

                <li>
                    กำหนดเงินเดือน
                </li>

                <li>
                    ดูจำนวน OT
                </li>

                <li>
                    ดูยอดเงินเดือนรวม
                </li>

            </ul>

        </div>


        <div class="card">

            <h2>7. 📱 การใช้งานบนมือถือ</h2>

            <p>
                ระบบออกแบบให้รองรับโทรศัพท์
                และแท็บเล็ต เช่น iPhone และ iPad
            </p>

            <p>
                สามารถเปิดผ่านเบราว์เซอร์
                แล้วเพิ่มเว็บไซต์ไว้ที่หน้าจอหลักได้
            </p>

        </div>


        <div class="card">

            <h2>8. ⚠️ หาก GPS ไม่ทำงาน</h2>

            <ol>

                <li>
                    ตรวจสอบว่าเปิด Location แล้ว
                </li>

                <li>
                    อนุญาต Location ให้เบราว์เซอร์
                </li>

                <li>
                    อยู่ในบริเวณที่รับสัญญาณ GPS ได้
                </li>

                <li>
                    กดตรวจตำแหน่งใหม่อีกครั้ง
                </li>

            </ol>

        </div>


        <div class="card">

            <h2>9. 🔒 ความปลอดภัย</h2>

            <p>
                ผู้ที่ไม่มีรหัสเข้าสู่ระบบจะไม่สามารถ
                เข้าหน้าระบบได้
            </p>

            <p>
                ส่วนจัดการข้อมูลพนักงานและฝ่ายบัญชี
                จำกัดไว้สำหรับบัญชีฝ่ายบัญชี
            </p>

        </div>

        """
    )


# =========================================================
# HEALTH CHECK FOR RENDER
# =========================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "pizza-company-system"
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return render_page(
        "ไม่พบหน้า",
        """
        <div class="card center">

            <h1>404</h1>

            <h2>
                ไม่พบหน้าที่ต้องการ
            </h2>

            <a class="btn" href="/">
                🏠 กลับหน้าหลัก
            </a>

        </div>
        """
    ), 404


@app.errorhandler(500)
def server_error(error):

    return render_page(
        "เกิดข้อผิดพลาด",
        """
        <div class="card center">

            <h2>
                ❌ เกิดข้อผิดพลาดในระบบ
            </h2>

            <p>
                กรุณาลองใหม่อีกครั้ง
            </p>

            <a class="btn" href="/">
                🏠 กลับหน้าหลัก
            </a>

        </div>
        """
    ), 500


# =========================================================
# START
# =========================================================

init_db()


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
    