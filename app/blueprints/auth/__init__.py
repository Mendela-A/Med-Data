# app/blueprints/auth/__init__.py
"""
Authentication Blueprint

Відповідає за:
- Login
- Logout
- Change Password
- User session management
"""

from flask import Blueprint

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Import routes after blueprint creation to avoid circular imports
from . import routes
