from datetime import datetime, timezone

from origin import config
from origin.contract import (NETWORK_REASONS, NODE_REASONS, POD_REASONS, TIME_FMT, UTC8,
                             fmt_ts, legal_reasons)

# docs/data.md "The possible reasons": the 15 legal reasons, exactly as written
DOC_REASONS = """container CPU load · container memory load · container network latency ·
container network packet corruption · container network packet retransmission ·
container packet loss · container process termination · container read I/O load ·
container write I/O load · node CPU load · node CPU spike ·
node disk read I/O consumption · node disk space consumption ·
node disk write I/O consumption · node memory consumption"""


def test_fmt_ts_is_utc8():
    ts = datetime(2022, 3, 20, 1, 0, tzinfo=timezone.utc).timestamp()
    assert fmt_ts(ts) == "2022-03-20 09:00:00"
    assert fmt_ts(1647738540) == "2022-03-20 09:09:00"
    assert datetime.strptime(fmt_ts(1647738540), TIME_FMT).replace(tzinfo=UTC8).timestamp() == 1647738540


def test_fmt_ts_crosses_midnight_in_utc8():
    ts = datetime(2022, 3, 20, 16, 30, tzinfo=timezone.utc).timestamp()
    assert fmt_ts(ts) == "2022-03-21 00:30:00"


def test_reasons_match_docs_exactly():
    doc = {r.strip() for r in DOC_REASONS.replace("\n", " ").split("·")}
    assert len(doc) == 15
    assert set(NODE_REASONS) | set(POD_REASONS) == doc
    assert not set(NODE_REASONS) & set(POD_REASONS)
    assert set(NETWORK_REASONS) <= set(POD_REASONS)


def test_legal_reasons_per_level():
    assert legal_reasons("node") == NODE_REASONS
    assert legal_reasons("pod") == POD_REASONS
    assert legal_reasons("service") == POD_REASONS


def test_config_sane():
    assert config.TAU > 0 and config.K >= 1 and config.Z_CAP > config.TAU
    assert config.BASELINE_S == 3600 and config.EDGE_BUCKET_S == 30
    assert all(len(r) == 4 for r in config.REASON_RULES)
