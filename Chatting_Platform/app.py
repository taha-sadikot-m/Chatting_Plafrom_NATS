"""
Chat Platform - Flask Application with AWS Cognito Authentication
"""

import os
import logging
import uuid
import time
import json
import asyncio
import threading
from datetime import datetime
from functools import wraps

import nats

from flask import Flask, request, jsonify, render_template, session, redirect
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from cognito_auth import (
    verify_cognito_token,
    get_cognito_login_url,
    get_cognito_logout_url,
    exchange_code_for_token,
    generate_oauth_state,
    consume_oauth_state,
    validate_cognito_config,
    _oauth_sessions,
)

# ──────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("chatting_platform")

# ──────────────────────────────────────────────────────────────────────────
# INITIALIZATION
# ──────────────────────────────────────────────────────────────────────────

PORT = int(os.getenv("PORT", "5000"))
COGNITO_ENABLED = validate_cognito_config()
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")

logger.info(f"Cognito enabled: {COGNITO_ENABLED}")

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates"
)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SESSION_COOKIE_SECURE"] = False  # localhost HTTP
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    allow_upgrades=False,      # threading mode cannot handle WS upgrades
    ping_timeout=60,
    ping_interval=25,
    logger=True,
    engineio_logger=True
)

# In-memory storage
users_online = {}  # user_id -> {name, email, sub}
messages_db = {}   # chat_id -> list of messages
user_connections = {}  # user_id -> session_id

# ──────────────────────────────────────────────────────────────────────────
# NATS - Async message bus (runs in a dedicated background thread)
# ──────────────────────────────────────────────────────────────────────────

_nats_client = None   # nats.Client instance
_nats_loop = None     # asyncio event loop running in background thread


async def _nats_init():
    """Connect to NATS and subscribe to all chat/presence subjects."""
    global _nats_client
    try:
        _nats_client = await nats.connect(
            NATS_URL,
            error_cb=lambda e: logger.error(f"NATS error: {e}"),
            closed_cb=lambda: logger.warning("NATS connection closed"),
            reconnected_cb=lambda: logger.info("NATS reconnected"),
        )
        logger.info(f"✓ NATS connected: {NATS_URL}")

        # Bridge all chat messages → Socket.IO
        await _nats_client.subscribe("chat.>", cb=_nats_to_socketio)
        # Bridge all presence events → Socket.IO
        await _nats_client.subscribe("presence.>", cb=_nats_to_socketio)
    except Exception as e:
        logger.error(f"✗ NATS connection failed: {e}")


async def _nats_to_socketio(msg):
    """Receive a NATS message and forward it to all Socket.IO clients."""
    try:
        subject = msg.subject
        data = json.loads(msg.data.decode())

        if subject.startswith("chat.message."):
            socketio.emit("new_message", data)
        elif subject.startswith("chat.typing."):
            socketio.emit("user_typing", data)
        elif subject == "presence.online":
            socketio.emit("user_online", data)
        elif subject == "presence.offline":
            socketio.emit("user_offline", data)
    except Exception as e:
        logger.error(f"NATS→SocketIO bridge error: {e}")


def nats_publish(subject: str, data: dict):
    """Thread-safe, fire-and-forget NATS publish from sync Flask/Socket.IO context."""
    if _nats_client and _nats_loop and not _nats_loop.is_closed():
        asyncio.run_coroutine_threadsafe(
            _nats_client.publish(subject, json.dumps(data).encode()),
            _nats_loop,
        )
    else:
        logger.warning(f"NATS not ready — dropping publish to {subject}")


def _run_nats_thread():
    """Run the NATS asyncio event loop in a dedicated daemon thread."""
    global _nats_loop
    _nats_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_nats_loop)
    _nats_loop.run_until_complete(_nats_init())
    _nats_loop.run_forever()


# Start the NATS background thread immediately so it is ready before requests arrive
threading.Thread(target=_run_nats_thread, daemon=True, name="nats-thread").start()





# ──────────────────────────────────────────────────────────────────────────
# DECORATORS
# ──────────────────────────────────────────────────────────────────────────

def require_auth(f):
    """Decorator to require valid Cognito token."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not token:
            token = session.get("id_token")
        
        if not token:
            return jsonify({"error": "Not authenticated"}), 401
        
        try:
            cognito_user = verify_cognito_token(token)
            kwargs["current_user"] = cognito_user
            return f(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Auth failed: {e}")
            return jsonify({"error": "Invalid token"}), 401
    
    return decorated_function

# ──────────────────────────────────────────────────────────────────────────
# ROUTES - HTML/PAGES
# ──────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve main chat interface."""
    return render_template("index.html")

@app.route("/favicon.ico")
def favicon():
    """Serve favicon (minimal response to suppress 404)."""
    return "", 204  # Return 204 No Content

# ──────────────────────────────────────────────────────────────────────────
# ROUTES - AUTHENTICATION
# ──────────────────────────────────────────────────────────────────────────

@app.route("/auth/login", methods=["GET"])
def login():
    """Redirect to Cognito login."""
    if not COGNITO_ENABLED:
        return jsonify({"error": "Cognito not configured"}), 500
    
    state = generate_oauth_state()
    
    # Detect the public base URL so the callback works through ngrok/any proxy
    # X-Forwarded-Host is set by ngrok; fall back to Host header
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "http")
    forwarded_host  = request.headers.get("X-Forwarded-Host") or request.headers.get("Host", "localhost:5000")
    base_url = f"{forwarded_proto}://{forwarded_host}"
    dynamic_redirect_uri = f"{base_url}/auth/callback"
    
    _oauth_sessions[state] = {
        "timestamp": time.time(),
        "redirect_uri": dynamic_redirect_uri,
    }
    
    login_url = get_cognito_login_url(state, redirect_uri=dynamic_redirect_uri)
    response = redirect(login_url)
    response.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")
    
    logger.info(f"Login redirect: state={state[:8]}..., callback={dynamic_redirect_uri}")
    return response


@app.route("/auth/callback", methods=["GET"])
def auth_callback():
    """Handle Cognito OAuth callback."""
    if not COGNITO_ENABLED:
        return redirect("/?error=cognito_disabled")
    
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    
    if error:
        logger.error(f"Cognito error: {error}")
        return redirect(f"/?error={error}")
    
    if not code or not state:
        return redirect("/?error=missing_code_or_state")
    
    try:
        # Validate state and retrieve stored session data (includes redirect_uri)
        session_data = consume_oauth_state(state)
        if not session_data:
            logger.error(f"Invalid state: {state[:8]}...")
            return redirect("/?error=invalid_state")
        
        stored_redirect_uri = session_data.get("redirect_uri")
        
        # Exchange code for token using the same redirect_uri that was sent to Cognito
        tokens = exchange_code_for_token(code, redirect_uri=stored_redirect_uri)
        if not tokens or "id_token" not in tokens:
            logger.error("No ID token in response")
            return redirect("/?error=no_token")
        
        id_token = tokens["id_token"]
        
        # Verify token
        cognito_user = verify_cognito_token(id_token)
        
        # Store user in session
        session.permanent = True
        session["id_token"] = id_token
        session["user_id"] = cognito_user.sub
        session["user_name"] = cognito_user.name
        session["user_email"] = cognito_user.email
        
        # Store in online users
        users_online[cognito_user.sub] = {
            "name": cognito_user.name,
            "email": cognito_user.email,
            "sub": cognito_user.sub,
        }
        
        logger.info(f"User logged in: {cognito_user.email}")
        
        # Redirect back to the same host the user came from (ngrok or localhost)
        if stored_redirect_uri:
            base_url = stored_redirect_uri.rsplit("/auth/callback", 1)[0]
        else:
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "http")
            forwarded_host  = request.headers.get("X-Forwarded-Host") or request.headers.get("Host", "localhost:5000")
            base_url = f"{forwarded_proto}://{forwarded_host}"
        
        return redirect(f"{base_url}/?token={id_token}&user_id={cognito_user.sub}&user_name={cognito_user.name}")
    
    except Exception as e:
        logger.exception(f"Auth callback failed: {e}")
        return redirect("/?error=auth_failed")


@app.route("/auth/logout", methods=["POST"])
def logout():
    """Logout user."""
    user_id = session.get("user_id")
    
    if user_id and user_id in users_online:
        del users_online[user_id]
    
    session.clear()
    
    if COGNITO_ENABLED:
        logout_url = get_cognito_logout_url(request.host_url.rstrip("/") + "/")
        return jsonify({"logout_url": logout_url}), 200
    
    return jsonify({"ok": True}), 200


# ──────────────────────────────────────────────────────────────────────────
# ROUTES - API
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/auth/verify", methods=["GET"])
@require_auth
def verify_auth(current_user):
    """Verify current authentication and return user info."""
    return jsonify({
        "user": {
            "id": current_user.sub,
            "name": current_user.name,
            "email": current_user.email,
        },
        "authenticated": True
    }), 200


@app.route("/api/users", methods=["GET"])
@require_auth
def get_users(current_user):
    """Get list of all online users."""
    user_list = [
        {"id": uid, "name": user["name"], "email": user["email"]}
        for uid, user in users_online.items()
        if uid != current_user.sub
    ]
    return jsonify({"users": user_list}), 200


@app.route("/api/current-user", methods=["GET"])
@require_auth
def get_current_user(current_user):
    """Get current authenticated user."""
    return jsonify({
        "id": current_user.sub,
        "name": current_user.name,
        "email": current_user.email,
    }), 200


@app.route("/api/messages/<recipient_id>", methods=["GET"])
@require_auth
def get_messages(recipient_id, current_user):
    """Get chat history with recipient."""
    chat_id = str(tuple(sorted([current_user.sub, recipient_id])))
    messages = messages_db.get(chat_id, [])
    return jsonify({"messages": messages}), 200


@app.route("/api/chats", methods=["GET"])
@require_auth
def get_chats(current_user):
    """Get all chat sessions for current user."""
    chat_sessions = []
    users_seen = set()
    
    # Find all chats this user is in by looking at messages_db keys
    for chat_id in messages_db.keys():
        # chat_id is str(tuple(sorted([user_id1, user_id2])))
        try:
            # Parse the chat_id back to get the two user IDs
            user_ids = eval(chat_id)  # Convert back from string representation
            if current_user.sub in user_ids:
                # Find the other user in this chat
                other_user_id = user_ids[0] if user_ids[1] == current_user.sub else user_ids[1]
                
                if other_user_id not in users_seen:
                    users_seen.add(other_user_id)
                    
                    # Get the other user's info from online users or construct from messages
                    other_user = None
                    if other_user_id in users_online:
                        other_user = users_online[other_user_id]
                        other_user_name = other_user.get("name", "Unknown")
                    else:
                        # Try to find name from messages if user is offline
                        messages_check = messages_db.get(chat_id, [])
                        other_user_name = "Unknown"
                        if messages_check:
                            for msg in messages_check:
                                if msg.get("from_id") == other_user_id:
                                    other_user_name = msg.get("from_name", "Unknown")
                                    break
                    
                    # Get last message
                    messages_check = messages_db.get(chat_id, [])
                    last_message = messages_check[-1] if messages_check else None
                    
                    chat_sessions.append({
                        "id": chat_id,  # IMPORTANT: Must be the chat_id
                        "other_user": {
                            "id": other_user_id,
                            "name": other_user_name,
                            "email": "unknown@example.com",
                            "avatar_color": get_avatar_color(other_user_id)
                        },
                        "last_message": last_message.get("text") if last_message else None,
                        "last_message_at": last_message.get("timestamp") if last_message else None,
                        "unread_count": 0,  # Placeholder - can be enhanced
                    })
        except Exception as e:
            logger.debug(f"Error parsing chat_id {chat_id}: {e}")
            continue
    
    return jsonify({"chat_sessions": chat_sessions}), 200


def get_avatar_color(user_id):
    """Generate a consistent avatar color based on user_id."""
    colors = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
        "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B195", "#C5E1A5"
    ]
    return colors[hash(user_id) % len(colors)]


@app.route("/api/chats/<user_id>", methods=["POST"])
@require_auth
def create_chat(user_id, current_user):
    """Create or get existing chat with a user."""
    # Create chat_id
    chat_id = str(tuple(sorted([current_user.sub, user_id])))
    
    # Get other user info
    other_user = None
    if user_id in users_online:
        other_user = users_online[user_id]
    else:
        # Try to find from messages if user is offline
        messages = messages_db.get(chat_id, [])
        if messages:
            for msg in messages:
                if msg.get("from_id") == user_id:
                    other_user = {
                        "sub": user_id,
                        "name": msg.get("from_name", "Unknown"),
                        "email": "unknown@example.com"
                    }
                    break
    
    if not other_user:
        other_user = {
            "sub": user_id,
            "name": "Unknown User",
            "email": "unknown@example.com"
        }
    
    return jsonify({
        "id": chat_id,
        "other_user_id": user_id,
        "other_user_name": other_user.get("name", "Unknown"),
        "other_user_email": other_user.get("email", "unknown@example.com"),
    }), 200


@app.route("/api/chats/<chat_id>/messages", methods=["GET"])
@require_auth
def get_chat_messages(chat_id, current_user):
    """Get messages from a chat."""
    # Validate that current user is part of this chat
    try:
        user_ids = eval(chat_id)
        if current_user.sub not in user_ids:
            return jsonify({"error": "Not authorized"}), 403
    except Exception as e:
        logger.debug(f"Invalid chat_id format: {chat_id}")
        return jsonify({"error": "Invalid chat_id"}), 400
    
    # Get messages and transform to frontend format
    raw_messages = messages_db.get(chat_id, [])
    messages = []
    
    for msg in raw_messages:
        messages.append({
            "sender": {
                "id": msg.get("from_id"),
                "name": msg.get("from_name", "Unknown"),
                "avatar_color": get_avatar_color(msg.get("from_id", ""))
            },
            "content": msg.get("text", ""),
            "created_at": msg.get("timestamp", datetime.utcnow().isoformat()),
        })
    
    return jsonify({"messages": messages}), 200


# ──────────────────────────────────────────────────────────────────────────
# WEBSOCKET - REAL-TIME CHAT
# ──────────────────────────────────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    """Handle WebSocket connection."""
    # Try to get token from query string first, then from auth header
    token = request.args.get("token")
    
    if not token:
        # Try to get from auth data (Socket.IO 4.x style)
        try:
            auth_data = request.environ.get("flask_session", {})
            token = auth_data.get("token") if isinstance(auth_data, dict) else None
        except:
            token = None
    
    if not token:
        logger.warning("✗ WebSocket connection attempted without token")
        emit("error", {"error": "No token provided"})
        # Don't return False - let the connection complete, just don't authenticate
        return True
    
    try:
        cognito_user = verify_cognito_token(token)
        
        # Store connection
        user_connections[cognito_user.sub] = request.sid
        users_online[cognito_user.sub] = {
            "name": cognito_user.name,
            "email": cognito_user.email,
            "sub": cognito_user.sub,
        }
        
        logger.info(f"✓ WebSocket authenticated: {cognito_user.email} (sid={request.sid})")
        
        # Emit auth success
        emit("auth_success", {
            "user_id": cognito_user.sub,
            "user_name": cognito_user.name,
            "user_email": cognito_user.email,
        })
        
        # Publish presence event via NATS → broadcast to all Socket.IO clients
        nats_publish("presence.online", {
            "user_id": cognito_user.sub,
            "name": cognito_user.name,
            "email": cognito_user.email,
        })
        
        # Send current online users to new user
        emit("users_list", {
            "users": [
                {"id": uid, "name": user["name"], "email": user["email"]}
                for uid, user in users_online.items()
                if uid != cognito_user.sub
            ]
        })
        
        return True
        
    except Exception as e:
        logger.error(f"✗ WebSocket auth error: {str(e)}")
        emit("auth_error", {"error": f"Authentication failed: {str(e)}"})
        return True  # Return True but emit error instead of closing


@socketio.on("disconnect")
def handle_disconnect():
    """Handle WebSocket disconnection."""
    # Find user by session_id
    user_id = None
    for uid, sid in list(user_connections.items()):
        if sid == request.sid:
            user_id = uid
            break
    
    if user_id:
        del user_connections[user_id]
        if user_id in users_online:
            user_name = users_online[user_id]["name"]
            del users_online[user_id]
            
            logger.info(f"User disconnected: {user_name}")

            # Publish presence event via NATS → broadcast to all Socket.IO clients
            nats_publish("presence.offline", {"user_id": user_id})


@socketio.on("message")
def handle_message(data):
    """Handle incoming message."""
    # Get sender from WebSocket connection
    sender_id = None
    for uid, sid in user_connections.items():
        if sid == request.sid:
            sender_id = uid
            break
    
    if not sender_id:
        logger.warning(f"✗ Message from unauthenticated connection: {request.sid}")
        emit("error", {"error": "Not authenticated"})
        return
    
    # Get message data
    recipient_id = data.get("recipient_id")
    content = data.get("content")
    
    if not recipient_id or not content:
        logger.warning(f"✗ Invalid message data from {sender_id}")
        emit("error", {"error": "Invalid message data"})
        return
    
    try:
        # Get sender info
        sender = users_online.get(sender_id)
        if not sender:
            logger.warning(f"✗ Sender {sender_id} not in users_online")
            emit("error", {"error": "Sender not found"})
            return
        
        # Create chat_id
        chat_id = str(tuple(sorted([sender_id, recipient_id])))
        if chat_id not in messages_db:
            messages_db[chat_id] = []
        
        # Store message
        message = {
            "from_id": sender_id,
            "from_name": sender.get("name", "Unknown"),
            "text": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        messages_db[chat_id].append(message)
        
        logger.info(f"✓ Message: {sender.get('email')} → {recipient_id}")

        # Publish via NATS → broadcast to all Socket.IO clients
        nats_publish(f"chat.message.{chat_id}", {
            "sender": {
                "id": sender_id,
                "name": sender.get("name", "Unknown"),
                "avatar_color": get_avatar_color(sender_id)
            },
            "content": content,
            "created_at": datetime.utcnow().isoformat(),
            "session_id": chat_id,
        })
        
    except Exception as e:
        logger.error(f"✗ Message error: {str(e)}")
        emit("error", {"error": f"Failed to send message: {str(e)}"})


@socketio.on("typing")
def handle_typing(data):
    """Handle typing indicator."""
    # Get sender from WebSocket connection
    sender_id = None
    for uid, sid in user_connections.items():
        if sid == request.sid:
            sender_id = uid
            break
    
    if not sender_id:
        return
    
    recipient_id = data.get("recipient_id")
    is_typing = data.get("is_typing", False)
    
    if not recipient_id:
        return
    
    try:
        sender = users_online.get(sender_id)
        if sender:
            # Publish via NATS → broadcast to all Socket.IO clients
            nats_publish(f"chat.typing.{str(tuple(sorted([sender_id, recipient_id])))}", {
                "user_id": sender_id,
                "user_name": sender.get("name", "Unknown"),
                "recipient_id": recipient_id,
                "is_typing": is_typing,
            })
        
    except Exception as e:
        logger.error(f"Typing error: {e}")


# ──────────────────────────────────────────────────────────────────────────
# ERROR HANDLERS
# ──────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(error):
    logger.exception(f"Server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


# ──────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"🚀 Chat Platform starting on http://localhost:{PORT}")
    logger.info(f"📍 Open http://localhost:{PORT} in your browser")
    socketio.run(app, host="0.0.0.0", port=PORT, debug=True, allow_unsafe_werkzeug=True)

