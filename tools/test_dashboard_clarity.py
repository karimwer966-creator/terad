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
    # v6.6.6: a drawn zone is not a signal, and the panel now says which gate
    # refused the alert instead of a generic "wait for a reaction".
    "the no-alert reason is on the panel and in the tooltip": all(token in text for token in (
        "string AlertWhyNoPopup(const int closed,const datetime bar_time)",
        'needs="NEEDS: "+AlertWhyNoPopup(closed,g_buf_t[closed]);',
        '"Why no alert this bar: "',
    )),
    "the no-alert reason names every real blocker": all(token in text for token in (
        "TOUCHED ON THE LIVE CANDLE only",
        "InpZREAlertMinStrength",
        "InpAlertMaxDistanceATR",
        "InpRXNAlertMinLevel",
        "InpAlertCooldownBars",
        "one alert per bar",
        "every alert channel is OFF",
        "arbiter top blocker",
    )),
}
# AlertWhyNoPopup() is a display helper. If it ever calls into the dispatcher it
# stops being an explanation and becomes an unreviewed second decision path.
# The DEFINITION block, not the forward declaration at the top of the file.
start = text.index('// v6.6.6 "WHY DID IT NOT ALERT ME?"')
body = text[start:text.index("void RXN_Alert(", start)]
for forbidden in ("AlertDispatcherSubmit", "QSMC_ClaimDirectionalAlert",
                  "AlertCooldownCommit", "AlertCooldownAllows(g_alert_primary", " Alert(",
                  "SendNotification", "PlaySound", "AlertDispatcherClear"):
    if forbidden == "AlertCooldownAllows(g_alert_primary":
        continue  # reading the cooldown is the point; writing it is not
    checks["the no-alert reason is read-only (no %s)" % forbidden.strip()] = forbidden not in body
checks["the no-alert reason never reads the forming bar"] = "states[rates_total-1]" not in body and "closed+1" not in body

failed = [name for name, passed in checks.items() if not passed]
for name, passed in checks.items():
    print(("PASS" if passed else "FAIL") + " " + name)
if failed:
    raise SystemExit("Dashboard contract failed: " + "; ".join(failed))
print("Dashboard clarity contracts passed; MetaEditor compile and chart review are still required.")
