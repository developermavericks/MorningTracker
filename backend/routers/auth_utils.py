import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Union, Any
import hashlib
import base64
import bcrypt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

# Configuration (should be in .env)
# Priority: JWT_SECRET_KEY -> SECRET_KEY -> fallback
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY") or "fallback_secret_key_nexus_6000"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7

# FIX: passlib-bcrypt compatibility monkeypatch for modern bcrypt (4.0+)
# This prevents 'module bcrypt has no attribute __about__' and other errors.
import bcrypt as _bcrypt_module
if not hasattr(_bcrypt_module, "__about__"):
    class BcryptAbout:
        def __init__(self):
            self.__version__ = getattr(_bcrypt_module, "__version__", "4.0.0")
    _bcrypt_module.__about__ = BcryptAbout()

# Hashing Context (Legacy/Fallback)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

class TokenData(BaseModel):
    email: Optional[str] = None
    id: Optional[str] = None
    user_id: Optional[str] = None

def get_password_hash(password: str) -> str:
    # Standardize on pure bcrypt to avoid passlib-bcrypt version conflicts
    # Industry standard: Pre-hash with SHA256 to allow passwords > 72 bytes with bcrypt
    pw_hash = hashlib.sha256(password.encode("utf-8")).digest()
    pw_b64 = base64.b64encode(pw_hash)
    salt = bcrypt.gensalt()
    # Ensure result is decoded to string for DB storage
    return bcrypt.hashpw(pw_b64, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pw_hash = hashlib.sha256(plain_password.encode("utf-8")).digest()
        pw_b64 = base64.b64encode(pw_hash)
        # Check standard bcrypt first (our new format)
        return bcrypt.checkpw(pw_b64, hashed_password.encode("utf-8"))
    except Exception:
        # Fallback for old passlib hashes if they exist
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except:
            return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire, "refresh": True})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str):
    """Core logic to verify token and return user data (No Depends in signature)."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        if email is None or user_id is None:
            raise credentials_exception
        token_data = TokenData(email=email, id=user_id, user_id=user_id)
    except JWTError:
        raise credentials_exception
    
    return token_data

async def get_auth_user(token: str = Depends(oauth2_scheme), query_token: Optional[str] = None):
    """Dependency for HTTP routes. Handles both Header and Query tokens."""
    # Priority: Query Param (for downloads) -> Header (for API)
    final_token = query_token if query_token else token
    return await get_current_user(final_token)
