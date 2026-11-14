from unittest.mock import AsyncMock, patch

from models.profile import Profile
from tests.conftest import auth_headers


def test_create_profile_and_prevent_duplicate(client, admin_user):
    mocked_external = {
        "error": False,
        "data": {
            "genderize": {"gender": "female", "probability": 0.97},
            "agify": {"age": 29},
            "nationalize": {
                "country": [
                    {"country_id": "NG", "probability": 0.88},
                    {"country_id": "GH", "probability": 0.12},
                ]
            },
        },
    }

    with patch(
        "routes.profile.all_external_data", new=AsyncMock(return_value=mocked_external)
    ):
        res = client.post(
            "/api/profiles",
            json={"name": "Chidinma"},
            headers=auth_headers(admin_user),
        )
        assert res.status_code == 201
        body = res.json()
        assert body["status"] == "success"
        assert body["data"]["name"] == "Chidinma"
        assert body["data"]["country_id"] == "NG"
        assert body["data"]["age_group"] == "adult"

        # Submitting the same name again (case-insensitive) returns 200 without duplicating
        dup_res = client.post(
            "/api/profiles",
            json={"name": "chidinma"},
            headers=auth_headers(admin_user),
        )
        assert dup_res.status_code == 200
        assert dup_res.json()["message"] == "Profile already exists"


def test_analyst_cannot_create_or_delete_profile(client, analyst_user, db_session):
    profile = Profile(
        name="Tunde",
        gender="male",
        gender_probability=0.95,
        age=34,
        age_group="adult",
        country_id="NG",
        country_name="Nigeria",
        country_probability=0.91,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    create_res = client.post(
        "/api/profiles",
        json={"name": "Bola"},
        headers=auth_headers(analyst_user),
    )
    assert create_res.status_code == 403

    delete_res = client.delete(
        f"/api/profiles/{profile.id}",
        headers=auth_headers(analyst_user),
    )
    assert delete_res.status_code == 403


def test_list_search_export_and_delete_profiles(client, admin_user, analyst_user, db_session):
    p1 = Profile(
        name="John",
        gender="male",
        gender_probability=0.99,
        age=22,
        age_group="adult",
        country_id="NG",
        country_name="Nigeria",
        country_probability=0.85,
    )
    p2 = Profile(
        name="Anna",
        gender="female",
        gender_probability=0.96,
        age=17,
        age_group="teenager",
        country_id="US",
        country_name="United States",
        country_probability=0.90,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    # 1. List with filters
    list_res = client.get(
        "/api/profiles?gender=male&country_id=NG",
        headers=auth_headers(analyst_user),
    )
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1
    assert list_res.json()["data"][0]["name"] == "John"

    # 2. NLP Search endpoint
    search_res = client.get(
        "/api/profiles/search?q=female+teenagers+from+usa",
        headers=auth_headers(analyst_user),
    )
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert search_res.json()["data"][0]["name"] == "Anna"

    # 3. Export CSV endpoint
    export_res = client.get(
        "/api/profiles/export?format=csv&country_id=NG",
        headers=auth_headers(analyst_user),
    )
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert "John" in export_res.text

    # 4. Admin delete endpoint
    del_res = client.delete(
        f"/api/profiles/{p1.id}",
        headers=auth_headers(admin_user),
    )
    assert del_res.status_code == 204


def test_api_key_creation_and_authentication(client, analyst_user):
    # Create an API key using JWT bearer token
    key_res = client.post("/auth/api-keys", headers=auth_headers(analyst_user))
    assert key_res.status_code == 200
    raw_api_key = key_res.json()["api_key"]
    assert raw_api_key.startswith("sk_live_")

    # Authenticate to /api/users/me using the generated sk_live_ API key
    me_res = client.get(
        "/api/users/me",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "X-API-Version": "1",
        },
    )
    assert me_res.status_code == 200
    assert me_res.json()["data"]["username"] == "analyst_tester"
