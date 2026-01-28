# Blueprints Structure

## Огляд

Проект використовує Flask Blueprints для модульної організації коду.

## Структура

```
app/
├── __init__.py              # Application Factory
├── blueprints/
│   ├── auth/               # Автентифікація
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── records/            # Записи виписок
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── nszu/              # Перевірка НСЗУ
│   │   ├── __init__.py
│   │   └── routes.py
│   └── admin/             # Адміністрування
│       ├── __init__.py
│       └── routes.py
```

## Blueprint розподіл роутів

### Auth Blueprint (`/auth`)
- `/auth/login` - Login page
- `/auth/logout` - Logout
- `/auth/change_password` - Change password

### Records Blueprint (`/`)
- `/` - Dashboard (список записів)
- `/add_record` - Додати запис
- `/api/add_record` - API додавання
- `/<int:record_id>/edit` - Редагувати запис
- `/api/edit_record/<int:record_id>` - API редагування
- `/<int:record_id>/delete` - Видалити запис
- `/export` - Експорт в Excel
- `/records/print` - Друк PDF

### NSZU Blueprint (`/nszu`)
- `/nszu` - Список НСЗУ
- `/nszu/add` - Додати НСЗУ
- `/api/nszu/add` - API додавання
- `/nszu/<int:correction_id>/edit` - Редагувати
- `/nszu/<int:correction_id>/delete` - Видалити
- `/nszu/export` - Експорт в Excel
- `/nszu/print` - Друк PDF

### Admin Blueprint (`/admin`)
- `/admin/users` - Користувачі
- `/admin/add_user` - Додати користувача
- `/admin/edit_user/<int:user_id>` - Редагувати
- `/admin/delete_user/<int:user_id>` - Видалити
- `/admin/statistics` - Статистика
- `/admin/departments` - Відділення
- `/admin/departments/<int:dept_id>/delete` - Видалити відділення
- `/admin/audit` - Аудит лог

## План міграції

### Фаза 1: Auth Blueprint (найпростіший) ✅ COMPLETED
- [x] Створити структуру
- [x] Перенести login route
- [x] Перенести logout route
- [x] Створено app/extensions.py для управління розширеннями
- [x] Зареєстровано auth_bp в app/__init__.py
- [x] Створено run_blueprint.py для тестування
- [x] Тестування (routes працюють: /login, /logout)
- [x] Commit

### Фаза 2: Admin Blueprint ✅ COMPLETED
- [x] Створити структуру
- [x] Перенести user management routes
- [x] Перенести departments routes
- [x] Перенести statistics route
- [x] Оновити url_for() в templates
- [x] Створено decorators.py для role_required
- [x] Оновлено utils.py з clear_dropdown_cache
- [x] Додано cache в app/extensions.py
- [x] Тестування (8 admin routes працюють в Docker)
- [x] Commit

### Фаза 3: NSZU Blueprint ✅ COMPLETED
- [x] Створити структуру
- [x] Перенести всі NSZU routes (7 routes)
- [x] Оновити url_for() в templates
- [x] Тестування (7 routes працюють в Docker)
- [x] Commit

### Фаза 4: Records Blueprint (найскладніший) ✅ COMPLETED
- [x] Створити структуру
- [x] Перенести всі Records routes (8 routes)
  - index (dashboard) - /
  - export - /export
  - print_records - /records/print
  - add_record - /records/add
  - api_add_record - /api/records/add
  - api_edit_record - /api/records/<id>/edit
  - edit_record - /records/<id>/edit
  - delete_record - /records/<id>/delete
- [x] Додано cached helper functions (get_distinct_statuses, physicians, departments)
- [x] Оновити url_for() в templates (5 files)
- [x] Тестування (8 routes працюють в Docker)
- [x] Commit

### Фаза 5: Cleanup ✅ COMPLETED
- [x] Міграція CLI commands до app/__init__.py (5 commands)
  - init-db, create-admin, create-user, backup-db, init-db-with-admin
- [x] Архівовано монолітний app.py → app_legacy.py (1969 ліній)
- [x] Тестування CLI commands в Docker
- [x] Commit

## ✅ Міграція завершена!

**Підсумок:**
- Монолітний app.py (1969 ліній) → Модульна Blueprint структура
- 4 Blueprints створено: Auth, Admin, NSZU, Records
- 23 routes мігровано (2 + 8 + 7 + 8 - 2 дублікати auth = 23)
- 5 CLI commands мігровано
- 10+ templates оновлено з новим namespace
- Всі features працюють в Docker

**Нова структура:**
```
app/
├── __init__.py           # Application factory + CLI commands
├── extensions.py         # Flask extensions (db, login_manager, cache, migrate)
├── blueprints/
│   ├── auth/            # Login/Logout routes
│   ├── admin/           # User management, departments, statistics, audit
│   ├── nszu/            # NSZU corrections management
│   └── records/         # Main dashboard, CRUD operations
models.py                # Database models
decorators.py            # role_required decorator
utils.py                 # Utility functions
config.py                # Configuration
```

## Примітки

- Кожен blueprint має власний `url_prefix`:
  - auth: `/` (login, logout)
  - admin: `/admin`
  - nszu: `/nszu`
  - records: `/` (dashboard та /records/* routes)
- Використовуємо `url_for('blueprint.route_name')` замість `url_for('route_name')`
- Всі blueprints реєструються в `app/__init__.py`
- Cached helper functions в records blueprint для оптимізації dropdown значень
- Зберігається повна зворотна сумісність з існуючими URL
