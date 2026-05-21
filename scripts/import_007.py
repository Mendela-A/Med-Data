"""
One-off import script: load 007.xlsx DailyReport data into the database.

Usage (inside Docker):
    docker cp "007.xlsx" flask_app:/tmp/007.xlsx
    docker exec -e SECRET_KEY=... flask_app python3 /app/scripts/import_007.py /tmp/007.xlsx 2026-05-01

Sheet name must match the day number (e.g. sheet "01" → day 01 of the month).
"""

import sys
import os
from datetime import date

# Allow running from the project root
sys.path.insert(0, '/app')

xlsx_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/007.xlsx'
date_str  = sys.argv[2] if len(sys.argv) > 2 else '2026-05-01'
report_date = date.fromisoformat(date_str)

import openpyxl

wb = openpyxl.load_workbook(xlsx_path, data_only=True)

# Sheet name = day number zero-padded, e.g. "01"
sheet_name = f"{report_date.day:02d}"
if sheet_name not in wb.sheetnames:
    # Fallback to first sheet
    sheet_name = wb.sheetnames[0]
ws = wb[sheet_name]

print(f"Importing sheet '{sheet_name}' → {report_date}")

from app import create_app
from app.extensions import db
from models import Department, DailyReport

app = create_app()
with app.app_context():
    dept_map = {d.name: d for d in Department.query.all()}
    created_depts = 0
    created_reports = 0
    updated_reports = 0

    # Data rows start at row 10 (0-indexed: row index 9)
    # Skip header rows and summary rows (КНП, ВСЬОГО, Пологовий, Готувала)
    SKIP_NAMES = {'КНП', 'ВСЬОГО', 'Пологовий', 'Готувала', None, ''}

    for row in ws.iter_rows(min_row=11, values_only=True):
        name = row[0]
        if name is None:
            continue
        name = str(name).strip()
        if not name or any(skip in name for skip in ('КНП', 'ВСЬОГО', 'Готувала')):
            continue

        # Find or create department
        dept = dept_map.get(name)
        if dept is None:
            dept = Department(
                name=name,
                row_no=row[1] if row[1] else None,
                bed_capacity=row[2] if row[2] else None,
            )
            db.session.add(dept)
            db.session.flush()
            dept_map[name] = dept
            created_depts += 1
            print(f"  Created dept: {name}")
        else:
            if dept.row_no is None and row[1]:
                dept.row_no = int(row[1])
            if dept.bed_capacity is None and row[2]:
                dept.bed_capacity = int(row[2])

        # Upsert DailyReport
        r = DailyReport.query.filter_by(
            report_date=report_date, department_id=dept.id
        ).first()
        is_new = r is None
        if is_new:
            r = DailyReport(report_date=report_date, department_id=dept.id)
            db.session.add(r)

        def _int(v):
            try:
                return int(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        r.beds_total            = _int(row[2])   # col C (3)
        r.beds_renovation       = _int(row[3])   # col D (4)
        r.patients_start        = _int(row[4])   # col E (5)
        r.admitted_total        = _int(row[5])   # col F (6)
        r.admitted_rural        = _int(row[6])   # col G (7)
        r.admitted_children     = _int(row[7])   # col H (8)
        r.transferred_in        = _int(row[8])   # col I (9)
        r.transferred_out       = _int(row[9])   # col J (10)
        r.discharged_total      = _int(row[10])  # col K (11)
        r.discharged_to_other   = _int(row[11])  # col L (12)
        r.deaths                = _int(row[12])  # col M (13)
        r.patients_end          = _int(row[13])  # col N (14)
        r.patients_end_rural    = _int(row[14])  # col O (15)
        r.mothers_with_children = _int(row[15])  # col P (16)
        r.free_male             = _int(row[16])  # col Q (17)
        r.free_female           = _int(row[17])  # col R (18)
        # col S (19) = free_total = computed property (beds_total - patients_end)

        if is_new:
            created_reports += 1
        else:
            updated_reports += 1

    db.session.commit()
    print(f"\nDone. Depts created: {created_depts}. "
          f"Reports: {created_reports} created, {updated_reports} updated.")
