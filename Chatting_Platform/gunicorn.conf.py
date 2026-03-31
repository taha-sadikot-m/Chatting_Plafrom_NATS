# Gunicorn Configuration for ChatRoom
# Save as gunicorn.conf.py or use with: gunicorn -c gunicorn.conf.py app:app

import os
import multiprocessing
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────
# Server Socket Configuration
# ──────────────────────────────────────────────────────────────────────────

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")
backlog = 2048

# ──────────────────────────────────────────────────────────────────────────
# Worker Processes
# ──────────────────────────────────────────────────────────────────────────

def num_workers():
    """Calculate optimal worker count."""
    try:
        # For CPU-bound: 2-4 * CPU_count
        # For I/O-bound (like chat): 4-8 * CPU_count
        return multiprocessing.cpu_count() * 4
    except NotImplementedError:
        return 4

workers = int(os.getenv("GUNICORN_WORKERS", num_workers()))
worker_class = "sync"  # Using sync worker with Flask-SocketIO
worker_connections = 1000
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 2

# ──────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────

accesslog = os.getenv("GUNICORN_ACCESS_LOG", "/var/log/chatroom/access.log")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "/var/log/chatroom/error.log")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s ms'

# ──────────────────────────────────────────────────────────────────────────
# Process Naming
# ──────────────────────────────────────────────────────────────────────────

proc_name = "chatroom"

# ──────────────────────────────────────────────────────────────────────────
# Server Mechanics
# ──────────────────────────────────────────────────────────────────────────

daemon = False
pidfile = "/var/run/gunicorn.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# ──────────────────────────────────────────────────────────────────────────
# SSL Configuration (if using SSL directly with Gunicorn)
# ──────────────────────────────────────────────────────────────────────────

# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"
# ssl_version = "TLSv1_2"

# ──────────────────────────────────────────────────────────────────────────
# Hooks
# ──────────────────────────────────────────────────────────────────────────

def on_starting(server):
    """Called when Gunicorn starts."""
    print(f"[{datetime.now()}] ChatRoom Server Starting...")
    print(f"Workers: {server.num_workers}")
    print(f"Worker Class: {server.worker_class}")

def on_exit(server):
    """Called when Gunicorn exits."""
    print(f"[{datetime.now()}] ChatRoom Server Stopped")

def when_ready(server):
    """Called when Gunicorn is ready to serve requests."""
    print(f"[{datetime.now()}] ChatRoom Server Ready! Listening on {bind}")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called after a worker has been forked."""
    # Close database connections before forking
    from app import db
    db.session.remove()

def post_worker_init(worker):
    """Called after a worker has initialized."""
    pass

# ──────────────────────────────────────────────────────────────────────────
# Server Behavior
# ──────────────────────────────────────────────────────────────────────────

raw_env = []
max_requests = 1000  # Restart worker after N requests (memory leak prevention)
max_requests_jitter = 100
reload = False  # Enable auto-reload on code changes (dev only)
reload_extra_files = []

# Preserve output from stdout/stderr in access log
capture_output = True

# ──────────────────────────────────────────────────────────────────────────
# Gevent Options
# ──────────────────────────────────────────────────────────────────────────

# The number of worker connections that will be kept open
# (for gevent-based workers)
# Default is 1000
