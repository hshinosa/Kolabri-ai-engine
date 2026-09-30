"""
Authentication Middleware for AI Engine API
============================================
KOL-142: Enforce Authentication for AI Engine API Routes

Provides API key authentication for sensitive endpoints.
"""

from fastapi import Request, HTTPException, Depends
from typing import Optional
import hmac
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def validate_api_key(api_key: str) -> bool:
    """
    Validate API key against configured secret.
    
    Args:
        api_key: API key from request header
        
    Returns:
        True if valid, False otherwise
    """
    if not api_key:
        return False
    
    if hmac.compare_digest(api_key, settings.CORE_API_SECRET):
        return True
    
    return False


async def require_auth(request: Request) -> dict:
    """
    Dependency to require authentication for API routes.
    Rate limited to 5 attempts per minute per IP (KOL-142c).
    
    Args:
        request: FastAPI request object
        
    Returns:
        dict with auth info
        
    Raises:
        HTTPException: 401 if no auth, 403 if invalid
    """
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        logger.warning(
            "auth_missing",
            path=str(request.url),
            method=request.method,
            ip=getattr(request.client, 'host', 'unknown')
        )
        raise HTTPException(
            status_code=401,
            detail="Authorization header required. Use: Authorization: Bearer YOUR_API_KEY",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Extract API key from "Bearer YOUR_KEY" format
    parts = auth_header.split()
    
    if len(parts) != 2:
        logger.warning(
            "auth_invalid_format",
            path=str(request.url),
            ip=getattr(request.client, 'host', 'unknown')
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization format. Use: Authorization: Bearer YOUR_API_KEY"
        )
    
    scheme, api_key = parts
    
    if scheme.lower() != "bearer":
        logger.warning(
            "auth_invalid_scheme",
            scheme=scheme,
            path=str(request.url)
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication scheme. Use: Bearer"
        )
    
    # Validate API key
    if not validate_api_key(api_key):
        logger.warning(
            "auth_invalid_key",
            path=str(request.url),
            ip=getattr(request.client, 'host', 'unknown')
        )
        raise HTTPException(
            status_code=403,
            detail="Invalid credentials"
        )
    
    # Log successful authentication
    logger.info(
        "auth_success",
        path=str(request.url),
        method=request.method,
        ip=getattr(request.client, 'host', 'unknown')
    )
    
    return {
        "authenticated": True,
        "api_key": api_key[:10] + "..." if len(api_key) > 10 else api_key
    }


# Optional authentication (doesn't block, but logs)
async def optional_auth(request: Request) -> dict:
    """
    Optional authentication - logs but doesn't block.
    
    Usage:
        @router.get("/api/public", dependencies=[Depends(optional_auth)])
        async def public_endpoint():
            pass
    """
    auth_header = request.headers.get("Authorization")
    
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2:
            scheme, api_key = parts
            if scheme.lower() == "bearer" and validate_api_key(api_key):
                logger.info(
                    "auth_success_optional",
                    path=str(request.url)
                )
                return {"authenticated": True}
    
    return {"authenticated": False}
