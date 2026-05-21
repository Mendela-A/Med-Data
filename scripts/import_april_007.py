"""
Import Форма 007 — April 2026 from data/007/04_data.xlsx.
Each sheet ('01'–'30') = one day. Data rows 12–32 + 34 (Пологовий будинок).
"""
import sys
sys.path.insert(0, '/app')
from datetime import date
import openpyxl
from app import create_app
from app.extensions import db
from models import Department, DailyReport

# xlsx department name → DB department name (None = intentionally skipped)
NAME_MAP = {
    'Неврологічні':         'Неврологічне',
    'Кардіологічні':        'Кардіологічне',
    'Хірургічні':           'Хірургічне',
    'Отоларингологічні':    'Отоларингологічне',
    'Офтальмологічні':      'Офтальмологічне',
    'Урологічні':           'Урологічне',
    'Пульмонологічні':      'Пульмонологічне',
    'Терапія':              'Терапевтичне',
    'Терапевтичне':         'Терапевтичне',
    'Травматологічні':      'Травматологічне',
    'Нейрохірургічні':      'Нейрохірургічне',
    'Гастроентерологіч':    'Гастроентерологічне',
    'Ендокринологічні':     'Ендокринологічне',
    'Реанімаційні':         'Реанімаційне',
    'Нефрологічні':         'Нефрологічне',
    'Реабілітаційні':       'Реабілітаційне',
    'Паліативні':           'Паліативне',
    'Педіатричні':          'Педіатричне',
    'Невідкладна допомога': 'НЕМД',
    'Пологовий будинок':    'Гінекологічне',
    # дитячі підрозділи без відповідника в DB
    'Хірургічні дитячі':    None,
    'Урологічні діти':      None,
    'Травматологіч діти':   None,
    # підсумкові рядки
    'КНП "Калуська ЦРЛ"':  None,
    'ВСЬОГО по КНП':        None,
}

XLSX_PATH = '/app/data/007/04_data.xlsx'
YEAR, MONTH = 2026, 4

app = create_app()
with app.app_context():
    dept_by_name = {d.name: d for d in Department.query.all()}

    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)

    # Update row_no from sheet '01' (consistent across all sheets)
    ws0 = wb['01']
    row_no_updated = 0
    for row in ws0.iter_rows(min_row=12, max_row=34, values_only=True):
        xlsx_name = str(row[0]).strip() if row[0] else None
        if not xlsx_name:
            continue
        db_name = NAME_MAP.get(xlsx_name)
        if db_name and row[1] is not None:
            dept = dept_by_name.get(db_name)
            if dept and dept.row_no != row[1]:
                dept.row_no = int(row[1])
                row_no_updated += 1
    db.session.flush()
    print(f"row_no оновлено: {row_no_updated}")

    created = updated = 0
    unknown = set()

    for sheet_name in wb.sheetnames:
        try:
            day = int(sheet_name)
        except ValueError:
            continue
        report_date = date(YEAR, MONTH, day)
        ws = wb[sheet_name]

        for row in ws.iter_rows(min_row=12, max_row=34, values_only=True):
            xlsx_name = str(row[0]).strip() if row[0] else None
            if not xlsx_name:
                continue

            if xlsx_name not in NAME_MAP:
                unknown.add(xlsx_name)
                continue

            db_name = NAME_MAP[xlsx_name]
            if db_name is None:
                continue

            dept = dept_by_name.get(db_name)
            if not dept:
                unknown.add(f'{xlsx_name} → {db_name} (немає в DB)')
                continue

            def _int(val):
                if val is None:
                    return None
                try:
                    v = int(val)
                    return v
                except (TypeError, ValueError):
                    return None

            r = DailyReport.query.filter_by(
                report_date=report_date, department_id=dept.id
            ).first()
            if r is None:
                r = DailyReport(report_date=report_date, department_id=dept.id)
                db.session.add(r)
                created += 1
            else:
                updated += 1

            r.beds_total            = _int(row[2])
            r.beds_renovation       = _int(row[3])
            r.patients_start        = _int(row[4])
            r.admitted_total        = _int(row[5])
            r.admitted_rural        = _int(row[6])
            r.admitted_children     = _int(row[7])
            r.transferred_in        = _int(row[8])
            r.transferred_out       = _int(row[9])
            r.discharged_total      = _int(row[10])
            r.discharged_to_other   = _int(row[11])
            r.deaths                = _int(row[12])
            r.patients_end          = _int(row[13])
            r.patients_end_rural    = _int(row[14])
            r.mothers_with_children = _int(row[15])
            r.free_male             = _int(row[16])
            r.free_female           = _int(row[17])

    db.session.commit()

    print(f"Створено: {created}, оновлено: {updated}")
    if unknown:
        print(f"Невідомі назви (пропущені): {sorted(unknown)}")

    total = DailyReport.query.filter(
        DailyReport.report_date >= date(YEAR, MONTH, 1),
        DailyReport.report_date <= date(YEAR, MONTH, 30),
    ).count()
    print(f"\nDailyReport за квітень 2026: {total}")
    print(f"Очікується: ~{19 * 30} ({len(dept_by_name)} відділень × 30 днів)")
