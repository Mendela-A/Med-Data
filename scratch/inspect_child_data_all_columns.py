import sys
import sqlite3
import os

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all columns
cursor.execute("PRAGMA table_info(daily_reports)")
cols = [c[1] for c in cursor.fetchall()]

for dept_id, name in [(20, 'Хірургічне дит.'), (22, 'Травматологічне дит.'), (21, 'Урологічне дит.')]:
    cursor.execute(f"SELECT {', '.join(cols)} FROM daily_reports WHERE department_id = ? AND report_date >= '2026-04-01' AND report_date <= '2026-04-30' ORDER BY report_date", (dept_id,))
    rows = cursor.fetchall()
    print(f"\nDepartment: {name} (ID: {dept_id}):")
    # print headers
    print(cols)
    for r in rows:
        # print if there is any data (excluding id, date, dept_id, created_by, created_at, updated_at)
        data_part = r[3:19]
        if any(x is not None and x != 0 for x in data_part):
            print(r)

conn.close()
