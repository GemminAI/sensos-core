"""Regenerate the MP0 test vectors. Usage: HEXT_V2_PATH=<hext repo> python generate.py

Writes valid/*.json (payloads), sealed/*.hext2.json (sealed HEXT v2 documents), invalid/*.json and manifest.json.
Sealed output is deterministic: fixed ids and times, no clock, no randomness.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(os.environ["HEXT_V2_PATH"]) / "reference" / "python"))

from sensos_core.mp.build import build_document

SEALED_AT = "2026-10-18T09:00:00Z"
OBSERVED = {"value": "2026-10-18T08:59:30Z", "precision": "second", "tz": "explicit"}
H64 = "sha256:" + "ab" * 32


def main() -> None:
    manifest: dict[str, Any] = {"valid": [], "invalid": []}

    def emit(name: str, payload: dict[str, Any], observed: dict[str, str] | None = OBSERVED) -> dict[str, str]:
        sealed, _doc = build_document(payload, object_id=name, sealed_at=SEALED_AT, observed_at=observed)
        (HERE / "valid" / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (HERE / "sealed" / f"{name}.hext2.json").write_bytes(sealed.canonical_bytes + b"\n")
        manifest["valid"].append({"name": name, "profile": payload["profile"], "object_id": name,
                                  "sealed_at": SEALED_AT, "observed_at": observed, "state_hash": sealed.state_hash})
        return {"id": name, "state_hash": sealed.state_hash}

    msg1 = {
        "profile": "sensos.mp.message/0.1",
        "from": "human:tomo",
        "to": ["mlx:llama-3.1-8b-instruct:4bit"],
        "body": "  この実験の N は 122 のままでよいですか？ 理由も。\n",
        "intent": {"purpose": {"accuracy": 800, "usefulness": 600}, "expects": "answer"},
        "claims": [
            {"id": "c1", "text": "N は現在 122 である", "time": {"frame": "absolute", "expression": "現在"}},
            {"id": "c2", "text": "段 3 は 2026-10-17 に完了した", "time": {"frame": "historical", "expression": "10-17", "value": "2026-10-17"}},
        ],
        "premises": [{"id": "p1", "text": "検出力の限界は N で決まる"}],
        "grounds": [
            {"kind": "hext", "id": "hext2-three-sentences", "state_hash": H64},
            {"kind": "hekb_trajectory", "trajectory_id": "traj-0001"},
            {"kind": "causal_log", "ref": "causal/exp_hekbv3_d71_stage3#L1"},
        ],
        "uncertainty": [{"ref": "c1", "value": 900}, {"ref": "p1", "value": 0}],
    }
    m1 = emit("mp0-message-01", msg1)

    msg2 = {
        "profile": "sensos.mp.message/0.1",
        "from": "mlx:llama-3.1-8b-instruct:4bit",
        "to": ["human:tomo", "api:anthropic:claude-example"],
        "thread": [m1],
        "in_reply_to": m1,
        "body": "N=122 では M1 の最小検出差は 0.15 です。",
        "intent": {"purpose": {"creativity": 1000}, "expects": "acknowledge"},
        "repairs": m1,
    }
    emit("mp0-message-02", msg2, observed=None)

    rb = {
        "profile": "sensos.mp.readback/0.1",
        "target": m1,
        "reader": "mlx:llama-3.1-8b-instruct:4bit",
        "paraphrase": "N を 122 に保つかどうかと、その理由を尋ねている。",
        "received_claims": [{"claim_ref": "c1", "text": "N は 122"}, {"claim_ref": None, "text": "理由が必要"}],
        "assumed": [{"text": "N は被験プロンプト数を指す"}],
        "missing": [{"text": "比較する条件の一覧"}],
        "expects_understood": "answer",
    }
    r1 = emit("mp0-readback-01", rb)

    al = {
        "profile": "sensos.mp.alignment/0.1",
        "target": m1,
        "readback": r1,
        "aligner": {"kind": "rule", "ref": "mp0-claim-matcher", "version": "0.1"},
        "inputs_sha256": [m1["state_hash"], r1["state_hash"]],
        "rule_sha256": H64,
        "results": [
            {"ref": "c1", "status": "preserved"}, {"ref": "c2", "status": "lost"},
            {"ref": None, "status": "added"}, {"ref": "p1", "status": "conflict"},
            {"ref": None, "status": "missing_candidate"},
        ],
        "verification_status": "unverified",
    }
    emit("mp0-alignment-01", al)

    def bad(name: str, base: dict[str, Any], mutate: Any, layer: str, expect: str) -> None:
        p = copy.deepcopy(base)
        mutate(p)
        (HERE / "invalid" / f"{name}.json").write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["invalid"].append({"name": name, "layer": layer, "expect": expect})

    bad("message-float-uncertainty", msg1, lambda p: p["uncertainty"][0].update(value=500.5), "strict", "float")
    bad("message-float-integral", msg1, lambda p: p["uncertainty"][0].update(value=500.0), "strict", "float")
    bad("message-purpose-empty", msg1, lambda p: p["intent"].update(purpose={}), "schema", "minProperties")
    bad("message-uncertainty-1001", msg1, lambda p: p["uncertainty"][0].update(value=1001), "schema", "maximum")
    bad("message-to-empty", msg1, lambda p: p.update(to=[]), "schema", "minItems")
    bad("message-expects-unknown", msg1, lambda p: p["intent"].update(expects="shout"), "schema", "enum")
    bad("message-uncertainty-dangling", msg1, lambda p: p["uncertainty"][0].update(ref="zz"), "semantic", "dangling_uncertainty_ref")
    bad("readback-target-missing", rb, lambda p: p.pop("target"), "schema", "required")
    bad("alignment-status-unknown", al, lambda p: p["results"][0].update(status="kept"), "schema", "enum")

    (HERE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
