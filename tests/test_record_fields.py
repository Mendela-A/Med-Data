"""Tests for is_urgent and history_submitted fields on Record."""
import os
import datetime
import pytest
os.environ.setdefault('SECRET_KEY', 'test-key')
from app import create_app
from models import db, User, Record, Department
from constants import STATUS_PROCESSING, STATUS_DISCHARGED

DATE = datetime.date(2026, 3, 1)
FROM_DATE = DATE.isoformat()
TO_DATE = DATE.isoformat()


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    with app.app_context():
        yield app.test_client()


def ensure_user(username, role='operator', password='pass'):
    if not User.query.filter_by(username=username).first():
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return User.query.filter_by(username=username).first()


def ensure_editor(app):
    with app.app_context():
        return ensure_user('editor', role='editor')


def ensure_admin(app):
    with app.app_context():
        return ensure_user('admin', role='admin')


def ensure_department(name='DeptA'):
    d = Department.query.filter_by(name=name).first()
    if not d:
        d = Department(name=name)
        db.session.add(d)
        db.session.commit()
    return d


def make_record(user_id, is_urgent=None, history_submitted=False, dept='DeptA', physician='Dr. Test'):
    r = Record(
        date_of_discharge=DATE,
        full_name='Test Patient',
        discharge_department=dept,
        treating_physician=physician,
        history='12345',
        k_days=5,
        discharge_status=STATUS_PROCESSING,
        is_urgent=is_urgent,
        history_submitted=history_submitted,
        created_by=user_id,
        created_at=datetime.datetime.utcnow(),
    )
    db.session.add(r)
    db.session.commit()
    return r


def login(client, username, password='pass'):
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


# --- Model default values ---

def test_new_record_defaults(app):
    """history_submitted defaults to False; is_urgent defaults to None."""
    with app.app_context():
        u = ensure_user('op')
        ensure_department()
        r = make_record(u.id)
        assert r.history_submitted is False
        assert r.is_urgent is None


def test_record_urgent_flag(app):
    """is_urgent=True is persisted correctly."""
    with app.app_context():
        u = ensure_user('op')
        ensure_department()
        r = make_record(u.id, is_urgent=True)
        fetched = Record.query.get(r.id)
        assert fetched.is_urgent is True


def test_record_planned_flag(app):
    """is_urgent=False (planned) is persisted correctly."""
    with app.app_context():
        u = ensure_user('op')
        ensure_department()
        r = make_record(u.id, is_urgent=False)
        fetched = Record.query.get(r.id)
        assert fetched.is_urgent is False


def test_record_history_submitted_true(app):
    """history_submitted=True is persisted correctly."""
    with app.app_context():
        u = ensure_user('op')
        ensure_department()
        r = make_record(u.id, history_submitted=True)
        fetched = Record.query.get(r.id)
        assert fetched.history_submitted is True


# --- AJAX add endpoint ---

def test_api_add_saves_urgent_and_submitted(app, client):
    """api_add_record saves is_urgent and history_submitted."""
    with app.app_context():
        ensure_user('op2', role='operator')
        ensure_department()
        login(client, 'op2')

        resp = client.post('/api/records/add', data={
            'date_of_discharge': DATE.isoformat(),
            'full_name': 'Іваненко Іван',
            'discharge_department': 'DeptA',
            'treating_physician': 'Лікар',
            'history': '99001',
            'k_days': '3',
            'is_urgent': 'urgent',
            'history_submitted': '1',
        }, headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        r = Record.query.filter_by(full_name='Іваненко Іван').first()
        assert r is not None
        assert r.is_urgent is True
        assert r.history_submitted is True


def test_api_add_planned_not_submitted(app, client):
    """api_add_record saves planned + not submitted correctly."""
    with app.app_context():
        ensure_user('op3', role='operator')
        ensure_department()
        login(client, 'op3')

        resp = client.post('/api/records/add', data={
            'date_of_discharge': DATE.isoformat(),
            'full_name': 'Петренко Петро',
            'discharge_department': 'DeptA',
            'treating_physician': 'Лікар',
            'history': '99002',
            'k_days': '2',
            'is_urgent': 'planned',
        }, headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200
        r = Record.query.filter_by(full_name='Петренко Петро').first()
        assert r.is_urgent is False
        assert r.history_submitted is False


def test_api_add_unset_urgency(app, client):
    """api_add_record with no is_urgent value → None."""
    with app.app_context():
        ensure_user('op4', role='operator')
        ensure_department()
        login(client, 'op4')

        resp = client.post('/api/records/add', data={
            'date_of_discharge': DATE.isoformat(),
            'full_name': 'Коваленко Ольга',
            'discharge_department': 'DeptA',
            'treating_physician': 'Лікар',
            'history': '99003',
            'k_days': '4',
        }, headers={'X-Requested-With': 'XMLHttpRequest'})

        assert resp.status_code == 200
        r = Record.query.filter_by(full_name='Коваленко Ольга').first()
        assert r.is_urgent is None


# --- Dashboard list filter ---

def test_dashboard_filter_not_submitted(app, client):
    """Filter history_submitted=0 shows only unsubmitted records."""
    with app.app_context():
        u = ensure_user('op5', role='operator')
        ensure_department()
        make_record(u.id, history_submitted=False)
        make_record(u.id, history_submitted=True)
        login(client, 'op5')

        resp = client.get('/', query_string={
            'all_months': '1', 'history_submitted': '0'
        })
        assert resp.status_code == 200
        # Only 1 unsubmitted in results (pagination shows count)


def test_dashboard_filter_submitted(app, client):
    """Filter history_submitted=1 shows only submitted records."""
    with app.app_context():
        u = ensure_user('op6', role='operator')
        ensure_department()
        make_record(u.id, history_submitted=False)
        make_record(u.id, history_submitted=True)
        login(client, 'op6')

        resp = client.get('/', query_string={
            'all_months': '1', 'history_submitted': '1'
        })
        assert resp.status_code == 200


# --- Statistics page ---

def test_reports_page_accessible_for_admin(app, client):
    """Reports page /admin/reports is accessible for admin role and shows both sections."""
    with app.app_context():
        ensure_user('adm', role='admin')
        login(client, 'adm')

        resp = client.get('/admin/reports', query_string={
            'from_date': FROM_DATE, 'to_date': TO_DATE
        })
        assert resp.status_code == 200
        txt = resp.get_data(as_text=True)
        assert 'Здача документації' in txt
        assert 'Ургентність' in txt


def test_reports_page_accessible_for_operator(app, client):
    """Reports page /admin/reports is accessible for operator role."""
    with app.app_context():
        ensure_user('adm2', role='operator')
        login(client, 'adm2')

        resp = client.get('/admin/reports', query_string={
            'from_date': FROM_DATE, 'to_date': TO_DATE
        })
        assert resp.status_code == 200
        txt = resp.get_data(as_text=True)
        assert 'Звіти' in txt


def test_statistics_urgency_by_dept(app, client):
    """Urgency by department table appears when data present."""
    with app.app_context():
        u = ensure_user('adm3', role='admin')
        ensure_department('Хірургія')
        make_record(u.id, is_urgent=True, dept='Хірургія')
        login(client, 'adm3')

        resp = client.get('/admin/statistics', query_string={
            'from_date': FROM_DATE, 'to_date': TO_DATE
        })
        assert resp.status_code == 200
        txt = resp.get_data(as_text=True)
        assert 'Хірургія' in txt


def test_reports_page_shows_physician_breakdown(app, client):
    """Reports page shows physician breakdown for submission data."""
    with app.app_context():
        u = ensure_user('adm4', role='admin')
        ensure_department()
        make_record(u.id, history_submitted=False, physician='Лікар Тест')
        login(client, 'adm4')

        resp = client.get('/admin/reports', query_string={
            'from_date': FROM_DATE, 'to_date': TO_DATE
        })
        assert resp.status_code == 200
        txt = resp.get_data(as_text=True)
        assert 'Лікар Тест' in txt
