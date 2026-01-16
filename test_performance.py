#!/usr/bin/env python3
"""
Скрипт для тестування продуктивності різних підходів до підрахунку статусів.
"""
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from models import db, Record
from sqlalchemy import func

def test_python_counting():
    """Старий підхід - підрахунок в Python після завантаження всіх записів"""
    app = create_app()
    with app.app_context():
        start_time = time.time()

        # Завантажуємо всі записи
        records = Record.query.all()

        # Підраховуємо в Python
        count_discharged = sum(1 for r in records if r.discharge_status == 'Виписаний')
        count_processing = sum(1 for r in records if r.discharge_status == 'Опрацьовується')
        count_violations = sum(1 for r in records if r.discharge_status == 'Порушені вимоги')

        elapsed = time.time() - start_time

        return {
            'method': 'Python counting',
            'time': elapsed,
            'count_discharged': count_discharged,
            'count_processing': count_processing,
            'count_violations': count_violations,
            'total_records': len(records)
        }

def test_sql_counting():
    """Новий підхід - підрахунок на рівні БД через func.count()"""
    app = create_app()
    with app.app_context():
        start_time = time.time()

        # Виконуємо один агрегований запит
        status_counts = db.session.query(
            Record.discharge_status,
            func.count(Record.id).label('count')
        ).group_by(Record.discharge_status).all()

        # Перетворюємо в словник
        status_count_dict = {status: cnt for status, cnt in status_counts if status}
        count_discharged = status_count_dict.get('Виписаний', 0)
        count_processing = status_count_dict.get('Опрацьовується', 0)
        count_violations = status_count_dict.get('Порушені вимоги', 0)

        elapsed = time.time() - start_time

        return {
            'method': 'SQL func.count()',
            'time': elapsed,
            'count_discharged': count_discharged,
            'count_processing': count_processing,
            'count_violations': count_violations,
            'total_records': sum(status_count_dict.values())
        }

def run_benchmark(iterations=10):
    """Запускає бенчмарк обох методів"""
    print("=" * 70)
    print("  БЕНЧМАРК: Підрахунок статусів записів")
    print("=" * 70)
    print(f"\nВиконується {iterations} ітерацій кожного методу...\n")

    python_times = []
    sql_times = []

    # Прогрів
    print("Прогрів (1 ітерація кожного методу)...")
    test_python_counting()
    test_sql_counting()

    print("\nВиконання бенчмарку...")

    # Python counting
    for i in range(iterations):
        result = test_python_counting()
        python_times.append(result['time'])
        if i == 0:
            python_result = result

    # SQL counting
    for i in range(iterations):
        result = test_sql_counting()
        sql_times.append(result['time'])
        if i == 0:
            sql_result = result

    # Результати
    python_avg = sum(python_times) / len(python_times)
    sql_avg = sum(sql_times) / len(sql_times)
    speedup = python_avg / sql_avg if sql_avg > 0 else 0

    print("\n" + "=" * 70)
    print("  РЕЗУЛЬТАТИ")
    print("=" * 70)

    print(f"\n📊 Дані:")
    print(f"   • Всього записів: {python_result['total_records']}")
    print(f"   • Виписаний: {python_result['count_discharged']}")
    print(f"   • Опрацьовується: {python_result['count_processing']}")
    print(f"   • Порушені вимоги: {python_result['count_violations']}")

    print(f"\n⏱️  Середній час виконання ({iterations} ітерацій):")
    print(f"   • Python counting:    {python_avg*1000:.2f} ms")
    print(f"   • SQL func.count():   {sql_avg*1000:.2f} ms")

    print(f"\n🚀 Прискорення:")
    print(f"   • SQL швидше в {speedup:.1f}x разів!")
    print(f"   • Економія часу: {(python_avg - sql_avg)*1000:.2f} ms на запит")

    improvement_pct = ((python_avg - sql_avg) / python_avg) * 100
    print(f"   • Покращення: {improvement_pct:.1f}%")

    print("\n" + "=" * 70)

    # Перевірка коректності
    if (python_result['count_discharged'] == sql_result['count_discharged'] and
        python_result['count_processing'] == sql_result['count_processing'] and
        python_result['count_violations'] == sql_result['count_violations']):
        print("✅ Результати обох методів збігаються!")
    else:
        print("⚠️  УВАГА: Результати методів відрізняються!")
        print(f"   Python: {python_result['count_discharged']}, {python_result['count_processing']}, {python_result['count_violations']}")
        print(f"   SQL:    {sql_result['count_discharged']}, {sql_result['count_processing']}, {sql_result['count_violations']}")

    print("=" * 70)

if __name__ == '__main__':
    try:
        run_benchmark(iterations=10)
    except Exception as e:
        print(f"\n❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
