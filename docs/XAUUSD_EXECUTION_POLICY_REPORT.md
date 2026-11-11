# XAUUSD execution policy — change and verification report

> **Superseded in part by v1.20 (2026-11-11)** — see
> [`QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md`](QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md). What still holds: the
> XAUUSD symbol rule, the diagnostic-only EMA / counter-D1 / class controls on XAUUSD, the broker-specification
> and stop-geometry checks, the atomic reservation with no automatic retry on XAUUSD, and the account policy.
> What changed:
>
> | statement below | v1.20 |
> |---|---|
> | "The existing signal generator and its scoring weights are unchanged" | Replaced. BUY and SELL are both evaluated on every bar by one function; a core-confirmation gate (`InpStrategyProfile`) precedes the score; the weights sum to 100 with no free points. |
> | "Same-direction decisions on a *new* M5 bar are treated as new signals even if they derive from the same persistent H1 setup" | No longer true. A setup that produced a position cannot produce another (`DUPLICATE_SETUP`). The per-bar reservation remains as the at-most-once submission guard. |
> | "Signal journal records show bar, symbol, direction, score …" | The record is now `[QATS][SIGNAL][SCORED]` with both scores and both evidence lists, plus `[DETECTED]`, `[CONFLICT]`, `[BLOCK][REASON]`, `[EXECUTION][APPROVED\|REJECTED\|FILLED]`. |
> | "The prior non-XAUUSD retry behavior remains outside this change" | Repaired: a queued retry keeps its plan, passes the whole guard chain, and can no longer lock entries out. |
> | "SL/TP are rounded outwards to the price tick" | The stop is snapped away from the entry; a liquidity target is snapped toward it, an R:R target away from it. A SELL stop and a SELL liquidity target are shifted by the spread. |
> | Offline test counts | `test_xau_execution_policy.py` now runs 24 score, 8 veto and 26 guard cases; the whole EA is additionally built and executed by `test_qats_native_build.py` and `test_qats_dual_direction.py`. |

## Scope and exact changes

The deployable source is `MQL5/Experts/QuantumAutonomousTradingSystem.mq5`.
The complete line-by-line patch is available with `git diff -- MQL5/Experts/QuantumAutonomousTradingSystem.mq5`. The XAUUSD rule applies when the chart symbol begins with `XAUUSD` (case-insensitive), including broker suffixes; aliases such as `GOLD` and broker prefixes are not inferred.

- `InpMinScore` defaults to 55; it remains configurable. A valid analysis direction is the existing engine's `dir == +1` or `dir == -1`; a neutral direction or unavailable market data is not a valid signal. There is one analysis per new M5 bar. The existing signal generator and its scoring weights are unchanged; this is not an independent scan of every conceivable SMC setup.
- For XAUUSD, EMA opposition and counter-D1 inputs do not veto a direction, including when an older saved preset enables them. Bias still contributes to the score as before. The execution profile/class thresholds are logged but never act as another XAUUSD score or RR gate. Other symbols retain their configured directional and profile gates.
- Signal journal records show bar, symbol, direction, score, threshold, score eligibility, outcome and rejection reason, independently of `InpVerbose`. Score eligibility is not a guarantee of execution. Existing master switch, account authorization and permissions checks, session, data-age, spread, zone-touch (if enabled), position/trade limits, drawdown, daily-loss, cooldown, RR and sizing controls remain in force.
- Broker symbol data is checked at attach and refreshed before XAUUSD execution, including finite positive point, tick size/value, lot limits/step, step alignment and contract size. SL/TP are rounded outwards to the price tick, then checked against current bid/ask, broker stop distance, current tick grid, configured stop distance and minimum RR before sizing. Sizing continues to use `OrderCalcProfit` and `OrderCalcMargin`.
- XAUUSD submissions are reserved atomically in terminal global variables before sending, keyed by account, magic, symbol, direction and M5 analysis bar. Same-direction decisions on a *new* M5 bar are treated as new signals even if they derive from the same persistent H1 setup. The reservation is flushed and retained after rejection or an uncertain response. There is deliberately no automatic retry for XAUUSD: a timeout, connection problem, broker rejection or failed verification requires journal/account inspection. This is a conservative at-most-once submission policy, not a guarantee of fills. It does not coordinate separate MT5 terminals, different magic numbers, or other EAs. Dry runs do not reserve.
- The prior non-XAUUSD retry behavior remains outside this change. Position verification failure is logged explicitly and is not proof of a fill. Broker-specific symbol rules and fill behavior still require MT5 verification.
- `tools/verify_quantum_ea.py` adds the standard MQL APIs used by the change to its structural verifier allowlist. `tools/test_xau_execution_policy.py` builds a C++ harness using selected actual MQL function bodies and stubbed terminal APIs.

## Compilation report

**MetaEditor compilation: NOT RUN.** This Linux environment has no MetaEditor/MT5 installation. Zero errors and zero warnings cannot be asserted. Run F7 on the deployable source in the target MT5 installation and save the complete MetaEditor build log before use. `python3 tools/verify_quantum_ea.py` passed with no structural-verifier warnings, but it is **not** an MQL compiler.

## Offline tests

- `python3 tools/test_xau_execution_policy.py`: **2 tests passed**. The compiled native harness exercises the real score/stop/reservation/sizing/execution function bodies with stubbed MT5 APIs: 24 BUY/SELL score cases (54, 55, 56, 59, 60, 69, 70, 79, 80, 89, 90, 100); 8 XAUUSD/non-XAUUSD directional-veto cases; and 18 BUY/SELL cases covering duplicate, SL, TP, guard, margin, fractional spread, dry run, ambiguous timeout and tick grid. The absolute-spread/risk guard is stubbed; wiring tests inspect the source. This does not simulate the actual MT5 event loop, real broker specs, fills, or terminal global-variable concurrency.
- `python3 tools/test_quantum_compile_regressions.py`: **4 tests passed**, structural checks only.
- `python3 tools/test_signal_execution_profiles.py`: **138 checks passed**, repository source/reference model checks, not a backtest.
- `python3 tools/verify_quantum_ea.py`: structural checks passed, no verifier warnings.

## MT5 execution test report

**NOT RUN** — no MT5 terminal, Strategy Tester, broker quotes, or demo account were available. Before deployment: compile in MetaEditor; run Strategy Tester for XAUUSD on the broker's actual symbol and specifications; verify both directions and threshold boundaries, opposing EMA/counter-D1, absolute and fractional spread, bad/moved stops, lot-step and min/max sizing, insufficient margin, duplicates including reload/two charts, rejected/ambiguous orders, account and risk locks, and journal reasons. Then repeat on a demo account, verify actual fills and server-side SL/TP. The EA is not production-ready on the basis of these offline tests.

## Account-mode update

The EA now supports REAL only with explicit opt-in and exact login/server confirmation; CONTEST remains blocked. The default preset is DEMO-only. See `docs/QUANTUM_DEMO_REAL_AR.md` for the current setup; no MT5 compilation or execution test has yet been performed.
