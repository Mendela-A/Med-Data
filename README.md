# Flask Records App (Dockerized)

This repository contains a Flask application with SQLite, roles (operator/editor/admin), audit logging and Excel export. The project includes Docker and nginx setup for deployment.

## Quick start (Docker)

1. Build and start containers:

   docker compose up -d --build

2. Open http://localhost/ in your browser (nginx listens on port 80 and proxies to Gunicorn on port 8000).

3. Create an admin user (if you haven't already) inside the running web container or use the CLI before building:
   - Locally: `flask create-admin <username> <password>`

## Notes
- Logging defaults to stdout (good for container logs). To enable file logging set `LOG_TO_FILE=1` in the web environment.
- The app reads `SECRET_KEY` and `DATABASE_URL` from environment variables. Provide them in a `.env` file or in `docker-compose.yml` for production.

## Preparing for GitHub
- Ensure you add a repository on GitHub and push this project.
- Don't commit secrets or `.env` files.

