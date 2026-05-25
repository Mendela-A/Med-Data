from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from sqlalchemy import event

# SQLAlchemy instance (init in app)
db = SQLAlchemy()
bcrypt = Bcrypt()


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable SQLite optimizations, falling back gracefully if unsupported."""
    import os
    cursor = dbapi_conn.cursor()

    # Вибір режиму журналювання (можна перевизначити через SQLITE_JOURNAL_MODE, наприклад, DELETE для Docker на Windows)
    journal_mode = os.environ.get('SQLITE_JOURNAL_MODE', 'WAL').upper()

    try:
        cursor.execute(f"PRAGMA journal_mode={journal_mode}")
    except Exception:
        try:
            cursor.execute("PRAGMA journal_mode=DELETE")
        except Exception:
            pass

    try:
        cursor.execute("PRAGMA synchronous=NORMAL")  # Баланс між швидкістю та надійністю
    except Exception:
        try:
            cursor.execute("PRAGMA synchronous=FULL")
        except Exception:
            pass

    try:
        cursor.execute("PRAGMA busy_timeout=5000")  # 5 секунд таймаут для блокувань
    except Exception:
        pass

    # Оптимізації кешу, пам'яті, читання/запису
    pragmas = [
        "PRAGMA cache_size=-64000",          # 64MB кеш (negative = KB)
        "PRAGMA temp_store=MEMORY",          # Тимчасові таблиці в пам'яті
        "PRAGMA mmap_size=268435456",        # 256MB memory-mapped I/O
        "PRAGMA query_only=OFF",             # Дозволити запис
        "PRAGMA read_uncommitted=0",         # Строга ізоляція
        "PRAGMA wal_autocheckpoint=1000",    # Checkpoint кожні 1000 сторінок (ігнорується в DELETE режимі)
        "PRAGMA journal_size_limit=67108864", # 64MB ліміт журналу
        "PRAGMA optimize",                   # Оптимізація статистики для планувальника
        "PRAGMA auto_vacuum=INCREMENTAL",    # Поступова очистка вільного місця
        "PRAGMA threads=4"                   # Використати 4 потоки для паралельних операцій
    ]

    for pragma in pragmas:
        try:
            cursor.execute(pragma)
        except Exception:
            pass

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
    date_of_admission = db.Column(db.Date, nullable=True, index=True)  # "дата_поступлення" (для Форми 007)
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
    bed_profile_name = db.Column(db.String(200), nullable=True)  # Назва профілю ліжка (для Форми 007)
    bed_capacity = db.Column(db.Integer, nullable=True)  # ліжковий фонд (для Форми 016)
    row_no = db.Column(db.Integer, nullable=True)        # № рядка у Формі 007 (МОЗ нумерація)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Department {self.id} {self.name}>"


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


class DailyReport(db.Model):
    """Форма 007/о — щоденний листок обліку руху хворих і ліжкового фонду."""
    __tablename__ = 'daily_reports'
    __table_args__ = (
        db.UniqueConstraint('report_date', 'department_id', name='uq_daily_report_date_dept'),
        db.Index('idx_daily_report_date', 'report_date'),
    )

    id                    = db.Column(db.Integer, primary_key=True)
    report_date           = db.Column(db.Date, nullable=False)
    department_id         = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)

    # col3 — розгорнуто ліжок (auto from dept.bed_capacity)
    beds_total            = db.Column(db.Integer, nullable=True)
    # col4 — в т.ч. на ремонті (manual)
    beds_renovation       = db.Column(db.Integer, nullable=True)
    # col5 — хворих на поч. минулої доби (auto = prev_day.patients_end)
    patients_start        = db.Column(db.Integer, nullable=True)
    # col6 — поступило всього (auto from records)
    admitted_total        = db.Column(db.Integer, nullable=True)
    # col7 — поступило сільських (manual)
    admitted_rural        = db.Column(db.Integer, nullable=True)
    # col8 — поступило дітей до 17р (manual)
    admitted_children     = db.Column(db.Integer, nullable=True)
    # col8_rural — поступило дітей до 17р сільських (manual)
    admitted_children_rural = db.Column(db.Integer, nullable=True)
    # col9 — переведено з ін. відділів (manual)
    transferred_in        = db.Column(db.Integer, nullable=True)
    # col10 — переведено в ін. відділи (manual)
    transferred_out       = db.Column(db.Integer, nullable=True)
    # col11 — виписано всього (auto from records)
    discharged_total      = db.Column(db.Integer, nullable=True)
    # col12 — виписано в ін. стаціонари (manual)
    discharged_to_other   = db.Column(db.Integer, nullable=True)
    # col13 — померло (auto from records)
    deaths                = db.Column(db.Integer, nullable=True)
    # col14 — на поч. поточного дня всього (computed: col5+col6+col9-col10-col11-col13)
    patients_end          = db.Column(db.Integer, nullable=True)
    # col15 — на поч. поточного дня сільських (manual)
    patients_end_rural    = db.Column(db.Integer, nullable=True)
    # col16 — матерів при дітях (manual)
    mothers_with_children = db.Column(db.Integer, nullable=True)
    # col17 — вільних чоловічих (manual)
    free_male             = db.Column(db.Integer, nullable=True)
    # col18 — вільних жіночих (manual)
    free_female           = db.Column(db.Integer, nullable=True)
    # col19 free_total = beds_total - patients_end (computed in code)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    department = db.relationship('Department', backref='daily_reports')
    creator    = db.relationship('User', foreign_keys=[created_by])
    updater    = db.relationship('User', foreign_keys=[updated_by])

    @property
    def free_total(self):
        if self.beds_total is not None and self.patients_end is not None:
            return self.beds_total - self.patients_end
        return None

    def compute_patients_end(self):
        """col14 = col5 + col6 + col9 - col10 - col11 - col13"""
        return (
            (self.patients_start or 0)
            + (self.admitted_total or 0)
            + (self.transferred_in or 0)
            - (self.transferred_out or 0)
            - (self.discharged_total or 0)
            - (self.deaths or 0)
        )

    def __repr__(self):
        return f"<DailyReport {self.report_date} dept={self.department_id}>"


class PrintSettings(db.Model):
    """Singleton (id=1) — налаштування шапки для друку форм."""
    __tablename__ = 'print_settings'

    id             = db.Column(db.Integer, primary_key=True)
    ministry       = db.Column(db.String(200), nullable=False,
                               default="Міністерство охорони здоров'я України")
    org_name       = db.Column(db.String(200), nullable=False,
                               default='КНП «Калуська центральна районна лікарня»')
    org_short_name = db.Column(db.String(100), nullable=False,
                               default='КНП «Калуська ЦРЛ»')
    org_address    = db.Column(db.String(300), nullable=False,
                               default='вул. Каракая, 25, м. Калуш, Івано-Франківська обл., 77300')
    signer1_title  = db.Column(db.String(200), nullable=False,
                               default='Заступник генерального директора')
    signer1_name   = db.Column(db.String(100), nullable=False,
                               default='Л. Луців')
    signer2_label  = db.Column(db.String(100), nullable=False,
                               default='Відповідальний:')
    signer2_name   = db.Column(db.String(100), nullable=False,
                               default='Валерій ПАЛЯНИЦЯ')
    form007_title    = db.Column(db.String(200), nullable=False,
                                 default='ЛИСТОК ОБЛІКУ РУХУ ХВОРИХ')
    form007_subtitle = db.Column(db.String(200), nullable=False,
                                 default='і ліжкового фонду стаціонару')
    form016_title    = db.Column(db.String(200), nullable=False,
                                 default='ЗВЕДЕНА ВІДОМІСТЬ ОБЛІКУ РУХУ ХВОРИХ')
    form016_subtitle = db.Column(db.String(200), nullable=False,
                                 default='і ліжкового фонду стаціонару')
    form007_form_no  = db.Column(db.String(50),  nullable=False,
                                 default='Форма № 007/о')
    form007_decree   = db.Column(db.String(200), nullable=False,
                                 default='Затверджено наказом МОЗ України від 29.05.2013 р. № 110')
    form016_form_no  = db.Column(db.String(50),  nullable=False,
                                 default='Форма № 016/о')
    form016_decree   = db.Column(db.String(200), nullable=False,
                                 default='Затверджено наказом МОЗ України від 27.12.05 р. № 760')

    def __repr__(self):
        return f"<PrintSettings org={self.org_short_name}>"


def log_action(actor_id, action, target_type=None, target_id=None, details=None):
    """Create an audit log entry. Caller is responsible for committing."""
    a = Audit(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, details=details)
    db.session.add(a)
    return a
