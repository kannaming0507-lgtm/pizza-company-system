from flask import Flask, request, redirect, session, render_template_string
import sqlite3
import os
import math
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "compizz-secret-key-change-me"
)

DB = os.environ.get(
    "DB_PATH",
    "pizza_company.db"
)

TZ = timezone(timedelta(hours=7))


# =========================================================
# COMPIZZ SETTINGS
# =========================================================

APP_NAME = "Compizz"

# โรงเรียนสวนกุหลาบวิทยาลัย รังสิต
SKR_LAT = 14.02308271
SKR_LNG = 100.67582120

# 300 เมตร
ALLOWED_DISTANCE_KM = 0.3

# เวลาเริ่มงาน
WORK_START = "08:00:00"

# รหัส Admin / ฝ่ายบัญชี
# สามารถเปลี่ยนใน Render Environment Variable: ADMIN_PIN
ADMIN_PIN = os.environ.get(
    "ADMIN_PIN",
    "9999"
)


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn, table, column):
    rows = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(
        row["name"] == column
        for row in rows
    )


def add_column_if_missing(
    conn,
    table,
    column,
    definition
):
    if not column_exists(
        conn,
        table,
        column
    ):
        conn.execute(
            f"ALTER TABLE {table} "
            f"ADD COLUMN {column} {definition}"
        )


def init_db():

    conn = db()

    # ---------------- USERS ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            employee_id TEXT
        )
    """)

    # ---------------- EMPLOYEES ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            position TEXT DEFAULT '',
            salary REAL DEFAULT 0,
            phone TEXT DEFAULT '',
            start_date TEXT DEFAULT ''
        )
    """)

    # ---------------- ATTENDANCE ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            work_date TEXT NOT NULL,
            time_in TEXT,
            time_out TEXT,
            work_hours REAL DEFAULT 0,
            ot_hours REAL DEFAULT 0,
            status TEXT DEFAULT 'ปกติ',
            latitude REAL,
            longitude REAL,
            location TEXT DEFAULT '',
            UNIQUE(employee_id, work_date)
        )
    """)

    # ---------------- LEAVES ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            days INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'รออนุมัติ'
        )
    """)

    # เผื่อฐานข้อมูลเก่าขาด column
    add_column_if_missing(
        conn,
        "employees",
        "position",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "employees",
        "salary",
        "REAL DEFAULT 0"
    )

    add_column_if_missing(
        conn,
        "employees",
        "phone",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "employees",
        "start_date",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "attendance",
        "latitude",
        "REAL"
    )

    add_column_if_missing(
        conn,
        "attendance",
        "longitude",
        "REAL"
    )

    add_column_if_missing(
        conn,
        "attendance",
        "location",
        "TEXT DEFAULT ''"
    )

    # บัญชีตัวอย่างสำหรับ Admin
    conn.execute("""
        INSERT OR IGNORE INTO users
        (
            username,
            password,
            role,
            employee_id
        )
        VALUES (?, ?, ?, ?)
    """, (
        "account",
        "1234",
        "admin",
        None
    ))

    # พนักงานตัวอย่าง
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM employees"
    ).fetchone()["n"]

    if count == 0:

        conn.execute("""
            INSERT INTO employees
            (
                id,
                name,
                position,
                salary,
                phone,
                start_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "001",
            "พนักงานตัวอย่าง",
            "พนักงาน",
            15000,
            "",
            ""
        ))

        conn.execute("""
            INSERT INTO employees
            (
                id,
                name,
                position,
                salary,
                phone,
                start_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "002",
            "ฝ่ายบัญชี",
            "ฝ่ายบัญชี",
            20000,
            "",
            ""
        ))

    conn.commit()
    conn.close()


# =========================================================
# TIME
# =========================================================

def now():
    return datetime.now(TZ)


# =========================================================
# ADMIN
# =========================================================

def is_admin():
    return session.get(
        "admin_logged_in",
        False
    )


def admin_required():
    return is_admin()


# =========================================================
# GPS
# =========================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c


def get_location_status(
    latitude,
    longitude
):

    # ไม่มี GPS
    if latitude is None or longitude is None:
        return (
            "-",
            None,
            False
        )

    try:

        lat = float(latitude)
        lng = float(longitude)

        distance = haversine_distance(
            SKR_LAT,
            SKR_LNG,
            lat,
            lng
        )

        if distance <= ALLOWED_DISTANCE_KM:

            location = (
                "สวนกุหลาบวิทยาลัย รังสิต "
                "(อยู่ในพื้นที่)"
            )

            return (
                location,
                distance,
                True
            )

        location = (
            f"อยู่นอกพื้นที่ "
            f"({distance:.2f} กม.)"
        )

        # สำคัญ:
        # อยู่นอกพื้นที่ก็ยังลงเวลาได้
        return (
            location,
            distance,
            False
        )

    except (
        ValueError,
        TypeError
    ):

        return (
            "-",
            None,
            False
        )


# =========================================================
# HTML STYLE
# =========================================================

STYLE = """
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
        Arial,
        sans-serif;
    background:
        linear-gradient(
            180deg,
            #fff5f6 0%,
            #f5f6f8 45%,
            #f1f3f5 100%
        );
    color: #202124;
    min-height: 100vh;
}

/* HEADER */

.header {
    background:
        linear-gradient(
            135deg,
            #a90024,
            #e31837
        );
    color: white;
    padding: 18px 22px;
    box-shadow:
        0 4px 18px
        rgba(0,0,0,.12);
}

.header-inner {
    max-width: 1100px;
    margin: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.logo {
    font-size: 22px;
    font-weight: 900;
}

.logo-small {
    font-size: 13px;
    opacity: .9;
}

/* CONTAINER */

.container {
    width: 94%;
    max-width: 1100px;
    margin: 20px auto 100px;
}

/* HERO */

.hero {
    position: relative;
    overflow: hidden;
    background:
        linear-gradient(
            135deg,
            #a90024,
            #ed1b3f
        );
    color: white;
    border-radius: 28px;
    padding: 34px 25px;
    margin-bottom: 20px;
    box-shadow:
        0 12px 35px
        rgba(200,16,46,.22);
}

.hero::after {
    content: "";
    position: absolute;
    width: 190px;
    height: 190px;
    right: -70px;
    top: -70px;
    background:
        rgba(255,255,255,.09);
    border-radius: 50%;
}

.hero-icon {
    font-size: 55px;
}

.hero h1 {
    font-size: 38px;
    margin: 5px 0;
    font-weight: 900;
}

.hero p {
    opacity: .92;
}

/* CARDS */

.card,
.panel {
    background: white;
    border-radius: 20px;
    padding: 20px;
    margin-bottom: 18px;
    box-shadow:
        0 4px 20px
        rgba(0,0,0,.06);
}

.cards {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(170px,1fr)
        );
    gap: 14px;
    margin-bottom: 18px;
}

.number {
    font-size: 29px;
    font-weight: 900;
    color: #c8102e;
    margin-top: 6px;
}

/* BUTTONS */

button,
.btn {
    border: 0;
    border-radius: 12px;
    padding: 12px 16px;
    background: #c8102e;
    color: white;
    text-decoration: none;
    cursor: pointer;
    display: inline-block;
    font-size: 15px;
    font-weight: 700;
    margin: 3px;
}

button:hover,
.btn:hover {
    opacity: .9;
}

.green {
    background: #16803c;
}

.blue {
    background: #2563eb;
}

.gray {
    background: #64748b;
}

.orange {
    background: #d97706;
}

.danger {
    background: #991b1b;
}

/* BIG BUTTON */

.big-btn {
    display: block;
    width: 100%;
    text-align: center;
    border-radius: 16px;
    padding: 17px;
    margin: 9px 0;
    color: white;
    text-decoration: none;
    font-weight: 800;
    font-size: 17px;
}

/* INPUT */

input,
select,
textarea {
    width: 100%;
    padding: 13px;
    border:
        1px solid #d9d9d9;
    border-radius: 11px;
    margin:
        6px 0 14px;
    font-size: 16px;
    background: white;
}

textarea {
    min-height: 100px;
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
    min-width: 850px;
}

th,
td {
    padding: 10px 8px;
    border-bottom:
        1px solid #eeeeee;
    text-align: center;
}

th {
    background: #f3f4f6;
}

/* BADGE */

.badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    font-size: 13px;
}

.ok {
    background: #dcfce7;
    color: #166534;
}

.bad {
    background: #fee2e2;
    color: #991b1b;
}

.wait {
    background: #fef3c7;
    color: #92400e;
}

.outside {
    background: #fff7ed;
    color: #9a3412;
}

/* GPS */

.gps-box {
    border-radius: 15px;
    padding: 15px;
    background: #f4f7fb;
    border:
        1px solid #e2e8f0;
    margin:
        10px 0 15px;
}

.gps-ok {
    background: #e8f8ee;
    color: #166534;
}

.gps-outside {
    background: #fff4e5;
    color: #9a3412;
}

.gps-error {
    background: #fff0f0;
    color: #991b1b;
}

/* NOTICE */

.notice {
    border-radius: 13px;
    padding: 14px;
    margin: 10px 0;
    background: #eef5ff;
}

/* MANUAL */

.manual-item {
    background: #f8f9fa;
    border-radius: 15px;
    padding: 15px;
    margin: 10px 0;
}

.manual-title {
    font-weight: 800;
    font-size: 17px;
}

/* ADMIN */

.admin-banner {
    background:
        linear-gradient(
            135deg,
            #222,
            #444
        );
    color: white;
    border-radius: 20px;
    padding: 22px;
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
    justify-content: space-around;
    align-items: center;
    z-index: 999;
    box-shadow:
        0 -4px 20px
        rgba(0,0,0,.08);
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
}

/* MOBILE */

@media(max-width:600px) {

    .container {
        width: 92%;
    }

    .hero h1 {
        font-size: 31px;
    }

    .header {
        padding: 15px;
    }

    button,
    .btn {
        padding: 11px 13px;
    }

}

</style>
"""


# =========================================================
# LAYOUT
# =========================================================

LAYOUT = """
<!doctype html>

<html lang="th">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>
    {{ title }} - Compizz
</title>

{{ style|safe }}

</head>


<body>

<div class="header">

    <div class="header-inner">

        <div>
            <div class="logo">
                🍕 Compizz
            </div>

            <div class="logo-small">
                ระบบจัดการพนักงาน
            </div>
        </div>

        {% if admin %}

        <div>
            🔐 Admin
        </div>

        {% endif %}

    </div>

</div>


<div class="container">

    {{ content|safe }}

</div>


<div class="bottom-nav">

    <a href="/">
        <span>🏠</span>
        หน้าแรก
    </a>

    <a href="/attendance">
        <span>⏰</span>
        ลงเวลา
    </a>

    <a href="/leaves">
        <span>📅</span>
        การลา
    </a>

    <a href="/manual">
        <span>📖</span>
        คู่มือ
    </a>

    {% if admin %}

    <a href="/admin">
        <span>⚙️</span>
        จัดการ
    </a>

    {% else %}

    <a href="/admin-login">
        <span>🔐</span>
        ผู้ดูแล
    </a>

    {% endif %}

</div>


</body>

</html>
"""


def page(
    content,
    title="Compizz"
):

    return render_template_string(
        LAYOUT,
        style=STYLE,
        content=content,
        title=title,
        admin=is_admin()
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    conn = db()

    today = now().strftime(
        "%Y-%m-%d"
    )

    employee_count = conn.execute("""
        SELECT COUNT(*) AS n
        FROM employees
    """).fetchone()["n"]

    checked = conn.execute("""
        SELECT COUNT(*) AS n
        FROM attendance
        WHERE work_date=?
        AND time_in IS NOT NULL
    """, (
        today,
    )).fetchone()["n"]

    conn.close()

    content = """
    <div class="hero">

        <div class="hero-icon">
            🍕
        </div>

        <h1>
            Compizz
        </h1>

        <p>
            ระบบจัดการพนักงาน
            ลงเวลา การลา เงินเดือน และ OT
        </p>

        <a
            href="/attendance"
            class="big-btn"
            style="
                background:white;
                color:#c8102e;
            "
        >
            ⏰ ลงเวลาเข้า–ออก
        </a>

    </div>


    <div class="cards">

        <div class="card">

            👥 พนักงานทั้งหมด

            <div class="number">
                {{ employee_count }}
            </div>

        </div>


        <div class="card">

            ⏰ ลงเวลาวันนี้

            <div class="number">
                {{ checked }}
            </div>

        </div>

    </div>


    <div class="card">

        <h2>
            ✨ เมนูหลัก
        </h2>


        <a
            class="big-btn"
            style="background:#c8102e;"
            href="/attendance"
        >
            ⏰ ลงเวลาเข้า–ออก
        </a>


        <a
            class="big-btn"
            style="background:#2563eb;"
            href="/leaves"
        >
            📅 ยื่นใบลา / ดูสถานะ
        </a>


        <a
            class="big-btn"
            style="background:#64748b;"
            href="/manual"
        >
            📖 คู่มือการใช้งาน
        </a>


        {% if admin %}

        <a
            class="big-btn"
            style="background:#16803c;"
            href="/admin"
        >
            ⚙️ ระบบจัดการ
        </a>

        {% endif %}

    </div>


    <div class="card">

        <h2>
            📍 ระบบ GPS
        </h2>

        <p>
            ระบบจะบันทึกสถานะพื้นที่ขณะลงเวลา
            เพื่อแสดงว่าอยู่ในหรือนอกพื้นที่
        </p>

        <p class="small">
            หากอยู่นอกพื้นที่ ระบบยังอนุญาตให้ลงเวลาได้
        </p>

    </div>
    """

    return page(
        render_template_string(
            content,
            employee_count=employee_count,
            checked=checked
        ),
        "หน้าแรก"
    )


# =========================================================
# ATTENDANCE
# =========================================================

@app.route(
    "/attendance",
    methods=["GET", "POST"]
)
def attendance():

    conn = db()
    message = ""

    if request.method == "POST":

        employee_id = request.form.get(
            "employee_id",
            ""
        ).strip()

        latitude = request.form.get(
            "latitude"
        )

        longitude = request.form.get(
            "longitude"
        )

        employee = conn.execute("""
            SELECT *
            FROM employees
            WHERE id=?
        """, (
            employee_id,
        )).fetchone()

        if employee is None:

            message = (
                "❌ ไม่พบรหัสพนักงาน"
            )

        else:

            location, distance, inside = (
                get_location_status(
                    latitude,
                    longitude
                )
            )

            today = now().strftime(
                "%Y-%m-%d"
            )

            current = now().strftime(
                "%H:%M:%S"
            )

            record = conn.execute("""
                SELECT *
                FROM attendance
                WHERE employee_id=?
                AND work_date=?
            """, (
                employee_id,
                today
            )).fetchone()


            # -------------------------
            # CHECK IN
            # -------------------------

            if record is None:

                status = (
                    "มาสาย"
                    if current > WORK_START
                    else "ปกติ"
                )

                conn.execute("""
                    INSERT INTO attendance
                    (
                        employee_id,
                        work_date,
                        time_in,
                        status,
                        latitude,
                        longitude,
                        location
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    employee_id,
                    today,
                    current,
                    status,
                    latitude,
                    longitude,
                    location
                ))

                message = (
                    f"✅ เข้างานสำเร็จ "
                    f"{current} | {status}"
                )

                if location != "-":

                    message += (
                        f" | {location}"
                    )


            # -------------------------
            # CHECK OUT
            # -------------------------

            elif record["time_out"] is None:

                try:

                    start = datetime.strptime(
                        record["time_in"],
                        "%H:%M:%S"
                    )

                    end = datetime.strptime(
                        current,
                        "%H:%M:%S"
                    )

                    seconds = (
                        end - start
                    ).total_seconds()

                    hours = max(
                        0,
                        seconds / 3600
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    hours = 0


                ot = max(
                    0,
                    hours - 8
                )


                conn.execute("""
                    UPDATE attendance

                    SET
                        time_out=?,
                        work_hours=?,
                        ot_hours=?,
                        latitude=?,
                        longitude=?,
                        location=?

                    WHERE id=?
                """, (
                    current,
                    hours,
                    ot,
                    latitude,
                    longitude,
                    location,
                    record["id"]
                ))


                message = (
                    f"✅ ออกงานสำเร็จ "
                    f"{current} | "
                    f"ทำงาน {hours:.2f} ชม. | "
                    f"OT {ot:.2f} ชม."
                )

                if location != "-":

                    message += (
                        f" | {location}"
                    )


            else:

                message = (
                    "⚠️ วันนี้ลงเวลาเข้า–ออกครบแล้ว"
                )


            conn.commit()


    employees = conn.execute("""
        SELECT *
        FROM employees
        ORDER BY id
    """).fetchall()


    records = conn.execute("""
        SELECT
            a.id,
            a.employee_id,
            a.work_date,
            a.time_in,
            a.time_out,
            a.work_hours,
            a.ot_hours,
            a.status,
            a.latitude,
            a.longitude,
            a.location,
            e.name
        FROM attendance a

        LEFT JOIN employees e
            ON e.id=a.employee_id

        ORDER BY
            a.work_date DESC,
            a.id DESC

        LIMIT 300
    """).fetchall()


    conn.close()


    content = """
    <h1>
        ⏰ ลงเวลาเข้า–ออก
    </h1>


    {% if message %}

    <div class="panel">
        {{ message }}
    </div>

    {% endif %}


    <div class="panel">

        <h2>
            📝 ลงเวลา
        </h2>

        <p>
            เวลาเข้างานปกติ:
            <b>08:00 น.</b>
        </p>


        <form
            method="post"
            id="attendanceForm"
        >

            <label>
                เลือกพนักงาน
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
                onclick="getLocation()"
            >
                📍 ตรวจตำแหน่งและลงเวลา
            </button>


            <div
                id="gps"
                class="gps-box"
            >
                กดปุ่มด้านบนเพื่อรับตำแหน่ง GPS
            </div>

        </form>

    </div>


    <div class="panel">

        <h2>
            📋 ประวัติการลงเวลา
        </h2>


        <div class="table-wrap">

        <table>

            <tr>

                <th>
                    วันที่
                </th>

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
                    ชั่วโมง
                </th>

                <th>
                    OT
                </th>

                <th>
                    สถานะ
                </th>

                <th>
                    สถานที่
                </th>

            </tr>


            {% for r in records %}

            <tr>

                <td>
                    {{ r["work_date"] or "-" }}
                </td>


                <td>
                    {{ r["name"] or "-" }}
                </td>


                <td>
                    {{ r["time_in"] or "-" }}
                </td>


                <td>
                    {{ r["time_out"] or "-" }}
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

                    {% if r["status"] == "มาสาย" %}

                    <span class="badge bad">
                        🔴 มาสาย
                    </span>

                    {% else %}

                    <span class="badge ok">
                        🟢 ปกติ
                    </span>

                    {% endif %}

                </td>


                <td>

                    {% if r["location"] %}

                        {% if "อยู่นอกพื้นที่" in r["location"] %}

                        <span class="badge outside">
                            {{ r["location"] }}
                        </span>

                        {% else %}

                        <span class="badge ok">
                            {{ r["location"] }}
                        </span>

                        {% endif %}

                    {% else %}

                        -

                    {% endif %}

                </td>

            </tr>

            {% endfor %}

        </table>

        </div>

    </div>


    <script>

    function getLocation() {

        const gps =
            document.getElementById("gps");

        const form =
            document.getElementById(
                "attendanceForm"
            );


        if (!navigator.geolocation) {

            gps.className =
                "gps-box gps-error";

            gps.textContent =
                "❌ อุปกรณ์นี้ไม่รองรับ GPS";

            return;
        }


        gps.className =
            "gps-box";

        gps.textContent =
            "📍 กำลังตรวจตำแหน่ง...";


        navigator.geolocation.getCurrentPosition(

            function(pos) {

                document.getElementById(
                    "latitude"
                ).value =
                    pos.coords.latitude;


                document.getElementById(
                    "longitude"
                ).value =
                    pos.coords.longitude;


                gps.className =
                    "gps-box gps-ok";


                gps.innerHTML =
                    "✅ พบตำแหน่งแล้ว " +
                    "<br>" +
                    "ความแม่นยำประมาณ " +
                    Math.round(
                        pos.coords.accuracy
                    ) +
                    " เมตร";


                setTimeout(
                    function() {
                        form.submit();
                    },
                    500
                );

            },


            function(error) {

                gps.className =
                    "gps-box gps-error";


                if (
                    error.code ===
                    error.PERMISSION_DENIED
                ) {

                    gps.textContent =
                        "⚠️ ไม่ได้รับอนุญาตให้ใช้ GPS " +
                        "กรุณาเปิด Location";

                } else {

                    gps.textContent =
                        "⚠️ ไม่สามารถรับตำแหน่งได้ " +
                        "ระบบจะบันทึกว่าไม่มีข้อมูล GPS";

                }


                setTimeout(
                    function() {
                        form.submit();
                    },
                    700
                );

            },


            {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 0
            }

        );

    }

    </script>
    """


    return page(
        render_template_string(
            content,
            message=message,
            employees=employees,
            records=records
        ),
        "ลงเวลา"
    )


# =========================================================
# LEAVES
# =========================================================

@app.route(
    "/leaves",
    methods=["GET", "POST"]
)
def leaves():

    conn = db()
    message = ""


    if request.method == "POST":

        employee_id = request.form.get(
            "employee_id",
            ""
        ).strip()

        leave_type = request.form.get(
            "leave_type",
            "ลากิจ"
        ).strip()

        start_date = request.form.get(
            "start_date",
            ""
        )

        end_date = request.form.get(
            "end_date",
            ""
        )

        reason = request.form.get(
            "reason",
            ""
        ).strip()


        employee = conn.execute("""
            SELECT *
            FROM employees
            WHERE id=?
        """, (
            employee_id,
        )).fetchone()


        if employee is None:

            message = (
                "❌ ไม่พบพนักงาน"
            )

        else:

            try:

                start = datetime.strptime(
                    start_date,
                    "%Y-%m-%d"
                )

                end = datetime.strptime(
                    end_date,
                    "%Y-%m-%d"
                )


                if end < start:

                    message = (
                        "❌ วันที่สิ้นสุด "
                        "ต้องไม่ก่อนวันที่เริ่ม"
                    )

                else:

                    days = (
                        end - start
                    ).days + 1


                    conn.execute("""
                        INSERT INTO leaves
                        (
                            employee_id,
                            leave_type,
                            start_date,
                            end_date,
                            days,
                            reason,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        employee_id,
                        leave_type,
                        start_date,
                        end_date,
                        days,
                        reason,
                        "รออนุมัติ"
                    ))

                    conn.commit()

                    message = (
                        "✅ ส่งใบลาสำเร็จ "
                        "รอ Admin/ฝ่ายบัญชีอนุมัติ"
                    )

            except ValueError:

                message = (
                    "❌ กรุณากรอกวันที่ให้ถูกต้อง"
                )


    employees = conn.execute("""
        SELECT *
        FROM employees
        ORDER BY id
    """).fetchall()


    rows = conn.execute("""
        SELECT
            l.*,
            e.name
        FROM leaves l

        LEFT JOIN employees e
            ON e.id=l.employee_id

        ORDER BY
            l.id DESC

        LIMIT 300
    """).fetchall()


    conn.close()


    content = """
    <h1>
        📅 ระบบการลา
    </h1>


    {% if message %}

    <div class="panel">
        {{ message }}
    </div>

    {% endif %}


    <div class="panel">

        <h2>
            📝 ยื่นใบลา
        </h2>


        <form method="post">

            <label>
                พนักงาน
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


            <label>
                ประเภทการลา
            </label>

            <select
                name="leave_type"
            >

                <option>
                    ลาป่วย
                </option>

                <option>
                    ลากิจ
                </option>

                <option>
                    ลาพักร้อน
                </option>

                <option>
                    ลาอื่น ๆ
                </option>

            </select>


            <label>
                วันที่เริ่มลา
            </label>

            <input
                type="date"
                name="start_date"
                required
            >


            <label>
                วันที่สิ้นสุด
            </label>

            <input
                type="date"
                name="end_date"
                required
            >


            <label>
                เหตุผล
            </label>

            <textarea
                name="reason"
                placeholder="กรอกเหตุผลการลา"
            ></textarea>


            <button>
                📤 ส่งใบลา
            </button>

        </form>

    </div>


    <div class="panel">

        <h2>
            📋 รายการใบลา
        </h2>


        <div class="table-wrap">

        <table>

            <tr>

                <th>
                    พนักงาน
                </th>

                <th>
                    ประเภท
                </th>

                <th>
                    เริ่ม
                </th>

                <th>
                    สิ้นสุด
                </th>

                <th>
                    วัน
                </th>

                <th>
                    เหตุผล
                </th>

                <th>
                    สถานะ
                </th>

                {% if admin %}

                <th>
                    จัดการ
                </th>

                {% endif %}

            </tr>


            {% for r in rows %}

            <tr>

                <td>
                    {{ r["name"] or "-" }}
                </td>

                <td>
                    {{ r["leave_type"] }}
                </td>

                <td>
                    {{ r["start_date"] }}
                </td>

                <td>
                    {{ r["end_date"] }}
                </td>

                <td>
                    {{ r["days"] }}
                </td>

                <td>
                    {{ r["reason"] or "-" }}
                </td>

                <td>

                    {% if r["status"] == "รออนุมัติ" %}

                    <span class="badge wait">
                        🟡 รออนุมัติ
                    </span>

                    {% elif r["status"] == "อนุมัติ" %}

                    <span class="badge ok">
                        🟢 อนุมัติ
                    </span>

                    {% else %}

                    <span class="badge bad">
                        🔴 ไม่อนุมัติ
                    </span>

                    {% endif %}

                </td>


                {% if admin %}

                <td>

                    {% if r["status"] == "รออนุมัติ" %}

                    <a
                        class="btn green"
                        href="/approve_leave/{{ r['id'] }}"
                    >
                        อนุมัติ
                    </a>

                    <a
                        class="btn danger"
                        href="/reject_leave/{{ r['id'] }}"
                    >
                        ไม่อนุมัติ
                    </a>

                    {% else %}

                    -

                    {% endif %}

                </td>

                {% endif %}

            </tr>

            {% endfor %}

        </table>

        </div>

    </div>
    """


    return page(
        render_template_string(
            content,
            message=message,
            employees=employees,
            rows=rows,
            admin=is_admin()
        ),
        "การลา"
    )


# =========================================================
# APPROVE LEAVE
# =========================================================

@app.route(
    "/approve_leave/<int:leave_id>"
)
def approve_leave(leave_id):

    if not admin_required():
        return redirect("/admin-login")


    conn = db()

    conn.execute("""
        UPDATE leaves
        SET status='อนุมัติ'
        WHERE id=?
    """, (
        leave_id,
    ))

    conn.commit()
    conn.close()

    return redirect("/leaves")


# =========================================================
# REJECT LEAVE
# =========================================================

@app.route(
    "/reject_leave/<int:leave_id>"
)
def reject_leave(leave_id):

    if not admin_required():
        return redirect("/admin-login")


    conn = db()

    conn.execute("""
        UPDATE leaves
        SET status='ไม่อนุมัติ'
        WHERE id=?
    """, (
        leave_id,
    ))

    conn.commit()
    conn.close()

    return redirect("/leaves")


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin-login",
    methods=["GET", "POST"]
)
def admin_login():

    message = ""


    if request.method == "POST":

        pin = request.form.get(
            "pin",
            ""
        ).strip()


        if pin == ADMIN_PIN:

            session["admin_logged_in"] = True

            return redirect("/admin")

        message = (
            "❌ รหัสผู้ดูแลไม่ถูกต้อง"
        )


    content = """
    <div
        class="card"
        style="
            max-width:430px;
            margin:50px auto;
        "
    >

        <div class="center">

            <div style="font-size:60px;">
                🔐
            </div>

            <h1>
                Compizz
            </h1>

            <p>
                Admin / ฝ่ายบัญชี
            </p>

        </div>


        {% if message %}

        <div class="notice">
            {{ message }}
        </div>

        {% endif %}


        <form method="post">

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
                style="width:100%;"
            >
                🔐 เข้าสู่ระบบ
            </button>

        </form>


        <br>

        <a
            class="btn gray"
            href="/"
        >
            กลับหน้าหลัก
        </a>

    </div>
    """


    return page(
        render_template_string(
            content,
            message=message
        ),
        "ผู้ดูแลระบบ"
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    if not admin_required():
        return redirect("/admin-login")


    conn = db()

    today = now().strftime(
        "%Y-%m-%d"
    )


    employees = conn.execute("""
        SELECT COUNT(*) AS n
        FROM employees
    """).fetchone()["n"]


    checked = conn.execute("""
        SELECT COUNT(*) AS n
        FROM attendance
        WHERE work_date=?
        AND time_in IS NOT NULL
    """, (
        today,
    )).fetchone()["n"]


    late = conn.execute("""
        SELECT COUNT(*) AS n
        FROM attendance
        WHERE work_date=?
        AND status='มาสาย'
    """, (
        today,
    )).fetchone()["n"]


    ot = conn.execute("""
        SELECT COALESCE(
            SUM(ot_hours),
            0
        ) AS n

        FROM attendance

        WHERE work_date=?
    """, (
        today,
    )).fetchone()["n"]


    pending = conn.execute("""
        SELECT COUNT(*) AS n
        FROM leaves
        WHERE status='รออนุมัติ'
    """).fetchone()["n"]


    conn.close()


    content = """
    <div class="admin-banner">

        <h1>
            ⚙️ Compizz Admin
        </h1>

        <p>
            ระบบจัดการสำหรับ Admin / ฝ่ายบัญชี
        </p>

    </div>


    <div class="cards">

        <div class="card">

            👥 พนักงาน

            <div class="number">
                {{ employees }}
            </div>

        </div>


        <div class="card">

            ⏰ ลงเวลาวันนี้

            <div class="number">
                {{ checked }}
            </div>

        </div>


        <div class="card">

            🔴 มาสายวันนี้

            <div class="number">
                {{ late }}
            </div>

        </div>


        <div class="card">

            ⏱️ OT วันนี้

            <div class="number">
                {{ "%.2f"|format(ot) }}
            </div>

        </div>

    </div>


    <div class="card">

        <h2>
            📌 ใบลารออนุมัติ
        </h2>

        <div class="number">
            {{ pending }}
        </div>

    </div>


    <div class="card">

        <h2>
            ⚙️ เมนูจัดการ
        </h2>


        <a
            class="big-btn"
            style="background:#2563eb;"
            href="/employees"
        >
            👥 จัดการพนักงาน
        </a>


        <a
            class="big-btn"
            style="background:#16803c;"
            href="/salary"
        >
            💰 เงินเดือน + OT
        </a>


        <a
            class="big-btn"
            style="background:#d97706;"
            href="/leaves"
        >
            📅 จัดการใบลา
        </a>


        <a
            class="big-btn"
            style="background:#64748b;"
            href="/reports"
        >
            📈 รายงาน
        </a>


        <a
            class="big-btn"
            style="background:#991b1b;"
            href="/admin-logout"
        >
            🚪 ออกจากระบบ Admin
        </a>

    </div>
    """


    return page(
        render_template_string(
            content,
            employees=employees,
            checked=checked,
            late=late,
            ot=ot,
            pending=pending
        ),
        "Admin"
    )


# =========================================================
# EMPLOYEES
# =========================================================

@app.route("/employees")
def employees():

    if not admin_required():
        return redirect("/admin-login")


    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM employees
        ORDER BY id
    """).fetchall()

    conn.close()


    content = """
    <h1>
        👥 จัดการพนักงาน
    </h1>


    <div class="panel">

        <a
            class="btn green"
            href="/add_employee"
        >
            ➕ เพิ่มพนักงาน
        </a>

    </div>


    <div class="panel">

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
                    ตำแหน่ง
                </th>

                <th>
                    เงินเดือน
                </th>

                <th>
                    โทร
                </th>

                <th>
                    จัดการ
                </th>

            </tr>


            {% for e in rows %}

            <tr>

                <td>
                    {{ e["id"] }}
                </td>

                <td>
                    {{ e["name"] }}
                </td>

                <td>
                    {{ e["position"] or "-" }}
                </td>

                <td>
                    {{ "%.2f"|format(
                        e["salary"] or 0
                    ) }}
                </td>

                <td>
                    {{ e["phone"] or "-" }}
                </td>

                <td>

                    <a
                        class="btn blue"
                        href="/edit_employee/{{ e['id'] }}"
                    >
                        แก้ไข
                    </a>


                    <a
                        class="btn danger"
                        href="/delete_employee/{{ e['id'] }}"
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
    """


    return page(
        render_template_string(
            content,
            rows=rows
        ),
        "พนักงาน"
    )


# =========================================================
# ADD EMPLOYEE
# =========================================================

@app.route(
    "/add_employee",
    methods=["GET", "POST"]
)
def add_employee():

    if not admin_required():
        return redirect("/admin-login")


    if request.method == "POST":

        employee_id = request.form.get(
            "id",
            ""
        ).strip()

        name = request.form.get(
            "name",
            ""
        ).strip()

        position = request.form.get(
            "position",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        start_date = request.form.get(
            "start_date",
            ""
        )


        try:

            salary = float(
                request.form.get(
                    "salary",
                    0
                ) or 0
            )

        except ValueError:

            salary = 0


        conn = db()


        try:

            conn.execute("""
                INSERT INTO employees
                (
                    id,
                    name,
                    position,
                    salary,
                    phone,
                    start_date
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                employee_id,
                name,
                position,
                salary,
                phone,
                start_date
            ))

            conn.commit()
            conn.close()

            return redirect(
                "/employees"
            )


        except sqlite3.IntegrityError:

            conn.close()

            return page(
                """
                <div class="panel center">

                    <h2>
                        ❌ รหัสพนักงานมีอยู่แล้ว
                    </h2>

                    <a
                        class="btn"
                        href="/add_employee"
                    >
                        กลับ
                    </a>

                </div>
                """,
                "เพิ่มพนักงาน"
            )


    content = """
    <h1>
        ➕ เพิ่มพนักงาน
    </h1>


    <div class="panel">

        <form method="post">

            <label>
                รหัสพนักงาน
            </label>

            <input
                name="id"
                required
            >


            <label>
                ชื่อ
            </label>

            <input
                name="name"
                required
            >


            <label>
                ตำแหน่ง
            </label>

            <input
                name="position"
            >


            <label>
                เงินเดือน
            </label>

            <input
                type="number"
                step="0.01"
                name="salary"
                value="15000"
            >


            <label>
                เบอร์โทร
            </label>

            <input
                name="phone"
            >


            <label>
                วันที่เริ่มงาน
            </label>

            <input
                type="date"
                name="start_date"
            >


            <button>
                💾 บันทึก
            </button>

        </form>

    </div>
    """


    return page(
        render_template_string(content),
        "เพิ่มพนักงาน"
    )


# =========================================================
# EDIT EMPLOYEE
# =========================================================

@app.route(
    "/edit_employee/<employee_id>",
    methods=["GET", "POST"]
)
def edit_employee(employee_id):

    if not admin_required():
        return redirect("/admin-login")


    conn = db()

    employee = conn.execute("""
        SELECT *
        FROM employees
        WHERE id=?
    """, (
        employee_id,
    )).fetchone()


    if employee is None:

        conn.close()

        return page(
            """
            <div class="panel center">

                <h2>
                    ❌ ไม่พบพนักงาน
                </h2>

                <a
                    class="btn"
                    href="/employees"
                >
                    กลับ
                </a>

            </div>
            """,
            "ไม่พบข้อมูล"
        )


    if request.method == "POST":

        try:

            salary = float(
                request.form.get(
                    "salary",
                    0
                ) or 0
            )

        except ValueError:

            salary = 0


        conn.execute("""
            UPDATE employees

            SET
                name=?,
                position=?,
                salary=?,
                phone=?,
                start_date=?

            WHERE id=?
        """, (
            request.form.get(
                "name",
                ""
            ).strip(),

            request.form.get(
                "position",
                ""
            ).strip(),

            salary,

            request.form.get(
                "phone",
                ""
            ).strip(),

            request.form.get(
                "start_date",
                ""
            ),

            employee_id
        ))


        conn.commit()
        conn.close()


        return redirect(
            "/employees"
        )


    conn.close()


    content = """
    <h1>
        ✏️ แก้ไขพนักงาน
    </h1>


    <div class="panel">

        <form method="post">

            <label>
                รหัสพนักงาน
            </label>

            <input
                value="{{ e['id'] }}"
                disabled
            >


            <label>
                ชื่อ
            </label>

            <input
                name="name"
                value="{{ e['name'] }}"
                required
            >


            <label>
                ตำแหน่ง
            </label>

            <input
                name="position"
                value="{{ e['position'] or '' }}"
            >


            <label>
                เงินเดือน
            </label>

            <input
                type="number"
                step="0.01"
                name="salary"
                value="{{ e['salary'] or 0 }}"
            >


            <label>
                เบอร์โทร
            </label>

            <input
                name="phone"
                value="{{ e['phone'] or '' }}"
            >


            <label>
                วันที่เริ่มงาน
            </label>

            <input
                type="date"
                name="start_date"
                value="{{ e['start_date'] or '' }}"
            >


            <button>
                💾 บันทึก
            </button>

        </form>

    </div>
    """


    return page(
        render_template_string(
            content,
            e=employee
        ),
        "แก้ไขพนักงาน"
    )


# =========================================================
# DELETE EMPLOYEE
# =========================================================

@app.route(
    "/delete_employee/<employee_id>"
)
def delete_employee(employee_id):

    if not admin_required():
        return redirect("/admin-login")


    conn = db()

    conn.execute(
        "DELETE FROM attendance WHERE employee_id=?",
        (employee_id,)
    )

    conn.execute(
        "DELETE FROM leaves WHERE employee_id=?",
        (employee_id,)
    )

    conn.execute(
        "DELETE FROM employees WHERE id=?",
        (employee_id,)
    )

    conn.commit()
    conn.close()


    return redirect(
        "/employees"
    )


# =========================================================
# SALARY
# =========================================================

@app.route("/salary")
def salary():

    if not admin_required():
        return redirect("/admin-login")


    month = request.args.get(
        "month",
        now().strftime("%Y-%m")
    )


    conn = db()

    employees = conn.execute("""
        SELECT *
        FROM employees
        ORDER BY id
    """).fetchall()


    rows = []

    base_total = 0
    ot_total = 0
    grand_total = 0


    for e in employees:

        result = conn.execute("""
            SELECT
                COALESCE(
                    SUM(ot_hours),
                    0
                ) AS ot

            FROM attendance

            WHERE employee_id=?

            AND substr(
                work_date,
                1,
                7
            )=?
        """, (
            e["id"],
            month
        )).fetchone()


        ot_hours = (
            result["ot"]
            or 0
        )

        salary_value = (
            e["salary"]
            or 0
        )


        hourly = (
            salary_value
            / 30
            / 8
        )


        ot_pay = (
            hourly
            * 1.5
            * ot_hours
        )


        total = (
            salary_value
            + ot_pay
        )


        base_total += salary_value
        ot_total += ot_pay
        grand_total += total


        rows.append({
            "id": e["id"],
            "name": e["name"],
            "salary": salary_value,
            "ot": ot_hours,
            "ot_pay": ot_pay,
            "total": total
        })


    conn.close()


    content = """
    <h1>
        💰 เงินเดือน + OT
    </h1>


    <div class="panel">

        <form method="get">

            <label>
                เดือน
            </label>

            <input
                type="month"
                name="month"
                value="{{ month }}"
            >


            <button>
                🔎 ดูข้อมูล
            </button>

        </form>

    </div>


    <div class="cards">

        <div class="card">

            เงินเดือนพื้นฐาน

            <div class="number">
                {{ "%.2f"|format(
                    base_total
                ) }}
            </div>

        </div>


        <div class="card">

            ค่า OT

            <div class="number">
                {{ "%.2f"|format(
                    ot_total
                ) }}
            </div>

        </div>


        <div class="card">

            ยอดจ่ายรวม

            <div class="number">
                {{ "%.2f"|format(
                    grand_total
                ) }}
            </div>

        </div>

    </div>


    <div class="panel">

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
                    เงินเดือน
                </th>

                <th>
                    OT ชม.
                </th>

                <th>
                    ค่า OT
                </th>

                <th>
                    รวม
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
                    {{ "%.2f"|format(
                        r["salary"]
                    ) }}
                </td>

                <td>
                    {{ "%.2f"|format(
                        r["ot"]
                    ) }}
                </td>

                <td>
                    {{ "%.2f"|format(
                        r["ot_pay"]
                    ) }}
                </td>

                <td>
                    <b>
                        {{ "%.2f"|format(
                            r["total"]
                        ) }}
                    </b>
                </td>

            </tr>

            {% endfor %}

        </table>

        </div>

    </div>
    """


    return page(
        render_template_string(
            content,
            month=month,
            rows=rows,
            base_total=base_total,
            ot_total=ot_total,
            grand_total=grand_total
        ),
        "เงินเดือน"
    )


# =========================================================
# REPORTS
# =========================================================

@app.route("/reports")
def reports():

    if not admin_required():
        return redirect("/admin-login")


    month = request.args.get(
        "month",
        now().strftime("%Y-%m")
    )


    conn = db()


    attendance_count = conn.execute("""
        SELECT COUNT(*) AS n
        FROM attendance

        WHERE substr(
            work_date,
            1,
            7
        )=?
    """, (
        month,
    )).fetchone()["n"]


    late_count = conn.execute("""
        SELECT COUNT(*) AS n
        FROM attendance

        WHERE status='มาสาย'

        AND substr(
            work_date,
            1,
            7
        )=?
    """, (
        month,
    )).fetchone()["n"]


    gps_count = conn.execute("""
        SELECT COUNT(*) AS n
        FROM attendance

        WHERE substr(
            work_date,
            1,
            7
        )=?

        AND latitude IS NOT NULL

        AND longitude IS NOT NULL
    """, (
        month,
    )).fetchone()["n"]


    outside_count = conn.execute("""
        SELECT COUNT(*) AS n
        FROM attendance

        WHERE substr(
            work_date,
            1,
            7
        )=?

        AND location LIKE 'อยู่นอกพื้นที่%'
    """, (
        month,
    )).fetchone()["n"]


    ot = conn.execute("""
        SELECT
            COALESCE(
                SUM(ot_hours),
                0
            ) AS n

        FROM attendance

        WHERE substr(
            work_date,
            1,
            7
        )=?
    """, (
        month,
    )).fetchone()["n"]


    leave_count = conn.execute("""
        SELECT COUNT(*) AS n
        FROM leaves

        WHERE substr(
            start_date,
            1,
            7
        )=?
    """, (
        month,
    )).fetchone()["n"]


    conn.close()


    content = """
    <h1>
        📈 รายงาน
    </h1>


    <div class="panel">

        <form method="get">

            <label>
                เดือน
            </label>

            <input
                type="month"
                name="month"
                value="{{ month }}"
            >


            <button>
                🔎 ดูรายงาน
            </button>

        </form>

    </div>


    <div class="cards">

        <div class="card">

            ⏰ การลงเวลา

            <div class="number">
                {{ attendance_count }}
            </div>

        </div>


        <div class="card">

            🔴 มาสาย

            <div class="number">
                {{ late_count }}
            </div>

        </div>


        <div class="card">

            📍 มี GPS

            <div class="number">
                {{ gps_count }}
            </div>

        </div>


        <div class="card">

            ⚠️ อยู่นอกพื้นที่

            <div class="number">
                {{ outside_count }}
            </div>

        </div>


        <div class="card">

            ⏱️ OT รวม

            <div class="number">
                {{ "%.2f"|format(ot) }}
            </div>

        </div>


        <div class="card">

            📅 ใบลา

            <div class="number">
                {{ leave_count }}
            </div>

        </div>

    </div>


    <div class="panel center">

        <button
            onclick="window.print()"
        >
            🖨️ พิมพ์รายงาน
        </button>

    </div>
    """


    return page(
        render_template_string(
            content,
            month=month,
            attendance_count=attendance_count,
            late_count=late_count,
            gps_count=gps_count,
            outside_count=outside_count,
            ot=ot,
            leave_count=leave_count
        ),
        "รายงาน"
    )


# =========================================================
# MANUAL
# =========================================================

@app.route("/manual")
def manual():

    content = """
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
            หรือ
            <b>การลา</b>
            ได้ทันที

        </div>

        <p>
            พนักงานทั่วไป
            <b>ไม่ต้อง Login</b>
            เพื่อใช้งานส่วนของพนักงาน
        </p>

    </div>


    <div class="card">

        <h2>
            2. ⏰ การลงเวลา
        </h2>

        <ol>

            <li>
                เลือกรหัสพนักงาน
            </li>

            <li>
                กด
                <b>📍 ตรวจตำแหน่งและลงเวลา</b>
            </li>

            <li>
                อนุญาต Location
                หากโทรศัพท์หรือ iPad ถาม
            </li>

            <li>
                ระบบจะบันทึกเวลาเข้า
                หรือเวลาออกให้อัตโนมัติ
            </li>

        </ol>


        <div class="notice">

            เวลาเริ่มงาน:
            <b>08:00 น.</b>

            <br><br>

            ก่อนหรือเท่ากับ 08:00
            =
            <b>ปกติ</b>

            <br>

            หลัง 08:00
            =
            <b>มาสาย</b>

        </div>

    </div>


    <div class="card">

        <h2>
            3. 📍 คู่มือระบบ GPS
        </h2>


        <div class="manual-item">

            <div class="manual-title">
                ขั้นตอนที่ 1
            </div>

            <p>
                เลือกรหัสพนักงาน
                ที่ต้องการลงเวลา
            </p>

        </div>


        <div class="manual-item">

            <div class="manual-title">
                ขั้นตอนที่ 2
            </div>

            <p>
                กดปุ่ม
                <b>
                    📍 ตรวจตำแหน่งและลงเวลา
                </b>
            </p>

        </div>


        <div class="manual-item">

            <div class="manual-title">
                ขั้นตอนที่ 3
            </div>

            <p>
                เมื่อเบราว์เซอร์ถาม
                ให้กดอนุญาตให้เข้าถึง Location
            </p>

        </div>


        <div class="manual-item">

            <div class="manual-title">
                ขั้นตอนที่ 4
            </div>

            <p>
                ระบบจะคำนวณระยะห่างจาก
                จุดอ้างอิงของโรงเรียน
            </p>

        </div>


        <div class="gps-box">

            <b>
                🏫 จุดอ้างอิง
            </b>

            <p>
                สวนกุหลาบวิทยาลัย รังสิต
            </p>


            <b>
                📏 รัศมีที่กำหนด
            </b>

            <p>
                300 เมตร
            </p>

        </div>


        <h3>
            ✅ อยู่ในพื้นที่
        </h3>

        <div class="gps-box gps-ok">

            ระบบจะแสดง

            <br><br>

            <b>
                สวนกุหลาบวิทยาลัย รังสิต
                (อยู่ในพื้นที่)
            </b>

        </div>


        <h3>
            ⚠️ อยู่นอกพื้นที่
        </h3>

        <div class="gps-box gps-outside">

            ระบบจะแสดง เช่น

            <br><br>

            <b>
                อยู่นอกพื้นที่ (1.25 กม.)
            </b>

            <br><br>

            <b>
                สำคัญ:
            </b>

            กรณีอยู่นอกพื้นที่
            <b>ยังสามารถลงเวลาได้</b>
            ระบบเพียงบันทึกสถานะว่าอยู่นอกพื้นที่

        </div>


        <h3>
            📱 ถ้า GPS ไม่ตรง
        </h3>

        <ol>

            <li>
                เปิด Location ของมือถือ/iPad
            </li>

            <li>
                อนุญาต Location ให้ Safari หรือ Chrome
            </li>

            <li>
                เปิด Wi-Fi หรือเครือข่ายมือถือ
                เพื่อช่วยระบุตำแหน่ง
            </li>

            <li>
                กดตรวจตำแหน่งใหม่อีกครั้ง
            </li>

        </ol>


        <div class="notice">

            💡 GPS ของโทรศัพท์และ iPad
            อาจมีความคลาดเคลื่อนได้
            โดยเฉพาะภายในอาคารหรือบริเวณ
            ที่สัญญาณดาวเทียมไม่ดี

        </div>

    </div>


    <div class="card">

        <h2>
            4. 📅 ระบบการลา
        </h2>

        <ol>

            <li>
                เข้าเมนู
                <b>📅 การลา</b>
            </li>

            <li>
                เลือกพนักงาน
            </li>

            <li>
                เลือกประเภทการลา
            </li>

            <li>
                เลือกวันที่เริ่มและวันที่สิ้นสุด
            </li>

            <li>
                กรอกเหตุผล
            </li>

            <li>
                กด
                <b>ส่งใบลา</b>
            </li>

        </ol>


        <div class="notice">

            ใบลาจะมีสถานะ
            <br>
            🟡 รออนุมัติ
            <br>
            🟢 อนุมัติ
            <br>
            🔴 ไม่อนุมัติ

        </div>

    </div>


    <div class="card">

        <h2>
            5. 💰 เงินเดือนและ OT
        </h2>

        <p>
            ระบบคำนวณชั่วโมงทำงาน
            และชั่วโมง OT จากเวลาเข้า–ออก
        </p>

        <p>
            ชั่วโมงที่เกิน 8 ชั่วโมง
            จะถูกนับเป็น OT
        </p>

    </div>


    <div class="card">

        <h2>
            6. 🔐 Admin / ฝ่ายบัญชี
        </h2>

        <p>
            พนักงานทั่วไปสามารถใช้งาน
            ลงเวลาและการลาได้เลย
        </p>

        <p>
            แต่การจัดการข้อมูลสำคัญ
            ต้องเข้า
            <b>🔐 ผู้ดูแล</b>
            และกรอกรหัส Admin
        </p>

        <ul>

            <li>
                👥 จัดการพนักงาน
            </li>

            <li>
                💰 เงินเดือน
            </li>

            <li>
                📅 อนุมัติใบลา
            </li>

            <li>
                📈 รายงาน
            </li>

        </ul>

    </div>


    <div class="card">

        <h2>
            7. 📱 การใช้งานบนมือถือ
        </h2>

        <p>
            Compizz รองรับโทรศัพท์
            และ iPad
            โดยออกแบบหน้าจอให้เหมาะกับ
            หน้าจอขนาดเล็ก
        </p>
        <div class="card">
            <h2>📱 วิธีติดตั้งแอปไว้บนหน้าจอมือถือ/ไอแพด</h2>
            <p>เพื่อความสะดวกในการใช้งาน สามารถกดเพิ่มแอปไว้ที่หน้าจอหลัก (Home Screen) ได้เลย:</p>
            
            <p><strong>สำหรับ iOS / iPadOS (Safari):</strong></p>
            <ul>
                <li>1. เปิดเว็บด้วย <strong>Safari</strong></li>
                <li>2. กดปุ่ม <strong>แชร์ (Share)</strong> <i>(รูปสี่เหลี่ยมที่มีลูกศรชี้ขึ้น)</i></li>
                <li>3. เลื่อนลงมาเลือก <strong>"เพิ่มไปยังหน้าจอโฮม" (Add to Home Screen)</strong></li>
                <li>4. กด <strong>"เพิ่ม" (Add)</strong> มุมขวาบน</li>
            </ul>

            <p><strong>สำหรับ Android (Chrome):</strong></p>
            <ul>
                <li>1. เปิดเว็บด้วย <strong>Chrome</strong></li>
                <li>2. กดปุ่ม <strong>เมนู (จุด 3 จุด)</strong> มุมขวาบน</li>
                <li>3. เลือก <strong>"ติดตั้งแอป" (Install App)</strong> หรือ <strong>"เพิ่มลงในหน้าจอโฮม"</strong></li>
                <li>4. กด <strong>"ยืนยัน / เพิ่ม"</strong></li>
            </ul>

            <div class="notice">
                💡 เมื่อติดตั้งแล้ว ไอคอนแอปจะไปขึ้นที่หน้าจอหลัก สามารถกดเข้าใช้งานได้ทันทีเหมือนแอปทั่วไปเลยครับ
            </div>
        </div>

    
    """


    return page(
        render_template_string(content),
        "คู่มือ"
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin-logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect("/")


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "app": APP_NAME
    }


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):

    content = """
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

    return page(
        render_template_string(content),
        "ไม่พบหน้า"
    ), 404


# =========================================================
# START
# =========================================================

init_db()


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
    

