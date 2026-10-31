# Shiftwise

A small workforce shift planner built for a DBMS expo project. The Python server uses Flask and SQLite; the browser UI supports employee and shift creation, staffing coverage, manual assignment, and an availability-aware auto-assigner.

## Run locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The SQLite database (`workforce.db`) and sample demo workspace are created automatically on first run.

## Database design

- `departments` groups employees and shifts.
- `employees` stores role, department, and a weekly-hours limit.
- `availability` stores each employee's available weekday/time window.
- `schedules` represents a date-bounded planning period.
- `shifts` defines department, date, time, staffing requirement, and schedule.
- `assignments` links employees to shifts.

The schema is documented in [`schema.sql`](./schema.sql) and applied automatically at startup.

The auto-assign endpoint fills open positions by department while checking availability, overlapping shifts, and weekly hour limits. It balances choices by assigning employees with fewer scheduled hours first.
