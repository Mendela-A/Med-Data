import pytest
from app import create_app, db
from models import User, Record, Department

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    yield app

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

def test_operator_add_does_not_auto_set_discharge_status(app, client):
    with app.app_context():
        ensure_user('op', role='operator')
        ensure_department()
        # login
        rv = client.post('/login', data={'username': 'op', 'password': 'pass'}, follow_redirects=True)
        assert rv.status_code == 200

        data = {
            'date_of_discharge': '2026-01-09',
            'full_name': 'Operator Auto Test',
            'discharge_department': 'DeptTest',
            'treating_physician': 'Dr',
            'history': 'HOP',
            'k_days': '1',
            'status': 'Some status'
        }
        client.post('/records/add', data=data, follow_redirects=True)
        r = Record.query.filter_by(full_name='Operator Auto Test').first()
        assert r is not None
        assert r.discharge_status is None or r.discharge_status == ''

def test_editor_can_view_and_set_discharge_status(app, client):
    with app.app_context():
        ensure_user('ed', role='editor')
        ensure_user('op', role='operator')
        ensure_department()

        # Create a record using operator
        client.post('/login', data={'username': 'op', 'password': 'pass'}, follow_redirects=True)
        data = {
            'date_of_discharge': '2026-01-09',
            'full_name': 'Editor Edit Test',
            'discharge_department': 'DeptTest',
            'treating_physician': 'Dr',
            'history': 'HED',
            'k_days': '2',
            'status': 'Initial'
        }
        client.post('/records/add', data=data, follow_redirects=True)
        r = Record.query.filter_by(full_name='Editor Edit Test').first()
        assert r is not None
        client.get('/logout')

        # Login as editor and GET edit page
        client.post('/login', data={'username': 'ed', 'password': 'pass'}, follow_redirects=True)
        rv = client.get(f'/records/{r.id}/edit')
        txt = rv.get_data(as_text=True)
        assert 'name="discharge_status"' in txt

        # POST updated discharge_status
        post_data = {
            'date_of_discharge': '2026-01-09',
            'full_name': r.full_name,
            'discharge_department': r.discharge_department,
            'treating_physician': r.treating_physician,
            'history': r.history,
            'k_days': str(r.k_days),
            'status': r.status,
            'discharge_status': 'Виписано'
        }
        client.post(f'/records/{r.id}/edit', data=post_data, follow_redirects=True)
        r2 = Record.query.get(r.id)
        assert r2.discharge_status == 'Виписано'
