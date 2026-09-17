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
# reason table: filled in Phase 3 from docs/data-notes.md kpi lists
REASON_RULES: list[tuple[str, str, str, float]] = []   # (level, regex on kpi, reason, weight)

# --- PERSON 2 ---  (model tiers / budget constants appended below this line)

# tiers confirmed by the CP1 spike (docs/model-findings.md): 4.7-Flash parsed 4/4 at
# ~90 output tokens and 2.4-3.7 s; 5.3-Flash only 2/4 (it rambles past the JSON), so it
# is the availability fallback, never the first choice. GLM-5.3 exists on Featherless
# but is NOT in cost.py's PRICES and would raise KeyError -- never call it.
CHEAP = ["zai-org/GLM-4.7-Flash", "zai-org/GLM-5.3-Flash"]
STRONG = ["zai-org/GLM-5.2", "zai-org/GLM-5.1"]     # 5.2: 1.5-17 s, ~45 out tok, 4/4
CHEAP_MAX_TOKENS = 700          # measured worst case 95 with thinking off; 700 is slack
STRONG_MAX_TOKENS = 700         # was 4000 for thinking-on; CP1 turned thinking OFF
CALL_TIMEOUT_S = 25
CASE_SOFT_DEADLINE_S = 45
STRONG_MIN_REMAINING_S = 20
RUN_AVG_LIMIT_S = 50            # above this running average, go engine-only
GATE_MARGIN = 0.35
GATE_SUPPORT = 2
ESCALATE_MARGIN = 0.15
FACTS_MAX = 40
CANDIDATES_SHOWN = 8
# CONFIRMED at CP1, not a placeholder. Pass this as extra_body on EVERY model call.
# With thinking on, all four models spend the whole output budget narrating and get cut
# off mid-JSON: 0/4 parsed at a 1200-token cap. With it off: 12/16 parsed, 1.5-4 s.
# The other documented switch, {"thinking": {"type": "disabled"}}, is silently ignored.
THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
