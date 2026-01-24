# app/blueprints/admin/routes.py
"""
Admin routes
"""

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import extract, case, func

from app.extensions import db
from models import User, Department, Audit, Record, log_action
from decorators import role_required
from utils import clear_dropdown_cache
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

    if not username or not password:
        flash('Ім\'я користувача та пароль обов\'язкові', 'warning')
        return redirect(url_for('admin.admin_users'))
    if User.query.filter_by(username=username).first():
        flash('Ім\'я користувача вже зайнято', 'warning')
        return redirect(url_for('admin.admin_users'))

    u = User(username=username, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    # audit & log
    try:
        log_action(current_user.id, 'user.create', 'user', u.id, f'role={role}')
    except Exception:
        current_app.logger.exception('Failed to write audit log for user.create')
    current_app.logger.info(f'User created: {username} by {current_user.username}')
    flash(f'Користувача {username} ({role}) успішно створено', 'success')
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_user(user_id):
    u = User.query.get_or_404(user_id)

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

        # Update username
        old_username = u.username
        u.username = username

        # Update password if provided
        if password:
            u.set_password(password)

        # Update role
        if role in ['operator', 'editor', 'admin', 'viewer']:
            u.role = role

        db.session.commit()

        try:
            details = f'username={old_username}->{username}, role={role}'
            if password:
                details += ', password_changed=True'
            log_action(current_user.id, 'user.update', 'user', u.id, details)
        except Exception:
            current_app.logger.exception('Failed to write audit log for user.update')
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
    u = User.query.get_or_404(user_id)
    db.session.delete(u)
    db.session.commit()
    try:
        log_action(current_user.id, 'user.delete', 'user', u.id, f'username={u.username}')
    except Exception:
        current_app.logger.exception('Failed to write audit log for user.delete')
    current_app.logger.info(f'User deleted: {u.username} by {current_user.username}')
    flash(f'Користувача {u.username} видалено', 'danger')
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
    db.session.commit()
    # Clear dropdown cache after creating department
    clear_dropdown_cache()
    try:
        log_action(current_user.id, 'department.create', 'department', d.id, f'name={name}')
    except Exception:
        current_app.logger.exception('Failed to write audit log for department.create')
    current_app.logger.info(f'Department created: {name} by {current_user.username}')
    flash(f'Відділення "{name}" успішно створено', 'success')
    return redirect(url_for('admin.admin_departments'))


@admin_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_department(dept_id):
    d = Department.query.get_or_404(dept_id)
    # prevent deletion if department in use
    in_use = Record.query.filter(Record.discharge_department == d.name).count()
    if in_use:
        flash(f'Неможливо видалити відділення "{d.name}" - використовується в {in_use} записах', 'danger')
        return redirect(url_for('admin.admin_departments'))
    db.session.delete(d)
    db.session.commit()
    # Clear dropdown cache after deleting department
    clear_dropdown_cache()
    try:
        log_action(current_user.id, 'department.delete', 'department', d.id, f'name={d.name}')
    except Exception:
        current_app.logger.exception('Failed to write audit log for department.delete')
    current_app.logger.info(f'Department deleted: {d.name} by {current_user.username}')
    flash(f'Відділення "{d.name}" видалено', 'danger')
    return redirect(url_for('admin.admin_departments'))


# Statistics Route
@admin_bp.route('/statistics')
@role_required('admin', 'viewer')
def admin_statistics():
    # Get selected month/year from query params or use current
    now = datetime.now()

    # Try to get from 'year' and 'month' params first (for backward compatibility)
    selected_year = request.args.get('year', type=int)
    selected_month = request.args.get('month', type=int)

    # If not found, try month_year param (YYYY-MM format from HTML5 month input)
    month_year = request.args.get('month_year', '')
    if month_year and '-' in month_year:
        try:
            year_str, month_str = month_year.split('-')
            selected_year = int(year_str)
            selected_month = int(month_str)
        except (ValueError, IndexError):
            pass

    # Default to current month if not set
    if selected_year is None:
        selected_year = now.year
    if selected_month is None:
        selected_month = now.month

    # Validate month/year
    if not (1 <= selected_month <= 12):
        selected_month = now.month
    if not (2000 <= selected_year <= 2100):
        selected_year = now.year

    # Get selected month boundaries
    first_day = datetime(selected_year, selected_month, 1)
    if selected_month == 12:
        last_day = datetime(selected_year + 1, 1, 1)
    else:
        last_day = datetime(selected_year, selected_month + 1, 1)

    # 1. Records per day by discharge date for current month
    records_per_day = db.session.query(
        func.date(Record.date_of_discharge).label('date'),
        func.count(Record.id).label('count')
    ).filter(
        Record.date_of_discharge != None,
        Record.date_of_discharge >= first_day.date(),
        Record.date_of_discharge < last_day.date()
    ).group_by(
        func.date(Record.date_of_discharge)
    ).order_by('date').all()

    # 2. Status distribution by department (OPTIMIZED: Single GROUP BY query)
    dept_stats = db.session.query(
        Record.discharge_department,
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deceased'),
        func.sum(case(((Record.discharge_status == 'Виписаний') & (Record.date_of_death.is_(None)), 1), else_=0)).label('discharged'),
        func.sum(case(((Record.discharge_status == 'Опрацьовується') & (Record.date_of_death.is_(None)), 1), else_=0)).label('processing')
    ).filter(
        Record.discharge_department.isnot(None),
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= first_day.date(),
        Record.date_of_discharge < last_day.date()
    ).group_by(Record.discharge_department).all()

    status_by_dept = {}
    for dept, deceased, discharged, processing in dept_stats:
        status_by_dept[dept] = {
            'Помер': deceased or 0,
            'Виписаний': discharged or 0,
            'Опрацьовується': processing or 0
        }

    dept_list = sorted(status_by_dept.keys())

    # 3. Overall status distribution for current month (OPTIMIZED: Single query)
    current_stats = db.session.query(
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deceased'),
        func.sum(case(((Record.discharge_status == 'Виписаний') & (Record.date_of_death.is_(None)), 1), else_=0)).label('discharged'),
        func.sum(case(((Record.discharge_status == 'Опрацьовується') & (Record.date_of_death.is_(None)), 1), else_=0)).label('processing')
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= first_day.date(),
        Record.date_of_discharge < last_day.date()
    ).first()

    status_distribution = {
        'Помер': current_stats.deceased or 0,
        'Виписаний': current_stats.discharged or 0,
        'Опрацьовується': current_stats.processing or 0
    }

    # Calculate total records for selected month
    total_records = sum(status_distribution.values())

    # Get previous month data for trends
    if selected_month == 1:
        prev_month = 12
        prev_year = selected_year - 1
    else:
        prev_month = selected_month - 1
        prev_year = selected_year

    prev_first_day = datetime(prev_year, prev_month, 1)
    if prev_month == 12:
        prev_last_day = datetime(prev_year + 1, 1, 1)
    else:
        prev_last_day = datetime(prev_year, prev_month + 1, 1)

    # Previous month statistics (OPTIMIZED: Single query)
    prev_stats = db.session.query(
        func.sum(case((Record.date_of_death.isnot(None), 1), else_=0)).label('deceased'),
        func.sum(case(((Record.discharge_status == 'Виписаний') & (Record.date_of_death.is_(None)), 1), else_=0)).label('discharged'),
        func.sum(case(((Record.discharge_status == 'Опрацьовується') & (Record.date_of_death.is_(None)), 1), else_=0)).label('processing')
    ).filter(
        Record.date_of_discharge.isnot(None),
        Record.date_of_discharge >= prev_first_day.date(),
        Record.date_of_discharge < prev_last_day.date()
    ).first()

    prev_deceased = prev_stats.deceased or 0
    prev_discharged = prev_stats.discharged or 0
    prev_processing = prev_stats.processing or 0
    prev_total = prev_deceased + prev_discharged + prev_processing

    # Calculate trends
    trends = {
        'total': total_records - prev_total,
        'processing': status_distribution['Опрацьовується'] - prev_processing,
        'discharged': status_distribution['Виписаний'] - prev_discharged,
        'deceased': status_distribution['Помер'] - prev_deceased
    }

    # Month name for display
    selected_month_name = datetime(selected_year, selected_month, 1).strftime('%B %Y')

    return render_template(
        'admin_statistics.html',
        records_per_day=records_per_day,
        status_by_dept=status_by_dept,
        dept_list=dept_list,
        status_distribution=status_distribution,
        total_records=total_records,
        trends=trends,
        current_month=selected_month_name,
        selected_year=selected_year,
        selected_month=selected_month
    )
