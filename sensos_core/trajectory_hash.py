"""Canonical hashing for `msr.abi.StabilizedTrajectory`.

`StabilizedTrajectory` is not redefined here — it is `msr.abi.StabilizedTrajectory`,
re-exported from `meaning-space-runtime` (see that package's own docstring:
"the frozen value types crossing every MSR boundary"). `categorical-lift-engine`
already consumes this same shape structurally via `cle.abi.inputs.StabilizedTrajectoryLike`.
Defining a second, independent `StabilizedTrajectory` in this package would repeat the
CLE/MSR/HEKB naming-collision pattern documented in
`~/vaults/20260124/OKF/SensOS-Naming-Collisions.md` — so this module only adds a
deterministic hash on top of the existing type.

The hash itself reuses this codebase's proven RFC 8785 (JCS) + SHA-256 pattern from
`sensos/services/observation-runtime/sensos/canonical_hash.py`
(`canonical_tag_hash`), generalized from that module's Contract-1-specific
`grounded_state` to a full `StabilizedTrajectory.as_dict()`. It does not replace or
alter that module, or the two other, unrelated hash schemes its docstring documents
(`crystallizer.py`'s `crystallize_state_hash`, `nvs74/object.py`'s `generate_state_hash`)
— those remain scoped to their own object shapes.
"""

from __future__ import annotations

import hashlib

import rfc8785
from msr.abi import MeaningState, StabilizedTrajectory

__all__ = ["MeaningState", "StabilizedTrajectory", "compute_trajectory_hash"]


def compute_trajectory_hash(trajectory: StabilizedTrajectory) -> str:
    """SHA-256(JCS(trajectory.as_dict())), hex-encoded.

    Deterministic: two `StabilizedTrajectory` values with bit-for-bit identical
    `as_dict()` output always hash to the same value, regardless of process or
    call order.
    """
    canonical_bytes = rfc8785.dumps(trajectory.as_dict())
    return hashlib.sha256(canonical_bytes).hexdigest()
