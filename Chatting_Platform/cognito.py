"""
AWS Cognito Authentication Module for Flask
=============================================
Handles JWT token verification, user validation, and Cognito operations.
"""

import os
import json
import logging
import requests
import base64
import uuid
import time
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import boto3
from jose import jwt, JWTError
from jose.exceptions import JWTClaimsError

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
except ImportError:
    try:
        from Crypto.PublicKey import RSA
        HAS_CRYPTO = True
    except ImportError:
        HAS_CRYPTO = False

logger = logging.getLogger("cognito_auth")

# ── Helper Functions ──────────────────────────────────────────────────────────

def jwk_to_rsa_public_key(jwk: dict) -> Any:
    """
    Convert a JWK (JSON Web Key) to an RSA public key suitable for JWT verification.
    
    Args:
        jwk: JWK dict with 'n' (modulus) and 'e' (exponent)
        
    Returns:
        RSA public key object
    """
    try:
        n = int.from_bytes(base64.urlsafe_b64decode(jwk['n'] + '=='), byteorder='big')
        e = int.from_bytes(base64.urlsafe_b64decode(jwk['e'] + '=='), byteorder='big')
        
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend
            
            public_numbers = rsa.RSAPublicNumbers(e, n)
            public_key = public_numbers.public_key(default_backend())
            logger.debug("JWK converted using cryptography library")
            return public_key
        except ImportError:
            from Crypto.PublicKey import RSA
            public_key = RSA.construct((n, e))
            logger.debug("JWK converted using PyCryptodome")
            return public_key
            
    except Exception as e:
        logger.error("Failed to convert JWK to RSA key: %s", str(e))
        raise ValueError(f"Invalid JWK format: {str(e)}")


def generate_oauth_state() -> str:
    """Generate a unique state parameter for OAuth2 CSRF protection."""
    return uuid.uuid4().hex


def is_valid_oauth_state(state: str) -> bool:
    """
    Validate OAuth state parameter exists and hasn't expired.
    
    Returns:
        True if state is valid and not expired
    """
    if state not in _oauth_sessions:
        logger.warning("OAuth state not found: %s", state[:8] + "...")
        return False
    
    session = _oauth_sessions[state]
    age = time.time() - session["timestamp"]
    
    if age > OAUTH_SESSION_TTL:
        logger.warning("OAuth session expired (age: %.0fs, TTL: %d): %s", age, OAUTH_SESSION_TTL, state[:8] + "...")
        del _oauth_sessions[state]
        return False
    
    return True


def consume_oauth_state(state: str):
    """
    Consume (validate and remove) an OAuth state.
    
    Returns:
        The stored session dict if state was valid (contains 'timestamp' and optionally 'redirect_uri'),
        or False if invalid/expired.
    """
    if state not in _oauth_sessions:
        logger.warning("OAuth state not found for consumption: %s", state[:8] + "...")
        return False
    
    age = time.time() - _oauth_sessions[state]["timestamp"]
    if age > OAUTH_SESSION_TTL:
        logger.warning("OAuth session expired (age: %.0fs, TTL: %d)", age, OAUTH_SESSION_TTL)
        del _oauth_sessions[state]
        return False
    
    session_data = _oauth_sessions.pop(state)
    logger.debug("OAuth session consumed (age: %.1fs)", age)
    return session_data


# ── Environment Configuration ────────────────────────────────────────────────
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET", "")
COGNITO_REGION = os.getenv("COGNITO_REGION", "us-east-1")
COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN")
APP_REDIRECT_URI = os.getenv("APP_REDIRECT_URI", "http://localhost:5000/auth/callback")

# AWS Cognito client
cognito_client = boto3.client("cognito-idp", region_name=COGNITO_REGION)

# Cache for JWKS (public keys) — refreshed hourly
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_time: float = 0

# Session state tracking for OAuth2 security (prevents CSRF)
_oauth_sessions: Dict[str, Dict[str, Any]] = {}
OAUTH_SESSION_TTL = 1800  # 30 minutes (allow time for user to login)


class CognitoUser:
    """Represents an authenticated Cognito user."""
    
    def __init__(self, sub: str, email: str, name: str, groups: Optional[list] = None):
        self.sub = sub
        self.email = email
        self.name = name
        self.groups = groups or []
    
    def to_dict(self) -> dict:
        return {
            "sub": self.sub,
            "email": self.email,
            "name": self.name,
            "groups": self.groups,
        }


def get_cognito_jwks():
    """
    Fetch AWS Cognito public keys (JWKS) for JWT verification.
    Caches for 1 hour to minimize API calls.
    """
    global _jwks_cache, _jwks_cache_time
    import time
    
    now = time.time()
    if _jwks_cache and (now - _jwks_cache_time) < 3600:
        return _jwks_cache
    
    try:
        jwks_url = (
            f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
            f"{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )
        response = requests.get(jwks_url, timeout=5)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_time = now
        logger.debug("JWKS refreshed from Cognito")
        return _jwks_cache
    except Exception as e:
        logger.error("Failed to fetch Cognito JWKS: %s", e)
        raise ValueError(f"Failed to verify token: {str(e)}")


def verify_cognito_token(token: str) -> CognitoUser:
    """
    Verify and decode a Cognito ID token (JWT).
    
    Args:
        token: JWT token from Cognito
        
    Returns:
        CognitoUser with claims extracted
        
    Raises:
        ValueError: If token is invalid, expired, or verification fails
    """
    if not token:
        raise ValueError("No token provided")
    
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            logger.warning("Token missing 'kid' in header")
            raise ValueError("Invalid token format")
        
        jwks = get_cognito_jwks()
        keys = jwks.get("keys", [])
        key_data = None
        
        for key in keys:
            if key.get("kid") == kid:
                key_data = key
                break
        
        if not key_data:
            logger.warning("No matching key found for kid: %s", kid)
            raise ValueError("Invalid token")
        
        public_key = jwk_to_rsa_public_key(key_data)
        logger.debug("Public key obtained from JWK")
        
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=COGNITO_CLIENT_ID,
            options={"verify_at_hash": False},
        )
        
        sub = claims.get("sub")
        email = claims.get("email", "")
        name = claims.get("name", claims.get("email", "Unknown"))
        
        if not sub:
            logger.warning("Token missing 'sub' claim")
            raise ValueError("Invalid token claims")
        
        logger.debug("Token verified for user: %s (%s)", sub, email)
        return CognitoUser(
            sub=sub,
            email=email,
            name=name,
            groups=claims.get("cognito:groups", [])
        )
        
    except JWTError as e:
        logger.warning("JWT verification failed: %s", str(e))
        raise ValueError(f"Invalid or expired token: {str(e)}")
    except JWTClaimsError as e:
        logger.warning("JWT claims validation failed: %s", str(e))
        raise ValueError(f"Token claims validation failed: {str(e)}")
    except Exception as e:
        logger.exception("Unexpected error during token verification: %s", e)
        raise ValueError(f"Token verification failed: {str(e)}")


def get_cognito_login_url(state: str, redirect_uri: str = None) -> str:
    """
    Generate the Cognito OAuth2 authorize endpoint URL with state parameter.
    
    Args:
        state: OAuth2 state parameter for CSRF protection
        redirect_uri: Override redirect URI (e.g. ngrok URL). Falls back to APP_REDIRECT_URI.
        
    Returns:
        The full Cognito authorize URL
    """
    authorize_endpoint = f"{COGNITO_DOMAIN}/oauth2/authorize"
    
    params = {
        "client_id": COGNITO_CLIENT_ID,
        "response_type": "code",
        "scope": "openid email",
        "redirect_uri": redirect_uri or APP_REDIRECT_URI,
        "state": state,
    }
    
    query_string = urlencode(params)
    login_url = f"{authorize_endpoint}?{query_string}"
    
    logger.debug(f"Generated Cognito login URL with state: {state[:8]}...")
    return login_url


def get_cognito_logout_url(logout_redirect_uri: str = "http://localhost:5000/") -> str:
    """
    Generate the Cognito logout endpoint URL.
    
    Args:
        logout_redirect_uri: Where to redirect after logout
        
    Returns:
        The full Cognito logout URL
    """
    logout_endpoint = f"{COGNITO_DOMAIN}/logout"
    
    params = {
        "client_id": COGNITO_CLIENT_ID,
        "post_logout_redirect_uri": logout_redirect_uri,
    }
    
    query_string = urlencode(params)
    logout_url = f"{logout_endpoint}?{query_string}"
    
    logger.debug(f"Generated Cognito logout URL, redirect to: {logout_redirect_uri}")
    return logout_url


def exchange_code_for_token(code: str, redirect_uri: str = None) -> Optional[Dict[str, Any]]:
    """
    Exchange Cognito authorization code for tokens.
    
    Args:
        code: Authorization code from Cognito redirect
        redirect_uri: Override redirect URI (must match what was used in /oauth2/authorize)
        
    Returns:
        Dict with tokens {id_token, access_token, refresh_token, expires_in}
        or None if exchange fails
    """
    try:
        payload = {
            "grant_type": "authorization_code",
            "client_id": COGNITO_CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri or APP_REDIRECT_URI,
        }
        
        if COGNITO_CLIENT_SECRET:
            payload["client_secret"] = COGNITO_CLIENT_SECRET
        
        response = requests.post(
            f"{COGNITO_DOMAIN}/oauth2/token",
            data=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            tokens = response.json()
            logger.debug("Successfully exchanged code for tokens")
            return tokens
        else:
            logger.error(
                "Token exchange failed: %d - %s",
                response.status_code,
                response.text
            )
            return None
            
    except Exception as e:
        logger.exception("Error exchanging code for token: %s", e)
        return None


def create_cognito_user(email: str, password: str, name: str) -> bool:
    """
    Create a new user in Cognito User Pool.
    
    Args:
        email: User email (must be unique)
        password: User password
        name: User display name
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cognito_client.admin_create_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=email,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": name},
            ]
        )
        
        cognito_client.admin_set_user_password(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=email,
            Password=password,
            Permanent=True
        )
        
        logger.info("Created Cognito user: %s", email)
        return True
        
    except cognito_client.exceptions.UsernameExistsException:
        logger.warning("User already exists: %s", email)
        return False
    except Exception as e:
        logger.error("Failed to create Cognito user: %s", e)
        return False


def validate_cognito_config() -> bool:
    """
    Validate that all required Cognito environment variables are set.
    """
    required = [
        COGNITO_USER_POOL_ID,
        COGNITO_CLIENT_ID,
        COGNITO_REGION,
        COGNITO_DOMAIN,
        APP_REDIRECT_URI,
    ]
    
    missing = [var for var in required if not var]
    
    if missing:
        logger.error("Missing required Cognito config")
        return False
    
    logger.info("Cognito config validated ✓")
    return True
