# Index — every document, by what it is for

113 documents in this folder, plus 5 more in `history/` and the incident
subfolders. This file is the map: which ones are **instructions** (true today, follow them), which ones are **architecture**
(explain the code as it is now), which ones are **QATS** (a separate product), and
which ones are **frozen history** (true on the date printed inside them, and not a
statement about the current build).

Front page: [`../README.md`](../README.md) · install: [`../INSTALL_AR.md`](../INSTALL_AR.md) ·
repository layout: [`PROJECT_MAP_AR.md`](PROJECT_MAP_AR.md)

## 1. Install, attach, go live

| Document | What it answers |
|---|---|
| [`../INSTALL_AR.md`](../INSTALL_AR.md) | التثبيت خطوة بخطوة، وملفات الإعداد المطلوبة |
| [`QSMC_BUILD_AND_RUN.md`](QSMC_BUILD_AND_RUN.md) | compile, attach, first run, what the log must say |
| [`QSMC_DEPLOYMENT_AR.md`](QSMC_DEPLOYMENT_AR.md) | النشر على حساب ديمو/حقيقي، وحدود الصلاحيات |
| [`ATTACH_EA_CORRECTLY_v6.6.14.md`](ATTACH_EA_CORRECTLY_v6.6.14.md) | تركيب المؤشر والروبوت على نفس الشارت بالترتيب الصحيح |
| [`STAGED_GO_LIVE_LADDER_v6.6.14.md`](STAGED_GO_LIVE_LADDER_v6.6.14.md) | three stages, each one file in `presets/`, with pass/fail criteria |
| [`QSMC_GO_LIVE_RUNBOOK.md`](QSMC_GO_LIVE_RUNBOOK.md) | قائمة تحقق الإطلاق: من الإعداد إلى أول صفقة |
| [`QSMC_PRODUCTION_CHECKLIST.md`](QSMC_PRODUCTION_CHECKLIST.md) | the one-page production checklist |
| [`DEMO_SETUP_AR_FULL.md`](DEMO_SETUP_AR_FULL.md) | إعداد الديمو الكامل من الصفر |
| [`DEMO_READY_AR_0.10_LOT_200_STOP.md`](DEMO_READY_AR_0.10_LOT_200_STOP.md) | إعداد الديمو الجاهز (0.10 / 200) |
| [`DEMO_AUTO_DEFAULTS_2026-11-09.md`](DEMO_AUTO_DEFAULTS_2026-11-09.md) | what the compiled defaults arm, and why |
| [`QSMC_SCALPER_M5_RUNBOOK_AR.md`](QSMC_SCALPER_M5_RUNBOOK_AR.md) | سكالبنج M5: الإعداد، الأوقات، وحدود الخطر |
| [`DEMO_TRIAL_RUNBOOK.md`](DEMO_TRIAL_RUNBOOK.md) | the v6.6.24 demo trial: pre-attach, week 0 dry run, weeks 1–8, stop conditions, how to read `analyze_trial.py` |
| [`QSMC_V6.6.25_F7_AND_TESTER_HANDOFF.md`](QSMC_V6.6.25_F7_AND_TESTER_HANDOFF.md) | the two v6.6.25 steps no sandbox can do: the ten-file F7 set and the four init-log lines that prove the right build loaded, the flags-OFF buffer/CSV comparison, the R0–R5 tester matrix with rejection thresholds, and the entry-review check |

## 2. Operate and read the chart

| Document | What it answers |
|---|---|
| [`QSMC_AUTOTRADER.md`](QSMC_AUTOTRADER.md) | the companion EA: every input, every guard, what it refuses |
| [`EA_RISK_INPUTS.md`](EA_RISK_INPUTS.md) | the five EA inputs that size the order: aggregate risk cap, profile match, and the WEAK/MODERATE/STRONG multipliers — meaning, units, default, effect on lots, and the two hard ceilings that bound them |
| [`BUFFER_CONTRACT.md`](BUFFER_CONTRACT.md) | the 27-buffer contract between the indicator and the EA: index, array, writer, whether the EA reads it, value range — and why buffer 26 is a label, not a gate |
| [`SEVEN_THRESHOLDS_2026-11-27.md`](SEVEN_THRESHOLDS_2026-11-27.md) | the seven thresholds behind the missed trade: current value, the `was` value its comment claims, every code site, what it gates — and the exact Strategy Tester A/B that would validate it |
| [`INPUTS_REFERENCE.md`](INPUTS_REFERENCE.md) | **generated** — every input in every shipped program and header: type, default, group, and the source's own one-line meaning (`UNDOCUMENTED IN SOURCE` where the author wrote none) |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | the whole system on one page: size, dependency graph, internal modules, the market→buffer→EA→trade data flow, the signal outcome model, and where the risk is concentrated |
| [`QSMC_CHART_READING_AR.md`](QSMC_CHART_READING_AR.md) | معنى كل نص على الشارت، وترتيب سلطة الطبقات |
| [`QSMC_DASHBOARD_CLARITY.md`](QSMC_DASHBOARD_CLARITY.md) | compact decision card, grouped SMC explainability panel, `DATA_WAITING`, verdict codes and caps |
| [`QSMC_WHY_NO_TRADES.md`](QSMC_WHY_NO_TRADES.md) | triage: a trade is missing — which gate refused it |
| [`QSMC_CORE_DIAGNOSTICS_AR.md`](QSMC_CORE_DIAGNOSTICS_AR.md) | التقاط سجل قارئ CORE على XAUUSD/M15 بحساب DEMO دون أوامر |
| [`QSMC_TRIAL_XAUUSD_M15_AR.md`](QSMC_TRIAL_XAUUSD_M15_AR.md) | تركيب حزمة التجربة واختيار المراقبة أو أوامر DEMO أو الإعادة التاريخية |
| [`QSMC_RUNTIME_LOG_REVIEW_AR.md`](QSMC_RUNTIME_LOG_REVIEW_AR.md) | قراءة سجل Experts سطرًا سطرًا |
| [`QSMC_TRADER_MIND_REVIEW_AR.md`](QSMC_TRADER_MIND_REVIEW_AR.md) | الخطوات التسع للقرار، ومقارنتها بمتداول محترف |
| [`QSMC_SCREENSHOT_PRIMARY_CONFLICT_AR.md`](QSMC_SCREENSHOT_PRIMARY_CONFLICT_AR.md) | لماذا تختلف الأولوية عن الشموع أحيانًا |
| [`QSMC_LIQUIDITY_VALUE_AR.md`](QSMC_LIQUIDITY_VALUE_AR.md) | طبقة السيولة والقيمة، وكيف تُقاس |
| [`QSMC_SMCVP_ENGINE_AR.md`](QSMC_SMCVP_ENGINE_AR.md) | محرك SMC + Volume Profile: المخرجات ومعناها |

## 3. Architecture and audits (living)

| Document | What it answers |
|---|---|
| [`EL_ENGINEERING_REVIEW_2026-11-18.md`](EL_ENGINEERING_REVIEW_2026-11-18.md) | EL/QSMC audit, targeted data/identity fixes, unresolved MTF/provenance blockers, test evidence and NOT READY verdict |
| [`EL_SOURCE_INVENTORY_2026-11-18.md`](EL_SOURCE_INVENTORY_2026-11-18.md) | complete MQL source/include inventory, tools/configuration map and host function locations |
| [`ARCHITECTURE_AUDIT_v6.6.24.md`](ARCHITECTURE_AUDIT_v6.6.24.md) | the whole tree at v6.6.24: file inventory, the 33-header dependency graph, the 14 modules mapped onto real owners, rules 1–15 status, and why no `QME.mqh`/second EA exists (gate `tools/check_include_graph.py`) |
| [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | every layer, its inputs and its authority (documents **QATS**, the separate product) |
| [`QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md`](QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md) | the pinned audit the test suites cite (ANCHORS/ORDER/GUARDS) |
| [`QSMC_MARKET_STRUCTURE.md`](QSMC_MARKET_STRUCTURE.md) | BOS/CHoCH, swings, structure state machine |
| [`QSMC_ZONE_SCORER.md`](QSMC_ZONE_SCORER.md) | zone scoring and the graded entry |
| [`QSMC_EARLY_BREAK.md`](QSMC_EARLY_BREAK.md) | early-break detection contract |
| [`QSMC_EDGEBOOK.md`](QSMC_EDGEBOOK.md) | the measurement layer (what is and is not measured) |
| [`QSMC_QUANT_STATS.md`](QSMC_QUANT_STATS.md) | quant statistics used by the gates |
| [`QSMC_ENTRY_REVIEW_v6.6.21.md`](QSMC_ENTRY_REVIEW_v6.6.21.md) | the 12-line entry-review checklist |
| [`QSMC_CORE_ZERO_INVESTIGATION.md`](QSMC_CORE_ZERO_INVESTIGATION.md) | why CORE published nothing, with the evidence boundary |
| [`SIGNAL_VISIBILITY_DIAGNOSIS.md`](SIGNAL_VISIBILITY_DIAGNOSIS.md) | the seven relaxed thresholds the `// was X` input comments cite: what each one actually gates (function / line / refusal string), the ZRE and v6.6.25-C interactions, and what no measurement has proven |
| [`QSMC_SMCVP_ENGINE_AUDIT_2026-11-11.md`](QSMC_SMCVP_ENGINE_AUDIT_2026-11-11.md) | SMC+VP engine audit (G1–G7) |
| [`QSMC_ROBUSTNESS_PLAYBOOK.md`](QSMC_ROBUSTNESS_PLAYBOOK.md) | how not to over-fit: WFA, state isolation, gates |
| [`QSMC_ROBUSTNESS_PLAYBOOK_AR.md`](QSMC_ROBUSTNESS_PLAYBOOK_AR.md) | نفس الدليل بالعربية |
| [`QSMC_REVIEW_INDEPENDENT.md`](QSMC_REVIEW_INDEPENDENT.md) | مراجعة مستقلة (2026-10-30) |
| [`QSMC_V6.6.10_TACTICAL_AUTHORITY.md`](QSMC_V6.6.10_TACTICAL_AUTHORITY.md) | TACTICAL layer audit — historical rules still enforced |
| [`KLJ_V6.6.0_SIGNAL_ARBITRATION.md`](KLJ_V6.6.0_SIGNAL_ARBITRATION.md) | arbitration layer, line by line |
| [`KLJ_V6.6.0_PART_C.md`](KLJ_V6.6.0_PART_C.md) | data layer (Phase 6) |
| [`KLJ_V6.6.9_ONE_ZONE_ROLE.md`](KLJ_V6.6.9_ONE_ZONE_ROLE.md) | one zone, one role |
| [`BUFFER_DIFF_v6.6.23_v6.6.24.md`](BUFFER_DIFF_v6.6.23_v6.6.24.md) | how to dump buffers 7..12 / 21..25 and read the diff between two builds |
| [`AI_PROMPT_FIX_SIGNALS.md`](AI_PROMPT_FIX_SIGNALS.md) | a ready-to-run prompt describing a signal defect |

## 4. Reports of this repository's own work

| Document | What it records |
|---|---|
| [`PRODUCTION_REVIEW_2026-11-16_AR.md`](PRODUCTION_REVIEW_2026-11-16_AR.md) | مراجعة كل ملف + الترتيب + ربط الإعدادات (هذه الدورة) |
| [`AUDIT_v6.6.24.md`](AUDIT_v6.6.24.md) | the v6.6.24 full-repository audit: findings by class, INVALID items with evidence, the demo-trial deliverables |
| [`QSMC_STRATEGY_CATALOG_ANALYSIS_2026-11-24.md`](QSMC_STRATEGY_CATALOG_ANALYSIS_2026-11-24.md) | cross-map of the 49-strategy TradeZella library onto QSMC surfaces: coverage classes, ranked adoption tiers, rejections with reasons (analysis only, no code) |
| [`AUDIT_v6.6.24_2026-11-16.md`](AUDIT_v6.6.24_2026-11-16.md) | archived prior audit cycle (2026-11-16), renamed via `git mv` from `AUDIT_v6.6.24.md` when the 2026-11-24 cycle took the canonical path; content unchanged |
| [`PRODUCTION_REVIEW_v6.6.24_AR.md`](PRODUCTION_REVIEW_v6.6.24_AR.md) | التقرير العربي لدورة v6.6.24: العيوب الأحد عشر، فصل (أ) عن (ب)، أدوات التجربة R1–R5، والخطوات اليدوية الست |
| [`QSMC_AUDIT_2026-11-25.md`](QSMC_AUDIT_2026-11-25.md) | independent repository-wide audit: baseline, dependency map, reproduced/deferred execution defects, repaired diagnostic gates, regression analysis and readiness verdict |
| [`CONFIRMATION_ENGINE_REPLAY_2026-11-25.md`](CONFIRMATION_ENGINE_REPLAY_2026-11-25.md) | deterministic replay of the two 2026-11-25 zone setups across parser/state/UTC/session/AI/risk layers; companion 42-column [`confirmation_replay_2026-11-25.csv`](confirmation_replay_2026-11-25.csv) |
| [`CONFIRMATION_ENGINE_TEST_BACKTEST_2026-11-25.md`](CONFIRMATION_ENGINE_TEST_BACKTEST_2026-11-25.md) | deterministic 3-month synthetic M1 surrogate, walk-forward split and parameter sensitivity; explicitly not Strategy Tester, broker ticks or evidence of edge |
| [`MISSED_TRADE_2026-11-27_HYPOTHESES.md`](MISSED_TRADE_2026-11-27_HYPOTHESES.md) | why the 2026-11-27 XAUUSD M15 Asia rally produced no CORE signal: five hypotheses verified in the v6.6.24 code (file / function / line / verdict), the v6.6.25 default-OFF switches B–G that address them, and the Strategy Tester plan (not run here) |
| [`REVIEW_INCLUDE_QSMC_v6.6.24_AR.md`](REVIEW_INCLUDE_QSMC_v6.6.24_AR.md) | مراجعة الطبقة الداخلية `Include/QSMC` (33 ملفًا): 23 عيبًا أُصلحت، وحكم على التغييرات المقترحة، وما لم يُراجَع صريحًا |
| [`QSMC_LINKS_REPAIR_2026-11-16_AR.md`](QSMC_LINKS_REPAIR_2026-11-16_AR.md) | إصلاح الروابط بين الأجزاء (الدورة السابقة) |
| [`PROJECT_MAP_AR.md`](PROJECT_MAP_AR.md) | خريطة المستودع: كل مجلد وماذا يحتوي |
| [`QSMC_FIXED_RANGE_DUMP_RUNBOOK.md`](QSMC_FIXED_RANGE_DUMP_RUNBOOK.md) | the diagnostic-only nadir2 fixed-range dump: side-effect limits, Windows compile/run, CSV checks (COMPILE/RUN/CSV **NOT VERIFIED**) |
| [`QSMC_BASELINE_HASHES.md`](QSMC_BASELINE_HASHES.md) | sha256 manifest of production sources @ base `06bd0896` (tag `pre-refactor-v6.6.24` no longer resolves) — the diagnostic tool is not a baseline change |
| [`QSMC_QSVP_3_OF_10_TRACE.md`](QSMC_QSVP_3_OF_10_TRACE.md) | what "SELL candidate 3/10, FAIL at LIQUIDITY SWEEP" means, with file:line evidence |
| [`QSMC_RELOCATION_MAP_CONDITIONAL.md`](QSMC_RELOCATION_MAP_CONDITIONAL.md) | relocation of QATS/KLJ_DataFeeder/ScannerProbe → `MQL5/Legacy/` — approved but CONDITIONAL on the baseline; not executed |
| [`QSMC_TESTER_PLAN_1_OBSERVATION.md`](QSMC_TESTER_PLAN_1_OBSERVATION.md) | Strategy Tester plan 1 — observation/dry-run diagnostics (no fills) |
| [`QSMC_TESTER_PLAN_2_EXECUTION.md`](QSMC_TESTER_PLAN_2_EXECUTION.md) | Strategy Tester plan 2 — execution characterization, isolated tester only, never live |
| [`QSMC_OPPORTUNITY_FUNNEL_AR.md`](QSMC_OPPORTUNITY_FUNNEL_AR.md) | Phase B: diagnostics-only per-closed-bar opportunity funnel — وحدة غير موصولة بعد، عقد عدم التداخل، خريطة خطافات مقترحة، صيغة CSV |
| [`QSMC_PERSONAL_PRODUCTION_AR.md`](QSMC_PERSONAL_PRODUCTION_AR.md) | دليل التشغيل الشخصي: sha256 للحزمة، ترتيب التركيب/الترجمة، المرحلة 0 DIAG ثم DEMO المسلح، بروتوكول 8 أسابيع/30 صفقة، شروط إيقاف، فصل REAL عن DEMO |
| [`QSMC_TRIAL_READY_AR.md`](QSMC_TRIAL_READY_AR.md) | بطاقة التجربة المصغّرة: الحزمة الموقعة، البوابات، خطوات Windows بالترتيب DIAG ثم DEMO، ما يجب إرجاعه للتأكيد |

## 5. QATS — a separate product (not production-ready)

[`QATS_README.md`](QATS_README.md) is the entry point and carries the honest
status block. The series below documents that product only:

`QATS_MASTER_AUDIT_2026-11-13.md` · `QATS_ADAPTIVE_PD_V124.md` ·
`QATS_LIQUIDITY_V124.md` · `QATS_DISPLACEMENT_FVG_V124.md` ·
`QATS_EXECUTION_RISK_V124.md` · `QATS_DIAGNOSTICS_JOURNAL_V124.md` ·
`QATS_REGIME_SESSION_NEWS_V124.md` · `QATS_M5_M1_SCALPING_V124.md` ·
`QATS_COMPILE_TEST_V124.md` · `QATS_CHANGELOG.md` · `QATS_LIMIT_ENTRY_V121.md` ·
`QATS_M15_DISPLACEMENT_V123.md` · `QATS_DUAL_DIRECTION_AR.md` ·
`QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md` · `QATS_BACKTEST_STUDY_2026-11-11.md` ·
`QATS_STRATEGY_TESTER_CONFIG.md` · `QATS_TEST_REPORT_TEMPLATE.md` ·
`QUANTUM_DEMO_REAL_AR.md` · `XAUUSD_EXECUTION_POLICY_REPORT.md` ·
`PRODUCTION_AUDIT_2026-11-09_QUANTUM_EA.md` ·
`PRODUCTION_VERIFICATION_2026-11-09_QUANTUM_EA.md`

## 6. Frozen history — read as dated, not as current

Everything in [`history/`](history/) (the v6.6.15 repair report, test report and
the $5k trial playbook), plus the point-in-time material below. These documents
describe a tree that no longer exists; they are kept because they are the evidence
behind decisions, not because they are instructions.

`audit_v6.6.15_RCA.md` · `demo_readiness_audit_v6.6.16.md` ·
`PRODUCTION_AUDIT_PHASE1_AR.md` · `PRODUCTION_AUDIT_PHASE1_v6.6.13.md` ·
`PRODUCTION_PHASE2A_AR.md` · `PRODUCTION_PHASE2B_AR.md` ·
`PRODUCTION_READINESS_REVIEW_2026-11-08_AR.md` · `PHASE2_FIXSET_v6.6.14.md` ·
`PHASE5_AT_RISK_REPORT.md` · `PHASE2A_RESOLVER.diff` · `PHASE2B_HOST.diff` ·
`REPORT_AR_2026-11-06_CAUSAL_CHAIN.md` · `QSMC_REVIEW_v6.6.1.md` ·
`incident-20261101/` (113 frozen files — start at its
[`README.md`](incident-20261101/README.md), which says which of the two log
subtrees is authoritative and for what) · `wfa/` · the replay artefacts
(`qats_backtest_study_2026-11-11.json`,
`qsmc_smcvp_replay_xauusd_m15_2024_2025.json` and its `_signals.csv`) ·
`img/`

> A document is "current" only if it is in sections 1–4. If a Markdown file here
> tells you to load a preset, run a command or expect a version that does not
> appear in [`../README.md`](../README.md), the file is history: trust the
> repository, then `tools/check_repo_layout.py`, then this index.

### Placeholders for documents that were never committed

Each of these is cited by the source or by a preset but was never committed
here. Rather than leave a dead link — or edit a 46,847-line file to delete the
citations, which would invalidate 291 pinned line numbers — each is a short
stub that says plainly it is not the original, names its citing line, separates
verified fact from what the citation merely implies, and points at where the
current truth lives. `tools/test_tool_reference_integrity.py` now reports zero
dangling citations.

| Placeholder | Cited by |
|---|---|
| [`KLJ_V6.5.0_REACTION_LAYER_AUDIT.md`](KLJ_V6.5.0_REACTION_LAYER_AUDIT.md) | `nadir2.mq5:202`, `:4451`, `:40188` |
| [`KLJ_V6.5.0_REACTION_LAYER_REPORT.md`](KLJ_V6.5.0_REACTION_LAYER_REPORT.md) | `nadir2.mq5:203` |
| [`KLJ_V6.5.1_FORENSIC_AUDIT.md`](KLJ_V6.5.1_FORENSIC_AUDIT.md) | `nadir2.mq5:1859` |
| [`KLJ_V6.5.2_FILE_AUDIT.md`](KLJ_V6.5.2_FILE_AUDIT.md) | `nadir2.mq5:143` |
| [`KLJ_V6.5.4_REACTION_CONFLICT_FIX.md`](KLJ_V6.5.4_REACTION_CONFLICT_FIX.md) | `nadir2.mq5:55` and `KLJ_V6.6.0_SIGNAL_ARBITRATION.md` |
| [`PART_A_REPAIR_HANDOFF.md`](PART_A_REPAIR_HANDOFF.md) | `nadir2.mq5:118` |
| [`PREDICTIVE_ENGINE_AUDIT.md`](PREDICTIVE_ENGINE_AUDIT.md) | `nadir2.mq5:1756` |
| [`QSMC_UNIFIED_DEMO_REAL_2026-11-09.md`](QSMC_UNIFIED_DEMO_REAL_2026-11-09.md) | two shipped `.set` presets |

