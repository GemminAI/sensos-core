from datetime import datetime, timedelta, timezone

from sensos_core.context_lifecycle_engine import (
    ArchiveThresholds,
    AttentionContext,
    ContextLifecycleEngine,
    is_leaf_node,
    should_archive,
)

THRESHOLDS = ArchiveThresholds(min_recall_count=3, max_idle_seconds=3600.0)
NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def _sidecar(*, recall_count=1, last_recalled_at="2026-09-05T10:00:00Z", archived=False):
    return {"recall_count": recall_count, "last_recalled_at": last_recalled_at, "archived": archived}


def _topology(edges):
    return {"nodes": [], "edges": [{"source": s, "target": t, "relation": "lineage_parent"} for s, t in edges]}


# ---------------------------------------------------------------------------
# is_leaf_node
# ---------------------------------------------------------------------------


def test_is_leaf_node_true_when_no_outgoing_edge():
    topology = _topology([("root", "child_a")])
    assert is_leaf_node(topology, "child_a") is True


def test_is_leaf_node_false_when_object_has_a_child():
    topology = _topology([("root", "child_a"), ("child_a", "grandchild")])
    assert is_leaf_node(topology, "child_a") is False


# ---------------------------------------------------------------------------
# should_archive — the required verification: nodes with children are excluded
# ---------------------------------------------------------------------------


def test_should_archive_excludes_node_with_children_even_if_otherwise_eligible():
    """The literal required check: an object that is otherwise fully
    eligible (low recall_count, long idle) must still be protected from
    Archive if it has a child in the current topology."""
    topology = _topology([("parent_id", "target_id"), ("target_id", "child_of_target")])
    sidecar = _sidecar(recall_count=0, last_recalled_at="2026-09-01T00:00:00Z")
    assert should_archive("target_id", sidecar, topology, THRESHOLDS, now=NOW) is False


def test_should_archive_true_for_a_genuine_low_recall_idle_leaf():
    topology = _topology([("parent_id", "target_id")])  # target_id has no children
    sidecar = _sidecar(recall_count=0, last_recalled_at="2026-09-01T00:00:00Z")
    assert should_archive("target_id", sidecar, topology, THRESHOLDS, now=NOW) is True


def test_should_archive_false_when_already_archived():
    topology = _topology([("parent_id", "target_id")])
    sidecar = _sidecar(recall_count=0, last_recalled_at="2026-09-01T00:00:00Z", archived=True)
    assert should_archive("target_id", sidecar, topology, THRESHOLDS, now=NOW) is False


def test_should_archive_false_when_last_recalled_at_missing():
    """SPEC-CLE-001_v2 §2.2's own caution: a sidecar reset zeroes
    recall_count but must not trigger a mass-Archive — a missing
    last_recalled_at blocks the judgment outright, regardless of how low
    recall_count is."""
    topology = _topology([("parent_id", "target_id")])
    sidecar = _sidecar(recall_count=0, last_recalled_at=None)
    assert should_archive("target_id", sidecar, topology, THRESHOLDS, now=NOW) is False


def test_should_archive_false_when_recall_count_at_threshold():
    topology = _topology([("parent_id", "target_id")])
    sidecar = _sidecar(recall_count=THRESHOLDS.min_recall_count, last_recalled_at="2026-09-01T00:00:00Z")
    assert should_archive("target_id", sidecar, topology, THRESHOLDS, now=NOW) is False


def test_should_archive_false_when_recently_recalled():
    topology = _topology([("parent_id", "target_id")])
    recent = (NOW - timedelta(seconds=THRESHOLDS.max_idle_seconds / 2)).isoformat().replace("+00:00", "Z")
    sidecar = _sidecar(recall_count=0, last_recalled_at=recent)
    assert should_archive("target_id", sidecar, topology, THRESHOLDS, now=NOW) is False


def test_should_archive_root_with_no_children_and_no_parent_edge_is_still_a_leaf():
    # A root object with no children at all has no edges referencing it
    # whatsoever — is_leaf_node must still correctly report it as a leaf.
    topology = _topology([])
    sidecar = _sidecar(recall_count=0, last_recalled_at="2026-09-01T00:00:00Z")
    assert should_archive("lonely_root", sidecar, topology, THRESHOLDS, now=NOW) is True


# ---------------------------------------------------------------------------
# AttentionContext — Prune reversibility, no HEKB I/O by construction
# ---------------------------------------------------------------------------


def test_attention_context_prune_then_reload_round_trips():
    ctx = AttentionContext()
    ctx.load("obj1", {"payload": "x"})
    assert ctx.is_loaded("obj1")

    pruned = ctx.prune("obj1")
    assert pruned is True
    assert not ctx.is_loaded("obj1")

    ctx.load("obj1", {"payload": "x"})  # re-load == "recall" in the real engine
    assert ctx.is_loaded("obj1")


def test_attention_context_prune_of_unloaded_object_is_a_harmless_no_op():
    ctx = AttentionContext()
    assert ctx.prune("never_loaded") is False


# ---------------------------------------------------------------------------
# ContextLifecycleEngine — orchestration, against a fake HTTP client
# ---------------------------------------------------------------------------


class FakeHekbClient:
    """Duck-typed stand-in for HekbClient — no real HTTP, no live
    hekb-vnext server needed for these tests. Records every call made so
    tests can assert CLE never calls anything beyond recall/archive/topology
    reads (in particular, nothing resembling a delete)."""

    def __init__(self, topology: dict, chains: dict[str, dict], sidecars: dict[str, dict]):
        self.topology = topology
        self.chains = chains
        self.sidecars = sidecars
        self.calls: list[tuple[str, tuple]] = []

    def get_topology(self, lineage_id=None, include_archived=False):
        self.calls.append(("get_topology", (lineage_id, include_archived)))
        return self.topology

    def get_ancestor_chain(self, from_object_id, depth=5):
        self.calls.append(("get_ancestor_chain", (from_object_id, depth)))
        return self.chains[from_object_id]

    def post_recall(self, object_id):
        self.calls.append(("post_recall", (object_id,)))
        return self.sidecars[object_id]

    def post_archive(self, object_id):
        self.calls.append(("post_archive", (object_id,)))
        sidecar = dict(self.sidecars[object_id])
        sidecar["archived"] = True
        self.sidecars[object_id] = sidecar
        return sidecar

    def close(self):
        self.calls.append(("close", ()))


def test_cle_recall_loads_ancestor_chain_into_attention_context():
    fake = FakeHekbClient(
        topology=_topology([]),
        chains={"leaf1": {"lineage_id": "L", "count": 2, "experiences": [
            {"object_id": "root1", "payload": {"title": "root"}},
            {"object_id": "leaf1", "payload": {"title": "leaf"}},
        ]}},
        sidecars={"leaf1": _sidecar(recall_count=1, last_recalled_at="2026-09-05T11:00:00Z")},
    )
    cle = ContextLifecycleEngine(fake, THRESHOLDS)

    chain = cle.recall("leaf1", depth=5)

    assert chain["count"] == 2
    assert cle.context.is_loaded("root1")
    assert cle.context.is_loaded("leaf1")
    assert cle.sidecar_snapshot("leaf1") == fake.sidecars["leaf1"]
    assert ("post_recall", ("leaf1",)) in fake.calls
    assert ("get_ancestor_chain", ("leaf1", 5)) in fake.calls


def test_cle_evaluate_archive_candidates_skips_node_with_child():
    """End-to-end through the orchestration layer: a candidate with a
    child in topology must not be archived even though its cached sidecar
    is otherwise eligible."""
    fake = FakeHekbClient(
        topology=_topology([("parent", "has_child"), ("has_child", "grandchild"), ("parent2", "true_leaf")]),
        chains={},
        sidecars={
            "has_child": _sidecar(recall_count=0, last_recalled_at="2026-09-01T00:00:00Z"),
            "true_leaf": _sidecar(recall_count=0, last_recalled_at="2026-09-01T00:00:00Z"),
        },
    )
    cle = ContextLifecycleEngine(fake, THRESHOLDS)
    # Populate the sidecar cache the way real usage would: via a prior recall.
    cle._sidecar_cache["has_child"] = fake.sidecars["has_child"]
    cle._sidecar_cache["true_leaf"] = fake.sidecars["true_leaf"]

    archived = cle.evaluate_archive_candidates(["has_child", "true_leaf"])

    assert "has_child" not in archived
    assert "true_leaf" in archived
    assert ("post_archive", ("true_leaf",)) in fake.calls
    assert ("post_archive", ("has_child",)) not in fake.calls


def test_cle_never_calls_anything_delete_shaped():
    fake = FakeHekbClient(topology=_topology([]), chains={}, sidecars={})
    cle = ContextLifecycleEngine(fake, THRESHOLDS)
    cle.prune("whatever")
    cle.evaluate_archive_candidates([])

    for name in dir(cle):
        assert "delete" not in name.lower()
    for method_name, _ in fake.calls:
        assert "delete" not in method_name.lower()
