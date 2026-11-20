# QSMC — CONDITIONAL relocation map (baseline-gated; NOT executed)

Status: **APPROVED PLAN, CONDITIONAL ON BASELINE. Do not execute now.**
Preconditions before any `git mv`:

1. Baseline gate closed: compile + run logs returned, clean dump CSV
   (`bar_status=OK`), hash verification of `docs/QSMC_BASELINE_HASHES.md`
   passes, and explicit user approval to proceed.
2. Working tree clean of unintended changes; the diagnostic script remains
   isolated (`MQL5/Scripts/QSMC_FixedRangeDump.mq5`).
3. Decide, with evidence, whether anything consumes the moved files at runtime
   (see deployment paths).

## The mapping (corrected; do not alter)

| Source (now) | Target (after baseline) | Mechanism |
|---|---|---|
| `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` (QATS) | `MQL5/Legacy/` (same basename) | `git mv` only |
| `MQL5/Experts/KLJ_DataFeeder.mq5` | `MQL5/Legacy/` (same basename) | `git mv` only |
| `MQL5/Indicators/QSMC_ScannerProbe.mq5` | `MQL5/Legacy/` (same basename) | `git mv` only |

Explicit prohibitions:

- **NOT** `Experts/Legacy/`, **NOT** `Indicators/Legacy/`. The destination is
  exactly `MQL5/Legacy/`.
- `git mv` only — preserves history; no copy-delete.
- The move preserves each file's basename under `MQL5/Legacy/`.
  Moving source does **NOT** stop an already-installed `EX5` on any terminal.
  EX5 lifecycle is separate (manual removal from Experts/Indicators folders +
  restart). Never describe the move as "removing the deployed tool".

## Optional deployment paths that must be preserved

- **KLJ_DataFeeder**: if the `FILE_COMMON` CSV feed
  (`QSMC\data_feed.csv` by default) is still required by any live flow, its
  deployment path stays supported: keep building/copying the EX5 into
  `MQL5/Experts\` **or** document an equivalent install step from
  `MQL5/Legacy/`. Moving source must not strand an active feed. Verify default
  `COMMON` location before and after (`FileCommon` folder).
- **QATS**: if still used as a separate product, keep its build/deploy path
  (`MQL5/Legacy/` → compiled and deployed to a terminal's `MQL5/Experts\`)
  documented. It is retired from the active tree; it is not deleted.

## What stays untouched (until separately decided)

- `MQL5/Indicators/nadir2.mq5` and `MQL5/Indicators/QSMC_SmcVpEngine.mq5` —
  still the **two active `.mq5` files in Indicators**. The one-file goal is NOT
  achieved; `SmcVp` is a separate, final integration decision, explicitly not
  taken in this step.
- `MQL5/Experts/QSMC_AutoTrader.mq5`, all `MQL5/Include/QSMC/*.mqh`,
  `QSMC_BufferDump`, presets, and trading rules/guards: unchanged.
- `tools/package_production.py` — reviewed as embedding the feeder and
  ScannerProbe in its packaging step; after the move, update its file list so
  packaging either excludes them or points at `MQL5/Legacy/…`, **only after**
  the baseline gate closes and with a separate commit. Do not edit it now.

## Verification after (future) execution

- `git status` shows pure renames (`R`), no content change
  (`git diff --cached --find-renames`).
- `docs/QSMC_BASELINE_HASHES.md` updated in a dedicated commit recording that
  paths changed but content hashes are identical.
- No new file is added to compiled include paths; `.set` compatibility of any
  separately deployed EX5 re-checked by the user on the demo terminal.
