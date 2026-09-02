# tests/test_form007_concurrent.py
"""Регресія: синхронізація одночасного редагування Форми 007.

Покриває:
  * ендпоінт ревізії `/statisty/form007/<range>/revision` (день / місяць / сміття);
  * оптимістичне блокування по кожному відділенню окремо у POST `/edit`
    (`_baseline_<id>` + `_dirty_<id>`), часткове збереження та no-op guard.
"""
import re
import datetime

import pytest

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


def ensure_department(name, row_no=1, bed_capacity=None):
    d = Department.query.filter_by(name=name).first()
    if not d:
        d = Department(name=name, row_no=row_no, bed_capacity=bed_capacity)
        db.session.add(d)
        db.session.commit()
    return d


def login(client, username='admin', password='pass'):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=True)


DATE = '2026-05-01'
DAY = datetime.date(2026, 5, 1)


def revision_of(client, range_str=DATE):
    rv = client.get(f'/statisty/form007/{range_str}/revision')
    assert rv.status_code == 200, rv.status_code
    return rv.get_json()['revision']


def baseline_of(dept_id, report_date=DAY):
    """Поточний токен оптимістичного блокування рядка (як його бачить сервер)."""
    db.session.expire_all()
    r = DailyReport.query.filter_by(report_date=report_date, department_id=dept_id).first()
    return r.updated_at.isoformat() if (r and r.updated_at) else ''


def row_of(dept_id, report_date=DAY):
    db.session.expire_all()
    return DailyReport.query.filter_by(report_date=report_date, department_id=dept_id).first()


def baselines_from_html(html):
    """Витягти всі `_baseline_<id>` зі сторінки редагування."""
    return {
        int(m.group(1)): m.group(2)
        for m in re.finditer(
            r'name="_baseline_(\d+)"\s+value="([^"]*)"', html)
    }


def payload(dept_id, baseline='', dirty=True, **fields):
    data = {f'{k}_{dept_id}': str(v) for k, v in fields.items()}
    data[f'_baseline_{dept_id}'] = baseline
    if dirty:
        data[f'_dirty_{dept_id}'] = '1'
    return data


# ---------------------------------------------------------------------------
# 1-4. Ендпоінт ревізії
# ---------------------------------------------------------------------------

def test_revision_day_empty(app, client):
    with app.app_context():
        ensure_user('admin')
        login(client)

        rv = client.get(f'/statisty/form007/{DATE}/revision')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['range'] == DATE
        assert data['revision'] == '0:0'


def test_revision_month_range(app, client):
    with app.app_context():
        ensure_user('admin')
        dept = ensure_department('Терапевтичне', row_no=1)
        db.session.add(DailyReport(report_date=DAY, department_id=dept.id,
                                   patients_start=5, patients_end=5))
        db.session.commit()
        login(client)

        rv = client.get('/statisty/form007/2026-05/revision')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['range'] == '2026-05'
        # Рядок за 2026-05-01 потрапляє в діапазон місяця.
        assert data['revision'].startswith('1:')
        assert data['revision'] != '0:0'


def test_revision_garbage_range_404(app, client):
    with app.app_context():
        ensure_user('admin')
        login(client)

        assert client.get('/statisty/form007/not-a-date/revision').status_code == 404
        assert client.get('/statisty/form007/2026-13-01/revision').status_code == 404


def test_revision_changes_on_save_and_is_stable_on_noop(app, client):
    with app.app_context():
        ensure_user('admin')
        dept = ensure_department('Терапевтичне', row_no=1)
        login(client)

        rev0 = revision_of(client)
        assert rev0 == '0:0'

        # Реальне збереження — токен змінюється.
        data = payload(dept.id, baseline='', patients_start=10, admitted_total=3)
        assert client.post(f'/statisty/form007/{DATE}/edit', data=data,
                           follow_redirects=True).status_code == 200
        rev1 = revision_of(client)
        assert rev1 != rev0
        assert rev1.startswith('1:')

        # No-op збереження тих самих значень — токен НЕ змінюється.
        data2 = payload(dept.id, baseline=baseline_of(dept.id),
                        patients_start=10, admitted_total=3)
        assert client.post(f'/statisty/form007/{DATE}/edit', data=data2,
                           follow_redirects=True).status_code == 200
        assert revision_of(client) == rev1


# ---------------------------------------------------------------------------
# 5-9. Оптимістичне блокування по відділеннях
# ---------------------------------------------------------------------------

def test_two_operators_different_departments_both_saved(app, client):
    """Два оператори правлять різні відділення — обидва записи проходять."""
    with app.app_context():
        ensure_user('op_a')
        ensure_user('op_b')
        d1 = ensure_department('Терапевтичне', row_no=1)
        d2 = ensure_department('Хірургічне', row_no=2)
        d1_id, d2_id = d1.id, d2.id

        ca = app.test_client()
        cb = app.test_client()
        login(ca, 'op_a')
        login(cb, 'op_b')

        # Обидва відкрили сторінку до будь-яких змін — базові токени порожні.
        html = ca.get(f'/statisty/form007/{DATE}/edit').get_data(as_text=True)
        base = baselines_from_html(html)
        assert base[d1_id] == '' and base[d2_id] == ''

        ra = ca.post(f'/statisty/form007/{DATE}/edit',
                     data=payload(d1_id, baseline=base[d1_id],
                                  patients_start=10, admitted_total=2),
                     follow_redirects=True)
        rb = cb.post(f'/statisty/form007/{DATE}/edit',
                     data=payload(d2_id, baseline=base[d2_id],
                                  patients_start=7, admitted_total=1),
                     follow_redirects=True)
        assert ra.status_code == 200 and rb.status_code == 200
        assert 'частково' not in ra.get_data(as_text=True)
        assert 'частково' not in rb.get_data(as_text=True)

        r1, r2 = row_of(d1_id), row_of(d2_id)
        assert r1 is not None and r2 is not None
        assert (r1.patients_start, r1.admitted_total) == (10, 2)
        assert (r2.patients_start, r2.admitted_total) == (7, 1)
        # col14 перерахований сервером
        assert r1.patients_end == 12
        assert r2.patients_end == 8


def test_same_department_stale_baseline_is_rejected(app, client):
    """Оператор B зі застарілим базовим токеном не перезаписує дані оператора A."""
    with app.app_context():
        ensure_user('op_a')
        ensure_user('op_b')
        d1 = ensure_department('Терапевтичне', row_no=1)
        d1_id = d1.id

        # Рядок уже існує — обидва оператори бачать один і той самий токен.
        db.session.add(DailyReport(report_date=DAY, department_id=d1_id,
                                   patients_start=5, patients_end=5))
        db.session.commit()
        shared_baseline = baseline_of(d1_id)
        assert shared_baseline != ''

        ca = app.test_client()
        cb = app.test_client()
        login(ca, 'op_a')
        login(cb, 'op_b')

        # A зберігає першим.
        ra = ca.post(f'/statisty/form007/{DATE}/edit',
                     data=payload(d1_id, baseline=shared_baseline, patients_start=42),
                     follow_redirects=True)
        assert ra.status_code == 200
        assert 'частково' not in ra.get_data(as_text=True)
        assert row_of(d1_id).patients_start == 42
        new_baseline = baseline_of(d1_id)
        assert new_baseline != shared_baseline

        # B зберігає зі застарілим токеном — конфлікт, дані A лишаються.
        rb = cb.post(f'/statisty/form007/{DATE}/edit',
                     data=payload(d1_id, baseline=shared_baseline, patients_start=99),
                     follow_redirects=True)
        assert rb.status_code == 200
        assert 'частково' in rb.get_data(as_text=True)

        r = row_of(d1_id)
        assert r.patients_start == 42
        assert baseline_of(d1_id) == new_baseline


def test_noop_save_does_not_bump_updated_at(app, client):
    with app.app_context():
        ensure_user('admin')
        dept = ensure_department('Терапевтичне', row_no=1)
        dept_id = dept.id
        login(client)

        # Створюємо рядок через форму, щоб усі 16 полів мали рівно ті значення,
        # які потім повторно надішлемо (решта — None).
        client.post(f'/statisty/form007/{DATE}/edit',
                    data=payload(dept_id, baseline='', patients_start=10,
                                 admitted_total=3, deaths=1),
                    follow_redirects=True)
        before = baseline_of(dept_id)
        assert before != ''

        rv = client.post(f'/statisty/form007/{DATE}/edit',
                         data=payload(dept_id, baseline=before, patients_start=10,
                                      admitted_total=3, deaths=1),
                         follow_redirects=True)
        assert rv.status_code == 200
        assert 'частково' not in rv.get_data(as_text=True)
        assert baseline_of(dept_id) == before


def test_js_off_fallback_saves_and_creates_no_empty_rows(app, client):
    """Без жодного `_dirty_*` обробляються всі відділення, але порожні пропускаються."""
    with app.app_context():
        ensure_user('admin')
        d1 = ensure_department('Терапевтичне', row_no=1)
        d2 = ensure_department('Хірургічне', row_no=2)
        d3 = ensure_department('Неврологічне', row_no=3)
        d1_id = d1.id
        login(client)

        data = payload(d1_id, baseline='', dirty=False, patients_start=8, admitted_total=4)
        # Порожні (незаповнені) поля для решти відділень — рядки не мають створитись.
        for other in (d2.id, d3.id):
            data[f'_baseline_{other}'] = ''
            data[f'patients_start_{other}'] = ''
            data[f'admitted_total_{other}'] = ''

        assert not any(k.startswith('_dirty_') for k in data)

        rv = client.post(f'/statisty/form007/{DATE}/edit', data=data, follow_redirects=True)
        assert rv.status_code == 200
        assert 'частково' not in rv.get_data(as_text=True)

        db.session.expire_all()
        rows = DailyReport.query.filter_by(report_date=DAY).all()
        assert len(rows) == 1
        assert rows[0].department_id == d1_id
        assert (rows[0].patients_start, rows[0].admitted_total) == (8, 4)
        assert rows[0].patients_end == 12


def test_new_row_baseline_then_stale_empty_baseline_conflicts(app, client):
    """Порожній базовий токен створює рядок; повторний порожній токен — конфлікт."""
    with app.app_context():
        ensure_user('op_a')
        ensure_user('op_b')
        dept = ensure_department('Терапевтичне', row_no=1)
        dept_id = dept.id

        ca = app.test_client()
        cb = app.test_client()
        login(ca, 'op_a')
        login(cb, 'op_b')

        ra = ca.post(f'/statisty/form007/{DATE}/edit',
                     data=payload(dept_id, baseline='', patients_start=11, admitted_total=2),
                     follow_redirects=True)
        assert ra.status_code == 200
        assert 'частково' not in ra.get_data(as_text=True)

        r = row_of(dept_id)
        assert r is not None
        assert (r.patients_start, r.admitted_total) == (11, 2)
        created_token = baseline_of(dept_id)
        assert created_token != ''

        # B тримає сторінку, відкриту ще до створення рядка → його токен порожній.
        rb = cb.post(f'/statisty/form007/{DATE}/edit',
                     data=payload(dept_id, baseline='', patients_start=77, admitted_total=9),
                     follow_redirects=True)
        assert rb.status_code == 200
        html = rb.get_data(as_text=True)
        assert 'частково' in html
        assert (dept.bed_profile_name or dept.name) in html

        r = row_of(dept_id)
        assert (r.patients_start, r.admitted_total) == (11, 2)
        assert baseline_of(dept_id) == created_token
