import click
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_migrate import Migrate
from config import Config
from models import db, User, Record, bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy.orm import joinedload

login_manager = LoginManager()
login_manager.login_view = 'login'

def create_app(config_class=Config):
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(config_class)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.route('/')
    @login_required
    def index():
        from datetime import datetime
        now = datetime.utcnow()
        start = datetime(now.year, now.month, 1)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1)
        else:
            end = datetime(now.year, now.month + 1, 1)

        records = (
            Record.query.options(joinedload(Record.creator))
            .filter(
                Record.created_by == current_user.id,
                Record.created_at >= start,
                Record.created_at < end,
            )
            .order_by(Record.date_of_discharge.desc(), Record.created_at.desc())
            .all()
        )

        return render_template('dashboard.html', records=records)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if not username or not password:
                flash('Please provide username and password')
                return redirect(url_for('register'))
            if User.query.filter_by(username=username).first():
                flash('Username already exists')
                return redirect(url_for('register'))
            u = User(username=username, role='operator')
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            return redirect(url_for('index'))
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('index'))
            flash('Invalid username or password')
            return redirect(url_for('login'))
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/records/add', methods=['GET', 'POST'])
    @login_required
    def add_record():
        # only operators can add records
        if getattr(current_user, 'role', None) != 'operator':
            flash('Only operators can add records')
            return redirect(url_for('index'))

        if request.method == 'POST':
            date_str = request.form.get('date_of_discharge', '').strip()
            full_name = request.form.get('full_name', '').strip()
            discharge_department = request.form.get('discharge_department', '').strip()
            treating_physician = request.form.get('treating_physician', '').strip()
            history = request.form.get('history', '').strip()
            k_days = request.form.get('k_days', '').strip()
            status = request.form.get('status', '').strip()

            # validate presence
            if not all([date_str, full_name, discharge_department, treating_physician, history, k_days, status]):
                flash('All fields are required')
                return redirect(url_for('add_record'))

            # validate date format DD.MM.YYYY
            from datetime import datetime
            try:
                date_of_discharge = datetime.strptime(date_str, '%d.%m.%Y').date()
            except ValueError:
                flash('Date must be in DD.MM.YYYY format')
                return redirect(url_for('add_record'))

            # validate k_days integer
            try:
                k_days_int = int(k_days)
            except ValueError:
                flash('"К днів" must be an integer')
                return redirect(url_for('add_record'))

            r = Record(
                date_of_discharge=date_of_discharge,
                full_name=full_name,
                discharge_department=discharge_department,
                treating_physician=treating_physician,
                history=history,
                k_days=k_days_int,
                discharge_status=status,
                status=status,
                created_by=current_user.id
            )
            db.session.add(r)
            db.session.commit()
            flash('Record added')
            return redirect(url_for('index'))

        return render_template('add_record.html')

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
        click.echo(f'Created admin user {username}')

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
