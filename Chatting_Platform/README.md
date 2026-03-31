# ChatRoom - Production-Grade Real-Time Messaging Platform

A secure, scalable real-time chat application with AWS Cognito authentication, built with Flask and WebSockets.

## Features

✨ **Core Features**
- 🔐 AWS Cognito authentication & authorization
- 💬 Real-time messaging with WebSocket support
- 👥 User discovery and online status
- 📱 Responsive design (desktop & mobile)
- 🎨 Beautiful modern UI with Bootstrap 5
- 📊 Message history with pagination
- ⚡ Production-grade error handling & logging

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│              Frontend (React/Vanilla JS)             │
│  • User authentication & authorization              │
│  • Real-time messaging UI                           │
│  • User discovery & search                          │
└────────────────┬────────────────────────────────────┘
                 │ WebSocket + REST API
┌────────────────▼────────────────────────────────────┐
│         Backend (Flask + Flask-SocketIO)            │
│  • AWS Cognito JWT verification                    │
│  • Real-time message delivery                       │
│  • User management & online status                 │
│  • Message storage & retrieval                      │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│      Database (SQLAlchemy + SQLite/PostgreSQL)     │
│  • Users, Chat Sessions, Messages                  │
│  • Audit logs & user activity                      │
└─────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.8+
- AWS Cognito User Pool configured
- pip or conda package manager
- Modern web browser

## Installation

### 1. Clone or Extract the Project

```bash
cd Chatting_Platform
```

### 2. Create Virtual Environment

```bash
# Using venv
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure AWS Cognito

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` and add your AWS Cognito credentials:

```env
# AWS Cognito Configuration
COGNITO_USER_POOL_ID=us-east-1_xxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxx
COGNITO_CLIENT_SECRET=your-client-secret-here
COGNITO_REGION=us-east-1
COGNITO_DOMAIN=https://your-domain.auth.us-east-1.amazoncognito.com
APP_REDIRECT_URI=http://localhost:5000/auth/callback

# Database
SQLALCHEMY_DATABASE_URI=sqlite:///chat_platform.db

# Server
SECRET_KEY=your-secret-key-change-in-production
FLASK_ENV=development
FLASK_DEBUG=False
PORT=5000
```

### 5. Initialize Database

```bash
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### 6. Run the Application

```bash
# Development
python app.py

# The app will be available at http://localhost:5000
```

## AWS Cognito Setup

### Create User Pool

1. Go to AWS Console → Cognito
2. Create User Pool with:
   - Sign-up and sign-in with email
   - Username attributes: Email
   - MFA: Optional (or required based on your needs)

### Create App Client

1. In User Pool → App integration → App clients → Create app client
2. Configure:
   - Uncheck "Generate client secret" (optional, depends on your setup)
   - Authentication flows: ALLOW_AUTHORIZATION_CODE_GRANT
   - Callback URL: `http://localhost:5000/auth/callback` (development)
   - Sign out URL: `http://localhost:5000/auth/logout`
   - Allowed OAuth scopes: openid, email, profile

### Create Cognito Domain

1. User Pool → App integration → Domain name
2. Set a unique domain name
3. This will give you the COGNITO_DOMAIN URL

### Get Credentials

- **COGNITO_USER_POOL_ID**: User Pool → General Settings → Pool ID
- **COGNITO_CLIENT_ID**: App clients → App client settings → Client ID
- **COGNITO_CLIENT_SECRET**: If generated, find it in Client ID details
- **COGNITO_REGION**: Region of your User Pool (e.g., us-east-1)
- **COGNITO_DOMAIN**: Your Cognito domain URL

## API Documentation

### Authentication

**POST /auth/login**
- Redirects to Cognito login page

**GET /auth/callback**
- Cognito callback endpoint
- Returns token and user information

**GET /api/auth/verify**
- Verify current authentication token
- Response: `{ user: {...}, authenticated: true }`

**POST /auth/logout**
- Logout current user
- Clears session

### Users

**GET /api/users**
- Get all active users (excluding current user)
- Headers: `Authorization: Bearer {token}`
- Response: `{ users: [{id, name, email, avatar_color, is_online}] }`

**GET /api/users/{user_id}**
- Get specific user details
- Response: Full user object

**PUT /api/users/{user_id}**
- Update user profile (only own profile)
- Body: `{ name, bio, avatar_color }`
- Response: Updated user object

### Chat Sessions

**GET /api/chats**
- Get all chat sessions for current user
- Response: `{ chat_sessions: [{id, other_user, last_message_at, ...}] }`

**GET/POST /api/chats/{recipient_id}**
- Get or create chat session with another user
- Response: Chat session object

**GET /api/chats/{session_id}/messages**
- Get messages in a chat session
- Query params: `page=1&per_page=50`
- Response: `{ messages: [...], pagination: {...} }`

### WebSocket Events

**Connect**
- Query param: `?token={jwt_token}`
- Events: `connect`, `disconnect`

**Message**
- Event: `message`
- Payload: `{ session_id, content }`
- Broadcast: `new_message` with message object

**Typing Indicator**
- Event: `typing`
- Payload: `{ session_id, is_typing }`
- Broadcast: `user_typing`

**User Status**
- Event: `user_status_changed`
- Payload: `{ user_id, is_online, user }`

## Project Structure

```
Chatting_Platform/
├── app.py                    # Main Flask application
├── config.py                 # Configuration management
├── models.py                 # Database models
├── cognito.py                # AWS Cognito authentication
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── .env                      # Environment variables (not in git)
├── chat_platform.log         # Application logs
├── templates/
│   └── index.html            # Main HTML template
├── static/
│   ├── app.js                # Frontend application logic
│   └── style.css             # Styling
└── Chatting_Platform.db      # SQLite database (auto-created)
```

## Database Schema

### Users Table
- `id` (UUID): Primary key
- `cognito_id` (String): AWS Cognito user ID
- `email` (String): User email (unique)
- `name` (String): Display name
- `avatar_color` (String): Hex color for avatar
- `bio` (Text): User bio/status
- `is_active` (Boolean): Active status
- `is_online` (Boolean): Online status
- `last_seen` (DateTime): Last activity time
- `created_at`, `updated_at` (DateTime)

### Chat Sessions Table
- `id` (UUID): Primary key
- `initiator_id` (UUID): First user
- `recipient_id` (UUID): Second user
- `last_message_at` (DateTime): Last message time
- `is_archived` (Boolean): Archived status
- `created_at`, `updated_at` (DateTime)

### Messages Table
- `id` (UUID): Primary key
- `session_id` (UUID): Chat session
- `sender_id` (UUID): Message sender
- `content` (Text): Message content
- `message_type` (String): Type (text, image, etc.)
- `is_edited` (Boolean): Edit status
- `edited_at` (DateTime): Edit time
- `created_at` (DateTime): Creation time

## Security Features

🔒 **Authentication**
- JWT verification with AWS Cognito
- Token validation on every request
- Secure session management

🔐 **Authorization**
- User can only access their own chats
- User can only modify their own profile
- Session isolation

🛡️ **Data Protection**
- CORS protection
- CSRF prevention with OAuth state
- SQL injection prevention with SQLAlchemy ORM
- XSS protection with HTML escaping

## Performance Optimizations

⚡ **Database**
- Indexed queries for fast lookups
- Connection pooling
- Query pagination for messages

🚀 **Frontend**
- Lazy loading of users
- WebSocket for real-time updates (no polling)
- Efficient DOM updates

📊 **Caching**
- JWKS cache (1 hour)
- OAuth session cache (10 minutes)

## Logging

Logs are written to `chat_platform.log` and console.

Configure log level in `.env`:
```env
LOG_LEVEL=info  # debug, info, warning, error
```

## Deployment

### Production Checklist

- [ ] Generate strong `SECRET_KEY`
- [ ] Set `FLASK_ENV=production`
- [ ] Use PostgreSQL instead of SQLite
- [ ] Enable HTTPS (SSL/TLS)
- [ ] Set secure Cognito redirect URIs
- [ ] Enable database backups
- [ ] Set up monitoring & alerting
- [ ] Configure CORS properly
- [ ] Use gunicorn + reverse proxy (Nginx)

### Using Gunicorn

```bash
gunicorn -w 4 -b 0.0.0.0:5000 --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker app:app
```

### Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
ENV FLASK_ENV=production
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### Heroku Deployment

```bash
# Create Procfile
echo "web: gunicorn app:app" > Procfile

# Deploy
heroku create your-app-name
heroku config:set COGNITO_USER_POOL_ID=... COGNITO_CLIENT_ID=... ...
git push heroku main
```

## Troubleshooting

### Token Verification Fails
- Check Cognito credentials in `.env`
- Verify COGNITO_CLIENT_ID matches
- Ensure token is not expired

### WebSocket Connection Issues
- Check firewall allows WebSocket
- Verify CORS configuration
- Check browser console for errors

### Messages Not Appearing
- Verify database is initialized
- Check user is part of chat session
- Look at logs for errors

### Login Redirect Loop
- Verify redirect URI in AWS Cognito matches
- Check `APP_REDIRECT_URI` in `.env`
- Clear browser cookies

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-flask pytest-socketio

# Run tests
pytest
```

### Database Migrations

For production deployments with PostgreSQL, use Alembic:

```bash
# Create migration
alembic revision --autogenerate -m "Add new column"

# Apply migration
alembic upgrade head
```

## Monitoring & Analytics

### Key Metrics
- Active users count
- Messages per hour
- Average response time
- Database size
- Error rate

### Recommended Tools
- AWS CloudWatch for logs
- New Relic for APM
- Sentry for error tracking
- DataDog for infrastructure

## Contributing

1. Follow PEP 8 style guide
2. Add logging for debugging
3. Write docstrings for functions
4. Test changes locally
5. Update documentation

## Support

For issues or questions:
1. Check logs in `chat_platform.log`
2. Review AWS Cognito configuration
3. Check browser console for frontend errors
4. Contact support team

## License

Proprietary - All rights reserved

## Version History

**v1.0.0** (2024-03-27)
- Initial production release
- AWS Cognito integration
- Real-time messaging with WebSocket
- User management and discovery
- Message history with pagination
- Production-grade error handling

---

**Happy Chatting! 💬**
