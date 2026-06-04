"""
Tests for write-operation authorization matrix.
Verifies that roles with insufficient privileges cannot perform write operations,
and that the viewer→form007_edit bug is caught.
"""
import pytest
from datetime import date
from app import create_app
from models import db, User, Record, Department, NSZUCorrection, AmbulatoryRecord


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


def make_user(username, role, extra_permissions=None, password='pass1234'):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role=role, extra_permissions=extra_permissions)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return u


def login(client, username, password='pass1234'):
    client.post('/login', data={'username': username, 'password': password},
                follow_redirects=True)


def make_record(app):
    """Create a test Record and return its id."""
    d = Department(name='Тестове відділення')
    db.session.add(d)
    db.session.flush()
    r = Record(
        date_of_discharge=date(2026, 5, 1),
        full_name='Тест Пацієнт',
        treating_physician='Лікар',
        history='12345',
        k_days=5,
        discharge_status='Виписаний',
        discharge_department='Тестове відділення',
    )
    db.session.add(r)
    db.session.commit()
    return r.id


def make_nszu(app):
    """Create a test NSZUCorrection and return its id."""
    c = NSZUCorrection(
        date=date(2026, 5, 1),
        nszu_record_id='TEST-001',
        doctor='Лікар',
        status='В обробці',
        fakt_summ=100.0,
    )
    db.session.add(c)
    db.session.commit()
    return c.id


def make_ambulatory(app):
    """Create a test AmbulatoryRecord and return its id."""
    r = AmbulatoryRecord(
        date=date(2026, 5, 1),
        journal_number='1/A',
        full_name='Амб Пацієнт',
        birth_date=date(1990, 1, 1),
        doctor='Лікар',
        diagnosis='ГРВІ',
        discharge_status='Опрацьовується',
    )
    db.session.add(r)
    db.session.commit()
    return r.id


# ---------------------------------------------------------------------------
# viewer cannot write records
# ---------------------------------------------------------------------------

class TestViewerCannotWrite:
    def test_viewer_cannot_edit_record(self, app, client):
        with app.app_context():
            make_user('viewer_r', 'viewer')
            record_id = make_record(app)
            login(client, 'viewer_r')
            rv = client.post(f'/records/{record_id}/edit', data={
                'date_of_discharge': '2026-05-02',
                'full_name': 'Hacked', 'treating_physician': 'x',
                'history': '1', 'k_days': '1',
                'discharge_status': 'Виписаний',
                'discharge_department': 'Тестове відділення',
            }, follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)
            # DB unchanged
            r = Record.query.get(record_id)
            assert r.full_name == 'Тест Пацієнт'

    def test_viewer_cannot_delete_record(self, app, client):
        with app.app_context():
            make_user('viewer_del', 'viewer')
            record_id = make_record(app)
            login(client, 'viewer_del')
            rv = client.post(f'/records/{record_id}/delete', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)
            assert Record.query.get(record_id) is not None

    def test_viewer_cannot_add_nszu(self, app, client):
        with app.app_context():
            make_user('viewer_nszu', 'viewer')
            login(client, 'viewer_nszu')
            rv = client.post('/nszu/add', data={
                'date': '2026-05-01',
                'nszu_record_id': 'X-001',
                'doctor': 'Лікар',
                'status': 'В обробці',
            }, follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)
            assert NSZUCorrection.query.count() == 0

    def test_viewer_cannot_edit_ambulatory(self, app, client):
        with app.app_context():
            make_user('viewer_amb', 'viewer')
            amb_id = make_ambulatory(app)
            login(client, 'viewer_amb')
            rv = client.post(f'/ambulatory/{amb_id}/edit', data={
                'journal_number': '1/A', 'date': '2026-05-01',
                'full_name': 'Hacked', 'birth_date': '1990-01-01',
                'doctor': 'Лікар', 'diagnosis': 'ГРВІ',
                'discharge_status': 'Виписаний',
            }, follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)
            a = AmbulatoryRecord.query.get(amb_id)
            assert a.full_name == 'Амб Пацієнт'


# ---------------------------------------------------------------------------
# operator cannot edit/delete records (only add)
# ---------------------------------------------------------------------------

class TestOperatorCannotEditOrDelete:
    def test_operator_cannot_edit_record(self, app, client):
        with app.app_context():
            make_user('op_edit', 'operator')
            record_id = make_record(app)
            login(client, 'op_edit')
            rv = client.post(f'/records/{record_id}/edit', data={
                'date_of_discharge': '2026-05-02',
                'full_name': 'Hacked', 'treating_physician': 'x',
                'history': '1', 'k_days': '1',
                'discharge_status': 'Виписаний',
                'discharge_department': 'Тестове відділення',
            }, follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)

    def test_operator_cannot_delete_nszu(self, app, client):
        with app.app_context():
            make_user('op_nszu_del', 'operator')
            nszu_id = make_nszu(app)
            login(client, 'op_nszu_del')
            rv = client.post(f'/nszu/{nszu_id}/delete', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)
            assert NSZUCorrection.query.get(nszu_id) is not None


# ---------------------------------------------------------------------------
# editor cannot access admin routes
# ---------------------------------------------------------------------------

class TestEditorCannotAccessAdmin:
    def test_editor_cannot_access_admin_users(self, app, client):
        with app.app_context():
            make_user('editor_adm', 'editor')
            login(client, 'editor_adm')
            rv = client.get('/admin/users', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)

    def test_editor_cannot_delete_nszu(self, app, client):
        with app.app_context():
            make_user('editor_del', 'editor')
            nszu_id = make_nszu(app)
            login(client, 'editor_del')
            rv = client.post(f'/nszu/{nszu_id}/delete', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Potential bug: viewer on form007_edit (write route)
# ---------------------------------------------------------------------------

class TestViewerForm007EditBug:
    def test_viewer_blocked_from_form007_edit_post(self, app, client):
        """
        form007_edit uses @role_required('admin', 'viewer') but is a write route.
        viewer should NOT be able to write DailyReport data.
        This test documents the expected behavior — viewer should be blocked.
        If this test FAILS, there is a real authorization bug.
        """
        with app.app_context():
            d = Department(name='Хірургічне')
            db.session.add(d)
            db.session.commit()

            make_user('viewer_form007', 'viewer')
            login(client, 'viewer_form007')

            rv = client.post('/statisty/form007/2026-05-01/edit',
                             data={f'row_{d.id}_beds_total': '30'},
                             follow_redirects=True)
            # viewer should NOT be able to write — expect redirect/403/flash
            # If this assertion fails, viewer can write Form 007 — that's the bug
            html = rv.get_data(as_text=True)
            assert 'Доступ заборонено' in html, (
                "BUG: viewer can write to form007_edit! "
                "Decorator @role_required('admin','viewer') incorrectly allows viewer on write route."
            )


# ---------------------------------------------------------------------------
# admin_delete_user self-protection
# ---------------------------------------------------------------------------

class TestAdminDeleteSelfProtection:
    def test_admin_cannot_delete_own_account(self, app, client):
        with app.app_context():
            admin = make_user('self_admin', 'admin')
            login(client, 'self_admin')
            rv = client.post(f'/admin/users/{admin.id}/delete',
                             follow_redirects=True)
            html = rv.get_data(as_text=True)
            assert 'не можете видалити' in html or 'самого себе' in html
            assert User.query.filter_by(username='self_admin').first() is not None
