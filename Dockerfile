FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# copy entrypoint and make it executable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# expose gunicorn port
EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
# Start the app with Gunicorn (create_app factory)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "app:create_app()"]
