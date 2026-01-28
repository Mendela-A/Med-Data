# app/blueprints/auth/__init__.py
"""
Authentication Blueprint

Відповідає за:
- Login
- Logout
- User session management
"""

from flask import Blueprint

# No url_prefix to keep /login and /logout URLs the same
auth_bp = Blueprint('auth', __name__)

# Import routes after blueprint creation to avoid circular imports
from . import routes
