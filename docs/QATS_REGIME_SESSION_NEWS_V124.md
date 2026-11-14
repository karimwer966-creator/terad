# QATS Regime / session / news (`QATS_REGIME_SESSION_NEWS`) — v1.24 module, Phase 7

**Status:** implementation landed and offline-verified. **NOT** compile-verified
in MetaEditor, **NOT** backtested, **NOT** demo-forward-tested. No production
claim is made by this document.

Scope: the master audit §8 Phase 7 (`QATS_REGIME_SESSION_NEWS`) — regime,
session windows, news guard (CR-6). Companion to `QATS_ADAPTIVE_PD_V124.md`,
`QATS_LIQUIDITY_V124.md`, `QATS_DISPLACEMENT_FVG_V124.md`,
`QATS_M5_M1_SCALPING_V124.md`.

QATS_VERSION remains `1.23`; the v1.24 tag names the Phase 2–10 upgrade track,
not a released version.

## 1. Market regime — REPORT-ONLY, never a veto

Mandate: regime rules are *report-only first*; gating only if evidence
justifies it. Implemented exactly that way. **No entry decision changes by any
regime value.** A `REGIME=` field appears on every `SCORED` journal line and is
the only consumer.

**Classification** (`ClassifyRegime`, pure and unit-tested; `ComputeRegime`
feeds it):

- `volRatio` = `ATR(H1, shift 1)` / median of the last `InpRegimeAtrWindow`
  (default 100) closed H1 ATR values (shift 1 onwards; insertion-sort median,
  once per evaluation).
- `volRatio >= InpRegimeHighVolMult` (default 1.5) → `HIGH_VOL` (boundary
  inclusive). `volRatio <= InpRegimeLowVolMult` (default 0.5) → `LOW_VOL`.
- else `TREND_BULL` if `close > EMA20 > EMA50 > EMA200`; `TREND_BEAR` for the
  mirror chain (new H1 EMA-200 handle `g_hH1Slow200`, read at shift 1,
  created/checked/released with the other handles).
- else `RANGE` if `|EMA20 − EMA50| <= 0.5 × ATR` (fast/slow pair flat vs one
  ATR).
- else `UNCLEAR`. **Fail closed to UNCLEAR** whenever the ATR median or the
  current ATR is unreadable — never a plausible-looking guess.
- `rangeRatio` (report-only context, never a classifier input):
  `(HH20 − LL20) / (HH100 − LL100)` over closed H1 bars — the share of the
  100-bar range the last 20 bars span.

`SAnalysis` gains `regime` (string label), `regimeVolRatio`,
`regimeRangeRatio`; `SRegime` struct after `SSweep`; `ResetAnalysis` defaults
all three to `UNCLEAR` / 0.0. `InpRegimeEnable` (default **true**) only decides
whether the computation/journal line runs; set false to skip the H1 ATR reads.
The news block and this report-only regime do NOT interact.

## 2. Sessions — behavior UNCHANGED, broker→UTC offset is advisory

The session guard is byte-identical to v1.23: broker **server-time** hour
window (`InpSessionStartHour/InpSessionEndHour`, 0/0 = all day, overnight
windows supported), `TimeTradeServer()`, no gating by UTC.

What Phase 7 adds is disclosure, NC-8:

- new advisory input `InpBrokerUtcOffsetMinutes = 0` — minutes from broker
  server time to UTC, printed at attach with an explicit note that the broker's
  own DST follows its server clock, not this input. It is **never** used for
  gating. Operators on NY-close (e.g. +120 winter / +180 summer) or GMT+3
  brokers set it so attach-time and logs are interpretable.
- attach banner lines: `[QATS][SESSION] trading windows are BROKER SERVER hours …
  broker->UTC offset input = %+d min (advisory only …)`.

The broker-midnight daily reset and the server-time session windows are
documented behavior (audit NC-8); they are not converted to UTC.

## 3. News / calendar guard (CR-6) — OPT-IN, fail-OPEN for trading

Mandate (audit §4 CR-6): *implement optional `CalendarValueHistory`-based guard
(currencies=XAU/USD, importance=high, configurable minutes before/after);
failure = log `[QATS][NEWS] CALENDAR_UNAVAILABLE — no events assumed, entries
NOT blocked by unverifiable data` once per session, never fabricated. Explicit
terminal verification required before any production claim.* Both honest
outcomes were implemented: the guard exists behind an opt-in input, and the
verification limitation is documented in code and here.

**Design contract**

- `InpNewsFilterEnable = false` by default. When off, the guard does not even
  run (no calendar calls are made per bar).
- When armed: entries are blocked while **any** calendar event with
  `importance >= InpNewsMinImportance` (default 3 = `CALENDAR_IMPORTANCE_HIGH`)
  for a watched currency (`InpNewsCurrencies`, default `USD,XAU`)
  sits inside `[now − InpNewsBlockAfterMin, now + InpNewsBlockBeforeMin]`
  (defaults 30/30 minutes, server time).
- Block code `NEWS_BLACKOUT` via `AddBlock` (after the session block); the
  `[QATS][BLOCK][REASON]` journal line names it, with event count, threshold
  and watched currencies.
- **An unreachable calendar blocks NOTHING.** `NewsHighImpactInWindow` reads the
  window once (`CalendarValueHistory` 3-arg) and joins values to the event
  library by `event_id` — `MqlCalendarValue` carries NO importance/currency of
  its own (importance lives on the event; the terminal-proven join used by
  nadir2 is the pattern). Each watched currency is matched via
  `CalendarEventByCurrency`; a currency lookup that fails is unverifiable for
  **that currency only** (fail-open — never fabricated). If the calendar read
  itself fails, or no watched currency verifies, entries are allowed and
  `[QATS][NEWS] CALENDAR_UNAVAILABLE …` is printed **once per attach** (never
  per bar). Partial reachability still enforces the reachable currencies.
- `NewsEntriesAllowed` also prints a one-time armed-line at first reachability
  (`[QATS][NEWS] enabled: importance>=… around …, window …`) so the operator
  can see the guard is actually reading the calendar, not merely switched on.

**The verification limitation is real and standing.** Whether MetaQuotes'
economic calendar is populated on the operator's terminal can only be verified
in MetaEditor on that platform — **F7 attempt #1 (2026-11-14, `d3df3f6`) failed with
one error: `undeclared identifier 'importance'` (the EA read importance off
`MqlCalendarValue`, which has none)** — and it was fixed to the event-join
pattern (see changelog 2026-11-14-F7-1). Two names used by the fixed join
could not be verified offline and are called out explicitly: `CalendarEventByCurrency`
and `MqlCalendarEvent.id`. If F7 attempt #2 reports either, the implemented
fallback is documented there (block on any high-importance event in the
window + explicit journal line; entries never blocked by unverifiable data,
never fabricated). Until a clean F7: the filter ships default-false, and no
production claim may cite it as active protection. If the terminal's calendar
turns out to be dead, keep `InpNewsFilterEnable=false` and treat news risk as
a documented operator responsibility (the demo forward test is where calendar
liveness will be observed).

**Offline exercisability.** The shim (`tools/qats_sim/mql5_shim.h`) now models
the calendar: `sim::State::calMode` (0 = reachable, 1 = unreachable; non-zero
makes `CalendarValueHistory` fail like an empty/unpopulated terminal — never a
fake positive) and `calEvents` (time/importance/currency seeds). The EA's
`CalendarValueHistory` call is therefore fully exercised offline.

## 4. What did NOT change

- No entry, exit, sizing, SL/TP, guard, or limit-entry decision changed.
  With defaults (`InpNewsFilterEnable=false`, `InpRegimeEnable=true`) the EA
  behaves exactly as the Phase 6 tree, plus one extra `REGIME=` journal field.
- Session windows: server-time enforcement identical to v1.23.
- REAL account authorization, DEMO-first posture, daily locks: untouched.
- QATS_VERSION remains `1.23`.

## 5. Verification (offline C++ transpile + g++ shim — NOT MetaEditor)

- `verify_quantum_ea.py` — clean (its native allow-list gained
  `CalendarValueHistory`; a used-but-unallowlisted API is the one failure mode
  it exists to catch).
- `test_qats_native_build.py` — **62/62**. The EA builds clean against the
  strictly-typed shim (the calendar model included); F7 remains the real gate.
- `qats_selftest` unit suite — **486/486** (added `unit.regime`: classification
  boundaries inclusive, fail-closed UNCLEAR, RegimeName mapping, range-breadth
  fixtures incl. mirror invariance; `unit.news_filter`: window before/after,
  importance threshold, unwatched currency, XAU watch, unreachable calendar
  allows + journals exactly once).
- `test_qats_dual_direction.py` — **89/89** (87 prior + 2 new mirror-pair
  scenario checks: bar-mismatch replay and trade-twin checks pass with the
  Phase 7 code in the tree). Mirror replay: 0 bar mismatches.
- New scenario `news_blackout_buy/sell` — armed filter blocks the full
  synthetic chain (with `[QATS][BLOCK][REASON] NEWS_BLACKOUT`), disarmed filter
  trades the same tape, unreachable calendar trades the same tape with exactly
  one `CALENDAR_UNAVAILABLE` line. 12/12 checks each side.
- `test_qats_limit_entry.py` — **98/98** (its `.set` completeness check pins
  the preset to name exactly the compiled inputs — the preset gained the ten
  Phase 7 inputs).
- `test_qats_journal_report.py` — **33/33**.
- `check_production_ready.py` — **57/57 OFFLINE GO**.
- One in-phase bug class: the news guard initially landed inside
  `GuardBlocks()` (function-definition-in-function-body); moved to file scope
  before SECTION 18; the intermediate never claimed green.

## 6. Unresolved / deferred

- Terminal calendar liveness on the operator's platform — **Phase 10**
  (MetaEditor / live terminal observation on demo). Until then the filter is
  default-off and advisory at best.
- Regime thresholds (1.5 / 0.5 / 0.5-ATR flat band) are engineering defaults,
  never evidence-tuned; any future regime gating (e.g. refusing trend entries
  in LOW_VOL) requires out-of-sample evidence per Phase 6's readiness gate, and
  would land as its own documented phase with audit.
- MetaEditor F7, Strategy Tester, demo forward test — Phase 10.
- The broker→UTC offset input is advisory only; a future phase could enforce
  UTC windows if and when the operator's terminal exposes reliable server DST.
  Today's guard text does not change.

## 7. Files

- `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` — Phase 7 sections (inputs
  5d; `g_hH1Slow200`; `SRegime`; regime engine; news/calendar guard;
  `NEWS_BLACKOUT` block; `SCORED` journal field; attach-banner lines).
- `tools/qats_sim/mql5_shim.h` — calendar model (`calMode`, `calEvents`,
  `MqlCalendarValue`, `CalendarValueHistory`).
- `tools/qats_sim/qats_selftest.inc` — `unit.regime`, `unit.news_filter`
  (486 unit checks total).
- `tools/qats_sim/qats_scenarios.inc` — `news_blackout_buy/sell` scenario pair.
- `tools/verify_quantum_ea.py` — `CalendarValueHistory` added to the native
  allow-list (additive).
- `presets/Quantum_XAUUSD_PRODUCTION.set` — the ten Phase 7 inputs.
- `docs/SYSTEM_ARCHITECTURE.md` — `SCORED` sample line carries `REGIME=`.
