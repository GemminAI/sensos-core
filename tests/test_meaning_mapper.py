import pytest

from sensos_core.meaning_mapper import ResolvedMeaningObject, resolve_scalar_unit

RESERVED_KEYS = {"schema", "raw_input", "resolved_meaning", "action", "title", "tags", "ext"}


def test_resolve_scalar_unit_matches_spec_example():
    result = resolve_scalar_unit("100")
    assert result.resolved_meaning == "100 Fahrenheit"
    assert result.action == "unit_conversion_fahrenheit"
    assert "CUMR001" in result.tags


def test_payload_has_exactly_the_seven_reserved_keys():
    """HEKB v3's ExperiencePayload (hekb-vnext/store_service.py) rejects any
    top-level key outside this set — MeaningMapper's output must match it
    exactly, not a superset or subset."""
    payload = resolve_scalar_unit("100").to_hekb_payload()
    assert set(payload.keys()) == RESERVED_KEYS


def test_payload_is_hekb_post_experience_compatible_shape():
    """Simulates what hekb-vnext's ExperiencePayload(**payload) construction
    checks, without importing hekb-vnext itself (a separate repo/process):
    every reserved key present, correct static types, and no trie_address
    anywhere (Trie-layer-omitted, No-Go-safe design)."""
    payload = resolve_scalar_unit("100").to_hekb_payload()

    assert isinstance(payload["schema"], str) and payload["schema"] == "hekb.experience/1"
    assert isinstance(payload["raw_input"], str)
    assert isinstance(payload["resolved_meaning"], str)
    assert payload["action"] is None or isinstance(payload["action"], str)
    assert payload["title"] is None or isinstance(payload["title"], str)
    assert isinstance(payload["tags"], list) and all(isinstance(t, str) for t in payload["tags"])
    assert isinstance(payload["ext"], dict)
    assert "trie_address" not in payload["ext"]


def test_ext_carries_confidence_and_candidate_domain_not_reserved_keys():
    payload = resolve_scalar_unit("100").to_hekb_payload()
    assert "confidence_score" in payload["ext"]
    assert "candidate_domain" in payload["ext"]
    assert 0.0 <= payload["ext"]["confidence_score"] <= 1.0


def test_body_temperature_range_favors_fahrenheit():
    # 98 is close to human body temperature in Fahrenheit; the heuristic
    # should favor that reading over Celsius (98 C would be near-boiling).
    result = resolve_scalar_unit("98")
    assert result.action == "unit_conversion_fahrenheit"


def test_freezing_range_favors_celsius():
    # 0 is a very ordinary Celsius reading (freezing point of water) and an
    # implausible Fahrenheit one in casual conversation.
    result = resolve_scalar_unit("0")
    assert result.action == "unit_conversion_celsius"


def test_non_numeric_raw_input_raises():
    with pytest.raises(ValueError):
        resolve_scalar_unit("not a number")


def test_resolved_meaning_object_payload_is_json_serializable():
    import json

    payload = resolve_scalar_unit("100").to_hekb_payload()
    json.dumps(payload)  # must not raise


def test_resolved_meaning_object_is_immutable():
    obj = ResolvedMeaningObject(raw_input="1", resolved_meaning="1 Fahrenheit", action=None, title=None)
    with pytest.raises(Exception):
        obj.raw_input = "2"  # frozen dataclass must reject mutation
