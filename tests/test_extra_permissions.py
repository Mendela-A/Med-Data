"""
Tests for per-user extra_permissions (tab access control).

Covers:
- User.has_tab_access() model method
- role_required decorator honoring extra_permissions
- Admin UI saving/clearing extra_permissions via edit_user
- Navbar HTML visibility controlled by has_tab_access()
"""
import pytest
from app import create_app
from models import db, User
from constants import DEFAULT_ROLE_TABS, TABS


class TestConfig:
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key-for-tests'
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
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=True)


# ---------------------------------------------------------------------------
# 1. User.has_tab_access() model method
# ---------------------------------------------------------------------------

class TestHasTabAccess:

    def test_admin_has_all_tabs(self, app):
        with app.app_context():
            u = make_user('adm', 'admin')
            for tab in TABS:
                assert u.has_tab_access(tab), f"Admin should access tab '{tab}'"

    def test_operator_default_tabs(self, app):
        with app.app_context():
            u = make_user('op', 'operator')
            assert u.has_tab_access('records')
            assert u.has_tab_access('ambulatory')
            assert not u.has_tab_access('nszu')
            assert not u.has_tab_access('statistics')
            assert not u.has_tab_access('statisty')
            assert not u.has_tab_access('admin_panel')

    def test_viewer_default_tabs(self, app):
        with app.app_context():
            u = make_user('vw', 'viewer')
            for tab in DEFAULT_ROLE_TABS['viewer']:
                assert u.has_tab_access(tab)
            assert not u.has_tab_access('admin_panel')
            assert not u.has_tab_access('print_settings')

    def test_extra_permissions_grant_additional_tab(self, app):
        with app.app_context():
            u = make_user('op_extra', 'operator', extra_permissions=['nszu'])
            assert u.has_tab_access('nszu'), "extra_permissions=['nszu'] should grant NSZU tab"
            # Base role tabs still work
            assert u.has_tab_access('records')
            assert u.has_tab_access('ambulatory')
            # Other non-granted tabs still blocked
            assert not u.has_tab_access('statistics')
            assert not u.has_tab_access('admin_panel')

    def test_multiple_extra_permissions(self, app):
        with app.app_context():
            u = make_user('op_multi', 'operator',
                          extra_permissions=['nszu', 'statisty', 'statistics'])
            assert u.has_tab_access('nszu')
            assert u.has_tab_access('statisty')
            assert u.has_tab_access('statistics')
            assert not u.has_tab_access('admin_panel')

    def test_null_extra_permissions_does_not_break(self, app):
        with app.app_context():
            u = make_user('op_null', 'operator', extra_permissions=None)
            assert u.has_tab_access('records')
            assert not u.has_tab_access('nszu')

    def test_empty_extra_permissions_does_not_grant_anything(self, app):
        with app.app_context():
            u = make_user('op_empty', 'operator', extra_permissions=[])
            assert not u.has_tab_access('nszu')
            assert not u.has_tab_access('statistics')

    def test_accessible_tabs_operator_default(self, app):
        with app.app_context():
            u = make_user('op_tabs', 'operator')
            tabs = u.accessible_tabs()
            assert 'records' in tabs
            assert 'ambulatory' in tabs
            assert 'nszu' not in tabs

    def test_accessible_tabs_with_extra(self, app):
        with app.app_context():
            u = make_user('op_tabs2', 'operator', extra_permissions=['nszu', 'statisty'])
            tabs = u.accessible_tabs()
            assert 'records' in tabs
            assert 'nszu' in tabs
            assert 'statisty' in tabs
            assert 'admin_panel' not in tabs

    def test_admin_accessible_tabs_returns_all(self, app):
        with app.app_context():
            u = make_user('adm_tabs', 'admin')
            tabs = u.accessible_tabs()
            for tab in TABS:
                assert tab in tabs


# ---------------------------------------------------------------------------
# 2. role_required decorator — route access
# ---------------------------------------------------------------------------

class TestRouteAccessWithExtraPermissions:

    def test_operator_blocked_from_nszu_without_extra(self, app, client):
        with app.app_context():
            make_user('op_blocked', 'operator')
            login(client, 'op_blocked')
            rv = client.get('/nszu', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)

    def test_operator_with_nszu_extra_can_access_nszu(self, app, client):
        with app.app_context():
            make_user('op_nszu', 'operator', extra_permissions=['nszu'])
            login(client, 'op_nszu')
            rv = client.get('/nszu', follow_redirects=False)
            assert rv.status_code == 200
            assert 'Доступ заборонено' not in rv.get_data(as_text=True)

    def test_operator_with_statisty_extra_can_access_form007(self, app, client):
        with app.app_context():
            make_user('op_stat', 'operator', extra_permissions=['statisty'])
            login(client, 'op_stat')
            rv = client.get('/statisty/form007', follow_redirects=False)
            assert rv.status_code == 200
            assert 'Доступ заборонено' not in rv.get_data(as_text=True)

    def test_operator_extra_nszu_still_blocked_from_admin_panel(self, app, client):
        with app.app_context():
            make_user('op_nszu2', 'operator', extra_permissions=['nszu'])
            login(client, 'op_nszu2')
            # admin-only route
            rv = client.get('/admin/users', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)

    def test_extra_permissions_dont_elevate_to_admin(self, app, client):
        """Even with all possible extra permissions, non-admin can't reach admin routes."""
        with app.app_context():
            make_user('op_all', 'operator',
                      extra_permissions=['nszu', 'statisty', 'statistics', 'records', 'ambulatory'])
            login(client, 'op_all')
            rv = client.get('/admin/users', follow_redirects=True)
            assert 'Доступ заборонено' in rv.get_data(as_text=True)

    def test_viewer_with_extra_statistics_can_access_stats(self, app, client):
        """Viewer already has statistics access by role — extra_permissions is redundant but harmless."""
        with app.app_context():
            make_user('vw_stat', 'viewer', extra_permissions=['statistics'])
            login(client, 'vw_stat')
            rv = client.get('/admin/statistics', follow_redirects=False)
            assert rv.status_code == 200

    def test_admin_always_accesses_everything_regardless_of_extra(self, app, client):
        with app.app_context():
            make_user('adm_x', 'admin', extra_permissions=None)
            login(client, 'adm_x')
            assert client.get('/admin/users').status_code == 200
            assert client.get('/nszu').status_code == 200
            assert client.get('/statisty/form007').status_code == 200


# ---------------------------------------------------------------------------
# 3. Admin UI — saving extra_permissions via edit_user
# ---------------------------------------------------------------------------

class TestEditUserSavesExtraPermissions:

    def test_admin_can_grant_extra_tab_to_operator(self, app, client):
        with app.app_context():
            make_user('admin_user', 'admin')
            target = make_user('op_target', 'operator')

            login(client, 'admin_user')

            rv = client.post(f'/admin/users/{target.id}/edit', data={
                'username': 'op_target',
                'role': 'operator',
                'tab_nszu': 'on',        # grant NSZU
            }, follow_redirects=True)

            assert rv.status_code == 200
            db.session.refresh(target)
            assert target.extra_permissions is not None
            assert 'nszu' in target.extra_permissions

    def test_base_role_tabs_not_stored_as_extra(self, app, client):
        """Tabs that the role already provides should NOT be stored in extra_permissions."""
        with app.app_context():
            make_user('admin_user', 'admin')
            target = make_user('op_base', 'operator')

            login(client, 'admin_user')

            # Check 'records' and 'ambulatory' — already in operator role
            client.post(f'/admin/users/{target.id}/edit', data={
                'username': 'op_base',
                'role': 'operator',
                'tab_records': 'on',       # in role — should be ignored
                'tab_ambulatory': 'on',    # in role — should be ignored
                'tab_nszu': 'on',          # extra
            }, follow_redirects=True)

            db.session.refresh(target)
            extra = target.extra_permissions or []
            assert 'records' not in extra, "role tabs should not appear in extra_permissions"
            assert 'ambulatory' not in extra, "role tabs should not appear in extra_permissions"
            assert 'nszu' in extra

    def test_revoking_all_extra_stores_none(self, app, client):
        """If no extra tabs are checked, extra_permissions should be None (not [])."""
        with app.app_context():
            make_user('admin_user', 'admin')
            target = make_user('op_revoke', 'operator', extra_permissions=['nszu'])

            login(client, 'admin_user')

            # Send form with no tab_* checkboxes
            client.post(f'/admin/users/{target.id}/edit', data={
                'username': 'op_revoke',
                'role': 'operator',
            }, follow_redirects=True)

            db.session.refresh(target)
            assert target.extra_permissions is None, \
                "empty extra_permissions should be stored as None"

    def test_changing_role_preserves_applicable_extra_permissions(self, app, client):
        """After promoting operator→editor, nszu is now in base role, so extra_permissions clears it."""
        with app.app_context():
            make_user('admin_user', 'admin')
            target = make_user('op_promote', 'operator', extra_permissions=['nszu'])

            login(client, 'admin_user')

            # Promote to editor (nszu is now in base role for editor)
            client.post(f'/admin/users/{target.id}/edit', data={
                'username': 'op_promote',
                'role': 'editor',
                # no tab_nszu — nszu is already in editor's base tabs
            }, follow_redirects=True)

            db.session.refresh(target)
            extra = target.extra_permissions or []
            assert 'nszu' not in extra, \
                "nszu should not be in extra_permissions after promotion to editor"


# ---------------------------------------------------------------------------
# 4. Navbar HTML visibility
# ---------------------------------------------------------------------------

class TestNavbarVisibility:

    def test_operator_without_extra_does_not_see_nszu_in_nav(self, app, client):
        with app.app_context():
            make_user('op_nav', 'operator')
            login(client, 'op_nav')
            rv = client.get('/', follow_redirects=False)
            html = rv.get_data(as_text=True)
            assert '/nszu' not in html

    def test_operator_with_nszu_extra_sees_nszu_in_nav(self, app, client):
        with app.app_context():
            make_user('op_nav2', 'operator', extra_permissions=['nszu'])
            login(client, 'op_nav2')
            rv = client.get('/', follow_redirects=False)
            html = rv.get_data(as_text=True)
            assert '/nszu' in html

    def test_operator_without_statisty_does_not_see_forms_in_nav(self, app, client):
        with app.app_context():
            make_user('op_nostat', 'operator')
            login(client, 'op_nostat')
            rv = client.get('/', follow_redirects=False)
            html = rv.get_data(as_text=True)
            assert '/statisty' not in html

    def test_operator_with_statisty_extra_sees_forms_in_nav(self, app, client):
        with app.app_context():
            make_user('op_statav', 'operator', extra_permissions=['statisty'])
            login(client, 'op_statav')
            rv = client.get('/', follow_redirects=False)
            html = rv.get_data(as_text=True)
            assert '/statisty' in html

    def test_admin_sees_all_nav_sections(self, app, client):
        with app.app_context():
            make_user('adm_nav', 'admin')
            login(client, 'adm_nav')
            rv = client.get('/', follow_redirects=False)
            html = rv.get_data(as_text=True)
            assert '/nszu' in html
            assert '/admin/users' in html
            assert '/admin/audit' in html
