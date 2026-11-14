# QATS Displacement / OB / FVG (`QATS_DISPLACEMENT_FVG`) — v1.24 module, Phase 5

**Status:** implemented, offline-verified (host-compiled simulation + unit suite).
**NOT** compile-verified in MetaEditor, **NOT** backtested, **NOT** demo-forward-tested.
No production claim is made by this document.

Scope: the displacement/OB/FVG mandate (master audit §5). Companion to
`QATS_ADAPTIVE_PD_V124.md` and `QATS_LIQUIDITY_V124.md`.

QATS_VERSION remains `1.23`; the v1.24 tag names the Phase 2–10 upgrade track,
not a released version.

## What was preserved (the engine itself)

`DetectDisplacement` is deliberately **unchanged**:

- directional closed bar only (bull = close > open, bear = close < open);
- `body >= InpDisplaceATR × ATR` (H1 ATR on the H1 path, M15 ATR on the M15
  path — the two ATRs never mix), **or**
- `body / range >= InpDisplaceBodyRatio` **and** `range >= 1.3 × ATR`;
- search starts at the bar that rejected the sweep when there is one, else the
  whole window — an impulse that precedes the stop run is never counted;
- H1 is checked first; only without an H1 impulse is M15 scanned
  (`InpDisplaceM15`), anchored at the M15 bar containing the sweep rejection
  H1 bar's open;
- closed bars only, no look-ahead.

Zones (`FindOrderBlock`, `FindFVG`) keep their rules; `ZoneStillValid` keeps
the Phase 2 CR-7 fail-closed semantics (invalid numbers, insufficient history,
unreadable bar ⇒ zone rejected, journal once per attach).

## What changed in Phase 5

### 1. Per-event TF+shift storage for liquidity sweep events (`SSweep`)

Mirror of the `e.dispTF/e.dispBar` treatment displacement got in v1.23. The
event is now journalled with its own coordinates instead of deriving them at
print time:

| field | meaning |
|---|---|
| `tf` | the timeframe the run was detected on (`PERIOD_H1` today — stored explicitly so a future M15 sweep pass cannot lie about its timeframe) |
| `poolShift` | formation bar of the pool: H1 shift for `SWING`/`EQH`/`EQL`; `0` for `PDH`/`PDL`/`PWH`/`PWL` (the day/week boundary) |
| `eventTime` | server time of the rejection bar, **frozen at detection** — the journal never re-reads history to say when the sweep happened |

`ResetSide` clears all three (`PERIOD_CURRENT` / `-1` / `0`). `SweepForDirection`
fills them (the same-bar multi-pool tie keeps the first-frozen `eventTime`;
`poolShift` tracks the pool whose label wins the `PoolRank` tie-break).

The chain journal now names the event, e.g.:

```
sweep=SSL:EQH@1996.00(detected H1 shift 3 @ 2026.11.13 09:00; level formed shift 14; extreme 1992.50)
```

(`BarText()` still re-reads history for the *structure* event, which has no
frozen timestamp; the sweep event no longer does.)
`TFName()` prints the timeframe (the offline shim has no `TimeframeToString`).

### 2. FVG/OB must be displacement-validated — made literal

Before Phase 5, `AnalyzeSide` fell back to anchoring the zone search at the
sweep bar when no displacement was present: a gap or order block that had not
formed around **any** impulse could still be scored as zone confluence, which
is what the mandate forbids ("FVG must be displacement-validated (it already is
via anchor impulse)" — it was not, on that path).

After Phase 5, zones are searched **only around a displacement impulse**:

- H1 displacement → anchor at `e.dispBar` (its own bar);
- M15 displacement → anchor at the closed H1 bar containing it (mapped via
  `ShiftOfTime`); if that bar cannot be established there is **no anchor and no
  zone** — the old "cross into the sweep bar" rescue is gone;
- no displacement ⇒ `impulse == 0` ⇒ `e.hasOB = e.hasFVG = false`,
  `e.zoneTouched = false`, zone confluence scores `ZONE:0`. Zone points were
  always optional confluence, never part of the core gate, so no entry decision
  changes beyond the removal of unvalidated zone points.

The `sweep_only/*` scenarios assert on the **swept** side that `ZONE:0` is
scored (the other side of the synthetic tape may have its own impulse and is
not constrained). The rule is side-symmetric.

### 3. Mitigated-zone reuse — rejected (unchanged)

A zone whose post-formation bar closes through it is rejected
(`ZoneStillValid`); the FVG/OB search window starts at the impulse bar and
never reaches into the future.

## Unit coverage added

`unit.sweep_event` — event TF/shift/time storage on the live H1 fixtures
(bull and mirror), the `ResetSide` reset contract, the chain-text format
(rejection TF+shift, formation shift, frozen time), `TFName` — 18 static
checks. Scenario: `sweep_only/*` asserts the swept side scores `ZONE:0`.
Unit suite: **430 checks, 0 failed** (was 410 at Phase 4 close-out).

## Rollback copies

- `MQL5/Experts/rollback/QuantumAutonomousTradingSystem_pre_phase5.mq5` — v1.23 + Phase 2 + Phase 3 + Phase 4 (reconstructed; the diff pre_phase5→worktree contains ONLY the Phase 5 hunks).
- `MQL5/Experts/rollback/qats_selftest_pre_phase5.inc` — Phase 4-exit selftest (verified: the pre_phase5 EA builds against it and reports `unit: 410 checks, 0 failed`; the current worktree EA reports `430 checks, 0 failed`).
- `MQL5/Experts/rollback/qats_scenarios_pre_phase5.inc` — Phase 4-exit scenarios (pairs with the above).

All were untracked (`MQL5/Experts/rollback/` is gitignored) and their copies are **ephemeral — they do not survive an ephemeral workspace snapshot**. If the directory is missing: v1.23 exact is commit `db025e9` (`git show db025e9:MQL5/Experts/QuantumAutonomousTradingSystem.mq5`); the Phase 2..5 boundaries are uncommitted working-tree state and can only be re-derived from the phase diffs recorded in `QATS_CHANGELOG.md` — durability requires committing the phase work.


## Limitations & open items

- Sweep detection is H1-only by construction; `SSweep.tf` stores `PERIOD_H1`
  for a truthful, auditable tape.
- Zone search remains "nearest unmitigated gap/candle around the impulse"; an
  old, still-open gap can be scored even if it is stale relative to the setup —
  freshness for zones is a Phase 9 diagnostics question, not a Phase 5 rule.
- Not compile-verified in MetaEditor (F7), not Strategy-Tester verified, not
  demo-forward tested. Readiness stays **MODIFIED**.
- QATS_VERSION stays `1.23` (the module series labels itself v1.24; see
  `QATS_ADAPTIVE_PD_V124.md`).
