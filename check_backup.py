import sqlite3
import os

db_path = 'data/app_2026-05-12_03-00.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print("Backup table row counts:")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f" - {table}: {cursor.fetchone()[0]}")
        except Exception as e:
            print(f" - {table}: Error: {e}")
    
    # Let's print users in backup!
    try:
        cursor.execute("SELECT id, username, role FROM users")
        print("Users in backup:")
        for r in cursor.fetchall():
            print(f" - {r}")
    except Exception as e:
        print(f"Error checking users: {e}")
        
    conn.close()
else:
    print("Backup file does not exist!")
