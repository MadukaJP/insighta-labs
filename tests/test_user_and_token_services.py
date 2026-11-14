import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core.config import settings
from dependencies.auth import get_current_user
from models.refresh_token import RefreshToken
from models.user import User
from services import user_service
from utils.custom_content import custom_content
from utils.tokens import create_access_token, create_refresh_token, decode_access_token


def make_http_request(headers=None, cookies=None):
    raw_headers = [
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    ]
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_str.encode()))

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": raw_headers,
            "client": ("127.0.0.1", 12345),
        }
    )


def test_upsert_user_first_user_becomes_admin(db_session, monkeypatch):
    monkeypatch.setattr(user_service, "ADMIN_USERNAMES", set())
    user = user_service.upsert_user(
        db_session,
        {"id": 111, "login": "first_dev", "email": "first@example.com", "avatar_url": None},
    )
    assert user.role == "admin"
    assert user.username == "first_dev"


def test_upsert_user_second_user_becomes_analyst(db_session, monkeypatch):
    monkeypatch.setattr(user_service, "ADMIN_USERNAMES", set())
    user_service.upsert_user(db_session, {"id": 111, "login": "first_dev"})
    second = user_service.upsert_user(db_session, {"id": 222, "login": "second_dev"})
    assert second.role == "analyst"


def test_upsert_user_updates_existing_without_downgrade(db_session, monkeypatch):
    monkeypatch.setattr(user_service, "ADMIN_USERNAMES", set())
    first = user_service.upsert_user(
        db_session, {"id": 111, "login": "old_name", "email": "old@example.com"}
    )
    assert first.role == "admin"

    updated = user_service.upsert_user(
        db_session, {"id": 111, "login": "new_name", "email": "new@example.com"}
    )
    assert updated.id == first.id
    assert updated.username == "new_name"
    assert updated.email == "new@example.com"
    assert updated.role == "admin"


def test_upsert_user_promotes_whitelisted_admin_username(db_session, monkeypatch):
    monkeypatch.setattr(user_service, "ADMIN_USERNAMES", {"boss_user"})
    user_service.upsert_user(db_session, {"id": 111, "login": "initial_admin"})
    promoted = user_service.upsert_user(db_session, {"id": 222, "login": "Boss_User"})
    assert promoted.role == "admin"


def test_create_and_decode_access_token():
    uid = uuid4()
    token = create_access_token(uid)
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["type"] == "access"


def test_create_refresh_token_stores_sha256_hash(db_session, analyst_user):
    raw_token = create_refresh_token(db_session, analyst_user.id)
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    stored = db_session.query(RefreshToken).filter(RefreshToken.token_hash == expected_hash).first()
    assert stored is not None
    assert stored.user_id == analyst_user.id
    assert stored.revoked is False


def test_custom_content_builds_minimal_and_full_payloads():
    minimal = custom_content("error", message="Failed")
    assert minimal == {"status": "error", "message": "Failed"}

    full = custom_content(
        "success",
        data={"id": "1"},
        message="OK",
        count=1,
        page=1,
        limit=10,
        total=5,
    )
    assert full == {
        "status": "success",
        "message": "OK",
        "count": 1,
        "page": 1,
        "limit": 10,
        "total": 5,
        "data": {"id": "1"},
    }


def test_get_current_user_rejects_missing_token(db_session):
    request = make_http_request()
    with pytest.raises(HTTPException) as exc:
        get_current_user(request, db_session)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


def test_get_current_user_rejects_invalid_or_wrong_type_token(db_session, analyst_user):
    bad_type_token = jwt.encode(
        {
            "sub": str(analyst_user.id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "type": "refresh",
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    request = make_http_request(headers={"Authorization": f"Bearer {bad_type_token}"})
    with pytest.raises(HTTPException) as exc:
        get_current_user(request, db_session)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


def test_get_current_user_rejects_inactive_user(db_session):
    inactive = User(
        github_id="9999",
        username="disabled_user",
        role="analyst",
        is_active=False,
    )
    db_session.add(inactive)
    db_session.commit()
    db_session.refresh(inactive)

    token = create_access_token(inactive.id)
    request = make_http_request(headers={"Authorization": f"Bearer {token}"})
    with pytest.raises(HTTPException) as exc:
        get_current_user(request, db_session)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Access denied"


def test_get_current_user_accepts_cookie_access_token(db_session, analyst_user):
    token = create_access_token(analyst_user.id)
    request = make_http_request(cookies={"access_token": token})
    current = get_current_user(request, db_session)
    assert current.id == analyst_user.id
