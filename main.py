from flask import Flask, render_template_string, request, redirect, url_for
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB = "pizza_company.db"


# =========================
# DATABASE
# =========================
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            salary REAL NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            date TEXT NOT NULL,
            time_in TEXT,
            time_out TEXT,
            work_hours REAL DEFAULT 0,
            ot_hours REAL DEFAULT 0,
            status TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================
# STYLE
# =========================
STYLE = """
<style>
body {
    font-family: Arial, sans-serif;
    background: #f5f5f5;
    margin: 0;
}

header {
    background: #d62828;
    color: white;
    padding: 20px;
    text-align: center;
}

.container {
    width: 90%;
    max-width: 1100px;
    margin: 25px auto;
}

.cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 15px;
}

.card {
    background: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 2px 8px #ccc;
}

.card h2 {
    margin: 0;
}

.menu {
    margin: 20px 0;
}

button, .btn {
    background: #d62828;
    color: white;
    border: none;
    padding: 10px 15px;
    border-radius: 7px;
    text-decoration: none;
    cursor: pointer;
}

.btn-green {
    background: #2a9d8f;
}

.btn-blue {
    background: #457b9d;
}

.btn-gray {
    background: #555;
}

table {
    width: 100%;
    background: white;
    border-collapse: collapse;
    margin-top: 20px;
}

th, td {
    padding: 12px;
    border-bottom: 1px solid #ddd;
    text-align: center;
}

th {
    background: #eee;
}

input, select {
    padding: 10px;
    margin: 5px;
    width: 90%;
}

.form-box {
    background: white;
    padding: 25px;
    border-radius: 12px;
}

.stat {
    font-size: 28px;
    font-weight: bold;
    margin-top: 10px;
}

.late {
    color: red;
    font-weight: bold;
}

.normal {
    color: green;
    font-weight: bold;
}
</style>
"""


# =========================
# DASHBOARD
# =========================
@app.route("/")
def home():
    conn = get_db()

    employee_count = conn.execute(
        "SELECT COUNT(*) FROM employees"
    ).fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")

    attendance_count = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE date=?",
        (today,)
    ).fetchone()[0]

    ot_total = conn.execute(
        "SELECT COALESCE(SUM(ot_hours),0) FROM attendance"
    ).fetchone()[0]

    salary_total = conn.execute(
        "SELECT COALESCE(SUM(salary),0) FROM employees"
    ).fetchone()[0]

    conn.close()

    return render_template_string(STYLE + """
    <header>
        <h1>🍕 Pizza Company Management</h1>
        <p>ระบบจัดการพนักงาน เวลาเข้าออก และเงินเดือน</p>
    </header>

    <div class="container">

        <div class="menu">
            <a class="btn" href="/employees">👨‍🍳 จัดการพนักงาน</a>
            <a class="btn btn-blue" href="/attendance">⏰ บันทึกเวลา</a>
            <a class="btn btn-green" href="/salary">💰 คำนวณเงินเดือน</a>
        </div>

        <div class="cards">

            <div class="card">
                <h3>พนักงานทั้งหมด</h3>
                <div class="stat">{{ employee_count }}</div>
                <p>คน</p>
            </div>

            <div class="card">
                <h3>เข้างานวันนี้</h3>
                <div class="stat">{{ attendance_count }}</div>
                <p>รายการ</p>
            </div>

            <div class="card">
                <h3>OT รวม</h3>
                <div class="stat">{{ "%.2f"|format(ot_total) }}</div>
                <p>ชั่วโมง</p>
            </div>

            <div class="card">
                <h3>เงินเดือนรวม</h3>
                <div class="stat">{{ "%.2f"|format(salary_total) }}</div>
                <p>บาท</p>
            </div>

        </div>

    </div>
    """,
    employee_count=employee_count,
    attendance_count=attendance_count,
    ot_total=ot_total,
    salary_total=salary_total)


# =========================
# EMPLOYEES
# =========================
@app.route("/employees")
def employees():
    conn = get_db()
    data = conn.execute(
        "SELECT * FROM employees"
    ).fetchall()
    conn.close()

    return render_template_string(STYLE + """
    <header><h1>👨‍🍳 จัดการพนักงาน</h1></header>

    <div class="container">

        <a class="btn" href="/">← กลับหน้าหลัก</a>
        <a class="btn btn-green" href="/add_employee">+ เพิ่มพนักงาน</a>

        <table>
            <tr>
                <th>รหัส</th>
                <th>ชื่อ</th>
                <th>เงินเดือน</th>
                <th>จัดการ</th>
            </tr>

            {% for e in data %}
            <tr>
                <td>{{ e["id"] }}</td>
                <td>{{ e["name"] }}</td>
                <td>{{ "%.2f"|format(e["salary"]) }} บาท</td>
                <td>
                    <a class="btn btn-blue"
                       href="/edit_employee/{{ e['id'] }}">
                       แก้ไข
                    </a>

                    <a class="btn"
                       href="/delete_employee/{{ e['id'] }}"
                       onclick="return confirm('ต้องการลบพนักงานคนนี้หรือไม่?')">
                       ลบ
                    </a>
                </td>
            </tr>
            {% endfor %}
        </table>

    </div>
    """, data=data)


# =========================
# ADD EMPLOYEE
# =========================
@app.route("/add_employee", methods=["GET", "POST"])
def add_employee():

    if request.method == "POST":

        employee_id = request.form["id"]
        name = request.form["name"]
        salary = float(request.form["salary"])

        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO employees (id,name,salary) VALUES (?,?,?)",
                (employee_id, name, salary)
            )
            conn.commit()

        except sqlite3.IntegrityError:
            conn.close()
            return "รหัสพนักงานนี้มีอยู่แล้ว <br><br><a href='/add_employee'>กลับ</a>"

        conn.close()

        return redirect(url_for("employees"))

    return render_template_string(STYLE + """
    <header><h1>➕ เพิ่มพนักงาน</h1></header>

    <div class="container">

        <div class="form-box">

            <form method="POST">

                <label>รหัสพนักงาน</label>
                <input name="id" required>

                <label>ชื่อพนักงาน</label>
                <input name="name" required>

                <label>เงินเดือน</label>
                <input name="salary" type="number" step="0.01" required>

                <button type="submit">บันทึกข้อมูล</button>

            </form>

        </div>

    </div>
    """)


# =========================
# EDIT EMPLOYEE
# =========================
@app.route("/edit_employee/<employee_id>", methods=["GET", "POST"])
def edit_employee(employee_id):

    conn = get_db()

    employee = conn.execute(
        "SELECT * FROM employees WHERE id=?",
        (employee_id,)
    ).fetchone()

    if request.method == "POST":

        name = request.form["name"]
        salary = float(request.form["salary"])

        conn.execute(
            "UPDATE employees SET name=?, salary=? WHERE id=?",
            (name, salary, employee_id)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("employees"))

    conn.close()

    return render_template_string(STYLE + """
    <header><h1>✏️ แก้ไขพนักงาน</h1></header>

    <div class="container">

        <div class="form-box">

            <form method="POST">

                <label>ชื่อพนักงาน</label>
                <input name="name"
                       value="{{ employee['name'] }}"
                       required>

                <label>เงินเดือน</label>
                <input name="salary"
                       type="number"
                       step="0.01"
                       value="{{ employee['salary'] }}"
                       required>

                <button type="submit">บันทึกการแก้ไข</button>

            </form>

        </div>

    </div>
    """, employee=employee)


# =========================
# DELETE EMPLOYEE
# =========================
@app.route("/delete_employee/<employee_id>")
def delete_employee(employee_id):

    conn = get_db()

    conn.execute(
        "DELETE FROM employees WHERE id=?",
        (employee_id,)
    )

    conn.execute(
        "DELETE FROM attendance WHERE employee_id=?",
        (employee_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("employees"))


# =========================
# ATTENDANCE
# =========================
@app.route("/attendance", methods=["GET", "POST"])
def attendance():

    conn = get_db()

    if request.method == "POST":

        employee_id = request.form["employee_id"]

        now = datetime.now()

        date = now.strftime("%Y-%m-%d")
        time_in = now.strftime("%H:%M")

        if now.hour >= 8:
            status = "มาสาย"
        else:
            status = "ปกติ"

        conn.execute("""
            INSERT INTO attendance
            (employee_id,date,time_in,status)
            VALUES (?,?,?,?)
        """, (employee_id, date, time_in, status))

        conn.commit()

    employees_data = conn.execute(
        "SELECT * FROM employees"
    ).fetchall()

    records = conn.execute("""
        SELECT attendance.*, employees.name
        FROM attendance
        JOIN employees
        ON attendance.employee_id = employees.id
        ORDER BY attendance.id DESC
    """).fetchall()

    conn.close()

    return render_template_string(STYLE + """
    <header>
        <h1>⏰ ระบบบันทึกเวลาเข้าออก</h1>
    </header>

    <div class="container">

        <a class="btn" href="/">← กลับหน้าหลัก</a>

        <div class="form-box">

            <h2>บันทึกเวลาเข้างาน</h2>

            <form method="POST">

                <select name="employee_id" required>

                    <option value="">-- เลือกพนักงาน --</option>

                    {% for e in employees_data %}

                    <option value="{{ e['id'] }}">
                        {{ e['id'] }} - {{ e['name'] }}
                    </option>

                    {% endfor %}

                </select>

                <button type="submit">
                    ⏰ บันทึกเวลาเข้างาน
                </button>

            </form>

        </div>

        <table>

            <tr>
                <th>วันที่</th>
                <th>พนักงาน</th>
                <th>เข้างาน</th>
                <th>ออกงาน</th>
                <th>ชั่วโมงทำงาน</th>
                <th>OT</th>
                <th>สถานะ</th>
            </tr>

            {% for r in records %}

            <tr>

                <td>{{ r["date"] }}</td>

                <td>{{ r["name"] }}</td>

                <td>{{ r["time_in"] or "-" }}</td>

                <td>{{ r["time_out"] or "-" }}</td>

                <td>{{ "%.2f"|format(r["work_hours"]) }}</td>

                <td>{{ "%.2f"|format(r["ot_hours"]) }}</td>

                <td>
                    {% if r["status"] == "มาสาย" %}
                        <span class="late">มาสาย</span>
                    {% else %}
                        <span class="normal">{{ r["status"] }}</span>
                    {% endif %}
                </td>

            </tr>

            {% endfor %}

        </table>

    </div>
    """,
    employees_data=employees_data,
    records=records)


# =========================
# SALARY
# =========================
@app.route("/salary")
def salary():

    conn = get_db()

    employees_data = conn.execute(
        "SELECT * FROM employees"
    ).fetchall()

    result = []

    for e in employees_data:

        salary = e["salary"]

        hourly_rate = salary / 30 / 8

        records = conn.execute("""
            SELECT
                COALESCE(SUM(work_hours),0),
                COALESCE(SUM(ot_hours),0)
            FROM attendance
            WHERE employee_id=?
        """, (e["id"],)).fetchone()

        work_hours = records[0]
        ot_hours = records[1]

        ot_pay = hourly_rate * 1.5 * ot_hours

        total = salary + ot_pay

        result.append({
            "id": e["id"],
            "name": e["name"],
            "salary": salary,
            "work_hours": work_hours,
            "ot_hours": ot_hours,
            "ot_pay": ot_pay,
            "total": total
        })

    conn.close()

    return render_template_string(STYLE + """
    <header>
        <h1>💰 ระบบคำนวณเงินเดือน</h1>
    </header>

    <div class="container">

        <a class="btn" href="/">← กลับหน้าหลัก</a>

        <table>

            <tr>
                <th>รหัส</th>
                <th>ชื่อ</th>
                <th>เงินเดือนพื้นฐาน</th>
                <th>ชั่วโมงทำงาน</th>
                <th>OT</th>
                <th>ค่าล่วงเวลา</th>
                <th>เงินเดือนรวม</th>
            </tr>

            {% for r in result %}

            <tr>

                <td>{{ r["id"] }}</td>

                <td>{{ r["name"] }}</td>

                <td>{{ "%.2f"|format(r["salary"]) }}</td>

                <td>{{ "%.2f"|format(r["work_hours"]) }}</td>

                <td>{{ "%.2f"|format(r["ot_hours"]) }}</td>

                <td>{{ "%.2f"|format(r["ot_pay"]) }}</td>

                <td>
                    <b>{{ "%.2f"|format(r["total"]) }} บาท</b>
                </td>

            </tr>

            {% endfor %}

        </table>

    </div>
    """, result=result)


# =========================
# START PROGRAM
# =========================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
