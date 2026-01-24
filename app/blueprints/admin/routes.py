# app/blueprints/admin/routes.py
"""
Admin routes

TODO: Перенести сюди роути з app.py:
- @app.route('/admin/users') -> admin_users()
- @app.route('/admin/add_user', methods=['GET', 'POST']) -> admin_add_user()
- @app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST']) -> admin_edit_user()
- @app.route('/admin/delete_user/<int:user_id>', methods=['POST']) -> admin_delete_user()
- @app.route('/admin/statistics') -> admin_statistics()
- @app.route('/admin/departments', methods=['GET', 'POST']) -> manage_departments()
- @app.route('/admin/departments/<int:dept_id>/delete', methods=['POST']) -> delete_department()
- @app.route('/admin/audit') -> audit_log()
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from models import User, Department, Audit, Record
from . import admin_bp


# TODO: Перенести роути сюди при рефакторингу
