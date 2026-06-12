# app/blueprints/admin/routes.py
"""
Admin routes
"""

from flask import render_template, redirect, url_for, flash, request, current_app, send_file
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from io import BytesIO
from collections import defaultdict
from sqlalchemy import extract, case, func

from app.extensions import db
from models import User, Department, Audit, Record, AmbulatoryRecord, NSZUCorrection, StatusOption, log_action
from decorators import role_required
from utils import clear_dropdown_cache, escape_like
from constants import VALID_ROLES, STATUS_DISCHARGED, STATUS_PROCESSING, STATUS_VIOLATIONS, UKRAINIAN_MONTHS
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

        try:
            details = f'username={old_username}->{username}, role={role}'
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

    return render_template('edit_user.html', user=u)


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
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin_departments.html', departments=departments)


@admin_bp.route('/departments/create', methods=['POST'])
@role_required('admin')
def admin_create_department():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Назва відділення обов\'язкова', 'warning')
        return redirect(url_for('admin.admin_departments'))
    if Department.query.filter_by(name=name).first():
        flash('Відділення з такою назвою вже існує', 'warning')
        return redirect(url_for('admin.admin_departments'))
    d = Department(name=name)
    db.session.add(d)
    db.session.flush()  # assigns d.id
    log_action(current_user.id, 'department.create', 'department', d.id, f'name={name}')
    db.session.commit()
    # Clear dropdown cache after creating department
    clear_dropdown_cache()
    current_app.logger.info(f'Department created: {name} by {current_user.username}')
    flash(f'Відділення "{name}" успішно створено', 'success')
    return redirect(url_for('admin.admin_departments'))


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


# Status Dictionary Routes (scopes: ambulatory / records / nszu)
STATUS_COLORS = ('primary', 'success', 'info', 'warning', 'danger', 'secondary', 'dark')

STATUS_SCOPES = {
    'ambulatory': {'label': 'Амбулаторія', 'model': AmbulatoryRecord, 'column': 'discharge_status'},
    'records': {'label': 'Записи (стаціонар)', 'model': Record, 'column': 'discharge_status'},
    'nszu': {'label': 'НСЗУ', 'model': NSZUCorrection, 'column': 'status'},
}


def _valid_scope(scope):
    return scope if scope in STATUS_SCOPES else 'ambulatory'


def _scope_status_column(scope):
    cfg = STATUS_SCOPES[scope]
    return getattr(cfg['model'], cfg['column'])


def _status_usage_counts(scope):
    """Кількість записів відповідного розділу на кожен статус (одним GROUP BY)."""
    col = _scope_status_column(scope)
    model = STATUS_SCOPES[scope]['model']
    rows = db.session.query(col, func.count(model.id)).group_by(col).all()
    return {name: cnt for name, cnt in rows if name}


@admin_bp.route('/statuses')
@role_required('admin')
def admin_statuses():
    scope = _valid_scope(request.args.get('scope', 'ambulatory'))
    statuses = (StatusOption.query.filter_by(scope=scope)
                .order_by(StatusOption.sort_order, StatusOption.name).all())
    usage = _status_usage_counts(scope)
    known = {s.name for s in statuses}
    orphans = {name: cnt for name, cnt in usage.items() if name not in known}
    return render_template('admin_statuses.html',
                           statuses=statuses, usage=usage, orphans=orphans,
                           colors=STATUS_COLORS, scope=scope,
                           scopes={k: v['label'] for k, v in STATUS_SCOPES.items()})


@admin_bp.route('/statuses/create', methods=['POST'])
@role_required('admin')
def admin_create_status():
    scope = _valid_scope(request.form.get('scope', 'ambulatory'))
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '').strip()
    icon = request.form.get('icon', '').strip() or 'bi-circle'
    show_in_stats = request.form.get('show_in_stats') == 'on'

    if not name:
        flash('Назва статусу обов\'язкова', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=scope))
    if color not in STATUS_COLORS:
        color = 'secondary'
    if StatusOption.query.filter_by(scope=scope, name=name).first():
        flash('Статус з такою назвою вже існує', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=scope))

    max_order = db.session.query(func.max(StatusOption.sort_order)).filter_by(scope=scope).scalar() or 0
    s = StatusOption(scope=scope, name=name, color=color, icon=icon,
                     sort_order=max_order + 10, show_in_stats=show_in_stats)
    db.session.add(s)
    db.session.flush()
    log_action(current_user.id, 'status.create', 'status_option', s.id, f'scope={scope}, name={name}')
    db.session.commit()
    clear_dropdown_cache()
    current_app.logger.info(f'StatusOption created: [{scope}] {name} by {current_user.username}')
    flash(f'Статус «{name}» успішно створено', 'success')
    return redirect(url_for('admin.admin_statuses', scope=scope))


@admin_bp.route('/statuses/<int:status_id>/update', methods=['POST'])
@role_required('admin')
def admin_update_status(status_id):
    s = db.get_or_404(StatusOption, status_id)
    new_name = request.form.get('name', '').strip()
    color = request.form.get('color', '').strip()
    icon = request.form.get('icon', '').strip() or s.icon
    sort_order = request.form.get('sort_order', type=int)
    show_in_stats = request.form.get('show_in_stats') == 'on'

    if not new_name:
        flash('Назва статусу обов\'язкова', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))

    old_name = s.name
    renamed = new_name != old_name
    if renamed and s.is_system:
        flash(f'Статус «{old_name}» — системний (на ньому тримаються статистика і звіти), його не можна перейменувати', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))
    if renamed and StatusOption.query.filter_by(scope=s.scope, name=new_name).first():
        flash('Статус з такою назвою вже існує', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))

    s.name = new_name
    if color in STATUS_COLORS:
        s.color = color
    s.icon = icon
    if sort_order is not None:
        s.sort_order = sort_order
    s.show_in_stats = show_in_stats

    try:
        renamed_count = 0
        if renamed:
            # Записи зберігають статус текстом — перейменування мусить
            # оновити їх в тій самій транзакції, інакше фільтри/піли
            # «загублять» старі записи.
            col = _scope_status_column(s.scope)
            model = STATUS_SCOPES[s.scope]['model']
            renamed_count = (model.query
                             .filter(col == old_name)
                             .update({STATUS_SCOPES[s.scope]['column']: new_name},
                                     synchronize_session=False))
        details = f'scope={s.scope}, name={old_name}->{new_name}, color={s.color}, records_renamed={renamed_count}'
        log_action(current_user.id, 'status.update', 'status_option', s.id, details)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to update status option')
        flash('Помилка при збереженні статусу', 'danger')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))

    clear_dropdown_cache()
    current_app.logger.info(f'StatusOption updated: [{s.scope}] {old_name}->{new_name} by {current_user.username}')
    if renamed and renamed_count:
        flash(f'Статус «{old_name}» перейменовано на «{new_name}», оновлено записів: {renamed_count}', 'success')
    else:
        flash(f'Статус «{new_name}» оновлено', 'success')
    return redirect(url_for('admin.admin_statuses', scope=s.scope))


@admin_bp.route('/statuses/<int:status_id>/set-default', methods=['POST'])
@role_required('admin')
def admin_set_default_status(status_id):
    s = db.get_or_404(StatusOption, status_id)
    if not s.is_active:
        flash('Неактивний статус не може бути статусом за замовчуванням', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))
    StatusOption.query.filter_by(scope=s.scope).update({'is_default': False}, synchronize_session=False)
    s.is_default = True
    log_action(current_user.id, 'status.set_default', 'status_option', s.id, f'scope={s.scope}, name={s.name}')
    db.session.commit()
    clear_dropdown_cache()
    flash(f'Статус «{s.name}» встановлено за замовчуванням для нових записів', 'success')
    return redirect(url_for('admin.admin_statuses', scope=s.scope))


@admin_bp.route('/statuses/<int:status_id>/toggle', methods=['POST'])
@role_required('admin')
def admin_toggle_status(status_id):
    s = db.get_or_404(StatusOption, status_id)
    if s.is_system:
        flash(f'Статус «{s.name}» — системний, його не можна деактивувати', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))
    if s.is_active and s.is_default:
        flash('Статус за замовчуванням не можна деактивувати — спочатку призначте інший', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))
    s.is_active = not s.is_active
    action = 'status.activate' if s.is_active else 'status.deactivate'
    log_action(current_user.id, action, 'status_option', s.id, f'scope={s.scope}, name={s.name}')
    db.session.commit()
    clear_dropdown_cache()
    state = 'активовано' if s.is_active else 'деактивовано'
    flash(f'Статус «{s.name}» {state}', 'success')
    return redirect(url_for('admin.admin_statuses', scope=s.scope))


@admin_bp.route('/statuses/<int:status_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_status(status_id):
    s = db.get_or_404(StatusOption, status_id)
    if s.is_system:
        flash(f'Статус «{s.name}» — системний, його не можна видалити', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))
    col = _scope_status_column(s.scope)
    in_use = STATUS_SCOPES[s.scope]['model'].query.filter(col == s.name).count()
    if in_use:
        flash(f'Неможливо видалити статус «{s.name}» — використовується в {in_use} записах. Деактивуйте його натомість.', 'danger')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))
    if s.is_default:
        flash('Статус за замовчуванням не можна видалити — спочатку призначте інший', 'warning')
        return redirect(url_for('admin.admin_statuses', scope=s.scope))
    saved_id, saved_name, saved_scope = s.id, s.name, s.scope
    db.session.delete(s)
    log_action(current_user.id, 'status.delete', 'status_option', saved_id, f'scope={saved_scope}, name={saved_name}')
    db.session.commit()
    clear_dropdown_cache()
    current_app.logger.info(f'StatusOption deleted: [{saved_scope}] {saved_name} by {current_user.username}')
    flash(f'Статус «{saved_name}» видалено', 'danger')
    return redirect(url_for('admin.admin_statuses', scope=saved_scope))


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

    # Period label for display (українські назви місяців, не залежимо від локалі)
    if from_date.day == 1 and to_date == (date(from_date.year, from_date.month + 1, 1) - timedelta(days=1) if from_date.month < 12 else date(from_date.year + 1, 1, 1) - timedelta(days=1)):
        period_label = f"{UKRAINIAN_MONTHS[from_date.month]} {from_date.year}"
    else:
        period_label = f"{from_date.strftime('%d.%m.%Y')} — {to_date.strftime('%d.%m.%Y')}"

    # 1. Records per day by discharge date
    per_day_rows = db.session.query(
        func.date(Record.date_of_discharge).label('date'),
        func.count(Record.id).label('count')
    ).filter(
        Record.date_of_discharge != None,
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).group_by(
        func.date(Record.date_of_discharge)
    ).order_by('date').all()

    # дд.мм.рррр + масштаб для міні-гістограми
    max_per_day = max((r.count for r in per_day_rows), default=0)
    records_per_day = []
    for r in per_day_rows:
        d = r.date if not isinstance(r.date, str) else datetime.strptime(r.date, '%Y-%m-%d').date()
        records_per_day.append({'date': d.strftime('%d.%m.%Y'), 'count': r.count})

    # 2. Status distribution by department (OPTIMIZED: Single GROUP BY query)
    dept_stats = db.session.query(
        Record.discharge_department,
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deceased'),
        func.sum(case(((Record.discharge_status == STATUS_DISCHARGED) & (Record.date_of_death.is_(None)), 1), else_=0)).label('discharged'),
        func.sum(case(((Record.discharge_status == STATUS_PROCESSING) & (Record.date_of_death.is_(None)), 1), else_=0)).label('processing'),
        func.sum(case(((Record.discharge_status == STATUS_VIOLATIONS) & (Record.date_of_death.is_(None)), 1), else_=0)).label('violations')
    ).filter(
        Record.discharge_department.isnot(None),
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).group_by(Record.discharge_department).all()

    status_by_dept = {}
    for dept, deceased, discharged, processing, violations in dept_stats:
        status_by_dept[dept] = {
            'Помер': deceased or 0,
            'Виписаний': discharged or 0,
            'Опрацьовується': processing or 0,
            'Порушені вимоги': violations or 0
        }

    dept_list = sorted(status_by_dept.keys())

    # АДСЖ group breakdown
    adsj_raw = db.session.query(
        func.coalesce(
            func.nullif(func.trim(Record.adsj), ''),
            'Без групи'
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
            'Без групи'
        )
    ).all()

    adsj_stats = sorted(
        [r for r in adsj_raw if r.group_name != 'Без групи'],
        key=lambda r: r.group_name
    ) + [r for r in adsj_raw if r.group_name == 'Без групи']

    adsj_total_count = sum(r.count for r in adsj_stats)
    adsj_total_suma = sum(r.total_suma or 0 for r in adsj_stats)

    # 3. Overall status distribution (OPTIMIZED: Single query)
    current_stats = db.session.query(
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deceased'),
        func.sum(case(((Record.discharge_status == STATUS_DISCHARGED) & (Record.date_of_death.is_(None)), 1), else_=0)).label('discharged'),
        func.sum(case(((Record.discharge_status == STATUS_PROCESSING) & (Record.date_of_death.is_(None)), 1), else_=0)).label('processing'),
        func.sum(case(((Record.discharge_status == STATUS_VIOLATIONS) & (Record.date_of_death.is_(None)), 1), else_=0)).label('violations')
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).first()

    status_distribution = {
        'Помер': current_stats.deceased or 0,
        STATUS_DISCHARGED: current_stats.discharged or 0,
        STATUS_PROCESSING: current_stats.processing or 0,
        STATUS_VIOLATIONS: current_stats.violations or 0
    }

    total_records = sum(status_distribution.values())

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

    prev_deceased = prev_stats.deceased or 0
    prev_discharged = prev_stats.discharged or 0
    prev_processing = prev_stats.processing or 0
    prev_violations = prev_stats.violations or 0
    prev_total = prev_deceased + prev_discharged + prev_processing + prev_violations

    trends = {
        'total': total_records - prev_total,
        'processing': status_distribution[STATUS_PROCESSING] - prev_processing,
        'discharged': status_distribution[STATUS_DISCHARGED] - prev_discharged,
        'deceased': status_distribution['Помер'] - prev_deceased,
        'violations': status_distribution[STATUS_VIOLATIONS] - prev_violations
    }

    return render_template(
        'admin_statistics.html',
        records_per_day=records_per_day,
        max_per_day=max_per_day,
        status_by_dept=status_by_dept,
        dept_list=dept_list,
        status_distribution=status_distribution,
        total_records=total_records,
        trends=trends,
        period_label=period_label,
        from_date=from_date,
        to_date=to_date,
        adsj_stats=adsj_stats,
        adsj_total_count=adsj_total_count,
        adsj_total_suma=adsj_total_suma,
    )


# Reports Route
@admin_bp.route('/reports')
@role_required('operator', 'editor', 'admin', 'viewer')
def admin_reports():
    now = datetime.now()
    today = now.date()

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
        if from_date.month == 12:
            to_date = date(from_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(from_date.year, from_date.month + 1, 1) - timedelta(days=1)

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    query_end = to_date + timedelta(days=1)

    if from_date.month == to_date.month and from_date.year == to_date.year and from_date.day == 1:
        period_label = f"{UKRAINIAN_MONTHS[from_date.month]} {from_date.year}"
    else:
        period_label = f"{from_date.strftime('%d.%m.%Y')} — {to_date.strftime('%d.%m.%Y')}"

    base_q = Record.query.filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    )

    # --- Submission stats ---
    submission_row = db.session.query(
        func.sum(case((Record.history_submitted == True, 1), else_=0)).label('submitted'),
        func.sum(case((Record.history_submitted == False, 1), else_=0)).label('not_submitted'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).first()
    submission_submitted = submission_row.submitted or 0
    submission_not_submitted = submission_row.not_submitted or 0

    submission_by_physician = db.session.query(
        Record.treating_physician,
        func.sum(case((Record.history_submitted == True, 1), else_=0)).label('submitted'),
        func.sum(case((Record.history_submitted == False, 1), else_=0)).label('not_submitted'),
        func.count(Record.id).label('total'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end,
        Record.treating_physician.isnot(None),
        func.trim(Record.treating_physician) != ''
    ).group_by(Record.treating_physician).order_by(func.count(Record.id).desc()).all()

    # --- Urgency stats ---
    urgency_row = db.session.query(
        func.sum(case((Record.is_urgent == True, 1), else_=0)).label('urgent'),
        func.sum(case((Record.is_urgent == False, 1), else_=0)).label('planned'),
        func.sum(case((Record.is_urgent.is_(None), 1), else_=0)).label('unset'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end
    ).first()
    urgency_urgent = urgency_row.urgent or 0
    urgency_planned = urgency_row.planned or 0
    urgency_unset = urgency_row.unset or 0

    urgency_by_dept = db.session.query(
        Record.discharge_department,
        func.sum(case((Record.is_urgent == True, 1), else_=0)).label('urgent'),
        func.sum(case((Record.is_urgent == False, 1), else_=0)).label('planned'),
        func.sum(case((Record.is_urgent.is_(None), 1), else_=0)).label('unset'),
        func.count(Record.id).label('total'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end,
        Record.discharge_department.isnot(None),
        func.trim(Record.discharge_department) != ''
    ).group_by(Record.discharge_department).order_by(func.count(Record.id).desc()).all()

    return render_template(
        'reports.html',
        from_date=from_date,
        to_date=to_date,
        period_label=period_label,
        submission_submitted=submission_submitted,
        submission_not_submitted=submission_not_submitted,
        submission_by_physician=submission_by_physician,
        urgency_urgent=urgency_urgent,
        urgency_planned=urgency_planned,
        urgency_unset=urgency_unset,
        urgency_by_dept=urgency_by_dept,
    )


@admin_bp.route('/reports/not-submitted')
@role_required('operator', 'editor', 'admin', 'viewer')
def report_not_submitted():
    """PDF: unsubmitted histories per department / physician."""
    now = datetime.now()
    today = now.date()

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
        if from_date.month == 12:
            to_date = date(from_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(from_date.year, from_date.month + 1, 1) - timedelta(days=1)

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    query_end = to_date + timedelta(days=1)

    rows = db.session.query(
        Record.discharge_department,
        Record.treating_physician,
        func.count(Record.id).label('not_submitted_count')
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge < query_end,
        Record.history_submitted == False,
        Record.discharge_department.isnot(None),
        func.trim(Record.discharge_department) != '',
        Record.treating_physician.isnot(None),
        func.trim(Record.treating_physician) != '',
    ).group_by(
        Record.discharge_department,
        Record.treating_physician,
    ).order_by(
        Record.discharge_department,
        func.count(Record.id).desc(),
    ).all()

    # Group into {dept: [{physician, count}, ...]}
    dept_data = defaultdict(list)
    for row in rows:
        dept_data[row.discharge_department].append({
            'physician': row.treating_physician,
            'count': row.not_submitted_count,
        })
    dept_list = [
        {'dept': dept, 'physicians': physicians, 'total': sum(p['count'] for p in physicians)}
        for dept, physicians in dept_data.items()
    ]
    grand_total = sum(d['total'] for d in dept_list)

    if from_date.year == to_date.year:
        year_label = str(from_date.year)
    else:
        year_label = f"{from_date.year}–{to_date.year}"

    kyiv_tz = __import__('datetime').timezone(__import__('datetime').timedelta(hours=2))
    generated_at = datetime.now(kyiv_tz)

    try:
        from weasyprint import HTML
    except ImportError:
        flash('Для формування PDF потрібен пакет WeasyPrint', 'danger')
        return redirect(url_for('admin.admin_reports', from_date=from_str, to_date=to_str))

    html_string = render_template(
        'print_not_submitted.html',
        from_date=from_date,
        to_date=to_date,
        year_label=year_label,
        dept_list=dept_list,
        grand_total=grand_total,
        generated_by=current_user.username,
        generated_at=generated_at,
    )
    pdf = HTML(string=html_string).write_pdf()
    bio = BytesIO(pdf)
    bio.seek(0)
    filename = f"not_submitted_{from_date.strftime('%d-%m-%Y')}_{to_date.strftime('%d-%m-%Y')}.pdf"
    try:
        log_action(current_user.id, 'admin.report_not_submitted', 'report', None,
                   f'from={from_date} to={to_date} total={grand_total}')
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to log report_not_submitted action')
    return send_file(bio, as_attachment=True, download_name=filename, mimetype='application/pdf')


@admin_bp.route('/reports/hospitalization')
@role_required('operator', 'editor', 'admin', 'viewer')
def report_hospitalization():
    """PDF: planned vs urgent hospitalizations per department."""
    now = datetime.now()
    today = now.date()
    from_str = request.args.get('from_date', '').strip()
    to_str   = request.args.get('to_date',   '').strip()
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
        if from_date.month == 12:
            to_date = date(from_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(from_date.year, from_date.month + 1, 1) - timedelta(days=1)
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    query_end = to_date + timedelta(days=1)

    rows = db.session.query(
        Record.discharge_department,
        func.sum(case((Record.is_urgent == True,  1), else_=0)).label('urgent'),
        func.sum(case((Record.is_urgent == False, 1), else_=0)).label('planned'),
        func.count(Record.id).label('total'),
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= from_date,
        Record.date_of_discharge <  query_end,
        Record.discharge_department.isnot(None),
        func.trim(Record.discharge_department) != ''
    ).group_by(Record.discharge_department
    ).order_by(func.count(Record.id).desc()).all()

    dept_list = []
    grand_total = grand_urgent = grand_planned = 0
    for row in rows:
        known = row.urgent + row.planned
        dept_list.append({
            'name':        row.discharge_department,
            'total':       row.total,
            'urgent':      row.urgent,
            'planned':     row.planned,
            'urgent_pct':  round(row.urgent  / known * 100, 1) if known else None,
            'planned_pct': round(row.planned / known * 100, 1) if known else None,
        })
        grand_total   += row.total
        grand_urgent  += row.urgent
        grand_planned += row.planned

    grand_known = grand_urgent + grand_planned
    grand_urgent_pct  = round(grand_urgent  / grand_known * 100, 1) if grand_known else None
    grand_planned_pct = round(grand_planned / grand_known * 100, 1) if grand_known else None

    if from_date.year == to_date.year:
        year_label = str(from_date.year)
    else:
        year_label = f"{from_date.year}–{to_date.year}"

    import datetime as _dt
    kyiv_tz = _dt.timezone(_dt.timedelta(hours=2))
    generated_at = datetime.now(kyiv_tz)

    try:
        from weasyprint import HTML
    except ImportError:
        flash('Для формування PDF потрібен пакет WeasyPrint', 'danger')
        return redirect(url_for('admin.admin_reports', from_date=from_str, to_date=to_str))

    html_string = render_template(
        'print_hospitalization.html',
        from_date=from_date, to_date=to_date, year_label=year_label,
        dept_list=dept_list,
        grand_total=grand_total, grand_urgent=grand_urgent, grand_planned=grand_planned,
        grand_urgent_pct=grand_urgent_pct, grand_planned_pct=grand_planned_pct,
        generated_by=current_user.username, generated_at=generated_at,
    )
    pdf = HTML(string=html_string).write_pdf()
    bio = BytesIO(pdf)
    bio.seek(0)
    filename = f"hospitalization_{from_date.strftime('%d-%m-%Y')}_{to_date.strftime('%d-%m-%Y')}.pdf"
    try:
        log_action(current_user.id, 'admin.report_hospitalization', 'report', None,
                   f'from={from_date} to={to_date} total={grand_total}')
        db.session.commit()
    except Exception:
        current_app.logger.exception('Failed to log report_hospitalization')
    return send_file(bio, as_attachment=True, download_name=filename, mimetype='application/pdf')


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
    )
