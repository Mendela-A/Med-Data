import sqlite3
import os

db_path = 'data/app.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print("Table row counts:")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f" - {table}: {cursor.fetchone()[0]}")
        except Exception as e:
            print(f" - {table}: Error: {e}")
    conn.close()
