# app/blueprints/nszu/__init__.py
"""
NSZU Blueprint

Відповідає за:
- NSZU corrections list
- Add/Edit/Delete NSZU corrections
- Export to Excel
- Print PDF
"""

from flask import Blueprint

nszu_bp = Blueprint('nszu', __name__, url_prefix='/nszu')

# Import routes after blueprint creation to avoid circular imports
from . import routes
