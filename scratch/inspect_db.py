import sqlite3
import os

files = ['data/app.db', 'data/app_2026-05-12_03-00.db', 'data/app_corrupted_backup.db', 'data/test_migrate.db']

for f in files:
    print(f"\n=========================================")
    print(f"Inspecting file: {f}")
    if not os.path.exists(f):
        print("File does not exist!")
        continue
    
    print(f"Size: {os.path.getsize(f)} bytes")
    
    try:
        conn = sqlite3.connect(f)
        cursor = conn.cursor()
        
        # Check integrity
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        print(f"Integrity check: {integrity}")
        
        # Get tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"Tables ({len(tables)}): {', '.join(tables)}")
        
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f" - {table}: {cursor.fetchone()[0]} rows")
            
        conn.close()
    except Exception as e:
        print(f"Error inspecting file: {e}")
