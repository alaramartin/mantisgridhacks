# The data

What's in your bundle, and which columns lie to you. Measured against the real files.

## What you have

One bundle, `Market-cloudbed-1` — see `GET_DATA.md`. It's a real microservice system
(an online shop), instrumented, with faults injected and labelled by the operators who
ran it. It comes from **OpenRCA** (Microsoft, ICLR 2025), built on the CCF AIOps
Challenge; licence and credits in `../ATTRIBUTION.md`.

```
data/Market-cloudbed-1/
├── query.csv            70 cases: task_index, instruction
├── dev/query_dev.csv    the same 70, plus scoring_points -- the answers
├── manifest.json
└── telemetry/
    ├── 2022_03_20/  { metric/, log/, trace/ }
    └── 2022_03_21/
```

You have every answer. **We don't score you on this deployment**: we score on another
deployment of the same shop — the same software and the same kinds of failure, but a
different set of components, many of which you won't have seen — on 20 of its cases,
and we don't say which 20. So these
70 cases are yours to develop against; tune on all of them and hold some back if you
want an honest estimate before we measure it.

## A case

One row of `query.csv`:

```
task_index:  task_6
instruction: "The cloud service system, cloudbed-1, experienced one failure within the
              time range of March 20, 2022, from 09:00 to 09:30. The specific component
              responsible for this failure and the underlying reason are currently
              unknown. You are tasked with identifying the root cause component and the
              root cause reason."
```

The answer to that one is `shippingservice-1` / `container read I/O load`.

Every instruction gives you **a 30-minute window** and **how many failures are in it**.
Both are free information, and the count matters a lot — see `docs/scoring.md`.

Seven task types, differing only in which of the three answers they ask for:

| Task | Time | Component | Reason | Difficulty |
|---|---|---|---|---|
| task_1 | ✓ | | | easy |
| task_2 | | | ✓ | easy |
| task_3 | | ✓ | | easy |
| task_4 | ✓ | | ✓ | middle |
| task_5 | ✓ | ✓ | | middle |
| task_6 | | ✓ | ✓ | middle |
| task_7 | ✓ | ✓ | ✓ | **hard** |

**Parse `query.csv` with a CSV reader**, never `wc -l` or line splitting — the
`instruction` text contains newlines.

## The telemetry

| File | Columns | Rows/day | Size/day |
|---|---|---|---|
| `metric/metric_container.csv` | `timestamp,cmdb_id,kpi_name,value` | 3.7 M | 265 MB |
| `metric/metric_mesh.csv` | `timestamp,cmdb_id,kpi_name,value` | 2.5 M | 247 MB |
| `metric/metric_node.csv` | `timestamp,cmdb_id,kpi_name,value` | 488 K | 21 MB |
| `metric/metric_runtime.csv` | `timestamp,cmdb_id,kpi_name,value` | 959 K | 88 MB |
| `metric/metric_service.csv` | `service,timestamp,rr,sr,mrt,count` | 16 K | 1 MB |
| `log/log_service.csv` | `log_id,timestamp,cmdb_id,log_name,value` | 4.6 M | 672 MB |
| `log/log_proxy.csv` | `log_id,timestamp,cmdb_id,log_name,value` | 7.9 M | 2.9 GB |
| `trace/trace_span.csv` | `timestamp,cmdb_id,span_id,trace_id,duration,type,status_code,operation_name,parent_span` | 9.1 M | 1.3 GB |

Distinct values, one day:

```
metric_container   42 cmdb_id    64 kpi_name    e.g. node-5.adservice-2
metric_mesh       176 cmdb_id   125 kpi_name    e.g. adservice-0.destination.frontend.adservice
metric_node         6 cmdb_id    59 kpi_name    e.g. node-1
metric_runtime      2 cmdb_id   333 kpi_name    e.g. adservice.ts:8088
trace_span         40 cmdb_id    27 operation_name, 5 type, 4 status_code
log_service        25 cmdb_id     9 log_name
```

**The topology is in the names.** `node-5.adservice-2` is the second pod of `adservice`,
running on `node-5`. Several pods make up one service, which is why a single pod's fault
may not show at service level at all.

## Traps

**Time units are mixed.** Metrics and logs are in **seconds**; traces are in
**milliseconds**. Join them without converting and you're off by 1000×. This is the
single most expensive mistake available in this data.

**Everything is UTC+8.** Every timestamp in the answers is UTC+8. Parse with your local
timezone and every answer is hours off — against a 60-second tolerance.

**There's no data point at the exact fault time.** Telemetry is sampled at intervals and
the true time usually falls between samples. Look for where behaviour changes, not for
an exact match.

**Network faults barely show in metrics.** You need the latency between parent and child
spans in the traces. About a third of the reasons are network faults, so an agent that
only reads metrics caps itself well below the ceiling.

**Some windows contain more than one failure.** Independent faults that happen to share
a half-hour. Report them in chronological order.

**The files are big.** `trace_span.csv` is about 1.3 GB a day and `log_proxy.csv` 2.9 GB.
A naive `pd.read_csv` on the wrong one will hang your laptop. Filter to the 30-minute
window first.

**`metric_mesh.cmdb_id` names two components.**
`adservice-0.destination.frontend.adservice` is the source *and* the destination.

**`metric_mesh.kpi_name` is quoted and contains commas.**
`"istio_tcp_connections_closed.UF,…"` — splitting on commas shears these rows.

**`trace_span` fields aren't uniform.** `type` is mostly `rpc`, plus `telemetry`, `db`,
`http` and empty; `status_code` is mostly `0`, but `Ok` on db spans.

## The possible reasons

`reason` is effectively multiple choice. For Market, these 15, exactly as written:

`container CPU load` · `container memory load` · `container network latency` ·
`container network packet corruption` · `container network packet retransmission` ·
`container packet loss` · `container process termination` · `container read I/O load` ·
`container write I/O load` · `node CPU load` · `node CPU spike` ·
`node disk read I/O consumption` · `node disk space consumption` ·
`node disk write I/O consumption` · `node memory consumption`

Knowing the label set isn't cheating — an SRE knows what can break. Working out *which*
component and *when* is the task.

## Upstream

- Repo: `github.com/microsoft/OpenRCA` (MIT). Its baseline agent, in
  `rca/baseline/rca_agent/`, is worth reading before you design your own, and you may
  use it as a starting point.
- Paper: *OpenRCA: Can Large Language Models Locate the Root Cause of Software
  Failures?*, ICLR 2025.

**Don't download the upstream dataset.** It contains the answers to the cases we
evaluate on.

---
