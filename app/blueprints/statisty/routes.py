from flask import render_template, request, redirect, url_for, Response, flash, abort, send_file
from flask_login import login_required, current_user
from datetime import date, timedelta, datetime
import calendar
from io import BytesIO
from sqlalchemy import func, case

from app.extensions import db
from models import Record, Department, DailyReport
from decorators import role_required
from . import statisty_bp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date_range():
    today = date.today()
    from_str = request.args.get('from_date', '').strip()
    to_str   = request.args.get('to_date', '').strip()
    from_date = None
    to_date   = None
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
    months_ua = {
        1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
        5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
        9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
    }
    last_day = calendar.monthrange(from_date.year, from_date.month)[1]
    if from_date.day == 1 and to_date == date(from_date.year, from_date.month, last_day):
        return f"{months_ua[from_date.month]} {from_date.year}"
    return f"{from_date.strftime('%d.%m.%Y')} — {to_date.strftime('%d.%m.%Y')}"


def _autofill_for_dept(report_date, dept):
    """Compute auto-fillable columns from Record data."""
    admitted = Record.query.filter(
        Record.date_of_admission == report_date,
        Record.discharge_department == dept.name,
    ).count()

    discharged = Record.query.filter(
        Record.date_of_discharge == report_date,
        Record.discharge_department == dept.name,
        Record.date_of_death.is_(None),
    ).count()

    deaths = Record.query.filter(
        Record.date_of_death == report_date,
        Record.discharge_department == dept.name,
    ).count()

    prev = DailyReport.query.filter_by(
        department_id=dept.id,
        report_date=report_date - timedelta(days=1),
    ).first()
    patients_start = prev.patients_end if prev else None

    return {
        'beds_total':      dept.bed_capacity,
        'patients_start':  patients_start,
        'admitted_total':  admitted,
        'discharged_total': discharged,
        'deaths':          deaths,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@statisty_bp.route('/')
@role_required('admin', 'viewer')
def index():
    return redirect(url_for('statisty.form016'))


# ---- Form 007 list (month overview) ----------------------------------------

@statisty_bp.route('/form007')
@role_required('admin', 'viewer')
def form007():
    from_date, _ = _parse_date_range()
    first_day = date(from_date.year, from_date.month, 1)
    last_day_num = calendar.monthrange(from_date.year, from_date.month)[1]
    last_day = date(from_date.year, from_date.month, last_day_num)

    # All days in month
    all_days = [date(first_day.year, first_day.month, d) for d in range(1, last_day_num + 1)]

    # Existing reports for the month
    reports = DailyReport.query.filter(
        DailyReport.report_date >= first_day,
        DailyReport.report_date <= last_day,
    ).all()

    # Build dict: date_str -> dept_id -> report
    report_map = {}
    for r in reports:
        report_map.setdefault(r.report_date, {})[r.department_id] = r

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()

    return render_template(
        'statisty/form007.html',
        depts=depts,
        all_days=all_days,
        report_map=report_map,
        from_date=first_day,
        to_date=last_day,
        period_label=_period_label(first_day, last_day),
    )


# ---- Form 007 single day view ----------------------------------------------

@statisty_bp.route('/form007/<report_date_str>')
@role_required('admin', 'viewer')
def form007_day(report_date_str):
    try:
        report_date = date.fromisoformat(report_date_str)
    except ValueError:
        abort(404)

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()
    reports = {
        r.department_id: r
        for r in DailyReport.query.filter_by(report_date=report_date).all()
    }

    # Compute free_total for each
    rows = []
    totals = {k: 0 for k in ['beds_total', 'beds_renovation', 'patients_start',
                               'admitted_total', 'admitted_rural', 'admitted_children',
                               'transferred_in', 'transferred_out', 'discharged_total',
                               'discharged_to_other', 'deaths', 'patients_end',
                               'patients_end_rural', 'mothers_with_children',
                               'free_male', 'free_female', 'free_total']}

    for dept in depts:
        r = reports.get(dept.id)
        free_total = None
        if r:
            free_total = r.free_total
            for k in totals:
                v = getattr(r, k, None) if k != 'free_total' else free_total
                if v is not None:
                    totals[k] += v
        rows.append((dept, r, free_total))

    return render_template(
        'statisty/form007_day.html',
        rows=rows,
        report_date=report_date,
        totals=totals,
    )


# ---- Form 007 edit (single day, all departments) ---------------------------

@statisty_bp.route('/form007/<report_date_str>/edit', methods=['GET', 'POST'])
@role_required('admin', 'viewer')
def form007_edit(report_date_str):
    try:
        report_date = date.fromisoformat(report_date_str)
    except ValueError:
        abort(404)

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()
    existing = {
        r.department_id: r
        for r in DailyReport.query.filter_by(report_date=report_date).all()
    }

    if request.method == 'POST':
        for dept in depts:
            r = existing.get(dept.id)
            if r is None:
                r = DailyReport(report_date=report_date, department_id=dept.id,
                                 created_by=current_user.id)
                db.session.add(r)

            def _int(field):
                v = request.form.get(f'{field}_{dept.id}', '').strip()
                return int(v) if v else None

            r.beds_total            = _int('beds_total')
            r.beds_renovation       = _int('beds_renovation')
            r.patients_start        = _int('patients_start')
            r.admitted_total        = _int('admitted_total')
            r.admitted_rural        = _int('admitted_rural')
            r.admitted_children     = _int('admitted_children')
            r.transferred_in        = _int('transferred_in')
            r.transferred_out       = _int('transferred_out')
            r.discharged_total      = _int('discharged_total')
            r.discharged_to_other   = _int('discharged_to_other')
            r.deaths                = _int('deaths')
            r.patients_end_rural    = _int('patients_end_rural')
            r.mothers_with_children = _int('mothers_with_children')
            r.free_male             = _int('free_male')
            r.free_female           = _int('free_female')
            r.updated_by            = current_user.id

            # Recompute col14
            r.patients_end = r.compute_patients_end()

        db.session.commit()
        flash(f"Форму 007 за {report_date.strftime('%d.%m.%Y')} збережено.", 'success')
        return redirect(url_for('statisty.form007_day', report_date_str=report_date_str))

    return render_template(
        'statisty/form007_edit.html',
        depts=depts,
        existing=existing,
        report_date=report_date,
    )


# ---- Form 007 autofill (POST) -----------------------------------------------

@statisty_bp.route('/form007/<report_date_str>/autofill', methods=['POST'])
@role_required('admin', 'viewer')
def form007_autofill(report_date_str):
    try:
        report_date = date.fromisoformat(report_date_str)
    except ValueError:
        abort(404)

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()
    existing = {
        r.department_id: r
        for r in DailyReport.query.filter_by(report_date=report_date).all()
    }

    for dept in depts:
        auto = _autofill_for_dept(report_date, dept)

        r = existing.get(dept.id)
        if r is None:
            r = DailyReport(report_date=report_date, department_id=dept.id,
                             created_by=current_user.id)
            db.session.add(r)

        # Only overwrite auto-computed fields; keep manual fields intact
        if auto['beds_total'] is not None:
            r.beds_total = auto['beds_total']
        if auto['patients_start'] is not None:
            r.patients_start = auto['patients_start']
        r.admitted_total   = auto['admitted_total']
        r.discharged_total = auto['discharged_total']
        r.deaths           = auto['deaths']
        r.updated_by       = current_user.id

        # Recompute col14
        r.patients_end = r.compute_patients_end()

    db.session.commit()
    flash(f"Авто-заповнення за {report_date.strftime('%d.%m.%Y')} виконано з даних записів.", 'success')
    return redirect(url_for('statisty.form007_day', report_date_str=report_date_str))


# ---- Form 007 print (PDF) ---------------------------------------------------

@statisty_bp.route('/form007/<report_date_str>/print')
@role_required('admin', 'viewer')
def form007_print(report_date_str):
    try:
        report_date = date.fromisoformat(report_date_str)
    except ValueError:
        abort(404)

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()
    reports = {
        r.department_id: r
        for r in DailyReport.query.filter_by(report_date=report_date).all()
    }

    rows = []
    totals = {k: 0 for k in ['beds_total', 'beds_renovation', 'patients_start',
                               'admitted_total', 'admitted_rural', 'admitted_children',
                               'transferred_in', 'transferred_out', 'discharged_total',
                               'discharged_to_other', 'deaths', 'patients_end',
                               'patients_end_rural', 'mothers_with_children',
                               'free_male', 'free_female', 'free_total']}
    for dept in depts:
        r = reports.get(dept.id)
        if r is None:
            continue  # skip depts with no data for this day
        free_total = r.free_total
        for k in totals:
            v = getattr(r, k, None) if k != 'free_total' else free_total
            if v:
                totals[k] += v
        rows.append((dept, r, free_total))

    html_string = render_template(
        'print_form007.html',
        rows=rows,
        totals=totals,
        report_date=report_date,
    )

    try:
        from weasyprint import HTML
    except ImportError:
        flash('WeasyPrint не встановлено.', 'danger')
        return redirect(url_for('statisty.form007_day', report_date_str=report_date_str))

    pdf = HTML(string=html_string).write_pdf()
    bio = BytesIO(pdf)
    bio.seek(0)
    return send_file(
        bio,
        as_attachment=False,
        download_name=f"forma007_{report_date_str}.pdf",
        mimetype='application/pdf',
    )


# ---- Form 016 ---------------------------------------------------------------

@statisty_bp.route('/form016')
@role_required('admin', 'viewer')
def form016():
    from_date, to_date = _parse_date_range()
    query_end = to_date + timedelta(days=1)
    days_in_period = (to_date - from_date).days + 1

    # Check if DailyReport data exists for this period
    dr_count = DailyReport.query.filter(
        DailyReport.report_date >= from_date,
        DailyReport.report_date <= to_date,
    ).count()

    data_source = 'daily_report' if dr_count > 0 else 'records'

    if data_source == 'daily_report':
        rows_raw = db.session.query(
            Department.name.label('dept'),
            Department.bed_capacity.label('capacity'),
            Department.row_no.label('row_no'),
            func.sum(DailyReport.admitted_total).label('admitted'),
            func.sum(DailyReport.discharged_total + DailyReport.deaths).label('treated'),
            func.sum(DailyReport.patients_end).label('bed_days'),
            func.sum(DailyReport.deaths).label('deaths'),
        ).join(Department, DailyReport.department_id == Department.id).filter(
            DailyReport.report_date >= from_date,
            DailyReport.report_date <= to_date,
        ).group_by(DailyReport.department_id).order_by(
            Department.row_no.nullslast(), Department.name
        ).all()
    else:
        dept_capacity = {d.name: d.bed_capacity for d in Department.query.all() if d.bed_capacity}
        rows_raw = db.session.query(
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

    for row in rows_raw:
        if data_source == 'daily_report':
            dept_name = row.dept
            capacity  = row.capacity
            admitted  = row.admitted or 0
            treated   = row.treated or 0
            bed_days  = row.bed_days or 0
            deaths    = row.deaths or 0
        else:
            dept_name = row.dept
            capacity  = dept_capacity.get(dept_name) if data_source == 'records' else None
            admitted  = row.admitted if hasattr(row, 'admitted') else 0
            treated   = row.treated
            bed_days  = row.bed_days
            deaths    = row.deaths

        avg_los       = round(bed_days / treated, 1) if treated else None
        mortality_pct = round(deaths * 100 / treated, 2) if treated else None
        occupancy     = round(bed_days / (capacity * days_in_period), 3) if capacity else None
        turnover      = round(treated / capacity, 1) if capacity else None

        table.append({
            'dept': dept_name, 'capacity': capacity,
            'admitted': admitted, 'treated': treated,
            'bed_days': bed_days, 'deaths': deaths,
            'avg_los': avg_los, 'mortality_pct': mortality_pct,
            'occupancy': occupancy, 'turnover': turnover,
        })
        totals['treated']  += treated
        totals['bed_days'] += bed_days
        totals['deaths']   += deaths
        totals['admitted'] += admitted

    if totals['treated']:
        totals['avg_los']       = round(totals['bed_days'] / totals['treated'], 1)
        totals['mortality_pct'] = round(totals['deaths'] * 100 / totals['treated'], 2)

    return render_template(
        'statisty/form016.html',
        table=table,
        totals=totals,
        from_date=from_date,
        to_date=to_date,
        period_label=_period_label(from_date, to_date),
        data_source=data_source,
        dr_count=dr_count,
    )


# ---- Form 016 Excel export --------------------------------------------------

@statisty_bp.route('/form016/export')
@role_required('admin', 'viewer')
def form016_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    from_date, to_date = _parse_date_range()
    query_end = to_date + timedelta(days=1)
    days_in_period = (to_date - from_date).days + 1

    dr_count = DailyReport.query.filter(
        DailyReport.report_date >= from_date,
        DailyReport.report_date <= to_date,
    ).count()

    if dr_count > 0:
        rows_raw = db.session.query(
            Department.name.label('dept'),
            Department.bed_capacity.label('capacity'),
            func.sum(DailyReport.admitted_total).label('admitted'),
            func.sum(DailyReport.discharged_total + DailyReport.deaths).label('treated'),
            func.sum(DailyReport.patients_end).label('bed_days'),
            func.sum(DailyReport.deaths).label('deaths'),
        ).join(Department, DailyReport.department_id == Department.id).filter(
            DailyReport.report_date >= from_date,
            DailyReport.report_date <= to_date,
        ).group_by(DailyReport.department_id).order_by(
            Department.row_no.nullslast(), Department.name
        ).all()
        source_label = 'Форма 007 (щоденні дані)'
    else:
        dept_cap = {d.name: d.bed_capacity for d in Department.query.all() if d.bed_capacity}
        rows_raw = db.session.query(
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
        source_label = 'Записи (виписки)'

    wb = Workbook()
    ws = wb.active
    ws.title = "Форма 016"

    header_font = Font(bold=True)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill_hdr = PatternFill("solid", fgColor="D9E1F2")

    period_label = _period_label(from_date, to_date)
    ws.merge_cells('A1:J1')
    ws['A1'] = f"Форма 016 — Звіт про роботу стаціонару: {period_label} (Джерело: {source_label})"
    ws['A1'].font = Font(bold=True, size=12)
    ws['A1'].alignment = center

    headers = ['Відділення', 'Ліжок (план)', 'Поступило', 'Проліковано',
               'Ліжко-днів', 'Померло', 'Летальність %',
               'Сер. ліжко-день', 'Зайнятість ліжка', 'Оборот ліжка']
    col_widths = [30, 12, 12, 12, 12, 10, 13, 14, 15, 13]

    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=2, column=ci, value=h)
        cell.font = header_font; cell.alignment = center
        cell.fill = fill_hdr; cell.border = border
        ws.column_dimensions[cell.column_letter].width = w

    tot_treated = tot_bed_days = tot_deaths = tot_admitted = 0

    for ri, row in enumerate(rows_raw, 3):
        dept_name = row.dept
        capacity  = row.capacity if dr_count > 0 else dept_cap.get(dept_name)
        admitted  = row.admitted or 0
        treated   = row.treated or 0
        bed_days  = row.bed_days or 0
        deaths    = row.deaths or 0
        avg_los        = round(bed_days / treated, 1) if treated else ''
        mortality_pct  = round(deaths * 100 / treated, 2) if treated else ''
        occupancy      = round(bed_days / (capacity * days_in_period), 3) if capacity else ''
        turnover       = round(treated / capacity, 1) if capacity else ''

        vals = [dept_name, capacity or '', admitted, treated, bed_days,
                deaths, mortality_pct, avg_los, occupancy, turnover]
        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.border = border
            if ci > 1:
                cell.alignment = Alignment(horizontal='center')

        tot_treated  += treated
        tot_bed_days += bed_days
        tot_deaths   += deaths
        tot_admitted += admitted

    tot_row = len(list(rows_raw)) + 3
    tot_avg_los    = round(tot_bed_days / tot_treated, 1) if tot_treated else ''
    tot_mortality  = round(tot_deaths * 100 / tot_treated, 2) if tot_treated else ''
    tot_vals = ['Разом', '', tot_admitted, tot_treated, tot_bed_days,
                tot_deaths, tot_mortality, tot_avg_los, '', '']
    for ci, v in enumerate(tot_vals, 1):
        cell = ws.cell(row=tot_row, column=ci, value=v)
        cell.font = header_font; cell.border = border
        if ci > 1:
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
