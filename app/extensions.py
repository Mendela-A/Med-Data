# app/extensions.py
"""
Flask extensions initialized here to avoid circular imports

Extensions are initialized here and then imported in __init__.py
"""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_caching import Cache

# Import db and bcrypt from models to avoid duplicate instances
from models import db, bcrypt, init_db_events

# Initialize other extensions (without app)
migrate = Migrate()
login_manager = LoginManager()
cache = Cache()


def init_extensions(app):
    """
    Initialize all Flask extensions with the app instance

    Args:
        app: Flask application instance
    """
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    init_db_events(app)

    # Initialize cache with simple in-memory storage
    cache.init_app(app, config={
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 900  # 15 minutes default
    })

    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Будь ласка, увійдіть для доступу до цієї сторінки.'
    login_manager.login_message_category = 'info'
