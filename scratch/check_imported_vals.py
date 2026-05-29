import sys
import sqlite3
import os

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get reports for April 1st
cursor.execute("""
    SELECT d.id, d.name, d.row_no, r.beds_total, r.patients_start, r.admitted_total, r.patients_end
    FROM daily_reports r
    JOIN departments d ON r.department_id = d.id
    WHERE r.report_date = '2026-04-01'
    ORDER BY d.row_no
""")
rows = cursor.fetchall()
print("Reports for 01.04.2026:")
for r in rows:
    print(f"Dept ID: {r[0]} | Name: '{r[1]}' | RowNo: {r[2]} | BedsTotal: {r[3]} | Start: {r[4]} | Admitted: {r[5]} | End: {r[6]}")

conn.close()
