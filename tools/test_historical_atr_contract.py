#!/usr/bin/env python3
"""Contract check: external current-bar ATR must not leak into historical replay."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
market = (root / "MQL5/Include/QSMC/QSMC_MarketData.mqh").read_text()
engine = (root / "MQL5/Include/QSMC/QSMC_Root.mqh").read_text()

checks = [
    ("int current_closed=ClosedIndex();" in market,
     "ATRAt bounds requests against the latest closed bar"),
    ("closed_index>current_closed" in market,
     "forming-bar ATR requests are refused"),
    ("closed_index==current_closed && m_atr_external_valid" in market,
     "host ATR is used only for its current closed bar"),
    ("double a=ComputeWilderATR(closed_index);" in market,
     "historical indices use their own causal Wilder ATR"),
    ("double atr=series.ATRAt(i);" in engine and "history_rebuild" not in engine,
     "structure warm-up uses per-index historical ATR without present-bar leakage"),
]

for passed, label in checks:
    print(("PASS" if passed else "FAIL") + "  " + label)
if not all(passed for passed, _ in checks):
    raise SystemExit("historical ATR contract failure")
print("Historical ATR checks passed; this is not an MT5 compile or backtest.")
