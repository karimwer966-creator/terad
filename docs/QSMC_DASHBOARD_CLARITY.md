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
