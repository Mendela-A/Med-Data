# 🚀 Production Deployment Checklist

## ❌ ВИДАЛИТИ перед деплоєм

### 1. Застарілі файли та директорії
```bash
# Стара blueprint структура (не в git, локальна)
rm -rf blueprints/

# Застарілий монолітний app.py (архівований, 1969 ліній)
rm -f app_legacy.py

# Тестові скрипти для локальної розробки
rm -f run_blueprint.py

# Тимчасові та кеш файли
rm -rf __pycache__/
rm -rf .pytest_cache/
rm -rf logs/*.log
```

### 2. Скрипти міграції/оптимізації (опціонально)
```bash
# Ці скрипти потрібні ТІЛЬКИ для one-time операцій
# Якщо БД вже оптимізована - можна видалити:
# - add_indexes.py (додавання індексів)
# - analyze_db.py (аналіз БД)
# - optimize_database.py (оптимізація БД)

# АБО перенести в окрему директорію:
mkdir -p scripts/maintenance/
mv add_indexes.py analyze_db.py optimize_database.py scripts/maintenance/
```

## ⚠️ ПЕРЕВІРИТИ перед деплоєм

### 3. Чутливі дані (.env)
```bash
# КРИТИЧНО: .env НЕ МАЄ бути в git!
git ls-files | grep -E "\.env$"  # має бути порожньо

# Для продакшин використовувати environment variables або secrets manager
# Згенерувати НОВИЙ SECRET_KEY для production:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Debug режим
```python
# config.py - переконатися що DEBUG=False
class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
```

### 5. Docker конфігурація
```yaml
# docker-compose.yml - видалити порти для development
# ВИДАЛИТИ:
# ports:
#   - "8000:8000"  # Не експонувати Flask безпосередньо

# Залишити тільки Nginx:
nginx:
  ports:
    - "443:443"
    - "80:80"
```

### 6. HTTPS сертифікати
```bash
# Перевірити що сертифікати НЕ в git
git ls-files static/certs/

# Використовувати Let's Encrypt або корпоративні сертифікати
# Зберігати в Docker secrets або volumes
```

## ✅ ДОДАТИ для продакшин

### 7. Health checks
```python
# app/blueprints/health.py
@health_bp.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': datetime.utcnow()}, 200
```

### 8. Gunicorn production config
```python
# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
```

### 9. Production requirements.txt
```bash
# Додати production-only пакети:
gunicorn==21.2.0
sentry-sdk==1.40.0  # Error tracking
prometheus-flask-exporter==0.22.4  # Metrics
```

### 10. .dockerignore optimization
```
# .dockerignore - не копіювати непотрібні файли в image
.git
.gitignore
*.md
README.md
tests/
.pytest_cache/
__pycache__/
*.pyc
logs/
data/
backups/
venv/
.env
.env.*
run_blueprint.py
app_legacy.py
scripts/
```

## 🔒 Security Checklist

### 11. CSRF Protection
```python
# app/__init__.py
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect()
csrf.init_app(app)
```

### 12. Security Headers
```python
# app/middleware/security.py
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response
```

### 13. Rate Limiting
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="redis://redis:6379"
)

@limiter.limit("5 per minute")
@auth_bp.route('/login', methods=['POST'])
def login():
    ...
```

## 📊 Monitoring

### 14. Logging
```python
# Production logging config
import logging
from logging.handlers import RotatingFileHandler

if not app.debug:
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240000, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
```

### 15. Sentry Integration
```python
# app/__init__.py
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

if not app.debug and app.config.get('SENTRY_DSN'):
    sentry_sdk.init(
        dsn=app.config['SENTRY_DSN'],
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1
    )
```

## 🗄️ Database

### 16. Міграція на PostgreSQL (рекомендовано)
```python
# config.py
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 
    'postgresql://user:password@db:5432/medical_records')

# docker-compose.yml
services:
  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: medical_records
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
```

### 17. Database Backups
```bash
# Автоматичні backup через cron
0 2 * * * docker exec postgres pg_dump -U user medical_records | gzip > /backups/db_$(date +\%Y\%m\%d).sql.gz

# Ротація старих backups (зберігати 30 днів)
find /backups -name "db_*.sql.gz" -mtime +30 -delete
```

## 🚀 Deployment команди

```bash
# 1. Очистка
rm -rf blueprints/ app_legacy.py run_blueprint.py __pycache__/ .pytest_cache/

# 2. Перевірка
git status  # переконатися що .env не в git
docker-compose config  # валідація docker-compose.yml

# 3. Build
docker-compose build --no-cache

# 4. Deploy
docker-compose up -d

# 5. Health check
curl https://your-domain.com/health

# 6. Logs monitoring
docker-compose logs -f flask_app
```

## 📋 Post-deployment

### 18. Моніторинг
- [ ] Налаштувати Prometheus metrics
- [ ] Налаштувати Grafana dashboards
- [ ] Налаштувати alerting (PagerDuty/Slack)
- [ ] Налаштувати uptime monitoring (UptimeRobot)

### 19. Backups
- [ ] Автоматичні щоденні backup БД
- [ ] Тестування restore процесу
- [ ] Off-site backup storage

### 20. Documentation
- [ ] API documentation (Swagger/OpenAPI)
- [ ] Runbook для operations team
- [ ] Disaster recovery plan

---

**Дата створення:** $(date +"%Y-%m-%d")
**Версія:** 1.0
