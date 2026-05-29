import sys
import os
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get table schema
cursor.execute("PRAGMA table_info(daily_reports)")
columns = cursor.fetchall()
print("Columns in daily_reports:")
for col in columns:
    print(f"Index: {col[0]}, Name: {col[1]}, Type: {col[2]}")

conn.close()
