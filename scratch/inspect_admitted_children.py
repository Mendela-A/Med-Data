import sys
import sqlite3
import os

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get non-zero admitted_children
cursor.execute("""
    SELECT r.report_date, d.name, d.row_no, r.admitted_children, r.admitted_children_rural
    FROM daily_reports r
    JOIN departments d ON r.department_id = d.id
    WHERE r.report_date >= '2026-04-01' AND r.report_date <= '2026-04-30'
      AND (r.admitted_children > 0 OR r.admitted_children_rural > 0)
    ORDER BY r.report_date
""")
rows = cursor.fetchall()
print(f"Total rows with kids data: {len(rows)}")
for r in rows:
    print(f"Date: {r[0]} | Dept: '{r[1]}' | RowNo: {r[2]} | AdmittedKids: {r[3]} | RuralKids: {r[4]}")

conn.close()
