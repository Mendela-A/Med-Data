import sys
import os
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all departments
cursor.execute("SELECT id, name, bed_profile_name, bed_capacity, row_no FROM departments ORDER BY row_no")
depts = cursor.fetchall()
print(f"Total departments in DB: {len(depts)}")
for d in depts:
    print(f"ID: {d[0]}, Name: '{d[1]}', Profile: '{d[2]}', BedCapacity: {d[3]}, RowNo: {d[4]}")

conn.close()
