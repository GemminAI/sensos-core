"""MeaningMapper — ambiguity resolution engine (SPEC-MM-001_v2).

Per SPEC-MM-001_v2 §2.0, step 1 (type-level Trie address reduction) is a
performance-optimization layer conditional on the geometry hypothesis's
Go/No-Go, never a correctness prerequisite. Phase 0-D
(experiments/EXP-PHASE0D-GEOMETRY) found that hypothesis CONDITIONAL GO,
not an unconditional Go, so this module implements step 2 (the CUMR
Resolver) standalone and never emits `ext.trie_address` — per §2.0's own
"No-Go" instruction, omitting that key changes nothing about the reserved
schema, so the same `ResolvedMeaningObject` shape works whether or not a
Trie layer is ever added later.

`resolve_scalar_unit` is a MINIMAL heuristic disambiguator (CUMR001: bare
numeric scalar -> most plausible physical-unit reading), not a trained
model — it exists to produce a real, non-stub `ResolvedMeaningObject`
end to end, matching SPEC-MM-001_v2 §3.1's own worked example
("100" -> "100 Fahrenheit"). A production-quality resolver is out of
scope here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "hekb.experience/1"


@dataclass(frozen=True)
class ResolvedMeaningObject:
    """SPEC-MM-001_v2 §3.1 / SPEC-HEKB-003_v2 §2.1 layer-1 payload. The
    seven reserved keys only — anything MeaningMapper-specific
    (`candidate_domain`, `confidence_score`, ...) belongs in `ext`, which
    is opaque and unindexed on the HEKB side."""

    raw_input: Any
    resolved_meaning: Any
    action: str | None
    title: str | None
    tags: list[str] = field(default_factory=list)
    ext: dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA

    def to_hekb_payload(self) -> dict[str, Any]:
        """The exact reserved-key dict `POST /experience`'s `payload` field
        expects (SPEC-HEKB-003_v2 §2.1) — safe to send as-is."""
        return {
            "schema": self.schema,
            "raw_input": self.raw_input,
            "resolved_meaning": self.resolved_meaning,
            "action": self.action,
            "title": self.title,
            "tags": list(self.tags),
            "ext": dict(self.ext),
        }


@dataclass(frozen=True)
class ScalarUnitCandidate:
    unit: str
    resolved_meaning: str
    action: str
    score: float


def _gaussian_plausibility(value: float, center: float, width: float) -> float:
    return math.exp(-((value - center) ** 2) / (2 * width**2))


def _fahrenheit_plausibility(value: float) -> float:
    # Centered near comfortable-room/body temperature in Fahrenheit.
    return _gaussian_plausibility(value, center=70.0, width=40.0)


def _celsius_plausibility(value: float) -> float:
    # Centered near comfortable-room temperature in Celsius.
    return _gaussian_plausibility(value, center=20.0, width=15.0)


def resolve_scalar_unit(raw_input: str) -> ResolvedMeaningObject:
    """CUMR001 scalar-unit ambiguity resolution: given a bare numeric
    string, scores Fahrenheit vs. Celsius readings by plausibility in
    everyday (non-scientific) usage and returns the higher-scoring
    interpretation as `resolved_meaning`, with both candidates' relative
    scores recorded in `ext.confidence_score`.

    Raises `ValueError` if `raw_input` isn't parseable as a number — this
    resolver only handles CUMR001's scalar-unit case, not general natural
    language."""
    try:
        value = float(raw_input)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"resolve_scalar_unit requires a numeric raw_input, got {raw_input!r}") from exc

    candidates = [
        ScalarUnitCandidate(
            unit="Fahrenheit",
            resolved_meaning=f"{raw_input} Fahrenheit",
            action="unit_conversion_fahrenheit",
            score=_fahrenheit_plausibility(value),
        ),
        ScalarUnitCandidate(
            unit="Celsius",
            resolved_meaning=f"{raw_input} Celsius",
            action="unit_conversion_celsius",
            score=_celsius_plausibility(value),
        ),
    ]
    best = max(candidates, key=lambda c: c.score)
    total_score = sum(c.score for c in candidates)
    confidence = best.score / total_score if total_score > 0 else 1.0 / len(candidates)

    return ResolvedMeaningObject(
        raw_input=raw_input,
        resolved_meaning=best.resolved_meaning,
        action=best.action,
        title=f"{raw_input} scalar unit disambiguation",
        tags=["CUMR001", "ScalarUnit", best.unit],
        ext={
            "candidate_domain": "ScalarUnit.Temperature",
            "confidence_score": round(confidence, 4),
            "candidates": [{"unit": c.unit, "score": round(c.score, 6)} for c in candidates],
        },
    )
