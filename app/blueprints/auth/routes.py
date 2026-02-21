# app/blueprints/auth/routes.py
"""
Authentication routes
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter, bcrypt
from models import User, log_action
from utils import safe_referrer
from . import auth_bp

# Pre-computed dummy hash for timing-safe login (prevents username enumeration)
_DUMMY_HASH = bcrypt.generate_password_hash('dummy-timing-placeholder').decode('utf-8')


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

        if user is None:
            # Perform dummy hash check to equalize timing (prevents username enumeration)
            bcrypt.check_password_hash(_DUMMY_HASH, password)
        elif user.check_password(password):
            login_user(user)
            return redirect(url_for('records.index'))

        flash('Невірне ім\'я користувача або пароль', 'danger')
        return redirect(url_for('auth.login'))

    return render_template('login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    Logout current user and redirect to login page
    """
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['POST'])
@limiter.limit("5 per minute")
@login_required
def change_password():
    """Allow the current user to change their own password."""
    current_password = request.form.get('current_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not all([current_password, new_password, confirm_password]):
        flash('Будь ласка, заповніть усі поля', 'warning')
        return redirect(safe_referrer())

    if not current_user.check_password(current_password):
        flash('Поточний пароль невірний', 'danger')
        return redirect(safe_referrer())

    if len(new_password) < 8:
        flash('Новий пароль повинен містити щонайменше 8 символів', 'warning')
        return redirect(safe_referrer())

    if new_password != confirm_password:
        flash('Паролі не співпадають', 'warning')
        return redirect(safe_referrer())

    current_user.set_password(new_password)
    try:
        log_action(current_user.id, 'user.password_change', 'user', current_user.id, 'self-service')
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Помилка при збереженні пароля', 'danger')
        return redirect(safe_referrer())

    flash('Пароль успішно змінено', 'success')
    return redirect(url_for('records.index'))
