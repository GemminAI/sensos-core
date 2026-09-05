"""SensOS Core Engine: MeaningMapper, MSR, CLE.

Initial implementation per SPEC-MM-001_v2, SPEC-MSR-001_v2, SPEC-CLE-001_v2,
and the cross-cutting decisions in SPEC-ARCH-IMPACT-001_v2 §0. Phase 0-D
found the geometry hypothesis CONDITIONAL GO (see
experiments/EXP-PHASE0D-GEOMETRY), so every module here is built to be
fully correct with the Trie/Static-geometry layer entirely absent —
nothing in this package imports or depends on a Trie implementation.
"""

from sensos_core.cle import ArchiveThresholds, ContextLifecycleEngine
from sensos_core.meaning_mapper import ResolvedMeaningObject, resolve_scalar_unit
from sensos_core.msr import Calibration, ShiftVerdict, evaluate_manifold_shift, load_calibration

__all__ = [
    "ResolvedMeaningObject",
    "resolve_scalar_unit",
    "Calibration",
    "ShiftVerdict",
    "evaluate_manifold_shift",
    "load_calibration",
    "ArchiveThresholds",
    "ContextLifecycleEngine",
]
