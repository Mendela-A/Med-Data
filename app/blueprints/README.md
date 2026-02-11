# Blueprints Structure

## Структура

```
app/
├── __init__.py              # Application Factory + CLI commands
├── extensions.py            # Flask extensions (db, login_manager, cache, migrate)
├── blueprints/
│   ├── auth/               # Login/Logout
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── records/            # Dashboard, CRUD, export, print
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── nszu/              # НСЗУ корекції
│   │   ├── __init__.py
│   │   └── routes.py
│   └── admin/             # Users, departments, statistics
│       ├── __init__.py
│       └── routes.py
```

## Routes

### Auth (`/`)
- `/login`, `/logout`, `/change_password`

### Records (`/`)
- `/` — Dashboard
- `/records/add`, `/records/<id>/edit`, `/records/<id>/delete`
- `/api/records/add`, `/api/records/<id>/edit`
- `/export`, `/records/print`

### NSZU (`/nszu`)
- `/nszu` — Список
- `/nszu/add`, `/nszu/<id>/edit`, `/nszu/<id>/delete`
- `/api/nszu/add`
- `/nszu/export`, `/nszu/print`

### Admin (`/admin`)
- `/admin/users`, `/admin/add_user`, `/admin/edit_user/<id>`, `/admin/delete_user/<id>`
- `/admin/departments`, `/admin/departments/<id>/delete`
- `/admin/statistics`
- `/admin/audit`

## Примітки

- `url_for('blueprint.route_name')` — з namespace
- Cached helpers для dropdown значень (statuses, physicians, departments)
- `decorators.py` — `role_required` decorator
- `utils.py` — `parse_date()`, `parse_integer()`, `parse_numeric()`, `clear_dropdown_cache()`
