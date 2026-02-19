# app/blueprints/auth/routes.py
"""
Authentication routes
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter
from models import User, log_action
from . import auth_bp


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    """
    Login page and authentication handler

    GET: Display login form
    POST: Authenticate user and redirect to dashboard
    """
    if current_user.is_authenticated:
        return redirect(url_for('records.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('records.index'))

        flash('Невірне ім\'я користувача або пароль', 'danger')
        return redirect(url_for('auth.login'))

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """
    Logout current user and redirect to login page
    """
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Allow the current user to change their own password."""
    current_password = request.form.get('current_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not all([current_password, new_password, confirm_password]):
        flash('Будь ласка, заповніть усі поля', 'warning')
        return redirect(request.referrer or url_for('records.index'))

    if not current_user.check_password(current_password):
        flash('Поточний пароль невірний', 'danger')
        return redirect(request.referrer or url_for('records.index'))

    if len(new_password) < 8:
        flash('Новий пароль повинен містити щонайменше 8 символів', 'warning')
        return redirect(request.referrer or url_for('records.index'))

    if new_password != confirm_password:
        flash('Паролі не співпадають', 'warning')
        return redirect(request.referrer or url_for('records.index'))

    current_user.set_password(new_password)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Помилка при збереженні пароля', 'danger')
        return redirect(request.referrer or url_for('records.index'))

    try:
        log_action(current_user.id, 'user.password_change', 'user', current_user.id, 'self-service')
    except Exception:
        pass

    flash('Пароль успішно змінено', 'success')
    return redirect(url_for('records.index'))
