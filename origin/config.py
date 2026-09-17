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
# reason table: filled in Phase 3 from docs/data-notes.md kpi lists
REASON_RULES: list[tuple[str, str, str, float]] = []   # (level, regex on kpi, reason, weight)

# --- PERSON 2 ---  (model tiers / budget constants appended below this line)
