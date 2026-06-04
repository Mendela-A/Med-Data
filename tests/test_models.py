"""Tests for model methods — unit tests."""
import pytest
from datetime import date
from app import create_app
from models import db, User, DailyReport, Department, Audit, log_action


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


# ---------------------------------------------------------------------------
# User password methods
# ---------------------------------------------------------------------------

class TestUserPassword:
    def test_set_and_check_password_correct(self, app):
        with app.app_context():
            u = User(username='u1', role='operator')
            u.set_password('securepass')
            assert u.check_password('securepass') is True

    def test_check_wrong_password_false(self, app):
        with app.app_context():
            u = User(username='u2', role='operator')
            u.set_password('securepass')
            assert u.check_password('wrongpass') is False

    def test_password_hash_not_plaintext(self, app):
        with app.app_context():
            u = User(username='u3', role='operator')
            u.set_password('mypassword')
            assert u.password_hash != 'mypassword'
            assert len(u.password_hash) > 20


# ---------------------------------------------------------------------------
# DailyReport.compute_patients_end
# ---------------------------------------------------------------------------

class TestDailyReportComputePatientsEnd:
    def _make_report(self, **kwargs):
        defaults = dict(
            report_date=date(2026, 5, 1),
            patients_start=10,
            admitted_total=5,
            transferred_in=2,
            transferred_out=1,
            discharged_total=3,
            deaths=1,
        )
        defaults.update(kwargs)
        return DailyReport(**defaults)

    def test_basic_formula(self, app):
        with app.app_context():
            r = self._make_report()
            # 10 + 5 + 2 - 1 - 3 - 1 = 12
            assert r.compute_patients_end() == 12

    def test_zero_values(self, app):
        with app.app_context():
            r = self._make_report(
                patients_start=0, admitted_total=0,
                transferred_in=0, transferred_out=0,
                discharged_total=0, deaths=0,
            )
            assert r.compute_patients_end() == 0

    def test_none_values_treated_as_zero(self, app):
        with app.app_context():
            r = self._make_report(
                patients_start=None, admitted_total=5,
                transferred_in=None, transferred_out=None,
                discharged_total=None, deaths=None,
            )
            assert r.compute_patients_end() == 5

    def test_large_numbers(self, app):
        with app.app_context():
            r = self._make_report(
                patients_start=100, admitted_total=50,
                transferred_in=10, transferred_out=5,
                discharged_total=30, deaths=2,
            )
            # 100 + 50 + 10 - 5 - 30 - 2 = 123
            assert r.compute_patients_end() == 123


# ---------------------------------------------------------------------------
# DailyReport.free_total property
# ---------------------------------------------------------------------------

class TestDailyReportFreeTotal:
    def test_free_total_calculated(self, app):
        with app.app_context():
            r = DailyReport(report_date=date(2026, 5, 1), beds_total=30, patients_end=22)
            assert r.free_total == 8

    def test_free_total_none_when_beds_none(self, app):
        with app.app_context():
            r = DailyReport(report_date=date(2026, 5, 1), beds_total=None, patients_end=22)
            assert r.free_total is None

    def test_free_total_none_when_patients_none(self, app):
        with app.app_context():
            r = DailyReport(report_date=date(2026, 5, 1), beds_total=30, patients_end=None)
            assert r.free_total is None


# ---------------------------------------------------------------------------
# log_action
# ---------------------------------------------------------------------------

class TestLogAction:
    def test_creates_audit_record(self, app):
        with app.app_context():
            u = User(username='admin_log', role='admin')
            u.set_password('pass1234')
            db.session.add(u)
            db.session.commit()

            log_action(u.id, 'test.action', 'user', u.id, 'test details')
            db.session.commit()

            audit = Audit.query.filter_by(action='test.action').first()
            assert audit is not None
            assert audit.actor_id == u.id
            assert audit.target_type == 'user'
            assert audit.details == 'test details'

    def test_log_action_without_actor(self, app):
        with app.app_context():
            log_action(None, 'user.login_failed', 'user', None, 'test')
            db.session.commit()
            audit = Audit.query.filter_by(action='user.login_failed').first()
            assert audit is not None
            assert audit.actor_id is None
