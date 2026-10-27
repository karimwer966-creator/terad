# QSMC decision dashboard clarity pass

The chart's Core decision card now defaults to a full-width, readable strip
(`InpDashboardFullWidth=true`, `InpDisplayMode=QSMC_MODE_FULL`) and the new-chart
visual preset starts with `InpUltraCleanMode=true` and `InpDeclutterMode=true`.
That keeps zones outline-only, reduces plotted zone clutter, and prioritizes
readable decisions. These are display defaults; turn either clean option off if
you prefer the previous dense chart. The card surfaces decision facts that were
previously split across several chart annotations:

1. The authoritative Core/RXN/ZRE primary status remains separate from the
   MTF level ranking.
2. `BEST LEVEL` reports the selected support/resistance price band, normalized
   structural strength, timeframe confluence, and zone type.
3. `ENTRY CHECK` reports the sniper engine's closed-bar grade and rejection
   evidence count (0-5), a confirmed entry or unconfirmed zone edge, advisory
   stop/TP1 levels, and the first reported blocking gate.
4. `DIRECTION` is explicitly `MIXED - WAIT` when the non-neutral HTF, D1, and
   enabled top-down directions disagree. It does not silently force one side.
5. Full details remain available in the chart-object tooltip. The card can be
   returned to a compact width by setting `InpDashboardFullWidth=false`.

## Color key

- Green: bullish / buy-side information.
- Light red: bearish / sell-side information.
- Amber: waiting, blocked, or mixed direction.
- Silver: neutral context.

The decision card uses these four meanings consistently; it does not use color
as a substitute for the printed state. The rest of the indicator's legacy zone
colors are controlled by its existing display/zone inputs and are not changed by
this pass.

## Safety and interpretation

This is a display and explainability change only. It does not relax entry gates,
change zone ranking, create trades, or turn the strength/evidence scores into a
probability or win-rate estimate. `READY - CLOSED BAR` reflects the MTF sniper
engine's existing eligibility; if the macro direction display is mixed, the
card downgrades its wording to `LOCAL READY / DIRECTION MIXED - WAIT`. The
existing authoritative signal lifecycle remains the only signal authority.

MetaEditor is not available in the repository test environment. Run
`python3 tools/test_dashboard_clarity.py`, `python3 tools/static_check.py`, and the
QSMC contract tests; then open `nadir2.mq5` in MetaEditor and compile with F7
before attaching it to a chart. Review on a demo chart first; no display score
proves future profitability.

## "A zone appeared on the chart but the system did not alert me"

This is the most common support question, and the answer is short: **a drawn zone
is not a signal.** The zone objects (`QSMC_..._ZONE_<id>_B`, `QSMC_..._FVG_...`)
are the Zones/ZRE layer showing where liquidity sits. Alerts come from a
different event: a **closed-bar rejection** of that zone that survived every gate.

The chain a popup must pass, in order:

| Step | What must be true | Where it is configured |
| --- | --- | --- |
| 1 | The bar is **closed**. A live-candle touch is `TOUCHED_PREVIEW` and is labelled `LIVE PREVIEW (NON-AUTHORITATIVE)`. Preview never alerts, by design | none — closed-bar only |
| 2 | A rejection was confirmed: touch, bounded penetration, reclaim close, and enough independent evidence groups | `InpZREMinEvidence` and the ZRE rejection rules |
| 3 | Zone strength reaches the alert floor | `InpZREAlertMinStrength` (default 70) |
| 4 | The zone is close enough to the closed price | `InpAlertMaxDistanceATR` (default 2.0) |
| 5 | The reaction level is high enough | `InpRXNAlertMinLevel` (default 4 = CONFIRMED) |
| 6 | The channel for that source is on | `InpPrimaryAlertPopup`, `InpZREAlertPopup`, `InpRXNAlerts`, push/sound switches |
| 7 | The same (zone, direction, level) is not in cooldown | `InpAlertCooldownBars` (default 5) |
| 8 | No other source already claimed this bar (one alert per bar) | automatic |
| 9 | The arbiter's gate chain accepted the candidate | `InpArbGate*`, `InpArbEnabled` |

Since v6.6.6 the panel answers this itself: when the closed bar produced no
directional candidate, the `NEEDS:` row and the panel tooltip print the specific
blocker, for example

```
NEEDS: zone 68640 is TOUCHED ON THE LIVE CANDLE only (3994.84, strength 91) - alerts are closed-bar, wait for this candle to close
NEEDS: REACTION CONFIRMED on zone 68640 but strength 62 < InpZREAlertMinStrength 70
NEEDS: nearest candidate is 3.20 ATR from the closed price, limit InpAlertMaxDistanceATR 2.00
NEEDS: deduplicated by InpAlertCooldownBars 5 on this exact (zone, direction, level)
NEEDS: already alerted on this bar by <event id> - one alert per bar
```

That explanation is **read-only** (`AlertWhyNoPopup()`): it never submits,
claims, commits or clears a candidate, and it never reads the forming bar. It
cannot change whether an alert fires; it only names the blocker. The dispatcher's
own journal line still exists behind `InpAlertDispatcherLog=true`.

### If your panel shows wording this build does not contain

A panel that prints `SCORE: n/a (no authoritative instance)` or
`CONTEXT: UNVALIDATED (… M15 disabled) - no weight or tiers` is **not** this
build: those exact strings do not exist in this repository or in its history.
Before debugging gates, confirm which build is on the chart — the first journal
line must read `[QSMC_ARB] v6.6.6 arbitration layer ON | …`. Any other version
means a stale compiled copy in the Data Folder, and no input you change on that
copy will add the behaviour documented here.

### Everyday checklist when a zone fires nothing

1. Read the `NEEDS:` row first — it names the blocker.
2. Confirm the bar closed: a touch on the current candle is a preview.
3. Check `InpZREAlertMinStrength` and `InpAlertMaxDistanceATR` before lowering
   anything: a zone 4 ATR away is not an entry, and a strength-40 zone is not an
   alert.
4. Check that Algorithmic trading is enabled only if you also run
   `QSMC_AutoTrader.mq5`; chart popups do not need it.
5. Only then look at the arbiter gates — and remember that a refusal is the
   system working, not the system failing.
