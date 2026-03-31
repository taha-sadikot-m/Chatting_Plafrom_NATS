#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# ChatRoom - AWS EC2 User-Data Bootstrap Script
# Paste this into EC2 > Advanced > User Data when launching instance
# Tested on: Ubuntu 22.04 LTS (ami-0c7217cdde317cfec in us-east-1)
# ─────────────────────────────────────────────────────────────────
set -e

apt-get update -y
apt-get install -y python3 python3-pip python3-venv git nginx

# ── App directory ──────────────────────────────────────────────────
APP_DIR=/home/ubuntu/chatroom
mkdir -p $APP_DIR
cd $APP_DIR

# ── Copy app files (uploaded via SCP / git clone) ─────────────────
# If using GitHub, uncomment and set your repo:
# git clone https://github.com/YOUR_USER/YOUR_REPO.git .

# ── Python environment ─────────────────────────────────────────────
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn eventlet

# ── Environment variables ──────────────────────────────────────────
cat > /etc/environment << 'EOF'
COGNITO_USER_POOL_ID=YOUR_POOL_ID
COGNITO_CLIENT_ID=YOUR_CLIENT_ID
COGNITO_CLIENT_SECRET=YOUR_CLIENT_SECRET
COGNITO_DOMAIN=YOUR_COGNITO_DOMAIN
APP_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_STRING
FRONTEND_URL=http://YOUR_EC2_PUBLIC_IP
EOF

# ── Systemd service ────────────────────────────────────────────────
cat > /etc/systemd/system/chatroom.service << 'EOF'
[Unit]
Description=ChatRoom Flask Application
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/chatroom
Environment="PATH=/home/ubuntu/chatroom/venv/bin"
EnvironmentFile=/etc/environment
ExecStart=/home/ubuntu/chatroom/venv/bin/gunicorn \
    --worker-class eventlet \
    --workers 1 \
    --bind 0.0.0.0:5000 \
    --timeout 120 \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable chatroom
systemctl start chatroom

# ── Nginx reverse proxy ────────────────────────────────────────────
cat > /etc/nginx/sites-available/chatroom << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
}
EOF

ln -sf /etc/nginx/sites-available/chatroom /etc/nginx/sites-enabled/chatroom
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "✅  ChatRoom deployed! Visit: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
