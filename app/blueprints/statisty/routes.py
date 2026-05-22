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


def _get_form016_data(from_date, to_date):
    # Check if DailyReport data exists for this period
    dr_count = DailyReport.query.filter(
        DailyReport.report_date >= from_date,
        DailyReport.report_date <= to_date,
    ).count()

    data_source = 'daily_report' if dr_count > 0 else 'records'
    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()

    table = []
    totals = {k: 0 for k in ['beds_total', 'beds_renovation', 'patients_start',
                               'admitted_total', 'admitted_rural', 'admitted_children',
                               'transferred_in', 'transferred_out', 'discharged_total',
                               'discharged_to_other', 'deaths', 'patients_end',
                               'patients_end_rural', 'mothers_with_children',
                               'free_male', 'free_female', 'free_total']}

    if data_source == 'daily_report':
        # Fetch all daily reports for the period
        reports = DailyReport.query.filter(
            DailyReport.report_date >= from_date,
            DailyReport.report_date <= to_date
        ).order_by(DailyReport.report_date.asc()).all()

        # Group by department
        reports_by_dept = {}
        for r in reports:
            reports_by_dept.setdefault(r.department_id, []).append(r)

        for dept in depts:
            dept_reports = reports_by_dept.get(dept.id, [])
            if not dept_reports:
                row = {
                    'dept': dept, 'beds_total': None, 'beds_renovation': None, 'patients_start': None,
                    'admitted_total': 0, 'admitted_rural': 0, 'admitted_children': 0,
                    'transferred_in': 0, 'transferred_out': 0, 'discharged_total': 0,
                    'discharged_to_other': 0, 'deaths': 0, 'patients_end': None,
                    'patients_end_rural': None, 'mothers_with_children': 0,
                    'free_male': None, 'free_female': None, 'free_total': None,
                }
            else:
                first_report = dept_reports[0]
                last_report = dept_reports[-1]

                row = {
                    'dept': dept,
                    'beds_total': last_report.beds_total,
                    'beds_renovation': last_report.beds_renovation,
                    'patients_start': first_report.patients_start,
                    'admitted_total': sum(r.admitted_total or 0 for r in dept_reports),
                    'admitted_rural': sum(r.admitted_rural or 0 for r in dept_reports),
                    'admitted_children': sum(r.admitted_children or 0 for r in dept_reports),
                    'transferred_in': sum(r.transferred_in or 0 for r in dept_reports),
                    'transferred_out': sum(r.transferred_out or 0 for r in dept_reports),
                    'discharged_total': sum(r.discharged_total or 0 for r in dept_reports),
                    'discharged_to_other': sum(r.discharged_to_other or 0 for r in dept_reports),
                    'deaths': sum(r.deaths or 0 for r in dept_reports),
                    'patients_end': last_report.patients_end,
                    'patients_end_rural': last_report.patients_end_rural,
                    'mothers_with_children': sum(r.mothers_with_children or 0 for r in dept_reports),
                    'free_male': last_report.free_male,
                    'free_female': last_report.free_female,
                    'free_total': last_report.free_total,
                }
            table.append(row)
            for k in totals:
                v = row[k]
                if v is not None:
                    totals[k] += v
    else:
        # Fallback from patient records
        # 1. Admitted
        admitted_counts = db.session.query(
            Record.discharge_department,
            func.count(Record.id)
        ).filter(
            Record.date_of_admission >= from_date,
            Record.date_of_admission <= to_date
        ).group_by(Record.discharge_department).all()
        admitted_map = {d: c for d, c in admitted_counts if d}

        # 2. Discharged
        discharged_counts = db.session.query(
            Record.discharge_department,
            func.count(Record.id)
        ).filter(
            Record.date_of_discharge >= from_date,
            Record.date_of_discharge <= to_date,
            Record.date_of_death.is_(None)
        ).group_by(Record.discharge_department).all()
        discharged_map = {d: c for d, c in discharged_counts if d}

        # 3. Deaths
        death_counts = db.session.query(
            Record.discharge_department,
            func.count(Record.id)
        ).filter(
            Record.date_of_discharge >= from_date,
            Record.date_of_discharge <= to_date,
            Record.date_of_death.isnot(None)
        ).group_by(Record.discharge_department).all()
        death_map = {d: c for d, c in death_counts if d}

        # 4. Patients start
        start_counts = db.session.query(
            Record.discharge_department,
            func.count(Record.id)
        ).filter(
            Record.date_of_admission < from_date,
            (Record.date_of_discharge.is_(None) | (Record.date_of_discharge >= from_date))
        ).group_by(Record.discharge_department).all()
        start_map = {d: c for d, c in start_counts if d}

        # 5. Patients end
        end_counts = db.session.query(
            Record.discharge_department,
            func.count(Record.id)
        ).filter(
            Record.date_of_admission <= to_date,
            (Record.date_of_discharge.is_(None) | (Record.date_of_discharge > to_date))
        ).group_by(Record.discharge_department).all()
        end_map = {d: c for d, c in end_counts if d}

        for dept in depts:
            name = dept.name
            beds_total = dept.bed_capacity
            patients_start = start_map.get(name, 0)
            admitted_total = admitted_map.get(name, 0)
            discharged_total = discharged_map.get(name, 0)
            deaths = death_map.get(name, 0)
            patients_end = end_map.get(name, 0)
            free_total = (beds_total - patients_end) if beds_total is not None else None

            row = {
                'dept': dept,
                'beds_total': beds_total,
                'beds_renovation': 0,
                'patients_start': patients_start,
                'admitted_total': admitted_total,
                'admitted_rural': 0,
                'admitted_children': 0,
                'transferred_in': 0,
                'transferred_out': 0,
                'discharged_total': discharged_total,
                'discharged_to_other': 0,
                'deaths': deaths,
                'patients_end': patients_end,
                'patients_end_rural': 0,
                'mothers_with_children': 0,
                'free_male': None,
                'free_female': None,
                'free_total': free_total,
            }
            table.append(row)
            for k in totals:
                v = row[k]
                if v is not None:
                    totals[k] += v

        # Unmatched departments
        all_dept_names = set(admitted_map.keys()) | set(discharged_map.keys()) | set(death_map.keys()) | set(start_map.keys()) | set(end_map.keys())
        known_dept_names = {d.name for d in depts}
        unmatched_names = all_dept_names - known_dept_names

        for name in sorted(unmatched_names):
            display_name = name or 'Без відділення'
            class MockDept:
                def __init__(self, name):
                    self.name = name
                    self.bed_profile_name = name
                    self.row_no = None
            mock_dept = MockDept(display_name)

            patients_start = start_map.get(name, 0)
            admitted_total = admitted_map.get(name, 0)
            discharged_total = discharged_map.get(name, 0)
            deaths = death_map.get(name, 0)
            patients_end = end_map.get(name, 0)

            row = {
                'dept': mock_dept,
                'beds_total': None,
                'beds_renovation': 0,
                'patients_start': patients_start,
                'admitted_total': admitted_total,
                'admitted_rural': 0,
                'admitted_children': 0,
                'transferred_in': 0,
                'transferred_out': 0,
                'discharged_total': discharged_total,
                'discharged_to_other': 0,
                'deaths': deaths,
                'patients_end': patients_end,
                'patients_end_rural': 0,
                'mothers_with_children': 0,
                'free_male': None,
                'free_female': None,
                'free_total': None,
            }
            table.append(row)
            for k in totals:
                v = row[k]
                if v is not None:
                    totals[k] += v

    return table, totals, data_source, dr_count


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

    # GET: Pre-populate fallbacks
    prev_date = report_date - timedelta(days=1)
    prev_reports = {
        r.department_id: r
        for r in DailyReport.query.filter_by(report_date=prev_date).all()
    }

    # Count from Records table for the selected day
    admitted_counts = db.session.query(
        Record.discharge_department,
        func.count(Record.id)
    ).filter(
        Record.date_of_admission == report_date
    ).group_by(Record.discharge_department).all()
    admitted_map = {d: c for d, c in admitted_counts if d}

    discharged_counts = db.session.query(
        Record.discharge_department,
        func.count(Record.id)
    ).filter(
        Record.date_of_discharge == report_date,
        Record.date_of_death.is_(None)
    ).group_by(Record.discharge_department).all()
    discharged_map = {d: c for d, c in discharged_counts if d}

    death_counts = db.session.query(
        Record.discharge_department,
        func.count(Record.id)
    ).filter(
        Record.date_of_discharge == report_date,
        Record.date_of_death.isnot(None)
    ).group_by(Record.discharge_department).all()
    death_map = {d: c for d, c in death_counts if d}

    return render_template(
        'statisty/form007_edit.html',
        depts=depts,
        existing=existing,
        prev_reports=prev_reports,
        admitted_map=admitted_map,
        discharged_map=discharged_map,
        death_map=death_map,
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
    table, totals, data_source, dr_count = _get_form016_data(from_date, to_date)

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
    table, totals, data_source, dr_count = _get_form016_data(from_date, to_date)
    source_label = 'Форма 007 (щоденні дані)' if data_source == 'daily_report' else 'Записи (виписки)'

    wb = Workbook()
    ws = wb.active
    ws.title = "Форма 016"

    # Common styles
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left = Alignment(horizontal='left', vertical='center')
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill_hdr = PatternFill("solid", fgColor="D9E1F2")
    fill_computed = PatternFill("solid", fgColor="FFFBEB")

    # Column widths (19 columns)
    col_widths = [
        32,  # A: Назва профілю ліжка
        8,   # B: № рядка
        12,  # C: Розгорнуто ліжок
        12,  # D: В т.ч. на ремонті
        12,  # E: Було на поч.
        10,  # F: Поступило - Всього
        10,  # G: Поступило - Сільських
        10,  # H: Поступило - Дітей
        10,  # I: Переведено - із
        10,  # J: Переведено - в
        10,  # K: Виписано - Всього
        10,  # L: Виписано - в т.ч. переведених
        10,  # M: Померло
        12,  # N: Знаходилось - всього
        12,  # O: Знаходилось - в т.ч. сільських
        12,  # P: перебуває матерів
        10,  # Q: вільних - чол
        10,  # R: вільних - жін
        12   # S: вільних - заг
    ]
    for ci, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    # Period title (A1:S1)
    period_label = _period_label(from_date, to_date)
    ws.merge_cells('A1:S1')
    ws['A1'] = f"Форма 016 — Звіт про роботу стаціонару: {period_label} (Джерело: {source_label})"
    ws['A1'].font = Font(name="Arial", size=11, bold=True)
    ws['A1'].alignment = Alignment(horizontal='left', vertical='center')

    # Apply default header styles to every cell in A2:S6
    for r in range(2, 7):
        for c in range(1, 20):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(name="Arial", size=9, bold=True)
            cell.alignment = center
            cell.fill = fill_hdr
            cell.border = border

    # Define merges and header text
    ws.merge_cells('A2:A5')
    ws['A2'] = "Назва профілю ліжка"
    
    ws.merge_cells('B2:B5')
    ws['B2'] = "№ рядка"
    
    ws.merge_cells('C2:C5')
    ws['C2'] = "Розгорнуто ліжок, вкл.\nзгорнуті на ремонт"
    
    ws.merge_cells('D2:D5')
    ws['D2'] = "В т.ч. згорнуті\nна ремонт"
    
    ws.merge_cells('E2:M2')
    ws['E2'] = "Рух хворих за минулу добу"
    
    ws.merge_cells('N2:S2')
    ws['N2'] = "На початок поточного дня"
    
    ws.merge_cells('E3:E5')
    ws['E3'] = "Було хворих на поч. мин. доби"
    
    ws.merge_cells('F3:H3')
    ws['F3'] = "Поступило хворих"
    
    ws.merge_cells('I3:J3')
    ws['I3'] = "Переведено всередині лікарні"
    
    ws.merge_cells('K3:L3')
    ws['K3'] = "Виписано хворих"
    
    ws.merge_cells('M3:M5')
    ws['M3'] = "Померло"
    
    ws.merge_cells('N3:O3')
    ws['N3'] = "Знаходилось хворих"
    
    ws.merge_cells('P3:P5')
    ws['P3'] = "перебуває матерів при дітях"
    
    ws.merge_cells('Q3:S3')
    ws['Q3'] = "к-ть вільних місць"
    
    ws.merge_cells('F4:H4')
    ws['F4'] = "Поступило без переведення всередині лікарні"
    
    ws.merge_cells('I4:I5')
    ws['I4'] = "із інших відділів"
    
    ws.merge_cells('J4:J5')
    ws['J4'] = "в інші відділи"
    
    ws.merge_cells('K4:K5')
    ws['K4'] = "Всього"
    
    ws.merge_cells('L4:L5')
    ws['L4'] = "в т.ч. переведених в інші стаціонари"
    
    ws.merge_cells('N4:N5')
    ws['N4'] = "всього"
    
    ws.merge_cells('O4:O5')
    ws['O4'] = "в т.ч. сільських"
    
    ws.merge_cells('Q4:Q5')
    ws['Q4'] = "чоловічих"
    
    ws.merge_cells('R4:R5')
    ws['R4'] = "жіночих"
    
    ws.merge_cells('S4:S5')
    ws['S4'] = "у загальному"
    
    ws['F5'] = "Всього"
    ws['G5'] = "Сільських жителів"
    ws['H5'] = "дітей до 17 р."

    # Row 6: numbers 1 to 19
    for c in range(1, 20):
        ws.cell(row=6, column=c, value=c)

    # Set row heights for headers
    ws.row_dimensions[1].height = 25
    ws.row_dimensions[2].height = 20
    ws.row_dimensions[3].height = 20
    ws.row_dimensions[4].height = 20
    ws.row_dimensions[5].height = 20
    ws.row_dimensions[6].height = 18

    # Populate rows starting from row 7
    for ri, row in enumerate(table, 7):
        dept = row['dept']
        dept_name = dept.bed_profile_name or dept.name
        row_no = dept.row_no or ''

        # Map row values
        vals = [
            dept_name,
            row_no,
            row['beds_total'] if row['beds_total'] is not None else '',
            row['beds_renovation'] if row['beds_renovation'] is not None else '',
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
            row['patients_end_rural'] if row['patients_end_rural'] is not None else '',
            row['mothers_with_children'],
            row['free_male'] if row['free_male'] is not None else '',
            row['free_female'] if row['free_female'] is not None else '',
            row['free_total'] if row['free_total'] is not None else '',
        ]

        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.font = Font(name="Arial", size=9)
            cell.border = border
            if ci == 1:
                cell.alignment = left
            else:
                cell.alignment = Alignment(horizontal='center', vertical='center')

            # Highlight computed cols (14: N and 19: S)
            if ci in [14, 19]:
                cell.fill = fill_computed

    # Footer Totals Row
    tot_row = len(table) + 7
    ws.merge_cells(start_row=tot_row, start_column=1, end_row=tot_row, end_column=2)
    tot_label_cell = ws.cell(row=tot_row, column=1, value='Разом')
    tot_label_cell.font = Font(name="Arial", size=9, bold=True)
    tot_label_cell.alignment = center
    tot_label_cell.border = border
    ws.cell(row=tot_row, column=2).border = border

    for ci in range(3, 20):
        cell = ws.cell(row=tot_row, column=ci)
        col_keys = [
            'beds_total', 'beds_renovation', 'patients_start', 'admitted_total', 'admitted_rural',
            'admitted_children', 'transferred_in', 'transferred_out', 'discharged_total',
            'discharged_to_other', 'deaths', 'patients_end', 'patients_end_rural', 'mothers_with_children',
            'free_male', 'free_female', 'free_total'
        ]
        key = col_keys[ci - 3]
        v = totals[key]
        cell.value = v if v is not None else ''
        cell.font = Font(name="Arial", size=9, bold=True)
        cell.border = border
        cell.alignment = Alignment(horizontal='center', vertical='center')
        if ci in [14, 19]:
            cell.fill = fill_computed

    ws.row_dimensions[tot_row].height = 20

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"form016_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.xlsx"
    return Response(
        buf.read(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )

