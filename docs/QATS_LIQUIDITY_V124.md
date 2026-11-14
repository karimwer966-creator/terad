# QATS Liquidity (`QATS_LIQUIDITY_ENGINE`) — v1.24 module

**Status:** implemented, offline-verified (host-compiled simulation + unit suite).
**NOT** compile-verified in MetaEditor, **NOT** backtested, **NOT** demo-forward-tested.
No production claim is made by this document.

Scope: the liquidity mandate (master audit §4) — BSL/SSL construction, equal
highs/lows, PDH/PDL, PWH/PWL, sweep vs acceptance vs spent, consumed-level
tracking, and what the map reports. Companion to `QATS_ADAPTIVE_PD_V124.md`.

QATS_VERSION remains `1.23`; the v1.24 tag names the Phase 2–10 upgrade track,
not a released version.

## The map (what existed and was preserved)

- **Pools** — one per confirmed H1 swing (kind `SWING`, or `EQH`/`EQL` when an
  older same-side swing sits within `MathMax(ATR(H1) × InpLiquidityToleranceATR,
  _Point × 2)`), plus `PDH`/`PDL` from PERIOD_D1 shift 1 and `PWH`/`PWL` from
  PERIOD_W1 shift 1. Closest pool wins on equal terms; ranks are
  week(4) > day(3) > equal(2) > swing(1), side-symmetric.
- **States** — `INTACT` (never traded through), `SWEPT` (first pierce bar or the
  bar right after closed back inside and no later close beyond the sweep
  extreme), `ACCEPTED` (two consecutive closes beyond — a breakout), `SPENT`
  (pierced, but undecidable: too old, still open, or the rejection later
  failed — never re-usable and never sweep evidence). First pierce is searched
  over closed bars only; `0` until the first qualifying bar exists.
- **Evidence rules** — `SweepForDirection` takes the newest standing sweep of
  the side the trade feeds on; same-bar multi-pool keeps the deepest extreme
  and the strongest label (`PoolRank`). A sweep older than the setup window is
  no longer evidence. No future candles: pool verdicts are recomputed from
  closed bars only on every evaluation.

## What changed in Phase 4

### 1. Pool de-duplication (`BuildLiquidityMap`) — one level, one identity

The same lever (a prior-day high) can coincide with a swing or an equal-high,
which used to produce two pools at the same price with different pierce
windows and different identities. Pools on the same side within tolerance are
now merged:

- **Group anchor** = the first (oldest-in-creation-order) member of the group.
- **Identity** = the winner by `PoolBetter`: stronger kind wins (week > day >
  equal > swing); on equal rank keep the NEWER formation (`shift == 0`, the
  day/week boundary, counts as the newest); fully equal keeps the first.
- **State is folded, not inherited**: the survivor carries the most **decided**
  state of the group (`ACCEPTED` > `SWEPT` > `SPENT` > `INTACT`) together with
  that member's decisive bar, and the further reach (higher for BSL, lower for
  SSL) always survives. A consumed level can never re-enter the map as INTACT
  just because the twin that got run had the weaker kind.
- **Side-local merge**: the map is stored BSL-block-then-SSL-block; each side is
  merged in its own array and recombined afterwards. (The first implementation
  merged in-place on the combined array with swap-with-last, which pulled SSL
  tail members into BSL positions, changed visit order asymmetrically under
  mirroring, and broke replay symmetry — caught by the symmetry replay, fixed
  in this phase.)
- Journalled once per evaluation when it happens:
  `[QATS][LIQUIDITY] merged N duplicate level(s) within tolerance (one level = one identity)`

**Consequences (honest):** strictly fewer double-booked levels; the nearest-
intact TP candidate set shrinks to distinct levels; a heavily duplicated level
keeps ONE identity whose pierce window is the winner's (a day/week-boundary
survivor has a narrower window than an old swing survivor) — an intentional
trade of window coverage for identity integrity, ERRING ON THE SIDE OF NOT
RE-USING CONSUMED LEVELS. Scoring is unaffected (boolean/nearest, not counts).

### 2. Transition journal — consumed levels are now tracked with bar and level

`JournalLiquidityTransitions` (called from the evaluation once per bar, per
attach):

```
[QATS][LIQUIDITY] TRANSITION side=BSL|SSL kind=<kind> level=<price> state=<OLD>-><NEW> bar=<time> extreme=<price>
```

- One line per pool per state change vs the previous evaluation (INTACT→SWEPT,
  SWEPT→SPENT/ACCEPTED, SPENT→INTACT when a level re-arms after the window
  rolls, etc.). State is rebuilt from closed bars every bar, so a verdict
  change is visible exactly once, when the bar changes it.
- `bar=` is the decisive bar (`eventBar`) in server time; `extreme=` the
  furthest reach beyond the level. A pool APPEARING is not a transition and is
  not journalled. Matching across evaluations is by side + level within
  tolerance.

### 3. TP provenance — `tpSource` and `SAnalysis.tpLevel`

- `tpSource` is now `"LIQUIDITY:<KIND>@<level>"` (e.g. `LIQUIDITY:EQH@212164.00`),
  or `"RR"` for the RR fallback. The journal therefore names both the pool kind
  and the exact level the TP is anchored to.
- `SAnalysis` gains `tpLevel` — the pool's own level (the POOL's price, not the
  spread-shifted `tpPrice` a SELL is anchored to; `0` = RR fallback). Reset in
  `ResetAnalysis` alongside `tpSource`.
- **No** selection rule changed: the target is still the nearest INTACT
  opposing pool paying ≥ `InpMinRR` (market) / `InpLimitMinRR` (limit); SELL
  targets are still level + one spread; TPs are still snapped toward the entry.

## Unit coverage added

`unit.liquidity_dedup` (merge grouping, identity winner, D1-priority,
`PoolBetter` lattice, merge journal line), `unit.liquidity_journal` (silent
baseline, exactly-once transitions, new-appearance silence, state naming),
`unit.liquidity_fold` (INTACT PDH absorbing a SWEPT SWING, ACCEPTED > SWEPT,
SPENT > INTACT, two INTACT stays INTACT, equal-conviction keeps the later
decisive bar, sell-side fold keeps the LOWER extreme, three-way group fold).
Unit suite: **410 checks, 0 failed** (was 348 at Phase 3 close-out).

## Rollback copies

- `MQL5/Experts/rollback/QuantumAutonomousTradingSystem_pre_phase4.mq5` — v1.23 + Phase 2 + Phase 3 (reconstructed; the diff pre_phase4→worktree contains ONLY the Phase 4 hunks).
- `MQL5/Experts/rollback/qats_selftest_pre_phase4.inc` — Phase 3-exit selftest; pairs with the pre_phase4 EA (verified: the pre_phase4 EA builds against it and reports `unit: 348 checks, 0 failed`; the current worktree EA reports `410 checks, 0 failed`).

All were untracked (`MQL5/Experts/rollback/` is gitignored) and their copies are **ephemeral — they do not survive an ephemeral workspace snapshot**. If the directory is missing: v1.23 exact is commit `db025e9` (`git show db025e9:MQL5/Experts/QuantumAutonomousTradingSystem.mq5`); the Phase 2..5 boundaries are uncommitted working-tree state and can only be re-derived from the phase diffs recorded in `QATS_CHANGELOG.md` — durability requires committing the phase work.


## Limitations & open items

- The de-duplication needs the two twins to land within the same tolerance
  band of the tolerance MEASURE (ATR(H1) × `InpLiquidityToleranceATR`); it is
  not a global "same level" normalizer.
- Pool state is rebuilt from scratch every evaluation; the transition journal
  is per-attach (restart re-establishes a silent baseline and misses the very
  first change of a pool that was already in its new state at restart).
- Not compile-verified in MetaEditor (F7), not Strategy-Tester verified, not
  demo-forward tested. Readiness stays **MODIFIED**.
- QATS_VERSION stays `1.23` (the module series labels itself v1.24; see
  `QATS_ADAPTIVE_PD_V124.md`).
