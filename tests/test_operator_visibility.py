import pytest, datetime
from app import create_app, db
from models import User, Record, Department

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        # ensure a clean DB for tests
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


def test_operator_default_month_filter(app, client):
    with app.app_context():
        ensure_user('op2', role='operator')
        ensure_department()
        client.post('/login', data={'username': 'op2', 'password': 'pass'}, follow_redirects=True)
        # create a record in the past (created_at older than 60 days)
        old_date = datetime.datetime.utcnow() - datetime.timedelta(days=60)
        r = Record(date_of_discharge=old_date.date(), full_name='Old Record', discharge_department='DeptTest', treating_physician='Dr', history='OLD', k_days=1, created_by=User.query.filter_by(username='op2').first().id, created_at=old_date)
        db.session.add(r)
        db.session.commit()

        rv = client.get('/')
        txt = rv.get_data(as_text=True)
        assert 'Old Record' not in txt

        # now request with all_months
        rv2 = client.get('/', query_string={'all_months':'1'})
        txt2 = rv2.get_data(as_text=True)
        assert 'Old Record' in txt2
