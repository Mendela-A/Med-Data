#!/bin/sh
set -e

# ensure FLASK_APP
export FLASK_APP=${FLASK_APP:-app.py}

# Ensure data dir exists (may already exist from Dockerfile with correct ownership)
mkdir -p /app/data 2>/dev/null || true
mkdir -p /app/logs 2>/dev/null || true

# Initialize DB if not present or missing expected tables
if [ ! -f /app/data/app.db ]; then
  echo "Initializing database (no DB file found)..."
  flask init-db || true
  flask db stamp head || true
  if [ -n "$ADMIN_USER" ] && [ -n "$ADMIN_PASSWORD" ]; then
    echo "Creating admin user $ADMIN_USER"
    flask create-admin "$ADMIN_USER" "$ADMIN_PASSWORD" || true
  fi
else
  # Check if users table exists; if not, initialize DB
  echo "DB file exists. Checking schema..."
  python - <<PY || true
from sqlalchemy import create_engine, text
import os
uri = os.environ.get('DATABASE_URL', 'sqlite:////app/data/app.db')
eng = create_engine(uri)
with eng.connect() as conn:
    res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"))
    if res.fetchone() is None:
        print('Users table missing; initializing DB...')
        import subprocess, os
        subprocess.run(['flask', 'init-db'])
        subprocess.run(['flask', 'db', 'stamp', 'head'])
        if os.environ.get('ADMIN_USER') and os.environ.get('ADMIN_PASSWORD'):
            subprocess.run(['flask', 'create-admin', os.environ.get('ADMIN_USER'), os.environ.get('ADMIN_PASSWORD')])
    else:
        print('Schema OK')
PY
  echo "Applying pending migrations..."
  flask db upgrade || true
fi

# Run command
exec "$@"
