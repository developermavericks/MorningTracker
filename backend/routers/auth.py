from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select, insert
from .auth_utils import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    get_auth_user,
    TokenData
)
from db.database import get_db_yield, User
import os
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# Google OAuth Setup
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@router.post("/register")
async def register(request: Request, db: AsyncSession = Depends(get_db_yield)):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    # Check if user exists
    stmt = select(User.id).where(User.email == email)
    res = await db.execute(stmt)
    if res.scalar():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(password)
    
    new_user = User(
        id=user_id,
        email=email,
        name=name,
        hashed_password=hashed_password
    )
    db.add(new_user)
    await db.commit()
    
    return {"message": "User registered successfully"}

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db_yield)):
    stmt = select(User).where(User.email == form_data.username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    
    if not user or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.email, "user_id": user.id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {"email": user.email, "name": user.name}
    }

@router.get("/google")
async def google_login(request: Request):
    redirect_uri = request.url_for('google_callback')
    # If we're behind a proxy (Railway) that terminates SSL, url_for might incorrectly return http.
    # We force https if not on localhost.
    if 'localhost' not in str(request.base_url) and not str(redirect_uri).startswith('https'):
        redirect_uri = str(redirect_uri).replace('http://', 'https://')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db_yield)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Google authentication failed")
    
    email = user_info['email']
    name = user_info.get('name')
    google_id = user_info['sub']
    
    # Check if user exists
    stmt = select(User).where(User.email == email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email=email,
            name=name,
            google_id=google_id
        )
        db.add(user)
        await db.commit()
    
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.email, "user_id": user.id})
    
    from fastapi.responses import RedirectResponse
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(url=f"{frontend_url}/login#token={access_token}")

@router.get("/me")
async def get_me(user_data: TokenData = Depends(get_auth_user), db: AsyncSession = Depends(get_db_yield)):
    """
    Returns the current authenticated user's information.
    """
    stmt = select(User).where(User.id == user_data.user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "email": user.email,
        "name": user.name,
        "id": user.id
    }
