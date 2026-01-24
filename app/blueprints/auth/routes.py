# app/blueprints/auth/routes.py
"""
Authentication routes
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required

from models import User
from . import auth_bp


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Login page and authentication handler

    GET: Display login form
    POST: Authenticate user and redirect to dashboard
    """
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
