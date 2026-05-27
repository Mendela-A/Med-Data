import pytest
import datetime
from app import create_app
from models import db, User, Department, DailyReport

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
    return User.query.filter_by(username=username).first()

def test_form016_departments_calculations_and_views(app, client):
    with app.app_context():
        # Setup users and departments
        u = ensure_user('admin_test', role='admin')
        
        dept1 = Department(name="Терапевтичне", row_no=5, bed_capacity=30)
        dept2 = Department(name="Хірургічне", row_no=10, bed_capacity=20)
        db.session.add_all([dept1, dept2])
        db.session.commit()

        # Populate daily reports for April 1st, 2026
        # Dept 1 (Therapeutic): 30 beds, start 10 patients, 5 admitted, end 15
        dr1 = DailyReport(
            report_date=datetime.date(2026, 4, 1),
            department_id=dept1.id,
            beds_total=30,
            patients_start=10,
            admitted_total=5,
            admitted_rural=2,
            admitted_children=1,
            discharged_total=0,
            patients_end=15,
            created_by=u.id
        )
        
        # Dept 2 (Surgical): 20 beds, start 8 patients, 2 admitted, end 10
        dr2 = DailyReport(
            report_date=datetime.date(2026, 4, 1),
            department_id=dept2.id,
            beds_total=20,
            patients_start=8,
            admitted_total=2,
            admitted_rural=1,
            admitted_children=0,
            discharged_total=0,
            patients_end=10,
            created_by=u.id
        )
        db.session.add_all([dr1, dr2])
        db.session.commit()

        # Login
        client.post('/login', data={'username': 'admin_test', 'password': 'pass'}, follow_redirects=True)

        # 1. Verify Web View
        rv = client.get('/statisty/form016_departments', query_string={'from_date': '2026-04'})
        assert rv.status_code == 200
        html = rv.get_data(as_text=True)
        
        # Verify both departments present with correct row numbers
        assert "Терапевтичне" in html
        assert "5" in html
        assert "Хірургічне" in html
        assert "10" in html
        
        # Verify aggregated values are printed correctly
        assert "15" in html  # patients_end of Dept 1
        assert "10" in html  # patients_end of Dept 2
        
        # Verify grand totals
        assert "Разом" in html
        
        # 2. Verify PDF Print View (may return 302 redirect if WeasyPrint is not installed)
        rv_print = client.get('/statisty/form016_departments/print', query_string={'from_date': '2026-04'})
        assert rv_print.status_code in (200, 302)
        if rv_print.status_code == 200:
            assert rv_print.mimetype == 'application/pdf'
        else:
            assert '/statisty/form016_departments' in rv_print.location

        # 3. Verify Excel Export View
        rv_export = client.get('/statisty/form016_departments/export', query_string={'from_date': '2026-04'})
        assert rv_export.status_code == 200
        assert rv_export.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
