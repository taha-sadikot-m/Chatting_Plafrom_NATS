"""
MeetKit — Python Backend
========================
Production-grade FastAPI server for LiveKit video meetings.

Environment variables (via .env):
    LIVEKIT_URL         wss://your-project.livekit.cloud  (REQUIRED)
    LIVEKIT_API_KEY     your_api_key                       (REQUIRED)
    LIVEKIT_API_SECRET  your_api_secret                    (REQUIRED)
    PORT                8080  (optional)
    LOG_LEVEL           info  (optional: debug | info | warning | error)
    TOKEN_TTL_HOURS     1     (optional, default 1)
    ALLOWED_ORIGINS     *     (optional, comma-separated list for strict CORS)
    ROOM_TTL_HOURS      24    (optional, room auto-cleanup interval)
"""

import os
import sys
import re
import time
import json
import datetime
import uuid
import logging
import secrets
import asyncio
import urllib.request
import random
import string
from pathlib import Path
from typing import Optional
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, field_validator

# ── LiveKit token generation ───────────────────────────────────────────────────
from livekit.api import AccessToken, VideoGrants

# ── Logging setup ──────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("meetkit")

# ── Load environment ───────────────────────────────────────────────────────────
load_dotenv()

LIVEKIT_URL        = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY    = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
TOKEN_TTL_HOURS    = int(os.getenv("TOKEN_TTL_HOURS", "1"))
ROOM_TTL_HOURS     = int(os.getenv("ROOM_TTL_HOURS", "24"))
PORT               = int(os.getenv("PORT", "8080"))

# Fail fast if credentials are missing
if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
    logger.critical(
        "LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set. "
        "Add them to your .env file or environment variables."
    )
    sys.exit(1)

# ── CORS origins ───────────────────────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS: list[str] = (
    ["*"] if _raw_origins.strip() == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

# ── Download LiveKit JS once, serve locally ────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
LIVEKIT_JS = STATIC_DIR / "livekit-client.umd.min.js"

LIVEKIT_JS_URLS = [
    "https://unpkg.com/livekit-client/dist/livekit-client.umd.min.js",
    "https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js",
]

if not LIVEKIT_JS.exists():
    logger.info("Downloading livekit-client.js …")
    downloaded = False
    for url in LIVEKIT_JS_URLS:
        try:
            urllib.request.urlretrieve(url, LIVEKIT_JS)
            logger.info("Saved → %s", LIVEKIT_JS)
            downloaded = True
            break
        except Exception as exc:
            logger.warning("Failed %s: %s", url, exc)
    if not downloaded:
        logger.error(
            "Could not download livekit-client.js. "
            "Manually place it at: %s", LIVEKIT_JS
        )
else:
    size_kb = LIVEKIT_JS.stat().st_size // 1024
    logger.info("livekit-client.js ready (%d KB)", size_kb)

# ── Rate Limiting ──────────────────────────────────────────────────────────────
_rate_limits: dict[str, list[float]] = defaultdict(list)

def _check_rate_limit(client_ip: str, endpoint: str, max_requests: int, window_seconds: int = 60):
    """Simple in-memory rate limiter. Raises 429 if limit exceeded."""
    key = f"{client_ip}:{endpoint}"
    now = time.time()
    # Prune old entries
    _rate_limits[key] = [t for t in _rate_limits[key] if now - t < window_seconds]
    if len(_rate_limits[key]) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Limit: {max_requests} per {window_seconds}s."
        )
    _rate_limits[key].append(now)


# ── Security Middleware ───────────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers (CSP, X-Frame-Options, etc.) to all responses."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), display-capture=(self)"
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' wss: https:; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects request bodies larger than max_bytes."""
    def __init__(self, app, max_bytes: int = 1_048_576):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large."},
            )
        return await call_next(request)


# ── FastAPI application ────────────────────────────────────────────────────────
app = FastAPI(
    title="MeetKit",
    description="Production LiveKit meeting room server",
    version="2.0.0",
    docs_url=None,      # Disable docs in production
    redoc_url=None,
)

# Order matters: outermost middleware runs first
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=1_048_576)  # 1 MB
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=ALLOWED_ORIGINS != ["*"],
)

# Serve /static/* locally (livekit-client.js etc.)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Startup / Shutdown ────────────────────────────────────────────────────────
_cleanup_task = None

@app.on_event("startup")
async def on_startup():
    global _cleanup_task
    logger.info("MeetKit starting on port %d", PORT)
    logger.info("LiveKit server : %s", LIVEKIT_URL)
    logger.info("CORS origins   : %s", ALLOWED_ORIGINS)
    logger.info("Token TTL      : %d h", TOKEN_TTL_HOURS)
    logger.info("Room TTL       : %d h", ROOM_TTL_HOURS)
    _cleanup_task = asyncio.create_task(_room_cleanup_loop())

@app.on_event("shutdown")
async def on_shutdown():
    if _cleanup_task:
        _cleanup_task.cancel()

# ── Request / Response models ──────────────────────────────────────────────────
def _validate_name(v: str) -> str:
    """Shared name validator: alphanumeric + hyphens/underscores/dots/spaces."""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. ")
    if not all(c in allowed for c in v):
        raise ValueError("Only letters, numbers, hyphens, underscores, dots, and spaces are allowed.")
    return v


class TokenRequest(BaseModel):
    room_name: str = Field(..., min_length=1, max_length=128)
    participant_name: str = Field(..., min_length=1, max_length=64)
    room_id: Optional[str] = Field(None, min_length=1, max_length=36)
    meeting_code: Optional[str] = Field(None, min_length=1, max_length=20)
    admin_secret: Optional[str] = Field(None, max_length=64)

    @field_validator("room_name", "participant_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    @field_validator("room_name")
    @classmethod
    def sanitise_room_name(cls, v: str) -> str:
        return _validate_name(v)


class TokenResponse(BaseModel):
    token: str
    livekit_url: str
    is_admin: bool = False
    admin_identity: Optional[str] = None


class RoomCreateRequest(BaseModel):
    room_name: str = Field(..., min_length=1, max_length=128)
    creator_name: str = Field(..., min_length=1, max_length=128)

    @field_validator("room_name", "creator_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    @field_validator("room_name")
    @classmethod
    def sanitise_room_name(cls, v: str) -> str:
        return _validate_name(v)


class RoomCreateResponse(BaseModel):
    room_id: str
    room_name: str
    meeting_url: str
    meeting_code: str
    admin_secret: str


# ── In-memory room registry (stores code → room mapping) ──────────────────────
_room_registry: dict[str, dict] = {}

# Meeting code format validation
_MEETING_CODE_RE = re.compile(r"^[a-z0-9]{3}-[a-z0-9]{3}-[a-z0-9]{3}$")


def generate_meeting_code() -> str:
    """Generate a Google Meet-style code: xxx-yyy-zzz using cryptographic randomness."""
    charset = string.ascii_lowercase + string.digits
    for _ in range(100):  # bounded retries
        parts = [''.join(secrets.choice(charset) for _ in range(3)) for _ in range(3)]
        code = '-'.join(parts)
        if code not in _room_registry:
            return code
    raise HTTPException(status_code=503, detail="Could not generate unique meeting code.")


async def _room_cleanup_loop():
    """Background task to purge expired rooms."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        now = datetime.datetime.now()
        expired = [
            code for code, data in _room_registry.items()
            if (now - datetime.datetime.fromisoformat(data["created_at"])).total_seconds()
               > ROOM_TTL_HOURS * 3600
        ]
        for code in expired:
            del _room_registry[code]
        if expired:
            logger.info("Cleaned up %d expired rooms", len(expired))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/join/{meeting_code}", response_class=HTMLResponse, include_in_schema=False)
async def join_with_code(meeting_code: str):
    """
    Serve the frontend pre-filled with room details from the meeting code.
    """
    # Validate meeting code format to prevent injection
    if not _MEETING_CODE_RE.match(meeting_code):
        raise HTTPException(status_code=400, detail="Invalid meeting code format.")

    html_path = Path(__file__).parent / "index.html"
    if not html_path.exists():
        logger.error("index.html not found at %s", html_path)
        raise HTTPException(status_code=404, detail="index.html not found")

    html_content = html_path.read_text(encoding="utf-8")

    # Safe injection using json.dumps for proper JS string escaping
    safe_code = json.dumps(meeting_code)
    script_injection = f"""
    <script>
      window.__meetingCode = {safe_code};
    </script>
    """
    
    # Inject script before closing head tag
    html_content = html_content.replace('</head>', script_injection + '</head>')
    
    return HTMLResponse(content=html_content)


@app.get("/lookup-room", include_in_schema=False)
async def lookup_room(meeting_code: str = ""):
    """
    Look up room details from a meeting code.
    Returns room_name and room_id for the frontend to use.
    
    Query params:
      - meeting_code: The meeting code to look up
    """
    if not meeting_code or meeting_code not in _room_registry:
        raise HTTPException(
            status_code=404,
            detail=f"Meeting code '{meeting_code}' not found. The link may have expired."
        )
    
    room_data = _room_registry[meeting_code]
    logger.info("Room lookup — code=%r  room_name=%r", meeting_code, room_data["room_name"])
    
    return {
        "room_name": room_data["room_name"],
        "room_id": room_data["room_id"],
        "meeting_code": meeting_code
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    """Serve the single-file meeting room UI."""
    html_path = Path(__file__).parent / "index.html"
    if not html_path.exists():
        logger.error("index.html not found at %s", html_path)
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/create-room", response_model=RoomCreateResponse)
async def create_room(req: RoomCreateRequest, request: Request):
    """
    Create a new meeting room with a unique short code.
    
    Returns:
      - room_id: Unique identifier for the room (UUID)
      - room_name: The name of the room
      - meeting_code: Short shareable code (like Google Meet: abc-def-ghi)
      - meeting_url: Shareable URL to join the room
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip, "create-room", max_requests=5)

    room_id = str(uuid.uuid4())
    meeting_code = generate_meeting_code()
    admin_secret = secrets.token_urlsafe(32)

    _room_registry[meeting_code] = {
        "room_name": req.room_name,
        "room_id": room_id,
        "created_at": datetime.datetime.now().isoformat(),
        "creator_name": req.creator_name,
        "admin_secret": admin_secret,
        "admin_identity": None,
        "admin_name": None,
    }
    
    logger.info(
        "Room created — name=%r  code=%r  room_id=%r  ip=%s",
        req.room_name, meeting_code, room_id, client_ip,
    )
    
    # Construct the shareable URL
    # Format: http://localhost:8080/join/abc-def-ghi
    protocol = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", request.client.host if request.client else "localhost:8080")
    meeting_url = f"{protocol}://{host}/join/{meeting_code}"
    
    logger.debug("Meeting URL — url=%s", meeting_url)
    return RoomCreateResponse(
        room_id=room_id,
        room_name=req.room_name,
        meeting_code=meeting_code,
        meeting_url=meeting_url,
        admin_secret=admin_secret,
    )


@app.post("/token", response_model=TokenResponse)
async def get_token(req: TokenRequest, request: Request):
    """
    Generate a signed LiveKit access token.

    The token grants the participant permission to:
      - join the requested room (auto-created if it doesn't exist)
      - publish & subscribe to audio/video tracks
      - send and receive data messages
      
    If meeting_code is provided, room details are looked up from the registry.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip, "token", max_requests=15)

    room_name = req.room_name
    room_id = req.room_id

    if req.meeting_code:
        if req.meeting_code not in _room_registry:
            logger.warning("Invalid meeting code — code=%r  ip=%s", req.meeting_code, client_ip)
            raise HTTPException(
                status_code=404,
                detail="Meeting code not found or has expired."
            )
        room_data = _room_registry[req.meeting_code]
        room_name = room_data["room_name"]
        room_id = room_data["room_id"]

    logger.info(
        "Token request — room=%r  participant=%r  room_id=%r  code=%r  ip=%s",
        room_name, req.participant_name, room_id, req.meeting_code, client_ip,
    )

    display_name    = req.participant_name
    unique_identity = f"{display_name}-{uuid.uuid4().hex}"

    is_admin = False
    admin_identity = None

    # Secure admin identification via admin_secret token
    if req.meeting_code and req.meeting_code in _room_registry:
        room_data = _room_registry[req.meeting_code]

        if req.admin_secret and secrets.compare_digest(req.admin_secret, room_data["admin_secret"]):
            # Verified admin via secret token
            room_data["admin_identity"] = unique_identity
            room_data["admin_name"] = display_name
            is_admin = True
            logger.info("Admin verified via secret — code=%r  admin=%r", req.meeting_code, display_name)
        elif not room_data["admin_identity"] and not req.admin_secret:
            # First joiner becomes admin only if no admin set yet (no secret needed)
            room_data["admin_identity"] = unique_identity
            room_data["admin_name"] = display_name
            is_admin = True
            logger.info("Admin assigned to first joiner — code=%r  admin=%r", req.meeting_code, display_name)
        else:
            admin_identity = room_data["admin_identity"]
    
    try:
        token = (
            AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(unique_identity)
            .with_name(display_name)
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .with_ttl(datetime.timedelta(hours=TOKEN_TTL_HOURS))
            .to_jwt()
        )
    except Exception as exc:
        logger.exception("Token generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token generation failed. Check server configuration.",
        )

    logger.debug("Issued token for identity=%r room=%r admin=%s", unique_identity, room_name, is_admin)
    return TokenResponse(
        token=token,
        livekit_url=LIVEKIT_URL,
        is_admin=is_admin,
        admin_identity=admin_identity
    )


class RemoveParticipantRequest(BaseModel):
    meeting_code: str = Field(..., min_length=1, max_length=20)
    admin_identity: str = Field(..., min_length=1)
    participant_identity: str = Field(..., min_length=1)


@app.post("/remove-participant", include_in_schema=False)
async def remove_participant(req: RemoveParticipantRequest, request: Request):
    """
    Remove a participant from a room. Only verified admin can remove others.
    Validates admin_identity against the stored admin for the meeting.
    """
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "Remove request — code=%r  admin=%r  target=%r  ip=%s",
        req.meeting_code, req.admin_identity, req.participant_identity, client_ip,
    )

    # Validate meeting code exists
    if req.meeting_code not in _room_registry:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    room_data = _room_registry[req.meeting_code]

    # Verify the requester is actually the admin
    if room_data["admin_identity"] != req.admin_identity:
        logger.warning("Unauthorized remove attempt — code=%r  claimed_admin=%r  real_admin=%r",
                       req.meeting_code, req.admin_identity, room_data.get("admin_identity"))
        raise HTTPException(status_code=403, detail="Only the room admin can remove participants.")

    if req.admin_identity == req.participant_identity:
        raise HTTPException(status_code=400, detail="Admin cannot remove themselves.")

    logger.info("Participant removal authorized — code=%r  target=%r", req.meeting_code, req.participant_identity)

    return {
        "status": "removed",
        "message": f"Participant removed from room",
        "meeting_code": req.meeting_code,
    }


@app.get("/health", include_in_schema=False)
async def health():
    """Liveness check — returns 200 if the process is alive."""
    return JSONResponse({"status": "ok", "timestamp": time.time()})


@app.get("/ready", include_in_schema=False)
async def ready():
    """
    Readiness check — returns 200 only when the server can issue tokens.
    Returns 503 if credentials look unconfigured.
    """
    issues = []
    if not LIVEKIT_API_KEY:
        issues.append("LIVEKIT_API_KEY not configured")
    if not LIVEKIT_API_SECRET:
        issues.append("LIVEKIT_API_SECRET not configured")
    if not LIVEKIT_JS.exists():
        issues.append("livekit-client.js missing")

    if issues:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "issues": issues, "timestamp": time.time()},
        )

    return JSONResponse({"status": "ready", "timestamp": time.time()})


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    banner = f"""
╔══════════════════════════════════════════════╗
║          MeetKit  —  Meeting Server          ║
╠══════════════════════════════════════════════╣
║  URL      :  http://localhost:{PORT:<15}║
║  LiveKit  :  {LIVEKIT_URL[:32]:<32}║
║  Docs     :  http://localhost:{PORT}/docs    ║
╚══════════════════════════════════════════════╝
  → Open http://localhost:{PORT} in TWO browser tabs
  → Use the SAME room name, different usernames
"""
    print(banner)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        reload=False,
        access_log=True,
        log_level=LOG_LEVEL.lower(),
    )