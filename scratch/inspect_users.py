import sys
import os
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

db_path = os.path.join("data", "app.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all users
cursor.execute("SELECT id, username, role FROM users")
users = cursor.fetchall()
print("Users in DB:")
for u in users:
    print(f"ID: {u[0]}, Username: '{u[1]}', Role: '{u[2]}'")

conn.close()
