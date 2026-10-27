#!/usr/bin/env python3
"""Guard the visible dashboard contract; not an MQL5 compiler or market test."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "nadir2.mq5"
text = SOURCE.read_text(encoding="utf-8")
checks = {
    # v6.6.8: the card ships COMPACT. A full-width card is still available, but it
    # is no longer what a new chart gets, because covering the candles was the
    # most common complaint about the panel.
    "new-chart defaults enable a compact, clean view": all(token in text for token in (
        "InpDashboardFullWidth = false",
        "InpUltraCleanMode = true",
        "InpDeclutterMode           = true",
        "InpDisplayMode    = QSMC_MODE_FULL",
    )),
    "the decision card has a bounded row budget": all(token in text for token in (
        "string lines[11]; color cols[11]; int ln=0;",
        "if(ln>11) ln=11;",
        "for(int i=ln;i<11;i++)",
        "int max_rows=(int)MathMax(3,MathMin(10,InpDashboardMaxRows));",
        "int rows_total=ln;",
        'lines[ln]="... +"+IntegerToString(hidden_rows)+" more (hover)";',
        "hidden_rows=rows_total-ln;",
    )),
    "the compact card is capped in pixels and in chart share": all(token in text for token in (
        "int cap_px=(InpDashboardMaxWidthPx>0?InpDashboardMaxWidthPx:430);",
        "int cap_pct=(int)(chart_w*2/5);",
        "safe_w=(int)MathMax(210,MathMin(safe_w,chart_w-16));",
        "MathMin(safe_w,MathMin(cap_px,cap_pct))" in text or
        "MathMin(SafeLeftPanelWidth(),MathMin(cap_px,cap_pct))",
    )),
    "wide mode is capped too, so it never spans a whole monitor": all(token in text for token in (
        "MathMin(chart_w-16,900)",
    )),
    "the card font is small and clamped": "panel_font=(int)MathMax(7,MathMin(10,panel_font));" in text,
    "the card spacing is tight": "int pad=6,line_h=panel_font+5;" in text,
    "clean modes shorten the chart captions and keep the full text in the tooltip": all(token in text for token in (
        '"> PREVIEW %s STRUCTURE"',
        '"> PREVIEW BREAK %s"',
        '"> PREVIEW "+ZRE_ZoneText',
    )),
    "the strongest MTF zone and its closed-bar evidence are visible": all(token in text for token in (
        "BEST LEVEL:", "g_sniper_best.level.price_low", "g_sniper_best.level.price_high",
        "rejection evidence %d/5", "READY - CLOSED BAR",
        "g_sniper_best.entry_price", "g_sniper_best.sl_price", "g_sniper_best.tp1_price",
    )),
    "mixed HTF/D1/top-down direction is shown as wait, not forced": all(token in text for token in (
        "direction_conflict=true", "MIXED - WAIT", "LOCAL READY / DIRECTION MIXED - WAIT",
    )),
    "entry-score wording remains evidence strength, not probability": "strength %.2f" in text and "not a probability" in text,
    # v6.6.8: a drawn zone is not a signal, and the panel now says which gate
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
start = text.index('// v6.6.8 "WHY DID IT NOT ALERT ME?"')
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
