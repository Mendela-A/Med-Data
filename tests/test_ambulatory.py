import pytest
from app import create_app
from models import db, User, AmbulatoryRecord
from datetime import date

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
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


def ensure_user(username, role='operator', password='password123'):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return u


def test_anonymous_redirect(client):
    rv = client.get('/ambulatory/', follow_redirects=False)
    assert rv.status_code == 302
    assert '/login' in rv.headers['Location']


def test_operator_can_add_ambulatory_record(app, client):
    with app.app_context():
        ensure_user('op_user', role='operator')
        
        # Login
        client.post('/login', data={'username': 'op_user', 'password': 'password123'}, follow_redirects=True)
        
        # Add Record
        data = {
            'journal_number': '123/A',
            'date': '2026-05-29',
            'full_name': 'Іванов Іван Іванович',
            'birth_date': '1990-01-01',
            'doctor': 'Д-р Петров',
            'diagnosis': 'ГРВІ, легкий перебіг',
            'comment': 'Тестовий коментар'
        }
        rv = client.post('/ambulatory/add', data=data, follow_redirects=True)
        txt = rv.get_data(as_text=True)
        
        assert 'успішно додано' in txt
        
        # Check DB
        r = AmbulatoryRecord.query.filter_by(journal_number='123/A').first()
        assert r is not None
        assert r.full_name == 'Іванов Іван Іванович'
        assert r.doctor == 'Д-р Петров'
        assert r.discharge_status == 'Опрацьовується'  # Defaults to processing


def test_editor_can_edit_ambulatory_record(app, client):
    with app.app_context():
        # Setup users
        ensure_user('ed_user', role='editor')
        op = ensure_user('op_user', role='operator')
        
        # Create record
        r = AmbulatoryRecord(
            journal_number='999/A',
            date=date(2026, 5, 29),
            full_name='Тестовий Пацієнт',
            birth_date=date(1985, 12, 10),
            doctor='Д-р Сидоров',
            diagnosis='Бронхіт',
            discharge_status='Опрацьовується',
            created_by=op.id,
            updated_by=op.id
        )
        db.session.add(r)
        db.session.commit()
        
        record_id = r.id
        
        # Login as editor
        client.post('/login', data={'username': 'ed_user', 'password': 'password123'}, follow_redirects=True)
        
        # Edit Record
        data = {
            'journal_number': '999/A-edited',
            'date': '2026-05-29',
            'full_name': 'Тестовий Пацієнт Редагований',
            'birth_date': '1985-12-10',
            'doctor': 'Д-р Сидоров',
            'diagnosis': 'Гострий бронхіт',
            'discharge_status': 'Виписаний',
            'comment': 'Успішно вилікуваний'
        }
        rv = client.post(f'/ambulatory/{record_id}/edit', data=data, follow_redirects=True)
        txt = rv.get_data(as_text=True)
        
        assert 'успішно оновлено' in txt
        
        # Verify in DB
        db.session.refresh(r)
        assert r.journal_number == '999/A-edited'
        assert r.full_name == 'Тестовий Пацієнт Редагований'
        assert r.diagnosis == 'Гострий бронхіт'
        assert r.discharge_status == 'Виписаний'
        assert r.comment == 'Успішно вилікуваний'


def test_operator_cannot_edit_ambulatory_record(app, client):
    with app.app_context():
        ensure_user('op_user', role='operator')
        op = ensure_user('op_user2', role='operator')
        
        r = AmbulatoryRecord(
            journal_number='111/A',
            date=date(2026, 5, 29),
            full_name='Пацієнт Недоторканий',
            birth_date=date(1985, 12, 10),
            doctor='Д-р Сидоров',
            diagnosis='Бронхіт',
            discharge_status='Опрацьовується',
            created_by=op.id,
            updated_by=op.id
        )
        db.session.add(r)
        db.session.commit()
        
        record_id = r.id
        
        # Login as operator
        client.post('/login', data={'username': 'op_user', 'password': 'password123'}, follow_redirects=True)
        
        # Attempt edit
        data = {
            'journal_number': '111/A-hacked',
            'date': '2026-05-29',
            'full_name': 'Змінене Ім\'я',
            'birth_date': '1985-12-10',
            'doctor': 'Д-р Сидоров',
            'diagnosis': 'Грип',
            'discharge_status': 'Виписаний'
        }
        rv = client.post(f'/ambulatory/{record_id}/edit', data=data, follow_redirects=True)
        
        # Should redirect to index or show access denied
        assert 'Доступ заборонено' in rv.get_data(as_text=True)
        
        # Verify DB is unchanged
        db.session.refresh(r)
        assert r.full_name == 'Пацієнт Недоторканий'
        assert r.discharge_status == 'Опрацьовується'


def test_ambulatory_role_has_access_only_to_ambulatory(app, client):
    with app.app_context():
        ensure_user('amb_user', role='ambulatory')

        # Login as ambulatory user
        client.post('/login', data={'username': 'amb_user', 'password': 'password123'}, follow_redirects=True)

        # 1. Main index redirect check
        rv = client.get('/', follow_redirects=True)
        txt = rv.get_data(as_text=True)
        # Should be redirected to ambulatory page
        assert 'Амбулаторна допомога' in txt

        # 2. Directly access ambulatory index
        rv2 = client.get('/ambulatory/', follow_redirects=False)
        assert rv2.status_code == 200

        # 3. Access forbidden standard records route
        rv3 = client.get('/records/add', follow_redirects=True)
        # Should be redirected to ambulatory page with access denied warning
        assert 'Доступ заборонено' in rv3.get_data(as_text=True)
        assert 'Амбулаторна допомога' in rv3.get_data(as_text=True)

        # 4. Successful addition of ambulatory record by ambulatory role
        data = {
            'journal_number': '777/A',
            'date': '2026-05-29',
            'full_name': 'Амбулаторний Користувач Тест',
            'birth_date': '1995-05-05',
            'doctor': 'Д-р Тестовий',
            'diagnosis': 'Ангіна',
            'comment': 'Швидкий додаток ролі'
        }
        rv4 = client.post('/ambulatory/add', data=data, follow_redirects=True)
        assert 'успішно додано' in rv4.get_data(as_text=True)

        # Verify DB entry
        r = AmbulatoryRecord.query.filter_by(journal_number='777/A').first()
        assert r is not None
        assert r.full_name == 'Амбулаторний Користувач Тест'
        assert r.discharge_status == 'Опрацьовується'
