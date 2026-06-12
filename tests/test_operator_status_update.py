"""Tests for /api/records/<id>/status — operator-only status update endpoint."""
import os
import datetime
import pytest
os.environ.setdefault('SECRET_KEY', 'test-key')
from app import create_app
from models import db, User, Record, Department
from constants import STATUS_PROCESSING

DATE = datetime.date(2026, 3, 1)


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


def make_record(user_id, is_urgent=None, history_submitted=False):
    r = Record(
        date_of_discharge=DATE,
        full_name='Тест Пацієнт',
        discharge_department='ДептА',
        treating_physician='Лікар',
        history='11111',
        k_days=3,
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


# --- Operator can update ---

def test_operator_can_set_urgent(app, client):
    """Operator sets is_urgent=True via status endpoint."""
    with app.app_context():
        u = ensure_user('op_s1', role='operator')
        r = make_record(u.id, is_urgent=None)
        login(client, 'op_s1')

        resp = client.post(f'/api/records/{r.id}/status', data={'is_urgent': 'urgent', 'history_submitted': '0'})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        updated = db.session.get(Record, r.id)
        assert updated.is_urgent is True
        assert updated.history_submitted is False


def test_operator_can_set_planned(app, client):
    """Operator sets is_urgent=False (planned) via status endpoint."""
    with app.app_context():
        u = ensure_user('op_s2', role='operator')
        r = make_record(u.id, is_urgent=True)
        login(client, 'op_s2')

        resp = client.post(f'/api/records/{r.id}/status', data={'is_urgent': 'planned', 'history_submitted': '0'})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        updated = db.session.get(Record, r.id)
        assert updated.is_urgent is False


def test_operator_can_set_history_submitted(app, client):
    """Operator marks history_submitted=True."""
    with app.app_context():
        u = ensure_user('op_s3', role='operator')
        r = make_record(u.id, history_submitted=False)
        login(client, 'op_s3')

        resp = client.post(f'/api/records/{r.id}/status', data={'is_urgent': 'planned', 'history_submitted': '1'})
        assert resp.status_code == 200

        updated = db.session.get(Record, r.id)
        assert updated.history_submitted is True


def test_operator_can_clear_history_submitted(app, client):
    """Operator clears history_submitted back to False."""
    with app.app_context():
        u = ensure_user('op_s4', role='operator')
        r = make_record(u.id, history_submitted=True)
        login(client, 'op_s4')

        resp = client.post(f'/api/records/{r.id}/status', data={'is_urgent': 'planned', 'history_submitted': '0'})
        assert resp.status_code == 200

        updated = db.session.get(Record, r.id)
        assert updated.history_submitted is False


# --- Access control ---

def test_viewer_cannot_update_status(app, client):
    """Viewer is blocked from status endpoint (403 or redirect)."""
    with app.app_context():
        op = ensure_user('op_s5', role='operator')
        r = make_record(op.id)
        ensure_user('viewer_s', role='viewer')
        login(client, 'viewer_s')

        resp = client.post(f'/api/records/{r.id}/status', data={'is_urgent': 'urgent', 'history_submitted': '0'})
        assert resp.status_code in (403, 302)


def test_editor_cannot_update_status(app, client):
    """Editor is blocked from status endpoint (403 or redirect)."""
    with app.app_context():
        op = ensure_user('op_s6', role='operator')
        r = make_record(op.id)
        ensure_user('editor_s', role='editor')
        login(client, 'editor_s')

        resp = client.post(f'/api/records/{r.id}/status', data={'is_urgent': 'urgent', 'history_submitted': '0'})
        assert resp.status_code in (403, 302)


def test_unauthenticated_cannot_update_status(app, client):
    """Unauthenticated request is redirected to login."""
    with app.app_context():
        u = ensure_user('op_s7', role='operator')
        r = make_record(u.id)

        resp = client.post(f'/api/records/{r.id}/status', data={'is_urgent': 'urgent', 'history_submitted': '0'})
        assert resp.status_code == 302


def test_nonexistent_record_returns_404(app, client):
    """Status endpoint returns 404 for missing record."""
    with app.app_context():
        ensure_user('op_s8', role='operator')
        login(client, 'op_s8')

        resp = client.post('/api/records/99999/status', data={'is_urgent': 'urgent', 'history_submitted': '0'})
        assert resp.status_code == 404
