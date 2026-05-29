import sys
import os
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get one report
cursor.execute("SELECT id, report_date, department_id, beds_total FROM daily_reports LIMIT 5")
reports = cursor.fetchall()
print("Sample reports in DB:")
for r in reports:
    print(f"ID: {r[0]}, Date: '{r[1]}' (type: {type(r[1])}), DeptID: {r[2]}, BedsTotal: {r[3]}")

# Count total daily reports in April 2026
cursor.execute("SELECT count(*) FROM daily_reports WHERE report_date >= '2026-04-01' AND report_date <= '2026-04-30'")
count_april = cursor.fetchone()[0]
print(f"Total reports in April 2026 before import: {count_april}")

conn.close()
