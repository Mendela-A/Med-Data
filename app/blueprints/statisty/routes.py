from flask import render_template, request, redirect, url_for, Response
from flask_login import login_required
from datetime import date, timedelta, datetime
import calendar
from io import BytesIO
from sqlalchemy import func, case

from app.extensions import db
from models import Record, Department
from decorators import role_required
from . import statisty_bp


def _parse_date_range():
    """Parse from_date/to_date from query params; default = current month."""
    today = date.today()
    from_str = request.args.get('from_date', '').strip()
    to_str = request.args.get('to_date', '').strip()

    from_date = None
    to_date = None

    if from_str:
        try:
            from_date = date.fromisoformat(from_str)
        except ValueError:
            pass
    if to_str:
        try:
            to_date = date.fromisoformat(to_str)
        except ValueError:
            pass

    if from_date is None:
        from_date = date(today.year, today.month, 1)
    if to_date is None:
        last_day = calendar.monthrange(from_date.year, from_date.month)[1]
        to_date = date(from_date.year, from_date.month, last_day)

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    return from_date, to_date


def _period_label(from_date, to_date):
    last_day = calendar.monthrange(from_date.year, from_date.month)[1]
    if from_date.day == 1 and to_date == date(from_date.year, from_date.month, last_day):
        months_ua = {
            1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
            5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
            9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
        }
        return f"{months_ua[from_date.month]} {from_date.year}"
    return f"{from_date.strftime('%d.%m.%Y')} — {to_date.strftime('%d.%m.%Y')}"


@statisty_bp.route('/')
@role_required('admin', 'viewer')
def index():
    return redirect(url_for('statisty.form016'))


@statisty_bp.route('/form016')
@role_required('admin', 'viewer')
def form016():
    from_date, to_date = _parse_date_range()
    query_end = to_date + timedelta(days=1)
    days_in_period = (to_date - from_date).days + 1

    # Bed capacity per department (from Department table)
    dept_capacity = {d.name: d.bed_capacity for d in Department.query.all() if d.bed_capacity}

    # Per-department aggregation
    rows = db.session.query(
        func.coalesce(Record.discharge_department, 'Без відділення').label('dept'),
        func.count(Record.id).label('treated'),
        func.coalesce(func.sum(Record.k_days), 0).label('bed_days'),
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deaths'),
        func.count(Record.date_of_admission).label('admitted'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end,
    ).group_by(
        func.coalesce(Record.discharge_department, 'Без відділення')
    ).order_by(
        func.coalesce(Record.discharge_department, 'Без відділення')
    ).all()

    table = []
    totals = {'treated': 0, 'bed_days': 0, 'deaths': 0, 'admitted': 0,
              'avg_los': None, 'mortality_pct': None, 'occupancy': None, 'turnover': None}

    for dept, treated, bed_days, deaths, admitted in rows:
        capacity = dept_capacity.get(dept)
        avg_los = round(bed_days / treated, 1) if treated else None
        mortality_pct = round(deaths * 100 / treated, 2) if treated else None
        occupancy = round(bed_days / (capacity * days_in_period), 3) if capacity else None
        turnover = round(treated / capacity, 1) if capacity else None

        table.append({
            'dept': dept,
            'capacity': capacity,
            'admitted': admitted,
            'treated': treated,
            'bed_days': bed_days,
            'deaths': deaths,
            'avg_los': avg_los,
            'mortality_pct': mortality_pct,
            'occupancy': occupancy,
            'turnover': turnover,
        })

        totals['treated'] += treated
        totals['bed_days'] += bed_days
        totals['deaths'] += deaths
        totals['admitted'] += admitted

    if totals['treated']:
        totals['avg_los'] = round(totals['bed_days'] / totals['treated'], 1)
        totals['mortality_pct'] = round(totals['deaths'] * 100 / totals['treated'], 2)

    return render_template(
        'statisty/form016.html',
        table=table,
        totals=totals,
        from_date=from_date,
        to_date=to_date,
        period_label=_period_label(from_date, to_date),
    )


@statisty_bp.route('/form007')
@role_required('admin', 'viewer')
def form007():
    from_date, to_date = _parse_date_range()
    # Clamp to single month for 007
    first_day = date(from_date.year, from_date.month, 1)
    last_day_num = calendar.monthrange(from_date.year, from_date.month)[1]
    last_day = date(from_date.year, from_date.month, last_day_num)
    query_end = last_day + timedelta(days=1)

    # All days in selected month
    all_days = [date(first_day.year, first_day.month, d) for d in range(1, last_day_num + 1)]

    # Discharges (non-death) per department per day
    discharge_rows = db.session.query(
        func.coalesce(Record.discharge_department, 'Без відділення').label('dept'),
        func.date(Record.date_of_discharge).label('day'),
        func.count(Record.id).label('cnt'),
        func.coalesce(func.sum(Record.k_days), 0).label('bed_days'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= first_day,
        Record.date_of_discharge < query_end,
        Record.date_of_death.is_(None),
    ).group_by('dept', 'day').all()

    # Deaths per department per day (by date_of_death)
    death_rows = db.session.query(
        func.coalesce(Record.discharge_department, 'Без відділення').label('dept'),
        func.date(Record.date_of_death).label('day'),
        func.count(Record.id).label('cnt'),
    ).filter(
        Record.date_of_death.isnot(None),
        Record.date_of_death >= first_day,
        Record.date_of_death < query_end,
    ).group_by('dept', 'day').all()

    # Admissions per department per day (if date_of_admission is populated)
    admission_rows = db.session.query(
        func.coalesce(Record.discharge_department, 'Без відділення').label('dept'),
        func.date(Record.date_of_admission).label('day'),
        func.count(Record.id).label('cnt'),
    ).filter(
        Record.date_of_admission.isnot(None),
        Record.date_of_admission >= first_day,
        Record.date_of_admission < query_end,
    ).group_by('dept', 'day').all()

    # Build lookup: dept -> day_str -> {discharged, deaths, admitted, bed_days}
    data = {}

    def _get(dept, day_str):
        return data.setdefault(dept, {}).setdefault(day_str, {
            'discharged': 0, 'deaths': 0, 'admitted': 0, 'bed_days': 0
        })

    for dept, day, cnt, bed_days in discharge_rows:
        entry = _get(dept, str(day))
        entry['discharged'] += cnt
        entry['bed_days'] += bed_days

    for dept, day, cnt in death_rows:
        _get(dept, str(day))['deaths'] += cnt

    for dept, day, cnt in admission_rows:
        _get(dept, str(day))['admitted'] += cnt

    depts = sorted(data.keys())

    return render_template(
        'statisty/form007.html',
        depts=depts,
        data=data,
        all_days=all_days,
        from_date=first_day,
        to_date=last_day,
        period_label=_period_label(first_day, last_day),
    )


@statisty_bp.route('/form016/export')
@role_required('admin', 'viewer')
def form016_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    from_date, to_date = _parse_date_range()
    query_end = to_date + timedelta(days=1)
    days_in_period = (to_date - from_date).days + 1
    dept_capacity = {d.name: d.bed_capacity for d in Department.query.all() if d.bed_capacity}

    rows = db.session.query(
        func.coalesce(Record.discharge_department, 'Без відділення').label('dept'),
        func.count(Record.id).label('treated'),
        func.coalesce(func.sum(Record.k_days), 0).label('bed_days'),
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deaths'),
        func.count(Record.date_of_admission).label('admitted'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end,
    ).group_by(
        func.coalesce(Record.discharge_department, 'Без відділення')
    ).order_by(
        func.coalesce(Record.discharge_department, 'Без відділення')
    ).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Форма 016"

    header_font = Font(bold=True)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill_header = PatternFill("solid", fgColor="D9E1F2")

    period_label = _period_label(from_date, to_date)
    ws.merge_cells('A1:J1')
    ws['A1'] = f"Форма 016 — Звіт про роботу стаціонару: {period_label}"
    ws['A1'].font = Font(bold=True, size=12)
    ws['A1'].alignment = center

    headers = [
        'Відділення', 'Ліжок (план)', 'Поступило', 'Проліковано',
        'Ліжко-днів', 'Померло', 'Летальність %',
        'Сер. ліжко-день', 'Зайнятість ліжка', 'Оборот ліжка'
    ]
    col_widths = [30, 12, 12, 12, 12, 10, 13, 14, 15, 13]

    for col_idx, (h, w) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=2, column=col_idx, value=h)
        cell.font = header_font
        cell.alignment = center
        cell.fill = fill_header
        cell.border = border
        ws.column_dimensions[cell.column_letter].width = w

    tot_treated = tot_bed_days = tot_deaths = tot_admitted = 0

    for row_idx, (dept, treated, bed_days, deaths, admitted) in enumerate(rows, start=3):
        capacity = dept_capacity.get(dept)
        avg_los = round(bed_days / treated, 1) if treated else ''
        mortality_pct = round(deaths * 100 / treated, 2) if treated else ''
        occupancy = round(bed_days / (capacity * days_in_period), 3) if capacity else ''
        turnover = round(treated / capacity, 1) if capacity else ''

        vals = [dept, capacity or '', admitted, treated, bed_days, deaths,
                mortality_pct, avg_los, occupancy, turnover]
        for col_idx, v in enumerate(vals, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=v)
            cell.border = border
            if col_idx > 1:
                cell.alignment = Alignment(horizontal='center')

        tot_treated += treated
        tot_bed_days += bed_days
        tot_deaths += deaths
        tot_admitted += admitted

    # Totals row
    tot_row = len(rows) + 3
    tot_avg_los = round(tot_bed_days / tot_treated, 1) if tot_treated else ''
    tot_mortality = round(tot_deaths * 100 / tot_treated, 2) if tot_treated else ''
    tot_vals = ['Разом', '', tot_admitted, tot_treated, tot_bed_days,
                tot_deaths, tot_mortality, tot_avg_los, '', '']
    for col_idx, v in enumerate(tot_vals, start=1):
        cell = ws.cell(row=tot_row, column=col_idx, value=v)
        cell.font = header_font
        cell.border = border
        if col_idx > 1:
            cell.alignment = Alignment(horizontal='center')

    ws.row_dimensions[2].height = 40

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"form016_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.xlsx"
    return Response(
        buf.read(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
