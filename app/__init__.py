# app/__init__.py - Application Factory Pattern
"""
Flask application factory для створення екземплярів додатку.
Використовується для легшого тестування та масштабування.
"""

import os

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

    # Statisty blueprint
    from app.blueprints.statisty import statisty_bp
    app.register_blueprint(statisty_bp)

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

    # Lightweight health check — only verifies the process is alive (no DB query).
    # SQLite is always reachable if the Flask process responds; a DB query here
    # adds 2880 unnecessary writes/day from Docker's 30s healthcheck interval.
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'}), 200

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

    def _nz(value):
        """Returns empty string for None and 0."""
        if value is None or value == 0:
            return ''
        return value

    app.jinja_env.filters['nz'] = _nz

    # Кеш-бастинг статики: nginx віддає /static/ з `expires 1d`, тож без версії
    # в URL зміни CSS/JS доходили до користувачів лише через добу або Ctrl+F5.
    # url_defaults спрацьовує на кожен url_for('static', ...), тому шаблони
    # правити не треба. mtime кешуємо — у проді файли не змінюються між
    # рестартами, а в дебазі перечитуємо, щоб не заважати розробці.
    _static_versions = {}

    @app.url_defaults
    def _add_static_version(endpoint, values):
        if endpoint != 'static' or 'filename' not in values:
            return
        filename = values['filename']
        version = _static_versions.get(filename)
        if version is None or app.debug:
            try:
                version = int(os.stat(os.path.join(app.static_folder, filename)).st_mtime)
            except OSError:
                # Файла немає (або недоступний) — лишаємо URL без версії
                return
            _static_versions[filename] = version
        values['v'] = version

    return app
