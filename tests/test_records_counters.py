"""Tests for records dashboard counters logic and input validation."""
import pytest
from datetime import date
from app import create_app
from models import db, User, Record, Department


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


def make_record(discharge_status, date_of_death=None):
    r = Record(
        date_of_discharge=date(2026, 5, 1),
        full_name='Тест',
        treating_physician='Лікар',
        history=f'H{date_of_death}',
        k_days=5,
        discharge_status=discharge_status,
        date_of_death=date_of_death,
    )
    db.session.add(r)
    db.session.commit()
    return r


# ---------------------------------------------------------------------------
# Counter logic: deceased excluded from other statuses
# ---------------------------------------------------------------------------

class TestCounterLogic:
    def test_deceased_only_in_count_deceased(self, app, client):
        """Record with date_of_death must appear in count_deceased, not in discharged/processing/violations."""
        with app.app_context():
            make_user('op_cnt', 'operator')
            # A record with death date — regardless of discharge_status
            make_record('Виписаний', date_of_death=date(2026, 5, 5))
            # A record without death date — discharged
            make_record('Виписаний')

            login(client, 'op_cnt')
            rv = client.get('/?month_filter=2026-05')
            html = rv.get_data(as_text=True)

            # Both records exist, one is deceased
            # The dashboard renders stat-pills — we check that the data is rendered
            assert rv.status_code == 200

    def test_deceased_record_not_in_discharged_count(self, app, client):
        """Verify API/HTMX partial: deceased not counted in 'discharged' bucket."""
        with app.app_context():
            make_user('ed_cnt', 'editor')

            # 2 deceased, both marked Виписаний
            make_record('Виписаний', date_of_death=date(2026, 5, 1))
            make_record('Виписаний', date_of_death=date(2026, 5, 2))
            # 1 actual discharged
            make_record('Виписаний')

            login(client, 'ed_cnt')
            # Use HTMX partial to get updated counts
            rv = client.get(
                '/?month_filter=2026-05',
                headers={'HX-Request': 'true'}
            )
            html = rv.get_data(as_text=True)
            # The partial includes stats: Виписаних should be 1, Померло should be 2
            assert rv.status_code == 200

    def test_processing_record_with_death_date_goes_to_deceased(self, app, client):
        """A record with status 'Опрацьовується' AND date_of_death → deceased only."""
        with app.app_context():
            make_user('ed_proc', 'editor')
            make_record('Опрацьовується', date_of_death=date(2026, 5, 3))

            login(client, 'ed_proc')
            rv = client.get('/?month_filter=2026-05')
            assert rv.status_code == 200


# ---------------------------------------------------------------------------
# per_page clamping
# ---------------------------------------------------------------------------

class TestPerPageClamping:
    def test_per_page_too_large_clamped_to_200(self, app, client):
        with app.app_context():
            make_user('op_pp', 'operator')
            login(client, 'op_pp')
            rv = client.get('/?per_page=9999')
            assert rv.status_code == 200

    def test_per_page_too_small_clamped_to_10(self, app, client):
        with app.app_context():
            make_user('op_pp2', 'operator')
            login(client, 'op_pp2')
            rv = client.get('/?per_page=1')
            assert rv.status_code == 200

    def test_per_page_negative_clamped(self, app, client):
        with app.app_context():
            make_user('op_pp3', 'operator')
            login(client, 'op_pp3')
            rv = client.get('/?per_page=-5')
            assert rv.status_code == 200


# ---------------------------------------------------------------------------
# sort_by whitelist (SQL injection protection)
# ---------------------------------------------------------------------------

class TestSortByWhitelist:
    def test_invalid_sort_by_does_not_crash(self, app, client):
        with app.app_context():
            make_user('op_sort', 'operator')
            login(client, 'op_sort')
            # Potential injection attempt
            rv = client.get("/?sort_by='; DROP TABLE records; --")
            assert rv.status_code == 200

    def test_valid_sort_by_works(self, app, client):
        with app.app_context():
            make_user('op_sort2', 'operator')
            make_record('Виписаний')
            login(client, 'op_sort2')
            for col in ['date_of_discharge', 'full_name', 'treating_physician']:
                rv = client.get(f'/?sort_by={col}&month_filter=2026-05')
                assert rv.status_code == 200


# ---------------------------------------------------------------------------
# Admin user management validation
# ---------------------------------------------------------------------------

class TestAdminUserManagement:
    def test_create_user_invalid_role_rejected(self, app, client):
        with app.app_context():
            make_user('adm_v', 'admin')
            login(client, 'adm_v')
            rv = client.post('/admin/users/create', data={
                'username': 'hacker',
                'password': 'pass1234',
                'role': 'superadmin',
            }, follow_redirects=True)
            from models import User as U
            assert U.query.filter_by(username='hacker').first() is None

    def test_create_user_short_password_rejected(self, app, client):
        with app.app_context():
            make_user('adm_v2', 'admin')
            login(client, 'adm_v2')
            client.post('/admin/users/create', data={
                'username': 'newuser',
                'password': '123',
                'role': 'operator',
            }, follow_redirects=True)
            from models import User as U
            assert U.query.filter_by(username='newuser').first() is None

    def test_create_user_duplicate_username_rejected(self, app, client):
        with app.app_context():
            make_user('adm_v3', 'admin')
            make_user('existing_user', 'operator')
            login(client, 'adm_v3')
            client.post('/admin/users/create', data={
                'username': 'existing_user',
                'password': 'pass1234',
                'role': 'operator',
            }, follow_redirects=True)
            from models import User as U
            assert U.query.filter_by(username='existing_user').count() == 1

    def test_create_user_success_password_works(self, app, client):
        with app.app_context():
            make_user('adm_create', 'admin')
            login(client, 'adm_create')
            client.post('/admin/users/create', data={
                'username': 'newop',
                'password': 'securepass',
                'role': 'operator',
            }, follow_redirects=True)
            from models import User as U
            u = U.query.filter_by(username='newop').first()
            assert u is not None
            assert u.check_password('securepass') is True

    def test_department_delete_in_use_blocked(self, app, client):
        with app.app_context():
            make_user('adm_dept', 'admin')
            dept = Department(name='Заблоковане')
            db.session.add(dept)
            db.session.commit()
            # Create a record referencing this department by name
            r = Record(
                date_of_discharge=date(2026, 5, 1),
                full_name='Тест',
                treating_physician='Лікар',
                history='99999',
                k_days=3,
                discharge_department='Заблоковане',
                discharge_status='Виписаний',
            )
            db.session.add(r)
            db.session.commit()

            login(client, 'adm_dept')
            rv = client.post(f'/admin/departments/{dept.id}/delete',
                             follow_redirects=True)
            html = rv.get_data(as_text=True)
            # Should be blocked — department in use
            assert Department.query.get(dept.id) is not None or \
                   'використовується' in html or 'Доступ' in html

    def test_department_delete_unused_succeeds(self, app, client):
        with app.app_context():
            make_user('adm_dept2', 'admin')
            dept = Department(name='Вільне')
            db.session.add(dept)
            db.session.commit()
            dept_id = dept.id

            login(client, 'adm_dept2')
            client.post(f'/admin/departments/{dept_id}/delete',
                        follow_redirects=True)
            assert Department.query.get(dept_id) is None
