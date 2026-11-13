# QATS v1.22 → v1.23 — displacement may confirm on M15

`MQL5/Experts/QuantumAutonomousTradingSystem.mq5` — `#property version "1.23"`

**Why:** a live journal on XAUUSD M15 rejected a `SELL=73/100` signal with
`reason=CORE_NOT_CONFIRMED` — `SELL core=FAIL(no displacement) 2/3` despite a
bearish D1/H4 context, a BOS/CHoCH and a swept BSL. The displacement detector
scans **H1 bars only**, so a strong impulsive M15 candle was invisible to it.
v1.23 lets the M15 timeframe vouch for the displacement instead.

**The honest status:** this is not a compile, not a Strategy Tester run and not a
forward test. The source builds cleanly (zero errors, zero warnings) with a host
C++ compiler against a typed MQL5 shim, and the whole EA runs inside an offline
broker simulator in both directions, including four new `m15_*` scenarios.
**F7 in MetaEditor remains the build gate and a DEMO chart remains the execution
gate.** Both were unavailable here. v1.23 *loosens the entry gate*: it will admit
setups v1.22 refused. That is the point — and the risk. Re-test on history, then
DEMO, before trusting a single live fill.

---

## 1. What changed

### 1.1 Inputs (1 new, declared inputs: 57 → 58)

| Input | Default | Meaning |
|---|---|---|
| `InpDisplaceM15` | `true` | v1.23: when H1 shows no displacement, scan M15 with the M15 ATR. `false` = v1.22 byte for byte (H1 only). |

H1 is **always checked first**, exactly as v1.22 did; the M15 scan runs only
when H1 finds no impulse. `InpDisplaceATR` (0.8) and `InpDisplaceBodyRatio`
(0.65) now scale off the ATR of the timeframe actually scanned — the M15 ATR on
the M15 path — which is the only correct normalization.

### 1.2 Engine

* `SReading` carries `atrM15` (new handle `g_hATRM15`), part of the `ready` gate,
  created in `OnInit()`, checked there, released in `ReleaseHandles()`, printed
  by the `data pipeline OK` banner.
* `SSide` carries `dispTF` next to `dispBar`: the timeframe that confirmed the
  displacement (`PERIOD_H1`, `PERIOD_M15`, `PERIOD_CURRENT` = none). The journal
  names it — `displacement=bar 2026.11.13 16:45 (M15)`.
* The M15 search starts at the M15 bar that **contains the sweep rejection H1
  bar's open** (found via the new `ShiftOfTime()`, which reads actual bar times —
  gaps and all — instead of assuming a fixed minute grid). An impulse strictly
  before the sweep is never counted: the same "at or after the sweep" rule the H1
  path has always enforced. Without a sweep, the M15 search window is
  `window * 4` M15 bars (`InpSetupWindowBars=6` → 24 bars).
* `ShiftOfTime()` is also used to map an M15 displacement onto its containing
  **closed H1 bar** for the zone logic: an M15 displacement anchors the H1
  order-block / fair-value-gap search at that H1 bar (falling back to the sweep
  bar), never at the raw M15 index. An M15 displacement is never used as an H1
  shift anywhere.
* The setup anchor (`setupTime`) is read from the timeframe that confirmed the
  displacement when there is neither structure nor sweep (journal-only identity;
  the structural anchors — BOS/CHoCH bar, then sweep bar — are unchanged).
* `BarText()` generalizes `H1BarText()`; the DETECTED line is byte-identical for
  H1 displacements (`displacement=bar <H1 time>`) and gains ` (M15)` otherwise.

### 1.3 What did NOT change

* The core gate of `BALANCED` still demands **displacement + BOS/CHoCH**. A sweep
  plus an M15 displacement (no structure) still refuses in BALANCED.
* `InpMinScore`, all weights, the conflict policy, vetoes, risk model, sizing,
  spread/session/permission/drawdown/cooldown guards, limit entry, exits,
  position management, `MAX_POSITIONS`, `DUPLICATE_SETUP` — untouched.
* M15-confirmation (`confirmM15`) and the M5 trigger were already independent of
  the displacement path and are untouched.
* The direction vetoes, the spread gate — untouched.
* Nothing is scored off the printed page: the listed weights still add to the
  score, only DISP is easier to earn.

### 1.4 The deliberate semantic consequence (ACTIVE profile)

The H1 sweep bar *includes* its own rejection candles. On M15 those rejection
candles are often the impulse itself, so in `ACTIVE` (any two of three) a sweep
plus its own impulsive rejection now passes the core — earlier than the H1 bar
closes. This is the intended rescue, and it is exactly what v1.22 structurally
refused. The new `m15_*` scenarios encode it; the pre-v1.23 behavior remains
reproducible with `InpDisplaceM15=false` (and is what the legacy scenario corpus
still measures).

`BALANCED` users are affected far less: the BOS/CHoCH requirement still stands.
Expect more `DISP:9` annotations in the SCORED lines, and a few of them tipping
`eligible=yes` that read `eligible=no` before.

---

## 2. Verification (all offline, host C++ against a typed MQL5 shim)

* `tools/verify_quantum_ea.py` — structural checks, pass.
* `tools/test_qats_native_build.py` — whole-EA strict build, zero warnings:
  62 checks, pass.
* `tools/test_qats_dual_direction.py` — unit (309) + **55 scenarios** (737 checks)
  incl. 4 new `strong_m15_*` / `sweep_only_m15_*` asserts and their mirrors:
  pass. The legacy ACTIVE scenarios (`strong_*_active`, `sweep_only_*_active`)
  are frozen to pre-v1.23 timing by the harness (`InpDisplaceM15=false`), the
  same freeze the market-entry path gets.
* `tools/test_qats_limit_entry.py`, `tools/test_qats_journal_report.py`,
  `tools/test_quantum_account_policy.py`, `tools/test_quantum_compile_regressions.py`,
  `tools/test_xau_execution_policy.py` — pass (the production preset now ships
  `InpDisplaceM15=true`; the journal report recognizes the v1.23 attach banner).
* ASan/UBSan with poisoned automatic variables — pass on all 55 scenarios.

What this does **not** prove: F7 compiles, the Strategy Tester, execution at a
broker, or profitability. The pre-v1.20 XAUUSD replay showed negative
expectancy in-sample; nothing in v1.23 is a claim that expectancy improved.
Re-run `docs/QATS_BACKTEST_STUDY_2026-11-11.md`-style analysis on history before
scaling risk — and keep `InpDryRun=true` until the DEMO forward test says so.

---

## 3. Rollback

One input: `InpDisplaceM15=false` (preset or inputs dialog) restores v1.22
detection exactly. No state migration, no persisted keys affected.
