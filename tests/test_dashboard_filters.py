import pytest
import datetime
from app import create_app, db
from models import User, Record, Department

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
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


def ensure_department(name='DeptTest'):
    d = Department.query.filter_by(name=name).first()
    if not d:
        d = Department(name=name)
        db.session.add(d)
        db.session.commit()
    return d


def test_new_records_displayed_first(app, client):
    with app.app_context():
        ensure_user('ed', role='editor')
        ensure_department()
        u = User.query.filter_by(username='ed').first()

        now = datetime.datetime.utcnow()
        older = now - datetime.timedelta(minutes=5)

        r_old = Record(date_of_discharge=now.date(), full_name='Oldest Record', discharge_department='DeptTest', treating_physician='Dr', history='H1', k_days=1, created_by=u.id, created_at=older)
        r_new = Record(date_of_discharge=now.date(), full_name='Newest Record', discharge_department='DeptTest', treating_physician='Dr', history='H2', k_days=1, created_by=u.id, created_at=now)
        db.session.add_all([r_old, r_new])
        db.session.commit()

        client.post('/login', data={'username': 'ed', 'password': 'pass'}, follow_redirects=True)
        rv = client.get('/')
        txt = rv.get_data(as_text=True)
        assert txt.index('Newest Record') < txt.index('Oldest Record')


def test_no_operator_info_message(app, client):
    with app.app_context():
        ensure_user('op', role='operator')
        client.post('/login', data={'username': 'op', 'password': 'pass'}, follow_redirects=True)
        rv = client.get('/')
        txt = rv.get_data(as_text=True)
        assert 'Оператори бачать тільки записи' not in txt


def test_month_year_filter(app, client):
    with app.app_context():
        ensure_user('ed', role='editor')
        ensure_department()
        u = User.query.filter_by(username='ed').first()

        # create record in Jan 2025
        jan = datetime.datetime(2025, 1, 15, 12, 0)
        r_jan = Record(date_of_discharge=jan.date(), full_name='Jan Record', discharge_department='DeptTest', treating_physician='Dr', history='J', k_days=1, created_by=u.id, created_at=jan)
        # create record in current month
        now = datetime.datetime.utcnow()
        r_now = Record(date_of_discharge=now.date(), full_name='Now Record', discharge_department='DeptTest', treating_physician='Dr', history='N', k_days=1, created_by=u.id, created_at=now)
        db.session.add_all([r_jan, r_now])
        db.session.commit()

        client.post('/login', data={'username': 'ed', 'password': 'pass'}, follow_redirects=True)
        rv = client.get('/', query_string={'month': '1', 'year': '2025'})
        txt = rv.get_data(as_text=True)
        assert 'Jan Record' in txt
        assert 'Now Record' not in txt
