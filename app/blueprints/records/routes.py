# app/blueprints/records/routes.py
"""
Records (Dashboard) routes - main application routes for medical records
"""

from flask import render_template, redirect, url_for, flash, request, current_app, send_file, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone, timedelta
from io import BytesIO
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from app.extensions import db, cache
from models import Record, User, Department, log_action
from decorators import role_required
from utils import parse_date, parse_integer, parse_numeric
from . import records_bp


# Cached helper functions for dropdown values
@cache.memoize(timeout=900)
def get_distinct_statuses():
    """Get distinct discharge statuses from database"""
    return [s[0] for s in db.session.query(Record.discharge_status).distinct()
            .filter(Record.discharge_status != None)
            .order_by(Record.discharge_status).all()]


@cache.memoize(timeout=900)
def get_distinct_physicians():
    """Get distinct treating physicians from database"""
    return [p[0] for p in db.session.query(Record.treating_physician).distinct()
            .filter(Record.treating_physician != None)
            .order_by(Record.treating_physician).all()]


@cache.memoize(timeout=900)
def get_distinct_departments():
    """Get distinct discharge departments from database"""
    return [d[0] for d in db.session.query(Record.discharge_department).distinct()
            .filter(Record.discharge_department != None)
            .order_by(Record.discharge_department).all()]


def clear_dropdown_cache():
    """Clear all dropdown caches - call after adding/editing records"""
    cache.delete_memoized(get_distinct_statuses)
    cache.delete_memoized(get_distinct_physicians)
    cache.delete_memoized(get_distinct_departments)


# Routes
@records_bp.route('/')
@login_required
def index():
    # Redirect viewer to statistics page ONLY if no filters applied
    if current_user.role == 'viewer' and not request.args:
        return redirect(url_for('admin.admin_statistics'))

    from datetime import datetime, timezone, timedelta
    # Use Kyiv timezone (UTC+2, or UTC+3 during DST) for correct month detection
    # Simple approach: use UTC+2 as base (covers most of the year)
    kyiv_tz = timezone(timedelta(hours=2))
    now = datetime.now(kyiv_tz)

    # support a toggle to show all months
    show_all = request.args.get('all_months', '').lower() in ('1', 'true', 'yes')

    # allow explicit month/year selection via query params or HTML5 month input (YYYY-MM format)
    month_input = request.args.get('month_filter', '').strip()
    selected_month = None
    selected_year = None

    try:
        if month_input:
            # Parse HTML5 month input format: YYYY-MM
            parts = month_input.split('-')
            if len(parts) == 2:
                selected_year = int(parts[0])
                selected_month = int(parts[1])
                if 1 <= selected_month <= 12:
                    start = datetime(selected_year, selected_month, 1)
                    if selected_month == 12:
                        end = datetime(selected_year + 1, 1, 1)
                    else:
                        end = datetime(selected_year, selected_month + 1, 1)
                else:
                    raise ValueError()
            else:
                raise ValueError()
        else:
            # Default to current month
            start = datetime(now.year, now.month, 1)
            selected_year = now.year
            selected_month = now.month
            if now.month == 12:
                end = datetime(now.year + 1, 1, 1)
            else:
                end = datetime(now.year, now.month + 1, 1)
    except Exception:
        # fallback to current month
        start = datetime(now.year, now.month, 1)
        selected_year = now.year
        selected_month = now.month
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1)
        else:
            end = datetime(now.year, now.month + 1, 1)

    # base query (by default for current month, unless show_all)
    q = Record.query.options(joinedload(Record.creator), joinedload(Record.updater))
    if not show_all:
        # show records discharged in the current month by date_of_discharge
        q = q.filter(
            Record.date_of_discharge != None,
            Record.date_of_discharge >= start.date(),
            Record.date_of_discharge < end.date(),
        )

    # --- filtering from query params ---
    selected_status = request.args.get('discharge_status', '').strip()
    selected_physician = request.args.get('treating_physician', '').strip()
    selected_department = request.args.get('discharge_department', '').strip()
    history_q = request.args.get('history', '').strip()
    full_name_q = request.args.get('full_name', '').strip()
    has_death_date = request.args.get('has_death_date', '').lower() in ('1', 'true', 'yes')

    conditions = []
    if selected_status:
        conditions.append(Record.discharge_status == selected_status)
    if selected_physician:
        conditions.append(Record.treating_physician == selected_physician)
    if selected_department:
        conditions.append(Record.discharge_department == selected_department)
    if history_q:
        conditions.append(Record.history.contains(history_q))
    if full_name_q:
        conditions.append(Record.full_name.ilike(f'%{full_name_q}%'))
    if has_death_date:
        conditions.append(Record.date_of_death != None)
    if conditions:
        q = q.filter(*conditions)

    # values for dropdowns (cached)
    statuses = get_distinct_statuses()
    physicians = get_distinct_physicians()
    departments = get_distinct_departments()

    # Sorting
    sort_by = request.args.get('sort_by', 'date_of_discharge')
    sort_order = request.args.get('sort_order', 'desc')

    valid_columns = {
        'id': Record.id,
        'date_of_discharge': Record.date_of_discharge,
        'full_name': Record.full_name,
        'discharge_department': Record.discharge_department,
        'treating_physician': Record.treating_physician,
        'history': Record.history,
        'k_days': Record.k_days,
        'discharge_status': Record.discharge_status,
        'date_of_death': Record.date_of_death,
        'created_at': Record.created_at,
        'updated_at': Record.updated_at,
    }

    if sort_by in valid_columns:
        col = valid_columns[sort_by]
        if sort_order == 'asc':
            # For string columns, use case-insensitive sorting
            if sort_by in ('full_name', 'discharge_department', 'treating_physician', 'history', 'discharge_status'):
                q = q.order_by(func.lower(col).asc())
            else:
                q = q.order_by(col.asc())
        else:
            if sort_by in ('full_name', 'discharge_department', 'treating_physician', 'history', 'discharge_status'):
                q = q.order_by(func.lower(col).desc())
            else:
                q = q.order_by(col.desc())

    # Calculate statistics counts BEFORE pagination
    # Total count
    count = q.count()

    # Count deceased (priority: any record with date_of_death)
    count_deceased = q.filter(Record.date_of_death != None).count()

    # Other counts: EXCLUDE records with date_of_death
    q_alive = q.filter(Record.date_of_death == None)
    count_discharged = q_alive.filter(Record.discharge_status == 'Виписаний').count()
    count_processing = q_alive.filter(Record.discharge_status == 'Опрацьовується').count()
    count_violations = q_alive.filter(Record.discharge_status == 'Порушені вимоги').count()

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    per_page = min(per_page, 200)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    records = pagination.items

    # user mapping for created_by / updated_by
    user_map = {u.id: u.username for u in User.query.all()}

    # Format month_filter_value for HTML5 month input (YYYY-MM)
    month_filter_value = f"{selected_year:04d}-{selected_month:02d}" if selected_year and selected_month else ""

    return render_template('dashboard.html',
                          records=records,
                          pagination=pagination,
                          statuses=statuses,
                          physicians=physicians,
                          departments=departments,
                          selected_status=selected_status,
                          selected_physician=selected_physician,
                          selected_department=selected_department,
                          history_q=history_q,
                          full_name_q=full_name_q,
                          has_death_date=has_death_date,
                          show_all=show_all,
                          selected_month=selected_month,
                          selected_year=selected_year,
                          month_filter_value=month_filter_value,
                          sort_by=sort_by,
                          sort_order=sort_order,
                          user_map=user_map,
                          count=count,
                          count_discharged=count_discharged,
                          count_processing=count_processing,
                          count_violations=count_violations,
                          count_deceased=count_deceased,
                          active_filters_count=(1 if selected_status else 0) + (1 if selected_physician else 0) + (1 if selected_department else 0) + (1 if history_q else 0) + (1 if full_name_q else 0))


@records_bp.route('/export', methods=['POST'])
@role_required('editor', 'viewer')
def export():
    """Export records to Excel based on form data (month or date range)"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from datetime import datetime

    export_mode = request.form.get('export_mode', 'month').strip()

    if export_mode == 'range':
        # date range mode
        from_str = request.form.get('from_date', '').strip()
        to_str = request.form.get('to_date', '').strip()
        if not from_str or not to_str:
            flash('Будь ласка, вкажіть обидві дати для експорту', 'warning')
            return redirect(url_for('records.index'))
        try:
            from_d = datetime.strptime(from_str, '%Y-%m-%d').date()
            to_d = datetime.strptime(to_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Невірний формат дати', 'warning')
            return redirect(url_for('records.index'))
        if from_d > to_d:
            flash('Дата "з" не може бути пізніше дати "по"', 'warning')
            return redirect(url_for('records.index'))
        # query
        conditions = [
            Record.date_of_discharge != None,
            Record.date_of_discharge >= from_d,
            Record.date_of_discharge <= to_d,
        ]
    else:
        # month mode (default)
        month_input = request.form.get('month_filter', '').strip()
        if not month_input:
            flash('Будь ласка, вкажіть місяць для експорту', 'warning')
            return redirect(url_for('records.index'))
        try:
            parts = month_input.split('-')
            if len(parts) != 2:
                raise ValueError()
            year = int(parts[0])
            month = int(parts[1])
            if not (1 <= month <= 12):
                raise ValueError()
            from_d = datetime(year, month, 1).date()
            if month == 12:
                to_d = datetime(year + 1, 1, 1).date()
            else:
                to_d = datetime(year, month + 1, 1).date()
            # adjust to_d so it's inclusive (last day of month)
            to_d = to_d - timedelta(days=1)
            conditions = [
                Record.date_of_discharge != None,
                Record.date_of_discharge >= from_d,
                Record.date_of_discharge <= to_d,
            ]
        except ValueError:
            flash('Невірний формат місяця (очікується YYYY-MM)', 'warning')
            return redirect(url_for('records.index'))

    # Optional filters
    discharge_status = request.form.get('discharge_status', '').strip()
    treating_physician = request.form.get('treating_physician', '').strip()
    discharge_department = request.form.get('discharge_department', '').strip()
    history_q = request.form.get('history', '').strip()
    full_name_q = request.form.get('full_name', '').strip()

    if discharge_status:
        conditions.append(Record.discharge_status == discharge_status)
    if treating_physician:
        conditions.append(Record.treating_physician == treating_physician)
    if discharge_department:
        conditions.append(Record.discharge_department == discharge_department)
    if history_q:
        conditions.append(Record.history.contains(history_q))
    if full_name_q:
        conditions.append(Record.full_name.contains(full_name_q))

    q = Record.query.filter(*conditions)
    records = q.order_by(Record.date_of_discharge.desc()).all()

    if not records:
        flash('Записів не знайдено для експорту', 'warning')
        return redirect(url_for('records.index'))

    # Determine access level
    use_write_only = current_user.role == 'viewer'

    # user mapping for creator/updater names
    user_map = {u.id: u.username for u in User.query.all()}

    wb = Workbook()
    ws = wb.active
    ws.title = 'Записи'

    # Headers
    if use_write_only:
        headers = ['ID', 'Дата виписки', 'ПІБ', 'Відділення', 'Лікар', 'Історія хвороби', 'К днів', 'Статус виписки']
    else:
        headers = ['ID', 'Дата виписки', 'ПІБ', 'Відділення', 'Лікар', 'Історія хвороби', 'К днів', 'Статус виписки', 'Дата смерті', 'Коментар', 'Створено', 'Оновлено', 'Автор', 'Редактор']

    ws.append(headers)

    # Style header row
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Data rows
    for r in records:
        if use_write_only:
            row = [
                r.id,
                r.date_of_discharge.strftime('%d.%m.%Y') if r.date_of_discharge else '',
                r.full_name,
                r.discharge_department or '',
                r.treating_physician,
                r.history,
                r.k_days,
                r.discharge_status or ''
            ]
        else:
            row = [
                r.id,
                r.date_of_discharge.strftime('%d.%m.%Y') if r.date_of_discharge else '',
                r.full_name,
                r.discharge_department or '',
                r.treating_physician,
                r.history,
                r.k_days,
                r.discharge_status or '',
                r.date_of_death.strftime('%d.%m.%Y') if r.date_of_death else '',
                r.comment or '',
                r.created_at.strftime('%d.%m.%Y %H:%M') if r.created_at else '',
                r.updated_at.strftime('%d.%m.%Y %H:%M') if r.updated_at else '',
                user_map.get(r.created_by, ''),
                user_map.get(r.updated_by, '')
            ]
        ws.append(row)

    # Auto-size columns
    for i, col in enumerate(ws.columns, 1):
        max_length = 0
        column = get_column_letter(i)
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column].width = adjusted_width

    # Save to BytesIO
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    # Generate filename
    if export_mode == 'range':
        filename = f"vipiski_export_{from_d.strftime('%d-%m-%Y')}_{to_d.strftime('%d-%m-%Y')}.xlsx"
        log_details = f'from={from_d} to={to_d} status={discharge_status} count={len(records)}'
    else:
        filename = f"vipiski_export_{from_d.strftime('%m-%Y')}.xlsx"
        log_details = f'month={from_d.strftime("%m-%Y")} status={discharge_status} count={len(records)}'

    # Audit log
    try:
        log_action(current_user.id, 'records.export', 'export', None, log_details)
    except Exception:
        current_app.logger.exception('Failed to write audit log for export')
    current_app.logger.info(f'Export by {getattr(current_user, "username", "unknown")}: {log_details} write_only={use_write_only}')

    return send_file(bio, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@records_bp.route('/records/print', methods=['POST'])
@role_required('editor', 'viewer')
def print_records():
    """Generate PDF print for records with filters"""
    from datetime import datetime
    from io import BytesIO

    try:
        from_str = request.form.get('from_date', '').strip()
        to_str = request.form.get('to_date', '').strip()
        if not from_str or not to_str:
            flash('Будь ласка, вкажіть обидві дати для друку', 'warning')
            return redirect(url_for('records.index'))
        from_d = datetime.strptime(from_str, '%Y-%m-%d').date()
        to_d = datetime.strptime(to_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Невірний формат дати', 'warning')
        return redirect(url_for('records.index'))

    if from_d > to_d:
        flash('Дата "з" не може бути пізніше дати "по"', 'warning')
        return redirect(url_for('records.index'))

    # Get optional filters
    discharge_status = request.form.get('discharge_status', '').strip()
    treating_physician = request.form.get('treating_physician', '').strip()
    discharge_department = request.form.get('discharge_department', '').strip()
    history_q = request.form.get('history', '').strip()
    full_name_q = request.form.get('full_name', '').strip()

    # Build query with filters
    conditions = [
        Record.date_of_discharge != None,
        Record.date_of_discharge >= from_d,
        Record.date_of_discharge <= to_d,
    ]
    if discharge_status:
        conditions.append(Record.discharge_status == discharge_status)
    if treating_physician:
        conditions.append(Record.treating_physician == treating_physician)
    if discharge_department:
        conditions.append(Record.discharge_department == discharge_department)
    if history_q:
        conditions.append(Record.history.contains(history_q))
    if full_name_q:
        conditions.append(Record.full_name.contains(full_name_q))

    q = Record.query.filter(*conditions)
    records = q.order_by(Record.date_of_discharge.desc()).all()

    if not records:
        flash('Записів не знайдено для друку', 'warning')
        return redirect(url_for('records.index'))

    # Get user mapping
    user_map = {u.id: u.username for u in User.query.all()}

    # Render HTML template for print
    html_string = render_template('print_records.html',
                                 records=records,
                                 from_date=from_d,
                                 to_date=to_d,
                                 discharge_status=discharge_status,
                                 treating_physician=treating_physician,
                                 discharge_department=discharge_department,
                                 user_map=user_map,
                                 generated_by=current_user.username,
                                 generated_at=datetime.now())

    # Generate PDF
    try:
        from weasyprint import HTML, CSS
    except ImportError:
        flash('Для друку потрібен пакет WeasyPrint', 'danger')
        return redirect(url_for('records.index'))

    pdf = HTML(string=html_string).write_pdf()

    # Create BytesIO object
    bio = BytesIO(pdf)
    bio.seek(0)

    # Log action
    try:
        log_details = f'from={from_d} to={to_d} status={discharge_status} count={len(records)}'
        log_action(current_user.id, 'records.print', 'print', None, log_details)
    except Exception:
        current_app.logger.exception('Failed to write audit log for records.print')

    filename = f"vipiski_print_{datetime.now().strftime('%d-%m-%Y')}.pdf"
    return send_file(bio, as_attachment=True, download_name=filename, mimetype='application/pdf')


@records_bp.route('/records/add', methods=['GET', 'POST'])
@role_required('operator')
def add_record():

    if request.method == 'POST':
        date_str = request.form.get('date_of_discharge', '').strip()
        full_name = request.form.get('full_name', '').strip()
        discharge_department = request.form.get('discharge_department', '').strip()
        treating_physician = request.form.get('treating_physician', '').strip()
        history = request.form.get('history', '').strip()
        k_days = request.form.get('k_days', '').strip()
        date_of_death_str = request.form.get('date_of_death', '').strip()

        # date_of_death (if provided) will indicate death; validate format if present
        # discharge_department is optional (may not exist yet); require other main fields
        if not all([date_str, full_name, treating_physician, history, k_days]):
            flash('Будь ласка, заповніть усі обов\'язкові поля (виключаючи відділення)', 'warning')
            return redirect(url_for('records.add_record'))

        # validate date format: accept DD.MM.YYYY or YYYY-MM-DD (HTML date input)
        from datetime import datetime
        date_of_discharge = parse_date(date_str)
        if date_of_discharge is None:
            flash('Дата виписки повинна бути у форматі ДД.ММ.РРРР або РРРР-ММ-ДД', 'warning')
            return redirect(url_for('records.add_record'))

        # validate k_days integer
        k_days_int = parse_integer(k_days)
        if k_days_int is None:
            flash('"К днів" повинно бути цілим числом', 'warning')
            return redirect(url_for('records.add_record'))

        # date_of_death handling: if given, validate format
        date_of_death = None
        if date_of_death_str:
            date_of_death = parse_date(date_of_death_str)
            if date_of_death is None:
                flash('Дата смерті повинна бути у форматі ДД.ММ.РРРР або РРРР-ММ-ДД', 'warning')
                return redirect(url_for('records.add_record'))

            # Logical validation: death date should not be before discharge date
            if date_of_death < date_of_discharge:
                flash('Дата смерті не може бути раніше дати виписки', 'warning')
                return redirect(url_for('records.add_record'))

        # Create new record with status "Опрацьовується"
        r = Record(
            date_of_discharge=date_of_discharge,
            full_name=full_name,
            discharge_department=discharge_department or None,
            treating_physician=treating_physician,
            history=history,
            k_days=k_days_int,
            discharge_status='Опрацьовується',
            date_of_death=date_of_death,
            created_by=current_user.id,
            updated_by=current_user.id
        )
        db.session.add(r)
        db.session.commit()
        # Clear dropdown cache so newly added values appear in dropdowns
        clear_dropdown_cache()
        try:
            log_action(current_user.id, 'record.create', 'record', r.id, f'full_name={r.full_name}')
        except Exception:
            current_app.logger.exception('Failed to write audit log for record.create')
        current_app.logger.info(f'Record created: {r.id} by {current_user.username}')
        flash(f'Запис "{r.full_name}" успішно додано', 'success')
        # preserve filters from form (if any)
        params = {}
        for k in ('discharge_status', 'treating_physician', 'history'):
            v = request.form.get(f'filter_{k}', '').strip()
            if v:
                params[k] = v
        if request.form.get('filter_has_death_date', '').strip():
            params['has_death_date'] = '1'
        return redirect(url_for('records.index', **params))

    # GET: pass through any filters so add form can include hidden fields and departments
    departments = Department.query.order_by(Department.name).all()
    # Get distinct physicians for autocomplete (cached)
    physicians = get_distinct_physicians()
    return render_template('add_record.html', selected_status=request.args.get('discharge_status', ''), selected_physician=request.args.get('treating_physician', ''), history_q=request.args.get('history', ''), departments=departments, selected_department=request.args.get('discharge_department', ''), physicians=physicians)


@records_bp.route('/api/records/add', methods=['POST'])
@role_required('operator')
def api_add_record():
    """AJAX endpoint for adding records with support for 'save and add another'"""
    from datetime import datetime

    current_app.logger.info(f'API add_record called by {current_user.username}')
    current_app.logger.debug(f'Form data: {dict(request.form)}')

    date_str = request.form.get('date_of_discharge', '').strip()
    full_name = request.form.get('full_name', '').strip()
    discharge_department = request.form.get('discharge_department', '').strip()
    treating_physician = request.form.get('treating_physician', '').strip()
    history = request.form.get('history', '').strip()
    k_days = request.form.get('k_days', '').strip()
    date_of_death_str = request.form.get('date_of_death', '').strip()
    comment = request.form.get('comment', '').strip()

    # Validate required fields
    if not all([date_str, full_name, treating_physician, history, k_days]):
        return jsonify({'success': False, 'error': 'Будь ласка, заповніть усі обов\'язкові поля'}), 400

    # Parse date_of_discharge
    date_of_discharge = parse_date(date_str)
    if date_of_discharge is None:
        return jsonify({'success': False, 'error': 'Невірний формат дати виписки'}), 400

    # Validate k_days
    k_days_int = parse_integer(k_days)
    if k_days_int is None:
        return jsonify({'success': False, 'error': '"К днів" повинно бути цілим числом'}), 400

    # Parse date_of_death if provided
    date_of_death = None
    if date_of_death_str:
        date_of_death = parse_date(date_of_death_str)
        if date_of_death is None:
            return jsonify({'success': False, 'error': 'Невірний формат дати смерті'}), 400

        if date_of_death < date_of_discharge:
            return jsonify({'success': False, 'error': 'Дата смерті не може бути раніше дати виписки'}), 400

    # Create record with status "Опрацьовується"
    r = Record(
        date_of_discharge=date_of_discharge,
        full_name=full_name,
        discharge_department=discharge_department or None,
        treating_physician=treating_physician,
        history=history,
        k_days=k_days_int,
        discharge_status='Опрацьовується',
        date_of_death=date_of_death,
        comment=comment or None,
        created_by=current_user.id,
        updated_by=current_user.id
    )

    try:
        db.session.add(r)
        db.session.commit()

        # Clear dropdown cache
        clear_dropdown_cache()

        # Audit log
        try:
            log_action(current_user.id, 'record.create', 'record', r.id, f'full_name={r.full_name}')
        except Exception:
            current_app.logger.exception('Failed to write audit log for record.create')

        current_app.logger.info(f'Record created via AJAX: {r.id} by {current_user.username}')

        return jsonify({
            'success': True,
            'record_id': r.id,
            'full_name': r.full_name,
            'message': f'Запис "{r.full_name}" успішно додано'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to create record via AJAX')
        return jsonify({'success': False, 'error': 'Помилка при збереженні запису'}), 500


@records_bp.route('/api/records/<int:record_id>/edit', methods=['POST'])
@role_required('editor')
def api_edit_record(record_id):
    """AJAX endpoint for editing records"""
    from datetime import datetime

    current_app.logger.info(f'API edit_record called by {current_user.username} for record {record_id}')
    current_app.logger.debug(f'Form data: {dict(request.form)}')

    r = Record.query.get_or_404(record_id)

    date_str = request.form.get('date_of_discharge', '').strip()
    full_name = request.form.get('full_name', '').strip()
    discharge_department = request.form.get('discharge_department', '').strip()
    treating_physician = request.form.get('treating_physician', '').strip()
    history = request.form.get('history', '').strip()
    k_days = request.form.get('k_days', '').strip()
    discharge_status = request.form.get('discharge_status', '').strip()
    date_of_death_str = request.form.get('date_of_death', '').strip()
    comment = request.form.get('comment', '').strip()

    # Validate required fields
    if not all([date_str, full_name, discharge_department, treating_physician, history, k_days, discharge_status]):
        return jsonify({'success': False, 'error': 'Будь ласка, заповніть усі обов\'язкові поля'}), 400

    # Parse date_of_discharge
    date_of_discharge = parse_date(date_str)
    if date_of_discharge is None:
        return jsonify({'success': False, 'error': 'Невірний формат дати виписки'}), 400

    # Validate k_days
    k_days_int = parse_integer(k_days)
    if k_days_int is None:
        return jsonify({'success': False, 'error': '"К днів" повинно бути цілим числом'}), 400

    # Parse date_of_death if provided
    date_of_death = None
    if date_of_death_str:
        date_of_death = parse_date(date_of_death_str)
        if date_of_death is None:
            return jsonify({'success': False, 'error': 'Невірний формат дати смерті'}), 400

        if date_of_death < date_of_discharge:
            return jsonify({'success': False, 'error': 'Дата смерті не може бути раніше дати виписки'}), 400

    # Apply changes
    r.date_of_discharge = date_of_discharge
    r.full_name = full_name
    r.discharge_department = discharge_department
    r.treating_physician = treating_physician
    r.history = history
    r.k_days = k_days_int
    r.discharge_status = discharge_status
    r.date_of_death = date_of_death
    r.comment = comment or None
    r.updated_by = current_user.id
    r.updated_at = datetime.utcnow()

    try:
        db.session.commit()

        # Clear dropdown cache
        clear_dropdown_cache()

        # Audit log
        try:
            log_action(current_user.id, 'record.update', 'record', r.id, f'full_name={r.full_name}')
        except Exception:
            current_app.logger.exception('Failed to write audit log for record.update')

        current_app.logger.info(f'Record updated via AJAX: {r.id} by {current_user.username}')

        return jsonify({
            'success': True,
            'record_id': r.id,
            'full_name': r.full_name,
            'message': f'Запис "{r.full_name}" успішно оновлено'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Failed to update record via AJAX')
        return jsonify({'success': False, 'error': 'Помилка при оновленні запису'}), 500


@records_bp.route('/records/<int:record_id>/edit', methods=['GET', 'POST'])
@role_required('editor')
def edit_record(record_id):

    r = Record.query.get_or_404(record_id)

    if request.method == 'POST':
        # gather form fields
        date_str = request.form.get('date_of_discharge', '').strip()
        full_name = request.form.get('full_name', '').strip()
        discharge_department = request.form.get('discharge_department', '').strip()
        treating_physician = request.form.get('treating_physician', '').strip()
        history = request.form.get('history', '').strip()
        k_days = request.form.get('k_days', '').strip()
        discharge_status = request.form.get('discharge_status', '').strip()
        date_of_death_str = request.form.get('date_of_death', '').strip()
        comment = request.form.get('comment', '').strip()

        # validate presence of main fields (status is optional; only required when it is 'Помер')
        if not all([date_str, full_name, discharge_department, treating_physician, history, k_days, discharge_status]):
            flash('Будь ласка, заповніть усі обов\'язкові поля', 'warning')
            return redirect(url_for('records.edit_record', record_id=record_id))

        from datetime import datetime
        date_of_discharge = parse_date(date_str)
        if date_of_discharge is None:
            flash('Дата виписки повинна бути у форматі ДД.ММ.РРРР або РРРР-ММ-ДД', 'warning')
            return redirect(url_for('records.edit_record', record_id=record_id))

        k_days_int = parse_integer(k_days)
        if k_days_int is None:
            flash('"К днів" повинно бути цілим числом', 'warning')
            return redirect(url_for('records.edit_record', record_id=record_id))

        # date_of_death handling
        date_of_death = None

        if date_of_death_str:
            date_of_death = parse_date(date_of_death_str)
            if date_of_death is None:
                flash('Дата смерті повинна бути у форматі ДД.ММ.РРРР або РРРР-ММ-ДД', 'warning')
                return redirect(url_for('records.edit_record', record_id=record_id))

            if date_of_death < date_of_discharge:
                flash('Дата смерті не може бути раніше дати виписки', 'warning')
                return redirect(url_for('records.edit_record', record_id=record_id))

        # apply changes
        r.date_of_discharge = date_of_discharge
        r.full_name = full_name
        r.discharge_department = discharge_department
        r.treating_physician = treating_physician
        r.history = history
        r.k_days = k_days_int
        r.discharge_status = discharge_status
        r.date_of_death = date_of_death
        r.comment = comment
        r.updated_by = current_user.id
        r.updated_at = datetime.utcnow()

        db.session.commit()
        # Clear dropdown cache after editing record
        clear_dropdown_cache()
        try:
            log_action(current_user.id, 'record.update', 'record', r.id, f'full_name={r.full_name}')
        except Exception:
            current_app.logger.exception('Failed to write audit log for record.update')
        current_app.logger.info(f'Record updated: {r.id} by {current_user.username}')
        flash(f'Запис #{r.id} ({r.full_name}) успішно оновлено', 'success')
        params = {}
        for k in ('discharge_status', 'treating_physician', 'history'):
            v = request.form.get(f'filter_{k}', '').strip()
            if v:
                params[k] = v
        if request.form.get('filter_has_death_date', '').strip():
            params['has_death_date'] = '1'
        # Add anchor to scroll to edited record
        return redirect(url_for('records.index', **params, _anchor=f'record-{r.id}'))

    # GET -> render form with record data (pass filters through if present) and departments
    departments = Department.query.order_by(Department.name).all()
    # Get distinct physicians for autocomplete (cached)
    physicians = get_distinct_physicians()
    return render_template('edit_record.html', r=r, selected_status=request.args.get('discharge_status', ''), selected_physician=request.args.get('treating_physician', ''), history_q=request.args.get('history', ''), departments=departments, physicians=physicians)


@records_bp.route('/records/<int:record_id>/delete', methods=['POST'])
@role_required('admin')
def delete_record(record_id):
    r = Record.query.get_or_404(record_id)
    db.session.delete(r)
    db.session.commit()
    # Clear dropdown cache after deleting record
    clear_dropdown_cache()
    try:
        log_action(current_user.id, 'record.delete', 'record', r.id, f'full_name={r.full_name}')
    except Exception:
        current_app.logger.exception('Failed to write audit log for record.delete')
    current_app.logger.info(f'Record deleted: {r.id} by {current_user.username}')
    flash(f'Запис #{r.id} ({r.full_name}) видалено', 'danger')
    # preserve filters from form (if any)
    params = {}
    for k in ('discharge_status', 'treating_physician', 'discharge_department', 'history', 'full_name'):
        v = request.form.get(k, '').strip()
        if v:
            params[k] = v
    if request.form.get('has_death_date', '').strip():
        params['has_death_date'] = '1'
    return redirect(url_for('records.index', **params))
