# app/blueprints/ambulatory/__init__.py
"""
Ambulatory Blueprint

Відповідає за:
- Список амбулаторних записів (Амбулаторна доп.)
- Додавання, редагування та видалення записів
- Експорт в Excel
- Друк PDF
"""

from flask import Blueprint

ambulatory_bp = Blueprint('ambulatory', __name__, url_prefix='/ambulatory')

# Import routes after blueprint creation to avoid circular imports
from . import routes
