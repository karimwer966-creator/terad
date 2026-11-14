# QATS — MT5 Strategy Tester configuration (`QATS_COMPILE_TEST`, v1.24 module series, Phase 10)

**Status: configuration deliverable. The tester has NOT been run in this environment.**
No compiling MetaEditor was available (see `QATS_COMPILE_TEST_V124.md` §2 for the
plain statement and the probe log). Everything below is what a human operator
runs on the machine that has a terminal.

> **NO PROFITABILITY CLAIM IS MADE OR IMPLIED anywhere in this document.**
> The offline simulation of the real source over 2017-02-01 → 2026-09-01
> (`QATS_BACKTEST_STUDY_2026-11-11.md`) found **no demonstrated edge** (in-sample
> PF 0.79 / −0.127 R; out-of-sample PF 1.00 / +0.006 R for v1.20 BALANCED).
> This configuration document exists so the answer is re-measured with the real
> execution mechanics instead of asserted. If the Strategy Tester does not
> reproduce an edge out-of-sample, the verdict is **no edge** and nothing ships
> to real money.

## 0. Non-negotiables

1. Money path stays DEMO-only: `InpDemoOnly=true`, `InpAllowRealTrading=false`,
   `InpRealAccountConfirm=""`, `InpRealServerConfirm=""`. The tester uses no
   broker — the same inputs are loaded for hygiene, not because they gate.
2. Order of operations: **F7 clean → tester runs (this document) → tester
   journal review → ≥ 4 weeks demo forward test → only then REAL discussion**,
   and only after `QSMC_GO_LIVE_RUNBOOK.md`. This document is step 2.
3. Every run is published, including the ugly ones. No cherry-picked windows,
   no re-rolling until a green number appears.
4. Nothing in this planning document edits the EA. Inputs marked "sweep" are
   for the tester only.

## 1. Environment

| Item | Setting |
|---|---|
| Terminal | MetaTrader 5, latest build the broker supports (record it in the report; e.g. `5.00 build 5200`) — see the About tab banner |
| EA | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` compiled with **F7, 0 errors / 0 warnings** |
| Symbol | `XAUUSD` (use the exact symbol for that broker: `XAUUSDm` if that is what the server serves) |
| Period | **M5** |
| Model | **Every tick based on real ticks** |
| Spread | **Current** (never a fixed lower spread; a "fixed 10" run would flatter the result) |
| Deposit | 10,000 USD |
| Leverage | As set by the broker at account opening |
| Optimization | **Off** (first pass); optimization grids come after one decorrelated baseline exists |
| Visual mode | Off for the matrix; on once for a sanity pass |
| Date range | **2024-01-01 → 2026-10-31** (≥ 2 years, includes the 2024 gold stress: the March 2024 breakout 1,984→2,160+, August 2024 1,912→2,531, April 2025 3,000+) |
| Forward split | Last 20–25% of the window (from 2026-04-01 onward) as the forward segment — marked in the report, never optimized |
| Walk-forward | Quarterly: 2024Q1…2026Q3, each quarter evaluated alone |

**Reality check on data:** "Every tick based on real ticks" requires the broker's
tick history for the symbol. If the broker cannot supply XAUUSD ticks for the
full window, record exactly that and fall back to "Every tick" with a note —
never to a shorter or prettier window.

## 2. Baseline preset under test

`presets/Quantum_XAUUSD_PRODUCTION.set` as committed — key facts to record:
`InpSignalExecutionProfile=2` (PERMISSIVE), `InpStrategyProfile=1` (BALANCED),
`InpEnableTrading=true`, `InpDryRun=false`, `InpUseLimitEntry=true` (LIMIT at the
zone), `InpDisplaceM15=true` (H1 checked first), `InpMinScore=55`,
`InpSetupWindowBars=6`, `InpDisplaceATR=0.8`, PD-adaptive gate on for the market
path (`InpPDEnforceMarket=true`), `InpLimitNeedPD=true`, news filter OFF, regime
REPORT-ONLY, `InpMaxTradesPerDay=3`, `InpMaxDailyLossPercent=0.50`,
`InpMaxAccountDrawdownPct=3.00`, `InpStopAfterConsecLoss=2`, cooldown 60 min.

## 3. Run matrix (full window each; record every run's metrics)

| Run | Change vs baseline | Question |
|---|---|---|
| R1 | none (preset as committed) | What the shipped configuration does |
| R2 | `InpUseLimitEntry=false` | Does the limit-at-zone premise add or remove EV? |
| R3 | `InpStrategyProfile=0` (CONSERVATIVE) | Sensitivity to the core-gate strictness |
| R4 | `InpStrategyProfile=2` (ACTIVE) | Same, loosened |
| R5 | `InpNewsFilterEnable=true` (USD,XAU, high-only) | Whether the calendar guard changes the result materially |
| R6 | `InpDisplaceM15=false` | Whether the v1.23 M15 fallback contributes or is noise |

## 4. Parameter sensitivity plan (one factor at a time, baseline = preset)

| Knob | Values | Runs |
|---|---|---|
| `InpMinScore` | 55, 60, 65 | 3 (one is the R1 baseline) |
| `InpDisplaceATR` | 1.2, 1.5, 2.0 | 3 (all stricter than the 0.8 preset) |
| `InpSetupWindowBars` | 12, 24, 48 | 3 (longer setup memory than the 6-bar preset) |

Total: R1 baseline + 8 one-factor variants = **9 full-window runs**. The
9 cells exist to detect a knife-edge parameter dependence, not to be optimized
over. **Pre-declared decision rule:** the preset is kept as-is unless a
neighbouring single-factor cell beats it on OUT-OF-SAMPLE expectancy with
profit factor > 1.05 and max drawdown ≤ the preset's own; even then the change
goes through explicit operator review, never silently into the preset. Any
cell that looks "too good" is a red flag, not a find.

Quarterly walk-forward rows for every Rk/grid cell are required in the
report template — not just the full-window numbers.

## 5. Metrics (mandatory, per run)

Net result, trade count, win rate, profit factor, expectancy in R/trade, max
drawdown (absolute and %, and the date it occurred), recovery factor
(net / max DD), average realized R:R, exposure % of window, expectancy
**decomposed by**: side (BUY/SELL), session (broker server-time), regime
(`REGIME=` field), PD bucket, displacement TF (H1 vs M15), entry path
(LIMIT vs market), and outcome class of refused setups
(`[QATS][GUARD] REJECTED AT=.. REASON=..` histogram). Behaviour with zero
trades in a class must be stated, never silently omitted.

Both BUY and SELL columns come from the same run — use
`tools/qats_journal_report.py trader-journal.log [--json]` on the saved tester
Journal tab for the BUY-vs-SELL split instead of recounting by hand.

## 6. Diagnostic journal review (uses Phase 9 records)

After R1, save the tester **Journal** tab to a file and record:

- `[QATS][ANALYSIS]` histogram of `EXECUTION_STATUS` and `FINAL_DECISION`
  across decided bars (EXECUTED / BLOCKED / REJECTED / NOT_PLACED /
  BELOW_MINIMUM / CONFLICT / DRY_RUN).
- Every `[QATS][GUARD]` line: `REJECTED AT=.. REASON=..` counts per layer —
  this is the "why high-scoring setups did not trade" answer. If the top reason
  is `DAILY_LOSS_LOCK`/`DRAWDOWN_HALT` with a healthy `[QATS][HB]` tail, the
  account is dying by its own brakes; that is a finding, not a defect, and must
  be named in the report.
- `FINAL_DECISION=BLOCKED` count vs `[QATS][BLOCK][REASON]` records — they must
  agree; a mismatch means a journal path bug to report, not work around.
- `[QATS][RISK]` / heartbeat tails on the days of the worst losses.
- Attach the `qats_journal_report.py` output and sheet of counts.

## 7. Spread & slippage stress (scenario runs, clearly labelled)

Re-run R1 three times with fixed 20/30/50-point spreads as **scenarios** (labelled,
never promoted to the baseline). The shipped default rejects entries when the
spread exceeds 20% of stop distance or `InpMaxSpreadPoints`; these scenario runs
show how much of the result that guard actually saves.

## 8. Kill criteria & honest verdict

Stop and report — do not tune — if any of these hold for R1:

- out-of-sample expectancy ≤ 0 or out-of-sample PF < 1.0, or
- OOS contains zero trades (the window is then meaningless and the verdict is
  "insufficient evidence"), or
- results depend on a single day/session (one lucky day).

The expected prior given the 2026-11-11 simulation is that **R1 does not clear
these bars**. A negative or neutral result does not get rationalized into
"it works live"; it gets documented in the report template with the same table
completed.

## 9. What the tester run cannot certify

It cannot certify broker tick feeds, spreads under stress, execution lag, swap,
deposit/withdrawal, connectivity, other symbols, other accounts, or time beyond
the window. ≥ 4 weeks of DEMO forward test (post-F7, post-tester) is the
minimum before any REAL conversation, and even then REAL requires the explicit
written authorization path in `QSMC_GO_LIVE_RUNBOOK.md`. Nothing here changes the
REAL-disarmed default.

## Appendix A — tick-box checklist

```
[ ] F7 in MetaEditor on the exact file in this checkout: errors=0 warnings=0 (build banner recorded in the report)
[ ] Inputs on the tester Inputs tab match this document §2 exactly (diff the exported .set)
[ ] Symbol == broker symbol; digits (2 or 3) confirmed on the specification — rejection of mismatched P/L models noted
[ ] Modeling = Every tick based on real ticks; spread = current
[ ] Window 2024-01-01..2026-10-31; forward split date marked; optimization off
[ ] R1..R6 run; §4 grid run; §7 scenarios run — all journals saved
[ ] qats_journal_report.py output attached; Phase-9 GUARD histogram filled in
[ ] QATS_TEST_REPORT_TEMPLATE.md completed IN FULL (zero TODO markers)
[ ] DEMO ≥ 4 weeks still required afterwards — noted on the sign-off lines
```

## Appendix B — where the numbers live in the tester

"Report" tab → Summary (net, gross, PF, DD, trades, win rate), Drawdown,
MFE/MAE, **Monthly analysis** (per-quarter cross-check), Time/weekday, "Orders"
and "Deals" tabs (export CSV if the Python tools need them). The **Journal"
tab is the EA's stdout — `Filtr: QATS` keeps the signal trail readable.

## Appendix C — artifact convention

Save everything under `out/tester/YYYY-MM-DD_<symbol>_<run-id>/` — `report.htm`,
`journal.log`, `orders.csv`, `param-dump.set`, `notes.md`. `out/` is gitignored;
nocturnal artifacts do not get committed. Attach hashes of `.mq5` and the preset
to the report so the run is reproducible against an exact source.

*Reminder: the offline host simulation (`tools/qats_backtest.py`) and MetaEditor/
Strategy Tester are different machines. A pass there never substitutes for a pass
here, and vice versa.*
