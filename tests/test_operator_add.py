import pytest
import datetime
from app import create_app, db
from models import User, Record

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


def test_operator_can_add_without_department(app, client):
    with app.app_context():
        ensure_user('op', role='operator')
        # ensure no departments exist
        # login as operator
        client.post('/login', data={'username': 'op', 'password': 'pass'}, follow_redirects=True)
        data = {
            'date_of_discharge': '2026-01-01',
            'full_name': 'NoDept Record',
            'discharge_department': '',
            'treating_physician': 'Dr',
            'history': 'ND',
            'k_days': '1'
        }
        rv = client.post('/records/add', data=data, follow_redirects=True)
        txt = rv.get_data(as_text=True)
        assert 'Record added' in txt
        # ensure record exists in DB
        r = Record.query.filter_by(full_name='NoDept Record').first()
        assert r is not None
        assert r.discharge_department is None or r.discharge_department == ''