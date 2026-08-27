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
# COMPIZZ - CONFIG
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "compizz-school-project-secret"
)

DB = os.environ.get(
    "DB_PATH",
    "compizz.db"
)

# =========================================================
# GPS CONFIG
# =========================================================

# โรงเรียนสวนกุหลาบวิทยาลัย รังสิต
# พิกัดอ้างอิงจากข้อมูลสถานศึกษา
SKR_LAT = 14.02308271
SKR_LNG = 100.67582120

# อนุญาตภายใน 300 เมตร
ALLOWED_DISTANCE_KM = 0.3

# เวลาเริ่มงาน
WORK_START = "08:00"

# =========================================================
# LOGIN CONFIG
# =========================================================

# พนักงานทั่วไปไม่ต้อง Login
# Admin / ฝ่ายบัญชี ต้องใช้รหัส
ADMIN_PIN = os.environ.get(
    "ADMIN_PIN",
    "9999"
)


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
            distance_km REAL DEFAULT 0
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

    count = cur.execute("""
        SELECT COUNT(*)
        FROM employees
    """).fetchone()[0]

    if count == 0:

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

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
# AUTHENTICATION
# =========================================================

def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(
                url_for("admin_login")
            )

        return view(*args, **kwargs)

    return wrapped


# =========================================================
# GPS
# =========================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):
    """
    คำนวณระยะทางระหว่างพิกัด GPS
    ผลลัพธ์เป็นกิโลเมตร
    """

    earth_radius = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    delta_lat = math.radians(
        lat2 * 180 / math.pi
        - lat1 * 180 / math.pi
    )

    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c


def check_location(
    latitude,
    longitude
):

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

            return (
                True,
                "สวนกุหลาบวิทยาลัย รังสิต (อยู่ในพื้นที่)",
                distance
            )

        return (
            False,
            f"อยู่นอกพื้นที่ ({distance:.2f} กม.)",
            distance
        )

    except (
        ValueError,
        TypeError
    ):

        return False, "-", None


# =========================================================
# TIME CALCULATION
# =========================================================

def calculate_work_hours(
    time_in,
    time_out
):

    if not time_in or not time_out:
        return 0

    try:

        start = datetime.strptime(
            time_in,
            "%H:%M:%S"
        )

        end = datetime.strptime(
            time_out,
            "%H:%M:%S"
        )

        if end < start:
            end += timedelta(days=1)

        seconds = (
            end - start
        ).total_seconds()

        return round(
            seconds / 3600,
            2
        )

    except Exception:
        return 0


def calculate_ot(work_hours):

    if work_hours <= 8:
        return 0

    return round(
        work_hours - 8,
        2
    )


def calculate_status(time_in):

    if not time_in:
        return "-"

    try:

        actual_time = datetime.strptime(
            time_in,
            "%H:%M:%S"
        ).time()

        start_time = datetime.strptime(
            WORK_START,
            "%H:%M"
        ).time()

        if actual_time <= start_time:
            return "ปกติ"

        return "มาสาย"

    except Exception:
        return "-"


# =========================================================
# BASE HTML
# =========================================================

BASE_HTML = """
<!DOCTYPE html>

<html lang="th">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
    {{ title }} - Compizz
</title>

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

    background:
        linear-gradient(
            180deg,
            #fff5f6 0%,
            #f5f6f8 40%,
            #f3f4f6 100%
        );

    color: #202124;

    padding-bottom: 90px;
}


/* HEADER */

.header {

    background:
        linear-gradient(
            135deg,
            #c8102e,
            #e31937
        );

    color: white;

    padding: 16px 20px;

    font-size: 21px;

    font-weight: 800;

    box-shadow:
        0 4px 15px
        rgba(200, 16, 46, 0.20);
}


/* CONTAINER */

.container {

    width: 94%;

    max-width: 1100px;

    margin:
        20px auto;
}


/* HERO */

.hero {

    position: relative;

    overflow: hidden;

    background:
        linear-gradient(
            135deg,
            #b90025,
            #e51b3e
        );

    color: white;

    border-radius: 28px;

    padding: 32px 24px;

    margin-bottom: 20px;

    box-shadow:
        0 12px 35px
        rgba(200, 16, 46, 0.25);
}

.hero::after {

    content: "";

    position: absolute;

    width: 170px;
    height: 170px;

    right: -50px;
    top: -50px;

    background:
        rgba(255,255,255,0.10);

    border-radius: 50%;
}

.hero-logo {

    font-size: 52px;

    margin-bottom: 5px;
}

.hero-title {

    font-size: 35px;

    font-weight: 900;

    margin: 0;
}

.hero-subtitle {

    margin:
        8px 0 20px;

    opacity: 0.92;

    font-size: 15px;
}


/* CARDS */

.card {

    background: white;

    border-radius: 20px;

    padding: 20px;

    margin-bottom: 18px;

    box-shadow:
        0 4px 20px
        rgba(0,0,0,0.07);
}

.card h2 {

    margin-top: 0;
}


/* GRID */

.grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );

    gap: 14px;

    margin-bottom: 18px;
}


/* STAT */

.stat {

    background: white;

    border-radius: 18px;

    padding: 18px;

    box-shadow:
        0 4px 16px
        rgba(0,0,0,0.06);
}

.stat-icon {

    font-size: 27px;
}

.stat-number {

    font-size: 28px;

    font-weight: 900;

    color: #c8102e;

    margin-top: 5px;
}


/* BUTTON */

.btn {

    display: inline-block;

    border: none;

    border-radius: 12px;

    padding:
        12px 17px;

    background: #c8102e;

    color: white;

    text-decoration: none;

    cursor: pointer;

    font-size: 15px;

    font-weight: 700;

    margin: 3px;

    transition:
        transform 0.15s,
        opacity 0.15s;
}

.btn:hover {

    opacity: 0.9;

    transform:
        translateY(-1px);
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


/* BIG BUTTON */

.big-btn {

    display: block;

    width: 100%;

    text-align: center;

    padding: 18px;

    margin: 8px 0;

    border-radius: 16px;

    color: white;

    text-decoration: none;

    font-weight: 800;

    font-size: 18px;

    box-shadow:
        0 5px 15px
        rgba(0,0,0,0.10);
}


/* INPUT */

input,
select {

    width: 100%;

    padding: 13px;

    border:
        1px solid #ddd;

    border-radius: 11px;

    font-size: 16px;

    margin:
        6px 0 14px;

    background: white;
}

label {

    font-weight: 700;
}


/* TABLE */

.table-wrap {

    overflow-x: auto;
}

table {

    width: 100%;

    border-collapse: collapse;

    background: white;
}

th,
td {

    padding:
        11px 8px;

    border-bottom:
        1px solid #eee;

    text-align: left;

    white-space: nowrap;
}

th {

    background: #f1f2f4;

    font-weight: 800;
}


/* BADGE */

.badge {

    display: inline-block;

    padding:
        5px 10px;

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


/* GPS */

.gps-box {

    padding: 15px;

    background:
        linear-gradient(
            135deg,
            #f5f8ff,
            #f9fafb
        );

    border:
        1px solid #e2e7ef;

    border-radius: 15px;

    margin:
        10px 0 15px;
}

.gps-success {

    background: #e6f8ec;

    color: #08752d;
}

.gps-warning {

    background: #fff5df;

    color: #8a5800;
}


/* NOTICE */

.notice {

    padding: 14px;

    border-radius: 13px;

    margin: 10px 0;

    background: #eef5ff;
}


/* MANUAL */

.manual-item {

    padding: 15px;

    border-radius: 15px;

    background: #f8f9fa;

    margin:
        10px 0;
}

.manual-number {

    display: inline-flex;

    width: 32px;
    height: 32px;

    align-items: center;
    justify-content: center;

    border-radius: 50%;

    background: #c8102e;

    color: white;

    font-weight: 800;

    margin-right: 8px;
}


/* BOTTOM NAV */

.bottom-nav {

    position: fixed;

    bottom: 0;

    left: 0;
    right: 0;

    height: 72px;

    background: white;

    border-top:
        1px solid #ddd;

    display: flex;

    justify-content:
        space-around;

    align-items: center;

    z-index: 999;

    box-shadow:
        0 -4px 20px
        rgba(0,0,0,0.08);
}

.bottom-nav a {

    color: #333;

    text-decoration: none;

    text-align: center;

    font-size: 11px;
}

.bottom-nav span {

    display: block;

    font-size: 21px;

    margin-bottom: 2px;
}


/* ADMIN */

.admin-banner {

    background:
        linear-gradient(
            135deg,
            #222,
            #424242
        );

    color: white;

    border-radius: 18px;

    padding: 18px;

    margin-bottom: 18px;
}


/* CENTER */

.center {
    text-align: center;
}

.small {

    font-size: 13px;

    color: #777;
}


/* MOBILE */

@media(max-width: 700px) {

    .container {
        width: 92%;
    }

    .hero-title {
        font-size: 30px;
    }

    th,
    td {
        font-size: 13px;
    }

}

</style>

</head>


<body>


<div class="header">

    🍕 Compizz

</div>


<div class="container">

    {{ content|safe }}

</div>


{% if show_nav %}

<div class="bottom-nav">

    <a href="/">
        <span>🏠</span>
        หน้าแรก
    </a>

    <a href="/attendance">
        <span>⏰</span>
        ลงเวลา
    </a>

    <a href="/manual">
        <span>📖</span>
        คู่มือ
    </a>

    {% if session.get("admin_logged_in") %}

    <a href="/admin">
        <span>⚙️</span>
        จัดการ
    </a>

    <a href="/admin/logout">
        <span>🔐</span>
        ออก
    </a>

    {% else %}

    <a href="/admin-login">
        <span>🔐</span>
        ผู้ดูแล
    </a>

    {% endif %}

</div>

{% endif %}


</body>

</html>
"""


def render_page(
    title,
    content,
    show_nav=True,
    **context
):

    rendered_content = render_template_string(
        content,
        **context
    )

    return render_template_string(
        BASE_HTML,
        title=title,
        content=rendered_content,
        show_nav=show_nav
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    conn = get_db()

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    employee_count = conn.execute("""
        SELECT COUNT(*)
        FROM employees
        WHERE active = 1
    """).fetchone()[0]

    today_count = conn.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE date = ?
    """, (
        today,
    )).fetchone()[0]

    conn.close()

    return render_page(
        "หน้าแรก",
        """
        <div class="hero">

            <div class="hero-logo">
                🍕
            </div>

            <div class="hero-title">
                Compizz
            </div>

            <div class="hero-subtitle">
                ระบบจัดการพนักงานและลงเวลาทำงาน
                สำหรับการใช้งานที่สะดวกและเป็นระบบ
            </div>

            <a
                href="/attendance"
                class="big-btn"
                style="background:white;color:#c8102e;"
            >
                ⏰ ลงเวลาเข้า–ออก
            </a>

        </div>


        <div class="grid">

            <div class="stat">

                <div class="stat-icon">
                    👥
                </div>

                <div>
                    พนักงาน
                </div>

                <div class="stat-number">
                    {{ employee_count }}
                </div>

            </div>


            <div class="stat">

                <div class="stat-icon">
                    ⏰
                </div>

                <div>
                    ลงเวลาวันนี้
                </div>

                <div class="stat-number">
                    {{ today_count }}
                </div>

            </div>

        </div>


        <div class="card">

            <h2>
                ✨ เมนูการใช้งาน
            </h2>

            <a
                href="/attendance"
                class="big-btn"
                style="background:#c8102e;"
            >
                🟢 ลงเวลาเข้า–ออก
            </a>

            <a
                href="/manual"
                class="big-btn"
                style="background:#1769e0;"
            >
                📖 คู่มือการใช้งาน
            </a>

            <a
                href="/admin-login"
                class="big-btn"
                style="background:#59636e;"
            >
                🔐 เข้าระบบผู้ดูแล / ฝ่ายบัญชี
            </a>

        </div>


        <div class="card">

            <h2>
                📍 ระบบ GPS
            </h2>

            <p>
                ก่อนลงเวลา ระบบจะตรวจสอบตำแหน่ง
                เพื่อยืนยันว่าผู้ใช้งานอยู่ในพื้นที่
                ที่กำหนด
            </p>

            <p class="small">
                ไม่แสดงพิกัด GPS ดิบบนหน้าจอ
            </p>

        </div>
        """,
        employee_count=employee_count,
        today_count=today_count
    )


# =========================================================
# ATTENDANCE
# =========================================================

@app.route(
    "/attendance",
    methods=["GET", "POST"]
)
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

        latitude = request.form.get(
            "latitude"
        )

        longitude = request.form.get(
            "longitude"
        )


        inside, location, distance = check_location(
            latitude,
            longitude
        )


        # GPS ไม่ผ่าน
        if not inside:

            conn.close()

            return render_page(
                "ตรวจสอบ GPS",
                """
                <div class="card">

                    <div class="center">

                        <div style="font-size:55px;">
                            📍
                        </div>

                        <h2>
                            ไม่สามารถลงเวลาได้
                        </h2>

                    </div>


                    {% if location == "-" %}

                    <div class="notice gps-warning">

                        ❌
                        ไม่ได้รับข้อมูลตำแหน่ง GPS

                    </div>

                    <p>
                        กรุณากด
                        <b>ตรวจตำแหน่ง</b>
                        และอนุญาตให้เว็บไซต์
                        เข้าถึงตำแหน่งของอุปกรณ์
                    </p>

                    {% else %}

                    <div class="notice gps-warning">

                        ❌
                        {{ location }}

                    </div>

                    <p>
                        ระบบกำหนดพื้นที่ลงเวลาไว้ภายใน
                        <b>300 เมตร</b>
                        จากจุดอ้างอิงของโรงเรียน
                    </p>

                    {% endif %}


                    <a
                        href="/attendance"
                        class="btn"
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
        """, (
            employee_id,
        )).fetchone()


        if not employee:

            conn.close()

            return render_page(
                "ข้อผิดพลาด",
                """
                <div class="card center">

                    <h2>
                        ❌ ไม่พบพนักงาน
                    </h2>

                    <a
                        class="btn"
                        href="/attendance"
                    >
                        กลับ
                    </a>

                </div>
                """
            )


        today = datetime.now().strftime(
            "%Y-%m-%d"
        )

        now = datetime.now().strftime(
            "%H:%M:%S"
        )


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


        # -------------------------
        # CHECK IN
        # -------------------------

        if action == "in":

            if existing and existing["time_in"]:

                conn.close()

                return render_page(
                    "ลงเวลา",
                    """
                    <div class="card center">

                        <div style="font-size:50px;">
                            ⚠️
                        </div>

                        <h2>
                            ลงเวลาเข้าแล้ว
                        </h2>

                        <p>
                            พนักงานคนนี้มีเวลาเข้า
                            ในวันนี้แล้ว
                        </p>

                        <a
                            class="btn"
                            href="/attendance"
                        >
                            กลับ
                        </a>

                    </div>
                    """
                )


            status = calculate_status(
                now
            )


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


        # -------------------------
        # CHECK OUT
        # -------------------------

        elif action == "out":

            if not existing or not existing["time_in"]:

                conn.close()

                return render_page(
                    "ลงเวลา",
                    """
                    <div class="card center">

                        <div style="font-size:50px;">
                            ⚠️
                        </div>

                        <h2>
                            ยังไม่มีเวลาเข้างาน
                        </h2>

                        <p>
                            ต้องลงเวลาเข้าก่อน
                            จึงจะลงเวลาออกได้
                        </p>

                        <a
                            class="btn"
                            href="/attendance"
                        >
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
                    <div class="card center">

                        <h2>
                            ⚠️ ลงเวลาออกแล้ว
                        </h2>

                        <a
                            class="btn"
                            href="/attendance"
                        >
                            กลับ
                        </a>

                    </div>
                    """
                )


            work_hours = calculate_work_hours(
                existing["time_in"],
                now
            )

            ot_hours = calculate_ot(
                work_hours
            )


            conn.execute("""
                UPDATE attendance

                SET
                    time_out = ?,
                    work_hours = ?,
                    ot_hours = ?,
                    location = ?,
                    distance_km = ?

                WHERE id = ?
            """, (
                now,
                work_hours,
                ot_hours,
                location,
                distance or 0,
                existing["id"]
            ))

            conn.commit()


    today = datetime.now().strftime(
        "%Y-%m-%d"
    )


    records = conn.execute("""
        SELECT
            a.*,
            e.name AS employee_name

        FROM attendance a

        LEFT JOIN employees e
            ON a.employee_id = e.id

        WHERE a.date = ?

        ORDER BY a.id DESC
    """, (
        today,
    )).fetchall()


    conn.close()


    return render_page(
        "ลงเวลา",
        """
        <h1>
            ⏰ ลงเวลาเข้า–ออก
        </h1>


        <div class="card">

            <h2>
                📝 ลงเวลาพนักงาน
            </h2>


            <form
                method="POST"
                id="attendanceForm"
            >

                <label>
                    รหัสพนักงาน
                </label>

                <select
                    name="employee_id"
                    required
                >

                    <option value="">
                        -- เลือกพนักงาน --
                    </option>

                    {% for e in employees %}

                    <option value="{{ e['id'] }}">

                        {{ e['id'] }}
                        -
                        {{ e['name'] }}

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
                    กด "ตรวจตำแหน่ง"
                    ก่อนลงเวลา
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

            <h2>
                📋 การลงเวลาวันนี้
            </h2>


            <div class="table-wrap">

            <table>

                <tr>

                    <th>
                        พนักงาน
                    </th>

                    <th>
                        เข้า
                    </th>

                    <th>
                        ออก
                    </th>

                    <th>
                        สถานะ
                    </th>

                    <th>
                        ชั่วโมง
                    </th>

                    <th>
                        OT
                    </th>

                    <th>
                        สถานที่
                    </th>

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
                        {{ "%.2f"|format(
                            r["work_hours"] or 0
                        ) }}
                    </td>


                    <td>
                        {{ "%.2f"|format(
                            r["ot_hours"] or 0
                        ) }}
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
                document.getElementById(
                    "gpsStatus"
                );


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


                    status.className =
                        "gps-box gps-success";


                    status.innerHTML =
                        "✅ ตรวจตำแหน่งสำเร็จ " +
                        "(ความแม่นยำประมาณ " +
                        accuracy +
                        " เมตร)";

                },


                function(error) {

                    status.className =
                        "gps-box gps-warning";


                    status.innerHTML =
                        "❌ ไม่สามารถรับตำแหน่งได้ " +
                        "กรุณาเปิด Location " +
                        "และอนุญาตให้เบราว์เซอร์ใช้ตำแหน่ง";

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
                    "กรุณากดตรวจตำแหน่ง GPS ก่อนลงเวลา"
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
# MANUAL
# =========================================================

@app.route("/manual")
def manual():

    return render_page(
        "คู่มือ",
        """
        <h1>
            📖 คู่มือการใช้งาน Compizz
        </h1>


        <div class="card">

            <h2>
                1. 🏠 เริ่มต้นใช้งาน
            </h2>

            <div class="manual-item">

                เปิดเว็บไซต์ Compizz
                แล้วสามารถเลือก
                <b>ลงเวลาเข้า–ออก</b>
                ได้ทันที

            </div>

            <p>
                พนักงานทั่วไปไม่ต้องกรอกรหัส
                เพื่อเข้าสู่หน้าลงเวลา
            </p>

        </div>


        <div class="card">

            <h2>
                2. ⏰ วิธีลงเวลา
            </h2>

            <ol>

                <li>
                    เลือกรหัสพนักงาน
                </li>

                <li>
                    กด
                    <b>📍 ตรวจตำแหน่ง</b>
                </li>

                <li>
                    อนุญาตให้เว็บไซต์ใช้ Location
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

            <h2>
                3. 📍 คู่มือระบบ GPS
            </h2>


            <div class="manual-item">

                <b>
                    ขั้นตอนที่ 1
                </b>

                <p>
                    เลือกรหัสพนักงานก่อน
                </p>

            </div>


            <div class="manual-item">

                <b>
                    ขั้นตอนที่ 2
                </b>

                <p>
                    กดปุ่ม
                    <b>📍 ตรวจตำแหน่ง</b>
                </p>

            </div>


            <div class="manual-item">

                <b>
                    ขั้นตอนที่ 3
                </b>

                <p>
                    หากอุปกรณ์ถามว่า
                    อนุญาตให้เว็บไซต์เข้าถึงตำแหน่งหรือไม่
                    ให้กดอนุญาต
                </p>

            </div>


            <div class="manual-item">

                <b>
                    ขั้นตอนที่ 4
                </b>

                <p>
                    รอจนระบบตรวจตำแหน่งสำเร็จ
                </p>

            </div>


            <div class="manual-item">

                <b>
                    ขั้นตอนที่ 5
                </b>

                <p>
                    กดเข้างานหรือออกงาน
                    หลังจากตรวจตำแหน่งสำเร็จ
                </p>

            </div>


            <div class="gps-box">

                <h3>
                    🏫 พื้นที่อ้างอิง
                </h3>

                <p>
                    โรงเรียนสวนกุหลาบวิทยาลัย รังสิต
                </p>


                <h3>
                    📏 ระยะที่อนุญาต
                </h3>

                <p>
                    ภายในรัศมี
                    <b>300 เมตร</b>
                </p>

            </div>


            <h3>
                ✅ ถ้าอยู่ในพื้นที่
            </h3>

            <div class="notice gps-success">

                ระบบจะแสดงว่า

                <br><br>

                <b>
                    สวนกุหลาบวิทยาลัย รังสิต
                    (อยู่ในพื้นที่)
                </b>

            </div>


            <h3>
                ❌ ถ้าอยู่นอกพื้นที่
            </h3>

            <div class="notice gps-warning">

                ระบบจะแสดงระยะห่าง เช่น

                <br><br>

                <b>
                    อยู่นอกพื้นที่ (3.50 กม.)
                </b>

            </div>


            <h3>
                🧭 ระบบคำนวณระยะอย่างไร?
            </h3>

            <p>
                Compizz ใช้การคำนวณระยะทางแบบ
                <b>Haversine</b>
                เพื่อคำนวณระยะห่างระหว่าง
                ตำแหน่ง GPS ของอุปกรณ์กับจุดอ้างอิง
                ของโรงเรียน
            </p>


            <h3>
                📱 ถ้า GPS ไม่ตรงทำอย่างไร?
            </h3>

            <ol>

                <li>
                    เปิด Location ของโทรศัพท์หรือ iPad
                </li>

                <li>
                    อนุญาต Location ให้ Safari/Chrome
                </li>

                <li>
                    ออกจากอาคารหรือบริเวณที่สัญญาณ GPS อ่อน
                    หากทำได้
                </li>

                <li>
                    กด
                    <b>ตรวจตำแหน่ง</b>
                    ใหม่อีกครั้ง
                </li>

            </ol>


            <div class="notice">

                💡 GPS ของโทรศัพท์และแท็บเล็ต
                อาจมีความคลาดเคลื่อนจากสภาพแวดล้อม
                เช่น อาคารหรือสัญญาณดาวเทียม

            </div>

        </div>


        <div class="card">

            <h2>
                4. 🚨 การเช็กมาสาย
            </h2>

            <p>
                เวลาเริ่มงานที่กำหนดคือ
                <b>08:00 น.</b>
            </p>

            <div class="manual-item">

                🟢
                เข้างานไม่เกิน 08:00
                →
                <b>ปกติ</b>

            </div>

            <div class="manual-item">

                🔴
                เข้างานหลัง 08:00
                →
                <b>มาสาย</b>

            </div>

        </div>


        <div class="card">

            <h2>
                5. ⏱️ ชั่วโมงทำงานและ OT
            </h2>

            <p>
                เมื่อพนักงานลงเวลาออก
                ระบบจะคำนวณชั่วโมงทำงานให้อัตโนมัติ
            </p>

            <p>
                ชั่วโมงที่เกิน 8 ชั่วโมง
                จะถูกนำไปคำนวณเป็น OT
            </p>

        </div>


        <div class="card">

            <h2>
                6. 🔐 ระบบผู้ดูแล
            </h2>

            <p>
                พนักงานทั่วไปสามารถลงเวลาได้
                โดยไม่ต้อง Login
            </p>

            <p>
                ส่วนการจัดการข้อมูล เช่น
            </p>

            <ul>

                <li>
                    👥 พนักงาน
                </li>

                <li>
                    💰 เงินเดือน
                </li>

                <li>
                    📊 ข้อมูลบัญชี
                </li>

                <li>
                    ⚙️ การจัดการระบบ
                </li>

            </ul>

            <p>
                ต้องเข้าสู่ระบบด้วยรหัส
                <b>Admin / ฝ่ายบัญชี</b>
            </p>

        </div>


        <div class="card">

            <h2>
                7. 📱 การใช้งานบนมือถือ
            </h2>

            <p>
                Compizz ออกแบบให้รองรับ
                โทรศัพท์และแท็บเล็ต
                เช่น iPhone และ iPad
            </p>

            <p>
                สามารถเปิดเว็บไซต์ผ่าน Safari
                หรือเบราว์เซอร์ที่รองรับ GPS ได้
            </p>

        </div>


        <div class="card">

            <h2>
                8. 🔒 ความปลอดภัย
            </h2>

            <p>
                หน้าลงเวลาเปิดให้พนักงานใช้งานได้ง่าย
                แต่หน้าจัดการข้อมูลสำคัญ
                จะต้องผ่านระบบ Admin
            </p>

            <p>
                ระบบ GPS ยังใช้ตรวจสอบพื้นที่
                ก่อนบันทึกการลงเวลา
            </p>

        </div>

        """
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin-login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        pin = request.form.get(
            "pin",
            ""
        ).strip()


        if pin == ADMIN_PIN:

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin")
            )


        return render_page(
            "เข้าสู่ระบบผู้ดูแล",
            """
            <div class="card center">

                <div style="font-size:55px;">
                    🔐
                </div>

                <h2>
                    รหัสไม่ถูกต้อง
                </h2>

                <a
                    class="btn"
                    href="/admin-login"
                >
                    ลองอีกครั้ง
                </a>

            </div>
            """,
            show_nav=False
        )


    return render_page(
        "ผู้ดูแลระบบ",
        """
        <div
            class="card"
            style="max-width:430px;margin:50px auto;"
        >

            <div class="center">

                <div style="font-size:60px;">
                    🔐
                </div>

                <h1>
                    Compizz
                </h1>

                <p>
                    ผู้ดูแลระบบ / ฝ่ายบัญชี
                </p>

            </div>


            <form method="POST">

                <label>
                    รหัสผู้ดูแล
                </label>

                <input
                    type="password"
                    name="pin"
                    inputmode="numeric"
                    placeholder="กรอกรหัส"
                    required
                >


                <button
                    class="btn"
                    style="width:100%;"
                >
                    เข้าสู่ระบบ
                </button>

            </form>


            <div class="notice">

                ℹ️
                หน้านี้สำหรับ Admin
                หรือฝ่ายบัญชีเท่านั้น

            </div>


            <a
                class="btn gray"
                href="/"
            >
                กลับหน้าหลัก
            </a>

        </div>
        """,
        show_nav=False
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin():

    conn = get_db()

    employee_count = conn.execute("""
        SELECT COUNT(*)
        FROM employees
        WHERE active = 1
    """).fetchone()[0]


    today = datetime.now().strftime(
        "%Y-%m-%d"
    )


    attendance_count = conn.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE date = ?
    """, (
        today,
    )).fetchone()[0]


    ot_total = conn.execute("""
        SELECT COALESCE(
            SUM(ot_hours),
            0
        )

        FROM attendance

        WHERE date = ?
    """, (
        today,
    )).fetchone()[0]


    salary_total = conn.execute("""
        SELECT COALESCE(
            SUM(salary),
            0
        )

        FROM employees

        WHERE active = 1
    """).fetchone()[0]


    conn.close()


    return render_page(
        "ผู้ดูแลระบบ",
        """
        <div class="admin-banner">

            <h1>
                ⚙️ ระบบจัดการ Compizz
            </h1>

            <p>
                Admin / ฝ่ายบัญชี
            </p>

        </div>


        <div class="grid">

            <div class="stat">

                👥 พนักงาน

                <div class="stat-number">
                    {{ employee_count }}
                </div>

            </div>


            <div class="stat">

                ⏰ ลงเวลาวันนี้

                <div class="stat-number">
                    {{ attendance_count }}
                </div>

            </div>


            <div class="stat">

                ⏱️ OT วันนี้

                <div class="stat-number">
                    {{ "%.2f"|format(ot_total) }}
                </div>

            </div>


            <div class="stat">

                💰 เงินเดือนรวม

                <div class="stat-number">
                    {{ "{:,.2f}".format(
                        salary_total
                    ) }}
                </div>

            </div>

        </div>


        <div class="card">

            <h2>
                ⚙️ จัดการระบบ
            </h2>


            <a
                class="big-btn"
                style="background:#1769e0;"
                href="/employees"
            >
                👥 จัดการพนักงาน
            </a>


            <a
                class="big-btn"
                style="background:#159447;"
                href="/payroll"
            >
                💰 ฝ่ายบัญชี
            </a>


            <a
                class="big-btn"
                style="background:#59636e;"
                href="/attendance"
            >
                📋 ดูการลงเวลา
            </a>


            <a
                class="big-btn"
                style="background:#c8102e;"
                href="/manual"
            >
                📖 คู่มือ
            </a>

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
@admin_required
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
        <h1>
            👥 จัดการพนักงาน
        </h1>


        <div class="card">

            <a
                class="btn green"
                href="/employees/add"
            >
                ➕ เพิ่มพนักงาน
            </a>

        </div>


        <div class="card">

        <div class="table-wrap">

        <table>

            <tr>

                <th>
                    รหัส
                </th>

                <th>
                    ชื่อ
                </th>

                <th>
                    ฝ่าย
                </th>

                <th>
                    เงินเดือน
                </th>

                <th>
                    จัดการ
                </th>

            </tr>


            {% for r in rows %}

            <tr>

                <td>
                    {{ r["id"] }}
                </td>

                <td>
                    {{ r["name"] }}
                </td>

                <td>
                    {{ r["department"] or "-" }}
                </td>

                <td>
                    {{ "{:,.2f}".format(
                        r["salary"]
                    ) }}
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
                        onclick="
                            return confirm(
                                'ยืนยันการลบพนักงาน?'
                            )
                        "
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


# =========================================================
# ADD EMPLOYEE
# =========================================================

@app.route(
    "/employees/add",
    methods=["GET", "POST"]
)
@admin_required
def add_employee():

    if request.method == "POST":

        employee_id = request.form.get(
            "id",
            ""
        ).strip()

        name = request.form.get(
            "name",
            ""
        ).strip()

        department = request.form.get(
            "department",
            "พนักงาน"
        ).strip()


        try:

            salary = float(
                request.form.get(
                    "salary",
                    "0"
                )
            )

        except ValueError:

            salary = 0


        if not employee_id or not name:

            return render_page(
                "เพิ่มพนักงาน",
                """
                <div class="card center">

                    <h2>
                        ❌ กรุณากรอกข้อมูลให้ครบ
                    </h2>

                    <a
                        class="btn"
                        href="/employees/add"
                    >
                        กลับ
                    </a>

                </div>
                """
            )


        conn = get_db()


        try:

            conn.execute("""
                INSERT INTO employees
                (
                    id,
                    name,
                    salary,
                    department,
                    active,
                    created_at
                )

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
                <div class="card center">

                    <h2>
                        ❌ รหัสพนักงานมีอยู่แล้ว
                    </h2>

                    <a
                        class="btn"
                        href="/employees/add"
                    >
                        กลับ
                    </a>

                </div>
                """
            )


        conn.close()

        return redirect(
            "/employees"
        )


    return render_page(
        "เพิ่มพนักงาน",
        """
        <h1>
            ➕ เพิ่มพนักงาน
        </h1>


        <div class="card">

            <form method="POST">

                <label>
                    รหัสพนักงาน
                </label>

                <input
                    name="id"
                    placeholder="เช่น 003"
                    required
                >


                <label>
                    ชื่อพนักงาน
                </label>

                <input
                    name="name"
                    placeholder="ชื่อ-นามสกุล"
                    required
                >


                <label>
                    ฝ่าย
                </label>

                <input
                    name="department"
                    placeholder="เช่น ฝ่ายบัญชี"
                >


                <label>
                    เงินเดือน
                </label>

                <input
                    name="salary"
                    type="number"
                    step="0.01"
                    value="15000"
                >


                <button class="btn green">
                    💾 บันทึก
                </button>


                <a
                    class="btn gray"
                    href="/employees"
                >
                    ยกเลิก
                </a>

            </form>

        </div>
        """
    )


# =========================================================
# EDIT EMPLOYEE
# =========================================================

@app.route(
    "/employees/edit/<employee_id>",
    methods=["GET", "POST"]
)
@admin_required
def edit_employee(
    employee_id
):

    conn = get_db()

    employee = conn.execute("""
        SELECT *
        FROM employees
        WHERE id = ?
    """, (
        employee_id,
    )).fetchone()


    if not employee:

        conn.close()

        return render_page(
            "ไม่พบข้อมูล",
            """
            <div class="card center">

                <h2>
                    ไม่พบข้อมูลพนักงาน
                </h2>

                <a
                    class="btn"
                    href="/employees"
                >
                    กลับ
                </a>

            </div>
            """
        )


    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        department = request.form.get(
            "department",
            "พนักงาน"
        ).strip()


        try:

            salary = float(
                request.form.get(
                    "salary",
                    "0"
                )
            )

        except ValueError:

            salary = 0


        conn.execute("""
            UPDATE employees

            SET
                name = ?,
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


        return redirect(
            "/employees"
        )


    conn.close()


    return render_page(
        "แก้ไขพนักงาน",
        """
        <h1>
            ✏️ แก้ไขพนักงาน
        </h1>


        <div class="card">

            <form method="POST">

                <label>
                    รหัสพนักงาน
                </label>

                <input
                    value="{{ employee['id'] }}"
                    disabled
                >


                <label>
                    ชื่อพนักงาน
                </label>

                <input
                    name="name"
                    value="{{ employee['name'] }}"
                    required
                >


                <label>
                    ฝ่าย
                </label>

                <input
                    name="department"
                    value="{{
                        employee['department']
                        or ''
                    }}"
                >


                <label>
                    เงินเดือน
                </label>

                <input
                    name="salary"
                    type="number"
                    step="0.01"
                    value="{{ employee['salary'] }}"
                >


                <button class="btn green">
                    💾 บันทึก
                </button>

            </form>

        </div>
        """,
        employee=employee
    )


# =========================================================
# DELETE EMPLOYEE
# =========================================================

@app.route(
    "/employees/delete/<employee_id>"
)
@admin_required
def delete_employee(
    employee_id
):

    conn = get_db()

    conn.execute("""
        UPDATE employees
        SET active = 0
        WHERE id = ?
    """, (
        employee_id,
    ))

    conn.commit()
    conn.close()

    return redirect(
        "/employees"
    )


# =========================================================
# PAYROLL
# =========================================================

@app.route("/payroll")
@admin_required
def payroll():

    month = request.args.get(
        "month",
        datetime.now().strftime(
            "%Y-%m"
        )
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
            SELECT COALESCE(
                SUM(ot_hours),
                0
            )

            FROM attendance

            WHERE employee_id = ?

              AND substr(
                    date,
                    1,
                    7
                  ) = ?
        """, (
            employee["id"],
            month
        )).fetchone()[0]


        hourly = (
            employee["salary"]
            / 30
            / 8
            if employee["salary"]
            else 0
        )


        ot_pay = (
            total_ot
            * hourly
            * 1.5
        )


        total = (
            employee["salary"]
            + ot_pay
        )


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
        <h1>
            💰 ฝ่ายบัญชี
        </h1>


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

        <div class="table-wrap">

        <table>

            <tr>

                <th>
                    รหัส
                </th>

                <th>
                    พนักงาน
                </th>

                <th>
                    เงินเดือน
                </th>

                <th>
                    OT
                </th>

                <th>
                    ค่า OT
                </th>

                <th>
                    รวม
                </th>

            </tr>


            {% for r in payroll_rows %}

            <tr>

                <td>
                    {{ r["id"] }}
                </td>

                <td>
                    {{ r["name"] }}
                </td>

                <td>
                    {{ "{:,.2f}".format(
                        r["salary"]
                    ) }}
                </td>

                <td>
                    {{ "%.2f"|format(
                        r["ot_hours"]
                    ) }}
                </td>

                <td>
                    {{ "{:,.2f}".format(
                        r["ot_pay"]
                    ) }}
                </td>

                <td>

                    <b>
                        {{ "{:,.2f}".format(
                            r["total"]
                        ) }}
                    </b>

                </td>

            </tr>

            {% endfor %}

        </table>

        </div>

        </div>


        <div class="card">

            <h2>
                ℹ️ การคำนวณ
            </h2>

            <p>
                ระบบนำจำนวนชั่วโมง OT
                มาคำนวณกับอัตราค่าจ้างต่อชั่วโมง
                และตัวคูณ OT
            </p>

        </div>
        """,
        month=month,
        payroll_rows=payroll_rows
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        "/"
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "app": "Compizz"
    })


# =========================================================
# ERROR
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return render_page(
        "ไม่พบหน้า",
        """
        <div class="card center">

            <div style="font-size:60px;">
                🔎
            </div>

            <h2>
                ไม่พบหน้าที่ต้องการ
            </h2>

            <a
                class="btn"
                href="/"
            >
                🏠 กลับหน้าหลัก
            </a>

        </div>
        """
    ), 404


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
    