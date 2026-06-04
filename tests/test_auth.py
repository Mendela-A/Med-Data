"""Tests for authentication flow — login, logout, change_password."""
import pytest
from app import create_app
from models import db, User, Audit


class TestConfig:
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RATELIMIT_ENABLED = False


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


def make_user(username, role='operator', password='pass1234'):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return u


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_unauthenticated_redirect_to_login(self, app, client):
        with app.app_context():
            rv = client.get('/', follow_redirects=False)
            assert rv.status_code == 302
            assert '/login' in rv.headers['Location']

    def test_successful_login_redirects_to_dashboard(self, app, client):
        with app.app_context():
            make_user('op', 'operator')
            rv = client.post('/login',
                             data={'username': 'op', 'password': 'pass1234'},
                             follow_redirects=False)
            assert rv.status_code == 302
            assert rv.headers['Location'] != '/login'

    def test_successful_login_creates_audit(self, app, client):
        with app.app_context():
            make_user('op_audit', 'operator')
            client.post('/login',
                        data={'username': 'op_audit', 'password': 'pass1234'},
                        follow_redirects=True)
            audit = Audit.query.filter_by(action='user.login').first()
            assert audit is not None

    def test_wrong_password_flash_danger(self, app, client):
        with app.app_context():
            make_user('op_bad', 'operator')
            rv = client.post('/login',
                             data={'username': 'op_bad', 'password': 'wrongpass'},
                             follow_redirects=True)
            assert 'Невірне' in rv.get_data(as_text=True)

    def test_wrong_password_creates_failed_audit(self, app, client):
        with app.app_context():
            make_user('op_fail', 'operator')
            client.post('/login',
                        data={'username': 'op_fail', 'password': 'wrongpass'},
                        follow_redirects=True)
            audit = Audit.query.filter_by(action='user.login_failed').first()
            assert audit is not None

    def test_unknown_user_also_creates_failed_audit(self, app, client):
        with app.app_context():
            client.post('/login',
                        data={'username': 'nosuchuser', 'password': 'pass'},
                        follow_redirects=True)
            audit = Audit.query.filter_by(action='user.login_failed').first()
            assert audit is not None

    def test_already_authenticated_redirects_away_from_login(self, app, client):
        with app.app_context():
            make_user('op_logged', 'operator')
            client.post('/login',
                        data={'username': 'op_logged', 'password': 'pass1234'},
                        follow_redirects=True)
            rv = client.get('/login', follow_redirects=False)
            assert rv.status_code == 302


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_redirects_to_login(self, app, client):
        with app.app_context():
            make_user('op_logout', 'operator')
            client.post('/login',
                        data={'username': 'op_logout', 'password': 'pass1234'},
                        follow_redirects=True)
            rv = client.post('/logout', follow_redirects=False)
            assert rv.status_code == 302
            assert '/login' in rv.headers['Location']

    def test_after_logout_protected_route_redirects(self, app, client):
        with app.app_context():
            make_user('op_lout2', 'operator')
            client.post('/login',
                        data={'username': 'op_lout2', 'password': 'pass1234'},
                        follow_redirects=True)
            client.post('/logout', follow_redirects=True)
            rv = client.get('/', follow_redirects=False)
            assert rv.status_code == 302
            assert '/login' in rv.headers['Location']

    def test_logout_creates_audit(self, app, client):
        with app.app_context():
            make_user('op_lout3', 'operator')
            client.post('/login',
                        data={'username': 'op_lout3', 'password': 'pass1234'},
                        follow_redirects=True)
            client.post('/logout', follow_redirects=True)
            audit = Audit.query.filter_by(action='user.logout').first()
            assert audit is not None


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def _login(self, client, username, password='pass1234'):
        client.post('/login',
                    data={'username': username, 'password': password},
                    follow_redirects=True)

    def test_successful_change(self, app, client):
        with app.app_context():
            make_user('op_cp', 'operator', password='oldpass12')
            self._login(client, 'op_cp', 'oldpass12')
            client.post('/change-password', data={
                'current_password': 'oldpass12',
                'new_password': 'newpass99',
                'confirm_password': 'newpass99',
            }, follow_redirects=True)
            u = User.query.filter_by(username='op_cp').first()
            assert u.check_password('newpass99') is True
            assert u.check_password('oldpass12') is False

    def test_wrong_current_password_rejected(self, app, client):
        with app.app_context():
            make_user('op_cp2', 'operator')
            self._login(client, 'op_cp2')
            rv = client.post('/change-password', data={
                'current_password': 'wrongold',
                'new_password': 'newpass99',
                'confirm_password': 'newpass99',
            }, follow_redirects=True)
            assert 'невірний' in rv.get_data(as_text=True).lower()

    def test_short_new_password_rejected(self, app, client):
        with app.app_context():
            make_user('op_cp3', 'operator')
            self._login(client, 'op_cp3')
            rv = client.post('/change-password', data={
                'current_password': 'pass1234',
                'new_password': 'short',
                'confirm_password': 'short',
            }, follow_redirects=True)
            assert '8' in rv.get_data(as_text=True)

    def test_mismatched_passwords_rejected(self, app, client):
        with app.app_context():
            make_user('op_cp4', 'operator')
            self._login(client, 'op_cp4')
            rv = client.post('/change-password', data={
                'current_password': 'pass1234',
                'new_password': 'newpass99',
                'confirm_password': 'differentpass',
            }, follow_redirects=True)
            assert 'співпадають' in rv.get_data(as_text=True).lower() or \
                   'password' in rv.get_data(as_text=True).lower()

    def test_change_password_creates_audit(self, app, client):
        with app.app_context():
            make_user('op_cp5', 'operator')
            self._login(client, 'op_cp5')
            client.post('/change-password', data={
                'current_password': 'pass1234',
                'new_password': 'newpass99',
                'confirm_password': 'newpass99',
            }, follow_redirects=True)
            audit = Audit.query.filter_by(action='user.password_change').first()
            assert audit is not None
