import uuid

import jwt
from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session

from dependencies.database import get_db
from models.api_key import ApiKey
from models.user import User
from utils.api_key import hash_api_key
from utils.tokens import decode_access_token


def get_request_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get("access_token")

def get_user_from_api_key(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        return None

    raw_key = authorization.replace("Bearer ", "").strip()

    key_hash = hash_api_key(raw_key)

    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash)
        .first()
    )

    if not api_key:
        return None

    user = db.query(User).filter(User.id == api_key.user_id).first()

    if not user or not user.is_active:
        return None

    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:

    # 1. Try API key first
    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.startswith("Bearer sk_"):
        user = get_user_from_api_key(auth_header, db)
        if user:
            return user

            
    token = get_request_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Access denied")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
