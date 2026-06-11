from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from sqlalchemy import event

# SQLAlchemy instance (init in app)
db = SQLAlchemy()
bcrypt = Bcrypt()


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and other optimizations for SQLite."""
    cursor = dbapi_conn.cursor()

    # Журналювання та синхронізація
    cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging для кращої конкурентності
    cursor.execute("PRAGMA synchronous=NORMAL")  # Баланс між швидкістю та надійністю
    cursor.execute("PRAGMA busy_timeout=5000")  # 5 секунд таймаут для блокувань

    # Оптимізація кешу та пам'яті
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB кеш (negative = KB)
    cursor.execute("PRAGMA temp_store=MEMORY")  # Тимчасові таблиці в пам'яті
    cursor.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O (збільшено з 30MB)

    # Оптимізація читання
    cursor.execute("PRAGMA query_only=OFF")  # Дозволити запис
    cursor.execute("PRAGMA read_uncommitted=0")  # Строга ізоляція

    # Оптимізація запису
    cursor.execute("PRAGMA wal_autocheckpoint=1000")  # Checkpoint кожні 1000 сторінок
    cursor.execute("PRAGMA journal_size_limit=67108864")  # 64MB ліміт журналу

    # Аналіз та оптимізація запитів
    cursor.execute("PRAGMA optimize")  # Оптимізація статистики для планувальника
    cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")  # Поступова очистка вільного місця

    # Оптимізація для багатопотоковості
    cursor.execute("PRAGMA threads=4")  # Використати 4 потоки для паралельних операцій

    cursor.close()


def init_db_events(app):
    """Initialize database event listeners for SQLite optimizations."""
    if app.config.get('SQLALCHEMY_DATABASE_URI', '').startswith('sqlite'):
        with app.app_context():
            event.listen(db.engine, "connect", _set_sqlite_pragma)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='operator')  # operator/editor/admin/viewer

    records = db.relationship('Record', foreign_keys='Record.created_by', backref='creator', lazy=True)

    def set_password(self, password):
        # bcrypt returns bytes, store as decoded UTF-8 string
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"

class Record(db.Model):
    __tablename__ = 'records'
    __table_args__ = (
        db.Index('idx_record_discharge_status', 'discharge_status'),
        db.Index('idx_record_treating_physician', 'treating_physician'),
        db.Index('idx_record_discharge_department', 'discharge_department'),
        db.Index('idx_record_date_of_discharge', 'date_of_discharge'),
        db.Index('idx_record_full_name', 'full_name'),
        db.Index('idx_record_updated_at', 'updated_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    date_of_discharge = db.Column(db.Date, nullable=True)  # "дата_виписки"
    full_name = db.Column(db.String(200), nullable=False)  # "ПІБ"
    discharge_department = db.Column(db.String(200), nullable=True)  # "відділення_виписки"
    treating_physician = db.Column(db.String(200), nullable=True)  # "лікуючий_лікар"
    history = db.Column(db.Text, nullable=True)  # "історія"
    k_days = db.Column(db.Integer, nullable=True)  # "к_днів"
    discharge_status = db.Column(db.String(200), nullable=True)  # "статус_виписки"
    date_of_death = db.Column(db.Date, nullable=True)  # "дата_смерті"
    comment = db.Column(db.Text, nullable=True)  # "коментар"
    adsj   = db.Column(db.String(200), nullable=True)  # "АДСГ"
    suma   = db.Column(db.Numeric(12, 2), nullable=True)  # "Сума"
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    updater = db.relationship('User', foreign_keys=[updated_by], backref='updated_records')

    def __repr__(self):
        return f"<Record {self.id} {self.full_name}>"


class Audit(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    actor = db.relationship('User', backref='audit_logs', foreign_keys=[actor_id])
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Audit {self.id} {self.action}>"


class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Department {self.id} {self.name}>"


class StatusOption(db.Model):
    """Довідник статусів, керований адміном. `scope` відокремлює розділи
    (поки використовується лише 'ambulatory'); записи зберігають назву статусу
    текстом (без FK) — за прецедентом discharge_department."""
    __tablename__ = 'status_options'
    __table_args__ = (
        db.UniqueConstraint('scope', 'name', name='uq_status_options_scope_name'),
        db.Index('idx_status_options_scope', 'scope'),
    )

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False, default='ambulatory', server_default='ambulatory')
    name = db.Column(db.String(200), nullable=False)
    color = db.Column(db.String(20), nullable=False, default='secondary', server_default='secondary')  # bootstrap variant
    icon = db.Column(db.String(50), nullable=False, default='bi-circle', server_default='bi-circle')
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    is_default = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    show_in_stats = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    # Системний статус: на ньому тримається статистика/телеграм-бот —
    # не можна перейменувати, видалити чи деактивувати
    is_system = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<StatusOption {self.id} [{self.scope}] {self.name}>"


# Seed-набори мають збігатися з data-seed у міграціях
# 20260611_add_status_options і 20260611_status_scopes
DEFAULT_STATUS_OPTIONS = {
    'ambulatory': [
        # (name, color, icon, sort_order, is_default, show_in_stats, is_system, is_active)
        ('Виписаний', 'success', 'bi-check-circle', 10, False, True, False, True),
        ('Опрацьовується', 'warning', 'bi-clock', 20, True, False, False, True),
        ('Порушені вимоги', 'danger', 'bi-exclamation-triangle', 30, False, False, False, True),
        ('Епізод відсутній', 'dark', 'bi-file-earmark-x', 40, False, True, False, True),
    ],
    # records: усі три системні — на них тримаються статистика і tg-бот
    'records': [
        ('Виписаний', 'success', 'bi-check-circle', 10, False, True, True, True),
        ('Опрацьовується', 'warning', 'bi-clock', 20, True, True, True, True),
        ('Порушені вимоги', 'danger', 'bi-exclamation-triangle', 30, False, True, True, True),
        # легасі: смерть тепер ведеться через date_of_death; статус лишається
        # в довіднику неактивним, щоб старі записи рендерились і валідувались
        ('Помер', 'danger', 'bi-heartbreak', 40, False, False, False, False),
    ],
    # nszu: 'В обробці' — системний (дефолт моделі NSZUCorrection);
    # кольори відтворюють історичні бейджі nszu_list
    'nszu': [
        ('В обробці', 'secondary', 'bi-clock', 10, True, True, True, True),
        ('Опрацьовано', 'warning', 'bi-hourglass-split', 20, False, True, False, True),
        ('Оплачено', 'success', 'bi-check-circle', 30, False, True, False, True),
        ('Не підлягає оплаті', 'danger', 'bi-x-circle', 40, False, True, False, True),
    ],
}


def seed_status_options():
    """Заповнити довідник статусів для кожного порожнього scope.
    Викликається з init-db (свіжа БД, де міграції з seed не виконуються)."""
    seeded = False
    for scope, rows in DEFAULT_STATUS_OPTIONS.items():
        if StatusOption.query.filter_by(scope=scope).first():
            continue
        for name, color, icon, sort_order, is_default, show_in_stats, is_system, is_active in rows:
            db.session.add(StatusOption(
                scope=scope, name=name, color=color, icon=icon,
                sort_order=sort_order, is_default=is_default,
                show_in_stats=show_in_stats, is_system=is_system,
                is_active=is_active,
            ))
        seeded = True
    if seeded:
        db.session.commit()
    return seeded


# Зворотна сумісність зі старою назвою (тести, init-db)
seed_ambulatory_statuses = seed_status_options


class NSZUCorrection(db.Model):
    __tablename__ = 'nszu_corrections'
    __table_args__ = (
        db.Index('idx_nszu_status', 'status'),
        db.Index('idx_nszu_doctor', 'doctor'),
        db.Index('idx_nszu_created_at', 'created_at'),
        db.Index('idx_nszu_record_id', 'nszu_record_id'),
        db.Index('idx_nszu_date', 'date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)  # Дата створення корекції
    nszu_record_id = db.Column(db.String(100), nullable=False, index=True)  # UUID від НСЗУ
    doctor = db.Column(db.String(200), nullable=False)  # ПІБ лікаря
    status = db.Column(db.String(50), nullable=False, default='В обробці')  # Статус
    detail = db.Column(db.Text, nullable=True)  # Опис проблеми
    fakt_summ = db.Column(db.Numeric(10, 2), nullable=True)  # Фактична сума
    comment = db.Column(db.Text, nullable=True)  # Коментар

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='nszu_corrections_created')
    updater = db.relationship('User', foreign_keys=[updated_by], backref='nszu_corrections_updated')

    def __repr__(self):
        return f"<NSZUCorrection {self.id} {self.nszu_record_id}>"


class AmbulatoryRecord(db.Model):
    __tablename__ = 'ambulatory_records'
    __table_args__ = (
        db.Index('idx_amb_discharge_status', 'discharge_status'),
        db.Index('idx_amb_doctor', 'doctor'),
        db.Index('idx_amb_date', 'date'),
        db.Index('idx_amb_full_name', 'full_name'),
        db.Index('idx_amb_updated_at', 'updated_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    journal_number = db.Column(db.String(100), nullable=False)  # "Номер у журналі"
    date = db.Column(db.Date, nullable=False)  # "Дата"
    full_name = db.Column(db.String(200), nullable=False)  # "П.І.П (повністю)"
    birth_date = db.Column(db.Date, nullable=False)  # "Дата народження"
    doctor = db.Column(db.String(200), nullable=False)  # "Лікар"
    diagnosis = db.Column(db.Text, nullable=False)  # "Діагноз"
    discharge_status = db.Column(db.String(200), nullable=True)  # "Статус виписки"
    comment = db.Column(db.Text, nullable=True)  # "Коментар"
    is_urgent = db.Column(db.Boolean, default=False, nullable=False, server_default='0')  # "Ургентний стан"

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', foreign_keys=[created_by], backref='amb_records_created')
    updater = db.relationship('User', foreign_keys=[updated_by], backref='amb_records_updated')

    def __repr__(self):
        return f"<AmbulatoryRecord {self.id} {self.full_name}>"


def log_action(actor_id, action, target_type=None, target_id=None, details=None):
    """Create an audit log entry. Caller is responsible for committing."""
    a = Audit(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, details=details)
    db.session.add(a)
    return a
