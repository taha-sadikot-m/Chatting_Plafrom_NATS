# Deployment Guide - ChatRoom

Production-grade deployment strategies and configurations for the ChatRoom application.

## Table of Contents

1. [Environment Configuration](#environment-configuration)
2. [Database Setup](#database-setup)
3. [AWS Cognito Configuration](#aws-cognito-configuration)
4. [Web Server Setup](#web-server-setup)
5. [SSL/TLS Configuration](#ssltls-configuration)
6. [Monitoring & Logging](#monitoring--logging)
7. [Scaling Strategies](#scaling-strategies)
8. [Backup & Recovery](#backup--recovery)

## Environment Configuration

### Production .env

Create a secure `.env` file in production with strong values:

```env
# Flask
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-very-secure-random-key-here  # Use: python -c "import secrets; print(secrets.token_hex(32))"

# AWS Cognito
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxxxxxx
COGNITO_CLIENT_ID=client_id_here
COGNITO_CLIENT_SECRET=client_secret_here
COGNITO_REGION=us-east-1
COGNITO_DOMAIN=https://yourdomain.auth.us-east-1.amazoncognito.com
APP_REDIRECT_URI=https://yourapp.com/auth/callback

# Database (PostgreSQL for production)
SQLALCHEMY_DATABASE_URI=postgresql://user:password@db-host:5432/chatroom_db

# Server
HOST=0.0.0.0
PORT=5000
ALLOWED_ORIGINS=https://yourapp.com,https://www.yourapp.com

# Logging
LOG_LEVEL=warning
```

### Generate Secure SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Database Setup

### PostgreSQL (Recommended for Production)

1. **Install PostgreSQL**

```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS
brew install postgresql
```

2. **Create Database and User**

```bash
sudo -u postgres psql
CREATE DATABASE chatroom_db;
CREATE USER chatroom_user WITH PASSWORD 'strong_password';
ALTER ROLE chatroom_user SET client_encoding TO 'utf8';
ALTER ROLE chatroom_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE chatroom_user SET default_transaction_deferrable TO on;
ALTER ROLE chatroom_user SET default_transaction_level TO 'read committed';
ALTER ROLE chatroom_user IN DATABASE chatroom_db GRANT ALL ON SCHEMA public TO chatroom_user;
\q
```

3. **Update .env**

```env
SQLALCHEMY_DATABASE_URI=postgresql://chatroom_user:strong_password@localhost:5432/chatroom_db
```

4. **Initialize Database**

```bash
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### Database Backup Strategy

```bash
#!/bin/bash
# backup.sh - Daily backup script

BACKUP_DIR="/backups/chatroom"
DB_NAME="chatroom_db"
DB_USER="chatroom_user"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Create backup
pg_dump -U $DB_USER $DB_NAME | gzip > $BACKUP_DIR/chatroom_${TIMESTAMP}.sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "chatroom_*.sql.gz" -mtime +30 -delete

echo "Backup completed: chatroom_${TIMESTAMP}.sql.gz"
```

Schedule with cron:
```bash
crontab -e
# Add: 0 2 * * * /path/to/backup.sh
```

## AWS Cognito Configuration

### Production Cognito Setup

1. **Update App Client Settings**

Go to AWS Console → Cognito → Your User Pool → App integration → App clients → Your app

- **Callback URLs (OAuth Authorized redirect URIs)**:
  - `https://yourapp.com/auth/callback`
  - `https://www.yourapp.com/auth/callback`

- **Sign out URLs (OAuth Authorized sign-out redirect URIs)**:
  - `https://yourapp.com/auth/logout`
  - `https://www.yourapp.com/auth/logout`

- **Allowed OAuth Flows**:
  - ✓ Authorization code grant
  - ✓ Implicit grant
  - ✓ Authorization code grant (access token)

- **Allowed OAuth Scopes**:
  - ✓ email
  - ✓ openid
  - ✓ profile

2. **Security Settings**

- Enable MFA (Required or Optional)
- Use strong password policies
- Enable email verification
- Set password expiration (90 days recommended)

3. **User Attributes**

- Standard attributes: email, family_name, given_name, name
- Custom attributes: company, department (if needed)

## Web Server Setup

### Using Gunicorn + Nginx

1. **Install Gunicorn**

```bash
pip install gunicorn gevent gevent-websocket
```

2. **Create systemd service file**

```bash
sudo nano /etc/systemd/system/chatroom.service
```

```ini
[Unit]
Description=ChatRoom Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/chatroom
Environment="PATH=/var/www/chatroom/venv/bin"
EnvironmentFile=/var/www/chatroom/.env
ExecStart=/var/www/chatroom/venv/bin/gunicorn \
    --workers 4 \
    --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    --bind unix:/var/run/chatroom.sock \
    --timeout 60 \
    --access-logfile /var/log/chatroom/access.log \
    --error-logfile /var/log/chatroom/error.log \
    app:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. **Start the service**

```bash
sudo systemctl daemon-reload
sudo systemctl enable chatroom
sudo systemctl start chatroom
sudo systemctl status chatroom
```

4. **Nginx Configuration**

```bash
sudo nano /etc/nginx/sites-available/chatroom
```

```nginx
upstream chatroom_app {
    server unix:/var/run/chatroom.sock fail_timeout=0;
}

server {
    listen 80;
    server_name yourapp.com www.yourapp.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourapp.com www.yourapp.com;

    ssl_certificate /etc/letsencrypt/live/yourapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourapp.com/privkey.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 10M;

    location / {
        proxy_pass http://chatroom_app;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /static/ {
        alias /var/www/chatroom/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

5. **Enable the site**

```bash
sudo ln -s /etc/nginx/sites-available/chatroom /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Docker Deployment

**Dockerfile**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 chatroom && chown -R chatroom:chatroom /app

USER chatroom

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", \
     "--workers", "4", \
     "--worker-class", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "60", \
     "app:app"]
```

**docker-compose.yml**

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: chatroom_db
      POSTGRES_USER: chatroom_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U chatroom_user"]
      interval: 10s
      timeout: 5s
      retries: 5

  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      FLASK_ENV: production
      SQLALCHEMY_DATABASE_URI: postgresql://chatroom_user:${DB_PASSWORD}@db:5432/chatroom_db
      COGNITO_USER_POOL_ID: ${COGNITO_USER_POOL_ID}
      COGNITO_CLIENT_ID: ${COGNITO_CLIENT_ID}
      COGNITO_CLIENT_SECRET: ${COGNITO_CLIENT_SECRET}
      COGNITO_REGION: ${COGNITO_REGION}
      COGNITO_DOMAIN: ${COGNITO_DOMAIN}
      APP_REDIRECT_URI: ${APP_REDIRECT_URI}
      SECRET_KEY: ${SECRET_KEY}
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
```

## SSL/TLS Configuration

### Using Let's Encrypt with Certbot

```bash
sudo apt-get install certbot python3-certbot-nginx

sudo certbot certonly --nginx -d yourapp.com -d www.yourapp.com

# Auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

## Monitoring & Logging

### Sentry Error Tracking

```bash
pip install sentry-sdk
```

In app.py:
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
    integrations=[
        FlaskIntegration(),
        SqlalchemyIntegration(),
    ],
    traces_sample_rate=0.1,
    environment="production"
)
```

### CloudWatch Logging

```python
import logging
import watchtower

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        watchtower.CloudWatchLogHandler(
            log_group='/chatroom/app',
            stream_name='production'
        )
    ]
)
```

### Monitoring with New Relic

```bash
pip install newrelic
```

```bash
NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program gunicorn app:app
```

## Scaling Strategies

### Horizontal Scaling

For multiple app instances, use:

1. **Redis for Session Management**

```python
from flask_session import Session
from redis import Redis

app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = Redis(host='localhost', port=6379)
Session(app)
```

2. **Message Queue for Real-time Updates**

Use Redis Pub/Sub or RabbitMQ for cross-instance messaging:

```python
from flask_socketio import SocketIO

socketio = SocketIO(app, message_queue='redis://localhost:6379')
```

3. **Load Balancer Configuration**

Use Nginx or AWS ELB to distribute traffic:

```nginx
upstream chatroom_backend {
    least_conn;
    server web1.internal:5000;
    server web2.internal:5000;
    server web3.internal:5000;
}
```

## Backup & Recovery

### Backup Strategy

1. **Database Backups** (daily)
2. **Application Code** (version control)
3. **User Uploads** (if applicable)
4. **Configuration Files** (encrypted)

### Recovery Plan

1. **Database Recovery**

```bash
psql -U chatroom_user chatroom_db < backup.sql
```

2. **Application Recovery**

```bash
git clone <repository> /var/www/chatroom
cd /var/www/chatroom
source venv/bin/activate
pip install -r requirements.txt
systemctl restart chatroom
```

## Performance Tuning

### Database Connection Pooling

```python
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_size": 20,
    "pool_recycle": 3600,
    "pool_pre_ping": True,
    "max_overflow": 40,
}
```

### Compression

```nginx
gzip on;
gzip_types text/plain text/css text/javascript application/json;
gzip_min_length 1000;
gzip_comp_level 9;
```

### Caching Headers

```python
@app.after_request
def add_cache_headers(response):
    if response.status_code == 200:
        response.cache_control.max_age = 3600
        response.cache_control.public = True
    return response
```

---

**For questions or support, contact the DevOps team.**
