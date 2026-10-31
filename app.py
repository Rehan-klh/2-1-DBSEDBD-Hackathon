from datetime import date, datetime, timedelta
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, request


ROOT = Path(__file__).parent
DATABASE = ROOT / "workforce.db"
app = Flask(__name__, static_folder="static", static_url_path="")


@contextmanager
def connect():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with connect() as db:
        db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        if db.execute("SELECT COUNT(*) FROM departments").fetchone()[0]:
            return

        departments = [
            ("Front of House", "#2b6de8"),
            ("Kitchen", "#ed8b36"),
            ("Operations", "#7d5ce7"),
            ("Guest Services", "#22a68a"),
        ]
        db.executemany("INSERT INTO departments(name, color) VALUES (?, ?)", departments)
        employees = [
            ("Ava Patel", "ava@shiftwise.demo", 1, "Team Lead", 40),
            ("Noah Williams", "noah@shiftwise.demo", 1, "Associate", 32),
            ("Mia Chen", "mia@shiftwise.demo", 1, "Associate", 30),
            ("Liam Johnson", "liam@shiftwise.demo", 2, "Head Chef", 40),
            ("Sofia Garcia", "sofia@shiftwise.demo", 2, "Line Cook", 32),
            ("Ethan Brown", "ethan@shiftwise.demo", 2, "Prep Cook", 28),
            ("Isabella Davis", "isabella@shiftwise.demo", 3, "Coordinator", 36),
            ("Lucas Martin", "lucas@shiftwise.demo", 4, "Host", 32),
            ("Amara Okafor", "amara@shiftwise.demo", 4, "Associate", 24),
        ]
        db.executemany(
            """INSERT INTO employees(name, email, department_id, role, max_weekly_hours)
               VALUES (?, ?, ?, ?, ?)""",
            employees,
        )
        for employee_id in range(1, len(employees) + 1):
            db.executemany(
                """INSERT INTO availability(employee_id, weekday, start_time, end_time)
                   VALUES (?, ?, ?, ?)""",
                [(employee_id, day, "07:00", "22:00") for day in range(7)],
            )

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        schedule_id = db.execute(
            "INSERT INTO schedules(name, start_date, end_date) VALUES (?, ?, ?)",
            (f"Week of {week_start.strftime('%b %d').replace(' 0', ' ')}", week_start.isoformat(), week_end.isoformat()),
        ).lastrowid
        shift_seed = [
            (1, 0, "08:00", "14:00", "Opening", 2),
            (1, 0, "14:00", "20:00", "Closing", 2),
            (2, 0, "09:00", "15:00", "Prep", 2),
            (2, 0, "15:00", "21:00", "Dinner service", 2),
            (3, 1, "09:00", "17:00", "Floor support", 1),
            (4, 1, "10:00", "16:00", "Welcome desk", 2),
            (1, 2, "08:00", "14:00", "Opening", 2),
            (2, 2, "15:00", "21:00", "Dinner service", 2),
            (3, 3, "09:00", "17:00", "Floor support", 1),
            (4, 3, "10:00", "16:00", "Welcome desk", 2),
            (1, 4, "08:00", "14:00", "Opening", 2),
            (2, 4, "15:00", "21:00", "Dinner service", 2),
        ]
        db.executemany(
            """INSERT INTO shifts(schedule_id, department_id, shift_date, start_time, end_time, label, required_staff)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (schedule_id, department, (week_start + timedelta(days=day)).isoformat(), start, end, label, needed)
                for department, day, start, end, label, needed in shift_seed
            ],
        )


def shift_hours(start_time, end_time):
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    return (end - start).total_seconds() / 3600


def employee_is_eligible(db, employee, shift):
    if employee["department_id"] != shift["department_id"]:
        return False
    weekday = date.fromisoformat(shift["shift_date"]).weekday()
    available = db.execute(
        """SELECT 1 FROM availability
           WHERE employee_id = ? AND weekday = ? AND start_time <= ? AND end_time >= ?""",
        (employee["id"], weekday, shift["start_time"], shift["end_time"]),
    ).fetchone()
    if not available:
        return False

    overlapping = db.execute(
        """SELECT 1 FROM assignments a
           JOIN shifts s ON s.id = a.shift_id
           WHERE a.employee_id = ? AND s.shift_date = ?
             AND s.start_time < ? AND s.end_time > ?""",
        (employee["id"], shift["shift_date"], shift["end_time"], shift["start_time"]),
    ).fetchone()
    if overlapping:
        return False

    schedule = db.execute(
        "SELECT start_date, end_date FROM schedules WHERE id = ?", (shift["schedule_id"],)
    ).fetchone()
    total = db.execute(
        """SELECT COALESCE(SUM(
               (CAST(substr(s.end_time, 1, 2) AS INTEGER) * 60 + CAST(substr(s.end_time, 4, 2) AS INTEGER)
                - CAST(substr(s.start_time, 1, 2) AS INTEGER) * 60 - CAST(substr(s.start_time, 4, 2) AS INTEGER)) / 60.0
           ), 0)
           FROM assignments a JOIN shifts s ON s.id = a.shift_id
           WHERE a.employee_id = ? AND s.shift_date BETWEEN ? AND ?""",
        (employee["id"], schedule["start_date"], schedule["end_date"]),
    ).fetchone()[0]
    return total + shift_hours(shift["start_time"], shift["end_time"]) <= employee["max_weekly_hours"]


@app.get("/")
def home():
    return app.send_static_file("index.html")


@app.get("/api/data")
def get_data():
    with connect() as db:
        departments = [dict(row) for row in db.execute("SELECT * FROM departments ORDER BY name")]
        employees = [
            dict(row)
            for row in db.execute(
                """SELECT e.*, d.name AS department, d.color AS department_color
                   FROM employees e JOIN departments d ON d.id = e.department_id
                   ORDER BY e.name"""
            )
        ]
        availability = db.execute(
            """SELECT employee_id, weekday, start_time, end_time
               FROM availability ORDER BY employee_id, weekday"""
        ).fetchall()
        availability_by_employee = {}
        for row in availability:
            availability_by_employee.setdefault(row["employee_id"], []).append(
                   {"weekday": row["weekday"], "start_time": row["start_time"], "end_time": row["end_time"]}
            )
        for employee in employees:
            employee["availability"] = availability_by_employee.get(employee["id"], [])
        schedules = [dict(row) for row in db.execute("SELECT * FROM schedules ORDER BY start_date DESC")]
        shifts = [
            dict(row)
            for row in db.execute(
                """SELECT s.*, d.name AS department, d.color AS department_color,
                          (SELECT COUNT(*) FROM assignments a WHERE a.shift_id = s.id) AS assigned_count,
                          (SELECT group_concat(e.name, ', ') FROM assignments a
                           JOIN employees e ON e.id = a.employee_id WHERE a.shift_id = s.id) AS assigned_names
                   FROM shifts s JOIN departments d ON d.id = s.department_id
                   ORDER BY s.shift_date, s.start_time"""
            )
        ]
    return jsonify(departments=departments, employees=employees, schedules=schedules, shifts=shifts)


@app.post("/api/employees")
def create_employee():
    body = request.get_json()
    try:
        name = body["name"].strip()
        email = body["email"].strip().lower()
        department_id = int(body["department_id"])
        role = body["role"].strip()
        max_hours = int(body.get("max_weekly_hours", 40))
        weekdays = body.get("weekdays", list(range(7)))
        start_time = body.get("availability_start", "07:00")
        end_time = body.get("availability_end", "22:00")
        if not name or not role or "@" not in email or not 1 <= max_hours <= 80:
            raise ValueError("Enter a name, valid email, role, and weekly limit between 1 and 80.")
        if not isinstance(weekdays, list) or not weekdays:
            raise ValueError("Select at least one available day.")
        weekdays = [int(day) for day in weekdays]
        if len(set(weekdays)) != len(weekdays) or any(day < 0 or day > 6 for day in weekdays):
            raise ValueError("Choose valid availability days.")
        if datetime.strptime(start_time, "%H:%M") >= datetime.strptime(end_time, "%H:%M"):
            raise ValueError("Availability must end after it starts.")
        with connect() as db:
            cursor = db.execute(
                """INSERT INTO employees(name, email, department_id, role, max_weekly_hours)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, email, department_id, role, max_hours),
            )
            employee_id = cursor.lastrowid
            db.executemany(
                "INSERT INTO availability(employee_id, weekday, start_time, end_time) VALUES (?, ?, ?, ?)",
                [(employee_id, day, start_time, end_time) for day in weekdays],
            )
    except (KeyError, TypeError, ValueError, sqlite3.IntegrityError) as error:
        return jsonify(error=str(error) or "Could not add employee."), 400
    return jsonify(id=employee_id), 201


@app.post("/api/shifts")
def create_shift():
    body = request.get_json()
    try:
        schedule_id = int(body["schedule_id"])
        department_id = int(body["department_id"])
        shift_date = date.fromisoformat(body["shift_date"])
        start = body["start_time"]
        end = body["end_time"]
        label = body["label"].strip()
        required = int(body.get("required_staff", 1))
        if not label or datetime.strptime(start, "%H:%M") >= datetime.strptime(end, "%H:%M"):
            raise ValueError("Enter a shift name and an end time after the start time.")
        if not 1 <= required <= 20:
            raise ValueError("Staff needed must be between 1 and 20.")
        with connect() as db:
            schedule = db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            if not schedule or not schedule["start_date"] <= shift_date.isoformat() <= schedule["end_date"]:
                raise ValueError("Choose a date inside the selected schedule.")
            shift_id = db.execute(
                """INSERT INTO shifts(schedule_id, department_id, shift_date, start_time, end_time, label, required_staff)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (schedule_id, department_id, shift_date.isoformat(), start, end, label, required),
            ).lastrowid
    except (KeyError, TypeError, ValueError, sqlite3.IntegrityError) as error:
        return jsonify(error=str(error) or "Could not add shift."), 400
    return jsonify(id=shift_id), 201


@app.post("/api/assignments")
def create_assignment():
    body = request.get_json()
    try:
        shift_id = int(body["shift_id"])
        employee_id = int(body["employee_id"])
        with connect() as db:
            shift = db.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
            employee = db.execute("SELECT * FROM employees WHERE id = ? AND active = 1", (employee_id,)).fetchone()
            if not shift or not employee:
                raise ValueError("Choose an active employee and a valid shift.")
            assigned = db.execute("SELECT COUNT(*) FROM assignments WHERE shift_id = ?", (shift_id,)).fetchone()[0]
            if assigned >= shift["required_staff"]:
                raise ValueError("This shift is already fully staffed.")
            if not employee_is_eligible(db, employee, shift):
                raise ValueError("This employee is unavailable, over their weekly limit, or has an overlapping shift.")
            db.execute("INSERT INTO assignments(shift_id, employee_id) VALUES (?, ?)", (shift_id, employee_id))
    except (KeyError, TypeError, ValueError, sqlite3.IntegrityError) as error:
        return jsonify(error=str(error) or "Could not assign employee."), 400
    return jsonify(ok=True), 201


@app.delete("/api/assignments/<int:assignment_id>")
def delete_assignment(assignment_id):
    with connect() as db:
        cursor = db.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
        if not cursor.rowcount:
            return jsonify(error="Assignment not found."), 404
    return jsonify(ok=True)


@app.post("/api/auto-assign")
def auto_assign():
    with connect() as db:
        shifts = db.execute(
            """SELECT s.* FROM shifts s
               ORDER BY s.shift_date, s.start_time, s.required_staff DESC"""
        ).fetchall()
        assigned_now = 0
        for shift in shifts:
            assigned = db.execute(
                "SELECT COUNT(*) FROM assignments WHERE shift_id = ?", (shift["id"],)
            ).fetchone()[0]
            while assigned < shift["required_staff"]:
                candidates = db.execute(
                    """SELECT e.*,
                              (SELECT COALESCE(SUM(
                                  (CAST(substr(s2.end_time, 1, 2) AS INTEGER) * 60 + CAST(substr(s2.end_time, 4, 2) AS INTEGER)
                                   - CAST(substr(s2.start_time, 1, 2) AS INTEGER) * 60 - CAST(substr(s2.start_time, 4, 2) AS INTEGER)) / 60.0
                               ), 0)
                               FROM assignments a2 JOIN shifts s2 ON s2.id = a2.shift_id
                               JOIN schedules sc ON sc.id = s2.schedule_id
                               WHERE a2.employee_id = e.id AND s2.shift_date BETWEEN ? AND ?) AS hours_worked
                       FROM employees e
                       WHERE e.active = 1 AND e.department_id = ?
                         AND NOT EXISTS (SELECT 1 FROM assignments a WHERE a.shift_id = ? AND a.employee_id = e.id)
                       ORDER BY hours_worked, e.id""",
                    (
                        db.execute("SELECT start_date FROM schedules WHERE id = ?", (shift["schedule_id"],)).fetchone()[0],
                        db.execute("SELECT end_date FROM schedules WHERE id = ?", (shift["schedule_id"],)).fetchone()[0],
                        shift["department_id"],
                        shift["id"],
                    ),
                ).fetchall()
                candidate = next((person for person in candidates if employee_is_eligible(db, person, shift)), None)
                if candidate is None:
                    break
                db.execute(
                    "INSERT INTO assignments(shift_id, employee_id) VALUES (?, ?)",
                    (shift["id"], candidate["id"]),
                )
                assigned += 1
                assigned_now += 1
        remaining = db.execute(
            """SELECT COALESCE(SUM(MAX(s.required_staff - COALESCE(assigned.count, 0), 0)), 0)
               FROM shifts s LEFT JOIN (
                   SELECT shift_id, COUNT(*) AS count FROM assignments GROUP BY shift_id
               ) assigned ON assigned.shift_id = s.id"""
        ).fetchone()[0]
    return jsonify(assigned=assigned_now, unfilled=remaining)


if __name__ == "__main__":
    initialize_database()
    app.run(port=5000)
