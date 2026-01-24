# app/blueprints/nszu/routes.py
"""
NSZU routes

TODO: Перенести сюди роути з app.py:
- @app.route('/nszu') -> nszu_list()
- @app.route('/nszu/add', methods=['GET', 'POST']) -> nszu_add()
- @app.route('/api/nszu/add', methods=['POST']) -> api_nszu_add()
- @app.route('/nszu/<int:correction_id>/edit', methods=['GET', 'POST']) -> nszu_edit()
- @app.route('/nszu/<int:correction_id>/delete', methods=['POST']) -> nszu_delete()
- @app.route('/nszu/export', methods=['POST']) -> nszu_export()
- @app.route('/nszu/print', methods=['POST']) -> print_nszu()
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from models import NSZUCorrection, User
from . import nszu_bp


# TODO: Перенести роути сюди при рефакторингу
