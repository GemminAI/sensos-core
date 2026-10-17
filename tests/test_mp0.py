"""MP0: profile schemas and test vectors. HEXT-dependent tests skip unless HEXT_V2_PATH points at a
GemminAI/hext checkout containing reference/python/hext2."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from sensos_core.mp import (
    MPError,
    check_envelope,
    check_references,
    find_floats,
    loads_strict,
    validate_payload,
)

jsonschema = pytest.importorskip("jsonschema")

VECTORS = Path(__file__).resolve().parent.parent / "sensos_core" / "mp" / "testvectors"
MANIFEST = json.loads((VECTORS / "manifest.json").read_text(encoding="utf-8"))
_HEXT = os.environ.get("HEXT_V2_PATH")
_HEXT_PY = Path(_HEXT) / "reference" / "python" if _HEXT else None
needs_hext = pytest.mark.skipif(
    _HEXT_PY is None or not (_HEXT_PY / "hext2").is_dir(),
    reason="HEXT_V2_PATH not set (or no reference/python/hext2 under it); HEXT v2 level-2 checks skipped",
)

VALID = [v["name"] for v in MANIFEST["valid"]]
INVALID = MANIFEST["invalid"]


def _payload(name: str) -> dict[str, Any]:
    p = loads_strict((VECTORS / "valid" / f"{name}.json").read_text(encoding="utf-8"))
    assert isinstance(p, dict)
    return p


def _hext() -> None:
    assert _HEXT_PY is not None
    if str(_HEXT_PY) not in sys.path:
        sys.path.insert(0, str(_HEXT_PY))


@pytest.mark.parametrize("name", VALID)
def test_valid_payload_passes_own_schema(name: str) -> None:
    p = _payload(name)
    assert validate_payload(p) == p["profile"]
    check_references(p)
    assert find_floats(p) == []


@pytest.mark.parametrize("case", INVALID, ids=[c["name"] for c in INVALID])
def test_invalid_payload_fails_for_intended_reason(case: dict[str, str]) -> None:
    text = (VECTORS / "invalid" / f"{case['name']}.json").read_text(encoding="utf-8")
    with pytest.raises(MPError) as ei:
        payload = loads_strict(text)
        validate_payload(payload)
        check_references(payload)
    assert ei.value.layer == case["layer"]
    assert case["expect"] in (ei.value.code, ei.value.detail)


def test_negative_coverage_of_required_reasons() -> None:
    names = {c["name"] for c in INVALID}
    assert {"message-float-uncertainty", "message-purpose-empty", "message-uncertainty-1001",
            "readback-target-missing", "alignment-status-unknown"} <= names


def test_loads_strict_rejects_duplicate_keys_and_nan() -> None:
    for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e3}'):
        with pytest.raises(MPError):
            loads_strict(text)


@needs_hext
@pytest.mark.parametrize("name", VALID)
def test_sealed_vector_reaches_hext_level_2(name: str) -> None:
    _hext()
    from hext2.verify import verify

    entry = next(v for v in MANIFEST["valid"] if v["name"] == name)
    raw = (VECTORS / "sealed" / f"{name}.hext2.json").read_bytes()
    known = {v["object_id"]: v["state_hash"] for v in MANIFEST["valid"]}
    res = verify(raw, known_sources=known, level=2)
    assert res.level == 2 and res.state_hash == entry["state_hash"] and res.canonical_bytes
    doc = loads_strict(raw.decode("utf-8").rstrip("\n"))
    payload = check_envelope(doc)
    assert payload == _payload(name)
    assert find_floats(doc) == [] and find_floats(payload) == []


@needs_hext
@pytest.mark.parametrize("name", VALID)
def test_rebuild_matches_golden(name: str) -> None:
    _hext()
    from sensos_core.mp.build import build_document

    entry = next(v for v in MANIFEST["valid"] if v["name"] == name)
    sealed, _ = build_document(_payload(name), object_id=entry["object_id"], sealed_at=entry["sealed_at"],
                               observed_at=entry["observed_at"])
    assert sealed.state_hash == entry["state_hash"]
    assert sealed.canonical_bytes + b"\n" == (VECTORS / "sealed" / f"{name}.hext2.json").read_bytes()


@needs_hext
def test_envelope_rejects_wrong_derived_from() -> None:
    _hext()
    from sensos_core.mp.build import build_document

    entry = next(v for v in MANIFEST["valid"] if v["name"] == "mp0-readback-01")
    _, doc = build_document(_payload(entry["name"]), object_id="x", sealed_at=entry["sealed_at"])
    doc["provenance"]["derived_from"] = []
    with pytest.raises(MPError) as ei:
        check_envelope(doc)
    assert ei.value.code == "derived_from"


_CHILD = """
import json, sys
sys.path.insert(0, {hext!r})
from sensos_core.mp.build import build_document
from sensos_core.mp import loads_strict
m = json.load(open({manifest!r}))
out = {{}}
for v in m['valid']:
    p = loads_strict(open({vec!r} + '/valid/' + v['name'] + '.json').read())
    out[v['name']] = build_document(p, object_id=v['object_id'], sealed_at=v['sealed_at'], observed_at=v['observed_at'])[0].state_hash
print(json.dumps(out, sort_keys=True))
"""


@needs_hext
def test_two_fresh_processes_seal_to_same_state_hash() -> None:
    assert _HEXT_PY is not None
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}  # hash randomisation stays on
    code = _CHILD.format(hext=str(_HEXT_PY), manifest=str(VECTORS / "manifest.json"), vec=str(VECTORS))
    runs = [subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True).stdout
            for _ in range(2)]
    assert runs[0] == runs[1]
    assert json.loads(runs[0]) == {v["name"]: v["state_hash"] for v in MANIFEST["valid"]}
