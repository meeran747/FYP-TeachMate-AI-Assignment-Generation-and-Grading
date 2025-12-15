"""
Authentication and Authorization Middleware for TeachMate

Provides:
- JWT token validation
- Role-based access control (RBAC)
- User context extraction
- Permission checking
"""

from fastapi import HTTPException, Security, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from functools import wraps
import logging
import os
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Supabase client for auth verification
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # Service role key for backend

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("✓ Supabase client initialized for auth")
    except Exception as e:
        logger.warning(f"Could not initialize Supabase client: {e}")

security = HTTPBearer(auto_error=False)


class UserContext:
    """User context extracted from JWT token"""
    def __init__(self, user_id: str, email: str, role: str, name: Optional[str] = None):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.name = name
    
    def is_admin(self) -> bool:
        return self.role == "admin"
    
    def is_teacher(self) -> bool:
        return self.role == "teacher"
    
    def is_student(self) -> bool:
        return self.role == "student"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "name": self.name
        }


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> UserContext:
    """
    Extract and validate user from JWT token.
    
    In production, this should verify the JWT token with Supabase.
    For now, we'll use a simplified approach that extracts user info from token.
    """
    # DEVELOPMENT ONLY: Bypass auth if BYPASS_AUTH env var is set
    BYPASS_AUTH = os.getenv("BYPASS_AUTH", "false").lower() == "true"
    if BYPASS_AUTH:
        logger.warning("⚠️ AUTH BYPASSED - Development mode only!")
        
        # Try to get token from credentials first, then from headers directly
        token = None
        if credentials and credentials.credentials:
            token = credentials.credentials.strip()
            logger.info(f"✓ Token found via HTTPBearer: {len(token)} chars")
        else:
            # Fallback: Check Authorization header directly
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()  # Remove "Bearer " prefix
                logger.info(f"✓ Token found via Authorization header: {len(token)} chars")
            else:
                logger.warning(f"⚠ No Authorization header found. Headers: {list(request.headers.keys())}")
        
        # If a token is provided, try to extract role from it
        if token:
            logger.info(f"🔍 Attempting to extract role from token in bypass mode (token length: {len(token)})")
            try:
                import base64
                import json
                # Try to decode token to get role
                try:
                    # Add padding if needed for base64
                    padding = 4 - len(token) % 4
                    if padding != 4:
                        token_padded = token + '=' * padding
                    else:
                        token_padded = token
                    
                    decoded = base64.b64decode(token_padded).decode('utf-8')
                    logger.info(f"✓ Token decoded successfully (length: {len(decoded)})")
                    
                    # Try JSON first
                    try:
                        token_data = json.loads(decoded)
                        logger.info(f"✓ Token parsed as JSON: {token_data}")
                        if isinstance(token_data, dict) and "role" in token_data:
                            role = token_data["role"]
                            user_id = token_data.get("id", "00000000-0000-0000-0000-000000000001")
                            email = token_data.get("email", "dev@example.com")
                            name = token_data.get("name", "Dev User")
                            logger.info(f"✓ Extracted role from token: {role} for user {email}")
                            return UserContext(
                                user_id=user_id,
                                email=email,
                                role=role,  # Use role from token
                                name=name
                            )
                        else:
                            logger.warning(f"Token JSON missing 'role' field. Keys: {list(token_data.keys()) if isinstance(token_data, dict) else 'not a dict'}")
                    except json.JSONDecodeError as json_err:
                        logger.info(f"Token is not JSON, trying colon-separated format: {json_err}")
                        # Try colon-separated format
                        if ':' in decoded:
                            parts = decoded.split(':')
                            logger.info(f"Colon-separated parts: {len(parts)} parts found")
                            if len(parts) >= 3:
                                role = parts[2]
                                user_id = parts[0]
                                email = parts[1] if len(parts) > 1 else "dev@example.com"
                                name = parts[3] if len(parts) > 3 else "Dev User"
                                logger.info(f"✓ Extracted role from colon-separated token: {role} for user {email}")
                                return UserContext(
                                    user_id=user_id,
                                    email=email,
                                    role=role,  # Use role from token
                                    name=name
                                )
                            else:
                                logger.warning(f"Colon-separated format has insufficient parts: {len(parts)}")
                        else:
                            logger.warning(f"Decoded token doesn't contain ':' separator")
                except Exception as decode_err:
                    logger.warning(f"Could not decode token in bypass mode: {decode_err}", exc_info=True)
            except Exception as e:
                logger.warning(f"Token parsing failed in bypass mode: {e}", exc_info=True)
        else:
            logger.info("No credentials or token provided in bypass mode")
        
        # Fallback: Use default dev user (teacher role)
        import uuid
        dev_user_id = os.getenv("DEV_USER_ID", "00000000-0000-0000-0000-000000000001")
        try:
            # Validate it's a valid UUID
            uuid.UUID(dev_user_id)
        except ValueError:
            # If invalid, use the default
            dev_user_id = "00000000-0000-0000-0000-000000000001"
        
        logger.info("Using default dev user (teacher role)")
        return UserContext(
            user_id=dev_user_id,
            email="dev@example.com",
            role="teacher",  # Default to teacher for assignment creation
            name="Dev User"
        )
    
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a valid token."
        )
    
    token = credentials.credentials
    
    # Clean token (remove any whitespace)
    token = token.strip() if token else token
    
    logger.info(f"🔐 Attempting to validate token (length: {len(token) if token else 0})")
    logger.info(f"   Token preview (first 50 chars): {token[:50] if token else 'None'}...")
    
    # Check if this is a real Supabase JWT (format: xxxx.yyyy.zzzz - 3 parts separated by dots)
    token_parts = token.split('.')
    is_jwt = len(token_parts) == 3
    
    if is_jwt:
        logger.info(f"✓ Detected JWT format (3 parts), verifying with Supabase Auth...")
        # This is a real JWT - verify with Supabase Auth directly
        if supabase:
            try:
                logger.info("🔐 Attempting Supabase JWT verification...")
                user_response = supabase.auth.get_user(token)
                
                if user_response and user_response.user:
                    user_id = user_response.user.id
                    
                    # Get user profile from database
                    profile = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
                    
                    if profile.data:
                        logger.info(f"✓ User verified via Supabase JWT: {profile.data['email']}")
                        return UserContext(
                            user_id=profile.data["id"],
                            email=profile.data["email"],
                            role=profile.data["role"],
                            name=profile.data.get("name")
                        )
                    else:
                        logger.warning(f"User {user_id} authenticated but profile not found in database")
                        raise HTTPException(status_code=404, detail="User profile not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid token")
                    
            except HTTPException:
                raise  # Re-raise HTTP exceptions
            except Exception as e:
                logger.error(f"Supabase JWT verification failed: {e}")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired token"
                )
        else:
            logger.error("Supabase client not initialized for JWT verification")
            raise HTTPException(
                status_code=500,
                detail="Authentication service not available"
            )
    
    # If not a JWT, try to decode as base64 JSON token (legacy custom format)
    import base64
    import json
    
    decoded = None
    token_data = None
    
    try:
        # Try base64 decoding with padding if needed
        try:
            decoded = base64.b64decode(token).decode('utf-8')
        except Exception:
            # Try adding padding if base64 decode fails
            padding = 4 - len(token) % 4
            if padding != 4:
                token = token + '=' * padding
                decoded = base64.b64decode(token).decode('utf-8')
        
        logger.info(f"✓ Token decoded successfully. Length: {len(decoded)}")
        logger.info(f"   First 150 chars: {decoded[:150]}")
        
        # Try to parse as JSON
        token_data = json.loads(decoded)
        logger.info(f"✓ Token parsed as JSON successfully!")
        
    except json.JSONDecodeError as e:
        # Not JSON - might be colon-separated format (legacy)
        logger.warning(f"✗ JSON decode failed: {e}")
        if decoded:
            logger.warning(f"   Decoded string (full): {decoded}")
            logger.warning(f"   Decoded string (repr): {repr(decoded)}")
            # Try parsing as colon-separated format (legacy: userId:email:role:name)
            if ':' in decoded:
                parts = decoded.split(':')
                if len(parts) >= 3:
                    logger.info("✓ Detected colon-separated token format, converting to JSON")
                    token_data = {
                        "id": parts[0],
                        "email": parts[1],
                        "role": parts[2],
                        "name": parts[3] if len(parts) > 3 else ""
                    }
                    logger.info(f"✓ Parsed token for user: {token_data.get('email')} (role: {token_data.get('role')})")
                else:
                    logger.warning(f"   Colon-separated format has wrong number of parts: {len(parts)}")
                    decoded = None
                    token_data = None
            else:
                logger.warning(f"   Will try Supabase JWT verification...")
                decoded = None
                token_data = None
        else:
            logger.warning(f"   Will try Supabase JWT verification...")
            decoded = None
            token_data = None
    except (UnicodeDecodeError, ValueError) as e:
        logger.warning(f"✗ Token decode failed: {e}, will try Supabase JWT...")
        decoded = None
        token_data = None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}", exc_info=True)
        decoded = None
        token_data = None
    
    # If we successfully decoded and parsed the token, validate it
    if token_data and isinstance(token_data, dict):
        # Validate token structure
        if "id" in token_data and "email" in token_data and "role" in token_data:
            logger.info(f"✓ Valid custom token format for user: {token_data.get('email')}")
            # This is our custom token format - verify user exists in database
            user_id = token_data["id"]
            email = token_data["email"]
            role = token_data["role"]
            name = token_data.get("name")
            
            # Optionally verify user still exists in database
            if supabase:
                try:
                    profile = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
                    if profile.data:
                        # User exists - return context
                        logger.info(f"✓ User verified in database: {email}")
                        return UserContext(
                            user_id=profile.data["id"],
                            email=profile.data["email"],
                            role=profile.data["role"],
                            name=profile.data.get("name")
                        )
                except Exception as db_error:
                    logger.warning(f"Could not verify user in database: {db_error}, using token data")
            
            # If database check failed or supabase not available, use token data
            logger.info(f"Using token data directly for user: {email}")
            return UserContext(
                user_id=user_id,
                email=email,
                role=role,
                name=name
            )
        else:
            logger.warning(f"Token decoded but missing required fields. Has: {list(token_data.keys())}")
            # Missing required fields - will try Supabase JWT
    
    # PRIMARY: Try Supabase JWT verification FIRST (this is what we want)
    if supabase:
        try:
            logger.info("🔐 Attempting Supabase JWT verification...")
            # Verify token with Supabase Auth
            # This expects a real Supabase JWT token (format: xxxx.yyyy.zzzz)
            user_response = supabase.auth.get_user(token)
            
            if user_response and user_response.user:
                user_id = user_response.user.id
                
                # Get user profile from database
                profile = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
                
                if profile.data:
                    logger.info(f"✓ User verified via Supabase JWT: {profile.data['email']}")
                    return UserContext(
                        user_id=profile.data["id"],
                        email=profile.data["email"],
                        role=profile.data["role"],
                        name=profile.data.get("name")
                    )
                else:
                    logger.warning(f"User {user_id} authenticated but profile not found in database")
                    raise HTTPException(status_code=404, detail="User profile not found")
            else:
                raise HTTPException(status_code=401, detail="Invalid token")
                
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            logger.debug(f"Supabase JWT verification failed (expected if using custom token): {e}")
            # Continue to custom token fallback
    
    # If all methods failed
    logger.error(f"All token validation methods failed. Token length: {len(token) if token else 0}")
    raise HTTPException(
        status_code=401,
        detail="Invalid token format. Please provide a valid authentication token."
    )


def require_role(*allowed_roles: str):
    """
    Decorator to require specific role(s) for an endpoint.
    
    Usage:
        @app.get("/admin-only")
        @require_role("admin")
        async def admin_endpoint(user: UserContext = Depends(get_current_user)):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user from kwargs (should be injected by Depends)
            user: Optional[UserContext] = None
            for key, value in kwargs.items():
                if isinstance(value, UserContext):
                    user = value
                    break
            
            if not user:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required"
                )
            
            if user.role not in allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_admin(func):
    """Shortcut decorator for admin-only endpoints"""
    return require_role("admin")(func)


def require_teacher(func):
    """Shortcut decorator for teacher-only endpoints"""
    return require_role("teacher")(func)


def require_student(func):
    """Shortcut decorator for student-only endpoints"""
    return require_role("student")(func)


# Dependency for optional authentication (for public endpoints)
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[UserContext]:
    """Get user if token is provided, otherwise return None"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

