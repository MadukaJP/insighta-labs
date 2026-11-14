import pytest

from core.nlp.profile_filter_detector import (
    detect_age_groups,
    detect_age_ranges,
    detect_countries,
    detect_gender_terms,
    detect_names,
    detect_profile_filters,
)


def test_detect_gender_terms_normalizes_and_deduplicates():
    assert detect_gender_terms("young men and boys") == ["male"]
    assert detect_gender_terms("female and women") == ["female"]
    assert detect_gender_terms("males and females") == ["male", "female"]
    assert detect_gender_terms("people from nigeria") == []


def test_detect_age_groups():
    assert detect_age_groups("kids and toddlers") == ["child"]
    assert detect_age_groups("teenagers and adults") == ["teenager", "adult"]
    assert detect_age_groups("elderly seniors") == ["senior"]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("between 20 and 35", (20, 35)),
        ("above 30", (30, None)),
        ("older than 45", (45, None)),
        ("under 18", (None, 18)),
        ("younger than 25", (None, 25)),
        ("young adults", (20, 35)),
        ("young males", (16, 24)),
        ("middle-aged women", (36, 55)),
        ("age 42", (42, 42)),
        ("all profiles", (None, None)),
    ],
)
def test_detect_age_ranges(query, expected):
    assert detect_age_ranges(query) == expected


def test_detect_countries_supports_names_aliases_and_fuzzy_matches():
    assert detect_countries("people from Nigeria") == ["NG"]
    assert detect_countries("users in usa and uk") == ["US", "GB"]
    # Fuzzy match for slight misspelling ("Nigeri" -> "NG")
    assert detect_countries("teenagers from Nigeri") == ["NG"]
    assert detect_countries("no country mentioned here") is None


def test_detect_names_explicit_and_bare():
    assert detect_names("males named John and Anna") == ["John", "Anna"]
    assert detect_names("people called Mary Jane from Kenya") == ["Mary Jane"]
    assert detect_names("john") == ["John"]
    assert detect_names("john, anna") == ["John", "Anna"]
    # Denylist / context words should not be treated as bare names
    assert detect_names("profiles") is None
    assert detect_names("males") is None


def test_detect_profile_filters_combined_query():
    result = detect_profile_filters(
        "male and female teenagers above 17 from Nigeria and USA named John and Anna"
    )
    assert result["genders"] == ["male", "female"]
    assert result["age_group"] == ["teenager"]
    assert result["age_range"] == (17, None)
    assert "NG" in result["countries"]
    assert "US" in result["countries"]
    assert result["names"] == ["John", "Anna"]
