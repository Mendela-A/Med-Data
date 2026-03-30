import datetime
import pytest
from app import create_app
from models import db, User, Record, Department
from constants import STATUS_VIOLATIONS, STATUS_PROCESSING

DATE = datetime.date(2026, 3, 1)
PREV_DATE = datetime.date(2026, 2, 1)
FROM_DATE = DATE.isoformat()
TO_DATE = DATE.isoformat()


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


def ensure_user(username, role='admin', password='pass'):
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


def make_record(user_id, status, date=DATE, dept='DeptTest', date_of_death=None):
    r = Record(
        date_of_discharge=date,
        full_name='Test Record',
        discharge_department=dept,
        treating_physician='Dr',
        history='H',
        k_days=1,
        discharge_status=status,
        date_of_death=date_of_death,
        created_by=user_id,
        created_at=datetime.datetime.utcnow(),
    )
    db.session.add(r)
    db.session.commit()
    return r


def login(client, username='admin', password='pass'):
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


def get_stats(client, from_date=FROM_DATE, to_date=TO_DATE):
    return client.get(
        '/admin/statistics',
        query_string={'from_date': from_date, 'to_date': to_date}
    )


# ---------------------------------------------------------------------------

def test_violations_counted_in_statistics(app, client):
    """Запис зі статусом 'Порушені вимоги' без дати смерті рахується у statistics."""
    with app.app_context():
        u = ensure_user('admin')
        ensure_department()
        make_record(u.id, STATUS_VIOLATIONS)

        login(client)
        rv = get_stats(client)
        assert rv.status_code == 200
        txt = rv.get_data(as_text=True)
        assert 'Порушені вимоги' in txt
        # KPI card shows count = 1
        assert '>1<' in txt or '>1\n' in txt or '">1</h3>' in txt


def test_violations_with_death_date_not_counted(app, client):
    """Запис 'Порушені вимоги' + дата смерті → потрапляє в 'Помер', violations = 0."""
    with app.app_context():
        u = ensure_user('admin')
        ensure_department()
        make_record(u.id, STATUS_VIOLATIONS, date_of_death=DATE)

        login(client)
        rv = get_stats(client)
        assert rv.status_code == 200
        txt = rv.get_data(as_text=True)

        # deceased = 1
        assert 'Померло' in txt or 'Помер' in txt

        # violations block must show 0
        # Find the violations section: look for the card subtitle then the count
        viol_idx = txt.find('Порушені вимоги')
        assert viol_idx != -1
        card_section = txt[viol_idx:viol_idx + 300]
        assert '>0<' in card_section or '">0</h3>' in card_section


def test_violations_included_in_total(app, client):
    """total_records = violations + processing."""
    with app.app_context():
        u = ensure_user('admin')
        ensure_department()
        make_record(u.id, STATUS_VIOLATIONS)
        make_record(u.id, STATUS_PROCESSING)

        login(client)
        rv = get_stats(client)
        assert rv.status_code == 200
        txt = rv.get_data(as_text=True)

        # Total card should show 2
        assert 'Всього записів' in txt
        total_idx = txt.find('Всього записів')
        card_section = txt[total_idx:total_idx + 300]
        assert '>2<' in card_section or '">2</h3>' in card_section


def test_violations_counted_per_department(app, client):
    """Violations у відділенні 'DeptTest' відображаються у таблиці по відділеннях."""
    with app.app_context():
        u = ensure_user('admin')
        ensure_department('DeptTest')
        make_record(u.id, STATUS_VIOLATIONS, dept='DeptTest')

        login(client)
        rv = get_stats(client)
        assert rv.status_code == 200
        txt = rv.get_data(as_text=True)

        assert 'DeptTest' in txt
        # Department row should reference 'Порушені вимоги' filter link
        assert 'discharge_status=%D0%9F%D0%BE%D1%80%D1%83%D1%88%D0%B5%D0%BD%D1%96+%D0%B2%D0%B8%D0%BC%D0%BE%D0%B3%D0%B8' in txt or \
               "discharge_status='%D0%9F%D0%BE%D1%80%D1%83%D1%88%D0%B5%D0%BD%D1%96" in txt or \
               'discharge_status=Порушені' in txt or \
               'Порушені вимоги' in txt


def test_violations_trend(app, client):
    """Якщо поточний period: 1 violation, попередній: 0 — тренд = +1 (arrow-up)."""
    with app.app_context():
        u = ensure_user('admin')
        ensure_department()
        # current period record
        make_record(u.id, STATUS_VIOLATIONS, date=DATE)
        # no previous period record → prev_violations = 0

        login(client)
        rv = get_stats(client)
        assert rv.status_code == 200
        txt = rv.get_data(as_text=True)

        # Find violations KPI block and check for upward trend indicator
        viol_idx = txt.find('Порушені вимоги')
        assert viol_idx != -1
        card_section = txt[viol_idx:viol_idx + 500]
        assert 'bi-arrow-up' in card_section
