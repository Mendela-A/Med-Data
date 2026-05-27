# tests/test_admin_audit.py
import datetime
import pytest
from app import create_app
from models import db, User, Department, DailyReport, Audit, PrintSettings

class TestConfig:
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test_secret_key'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        # Seed print settings
        ps = PrintSettings(id=1)
        db.session.add(ps)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    with app.app_context():
        yield app.test_client()

def ensure_user(username, role='admin', password='pass'):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return u

def ensure_department(name='Терапевтичне', row_no=1):
    d = Department.query.filter_by(name=name).first()
    if not d:
        d = Department(name=name, row_no=row_no)
        db.session.add(d)
        db.session.commit()
    return d

def login(client, username='admin', password='pass'):
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

def test_audit_logs_login_and_logout(app, client):
    """Test that login, login failure, and logout actions are logged properly."""
    with app.app_context():
        u = ensure_user('admin_user', role='admin', password='secretpassword')

        # Test login failure
        response = client.post('/login', data={'username': 'admin_user', 'password': 'wrongpassword'}, follow_redirects=True)
        assert response.status_code == 200
        
        # Check login failed log
        log_failed = Audit.query.filter_by(action='user.login_failed').first()
        assert log_failed is not None
        assert "attempted_username=admin_user" in log_failed.details

        # Test login success
        response = client.post('/login', data={'username': 'admin_user', 'password': 'secretpassword'}, follow_redirects=True)
        assert response.status_code == 200

        # Check login success log
        log_success = Audit.query.filter_by(action='user.login').first()
        assert log_success is not None
        assert log_success.actor_id == u.id
        assert "username=admin_user" in log_success.details

        # Test logout
        response = client.post('/logout', follow_redirects=True)
        assert response.status_code == 200

        # Check logout log
        log_logout = Audit.query.filter_by(action='user.logout').first()
        assert log_logout is not None
        assert log_logout.actor_id == u.id
        assert "username=admin_user" in log_logout.details

def test_audit_logs_daily_report_and_print_settings(app, client):
    """Test that Form 007 edit and PrintSettings modifications are logged in audit logs."""
    with app.app_context():
        u = ensure_user('admin')
        dept = ensure_department('Терапія', row_no=1)
        login(client)

        # 1. Edit Form 007 (DailyReport save)
        date_str = "2026-05-27"
        response = client.post(
            f'/statisty/form007/{date_str}/edit',
            data={
                f'beds_total_{dept.id}': '30',
                f'patients_start_{dept.id}': '10',
                f'admitted_total_{dept.id}': '5',
                f'discharged_total_{dept.id}': '2'
            },
            follow_redirects=True
        )
        assert response.status_code == 200

        # Check audit log for Form 007
        log_007 = Audit.query.filter_by(action='daily_report.update').first()
        assert log_007 is not None
        assert log_007.actor_id == u.id
        assert f"date={date_str}" in log_007.details
        assert "Терапія" in log_007.details

        # 2. Update PrintSettings
        response = client.post(
            '/statisty/print-settings',
            data={
                'org_name': 'КНП Калуська ЦРЛ',
                'signer1_name': 'Іван Іванов',
                'signer2_name': 'Петро Петров'
            },
            follow_redirects=True
        )
        assert response.status_code == 200

        # Check audit log for PrintSettings
        log_print = Audit.query.filter_by(action='print_settings.update').first()
        assert log_print is not None
        assert log_print.actor_id == u.id
        assert "org_name=КНП Калуська ЦРЛ" in log_print.details
        assert "signer1=Іван Іванов" in log_print.details

def test_admin_audit_filtering_and_search(app, client):
    """Test the admin audit route keyword search and HTMX rendering."""
    with app.app_context():
        u = ensure_user('admin')
        login(client)

        # Manually create some logs
        log1 = Audit(actor_id=u.id, action='user.login', details='ip=127.0.0.1, username=admin')
        log2 = Audit(actor_id=u.id, action='daily_report.update', details='date=2026-05-27, depts=Терапія')
        log3 = Audit(actor_id=u.id, action='record.create', target_type='record', target_id=123, details='full_name=Тестовий Пацієнт')
        db.session.add_all([log1, log2, log3])
        db.session.commit()

        # Test normal GET view
        response = client.get('/admin/audit')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Журнал дій системного аудиту" in html
        assert "user.login" in html
        assert "daily_report.update" in html

        # Test keyword search 'Терапія'
        response = client.get('/admin/audit', query_string={'q_search': 'Терапія'})
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "daily_report.update" in html
        assert "ip=127.0.0.1" not in html

        # Test keyword search by target ID '123'
        response = client.get('/admin/audit', query_string={'q_search': '123'})
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "record.create" in html
        assert "ip=127.0.0.1" not in html

        # Test HTMX partial rendering
        response = client.get('/admin/audit', headers={'HX-Request': 'true'}, query_string={'q_search': 'login'})
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        # Should contain the partial container, but not the base layout boilerplate
        assert "audit-table-container" in html
        assert "user.login" in html
        assert "Журнал дій системного аудиту" not in html
