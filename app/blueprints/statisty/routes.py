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
            from_date = date.fromisoformat(from_str if len(from_str) > 7 else from_str + '-01')
        except ValueError:
            pass
    if to_str:
        try:
            to_date = date.fromisoformat(to_str if len(to_str) > 7 else to_str + '-01')
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


def _aggregate_period(year, start_month, end_month, department_id=None):
    # Start and end dates for the period
    start_date = date(year, start_month, 1)
    last_day = calendar.monthrange(year, end_month)[1]
    end_date = date(year, end_month, last_day)

    # Get departments
    if department_id:
        depts = [Department.query.get(department_id)]
    else:
        depts = Department.query.all()

    dept_ids = [d.id for d in depts if d]
    if not dept_ids:
        return None

    # Query all reports in this range for these departments
    reports = DailyReport.query.filter(
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date,
        DailyReport.department_id.in_(dept_ids)
    ).all()

    # Total number of days in the period
    days_list = []
    curr = start_date
    while curr <= end_date:
        days_list.append(curr)
        curr += timedelta(days=1)

    # Group reports by date and department_id
    reports_by_date_dept = {}
    for r in reports:
        reports_by_date_dept.setdefault(r.report_date, {})[r.department_id] = r

    # Compute daily statistics
    daily_stats = []
    for d in days_list:
        day_reports = reports_by_date_dept.get(d, {})
        day_beds_total = 0
        day_patients_start = 0
        day_patients_end = 0
        day_admitted_total = 0
        day_admitted_rural = 0
        day_admitted_children = 0
        day_transferred_in = 0
        day_transferred_out = 0
        day_discharged_total = 0
        day_discharged_to_other = 0
        day_deaths = 0
        day_bed_days_rural = 0
        day_bed_days_renovation = 0
        day_bed_days_mothers = 0

        for dept in depts:
            r = day_reports.get(dept.id)
            if r:
                day_beds_total += r.beds_total if r.beds_total is not None else (dept.bed_capacity or 0)
                day_patients_start += r.patients_start or 0
                day_patients_end += r.patients_end or 0
                day_admitted_total += r.admitted_total or 0
                day_admitted_rural += r.admitted_rural or 0
                day_admitted_children += r.admitted_children or 0
                day_transferred_in += r.transferred_in or 0
                day_transferred_out += r.transferred_out or 0
                day_discharged_total += r.discharged_total or 0
                day_discharged_to_other += r.discharged_to_other or 0
                day_deaths += r.deaths or 0
                day_bed_days_rural += r.patients_end_rural or 0
                day_bed_days_renovation += r.beds_renovation or 0
                day_bed_days_mothers += r.mothers_with_children or 0
            else:
                day_beds_total += dept.bed_capacity or 0

        daily_stats.append({
            'beds_total': day_beds_total,
            'patients_start': day_patients_start,
            'patients_end': day_patients_end,
            'admitted_total': day_admitted_total,
            'admitted_rural': day_admitted_rural,
            'admitted_children': day_admitted_children,
            'transferred_in': day_transferred_in,
            'transferred_out': day_transferred_out,
            'discharged_total': day_discharged_total,
            'discharged_to_other': day_discharged_to_other,
            'deaths': day_deaths,
            'bed_days_rural': day_bed_days_rural,
            'bed_days_renovation': day_bed_days_renovation,
            'bed_days_mothers': day_bed_days_mothers,
        })

    # Now aggregate the period stats
    total_days = len(daily_stats)
    if total_days == 0:
        return None

    # Sum of all movement and bed days
    admitted_total = sum(s['admitted_total'] for s in daily_stats)
    admitted_rural = sum(s['admitted_rural'] for s in daily_stats)
    admitted_children = sum(s['admitted_children'] for s in daily_stats)
    transferred_in = sum(s['transferred_in'] for s in daily_stats)
    transferred_out = sum(s['transferred_out'] for s in daily_stats)
    discharged_total = sum(s['discharged_total'] for s in daily_stats)
    discharged_to_other = sum(s['discharged_to_other'] for s in daily_stats)
    deaths = sum(s['deaths'] for s in daily_stats)
    bed_days_rural = sum(s['bed_days_rural'] for s in daily_stats)
    bed_days_renovation = sum(s['bed_days_renovation'] for s in daily_stats)
    bed_days_mothers = sum(s['bed_days_mothers'] for s in daily_stats)

    # Bed days total is the sum of daily patients_end
    bed_days_total = sum(s['patients_end'] for s in daily_stats)

    # beds_total on the last day of the period
    beds_total = daily_stats[-1]['beds_total']

    # patients_end on the last day of the period
    patients_end = daily_stats[-1]['patients_end']

    # patients_start on the first day of the period
    patients_start = daily_stats[0]['patients_start']

    # beds_average is the average of daily beds_total
    beds_average = sum(s['beds_total'] for s in daily_stats) / total_days
    beds_average = round(beds_average, 1)

    return {
        'beds_total': beds_total,
        'beds_average': beds_average,
        'patients_start': patients_start,
        'admitted_total': admitted_total,
        'admitted_rural': admitted_rural,
        'admitted_children': admitted_children,
        'transferred_in': transferred_in,
        'transferred_out': transferred_out,
        'discharged_total': discharged_total,
        'discharged_to_other': discharged_to_other,
        'deaths': deaths,
        'patients_end': patients_end,
        'bed_days_total': bed_days_total,
        'bed_days_rural': bed_days_rural,
        'bed_days_renovation': bed_days_renovation,
        'bed_days_mothers': bed_days_mothers,
    }


def _get_form016_data(from_date, to_date, department_id=None):
    # Year of the report is determined by from_date
    year = from_date.year

    # Check the total count of daily reports in the calendar year to display dr_count correctly
    # The date range for the calendar year is from Jan 1st to Dec 31st
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    dr_query = DailyReport.query.filter(
        DailyReport.report_date >= year_start,
        DailyReport.report_date <= year_end,
    )
    if department_id:
        dr_query = dr_query.filter(DailyReport.department_id == department_id)
    dr_count = dr_query.count()

    selected_dept = None
    if department_id:
        selected_dept = Department.query.get(department_id)

    # Let's map months
    MONTHS_UA_NOMINATIVE = {
        1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
        5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
        9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
    }

    table = []

    # Months 1 to 6
    for m in range(1, 7):
        m_data = _aggregate_period(year, m, m, department_id)
        row = {
            'date_str': MONTHS_UA_NOMINATIVE[m],
            'is_totals': False,
        }
        if m_data:
            row.update(m_data)
        else:
            row.update({k: 0 for k in ['beds_total', 'beds_average', 'patients_start', 'admitted_total', 'admitted_rural', 'admitted_children', 'transferred_in', 'transferred_out', 'discharged_total', 'discharged_to_other', 'deaths', 'patients_end', 'bed_days_total', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers']})
        table.append(row)

    # Subtotal "За півріччя" (months 1-6)
    half_year_data = _aggregate_period(year, 1, 6, department_id)
    half_year_row = {
        'date_str': 'За півріччя',
        'is_totals': True,
    }
    if half_year_data:
        half_year_row.update(half_year_data)
    else:
        half_year_row.update({k: 0 for k in ['beds_total', 'beds_average', 'patients_start', 'admitted_total', 'admitted_rural', 'admitted_children', 'transferred_in', 'transferred_out', 'discharged_total', 'discharged_to_other', 'deaths', 'patients_end', 'bed_days_total', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers']})
    table.append(half_year_row)

    # Months 7 to 12
    for m in range(7, 13):
        m_data = _aggregate_period(year, m, m, department_id)
        row = {
            'date_str': MONTHS_UA_NOMINATIVE[m],
            'is_totals': False,
        }
        if m_data:
            row.update(m_data)
        else:
            row.update({k: 0 for k in ['beds_total', 'beds_average', 'patients_start', 'admitted_total', 'admitted_rural', 'admitted_children', 'transferred_in', 'transferred_out', 'discharged_total', 'discharged_to_other', 'deaths', 'patients_end', 'bed_days_total', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers']})
        table.append(row)

    # Total "За рік" (months 1-12)
    full_year_data = _aggregate_period(year, 1, 12, department_id)
    full_year_row = {
        'date_str': 'За рік',
        'is_totals': True,
    }
    if full_year_data:
        full_year_row.update(full_year_data)
    else:
        full_year_row.update({k: 0 for k in ['beds_total', 'beds_average', 'patients_start', 'admitted_total', 'admitted_rural', 'admitted_children', 'transferred_in', 'transferred_out', 'discharged_total', 'discharged_to_other', 'deaths', 'patients_end', 'bed_days_total', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers']})
    table.append(full_year_row)

    totals = full_year_row

    return table, totals, 'daily_report', dr_count


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
        return redirect(url_for('statisty.form007_edit', report_date_str=report_date_str))

    # GET: Pre-populate fallbacks
    prev_date = report_date - timedelta(days=1)
    prev_reports = {
        r.department_id: r
        for r in DailyReport.query.filter_by(report_date=prev_date).all()
    }

    return render_template(
        'statisty/form007_edit.html',
        depts=depts,
        existing=existing,
        prev_reports=prev_reports,
        report_date=report_date,
    )



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

    department_id_str = request.args.get('department_id', '').strip()
    department_id = int(department_id_str) if department_id_str.isdigit() else None

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()
    selected_dept = Department.query.get(department_id) if department_id else None

    table, totals, data_source, dr_count = _get_form016_data(from_date, to_date, department_id)

    return render_template(
        'statisty/form016.html',
        table=table,
        totals=totals,
        from_date=from_date,
        to_date=to_date,
        period_label=_period_label(from_date, to_date),
        data_source=data_source,
        dr_count=dr_count,
        depts=depts,
        department_id=department_id,
        selected_dept=selected_dept,
    )


# ---- Form 016 Excel export --------------------------------------------------

@statisty_bp.route('/form016/export')
@role_required('admin', 'viewer')
def form016_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    from_date, to_date = _parse_date_range()

    department_id_str = request.args.get('department_id', '').strip()
    department_id = int(department_id_str) if department_id_str.isdigit() else None

    selected_dept = Department.query.get(department_id) if department_id else None
    table, totals, data_source, dr_count = _get_form016_data(from_date, to_date, department_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Форма 016"

    # Common styles
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left = Alignment(horizontal='left', vertical='center')
    right = Alignment(horizontal='right', vertical='center')
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill_hdr = PatternFill("solid", fgColor="D9E1F2")
    fill_computed = PatternFill("solid", fgColor="FFFBEB")

    # Column widths (17 columns: A to Q)
    col_widths = [
        32,  # A: Назва профілю ліжка / Дата (Col А)
        12,  # B: Розгорнуто ліжок на кінець звіт. періоду (Col 1)
        12,  # C: Число середньомісячних (річних) ліжок (Col 2)
        12,  # D: Перебувало на початок звітного періоду (Col 3)
        10,  # E: Поступило - всього (Col 4)
        10,  # F: Поступило - сільських жителів (Col 5)
        10,  # G: Поступило - дітей до 17 р. вкл. (Col 6)
        10,  # H: Переведено - із інших відділень (Col 7)
        10,  # I: Переведено - в інші відділення (Col 8)
        10,  # J: Виписано - всього (Col 9)
        10,  # K: Виписано - переведено в інші стаціонари (Col 10)
        10,  # L: Померло (Col 11)
        12,  # M: Перебувало на кінець звітного періоду (Col 12)
        12,  # N: Ліжко-дні - всього (Col 13)
        12,  # O: Ліжко-дні - сільськими (Col 14)
        12,  # P: Ліжко-дні - ремонт (Col 15)
        12,  # Q: Ліжко-дні - матерями (Col 16)
    ]
    for ci, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    # Row 1 & 2: Ministry of Health Ukraine & Official Form Info
    ws.merge_cells('A1:I1')
    ws['A1'] = "Міністерство охорони здоров'я України / КНП «Калуська ЦРЛ»"
    ws['A1'].font = Font(name="Arial", size=8, italic=True)
    ws['A1'].alignment = left

    ws.merge_cells('J1:Q1')
    ws['J1'] = "МЕДИЧНА ДОКУМЕНТАЦІЯ"
    ws['J1'].font = Font(name="Arial", size=8, bold=True)
    ws['J1'].alignment = right

    ws.merge_cells('A2:I2')
    ws['A2'] = "вул. Каракая, 25, м. Калуш, Івано-Франківська обл., 77300"
    ws['A2'].font = Font(name="Arial", size=8, italic=True)
    ws['A2'].alignment = left

    ws.merge_cells('J2:Q2')
    ws['J2'] = "Форма № 016/о / Затверджено наказом МОЗ України від 27.12.05 р. № 760"
    ws['J2'].font = Font(name="Arial", size=8, italic=True)
    ws['J2'].alignment = right

    # Period title (A3:Q3)
    period_label = _period_label(from_date, to_date)
    ws.merge_cells('A3:Q3')
    if selected_dept:
        ws['A3'] = f"ЗВЕДЕНА ВІДОМІСТЬ обліку руху хворих і ліжкового фонду в стаціонарі, відділенні або профілю ліжок по відділенню: {selected_dept.name} за період: {period_label}"
    else:
        ws['A3'] = f"ЗВЕДЕНА ВІДОМІСТЬ обліку руху хворих і ліжкового фонду в стаціонарі за період: {period_label}"
    ws['A3'].font = Font(name="Arial", size=11, bold=True)
    ws['A3'].alignment = center

    # Setup headers spanning Rows 4, 5, 6, 7, 8
    # Apply default header styles to every cell in A4:Q8
    for r in range(4, 9):
        for c in range(1, 18):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(name="Arial", size=8, bold=True)
            cell.alignment = center
            cell.fill = fill_hdr
            cell.border = border

    # Row 4 merges and texts
    ws.merge_cells('A4:A7')
    ws['A4'] = "Найменування місяців"

    ws.merge_cells('B4:B7')
    ws['B4'] = "Число ліжок у межах кошторису фактично розгорнутих + згорнутих на ремонт на кінець звітного періоду\n(гр. 1)"

    ws.merge_cells('C4:C7')
    ws['C4'] = "Середньомісячних (річних) ліжок\n(гр. 2)"

    ws.merge_cells('D4:D7')
    ws['D4'] = "Перебувало хворих на початок звітного періоду\n(гр. 3)"

    ws.merge_cells('E4:K4')
    ws['E4'] = "За звітний період"

    ws.merge_cells('E5:G5')
    ws['E5'] = "поступило хворих"

    ws.merge_cells('E6:E7')
    ws['E6'] = "всього\n(гр. 4)"

    ws.merge_cells('F6:G6')
    ws['F6'] = "із них"

    ws.cell(row=7, column=6, value="сільських\nжителів\n(гр. 5)")
    ws.cell(row=7, column=7, value="дітей до 17 років\nвключно\n(гр. 6)")

    ws.merge_cells('H5:I5')
    ws['H5'] = "переведено хворих всередині лікарні"

    ws.merge_cells('H6:H7')
    ws['H6'] = "із інших\nвідділень\n(гр. 7)"

    ws.merge_cells('I6:I7')
    ws['I6'] = "в інші\nвідділення\n(гр. 8)"

    ws.merge_cells('J5:K5')
    ws['J5'] = "виписано хворих"

    ws.merge_cells('J6:J7')
    ws['J6'] = "всього\n(гр. 9)"

    ws.merge_cells('K6:K7')
    ws['K6'] = "у тому числі\nпереведено в інші\nстаціонари (з гр.9)\n(гр. 10)"

    ws.merge_cells('L4:L7')
    ws['L4'] = "Померло\n(гр. 11)"

    ws.merge_cells('M4:M7')
    ws['M4'] = "Перебувало хворих на кінець звітного періоду\n(гр. 12)"

    ws.merge_cells('N4:N7')
    ws['N4'] = "Проведено всіма хворими ліжко-днів\n(гр. 13)"

    ws.merge_cells('O4:O7')
    ws['O4'] = "у тому числі сільськими жителями\n(гр. 14)"

    ws.merge_cells('P4:P7')
    ws['P4'] = "Число ліжко-днів закриття\n(гр. 15)"

    ws.merge_cells('Q4:Q7')
    ws['Q4'] = "Крім того, проведено ліжко-днів матерями з хворими дітьми\n(гр. 16)"

    # Row 8: column letters/numbers (official state form numbering)
    ws.cell(row=8, column=1, value="А")
    for col_idx in range(1, 17):
        ws.cell(row=8, column=col_idx + 1, value=col_idx)

    # Set row heights for headers
    ws.row_dimensions[1].height = 18
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 25
    ws.row_dimensions[4].height = 20
    ws.row_dimensions[5].height = 20
    ws.row_dimensions[6].height = 20
    ws.row_dimensions[7].height = 20
    ws.row_dimensions[8].height = 18

    # Populate rows starting from row 9 (Totals row sits at Row 9 as first item of table)
    for ri, row in enumerate(table, 9):
        is_totals_row = row.get('is_totals', False)
        col_a_val = row['date_str']

        # Map row values to the 17 Excel columns (A to Q)
        vals = [
            col_a_val,
            row['beds_total'] if row['beds_total'] is not None else '',
            row['beds_average'] if row['beds_average'] is not None else '',
            row['patients_start'] if row['patients_start'] is not None else '',
            row['admitted_total'],
            row['admitted_rural'],
            row['admitted_children'],
            row['transferred_in'],
            row['transferred_out'],
            row['discharged_total'],
            row['discharged_to_other'],
            row['deaths'],
            row['patients_end'] if row['patients_end'] is not None else '',
            row['bed_days_total'],
            row['bed_days_rural'],
            row['bed_days_renovation'],
            row['bed_days_mothers'],
        ]

        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.border = border
            
            # Formatting for Totals vs regular rows
            if is_totals_row:
                cell.font = Font(name="Arial", size=9, bold=True)
            else:
                cell.font = Font(name="Arial", size=9)

            if ci == 1:
                if is_totals_row:
                    cell.alignment = left
                else:
                    cell.alignment = center
            else:
                cell.alignment = center

            # Highlight computed columns: Column 2 (Excel C, ci=3) and Column 13 (Excel N, ci=14)
            if ci in [3, 14]:
                cell.fill = fill_computed

        ws.row_dimensions[ri].height = 20

    # Official Signature Block at the bottom
    sig_row = len(table) + 11
    ws.cell(row=sig_row, column=1, value="Заступник генерального директора").font = Font(name="Arial", size=9, bold=True)
    ws.cell(row=sig_row+1, column=1, value="КНП «Калуська ЦРЛ» з адміністративної діяльності").font = Font(name="Arial", size=9)
    ws.cell(row=sig_row+2, column=1, value="____________________ Л. Луців").font = Font(name="Arial", size=9)
    
    ws.cell(row=sig_row+2, column=12, value="____________________ Валерій ПАЛЯНИЦЯ").font = Font(name="Arial", size=9, bold=True)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"form016_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.xlsx"
    return Response(
        buf.read(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

