# app/blueprints/records/routes.py
"""
Records routes

TODO: Перенести сюди роути з app.py:
- @app.route('/') -> index() (dashboard)
- @app.route('/add_record', methods=['GET', 'POST']) -> add_record()
- @app.route('/api/add_record', methods=['POST']) -> api_add_record()
- @app.route('/<int:record_id>/edit', methods=['GET', 'POST']) -> edit_record()
- @app.route('/api/edit_record/<int:record_id>', methods=['POST']) -> api_edit_record()
- @app.route('/<int:record_id>/delete', methods=['POST']) -> delete_record()
- @app.route('/export', methods=['POST']) -> export()
- @app.route('/records/print', methods=['POST']) -> print_records()
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from models import Record, User, Department
from . import records_bp


# TODO: Перенести роути сюди при рефакторингу
