import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.api_version import APIVersionMiddleware
from models.profile import Profile
from utils.api_key import generate_api_key, hash_api_key, verify_api_key
from utils.country_utils import get_country_name_from_id
from utils.get_age_group import get_age_group


def make_versioned_app():
    app = FastAPI()
    app.add_middleware(APIVersionMiddleware)

    @app.get("/api/test")
    def api_endpoint():
        return {"status": "success"}

    @app.get("/health")
    def health_endpoint():
        return {"status": "ok"}

    return app


def test_api_version_middleware_enforces_header_on_api_routes():
    client = TestClient(make_versioned_app())

    # Missing header on /api/* returns 400
    res_missing = client.get("/api/test")
    assert res_missing.status_code == 400
    assert res_missing.json() == {
        "status": "error",
        "message": "API version header required",
    }

    # Unsupported version returns 400
    res_invalid = client.get("/api/test", headers={"X-API-Version": "2"})
    assert res_invalid.status_code == 400
    assert res_invalid.json() == {
        "status": "error",
        "message": "Unsupported API version",
    }

    # Valid version 1 succeeds
    res_valid = client.get("/api/test", headers={"X-API-Version": "1"})
    assert res_valid.status_code == 200
    assert res_valid.json() == {"status": "success"}

    # Non-/api/ routes bypass version header requirement
    res_health = client.get("/health")
    assert res_health.status_code == 200


@pytest.mark.parametrize(
    "age,expected_group",
    [
        (0, "child"),
        (12, "child"),
        (13, "teenager"),
        (19, "teenager"),
        (20, "adult"),
        (59, "adult"),
        (60, "senior"),
        (85, "senior"),
    ],
)
def test_get_age_group_boundaries(age, expected_group):
    assert get_age_group(age) == expected_group


def test_get_country_name_from_id():
    assert get_country_name_from_id("NG") == "Nigeria"
    assert get_country_name_from_id("us") == "United States"
    assert get_country_name_from_id("ZZ") is None
    assert get_country_name_from_id("") is None


def test_api_key_generation_and_verification():
    raw_key = generate_api_key()
    assert raw_key.startswith("sk_live_")
    hashed = hash_api_key(raw_key)
    assert hashed != raw_key
    assert verify_api_key(raw_key, hashed) is True
    assert verify_api_key("sk_live_wrong", hashed) is False


def test_profile_model_validators():
    profile = Profile(
        name="Ada",
        gender="FEMALE",
        gender_probability=0.98,
        age=28,
        age_group="ADULT",
        country_id="ng",
        country_probability=0.85,
    )
    assert profile.gender == "female"
    assert profile.age_group == "adult"
    assert profile.country_id == "NG"
    assert profile.country_name == "Nigeria"

    with pytest.raises(ValueError, match="Gender must be"):
        Profile(
            name="InvalidGender",
            gender="unknown",
            gender_probability=0.5,
            age=25,
            age_group="adult",
            country_id="NG",
            country_probability=0.5,
        )

    with pytest.raises(ValueError, match="Age group must be"):
        Profile(
            name="InvalidAgeGroup",
            gender="male",
            gender_probability=0.5,
            age=25,
            age_group="infant",
            country_id="NG",
            country_probability=0.5,
        )
