# ---- fixed parameters (SPEC "Fixed parameters"); change only from dev-tune, log in REPORT.md ----
TAU = 3.0
K = 2
Z_CAP = 50.0
IQR_FLOOR_FRAC = 0.05
MIN_BASE_SAMPLES = 5
BASELINE_S = 3600             # 60 min before the window
READ_PAD_S = 120              # slack around every time filter
EDGE_BUCKET_S = 30
DISAPPEAR_MIN_BASE = 10       # baseline samples before "missing" means anything
CAUSAL_EARLIER_S = 60         # dependency must be this much earlier to demote
CAUSAL_DEMOTE = 0.3
NODE_PROMOTE_MIN_PODS = 2
NODE_PROMOTE_WINDOW_S = 120
SPIKE_MAX_SAMPLES = 3         # node CPU breach this short = "node CPU spike"
MULTI_FAILURE_SEP_S = 300     # for n >= 2, prefer candidates with onsets this far apart
MAX_CANDIDATES = 15
ONSET_SHIFT_S = 0             # PLACEHOLDER: dev-tune may set -30; log it
METRIC_SOURCES = ("metric_container", "metric_node", "metric_service")
LOAD_LOGS = True              # log_service error lines (cut-order #1): ~11 s once per day, then cached
# reason table (docs/data-notes.md kpi lists): (level, regex on the raw kpi_name, reason, weight).
# First matching rule per (level, kpi) wins, case-insensitive. Services use the pod rules plus their own.
# "node CPU load" becomes "node CPU spike" in signals.py when the breach is <= SPIKE_MAX_SAMPLES long.
# A kpi matching no rule (or reason None) gets no vote but still counts as support.
REASON_RULES: list[tuple[str, str, str | None, float]] = [
    # pods (metric_container)
    ("pod", r"^container_spec_|_limit|_max$|threads_max|ulimits", None, 0.0),   # configuration, not load
    ("pod", r"fs_(sector_)?reads|fs_read_seconds", "container read I/O load", 1.0),
    ("pod", r"fs_(sector_)?writes|fs_write_seconds|fs_usage", "container write I/O load", 1.0),
    ("pod", r"fs_io_", "container read I/O load", 0.3),
    ("pod", r"memory", "container memory load", 1.0),
    ("pod", r"cpu", "container CPU load", 1.0),
    ("pod", r"network_.*dropped", "container packet loss", 0.8),
    ("pod", r"network_.*errors", "container network packet corruption", 0.6),
    ("pod", r"network_(receive|transmit)", "container network latency", 0.2),
    ("pod", r"threads|processes|file_descriptors|sockets|last_seen|start_time|tasks_state",
     "container process termination", 0.6),
    # services (metric_service: rr request rate, sr success rate, mrt mean response time, count)
    ("service", r"^mrt$", "container network latency", 0.3),
    ("service", r"^sr$", "container packet loss", 0.2),
    # nodes (metric_node)
    ("node", r"^system\.(cpu|load)\.", "node CPU load", 1.0),
    ("node", r"^system\.(mem|swap)\.", "node memory consumption", 1.0),
    ("node", r"^system\.io\.(r_s|rkb_s|r_await)$", "node disk read I/O consumption", 1.0),
    ("node", r"^system\.io\.(w_s|wkb_s|w_await)$", "node disk write I/O consumption", 1.0),
    ("node", r"^system\.(disk\.(used|free|pct_usage)|fs\.inodes\.(used|free|in_use))", "node disk space consumption", 1.0),
    ("node", r"^system\.io\.", "node disk read I/O consumption", 0.3),   # util / await / queue: generic disk
]
# votes that don't come from a kpi_name (signals.py)
EDGE_GAP_VOTES = {"container network latency": 1.0, "container network packet retransmission": 0.3}
EDGE_ERROR_VOTES = {"container packet loss": 0.6, "container network packet corruption": 0.4,
                    "container network packet retransmission": 0.4}
DISAPPEAR_VOTES = {"container process termination": 1.5}
EDGE_MIN_BASE_CALLS = 20      # an edge needs this many baseline calls to be scored
BASE_RANGE_GUARD = True       # P1 addition: a breach must also leave the baseline's own [min, max]

# --- PERSON 2 ---  (model tiers / budget constants appended below this line)
