# app/blueprints/auth/routes.py
"""
Authentication routes

TODO: Перенести сюди роути з app.py:
- @app.route('/login', methods=['GET', 'POST']) -> login()
- @app.route('/logout') -> logout()
- @app.route('/change_password', methods=['GET', 'POST']) -> change_password()
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from models import User
from . import auth_bp


# TODO: Перенести роути сюди при рефакторингу
