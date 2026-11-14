import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from models.profile import Profile
from models.refresh_token import RefreshToken
from tests.conftest import auth_headers
from utils.tokens import create_refresh_token


def test_health_check_returns_welcome_message(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json() == {"status": "success", "message": "Welcome to Instalabs API"}


def test_refresh_token_rotation_success_and_reuse_rejected(client, db_session, analyst_user):
    raw_refresh = create_refresh_token(db_session, analyst_user.id)

    res = client.post("/auth/refresh", json={"refresh_token": raw_refresh})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["refresh_token"] != raw_refresh

    # Reusing the revoked refresh token must fail
    reuse_res = client.post("/auth/refresh", json={"refresh_token": raw_refresh})
    assert reuse_res.status_code == 401


def test_refresh_token_expired_rejected(client, db_session, analyst_user):
    raw_refresh = "expired-refresh-token"
    expired = RefreshToken(
        user_id=analyst_user.id,
        token_hash=hashlib.sha256(raw_refresh.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        revoked=False,
    )
    db_session.add(expired)
    db_session.commit()

    res = client.post("/auth/refresh", json={"refresh_token": raw_refresh})
    assert res.status_code == 401


def test_refresh_token_missing_returns_401(client):
    res = client.post("/auth/refresh")
    assert res.status_code == 401


def test_logout_revokes_refresh_token_and_clears_cookies(client, db_session, analyst_user):
    raw_refresh = create_refresh_token(db_session, analyst_user.id)
    token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()

    res = client.post("/auth/logout", json={"refresh_token": raw_refresh})
    assert res.status_code == 200
    assert res.json() == {"status": "success"}

    stored = db_session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    assert stored.revoked is True


def test_csrf_token_endpoint_requires_admin_and_sets_cookie(client, admin_user, analyst_user):
    analyst_res = client.get("/auth/csrf-token", headers=auth_headers(analyst_user))
    assert analyst_res.status_code == 403

    admin_res = client.get("/auth/csrf-token", headers=auth_headers(admin_user))
    assert admin_res.status_code == 200
    token = admin_res.json()["data"]["csrf_token"]
    assert token
    assert admin_res.cookies.get("csrf_token") == token


def test_auth_me_and_api_users_me_return_user_info(client, analyst_user):
    headers = auth_headers(analyst_user)

    auth_me_res = client.get("/auth/me", headers=headers)
    assert auth_me_res.status_code == 200
    assert auth_me_res.json()["data"]["username"] == "analyst_tester"

    api_me_res = client.get("/api/users/me", headers=headers)
    assert api_me_res.status_code == 200
    assert api_me_res.json()["data"]["role"] == "analyst"


def test_create_profile_rejects_empty_and_invalid_names(client, admin_user):
    headers = auth_headers(admin_user)

    empty_res = client.post("/api/profiles", json={"name": "   "}, headers=headers)
    assert empty_res.status_code == 400

    invalid_res = client.post("/api/profiles", json={"name": "John123!"}, headers=headers)
    assert invalid_res.status_code == 422


def test_create_profile_handles_upstream_failures(client, admin_user):
    headers = auth_headers(admin_user)

    # Upstream returned error flag
    with patch(
        "routes.profile.all_external_data",
        new=AsyncMock(return_value={"error": True, "message": "Agify failed"}),
    ):
        err_res = client.post("/api/profiles", json={"name": "Maya"}, headers=headers)
        assert err_res.status_code == 502

    # Upstream returned null gender
    with patch(
        "routes.profile.all_external_data",
        new=AsyncMock(
            return_value={
                "error": False,
                "data": {
                    "genderize": {"gender": None, "probability": 0},
                    "agify": {"age": 25},
                    "nationalize": {"country": [{"country_id": "US", "probability": 0.9}]},
                },
            }
        ),
    ):
        null_gender_res = client.post("/api/profiles", json={"name": "Zed"}, headers=headers)
        assert null_gender_res.status_code == 502


def test_get_profile_by_id_success_not_found_and_invalid_uuid(client, analyst_user, db_session):
    profile = Profile(
        name="Ngozi",
        gender="female",
        gender_probability=0.98,
        age=31,
        age_group="adult",
        country_id="NG",
        country_name="Nigeria",
        country_probability=0.92,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    headers = auth_headers(analyst_user)

    ok_res = client.get(f"/api/profiles/{profile.id}", headers=headers)
    assert ok_res.status_code == 200
    assert ok_res.json()["data"]["name"] == "Ngozi"

    not_found_res = client.get(f"/api/profiles/{uuid4()}", headers=headers)
    assert not_found_res.status_code == 404

    invalid_res = client.get("/api/profiles/not-a-uuid", headers=headers)
    assert invalid_res.status_code == 400


def test_list_profiles_validation_and_sorting_pagination(client, analyst_user, db_session):
    p1 = Profile(
        name="Ayo",
        gender="male",
        gender_probability=0.9,
        age=40,
        age_group="adult",
        country_id="NG",
        country_name="Nigeria",
        country_probability=0.8,
    )
    p2 = Profile(
        name="Bisi",
        gender="female",
        gender_probability=0.95,
        age=22,
        age_group="adult",
        country_id="NG",
        country_name="Nigeria",
        country_probability=0.85,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    headers = auth_headers(analyst_user)

    bad_sort = client.get("/api/profiles?sort_by=invalid_col", headers=headers)
    assert bad_sort.status_code == 400

    bad_gender = client.get("/api/profiles?gender=other", headers=headers)
    assert bad_gender.status_code == 400

    sorted_res = client.get(
        "/api/profiles?sort_by=age&order=asc&page=1&limit=1", headers=headers
    )
    assert sorted_res.status_code == 200
    body = sorted_res.json()
    assert body["total"] == 2
    assert body["total_pages"] == 2
    assert body["data"][0]["name"] == "Bisi"
    assert body["links"]["next"] is not None


def test_search_profiles_validation_and_uninterpretable_query(client, analyst_user):
    headers = auth_headers(analyst_user)

    empty_res = client.get("/api/profiles/search?q=+", headers=headers)
    assert empty_res.status_code == 400

    uninterpretable_res = client.get("/api/profiles/search?q=!!!", headers=headers)
    assert uninterpretable_res.status_code == 400
    assert uninterpretable_res.json()["message"] == "Unable to interpret query"


def test_export_profiles_rejects_unsupported_format(client, analyst_user):
    res = client.get("/api/profiles/export?format=json", headers=auth_headers(analyst_user))
    assert res.status_code == 400
    assert res.json()["message"] == "Invalid query parameters"
