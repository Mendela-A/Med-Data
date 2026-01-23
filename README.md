# Flask Records App (Dockerized)

This repository contains a Flask application with SQLite, roles (operator/editor/admin), audit logging and Excel export. The project includes Docker and nginx setup for deployment.

## Quick start (Docker)

1. Build and start containers:

   ```bash
   docker compose up -d --build
   ```

2. Open https://localhost/ in your browser (nginx listens on ports 80/443 with automatic HTTPS redirect).

3. Create an admin user (if you haven't already):
   ```bash
   docker exec flask_app flask create-admin <username> <password>
   ```

   Or use combined command:
   ```bash
   docker exec flask_app flask init-db-with-admin --username admin --password admin
   ```

## CLI Commands

### Database Management

| Command | Description |
|---------|-------------|
| `flask init-db` | Create database tables |
| `flask init-db-with-admin` | Create tables + admin user |
| `flask create-admin <user> <pass>` | Create admin user |
| `flask backup-db` | Create safe database backup |

### Backup Database

The application uses SQLite with WAL mode for better performance. To create a safe backup:

```bash
# Default backup (saves to data/backup_YYYYMMDD_HHMMSS.db)
docker exec flask_app flask backup-db

# Custom output path
docker exec flask_app flask backup-db -o /app/data/my_backup.db

# Copy backup from container to host
docker cp flask_app:/app/data/backup_20260115_143052.db ./backups/
```

**Output example:**
```
Backup created successfully: data/backup_20260115_143052.db (0.15 MB)
Date: 15.01.2026 14:30:52
```

### Automatic Backups (cron)

**Метод 1: Використання Flask CLI (рекомендовано)**

Add to host crontab for daily backups at 3:00 AM:

```bash
# Edit crontab
crontab -e

# Add line:
0 3 * * * docker exec flask_app flask backup-db >> /var/log/flask_backup.log 2>&1
```

**Метод 2: Прямий бекап через sqlite3 (альтернатива)**

Створіть скрипт `/usr/local/bin/backup-vipiski.sh`:

```bash
#!/bin/bash
# Backup script for Flask Vipiski app

CONTAINER_NAME="flask_app"
BACKUP_DIR="/var/backups/vipiski"
TIMESTAMP=$(date +%F_%H-%M)
BACKUP_FILE="app_${TIMESTAMP}.db"

# Create backup directory if not exists
mkdir -p "$BACKUP_DIR"

# Backup database using sqlite3
docker exec "$CONTAINER_NAME" sqlite3 /app/data/app.db ".backup '/app/data/$BACKUP_FILE'"
if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup FAILED: sqlite3 backup error" >&2
    exit 1
fi

# Copy backup to host
docker cp "${CONTAINER_NAME}:/app/data/${BACKUP_FILE}" "${BACKUP_DIR}/${BACKUP_FILE}"
if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup FAILED: docker cp error" >&2
    exit 1
fi

# Remove temporary backup from container
docker exec "$CONTAINER_NAME" rm -f "/app/data/${BACKUP_FILE}"

# Log success
echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup successful: ${BACKUP_DIR}/${BACKUP_FILE}"
```

Налаштування:

```bash
# 1. Створіть скрипт
sudo nano /usr/local/bin/backup-vipiski.sh
# (вставте код вище)

# 2. Зробіть виконуваним
sudo chmod +x /usr/local/bin/backup-vipiski.sh

# 3. Тестовий запуск
sudo /usr/local/bin/backup-vipiski.sh

# 4. Додайте в crontab для щоденного бекапу о 3:00
sudo crontab -e
# Додайте рядок:
0 3 * * * /usr/local/bin/backup-vipiski.sh >> /var/log/vipiski-backup.log 2>&1

# 5. Перевірка бекапів
ls -lh /var/backups/vipiski/
```

## Database (SQLite + WAL)

The application uses SQLite with WAL (Write-Ahead Logging) mode for:
- Better concurrent read/write performance
- Reduced database locking
- Safe hot backups

**Database files:**
```
data/
├── app.db       # Main database
├── app.db-wal   # WAL journal (uncommitted changes)
└── app.db-shm   # Shared memory index
```

**Important:** Never copy `app.db` alone! Use `flask backup-db` command which safely merges WAL into the backup.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev` | Flask secret key (change in production!) |
| `DATABASE_URL` | `sqlite:///data/app.db` | Database connection string |
| `LOG_TO_FILE` | `0` | Set to `1` to enable file logging |

## User Roles

| Role | Permissions |
|------|-------------|
| `operator` | Add records |
| `editor` | Edit records, export to Excel |
| `admin` | Full access: users, departments, delete records |

## Project Structure

```
├── app.py              # Main Flask application
├── models.py           # Database models (User, Record, Audit, Department)
├── config.py           # Configuration
├── templates/          # Jinja2 templates
├── static/             # CSS, certificates
├── nginx/              # Nginx configuration
├── docker-compose.yml  # Docker setup
├── Dockerfile          # Container build
└── data/               # SQLite database (mounted volume)
```

## Security Notes

- HTTPS enabled with self-signed certificate (replace for production)
- Automatic HTTP to HTTPS redirect
- Security headers: HSTS, X-Frame-Options, X-Content-Type-Options
- Don't commit `.env` files or secrets to git
