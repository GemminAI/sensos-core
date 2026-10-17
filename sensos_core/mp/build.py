"""Build and seal HEXT v2 documents that carry MP profile payloads.

Needs the HEXT v2 reference implementation (``hext2``) importable; its location is the caller's business
(tests use the ``HEXT_V2_PATH`` environment variable). Imported lazily so the rest of the package does not
depend on it.
"""

from __future__ import annotations

from typing import Any

import rfc8785

from sensos_core.mp.profile import PROFILES

_ROLE = {"message": "sender", "readback": "reader", "alignment": "aligner"}


def _actor(payload: dict[str, Any]) -> str:
    if "from" in payload:
        return str(payload["from"])
    if "reader" in payload:
        return str(payload["reader"])
    return str(payload["aligner"]["ref"])


def build_document(
    payload: dict[str, Any],
    *,
    object_id: str,
    sealed_at: str,
    observed_at: dict[str, str] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Return (SealedDocument, document dict). ``sealed_at`` is an input; the clock is never read."""
    from hext2.create import empty_time, new_source
    from hext2.seal import seal

    profile = payload["profile"]
    kind = PROFILES[profile][0]
    actor = _actor(payload)
    human = actor.startswith("human:")
    aligner_rule = payload.get("aligner", {}).get("kind") == "rule"
    doc = new_source(
        object_id=object_id,
        object_type=profile,
        evidence=[{"evidence_id": "mp", "format": profile, "body": rfc8785.dumps(payload).decode("utf-8")}],
        contributors=[{"agent": actor, "role": _ROLE[profile.split(".")[2].split("/")[0]]}],
        primary_generator="human" if human else "ai",
        human_touch="1.0" if human else "0.0",
        ledger=[{"t": sealed_at, "type": "HUMAN" if human else ("SYSTEM" if aligner_rule else "AI"), "actor": actor, "delta": 0}],
        sealed_at=sealed_at,
        time=empty_time(observed_at=observed_at),
    )
    if kind == "annotation":
        doc["kind"] = "annotation"
        refs = [payload["target"]] + ([payload["readback"]] if "readback" in payload else [])
        doc["provenance"]["derived_from"] = [{"id": r["id"], "state_hash": r["state_hash"]} for r in refs]
    return seal(doc), doc
