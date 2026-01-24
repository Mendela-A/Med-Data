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

### Фаза 1: Auth Blueprint (найпростіший)
- [x] Створити структуру
- [ ] Перенести login route
- [ ] Перенести logout route
- [ ] Перенести change_password route
- [ ] Тестування
- [ ] Commit

### Фаза 2: Admin Blueprint
- [x] Створити структуру
- [ ] Перенести user management routes
- [ ] Перенести departments routes
- [ ] Перенести statistics route
- [ ] Перенести audit route
- [ ] Тестування
- [ ] Commit

### Фаза 3: NSZU Blueprint
- [x] Створити структуру
- [ ] Перенести всі NSZU routes
- [ ] Тестування
- [ ] Commit

### Фаза 4: Records Blueprint (найскладніший)
- [x] Створити структуру
- [ ] Перенести всі Records routes
- [ ] Тестування
- [ ] Commit

### Фаза 5: Cleanup
- [ ] Видалити старий app.py
- [ ] Оновити run.py
- [ ] Оновити документацію
- [ ] Final testing

## Примітки

- Кожен blueprint має власний `url_prefix`
- Використовуємо `url_for('blueprint.route_name')` замість `url_for('route_name')`
- Всі blueprints реєструються в `app/__init__.py`
- Зберігаємо зворотну сумісність під час міграції
