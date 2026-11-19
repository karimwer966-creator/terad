# Strategy Tester Plan 2 — EXECUTION CHARACTERIZATION (isolated tester only)

> Hard rules: this plan runs **only** inside an isolated Strategy Tester on a
> disposable terminal/profile. It never runs on a live chart or live/demo
> account. It may run only if the **existing** safety gates allow order
> submission in tester context **as shipped** — if any guard or gate blocks
> submission, the correct outcome is *do not execute* and report; we do not
> widen gates, spreads allowed, risk %, or breaker thresholds to force
> activity, and we never add a bypass.

## Objective

Characterize how the already-written execution path behaves **inside the
simulated tester**: order send/modify/close outcomes, retcodes, fills vs
assumed prices, stop/target geometry behavior, partial close behavior,
protection/breaker reactions. This is characterization, not optimization and
not live trading.

## Preconditions (ALL must hold, else skip and report)

1. Plan 1 has been executed on the same window and produced an archived
   artifact set including at least a few CORE publications (or an explicit,
   user-approved note that the window is signal-free and this plan is
   deferred until a representative period exists).
2. The shipped gates/guards/breakers, the DIAG preset semantics, and the
   current production sources are unchanged (verify hashes against
   `docs/QSMC_BASELINE_HASHES.md`).
3. Tester configured with realistic costs: broker-typical spread **or**
   fixed spread model, commission and swap if the broker charges them,
   "Every tick based on real ticks" if available.
4. Permissions: the user explicitly authorizes this test and accepts the
   risk that tester results are still only simulation.
5. Environment: disposable portable terminal; dedicated tester profile;
   no production charts open; network profile isolated if possible.

## Setup variants

- **2A (preferred, if allowed by existing gates):** EA runs in tester with its
  production execution logic permitted to submit orders *in the tester* (the
  tester's simulated server fills them per the model). Use a tester balance
  and lot sizing identical to production risk settings; do not change risk
  inputs. Keep every protection (breaker, spread filter, session filter,
  daily loss, max positions) at production defaults.
- **2B (if gates block submission, as the DIAG preset does):** characterization
  is limited to Plan 1's dry-run plus retcode/validation audit of the order
  builder *without sending*. State explicitly: "execution characterization not
  performed — existing safety gates blocked submission in tester; no gate was
  modified." Do **not** edit gates to proceed.

## Metrics to capture

- Orders sent/accepted/rejected, retcodes and their meanings, requotes,
  invalid stops, insufficient margin.
- Fill price vs intended entry; slippage per trade (tester-implied); MFE/MAE.
- SL/TP/partial-close behavior; break-even moves; trailing; protection exits.
- Equity curve, max drawdown, streak distribution — descriptive only.
- Gate rejections that occurred *before* submission (kept separate).
- Netting vs hedging account mode behavior if the tester offers the choice;
  verify position ownership by symbol+magic; check partial-close invariants
  (volume reduction, not reversal).

## What it can prove

- Internal consistency of the order pipeline under the tester's fill model.
- Behavior of SL/TP/partial-close/protection code paths when orders exist.
- Whether the EA's own state machine handles retcodes and edge cases as coded.
- Relative comparison of two *configuration-tagged* runs on the same window
  (same gates, same costs) — e.g., before/after a legitimate, approved change.

## What it cannot prove — ever

- Live execution quality: real slippage, real spread, latency, requotes,
  partial fills, tick gaps, broker-specific behavior, real netting edges.
- Profitability or forward expectancy; OOS requires a separately frozen,
  untouched window and, ultimately, demo-forward trading before any live
  consideration.
- Equivalence between tester and live, or between brokers, or between models.
- Robustness to news/spikes; tester has no real order-book queue.

## Zero-trade periods

A period with zero filled trades proves nothing about execution equivalence.
If the representative period yields no submissions even under 2A (because no
setup qualified or gates blocked), report: "execution not characterized — no
submissions occurred; gates unchanged; equivalence NOT VERIFIED." Do not
manufacture trades.

## Acceptance criteria

- Only tester artifacts are produced; production terminals untouched.
- Hashes verified pre/post run; no source changes bundled into the test.
- Report separates: data window, model, costs, counts, retcode table,
  drawdown, and an explicit "does NOT prove" section.
- Verdict recorded as "characterization in tester only", never "proven live".

## Sequencing

Plan 1 first. Plan 2 only if preconditions hold and the user authorizes it.
Demo-forward remains the next step after tester work — and only after the
baseline gate is closed with real logs and the relocation decision (Phase C)
is made explicitly.
