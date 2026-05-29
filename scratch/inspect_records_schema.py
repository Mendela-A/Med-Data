import sys
import sqlite3
import os

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(records)")
columns = cursor.fetchall()
print("Columns in records:")
for col in columns:
    print(f"Index: {col[0]}, Name: {col[1]}, Type: {col[2]}")

conn.close()
