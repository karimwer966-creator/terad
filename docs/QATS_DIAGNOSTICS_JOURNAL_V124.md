# QATS Diagnostics & Journal (`QATS_DIAGNOSTICS_JOURNAL`) — v1.24 module, Phase 9

**Status:** implementation landed and offline-verified. **NOT** compile-verified
in MetaEditor, **NOT** backtested, **NOT** demo-forward-tested. No production
claim is made by this document.

Scope: the master audit §8 Phase 9 — the per-setup single-record diagnostic
contract, the `[QATS][FINAL]` decision record, the high-score rejection
explanation, and the RISK_STATUS fold-in. Companion to `QATS_ADAPTIVE_PD_V124.md`,
`QATS_LIQUIDITY_V124.md`, `QATS_DISPLACEMENT_FVG_V124.md`,
`QATS_M5_M1_SCALPING_V124.md`, `QATS_REGIME_SESSION_NEWS_V124.md`,
`QATS_EXECUTION_RISK_V124.md`.

QATS_VERSION remains `1.23`. Nothing about trading decisions changed — Phase 9
is journal-only plus bookkeeping globals; no guard, sizing, or order path is
modified by it.

## 1. The single-record contract

For every **setup** (a side whose core chain passed), on every outcome change,
once per setup per outcome, exactly two records are printed:

```
[QATS][ANALYSIS] bar=2024.03.25 13:00 side=BUY BUY_SCORE=87 SELL_SCORE=4 SCORE=87
       CORE_STATUS=PASS 3/3 STRUCTURE_STATUS=BOS@1866.58(shift 1)
       LIQUIDITY_STATUS=sweep=SSL:SWING@1859.10(shift 2)
       DISPLACEMENT_STATUS=TF=H1 shift=1 STATUS=OK
       PD_STATUS=OK EXECUTION_STATUS=BLOCKED FINAL_DECISION=BLOCKED
       REASON=DAILY_LOSS_LOCK | RISK equity=10000.00 dayPnL=-1000.00(-9.1%)
       DD=0.00% streak=0/3 cap=0/4 dayLocked=yes ddHalted=no cooldown=no
[QATS][FINAL] DECISION=BLOCKED REASON=DAILY_LOSS_LOCK side=BUY SCORE=87 setup=B-20240325-1300
```

Field order follows the mandated contract (master audit, Phase 9): `bar side
BUY_SCORE SELL_SCORE CORE_STATUS STRUCTURE_STATUS LIQUIDITY_STATUS
DISPLACEMENT_STATUS=TF=.. STATUS=.. PD_STATUS EXECUTION_STATUS FINAL_DECISION
REASON`, with `SCORE` (the setup's own score) and the RISK_STATUS exposure map
appended. `DISPLACEMENT_STATUS` carries `TF=` and `STATUS=` literally as the
contract requires. Field order is stable and pipe-separated payloads never
collide with the token grammar (`bull=2026.03.25 13:00` dates/prices carry
spaces only inside the date token — parsers should key on `key=` tokens, as the
in-repo journal tooling does).

**Deduplication is unchanged** — `[QATS][ANALYSIS]`/`[QATS][FINAL]` are keyed
`setup|outcome|reason` per side and print once per setup per outcome, even when
a guard keeps blocking the same setup bar after bar. Both sides that pass core
get their own independent record (a conflict prints two `[QATS][FINAL]` lines
with `rule=` context already journalled by `[QATS][SIGNAL][CONFLICT]`).

**What is NOT a setup** gets no single record: bars where no side passed the
core confirmation print no ANALYSIS line (the `[QATS][SIGNAL][SCORED]` record
already covers them) — the journal does not grow a record per quiet bar.

`FINAL_DECISION` vocabulary: `ENTER_MARKET` (from `EXECUTED`), `ENTER_LIMIT`
(from `LIMIT_PLACED`), `NO_ORDER` (from `DRY_RUN`), otherwise the outcome is
carried verbatim (`BLOCKED`, `REJECTED`, `NOT_PLACED`, `VETOED`,
`BELOW_MINIMUM`, `CONFLICT`).

## 2. Every rejection explains itself — including high-scoring ones

When a setup that still scores ≥ `InpMinScore` is refused (any outcome other
than `EXECUTED` / `LIMIT_PLACED`), one additional record is printed:

```
[QATS][GUARD] SCORE=87 REJECTED AT=RISK_GUARD REASON=DAILY_LOSS_LOCK side=BUY setup=B-20240325-1300
```

`AT=` names the layer: `RISK_GUARD` (anything from the guard chain —
`DAILY_LOSS_LOCK`, `DRAWDOWN_HALT`, `LOSS_COOLDOWN`, `DAILY_TRADE_CAP`,
`OUTSIDE_SESSION`, `NEWS_BLACKOUT`, `PROTECTION`, `MASTER_SWITCH_OFF`,
`EXEC_BLOCKED`), `PD_GATE` (`PD_MARKET`), `SCORE_GATE`, `VETO`, `CONFLICT`,
`DRY_RUN`, `LIMIT_GATE`, or the execution stage for `REJECTED`/`NOT_PLACED`
(`PLAN`, `SIZE`, `SPREAD_VS_STOP`, `RESERVE`, `BROKER`, `LIMIT_PLAN`, …).
It is deduplicated per setup per outcome like the other records. This is the
mandated `SCORE=78 REJECTED AT=RISK_GUARD REASON=…` shape for "why a
high-scoring setup was rejected".

## 3. RISK_STATUS folded into the per-setup record

The Phase 8 `BuildRiskStatus` exposure map (equity, day P/L money/%, equity
HWM, DD %, streak with its cap, daily-cap usage, `dayLocked`, `ddHalted`,
cooldown) is appended to every `[QATS][ANALYSIS]` record as the `| RISK …`
tail. The heartbeat keeps its own `[QATS][RISK]` line. Phase 9 journals it; it
enforces nothing — the guard chain remains the only enforcer.

## 4. Dedup, wiring, compatibility

- `JournalSetupRecord()` is called from the one outcome funnel
  (`LogSignal`), before the SCORED dedup — the single records have their own
  per-side dedup and are unaffected by `InpVerbose`.
- `[QATS][SIGNAL][SCORED]`, `[QATS][BLOCK][REASON]`, `[QATS][EXECUTION]*`,
  `[QATS][GUARD] position …` are unchanged; the journal-report tool parses
  SCORED only and its contract is untouched (33/33).
- No behavior change anywhere else; `g_lastAnalysisKey`/`g_lastGuardKey` are
  the only new state.
- Diagnostics volume is bounded by setup count, not bar count.

## 5. NC-6 (DrawPanel via Comment()) — resolution

Kept, documented, not re-engineered. `Comment()` text is re-drawn on **every
tick**, so a chart change that clears it self-heals within a tick; the panel's
content is fully redundant with the journal (`[QATS][HB]`, `[QATS][RISK]`,
`SCORED`). Moving the panel to chart objects would add object-lifecycle and
deinit-cleanup risk for zero decision value — rejected as unnecessary
engineering. Standing limitation, recorded here and in the audit addendum.

## 5a. NC-7 (same-bar double break) — log-once

Already implemented (via `g_loggedDoubleBreak`, in place since the structure
work and present in the phase working tree): when one closed bar satisfies
both break branches, BuildStructure credits neither side, resets trend/
break state, and prints once per session
`[QATS][STRUCTURE] same closed bar <t> satisfies BOTH break branches - contradictory data, neither side credited (trend reset)`.
The audit's "→ Phase 9 log-once" box is ticked rather than re-done; the
guard against same-bar double-crediting was already in place, and the
log-once output makes it visible to the operator as mandated.

## 5b. NC-11 (no trailing stop)

Intentional design: break-even + partial bank only; no trailing. Documented as
a known limitation across the phase docs; unchanged in Phase 9.

## 6. Verification (offline C++ transpile + g++ shim — NOT MetaEditor)

- `verify_quantum_ea.py` — clean (`user_functions=166`); one in-phase dialect
  regression caught by the F5-class lint (`const SSide &e` local reference)
  and fixed before any green claim.
- Unit suite **558/558** (540 → 558; new `unit.diagnostics_record`: single
  record per setup per outcome, both scores + core/structure/sweep/
  displacement/PD status, RISK fold-in, per-side independence, dedup on
  repeat outcome, re-print on outcome change, no record for a coreless bar,
  GUARD explanation at `AT=RISK_GUARD`).
- New mirror-pair scenario `diagnostics_record_buy/sell` — blocked chain:
  `DAILY_LOSS_LOCK` named in ANALYSIS/FINAL/GUARD, FINAL printed once per
  setup per outcome; phase 2 (no lock): same tape executes, record carries
  `FINAL_DECISION=ENTER_MARKET`, no rejection explanation (20/20 each).
- `test_qats_dual_direction.py` — **91/91** (89 + the 2 new scenario mirror
  legs; the buy/sell mirror-parity pairs report identical mirrored entries).
- `test_qats_limit_entry.py` — **98/98**; `test_qats_journal_report.py` —
  **33/33**; `test_qats_native_build.py` — **62/62**;
  `check_production_ready.py` — **57/57 OFFLINE GO**.
- In-phase bugs before any green claim: MQL5 reference-local rejected by the
  dialect lint; scenario's daily-loss baseline was keyed against a pre-attach
  clock (1970) — armed after the tape clock was on its day; phase-2 assertion
  originally demanded zero GUARD lines, but post-fill blocked evaluations
  while holding the position legitimately explain themselves — the assertion
  was narrowed to the executed outcome, not deleted.

## 7. What did NOT change

- No guard, cap, sizing, SL/TP, PD, session, regime, news or reservation
  behavior changed. No inputs added. Preset unchanged. REAL disarmed.
- QATS_VERSION remains `1.23`.

## 8. Unresolved / deferred

- MetaEditor F7, Strategy Tester, demo forward test — Phase 10. The demo
  forward test is where these records get read live (the journal report tool
  consumes them).
- The `[QATS][ANALYSIS]` record is not yet consumed by any automated report;
  the DEMO journal review (Phase 10) is the consumer.

## 9. Files

- `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` — Phase 9 sections
  (`QATS_DecisionName`, `QATS_RejectAt`, `QATS_Core/Structure/Sweep/
  DisplacementText`, `JournalSetupRecord`, wiring in `LogSignal`,
  `g_lastAnalysisKey`/`g_lastGuardKey`).
- `tools/qats_sim/qats_selftest.inc` — `unit.diagnostics_record`.
- `tools/qats_sim/qats_scenarios.inc` — `diagnostics_record_buy/sell`
  (mirror pair).
- `docs/SYSTEM_ARCHITECTURE.md` — journal sample carries `[QATS][RISK]`.
