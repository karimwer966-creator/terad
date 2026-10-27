#!/usr/bin/env python3
"""Guard the visible dashboard contract; not an MQL5 compiler or market test."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "nadir2.mq5"
text = SOURCE.read_text(encoding="utf-8")
checks = {
    "new-chart defaults enable a full-width, clean view": all(token in text for token in (
        "InpDashboardFullWidth = true",
        "InpUltraCleanMode = true",
        "InpDeclutterMode           = true",
        "InpDisplayMode    = QSMC_MODE_FULL",
    )),
    "the decision card has a bounded ten-row layout": all(token in text for token in (
        "string lines[10]; color cols[10]; int ln=0;",
        "if(ln>10) ln=10;",
        "for(int i=ln;i<10;i++)",
    )),
    "full-width mode uses the live chart viewport": "chart_w-16" in text and "InpDashboardFullWidth?safe_w" in text,
    "the strongest MTF zone and its closed-bar evidence are visible": all(token in text for token in (
        "BEST LEVEL:", "g_sniper_best.level.price_low", "g_sniper_best.level.price_high",
        "rejection evidence %d/5", "READY - CLOSED BAR",
        "g_sniper_best.entry_price", "g_sniper_best.sl_price", "g_sniper_best.tp1_price",
    )),
    "mixed HTF/D1/top-down direction is shown as wait, not forced": all(token in text for token in (
        "direction_conflict=true", "MIXED - WAIT", "LOCAL READY / DIRECTION MIXED - WAIT",
    )),
    "entry-score wording remains evidence strength, not probability": "strength %.2f" in text and "not a probability" in text,
}
failed = [name for name, passed in checks.items() if not passed]
for name, passed in checks.items():
    print(("PASS" if passed else "FAIL") + " " + name)
if failed:
    raise SystemExit("Dashboard contract failed: " + "; ".join(failed))
print("Dashboard clarity contracts passed; MetaEditor compile and chart review are still required.")
