"""
merge_production_with_form007.py

Зливає виробничу БД (реальні записи/користувачі/амбулаторка)
з проєктною БД (Форми 007/016: daily_reports, print_settings, departments).

Алгоритм:
1. Копіює виробничу БД → app_merged.db
2. Застосовує pending Alembic-міграції (daily_reports, print_settings, extra_permissions)
3. Копіює Form 007 дані з проєктної БД:
   - daily_reports (3339 рядків)
   - print_settings (1 рядок налаштувань друку)
   - departments: оновлює row_no/bed_capacity/bed_profile_name + додає нові відділення
4. Перевіряє цілісність результату

Використання:
  python scripts/merge_production_with_form007.py

Результат: data/app_merged.db — готова до заміни app.db
"""
import os
import sys
import shutil
import sqlite3
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

PROD_DB    = os.path.join(DATA_DIR, 'app_2026-06-04_03-00.db')
PROJECT_DB = os.path.join(DATA_DIR, 'app.db')
MERGED_DB  = os.path.join(DATA_DIR, 'app_merged.db')
BACKUP_DB  = os.path.join(DATA_DIR, f'app_before_merge_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')


def log(msg):
    print(f'  {msg}')


def check(cond, msg):
    if not cond:
        print(f'ПОМИЛКА: {msg}')
        sys.exit(1)


def row_count(con, table):
    try:
        return con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
    except Exception:
        return None


def main():
    print('=== Merge: виробнича БД + Form 007 ===\n')

    # --- Перевірка вхідних файлів ---
    check(os.path.exists(PROD_DB),    f'Виробнича БД не знайдена: {PROD_DB}')
    check(os.path.exists(PROJECT_DB), f'Проєктна БД не знайдена: {PROJECT_DB}')

    # --- Крок 1: Копіюємо виробничу БД ---
    print('Крок 1: Копіюємо виробничу БД...')
    shutil.copy2(PROD_DB, MERGED_DB)
    log(f'Скопійовано: {PROD_DB} → {MERGED_DB}')

    # Перевіримо вміст виробничої
    con_prod = sqlite3.connect(MERGED_DB)
    log(f'records: {row_count(con_prod, "records")}')
    log(f'ambulatory_records: {row_count(con_prod, "ambulatory_records")}')
    log(f'users: {row_count(con_prod, "users")}')
    log(f'alembic: {con_prod.execute("SELECT version_num FROM alembic_version").fetchone()[0]}')
    con_prod.close()

    # --- Крок 2: Alembic upgrade ---
    print('\nКрок 2: Застосовуємо pending міграції...')
    env = os.environ.copy()
    env['DATABASE_URL'] = f'sqlite:///{MERGED_DB}'
    env['FLASK_APP'] = 'app.py'

    result = subprocess.run(
        [sys.executable, '-m', 'flask', 'db', 'upgrade'],
        cwd=BASE_DIR, env=env,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print('STDERR:', result.stderr[-2000:])
        check(False, 'flask db upgrade завершився з помилкою')

    # Перевіримо head
    result2 = subprocess.run(
        [sys.executable, '-m', 'flask', 'db', 'current'],
        cwd=BASE_DIR, env=env,
        capture_output=True, text=True
    )
    current = result2.stdout.strip()
    log(f'alembic після upgrade: {current}')
    check('head' in current, f'Не досягнуто head: {current}')

    # Перевіримо що таблиці Form 007 з'явились
    con_m = sqlite3.connect(MERGED_DB)
    tables = {r[0] for r in con_m.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    check('daily_reports' in tables,   'Після upgrade немає таблиці daily_reports')
    check('print_settings' in tables,  'Після upgrade немає таблиці print_settings')
    log('Таблиці daily_reports і print_settings створено ✓')

    # --- Крок 3: Копіюємо Form 007 дані ---
    print('\nКрок 3: Копіюємо Form 007 дані з проєктної БД...')
    con_proj = sqlite3.connect(PROJECT_DB)

    # 3a. daily_reports
    log('daily_reports...')
    existing_dr = row_count(con_m, 'daily_reports')
    log(f'  Поточно в merged: {existing_dr}')
    rows = con_proj.execute(
        'SELECT report_date, department_id, beds_total, beds_renovation, '
        'patients_start, admitted_total, admitted_rural, admitted_children, '
        'admitted_children_rural, transferred_in, transferred_out, '
        'discharged_total, discharged_to_other, deaths, patients_end, '
        'patients_end_rural, mothers_with_children, free_male, free_female, '
        'created_by, updated_by, created_at, updated_at FROM daily_reports'
    ).fetchall()

    if rows:
        # Видаляємо old daily_reports (порожній), вставляємо з проєктної
        con_m.execute('DELETE FROM daily_reports')
        con_m.executemany(
            'INSERT INTO daily_reports (report_date, department_id, beds_total, beds_renovation, '
            'patients_start, admitted_total, admitted_rural, admitted_children, '
            'admitted_children_rural, transferred_in, transferred_out, '
            'discharged_total, discharged_to_other, deaths, patients_end, '
            'patients_end_rural, mothers_with_children, free_male, free_female, '
            'created_by, updated_by, created_at, updated_at) VALUES '
            '(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            rows
        )
        con_m.commit()
        log(f'  Вставлено: {len(rows)} рядків ✓')
    else:
        log('  Проєктна БД не має daily_reports — пропускаємо')

    # 3b. print_settings
    log('print_settings...')
    ps_row = con_proj.execute('SELECT * FROM print_settings WHERE id=1').fetchone()
    if ps_row:
        cols = [d[0] for d in con_proj.execute('SELECT * FROM print_settings WHERE id=1').description]
        # Видаляємо дефолтний рядок (якщо є) і вставляємо з проєктної
        con_m.execute('DELETE FROM print_settings')
        placeholders = ','.join('?' * len(ps_row))
        col_names = ','.join(cols)
        con_m.execute(f'INSERT INTO print_settings ({col_names}) VALUES ({placeholders})', ps_row)
        con_m.commit()
        log('  print_settings скопійовано ✓')
    else:
        log('  Немає print_settings у проєктній БД — пропускаємо')

    # 3c. departments: оновлюємо row_no/bed_capacity/bed_profile_name + додаємо нові
    log('departments...')
    prod_depts = {r[1]: r for r in con_m.execute(
        'SELECT id, name, bed_profile_name, bed_capacity, row_no FROM departments'
    ).fetchall()}  # key = name
    proj_depts = {r[1]: r for r in con_proj.execute(
        'SELECT id, name, bed_profile_name, bed_capacity, row_no FROM departments'
    ).fetchall()}

    updated = 0
    added = 0
    for name, proj_row in proj_depts.items():
        proj_id, proj_name, proj_profile, proj_beds, proj_rowno = proj_row
        if name in prod_depts:
            # Оновлюємо колонки Form 007 для існуючих відділень
            prod_id = prod_depts[name][0]
            con_m.execute(
                'UPDATE departments SET bed_profile_name=?, bed_capacity=?, row_no=? WHERE id=?',
                (proj_profile, proj_beds, proj_rowno, prod_id)
            )
            updated += 1
        else:
            # Нове відділення (Кардіохірургічне, дитячі) — додаємо
            con_m.execute(
                'INSERT INTO departments (name, bed_profile_name, bed_capacity, row_no) VALUES (?,?,?,?)',
                (name, proj_profile, proj_beds, proj_rowno)
            )
            added += 1
            log(f'    Додано нове відділення: {name}')

    con_m.commit()
    log(f'  Оновлено: {updated}, додано нових: {added} ✓')

    con_proj.close()

    # --- Крок 4: Фінальна перевірка ---
    print('\nКрок 4: Перевірка результату...')
    log(f'records:             {row_count(con_m, "records")}')
    log(f'ambulatory_records:  {row_count(con_m, "ambulatory_records")}')
    log(f'users:               {row_count(con_m, "users")}')
    log(f'nszu_corrections:    {row_count(con_m, "nszu_corrections")}')
    log(f'daily_reports:       {row_count(con_m, "daily_reports")}')
    log(f'print_settings:      {row_count(con_m, "print_settings")}')
    log(f'departments:         {row_count(con_m, "departments")}')
    alembic_ver = con_m.execute('SELECT version_num FROM alembic_version').fetchone()[0]
    log(f'alembic:             {alembic_ver}')
    con_m.close()

    print(f'\n✅ Готово! Результат: {MERGED_DB}')
    print('\nЩоб застосувати:')
    print(f'  1. Зупиніть контейнери:    docker compose stop web tg-bot')
    print(f'  2. Замініть БД:             copy data\\app_merged.db data\\app.db')
    print(f'  3. Запустіть:               docker compose up -d web tg-bot')
    print(f'  4. Перевірте:               docker compose exec -T web flask db current')


if __name__ == '__main__':
    main()
