# QSMC repository-wide technical audit — 2026-11-25

Scope: the local checkout of `karimwer966-creator/terad` on branch
`arena/2ba04428-terad`, based on `8aad43c6a93a1fb8a5617396876f5be1a9cc44fc`.
The `qmcaa` repository was inspected read-only only to explain why the brief's
modular state-machine filenames do not exist here; it is **not** the audit
target. The brief's `CREATED / INITIALIZING / READY / RUNNING / SAFE_MODE /
FAILED / STOPPING / STOPPED` names are generic guidance: `terad` implements its
lifecycle through MQL5 `OnInit/OnCalculate/OnDeinit`, `CQuantumRoot::Init/
Deinit/Ready`, and the companion EA's `OnInit/OnTick/OnTimer/OnDeinit`. No
`QSMC_StateMachine.mqh` or equivalent module exists in this tree.

All commands below were executed in `/home/user/terad`. Generated `out/` logs
are ignored by `.gitignore`; they are evidence, not source changes.

---

## A. Repository Assessment

### A1. Product boundary and entry points

| Surface | Actual owner | Role |
|---|---|---|
| `nadir2.mq5` and byte-identical `MQL5/Indicators/nadir2.mq5` | QSMC analytical host | 45,584 source lines, 26 indicator buffers, 603 declared inputs, 0 trade API calls. Publishes signal buffers 7..12 / 21..25 and builds the 12-line diagnostic entry review. |
| `MQL5/Experts/QSMC_AutoTrader.mq5` | QSMC execution companion | Only QSMC production order boundary. Reads the indicator through a private `iCustom` handshake, revalidates account/risk/geometry/session/spread and calls `CTrade::Buy/Sell/PositionClose/PositionModify`. REAL is disarmed by default. |
| `MQL5/Include/QSMC/*.mqh` | 34 headers | Pure rules, market data, bias, zones, structure, reaction, arbiters, alert manager, renderers, stats, instance identity and input fingerprint. |
| `presets/*.set` | 10 presets | Demo/scalper configurations; none arms REAL. |
| `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` | Separate QATS product | Experimental, separate `CTrade` execution path. Not the QSMC production boundary and not part of the QSMC readiness verdict below. |
| `MQL5/Experts/KLJ_DataFeeder.mq5`, `MQL5/Indicators/QSMC_ScannerProbe.mq5`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5`, `MQL5/Scripts/QSMC_*.mq5` | Support/diagnostic entry points | Scanner probe, SMC/VP engine, buffer dumps, guard reset and arbiter test script. |

There is no `.mqproj`. `tools/check_include_graph.py --verbose` resolves the
actual dependency map: **34 headers, 54 edges, all reachable**, 6/6 PASS
(`out/final/include_graph.log`). The older architecture document's 33-header
claim is superseded by this local graph.

### A2. Lifecycle and state ownership

The analytical host creates one global `CQuantumRoot` through
`QSMC_RootCreate()`, destroys it in `OnDeinit()`, and gates most operations on
`QSMC_Root()!=NULL`. `CQuantumRoot` owns five `CBarSeries` objects, the arbiter,
alert manager, renderer and stats CSV writer; `Deinit()` is idempotent and
releases resources before its leak report. The EA owns one timer
(`EventSetTimer`/`EventKillTimer`), one trial-journal file handle, a private
indicator handle, and per-magic/per-symbol/per-account global-variable keys.
`InpAllowRealTrading=false`, empty `InpRealAccountConfirm` and
`InpRealServerConfirm`, and `TradeEnvBlock()` revalidate account identity,
permissions and trade mode immediately before every order. Hard ceilings are
`0.50%` per-trade risk, `2.00%` daily loss and `8.00%` account drawdown.

### A3. Baseline before any edit

- Branch/status verified clean: `arena/2ba04428-terad`, HEAD `8aad43c`.
- `python3 tools/check_production_ready.py --require-native`: rc=0,
  `OFFLINE GO: 70/70 curated checks passed` (`out/baseline_curated.log`,
  `out/production/SUMMARY.txt`).
- All 72 `tools/test_*.py` scripts: rc=0, no failures
  (`out/baseline/all_tests.txt` and `out/baseline/<test>.log`).
- `tools/check_include_graph.py --verbose`: 6/6 PASS, 34 headers, 54 edges.
- 11 remaining gates: all rc=0 (`out/baseline/<check>.log`).
- Python 3.11.2 and `g++ 12.2.0` available. `metaeditor64.exe`,
  `metaeditor.exe` and `wine` are **not** available; no MetaEditor F7 compile,
  Strategy Tester run, MT5 demo session or broker-latency test was executed.

These are offline/static/native-subset checks, not a full MQL5 compilation.

---

## B. Audit Findings

Priority: P0 unauthorized trading/uncontrolled risk/data corruption; P1
signal/look-ahead/lifecycle/resource; P2 edge cases/config/diagnostics; P3
maintainability. P0/P1 defects that change real-money execution were not
silently repaired: an approval request was surfaced and skipped, so those
specific source changes are deferred while independent safe repairs continue.

### B1. Repaired findings

| ID | Priority | File / function | Root cause | Impact | Repair | Test evidence |
|---|---|---|---|---|---|---|
| AUD-01 | P2 | `nadir2.mq5`, `MQL5/Indicators/nadir2.mq5` comments near L325, L443, L525, L6842, L22921, L34716, L36635, L38011, L39895, L40104 | Six comments named absent harnesses: a replay-equivalence harness, a predictive-model harness, a chart-layout model harness, a market-profile model harness, an RXN pure-core harness and a ZRE pure-core harness. None of those files exists in this checkout. Two comments claimed 700+ randomized incremental/full replay trials with zero mismatches. | An operator could believe a replay-equivalence suite exists and has verified the current build. The claim is unverifiable here; historical docs are frozen but active source comments were not marked as history. | Replaced all six names with accurate, line-count-neutral wording: external/absent harnesses, design notes, not current verification results. Added `tools/test_tool_reference_integrity.py` scanning the tracked corpus for missing tool references. Registered it in `tools/check_production_ready.py` and `.github/workflows/qsmc-verify.yml`. | Before: `out/repro/` tool run reported 20 missing refs (10 per host copy). After: `1050 resolved, 0 missing, 399 files scanned`, rc=0 (`out/final/test_tool_reference_integrity.log`). `check_repo_layout.py` mirror check still PASS. |
| AUD-02 | P2 | `nadir2.mq5` / `MQL5/Indicators/nadir2.mq5`, `PMI_ReplayAudit()` near L13307 | The periodic failure-print condition checked only `pass_repaint` and `pass_lookahead`. `Overall` has three tri-state components; a causality-only `FAIL` was silent when `InpPMILogEvents=false`. | A replay audit could set `Overall FAIL` in `last_report` while printing nothing to the journal, hiding a causality regression. | One-line, line-count-neutral condition now includes `!g_pmi_replay.pass_causality`. Added two source-contract assertions to `tools/test_pmi_replay_audit.py`; registered that suite in the curated gate. | Before: `out/repro/pmi_replay_before.log` FAILed both new assertions. After: rc=0, `PASS a causality failure is loud even with event logging off` (`out/final/test_pmi_replay_audit.log`). Native tri-state harness still passes under ASan/UBSan. |

### B2. Reproduced but deferred execution-safety findings

| ID | Priority | File / function | Root cause | Impact | Deferred reason | Reproduction evidence |
|---|---|---|---|---|---|---|
| AUD-03 | P1 | `MQL5/Experts/QSMC_AutoTrader.mq5`, `RunEntryReview()` L2419–2525; call site near L2908 | `if(!InpPrintEntryReview) return "";` exits before R1–R12. The call site treats `""` as READY. A print-only switch disables the final 12-condition safety review. | With `InpPrintEntryReview=false`, class/account/tick-age/spread/session/daily-cap/open-position/geometry/RR/stops/size/opposite checks are skipped at the final gate. Upstream `HandleSignal()` still applies most individual gates, so this is not uncontrolled trading, but the documented final review is bypassed. | Changing the real-money execution path requires explicit approval; the approval UI was skipped. No source change made. | `tools/test_entry_review_gate.py` compiles the shipped review bodies with deterministic stubs. Before any source edit it reported all 12 OFF verdicts as `""`, plus 3 source-contract failures (`out/repro/entry_review_gate_before.log`). Final full loop still reports rc=1 for this suite (`out/final/test_entry_review_gate.log`). |
| AUD-04 | P1 | `MQL5/Include/QSMC/QSMC_ExecutionRules.mqh`, `QER_SpreadOk()` L173–185 | `bool abs_ok=((int)spread_points<=cap_points);` truncates fractional spreads; NaN and negative spreads are not rejected. | `20.9` points passes a `20`-point cap, `60.9` passes `60`, a NaN quote and a `-5` quote PASS with the share cap off. A spread gate can admit a quote the documented cap should refuse. | Same approval boundary as AUD-03. No source change made. | `out/repro/spread_repro.cpp` compiled the shipped header with g++ and printed `PASS` for all four cases (`out/repro/spread_repro` binary, console captured in `out/repro/entry_review_gate_before.log` source-contract run). The new review-gate suite also fails `20.9 pts` and `NaN` cases. |
| AUD-05 | P1 | `MQL5/Experts/QSMC_AutoTrader.mq5`, `HandleSignal()` L2706–2720 | `if(SymbolInfoTick(sym,tk)) { ... refuse stale ... }` has no `else`. A failed tick read falls through to the terminal-connected check and later order path. | A broker-feed API failure can bypass the explicit `InpMaxDataAgeSeconds` stale-feed refusal. The separate `RunEntryReview()` R3 uses `SymbolInfoInteger(SYMBOL_TIME)` and fails closed, but with AUD-03 the review can be disabled. | Execution-path change; approval skipped. No source change made. | Source review; no native reproduction performed. Exact lines cited. |

### B3. Other findings and audit observations

| ID | Priority | Area | Finding | Status / evidence |
|---|---|---|---|---|
| AUD-06 | P2 | Config validation, `MQL5/Experts/QSMC_AutoTrader.mq5` `OnInit()` L4420+ | `InpSessionStartHour` / `InpSessionEndHour` (L393–394) are not range-checked for `0..23`. `QER_SessionInside()` correctly handles half-open and wrap-around windows, but an out-of-range hour produces a nonsensical window and the EA still returns `INIT_SUCCEEDED`. | Deferred: adding startup validation changes the execution lifecycle and needs approval. Source review only. |
| AUD-07 | P1 | Analytical lifecycle, `MQL5/Include/QSMC/QSMC_Root.mqh` `QSMC_RootCreate()` L1101–1110; host `OnInit()` L15127 | `QSMC_RootCreate()` returns `true` whenever `g_qsmc_root!=NULL`, including a previous failed `Init()`; it does not delete a half-initialized root when `Init()` returns false. The host ignores the return value. `QSMC_ArbiterFeedAndFinalize()` and `FireQuantAlert()` check only `QSMC_Root()!=NULL`, not `Ready()`. | Deferred: a lifecycle repair is executable-source change and could alter signal availability. No native reproduction performed. Exact lines cited. |
| AUD-08 | P3 | Replay diagnostics, `nadir2.mq5` L3936–3940, L16306–16329 | `g_replay_equivalence_ok` and `g_replay_audit_status` are written but never read in the shipped host; a `SKIPPED (no same-bar tick)` leaves `g_replay_equivalence_ok` at its initial `true`. The status strings are dead state, not a displayed verdict. | No change: cosmetic/dead-state cleanup would alter executable text without a demonstrated correctness benefit. Source review. |
| AUD-09 | P2 | Causality/replay | `PMI_ReplayAudit()` cold start is INCONCLUSIVE, not PASS (`digests_stored<2`), and `PMI_TriStateVerdict()` is natively tested. `CausalReplay` compares same-bar `CausalGraphFingerprint()` hashes and marks `SKIPPED` without a same-bar tick. No incremental-vs-full mismatch was reproduced in this checkout. | No replay comparison, assertion or expected result was weakened. `tools/test_pmi_replay_audit.py` and `tools/test_causal_chain_regressions.py` pass. |
| AUD-10 | P2 | Multi-instance/resources | `QSMC_InstanceBase()` scopes diagnostics by server/login/symbol/timeframe; role-aware hash keys separate VISUAL and EA_READER. `ClaimExecutionLane()` keys signal ownership by login/sanitised symbol/bar key and records the owner magic. EA `OnDeinit()` kills the timer, releases the indicator handle and closes the journal; host `OnDeinit()` destroys the root and releases indicator handles. | No simultaneous-instance terminal run possible here. Static/source review plus passing `tools/test_instance_identity.py`, `tools/test_qsmc_chart_hygiene.py` and `tools/test_runtime_diagnostics.py`. |
| AUD-11 | P2 | Performance | `nadir2.mq5` contains 7 `CopyRates`, 17 `CopyBuffer`, 321 `ArrayResize` sites; the EA contains 15 `CopyBuffer` and 2 `ArrayResize`. The host coalesces chart writes to a 100 ms slice and gates closed-bar work per new bar. No measured bottleneck was available, so no speculative optimisation was made. | Static counts from the local tree; `tools/test_tick_performance.py`, `tools/test_runtime_diagnostics.py`, `tools/static_check.py` pass. |
| AUD-12 | P3 | State-machine test coverage | The brief's named state machine does not exist in `terad`; there is no exhaustive CREATED→...→STOPPED transition suite to run. The closest shipped equivalents are root `Ready()`, EA `INIT_*` returns, breaker latches and `OnDeinit()` idempotence. | Reported as a scope mismatch, not fabricated into a test. |

No P0 defect (unauthorized REAL trading, uncontrolled risk, data corruption or
severe execution failure) was reproduced. REAL remains disarmed by default;
no risk ceiling, preset, magic, buffer, public interface or input fingerprint
was changed.

---

## C. Changed Files

| File | Change |
|---|---|
| `nadir2.mq5` | Line-count-neutral correction of six absent-harness comment references; one-line PMI replay audit failure-print condition now includes causality. |
| `MQL5/Indicators/nadir2.mq5` | Byte-identical mirror of the above; `check_repo_layout.py` L3 PASS. |
| `tools/test_tool_reference_integrity.py` | New static gate: every tracked `tools/...` reference must resolve to a shipped file. |
| `tools/test_pmi_replay_audit.py` | Two new source-contract assertions for three-component failure printing. |
| `tools/check_production_ready.py` | Registered `tool-reference-integrity` and `pmi-replay-audit` in the curated gate. |
| `.github/workflows/qsmc-verify.yml` | Added `tools/test_tool_reference_integrity.py` to the offline layout step. |
| `tools/test_entry_review_gate.py` | New standalone regression suite reproducing AUD-03/AUD-04. Intentionally red until those execution-source repairs are authorized; deliberately **not** added to the curated gate or CI so no existing green check is hidden or disabled. |
| `docs/INDEX.md` | Catalogue entry and document count updated for this report. |
| `docs/QSMC_AUDIT_2026-11-25.md` | This report. |

No MQL5 execution source, risk limit, REAL authorization, indicator buffer,
public interface, preset, input default or expected test outcome was changed.
All host edits preserve the original 45,584 CRLF line count, which was
necessary because `tools/test_docs_freshness.py`,
`tools/test_tactical_authority.py` and `tools/pinmap.py` pin exact source line
numbers.

---

## D. Test Results

### Passed

| Command / suite | Result | Log |
|---|---|---|
| `python3 tools/check_production_ready.py --require-native` | rc=0, `OFFLINE GO: 72/72 curated checks passed` | `out/final/curated.log`, `out/production/SUMMARY.txt` |
| All `tools/test_*.py` loop | 74 scripts: 73 rc=0, 1 rc=1 (AUD-03/AUD-04 reproduction) | `out/final/all_tests.txt`, `out/final/<test>.log` |
| `python3 tools/check_include_graph.py --verbose` | rc=0, 6/6 PASS, 34 headers / 54 edges / all reachable | `out/final/include_graph.log` |
| 11 remaining gates (`layout`, `presets`, `mql5-rules`, `static`, `release`, `scenario`, `preflight`, `pinmap`, `input-fingerprint`, `set-presets`, `arb-patch`) | all rc=0 | `out/final/remaining_gates.txt`, `out/final/gate_*.log` |
| `python3 tools/test_tool_reference_integrity.py` | rc=0, 1050 resolved / 0 missing / 399 files | `out/final/test_tool_reference_integrity.log` |
| `python3 tools/test_pmi_replay_audit.py` | rc=0; native ASan/UBSan tri-state harness and all source contracts pass | `out/final/test_pmi_replay_audit.log` |
| `python3 tools/test_docs_freshness.py`, `tools/test_tactical_authority.py`, `tools/test_comment_integrity.py` | rc=0 after line-count-neutral edits | `out/final/test_docs_freshness.log`, `out/final/test_tactical_authority.log`, `out/final/test_comment_integrity.log` |
| `python3 tools/mql5_rules.py --quiet` | rc=0, 0 dialect warnings | `out/final/gate_mql5_rules.py___quiet.log` |
| `python3 tools/static_check.py` | rc=0, 0 errors | `out/final/gate_static_check.py.log` |

### Failed

| Suite | Result | Why it is red |
|---|---|---|
| `python3 tools/test_entry_review_gate.py` | rc=1, 4 source-contract failures + 26 native behavioural failures | Documents the reproduced, deferred AUD-03/AUD-04 fail-open defects. It is not wired into the curated gate or CI; the source repairs were not authorized. See `out/final/test_entry_review_gate.log` and `out/repro/entry_review_gate_before.log`. |

During development, an earlier line-count-changing edit made
`test_docs_freshness.py` and `test_tactical_authority.py` fail on shifted pinned
line numbers. That was **not** accepted: the host edits were reworked to be
line-count-neutral, and both suites returned to rc=0. The intermediate failure
logs are preserved in `out/repro/*_line_neutral.log`.

### Blocked / Not executed

| Item | Status | Exact reason / manual command |
|---|---|---|
| Full MQL5 compile | Not executed | `metaeditor64.exe`, `metaeditor.exe`, `wine` absent. Manual: open `MQL5/Indicators/nadir2.mq5`, `MQL5/Experts/QSMC_AutoTrader.mq5` and the QSMC indicators/scripts in MetaEditor and press F7; record 0 errors/0 warnings. |
| Strategy Tester / historical backtest | Not executed | Requires MT5 terminal and broker data. |
| Live MT5 demo attach, iCustom handshake, banner, dry-run, paper trial | Not executed | Requires MT5 terminal. Manual runbook: `docs/DEMO_TRIAL_RUNBOOK.md`, `docs/QSMC_BUILD_AND_RUN.md`, `docs/QSMC_GO_LIVE_RUNBOOK.md`. |
| Broker latency, partial fills, rejection/retry, simultaneous multi-instance terminal run | Not executed | Requires MT5 terminal and broker. |
| Regression tests for AUD-03/AUD-04/AUD-05/AUD-06/AUD-07 source repairs | Not executed | Repairs deferred; AUD-03/AUD-04 already have a failing reproduction suite, the others are source-review findings. |
| Real-money validation | Not executed and not armed | `InpAllowRealTrading=false`, confirmations empty, REAL refused by `TradeEnvBlock()`. |

No test was disabled, no assertion removed, no failed bar ignored, no replay
comparison weakened, no expected outcome changed merely to obtain green.

---

## E. Regression Analysis

- **Mirror integrity:** root `nadir2.mq5` and `MQL5/Indicators/nadir2.mq5`
  remain byte-identical; `check_repo_layout.py` L3 PASS. Both are CRLF files
  marked `-text` by `.gitattributes`; `git -c core.whitespace=cr-at-eol diff
  --check` is clean, while plain `git diff --check` flags the CR at EOL as
  trailing whitespace.
- **Line-number stability:** the first attempt added comment lines and broke
  60+ exact line pins in `test_docs_freshness.py` and 3 tactical-authority
  pins. The final edits preserve the original 45,584 CRLF lines; both suites
  are green again. This is evidence that the pinned contracts were respected,
  not weakened.
- **MQL5 dialect / lexical contracts:** `mql5_rules.py --quiet` 0 warnings;
  `test_comment_integrity.py` rc=0; `static_check.py` 0 errors. These are
  static contracts, not F7 compilation.
- **Curated gate coverage:** two new checks were added, not substituted for
  existing ones. Baseline 70/70 became final 72/72.
- **CI coverage:** `qsmc-verify.yml` now runs the tool-reference gate in the
  same layout step. `test_entry_review_gate.py` is intentionally excluded from
  CI because it is a red reproduction of an unauthorized repair; hiding or
  `continue-on-error`-ing it would misrepresent the execution-safety state.
- **Compatibility:** no input, preset, buffer, include edge, public function
  name, magic, fingerprint, REAL switch or risk ceiling changed. The only
  executable-code change is the PMI failure-print boolean, which adds a log
  line for a causality failure and cannot submit, modify or close an order.
- **Causality:** no incremental/full replay mismatch was reproduced; no replay
  assertion, digest comparison, skip rule or verdict text was loosened.

---

## F. Remaining Risks

1. **AUD-03/AUD-04/AUD-05 are unresolved P1 execution fail-open paths.** The
   standalone regression suite is red by design. They must be repaired and
   retested before any demo or live validation.
2. **AUD-06/AUD-07 are unresolved config/lifecycle defects.** Both require
   executable-source changes and explicit approval.
3. **No MetaEditor F7 or MT5 run occurred.** Offline/static/native green is
   necessary but not sufficient; 0 compile errors/warnings and a live banner
   are still unverified.
4. **No full replay-equivalence suite exists in this checkout.** The six
   historical harness names were corrected, but no shipped tool reproduces the
   claimed 700+ randomized trials. `CausalReplay` same-bar fingerprint
   comparisons and PMI tri-state audits remain the available evidence.
5. **Dead replay flags (AUD-08)** could mislead a future maintainer into
   treating `SKIPPED` as equivalence success if they are later wired into a UI.
6. **No exhaustive state-transition suite** exists because the brief's named
   state machine is not present in `terad`; the actual OnInit/Ready/Deinit
   lifecycle is covered only by static/runtime diagnostics.
7. **QATS** is a separate experimental product with its own `CTrade` path and
   was not promoted, merged into QSMC, or certified here.
8. **Historical docs** are frozen snapshots; only `docs/INDEX.md` sections 1–4
   and this report describe the current tree.

---

## G. Production Readiness

`NOT READY`

Reason: offline gates are green and two independent diagnostic defects were
repaired, but a red regression suite still reproduces three P1 execution-safety
fail-open paths, no approved execution-source repair was made, and MetaEditor
F7, Strategy Tester, live MT5 demo attach and broker validation remain not
executed. No success claim is made from compilation or offline test counts.
