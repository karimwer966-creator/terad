# QSMC v6.6.24 — full-repository audit and demo-trial readiness

**Date:** 2026-11-16 · **Base:** `cb8785a` (v6.6.23, PR #74) · **Branch:**
`arena/6a85293d-terad` · **Target:** a build that can be attached to a **DEMO**
account at **0.10 % risk per trade**.

**No profitability claim is made anywhere in this document.** Nothing here is a
backtest, a win rate, or a forecast. The score the engine prints is *evidence
strength*, not probability.

---

## 0. What this audit could and could not do

| | |
|---|---|
| **MetaEditor compile** | **NOT DONE.** The host is Linux and has no MQL5 compiler. `F7` remains the first real compile. Every "verified" below is a source-level or native-C++ statement, never an MQL5 build. |
| **Backtest / optimisation** | **NOT DONE.** No history was replayed; no parameter was tuned. |
| **Runtime in a terminal** | **NOT DONE.** `QSMC_RunSelfTest()` has not been executed. |
| **Native execution of the extracted rules** | **DONE.** `tools/test_execution_rules.py` and `tools/test_candle_patterns.py` compile the *shipped headers* with `g++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined` and execute them. |
| **Static gates** | **DONE.** `check_production_ready.py`, `check_repo_layout.py`, `check_presets.py`, `check_release_gate.py`, `static_check.py`, `mql5_rules.py`, `test_arbiter.py`, plus the EA contract suites. |

### Coverage, stated honestly

Read end-to-end: `QSMC_Zones.mqh`, `QSMC_ZoneScorer.mqh`, `QSMC_Reaction.mqh`,
`QSMC_ExecutionRules.mqh` (new), `QSMC_CandlePatterns.mqh` (new),
`QSMC_UnifiedDecision.mqh` (merge/keys/log), `QSMC_Gates.mqh` §5,
`QSMC_MarketData.mqh`, `QSMC_DataProvider.mqh`, and in
`QSMC_AutoTrader.mq5`: the globals, the key/namespace helpers, the day guard,
the session/account guards, sizing (`CalcLots`), the review, the whole send path
(2600–2900), position management (3818–3960), the housekeeping, and `OnInit`'s
tail.

Read partially (targeted greps + the cited regions): `QSMC_Root.mqh`,
`QSMC_Arbiter.mqh`, `QSMC_Selftest.mqh`, `QSMC_Stats.mqh`, `QSMC_Scanners.mqh`,
`QSMC_InputFingerprint.mqh`, `QSMC_IncidentSafety.mqh`, `QSMC_ChartLayers.mqh`,
`QSMC_SvpChart.mqh`, `nadir2.mq5`.

**Not read line by line:** `nadir2.mq5` as a whole (45 002 lines), the five
`QSMC_Svp*` modules, `QSMC_Renderer.mqh`, the QATS product
(`QuantumAutonomousTradingSystem.mq5`), and the UI/drawing internals of
`QSMC_ChartLayers.mqh`. Findings there are therefore *not* claimed.

## 1. Inventory

| Area | Files | Notes |
|---|---|---|
| `MQL5/Include/QSMC/*.mqh` | 31 → **33** | 16 225 lines before this cycle; +2 headers (`ExecutionRules`, `CandlePatterns`), both dependency-free by design |
| Indicators | `nadir2.mq5` (45 002 lines, mirrored byte-identically), `QSMC_ScannerProbe.mq5`, `QSMC_SmcVpEngine.mq5` | mirrors verified with `cmp` after the version bump |
| Experts | `QSMC_AutoTrader.mq5` (~5 160 lines), `KLJ_DataFeeder.mq5`, QATS (separate product) | QATS is out of scope and keeps its own version line |
| Scripts | `QSMC_ArbiterTest.mq5`, `QSMC_ResetGuards.mq5`, **`QSMC_BufferDump.mq5`** (new, R4) | |
| Tools | 60+ Python suites | +4 new: `test_execution_rules.py`, `test_candle_patterns.py`, `analyze_trial.py`, `preflight_demo.py` |
| Presets | 9 bound to their sources | all four executing EA presets exercised this cycle |

## 2. The signal path, as it actually runs

```
nadir2.mq5 (OnCalculate, closed bars only)
  └─ QSMC_UnifiedDecision / gates / arbiter
       ├─ buffer 7  CORE_DIR     ─┐
       ├─ buffer 8  CORE_ENTRY    │  the executor's whole input
       ├─ buffer 9  CORE_SL       │
       ├─ buffer 10/11/12 TP1..3  │
       └─ buffer 21..25 class/score/reliability/rr1/risk_mult ─┘
                                   │
QSMC_AutoTrader (OnTick / OnTimer, last closed bar + InpMaxSignalAgeBars)
  └─ ProcessSignals → SeenBefore → ReadClassification
       └─ HandleSignal
            ├─ gate re-checks (spread, stops, session, positions)
            ├─ CalcLots (class multiplier → cap → HARD ceiling)
            ├─ ClaimExecutionLane (cross-EA)
            ├─ RunEntryReview (12 conditions)
            ├─ TradeEnvBlock (account gate, again)
            ├─ CTrade::Buy/Sell
            └─ verify from the ACCOUNT: retcode class → position exists →
               server-side SL/TP on the right side → only then g_sent++
                 ├─ missing protection → repair → else close / emergency lockout
                 └─ unverifiable → UNCONFIRMED (marked seen, slot consumed)
```

Two facts about this path drive most of the findings below: **nothing between
the buffer and the order is re-derived from the market**, and **every refusal is
a log line, not a state** — so a refusal that does not print is invisible.

## 3. Findings

Severity: **S1** = can lose money or silently stop protecting it · **S2** =
misleads the operator or leaks a resource · **S3** = dead code / hygiene.

### Class A — fixed in this cycle (pure bug, fail-safe, misleading text, perf)

| ID | Sev | File | Defect | Fix |
|---|---|---|---|---|
| **F-001** | S2 | `QSMC_AutoTrader.mq5` | The execution-lane claim (`QSMC_EXEC_OWNER_*`) was never released: `ReleaseExecutionLane()` had **no call site**, and nothing expired a claim, so the terminal accumulated one global per signal bar for the life of the installation. | `SweepStaleLaneGlobals()` once per server day (drops claims > 7 days, which can never be executed again — `InpMaxSignalAgeBars` is 1) + release on permanent abandonment. |
| **F-002** | S1 | same | The cross-EA ownership lane **could never refuse anything**: the claim's NAME contained `InpMagic` and its VALUE was `InpMagic`, so `owner!=(long)InpMagic` was unreachable. Two executors with different magics never even saw each other's claim. | Name = (login, symbol, key) — the identity of the BAR; value = the owning magic. Single-EA behaviour is bit-identical. |
| **F-003** | S1 | same | The transient-retry budget was ONE `(key,count)` slot reset by *any* other key, so two signals alternating their failures restarted the counter forever and `InpOrderRetryMax` was never reached — the flood it exists to prevent. | Fixed table of 8 identities keyed by `SignalKey()`, with `QER_RetryFind/Allows/NextSlot` (native-tested). New bar = new identity; old identity keeps its count. |
| **F-004** | S2 | same | Both `UNCONFIRMED` journal lines said only "not counted as sent; check the Journal before the next bar", while the code *did* mark the signal seen (no retry, ever) and *did* consume an entry slot. An operator waiting for a retry waited while the day's budget was already spent. | Text states all three facts, with the live "trades today = X of Y". |
| **F-005** | S3 | `QSMC_Gates.mqh` | `CRoomGate` published `SIG_LIMITED_ROOM` as its downgrade value while every branch returned `GATE_FAIL`: a value nothing could read, and an invitation to soften a hard reject later. (**T9** of the owner's list.) | Publishes `SIG_NONE`; the enum keeps value 6 (published state space), documented as never produced by this gate. |
| **F-006** | S1 | EA + 4 presets + docs | `InpMaxSignalAgeBars = 2` let the executor fill a plan the indicator had validated on a bar up to 30 minutes old on M15. (**T12**.) | Default **1** everywhere (EA, presets, generator, defaults-vs-preset pin, docs). Strictly narrowing. |
| **F-007** | S2 | `QSMC_UnifiedDecision.mqh` + docs | (**T8**.) The merge already rebuilds the geometric id; what was missing was a pin and the upgrade note. | Native assertions that the merged id is `ZRE_ZoneId(side, union_lo, union_hi)` and equals no constituent; documented one-time key reset on upgrade. |
| **F-010** | — | EA + `QSMC_ExecutionRules.mqh` | The breaker arithmetic and all twelve review conditions were inline expressions no test could execute. | Extracted to side-effect-free functions the EA calls; `tools/test_execution_rules.py` compiles and executes them (truth tables incl. every boundary). |
| **F-011** | S2 | EA | `PurgeStaleSignalGlobals()` built its prefix **without the account login** that `GlobName()` includes, so `StringFind` never matched: the purge removed nothing, ever, and every seen key stayed in the terminal. | One `SeenNamespace()` used by both the writer and the purge. Current-day keys are still kept (that is what stops a re-fire after a reload). |

### Class B — separate commits, `[needs owner approval]` (change WHICH signals are taken)

| ID | Sev | File | Defect | Effect |
|---|---|---|---|---|
| **F-008** | S1 | `QSMC_Reaction.mqh` | `piercing` required `r_c > p_o` **and** `r_c < (p_o+p_c)/2` while the prior bar is bearish (`mid < p_o`). `dark_cloud` required the mirror image. Both were **algebraically unsatisfiable** — two of the four named reversal patterns could never fire, silently. | Restores two evidence shapes: `evidence_count` can rise, score +10, more candidates can pass `min_evidence`/`min_score`. |
| **F-009** | S1 | `QSMC_Reaction.mqh` | The E3 volume branch granted `QEV_VOLUME` when the median was `<= 0` ("no baseline: not refuted"), i.e. **absent data scored** — the one place in the detector that contradicted its own doctrine. | On a symbol with unusable volume history, one fewer evidence group and −10 score: fewer candidates. |

Both are shipped as separate commits on this branch so the owner can drop either
one without touching the other. Neither touches risk, stops, size or a ceiling.

### Class C — observations, no change made

* **C-1 `R3 TICK_AGE` cannot detect a totally frozen feed.** The check compares
  `SYMBOL_TIME` against `TimeCurrent()`, and both freeze together if no tick
  arrives anywhere in the terminal. In practice a total freeze also stops
  `OnTick`, so no order can be attempted from a stale clock — but the review
  line will read PASS during the freeze, and an operator reading it later could
  believe the check proved liveness. Documented, not changed: the alternative
  (`TimeLocal`) introduces a server/local offset that would produce a false FAIL
  every day on a broker whose server clock differs.
* **C-2 `Note()` throttles against the PREVIOUS tag only.** Two refusals
  alternating (A, B, A, B) both print on every poll. On a 1-minute chart with a
  wide spread this can produce a few hundred lines a day. Cosmetic; the journal
  (R1) is the record.
* **C-3 `CooldownActive()` fails OPEN if `HistorySelect` fails.** A transient
  history read failure releases the post-loss cooldown. Changing it to fail
  closed would block trading on a broker hiccup, which is worse; recorded so the
  owner can decide.
* **C-4 `CalcLots` in FIXED mode refuses a volume whose risk cannot be priced**
  (`OrderCalcProfit` failure), which is correct — but it refuses *silently* in
  the sense that the operator sees the reason only in the Experts tab, not in
  the Dashboard. R1 now records it.
* **C-5 `QSMC_DataProvider` is dashboard-only.** No signal path reads it; a
  stale file can therefore change a displayed label but never a trade.

### INVALID — premises from the brief that do not match the code

| Claim | Verdict | Evidence |
|---|---|---|
| "`CBarSeries` may publish a partial `CopyRates` under the same indexes" | **INVALID** | `Refresh()` sets `m_ready=false` and returns the *previous* count on `got<m_need` and on `ArraySize(tmp)<m_need`; `Ready()` is what every consumer tests. The forming bar is the only index the fast path rewrites. |
| "`ClosedIndex()` may be off by one / the series may repaint" | **INVALID** | `ClosedIndex() = m_count-2` with `m_count` chronological and `m_count-1` the forming bar; every confirmed reader clamps (`bar_index<1 \|\| bar_index>last_closed → return false`). |
| "`MedianVolume()` includes the evaluated bar in its own baseline" | **INVALID** | `CReactionDetector::Evaluate` calls `MedianVolume(bar_index-1, lookback)` — the baseline ends at the previous bar. |
| "`InpDryRun` should default to true" | **INVALID (owner decision)** | The owner explicitly refused this flip; T12 resolved to `InpMaxSignalAgeBars` only. `InpDryRun` is unchanged. |

### Re-verified: the v6.6.23 fixes still hold

T1 UNKNOWN⇒WATCH · T2 append-only per-TF known flags · T3 `reject_first` +
`[QSMC_ARB] no alert | …` · T4 `valid=false` on every reject path · T5 sticky
per-bar alert claim · T6 oldest-slot recycle · T7 `QSMC_ALERT_SRC_*` defined
once · T10 `RoundNear` gone · T11 badge-cache key + `hi<=lo` guard. T12 was
re-opened by the owner and is now F-006. `test_arbiter.py` 38/38,
`test_unified_decision_*` green.

## 4. Deliverables for the demo trial

| Item | Path | State |
|---|---|---|
| **R1** CSV journal | `QSMC_AutoTrader.mq5` → `MQL5/Files/QSMC_trial_<login>.csv` | written; 17 columns; events signal_seen / order_sent / order_refused / fill / partial_close / sl_move / close / breaker_trip; a write failure disables the journal and prints one line, and cannot affect an order |
| **R2** analysis | `tools/analyze_trial.py`, `tools/trial_acceptance.json` | funnel + refusals + breakers + 4 thresholds; prints "sample size too small to conclude" below 100 closed trades |
| **R3** preflight | `tools/preflight_demo.py` | 24 checks; wired into the curated gate and CI; must print `GO for a DEMO attach` |
| **R4** buffer diff | `MQL5/Scripts/QSMC_BufferDump.mq5`, `docs/BUFFER_DIFF_v6.6.23_v6.6.24.md` | dump + reading rules; the diff itself is a manual step in the terminal |
| **R5** runbook | `docs/DEMO_TRIAL_RUNBOOK.md` | pre-attach, demo-only attach, week 0 dry run, weeks 1–8, stop conditions, how to read the result |

## 5. What must still happen before a live-demo attach (MANUAL)

1. **F7 in MetaEditor** on all seven programs. No file here has been compiled.
2. **`QSMC_RunSelfTest()`** in the terminal (`MQL5/Scripts/QSMC_ArbiterTest.mq5`)
   — 0 failed.
3. **`python3 tools/preflight_demo.py`** on the operator's machine → GO.
4. **The buffer diff** (`docs/BUFFER_DIFF…` §2) if upgrading from v6.6.23; if it
   cannot be produced, start with both Class B commits reverted.
5. **One `InpDryRun=true` week**, then flip it to false and record the time.
6. **The owner edits `tools/trial_acceptance.json`** before the first trade.

Two of these (1 and 2) are the only steps that can still find a *compile* error;
everything else in this document is source-level or native-C++ evidence.
