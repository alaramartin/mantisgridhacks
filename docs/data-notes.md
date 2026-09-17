# Data notes — Market-cloudbed-1 (Person 1)

Measured on the real files with `python eval/verify_traps.py` (re-runnable; ~12 s,
never full-reads traces or logs). The full output for `2022_03_20` is below the summary.

## Summary and decisions for Checkpoint 1

| Question | Finding | Consequence |
|---|---|---|
| Times UTC+8? | **Yes.** For 3 dev answers on pods/nodes, the answer time read as UTC+8 lands within ~5 min of a capped (z = 50) change on the answer component; the same check 8 h earlier/later shows only noise (z 4–14). Answer day = telemetry folder date in UTC+8. All 55 answer times in the 70 dev cases fall inside their instruction window parsed as UTC+8, and in a telemetry folder from `case.days`. | `case.py` builds datetimes with `tzinfo=UTC8`. |
| Timestamp units | Metrics, logs (`log_service`, `log_proxy`): integer **seconds** (~1.65e9). `trace_span.timestamp`: integer **milliseconds** (~1.65e12). | Divide trace ts by 1000 once, at load. |
| Trace `duration` unit | **Microseconds.** Median 3,007, p99 65,876. In a contiguous block, 99.9% of children start within `parent.duration / 1000` ms of their parent, and 100% of child durations ≤ parent durations. | `parent_ms = duration / 1000`. |
| Sampling interval | `metric_container` 60 s (all 2,576 series). `metric_node` 60 s (339 series) and 300 s (12 series). `metric_service` 60 s. | k = 2 samples ≈ 2 min; disappearance uses each series' own median interval. |
| Sorted by time? | `metric_node.csv`: **fully sorted**. `trace_span.csv`: **9–10 concatenated shards, each time-sorted** (≈5 covering 00:00–08:00 and ≈5 covering 08:00–24:00, in byte-order that differs by day). `metric_container`, `metric_mesh`, `metric_runtime`, `metric_service`: **grouped by series, not by time** (~250–500 runs at 1,024 probes). `log_service.csv`: **~420 runs, not sorted**. | Loader: `trace_span` → find shard boundaries (backward jumps), binary-search **inside each shard**, read only the matching byte ranges. `metric_node` → seek. `metric_container` / `metric_service` (278 MB / 1 MB) → **read once per day** with `usecols` + categories and cache in-process, then filter. `log_service` → chunked (and first on the cut list). |
| Answer component forms (54 labels) | **node `node-N`: 20 · pod `name-N`: 10 · bare service `name`: 24.** | **Service-level candidates are needed** (44% of component labels). A service candidate aggregates its pods and `metric_service`. |
| Reasons (55 labels) | container CPU load 8 · container read I/O load 6 · container network packet retransmission 5 · container memory load 5 · container network latency 5 · node disk read I/O consumption 4 · node disk space consumption 4 · node memory consumption 3 · container network packet corruption 3 · node CPU load 3 · container process termination 3 · node disk write I/O consumption 2 · container write I/O load 2 · node CPU spike 1 · container packet loss 1 | Network reasons 14/55 (25%). Node reasons 17/55. |
| Failures per case | 1: 44 cases · 2: 26 cases | `n_failures` parsed and checked against all 70 answers (`tests/test_case.py`). |

## Other findings

- **Pod names include a second deployment per service**: `adservice2-0`, `cartservice2-0`, … and `redis-cart-0` / `redis-cart2-0`.
  `pod → service` by stripping `-\d+$` gives `adservice2` for `adservice2-0` — **open question for Phase 2**:
  whether `adservice2` should map to service `adservice` (strip a trailing digit too). Decide from how service
  labels relate to pods, without naming components in code.
- `metric_container.cmdb_id` is always `<node>.<pod>` (42 ids, no id without a `.`). Nodes: `node-1` … `node-6`.
- `metric_service.service` has a `-grpc` or `-http` suffix (`adservice` has both). Strip it to get the service.
- `trace_span` (100 k sample): `type` rpc 69% · telemetry 13% · http 8% · empty 6% · db 4%.
  `status_code` `0` 89% · `Ok` 4% · `200` 4% · `OK` 3% → **no error codes in the sample**; treat anything outside
  `{0, Ok, OK, 200, ""}` as an error. `parent_span` empty for 4.5% (roots). 40 pods emit spans (no `redis-cart`).
- `log_service.log_name` = `log_<service>-service_application`; `value` looks like `severity: info, message: …`.
  `log_proxy.csv` (envoy access logs) was **not unzipped** to save 6.5 GB of disk; it is never read. It is still in
  `data/track-1-Market-cloudbed-1.zip` (`unzip data/track-1-Market-cloudbed-1.zip '*/log_proxy.csv' -d data`).
- `query_dev.csv` instructions contain no newlines in this bundle, but parse with `pd.read_csv` anyway.

## Instruction wording (for `origin/case.py`)

- Failure count phrases seen: `one failure`, `a failure`, `a single failure`, `two failures` (verbs: experienced / encountered).
- The **last sentence** is the request and names exactly the asked fields ("Please pinpoint the root cause occurrence
  datetime.", "…identify the root cause component and the root cause reason."). Earlier sentences say what is unknown and
  can mention other words, so `asks` is read from the last sentence only. Verbs vary (identify / determine / pinpoint), so
  no verb list is used. "occurrence time" and "occurrence datetime" both mean `datetime`.
- Checked on all 70: every task type gives one `asks` pattern matching `docs/data.md`, and `n_failures` equals the answer count.

---

# Full `verify_traps.py` output (2022_03_20)

# Trap verification — data/Market-cloudbed-1 / 2022_03_20

## 2. Sortedness by timestamp (1024 evenly spaced byte offsets; a new run starts at a backward jump > 120 s)

A file with few runs, each sorted, can be binary-searched run by run; a file with
many runs (grouped by series) cannot.

| file | size MB | sampled time range | backward jumps | sorted runs (byte fraction: time range) |
|---|---|---|---|---|
| log_service.csv | 705 | 00:00–23:57 | 417 | 418 runs (not time-sorted) |
| metric_container.csv | 278 | 00:03–23:59 | 497 | 498 runs (not time-sorted) |
| metric_mesh.csv | 259 | 00:02–23:59 | 472 | 473 runs (not time-sorted) |
| metric_node.csv | 22 | 00:00–23:58 | 0 | 0.000–0.999: 00:00–23:58 |
| metric_runtime.csv | 93 | 00:00–23:59 | 487 | 488 runs (not time-sorted) |
| metric_service.csv | 1 | 00:01–23:59 | 250 | 251 runs (not time-sorted) |
| trace_span.csv | 1,357 | 00:00–23:55 | 8 | 0.000–0.032: 00:00–07:50<br>0.033–0.065: 00:04–07:54<br>0.066–0.099: 00:08–07:59<br>0.100–0.131: 00:14–07:50<br>0.132–0.331: 00:04–23:55<br>0.332–0.498: 08:09–23:52<br>0.499–0.665: 08:06–23:52<br>0.666–0.832: 08:07–23:46<br>0.833–0.999: 08:01–23:46 |

## 3. UTC+8 check

- row 8 · answer `2022-03-20 13:13:19` UTC+8 → epoch 1647753199; inside the instruction window (parsed as UTC+8): **True**; day folder `2022_03_20` exists: **True**
    - UTC+8 reading: z 50.0 (capped at 50) on `node-2` · `system.io.avg_q_sz`: value 13.51 at 2022-03-20 13:17:00 (ts 1647753420) vs baseline median 0
    - 8 h earlier: z 7.2 (capped at 50) on `node-2` · `system.cpu.user`: value 3.69 at 2022-03-20 05:18:00 (ts 1647724680) vs baseline median 1.24
    - 8 h later: z 14.0 (capped at 50) on `node-2` · `system.io.avg_q_sz`: value 0.14 at 2022-03-20 21:11:00 (ts 1647781860) vs baseline median 0
- row 13 · answer `2022-03-20 16:31:44` UTC+8 → epoch 1647765104; inside the instruction window (parsed as UTC+8): **True**; day folder `2022_03_20` exists: **True**
    - UTC+8 reading: z 50.0 (capped at 50) on `node-6.currencyservice-0` · `container_fs_reads./dev/vda`: value 13.5 at 2022-03-20 16:36:00 (ts 1647765360) vs baseline median 0
    - 8 h earlier: z 4.0 (capped at 50) on `node-6.currencyservice-0` · `container_cpu_system_seconds`: value 0.03 at 2022-03-20 08:30:00 (ts 1647736200) vs baseline median 0.02
    - 8 h later: no series with data
- row 25 · answer `2022-03-20 23:09:26` UTC+8 → epoch 1647788966; inside the instruction window (parsed as UTC+8): **True**; day folder `2022_03_20` exists: **True**
    - UTC+8 reading: z 50.0 (capped at 50) on `node-5.checkoutservice-2` · `container_cpu_cfs_throttled_periods`: value 243.333 at 2022-03-20 23:13:00 (ts 1647789180) vs baseline median 0.666667
    - 8 h earlier: z 5.2 (capped at 50) on `node-5.checkoutservice-2` · `container_network_transmit_MB.eth0`: value 2.27103 at 2022-03-20 15:07:00 (ts 1647760020) vs baseline median 1.80429
    - 8 h later: no series with data

## 4. Units (trace vs metric timestamps, trace duration)

- trace_span.timestamp median 1647756941636 (≈1.65e+12) → milliseconds; as seconds/1000: 2022-03-20 14:15:41 UTC+8
- metric_container.timestamp median 1647761340 (≈1.65e+09) → seconds
- trace_span.duration over 100,000 sampled rows: median 3,007, p90 6,873, p99 65,876, max 12,972,826
- parent/child pairs in a contiguous 300 k-row block: 57,376
  - child starts within parent if duration is **µs** (≤ duration/1000 ms after parent start): 99.9%
  - child duration ≤ parent duration: 100.0%
  - median child start offset 1 ms vs median parent duration 6,933 (unit under test)

## 5. Sampling interval (median diff between consecutive timestamps of one series)

- metric_container.csv: median diff 60 s over all series; per-series medians: {60.0: 2576}
- metric_node.csv: median diff 60 s over all series; per-series medians: {60.0: 339, 300.0: 12}
- metric_service.csv: median diff 60 s over all series; per-series medians: {60.0: 11}

## 1. Headers and first rows (head -c 2000, first 3 lines)

### log/log_service.csv  (705 MB) — timestamp: `1647705660` (integer, seconds)
```
log_id,timestamp,cmdb_id,log_name,value
Fovpon8BDiVcQfZwJ5a9,1647705660,currencyservice-1,log_currencyservice-service_application,"severity: info, message: conversion request successful"
GIvpon8BDiVcQfZwJ5a9,1647705660,currencyservice-0,log_currencyservice-service_application,"severity: info, message: Getting supported currencies..."
HYvpon8BDiVcQfZwJ5a9,1647705660,currencyservice-2,log_currencyservice-service_application,"severity: info, message: received conversion request"
```
### metric/metric_container.csv  (278 MB) — timestamp: `1647759600` (integer, seconds)
```
timestamp,cmdb_id,kpi_name,value
1647759600,node-6.adservice2-0,container_network_receive_packets_dropped.eth0,0.0
1647759660,node-6.adservice2-0,container_network_receive_packets_dropped.eth0,0.0
1647759720,node-6.adservice2-0,container_network_receive_packets_dropped.eth0,0.0
```
### metric/metric_mesh.csv  (259 MB) — timestamp: `1647777600` (integer, seconds)
```
timestamp,cmdb_id,kpi_name,value
1647777600,istio-egressgateway-7bfdcc9d86-zpjpg,istio_agent_startup_duration_seconds,2.573041117
1647777660,istio-egressgateway-7bfdcc9d86-zpjpg,istio_agent_startup_duration_seconds,2.573041117
1647777720,istio-egressgateway-7bfdcc9d86-zpjpg,istio_agent_startup_duration_seconds,2.573041117
```
### metric/metric_node.csv  (22 MB) — timestamp: `1647705600` (integer, seconds)
```
timestamp,cmdb_id,kpi_name,value
1647705600,node-1,system.cpu.iowait,0.31
1647705600,node-1,system.net.packets_out.error,0.0
1647705600,node-5,system.net.udp.in_errors,0.0
```
### metric/metric_runtime.csv  (93 MB) — timestamp: `1647759600` (integer, seconds)
```
timestamp,cmdb_id,kpi_name,value
1647759600,adservice.ts:8088,java_nio_BufferPool_TotalCapacity.direct,57343.0
1647759660,adservice.ts:8088,java_nio_BufferPool_TotalCapacity.direct,57343.0
1647759720,adservice.ts:8088,java_nio_BufferPool_TotalCapacity.direct,57343.0
```
### metric/metric_service.csv  (1 MB) — timestamp: `1647716400` (integer, seconds)
```
service,timestamp,rr,sr,mrt,count
adservice-grpc,1647716400,100.0,100.0,2.429508196728182,61
adservice-grpc,1647716460,100.0,100.0,2.429508196728182,61
adservice-grpc,1647716520,100.0,100.0,2.332967032959869,91
```
### trace/trace_span.csv  (1,357 MB) — timestamp: `1647705600395` (integer, milliseconds)
```
timestamp,cmdb_id,span_id,trace_id,duration,type,status_code,operation_name,parent_span
1647705600395,currencyservice-1,cf4f12dee7b2b1d8,7b532f0b62717b83b9d3ff72e97447c2,120,telemetry,0,grpc.hipstershop.CurrencyService/Convert,dc3292f5e193a9a3
1647705600361,frontend-0,a652d4d10e9478fc,9451fd8fdf746a80687451dae4c4e984,49877,rpc,0,hipstershop.CheckoutService/PlaceOrder,952754a738a11675
1647705600416,frontend-0,bb220a9318fcb31c,9451fd8fdf746a80687451dae4c4e984,7614,rpc,0,hipstershop.ProductCatalogService/GetProduct,952754a738a11675
```

## 6. Distinct values

### metric_container.csv: 42 cmdb_id, 64 kpi_name
cmdb_id examples: `node-5.adservice-2`, `node-5.cartservice2-0`, `node-5.checkoutservice-2`, `node-5.frontend-1`, `node-5.frontend-2`, `node-5.shippingservice-2`, `node-6.adservice-0`, `node-6.adservice-1`
cmdb_id without a `.` (not `<node>.<pod>`): none
pods (42): adservice-0, adservice-1, adservice-2, adservice2-0, cartservice-0, cartservice-1, cartservice-2, cartservice2-0, checkoutservice-0, checkoutservice-1, checkoutservice-2, checkoutservice2-0, currencyservice-0, currencyservice-1, currencyservice-2, currencyservice2-0, emailservice-0, emailservice-1, emailservice-2, emailservice2-0, frontend-0, frontend-1, frontend-2, frontend2-0, paymentservice-0, paymentservice-1, paymentservice-2, paymentservice2-0, productcatalogservice-0, productcatalogservice-1, productcatalogservice-2, productcatalogservice2-0, recommendationservice-0, recommendationservice-1, recommendationservice-2, recommendationservice2-0, redis-cart-0, redis-cart2-0, shippingservice-0, shippingservice-1, shippingservice-2, shippingservice2-0

kpi_name:
```
container_cpu_cfs_periods
container_cpu_cfs_throttled_periods
container_cpu_cfs_throttled_seconds
container_cpu_load_average_10s
container_cpu_system_seconds
container_cpu_usage_seconds
container_cpu_user_seconds
container_file_descriptors
container_fs_inodes./dev/vda1
container_fs_inodes_free./dev/vda1
container_fs_io_current./dev/vda1
container_fs_io_time_seconds./dev/vda1
container_fs_io_time_weighted_seconds./dev/vda1
container_fs_limit_MB./dev/vda1
container_fs_read_seconds./dev/vda1
container_fs_reads./dev/vda
container_fs_reads./dev/vda1
container_fs_reads_MB./dev/vda
container_fs_reads_merged./dev/vda1
container_fs_sector_reads./dev/vda1
container_fs_sector_writes./dev/vda1
container_fs_usage_MB./dev/vda1
container_fs_write_seconds./dev/vda1
container_fs_writes./dev/vda
container_fs_writes./dev/vda1
container_fs_writes_MB./dev/vda
container_fs_writes_merged./dev/vda1
container_last_seen
container_memory_cache
container_memory_failcnt
container_memory_failures.container.pgfault
container_memory_failures.container.pgmajfault
container_memory_failures.hierarchy.pgfault
container_memory_failures.hierarchy.pgmajfault
container_memory_mapped_file
container_memory_max_usage_MB
container_memory_rss
container_memory_swap
container_memory_usage_MB
container_memory_working_set_MB
container_network_receive_MB.eth0
container_network_receive_errors.eth0
container_network_receive_packets.eth0
container_network_receive_packets_dropped.eth0
container_network_transmit_MB.eth0
container_network_transmit_errors.eth0
container_network_transmit_packets.eth0
container_network_transmit_packets_dropped.eth0
container_sockets
container_spec_cpu_period
container_spec_cpu_quota
container_spec_cpu_shares
container_spec_memory_limit_MB
container_spec_memory_reservation_limit_MB
container_spec_memory_swap_limit_MB
container_start_time_seconds
container_tasks_state.iowaiting
container_tasks_state.running
container_tasks_state.sleeping
container_tasks_state.stopped
container_tasks_state.uninterruptible
container_threads
container_threads_max
container_ulimits_soft.max_open_files
```
### metric_node.csv: 6 cmdb_id, 59 kpi_name
cmdb_id examples: `node-1`, `node-2`, `node-3`, `node-4`, `node-5`, `node-6`

kpi_name:
```
ping.can_connect
system.cpu.iowait
system.cpu.pct_usage
system.cpu.system
system.cpu.user
system.disk.free
system.disk.pct_usage
system.disk.readonly
system.disk.total
system.disk.used
system.fs.inodes.free
system.fs.inodes.in_use
system.fs.inodes.total
system.fs.inodes.used
system.io.avg_q_sz
system.io.await
system.io.r_await
system.io.r_s
system.io.rkb_s
system.io.svctm
system.io.util
system.io.w_await
system.io.w_s
system.load.1
system.load.15
system.load.5
system.mem.free
system.mem.pct_usage
system.mem.real.pct_useage
system.mem.real.used
system.mem.total
system.mem.usable
system.mem.used
system.net.bytes_rcvd
system.net.bytes_sent
system.net.packets_in.count
system.net.packets_in.error
system.net.packets_out.count
system.net.packets_out.error
system.net.tcp.in_segs
system.net.tcp.out_segs
system.net.tcp.retrans_segs
system.net.udp.in_datagrams
system.net.udp.in_errors
system.net.udp.out_datagrams
system.net.udp.rcv_buf_errors
system.net.udp.snd_buf_errors
system.os.nofile.current
system.os.nofile.max
system.os.nofile.used_pct
system.process.zombie.num
system.swap.free
system.swap.si
system.swap.so
system.swap.total
system.swap.used
system.swap.used_pct
system.tcp.retrans_pct
system.udp.connect.num
```
### metric_service.csv service values
['adservice-grpc', 'adservice-http', 'cartservice-grpc', 'checkoutservice-grpc', 'currencyservice-grpc', 'emailservice-grpc', 'frontend-http', 'paymentservice-grpc', 'productcatalogservice-grpc', 'recommendationservice-grpc', 'shippingservice-grpc']

### trace_span (100 k-row sample)
- type: {'rpc': 69073, 'telemetry': 12586, 'http': 7978, '<empty>': 6005, 'db': 4358}
- status_code: {'0': 89215, 'Ok': 4358, '200': 3878, 'OK': 2549}
- cmdb_id (40): ['adservice-0', 'adservice-1', 'adservice-2', 'adservice2-0', 'cartservice-0', 'cartservice-1', 'cartservice-2', 'cartservice2-0', 'checkoutservice-0', 'checkoutservice-1', 'checkoutservice-2', 'checkoutservice2-0', 'currencyservice-0', 'currencyservice-1', 'currencyservice-2', 'currencyservice2-0', 'emailservice-0', 'emailservice-1', 'emailservice-2', 'emailservice2-0', 'frontend-0', 'frontend-1', 'frontend-2', 'frontend2-0', 'paymentservice-0', 'paymentservice-1', 'paymentservice-2', 'paymentservice2-0', 'productcatalogservice-0', 'productcatalogservice-1', 'productcatalogservice-2', 'productcatalogservice2-0', 'recommendationservice-0', 'recommendationservice-1', 'recommendationservice-2', 'recommendationservice2-0', 'shippingservice-0', 'shippingservice-1', 'shippingservice-2', 'shippingservice2-0']
- parent_span empty/NaN: 4.5%

### log_service.csv (50 k-row sample)
- log_name: {'log_cartservice-service_application': 23609, 'log_currencyservice-service_application': 14165, 'log_frontend-service_application': 8153, 'log_recommendationservice-service_application': 1980, 'log_shippingservice-service_application': 1433, 'log_checkoutservice-service_application': 294, 'log_paymentservice-service_application': 200, 'log_emailservice-service_application': 142, 'log_redis-cart-service_application': 24}
- cmdb_id examples: ['cartservice-0', 'cartservice-1', 'cartservice-2', 'checkoutservice-0', 'checkoutservice-1', 'checkoutservice-2', 'currencyservice-0', 'currencyservice-1', 'currencyservice-2', 'emailservice-0']

## 7. Answer forms in dev/query_dev.csv (label shape only, no names copied into code)

- component forms (54 labels): {'pod (`name-N`)': 10, 'node (`node-N`)': 20, 'service (bare `name`, no trailing -N)': 24}
  - bare-service labels that also exist as a pod prefix in the labels: 5/9 distinct
- reasons (55 labels; component labels 54: they differ because tasks ask different fields):
  - container CPU load: 8
  - container read I/O load: 6
  - container network packet retransmission: 5
  - container memory load: 5
  - container network latency: 5
  - node disk read I/O consumption: 4
  - node disk space consumption: 4
  - node memory consumption: 3
  - container network packet corruption: 3
  - node CPU load: 3
  - container process termination: 3
  - node disk write I/O consumption: 2
  - container write I/O load: 2
  - node CPU spike: 1
  - container packet loss: 1
- failures per case: {1: 44, 2: 26}
- task_index counts: {'task_1': 12, 'task_2': 10, 'task_3': 8, 'task_4': 7, 'task_5': 10, 'task_6': 12, 'task_7': 11}

_verify_traps.py ran in 13 s_
