import sys
import sqlite3
import os

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Imported Daily Reports for children's departments in April 2026:")
for dept_id, name in [(20, 'Хірургічне дит.'), (22, 'Травматологічне дит.'), (21, 'Урологічне дит.')]:
    cursor.execute("""
        SELECT report_date, beds_total, patients_start, admitted_total, patients_end
        FROM daily_reports
        WHERE department_id = ? AND report_date >= '2026-04-01' AND report_date <= '2026-04-30'
        ORDER BY report_date
    """, (dept_id,))
    rows = cursor.fetchall()
    print(f"\nDepartment: {name} (ID: {dept_id}):")
    for r in rows:
        if r[1] or r[2] or r[3] or r[4]: # if there's any data
            print(f"  Date: {r[0]} | BedsTotal: {r[1]} | Start: {r[2]} | Admitted: {r[3]} | End: {r[4]}")

conn.close()
