"""Захист сюїти від запису в бойову БД.

Фікстури в тестах роблять так:

    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'   # ← не діє

Flask-SQLAlchemy 3.x створює движки одразу в `init_app()`, читаючи конфіг на
той момент, тож підміна URI після `create_app()` ігнорується: движок лишається
прив'язаним до `DATABASE_URL` (а без нього — до `data/app.db` з config.py).
Через це `db.drop_all()` у teardown фікстур зносив таблиці справжньої бази.

Conftest імпортується pytest'ом до будь-якого тестового модуля, тому виставлена
тут змінна оточення потрапляє в `config.Config` ще до створення движка.

Шлях перевизначається БЕЗУМОВНО — навіть якщо `DATABASE_URL` уже стоїть в
оточенні. Це навмисно: інакше запуск pytest у терміналі з бойовим
`DATABASE_URL` знову знищив би базу.

Використано файл у тимчасовій теці, а не `:memory:`, бо config.py задає
`poolclass: NullPool` — з ним кожне з'єднання отримувало б окрему порожню
in-memory базу.
"""
import atexit
import os
import shutil
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix='medapp-tests-')
_DB_PATH = os.path.join(_TMPDIR, 'test.db').replace('\\', '/')

os.environ['DATABASE_URL'] = f'sqlite:///{_DB_PATH}'
os.environ.setdefault('SECRET_KEY', 'test-key')


@atexit.register
def _cleanup_tmp_db():
    shutil.rmtree(_TMPDIR, ignore_errors=True)


def pytest_report_header(config):
    return f'test database: {_DB_PATH}'
