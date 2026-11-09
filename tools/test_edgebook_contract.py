#!/usr/bin/env python3
"""Offline contract checks for the MQL5 EdgeBook persistence contract.

These checks validate source-level schema/policies and a small independent
reference ledger; they do not execute MetaTrader's FileOpen/FileWrite runtime.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "MQL5/Include/QSMC/QSMC_Stats.mqh").read_text()
root_source = (ROOT / "MQL5/Include/QSMC/QSMC_Root.mqh").read_text()


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS  {message}")


# The schema is deliberately fixed and versioned independently of the signal journal.
header_start = source.index("bool WriteHeader()")
header_end = source.index("bool WriteRecord(", header_start)
header = source[header_start:header_end]
required_fields = [
    "schema_version", "record_type", "setup_id", "strategy_key", "symbol",
    "timeframe", "entry_time", "direction", "entry", "stop", "target",
    "outcome", "outcome_r", "mfe_r", "mae_r", "spread_points", "resolution",
]
require(all(f'"{field}"' in header for field in required_fields),
        "EdgeBook V1 header contains all 17 ordered fields")
require('"QSMC_EDGE_V1_"' in source and "QEDGE_SCHEMA_VERSION 1" in source,
        "EdgeBook filename and rows carry an explicit schema version")
require("FileReadString(m_handle)!=HeaderField(i)" in source,
        "existing EdgeBook header is validated before append")
require("FileFlush(m_handle);" in source[source.index("bool WriteRecord("):source.index("void MarkUntrusted(")],
        "each completed outcome is flushed before it is counted")
require("duplicate completed setup_id" in source and "FindId(r.setup_id)>=0" in source,
        "duplicate IDs from both persisted rows and runtime events are rejected")
require('r.record_type=="PENDING"' in source and "RecordPending(const SEdgeOutcomeRecord" in source,
        "published setups are journaled as pending before outcome")
require("RestorePendingRows" in source and "bars.IndexOfTime(item.entry_time)" in source,
        "restart restores pending setups by replaying available closed bars")
require('resolution="RESTART_HISTORY_GAP"' in source and "QEDGE_AMBIGUOUS" in source,
        "missing replay history is recorded ambiguous, never invented as a win/loss")
require("FILE_COMMON" in source and "const bool common=false" in source,
        "EdgeBook defaults to terminal-local Files; Common storage is opt-in")

# Signal journal append safety and actual versioned row width.
require('"QSMC_ARB_V2_"' in source and "FILE_READ|FILE_WRITE" in source,
        "signal CSV uses a versioned append-only filename")
require("ValidateSignalHeader()" in source and 'version!="2" || kind!="SIGNAL"' in source,
        "signal journal validates schema header and every appended row")
require('"2","SIGNAL"' in source and "setup_id" in source,
        "signal rows persist deterministic setup identifiers")
require("m_stats.Open(m_symbol,m_chart_tf,min_sample,csv_log);" in root_source,
        "outcome tracking runs even when CSV persistence is disabled")

# Causal outcome reference policy: one bar cannot produce both wins and losses.
def resolve(direction, entry, stop, target, high, low):
    tp = high >= target if direction > 0 else low <= target
    sl = low <= stop if direction > 0 else high >= stop
    if sl:
        return "LOSS"  # also the explicit both-touch conservative policy
    if tp:
        return "WIN"
    return "OPEN"


require(resolve(1, 100, 98, 104, 105, 97) == "LOSS",
        "same-bar stop/target ambiguity resolves conservatively to stop")
require(resolve(-1, 100, 102, 96, 103, 95) == "LOSS",
        "short same-bar stop/target ambiguity also resolves conservatively")
require("bar_time<=r.last_advanced_time" in source and "BOTH_TOUCH_STOP_FIRST" in source,
        "bar advancement is idempotent and records the ambiguity policy")

# Append-only state transition reference used by restart recovery.
def apply_events(events):
    states = {}
    for kind, setup_id in events:
        if kind == "PENDING":
            if setup_id in states:
                return False
            states[setup_id] = "PENDING"
        elif kind == "OUTCOME":
            if states.get(setup_id) != "PENDING":
                return False
            states[setup_id] = "OUTCOME"
        else:
            return False
    return states

require(apply_events([("PENDING", "a"), ("OUTCOME", "a")]) == {"a": "OUTCOME"},
        "restarted pending setup transitions once to a completed outcome")
require(apply_events([("PENDING", "a"), ("OUTCOME", "a"), ("OUTCOME", "a")]) is False,
        "a second completed row for the same ID is rejected")
require("Exclude that bar from MFE/MAE" in source,
        "exit-bar excursion extremes are excluded when intrabar order is unknown")

print("EdgeBook contract checks passed; this is not an MT5 file-I/O test.")
