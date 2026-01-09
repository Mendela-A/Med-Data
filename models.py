from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin

# SQLAlchemy instance (init in app)
db = SQLAlchemy()
bcrypt = Bcrypt()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='operator')  # operator/editor/admin

    records = db.relationship('Record', backref='creator', lazy=True)

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
    status = db.Column(db.String(200), nullable=True)
    date_of_death = db.Column(db.Date, nullable=True)  # "дата_смерті"
    comment = db.Column(db.Text, nullable=True)  # "коментар"
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Record {self.id} {self.full_name}>"
