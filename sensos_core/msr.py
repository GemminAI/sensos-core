"""MSR (Meaning Space Representation) — Dynamic Geometry (SPEC-MSR-001_v2).

Per SPEC-MSR-001_v2 §2.0, the Static (`d_ultra`, Trie-based) and Dynamic
(`d_manifold`, `mlba-core`-based) layers are independent — a No-Go on the
geometry hypothesis removes Static entirely and leaves Dynamic untouched.
This module implements only the Dynamic-layer shift judgment
(`evaluate_manifold_shift`) and its calibration loading; it has no Trie
dependency of any kind. Computing `d_manifold` itself
(`msr_compute_manifold_distance` / `msr_compute_sliced_wasserstein` via
`mlba-core`) is out of scope here — this module consumes an already-computed
`d_manifold` float.

Per §3.1, the MAC001 noise-floor constants (5.93 / 10.98 / 8.50) were
measured against Micro-LLM v0.1 and must never be hardcoded here — they
only ever enter this module through a per-build calibration file, and a
missing file means `UNCALIBRATED`, not a silent fallback to some default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ShiftVerdict = Literal["UNCALIBRATED", "STAGNANT", "NOISE_FLOOR_INTERNAL", "STRUCTURAL_SHIFT_DETECTED"]


@dataclass(frozen=True)
class Calibration:
    """SPEC-MSR-001_v2 §3.1's `<data_dir>/calibration/<model_build_id>.json`
    contents, one file per model build — never applied across builds."""

    model_build_id: str
    measured_at: str
    noise_floor_lower: float
    noise_floor_upper: float
    background_mean: float
    sample_config: dict[str, Any]


def calibration_path(data_dir: Path, model_build_id: str) -> Path:
    return Path(data_dir) / "calibration" / f"{model_build_id}.json"


def load_calibration(data_dir: Path, model_build_id: str) -> Calibration | None:
    """Returns `None` (never raises) when no calibration file exists for
    this exact `model_build_id` — the caller must treat that as
    `UNCALIBRATED`, not as "use some other build's numbers"."""
    path = calibration_path(data_dir, model_build_id)
    if not path.exists():
        return None

    data = json.loads(path.read_text())
    return Calibration(
        model_build_id=data["model_build_id"],
        measured_at=data["measured_at"],
        noise_floor_lower=data["noise_floor_lower"],
        noise_floor_upper=data["noise_floor_upper"],
        background_mean=data["background_mean"],
        sample_config=data.get("sample_config", {}),
    )


def evaluate_manifold_shift(d_manifold: float, calib: Calibration | None) -> ShiftVerdict:
    """SPEC-MSR-001_v2 §3.2's four-way judgment, verbatim. Unlike v1's
    boolean `msr_check_noise_floor_breach`, this returns all four states —
    including the below-floor `STAGNANT` case v1's own bug collapsed into
    `NOISE_FLOOR_INTERNAL`."""
    if calib is None:
        return "UNCALIBRATED"
    if d_manifold < calib.noise_floor_lower:
        return "STAGNANT"
    if d_manifold <= calib.noise_floor_upper:
        return "NOISE_FLOOR_INTERNAL"
    return "STRUCTURAL_SHIFT_DETECTED"
