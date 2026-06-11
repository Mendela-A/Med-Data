# app/__init__.py - Application Factory Pattern
"""
Flask application factory для створення екземплярів додатку.
Використовується для легшого тестування та масштабування.
"""

from flask import Flask, jsonify, request, flash, redirect, url_for


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
    from app.extensions import init_extensions, login_manager, db
    init_extensions(app)

    # User loader callback
    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

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

    # Ambulatory blueprint
    from app.blueprints.ambulatory import ambulatory_bp
    app.register_blueprint(ambulatory_bp)

    # CSRF errors: для AJAX повертаємо JSON із зрозумілим поясненням,
    # інакше fetch показував оману «Помилка з'єднання з сервером»
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'Сесія застаріла. Оновіть сторінку (F5) і повторіть спробу — дані форми перед цим скопіюйте.',
            }), 400
        flash('Сесія застаріла. Спробуйте ще раз.', 'warning')
        return redirect(request.referrer or url_for('auth.login'))

    # Health check endpoint (no auth, no CSRF)
    @app.route('/health')
    def health():
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            return jsonify({'status': 'ok'}), 200
        except Exception:
            return jsonify({'status': 'error', 'detail': 'database unreachable'}), 503

    # CLI commands for database management
    import click
    from models import log_action
    from constants import VALID_ROLES

    @app.cli.command('init-db')
    def init_db():
        """Create database tables."""
        from models import seed_status_options
        db.create_all()
        if seed_status_options():
            click.echo('Seeded default status options.')
        click.echo('Initialized the database.')

    @app.cli.command('create-admin')
    @click.argument('username')
    @click.argument('password')
    def create_admin(username, password):
        """Create an admin user: flask create-admin <username> <password>"""
        if len(password) < 8:
            click.echo('Error: Password must be at least 8 characters.')
            return
        if User.query.filter_by(username=username).first():
            click.echo('User already exists.')
            return
        u = User(username=username, role='admin')
        u.set_password(password)
        db.session.add(u)
        db.session.flush()  # assigns u.id
        log_action(None, 'user.create', 'user', u.id, 'created by CLI')
        db.session.commit()
        app.logger.info(f'Admin user created by CLI: {username}')
        click.echo(f'Created admin user {username}')

    @app.cli.command('create-user')
    @click.argument('username')
    @click.argument('password')
    @click.argument('role', type=click.Choice(list(VALID_ROLES), case_sensitive=False))
    def create_user(username, password, role):
        """Create a user with specified role: flask create-user <username> <password> <role>"""
        if len(password) < 8:
            click.echo('Error: Password must be at least 8 characters.')
            return
        if User.query.filter_by(username=username).first():
            click.echo('User already exists.')
            return
        u = User(username=username, role=role.lower())
        u.set_password(password)
        db.session.add(u)
        db.session.flush()  # assigns u.id
        log_action(None, 'user.create', 'user', u.id, f'created by CLI with role={role}')
        db.session.commit()
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
    @click.option('--password', required=True, help='Admin password (min 8 chars)')
    def init_db_with_admin(username, password):
        """Create database tables and an admin user if not present."""
        from models import seed_status_options
        if len(password) < 8:
            click.echo('Error: Password must be at least 8 characters.')
            return
        db.create_all()
        seed_status_options()
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='admin')
            u.set_password(password)
            db.session.add(u)
            db.session.flush()  # assigns u.id
            log_action(None, 'user.create', 'user', u.id, 'created by init-db-with-admin')
            db.session.commit()
            app.logger.info(f'Admin user created during init: {username}')
            click.echo(f'Created admin user {username}')
        click.echo('Initialized the database (with admin).')

    # Jinja2 filter: format suma as "20 000" (no decimals, space thousands separator)
    def _format_suma(value):
        if value is None:
            return ''
        return f"{int(value):,}".replace(",", " ")

    app.jinja_env.filters['format_suma'] = _format_suma

    return app
