# QSMC — Architecture & Dependency Audit (v6.6.24)

**Scope:** the whole checkout at `fc633b8` (v6.6.24): one analytical indicator, one
execution companion, one separate product (QATS), one in-progress modular engine
(Part C), 33 headers, 9 presets, 92 tool files, 4 CI workflows.
**Method:** every number below was produced by running a command against this
tree — not copied from a previous report. Nothing here is a compile result.
**Companion gate:** [`../tools/check_include_graph.py`](../tools/check_include_graph.py)
enforces §5 mechanically; [`../tools/test_include_graph.py`](../tools/test_include_graph.py)
proves the gate rejects what it claims to reject.

---

## 0. الخلاصة العربية

- **«QME» اسم مظلّة لهذا المنتج القائم** (المؤشر + روبوت التنفيذ + الهيدرات)، **وليس منتجًا جديدًا**:
  لا `QME.mqh`، ولا ملف EA ثانٍ. الاسم `QME` محجوز أصلاً في أدوات المستودع لشرّك آخر يملك الماجيك
  `20261110` (`tools/preflight_demo.py`)، وأي برنامج جديد يحمل هذا الاسم يخلط مساحة الهوية.
- المستودع **ثلاثة برامج + مسار إعادة بناء رابع**: `nadir2.mq5` (45,002 سطر، 599 مُدخلاً، لا يلمس واجهة
  التداول)، `QSMC_AutoTrader.mq5` (الملف الوحيد المسموح له بذلك، بقرار آلي في `tools/check_release_gate.py`)،
  `QuantumAutonomousTradingSystem.mq5` (منتج مستقل)، ومحرك Part C (`QSMC_Svp*`، المراحل 1–7).
- **المسار المعياري الذي نكمله هو Part C**، مع بقاء `nadir2.mq5` مضيفًا للتحليل حتى تنتهي الهجرة.
- **الرسم البياني للـ include: 33 عقدة، 54 حافة، بلا حلقات، 7 طبقات**، وكل الحُرّاس سليمة (33/33).
- **ثلاثة هيدرات مرتبطة بالسياق** (لا تُدرج شيئًا وتقرأ متغيّرات معرّفة في `nadir2.mq5` فقط):
  `QSMC_IncidentSafety.mqh`، `QSMC_LiquidityValue.mqh`، `QSMC_UnifiedDecision.mqh` — هذه القائمة **مجمّدة** بقرار.
- **لا ادّعاء ترجمة ولا باكتست**: F7 في MetaEditor والاختبار في Strategy Tester والديمو **لم تُنفَّذ هنا**.

---

## 1. Naming decision: what "QME" means in this repository

`QME` is **an umbrella label for the product that already exists**, not a new tree:

| Name | What it refers to | Status |
|---|---|---|
| **QME** | umbrella label for the shipped product: `nadir2.mq5` + `MQL5/Experts/QSMC_AutoTrader.mq5` + `MQL5/Include/QSMC/` | documentation label only |
| QSMC | the product's code namespace (`QSMC_*` files, `QSMC_VERSION_TEXT`, buffers, presets) | unchanged |
| QATS | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` — a **different** product with its own preset and version line | unchanged, out of scope |
| "the QME instance" | a **different engine outside this tree** that owns magic `20261110` | reserved; see below |

Consequences, written down so the next round cannot drift:

1. **No `QME.mqh`.** `MQL5/Include/QSMC/QSMC_Root.mqh` already aggregates 14 headers,
   and the remaining 19 headers are spliced by their hosts. A second aggregator would
   duplicate it and would have to reproduce an include order that is load-bearing
   (see the three context-coupled headers in §5).
2. **No `QME_Main.mq5`, no second EA.** `tools/check_release_gate.py` allows the trade API
   in exactly one file (`QSMC_AutoTrader.mq5`, sets `EXEC_TRADE_ALLOWED`/`QATS_TRADE_ALLOWED`).
   A new EA either duplicates `HandleSignal()` or requires widening that allowlist —
   which is weakening a gate to fit a document, and is refused.
3. **The magic `20261110` stays untouched.** `tools/preflight_demo.py` fails the preflight if
   any QSMC program declares it: *"the QSMC executor does not reuse the QME magic"*.
   The QME label here is a name, never an identity.

---

## 2. What the tree actually contains (verified counts)

| Artifact | Count | Detail |
|---|---|---|
| `nadir2.mq5` (canonical) | 45,002 lines / 2.12 MB | 599 `input` (65 groups), 47 enums, 26 buffers, `#property version "6.624"`, **0** trade-API calls |
| `MQL5/Indicators/nadir2.mq5` | byte-identical mirror | enforced by `tools/check_repo_layout.py` (L3) |
| `MQL5/Experts/QSMC_AutoTrader.mq5` | 5,166 lines, 68 inputs | the only execution boundary; one funnel `HandleSignal()` → `g_trade.Buy/Sell` |
| `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` | 5,112 lines | separate product (QATS), own preset |
| `MQL5/Include/QSMC/*.mqh` | 33 files / 16,771 lines | 54 include edges, depth 7 |
| `MQL5/Indicators/QSMC_SmcVpEngine.mq5` | 495 lines | Part C host, display-only |
| Diagnostics | `QSMC_ScannerProbe.mq5`, `KLJ_DataFeeder.mq5`, `QSMC_BufferDump.mq5`, `QSMC_ArbiterTest.mq5`, `QSMC_ResetGuards.mq5` | none of them trades |
| `presets/` | 9 `.set` | each bound to a real source; none can arm REAL |
| `tools/` | 92 Python files | 4 gates + 68 curated checks + simulators + fixtures |
| `docs/` | 84 Markdown files (incl. `docs/history/`) | catalogue in `docs/INDEX.md` |
| `.github/workflows` | 4 workflows | `qsmc-verify`, `qsmc-production`, `liquidity-value`, `quantum-verify` |

---

## 3. Architecture tree

```
terad/
├── nadir2.mq5                          analytical host · observation only · 45 002 lines
├── MQL5/
│   ├── Indicators/
│   │   ├── nadir2.mq5                  byte-identical mirror (layout gate L3)
│   │   ├── QSMC_SmcVpEngine.mq5        Part C modular engine host
│   │   └── QSMC_ScannerProbe.mq5       QSMC_Scanners.mqh host
│   ├── Experts/
│   │   ├── QSMC_AutoTrader.mq5         THE execution boundary (iCustom reader)
│   │   ├── KLJ_DataFeeder.mq5          data-layer feeder (QSMC-DATA v1)
│   │   └── QuantumAutonomousTradingSystem.mq5   QATS (separate product)
│   ├── Scripts/                        ArbiterTest · BufferDump · ResetGuards
│   └── Include/QSMC/*.mqh              33 modules, 7 layers, guard-checked
├── presets/                            9 .set files, bound and validated
├── tools/                              gates + contracts + simulators
├── docs/                               instructions · architecture · QATS · frozen history
└── .github/workflows/                  CI: static, production, liquidity, quantum
```

The separation of analysis from execution is **mechanical, not cultural**: gate G4 scans
every `.mq5`/`.mqh` outside the allowlist for `OrderSend`, `CTrade`, `trade.*` and fails the
release. That is why the indicator can be left on a live chart.

---

## 4. Module ownership — the 14 requested modules against what exists

| Module | Existing owner(s) | Coverage |
|---|---|---|
| Core | `MQL5/Include/QSMC/QSMC_Root.mqh` (1,121), `MQL5/Include/QSMC/QSMC_Types.mqh` (472) | full |
| Data | `QSMC_MarketData.mqh` (543), `QSMC_DataProvider.mqh` (350), `KLJ_DataFeeder.mq5` | full |
| Account | `QSMC_InstanceIdentity.mqh` (107) + `AccountModeKnown()` / `RealAuthorized()` inside the companion | partial — no module |
| Analysis | `QSMC_Structure.mqh` (412), `QSMC_Bias.mqh` (205), `QSMC_Reaction.mqh` (380), `QSMC_EarlyBreakDetector.mqh` (247), `QSMC_CandlePatterns.mqh` (74); Wyckoff / price-action / mean-reversion / confluence live **inside** `nadir2.mq5` | partial |
| Zones | `QSMC_Zones.mqh` (412), `QSMC_ZoneScorer.mqh` (138), `QSMC_LiquidityValue.mqh` (200), `QSMC_IncidentSafety.mqh` (237) | full |
| Intelligence | `QSMC_Gates.mqh` (506), `QSMC_Arbiter.mqh` (461), `QSMC_UnifiedDecision.mqh` (271), `QSMC_SignalRegistry.mqh` (510) | full |
| Strategy | `QSMC_Preset.mqh` (280), `QSMC_ExecutionRules.mqh` (275) | full (as parameters + rules) |
| Risk | procedural inside `QSMC_AutoTrader.mq5`: per-trade %, aggregate %, hard ceilings, day guard, HWM drawdown, loss-streak cooldown, margin shrink-to-fit | partial — no `RiskEngine` type |
| Execution | `MQL5/Experts/QSMC_AutoTrader.mq5`, single funnel + `MarkSeen()` dedupe | full for function |
| Persistence | terminal `GlobalVariable`s (seen-keys, day guard, HWM) + trial-journal CSV + `QSMC_Stats.mqh` (1,213) | partial — no state file, no reconcile routine |
| Runtime | hosts only: `OnCalculate` (indicator), `OnTick` / `OnTimer` (companion); no `OnTradeTransaction`, no `OnTester` | partial |
| Monitoring | `QSMC_AlertManager.mqh` (376 — the only class allowed to `Alert`/`PlaySound`), `QSMC_Stats.mqh`, lifecycle + instance banners | full |
| Output | `QSMC_ChartLayers.mqh` (214), `QSMC_Renderer.mqh` (210), `QSMC_SvpChart.mqh` (1,259), export buffers 7–18 / 19–25 | full |
| Tests | `QSMC_Selftest.mqh` (1,341) + 31 self-test routines in headers + 68 curated offline checks | full offline, no MetaEditor automation |

The two gaps that matter for the objectives in the brief are **Risk** and **Persistence**:
both exist as behaviour, neither exists as a boundary with a test of its own.

---

## 5. Dependency graph

Generated from `#include` directives, comments and string literals blanked out first
(`tools/check_include_graph.py`). 33 nodes, **54 edges**, **0 cycles**, depth 7.

```
L1 (11) Types · CandlePatterns · SvpCore · SignalRegistry · InstanceIdentity · InputFingerprint
        ExecutionRules · IncidentSafety · LiquidityValue · UnifiedDecision · ChartLayers
L2 (9)  MarketData · Zones · ZoneScorer · Preset · Renderer · DataProvider
        SvpLiquidity · SvpVolumeProfile · SvpZones
L3 (6)  Structure · Bias · Reaction · Stats · Gates · SvpDecision
L4 (4)  EarlyBreakDetector · Scanners · AlertManager · SvpChart
L5 (1)  Arbiter
L6 (1)  Root        (aggregates 14 headers — the existing aggregator)
L7 (1)  Selftest
```

Connectivity splits the tree into three clusters:

- **A — arbitration/decision core (19 headers)**, rooted at `QSMC_Root.mqh`;
- **B — Part C SMC + Volume Profile pipeline (7 headers)**, rooted at `QSMC_SvpChart.mqh`;
- **C — context-coupled headers (3)**, no edges at all, spliced directly into a host.

Cluster B reaches cluster A through exactly one edge (`SvpChart → SignalRegistry`); the
repository therefore hosts two analysis engines, which is a deliberate, documented state,
not an accident — but it is also why "add a third engine" is refused in §1.

Per-program closure: `nadir2.mq5` 23 headers · `QSMC_ArbiterTest.mq5` 17 ·
`QSMC_ScannerProbe.mq5` 8 · `QSMC_SmcVpEngine.mq5` 7 · `KLJ_DataFeeder.mq5` 2 ·
`QSMC_AutoTrader.mq5` 2. No header is orphaned.

### 5.1 The three context-coupled headers (frozen)

These include nothing of their own, yet read globals that only `nadir2.mq5` declares
(555 file-scope `g_*` globals live there). Their dependency is invisible to the compiler
until link time, because MQL5 splices text:

| Header | own inputs | host globals it reads |
|---|---|---|
| `QSMC_UnifiedDecision.mqh` | 4 | 14 (`g_atr`, `g_buf_t`, `g_confirmed_signal_journal`, `g_htf_bias`, …) |
| `QSMC_LiquidityValue.mqh` | 3 | 8 (`g_buf_o`, `g_liquidity`, `g_mvp`, …) |
| `QSMC_IncidentSafety.mqh` | 4 | 4 (`g_buf_t`, `g_rates_total`, `g_instance_role`, …) |

The set is frozen in the gate. A fourth one fails CI with the file name and the symbols,
instead of compiling by luck and failing in the field.

### 5.2 Guards

33/33 headers carry a matching `#ifndef`/`#define` pair, balanced `#if*`/`#endif`, a closing
`#endif` as the last code line (trailing banners allowed), and the guard opens before the
first `#include`. Naming uses two conventions (`__QSMC_X_MQH__` and `QSMC_X_MQH`); both are
correct, the inconsistency is cosmetic and is not worth a release.

---

## 6. Engineering rules — status at v6.6.24

| # | Rule | Status | Evidence |
|---|---|---|---|
| 1 | Inspect before changing | done | this document; counts re-derived from source |
| 2 | Preserve working functionality | done | Phase 2 changes no MQL5 file |
| 3 | No duplicate modules / abstractions | guarded | two engines exist by decision; a third is refused (§1) |
| 4 | No invented files / APIs | enforced | no `QME.*` invented; the aggregator already exists |
| 5 | Documented dependency graph | done | §5, machine-checked |
| 6 | No circular includes | pass | gate I2 (DFS colouring) |
| 7 | Consistent include guards | pass | gate I3, 33/33 |
| 8 | Analysis independent of execution | pass | release gate G4/G8 allowlist: one file |
| 9 | Risk boundary before every order | **partial** | one funnel, but risk is procedural; no `RiskEngine` type |
| 10 | Closed candles for confirmed decisions | pass | `ch.ClosedIndex()` in `BuildContext`; companion refuses shift 0 |
| 11 | One validated tick snapshot | **partial** | `SymbolInfoTick` used for staleness only; the order price comes from two separate `SymbolInfoDouble` calls |
| 12 | Reject missing / stale / invalid data | pass | `data_reason` ladder, `history unavailable`, `invalid band`, `EMPTY_VALUE` guards |
| 13 | Never bypass risk to raise frequency | pass | hard ceilings pinned by `tools/preflight_demo.py`; `InpDryRun`; no martingale |
| 14 | No duplicate orders | pass | key `(bar_time, dir)` → in-memory ring + terminal global variable |
| 15 | Safe recovery after restart | **partial** | guards survive reload via global variables; no state file, no named reconcile routine |

Rules 9, 11 and 15 are **not** defects found by this audit — they are the three places where
the architecture is thinner than the brief asks. Each needs its own commit, its own test and
(where it changes displayed values) a buffer diff, so none of them is in Phase 2.

---

## 7. Verification matrix — executed vs not executed

| Stage | Status in this environment | Result |
|---|---|---|
| Static / offline gates | **executed** | `tools/check_production_ready.py` → `OFFLINE GO: 68/68`; `tools/check_release_gate.py` → `GO (0 warnings)`; `tools/check_repo_layout.py` → `8/8`; `tools/check_presets.py` → `9 bound, 0 invalid` |
| Include-graph gate + contracts | **executed** | `tools/check_include_graph.py` → 6/6; `tools/test_include_graph.py` → PASS |
| **MetaEditor compilation (F7)** | **NOT executed** | no MetaEditor in this environment — not claimed |
| **Strategy Tester** | **NOT executed** | not claimed |
| **MT5 demo runtime** | **NOT executed** | not claimed |

---

## 8. The spine: finish Part C, keep the host

Part C (`docs/KLJ_V6.6.0_PART_C.md`) is the modular rewrite of the analysis body into
`QSMC_Svp*` headers, and phases 1–7 already exist with their own tests
(`tools/test_phase2_modules.py` … `tools/test_phase7_riskmodel.py`):

| Phase | Content | State |
|---|---|---|
| 1–5 | core types, Wyckoff, price action, mean reversion | built |
| 6 | data layer (`QSMC_DataProvider.mqh` + `KLJ_DataFeeder.mq5`) | built |
| 7 | scanners and heatmaps (`QSMC_Scanners.mqh`) | built |
| 8 | COT / retail sentiment / macro dashboard | **blocked**: needs the owner's provider choice, payload shape, symbol mapping and licence confirmation |

Rules for the migration, so it stays safe:

1. `nadir2.mq5` remains the analytical host and the source of the published buffers until a
   Part C equivalent is proven on the same bar;
2. a module moves only when its Part C file has a contract test and the host's behaviour is
   unchanged (buffer diff, not an opinion);
3. the execution boundary never moves: Part C output reaches orders only through the
   existing `iCustom` buffer contract and `HandleSignal()`.

---

## 9. What Phase 2 changed (and what it deliberately did not)

Changed — documentation and gates only, zero MQL5 edits:

- `tools/check_include_graph.py` — six checks (I1 resolution, I2 acyclicity, I3 guards,
  I4 reachability, I5 frozen context-coupled set, I6 aggregator ordering);
- `tools/test_include_graph.py` — negative contracts for each of the six, plus the live tree;
- `tools/check_production_ready.py` — both registered in the curated list (66 → 68);
- this document, `docs/INDEX.md`, and the stale counts in `README.md`.

Not changed, on purpose: no MQL5 file, no preset, no input, no buffer, no default, no gate
threshold, no merge of clusters A and B, no `RiskEngine`, no tick-snapshot accessor, no
persistence module.

---

## 10. What this document does not claim

It is not a compile result, not a backtest, not a profitability statement, and not a review
of the trading logic — that was `docs/REVIEW_INCLUDE_QSMC_v6.6.24_AR.md` (23 defects, merged).
Line counts, include edges and check counts are facts about this commit and will be re-derived
by the gates on every run; if this file and a gate disagree, the gate is right.
