from datetime import datetime
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
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_db_events(app):
    """Initialize database event listeners for SQLite optimizations."""
    if app.config.get('SQLALCHEMY_DATABASE_URI', '').startswith('sqlite'):
        with app.app_context():
            event.listen(db.engine, "connect", _set_sqlite_pragma)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='operator')  # operator/editor/admin

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
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Audit {self.id} {self.action}>"


class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Department {self.id} {self.name}>"


def log_action(actor_id, action, target_type=None, target_id=None, details=None):
    """Create an audit log entry and commit it."""
    a = Audit(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, details=details)
    db.session.add(a)
    db.session.commit()
    return a
