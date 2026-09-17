# Engine tuning log (Person 1, Phase 4)

Every change below was decided on the **dev-tune split (49 cases) only**. The holdout (21 cases) was
never scored while tuning; the only thing it was used for is a timing run over its *instructions*
(`python -m origin.engine --split holdout`, no scoring, mean 4.2 s / max 16.6 s per case).
Person 2 folds this into `REPORT.md` → "Tuning log"; the numbers come from
`python -m eval.run_eval --config engine --split dev_tune` (`eval/results/runs.csv`).

| # | Change | Why | dev-tune before → after |
|---|---|---|---|
| 0 | starting point (CP3 merge) | — | **0.539**, 18/49 solved |
| 1 | `ONSET_SHIFT_BY_KIND = {"metric": -30, "disappear": -30}` (trace buckets unshifted) | A metric sample stamped T reports the minute *ending* at T, so a fault started in (T−60, T]; the midpoint is the honest estimate against the evaluator's 60 s tolerance. A trace bucket is already labelled with its start. Measured: a flat shift of −30 s lifts 23→25 of 38 time answers inside tolerance, −45 s and beyond collapses it (18, then 14), so the per-kind form is both better grounded and safer | 0.539 → **0.554**, 20/49 |
| 2 | `EDGE_GAP_VOTES_RETRANS`: when any node's `tcp.retrans_*` leaves its normal range, call-gap facts vote packet **corruption / retransmission / loss** over plain latency | A call-gap anomaly alone cannot tell delay from damage. Corrupted or dropped packets get retransmitted; added latency does not. On dev-tune the node retrans signal is present in **3/3 packet-corruption cases and absent in the latency case** (7 cases have it at all; in the other 4 the top reason comes from non-network evidence). Small sample, physically motivated — stated as such in REPORT | 0.554 → **0.575**, 21/49 (task_2, reason-only, 0.214 → 0.357) |
| — | `CAUSAL_DEMOTE` 0.3 → 0.5 | **Rejected.** It gains exactly one case (0.575 → 0.585) while 0.4 changes nothing and 0.6 loses a different case. That is a knife edge fitted to one dev row, not a finding, so the SPEC value stands | kept 0.3 |
| — | `SERVICE_PROMOTE_FRAC` 0.5/0.6/1.0 · `SERVICE_PROMOTE_MIN_PODS` 2/4 · `SERVICE_MEMBER_FRAC` 0.25/0.6 · `NODE_PROMOTE_WINDOW_S` 180/300 · `SIGNAL_MIN_FACTOR` 0.2/0.5 · `NODE_SINGLE_POD_FRAC` 0.3/0.8 · `SHARED_CALLEE_BONUS` 0/4 · `REASON_REST_WEIGHT` 1/4 · `CAUSAL_EARLIER_S` 60/180 | **All swept, none adopted**: every neighbour of the current value scores the same or worse. The parameters are at a local optimum rather than on a cliff, which is the more reassuring of the two for a different deployment | kept |

## Engine failure taxonomy (dev-tune, at 0.539; the first thing wrong per case)

| bucket | cases | notes |
|---|---|---|
| wrong reason | 12 | network group 4 · node group 3 · process termination 2 · other 3 |
| wrong component **level** (node vs pod vs service) | 10 | every component error was a level error, never an unrelated component — the right *family* is usually found |
| time only | 9 | offsets were −1256 s … +1336 s, but 4 of them sat at +75 … +109 s, which is what change 1 addresses |
| wrong count | 0 | the instruction parser has never missed a count on any of the 70 dev cases |

## What the engine is blind to, and why we say so rather than guess

- **`container process termination`** (3/55 dev reasons): invisible in this bundle. For both dev-tune cases
  that have it, no metric series stops or gaps, `container_start_time_seconds` never changes, per-pod span
  counts hold, and `log_service.csv` has no error lines in the window. The disappearance rule is
  implemented and unit-tested; it fires on no dev case.
- **`node disk space consumption`** (4/55): `system.disk.used` on the busiest node swings from 3.6 GB to
  9.7 GB *inside the baseline hour*, so a fault that consumes disk hides inside normal variation. Detrending
  it is the obvious next step and was not attempted before the freeze.
- **The same component failing twice** in one window (1 of 7 multi-failure dev-tune cases, e.g. read I/O then
  write I/O on one service): `engine_answers` picks distinct candidates, so it cannot express that. Left
  alone deliberately — fixing it for 1 case risks the other 6.
- **`metric_mesh` and `log_proxy`** are never read (`log_proxy` is 2.9 GB/day and was not even unzipped).
