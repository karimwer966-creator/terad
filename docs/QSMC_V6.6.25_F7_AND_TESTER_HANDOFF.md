# v6.6.25 handoff — the two steps that need a terminal (F7 and the Strategy Tester)

Everything that can be checked without MetaEditor has been checked: 59 CI commands
plus 30 non-CI suites, GitHub Actions green on the branch. Two things cannot be
done in this repository, and no claim in the v6.6.25 docs should be read as
covering them:

1. **F7.** There is no MetaEditor here. Nothing in v6.6.25 has ever been compiled.
2. **The Strategy Tester.** There is no terminal, no broker history and no ticks,
   so the flags-OFF identity of the seven new switches has never been observed on
   real bars, and no switch has a measured effect.

This file is the operator's checklist for closing both. Build/attach mechanics live
in [`QSMC_BUILD_AND_RUN.md`](QSMC_BUILD_AND_RUN.md); the reason the switches exist
lives in [`MISSED_TRADE_2026-11-27_HYPOTHESES.md`](MISSED_TRADE_2026-11-27_HYPOTHESES.md).
Nothing here is repeated from those two except the exact numbers.

---

## Step 1 — compile, and prove the right build loaded

**Version triple that must be in the sources you compile** (v6.6.25):

| What | Where | Value |
|---|---|---|
| `#property version` | `nadir2.mq5:653`, `MQL5/Experts/QSMC_AutoTrader.mq5:153` | `"6.625"` |
| `QSMC_VERSION_TEXT` | `nadir2.mq5:664` | `"v6.6.25"` |
| ARB banner | `MQL5/Include/QSMC/QSMC_Root.mqh:464` | `[QSMC_ARB] v6.6.25 …` |
| harness banner | `MQL5/Scripts/QSMC_ArbiterTest.mq5:47` | `QSMC_ArbiterTest - v6.6.25 …` |

**Compile, in this order** (MetaEditor, F7 on each). This is the complete shipped
inventory — ten programs, nothing else is in the tree:

| # | File | Note |
|---|---|---|
| 1 | `nadir2.mq5` | the source of truth; `MQL5/Indicators/nadir2.mq5` is a byte-identical mirror, so compile one of them and copy the `.ex5` |
| 2 | `MQL5/Experts/QSMC_AutoTrader.mq5` | the execution companion |
| 3 | `MQL5/Scripts/QSMC_ArbiterTest.mq5` | offline arbitration harness, no market data needed |
| 4 | `MQL5/Scripts/QSMC_BufferDump.mq5` | how the flags-OFF comparison in Step 2 is made |
| 5 | `MQL5/Scripts/QSMC_FixedRangeDump.mq5` | |
| 6 | `MQL5/Scripts/QSMC_ResetGuards.mq5` | |
| 7 | `MQL5/Indicators/QSMC_ScannerProbe.mq5` | |
| 8 | `MQL5/Experts/QSMC_ConfirmationEngine.mq5` | |
| 9 | `MQL5/Experts/KLJ_DataFeeder.mq5` | optional (PART C) |
| — | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5` | **not part of this release** — they carry their own version scheme on purpose (`OWN_VERSION` in `tools/preflight_demo.py`) |

**Acceptance: 0 errors.** Warnings are worth pasting back but are not a gate.

**Then attach and read the init log.** These four lines are the identity of the
build; if any of them disagrees, you are running a stale `.ex5` from the Data
Folder and every later observation is worthless:

```
[QSMC_ARB] v6.6.25 arbitration layer ON | preset <name> | gates <n> | exec TF <tf>
           | tactical may confirm: YES|NO (informational only) | on <symbol> <tf>
 Quantum SMC Intelligence Engine v6.6.25 PRODUCTION BUILD
[QSMC_AT] QSMC v6.625 execution companion ON | <symbol> <tf> | magic <n> | mode …
 QSMC_ArbiterTest - v6.6.25 signal arbitration harness        (script run only)
```

Sources: `QSMC_Root.mqh:464` (printed only by the non-silent instance — an
EA-reader copy stays quiet by design), `nadir2.mq5:15771` (behind
`!QSMC_IsReaderSilent()`), `QSMC_AutoTrader.mq5:4993`, `QSMC_ArbiterTest.mq5:47`.

The same block also prints the seven thresholds documented in
[`SIGNAL_VISIBILITY_DIAGNOSIS.md`](SIGNAL_VISIBILITY_DIAGNOSIS.md) — `- Displacement
ATR: 0.90`, `- RetestTimeout: 40 bars / 4.0 ATR`, `- Mandatory: MSS=false`
(`nadir2.mq5:15781`–`15797`). Check them against the presets you loaded.

**Two v6.6.25-specific things to look for in `OnInit`:**

- A switch paired with a window too small to use it is now refused **by name**
  (`InpRearmStructureBars` must be ≥ 2 with `InpRearmStructureAfterBreak`, and
  `InpSweepToStructureMaxBarsContinuation` ≥ 2 with `InpAllowContinuationChain`).
  The indicator does not start; the log names the input.
- With `InpWarmupWaitHTFData=true` on a chart whose H1/W1 history is still
  loading, expect `[WARMUP] … deferred` lines and quality class `WARMUP`, then one
  `[WARMUP] … DATA_READY - re-evaluating closed bar <t>` line. Exactly one instance
  prints them: the silent-reader rule applies to both.

## Step 2 — the flags-OFF proof (do this before any switch is enabled)

Run **R0** (every v6.6.25 switch OFF, i.e. the compiled defaults) and compare it
against the same history on the v6.6.24 build:

| Must be identical | How to check |
|---|---|
| CORE exports, buffers 7–12 | `QSMC_BufferDump.mq5` on both builds, same history; diff the dumps |
| verdict codes 19–20, classification 21–25 | same dump |
| the SigLog CSV | column-for-column diff |
| the confirmed journal | line count and the decision rows |
| **buffer 26** | **all zeros** — it is the CONTINUATION chain kind (0 = none/OFF, 1 = REVERSAL, 2 = CONTINUATION; `nadir2.mq5:666`, `:15525`) |

One expected difference: the **input fingerprint changes**, because seven inputs
were added. It is an identity of the input set, not a signal. Anything else that
differs is a defect in the flags-OFF guarantee and should stop the trial.

## Step 3 — the switch matrix

Because the AutoTrader reads the indicator with its **compiled defaults**
(`InpPinIndicatorDefaults`), each variant is a copy of `nadir2.mq5` compiled under
its own name with the switch defaults edited, selected with `InpIndicatorName`:

| Run | Indicator build | Switches ON |
|---|---|---|
| R0 | `nadir2` | none (= v6.6.24 behaviour) |
| R1 | `nadir2_B` | B `InpRearmStructureAfterBreak` |
| R2 | `nadir2_C` | C `InpAllowContinuationChain` |
| R3 | `nadir2_BC` | B + C |
| R4 | `nadir2_BCD` | B + C + D `InpTargetLiquidityAware` |
| R5 | `nadir2_BCDE` | B + C + D + E `InpWarmupWaitHTFData` (+ G `InpLogCompactBarLine` for the log) |

**Settings, identical across all six runs:** `QSMC_AutoTrader` pinned to M15,
XAUUSD, 2026-08-31 → 2026-11-27 (≈ 64 trading days; ≥ 60 required), *Every tick
based on real ticks*, the demo account's own deposit and leverage, and the EA's
default risk (`InpRiskPercent`, daily-loss, DD halt, spread/slippage, max
positions, consecutive-loss breaker, news — none of them changed).

**Reject a switch against R0 if:** max equity drawdown grows by more than 20 %, or
profit factor drops by more than 0.10, or published CORE signals more than double
(flood). Record per run: CORE signals published (total and per week), trades, win
rate, profit factor, max DD in money and %, average realised R, expectancy, and
the REVERSAL/CONTINUATION split from buffer 26 or the CSV `causal_chain` column.

**Then the replay that answers the original question:** 2026-11-25 → 2026-11-27,
visual mode, R5, `InpLogLifecycleTransitions=true` and `InpLogCompactBarLine=true`.
Read the `[BAR]` and `[CONTINUATION]` lines around 3570. Only that replay can say
whether a BUY appears, and with which tag.

**C interacts with an old threshold:** `InpRequireMSSAfterSweep=true` disables the
CONTINUATION path outright (`nadir2.mq5:5451`) with no log line saying why. If R2
produces nothing, check that input first.

## Step 4 — the entry-review check (new in v6.6.25)

`RunEntryReview()` used to return `""` when `InpPrintEntryReview=false`, which
switched all twelve final checks off. It now always runs; the switch only decides
whether the checklist reaches the Journal. Verify it in the terminal:

1. Attach with `InpPrintEntryReview=true`, wait for one `[QSMC_ENTRY_REVIEW] BEGIN
   … END … verdict=READY` pair.
2. Set `InpPrintEntryReview=false` and force a refusal (e.g. `InpMaxSpreadPoints`
   below the live spread, or `InpMaxOpenPositions` already reached).
3. **Expected:** no checklist lines, but the order is still refused and the journal
   still carries `ENTRY REVIEW BLOCKED: <condition>` — `NoteClass()`,
   `SignalAudit()` and `JournalOrder()` do not read the print switch
   (`QSMC_AutoTrader.mq5:955`, `:2268`, `:751`).

If step 3 shows no refusal, the fix is not in the build you compiled.

### The spread gate inside that review also changed (AUD-04)

Review line **R4** delegates to `QER_SpreadOk()`
(`QSMC_ExecutionRules.mqh:173`–`190`, called from `QSMC_AutoTrader.mq5:2492`).
Three of its behaviours are new in v6.6.25, and all three can produce a refusal
that did not happen before:

- a spread that is not a finite number — no tick yet, or a NaN out of a broken
  feed — now **fails closed** instead of casting to garbage and passing;
- the spread is compared as a real number, so a `20.9`-point spread no longer
  truncates to `20` and slips under a 20-point cap;
- `InpMaxSpreadPoints=0` now **disables** the absolute cap instead of vetoing
  every order, matching how the EA's own `SpreadOK()` reads a zero.

None of this is a new restriction on a healthy feed. If R4 refuses during your
run, the journal line prints the measured spread and both caps
(`… pts (abs cap …) = …% of a …-pt stop`), so read the number before concluding
the gate is wrong — a refusal with a sane spread means the cap inputs are tight,
and a refusal with a nonsense spread means the feed, not the EA.

## What to send back

- the F7 output for each file (errors **and** warnings);
- the full init log of one attach (indicator + EA), including the four identity
  lines;
- the two buffer dumps and the CSV pair for the flags-OFF comparison;
- the per-run table from Step 3 and the visual-replay log around 3570;
- the Step 4 journal excerpt.

With those, the v6.6.25 claims become measured instead of argued, and the next
review has something to reject.

## Still open in this repository

- ~~**AUD-05 (P1)**~~ — **fixed.** `HandleSignal()` now has the `else`: when
  `SymbolInfoTick()` returns false the order is refused, because a symbol with no
  tick has an *unknown* feed age and unknown age must refuse exactly like old age
  (`QSMC_AutoTrader.mq5:2753`–`2764`). Asserted by `test_execution_safety.py`
  block **D12**.
- ~~**AUD-06 (P2)**~~ — **fixed.** `OnInit()` now range-checks
  `InpSessionStartHour` / `InpSessionEndHour` against `0..23` and refuses the
  attach with `INIT_PARAMETERS_INCORRECT` (`QSMC_AutoTrader.mq5:4523`–`4540`).
  A window no hour can satisfy used to return `INIT_SUCCEEDED` and then refuse
  every signal for the whole session. The wrap over midnight (`22 -> 6`) and the
  `Start == End` OFF switch are both still legal. Asserted by block **D13**.
- ~~**AUD-07 (P1)**~~ — **fixed.** `QSMC_RootCreate()` now reports `Ready()` for
  an existing root instead of a bare `true`, and destroys the root when `Init()`
  fails so the next call starts clean (`QSMC_Root.mqh:1118`–`1134`). The host no
  longer discards the verdict (`nadir2.mq5:15276`), and the arbiter feed refuses
  a root that is allocated but not ready (`nadir2.mq5:15107`). Asserted by
  `test_runtime_diagnostics.py`, including a native harness that runs the
  lifecycle and reproduces the old shape as the defect.

`docs/QSMC_AUDIT_2026-11-25.md` still lists all three as deferred. That document
is the audit as it stood on its date and has not been rewritten; this list is the
current state.
- The seven relaxed thresholds in
  [`SIGNAL_VISIBILITY_DIAGNOSIS.md`](SIGNAL_VISIBILITY_DIAGNOSIS.md) still have no
  before/after measurement; Step 3 is where that number would come from.
