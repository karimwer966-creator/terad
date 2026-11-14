# QATS Compile & Test (`QATS_COMPILE_TEST`) — v1.24 module, Phase 10

**Status: offline scope complete; MetaEditor compile NOT performed — not available
in this environment (stated plainly below). NOT compile-verified, NOT
Strategy-Tester run, NOT demo-forward-tested. REAL remains disarmed.**

This phase is the gate between "engineered and offline-sim-verified" and
"allowed to touch a demo terminal". It can close only as far as this environment
permits. What closed and what did not is listed exactly; nothing is dressed up.

## 1. What landed

- `docs/QATS_STRATEGY_TESTER_CONFIG.md` — deliverable #7 (test configuration):
  terminal/model/window (2024-01-01 → 2026-10-31 incl. the 2024 gold stress),
  forward split 20–25%, quarterly walk-forward, run matrix R1..R6
  (limit-entry toggle, profiles, news, M15 displacement), one-factor-at-a-time
  sensitivity grid (`InpMinScore` 55/60/65, `InpDisplaceATR` 1.2/1.5/2.0,
  `InpSetupWindowBars` 12/24/48; 9 cells), mandatory metric decomposition,
  Phase-9 journal-diagnostics review recipe, spread scenarios, kill criteria,
  tick-box checklist, NO-profitability-claim banner, artifact convention.
- `docs/QATS_TEST_REPORT_TEMPLATE.md` — deliverable #8 (test report template):
  identity/hashes, F7 gate line, primary-run table, sensitivity grid with the
  pre-declared decision rule (no silent preset adoption), quarterly
  walk-forward, per-slice decomposition, Phase-9 `[QATS][GUARD]` histogram
  table, spread scenarios, exactly-one verdict rubric, and explicit REAL-stays-
  disarmed wording.
- Offline suites re-run against the exact shipping source (after the one
  in-phase dialect fix from Phase 9's close-out):

  | Suite | Result |
  |---|---|
  | `verify_quantum_ea.py` (structural) | PASS; `user_functions=166` |
  | `test_qats_native_build.py` (strict MQL5-shim build) | 62/62 defect-injection rejections |
  | `test_qats_dual_direction.py` | **91/91** (unit + 61 scenarios incl. Phase-9 `diagnostics_record_*`) |
  | `test_qats_limit_entry.py` | **98/98** |
  | `test_qats_journal_report.py` | **33/33** |
  | `test_qats_native_build.py` + qats-backtest study (2026-11-11, prior) | study figures unchanged; no demonstrated edge |
  | `check_production_ready.py` (61 curated checks) | **61/61 OFFLINE GO** (57/57 at first Phase-10 run; extended in the 2026-11-14 PR-68 close-out) |

- Changelog entry **2026-11-14, Phase 10**; audit addendum updated (phases
  2..9 → 2..10); README status block extended.

## 2. The compile, plainly

**No MetaEditor F7 compile was performed in this work.** The environment probe
on 2026-11-14 found no MT5 toolchain:

```
$ for b in wine wine64 metaeditor metaeditor64 metatester metatester64; do command -v $b; done
(none)
$ ls /opt                        # yarn-v1.22.22 only — no MT5
$ ls -d ~/.mt5 /root/.wine …
(none)
$ python3 -c "import MetaTrader5"
ModuleNotFoundError …
```

`MetaTrader5` (where importable) is an RPC client to a *running* terminal, not a
compiler; no terminal is installed here, and the MetaQuotes CDN is not an outbound
host available to this workspace. **The offline suites — including the strict
shim build and the dialect lint — are not a compile.** F7 on this exact file
remains the gate that only a human with a terminal can open. Until it reads
`0 errors, 0 warnings`, the binary nobody has built is "the same source text",
nothing more.

## 2a. F7 attempts (operator-side, this checkout)

| # | Date | Tree | Result |
|---|---|---|---|
| 1 | 2026-11-14 | `d3df3f6` (PR-#68 merge) | **1 error** — `undeclared identifier 'importance'` (QuantumAutonomousTradingSystem.mq5:2911; the news guard read importance off `MqlCalendarValue`). **FIXED** on branch `arena/7c5c992a-terad` to the event-join pattern proven by nadir2 (History NULL → join by `event_id`); changelog 2026-11-14-F7-1. Note: the Phase-10 wording below ("no F7 performed") is superseded by this table. |
| 2 | pending | `arena/7c5c992a-terad` | awaits the operator's F7 — specifically to verify `CalendarEventByCurrency` and `MqlCalendarEvent.id` (both unverifiable offline; documented fallback if either fails) |

## 3. Readiness classification (unchanged, deliberately)

**MODIFIED — not compile-verified, not backtested in the terminal, not
demo-forward-tested, not production-ready.** Phase 10 closed everything this
environment can close (docs, offline evidence, tester plan, report skeleton).
The remaining gates are, in order: (1) human F7 with the banner recorded;
(2) the tester matrix run per `QATS_STRATEGY_TESTER_CONFIG.md` with
`QATS_TEST_REPORT_TEMPLATE.md` filled in — including a legitimate
**negative** verdict; (3) ≥ 4 weeks DEMO forward test; (4) REAL only via
`QSMC_GO_LIVE_RUNBOOK.md` and explicit written authorization. Anyone who
reads "Phase 10 complete" as "ready to trade" has misread it.

Known environmental limitation, unchanged: the offline host simulation is a C++
transpile against a typed shim, not MT5; the 2026-11-11 study's figures predate
the v1.24 module series (PD-adaptive, regime report-only, news-fail-open,
limit re-validation, watermark scan, Phase-9 journal) and describe the engine
as it existed then. They remain the public prior: **no demonstrated edge.**

## 4. What this phase did NOT change

- `QATS_VERSION` remains **1.23**. No EA code, no inputs, no preset keys, no
  guard, no sizing, no order path — documentation and a report template only.
  `git diff` touches no `.mq5` for this phase (the one Phase-9 dialect fix
  landed before the 57/57 GO that closes Phase 9's close-out).
- The production preset, REAL-disarm, `InpDemoOnly=true` — untouched.
- Docs freshness policy: the 119 pre-existing "freshness" citations flagged by
  the gate tooling in sibling documents are untouched, per standing policy.

## 5. Operator's next actions (in order)

1. F7 this exact checkout in MetaEditor; paste the build banner into
   `QATS_TEST_REPORT_<date>.md` §2.
2. Run the tester matrix (config doc §3–§7); fill `QATS_TEST_REPORT_TEMPLATE.md`
   completely, including the §7 GUARD histogram.
3. Honest verdict. If it is NO EDGE, write it out and keep the EA DEMO/research.
4. If the verdict is unconfirmed-or-better, ≥ 4 weeks DEMO forward test with the
   same metrics; then, only with explicit authorization, the REAL path.

## 6. Deliverables map (audit §8)

1. Audit — `docs/QATS_MASTER_AUDIT_2026-11-13.md` (updated phases 2..10)
2. Bug lists — same document, §4/§5 (+ addendum)
3. Updated `.mq5` — Phases 1–9 work on this branch (uncommitted)
4. Changelog — `docs/QATS_CHANGELOG.md`, entries through 2026-11-14
5. Module notes — `QATS_ADAPTIVE_PD_V124.md` … `QATS_DIAGNOSTICS_JOURNAL_V124.md`,
   this file, `QATS_STRATEGY_TESTER_CONFIG.md`, `QATS_TEST_REPORT_TEMPLATE.md`
6. Real compile log — **not performed; §2 records why**
7. `docs/QATS_STRATEGY_TESTER_CONFIG.md` — landed
8. Test report — template landed; the report itself awaits the tester run
9. Known limitations — `QATS_MASTER_AUDIT_2026-11-13.md` §10 + addendum
10. Readiness — MODIFIED, restated in §3

*No profitability claim is made or implied anywhere in this phase's deliverables.*
