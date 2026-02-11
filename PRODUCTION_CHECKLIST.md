# Production Checklist

## Виконано

- [x] Міграція на Blueprint архітектуру (`app/blueprints/`)
- [x] Видалено `app_legacy.py`, `run_blueprint.py`
- [x] DB-скрипти перенесено в `scripts/maintenance/`
- [x] `.env`, `/data/`, `/logs/`, `/backups/`, сертифікати — не в git
- [x] CSRF protection (Flask-WTF + meta-tag)
- [x] Docker + Nginx reverse proxy

## Перед деплоєм

- [ ] Згенерувати новий `SECRET_KEY` для production
- [ ] `DEBUG = False` в конфігурації
- [ ] Docker: не експонувати Flask порт напряму (тільки через Nginx)
- [ ] HTTPS: Let's Encrypt або корпоративні сертифікати
- [ ] Rate limiting на `/login` (Flask-Limiter)
- [ ] Security headers (X-Content-Type-Options, X-Frame-Options, HSTS)

## Після деплою

- [ ] Health check endpoint (`/health`)
- [ ] Logging: RotatingFileHandler або stdout для Docker
- [ ] Error tracking (Sentry)
- [ ] Моніторинг (Prometheus + Grafana)
- [ ] Автоматичні backups БД + тест restore
- [ ] Міграція SQLite → PostgreSQL (за потреби)

## Структура проекту

```
app/                    # Blueprint архітектура
  __init__.py           # Application factory
  extensions.py         # Flask extensions
  blueprints/           # auth, admin, nszu, records
models.py               # Database models
config.py               # Configuration
templates/              # Jinja2 templates
static/                 # CSS, JS, images
migrations/             # Alembic migrations
scripts/maintenance/    # DB optimization scripts
docker-compose.yml      # Docker orchestration
Dockerfile              # Flask app container
entrypoint.sh           # Container startup
nginx/                  # Nginx config
```

## Deploy

```bash
docker-compose config          # валідація
docker-compose build --no-cache
docker-compose up -d
docker-compose logs -f flask_app
```
