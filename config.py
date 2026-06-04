import os
from sqlalchemy.pool import NullPool

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY environment variable is required. "
            "Set it via: export SECRET_KEY='your-secure-random-key'"
        )

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(basedir, 'data', 'app.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite doesn't benefit from connection pooling; NullPool creates a fresh
    # connection per request and closes it immediately, avoiding file-lock contention.
    SQLALCHEMY_ENGINE_OPTIONS = {'poolclass': NullPool}

    # Static file caching (matches nginx `expires 1d`)
    SEND_FILE_MAX_AGE_DEFAULT = 86400
    PREFERRED_URL_SCHEME = 'https'

    # Session cookie security. Set FLASK_ENV=production in docker-compose/env; defaults
    # to False in dev. Missing FLASK_ENV silently disables secure flag — set explicitly.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours
