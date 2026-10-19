# QSMC review + fix report — v6.6.1

Reviewed: `nadir2.mq5` (39 792 lines, CRLF) + the 15 headers of
`MQL5/Include/QSMC` + `MQL5/Scripts/QSMC_ArbiterTest.mq5` +
`MQL5/Experts/KLJ_DataFeeder.mq5` + the 5 tools in `tools/`.

Trigger: MetaEditor rejected the v6.6.0 build with **30 errors, 4 warnings**,
all of them inside `QSMC_Root.mqh` and `QSMC_AlertManager.mqh`.

Verdict: the **design and the decision logic are sound** (the 22-scenario
self-test and the independent Python mirror agree with the rules R1–R7 of
`docs/KLJ_V6.6.0_SIGNAL_ARBITRATION.md`). What failed is the **MQL5 dialect**:
three constructs that are legal C++ and illegal MQL5, plus one real behaviour
bug that the compiler could not have seen. All four are fixed here, and the
classes of mistake are now checked mechanically so they cannot come back.

---

## 1. The 30 errors in one line each

30 error lines, 3 root causes, 2 files:

| Root cause | MQL5 rule broken | Errors attributed |
|---|---|---|
| A getter returned a **reference** | a function may not return a reference; a reference *parameter* is fine | 8 × `reference cannot used` (Root 132-138, 346) |
| `LeakReport()` built its text with **commas** | there is no comma operator; `,` outside a call/declaration list starts a *second declaration* | 19 of the remaining errors (Root 194-201: `class type expected`, `name expected`, `variable already defined`, `some operator expected`, `… not used`) |
| integer literals carried a **`u` suffix** | MQL5 has no integer literal suffixes | 3 (AlertManager 68: `'0xFF' - invalid number`, `undeclared identifier 'u'`, `some operator expected`) |

The 30 lines were therefore *one* cascade: 8 real problems, 20 ghosts produced
by the parser inventing a variable called `IntegerToString`.

---

## 2. Fixes

### 2a. No getter returns a reference (`QSMC_Root.mqh`)

Before:

```cpp
   const SGateCtx   &Ctx()   const { return m_ctx;   }   // reference cannot used
   const SQsmcArbConfig &Cfg() const { return m_cfg; }
   const SArbiterReport &Report() const { return m_rep; }
   CZoneRegistry    &Zones() { return m_zones; }
   CMarketData      &Market() { return m_md; }
   CSignalArbiter   &Arbiter() { return m_arbiter; }
   CStatsLogger     &Stats() { return m_stats; }
   ...
   SQsmcArbConfig   &MutableConfig() { return m_cfg; }
```

After — sub-objects are handed out as **pointers** (`GetPointer` is already the
pattern used elsewhere in this subsystem, e.g. `m_arbiter.Init(GetPointer(m_alerts), …)`),
and the plain-data structs as **narrow const accessors**:

```cpp
   CZoneRegistry    *Zones()    { return GetPointer(m_zones);   }
   CMarketData      *Market()   { return GetPointer(m_md);      }
   CSignalArbiter   *Arbiter()  { return GetPointer(m_arbiter); }
   CStatsLogger     *Stats()    { return GetPointer(m_stats);   }
   CAlertManager    *Alerts()   { return GetPointer(m_alerts);  }
   CChartRenderer   *Renderer() { return GetPointer(m_render);  }

   double            CtxAtr()        const { return m_ctx.atr;          }
   string            CtxDataReason() const { return m_ctx.data_reason;  }
   ...                                 // 22 context accessors in total
   bool              ReportPublished() const { return m_rep.published; }
   string            ReportTrace()     const { return m_rep.trace;     }
   string            ReportGateLine(const int i) const { … }
   int               PrimaryState()    const { return m_rep.primary.state; }
   ...                                 // 16 report/candidate accessors
   void              GetContext(SGateCtx &out) const { out=m_ctx; }
   void              GetPrimaryCandidate(SSignalCandidate &out) const { out=m_rep.primary; }
```

Because MQL5 dereferences with `.` for pointers as well as for objects,
`root.Market().Bars()` and `root.Zones().Count()` keep working **unchanged**.
Only three call sites needed editing, all in the self-test, which read a
struct copy of the report:

| old | new |
|---|---|
| `r.Ctx().data_reason` | `r.CtxDataReason()` |
| `r.Ctx().atr` | `r.CtxAtr()` |
| `const SArbiterReport rep=r.Report();` + `rep.published` / `rep.trace` / `rep.primary.dir` | `r.ReportPublished()` / `r.ReportTrace()` / `r.PrimaryDir()` (the temporary is gone; the scenario text is unchanged) |

`MutableConfig()` — which nothing called — became an explicit read/commit pair
that respects the config lock:

```cpp
   void   CopyConfig(SQsmcArbConfig &out) const { out=m_cfg; }
   bool   SetConfig(const SQsmcArbConfig &cfg) { if(m_cfg_locked) return false; m_cfg=cfg; return true; }
```

**Why not "make the structs return by value"?** It would have worked for
`SQsmcArbConfig` (POD) and made `SGateCtx` (two strings) and `SArbiterReport`
(a `string[8]`) copy on every panel refresh. Narrow accessors are cheaper and
they stop a host from writing to a struct the root owns.

### 2b. `LeakReport()` builds text with `StringFormat` (`QSMC_Root.mqh`)

```cpp
      string s=StringFormat("alloc/free: market %d/%d | gates %d/%d | chart objects created/deleted %d/%d",
                            m_md.AllocCalls(),m_md.FreeCalls(),
                            m_arbiter.AllocCalls(),m_arbiter.FreeCalls(),
                            m_render.Created(),m_render.Deleted());
      if(a==f) s+=" => no leak";
      else     s+=StringFormat(" => LEAK (alloc %d vs free %d)",a,f);
```

Same output as intended before, one statement per line, and `StringFormat`
argument counts are now machine-checked (rule D7).

### 2c. FNV-1a hash without suffixes (`QSMC_AlertManager.mqh`)

```cpp
      uint h=0x811C9DC5;            // FNV-1a 32-bit offset basis (2166136261)
      uint p=0x01000193;            // FNV-1a 32-bit prime      (  16777619)
      ...
          h=(h ^ (c & (uint)0xFF))*p;
```

Values are **byte-identical** to the intended algorithm, so the GlobalVariable
names the multi-chart lock (T08) depends on stay stable across the upgrade:
`QSMC_ARBDUP_<symbol>_<hash>`. The `& 0xFF` keeps the byte-wise behaviour the
comment promised; `uint` wraps exactly like the reference implementation in
`tools/test_arbiter.py`.

### 2d. Behaviour bug found by reading, not by the compiler

`CQuantumRoot::Refresh()` called `m_preset.Build(m_cfg, …)` **unconditionally**,
while `BuildContext()` correctly guarded it with `if(!m_cfg_locked)`. A host that
installs its own configuration —

```cpp
   SQsmcArbConfig c; root.CopyConfig(c); c.min_evidence=4; root.LockConfig(c);
```

— had it overwritten by the preset on the very next `Refresh()`, i.e. on the
next bar, with no log line saying so. `Refresh()` now honours the lock. This is
the documented host path in the file header (call-order step 1), so it is a
real defect, not a theoretical one.

### 2e. Version drift closed (AUDIT-04 of the host banner)

`nadir2.mq5` carried `QSMC_VERSION_TEXT "v6.5.5"` / `#property version "6.55"`
while shipping the v6.6.0 layer — an `[WARNING]` the file itself listed as
unresolved. Both now read **v6.6.1 / 6.61**, the layer banner says
`[QSMC_ARB] v6.6.1 arbitration layer ON`, and rule D10 keeps the three in sync
mechanically from now on.

---

## 3. Prevention: rules D1–D11 (`tools/mql5_rules.py`)

A new linter, run standalone or as part of `tools/static_check.py`, over the
**translation unit** rather than over one file — the indicator, the self-test
script, the feeder, and `QSMC_Scanners.mqh` (nothing includes it today, so it
is linted as a synthetic unit so it cannot rot).

| Rule | Catches | MetaEditor message |
|---|---|---|
| D1 ref-return | `Type &Name()` in return position | `reference cannot used` |
| D2 ref-decl | `Struct &r = obj;` outside a parameter list | `reference cannot used` |
| D3 num-suffix | `0xFFu`, `10l`, and decimal literals > `INT_MAX` (warn) | `'0xFF' - invalid number` |
| D4 comma-chain | a `,` at statement level / after a declarator | `class type expected`, `name expected` |
| D5 const-call | a non-const method through a `const T *` / `const T &` handle, resolved to the *nearest* declaration | `cannot be called on a const object` |
| D6 class-copy | `a = b;` between two class objects | `operator = is not defined for objects of this type` |
| D7 fmt-args | `StringFormat` specifier count vs argument count; `%d` inside `Print()` | wrong text at runtime, not a compile error |
| D8 dyn-array-copy | a struct that owns a dynamic array copied by value (warn) | — |
| D9 dup-symbol | the same global function/variable defined twice in one unit | `already defined` |
| D10 version-drift | build text vs `#property version` vs the layer banner | silent misreporting |
| D11 member-chain | `a.b.c` where `b`/`c` is neither a member nor a method of `a`'s type (`a.x.F()` too) | `'zone_idx' is not a member of 'SSignalCandidate'` |

Validation: against the **pre-fix** tree it reports exactly the 12 real defects
(8×D1, 3×D3, 1×D4 — i.e. all 30 lines of the compiler log collapsed onto them)
plus the version drift MetaEditor could not see (1×D10) = 13 findings; against
this tree it reports **no errors**, only 7 advisory warnings (D3 notes about
decimal literals that exceed `INT_MAX` in the legacy host). D11 was proved by
injecting `m_rep.primary.zone_idx` and `r.ReportPublised()` into the subsystem
— both were named correctly, and both injections were then reverted.

It is not a compiler — it has no type system — and says so:
*"now press F7 in MetaEditor"*.

Four hardening notes from writing it, all recorded in the code:

1. **No nested quantifiers.** The head-classifier regex originally put a `*`
   inside a `*` and cost 150 s of backtracking on the 1.8 MB host file; it is a
   flat character class plus a per-file memo now (2 s for the whole tree).
2. **The mask preserves byte length.** Rules that read literal text
   (`StringFormat` arguments, the version banner) need the raw file at the same
   offset, so `check_unit` keeps two masks per file: one with the literals
   blanked (structural) and one with them readable.
3. **A declaration anchor must be zero-width.** The declaration patterns began
   with `(?:^|[;{}])`, which *consumed* the `;` that ends the previous
   statement — so in `int a; int b;` only `a` was ever seen, and `m_rep`'s type
   was invisible to D11. It is `(?:^|(?<=[;{}\n]))` now, which is also why the
   pre-fix tree yields 3 D3 findings instead of 2.
4. **A name is not a type.** Resolving an identifier against the whole file made
   D11 fire 71 times in `nadir2.mq5`: the host re-uses `cand`, `dt`, `r` in
   sibling blocks. `ScopeIndex` now compares the stack of open braces at the
   declaration with the stack at the use, so a declaration is visible only in
   its own block or a descendant of it, and the two type-inference rules (D6,
   D11) do not run on the legacy host at all (`LEGACY_HOST`). A rule that lies
   is worse than a rule that is missing.

---

## 4. What was reviewed and found correct

Not changed, checked line by line:

* **Location-first decision (R1).** `BuildTacticalCandidate()` resolves the zone
  *before* the direction, and the direction comes from the zone role + the
  closed-bar fact; a tactical hint can only *agree*, never originate (Root
  451-509). This is what kills "SELL at support".
* **Closed-bar discipline (R3).** `CClosedBarGate` + `Evaluate()` refuse
  `bar_index<1`; the exec-bar lookup clamps to `i<=ClosedIndex()`; a PREVIEW
  can never reach CONFIRMED.
* **One alert per bar (R5).** per-bar dedupe ring → cooldown → distance →
  flip-flop, then `alerts.Allows()` immediately before `Publish()`, plus the
  GlobalVariable lock for the multi-chart case; the tactical pass is skipped
  entirely when an authoritative source claimed the bar.
* **Unknown ≠ neutral (R2).** `SetExternalBias(..., h1_known=false)` removes H1
  from the weight sum instead of counting it as agreement.
* **Memory (OOP/RAII).** gates are `new`ed once in `CSignalArbiter::Init()`,
  released in `Shutdown()` **and** in the destructor with
  `CheckPointer(POINTER_DYNAMIC)`, so the second path is a no-op; counters are
  printed by `LeakReport()`. `CQuantumRoot::Deinit()` is idempotent
  (`m_deinit_done`) because both `OnDeinit` and the destructor call it.
* **No trading API, no recursion, every loop bounded** (`QSMC_ZONE_MAX`,
  `QSMC_ARB_MAX_CANDIDATES`, `QSMC_TACTICAL_MAX_FACTS`, `QSMC_STATS_MAX_ROWS`).
* **Complexity claims in the header match the code:** `Refresh` O(Σ series),
  `SetZones` O(N log N) merge + O(N·look) retest scan, `FinalizeBar`
  O(C·G·(log N + k)) — all once per closed bar, never per tick.

---

## 5. Known weaknesses, not fixed in this pass

| # | Finding | Why it is not urgent | Suggested step |
|---|---|---|---|
| 1 | `QSMC_Scanners.mqh` (899 lines) is included by nobody | it is Phase 7 code waiting for a host; it lints and its arithmetic is tested | either attach it to a `CFX*` panel or move it to `docs/` as a design draft — dead source in `Include/` invites drift |
| 2 | `BuildContext()` reads `_Symbol`/`_Period` instead of the values passed to `Init()` | an indicator instance is per-chart, so they always agree today | keep `m_symbol`/`m_tf` fields and use them, if the root is ever reused by a service EA |
| 3 | `static_check.py`'s new/delete count is a per-file heuristic (4 warnings forever) | the runtime ledger is the real check | make the warning disappear only by teaching it about `Shutdown()` pairs — cosmetic |
| 4 | no CI gate: a broken build is discovered by hand, in MetaEditor | this repo has no workflow files at all | add a GitHub Action running `python3 tools/static_check.py` + the three `test_*.py`; F7 still has to happen on a Windows runner or manually |
| 5 | `nadir2.mq5` is 39.8 k lines of legacy code around 6.6 k lines of clean subsystem | the audit trail (AUDIT-01…05) is inside the file and useful | extract the ZRE / RXN / SigLog sections into `Include/QSMC/` one layer at a time, each with its own self-test |
| 6 | the self-test lives in the terminal only | `tools/test_arbiter.py` covers the decision logic offline, but not the MQL5 harness wiring | keep both; run `tools/check_scenario_geometry.py` whenever a scenario's numbers change |
| 7 | D6 and D11 infer a variable's type from the nearest *visible* declaration, so they are heuristic, and they skip `nadir2.mq5` | they never fire on the current subsystem and each was proved with an injected typo | only worth replacing with a real declaration table if a rule starts lying; until then F7 is the proof |

---

## 6. Changelog v6.6.1

* `QSMC_Root.mqh` — all 8 reference-returning getters replaced by pointers /
  accessors; `LeakReport()` rebuilt with `StringFormat()`; `Refresh()` honours
  `LockConfig()`; `MutableConfig()` → `CopyConfig()` + `SetConfig()`;
  38 new narrow accessors; banner `v6.6.1`.
* `QSMC_AlertManager.mqh` — `HashHex()` without literal suffixes (same values).
* `QSMC_Selftest.mqh` — 6 scenarios read the verdict through the root's
  accessors instead of copying the report struct; `PASS/FAIL` text identical, so
  `tools/test_arbiter.py` still cross-checks 1:1.
* `nadir2.mq5` — `QSMC_VERSION_TEXT` → `"v6.6.1"`, `#property version` →
  `"6.61"`, AUDIT-04 marked resolved. No logic change.
* `tools/mql5_rules.py` — new: dialect rules D1–D11, one run per translation unit.
* `tools/static_check.py` — runs D1–D11 and merges the report; de-duplicates a
  shared header across units.
* `docs/QSMC_BUILD_AND_RUN.md` — new: install → compile → run → self-test →
  offline checks → rollback (Arabic quick-start at the top).

**Still required from you:** F7 in MetaEditor. Every claim in this file is
either a mechanical check or a reading; only the compiler is the proof.
