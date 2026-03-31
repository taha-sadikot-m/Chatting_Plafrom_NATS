# ChatRoom - Quick Start Guide

Get the ChatRoom messaging platform up and running in 5 minutes!

## Prerequisites Checklist

- [ ] Python 3.8+ installed
- [ ] pip or conda package manager
- [ ] AWS Cognito User Pool created
- [ ] AWS Cognito App Client configured
- [ ] Internet connection (for Cognito)

## Step-by-Step Setup

### Step 1: Navigate to Project Directory

```bash
cd Chatting_Platform
```

### Step 2: Create Python Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- Flask (web framework)
- Flask-SocketIO (real-time messaging)
- SQLAlchemy (database ORM)
- AWS boto3 & python-jose (Cognito auth)
- And more...

Installation time: ~2 minutes

### Step 4: Configure Cognito Credentials

**Get your Cognito credentials:**

1. Go to [AWS Console - Cognito](https://console.aws.amazon.com/cognito)
2. Select your User Pool
3. Go to **App integration** → **App clients** → Your app
4. Copy:
   - **Client ID** → `COGNITO_CLIENT_ID`
   - **Client Secret** (if visible) → `COGNITO_CLIENT_SECRET`
   - **User Pool ID** from General Settings → `COGNITO_USER_POOL_ID`
   - **Region** (from URL or Settings) → `COGNITO_REGION`
   - **Domain name** (from Domain name section) → `COGNITO_DOMAIN`

**Create `.env` file:**

```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

**Edit `.env` file with your Cognito credentials:**

```env
# AWS Cognito Configuration
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxxxxxx
COGNITO_CLIENT_ID=abc123def456...
COGNITO_CLIENT_SECRET=your-client-secret
COGNITO_REGION=us-east-1
COGNITO_DOMAIN=https://your-domain.auth.us-east-1.amazoncognito.com
APP_REDIRECT_URI=http://localhost:5000/auth/callback

# Secret Key (generate a new one)
SECRET_KEY=your-secret-key-here
```

**Generate a secret key:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Replace `your-secret-key-here` with the output.

### Step 5: Initialize Database

```bash
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

This creates the SQLite database and tables.

### Step 6: Configure Cognito Callback URLs

1. Go to AWS Cognito Console
2. Your User Pool → **App integration** → **App clients** → Your app
3. Click **Edit** or **Show Details**
4. Update:
   - **Callback URLs (OAuth Authorized redirect URIs)**:
     - `http://localhost:5000/auth/callback`
   - **Sign out URLs (OAuth Authorized sign-out redirect URIs)**:
     - `http://localhost:5000/auth/logout`
5. Click **Save changes**

### Step 7: Run the Application

```bash
python app.py
```

You should see:
```
 * Running on http://127.0.0.1:5000
 * WebSocket connected
```

### Step 8: Open in Browser

Open your browser and go to:
```
http://localhost:5000
```

You should see the ChatRoom login page!

## First Run Test

1. **Click "Login with AWS Cognito"**
2. **Login with your Cognito user credentials**
3. **You'll be redirected back to ChatRoom**
4. **See all active users in the sidebar**
5. **Click a user to start chatting!**

## Troubleshooting

### "Port 5000 already in use"

```bash
# Change port in .env
PORT=5001

# Or kill the process using port 5000
# Windows:
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# macOS/Linux:
lsof -i :5000
kill -9 <PID>
```

### "Cognito login not working"

**Check:**
1. Credentials in `.env` are correct
2. Cognito User Pool exists
3. App Client is configured
4. Callback URL is registered in Cognito
5. Your network allows HTTPS (Cognito requires it in production)

### "Database errors"

```bash
# Delete old database and recreate
rm chat_platform.db

# Then reinitialize:
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### "WebSocket connection failed"

1. Check browser console (F12 → Console tab)
2. Verify token is valid
3. Try refreshing the page
4. Clear browser cache

## Project Structure

```
Chatting_Platform/
├── app.py                  # Main application
├── config.py               # Configuration
├── models.py               # Database models
├── cognito.py              # Cognito auth
├── requirements.txt        # Dependencies
├── .env.example            # Template
├── .env                    # Your config (SECRET!)
├── chat_platform.db        # Database (created after init)
├── templates/
│   └── index.html          # Web UI
└── static/
    ├── app.js              # JavaScript
    └── style.css           # Styling
```

## Features You Can Try

✅ **Login/Logout**
- Click "Login with AWS Cognito"
- Enter credentials created in your Cognito User Pool

✅ **View Users**
- See all active users in left sidebar
- See online/offline status

✅ **Search Users**
- Type in search box to filter users

✅ **Start Chat**
- Click any user to open chat
- See chat history

✅ **Send Messages**
- Type message in input field
- Click send button (paper plane icon)
- Message appears instantly (WebSocket)

✅ **Profile**
- Click menu → Profile
- Update name, bio, avatar color

✅ **Real-time Updates**
- See when users go online/offline
- Messages appear instantly
- User list updates in real-time

## Next Steps

### For Development
- Read [README.md](README.md) for full documentation
- Read [API.md](API.md) for API endpoints
- Check [app.py](app.py) for backend code
- Check [static/app.js](static/app.js) for frontend code

### For Production
- Read [DEPLOYMENT.md](DEPLOYMENT.md) for production setup
- Use PostgreSQL instead of SQLite
- Configure Nginx + Gunicorn
- Enable HTTPS/SSL
- Set up monitoring
- Configure backups

### Add More Features
- File sharing
- Voice/video calls (integrate LiveKit)
- Encrypted messages
- Message reactions
- Group chats
- Media gallery

## Common Commands

```bash
# Activate environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Deactivate environment
deactivate

# Install new package
pip install package-name

# Update dependencies
pip install -r requirements.txt --upgrade

# Run app
python app.py

# Stop app
Ctrl + C

# View logs
tail -f chat_platform.log  # macOS/Linux
type chat_platform.log     # Windows (live view not available)
```

## Security Reminders

🔐 **Important:**
- Never commit `.env` file to git
- Keep `SECRET_KEY` secret
- Use HTTPS in production
- Change default passwords
- Keep dependencies updated

## Getting Help

1. **Check logs**: `chat_platform.log`
2. **Browser console**: F12 → Console tab
3. **Terminal output**: Look for error messages
4. **AWS Documentation**: [AWS Cognito Docs](https://docs.aws.amazon.com/cognito/)
5. **Flask Documentation**: [Flask Docs](https://flask.palletsprojects.com/)

## Performance Tips

- Use PostgreSQL for production (faster than SQLite)
- Enable caching headers
- Use Nginx as reverse proxy
- Run with Gunicorn (multiple workers)
- Enable gzip compression

## Version Information

- Python: 3.8+
- Flask: 3.0.0
- SQLAlchemy: 2.0.23
- Socket.IO: 5.3.5
- Bootstrap: 5.3.0

## What's Next?

After confirming everything works:

1. ✅ Create real Cognito users
2. ✅ Invite team members
3. ✅ Start using for real communication
4. ✅ Provide feedback
5. ✅ Deploy to production
6. ✅ Monitor performance

---

**Congratulations! You now have a production-ready chat application! 🎉**

For questions or issues, refer to the documentation or check the application logs.

**Happy chatting! 💬**
