from copy import deepcopy

import pytest

from apps.api.app.transformation.profile_registry import (
    create_custom_profile,
    get_profile,
    list_profiles,
    validate_profile,
)


def test_all_builtin_profiles_are_valid():
    profiles = list_profiles()
    assert {item["profile_id"] for item in profiles} == {
        "general_llm", "coding", "research", "retrieval"
    }
    assert all(validate_profile(item)["valid"] for item in profiles)


@pytest.mark.parametrize(
    "profile_id",
    ["general_llm", "coding", "research", "retrieval"],
)
def test_builtin_profile_lookup(profile_id):
    profile = get_profile(profile_id)
    assert profile["profile_id"] == profile_id
    assert profile["custom"] is False


def test_profile_lookup_returns_independent_copy():
    profile = get_profile("coding")
    profile["required_fields"].append("corrupted")
    assert "corrupted" not in get_profile("coding")["required_fields"]


def test_unknown_profile_raises():
    with pytest.raises(KeyError):
        get_profile("unknown")


def test_invalid_quality_threshold_is_rejected():
    profile = get_profile("general_llm")
    profile["quality_threshold"] = 1.5
    assert not validate_profile(profile)["valid"]


def test_unknown_fields_are_rejected():
    profile = get_profile("general_llm")
    profile["execute_python"] = True
    assert not validate_profile(profile)["valid"]


def test_required_and_optional_field_overlap_is_rejected():
    profile = get_profile("general_llm")
    profile["optional_fields"].append("instruction")
    assert not validate_profile(profile)["valid"]


def test_invalid_chunking_overlap_is_rejected():
    profile = get_profile("research")
    profile["chunking"]["overlap_tokens"] = profile["chunking"]["max_tokens"]
    assert not validate_profile(profile)["valid"]


def test_custom_profile_is_validated_and_marked_custom():
    profile = get_profile("general_llm")
    profile["profile_id"] = "my_custom_profile"
    profile["name"] = "My Custom Profile"

    result = create_custom_profile(profile)

    assert result["custom"] is True
    assert result["profile_id"] == "my_custom_profile"


def test_custom_profile_cannot_overwrite_builtin():
    profile = get_profile("coding")
    with pytest.raises(ValueError):
        create_custom_profile(profile)


def test_custom_profile_does_not_mutate_input():
    profile = get_profile("general_llm")
    profile["profile_id"] = "independent_profile"
    original = deepcopy(profile)

    create_custom_profile(profile)

    assert profile == original


def test_provenance_warning_is_reported():
    profile = get_profile("general_llm")
    profile["preserve_provenance"] = False

    result = validate_profile(profile)

    assert result["valid"] is True
    assert result["warnings"]
