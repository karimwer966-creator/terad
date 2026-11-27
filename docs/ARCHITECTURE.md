# QSMC architecture — v6.6.25

What the system is, what each part does, how data moves, and where the risk
sits. Written from the source at v6.6.25; every number in it was measured
against the tree, not remembered.

> **Status: source-contract ready. No file in this repository has been compiled
> with MetaEditor F7 and no Strategy Tester evidence exists. This document
> describes the source.**

Related: [`BUFFER_CONTRACT.md`](BUFFER_CONTRACT.md) · [`INPUTS_REFERENCE.md`](INPUTS_REFERENCE.md) ·
[`EA_RISK_INPUTS.md`](EA_RISK_INPUTS.md) · [`SEVEN_THRESHOLDS_2026-11-27.md`](SEVEN_THRESHOLDS_2026-11-27.md) ·
[`INDEX.md`](INDEX.md)

---

## 1. Two products, one repository

| | QSMC | QATS |
|---|---|---|
| Files | `nadir2.mq5`, `QSMC_AutoTrader.mq5`, 34 headers | `QuantumAutonomousTradingSystem.mq5` |
| Lines | 46,847 + 5,327 + 17,138 | 5,112 |
| Version line | v6.6.25 / `"6.625"` | its own v1.x line |
| State | the production product | **not production-ready — no demonstrated edge** |

They share no preset format and no execution path. `check_repo_layout.py:199`
(`OWN_VERSION`) keeps QATS and `QSMC_SmcVpEngine.mq5` out of the one-version
rule on purpose. `README.md:6` states the split.

## 2. Size, honestly

| | |
|---|---|
| Unique MQL5 source | 62,338 lines |
| of which `nadir2.mq5` | **46,847 (75.2%)** |
| `nadir2.mq5` mirror | `MQL5/Indicators/nadir2.mq5`, byte-identical, gated by `check_repo_layout.py:104` |
| top-level functions in `nadir2.mq5` | 1,048 |
| median function | 14 lines · mean 33.2 · p90 74 |
| functions > 400 lines | 6 (8.6% of the file) |
| global variables | 631, of which 586 `g_`-prefixed |
| structs / enums | 143 |
| inputs | 545 in `nadir2.mq5` + 71 in the EA + 57 injected by headers |

The file is large but not chaotic: most functions are small and single-purpose.
The complexity is concentrated in six functions and in the global state that
connects everything.

**Dead code: effectively none.** Scanning all 1,048 definitions for call sites
finds exactly two with no caller — `OnChartEvent` and `OnDeinit`, which the
terminal invokes.

## 3. Dependency graph

34 headers, **54 header→header edges**, 24 program→header edges, acyclic, no
orphans. Those are the numbers `tools/test_include_graph.py:123` pins, so the
shape of the graph is enforced, not just observed. Three includes resolve
outside the tree (`<Trade/Trade.mqh>`, stdlib).

Highest fan-in — what breaks if you touch it:

| fan-in | header |
|---|---|
| **14** | `QSMC_Types.mqh` — every struct and enum |
| 6 | `QSMC_MarketData.mqh` |
| 4 | `QSMC_Zones.mqh`, `QSMC_SvpCore.mqh` |
| 3 | `QSMC_Root.mqh`, `QSMC_SignalRegistry.mqh`, `QSMC_Reaction.mqh`, `QSMC_InstanceIdentity.mqh`, `QSMC_Gates.mqh` |
| 1 | 21 leaf headers |

Fan-out: `nadir2.mq5` reaches **23** headers. `QSMC_AutoTrader.mq5` reaches
**3** — `QSMC_ExecutionRules.mqh`, `QSMC_InstanceIdentity.mqh`, and stdlib
`Trade/Trade.mqh`.

**That isolation is the most important structural fact in the system.** The EA
shares almost no code with a 46,847-line indicator; it talks to it through
buffers and `GlobalVariable`s. A broken indicator cannot break the EA at
compile time.

## 4. Internal modules of `nadir2.mq5`

Measured by function-name prefix over 1,048 brace-matched bodies:

| prefix | functions | lines | share |
|---|---|---|---|
| *(no prefix — the CORE path)* | 487 | 18,531 | 53.3% |
| `PMI_` price-action intelligence | 125 | 3,648 | 10.5% |
| `RXN_` reaction layer | 86 | 2,826 | 8.1% |
| `ZRE_` zone-reaction engine | 100 | 2,419 | 7.0% |
| `MTF_` multi-timeframe / sniper | 41 | 2,102 | 6.0% |
| `MVP_` market-volume profile | 52 | 1,132 | 3.3% |
| `QSMC_` shared-header glue | 57 | 1,127 | 3.2% |
| `RM_ MR_ CF_ WY_ PA_ A2_ SCALP_ SB_ OBS_ P3_` | 86 | 2,890 | 8.3% |

The six largest functions: `CalculateAITradeSetup()` **887**, `OnInit()` **809**,
`OnCalculate()` **754**, `RXN_SelfTestRun()` 556, `MTF_SniperCollectTF()` 549,
`DrawQuantumDashboard()` 492.

## 5. Data flow

```
OnTick (terminal)
  └─ nadir2 OnCalculate()            L16157 · 754 lines · 52 first-level calls
       ├─ MTF_RefreshAlignment()         multi-timeframe alignment
       ├─ FillEMAAndVWAP()               buffers 0-2
       ├─ TopDown_Update()               HTF context
       ├─ ManageSetupLifecycle()         287 lines - the setup state machine
       ├─ PMI_Update()                   the largest module
       ├─ MTF_SniperZone_Update()
       ├─ CalculateAITradeSetup()        887 lines - where a signal is born
       ├─ ApplyCausalDecisionState()
       ├─ 13 subsystem updates (MVP/LV/PA/MR/A2/CF/RM/SCALP/ZRE/RXN/Scenario/OBS)
       ├─ DrawTradeBox / DrawTradeLevels / DrawEntrySignalVisuals()   buffers 3-6
       ├─ SigLog_Update()                writes buffers 7-26 and the CSV
       └─ DiagPublishCoreState()         buffer 19 + the GlobalVariable bridge
                                            │
             ┌──────────────────────────────┘  27 buffers
             ▼
QSMC_AutoTrader OnTimer()   L5231
  └─ ProcessSignals()       L3323
       ├─ CopySignalBuffers()          L2307  buffers 7-12
       ├─ CopyClassificationBuffers()  L2292  buffers 21-25
       └─ HandleSignal()    L2560
            ├─ RunEntryReview()  L2451   12 checks, a GATE since v6.6.25
            ├─ breakers / session / day cap / cooldown
            ├─ freshness (SymbolInfoTick) + TERMINAL_CONNECTED
            ├─ aggregate open-risk cap
            └─ g_trade.Buy()/Sell()   L2984 / L2986
                 └─ OnTradeTransaction() L5282  confirm, verify SL/TP, repair
```

The 27-buffer contract, index by index, is
[`BUFFER_CONTRACT.md`](BUFFER_CONTRACT.md). The short version: the EA reads
**13 of 27**. Buffers 0–6 are display. Buffers 13–18 are ZRE and the EA never
executes ZRE. Buffer 26 is a chain-kind **label**, not a gate.

**One writer, so the buffers cannot disagree.** All of 7–26 are written from a
single registration, `SigLog_BufRegister()` `:14649`, which calls
`SigLog_BufWrite()` `:14706` (7–12), `SigLog_BufWriteClass()` `:14707` (21–25)
and `SigLog_BufWriteChain()` `:14708` (26) for the same signal.

## 6. Signal outcome log

`nadir2.mq5:13771` cites this section by name.

The outcome model is **read-only**: it measures what happened on bars strictly
after a published signal and never writes to a setup, a journal entry, a ZRE
record or any decision state. Its only side effects are an append-only CSV
(`InpSigLogCSV`, off by default) and the hidden calculation buffers
(`InpExportSignalBuffers`).

- Only bars strictly after the signal bar are used, one closed bar at a time; a
  bar is folded in at most once (idempotent).
- Three fixed-bracket exit policies are measured side by side: exit 100% at
  TP1 / TP2 / TP3, or at the stop, whichever is touched first. The stop is never
  moved. `result_r` is the TP1 policy.
- Stop and targets are touched by **bar extremes**. A bar touching both is
  resolved as a LOSS and flagged `ambiguous` — bar data cannot say which came
  first, so the conservative side is taken.
- A bar that *opens* beyond the stop fills the stop at that open (a gap, worse
  than −1R). Targets fill exactly at the target price.
- Entry model, `InpSigLogEntryRef`:
  - `PUBLISHED` — a limit order at the published entry; filled at the signal
    close when that close is already at or through the entry (no price
    improvement credited), otherwise when a later bar trades through it. If TP1
    or the horizon comes first the signal is `MISSED`.
  - `SIGNAL_CLOSE` — a market fill at the close of the signal bar.
- After `InpSigLogHorizonBars` bars every open policy is closed at that bar's
  close (`TIMEOUT`, marked to market).
- MFE / MAE are bar-extreme excursions in R from the fill until the last policy
  closes.

States (`nadir2.mq5:13797-13805`): fill `PENDING/FILLED/MISSED/INVALID`,
outcome `OPEN/WIN/LOSS/TIMEOUT`. The CSV carries 53 columns
(`row_type … horizon_bars`), including `gates`, `gates_failed`, `first_fail` —
the per-gate attribution that makes a refusal histogram possible.

**These rows are observed results of a logged sample. No row, and no aggregate
of rows, is a forecast.**

## 7. Where the risk is concentrated

1. **Nothing has been compiled.** No F7 evidence exists for any of the 10
   shipped programs. Every "PASS" in this repository is a source contract.
2. **`nadir2.mq5` is 75% of the codebase and one compile unit.** Any edit forces
   a full F7 of 46,847 lines, and 291 pinned line citations across 8 suites must
   be re-anchored when lines shift.
3. **`QSMC_Types.mqh` has fan-in 14.** A struct change touches every product.
4. **Six functions over 400 lines carry the decision path**, and
   `CalculateAITradeSetup()` has no unit-level seam.
5. **One file can lose money.** All 15 trade-API call sites are in
   `QSMC_AutoTrader.mq5`. REAL trading is behind `InpAllowRealTrading=false`
   plus exact login and exact server (`:313`, `:315`), re-verified at init and
   before every order.
6. **586 globals** couple every subsystem; two features can interact through a
   global neither owns, and nothing in the tree would catch it.
7. **Seven thresholds implicated in the 2026-11-27 missed trade have never been
   measured** — see [`SEVEN_THRESHOLDS_2026-11-27.md`](SEVEN_THRESHOLDS_2026-11-27.md).

## 8. What the verification actually proves

89 offline suites, all passing. `tools/qats_sim/` (8,539 lines) and
`tools/smcvp_sim/` (4,019 lines) are a host-side MQL5 simulator: shim headers
plus drivers that compile **real** `.mq5` bodies with a strict C++ compiler.
That is what lets this project claim "the shipped function body ran" without a
terminal.

They prove: source contracts hold, the include graph is a DAG, buffers / inputs
/ versions / presets agree, doc citations resolve, pinned line numbers still
point at the right code, and specific shipped bodies behave correctly on
synthetic data. The reaction layer's "CLASSIFICATION ONLY" promise is one of
those contracts (`tools/test_rxn_classification_only.py`), as is the frozen
incident evidence folder (`tools/test_incident_evidence_map.py`).

They do not prove: that MetaEditor compiles anything, that a signal fires on
real bars, or that a trade fills.

## 9. Recommended after F7 — deliberately deferred

This section used to say that *none* of the items below could be verified
without a compiler. That was wrong, and the fifth item proved it: narrowing one
row of `docs/INDEX.md` needed no compiler at all, and it is now done. The list is
split by what actually blocks it.

**Blocked on a compiler (F7).** Both change the shape of 46,847 lines of source
that nothing here can compile, so neither is safe to attempt before the F7 pass:

- split `CalculateAITradeSetup()` (887), `OnInit()` (809) and
  `OnCalculate()` (754) into named stages;
- reduce the 586 globals, starting with the ones read by more than one module
  prefix.

**Not blocked on a compiler — but not free either.** A source edit plus a static
gate is sufficient, which is exactly the shape of AUD-06
(`QSMC_AutoTrader.mq5:4523-4540`) and AUD-07 (`QSMC_Root.mqh:1118-1134`), both of
which landed without one. What blocks these is not tooling: each changes
observable behaviour, so each needs an explicit go-ahead rather than a tidy-up:

- a log line when `InpRequireMSSAfterSweep=true` disables the CONTINUATION path
  (currently silent, `nadir2.mq5:5451`).

**Done.**

- ~~attach-time validation for the five risk inputs that are currently only
  clamped at use~~ — done after an explicit go-ahead. The four numeric ones are
  now refused outside their bounds at `QSMC_AutoTrader.mq5:4548-4582`, asking the
  same `1.0` and `HardMaxAggregateRiskPercent()` the enforcement applies, so
  "accepted at attach" and "clamped at use" cannot disagree. `0.00` stays legal
  for all four, `InpRequireProfileMatch` is a `bool` with no range to fail, and
  **all ten shipped presets still load** — measured. Blocks **D14/D15/D16** in
  `tools/test_execution_safety.py` hold the bounds, the refusal and the document.
  The REAL profile's `InpRealMaxRiskPercent` / `InpRealMaxAggregateRiskPercent`
  are still clamp-at-use only; closing those changes which presets load on a live
  account, so they need their own go-ahead.

- ~~reconcile `docs/QSMC_AUTOTRADER.md` with the generated
  [`INPUTS_REFERENCE.md`](INPUTS_REFERENCE.md), or narrow its claim in
  `docs/INDEX.md`~~ — the second option was taken: `docs/INDEX.md` no longer
  calls the operator guide *"every input, every guard"*, because the guide names
  34 of the EA's 71 inputs. `tools/test_inputs_reference.py` block R8 holds both
  counts. The guide is still an operator guide and not an input reference; the
  reconciliation option stays open.
