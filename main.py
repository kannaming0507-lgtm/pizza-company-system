from flask import Flask, request, redirect, session, render_template_string, jsonify
import sqlite3
import os
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# =========================================================
# BASIC SETTINGS
# =========================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "pizza-company-school-project"
)

DB = os.environ.get(
    "DATABASE_PATH",
    "pizza_company.db"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "1234"
)

# =========================================================
# GPS SETTINGS
# =========================================================

SKR_LAT = 14.02308
SKR_LNG = 100.67582

ALLOWED_DISTANCE_KM = 0.3

# =========================================================
# TIMEZONE
# =========================================================

THAILAND_TZ = timezone(
    timedelta(hours=7)
)


def now():
    return datetime.now(
        THAILAND_TZ
    )


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(
        DB,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    # -----------------------------------------------------
    # EMPLOYEES
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # ATTENDANCE
    # -----------------------------------------------------

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
            location TEXT DEFAULT '-',
            UNIQUE(employee_id, work_date)
        )
    """)

    # -----------------------------------------------------
    # LEAVES
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            days INTEGER DEFAULT 1,
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'รออนุมัติ'
        )
    """)

    conn.commit()

    # -----------------------------------------------------
    # DATABASE MIGRATION
    # -----------------------------------------------------
    # ป้องกันฐานข้อมูลเก่าที่ไม่มีคอลัมน์ใหม่
    # -----------------------------------------------------

    columns = conn.execute(
        "PRAGMA table_info(attendance)"
    ).fetchall()

    column_names = [
        row["name"]
        for row in columns
    ]

    if "latitude" not in column_names:

        conn.execute("""
            ALTER TABLE attendance
            ADD COLUMN latitude REAL
        """)

    if "longitude" not in column_names:

        conn.execute("""
            ALTER TABLE attendance
            ADD COLUMN longitude REAL
        """)

    if "location" not in column_names:

        conn.execute("""
            ALTER TABLE attendance
            ADD COLUMN location TEXT DEFAULT '-'
        """)

    conn.commit()

    conn.close()


# =========================================================
# GPS FUNCTIONS
# =========================================================

def calculate_distance_km(
    latitude,
    longitude
):

    try:

        latitude = float(latitude)
        longitude = float(longitude)

    except (
        ValueError,
        TypeError
    ):

        return None

    lat_diff = latitude - SKR_LAT
    lng_diff = longitude - SKR_LNG

    distance = (
        (
            lat_diff ** 2
            +
            lng_diff ** 2
        ) ** 0.5
    ) * 111

    return distance


def get_location_name(
    latitude,
    longitude
):

    if (
        latitude is None
        or longitude is None
        or latitude == ""
        or longitude == ""
    ):

        return "-"

    distance = calculate_distance_km(
        latitude,
        longitude
    )

    if distance is None:

        return "-"

    if distance <= ALLOWED_DISTANCE_KM:

        return (
            "สวนกุหลาบวิทยาลัย รังสิต "
            "(อยู่ในพื้นที่)"
        )

    return (
        "อยู่นอกพื้นที่ "
        "({:.2f} กม.)"
        .format(distance)
    )


# =========================================================
# ADMIN
# =========================================================

def admin_unlocked():

    return session.get(
        "admin_unlocked",
        False
    )


# =========================================================
# CSS
# =========================================================

STYLE = """
<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #f5f6fa;

    color: #222;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Arial,
        sans-serif;

}

.header {

    background: #b91c1c;

    color: white;

    padding: 17px 20px;

    position: sticky;

    top: 0;

    z-index: 20;

    box-shadow:
        0 2px 8px
        rgba(0,0,0,.12);

}

.header h2 {

    margin: 0;

    font-size: 21px;

}

.container {

    width: 100%;

    max-width: 1150px;

    margin: auto;

    padding: 18px;

    padding-bottom: 100px;

}

h1 {

    margin-top: 5px;

    font-size: 27px;

}

h3 {

    margin-top: 5px;

}

.cards {

    display: grid;

    grid-template-columns:
        repeat(2, 1fr);

    gap: 13px;

}

.card {

    background: white;

    padding: 18px;

    border-radius: 17px;

    box-shadow:
        0 3px 12px
        rgba(0,0,0,.07);

}

.card-title {

    color: #777;

    font-size: 13px;

}

.card-number {

    font-size: 28px;

    font-weight: 800;

    margin-top: 7px;

}

.panel {

    background: white;

    padding: 18px;

    margin-top: 15px;

    border-radius: 17px;

    box-shadow:
        0 3px 12px
        rgba(0,0,0,.07);

}

button,
.btn {

    border: 0;

    border-radius: 11px;

    padding:
        11px 15px;

    background: #b91c1c;

    color: white;

    text-decoration: none;

    display: inline-block;

    cursor: pointer;

    font-size: 14px;

}

button:hover,
.btn:hover {

    opacity: .9;

}

.blue {

    background: #2563eb;

}

.green {

    background: #15803d;

}

.gray {

    background: #6b7280;

}

.danger {

    background: #991b1b;

}

label {

    display: block;

    font-weight: 600;

    margin-top: 9px;

}

input,
select,
textarea {

    width: 100%;

    padding: 12px;

    margin:
        6px 0 12px;

    border:
        1px solid #ddd;

    border-radius: 11px;

    font-size: 15px;

    background: white;

}

textarea {

    min-height: 90px;

    resize: vertical;

}

.table-wrap {

    overflow-x: auto;

}

table {

    width: 100%;

    min-width: 750px;

    border-collapse:
        collapse;

}

th,
td {

    padding: 10px;

    border-bottom:
        1px solid #eee;

    text-align: center;

    vertical-align: middle;

}

th {

    background: #f3f4f6;

}

.badge {

    padding:
        6px 10px;

    border-radius: 30px;

    display: inline-block;

    font-size: 12px;

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

.info-box {

    background: #f8fafc;

    border:
        1px solid #e5e7eb;

    border-radius: 12px;

    padding: 13px;

    margin-top: 10px;

}

.success-box {

    background: #ecfdf5;

    color: #166534;

    border-radius: 12px;

    padding: 13px;

}

.error-box {

    background: #fef2f2;

    color: #991b1b;

    border-radius: 12px;

    padding: 13px;

}

.manual-item {

    padding:
        12px 0;

    border-bottom:
        1px solid #eee;

}

.manual-item:last-child {

    border-bottom: 0;

}

.bottom-nav {

    position: fixed;

    left: 0;

    right: 0;

    bottom: 0;

    height: 68px;

    background: white;

    border-top:
        1px solid #ddd;

    display: flex;

    justify-content:
        space-around;

    align-items: center;

    z-index: 30;

}

.bottom-nav a {

    color: #555;

    text-decoration: none;

    text-align: center;

    font-size: 12px;

}

.bottom-nav span {

    display: block;

    font-size: 21px;

    margin-bottom: 2px;

}

@media (min-width: 800px) {

    .cards {

        grid-template-columns:
            repeat(4, 1fr);

    }

}

@media (max-width: 500px) {

    .container {

        padding: 13px;

        padding-bottom: 95px;

    }

    .cards {

        grid-template-columns:
            1fr;

    }

    h1 {

        font-size: 23px;

    }

}

</style>
"""


# =========================================================
# MAIN LAYOUT
# =========================================================

LAYOUT = """
<!doctype html>

<html lang="th">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content=
    "width=device-width,
    initial-scale=1,
    maximum-scale=1"
>

<meta
    name="theme-color"
    content="#b91c1c"
>

<link
    rel="manifest"
    href="/manifest.json"
>

<title>
    Pizza Company
</title>

{{ style|safe }}

</head>

<body>

<div class="header">

    <h2>
        🍕 Pizza Company
    </h2>

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

        ใบลา

    </a>

    <a href="/manual">

        <span>📖</span>

        คู่มือ

    </a>

    <a href="/admin">

        <span>🔐</span>

        บัญชี

    </a>

</div>

</body>

</html>
"""


def page(content):

    return render_template_string(

        LAYOUT,

        style=STYLE,

        content=content

    )


# =========================================================
# MANIFEST
# =========================================================

@app.route("/manifest.json")
def manifest():

    return jsonify({

        "name":
            "Pizza Company System",

        "short_name":
            "Pizza System",

        "start_url":
            "/",

        "display":
            "standalone",

        "background_color":
            "#f5f6fa",

        "theme_color":
            "#b91c1c"

    })


# =========================================================
# HOME
# =========================================================

@app.route("/")
def dashboard():

    conn = get_db()

    today = now().strftime(
        "%Y-%m-%d"
    )

    employee_count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM employees
        """
    ).fetchone()["n"]

    attendance_count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM attendance

        WHERE work_date=?

        AND time_in IS NOT NULL
        """,
        (today,)
    ).fetchone()["n"]

    late_count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM attendance

        WHERE work_date=?

        AND status='มาสาย'
        """,
        (today,)
    ).fetchone()["n"]

    ot_total = conn.execute(
        """
        SELECT
            COALESCE(
                SUM(ot_hours),
                0
            ) AS n

        FROM attendance

        WHERE work_date=?
        """,
        (today,)
    ).fetchone()["n"]

    conn.close()

    content = """
    <h1>
        📊 Dashboard
    </h1>

    <div class="cards">

        <div class="card">

            <div class="card-title">
                พนักงานทั้งหมด
            </div>

            <div class="card-number">
                {{ employee_count }}
            </div>

        </div>

        <div class="card">

            <div class="card-title">
                ลงเวลาวันนี้
            </div>

            <div class="card-number">
                {{ attendance_count }}
            </div>

        </div>

        <div class="card">

            <div class="card-title">
                มาสายวันนี้
            </div>

            <div class="card-number">
                {{ late_count }}
            </div>

        </div>

        <div class="card">

            <div class="card-title">
                OT วันนี้
            </div>

            <div class="card-number">
                {{ "%.2f"|format(ot_total or 0) }}
            </div>

        </div>

    </div>


    <div class="panel">

        <h3>
            👋 ยินดีต้อนรับ
        </h3>

        <p>
            ระบบบริหารจัดการพนักงาน
            และบัญชีของ Pizza Company
        </p>

        <p>
            สามารถลงเวลา
            จัดการพนักงาน
            คำนวณเงินเดือน
            บันทึกการลา
            และดูรายงานได้
        </p>

    </div>


    <div class="panel">

        <h3>
            ⚡ เมนูด่วน
        </h3>

        <p>

            <a
                class="btn"
                href="/attendance"
            >
                ⏰ ลงเวลา
            </a>

            <a
                class="btn blue"
                href="/leaves"
            >
                📅 ยื่นใบลา
            </a>

            <a
                class="btn green"
                href="/manual"
            >
                📖 คู่มือ
            </a>

        </p>

    </div>
    """

    return page(

        render_template_string(

            content,

            employee_count=
                employee_count,

            attendance_count=
                attendance_count,

            late_count=
                late_count,

            ot_total=
                ot_total

        )
    )


# =========================================================
# ATTENDANCE
# =========================================================

@app.route(
    "/attendance",
    methods=["GET", "POST"]
)
def attendance():

    message = ""

    if request.method == "POST":

        employee_id = request.form.get(
            "employee_id",
            ""
        ).strip()

        action = request.form.get(
            "action",
            "check_in"
        )

        latitude = request.form.get(
            "latitude"
        )

        longitude = request.form.get(
            "longitude"
        )

        conn = get_db()

        employee = conn.execute(
            """
            SELECT *
            FROM employees
            WHERE id=?
            """,
            (employee_id,)
        ).fetchone()

        if employee is None:

            conn.close()

            return page(
                """
                <div class="error-box">
                    ❌ ไม่พบรหัสพนักงาน
                </div>
                """
            )

        today = now().strftime(
            "%Y-%m-%d"
        )

        current_time = now().strftime(
            "%H:%M:%S"
        )

        record = conn.execute(
            """
            SELECT *
            FROM attendance

            WHERE employee_id=?
            AND work_date=?
            """,
            (
                employee_id,
                today
            )
        ).fetchone()

        # -------------------------------------------------
        # CHECK IN
        # -------------------------------------------------

        if action == "check_in":

            if record is not None:

                message = """
                <div class="error-box">
                    ⚠️ พนักงานคนนี้
                    ลงเวลาเข้าแล้ววันนี้
                </div>
                """

            else:

                location = get_location_name(
                    latitude,
                    longitude
                )

                # เวลาเกิน 08:00 ถือว่าสาย
                if current_time <= "08:00:00":

                    status = "ปกติ"

                else:

                    status = "มาสาย"

                conn.execute(
                    """
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
                    """,
                    (
                        employee_id,
                        today,
                        current_time,
                        status,
                        float(latitude)
                        if latitude
                        else None,
                        float(longitude)
                        if longitude
                        else None,
                        location
                    )
                )

                conn.commit()

                status_class = (
                    "ok"
                    if status == "ปกติ"
                    else "bad"
                )

                message_template = """
                <div class="success-box">

                    <h3>
                        ✅ ลงเวลาเข้าสำเร็จ
                    </h3>

                    <p>
                        พนักงาน:
                        <b>{{ name }}</b>
                    </p>

                    <p>
                        เวลา:
                        <b>{{ time }}</b>
                    </p>

                    <p>
                        สถานะ:

                        <span
                            class="badge {{ status_class }}"
                        >
                            {{ status }}
                        </span>

                    </p>

                    <p>
                        📍
                        <b>{{ location }}</b>
                    </p>

                </div>
                """

                message = render_template_string(
                    message_template,

                    name=employee["name"],

                    time=current_time,

                    status=status,

                    status_class=status_class,

                    location=location

                )

        # -------------------------------------------------
        # CHECK OUT
        # -------------------------------------------------

        elif action == "check_out":

            if record is None:

                message = """
                <div class="error-box">

                    ⚠️
                    ยังไม่มีข้อมูล
                    ลงเวลาเข้าวันนี้

                </div>
                """

            elif record["time_out"]:

                message = """
                <div class="error-box">

                    ⚠️
                    ลงเวลาออกไปแล้ววันนี้

                </div>
                """

            else:

                try:

                    start = datetime.strptime(
                        record["time_in"],
                        "%H:%M:%S"
                    )

                    end = datetime.strptime(
                        current_time,
                        "%H:%M:%S"
                    )

                    seconds = (
                        end - start
                    ).total_seconds()

                    work_hours = (
                        seconds / 3600
                    )

                    if work_hours < 0:

                        work_hours = 0

                except (
                    ValueError,
                    TypeError
                ):

                    work_hours = 0

                if work_hours > 8:

                    ot_hours = (
                        work_hours - 8
                    )

                else:

                    ot_hours = 0

                location = get_location_name(
                    latitude,
                    longitude
                )

                if location == "-":

                    location = (
                        record["location"]
                        or "-"
                    )

                conn.execute(
                    """
                    UPDATE attendance

                    SET
                        time_out=?,
                        work_hours=?,
                        ot_hours=?,
                        latitude=?,
                        longitude=?,
                        location=?

                    WHERE id=?
                    """,
                    (
                        current_time,
                        work_hours,
                        ot_hours,
                        float(latitude)
                        if latitude
                        else record["latitude"],
                        float(longitude)
                        if longitude
                        else record["longitude"],
                        location,
                        record["id"]
                    )
                )

                conn.commit()

                message_template = """
                <div class="success-box">

                    <h3>
                        ✅ ลงเวลาออกสำเร็จ
                    </h3>

                    <p>
                        พนักงาน:
                        <b>{{ name }}</b>
                    </p>

                    <p>
                        เวลาออก:
                        <b>{{ time }}</b>
                    </p>

                    <p>
                        ชั่วโมงทำงาน:
                        <b>
                            {{ "%.2f"|format(hours) }}
                        </b>
                        ชั่วโมง
                    </p>

                    <p>
                        OT:
                        <b>
                            {{ "%.2f"|format(ot) }}
                        </b>
                        ชั่วโมง
                    </p>

                    <p>
                        📍
                        <b>{{ location }}</b>
                    </p>

                </div>
                """

                message = render_template_string(
                    message_template,

                    name=employee["name"],

                    time=current_time,

                    hours=work_hours,

                    ot=ot_hours,

                    location=location

                )

        conn.close()

    # -----------------------------------------------------
    # LOAD DATA
    # -----------------------------------------------------

    conn = get_db()

    today = now().strftime(
        "%Y-%m-%d"
    )

    employees = conn.execute(
        """
        SELECT *
        FROM employees
        ORDER BY name
        """
    ).fetchall()

    records = conn.execute(
        """
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

        ON a.employee_id = e.id

        WHERE a.work_date=?

        ORDER BY a.time_in DESC
        """,
        (today,)
    ).fetchall()

    conn.close()

    content = """
    <h1>
        ⏰ ลงเวลาเข้า–ออก
    </h1>

    {{ message|safe }}

    <div class="panel">

        <h3>
            📝 ลงเวลาพนักงาน
        </h3>

        <form
            method="post"
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

                <option
                    value="{{ e['id'] }}"
                >

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
                onclick="getGPS()"
            >
                📍 ตรวจตำแหน่ง
            </button>


            <div
                id="gpsStatus"
                class="info-box"
            >
                กดตรวจตำแหน่งก่อนลงเวลา
            </div>

            <br>


            <button
                name="action"
                value="check_in"
            >
                🟢 เข้างาน
            </button>


            <button
                name="action"
                value="check_out"
                class="gray"
            >
                🔴 ออกงาน
            </button>

        </form>

    </div>


    <div class="panel">

        <h3>
            📋 การลงเวลาวันนี้
        </h3>

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

                    {{ r["name"] or "-" }}

                </td>


                <td>
                    {{ r["time_in"] or "-" }}
                </td>


                <td>
                    {{ r["time_out"] or "-" }}
                </td>


                <td>

                    {% if r["status"] == "มาสาย" %}

                    <span class="badge bad">
                        มาสาย
                    </span>

                    {% else %}

                    <span class="badge ok">
                        {{ r["status"] or "-" }}
                    </span>

                    {% endif %}

                </td>


                <td>

                    {{
                        "%.2f"|format(
                            r["work_hours"] or 0
                        )
                    }}

                </td>


                <td>

                    {{
                        "%.2f"|format(
                            r["ot_hours"] or 0
                        )
                    }}

                </td>


                <td>

                    {{
                        r["location"]
                        if "location"
                        in r.keys()
                        else "-"
                    }}

                </td>

            </tr>


            {% else %}

            <tr>

                <td colspan="7">

                    ยังไม่มีข้อมูลวันนี้

                </td>

            </tr>

            {% endfor %}

        </table>

        </div>

    </div>


    <script>

    function getGPS() {

        const status =
            document.getElementById(
                "gpsStatus"
            );

        if (!navigator.geolocation) {

            status.innerHTML =
                "❌ อุปกรณ์ไม่รองรับ GPS";

            return;

        }

        status.innerHTML =
            "📍 กำลังตรวจตำแหน่ง...";

        navigator.geolocation.getCurrentPosition(

            function(position) {

                const lat =
                    position.coords.latitude;

                const lng =
                    position.coords.longitude;

                document.getElementById(
                    "latitude"
                ).value = lat;

                document.getElementById(
                    "longitude"
                ).value = lng;

                status.innerHTML =
                    "✅ ตรวจตำแหน่งเรียบร้อย " +
                    "สามารถลงเวลาได้";

            },

            function(error) {

                status.innerHTML =
                    "❌ ไม่สามารถรับตำแหน่งได้ " +
                    "กรุณาอนุญาต Location";

            },

            {

                enableHighAccuracy: true,

                timeout: 10000,

                maximumAge: 0

            }

        );

    }

    </script>
    """

    return page(
        render_template_string(
            content,

            employees=employees,

            records=records,

            message=message
        )
    )


# =========================================================
# LEAVE SYSTEM
# =========================================================

@app.route(
    "/leaves",
    methods=["GET", "POST"]
)
def leaves():

    message = ""

    conn = get_db()

    if request.method == "POST":

        employee_id = request.form.get(
            "employee_id",
            ""
        ).strip()

        leave_type = request.form.get(
            "leave_type",
            ""
        )

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

        try:

            start = datetime.strptime(
                start_date,
                "%Y-%m-%d"
            )

            end = datetime.strptime(
                end_date,
                "%Y-%m-%d"
            )

            days = (
                end - start
            ).days + 1

            if days < 1:

                days = 1

        except (
            ValueError,
            TypeError
        ):

            days = 1

        employee = conn.execute(
            """
            SELECT *
            FROM employees
            WHERE id=?
            """,
            (employee_id,)
        ).fetchone()

        if employee is None:

            message = """
            <div class="error-box">
                ❌ ไม่พบพนักงาน
            </div>
            """

        else:

            conn.execute(
                """
                INSERT INTO leaves
                (
                    employee_id,
                    leave_type,
                    start_date,
                    end_date,
                    days,
                    reason
                )

                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    leave_type,
                    start_date,
                    end_date,
                    days,
                    reason
                )
            )

            conn.commit()

            message = """
            <div class="success-box">
                ✅ ส่งใบลาเรียบร้อยแล้ว
            </div>
            """

    employees = conn.execute(
        """
        SELECT *
        FROM employees
        ORDER BY name
        """
    ).fetchall()

    leave_rows = conn.execute(
        """
        SELECT

            l.*,

            e.name

        FROM leaves l

        LEFT JOIN employees e

        ON l.employee_id = e.id

        ORDER BY l.id DESC
        """
    ).fetchall()

    conn.close()

    content = """
    <h1>
        📅 ระบบลา
    </h1>

    {{ message|safe }}


    <div class="panel">

        <h3>
            📝 ยื่นใบลา
        </h3>

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

                <option
                    value="{{ e['id'] }}"
                >

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
                required
            >

                <option value="">
                    -- เลือกประเภท --
                </option>

                <option>
                    ลาป่วย
                </option>

                <option>
                    ลากิจ
                </option>

                <option>
                    ลาพักร้อน
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
                placeholder="ระบุเหตุผล"
            ></textarea>


            <button>
                📤 ส่งใบลา
            </button>

        </form>

    </div>


    <div class="panel">

        <h3>
            📋 รายการลา
        </h3>

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
                    วันที่
                </th>

                <th>
                    จำนวน
                </th>

                <th>
                    สถานะ
                </th>

            </tr>


            {% for l in leave_rows %}

            <tr>

                <td>
                    {{ l["name"] or "-" }}
                </td>

                <td>
                    {{ l["leave_type"] }}
                </td>

                <td>

                    {{ l["start_date"] }}

                    <br>

                    ถึง

                    <br>

                    {{ l["end_date"] }}

                </td>

                <td>
                    {{ l["days"] }}
                    วัน
                </td>

                <td>

                    {% if l["status"] == "อนุมัติ" %}

                    <span class="badge ok">
                        อนุมัติ
                    </span>

                    {% elif l["status"] == "ไม่อนุมัติ" %}

                    <span class="badge bad">
                        ไม่อนุมัติ
                    </span>

                    {% else %}

                    <span class="badge wait">
                        รออนุมัติ
                    </span>

                    {% endif %}

                </td>

            </tr>


            {% else %}

            <tr>

                <td colspan="5">
                    ยังไม่มีใบลา
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

            employees=employees,

            leave_rows=leave_rows,

            message=message
        )
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin():

    message = ""

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        if password == ADMIN_PASSWORD:

            session["admin_unlocked"] = True

            return redirect(
                "/admin"
            )

        message = """
        <div class="error-box">
            ❌ รหัสฝ่ายบัญชีไม่ถูกต้อง
        </div>
        """

    if not admin_unlocked():

        content = """
        <div class="panel">

            <h1>
                🔐 ฝ่ายบัญชี
            </h1>

            <p>
                ส่วนนี้สำหรับผู้มีสิทธิ์
                ฝ่ายบัญชี
            </p>

            {{ message|safe }}

            <form method="post">

                <label>
                    รหัสฝ่ายบัญชี
                </label>

                <input
                    type="password"
                    name="password"
                    placeholder="กรอกรหัส"
                    required
                >

                <button>
                    🔓 เข้าสู่ระบบ
                </button>

            </form>

        </div>
        """

        return page(
            render_template_string(
                content,
                message=message
            )
        )

    conn = get_db()

    employee_count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM employees
        """
    ).fetchone()["n"]

    pending_leave = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM leaves

        WHERE status='รออนุมัติ'
        """
    ).fetchone()["n"]

    conn.close()

    content = """
    <h1>
        👑 ฝ่ายบัญชี
    </h1>

    <div class="cards">

        <div class="card">

            <div class="card-title">
                พนักงาน
            </div>

            <div class="card-number">
                {{ employee_count }}
            </div>

        </div>

        <div class="card">

            <div class="card-title">
                ใบรออนุมัติ
            </div>

            <div class="card-number">
                {{ pending_leave }}
            </div>

        </div>

    </div>


    <div class="panel">

        <h3>
            🛠️ จัดการระบบ
        </h3>

        <p>
            <a
                class="btn blue"
                href="/employees"
            >
                👥 พนักงาน
            </a>
        </p>

        <p>
            <a
                class="btn"
                href="/salary"
            >
                💰 เงินเดือน + OT
            </a>
        </p>

        <p>
            <a
                class="btn green"
                href="/reports"
            >
                📊 รายงาน
            </a>
        </p>

        <p>
            <a
                class="btn gray"
                href="/approve_leaves"
            >
                📅 อนุมัติใบลา
            </a>
        </p>

        <p>
            <a
                class="btn danger"
                href="/admin_logout"
            >
                🔒 ออกจากฝ่ายบัญชี
            </a>
        </p>

    </div>
    """

    return page(
        render_template_string(
            content,

            employee_count=
                employee_count,

            pending_leave=
                pending_leave
        )
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route(
    "/admin_logout"
)
def admin_logout():

    session.clear()

    return redirect("/")


# =========================================================
# EMPLOYEE MANAGEMENT
# =========================================================

@app.route(
    "/employees",
    methods=["GET", "POST"]
)
def employees():

    if not admin_unlocked():

        return redirect("/admin")

    conn = get_db()

    message = ""

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
                    "0"
                )
            )

        except (
            ValueError,
            TypeError
        ):

            salary = 0

        if not employee_id or not name:

            message = """
            <div class="error-box">
                ❌ กรุณากรอกข้อมูลให้ครบ
            </div>
            """

        else:

            try:

                conn.execute(
                    """
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
                    """,
                    (
                        employee_id,
                        name,
                        position,
                        salary,
                        phone,
                        start_date
                    )
                )

                conn.commit()

                message = """
                <div class="success-box">
                    ✅ เพิ่มพนักงานสำเร็จ
                </div>
                """

            except sqlite3.IntegrityError:

                message = """
                <div class="error-box">
                    ❌ รหัสพนักงานนี้มีอยู่แล้ว
                </div>
                """

    rows = conn.execute(
        """
        SELECT *
        FROM employees
        ORDER BY id
        """
    ).fetchall()

    conn.close()

    content = """
    <h1>
        👥 จัดการพนักงาน
    </h1>

    {{ message|safe }}


    <div class="panel">

        <h3>
            ➕ เพิ่มพนักงาน
        </h3>

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
                value="0"
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
                💾 เพิ่มพนักงาน
            </button>

        </form>

    </div>


    <div class="panel">

        <h3>
            📋 รายชื่อพนักงาน
        </h3>

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

                    {{
                        "%.2f"|format(
                            e["salary"] or 0
                        )
                    }}

                </td>

                <td>

                    <a
                        class="btn blue"
                        href=
                        "/edit_employee/{{ e['id'] }}"
                    >
                        ✏️
                    </a>

                    <a
                        class="btn danger"
                        href=
                        "/delete_employee/{{ e['id'] }}"
                        onclick=
                        "return confirm('ยืนยันการลบพนักงาน?')"
                    >
                        🗑️
                    </a>

                </td>

            </tr>


            {% else %}

            <tr>

                <td colspan="5">
                    ยังไม่มีพนักงาน
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

            rows=rows,

            message=message
        )
    )


# =========================================================
# EDIT EMPLOYEE
# =========================================================

@app.route(
    "/edit_employee/<employee_id>",
    methods=["GET", "POST"]
)
def edit_employee(employee_id):

    if not admin_unlocked():

        return redirect("/admin")

    conn = get_db()

    employee = conn.execute(
        """
        SELECT *
        FROM employees
        WHERE id=?
        """,
        (employee_id,)
    ).fetchone()

    if employee is None:

        conn.close()

        return page(
            """
            <div class="error-box">
                ❌ ไม่พบพนักงาน
            </div>
            """
        )

    if request.method == "POST":

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
                    "0"
                )
            )

        except (
            ValueError,
            TypeError
        ):

            salary = 0

        conn.execute(
            """
            UPDATE employees

            SET
                name=?,
                position=?,
                salary=?,
                phone=?,
                start_date=?

            WHERE id=?
            """,
            (
                name,
                position,
                salary,
                phone,
                start_date,
                employee_id
            )
        )

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
                value=
                "{{ e['position'] or '' }}"
            >


            <label>
                เงินเดือน
            </label>

            <input
                type="number"
                step="0.01"
                name="salary"
                value=
                "{{ e['salary'] or 0 }}"
            >


            <label>
                เบอร์โทร
            </label>

            <input
                name="phone"
                value=
                "{{ e['phone'] or '' }}"
            >


            <label>
                วันที่เริ่มงาน
            </label>

            <input
                type="date"
                name="start_date"
                value=
                "{{ e['start_date'] or '' }}"
            >


            <button>
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

    return page(
        render_template_string(
            content,
            e=employee
        )
    )


# =========================================================
# DELETE EMPLOYEE
# =========================================================

@app.route(
    "/delete_employee/<employee_id>"
)
def delete_employee(employee_id):

    if not admin_unlocked():

        return redirect("/admin")

    conn = get_db()

    conn.execute(
        """
        DELETE FROM attendance
        WHERE employee_id=?
        """,
        (employee_id,)
    )

    conn.execute(
        """
        DELETE FROM leaves
        WHERE employee_id=?
        """,
        (employee_id,)
    )

    conn.execute(
        """
        DELETE FROM employees
        WHERE id=?
        """,
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

    if not admin_unlocked():

        return redirect("/admin")

    conn = get_db()

    month = request.args.get(
        "month",
        now().strftime("%Y-%m")
    )

    employees = conn.execute(
        """
        SELECT *
        FROM employees
        ORDER BY name
        """
    ).fetchall()

    result = []

    for employee in employees:

        attendance = conn.execute(
            """
            SELECT

                COALESCE(
                    SUM(work_hours),
                    0
                ) AS work_hours,

                COALESCE(
                    SUM(ot_hours),
                    0
                ) AS ot_hours

            FROM attendance

            WHERE employee_id=?

            AND substr(
                work_date,
                1,
                7
            )=?
            """,
            (
                employee["id"],
                month
            )
        ).fetchone()

        base_salary = (
            employee["salary"]
            or 0
        )

        work_hours = (
            attendance["work_hours"]
            or 0
        )

        ot_hours = (
            attendance["ot_hours"]
            or 0
        )

        hourly_rate = (
            base_salary / 30 / 8
            if base_salary > 0
            else 0
        )

        ot_rate = (
            hourly_rate * 1.5
        )

        ot_pay = (
            ot_hours * ot_rate
        )

        total_salary = (
            base_salary
            + ot_pay
        )

        result.append({

            "id":
                employee["id"],

            "name":
                employee["name"],

            "salary":
                base_salary,

            "work_hours":
                work_hours,

            "ot_hours":
                ot_hours,

            "ot_pay":
                ot_pay,

            "total":
                total_salary

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


    <div class="panel">

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
                    ชั่วโมง
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


            {% for r in result %}

            <tr>

                <td>
                    {{ r["id"] }}
                </td>

                <td>
                    {{ r["name"] }}
                </td>

                <td>

                    {{
                        "%.2f"|format(
                            r["salary"]
                        )
                    }}

                </td>

                <td>

                    {{
                        "%.2f"|format(
                            r["work_hours"]
                        )
                    }}

                </td>

                <td>

                    {{
                        "%.2f"|format(
                            r["ot_hours"]
                        )
                    }}

                </td>

                <td>

                    {{
                        "%.2f"|format(
                            r["ot_pay"]
                        )
                    }}

                </td>

                <td>

                    <b>

                        {{
                            "%.2f"|format(
                                r["total"]
                            )
                        }}

                    </b>

                </td>

            </tr>


            {% else %}

            <tr>

                <td colspan="7">
                    ยังไม่มีข้อมูล
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

            result=result,

            month=month
        )
    )


# =========================================================
# APPROVE LEAVES
# =========================================================

@app.route(
    "/approve_leaves",
    methods=["GET", "POST"]
)
def approve_leaves():

    if not admin_unlocked():

        return redirect("/admin")

    conn = get_db()

    message = ""

    if request.method == "POST":

        leave_id = request.form.get(
            "leave_id",
            ""
        )

        action = request.form.get(
            "action",
            ""
        )

        if action == "approve":

            status = "อนุมัติ"

        elif action == "reject":

            status = "ไม่อนุมัติ"

        else:

            status = "รออนุมัติ"

        conn.execute(
            """
            UPDATE leaves

            SET status=?

            WHERE id=?
            """,
            (
                status,
                leave_id
            )
        )

        conn.commit()

        message = """
        <div class="success-box">
            ✅ เปลี่ยนสถานะใบลาแล้ว
        </div>
        """

    rows = conn.execute(
        """
        SELECT

            l.*,

            e.name

        FROM leaves l

        LEFT JOIN employees e

        ON l.employee_id = e.id

        ORDER BY l.id DESC
        """
    ).fetchall()

    conn.close()

    content = """
    <h1>
        📅 อนุมัติใบลา
    </h1>

    {{ message|safe }}


    <div class="panel">

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
                    วันที่
                </th>

                <th>
                    จำนวน
                </th>

                <th>
                    เหตุผล
                </th>

                <th>
                    สถานะ
                </th>

                <th>
                    จัดการ
                </th>

            </tr>


            {% for r in rows %}

            <tr>

                <td>

                    {{ r["employee_id"] }}

                    <br>

                    {{ r["name"] or "-" }}

                </td>


                <td>
                    {{ r["leave_type"] }}
                </td>


                <td>

                    {{ r["start_date"] }}

                    <br>
                    ถึง
                    <br>

                    {{ r["end_date"] }}

                </td>


                <td>

                    {{ r["days"] }}
                    วัน

                </td>


                <td>

                    {{ r["reason"] or "-" }}

                </td>


                <td>

                    {% if r["status"] == "อนุมัติ" %}

                    <span class="badge ok">
                        อนุมัติ
                    </span>

                    {% elif r["status"] == "ไม่อนุมัติ" %}

                    <span class="badge bad">
                        ไม่อนุมัติ
                    </span>

                    {% else %}

                    <span class="badge wait">
                        รออนุมัติ
                    </span>

                    {% endif %}

                </td>


                <td>

                    {% if r["status"] == "รออนุมัติ" %}

                    <form
                        method="post"
                        style="display:inline"
                    >

                        <input
                            type="hidden"
                            name="leave_id"
                            value="{{ r['id'] }}"
                        >

                        <button
                            name="action"
                            value="approve"
                            class="green"
                        >
                            ✓
                        </button>

                    </form>


                    <form
                        method="post"
                        style="display:inline"
                    >

                        <input
                            type="hidden"
                            name="leave_id"
                            value="{{ r['id'] }}"
                        >

                        <button
                            name="action"
                            value="reject"
                            class="danger"
                        >
                            ✕
                        </button>

                    </form>

                    {% else %}

                    ดำเนินการแล้ว

                    {% endif %}

                </td>

            </tr>


            {% else %}

            <tr>

                <td colspan="7">
                    ยังไม่มีใบลา
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

            rows=rows,

            message=message
        )
    )


# =========================================================
# REPORTS
# =========================================================

@app.route("/reports")
def reports():

    if not admin_unlocked():

        return redirect("/admin")

    conn = get_db()

    month = request.args.get(
        "month",
        now().strftime("%Y-%m")
    )

    employee_count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM employees
        """
    ).fetchone()["n"]

    attendance_count = conn.execute(
        """
        SELECT COUNT(*) AS n

        FROM attendance

        WHERE substr(
            work_date,
            1,
            7
        )=?
        """,
        (month,)
    ).fetchone()["n"]

    late_count = conn.execute(
        """
        SELECT COUNT(*) AS n

        FROM attendance

        WHERE substr(
            work_date,
            1,
            7
        )=?

        AND status='มาสาย'
        """,
        (month,)
    ).fetchone()["n"]

    ot_total = conn.execute(
        """
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
        """,
        (month,)
    ).fetchone()["n"]

    leave_count = conn.execute(
        """
        SELECT COUNT(*) AS n

        FROM leaves

        WHERE substr(
            start_date,
            1,
            7
        )=?
        """,
        (month,)
    ).fetchone()["n"]

    rows = conn.execute(
        """
        SELECT

            e.id,
            e.name,
            e.salary,

            COALESCE(
                SUM(a.work_hours),
                0
            ) AS work_hours,

            COALESCE(
                SUM(a.ot_hours),
                0
            ) AS ot_hours,

            COUNT(a.id)
                AS attendance_days,

            COALESCE(
                SUM(
                    CASE
                        WHEN a.status='มาสาย'
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS late_days

        FROM employees e

        LEFT JOIN attendance a

        ON e.id = a.employee_id

        AND substr(
            a.work_date,
            1,
            7
        )=?

        GROUP BY
            e.id,
            e.name,
            e.salary

        ORDER BY e.id
        """,
        (month,)
    ).fetchall()

    conn.close()

    content = """
    <h1>
        📊 รายงานระบบ
    </h1>


    <div class="panel">

        <form method="get">

            <label>
                เลือกเดือน
            </label>

            <input
                type="month"
                name="month"
                value="{{ month }}"
            >

            <button>
                🔎 แสดงรายงาน
            </button>

        </form>

    </div>


    <div class="cards">

        <div class="card">

            <div class="card-title">
                พนักงาน
            </div>

            <div class="card-number">
                {{ employee_count }}
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                การลงเวลา
            </div>

            <div class="card-number">
                {{ attendance_count }}
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                มาสาย
            </div>

            <div class="card-number">
                {{ late_count }}
            </div>

        </div>


        <div class="card">

            <div class="card-title">
                OT รวม
            </div>

            <div class="card-number">

                {{
                    "%.2f"|format(
                        ot_total or 0
                    )
                }}

            </div>

        </div>

    </div>


    <div class="panel">

        <h3>
            📋 รายงานรายบุคคล
        </h3>

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
                    วันลงเวลา
                </th>

                <th>
                    ชั่วโมง
                </th>

                <th>
                    OT
                </th>

                <th>
                    มาสาย
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

                    {{
                        "%.2f"|format(
                            r["salary"] or 0
                        )
                    }}

                </td>

                <td>
                    {{ r["attendance_days"] or 0 }}
                </td>

                <td>

                    {{
                        "%.2f"|format(
                            r["work_hours"] or 0
                        )
                    }}

                </td>

                <td>

                    {{
                        "%.2f"|format(
                            r["ot_hours"] or 0
                        )
                    }}

                </td>

                <td>
                    {{ r["late_days"] or 0 }}
                </td>

            </tr>


            {% else %}

            <tr>

                <td colspan="7">
                    ยังไม่มีข้อมูล
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

            employee_count=
                employee_count,

            attendance_count=
                attendance_count,

            late_count=
                late_count,

            ot_total=
                ot_total,

            leave_count=
                leave_count,

            rows=rows
        )
    )


# =========================================================
# MANUAL / USER GUIDE
# =========================================================

@app.route("/manual")
def manual():

    content = """
    <h1>
        📖 คู่มือการใช้งาน
    </h1>


    <div class="panel">

        <h3>
            1. 🏠 หน้าแรก
        </h3>

        <div class="manual-item">

            หน้าแรกใช้สำหรับดูภาพรวม
            ของระบบ เช่น จำนวนพนักงาน
            จำนวนการลงเวลา
            จำนวนคนมาสาย
            และ OT ของวันนั้น

        </div>


        <h3>
            2. ⏰ การลงเวลา
        </h3>

        <div class="manual-item">

            เลือกรหัสพนักงาน
            จากนั้นกดตรวจตำแหน่ง
            แล้วเลือก
            <b>เข้างาน</b>
            หรือ
            <b>ออกงาน</b>

            <br><br>

            ระบบจะบันทึกเวลา
            และตรวจสอบตำแหน่ง
            ตามพื้นที่ที่กำหนดไว้

        </div>


        <h3>
            3. 📅 การลา
        </h3>

        <div class="manual-item">

            เลือกพนักงาน
            เลือกประเภทการลา
            กำหนดวันที่
            และกรอกเหตุผล
            จากนั้นกดส่งใบลา

            <br><br>

            ใบลาจะมีสถานะ
            <b>รออนุมัติ</b>
            จนกว่าฝ่ายบัญชี
            จะดำเนินการ

        </div>


        <h3>
            4. 🔐 ฝ่ายบัญชี
        </h3>

        <div class="manual-item">

            ส่วนฝ่ายบัญชีใช้สำหรับ
            ผู้ที่มีรหัสผ่านเท่านั้น

            <br><br>

            สามารถจัดการข้อมูลพนักงาน
            เงินเดือน
            OT
            ใบลา
            และรายงานได้

        </div>


        <h3>
            5. 👥 จัดการพนักงาน
        </h3>

        <div class="manual-item">

            ฝ่ายบัญชีสามารถ
            เพิ่ม แก้ไข และลบ
            ข้อมูลพนักงานได้

        </div>


        <h3>
            6. 💰 เงินเดือน
        </h3>

        <div class="manual-item">

            ระบบนำเงินเดือนพื้นฐาน
            มาคำนวณร่วมกับ
            ชั่วโมง OT
            เพื่อแสดงยอดรวม

        </div>


        <h3>
            7. 📊 รายงาน
        </h3>

        <div class="manual-item">

            สามารถเลือกเดือน
            เพื่อดูข้อมูลการทำงาน
            จำนวนครั้งลงเวลา
            การมาสาย
            ชั่วโมง OT
            และข้อมูลพนักงาน

        </div>


        <div class="info-box">

            💡
            หากพบปัญหาในการใช้งาน
            ให้ตรวจสอบการเชื่อมต่ออินเทอร์เน็ต
            และสิทธิ์การเข้าถึง Location
            ของอุปกรณ์

        </div>

    </div>
    """

    return page(
        render_template_string(
            content
        )
    )


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return page(
        """
        <div class="error-box">

            <h2>
                ❌ ไม่พบหน้าที่ต้องการ
            </h2>

            <a
                class="btn"
                href="/"
            >
                🏠 กลับหน้าแรก
            </a>

        </div>
        """
    ), 404


@app.errorhandler(500)
def internal_error(error):

    return page(
        """
        <div class="error-box">

            <h2>
                ❌ เกิดข้อผิดพลาด
            </h2>

            <p>
                กรุณาลองใหม่อีกครั้ง
            </p>

            <a
                class="btn"
                href="/"
            >
                🏠 กลับหน้าแรก
            </a>

        </div>
        """
    ), 500


# =========================================================
# START DATABASE
# =========================================================

init_db()


# =========================================================
# RUN APP
# =========================================================

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
    