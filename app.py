import click
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_migrate import Migrate
from config import Config
from models import db, User, Record, bcrypt, log_action, Department
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy.orm import joinedload

login_manager = LoginManager()
login_manager.login_view = 'login'

def create_app(config_class=Config):
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(config_class)

    # setup logging: prefer stdout (good for Docker); enable file logging with LOG_TO_FILE=1
    import logging
    import os, sys
    log_to_file = os.environ.get('LOG_TO_FILE') == '1'
    if log_to_file:
        from logging.handlers import RotatingFileHandler
        if not os.path.exists('logs'):
            os.makedirs('logs')
        try:
            file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=3)
            file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
        except Exception:
            # fallback to stderr if file logging cannot be configured
            app.logger.addHandler(logging.StreamHandler(sys.stderr))
            app.logger.warning('Could not configure file logging; logs will be sent to stderr')
    else:
        # In containers, it's best to log to stdout
        app.logger.addHandler(logging.StreamHandler(sys.stdout))
    app.logger.setLevel(logging.INFO)
    app.logger.info('Application startup')

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    # Ensure data directory exists when using a local sqlite file
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception:
                app.logger.warning(f'Could not create directory for sqlite DB: {db_dir}')

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from functools import wraps
    def role_required(role):
        """Decorator to require a specific role or admin."""
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if not current_user.is_authenticated:
                    return redirect(url_for('login'))
                # admin has all rights
                if getattr(current_user, 'role', None) != role and getattr(current_user, 'role', None) != 'admin':
                    flash('Access denied')
                    return redirect(url_for('index'))
                return f(*args, **kwargs)
            return decorated_function
        return decorator

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

        # support a toggle to show all months
        show_all = request.args.get('all_months', '').lower() in ('1', 'true', 'yes')

        # base query (by default for current month, unless show_all)
        q = Record.query.options(joinedload(Record.creator))
        if not show_all:
            q = q.filter(
                Record.created_at >= start,
                Record.created_at < end,
            )
        # Operators see only their own records; editors and admins see all records
        role = getattr(current_user, 'role', None)
        if role == 'operator':
            q = q.filter(Record.created_by == current_user.id)

        # --- filtering from query params ---
        selected_status = request.args.get('discharge_status', '').strip()
        selected_physician = request.args.get('treating_physician', '').strip()
        history_q = request.args.get('history', '').strip()

        conditions = []
        if selected_status:
            conditions.append(Record.discharge_status == selected_status)
        if selected_physician:
            conditions.append(Record.treating_physician == selected_physician)
        if history_q:
            conditions.append(Record.history.contains(history_q))
        if conditions:
            q = q.filter(*conditions)

        # values for dropdowns (distinct non-null values)
        statuses = [s[0] for s in db.session.query(Record.discharge_status).distinct().filter(Record.discharge_status != None).order_by(Record.discharge_status).all()]
        physicians = [p[0] for p in db.session.query(Record.treating_physician).distinct().filter(Record.treating_physician != None).order_by(Record.treating_physician).all()]

        # count and results
        count = q.count()
        records = q.order_by(Record.date_of_discharge.desc(), Record.created_at.desc()).all()

        return render_template('dashboard.html', records=records, statuses=statuses, physicians=physicians, selected_status=selected_status, selected_physician=selected_physician, history_q=history_q, count=count)

    @app.route('/export', methods=['POST'])
    @role_required('editor')
    def export():
        # editors and admins can export records within a date range (by date_of_discharge)
        from datetime import datetime
        from io import BytesIO
        try:
            from_str = request.form.get('from_date', '').strip()
            to_str = request.form.get('to_date', '').strip()
            if not from_str or not to_str:
                flash('Please provide both From and To dates for export')
                return redirect(url_for('index'))
            from_d = datetime.strptime(from_str, '%Y-%m-%d').date()
            to_d = datetime.strptime(to_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format for export (use the date picker)')
            return redirect(url_for('index'))

        if from_d > to_d:
            flash('From date cannot be after To date')
            return redirect(url_for('index'))

        q = Record.query.options(joinedload(Record.creator)).filter(
            Record.date_of_discharge != None,
            Record.date_of_discharge >= from_d,
            Record.date_of_discharge <= to_d,
        )
        # apply active filters if provided (discharge_status, treating_physician, history)
        discharge_status = request.form.get('discharge_status', '').strip()
        treating_physician = request.form.get('treating_physician', '').strip()
        history_q = request.form.get('history', '').strip()
        if discharge_status:
            q = q.filter(Record.discharge_status == discharge_status)
        if treating_physician:
            q = q.filter(Record.treating_physician == treating_physician)
        if history_q:
            q = q.filter(Record.history.contains(history_q))

        # operators can only export their own records; editors and admins can export all
        if getattr(current_user, 'role', None) == 'operator':
            q = q.filter(Record.created_by == current_user.id)

        records = q.order_by(Record.date_of_discharge.desc(), Record.created_at.desc()).all()

        if not records:
            flash('No records found for selected date range and filters')
            return redirect(url_for('index'))

        # create excel with openpyxl, format headers bold, and auto-size columns
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
            from openpyxl.utils import get_column_letter
        except Exception:
            flash('Export requires openpyxl package. Please install it.')
            return redirect(url_for('index'))

        wb = Workbook()
        ws = wb.active
        ws.title = 'Vipiski'

        # headers: include all columns from the Record model
        headers = ['ID','Дата виписки','ПІБ','Відділення','Лікар','Історія','К днів','Статус виписки','Дата смерті','Коментар','Створив','Створено']
        ws.append(headers)

        # append rows
        for r in records:
            ws.append([
                r.id,
                r.date_of_discharge.strftime('%d.%m.%Y') if r.date_of_discharge else '',
                r.full_name,
                r.discharge_department or '',
                r.treating_physician or '',
                r.history or '',
                r.k_days if r.k_days is not None else '',
                r.discharge_status or '',
                r.date_of_death.strftime('%d.%m.%Y') if r.date_of_death else '',
                r.comment or '',
                r.creator.username if r.creator else r.created_by,
                r.created_at.strftime('%d.%m.%Y %H:%M') if r.created_at else '',
            ])

        # style headers bold
        bold = Font(bold=True)
        for cell in ws[1]:
            cell.font = bold

        # auto width columns
        for i, column_cells in enumerate(ws.columns, 1):
            max_length = 0
            for cell in column_cells:
                try:
                    value = str(cell.value) if cell.value is not None else ''
                except Exception:
                    value = ''
                if len(value) > max_length:
                    max_length = len(value)
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[get_column_letter(i)].width = adjusted_width

        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)

        # audit export
        try:
            log_action(current_user.id, 'export', 'export', None, f'from={from_d} to={to_d} discharge_status={discharge_status} treating_physician={treating_physician} history={history_q}')
        except Exception:
            app.logger.exception('Failed to write audit log for export')
        app.logger.info(f'Export by {getattr(current_user, "username", "unknown")}: from {from_d} to {to_d} count={len(records)}')

        filename = f"vipiski_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        return send_file(bio, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        # Public registration is disabled. Only administrators can create new users via the admin UI.
        flash('Реєстрація вимкнена. Нових користувачів створює лише адміністратор.')
        return redirect(url_for('login'))

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
    @role_required('operator')
    def add_record():

        if request.method == 'POST':
            date_str = request.form.get('date_of_discharge', '').strip()
            full_name = request.form.get('full_name', '').strip()
            discharge_department = request.form.get('discharge_department', '').strip()
            treating_physician = request.form.get('treating_physician', '').strip()
            history = request.form.get('history', '').strip()
            k_days = request.form.get('k_days', '').strip()
            date_of_death_str = request.form.get('date_of_death', '').strip()

            # date_of_death (if provided) will indicate death; validate format if present
            if not all([date_str, full_name, discharge_department, treating_physician, history, k_days]):
                flash('Будь ласка, заповніть усі обов\'язкові поля')
                return redirect(url_for('add_record'))

            # validate date format: accept DD.MM.YYYY or YYYY-MM-DD (HTML date input)
            from datetime import datetime
            date_of_discharge = None
            for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
                try:
                    date_of_discharge = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if date_of_discharge is None:
                flash('Date of discharge must be in DD.MM.YYYY or YYYY-MM-DD format')
                return redirect(url_for('add_record'))

            # validate k_days integer
            try:
                k_days_int = int(k_days)
            except ValueError:
                flash('"К днів" must be an integer')
                return redirect(url_for('add_record'))

            date_of_death = None
            if date_of_death_str:
                date_of_death = None
                for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
                    try:
                        date_of_death = datetime.strptime(date_of_death_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if date_of_death is None:
                    flash('Date of death must be in DD.MM.YYYY or YYYY-MM-DD format')
                    return redirect(url_for('add_record'))

                # date_of_death cannot be earlier than date_of_discharge
                if date_of_death < date_of_discharge:
                    flash('Дата смерті не може бути раніше дати виписки')
                    return redirect(url_for('add_record'))

            # Do not auto-fill discharge_status from status for operator adds; allow explicit discharge_status if provided
            discharge_status = request.form.get('discharge_status', '').strip()

            r = Record(
                date_of_discharge=date_of_discharge,
                full_name=full_name,
                discharge_department=discharge_department,
                treating_physician=treating_physician,
                history=history,
                k_days=k_days_int,
                discharge_status=discharge_status or None,
                date_of_death=date_of_death,
                created_by=current_user.id
            )
            db.session.add(r)
            db.session.commit()
            try:
                log_action(current_user.id, 'record.create', 'record', r.id, f'full_name={r.full_name}')
            except Exception:
                app.logger.exception('Failed to write audit log for record.create')
            app.logger.info(f'Record created: {r.id} by {current_user.username}')
            flash('Record added')
            # preserve filters if sent with form (check prefixed filter_* fields to avoid shadowing actual inputs)
            params = {}
            for k in ('discharge_status', 'treating_physician', 'history'):
                v = request.form.get(f'filter_{k}', '').strip()
                if v:
                    params[k] = v
            return redirect(url_for('index', **params))

        # GET: pass through any filters so add form can include hidden fields and departments
        departments = Department.query.order_by(Department.name).all()
        return render_template('add_record.html', selected_status=request.args.get('discharge_status', ''), selected_physician=request.args.get('treating_physician', ''), history_q=request.args.get('history', ''), departments=departments, selected_department=request.args.get('discharge_department', ''))

    @app.route('/records/<int:record_id>/edit', methods=['GET', 'POST'])
    @role_required('editor')
    def edit_record(record_id):

        r = Record.query.get_or_404(record_id)

        if request.method == 'POST':
            # gather form fields
            date_str = request.form.get('date_of_discharge', '').strip()
            full_name = request.form.get('full_name', '').strip()
            discharge_department = request.form.get('discharge_department', '').strip()
            treating_physician = request.form.get('treating_physician', '').strip()
            history = request.form.get('history', '').strip()
            k_days = request.form.get('k_days', '').strip()
            discharge_status = request.form.get('discharge_status', '').strip()
            date_of_death_str = request.form.get('date_of_death', '').strip()
            comment = request.form.get('comment', '').strip()

            # validate presence of main fields (status is optional; only required when it is 'Помер')
            if not all([date_str, full_name, discharge_department, treating_physician, history, k_days, discharge_status]):
                flash('Будь ласка, заповніть усі обов\'язкові поля')
                return redirect(url_for('edit_record', record_id=record_id))

            from datetime import datetime
            date_of_discharge = None
            for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
                try:
                    date_of_discharge = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if date_of_discharge is None:
                flash('Date of discharge must be in DD.MM.YYYY or YYYY-MM-DD format')
                return redirect(url_for('edit_record', record_id=record_id))

            try:
                k_days_int = int(k_days)
            except ValueError:
                flash('"К днів" must be an integer')
                return redirect(url_for('edit_record', record_id=record_id))

            # date_of_death handling
            date_of_death = None

            if date_of_death_str:
                date_of_death = None
                for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
                    try:
                        date_of_death = datetime.strptime(date_of_death_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if date_of_death is None:
                    flash('Date of death must be in DD.MM.YYYY or YYYY-MM-DD format')
                    return redirect(url_for('edit_record', record_id=record_id))

                if date_of_death < date_of_discharge:
                    flash('Дата смерті не може бути раніше дати виписки')
                    return redirect(url_for('edit_record', record_id=record_id))

            # apply changes
            r.date_of_discharge = date_of_discharge
            r.full_name = full_name
            r.discharge_department = discharge_department
            r.treating_physician = treating_physician
            r.history = history
            r.k_days = k_days_int
            r.discharge_status = discharge_status
            r.date_of_death = date_of_death
            r.comment = comment

            db.session.commit()
            try:
                log_action(current_user.id, 'record.update', 'record', r.id, f'full_name={r.full_name}')
            except Exception:
                app.logger.exception('Failed to write audit log for record.update')
            app.logger.info(f'Record updated: {r.id} by {current_user.username}')
            flash('Record updated')
            params = {}
            for k in ('discharge_status', 'treating_physician', 'history'):
                v = request.form.get(f'filter_{k}', '').strip()
                if v:
                    params[k] = v
            return redirect(url_for('index', **params))

        # GET -> render form with record data (pass filters through if present) and departments
        departments = Department.query.order_by(Department.name).all()
        return render_template('edit_record.html', r=r, selected_status=request.args.get('discharge_status', ''), selected_physician=request.args.get('treating_physician', ''), history_q=request.args.get('history', ''), departments=departments)

    @app.route('/records/<int:record_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_record(record_id):
        r = Record.query.get_or_404(record_id)
        db.session.delete(r)
        db.session.commit()
        try:
            log_action(current_user.id, 'record.delete', 'record', r.id, f'full_name={r.full_name}')
        except Exception:
            app.logger.exception('Failed to write audit log for record.delete')
        app.logger.info(f'Record deleted: {r.id} by {current_user.username}')
        flash('Record deleted')
        # preserve filters from form (if any)
        params = {}
        for k in ('discharge_status', 'treating_physician', 'history'):
            v = request.form.get(k, '').strip()
            if v:
                params[k] = v
        return redirect(url_for('index', **params))

    # --- Admin: user management ---
    @app.route('/admin/users')
    @role_required('admin')
    def admin_users():
        users = User.query.order_by(User.username).all()
        return render_template('admin_users.html', users=users)

    @app.route('/admin/users/create', methods=['POST'])
    @role_required('admin')
    def admin_create_user():
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip() or 'operator'

        if not username or not password:
            flash('Username and password are required')
            return redirect(url_for('admin_users'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('admin_users'))

        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        # audit & log
        try:
            log_action(current_user.id, 'user.create', 'user', u.id, f'role={role}')
        except Exception:
            app.logger.exception('Failed to write audit log for user.create')
        app.logger.info(f'User created: {username} by {current_user.username}')
        flash(f'User {username} created')
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
    @role_required('admin')
    def admin_delete_user(user_id):
        if current_user.id == user_id:
            flash('You cannot delete yourself')
            return redirect(url_for('admin_users'))
        u = User.query.get_or_404(user_id)
        db.session.delete(u)
        db.session.commit()
        try:
            log_action(current_user.id, 'user.delete', 'user', u.id, f'username={u.username}')
        except Exception:
            app.logger.exception('Failed to write audit log for user.delete')
        app.logger.info(f'User deleted: {u.username} by {current_user.username}')
        flash(f'User {u.username} deleted')
        return redirect(url_for('admin_users'))

    # Departments management
    @app.route('/admin/departments')
    @role_required('admin')
    def admin_departments():
        departments = Department.query.order_by(Department.name).all()
        return render_template('admin_departments.html', departments=departments)

    @app.route('/admin/departments/create', methods=['POST'])
    @role_required('admin')
    def admin_create_department():
        name = request.form.get('name', '').strip()
        if not name:
            flash('Name is required')
            return redirect(url_for('admin_departments'))
        if Department.query.filter_by(name=name).first():
            flash('Department already exists')
            return redirect(url_for('admin_departments'))
        d = Department(name=name)
        db.session.add(d)
        db.session.commit()
        try:
            log_action(current_user.id, 'department.create', 'department', d.id, f'name={name}')
        except Exception:
            app.logger.exception('Failed to write audit log for department.create')
        app.logger.info(f'Department created: {name} by {current_user.username}')
        flash(f'Department {name} created')
        return redirect(url_for('admin_departments'))

    @app.route('/admin/departments/<int:dept_id>/delete', methods=['POST'])
    @role_required('admin')
    def admin_delete_department(dept_id):
        d = Department.query.get_or_404(dept_id)
        # prevent deletion if department in use
        in_use = Record.query.filter(Record.discharge_department == d.name).count()
        if in_use:
            flash('Cannot delete department which is in use by records')
            return redirect(url_for('admin_departments'))
        db.session.delete(d)
        db.session.commit()
        try:
            log_action(current_user.id, 'department.delete', 'department', d.id, f'name={d.name}')
        except Exception:
            app.logger.exception('Failed to write audit log for department.delete')
        app.logger.info(f'Department deleted: {d.name} by {current_user.username}')
        flash(f'Department {d.name} deleted')
        return redirect(url_for('admin_departments'))

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


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
