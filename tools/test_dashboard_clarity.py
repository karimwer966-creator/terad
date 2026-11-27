#!/usr/bin/env python3
"""Guard the visible dashboard contract; not an MQL5 compiler or market test."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "nadir2.mq5"
MIRROR = ROOT / "MQL5" / "Indicators" / "nadir2.mq5"
DOC = ROOT / "docs" / "QSMC_DASHBOARD_CLARITY.md"
text = SOURCE.read_text(encoding="utf-8")
raw = SOURCE.read_bytes()
mirror_raw = MIRROR.read_bytes()
doc = DOC.read_text(encoding="utf-8")
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
    "the compact card is capped in pixels and in chart share": (
        all(token in text for token in (
            "int cap_px=(InpDashboardMaxWidthPx>0?InpDashboardMaxWidthPx:430);",
            "int cap_pct=(int)(chart_w*2/5);",
            "safe_w=(int)MathMax(210,MathMin(safe_w,chart_w-16));",
        )) and (
            "MathMin(safe_w,MathMin(cap_px,cap_pct))" in text or
            "MathMin(SafeLeftPanelWidth(),MathMin(cap_px,cap_pct))" in text
        )
    ),
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
    # v6.6.13 AUDIT-PR1. Observed on a live demo chart: the card read
    # "STATUS: WAIT" and, one row below, "PRIMARY BUY @ 3897.59 | 64/100" in BUY
    # green - while that level was 4.4 ATR BELOW the price (beyond
    # InpAlertMaxDistanceATR) and the chart tag on the same level said
    # "BUY PLAN - CONDITIONAL - LATE - WAIT FOR RETEST". Two causes, both display:
    # (a) the compact card's width fallback rebuilt row 1 as "PRIMARY <side> @ ..."
    #     and dropped the "CONTEXT (NOT ENTRY)" qualifier that the full row carries,
    #     so the one row a compact chart always shows was the one row without it;
    # (b) the row was coloured by direction alone, so an unreachable level looked
    #     like a live side.
    "the compact card's width fallback cannot drop the qualifier": all(
        token in text for token in (
            'lines[1]=StringFormat("CONTEXT (NOT ENTRY) | %s @ %s | %d/100 | %s"',
            "primary_dir>0?\"BUY\":\"SELL\")",
        )),
    "the primary row states how far the level is": all(token in text for token in (
        "string p_dist=(g_alert_primary.distance_atr<=0.05?\"at the zone\"",
        '"%.1f ATR %s"',
        'primary=StringFormat("PRIMARY %s %s %s | %d/100 | %s"',
    )),
    "a level beyond InpAlertMaxDistanceATR is amber, not a live side colour": all(
        token in text for token in (
            "bool p_near=(g_alert_primary.valid && g_alert_primary.distance_atr<=",
            "p_near?(primary_dir>0?clrLimeGreen:clrLightCoral):clrOrange",
        )),
    "an out-of-reach level reports the real blocker beside it": (
        'needs=(p_near?"NEEDS: "+(g_alert_primary.needs==""?"none":g_alert_primary.needs)'
        ':"NEEDS: "+AlertWhyNoPopup(closed,g_buf_t[closed]));' in text),
    "the S/R token is gone from the row (S for support read as SELL)": (
        '"PRIMARY %s %s %s-%s | %d/100"' not in text),
    # The same complaint on the other surface: the plan tag named its state but
    # never how far the closed price sat from the zone, which is the whole reason
    # a LATE plan must wait. The tag now carries it, for live plans only.
    "the conditional plan tag states the closed distance to its zone": all(
        token in text for token in (
            '" | %.1f H1-ATR %s the zone"',
            "terminal||!p.distance_available||g_scn_ctx.selection_atr<=0.0",
        )),
}

# Grouped display-only explainability panel addendum. It is deliberately pinned
# on the same source file as the compact card: one chart, one set of facts, no
# second decision path. These are transcription/display contracts, not F7.
grouped_def = re.search(r"void DrawGroupedSMCDashboard\([^)]*\)\s*\{", text)
grouped_head = text[grouped_def.start():grouped_def.start() + 320] if grouped_def else ""
headings = ("MARKET CONTEXT", "LIQUIDITY ANALYSIS", "MARKET STRUCTURE",
            "ZONE ANALYSIS", "SIGNAL ENGINE", "BUY", "SELL", "WATCH")
checks["grouped panel is drawn from the existing dashboard path"] = (
    grouped_def is not None and
    text.count("DrawGroupedSMCDashboard(total,c);") == 1 and
    "if(!QSMC_PaintAllowed()) return;" in grouped_head and
    "if(!InpShowAIDashboard) return;" in grouped_head
)
checks["grouped panel renders every requested heading"] = all(
    'ScenarioDashAdd(lines,cols,ln,cap,"%s",clrDodgerBlue);' % h in text
    for h in headings
)
checks["grouped panel has a graceful DATA_WAITING state"] = (
    '"DATA_WAITING | "' in text and
    "g_sniper_data_ready" in text and
    "g_sniper_data_status" in text and
    "g_sniper_atr_warned" in text and
    "g_sniper_adx_warned" in text and
    "4806" in text and
    "open W1/D1/H4/H1, raise Max bars, wait 2-3 min" in text
)
checks["grouped panel states it is display only, not an entry"] = (
    "display only (NOT ENTRY)" in text and
    "CONFIRMED" in text and
    "CANDIDATE (NOT ENTRY)" in text and
    "no candidate" in text
)
checks["grouped objects stay in the classified CORE_DASH_ primary family"] = (
    'PFX+"CORE_DASH_GRP_BG"' in text and
    'PFX+"CORE_DASH_GRP_ROW_"' in text and
    'ObjectsDeleteAll(0,PFX+"CORE_DASH_");' in text
)
checks["grouped panel keeps full rows in the hover tooltip"] = (
    '"... +"+IntegerToString(hidden_rows)+" more (hover)"' in text and
    "for(int i=0;i<rows_total;i++) tooltip+=" in text and
    "OBJPROP_TOOLTIP" in text
)
checks["grouped panel adds no input, header, object-create or redraw site"] = (
    sum(1 for line in text.splitlines() if line.startswith("input ")) == 612 and   # 604 + v6.6.25 group banner + 7 switches
    text.count("#include") == 8 and
    text.count("ObjectCreate(") == 16 and
    text.count("ChartRedraw(") == 3
)
checks["grouped panel adds no trade API"] = all(
    api not in text for api in ("OrderSend(", "OrderSendAsync(", "PositionOpen(", "CTrade")
)
checks["both nadir2.mq5 copies remain byte-identical pure CRLF"] = (
    raw == mirror_raw and
    raw.count(b"\n") == raw.count(b"\r\n") and
    raw.count(b"\r") == raw.count(b"\r\n")
)
checks["dashboard clarity doc documents the grouped panel and DATA_WAITING"] = (
    "Grouped SMC explainability panel" in doc and
    "DATA_WAITING" in doc and
    "MARKET CONTEXT" in doc and
    "4806" in doc and
    "F7 / MetaEditor" in doc
)

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
