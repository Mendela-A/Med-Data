# app/__init__.py - Application Factory Pattern
"""
Flask application factory для створення екземплярів додатку.
Використовується для легшого тестування та масштабування.
"""

from flask import Flask


def create_app(config_class=None):
    """
    Application Factory Pattern

    Args:
        config_class: Configuration class (default: Config from config.py)

    Returns:
        Flask application instance
    """
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    # Load configuration
    if config_class is None:
        from config import Config
        config_class = Config
    app.config.from_object(config_class)

    # Initialize extensions
    from app.extensions import init_extensions, login_manager
    init_extensions(app)

    # User loader callback
    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    # Auth blueprint (migrated)
    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    # TODO: Поступово додавати blueprints при рефакторингу
    # from app.blueprints.records import records_bp
    # app.register_blueprint(records_bp)

    # from app.blueprints.nszu import nszu_bp
    # app.register_blueprint(nszu_bp)

    # from app.blueprints.admin import admin_bp
    # app.register_blueprint(admin_bp)

    return app
