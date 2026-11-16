# Index — every document, by what it is for

74 documents accumulated across eleven releases. This file is the map: which ones
are **instructions** (true today, follow them), which ones are **architecture**
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

## 2. Operate and read the chart

| Document | What it answers |
|---|---|
| [`QSMC_AUTOTRADER.md`](QSMC_AUTOTRADER.md) | the companion EA: every input, every guard, what it refuses |
| [`QSMC_CHART_READING_AR.md`](QSMC_CHART_READING_AR.md) | معنى كل نص على الشارت، وترتيب سلطة الطبقات |
| [`QSMC_DASHBOARD_CLARITY.md`](QSMC_DASHBOARD_CLARITY.md) | dashboard rows, verdict codes, caps |
| [`QSMC_WHY_NO_TRADES.md`](QSMC_WHY_NO_TRADES.md) | triage: a trade is missing — which gate refused it |
| [`QSMC_RUNTIME_LOG_REVIEW_AR.md`](QSMC_RUNTIME_LOG_REVIEW_AR.md) | قراءة سجل Experts سطرًا سطرًا |
| [`QSMC_TRADER_MIND_REVIEW_AR.md`](QSMC_TRADER_MIND_REVIEW_AR.md) | الخطوات التسع للقرار، ومقارنتها بمتداول محترف |
| [`QSMC_SCREENSHOT_PRIMARY_CONFLICT_AR.md`](QSMC_SCREENSHOT_PRIMARY_CONFLICT_AR.md) | لماذا تختلف الأولوية عن الشموع أحيانًا |
| [`QSMC_LIQUIDITY_VALUE_AR.md`](QSMC_LIQUIDITY_VALUE_AR.md) | طبقة السيولة والقيمة، وكيف تُقاس |
| [`QSMC_SMCVP_ENGINE_AR.md`](QSMC_SMCVP_ENGINE_AR.md) | محرك SMC + Volume Profile: المخرجات ومعناها |

## 3. Architecture and audits (living)

| Document | What it answers |
|---|---|
| [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | every layer, its inputs and its authority |
| [`QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md`](QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md) | the pinned audit the test suites cite (ANCHORS/ORDER/GUARDS) |
| [`QSMC_MARKET_STRUCTURE.md`](QSMC_MARKET_STRUCTURE.md) | BOS/CHoCH, swings, structure state machine |
| [`QSMC_ZONE_SCORER.md`](QSMC_ZONE_SCORER.md) | zone scoring and the graded entry |
| [`QSMC_EARLY_BREAK.md`](QSMC_EARLY_BREAK.md) | early-break detection contract |
| [`QSMC_EDGEBOOK.md`](QSMC_EDGEBOOK.md) | the measurement layer (what is and is not measured) |
| [`QSMC_QUANT_STATS.md`](QSMC_QUANT_STATS.md) | quant statistics used by the gates |
| [`QSMC_ENTRY_REVIEW_v6.6.21.md`](QSMC_ENTRY_REVIEW_v6.6.21.md) | the 12-line entry-review checklist |
| [`QSMC_CORE_ZERO_INVESTIGATION.md`](QSMC_CORE_ZERO_INVESTIGATION.md) | why CORE published nothing, with the evidence boundary |
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
| [`PRODUCTION_REVIEW_v6.6.24_AR.md`](PRODUCTION_REVIEW_v6.6.24_AR.md) | التقرير العربي لدورة v6.6.24: العيوب الأحد عشر، فصل (أ) عن (ب)، أدوات التجربة R1–R5، والخطوات اليدوية الست |
| [`QSMC_LINKS_REPAIR_2026-11-16_AR.md`](QSMC_LINKS_REPAIR_2026-11-16_AR.md) | إصلاح الروابط بين الأجزاء (الدورة السابقة) |
| [`PROJECT_MAP_AR.md`](PROJECT_MAP_AR.md) | خريطة المستودع: كل مجلد وماذا يحتوي |

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
`incident-20261101/` · `wfa/` · the replay artefacts
(`qats_backtest_study_2026-11-11.json`,
`qsmc_smcvp_replay_xauusd_m15_2024_2025.json` and its `_signals.csv`) ·
`img/`

> A document is "current" only if it is in sections 1–4. If a Markdown file here
> tells you to load a preset, run a command or expect a version that does not
> appear in [`../README.md`](../README.md), the file is history: trust the
> repository, then `tools/check_repo_layout.py`, then this index.
