import pytest
from app import create_app
from models import db, User, AmbulatoryRecord, StatusOption, seed_ambulatory_statuses
from datetime import date


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        seed_ambulatory_statuses()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    with app.app_context():
        yield app.test_client()


def ensure_user(username, role='admin', password='password123'):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return u


def login(client, username, password='password123'):
    return client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


def make_record(status='Опрацьовується', journal_number='1/A'):
    op = ensure_user('rec_op', role='operator')
    r = AmbulatoryRecord(
        journal_number=journal_number,
        date=date(2026, 6, 1),
        full_name='Тестовий Пацієнт',
        birth_date=date(1990, 1, 1),
        doctor='Д-р Тест',
        diagnosis='Тестовий діагноз',
        discharge_status=status,
        created_by=op.id,
        updated_by=op.id,
    )
    db.session.add(r)
    db.session.commit()
    return r


def test_seed_creates_default_statuses(app):
    with app.app_context():
        names = {s.name for s in StatusOption.query.filter_by(scope='ambulatory').all()}
        assert names == {'Виписаний', 'Опрацьовується', 'Порушені вимоги', 'Епізод відсутній'}
        default = StatusOption.query.filter_by(scope='ambulatory', is_default=True).all()
        assert len(default) == 1
        assert default[0].name == 'Опрацьовується'


def test_admin_can_create_status_and_it_appears_in_list(app, client):
    with app.app_context():
        ensure_user('adm', role='admin')
        login(client, 'adm')

        rv = client.post('/admin/statuses/create', data={
            'name': 'На дообстеженні', 'color': 'info', 'icon': 'bi-search', 'show_in_stats': 'on',
        }, follow_redirects=True)
        assert 'успішно створено' in rv.get_data(as_text=True)

        s = StatusOption.query.filter_by(scope='ambulatory', name='На дообстеженні').first()
        assert s is not None
        assert s.color == 'info'
        assert s.show_in_stats is True

        # Новий статус доступний у фільтрі та модалці амбулаторної сторінки
        rv2 = client.get('/ambulatory/')
        assert 'На дообстеженні' in rv2.get_data(as_text=True)


def test_non_admin_cannot_manage_statuses(app, client):
    with app.app_context():
        ensure_user('ed', role='editor')
        login(client, 'ed')
        rv = client.post('/admin/statuses/create', data={'name': 'Хакнутий'}, follow_redirects=True)
        assert 'Доступ заборонено' in rv.get_data(as_text=True)
        assert StatusOption.query.filter_by(name='Хакнутий').first() is None


def test_rename_status_updates_existing_records(app, client):
    with app.app_context():
        ensure_user('adm', role='admin')
        r = make_record(status='Опрацьовується')
        s = StatusOption.query.filter_by(scope='ambulatory', name='Опрацьовується').first()

        login(client, 'adm')
        rv = client.post(f'/admin/statuses/{s.id}/update', data={
            'name': 'В роботі', 'color': s.color, 'icon': s.icon,
            'sort_order': s.sort_order, 'show_in_stats': 'on',
        }, follow_redirects=True)
        txt = rv.get_data(as_text=True)
        assert 'перейменовано' in txt

        db.session.refresh(r)
        assert r.discharge_status == 'В роботі'
        assert StatusOption.query.filter_by(name='Опрацьовується').first() is None


def test_delete_status_blocked_when_in_use(app, client):
    with app.app_context():
        ensure_user('adm', role='admin')
        make_record(status='Виписаний')
        s = StatusOption.query.filter_by(scope='ambulatory', name='Виписаний').first()

        login(client, 'adm')
        rv = client.post(f'/admin/statuses/{s.id}/delete', follow_redirects=True)
        assert 'Неможливо видалити' in rv.get_data(as_text=True)
        assert StatusOption.query.filter_by(name='Виписаний').first() is not None


def test_delete_unused_status(app, client):
    with app.app_context():
        ensure_user('adm', role='admin')
        s = StatusOption.query.filter_by(scope='ambulatory', name='Порушені вимоги').first()

        login(client, 'adm')
        rv = client.post(f'/admin/statuses/{s.id}/delete', follow_redirects=True)
        assert 'видалено' in rv.get_data(as_text=True)
        assert StatusOption.query.filter_by(name='Порушені вимоги').first() is None


def test_default_status_cannot_be_deactivated(app, client):
    with app.app_context():
        ensure_user('adm', role='admin')
        s = StatusOption.query.filter_by(scope='ambulatory', is_default=True).first()

        login(client, 'adm')
        rv = client.post(f'/admin/statuses/{s.id}/toggle', follow_redirects=True)
        assert 'не можна деактивувати' in rv.get_data(as_text=True)
        db.session.refresh(s)
        assert s.is_active is True


def test_new_record_gets_configured_default_status(app, client):
    with app.app_context():
        ensure_user('adm', role='admin')
        ensure_user('op', role='operator')

        # Адмін призначає інший статус за замовчуванням
        login(client, 'adm')
        client.post('/admin/statuses/create', data={'name': 'Прийнято', 'color': 'info'}, follow_redirects=True)
        s = StatusOption.query.filter_by(scope='ambulatory', name='Прийнято').first()
        rv = client.post(f'/admin/statuses/{s.id}/set-default', follow_redirects=True)
        assert 'за замовчуванням' in rv.get_data(as_text=True)
        client.post('/logout')

        # Оператор додає запис — отримує новий дефолтний статус
        login(client, 'op')
        rv2 = client.post('/ambulatory/add', data={
            'journal_number': '55/A',
            'date': '2026-06-10',
            'full_name': 'Новий Пацієнт',
            'birth_date': '1980-02-02',
            'doctor': 'Д-р Дефолт',
            'diagnosis': 'ГРВІ',
        }, follow_redirects=True)
        assert 'успішно додано' in rv2.get_data(as_text=True)
        r = AmbulatoryRecord.query.filter_by(journal_number='55/A').first()
        assert r.discharge_status == 'Прийнято'


def test_edit_rejects_unknown_status(app, client):
    with app.app_context():
        ensure_user('ed', role='editor')
        r = make_record(status='Опрацьовується')

        login(client, 'ed')
        rv = client.post(f'/ambulatory/{r.id}/edit', data={
            'journal_number': r.journal_number,
            'date': '2026-06-01',
            'full_name': r.full_name,
            'birth_date': '1990-01-01',
            'doctor': r.doctor,
            'diagnosis': r.diagnosis,
            'discharge_status': 'Вигаданий статус',
        }, follow_redirects=True)
        assert 'Невідомий статус' in rv.get_data(as_text=True)
        db.session.refresh(r)
        assert r.discharge_status == 'Опрацьовується'


def test_edit_accepts_inactive_status(app, client):
    """Редагування запису з деактивованим статусом не повинно блокуватись."""
    with app.app_context():
        ensure_user('adm', role='admin')
        ensure_user('ed', role='editor')
        r = make_record(status='Епізод відсутній')
        s = StatusOption.query.filter_by(scope='ambulatory', name='Епізод відсутній').first()

        login(client, 'adm')
        client.post(f'/admin/statuses/{s.id}/toggle', follow_redirects=True)
        db.session.refresh(s)
        assert s.is_active is False
        client.post('/logout')

        login(client, 'ed')
        rv = client.post(f'/ambulatory/{r.id}/edit', data={
            'journal_number': r.journal_number,
            'date': '2026-06-01',
            'full_name': r.full_name,
            'birth_date': '1990-01-01',
            'doctor': r.doctor,
            'diagnosis': 'Уточнений діагноз',
            'discharge_status': 'Епізод відсутній',
        }, follow_redirects=True)
        assert 'успішно оновлено' in rv.get_data(as_text=True)
        db.session.refresh(r)
        assert r.diagnosis == 'Уточнений діагноз'


def test_orphan_statuses_shown_on_admin_page(app, client):
    with app.app_context():
        ensure_user('adm', role='admin')
        make_record(status='Статус-привид')

        login(client, 'adm')
        rv = client.get('/admin/statuses')
        txt = rv.get_data(as_text=True)
        assert 'Статус-привид' in txt
        assert 'поза довідником' in txt
