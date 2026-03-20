import os

# Force ASGI worker for FastAPI apps.
worker_class = "uvicorn.workers.UvicornWorker"

# Render provides PORT at runtime.
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"

# Production defaults: 2 workers, tunable via env vars.
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30

# Restart workers periodically to prevent memory leaks
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
