# QATS Execution & Risk (`QATS_EXECUTION_RISK`) — v1.24 module, Phase 8

**Status:** implementation landed and offline-verified. **NOT** compile-verified
in MetaEditor, **NOT** backtested, **NOT** demo-forward-tested. No production
claim is made by this document.

Scope: the master audit §8 Phase 8 — execution-guard coverage, deal-history
scan bound, per-bar memoization, partial-fill accounting, limit-order send
validation, GV flush verification, and the RISK_STATUS exposure map for the
Phase 9 journal contract. Companion to `QATS_ADAPTIVE_PD_V124.md`,
`QATS_LIQUIDITY_V124.md`, `QATS_DISPLACEMENT_FVG_V124.md`,
`QATS_M5_M1_SCALPING_V124.md`, `QATS_REGIME_SESSION_NEWS_V124.md`.

QATS_VERSION remains `1.23`; the v1.24 tag names the Phase 2–10 upgrade track,
not a released version. Direction of every change: **protections added or
exposed — never relaxed.** No risk cap, SL/TP rule, or sizing math changed.

## 1. CR-3 — atomic reservation on EVERY symbol

The one-reservation-per-setup mutex (`GlobalVariableSetOnCondition`) existed
only for XAUUSD. Now:

- `InitSignalKeys()` runs unguarded at attach — **an account/terminal that
  cannot persist the reservation refuses to run (`INIT_FAILED`)**, on every
  symbol. XAUUSD keeps the exact legacy key names (`GVKey` already embeds
  account + magic + symbol, so other symbols get parallel namespaced keys).
- `ReserveSignal()` is called by the market path and the limit path on every
  symbol (previously `if(IsXAUUSD() && …)`).
- A consequence, made explicit: `ProcessPendingRetry()` carries the
  reservation into the retry (`ExecuteSignal(plan, /*reserved=*/true)`), so a
  re-submitted plan is not bricked by its own first-attempt reservation. A
  reserved signal still never auto-retries on **REAL** accounts, and XAUUSD
  keeps its no-automatic-retry policy after ambiguous sends (unchanged,
  pinned by the rejection scenario). No protection was removed; DEMO
  non-XAUUSD symbols keep their 3-retry budget, now functional.
- **Limit orders re-validate at the send boundary** exactly as before (full
  guard chain, opposite-position check, setup-spent check at placement), and
  the final filling-policy attempt still sends the order itself only after
  all other policies were rejected (`IsInvalidFillRetcode` loop unchanged).

## 2. Verification of the reservation itself (`GV flush`)

`ReserveSignal()` now re-reads the key after `GlobalVariablesFlush()` and
**fails closed** (`reservation did not persist (GV flush verification failed)`)
if the persisted value is not at least the reserved bar. A reservation that
existed only in RAM no longer authorizes an order. `InitSignalKeys()` applies
the same persistence check to both direction keys after its flush. The
scenario harness confirms a reservation is not spent by a dry run, is consumed
once, and survives the ambiguity paths (rejection scenario: refused order
consumes nothing; the same bar is re-evaluated next bar exactly once).

## 3. CR-5 — deal-history scan is watermark-bounded

`ProcessClosedDeals()` no longer rescans 30 days every M5 bar. A persisted
`last_deal_time` watermark (time of the newest counted deal) bounds the scan
to `[max(lastDealTime − 6h, now − 30d), now + 1d]`; the ticket filter against
`last_deal` prevents any double counting regardless of the window.
`InitDealWatermark()` seeds **both** watermarks from a single 30-day lookback
on first sight (once per account/magic/symbol), so an upgrade from a pre-CR-5
tree does not rescan-per-bar either. The 6h slack covers late-arriving stamps;
the 30d floor keeps the worst case no worse than the old behavior.

## 4. NC-2 — per-bar memoization of swings + liquidity pools

`AnalyzeMarket`, `BuildTradePlan` and `BuildLimitPlan` each rebuilt the swing
sets and the liquidity map on the same bar (2–3× the series work per M5 bar).
A new `LiquidityContext()` builds them once per H1 bar and hands out
element-copies:

- Cache key: the closed-bar H1 context — newest closed bar time, bar count,
  and shift-1 close/high/low. A re-read of the same series hits; anything
  else rebuilds. Closed bars never change inside a decision, so the cache is
  exact for the decision path.
- The offline harness clears the cache in `resetSimOnly()` on every tape
  swap (mirror replays included) — a stale pool map can never leak across
  markets in the simulator.
- `JournalLiquidityTransitions` still runs once per evaluation (in
  `AnalyzeMarket`), unchanged.

## 5. Partial-fill accounting (market path)

`QATS_FillShort(requested, filled)` (shared predicate, unit-pinned with a
1e-8 epsilon) drives a new `[QATS][EXECUTION][PARTIAL]` line when the broker
fills less than requested (DONE_PARTIAL or a short DONE): requested vs
filled, the shortfall, the retcode. The fill is still treated as
filled-with-report — verified via `VerifyPositionOpened`, counted against the
daily cap, the setup spent exactly once — never silently sized up or down.
The `[EXECUTION][FILLED]` line now carries `requested=` next to `volume=`.

Honest limitation: the offline shim cannot make a broker return a partial
fill, so the end-to-end behavior is verified by the unit-pinned predicate
plus the unchanged success path; the `[PARTIAL]` line fires only on a real
(or MetaEditor-simulated) partial fill. At FILL time for resting LIMIT
orders, the entry deal volume is logged with every `[QATS][DEAL]` line; a
volume-vs-placed comparison would need an order-history API the shim does not
model and is recorded here as not implemented offline (Phase 10 observation).

## 6. RISK_STATUS exposure map (for the Phase 9 journal)

`BuildRiskStatus(SRiskStatus&)` + `RiskStatusText()` expose, read-only:
equity, day P/L (money and % of the server-day baseline), equity HWM,
drawdown % with the effective cap and % of cap used, loss streak with its
cap, daily-cap usage (`tradesToday`/`InpMaxTradesPerDay`), day-loss % with
the effective cap, `dayLocked`, `ddHalted`, cooldown state and deadline, and
margin usage (`used/(used+free)`). The heartbeat now prints a one-line
`[QATS][RISK] …` record per heartbeat alongside `[QATS][HB]`. Nothing is
enforced by the map — the guard chain remains the only enforcer; Phase 9
folds the same object into the per-setup ANALYSIS record.

## 7. Verification (offline C++ transpile + g++ shim — NOT MetaEditor)

- `verify_quantum_ea.py` — clean (recognizes `SSwing` globals now;
  `user_functions=159`, `globals=78`).
- `test_qats_native_build.py` — **62/62**; `qats_selftest` unit suite —
  **540/540** (486 → 540; four new suites — `unit.fill_short`,
  `unit.reservation`, `unit.risk_status`, `unit.liquidity_context` — each
  also carrying the standard sim-diagnostics guard).
- `test_qats_dual_direction.py` — **89/89** (mirror replay still 0 bar
  mismatches with the memoized context in the decision path).
- `test_qats_limit_entry.py` — **98/98**; `test_qats_journal_report.py` —
  **33/33**; `check_production_ready.py` — **57/57 OFFLINE GO**.
- In-phase bugs fixed before any green claim: forward prototypes for the new
  functions required the `SRiskStatus` struct in house style (single-line
  comment) for the transpiler's struct discovery; the memoization cache key
  was strengthened from the bare H1 bar time after review showed the offline
  harness reuses identical bar times across tape swaps (harness now clears
  the cache on swap); one unit fixture initially assumed `g_dayBase` equals
  the simulated equity and was corrected to derive from the live sim equity.

## 8. What did NOT change

- No risk cap, daily lock, drawdown halt, cooldown, sizing, margin, SL/TP,
  PD gate, session, regime or news behavior changed.
- `IsXAUUSD()` remains for POLICY/diagnostics and profile behavior; only the
  reservation gates were generalized. REAL stays triple-opt-in and disarmed;
  DEMO-first posture untouched.
- QATS_VERSION remains `1.23`.

## 9. Unresolved / deferred

- MetaEditor F7, Strategy Tester, demo forward test — Phase 10 (the partial
  fill path and the terminal calendar need a live/simulated terminal).
- Order-history API for limit-fill volume comparison — shim/terminal work
  deferred; the DEAL journal line carries the filled volume today.
- `RISK_STATUS` is reported in the heartbeat only; the per-setup ANALYSIS
  record is Phase 9.

## 10. Files

- `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` — Phase 8 sections
  (`SRiskStatus`; `QATS_FillShort`; reservation universalization + GV flush
  verification; `last_deal_time` watermark-bounded scan incl.
  `InitDealWatermark` seeding; `LiquidityContext` memoization;
  `[QATS][EXECUTION][PARTIAL]`; `[QATS][RISK]` heartbeat line).
- `tools/qats_sim/qats_selftest.inc` — four new unit suites (540 checks).
- `tools/qats_sim/qats_market.inc` — harness clears the memoization cache on
  tape swaps (`resetSimOnly`).
- `tools/verify_quantum_ea.py` — `SSwing` recognized as a global type
  (additive).
- `docs/SYSTEM_ARCHITECTURE.md` — journal sample carries the `[QATS][RISK]`
  record.
