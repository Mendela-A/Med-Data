from flask import render_template, request, redirect, url_for, Response, flash, abort, send_file
from flask_login import current_user
from datetime import date, timedelta, datetime
import calendar
from io import BytesIO

from app.extensions import db
from models import Department, DailyReport, PrintSettings, log_action
from decorators import role_required
from . import statisty_bp

# Combined department display names for merged dept groups (hardcoded IDs per hospital config)
_COMBINED_DEPT_NAMES = {
    frozenset({4, 20}):     "Хірургічне (доросле + дитяче)",
    frozenset({6, 22}):     "Травматологічне (доросле + дитяче)",
    frozenset({12, 21}):    "Урологічне (доросле + дитяче)",
    frozenset({1, 23, 24}): "Пологовий будинок",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _day_stats_for_dept(dept, report):
    """Return a stat-dict for one department on one day. report may be None."""
    if report:
        return {
            'beds_total':            report.beds_total if report.beds_total is not None else (dept.bed_capacity or 0),
            'patients_start':        report.patients_start        or 0,
            'patients_end':          report.patients_end          or 0,
            'admitted_total':        report.admitted_total        or 0,
            'admitted_rural':        report.admitted_rural        or 0,
            'admitted_children':     report.admitted_children     or 0,
            'admitted_children_rural': report.admitted_children_rural or 0,
            'transferred_in':        report.transferred_in        or 0,
            'transferred_out':       report.transferred_out       or 0,
            'discharged_total':      report.discharged_total      or 0,
            'discharged_to_other':   report.discharged_to_other   or 0,
            'deaths':                report.deaths                or 0,
            'bed_days_rural':        report.patients_end_rural    or 0,
            'bed_days_renovation':   report.beds_renovation       or 0,
            'bed_days_mothers':      report.mothers_with_children or 0,
        }
    return {
        'beds_total': dept.bed_capacity or 0,
        'patients_start': 0, 'patients_end': 0,
        'admitted_total': 0, 'admitted_rural': 0,
        'admitted_children': 0, 'admitted_children_rural': 0,
        'transferred_in': 0, 'transferred_out': 0,
        'discharged_total': 0, 'discharged_to_other': 0,
        'deaths': 0, 'bed_days_rural': 0,
        'bed_days_renovation': 0, 'bed_days_mothers': 0,
    }


def _sum_daily_stats(daily_stats):
    """Aggregate a list of per-day stat dicts into period totals. Returns None if empty."""
    n = len(daily_stats)
    if not n:
        return None
    sum_keys = [
        'admitted_total', 'admitted_rural', 'admitted_children', 'admitted_children_rural',
        'transferred_in', 'transferred_out', 'discharged_total', 'discharged_to_other',
        'deaths', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers',
    ]
    return {
        'beds_total':      daily_stats[-1]['beds_total'],
        'beds_average':    int(round(sum(s['beds_total'] for s in daily_stats) / n)),
        'patients_start':  daily_stats[0]['patients_start'],
        'patients_end':    daily_stats[-1]['patients_end'],
        'bed_days_total':  sum(s['patients_end'] for s in daily_stats),
        **{k: sum(s[k] for s in daily_stats) for k in sum_keys},
    }


def _get_print_settings():
    ps = db.session.get(PrintSettings, 1)
    if ps is None:
        ps = PrintSettings(id=1)
        db.session.add(ps)
        db.session.commit()
    return ps


def _parse_date_range(default_to_year=False):
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
        if default_to_year:
            from_date = date(today.year, 1, 1)
            to_date = date(today.year, 12, 31)
        else:
            from_date = date(today.year, today.month, 1)
    if to_date is None:
        last_day = calendar.monthrange(from_date.year, from_date.month)[1]
        to_date = date(from_date.year, from_date.month, last_day)
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date


def _period_label(from_date, to_date):
    from constants import UKRAINIAN_MONTHS
    last_day = calendar.monthrange(from_date.year, from_date.month)[1]
    if from_date.day == 1 and to_date == date(from_date.year, from_date.month, last_day):
        return f"{UKRAINIAN_MONTHS[from_date.month]} {from_date.year}"
    if from_date == date(from_date.year, 1, 1) and to_date == date(from_date.year, 12, 31):
        return f"{from_date.year} рік"
    return f"{from_date.strftime('%d.%m.%Y')} – {to_date.strftime('%d.%m.%Y')}"


def _aggregate_period(year, start_month, end_month, department_ids=None):
    start_date = date(year, start_month, 1)
    end_date   = date(year, end_month, calendar.monthrange(year, end_month)[1])

    if department_ids:
        depts = Department.query.filter(Department.id.in_(department_ids)).all()
    else:
        depts = Department.query.all()

    dept_ids = [d.id for d in depts if d]
    if not dept_ids:
        return None

    reports = DailyReport.query.filter(
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date,
        DailyReport.department_id.in_(dept_ids),
    ).all()

    days_list = []
    curr = start_date
    while curr <= end_date:
        days_list.append(curr)
        curr += timedelta(days=1)

    reports_by_date_dept = {}
    for r in reports:
        reports_by_date_dept.setdefault(r.report_date, {})[r.department_id] = r

    daily_stats = []
    for d in days_list:
        day_reports = reports_by_date_dept.get(d, {})
        day = {k: 0 for k in ('beds_total', 'patients_start', 'patients_end',
                               'admitted_total', 'admitted_rural', 'admitted_children',
                               'admitted_children_rural', 'transferred_in', 'transferred_out',
                               'discharged_total', 'discharged_to_other', 'deaths',
                               'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers')}
        for dept in depts:
            s = _day_stats_for_dept(dept, day_reports.get(dept.id))
            for k in day:
                day[k] += s[k]
        daily_stats.append(day)

    return _sum_daily_stats(daily_stats)


def _get_form016_data(from_date, to_date, department_ids=None):
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
    if department_ids:
        dr_query = dr_query.filter(DailyReport.department_id.in_(department_ids))
    dr_count = dr_query.count()

    selected_dept = None
    if department_ids:
        if len(department_ids) == 1:
            selected_dept = db.session.get(Department, department_ids[0])
        elif len(department_ids) > 1:
            combined_name = _COMBINED_DEPT_NAMES.get(frozenset(department_ids))
            if combined_name is None:
                depts_in = Department.query.filter(Department.id.in_(department_ids)).all()
                combined_name = " + ".join([d.name for d in depts_in])
            selected_dept = Department(name=combined_name)

    # Let's map months
    MONTHS_UA_NOMINATIVE = {
        1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
        5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
        9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
    }

    _ZERO = {k: 0 for k in [
        'beds_total', 'beds_average', 'patients_start', 'admitted_total',
        'admitted_rural', 'admitted_children', 'transferred_in', 'transferred_out',
        'discharged_total', 'discharged_to_other', 'deaths', 'patients_end',
        'bed_days_total', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers',
    ]}

    def _month_row(m):
        data = _aggregate_period(year, m, m, department_ids)
        row = {'date_str': MONTHS_UA_NOMINATIVE[m], 'is_totals': False}
        row.update(data if data else _ZERO)
        return row

    def _subtotal_row(label, start_m, end_m):
        data = _aggregate_period(year, start_m, end_m, department_ids)
        row = {'date_str': label, 'is_totals': True}
        row.update(data if data else _ZERO)
        return row

    table = []
    selected_month = to_date.month

    # Q1: Jan–Mar
    q1_months = range(1, min(selected_month, 3) + 1)
    for m in q1_months:
        table.append(_month_row(m))
    if selected_month >= 3:
        table.append(_subtotal_row('За I квартал', 1, 3))

    # Q2: Apr–Jun
    if selected_month >= 4:
        q2_months = range(4, min(selected_month, 6) + 1)
        for m in q2_months:
            table.append(_month_row(m))
        if selected_month >= 6:
            table.append(_subtotal_row('За II квартал', 4, 6))
            table.append(_subtotal_row('За півріччя', 1, 6))

    # Q3: Jul–Sep
    if selected_month >= 7:
        q3_months = range(7, min(selected_month, 9) + 1)
        for m in q3_months:
            table.append(_month_row(m))
        if selected_month >= 9:
            table.append(_subtotal_row('За III квартал', 7, 9))

    # Q4: Oct–Dec
    if selected_month >= 10:
        q4_months = range(10, min(selected_month, 12) + 1)
        for m in q4_months:
            table.append(_month_row(m))
        if selected_month >= 12:
            table.append(_subtotal_row('За IV квартал', 10, 12))

    # Annual / period totals
    if selected_month == 12:
        totals_row = _subtotal_row('За рік', 1, 12)
    else:
        totals_row = _subtotal_row(f"Всього за період (січень–{MONTHS_UA_NOMINATIVE[selected_month].lower()})", 1, selected_month)
    table.append(totals_row)

    totals = totals_row

    return table, totals, 'daily_report', dr_count


def _get_form016_departments_data(from_date, to_date):
    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()

    reports = DailyReport.query.filter(
        DailyReport.report_date >= from_date,
        DailyReport.report_date <= to_date,
    ).all()

    reports_by_dept_date = {}
    for r in reports:
        reports_by_dept_date.setdefault(r.department_id, {})[r.report_date] = r

    dr_count = len(reports)

    days_list = []
    curr = from_date
    while curr <= to_date:
        days_list.append(curr)
        curr += timedelta(days=1)

    _ZERO = {k: 0 for k in [
        'beds_total', 'beds_average', 'patients_start', 'admitted_total',
        'admitted_rural', 'admitted_children', 'admitted_children_rural',
        'transferred_in', 'transferred_out', 'discharged_total', 'discharged_to_other',
        'deaths', 'patients_end', 'bed_days_total',
        'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers',
    ]}

    table = []
    grand = {k: 0 for k in _ZERO}

    for dept in depts:
        dept_reports = reports_by_dept_date.get(dept.id, {})
        daily_stats = [_day_stats_for_dept(dept, dept_reports.get(d)) for d in days_list]
        agg = _sum_daily_stats(daily_stats)

        if agg is None:
            row = {'dept_name': dept.name, 'row_no': dept.row_no, 'is_totals': False}
            row.update(_ZERO)
        else:
            row = {'dept_name': dept.name, 'row_no': dept.row_no, 'is_totals': False, **agg}
            for k in ('beds_total', 'beds_average', 'patients_start', 'admitted_total',
                      'admitted_rural', 'admitted_children', 'admitted_children_rural',
                      'transferred_in', 'transferred_out', 'discharged_total',
                      'discharged_to_other', 'deaths', 'patients_end',
                      'bed_days_total', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers'):
                grand[k] += agg.get(k, 0)
        table.append(row)

    totals = {
        'dept_name': 'Разом', 'row_no': '', 'is_totals': True,
        'patients_start': '',  # excluded from totals row per form spec
        **grand,
    }
    table.append(totals)

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
                               'admitted_children_rural',
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
        depts=depts,
    )


# ---- Form 007 monthly view for a single department -------------------------

@statisty_bp.route('/form007/dept/<int:department_id>')
@role_required('admin', 'viewer')
def form007_dept_month(department_id):
    dept = db.get_or_404(Department, department_id)
    from_date, _ = _parse_date_range()
    first_day = date(from_date.year, from_date.month, 1)
    last_day_num = calendar.monthrange(from_date.year, from_date.month)[1]
    last_day = date(from_date.year, from_date.month, last_day_num)

    all_days = [date(first_day.year, first_day.month, d) for d in range(1, last_day_num + 1)]

    reports = {
        r.report_date: r
        for r in DailyReport.query.filter(
            DailyReport.department_id == department_id,
            DailyReport.report_date >= first_day,
            DailyReport.report_date <= last_day,
        ).all()
    }

    rows = [(d, reports.get(d)) for d in all_days]

    flow_keys = ['patients_start', 'admitted_total', 'admitted_rural', 'admitted_children',
                 'admitted_children_rural',
                 'transferred_in', 'transferred_out', 'discharged_total',
                 'discharged_to_other', 'deaths', 'patients_end', 'patients_end_rural',
                 'mothers_with_children']
    totals = {k: sum(getattr(r, k) or 0 for _, r in rows if r) for k in flow_keys}
    last_r = next((reports[d] for d in reversed(all_days) if d in reports), None)
    totals['beds_total']         = last_r.beds_total          if last_r  else None
    totals['beds_renovation']    = last_r.beds_renovation     if last_r  else None
    totals['free_male']          = None
    totals['free_female']        = None

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()

    return render_template(
        'statisty/form007_dept_month.html',
        dept=dept,
        depts=depts,
        rows=rows,
        totals=totals,
        from_date=first_day,
        period_label=_period_label(first_day, last_day),
    )


# ---- Form 007 monthly dept print (PDF) -------------------------------------

@statisty_bp.route('/form007/dept/<int:department_id>/print')
@role_required('admin', 'viewer')
def form007_dept_month_print(department_id):
    dept = db.get_or_404(Department, department_id)
    from_date, _ = _parse_date_range()
    first_day = date(from_date.year, from_date.month, 1)
    last_day_num = calendar.monthrange(from_date.year, from_date.month)[1]
    last_day = date(from_date.year, from_date.month, last_day_num)

    all_days = [date(first_day.year, first_day.month, d) for d in range(1, last_day_num + 1)]
    reports = {
        r.report_date: r
        for r in DailyReport.query.filter(
            DailyReport.department_id == department_id,
            DailyReport.report_date >= first_day,
            DailyReport.report_date <= last_day,
        ).all()
    }
    rows = [(d, reports.get(d)) for d in all_days]

    flow_keys = ['admitted_total', 'admitted_rural', 'admitted_children',
                 'transferred_in', 'transferred_out', 'discharged_total',
                 'discharged_to_other', 'deaths', 'patients_end', 'patients_end_rural',
                 'mothers_with_children', 'admitted_children_rural']
    totals = {k: sum(getattr(r, k) or 0 for _, r in rows if r) for k in flow_keys}
    totals['patients_start'] = sum(getattr(r, 'patients_start') or 0 for _, r in rows if r)
    last_r = next((reports[d] for d in reversed(all_days) if d in reports), None)
    totals['beds_total']         = last_r.beds_total          if last_r  else None
    totals['beds_renovation']    = last_r.beds_renovation     if last_r  else None
    totals['free_male']          = None
    totals['free_female']        = None

    html_string = render_template(
        'print_form007_dept_month.html',
        dept=dept,
        rows=rows,
        totals=totals,
        from_date=first_day,
        period_label=_period_label(first_day, last_day),
        ps=_get_print_settings(),
    )

    try:
        from weasyprint import HTML
    except ImportError:
        flash('WeasyPrint не встановлено.', 'danger')
        return redirect(url_for('statisty.form007_dept_month',
                                department_id=department_id,
                                from_date=from_date.strftime('%Y-%m')))

    pdf = HTML(string=html_string).write_pdf()
    bio = BytesIO(pdf)
    bio.seek(0)
    dept_slug = dept.name.replace(' ', '_')[:30]
    filename = f"forma007_{dept_slug}_{from_date.strftime('%Y-%m')}.pdf"
    return send_file(bio, as_attachment=False,
                     download_name=filename, mimetype='application/pdf')


# ---- Form 007 edit (single day, all departments) ---------------------------

@statisty_bp.route('/form007/<report_date_str>/edit', methods=['GET', 'POST'])
@role_required('admin')
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
            r.admitted_children_rural = _int('admitted_children_rural')
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

        log_action(
            current_user.id,
            'daily_report.update',
            'daily_report',
            None,
            f"date={report_date_str}, depts={', '.join([d.name for d in depts])}"
        )
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
                               'admitted_children_rural',
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
        ps=_get_print_settings(),
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
def _parse_department_ids(department_id_str):
    department_id_str = department_id_str.strip()
    if ',' in department_id_str:
        department_ids = [int(x) for x in department_id_str.split(',') if x.isdigit()]
    elif department_id_str.isdigit():
        department_ids = [int(department_id_str)]
    else:
        department_ids = []
    
    selected_dept = None
    if len(department_ids) == 1:
        selected_dept = db.session.get(Department, department_ids[0])
    elif len(department_ids) > 1:
        combined_name = _COMBINED_DEPT_NAMES.get(frozenset(department_ids))
        if combined_name is None:
            depts_in = Department.query.filter(Department.id.in_(department_ids)).all()
            combined_name = " + ".join([d.name for d in depts_in])
        selected_dept = Department(name=combined_name)

    return department_ids, selected_dept


# ---- Form 016 ---------------------------------------------------------------

@statisty_bp.route('/form016')
@role_required('admin', 'viewer')
def form016():
    from_date, to_date = _parse_date_range(default_to_year=True)

    department_id_str = request.args.get('department_id', '').strip()
    department_ids, selected_dept = _parse_department_ids(department_id_str)

    depts = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()

    table, totals, data_source, dr_count = _get_form016_data(from_date, to_date, department_ids)

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
        department_id_str=department_id_str,
        selected_dept=selected_dept,
    )


# ---- Form 016 PDF print -----------------------------------------------------

@statisty_bp.route('/form016/print')
@role_required('admin', 'viewer')
def form016_print():
    from_date, to_date = _parse_date_range(default_to_year=True)
    department_id_str = request.args.get('department_id', '').strip()
    department_ids, selected_dept = _parse_department_ids(department_id_str)

    table, totals, _, _ = _get_form016_data(from_date, to_date, department_ids)

    html_string = render_template(
        'print_form016.html',
        table=table,
        totals=totals,
        from_date=from_date,
        to_date=to_date,
        period_label=_period_label(from_date, to_date),
        selected_dept=selected_dept,
        ps=_get_print_settings(),
    )

    try:
        from weasyprint import HTML
    except ImportError:
        flash('WeasyPrint не встановлено.', 'danger')
        return redirect(url_for('statisty.form016',
                                from_date=from_date.isoformat(),
                                to_date=to_date.isoformat(),
                                department_id=department_id_str or ''))

    pdf = HTML(string=html_string).write_pdf()
    bio = BytesIO(pdf)
    bio.seek(0)
    dept_slug = f"_{selected_dept.name[:20].replace(' ', '_')}" if selected_dept else ''
    filename = f"forma016{dept_slug}_{from_date.year}.pdf"
    return send_file(bio, as_attachment=False,
                     download_name=filename, mimetype='application/pdf')


# ---- Form 016 Excel export --------------------------------------------------

@statisty_bp.route('/form016/export')
@role_required('admin', 'viewer')
def form016_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    from_date, to_date = _parse_date_range(default_to_year=True)

    department_id_str = request.args.get('department_id', '').strip()
    department_ids, selected_dept = _parse_department_ids(department_id_str)
    table, totals, data_source, dr_count = _get_form016_data(from_date, to_date, department_ids)

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
            row['patients_start'] if (row['patients_start'] is not None and not is_totals_row) else '',
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


# ---- Form 016 by Departments ------------------------------------------------

@statisty_bp.route('/form016_departments')
@role_required('admin', 'viewer')
def form016_departments():
    from_date, to_date = _parse_date_range(default_to_year=True)

    table, totals, data_source, dr_count = _get_form016_departments_data(from_date, to_date)

    return render_template(
        'statisty/form016_departments.html',
        table=table,
        totals=totals,
        from_date=from_date,
        to_date=to_date,
        period_label=_period_label(from_date, to_date),
        data_source=data_source,
        dr_count=dr_count,
    )


# ---- Form 016 by Departments PDF print --------------------------------------

@statisty_bp.route('/form016_departments/print')
@role_required('admin', 'viewer')
def form016_departments_print():
    from_date, to_date = _parse_date_range(default_to_year=True)

    table, totals, _, _ = _get_form016_departments_data(from_date, to_date)

    html_string = render_template(
        'print_form016_departments.html',
        table=table,
        totals=totals,
        from_date=from_date,
        to_date=to_date,
        period_label=_period_label(from_date, to_date),
        ps=_get_print_settings(),
    )

    try:
        from weasyprint import HTML
    except ImportError:
        flash('WeasyPrint не встановлено.', 'danger')
        return redirect(url_for('statisty.form016_departments',
                                from_date=from_date.isoformat(),
                                to_date=to_date.isoformat()))

    pdf = HTML(string=html_string).write_pdf()
    bio = BytesIO(pdf)
    bio.seek(0)
    filename = f"forma016_depts_{from_date.year}.pdf"
    return send_file(bio, as_attachment=False,
                     download_name=filename, mimetype='application/pdf')


# ---- Form 016 by Departments Excel export -----------------------------------

@statisty_bp.route('/form016_departments/export')
@role_required('admin', 'viewer')
def form016_departments_export():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    from_date, to_date = _parse_date_range(default_to_year=True)
    table, totals, data_source, dr_count = _get_form016_departments_data(from_date, to_date)

    wb = Workbook()
    ws = wb.active
    ws.title = "Форма 016 по відділеннях"

    # Common styles
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left = Alignment(horizontal='left', vertical='center')
    right = Alignment(horizontal='right', vertical='center')
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill_hdr = PatternFill("solid", fgColor="D9E1F2")
    fill_computed = PatternFill("solid", fgColor="FFFBEB")

    # Column widths (19 columns: A to S)
    col_widths = [
        32,  # A: Найменування відділень (Col А)
        10,  # B: Номер рядка (Col Б)
        12,  # C: Розгорнуто ліжок на кінець (Col 1)
        12,  # D: Середньомісячних ліжок (Col 2)
        12,  # E: Перебувало на початок (Col 3)
        10,  # F: Поступило - всього (Col 4)
        10,  # G: Поступило - сільських (Col 5)
        10,  # H: Поступило - дітей (Col 6)
        10,  # I: Поступило - дітей сільських (Col 6.1)
        10,  # J: Переведено - із інших (Col 7)
        10,  # K: Переведено - в інші (Col 8)
        10,  # L: Виписано - всього (Col 9)
        10,  # M: Виписано - переведено (Col 10)
        10,  # N: Померло (Col 11)
        12,  # O: Перебувало на кінець (Col 12)
        12,  # P: Ліжко-дні - всього (Col 13)
        12,  # Q: Ліжко-дні - сільськими (Col 14)
        12,  # R: Ліжко-дні - ремонт (Col 15)
        12,  # S: Ліжко-дні - матерями (Col 16)
    ]
    for ci, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    # Row 1 & 2: Ministry of Health Ukraine & Official Form Info
    ws.merge_cells('A1:J1')
    ws['A1'] = "Міністерство охорони здоров'я України / КНП «Калуська ЦРЛ»"
    ws['A1'].font = Font(name="Arial", size=8, italic=True)
    ws['A1'].alignment = left

    ws.merge_cells('K1:S1')
    ws['K1'] = "МЕДИЧНА ДОКУМЕНТАЦІЯ"
    ws['K1'].font = Font(name="Arial", size=8, bold=True)
    ws['K1'].alignment = right

    ws.merge_cells('A2:J2')
    ws['A2'] = "вул. Каракая, 25, м. Калуш, Івано-Франківська обл., 77300"
    ws['A2'].font = Font(name="Arial", size=8, italic=True)
    ws['A2'].alignment = left

    ws.merge_cells('K2:S2')
    ws['K2'] = "Форма № 016/о (модифікована) / Затверджено наказом МОЗ України від 27.12.05 р. № 760"
    ws['K2'].font = Font(name="Arial", size=8, italic=True)
    ws['K2'].alignment = right

    # Period title (A3:S3)
    period_label = _period_label(from_date, to_date)
    ws.merge_cells('A3:S3')
    ws['A3'] = f"ЗВЕДЕНА ВІДОМІСТЬ обліку руху хворих і ліжкового фонду в стаціонарі по відділеннях за період: {period_label}"
    ws['A3'].font = Font(name="Arial", size=11, bold=True)
    ws['A3'].alignment = center

    # Setup headers spanning Rows 4, 5, 6, 7, 8
    for r in range(4, 9):
        for c in range(1, 20):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(name="Arial", size=8, bold=True)
            cell.alignment = center
            cell.fill = fill_hdr
            cell.border = border

    # Row 4 merges and texts
    ws.merge_cells('A4:A7')
    ws['A4'] = "Найменування відділень"

    ws.merge_cells('B4:B7')
    ws['B4'] = "Номер рядка"

    ws.merge_cells('C4:C7')
    ws['C4'] = "Число ліжок у межах кошторису фактично розгорнутих + згорнутих на ремонт на кінець звітного періоду\n(гр. 1)"

    ws.merge_cells('D4:D7')
    ws['D4'] = "Число середньомісячних (річних) ліжок\n(гр. 2)"

    ws.merge_cells('E4:E7')
    ws['E4'] = "Перебувало хворих на початок звітного періоду\n(гр. 3)"

    ws.merge_cells('F4:M4')
    ws['F4'] = "За звітний період"

    ws.merge_cells('N4:N7')
    ws['N4'] = "Померло\n(гр. 11)"

    ws.merge_cells('O4:O7')
    ws['O4'] = "Перебувало хворих на кінець звітного періоду\n(гр. 12)"

    ws.merge_cells('P4:P7')
    ws['P4'] = "Проведено всіма хворими ліжко-днів\n(гр. 13)"

    ws.merge_cells('Q4:Q7')
    ws['Q4'] = "у тому числі сільськими жителями\n(гр. 14)"

    ws.merge_cells('R4:R7')
    ws['R4'] = "Число ліжко-днів закриття\n(гр. 15)"

    ws.merge_cells('S4:S7')
    ws['S4'] = "Крім того, проведено ліжко-днів матерями з хворими дітьми\n(гр. 16)"

    # Row 5 merges
    ws.merge_cells('F5:I5')
    ws['F5'] = "поступило хворих"

    ws.merge_cells('J5:K5')
    ws['J5'] = "переведено хворих всередині лікарні"

    ws.merge_cells('L5:M5')
    ws['L5'] = "виписано хворих"

    # Row 6 merges
    ws.merge_cells('F6:F7')
    ws['F6'] = "всього\n(гр. 4)"

    ws.merge_cells('G6:I6')
    ws['G6'] = "із них"

    ws.merge_cells('J6:J7')
    ws['J6'] = "із інших відділень\n(гр. 7)"

    ws.merge_cells('K6:K7')
    ws['K6'] = "в інші відділення\n(гр. 8)"

    ws.merge_cells('L6:L7')
    ws['L6'] = "всього\n(гр. 9)"

    ws.merge_cells('M6:M7')
    ws['M6'] = "переведені в інші стаціонари\n(гр. 10)"

    # Row 7 texts
    ws['G7'] = "сільських жителів\n(гр. 5)"
    ws['H7'] = "дітей до 17 р. вкл.\n(гр. 6)"
    ws['I7'] = "дітей, з них\nсільських жителів\n(гр. 6.1)"

    # Row 8: Column letters/numbers row
    cols_letters = ["А", "Б", "1", "2", "3", "4", "5", "6", "6.1", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"]
    for ci, letter in enumerate(cols_letters, 1):
        cell = ws.cell(row=8, column=ci, value=letter)
        cell.font = Font(name="Arial", size=7, italic=True)

    # Insert Data rows (starting at Row 9)
    current_row = 9
    for row in table:
        is_tot = row.get('is_totals', False)
        
        ws.cell(row=current_row, column=1, value=row.get('dept_name')).font = Font(name="Arial", size=9, bold=is_tot)
        ws.cell(row=current_row, column=1).alignment = left if is_tot else center
        ws.cell(row=current_row, column=1).border = border

        # Column Б (Row Number)
        val_b = row.get('row_no') if row.get('row_no') is not None else ''
        ws.cell(row=current_row, column=2, value=val_b).font = Font(name="Arial", size=9, bold=is_tot)
        ws.cell(row=current_row, column=2).alignment = center
        ws.cell(row=current_row, column=2).border = border

        # Col 1 - 16 values (+ 6.1)
        cols_keys = [
            'beds_total', 'beds_average', 'patients_start', 'admitted_total',
            'admitted_rural', 'admitted_children', 'admitted_children_rural',
            'transferred_in', 'transferred_out',
            'discharged_total', 'discharged_to_other', 'deaths', 'patients_end',
            'bed_days_total', 'bed_days_rural', 'bed_days_renovation', 'bed_days_mothers'
        ]

        for ci, key in enumerate(cols_keys, 3):
            val = row.get(key)
            if val == 0 or val == '' or val is None:
                val_disp = ''
            else:
                val_disp = val

            cell = ws.cell(row=current_row, column=ci, value=val_disp)
            cell.font = Font(name="Arial", size=9, bold=is_tot)
            cell.alignment = center
            cell.border = border
            
            # Highlight computed average & bed days
            if not is_tot and key in ('beds_average', 'bed_days_total'):
                cell.fill = fill_computed

            if is_tot:
                cell.font = Font(name="Arial", size=9, bold=True)
                cell.fill = fill_hdr

        current_row += 1

    # Apply row heights
    for ri in range(4, current_row):
        ws.row_dimensions[ri].height = 20

    # Official Signature Block at the bottom
    sig_row = current_row + 2
    ws.cell(row=sig_row, column=1, value="Заступник генерального директора").font = Font(name="Arial", size=9, bold=True)
    ws.cell(row=sig_row+1, column=1, value="КНП «Калуська ЦРЛ» з адміністративної діяльності").font = Font(name="Arial", size=9)
    ws.cell(row=sig_row+2, column=1, value="____________________ Л. Луців").font = Font(name="Arial", size=9)
    
    ws.cell(row=sig_row+2, column=12, value="____________________ Валерій ПАЛЯНИЦЯ").font = Font(name="Arial", size=9, bold=True)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"form016_depts_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.xlsx"
    return Response(
        buf.read(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


# ---- Print settings ---------------------------------------------------------

@statisty_bp.route('/print-settings', methods=['GET', 'POST'])
@role_required('admin')
def print_settings_edit():
    ps = _get_print_settings()
    if request.method == 'POST':
        ps.ministry       = request.form.get('ministry', '').strip()
        ps.org_name       = request.form.get('org_name', '').strip()
        ps.org_short_name = request.form.get('org_short_name', '').strip()
        ps.org_address    = request.form.get('org_address', '').strip()
        ps.signer1_title  = request.form.get('signer1_title', '').strip()
        ps.signer1_name   = request.form.get('signer1_name', '').strip()
        ps.signer2_label  = request.form.get('signer2_label', '').strip()
        ps.signer2_name   = request.form.get('signer2_name', '').strip()
        ps.form007_title    = request.form.get('form007_title', '').strip()
        ps.form007_subtitle = request.form.get('form007_subtitle', '').strip()
        ps.form016_title    = request.form.get('form016_title', '').strip()
        ps.form016_subtitle = request.form.get('form016_subtitle', '').strip()
        ps.form007_dept_title = request.form.get('form007_dept_title', '').strip()
        ps.form007_form_no  = request.form.get('form007_form_no', '').strip()
        ps.form007_decree   = request.form.get('form007_decree',  '').strip()
        ps.form016_form_no  = request.form.get('form016_form_no', '').strip()
        ps.form016_decree   = request.form.get('form016_decree',  '').strip()
        log_action(
            current_user.id,
            'print_settings.update',
            'print_settings',
            ps.id,
            f"org_name={ps.org_name}, signer1={ps.signer1_name}, signer2={ps.signer2_name}"
        )
        db.session.commit()
        flash('Налаштування друку збережено.', 'success')
        return redirect(url_for('statisty.print_settings_edit'))
    return render_template('statisty/print_settings.html', ps=ps)

