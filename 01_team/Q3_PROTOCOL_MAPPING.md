# Q3 simulator protocol mapping

## 1. Labels and evidence

- **OBSERVED**: directly visible in a saved Q3-S-001--005 artifact or the
  preserved rejected preflight console.
- **CONFIRMED_BY_SPEC**: stated in `官方材料/附件2.docx` but not fully exposed
  by the saved selective console logs.
- **UNCONFIRMED**: not established by accessible historical evidence or spec.

The official `.jlog` action frames are encrypted and no decoder/key is present
in the repository. Their filenames and cleartext envelopes are observed, but
their per-action payloads cannot be used as raw-response evidence here.

## 2. Common request and response fields

| Item | Mapping | Status | Evidence/notes |
| --- | --- | --- | --- |
| Method/path | `POST /enter`, `/measure`, `/clear`, `/exit` | CONFIRMED_BY_SPEC | Attachment sections 3, 6--9; baseline client uses all four |
| Common request | `arena_id`, `robot_id`, `request_id` | CONFIRMED_BY_SPEC | Attachment section 5.1; client implementation |
| Action request | adds `position:{x,y}`, `channel` | CONFIRMED_BY_SPEC | Attachment sections 7.1, 8.1; client implementation |
| Common business response | `accepted`, `real_timestamp_ms`, `virtual_time_s` | OBSERVED | Rejected preflight shows all three; consoles expose virtual time on accepted actions |
| `accepted=false` response | only common three fields; action not executed; reported `virtual_time_s=0` is not current clock | OBSERVED / CONFIRMED_BY_SPEC | Exact preflight response observed; general rule attachment 4.1/5.2 |
| Successful `/enter` extras | `max_virtual_duration_s`, `max_real_duration_s`, `remaining_real_duration_s` | CONFIRMED_BY_SPEC | Not printed by saved baseline consoles |
| Successful `/exit` extra | `exit_reason` | OBSERVED | All five successful consoles show `user_exit` |
| Unknown fields | HTTP 200 plus `accepted=false` | CONFIRMED_BY_SPEC | Attachment 5.1/5.3 |
| Malformed/type/range error | HTTP 400, action not executed | CONFIRMED_BY_SPEC | Attachment 5.3, 7.4, 8.5 |
| Timeout/connection loss | May have no JSON; execution outcome can be unknown | CONFIRMED_BY_SPEC | Attachment 4.5/5.3; not observed in saved runs |

## 3. Enumerations actually seen and specified

| Field | Value | Status | Historical evidence |
| --- | --- | --- | --- |
| `accepted` | `true` | OBSERVED indirectly | All successful actions passed the baseline client's strict check and produced action fields |
| `accepted` | `false` | OBSERVED directly | Preserved Q3-S-001 preflight response |
| `measure_result` | `direction` | OBSERVED | Printed in every Q3-S-001--005 console |
| `measure_result` | `near` | CONFIRMED_BY_SPEC | No occurrence printed in the five consoles |
| `measure_result` | `no_signal` | CONFIRMED_BY_SPEC | Baseline suppresses ordinary negative scan lines, so individual occurrences are not directly recoverable |
| `clear_result` | `success` | OBSERVED | 65 successful clears printed across five runs |
| `clear_result` | `no_target_in_range` | OBSERVED | Q3-S-004 channel 1 twice; Q3-S-005 channel 11 once |
| `exit_reason` | `user_exit` | OBSERVED | All five successful consoles |
| Other `measure_result` values | none specified | CONFIRMED_BY_SPEC | Spec enum is exactly the three above |
| Other `clear_result` values | none specified | CONFIRMED_BY_SPEC | Spec enum is exactly the two above |
| Other `exit_reason` values | none returned by `/exit` | CONFIRMED_BY_SPEC | Timeout/manual stop closes interface; no later query |

Normalization must therefore use a state/outcome distinction, not invent a
wire enum named `OUT_OF_RANGE`:

```text
success                    -> SUCCESS
no_target_in_range         -> KNOWN_NO_TARGET_IN_RANGE
accepted=false             -> REJECTED_NOT_EXECUTED
HTTP/connection ambiguity  -> RESULT_UNKNOWN
```

`KNOWN_NO_TARGET_IN_RANGE` may be promoted to the geometric fact `distance>20`
only when channel existence and not-yet-cleared state are already established.

## 4. State effects

| Event | Position | Receiver channel | Geometry/coverage/observations | Virtual time | Status |
| --- | --- | --- | --- | --- | --- |
| `/enter accepted=true` | reset `(0,0)` | reset `1` | no measurement | unchanged | CONFIRMED_BY_SPEC |
| `/measure accepted=true` | becomes requested position | becomes requested channel | commit exactly one returned observation | response-authoritative advance | CONFIRMED_BY_SPEC; increasing times observed |
| `/clear accepted=true` | becomes requested position | unchanged | clear history; geometry only under qualified failure rule | response-authoritative advance | CONFIRMED_BY_SPEC; success/failure times observed |
| `/exit accepted=true` | unchanged | unchanged | terminal journal entry | unchanged | CONFIRMED_BY_SPEC; `user_exit` observed |
| Any `accepted=false` | unchanged | unchanged | no commit | unchanged; ignore response zero | OBSERVED / CONFIRMED_BY_SPEC |
| Result unknown | unknown until same-request resolution | unknown for `/measure` | no speculative commit | retain last confirmed clock | CONFIRMED_BY_SPEC consequence |

The baseline's accepted reconnaissance endpoint was always 2273 s in the five
runs. This is consistent with its exact radius-1200 serpentine route, 5 m/s
movement, 5 s measures and 1 s channel switches; it does not validate the new
`900*sqrt(3)` route's time.

## 5. Timing mapping

| Rule | Mapping | Status |
| --- | --- | --- |
| Movement | Euclidean distance from last accepted action position divided by 5 m/s | CONFIRMED_BY_SPEC |
| Measure | movement + 5 s + 1 s iff requested channel differs from current receiver channel | CONFIRMED_BY_SPEC |
| Successful clear | movement + 5 s | CONFIRMED_BY_SPEC; consistent with saved deltas |
| `no_target_in_range` clear | movement + 3 s | CONFIRMED_BY_SPEC; consistent with saved recovery sequences |
| Clear changes receiver channel | no | CONFIRMED_BY_SPEC |
| Rejected action | no time advance | OBSERVED / CONFIRMED_BY_SPEC |
| Client-side inferred/fixed failure time | forbidden; use response clock only | Derived implementation invariant |

The plan's warning against hard-coding “failed clear = 3 seconds” is retained:
3 seconds is the current specified action-time component for an **accepted**
`no_target_in_range`, not a safe clock update for rejected, timed-out or
unknown requests.

## 6. Idempotency and retry

| Question | Mapping | Status |
| --- | --- | --- |
| Key | `request_id` within current session | CONFIRMED_BY_SPEC |
| New logical action | must use new ID | CONFIRMED_BY_SPEC |
| Network retry | reuse byte-equivalent path/payload and same ID | CONFIRMED_BY_SPEC |
| Same ID + same content | returns first complete response; no repeated action/time | CONFIRMED_BY_SPEC |
| Same ID + changed action/content | HTTP 409 | CONFIRMED_BY_SPEC |
| Concurrent new actions | forbidden | CONFIRMED_BY_SPEC |
| Historical duplicate prevention | not checkable from saved selective consoles | UNCONFIRMED |
| Number/backoff of retry attempts | not specified | UNCONFIRMED; must be configurable/finite |
| Whether a connection loss executed the action | unknown until idempotent replay resolves it | CONFIRMED_BY_SPEC consequence |

Adapter requirement: allocate and persist the request record before send;
retry only that identical record; commit the state transition once, keyed by
request ID. Never generate a new request ID merely because the response was
lost.

## 7. Observation semantics and unresolved model mapping

| Response | Protocol meaning | Safe immediate state fact | Status |
| --- | --- | --- | --- |
| `direction` | detected signal, distance `>5` and within effective receive/coverage; `svd_deg` present | channel detected; bearing wedge and positive distance bound | CONFIRMED_BY_SPEC |
| `near` | detected signal at distance `<=5`; no `svd_deg` | channel detected; clear at current point is physically within 20 m | CONFIRMED_BY_SPEC |
| `no_signal` | absent/cleared, beyond receive radius, or outside directional coverage | store immutable negative response; not absence by itself | CONFIRMED_BY_SPEC |
| `success` | specified channel source cleared | channel cleared | CONFIRMED_BY_SPEC |
| `no_target_in_range` | absent, already cleared, or distance `>20` | known unsuccessful accepted clear; no unconditional geometry fact | CONFIRMED_BY_SPEC |

**UNCONFIRMED model step:** treating every `no_signal` on a detected but
possibly directional channel as `distance > fixed R` is not justified by the
wire protocol. Likewise, seven negative fixed-node responses do not yet have
an audited directional-source absence proof. These must remain explicit model
TODOs before P0 geometry/absence implementation.

## 8. Replay checkability for Q3-S-001--005

| Replay assertion | Old artifacts |
| --- | --- |
| Locate case/log/result and parse aggregate result | CHECKABLE |
| Parse printed positive bearings and clear outcomes | CHECKABLE |
| `virtual_time_s` monotone for printed actions | CHECKABLE |
| Exact 140 fixed action schedule from code plus point headings | PARTIALLY_CHECKABLE |
| Every accepted fixed-node result and timestamp | NOT_CHECKABLE |
| Raw `accepted` semantics for successful actions | PARTIALLY_CHECKABLE (client would abort otherwise) |
| Raw request ID and idempotent duplicate commit | NOT_CHECKABLE |
| Full channel transition sequence | PARTIALLY_CHECKABLE |
| No false `ABSENT_CERTIFIED` | NOT_APPLICABLE to baseline; state did not exist |
| No illegal negative-geometry exclusion | NOT_APPLICABLE to baseline; exclusion did not exist |

New improved runs must preserve every request and complete raw response in
`actions.jsonl`; that artifact is required before C12/replay can become fully
checkable against live simulator behavior.
