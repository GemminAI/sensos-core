"""CLE (Context Lifecycle Engine) — SPEC-CLE-001_v2.

Implements exactly the two operations SPEC-ARCH-IMPACT-001_v2 §0.1 permits
CLE to perform: Prune (reversible, in-memory only, no HEKB write) and
Archive (a sidecar flag flip via `POST /experience/{id}/archive` — never a
physical delete). Context Recall (§2.3) is the third lifecycle operation:
it re-expands a pruned trajectory into attention context via
`POST /experience/{id}/recall` (the only endpoint permitted to increment
`recall_count`) plus `GET /experience/recall` for the ancestor chain.

CLE never calls anything resembling a Delete API — there is no delete
method, HTTP verb, or endpoint reference anywhere in this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

_UNLOADED = object()


# ---------------------------------------------------------------------------
# HTTP client — thin wrapper over hekb-vnext's read/recall/archive surface
# ---------------------------------------------------------------------------


class HekbClient:
    """Wraps exactly the hekb-vnext endpoints CLE is allowed to call:
    `GET /graph/topology`, `GET /experience/recall`,
    `POST .../recall`, `POST .../archive`. Deliberately has no method for
    `POST /experience` (object creation, which also requires the
    `X-Audit-Signature` governance CLE has no business producing) and none
    resembling a delete."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self._base_url, timeout=10.0)

    def get_topology(self, lineage_id: str | None = None, include_archived: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {"include_archived": include_archived}
        if lineage_id is not None:
            params["lineage_id"] = lineage_id
        response = self._client.get("/graph/topology", params=params)
        response.raise_for_status()
        return response.json()

    def get_ancestor_chain(self, from_object_id: str, depth: int = 5) -> dict[str, Any]:
        response = self._client.get("/experience/recall", params={"from_object_id": from_object_id, "depth": depth})
        response.raise_for_status()
        return response.json()

    def post_recall(self, object_id: str) -> dict[str, Any]:
        response = self._client.post(f"/experience/{object_id}/recall")
        response.raise_for_status()
        return response.json()

    def post_archive(self, object_id: str) -> dict[str, Any]:
        response = self._client.post(f"/experience/{object_id}/archive")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Attention context — Prune target. In-memory only, never touches HEKB.
# ---------------------------------------------------------------------------


@dataclass
class AttentionContext:
    """The currently-loaded attention window. Prune/load against this
    class never issue an HTTP call — that is what makes Prune's
    reversibility and zero-write guarantee (SPEC-CLE-001_v2 AC2) trivially
    true by construction rather than something to test for."""

    loaded: dict[str, Any] = field(default_factory=dict)

    def is_loaded(self, object_id: str) -> bool:
        return object_id in self.loaded

    def load(self, object_id: str, trajectory: Any) -> None:
        self.loaded[object_id] = trajectory

    def prune(self, object_id: str) -> bool:
        """§2.1 Context Prune: reversible unload, no HEKB write. Returns
        True iff the object was actually loaded — unloading something not
        present is a no-op, not an error."""
        return self.loaded.pop(object_id, _UNLOADED) is not _UNLOADED

    def __len__(self) -> int:
        return len(self.loaded)


# ---------------------------------------------------------------------------
# Archive judgment — pure function, no I/O
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchiveThresholds:
    min_recall_count: int
    max_idle_seconds: float


def is_leaf_node(topology: dict[str, Any], object_id: str) -> bool:
    """True iff `object_id` has no outgoing edge in a `GET /graph/topology`
    response — edges are `source=parent -> target=child`
    (SPEC-HEKB-003_v2 §3.2's direction convention), so "no children" means
    no edge in this list has `object_id` as its `source`."""
    return not any(edge["source"] == object_id for edge in topology.get("edges", []))


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def should_archive(
    object_id: str,
    sidecar: dict[str, Any],
    topology: dict[str, Any],
    thresholds: ArchiveThresholds,
    now: datetime | None = None,
) -> bool:
    """SPEC-CLE-001_v2 §2.2's three-way AND (low `recall_count`, idle past
    threshold, no children), evaluated as short-circuiting guards — each
    one alone is sufficient to protect the object from Archive:

    1. Already archived -> nothing to do.
    2. `last_recalled_at` missing -> refuse to judge at all. This is
       §2.2's own explicit caution: a sidecar reset (SPEC-HEKB-003_v2
       §2.1) zeroes `recall_count`, and that reset must never itself be
       mistaken for "long overdue for archive".
    3. `recall_count` at or above threshold -> still relevant, keep it.
    4. Idle time at or below threshold -> recently used, keep it.
    5. Has a child in the current topology -> keep it. Archiving a node
       with descendants would break the ancestor-chain continuity Recall
       depends on (SPEC-CLE-001_v2 §2.2 / SPEC-ARCH-IMPACT-001_v2 §0.1).

    Only once none of the above disqualify it does this return True."""
    if sidecar.get("archived"):
        return False
    last_recalled_at = sidecar.get("last_recalled_at")
    if last_recalled_at is None:
        return False
    if sidecar.get("recall_count", 0) >= thresholds.min_recall_count:
        return False

    reference_now = now or datetime.now(timezone.utc)
    idle_seconds = (reference_now - _parse_iso8601(last_recalled_at)).total_seconds()
    if idle_seconds <= thresholds.max_idle_seconds:
        return False

    if not is_leaf_node(topology, object_id):
        return False

    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class ContextLifecycleEngine:
    """Orchestrates Prune / Archive-judgment / Recall against a live
    hekb-vnext instance, per SPEC-CLE-001_v2 §2.

    The sidecar state `should_archive` needs (`recall_count`,
    `last_recalled_at`, `archived`) comes from CLE's OWN cache, populated
    exclusively as a byproduct of CLE's own `recall()` / archive calls —
    both endpoints return the updated sidecar in their response, so no
    separate read-only sidecar-fetch endpoint is needed. An object CLE has
    never itself recalled has no cache entry and is therefore never
    archived, which is exactly right: it also has no `last_recalled_at`,
    and `should_archive` refuses to judge that case anyway."""

    def __init__(self, client: HekbClient, thresholds: ArchiveThresholds) -> None:
        self._client = client
        self._thresholds = thresholds
        self._context = AttentionContext()
        self._sidecar_cache: dict[str, dict[str, Any]] = {}

    @property
    def context(self) -> AttentionContext:
        return self._context

    def sidecar_snapshot(self, object_id: str) -> dict[str, Any] | None:
        return self._sidecar_cache.get(object_id)

    def prune(self, object_id: str) -> bool:
        """§2.1: unload from attention context only. Deliberately makes no
        HEKB call at all — the cleanest way to guarantee AC2 (Prune must
        never write to `objects/`, `relations/`, `lineages/`, or `meta/`)
        is for this method to have no HTTP call in it to begin with."""
        return self._context.prune(object_id)

    def recall(self, object_id: str, depth: int = 5) -> dict[str, Any]:
        """§2.3 Context Recall: always calls `POST .../recall` first (the
        only path that increments `recall_count`), then re-expands the
        ancestor chain into attention context via
        `GET /experience/recall?from_object_id=&depth=`."""
        sidecar = self._client.post_recall(object_id)
        self._sidecar_cache[object_id] = sidecar

        chain = self._client.get_ancestor_chain(object_id, depth=depth)
        for experience in chain.get("experiences", []):
            self._context.load(experience["object_id"], experience)

        return chain

    def evaluate_archive_candidates(
        self, candidate_object_ids: list[str], lineage_id: str | None = None
    ) -> list[str]:
        """Fetches topology ONCE for this batch (a single live read,
        deliberately not per-candidate), then applies `should_archive` to
        each candidate using CLE's own cached sidecar state. Returns the
        object_ids actually archived."""
        topology = self._client.get_topology(lineage_id=lineage_id, include_archived=True)
        archived: list[str] = []
        for object_id in candidate_object_ids:
            sidecar = self._sidecar_cache.get(object_id)
            if sidecar is None:
                continue
            if should_archive(object_id, sidecar, topology, self._thresholds):
                updated = self._client.post_archive(object_id)
                self._sidecar_cache[object_id] = updated
                archived.append(object_id)
        return archived

    def close(self) -> None:
        self._client.close()
