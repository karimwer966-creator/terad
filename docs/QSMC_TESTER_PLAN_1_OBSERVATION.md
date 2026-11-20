# Strategy Tester Plan 1 — OBSERVATION / DRY-RUN (no executions)

Isolated Strategy Tester only. **Never on a live chart, never on a real or
demo account with order submission.** Goal: observe the diagnostic and
decision flow — not fills.

## Objective

Walk a historical M15 window bar-by-bar and record what the system *would*
do: nadir2 buffer contents as they are produced, CORE publication events, EA
gate verdicts, dry-run decision lines, and gate rejections. No order is sent.

## Setup

- Terminal/tester profile: dedicated, disposable (same portability discipline
  as the dump tool). Model: "Every tick based on real ticks" if the broker/
  symbol provides them, else the finest model available — record which.
- Symbol: the intended production symbol; Timeframe **M15** (EA
  `PERIOD_M15` assumption; anything else is a different test).
- Period: a representative window **with broker M15 history that is complete
  and synchronized** — verify by scrolling + `Bars()` before relying on it.
  Prefer a window known to contain CORE activity; see "Representative period".
- Inputs: copy the DIAG dry-run preset
  `presets/QSMC_AutoTrader_DIAG_XAUUSD_M15.set` **as-is** (trading=false,
  dry-run=true). **Do not** weaken or disable gates, breakers, spread
  filters, or guard rails. Do not add new inputs to production sources.
- Instrument: QSMC_AutoTrader.mq5 as-is (hash `287e2b5…` per
  `docs/QSMC_BASELINE_HASHES.md`). nadir2 is consumed by the EA through its
  own iCustom path.
- Collect: Strategy Tester report, Journal + Experts logs, and the EA's DIAG
  CSV outputs if any (check DIAG inputs; e.g. SigLog CSV if enabled).

## What to record (per run)

- terminal build, tester model, symbol, period, spread/commission settings,
  starting balance (tester value), optimization OFF.
- number of closed bars replayed; number of CORE publications observed
  (non-zero buffer 7/19/21/22 in replay logs or DIAG CSVs); count by
  direction and by class.
- gate verdict distribution (which gates blocked, in order), dry-run "would
  enter" lines, setup timeouts, invalidations.
- any `[DataHealth]`, indicator-copy retry, or data-incomplete lines.
- Book/store the raw artifacts; do not post-process numbers into claims.

## What it proves

- Buffer/event generation **inside the replay** — including on historical
  bars, which a fresh attach cannot show.
- The EA's diagnostic and decision flow and gate arithmetic on this window.
- Whether a "silent" period is silent because of gates, data, or no signals.

## What it does NOT prove

- Executions, fills, slippage, commissions/swaps fidelity, partial fills,
  requotes, latency, broker behavior, live spread, queue position — none.
- Profitability, expectancy, or forward equivalence.
- Anything about other windows, symbols, TFs, brokers, or costs.
- A zero-signal window proves nothing except that no signal fired. If the
  chosen window shows zero CORE publications, **report the limitation and
  pick a representative window**; do not lower gates to manufacture activity.

## Acceptance criteria

- Replay completes without tester errors; artifacts archived.
- Counts reported with the exact window and model named.
- Every "no trade" outcome attributed (data / gate / no setup), not assumed.
- Verdict wording in reports: "observed in tester replay of <window>, model
  <model>" — never "validated live".

## Non-goals

No order is submitted; no optimization; no parameter sweep; no strategy
change; no enablement of new entries; no comparison of strategies here.
