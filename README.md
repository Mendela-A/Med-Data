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

Add to host crontab for daily backups at 3:00 AM:

```bash
# Edit crontab
crontab -e

# Add line:
0 3 * * * docker exec flask_app flask backup-db >> /var/log/flask_backup.log 2>&1
```

Or create a backup script:

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/path/to/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

docker exec flask_app flask backup-db -o /app/data/backup_${TIMESTAMP}.db
docker cp flask_app:/app/data/backup_${TIMESTAMP}.db ${BACKUP_DIR}/
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
