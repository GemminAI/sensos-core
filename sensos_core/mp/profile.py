"""Profile payload handling: strict loading, schema validation, envelope and reference checks.

Stdlib + ``rfc8785`` only; ``jsonschema`` is imported lazily by :func:`validate_payload`.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

import rfc8785

# profile id -> (HEXT kind, schema file)
PROFILES: dict[str, tuple[str, str]] = {
    "sensos.mp.message/0.1": ("source", "message.schema.json"),
    "sensos.mp.readback/0.1": ("annotation", "readback.schema.json"),
    "sensos.mp.alignment/0.1": ("annotation", "alignment.schema.json"),
}


class MPError(Exception):
    """A profile check failed. ``layer`` is one of strict, schema, envelope, semantic."""

    def __init__(self, layer: str, code: str, detail: str = "") -> None:
        super().__init__(f"{layer}:{code} {detail}".strip())
        self.layer = layer
        self.code = code
        self.detail = detail


def load_schema(profile: str) -> dict[str, Any]:
    name = PROFILES[profile][1]
    text = resources.files("sensos_core.mp").joinpath("schemas", name).read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


def _no_float(token: str) -> Any:
    raise MPError("strict", "float", token)


def _no_const(token: str) -> Any:
    raise MPError("strict", "nonfinite", token)


def _no_dup(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise MPError("strict", "duplicate_key", k)
        out[k] = v
    return out


def loads_strict(text: str) -> Any:
    """Parse JSON refusing floats (any ``.``/exponent number, including ``1.0``), NaN/Infinity, duplicate keys."""
    try:
        return json.loads(text, parse_float=_no_float, parse_constant=_no_const, object_pairs_hook=_no_dup)
    except json.JSONDecodeError as exc:
        raise MPError("strict", "json", str(exc)) from exc


def find_floats(value: Any, path: str = "") -> list[str]:
    """Paths of every float in an already-parsed value (the sealed content must have none, D-72)."""
    if isinstance(value, float):
        return [path or "/"]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in find_floats(v, f"{path}/{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in find_floats(v, f"{path}/{i}")]
    return []


def validate_payload(payload: Any) -> str:
    """Validate a payload against the schema of its declared profile. Returns the profile id."""
    from jsonschema import Draft202012Validator

    profile = payload.get("profile") if isinstance(payload, dict) else None
    if profile not in PROFILES:
        raise MPError("schema", "profile", repr(profile))
    errors = sorted(Draft202012Validator(load_schema(profile)).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        raise MPError("schema", str(e.validator), "/".join(str(p) for p in e.absolute_path))
    return str(profile)


def check_references(payload: dict[str, Any]) -> None:
    """Cross-field rules JSON Schema cannot state (message payloads only)."""
    if payload.get("profile") != "sensos.mp.message/0.1":
        return
    ids = [x["id"] for key in ("claims", "premises") for x in payload.get(key, [])]
    if len(ids) != len(set(ids)):
        raise MPError("semantic", "duplicate_id")
    for u in payload.get("uncertainty", []):
        if u["ref"] not in ids:
            raise MPError("semantic", "dangling_uncertainty_ref", u["ref"])


def _ref_key(r: dict[str, str]) -> tuple[str, str]:
    return (r["id"], r["state_hash"])


def check_envelope(doc: dict[str, Any]) -> dict[str, Any]:
    """Check how a parsed HEXT v2 document carries an MP profile; return the parsed payload."""
    obj_type = doc["object"]["type"]
    if obj_type not in PROFILES:
        raise MPError("envelope", "object_type", obj_type)
    kind = PROFILES[obj_type][0]
    if doc["kind"] != kind:
        raise MPError("envelope", "kind", f"{obj_type} needs {kind}")
    items = [e for e in doc["evidence"] if e["format"] == obj_type]
    if len(items) != 1 or "body" not in items[0]:
        raise MPError("envelope", "evidence", "exactly one inline evidence item with the profile format")
    body = items[0]["body"]
    payload = loads_strict(body)
    if rfc8785.dumps(payload).decode("utf-8") != body:
        raise MPError("envelope", "body_not_canonical")
    if validate_payload(payload) != obj_type:
        raise MPError("envelope", "profile_mismatch")
    check_references(payload)
    derived = sorted(_ref_key(r) for r in doc["provenance"]["derived_from"])
    if obj_type.endswith("message/0.1"):
        want: list[tuple[str, str]] = []
    elif obj_type.endswith("readback/0.1"):
        want = [_ref_key(payload["target"])]
    else:
        want = [_ref_key(payload["target"]), _ref_key(payload["readback"])]
    if derived != sorted(want):
        raise MPError("envelope", "derived_from", "must equal the payload's target/readback refs")
    return payload
