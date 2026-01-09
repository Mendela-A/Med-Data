import click
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
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

        # base query for current month
        q = Record.query.options(joinedload(Record.creator)).filter(
            Record.created_at >= start,
            Record.created_at < end,
        )
        if getattr(current_user, 'role', None) != 'admin':
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
        if getattr(current_user, 'role', None) != 'admin':
            q = q.filter(Record.created_by == current_user.id)

        records = q.order_by(Record.date_of_discharge.desc(), Record.created_at.desc()).all()

        # create excel with openpyxl
        try:
            from openpyxl import Workbook
        except Exception:
            flash('Export requires openpyxl package. Please install it.')
            return redirect(url_for('index'))

        wb = Workbook()
        ws = wb.active
        ws.title = 'Vipiski'
        headers = ['ID','Дата виписки','ПІБ','Відділення','Лікар','Історія','К днів','Статус виписки','Статус','Дата смерті','Коментар','Створив','Створено']
        ws.append(headers)
        for r in records:
            ws.append([
                r.id,
                r.date_of_discharge.strftime('%d.%m.%Y') if r.date_of_discharge else '',
                r.full_name,
                r.discharge_department or '',
                r.treating_physician or '',
                r.history or '',
                r.k_days or '',
                r.discharge_status or '',
                r.status or '',
                r.date_of_death.strftime('%d.%m.%Y') if r.date_of_death else '',
                r.comment or '',
                r.creator.username if r.creator else r.created_by,
                r.created_at.strftime('%d.%m.%Y %H:%M') if r.created_at else '',
            ])

        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)

        filename = f"vipiski_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        return send_file(bio, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

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
    @role_required('operator')
    def add_record():

        if request.method == 'POST':
            date_str = request.form.get('date_of_discharge', '').strip()
            full_name = request.form.get('full_name', '').strip()
            discharge_department = request.form.get('discharge_department', '').strip()
            treating_physician = request.form.get('treating_physician', '').strip()
            history = request.form.get('history', '').strip()
            k_days = request.form.get('k_days', '').strip()
            status = request.form.get('status', '').strip()
            date_of_death_str = request.form.get('date_of_death', '').strip()

            # validate presence
            if not all([date_str, full_name, discharge_department, treating_physician, history, k_days, status]):
                flash('All fields are required')
                return redirect(url_for('add_record'))

            # validate date format DD.MM.YYYY for discharge
            from datetime import datetime
            try:
                date_of_discharge = datetime.strptime(date_str, '%d.%m.%Y').date()
            except ValueError:
                flash('Date of discharge must be in DD.MM.YYYY format')
                return redirect(url_for('add_record'))

            # validate k_days integer
            try:
                k_days_int = int(k_days)
            except ValueError:
                flash('"К днів" must be an integer')
                return redirect(url_for('add_record'))

            # If status == 'Помер', date_of_death is required
            date_of_death = None
            if status == 'Помер':
                if not date_of_death_str:
                    flash('When status is "Помер", "Дата смерті" is required')
                    return redirect(url_for('add_record'))

            if date_of_death_str:
                try:
                    date_of_death = datetime.strptime(date_of_death_str, '%d.%m.%Y').date()
                except ValueError:
                    flash('Date of death must be in DD.MM.YYYY format')
                    return redirect(url_for('add_record'))

                # date_of_death cannot be earlier than date_of_discharge
                if date_of_death < date_of_discharge:
                    flash('Дата смерті не може бути раніше дати виписки')
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
                date_of_death=date_of_death,
                created_by=current_user.id
            )
            db.session.add(r)
            db.session.commit()
            flash('Record added')
            # preserve filters if sent with form
            params = {}
            for k in ('discharge_status', 'treating_physician', 'history'):
                v = request.form.get(k, '').strip()
                if v:
                    params[k] = v
            return redirect(url_for('index', **params))

        # GET: pass through any filters so add form can include hidden fields
        return render_template('add_record.html', selected_status=request.args.get('discharge_status', ''), selected_physician=request.args.get('treating_physician', ''), history_q=request.args.get('history', ''))

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
            status = request.form.get('status', '').strip()
            discharge_status = request.form.get('discharge_status', '').strip()
            date_of_death_str = request.form.get('date_of_death', '').strip()
            comment = request.form.get('comment', '').strip()

            # validate presence of main fields
            if not all([date_str, full_name, discharge_department, treating_physician, history, k_days, status]):
                flash('All fields are required')
                return redirect(url_for('edit_record', record_id=record_id))

            from datetime import datetime
            try:
                date_of_discharge = datetime.strptime(date_str, '%d.%m.%Y').date()
            except ValueError:
                flash('Date of discharge must be in DD.MM.YYYY format')
                return redirect(url_for('edit_record', record_id=record_id))

            try:
                k_days_int = int(k_days)
            except ValueError:
                flash('"К днів" must be an integer')
                return redirect(url_for('edit_record', record_id=record_id))

            # date_of_death handling
            date_of_death = None
            if status == 'Помер':
                if not date_of_death_str:
                    flash('When status is "Помер", "Дата смерті" is required')
                    return redirect(url_for('edit_record', record_id=record_id))

            if date_of_death_str:
                try:
                    date_of_death = datetime.strptime(date_of_death_str, '%d.%m.%Y').date()
                except ValueError:
                    flash('Date of death must be in DD.MM.YYYY format')
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
            r.discharge_status = discharge_status or status
            r.status = status
            r.date_of_death = date_of_death
            r.comment = comment

            db.session.commit()
            flash('Record updated')
            params = {}
            for k in ('discharge_status', 'treating_physician', 'history'):
                v = request.form.get(k, '').strip()
                if v:
                    params[k] = v
            return redirect(url_for('index', **params))
            r.date_of_discharge = date_of_discharge
            r.full_name = full_name
            r.discharge_department = discharge_department
            r.treating_physician = treating_physician
            r.history = history
            r.k_days = k_days_int
            r.discharge_status = discharge_status or status
            r.status = status
            r.date_of_death = date_of_death
            r.comment = comment

            db.session.commit()
            flash('Record updated')
            return redirect(url_for('index'))

        # GET -> render form with record data (pass filters through if present)
        return render_template('edit_record.html', r=r, selected_status=request.args.get('discharge_status', ''), selected_physician=request.args.get('treating_physician', ''), history_q=request.args.get('history', ''))

    @app.route('/records/<int:record_id>/delete', methods=['POST'])
    @role_required('admin')
    def delete_record(record_id):
        r = Record.query.get_or_404(record_id)
        db.session.delete(r)
        db.session.commit()
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
        flash(f'User {u.username} deleted')
        return redirect(url_for('admin_users'))

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
