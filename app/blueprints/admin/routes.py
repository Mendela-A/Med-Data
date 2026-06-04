# app/blueprints/admin/routes.py
"""
Admin routes
"""

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import case, func

from app.extensions import db, cache
from models import User, Department, Audit, Record, DailyReport, AmbulatoryRecord, log_action
from decorators import role_required
from utils import clear_dropdown_cache, escape_like
from constants import (VALID_ROLES, STATUS_DISCHARGED, STATUS_PROCESSING, STATUS_VIOLATIONS,
                       STATUS_DECEASED, STATUS_NO_GROUP, STATUS_NO_EPISODE, TABS, DEFAULT_ROLE_TABS)
from . import admin_bp


# User Management Routes
@admin_bp.route('/users')
@role_required('admin')
def admin_users():
    users = User.query.order_by(User.username).all()
    return render_template('admin_users.html', users=users)


@admin_bp.route('/users/create', methods=['POST'])
@role_required('admin')
def admin_create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', '').strip() or 'operator'

    if role not in VALID_ROLES:
        flash('Невірна роль користувача', 'warning')
        return redirect(url_for('admin.admin_users'))

    if not username or not password:
        flash('Ім\'я користувача та пароль обов\'язкові', 'warning')
        return redirect(url_for('admin.admin_users'))
    if len(password) < 8:
        flash('Пароль повинен містити щонайменше 8 символів', 'warning')
        return redirect(url_for('admin.admin_users'))
    if User.query.filter_by(username=username).first():
        flash('Ім\'я користувача вже зайнято', 'warning')
        return redirect(url_for('admin.admin_users'))

    u = User(username=username, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()  # assigns u.id
    log_action(current_user.id, 'user.create', 'user', u.id, f'role={role}')
    db.session.commit()
    current_app.logger.info(f'User created: {username} by {current_user.username}')
    flash(f'Користувача {username} ({role}) успішно створено', 'success')
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_user(user_id):
    u = db.get_or_404(User, user_id)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip()

        if not username:
            flash('Ім\'я користувача обов\'язкове', 'warning')
            return redirect(url_for('admin.admin_edit_user', user_id=user_id))

        # Check if username is taken by another user
        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != user_id:
            flash('Ім\'я користувача вже зайнято', 'warning')
            return redirect(url_for('admin.admin_edit_user', user_id=user_id))

        if password and len(password) < 8:
            flash('Пароль повинен містити щонайменше 8 символів', 'warning')
            return redirect(url_for('admin.admin_edit_user', user_id=user_id))

        # Update username
        old_username = u.username
        u.username = username

        # Update password if provided
        if password:
            u.set_password(password)

        # Update role
        if role in VALID_ROLES:
            u.role = role

        # Update extra_permissions (tabs beyond role defaults)
        base_tabs = DEFAULT_ROLE_TABS.get(role, [])
        extra = [t for t in TABS if t not in base_tabs and request.form.get(f'tab_{t}')]
        u.extra_permissions = extra if extra else None

        try:
            details = f'username={old_username}->{username}, role={role}'
            if extra:
                details += f', extra_tabs={extra}'
            if password:
                details += ', password_changed=True'
            log_action(current_user.id, 'user.update', 'user', u.id, details)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed to update user')
            flash('Помилка при збереженні змін', 'danger')
            return redirect(url_for('admin.admin_edit_user', user_id=user_id))
        current_app.logger.info(f'User updated: {u.username} by {current_user.username}')
        flash(f'Користувача {u.username} успішно оновлено', 'success')
        return redirect(url_for('admin.admin_users'))

    return render_template('edit_user.html', user=u, tabs=TABS, default_role_tabs=DEFAULT_ROLE_TABS)


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_user(user_id):
    if current_user.id == user_id:
        flash('Ви не можете видалити самого себе', 'danger')
        return redirect(url_for('admin.admin_users'))
    u = db.get_or_404(User, user_id)
    saved_id = u.id
    saved_username = u.username
    try:
        db.session.delete(u)
        log_action(current_user.id, 'user.delete', 'user', saved_id, f'username={saved_username}')
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to delete user')
        flash('Помилка при видаленні користувача', 'danger')
        return redirect(url_for('admin.admin_users'))
    current_app.logger.info(f'User deleted: {saved_username} by {current_user.username}')
    flash(f'Користувача {saved_username} видалено', 'danger')
    return redirect(url_for('admin.admin_users'))


# Department Management Routes
@admin_bp.route('/departments')
@role_required('admin')
def admin_departments():
    departments = Department.query.order_by(Department.row_no.nullslast(), Department.name).all()
    return render_template('admin_departments.html', departments=departments)


@admin_bp.route('/departments/create', methods=['POST'])
@role_required('admin')
def admin_create_department():
    name = request.form.get('name', '').strip()
    bed_profile_name = request.form.get('bed_profile_name', '').strip() or None
    row_no_str = request.form.get('row_no', '').strip()
    bed_capacity_str = request.form.get('bed_capacity', '').strip()

    if not name:
        flash('Назва відділення обов\'язкова', 'warning')
        return redirect(url_for('admin.admin_departments'))
    if Department.query.filter_by(name=name).first():
        flash('Відділення з такою назвою вже існує', 'warning')
        return redirect(url_for('admin.admin_departments'))

    row_no = None
    if row_no_str:
        try:
            row_no = int(row_no_str)
        except ValueError:
            flash('№ рядка має бути числом', 'warning')
            return redirect(url_for('admin.admin_departments'))

    bed_capacity = None
    if bed_capacity_str:
        try:
            bed_capacity = int(bed_capacity_str)
        except ValueError:
            flash('Ліжковий фонд має бути числом', 'warning')
            return redirect(url_for('admin.admin_departments'))

    d = Department(
        name=name,
        bed_profile_name=bed_profile_name,
        row_no=row_no,
        bed_capacity=bed_capacity
    )
    db.session.add(d)
    db.session.flush()  # assigns d.id
    log_action(current_user.id, 'department.create', 'department', d.id, f'name={name}, profile={bed_profile_name}, row={row_no}, beds={bed_capacity}')
    db.session.commit()
    # Clear dropdown cache after creating department
    clear_dropdown_cache()
    current_app.logger.info(f'Department created: {name} by {current_user.username}')
    flash(f'Відділення "{name}" успішно створено', 'success')
    return redirect(url_for('admin.admin_departments'))


@admin_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_department(dept_id):
    d = db.get_or_404(Department, dept_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        bed_profile_name = request.form.get('bed_profile_name', '').strip() or None
        row_no_str = request.form.get('row_no', '').strip()
        bed_capacity_str = request.form.get('bed_capacity', '').strip()

        if not name:
            flash('Назва відділення обов\'язкова', 'warning')
            return redirect(url_for('admin.admin_edit_department', dept_id=dept_id))

        existing = Department.query.filter_by(name=name).first()
        if existing and existing.id != dept_id:
            flash('Відділення з такою назвою вже існує', 'warning')
            return redirect(url_for('admin.admin_edit_department', dept_id=dept_id))

        row_no = None
        if row_no_str:
            try:
                row_no = int(row_no_str)
            except ValueError:
                flash('№ рядка має бути числом', 'warning')
                return redirect(url_for('admin.admin_edit_department', dept_id=dept_id))

        bed_capacity = None
        if bed_capacity_str:
            try:
                bed_capacity = int(bed_capacity_str)
            except ValueError:
                flash('Ліжковий фонд має бути числом', 'warning')
                return redirect(url_for('admin.admin_edit_department', dept_id=dept_id))

        old_name = d.name
        d.name = name
        d.bed_profile_name = bed_profile_name
        d.row_no = row_no
        d.bed_capacity = bed_capacity

        try:
            log_action(current_user.id, 'department.update', 'department', d.id, f'name={old_name}->{name}, profile={bed_profile_name}, row={row_no}, beds={bed_capacity}')
            db.session.commit()
            clear_dropdown_cache()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed to update department')
            flash('Помилка при збереженні змін', 'danger')
            return redirect(url_for('admin.admin_edit_department', dept_id=dept_id))

        current_app.logger.info(f'Department updated: {d.name} by {current_user.username}')
        flash(f'Відділення "{d.name}" успішно оновлено', 'success')
        return redirect(url_for('admin.admin_departments'))

    return render_template('edit_department.html', department=d)


@admin_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_department(dept_id):
    d = db.get_or_404(Department, dept_id)
    # prevent deletion if department in use
    in_use = Record.query.filter(Record.discharge_department == d.name).count()
    if in_use:
        flash(f'Неможливо видалити відділення "{d.name}" - використовується в {in_use} записах', 'danger')
        return redirect(url_for('admin.admin_departments'))
    saved_id = d.id
    saved_name = d.name
    db.session.delete(d)
    log_action(current_user.id, 'department.delete', 'department', saved_id, f'name={saved_name}')
    db.session.commit()
    # Clear dropdown cache after deleting department
    clear_dropdown_cache()
    current_app.logger.info(f'Department deleted: {saved_name} by {current_user.username}')
    flash(f'Відділення "{saved_name}" видалено', 'danger')
    return redirect(url_for('admin.admin_departments'))


# Statistics Route
@admin_bp.route('/statistics')
@role_required('admin', 'viewer')
def admin_statistics():
    now = datetime.now()
    today = now.date()

    # --- Parse date range from query params ---
    from_str = request.args.get('from_date', '').strip()
    to_str = request.args.get('to_date', '').strip()

    # Backward compatibility: month_year param (YYYY-MM)
    month_year = request.args.get('month_year', '')

    from_date = None
    to_date = None

    # Try from_date / to_date first
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

    # Fallback: month_year param
    if from_date is None and month_year and '-' in month_year:
        try:
            y, m = month_year.split('-')
            y, m = int(y), int(m)
            if 1 <= m <= 12 and 2000 <= y <= 2100:
                from_date = date(y, m, 1)
                to_date = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
        except (ValueError, IndexError):
            pass

    # Default: current month
    if from_date is None:
        from_date = date(today.year, today.month, 1)
    if to_date is None:
        if from_date.month == 12:
            to_date = date(from_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(from_date.year, from_date.month + 1, 1) - timedelta(days=1)

    # Validate: from <= to
    if from_date > to_date:
        from_date, to_date = to_date, from_date

    # Exclusive upper bound for queries (to_date is inclusive, so +1 day)
    query_end = to_date + timedelta(days=1)

    # Period label for display
    if from_date.day == 1 and to_date == (date(from_date.year, from_date.month + 1, 1) - timedelta(days=1) if from_date.month < 12 else date(from_date.year + 1, 1, 1) - timedelta(days=1)):
        period_label = datetime(from_date.year, from_date.month, 1).strftime('%B %Y')
    else:
        period_label = f"{from_date.strftime('%d.%m.%Y')} — {to_date.strftime('%d.%m.%Y')}"

    # Cache key — 5-minute TTL, no manual invalidation needed
    _cache_key = f'stats_{from_date}_{to_date}'
    _cached = cache.get(_cache_key)
    if _cached:
        return render_template('admin_statistics.html',
                               period_label=period_label,
                               from_date=from_date, to_date=to_date,
                               **_cached)

    # 1. Records per day by discharge date (M3: removed func.date() wrapper)
    records_per_day = db.session.query(
        Record.date_of_discharge.label('date'),
        func.count(Record.id).label('count')
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).group_by(
        Record.date_of_discharge
    ).order_by(Record.date_of_discharge).all()

    # 2. Status distribution by department + ALOS (H2: added avg k_days)
    dept_stats = db.session.query(
        Record.discharge_department,
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deceased'),
        func.sum(case(((Record.discharge_status == STATUS_DISCHARGED) & (Record.date_of_death.is_(None)), 1), else_=0)).label('discharged'),
        func.sum(case(((Record.discharge_status == STATUS_PROCESSING) & (Record.date_of_death.is_(None)), 1), else_=0)).label('processing'),
        func.sum(case(((Record.discharge_status == STATUS_VIOLATIONS) & (Record.date_of_death.is_(None)), 1), else_=0)).label('violations'),
        func.avg(Record.k_days).label('avg_k_days')
    ).filter(
        Record.discharge_department.isnot(None),
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).group_by(Record.discharge_department).all()

    status_by_dept = {}
    for row in dept_stats:
        dept, deceased, discharged, processing, violations, avg_k = (
            row.discharge_department, row.deceased, row.discharged,
            row.processing, row.violations, row.avg_k_days)
        status_by_dept[dept] = {
            STATUS_DECEASED:   deceased or 0,
            STATUS_DISCHARGED: discharged or 0,
            STATUS_PROCESSING: processing or 0,
            STATUS_VIOLATIONS: violations or 0,
            'avg_k_days': round(avg_k, 1) if avg_k is not None else None,
        }

    dept_list = sorted(status_by_dept.keys())

    # H3: compute status_distribution from status_by_dept (removes redundant current_stats query)
    status_distribution = {
        STATUS_DECEASED:   sum(d[STATUS_DECEASED]   for d in status_by_dept.values()),
        STATUS_DISCHARGED: sum(d[STATUS_DISCHARGED] for d in status_by_dept.values()),
        STATUS_PROCESSING: sum(d[STATUS_PROCESSING] for d in status_by_dept.values()),
        STATUS_VIOLATIONS: sum(d[STATUS_VIOLATIONS] for d in status_by_dept.values()),
    }
    total_records = sum(status_distribution.values())

    # H2: global ALOS
    all_k = [d['avg_k_days'] for d in status_by_dept.values() if d['avg_k_days'] is not None]
    global_alos = round(sum(all_k) / len(all_k), 1) if all_k else None

    # АДСЖ group breakdown
    adsj_raw = db.session.query(
        func.coalesce(
            func.nullif(func.trim(Record.adsj), ''),
            STATUS_NO_GROUP
        ).label('group_name'),
        func.count(Record.id).label('count'),
        func.sum(Record.suma).label('total_suma')
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).group_by(
        func.coalesce(
            func.nullif(func.trim(Record.adsj), ''),
            STATUS_NO_GROUP
        )
    ).all()

    adsj_stats = sorted(
        [r for r in adsj_raw if r.group_name != STATUS_NO_GROUP],
        key=lambda r: r.group_name
    ) + [r for r in adsj_raw if r.group_name == STATUS_NO_GROUP]

    adsj_total_count = sum(r.count for r in adsj_stats)
    adsj_total_suma = sum(r.total_suma or 0 for r in adsj_stats)

    # --- Trends: compare with previous period of equal length ---
    range_days = (to_date - from_date).days + 1
    prev_to = from_date - timedelta(days=1)
    prev_from = prev_to - timedelta(days=range_days - 1)
    prev_query_end = prev_to + timedelta(days=1)

    prev_stats = db.session.query(
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deceased'),
        func.sum(case(((Record.discharge_status == STATUS_DISCHARGED) & (Record.date_of_death.is_(None)), 1), else_=0)).label('discharged'),
        func.sum(case(((Record.discharge_status == STATUS_PROCESSING) & (Record.date_of_death.is_(None)), 1), else_=0)).label('processing'),
        func.sum(case(((Record.discharge_status == STATUS_VIOLATIONS) & (Record.date_of_death.is_(None)), 1), else_=0)).label('violations')
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= prev_from,
        Record.date_of_discharge < prev_query_end
    ).first()

    prev_deceased   = prev_stats.deceased or 0
    prev_discharged = prev_stats.discharged or 0
    prev_processing = prev_stats.processing or 0
    prev_violations = prev_stats.violations or 0
    prev_total = prev_deceased + prev_discharged + prev_processing + prev_violations

    trends = {
        'total':      total_records - prev_total,
        'processing': status_distribution[STATUS_PROCESSING] - prev_processing,
        'discharged': status_distribution[STATUS_DISCHARGED] - prev_discharged,
        'deceased':   status_distribution[STATUS_DECEASED]   - prev_deceased,
        'violations': status_distribution[STATUS_VIOLATIONS] - prev_violations,
    }

    # H1: Bed occupancy from DailyReport
    bed_rows = db.session.query(
        Department.name,
        func.avg(DailyReport.beds_total).label('avg_beds'),
        func.avg(DailyReport.patients_end).label('avg_occupied'),
        func.sum(DailyReport.admitted_total).label('total_admitted'),
        func.sum(DailyReport.deaths).label('total_deaths'),
    ).join(Department, DailyReport.department_id == Department.id
    ).filter(
        DailyReport.report_date >= from_date,
        DailyReport.report_date < query_end,
        DailyReport.beds_total.isnot(None),
    ).group_by(DailyReport.department_id, Department.name).all()

    bed_stats = sorted([{
        'name':         r.name,
        'avg_beds':     round(r.avg_beds or 0),
        'avg_occupied': round(r.avg_occupied or 0),
        'occupancy_pct': round((r.avg_occupied or 0) / max(r.avg_beds or 1, 1) * 100),
        'admitted':     r.total_admitted or 0,
        'deaths':       r.total_deaths or 0,
    } for r in bed_rows], key=lambda x: x['name'])

    global_bed = {
        'avg_beds':      sum(d['avg_beds'] for d in bed_stats),
        'avg_occupied':  sum(d['avg_occupied'] for d in bed_stats),
        'occupancy_pct': round(
            sum(d['avg_occupied'] for d in bed_stats) /
            max(sum(d['avg_beds'] for d in bed_stats), 1) * 100
        ) if bed_stats else 0,
        'total_admitted': sum(d['admitted'] for d in bed_stats),
        'total_deaths':   sum(d['deaths'] for d in bed_stats),
    }

    # H1: Ambulatory record stats
    amb_r = db.session.query(
        func.count(AmbulatoryRecord.id).label('total'),
        func.sum(case((AmbulatoryRecord.is_urgent == True, 1), else_=0)).label('urgent'),
        func.sum(case((AmbulatoryRecord.discharge_status == STATUS_DISCHARGED, 1), else_=0)).label('discharged'),
        func.sum(case((AmbulatoryRecord.discharge_status == STATUS_NO_EPISODE, 1), else_=0)).label('no_episode'),
    ).filter(
        AmbulatoryRecord.date >= from_date,
        AmbulatoryRecord.date < query_end,
    ).first()
    amb_stats = {
        'total':      amb_r.total or 0,
        'urgent':     amb_r.urgent or 0,
        'discharged': amb_r.discharged or 0,
        'no_episode': amb_r.no_episode or 0,
    }

    ctx = dict(
        records_per_day=records_per_day,
        status_by_dept=status_by_dept,
        dept_list=dept_list,
        status_distribution=status_distribution,
        total_records=total_records,
        global_alos=global_alos,
        trends=trends,
        adsj_stats=adsj_stats,
        adsj_total_count=adsj_total_count,
        adsj_total_suma=adsj_total_suma,
        bed_stats=bed_stats,
        global_bed=global_bed,
        amb_stats=amb_stats,
    )
    cache.set(_cache_key, ctx, timeout=300)

    return render_template(
        'admin_statistics.html',
        period_label=period_label,
        from_date=from_date,
        to_date=to_date,
        **ctx,
    )


# Audit Log Route
@admin_bp.route('/audit')
@role_required('admin')
def admin_audit():
    """View audit log with filters and pagination."""
    from utils import get_user_map

    # Filters
    action_filter = request.args.get('action', '').strip()
    actor_filter = request.args.get('actor', '').strip()
    from_str = request.args.get('from_date', '').strip()
    to_str = request.args.get('to_date', '').strip()
    q_search = request.args.get('q_search', '').strip()

    q = Audit.query

    if action_filter:
        q = q.filter(Audit.action.like(f'%{escape_like(action_filter)}%', escape='\\'))
    if actor_filter:
        try:
            actor_id = int(actor_filter)
            q = q.filter(Audit.actor_id == actor_id)
        except ValueError:
            pass
    if from_str:
        try:
            from_date = date.fromisoformat(from_str)
            q = q.filter(Audit.created_at >= datetime.combine(from_date, datetime.min.time()))
        except ValueError:
            pass
    if to_str:
        try:
            to_date = date.fromisoformat(to_str)
            q = q.filter(Audit.created_at < datetime.combine(to_date + timedelta(days=1), datetime.min.time()))
        except ValueError:
            pass

    if q_search:
        search_pattern = f'%{escape_like(q_search)}%'
        if q_search.isdigit():
            q = q.filter(
                (Audit.details.like(search_pattern, escape='\\')) |
                (Audit.target_type.like(search_pattern, escape='\\')) |
                (Audit.action.like(search_pattern, escape='\\')) |
                (Audit.target_id == int(q_search))
            )
        else:
            q = q.filter(
                (Audit.details.like(search_pattern, escape='\\')) |
                (Audit.target_type.like(search_pattern, escape='\\')) |
                (Audit.action.like(search_pattern, escape='\\'))
            )

    q = q.order_by(Audit.created_at.desc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = max(10, min(per_page, 200))

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items

    # Distinct actions for filter dropdown
    actions = [a[0] for a in db.session.query(Audit.action).distinct().order_by(Audit.action).all()]

    user_map = get_user_map()
    users = User.query.order_by(User.username).all()

    is_htmx = request.headers.get('HX-Request') is not None

    if is_htmx:
        return render_template(
            'admin/_audit_table_partial.html',
            logs=logs,
            pagination=pagination,
            action_filter=action_filter,
            actor_filter=actor_filter,
            from_date=from_str,
            to_date=to_str,
            q_search=q_search,
            user_map=user_map,
        )

    return render_template(
        'admin_audit.html',
        logs=logs,
        pagination=pagination,
        actions=actions,
        users=users,
        user_map=user_map,
        action_filter=action_filter,
        actor_filter=actor_filter,
        from_date=from_str,
        to_date=to_str,
        q_search=q_search,
    )
