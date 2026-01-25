"""
Clerk Authentication Module for LeadPilot.

Provides JWT verification, session management, and authentication middleware
for the FastAPI application using Clerk as the authentication provider.
"""

import os
import logging
import httpx
from functools import wraps
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, jwk, JWTError
from jose.utils import base64url_decode

logger = logging.getLogger(__name__)

# Clerk Configuration
CLERK_PUBLISHABLE_KEY = os.environ.get(
    "CLERK_PUBLISHABLE_KEY", 
    "pk_test_ZGVjaWRpbmctcmVwdGlsZS00NS5jbGVyay5hY2NvdW50cy5kZXYk"
)
CLERK_SECRET_KEY = os.environ.get(
    "CLERK_SECRET_KEY",
    "sk_test_4ZLvDlSIzqRk2vhW3Rb3EIKjRaINqZoDyWmXw0JLHH"
)
CLERK_FRONTEND_API = os.environ.get(
    "CLERK_FRONTEND_API",
    "https://deciding-reptile-45.clerk.accounts.dev"
)
CLERK_JWKS_URL = f"{CLERK_FRONTEND_API}/.well-known/jwks.json"

# Cache for JWKS keys
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_time: Optional[datetime] = None
JWKS_CACHE_DURATION = 3600  # 1 hour


async def get_jwks() -> Dict[str, Any]:
    """Fetch and cache JWKS from Clerk."""
    global _jwks_cache, _jwks_cache_time
    
    now = datetime.now()
    
    # Return cached if valid
    if _jwks_cache and _jwks_cache_time:
        age = (now - _jwks_cache_time).total_seconds()
        if age < JWKS_CACHE_DURATION:
            return _jwks_cache
    
    # Fetch fresh JWKS
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(CLERK_JWKS_URL)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_time = now
            logger.info("Successfully fetched Clerk JWKS")
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache:
            return _jwks_cache
        raise HTTPException(status_code=500, detail="Authentication service unavailable")


def get_key_from_jwks(jwks: Dict[str, Any], kid: str) -> Optional[Dict]:
    """Find the correct key from JWKS by key ID."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


async def verify_clerk_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Clerk JWT token and return the decoded payload.
    
    Returns None if verification fails.
    """
    try:
        # Get the header to find the key ID
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        
        if not kid:
            logger.warning("Token missing key ID (kid)")
            return None
        
        # Get JWKS and find matching key
        jwks = await get_jwks()
        key_data = get_key_from_jwks(jwks, kid)
        
        if not key_data:
            logger.warning(f"No matching key found for kid: {kid}")
            return None
        
        # Construct the public key
        public_key = jwk.construct(key_data)
        
        # Verify and decode the token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=None,  # Clerk doesn't set audience by default
            options={
                "verify_aud": False,
                "verify_iss": True,
            },
            issuer=CLERK_FRONTEND_API
        )
        
        logger.info(f"Token verified for user: {payload.get('sub')}")
        return payload
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return None


def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract the Clerk session token from the request."""
    
    # Check Authorization header first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Check for __session cookie (Clerk's default)
    session_cookie = request.cookies.get("__session")
    if session_cookie:
        return session_cookie
    
    # Check for __clerk_db_jwt cookie (alternative)
    clerk_jwt = request.cookies.get("__clerk_db_jwt")
    if clerk_jwt:
        return clerk_jwt
    
    return None


async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Get the current authenticated user from the request.
    
    Returns the user payload if authenticated, None otherwise.
    """
    token = extract_token_from_request(request)
    
    if not token:
        return None
    
    return await verify_clerk_token(token)


async def require_auth(request: Request) -> Dict[str, Any]:
    """
    Dependency that requires authentication.
    
    Raises HTTPException 401 if not authenticated.
    """
    user = await get_current_user(request)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user


async def get_user_info(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed user information from Clerk Backend API.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.clerk.com/v1/users/{user_id}",
                headers={
                    "Authorization": f"Bearer {CLERK_SECRET_KEY}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to fetch user info: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"Error fetching user info: {e}")
        return None


class AuthState:
    """Helper class to manage authentication state in templates."""
    
    def __init__(self, user: Optional[Dict[str, Any]] = None):
        self.user = user
        self.is_authenticated = user is not None
    
    @property
    def user_id(self) -> Optional[str]:
        return self.user.get("sub") if self.user else None
    
    @property
    def email(self) -> Optional[str]:
        return self.user.get("email") if self.user else None
    
    @property
    def name(self) -> Optional[str]:
        if not self.user:
            return None
        # Try different name fields
        return (
            self.user.get("name") or 
            self.user.get("given_name") or 
            self.user.get("email", "").split("@")[0]
        )
    
    @property
    def picture(self) -> Optional[str]:
        return self.user.get("picture") if self.user else None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_authenticated": self.is_authenticated,
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "picture": self.picture,
        }


async def get_auth_state(request: Request) -> AuthState:
    """Get authentication state for use in templates."""
    user = await get_current_user(request)
    return AuthState(user)


# Middleware helper for optional auth
async def optional_auth(request: Request) -> Optional[Dict[str, Any]]:
    """
    Dependency that optionally gets user info.
    
    Returns user if authenticated, None otherwise.
    Does not raise exceptions.
    """
    try:
        return await get_current_user(request)
    except Exception:
        return None
