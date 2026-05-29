import sys
import sqlite3
import os

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check reports count for kids depts (IDs 20, 21, 22)
cursor.execute("SELECT department_id, count(*) FROM daily_reports WHERE report_date >= '2026-04-01' AND report_date <= '2026-04-30' GROUP BY department_id")
results = cursor.fetchall()
print("Daily reports count by department ID in April 2026:")
for r in results:
    cursor.execute("SELECT name, row_no FROM departments WHERE id = ?", (r[0],))
    dept_info = cursor.fetchone()
    print(f"  Dept ID: {r[0]} ({dept_info[0]}, row_no: {dept_info[1]}): {r[1]} reports")

conn.close()
