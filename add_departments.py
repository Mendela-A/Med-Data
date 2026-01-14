import sqlite3
from datetime import datetime

# Список відділень
DEPARTMENTS = [
    "Гінекологічне",
    "Реанімаційне",
    "Кардіологічне",
    "Хірургічне",
    "Терапевтичне",
    "Травматологічне",
    "Отоларингологічне",
    "Педіатричне",
    "Паліативне",
    "Гастроентерологічне",
    "Ендокринологічне",
    "Урологічне",
    "Реабілітаційне",
    "Нейрохірургічне",
    "Неврологічне",
    "Нефрологічне",
    "НЕМД"
]

# Конфігурація
DB_FILE = 'data\\app.db'  # Замініть на шлях до вашої бази даних

def add_departments_to_db(db_file, departments):
    """Додає відділення до бази даних"""
    
    print("="*60)
    print("ДОДАВАННЯ ВІДДІЛЕНЬ ДО БАЗИ ДАНИХ")
    print("="*60)
    
    # Підключення до БД
    print(f"\n📊 Підключення до бази даних {db_file}...")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Лічильники
    added_count = 0
    exists_count = 0
    error_count = 0
    errors = []
    
    print(f"\n📝 Відділень для додавання: {len(departments)}")
    print()
    
    # Додавання кожного відділення
    for dept_name in departments:
        try:
            cursor.execute('''
                INSERT INTO departments (name, created_at)
                VALUES (?, ?)
            ''', (dept_name, datetime.now()))
            
            added_count += 1
            print(f"  ✅ Додано: {dept_name}")
            
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                exists_count += 1
                print(f"  ℹ️  Вже існує: {dept_name}")
            else:
                error_count += 1
                error_msg = f"Помилка при додаванні '{dept_name}': {str(e)}"
                errors.append(error_msg)
                print(f"  ❌ {error_msg}")
                
        except Exception as e:
            error_count += 1
            error_msg = f"Помилка при додаванні '{dept_name}': {str(e)}"
            errors.append(error_msg)
            print(f"  ❌ {error_msg}")
    
    # Збереження змін
    conn.commit()
    
    # Перевірка результатів
    cursor.execute("SELECT COUNT(*) FROM departments")
    total_in_db = cursor.fetchone()[0]
    
    conn.close()
    
    # Звіт про результати
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТИ")
    print("="*60)
    print(f"✅ Нових відділень додано: {added_count}")
    print(f"ℹ️  Вже існувало: {exists_count}")
    print(f"❌ Помилки: {error_count}")
    print(f"📊 Всього відділень в БД: {total_in_db}")
    
    if errors:
        print("\nДеталі помилок:")
        for error in errors:
            print(f"  • {error}")
    
    print("="*60)
    
    return added_count, exists_count, error_count

def view_departments(db_file):
    """Показує всі відділення з бази даних"""
    
    print("\n" + "="*60)
    print("СПИСОК ВІДДІЛЕНЬ В БАЗІ ДАНИХ")
    print("="*60)
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, created_at 
        FROM departments 
        ORDER BY name
    ''')
    
    departments = cursor.fetchall()
    conn.close()
    
    if not departments:
        print("\n⚠️  База даних не містить жодного відділення")
        return
    
    print(f"\n📊 Всього відділень: {len(departments)}\n")
    
    for dept_id, name, created_at in departments:
        print(f"  {dept_id:3d}. {name}")
    
    print("\n" + "="*60)

if __name__ == '__main__':
    import sys
    
    # Перевірка аргументів командного рядка
    if len(sys.argv) > 1:
        if sys.argv[1] == '--view':
            # Показати існуючі відділення
            db_path = sys.argv[2] if len(sys.argv) > 2 else DB_FILE
            try:
                view_departments(db_path)
            except Exception as e:
                print(f"❌ ПОМИЛКА: {str(e)}")
            sys.exit(0)
        elif sys.argv[1] == '--help':
            print("Використання:")
            print("  python add_departments.py              # Додати відділення")
            print("  python add_departments.py --view       # Показати існуючі")
            print("  python add_departments.py --view db.db # Показати з конкретної БД")
            sys.exit(0)
        else:
            DB_FILE = sys.argv[1]
    
    # Додавання відділень
    try:
        add_departments_to_db(DB_FILE, DEPARTMENTS)
        
        # Показати результат
        view_departments(DB_FILE)
        
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"\n❌ ПОМИЛКА: Таблиця 'departments' не знайдена в базі даних!")
            print("Переконайтеся, що база даних містить таблицю 'departments'")
        else:
            print(f"\n❌ ПОМИЛКА БД: {str(e)}")
    except FileNotFoundError:
        print(f"\n❌ ПОМИЛКА: Файл бази даних '{DB_FILE}' не знайдено!")
    except Exception as e:
        print(f"\n❌ КРИТИЧНА ПОМИЛКА: {str(e)}")