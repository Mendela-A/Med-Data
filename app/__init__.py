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

    # Admin blueprint (migrated)
    from app.blueprints.admin import admin_bp
    app.register_blueprint(admin_bp)

    # NSZU blueprint (migrated)
    from app.blueprints.nszu import nszu_bp
    app.register_blueprint(nszu_bp)

    # Records blueprint (migrated)
    from app.blueprints.records import records_bp
    app.register_blueprint(records_bp)

    # CLI commands for database management
    import click
    from models import log_action
    from app.extensions import db

    @app.cli.command('init-db')
    def init_db():
        """Create database tables."""
        db.create_all()
        click.echo('Initialized the database.')

    @app.cli.command('create-admin')
    @click.argument('username')
    @click.argument('password')
    def create_admin(username, password):
        """Create an admin user: flask create-admin <username> <password>"""
        if User.query.filter_by(username=username).first():
            click.echo('User already exists.')
            return
        u = User(username=username, role='admin')
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        # audit (CLI-created)
        try:
            log_action(None, 'user.create', 'user', u.id, 'created by CLI')
        except Exception:
            app.logger.exception('Failed to write audit log for create-admin')
        app.logger.info(f'Admin user created by CLI: {username}')
        click.echo(f'Created admin user {username}')

    @app.cli.command('create-user')
    @click.argument('username')
    @click.argument('password')
    @click.argument('role', type=click.Choice(['admin', 'editor', 'operator', 'viewer'], case_sensitive=False))
    def create_user(username, password, role):
        """Create a user with specified role: flask create-user <username> <password> <role>"""
        if User.query.filter_by(username=username).first():
            click.echo('User already exists.')
            return
        u = User(username=username, role=role.lower())
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        # audit (CLI-created)
        try:
            log_action(None, 'user.create', 'user', u.id, f'created by CLI with role={role}')
        except Exception:
            app.logger.exception('Failed to write audit log for create-user')
        app.logger.info(f'User created by CLI: {username} with role {role}')
        click.echo(f'Created {role} user {username}')

    @app.cli.command('backup-db')
    @click.option('--output', '-o', default=None, help='Output file path (default: data/backup_YYYYMMDD_HHMMSS.db)')
    def backup_db(output):
        """Create a safe backup of the SQLite database (works with WAL mode)."""
        import sqlite3
        import shutil
        import os
        from datetime import datetime

        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not db_uri.startswith('sqlite'):
            click.echo('Backup command only works with SQLite databases')
            return

        source_path = db_uri.replace('sqlite:///', '')
        if not os.path.exists(source_path):
            click.echo(f'Database file not found: {source_path}')
            return

        # Generate default output path
        if not output:
            backup_dir = os.path.dirname(source_path)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output = os.path.join(backup_dir, f'backup_{timestamp}.db')

        # Ensure output directory exists
        output_dir = os.path.dirname(output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        try:
            # Use SQLite backup API for safe hot backup
            source_conn = sqlite3.connect(source_path)
            dest_conn = sqlite3.connect(output)

            source_conn.backup(dest_conn)

            source_conn.close()
            dest_conn.close()

            # Get file size
            size_mb = os.path.getsize(output) / (1024 * 1024)
            click.echo(f'Backup created successfully: {output} ({size_mb:.2f} MB)')
            click.echo(f'Date: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}')
            app.logger.info(f'Database backup created: {output}')

        except Exception as e:
            click.echo(f'Backup failed: {e}')
            app.logger.exception('Database backup failed')

    @app.cli.command('init-db-with-admin')
    @click.option('--username', default='admin', help='Admin username')
    @click.option('--password', default='admin', help='Admin password')
    def init_db_with_admin(username, password):
        """Create database tables and an admin user if not present."""
        db.create_all()
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='admin')
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            try:
                log_action(None, 'user.create', 'user', u.id, 'created by init-db-with-admin')
            except Exception:
                app.logger.exception('Failed to write audit log for init-db-with-admin')
            app.logger.info(f'Admin user created during init: {username}')
            click.echo(f'Created admin user {username}')
        click.echo('Initialized the database (with admin).')

    return app
