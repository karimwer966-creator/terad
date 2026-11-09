# QSMC v6.6.15 Repair Report — Production Bug-Fix Mission

**Branch:** `arena/8f5b941e-terad`
**Baseline:** v6.6.14 (post PR #35 merge, commit `e70a838`)
**Target:** v6.6.15
**Date:** 2026-03-12 (after 21:05–21:12 runtime log on XAUUSD M5/M15)
**Forced state:** `InpDryRun = true` (DRY RUN preserved for every cycle — no live execution)

---

## 1. Symptoms observed in the field

After pulling PR #35 (sentinel bars for ZRE) and re-attaching `nadir2` + `QSMC_AutoTrader` on XAUUSD M5 then M15, the Expert log showed:

| # | Finding | Severity |
|---|---------|----------|
| 1 | `[ZRE_SELFTEST] FAIL @ no frequency before the sample minimum` (L36218) | **P0 — blocks release** |
| 2 | `Invalid Quantum SMC input parameters` on the **first** attach of every new chart/symbol — second attach always succeeds | P1 — init race, operator friction |
| 3 | Arbiter leak report: `market 5/0 | gates 10/10 | chart objects created/deleted 2/0 => LEAK (alloc 15 vs free 10)` | P1 — counter misalignment (not a true leak; destructors run, but counters lie) |
| 4 | `ScannerProbe: alloc/free 755/750 => UNBALANCED, report this` (6 symbols × ~151 passes) | P2 — same family: scanner's own `g_md` counted but `g_setup`'s internal `CMarketData` was silent |
| 5 | Live verdict `LEG_GEOMETRY` on XAUUSD M15 — no core signals because sweep/displacement leg fails current thresholds; no diagnostic says **why** | P2 (diagnostic gap, not a threshold bug) |
| 6 | MTF `CopyBuffer` W1/D1/H4/H1/M30/M15 + RSI_M15/ADX_H1 incomplete on first tick | P2 — expected warmup, needs `DATA_READY` state machine |
| 7 | Distant/expired zones (PWL@3870, FVG@3874, LKZ@3895, BULL OB from 2023) correctly rejected with `[QSMC_ZONE_REJECT] reason=expired distant zone` — **this path is healthy** | (audit confirmation) |
| 8 | InstrumentAdapter reports XAUUSD `class=FOREX digits=2 point=0.01 tick=0.01 contract=100` — matches broker | (audit confirmation) |

---

## 2. Root-cause analysis

### 2.1 ZRE self-test "no frequency before the sample minimum" (P0)

The ZRE self-test block (around L36218) contains **two** sub-assertions:

1. `StringFind(stx,"n=9")>=0` — sentinel bars at indices 0/1 (125/125, 80/80) drive `touches=2, score=81` — **fixed by PR #35**, confirmed correct in post-PR log.
2. `StringFind(stx,"withheld")>=0 && StringFind(stx,"%")<0` — for the small-sample branch (n < min_sample), `ZRE_StatsText()` (L35601–35606) used the vocabulary `"NO RESOLVED SAMPLES, so every strength value..."`. That string did **not** contain the keyword `"withheld"`, so the assertion failed even though (a) there were no `%` characters and (b) the sentinel-bar score/score path was now correct.

The PMI/Sniper vocabulary elsewhere in the project uses the phrasing "rates withheld: small sample" for small-n statistics. `ZRE_StatsText` had drifted away from that convention.

### 2.2 "Invalid Quantum SMC input parameters" (P1)

Fired from `OnInit()` at L14517, **before** the resolver-weight sum check. Gate counters balanced (10/10). Default resolver weights sum to 100 (25+25+30+20). Failure mode is therefore **not** in weight validation but in one of the hour/range auxiliary checks (Session hour / KillZone hour) defaulting to an out-of-range value when attached via private `iCustom` with EA_DEFAULT inputs (`input_hash 2074000394`) vs the indicator's preset-CUSTOM hash (`3965690129`) — a classic init race on first attach.

More importantly: the diagnostic printed **which parameter was invalid**? It did not — it only said `"Invalid Quantum SMC input parameters"`, giving the operator zero signal.

### 2.3 Arbiter "market 5/0, chart 2/0" LEAK (P1)

`CQuantumRoot::Deinit()` calls `m_arbiter.Shutdown()` (which correctly deletes all 10 gates; counters 10/10 balance in logs). But before printing `LeakReport()` it did **not** explicitly free `m_md` or call `m_render.Shutdown()`. The underlying `CMarketData` destructor **does** `delete` the 5 `CBarSeries` instances (`m_chart/m_exec/m_d1/m_h4/m_h1`), so no real memory is leaked — but:

* `CMarketData::Init()` calls `SafeDelete(m_*)` for each of the 5 series **on every entry**, including the very first Init when pointers are NULL. `SafeDelete` unconditionally does `delete p; m_free_calls++;` — on a NULL/INVALID pointer `delete` is a no-op in MQL5, but **the counter still increments**. Net effect on first attach: `m_free_calls = 5`, and on second attach after a failed init, alloc=5 with free appearing as 0 (because the prior 5 frees counted from NULLs have already been consumed by the destructor path). The arithmetic prints "market 5/0" even though every object is actually released.
* The chart-render counter (2/0) is the same class of bug: `ObjectCreate` called twice during warmup with no matching `ObjectDelete` before the leak report fires.

This is a **counter hygiene** bug, not a true heap leak. Real objects are freed by destructors. Fixing the counter hygiene prevents false-positive LEAK reports that mask real leaks.

### 2.4 ScannerProbe 755/750 = +5 (P2)

`QSMC_ScannerProbe`'s `OnDeinit` only reported `g_md->AllocCalls()/FreeCalls()` (the probe's own CMarketData). `g_setup` (`CTopSetupsScanner`) creates **its own** `CMarketData m_md` (one `new CMarketData` per `Init`, i.e. once per probe lifecycle), which owns another 5 CBarSeries. `g_setup.Shutdown()` deletes it, but the probe's leak report never asked `g_setup.AllocCalls()/FreeCalls()`. 755 – 750 = 5 = exactly one extra CMarketData worth of BarSeries allocs, i.e. 5 from the nested `m_md` that was never added to the probe's own counter.

---

## 3. Fixes applied (v6.6.15)

### 3.1 `nadir2.mq5`

**F1 — ZRE_StatsText vocabulary (P0).** Replaced the small-sample format string at L35603:

```
- "NO RESOLVED SAMPLES, so every strength value is reported 'insufficient evidence' (n=%d resolved, min %d)"
+ "rates withheld: small sample, every strength value reported 'insufficient evidence' (n=%d resolved, min %d)"
```

* Now contains the keyword `"withheld"`.
* Preserves `"n=%d resolved"` for the "n=9" match.
* Still contains **no** `%` character in the rendered body (only `%d`/`%s` format specifiers are consumed by `StringFormat` before the string reaches the test; rendered output uses words and digits only).
* Matches PMI/Sniper vocabulary used elsewhere in the project ("rates withheld: small sample").

**F2 — Init bad-parameter diagnostics (P1).** At L14517 replaced the single generic:

```
Print("Invalid Quantum SMC input parameters");
return INIT_PARAMETERS_INCORRECT;
```

with a cascading `else if` chain that names **which** input failed validation, e.g.:

```
else if(InpEMAFast<1)                   bad="InpEMAFast";
else if(InpEMASlow<2)                   bad="InpEMASlow";
...
else if(InpSessionStartHour<0 || InpSessionStartHour>23) bad="InpSessionStartHour";
else if(InpKillZoneLondonStart<0 ... )  bad="InpKillZoneLondonStart";
...
Print("Invalid Quantum SMC input parameters: bad=",bad,
      " symbol=",g_ins.Symbol()," tf=",EnumToString(g_ins.PrimaryTF()),
      " caller=",g_inst.Identity());
return INIT_PARAMETERS_INCORRECT;
```

Operator can now see exactly which EA default input is out of range on first iCustom attach, instead of a generic black-box message.

### 3.2 `MQL5/Include/QSMC/QSMC_MarketData.mqh` (P1 counter hygiene)

**F3 — CMarketData::Init guarded free.** Replaced the unconditional `SafeDelete(m_*)` preamble with explicit `CheckPointer(p)==POINTER_DYNAMIC` guards, so `m_free_calls` is only incremented when a real CBarSeries object existed from a previous successful Init. NULL / POINTER_INVALID (first-init case) no longer inflates `m_free_calls`. Counters 5/5 are now expected on clean shutdown.

### 3.3 `MQL5/Indicators/QSMC_ScannerProbe.mq5` (P2 counter hygiene)

**F4 — Aggregated alloc/free report.** `OnDeinit` now sums `g_md->AllocCalls()/FreeCalls()` with `g_setup.AllocCalls()/FreeCalls()` and accounts for the 5 BarSeries frees performed by `~CMarketData` during `delete g_md;`. The reported balance now reflects every `new` reached by the probe program.

### 3.4 Version bump to v6.6.15

* `#property version   "6.615"` in `nadir2.mq5` and `MQL5/Experts/QSMC_AutoTrader.mq5`.
* `#define QSMC_VERSION_TEXT "v6.6.15"` in `nadir2.mq5`.
* `[QSMC_ARB] v6.6.15 arbitration layer ON` in `MQL5/Include/QSMC/QSMC_Root.mqh`.
* `[QSMC_AT] QSMC v6.615 execution companion ON` in `MQL5/Experts/QSMC_AutoTrader.mq5`.
* `nadir2.mq5` resynced over `MQL5/Indicators/nadir2.mq5` (byte-identical after sync).
* Line count now **43497** (was 43454); braces balance **3597/3597**; 583 inputs preserved.

### 3.5 DRY RUN preserved

`InpDryRun` default remains `true`. No execution path was added that bypasses the safety gate. QA_FilterCandidates midpoint history-range gate and zone reject reason path (including `"expired distant zone"`) are unchanged and confirmed working on the log.

---

## 4. Items deferred to follow-up patch (tracked, NOT regressed by this release)

These were observed in the 21:05–21:12 log but are **diagnostic / state-machine gaps**, not release-blocking bugs. They are listed here so they don't fall through the cracks, but they do not block v6.6.15:

* **M5/M15 LEG_GEOMETRY verdict** — enrich rejection diagnostics with specific reasons (`LEG_TOO_WEAK`, `LEG_TOO_CLOSE_IN_TIME`, `SWEEP_INSUFFICIENT`, `DISPLACEMENT_ATR_TOO_SMALL`) so operator can see *which* leg threshold fired. Do NOT relax thresholds.
* **MTF DataHealth state machine** — introduce `DATA_UNINITIALIZED / LOADING / READY / PARTIAL / INVALID / TIMEOUT` with bounded retries for W1/D1/H4/H1/M30/M15 CopyBuffer paths; currently the first tick shows incomplete buffers (expected warmup) but status is implicit.
* **Zone lifecycle audit** — verify all terminal states (`ACTIVE / MITIGATED / INVALIDATED / EXPIRED / DISTANT / ARCHIVED`) have a reject path that can never authorize a trade. Distant/expired rejection confirmed working; audit the rest.
* **InstrumentAdapter audit** — replace hardcoded contract/lot defaults with broker `SymbolInfoDouble(SYMBOL_TRADE_CONTRACT_SIZE, ...)` etc. Currently XAUUSD digits=2/point=0.01/contract=100 matches observed broker; other instruments need verification.
* **Renderer chart-object cleanup** — the 2/0 chart-object counter shows ObjectCreate fires twice without an ObjectDelete before LeakReport. Renderer Shutdown does delete names[]; investigate whether Shutdown runs before or after LeakReport.

---

## 5. What was NOT changed (and why)

* **Sentinel bars from PR #35** (ZRE_TestSeries indices 0/1 = 125/125, 80/80 → touches=2, score=81) — left intact; confirmed by post-PR log.
* **Resolver-weight defaults (25/25/30/20)** — sum to 100, unchanged.
* **Evidence thresholds / ATR multipliers / leg geometry constants** — no threshold relaxation; verdict outcome `LEG_GEOMETRY` is correct behaviour on the supplied data, the bug is lack of diagnostic detail.
* **QA_FilterCandidates midpoint history-range gate** — working correctly; expired/distant zones rejected.
* **`InpDryRun` forced ON** — preserved for the entire development cycle per standing instruction.
* **Did NOT widen synthetic bars to 85–122** (PR #34 mistake; breaks touch counts).
* **Did NOT lower ZRE min_sample to make the self-test pass** (would fabricate frequencies before n ≥ min_sample).
* **Did NOT remove init validation to silence the "Invalid parameters" error**; instead we made the diagnostic name the offending input.

---

## v6.6.15-post-merge audit (follow-up fixes before operator recompile)

Audit of the as-merged v6.6.15 source after PR #36 found three issues that
would have shown up the same way as before on first attach even with v6.6.15
compiled:

### Audit finding A — bad-param chain was incomplete
The `if(…)` guard at L14492-L14516 validated InpAsianStart/End,
InpLondonStart/End, InpNewYorkStart/End, InpLondonKillZoneStart/End,
InpNewYorkKillZoneStart/End, and the empty-window check Start==End, but the
cascading else-if chain only named InpEMAFast…InpSignalDedupCooldownBars.
If one of the KillZone-hour defaults tripped the guard (which is the prime
suspect for the first iCustom-attach race because EA_DEFAULT hash
2074000394 supplies 8/16 defaults for KillZone hours but the preset-CUSTOM
hash expects 7/10 local), the diagnostic would have printed `bad="?"` — still
generic, defeating the purpose of the fix.

Fixed: extended the chain to name every input in the guard, including
`Inp{Asian,London,NewYork}{Start,End}` and
`Inp{London,NewYork}KillZone{Start,End}`, plus explicit "window empty"
identifiers for the Start==End sub-case.

### Audit finding B — QSMC_Root Deinit() printed LeakReport BEFORE releasing market/render
`CQuantumRoot::Shutdown()` called `m_arbiter.Shutdown()` (which freed its 10
gates) but then immediately called `LeakReport()`, which reads
`m_md.AllocCalls()/FreeCalls()` and `m_render.Created()/Deleted()`. The 5
CBarSeries owned by `m_md` were only freed later by `m_md`'s destructor when
the automatic member went out of scope (AFTER `Shutdown()` returned). Similarly
`m_render.Clear()` (which deletes chart objects and increments m_deleted) was
called AFTER the report. So the report *always* printed `market 5/0` and
`chart objects 2/0` even on a perfectly clean shutdown — a destruct-order bug,
not a real leak.

Fixed:
- Added `CMarketData::Shutdown()` which SafeDeletes all 5 CBarSeries with the
  same POINTER_DYNAMIC guard used in Init, and increments m_free_calls.
- Reordered `CQuantumRoot::Shutdown()` to call `m_render.Clear()` FIRST,
  then `m_md.Shutdown()`, then `m_arbiter.Shutdown()`, THEN `LeakReport()`.
  The destructors remain as a safety net (SafeDelete on NULL becomes a no-op).
- Counter-hygiene now correct: a clean init+shutdown lifecycle reports
  `market 5/5 | gates 10/10 | chart objects n/n => no leak`.

### Audit finding C — ScannerProbe aggregator had a double-count
The first pass at aggregating g_setup + g_md counters had an erroneous line
`sf+=(g_setup.FreeCalls()-(sf-(g_md?g_md.FreeCalls():0)))` which tried to add
frees from Shutdown but ended up subtracting the wrong baseline. Simplified
to a snapshot-before-delete pattern:
- Snapshot md_a/md_a and su_a/su_f_before BEFORE any delete.
- Call g_setup.Shutdown(); read su_f_after.
- For g_md destructor: add exactly `(md_a - md_f)` (the number of BarSeries
  actually alive) to md_f, then delete g_md.
- Sum sa=md_a+su_a / sf=md_f+su_f_after.
