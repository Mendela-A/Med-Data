"""Tests for NSZU corrections module — full CRUD coverage."""
import pytest
from datetime import date
from app import create_app
from models import db, User, NSZUCorrection, Audit


class TestConfig:
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    with app.app_context():
        yield app.test_client()


def make_user(username, role, password='pass1234'):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return u


def login(client, username, password='pass1234'):
    client.post('/login', data={'username': username, 'password': password},
                follow_redirects=True)


def make_nszu_correction(**kwargs):
    defaults = dict(
        date=date(2026, 5, 1),
        nszu_record_id='TEST-001',
        doctor='Лікар Тест',
        status='В обробці',
        fakt_summ=500.0,
    )
    defaults.update(kwargs)
    c = NSZUCorrection(**defaults)
    db.session.add(c)
    db.session.commit()
    return c


# ---------------------------------------------------------------------------
# nszu_list
# ---------------------------------------------------------------------------

class TestNszuList:
    def test_editor_can_view_list(self, app, client):
        with app.app_context():
            make_user('ed_list', 'editor')
            login(client, 'ed_list')
            rv = client.get('/nszu', follow_redirects=False)
            assert rv.status_code == 200

    def test_operator_blocked_from_list(self, app, client):
        with app.app_context():
            make_user('op_list', 'operator')
            login(client, 'op_list')
            rv = client.get('/nszu', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)

    def test_month_filter_applied(self, app, client):
        with app.app_context():
            make_user('ed_mf', 'editor')
            make_nszu_correction(date=date(2026, 5, 15), nszu_record_id='MAY-001')
            make_nszu_correction(date=date(2026, 4, 15), nszu_record_id='APR-001')
            login(client, 'ed_mf')
            rv = client.get('/nszu?month_year=2026-05')
            html = rv.get_data(as_text=True)
            assert 'MAY-001' in html
            assert 'APR-001' not in html


# ---------------------------------------------------------------------------
# nszu_add
# ---------------------------------------------------------------------------

class TestNszuAdd:
    def test_editor_can_add_valid(self, app, client):
        with app.app_context():
            make_user('ed_add', 'editor')
            login(client, 'ed_add')
            rv = client.post('/nszu/add', data={
                'date': '2026-05-01',
                'nszu_record_id': 'NEW-001',
                'doctor': 'Лікар',
                'status': 'В обробці',
                'fakt_summ': '1500,50',
            }, follow_redirects=True)
            assert rv.status_code == 200
            c = NSZUCorrection.query.filter_by(nszu_record_id='NEW-001').first()
            assert c is not None
            assert abs(float(c.fakt_summ) - 1500.50) < 0.01

    def test_invalid_status_rejected(self, app, client):
        with app.app_context():
            make_user('ed_bad_status', 'editor')
            login(client, 'ed_bad_status')
            client.post('/nszu/add', data={
                'date': '2026-05-01',
                'nszu_record_id': 'BAD-001',
                'doctor': 'Лікар',
                'status': 'INVALID_STATUS',
            }, follow_redirects=True)
            assert NSZUCorrection.query.filter_by(nszu_record_id='BAD-001').first() is None

    def test_missing_required_fields_rejected(self, app, client):
        with app.app_context():
            make_user('ed_miss', 'editor')
            login(client, 'ed_miss')
            client.post('/nszu/add', data={
                'date': '2026-05-01',
                # missing nszu_record_id and doctor
                'status': 'В обробці',
            }, follow_redirects=True)
            assert NSZUCorrection.query.count() == 0

    def test_comma_fakt_summ_parsed_correctly(self, app, client):
        with app.app_context():
            make_user('ed_comma', 'editor')
            login(client, 'ed_comma')
            client.post('/nszu/add', data={
                'date': '2026-05-01',
                'nszu_record_id': 'COMMA-001',
                'doctor': 'Лікар',
                'status': 'В обробці',
                'fakt_summ': '123,45',
            }, follow_redirects=True)
            c = NSZUCorrection.query.filter_by(nszu_record_id='COMMA-001').first()
            assert c is not None
            assert abs(float(c.fakt_summ) - 123.45) < 0.01

    def test_add_creates_audit(self, app, client):
        with app.app_context():
            make_user('ed_audit', 'editor')
            login(client, 'ed_audit')
            client.post('/nszu/add', data={
                'date': '2026-05-01',
                'nszu_record_id': 'AUD-001',
                'doctor': 'Лікар',
                'status': 'В обробці',
            }, follow_redirects=True)
            audit = Audit.query.filter_by(action='nszu.create').first()
            assert audit is not None

    def test_viewer_cannot_add(self, app, client):
        with app.app_context():
            make_user('vw_add', 'viewer')
            login(client, 'vw_add')
            rv = client.post('/nszu/add', data={
                'date': '2026-05-01',
                'nszu_record_id': 'VIEW-001',
                'doctor': 'Лікар',
                'status': 'В обробці',
            }, follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)
            assert NSZUCorrection.query.count() == 0


# ---------------------------------------------------------------------------
# nszu_delete
# ---------------------------------------------------------------------------

class TestNszuDelete:
    def test_admin_can_delete(self, app, client):
        with app.app_context():
            make_user('adm_del', 'admin')
            c = make_nszu_correction(nszu_record_id='DEL-001')
            cid = c.id
            login(client, 'adm_del')
            rv = client.post(f'/nszu/{cid}/delete', follow_redirects=True)
            assert rv.status_code == 200
            assert NSZUCorrection.query.get(cid) is None

    def test_editor_cannot_delete(self, app, client):
        with app.app_context():
            make_user('ed_del', 'editor')
            c = make_nszu_correction(nszu_record_id='EDEL-001')
            cid = c.id
            login(client, 'ed_del')
            rv = client.post(f'/nszu/{cid}/delete', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)
            assert NSZUCorrection.query.get(cid) is not None

    def test_delete_creates_audit(self, app, client):
        with app.app_context():
            make_user('adm_audit_del', 'admin')
            c = make_nszu_correction(nszu_record_id='ADEL-001')
            cid = c.id
            login(client, 'adm_audit_del')
            client.post(f'/nszu/{cid}/delete', follow_redirects=True)
            audit = Audit.query.filter_by(action='nszu.delete').first()
            assert audit is not None
