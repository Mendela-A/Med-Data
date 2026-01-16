#!/usr/bin/env python3
"""
Міграційний скрипт для додавання індексів до існуючої бази даних.
Виконати: python add_indexes.py
"""
import sqlite3
import os
from datetime import datetime

# Підтримка запуску як локально так і в Docker
if os.path.exists('data/app.db'):
    DB_PATH = 'data/app.db'
elif os.path.exists('/app/data/app.db'):
    DB_PATH = '/app/data/app.db'
else:
    DB_PATH = 'app.db'

def create_backup():
    """Створює резервну копію БД перед міграцією"""
    if os.path.exists(DB_PATH):
        db_dir = os.path.dirname(DB_PATH) or '.'
        backup_filename = f'app_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        backup_path = os.path.join(db_dir, 'backups', backup_filename)

        # Створюємо директорію backups якщо не існує
        os.makedirs(os.path.join(db_dir, 'backups'), exist_ok=True)

        import shutil
        shutil.copy2(DB_PATH, backup_path)
        print(f"✓ Створено резервну копію: {backup_path}")
        return backup_path
    return None

def check_index_exists(cursor, index_name):
    """Перевіряє чи існує індекс"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
    return cursor.fetchone() is not None

def add_indexes():
    """Додає індекси до існуючої бази даних"""
    if not os.path.exists(DB_PATH):
        print(f"⚠ База даних {DB_PATH} не знайдена!")
        return

    # Створюємо резервну копію
    backup_path = create_backup()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Список індексів для створення
    indexes = [
        # Індекси для таблиці records
        ("idx_record_discharge_status", "CREATE INDEX IF NOT EXISTS idx_record_discharge_status ON records(discharge_status)"),
        ("idx_record_treating_physician", "CREATE INDEX IF NOT EXISTS idx_record_treating_physician ON records(treating_physician)"),
        ("idx_record_discharge_department", "CREATE INDEX IF NOT EXISTS idx_record_discharge_department ON records(discharge_department)"),
        ("idx_record_date_of_discharge", "CREATE INDEX IF NOT EXISTS idx_record_date_of_discharge ON records(date_of_discharge)"),
        ("idx_record_full_name", "CREATE INDEX IF NOT EXISTS idx_record_full_name ON records(full_name)"),
        ("idx_record_updated_at", "CREATE INDEX IF NOT EXISTS idx_record_updated_at ON records(updated_at)"),

        # Індекс для таблиці users (якщо не існує через unique=True)
        ("idx_users_username", "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"),

        # Індекс для таблиці departments (якщо не існує через unique=True)
        ("idx_departments_name", "CREATE INDEX IF NOT EXISTS idx_departments_name ON departments(name)"),
    ]

    print("\n🔧 Додавання індексів до бази даних...")
    print("=" * 60)

    created_count = 0
    skipped_count = 0

    for index_name, create_sql in indexes:
        if check_index_exists(cursor, index_name):
            print(f"⊘ {index_name:<40} (вже існує)")
            skipped_count += 1
        else:
            try:
                cursor.execute(create_sql)
                print(f"✓ {index_name:<40} створено")
                created_count += 1
            except sqlite3.Error as e:
                print(f"✗ {index_name:<40} помилка: {e}")

    # Оптимізація БД після створення індексів
    print("\n🔧 Оптимізація бази даних...")
    cursor.execute("ANALYZE")
    cursor.execute("VACUUM")

    conn.commit()
    conn.close()

    print("=" * 60)
    print(f"\n📊 Результати:")
    print(f"   • Створено індексів: {created_count}")
    print(f"   • Пропущено (існують): {skipped_count}")
    print(f"   • Резервна копія: {backup_path if backup_path else 'не потрібна'}")
    print("\n✅ Міграція завершена успішно!")

    # Показуємо статистику
    print("\n📈 Статистика індексів:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, tbl_name
        FROM sqlite_master
        WHERE type='index'
        AND name LIKE 'idx_%'
        ORDER BY tbl_name, name
    """)
    for idx_name, tbl_name in cursor.fetchall():
        print(f"   • {tbl_name}.{idx_name}")
    conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("   ДОДАВАННЯ ІНДЕКСІВ ДЛЯ ОПТИМІЗАЦІЇ ПРОДУКТИВНОСТІ")
    print("=" * 60)
    add_indexes()
