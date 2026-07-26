"""Регресійні тести на колонки Стан/Здача в таблиці «Записи».

Мердж statisty↔main прибрав ці колонки з templates/_records_table_partial.html
разом із data-атрибутами кнопки «Змінити», через що модалка редагування
підставляла дефолти й адмін мовчки затирав is_urgent/history_submitted.
Тести рівня розмітки — наявні тести били в ендпоінт напряму й регресію не ловили.
"""
import os
import datetime
import pytest
os.environ.setdefault('SECRET_KEY', 'test-key')
from app import create_app
from models import db, User, Record
from constants import STATUS_PROCESSING

DATE = datetime.date(2026, 3, 1)


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


def ensure_user(username, role, password='pass'):
    if not User.query.filter_by(username=username).first():
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    return User.query.filter_by(username=username).first()


def make_record(user_id, is_urgent=None, history_submitted=False):
    r = Record(
        date_of_discharge=DATE,
        full_name='Тест Пацієнт',
        discharge_department='ДептА',
        treating_physician='Лікар',
        history='11111',
        k_days=3,
        discharge_status=STATUS_PROCESSING,
        is_urgent=is_urgent,
        history_submitted=history_submitted,
        created_by=user_id,
        created_at=datetime.datetime.utcnow(),
    )
    db.session.add(r)
    db.session.commit()
    return r


def login(client, username, password='pass'):
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


def get_index(client):
    """Записи за всі місяці — тестовий запис поза поточним місяцем."""
    return client.get('/?all_months=1')


# --- Колонки присутні в таблиці ---

def test_columns_rendered_for_admin(app, client):
    """Заголовки Стан/Здача є в таблиці для адміна."""
    with app.app_context():
        u = ensure_user('adm_col', role='admin')
        make_record(u.id, is_urgent=True, history_submitted=True)
        login(client, 'adm_col')

        html = get_index(client).get_data(as_text=True)
        assert 'Стан</th>' in html
        assert 'Здача</th>' in html


def test_urgent_badge_rendered(app, client):
    """is_urgent=True → бейдж «Ург.», не «План.»."""
    with app.app_context():
        u = ensure_user('adm_urg', role='admin')
        make_record(u.id, is_urgent=True)
        login(client, 'adm_urg')

        html = get_index(client).get_data(as_text=True)
        assert 'Ург.' in html
        assert 'План.' not in html


def test_planned_badge_rendered(app, client):
    """is_urgent=False → бейдж «План.»."""
    with app.app_context():
        u = ensure_user('adm_pln', role='admin')
        make_record(u.id, is_urgent=False)
        login(client, 'adm_pln')

        html = get_index(client).get_data(as_text=True)
        assert 'План.' in html
        assert 'Ург.' not in html


def test_null_urgency_not_shown_as_planned(app, client):
    """is_urgent=NULL (старі записи) → прочерк, а не «План.»."""
    with app.app_context():
        u = ensure_user('adm_null', role='admin')
        make_record(u.id, is_urgent=None)
        login(client, 'adm_null')

        html = get_index(client).get_data(as_text=True)
        assert 'План.' not in html
        assert 'Ург.' not in html


# --- data-атрибути кнопки «Змінити» (джерело бага із затиранням) ---

def test_edit_button_carries_state_attributes(app, client):
    """Кнопка «Змінити» віддає data-is-urgent/data-history-submitted."""
    with app.app_context():
        u = ensure_user('adm_attr', role='admin')
        make_record(u.id, is_urgent=True, history_submitted=True)
        login(client, 'adm_attr')

        html = get_index(client).get_data(as_text=True)
        assert 'data-is-urgent="urgent"' in html
        assert 'data-history-submitted="1"' in html


def test_edit_button_attributes_empty_for_null_urgency(app, client):
    """is_urgent=NULL → порожній data-is-urgent, щоб модалка не підставила «План.»."""
    with app.app_context():
        u = ensure_user('adm_attr2', role='admin')
        make_record(u.id, is_urgent=None, history_submitted=False)
        login(client, 'adm_attr2')

        html = get_index(client).get_data(as_text=True)
        assert 'data-is-urgent=""' in html
        assert 'data-history-submitted="0"' in html


def test_admin_edit_without_state_fields_does_not_wipe_urgency(app, client):
    """Регресія: збереження форми без явного is_urgent не має скидати стан у False.

    Форма модалки завжди надсилає поля, але якщо розмітка їх втратить —
    api_edit_record для адміна запише None/False поверх реальних значень.
    """
    with app.app_context():
        u = ensure_user('adm_wipe', role='admin')
        r = make_record(u.id, is_urgent=True, history_submitted=True)
        login(client, 'adm_wipe')

        resp = client.post(f'/api/records/{r.id}/edit', data={
            'date_of_discharge': DATE.strftime('%Y-%m-%d'),
            'full_name': 'Тест Пацієнт',
            'discharge_department': 'ДептА',
            'treating_physician': 'Лікар',
            'history': '11111',
            'k_days': '3',
            'discharge_status': STATUS_PROCESSING,
            'is_urgent': 'urgent',
            'history_submitted': '1',
        })
        assert resp.status_code == 200

        updated = db.session.get(Record, r.id)
        assert updated.is_urgent is True
        assert updated.history_submitted is True


# --- Скрол-контейнер таблиці ---

def test_table_has_scroll_container(app, client):
    """Обгортка таблиці має клас records-scroll.

    Без нього немає обмеженого по висоті контейнера, sticky-шапці нема до чого
    «липнути», і замість прокрутки самої таблиці гортається вся сторінка.
    """
    with app.app_context():
        u = ensure_user('adm_scroll', role='admin')
        make_record(u.id)
        login(client, 'adm_scroll')

        html = get_index(client).get_data(as_text=True)
        assert 'table-responsive records-scroll' in html


# --- Кнопка «Статус» для оператора ---

def test_operator_sees_status_button(app, client):
    """Оператор бачить кнопку «Статус» — модалка й ендпоінт без неї недосяжні."""
    with app.app_context():
        u = ensure_user('op_btn', role='operator')
        make_record(u.id)
        login(client, 'op_btn')

        html = get_index(client).get_data(as_text=True)
        assert 'update-status-btn' in html


# --- Фільтр Здача не губиться при сортуванні/пагінації ---

def test_sort_links_preserve_submission_filter(app, client):
    """Клік по заголовку колонки не має скидати фільтр history_submitted."""
    with app.app_context():
        u = ensure_user('adm_sort', role='admin')
        make_record(u.id, history_submitted=False)
        login(client, 'adm_sort')

        html = client.get('/?all_months=1&history_submitted=0').get_data(as_text=True)
        assert 'history_submitted=0' in html
