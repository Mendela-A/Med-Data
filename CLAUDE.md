# CLAUDE.md — project context for AI assistants

## Stack
Flask + SQLAlchemy + Flask-Migrate (Alembic) + SQLite (WAL mode). Python 3.x. Docker/Gunicorn.

## Critical files (read these first)
- `models.py` — all DB models, indexes, relationships, SQLite pragma config
- `config.py` — env vars (SECRET_KEY required, DATABASE_URL optional)
- `app/__init__.py` — app factory, CLI commands (init-db, create-admin, backup-db)
- `app/extensions.py` — extension init order (db, migrate, login_manager, bcrypt)
- `entrypoint.sh` — Docker startup: init-db → stamp head → db upgrade
- `migrations/versions/` — schema history (chain: 20260109 → e451abd → 20260321 → 20260330_*)

## Blueprint structure
- `app/blueprints/records/` — CRUD for medical records (виписки)
- `app/blueprints/admin/` — users, stats dashboard, audit logs
- `app/blueprints/nszu/` — NSZU corrections (корекції НСЗУ)
- `app/blueprints/auth/` — login/logout

## Do NOT read unless asked
- `static/` — CSS/JS assets, no logic impact
- `migrations/env.py`, `migrations/script.py.mako` — Alembic boilerplate
- `scripts/` — one-off maintenance utilities

## Common commands
```
flask db migrate -m "description"   # generate new migration from model changes
flask db upgrade                    # apply pending migrations
flask db current                    # show current migration revision
flask db history                    # show full migration chain
flask init-db                       # create all tables (bypasses migrations)
flask create-admin <user> <pass>    # create admin user
flask backup-db                     # hot SQLite backup to data/backup_YYYYMMDD.db
```

## DB migration workflow
1. Change models in `models.py`
2. `flask db migrate -m "description"` — generates migration file
3. Review generated file in `migrations/versions/`
4. Commit + redeploy → `entrypoint.sh` runs `flask db upgrade` automatically

## Known design decisions
- `records.discharge_department` — plain text (historical). `records.department_id` FK added later; both coexist
- `audit_logs.target_id` — polymorphic association, no FK by design
- SQLite in production: WAL mode + 4 threads, safe for single-instance low-concurrency workload
- Roles: `operator` / `editor` / `admin` / `viewer`
- `records.full_name` has no UNIQUE — one patient can have multiple discharge records (intentional)

## Known DB issues (not yet fixed)
- `records.treating_physician` / `nszu_corrections.doctor` — free text, no physicians table
- `records.discharge_status` — free text, no CHECK constraint
- LIKE `%text%` on `full_name` and `history` — full table scan (B-tree index unused with leading %)
