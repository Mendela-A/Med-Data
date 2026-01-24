# app/blueprints/admin/__init__.py
"""
Admin Blueprint

Відповідає за:
- User management (list, add, edit, delete)
- Department management
- Statistics
- Audit logs
"""

from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Import routes after blueprint creation to avoid circular imports
from . import routes
