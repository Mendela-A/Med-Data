# app/blueprints/records/__init__.py
"""
Records Blueprint

Відповідає за:
- Dashboard (список записів)
- Add/Edit/Delete records
- Export to Excel
- Print PDF
"""

from flask import Blueprint

records_bp = Blueprint('records', __name__, url_prefix='/')

# Import routes after blueprint creation to avoid circular imports
from . import routes
