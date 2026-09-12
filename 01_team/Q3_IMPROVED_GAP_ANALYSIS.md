# Q3-improved-v1 gap analysis

## 1. Audit scope and evidence boundary

This audit covers the frozen `Q3-baseline-v1`, current `B_code/src`, tests,
scripts and tools, the team specifications/status files, and the five saved
stress runs `Q3-S-001`--`Q3-S-005`. No frozen file was modified.

Evidence priority follows `SOURCE_OF_TRUTH.md`. The five `.jlog` files are
encrypted behavior-log packages: their unencrypted envelope identifies the
case, but the repository contains no decoder/key for their action frames.
Consequently, per-action protocol claims below come from the saved console
output when available and from `官方材料/附件2.docx` otherwise. The console
output is not a raw-response log and does not expose accepted responses for
every action.

## 2. Requirement-to-baseline matrix

| New-plan requirement | In baseline? | Reusable? | Rewrite/new work? | Evidence |
| --- | --- | --- | --- | --- |
| Simulator adapter | Partial | Wrap request construction and serial HTTP transport | Yes: typed outcomes, raw response retention, unknown-result state, same-request retry | `B_code/frozen/q3_baseline_v1/simulator_client.py` |
| Seven-point scan | Partial, but wrong radius | Reuse serpentine channel order and fixed scan loop concept | Yes: nodes must be center plus radius `900*sqrt(3)`, accepted/completed ledger | `baseline_q3_all.py:regular_hexagon_points(radius=1200.0)`; all five consoles |
| Channel state | No formal state machine | Discovered/near/cleared sets only as migration hints | Yes: all six statuses and legal transitions | `baseline_q3_all.py:main`, `clear_discovered_targets` |
| Coverage log | Partial in memory | `recon_results` schema is a starting point | Yes: requested/accepted/completed/result/time/raw-id and durable CSV | `baseline_q3_all.py:run_reconnaissance` |
| Bearing geometry | Baseline only has point least squares | Do not use baseline estimate as a certificate | Reuse Q1 verified `wedge_halfplanes`; add conservative box-corner tests | `B_code/frozen/q3_baseline_v1/geometry.py`; `B_code/src/q1_localization.py` |
| Localization | Heuristic point estimate only | May remain a P1 ranking diagnostic | Yes: immutable observations, fixed-R consistency, adaptive OUTER/rebuild | frozen `geometry.py`; Q1 set-membership code |
| Clear | Attempts an estimated/near point | Reuse `NEAR -> clear current point` behavior and nearest-neighbor idea | Yes: certificate gate, typed failures, history | `baseline_q3_all.py:clear_one_channel` |
| Retry/recovery | Limited geometry-driven retry | Lateral measurement construction may be a P1 heuristic | Yes: protocol-idempotent retry, RECOVERY without unsafe geometry mutation | `clear_one_channel`; official attachment section 5.3 |
| `virtual_time` | Tracks last accepted response in normal path | Reuse response-authoritative clock principle | Yes: rejected/unknown handling, monotonic checks, action ledger | `update_state`; official attachment section 4 |
| Terminal condition | No; stops after one pass over discovered channels | No | Yes: 16 successful channels OR all 20 terminal states | `clear_discovered_targets`; final `cleared==discovered` message |
| Simulator log export | Stress harness copies official `.jlog` and saves console/result | Reuse artifact-discovery/copy logic | Yes: `actions.jsonl`, `coverage.csv`, `channels.json`, `summary.json` | `B_code/tools/run_q3_stress.py`; stress result directories |
| Seven-negative absence certificate | No | No | Yes, after directional-source safety is resolved | official attachment sections 2.2 and 7.3 |
| Fixed unknown receive-radius consistency | No | Q2 `receive_floor`/strict-receive logic is conceptual reference only | Yes: per-source online constraints and strict endpoint tests | `B_code/src/q2_selection.py`; `MODEL_SPEC.md` Q2 |
| Conservative adaptive OUTER | No | Q1 half-planes/MEC can be called through stable interfaces | Yes: box distances, exclusions, splitting/budget, verified snapshot recovery | Q1 source/tests |
| MEC clear certificate | No in baseline | Yes: Q1 `minimum_enclosing_circle`, `EPS_MEC=1.8e-4 m`, independent tests | Q3 wrapper/tests still required; use all retained box corners | `q1_localization.py`; Q1 verification report |
| Finite grid fallback | No | Nearest-neighbor ordering idea only | Yes: globally aligned cells, box-intersection retention, finite visit ledger | baseline nearest-clear scheduling |
| C01--C12, randomized OUTER/MEC/exclusion tests | No Q3 tests | Reuse Q1 C01-like wedge and MEC test patterns/oracles | Yes: dedicated Q3 suite | `B_code/tests/test_q1_localization.py`; no `tests/q3_improved` |
| Historical replay | No | Stress parser summaries can help discover artifacts | Yes; unavailable fields must be `NOT_CHECKABLE` | `run_q3_stress.py`; saved artifacts |

## 3. Directly reusable components

1. The frozen client establishes the four endpoints, payload fields, unique
   request-id convention, sequential transport, JSON decoding and basic HTTP
   error handling. Improved code should wrap/copy the stable behavior, not
   import from or alter the frozen directory.
2. The baseline serpentine `1..20/20..1` channel order avoids an unnecessary
   channel switch at each fixed-node boundary. The loop structure is useful;
   its node radius is not.
3. `NEAR` is already treated as the current measurement position, and the
   baseline never invents `svd_deg` for it.
4. Q1 provides tested vector/half-plane bearing wedges, including a 359.5
   degree wraparound test, plus a deterministic MEC whose returned radius is
   recomputed over all input points. Q1 documents and tests
   `EPS_MEC=1.8e-4 m`; it is a team numerical parameter, not an official one.
5. The stress harness preserves official logs under their original names and
   records source hashes, wall runtime, virtual time and summary counts.

## 4. Conflicts and unsafe baseline behavior

- Baseline scans `(0,0)` plus a radius-1200 regular hexagon. The new fixed
  nodes use radius `900*sqrt(3) ~= 1558.846 m`; the existing coordinates do
  not strictly match.
- Every accepted fixed-node result is not retained as an immutable observation.
  `no_signal` is mostly discarded, and direction observations are capped at
  five.
- The client converts `accepted=false`, HTTP errors, timeouts and connection
  loss into `RuntimeError`. It therefore loses the required distinction
  between confirmed rejection and unknown execution, and has no same-id retry.
- Baseline updates position/time only after the client returns an
  `accepted=true` response, which is safe on the happy path. It cannot recover
  an accepted action whose response was lost.
- Least-squares ray intersection treats measured bearings as exact center
  lines. It has no `+/-1 degree` set-membership guarantee, range constraint,
  negative constraint, OUTER containment certificate or safe clear radius.
- Any non-success clear result enters the same recovery branch. The observed
  `no_target_in_range` result is ambiguous: per the official attachment it can
  mean absent, already cleared, or farther than 20 m. It proves `>20 m` only
  if channel existence and not-yet-cleared status are already established.
- Termination is effectively “processed all channels discovered by the fixed
  scan,” not either required online terminal condition. Undetected channels
  have no proof status and a detected channel without a candidate can be
  silently left unresolved.
- The clear-attempt cap of three is finite but is not a complete fallback: a
  detected source can remain uncleared.
- Baseline console output is selective and does not meet the required raw
  action-log/export schema.

## 5. Historical run findings

All five successful runs executed 140 fixed reconnaissance measures and
reported reconnaissance virtual time 2273 s, consistent with the baseline's
radius-1200 route and serpentine channel scan. Across the five consoles:

| Run | `direction` observations printed | `near` printed | clear success | `no_target_in_range` |
| --- | ---: | ---: | ---: | ---: |
| Q3-S-001 | 40 | 0 | 12 | 0 |
| Q3-S-002 | 34 | 0 | 12 | 0 |
| Q3-S-003 | 28 | 0 | 11 | 0 |
| Q3-S-004 | 43 | 0 | 14 | 2 |
| Q3-S-005 | 44 | 0 | 16 | 1 |

The consoles omit ordinary reconnaissance `no_signal` lines, so their exact
count and per-action timestamps are not recoverable. Q3-S-004 channel 1
returned `no_target_in_range` twice before two extra `direction` measurements
and eventual success. Q3-S-005 channel 11 returned it once before one extra
`direction` measurement and success. No successful-run console shows `near`.

A separately preserved preflight attempt shows an actual rejected business
response:

```text
{'accepted': False, 'real_timestamp_ms': 1789096420253, 'virtual_time_s': 0}
```

It did not advance local time/position. Successful actions expose increasing
`virtual_time_s`; all successful exits printed `user_exit`. The current logs
do not expose raw request IDs or response bodies, so duplicate-commit and
same-id replay behavior are not historically checkable.

## 6. P0 model/protocol risks requiring resolution

### R1: directional `NO_SIGNAL` versus fixed-R negative geometry (blocker)

The official attachment says `no_signal` can mean (a) absent/already cleared,
(b) beyond the fixed receive radius, or (c) a directional source not covering
the observation point. Therefore, for an arbitrary source type, a raw
`no_signal` does **not** by itself prove `|G-S| > R`. The proposed fixed-R
negative constraint and whole-box exclusions are safe only under an additional
proved condition (for example, the channel is known omnidirectional) or a
directional-source-aware feasible model. No such proof or type signal exists
in the audited repository.

### R2: seven-negative absence certificate for directional sources (blocker)

For the same reason, seven accepted negative samples require a geometric proof
that every possible source position, receive radius and 180-degree directional
orientation would be detected at at least one fixed node. The audited model
and code do not contain that proof. The four runs with known truth were
manually reported as all-omnidirectional, but this does not establish the rule
for future Q3 cases.

### R3: meaning of `no_target_in_range`

The protocol exposes only `success` and `no_target_in_range`; there is no
separate wire-level `OUT_OF_RANGE` enum. Mapping it to a `>20 m` exclusion is
valid only when the state has already certified that the channel exists and
has not been cleared. Otherwise absence/already-cleared alternatives remain.

### R4: replay evidence completeness

Encrypted `.jlog` payloads and selective consoles cannot support the planned
raw-response replay assertions. New runs must produce `actions.jsonl`; old-run
replay must report affected checks as `NOT_CHECKABLE`, not `PASS`.

## 7. Proposed file structure and minimum-change plan

Use the proposed `B_code/src/q3_improved/` package, with these adjustments:

```text
q3_improved/
  config.py
  protocol.py          # response/outcome types and normalization
  adapter.py           # transport wrapper and idempotent same-payload retry
  state.py
  coverage.py
  observations.py
  conservative_geometry.py
  mec.py               # thin Q1 stable-interface wrapper + Q3 validation
  clear_certificate.py
  fallback.py
  scheduler.py
  runner.py
  replay.py
```

Defer `active_measure.py` to P1. Add tests under
`B_code/tests/q3_improved/`; add a thin executable under `B_code/scripts/`
only when P0 orchestration is ready.

Implementation order after approval:

1. Resolve R1/R2 with the modeling owner; freeze the exact semantics in
   `MODEL_SPEC.md` before geometry code.
2. Implement protocol/outcome types, adapter retry journal and raw action log;
   test accepted-false and unknown-outcome separation first.
3. Implement immutable observations, coverage ledger, channel transitions and
   terminal predicate independently of geometry.
4. Implement conservative box primitives and bearing exclusions; then the
   proved fixed-R/negative rules. Add boundary and containment property tests
   as each exclusion is introduced.
5. Wrap Q1 MEC, derive/retain its documented `EPS_MEC`, and add Q3-specific
   independent oracle tests before enabling `CLEAR_READY`.
6. Implement deterministic fallback, recovery rebuild and scheduler; then
   C01--C12 and randomized tests.
7. Implement old-log replay with explicit `NOT_CHECKABLE`, output artifacts,
   and baseline regression. Stop at `CODED=YES`, `VERIFIED=NO` until new
   official simulator runs.
8. Only after all P0 gates pass, add P1 ranking/route heuristics without
   changing any P0 certificate or transition.

## 8. Current status

`Q3-improved-v1`: **CODED = NO, TESTED = NO, VERIFIED = NO**.

This stage is documentation/audit only. The next implementation stage should
not begin until the directional-source questions R1 and R2 are answered.
