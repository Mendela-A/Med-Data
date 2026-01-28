#!/usr/bin/env python3
"""
Скрипт для оптимізації та обслуговування бази даних SQLite.
Виконати: python optimize_database.py
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

def get_db_stats(cursor):
    """Отримати статистику бази даних"""
    # Розмір БД
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    db_size = cursor.fetchone()[0]

    # Кількість таблиць
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    tables_count = cursor.fetchone()[0]

    # Кількість індексів
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
    indexes_count = cursor.fetchone()[0]

    return {
        'size': db_size,
        'size_mb': round(db_size / 1024 / 1024, 2),
        'tables': tables_count,
        'indexes': indexes_count
    }

def optimize_database():
    """Оптимізація бази даних"""
    if not os.path.exists(DB_PATH):
        print(f"⚠️  База даних {DB_PATH} не знайдена!")
        return

    print("=" * 70)
    print("   ОПТИМІЗАЦІЯ БАЗИ ДАНИХ SQLite")
    print("=" * 70)
    print(f"\nБаза даних: {DB_PATH}")
    print(f"Час: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Статистика ДО оптимізації
    print("📊 Статистика ДО оптимізації:")
    stats_before = get_db_stats(cursor)
    print(f"   • Розмір БД: {stats_before['size_mb']} MB")
    print(f"   • Таблиць: {stats_before['tables']}")
    print(f"   • Індексів: {stats_before['indexes']}")

    print("\n🔧 Виконання оптимізації...\n")

    # 1. ANALYZE - оновлення статистики для планувальника запитів
    print("   1️⃣  ANALYZE - оновлення статистики запитів...")
    start = datetime.now()
    cursor.execute("ANALYZE")
    elapsed = (datetime.now() - start).total_seconds()
    print(f"      ✓ Завершено за {elapsed:.3f}s")

    # 2. VACUUM - дефрагментація та стиснення БД
    print("   2️⃣  VACUUM - дефрагментація БД...")
    start = datetime.now()
    cursor.execute("VACUUM")
    elapsed = (datetime.now() - start).total_seconds()
    print(f"      ✓ Завершено за {elapsed:.3f}s")

    # 3. PRAGMA optimize - автоматична оптимізація
    print("   3️⃣  PRAGMA optimize - автоматична оптимізація...")
    start = datetime.now()
    cursor.execute("PRAGMA optimize")
    elapsed = (datetime.now() - start).total_seconds()
    print(f"      ✓ Завершено за {elapsed:.3f}s")

    # 4. PRAGMA incremental_vacuum - поступове звільнення місця
    print("   4️⃣  PRAGMA incremental_vacuum - очищення...")
    start = datetime.now()
    cursor.execute("PRAGMA incremental_vacuum(100)")  # Звільнити до 100 сторінок
    elapsed = (datetime.now() - start).total_seconds()
    print(f"      ✓ Завершено за {elapsed:.3f}s")

    # 5. PRAGMA wal_checkpoint - збереження WAL журналу
    print("   5️⃣  PRAGMA wal_checkpoint - збереження WAL...")
    start = datetime.now()
    cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    result = cursor.fetchone()
    elapsed = (datetime.now() - start).total_seconds()
    print(f"      ✓ Завершено за {elapsed:.3f}s (busy: {result[0]}, log: {result[1]}, checkpointed: {result[2]})")

    conn.commit()

    # Статистика ПІСЛЯ оптимізації
    print("\n📊 Статистика ПІСЛЯ оптимізації:")
    stats_after = get_db_stats(cursor)
    print(f"   • Розмір БД: {stats_after['size_mb']} MB")
    print(f"   • Таблиць: {stats_after['tables']}")
    print(f"   • Індексів: {stats_after['indexes']}")

    # Різниця
    size_diff = stats_before['size_mb'] - stats_after['size_mb']
    if size_diff > 0:
        print(f"\n💾 Звільнено місця: {size_diff:.2f} MB ({size_diff/stats_before['size_mb']*100:.1f}%)")
    elif size_diff < 0:
        print(f"\n📈 Розмір збільшився: {abs(size_diff):.2f} MB (нормально після ANALYZE)")
    else:
        print(f"\n✓ Розмір без змін")

    # Перевірка PRAGMA налаштувань
    print("\n🔍 Поточні PRAGMA налаштування:")
    pragmas = [
        'journal_mode',
        'synchronous',
        'cache_size',
        'temp_store',
        'page_size',
        'auto_vacuum',
        'wal_autocheckpoint'
    ]

    for pragma in pragmas:
        try:
            cursor.execute(f"PRAGMA {pragma}")
            value = cursor.fetchone()[0]
            print(f"   • {pragma}: {value}")
        except Exception as e:
            print(f"   • {pragma}: помилка - {e}")

    conn.close()

    print("\n" + "=" * 70)
    print("✅ Оптимізація завершена успішно!")
    print("=" * 70)

    # Рекомендації
    print("\n💡 Рекомендації:")
    print("   • Запускайте цей скрипт раз на тиждень для підтримки продуктивності")
    print("   • ANALYZE виконується автоматично на 1% запитів")
    print("   • VACUUM може зайняти багато часу на великих БД")
    print("   • Для production краще робити VACUUM в не піковий час")

if __name__ == '__main__':
    try:
        optimize_database()
    except Exception as e:
        print(f"\n❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
