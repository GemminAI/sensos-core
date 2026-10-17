# MP0 - Messaging Plane (provisional name): profile schemas and test vectors

Status: draft, stage MP0 (design v0.1). Nothing here changes `GemminAI/hext`, hekb-vnext, nvs-kernel or nvs-runtime.

## 1. What MP stores

MP adds no storage format. Each record is a HEXT v2 document (`hext: "2.0.0"`):

| MP record | HEXT kind | `object.type` (profile id) | `provenance.derived_from` |
|---|---|---|---|
| message | `source` | `sensos.mp.message/0.1` | `[]` |
| readback | `annotation` | `sensos.mp.readback/0.1` | `[target]` |
| alignment | `annotation` | `sensos.mp.alignment/0.1` | `[target, readback]` |

### Where the profile lives (HEXT v2 draft `632e108`)

`schemas/hext-2.schema.json` has `additionalProperties: false` at the top level and in `object`, `time`, `measurement`, so there is no extension slot. The profile is carried by two fields that are free strings in the standard:

- `object.type` (schema line 66) = the profile id;
- one `evidence` item (schema lines 282-301): `evidence_id: "mp"`, `format` = the profile id, `body` = the payload as RFC 8785 text (a string, so sealed byte-for-byte).

The payload JSON is validated by this repo's schemas (`sensos_core/mp/schemas/`), not by the HEXT schema. The envelope rules (type/kind match, exactly one profile evidence item, canonical body, `derived_from` equal to the payload's refs) are `sensos_core.mp.check_envelope`.

HEXT's own `time.claims[]` (temporal claims, keyed by `time_id`) is unrelated to the MP payload's `claims[]` (keyed by `id`); the payload's optional `time` attribute on a claim is subject/historical time only. Ordering time is HEXT `time.observed_at` only (D-72).

Verification entry points in the HEXT reference implementation: `hext2.verify.verify(raw, known_sources={id: state_hash}, level=2)` (reference/python/hext2/verify.py:35); sealing `hext2.seal.seal` (seal.py:52, JCS via `hext2.jcs.canonicalize`, state_hash at seal.py:38). For an annotation, `known_sources` must map every `derived_from` id (message and readback) to its state_hash.

## 2. Payload fields

Rules for all profiles: every number is an integer (certainty/weight 0-1000); no floats in sealed content (`loads_strict` rejects `1.0`, exponents, NaN, duplicate keys); no 64D coordinates or 38-port values in a message (they belong to the receiver's Observation in HEKB).

**message** - `from` actor_ref; `to[]` actor_ref (>=1); `thread[]`, `in_reply_to` refs `{id, state_hash}` (optional); `body` verbatim text; `intent.purpose` `{usefulness?, accuracy?, creativity?}` integers 0-1000, at least one; `intent.expects` one of answer/act/clarify/acknowledge/none; `claims[]` `{id, text, time?}`; `premises[]` `{id, text}`; `grounds[]` one of `{kind:"hext", id, state_hash}` / `{kind:"hekb_trajectory", trajectory_id}` / `{kind:"causal_log", ref}`; `uncertainty[]` `{ref, value 0-1000}` where `ref` must be a claim/premise id; `repairs` ref (optional). actor_ref = `<scheme>:<name>` (`^[a-z][a-z0-9_-]*:.+$`).

**readback** - `target` ref; `reader`; `paraphrase`; `received_claims[]` `{claim_ref|null, text}`; `assumed[]`, `missing[]` `{text}`; `expects_understood` (same vocabulary as `expects`).

**alignment** - `target`, `readback` refs; `aligner` `{kind: rule|llm|human, ref, version}`; `inputs_sha256[]` (>=1) and `rule_sha256` as `sha256:<hex>`; `results[]` `{ref|null, status: preserved|lost|added|conflict|missing_candidate}`; `verification_status` unverified|verified|rejected.

## 3. HEKBv3 graph edges (definition only; hekb-vnext untouched)

No new node kinds (D-70: Observation, Evidence, Interpretation, Selection, Outcome). New edges: `sent_to`, `received_by`, `reads_back`, `aligns`, `repairs`, `results_in` (D-70's `corrects`/`supersedes` unchanged).

| MP record | node kind | edges |
|---|---|---|
| message | Evidence | `sent_to` (message -> recipient actor), `repairs` (message -> repaired message), `results_in` (message -> Outcome) |
| readback | Interpretation | `reads_back` (readback -> message), `received_by` (message -> readback's reader) |
| alignment | Interpretation | `aligns` (alignment -> message, alignment -> readback) |

Edge endpoint details beyond this table (actor nodes, direction conventions) are not decided here.

## 4. Name collision check (2026-10-18)

Searched all 15 git repositories under `~/GemminAI` (tracked files, `git grep`) for `sensos\.mp`, `sensos_core/mp`, `Messaging Plane`, `\bMP\b`, `readback`, and tracked paths named `mp`. Result: no hits in any repository; no `mp` directory. `sensos_core` had no `mp` package before this branch. Not searched: untracked files, `_archive/`, other machines. The abbreviation MP is provisional; if it is renamed, only the `mp` package name and profile ids change.

## 5. Tests and CI

`tests/test_mp0.py`. Schema/negative-vector tests need only `jsonschema` (test extra). Tests that use the HEXT v2 reference implementation (level-2 verification, rebuild vs golden, two-fresh-process sealing) need `HEXT_V2_PATH=<GemminAI/hext checkout on v2-draft>`; without it they are **skipped with a reason**. sensos-core has no CI configuration today, so nothing runs in CI; once one exists it will skip those tests unless it checks out hext `v2-draft` and sets the variable.

Regenerate vectors: `HEXT_V2_PATH=... python -m sensos_core.mp.testvectors.generate`.

## 6. Not decided / unverified

- `inputs_sha256`/`rule_sha256` use the `sha256:<hex>` form; the GRAPH-ALIGN001 Verification shape could not be located on the checked-out hekb-vnext branches, so equivalence is unconfirmed.
- Carrying the payload as an evidence `body` string is a convention, not a HEXT-sanctioned extension mechanism; a formal profile slot would be a HEXT change.
