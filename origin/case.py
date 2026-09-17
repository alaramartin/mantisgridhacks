"""Stage 0: parse a case instruction into a Case. No LLM.

The window in the instruction is local shop time, UTC+8 (docs/data.md "Traps").
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from origin.config import BASELINE_S
from origin.contract import UTC8, Case

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}

WORDS = {"one": 1, "a single": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# Same shape as the starter's agents/heuristic.py::parse_window (the second bound
# may name its own date), but the result is built in UTC+8, not UTC.
_WINDOW = re.compile(r"(\w+)\s+(\d{1,2}),?\s+(\d{4}).{0,40}?(\d{1,2}):(\d{2})"
                     r"\s*(?:to|-|and|until)\s*.{0,40}?(\d{1,2}):(\d{2})", re.I | re.S)
_SECOND_DATE = re.compile(r"(?:to|-|and|until)\s*(\w+)\s+(\d{1,2}),?\s+(\d{4})", re.I)
_COUNT = re.compile(r"\b(one|a single|two|three|four|five|\d+)\s+failures?\b")


def _window(instruction: str, notes: list[str]) -> tuple[datetime, datetime]:
    m = _WINDOW.search(instruction)
    if not m or m.group(1).lower() not in MONTHS:
        raise ValueError("could not parse a time window from the instruction")
    mon, day, year, h1, m1, h2, m2 = m.groups()
    lo = datetime(int(year), MONTHS[mon.lower()], int(day), int(h1), int(m1), tzinfo=UTC8)
    hi = datetime(int(year), MONTHS[mon.lower()], int(day), int(h2), int(m2), tzinfo=UTC8)
    d2 = _SECOND_DATE.search(instruction, m.start(), m.end())
    if d2 and d2.group(1).lower() in MONTHS:
        hi = datetime(int(d2.group(3)), MONTHS[d2.group(1).lower()], int(d2.group(2)),
                      int(h2), int(m2), tzinfo=UTC8)
    if hi <= lo:
        hi += timedelta(days=1)
        notes.append("window end was not after its start; moved the end to the next day")
    return lo, hi


def _count(text: str, notes: list[str]) -> int:
    m = _COUNT.search(text)
    if not m:
        notes.append("no failure count found in the instruction; assuming 1")
        return 1
    g = m.group(1)
    return int(g) if g.isdigit() else WORDS[g]


def _asks(text: str) -> dict[str, bool]:
    return {
        "datetime": any(p in text for p in ("occurrence time", "occurrence datetime",
                                            "datetime", "time of")),
        "component": "component" in text,
        "reason": "reason" in text,
    }


def _days(lo_ts: float, hi_ts: float) -> list[str]:
    start = datetime.fromtimestamp(lo_ts - BASELINE_S, tz=UTC8).date()
    end = datetime.fromtimestamp(hi_ts, tz=UTC8).date()
    out = []
    d = start
    while d <= end:
        out.append(d.strftime("%Y_%m_%d"))
        d += timedelta(days=1)
    return out


def parse_instruction(instruction: str) -> Case:
    notes: list[str] = []
    text = instruction.lower()
    lo, hi = _window(instruction, notes)
    lo_ts, hi_ts = lo.timestamp(), hi.timestamp()
    return Case(instruction=instruction, n_failures=_count(text, notes), asks=_asks(text),
                lo_ts=lo_ts, hi_ts=hi_ts, days=_days(lo_ts, hi_ts), notes=notes)
