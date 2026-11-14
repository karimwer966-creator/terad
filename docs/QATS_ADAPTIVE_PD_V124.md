# QATS Adaptive Premium / Discount (`QATS_PD_ADAPTIVE`) — v1.24 module

**Status:** implemented, offline-verified (host-compiled simulation + unit suite).
**NOT** compile-verified in MetaEditor, **NOT** backtested, **NOT** demo-forward-tested.
No production claim is made by this document.

## What it replaces

`DealingRangePosition()` (one 120-closed-H1-bar highest-high/lowest-low with a
silent `0.5` fallback on data failure) and `LimitPriceInPD()` (an independent
second copy of the same math, consulted only on the limit path). Both are gone;
one engine feeds both the score's `location` weight and BOTH premium/discount
gates, so the protection can never drift.

## The three ranges (H1, closed bars only)

| Range | Window | Extremes | Selection |
|-------|--------|----------|-----------|
| **A** | `InpSwingLookback` (120) closed H1 bars | highest high / lowest low, with their shifts | fallback |
| **B** | `InpPdShortLookback` (48) closed H1 bars | highest high / lowest low, with their shifts | preferred over A |
| **C** | most recent CONFIRMED swing high → most recent CONFIRMED swing low (`FindSwings`, k = `InpSwingK`) | the pair itself, with ages | preferred when valid + fresh |

## Validity rules (any failure rejects the range — loudly)

1. **Incomplete** — the closed H1 history cannot cover the full window → rejected.
2. **Flat** — `high <= low`, or `width < 0.25 x ATR(H1)` → rejected.
3. **Stale extreme dominating** — an extreme older than `InpPdSwingMaxAge` (default
   60 bars) whose distance from price exceeds `InpPdStaleBufferATR` (default 0.5)
   × ATR → the range no longer anchors price → rejected.
   Note: under the defaults B (48 bars) can never be stale by age — it is the
   recent-regime anchor. The rule exists for A and for C.
4. **Swing relevance & freshness (C only)** — the defining swings must exist,
   `swingHigh > swingLow`, width `>= InpPdSwingMinATR` (default 0.5) × ATR, and
   the NEWER of the two defining swings must be no older than `InpPdSwingMaxAge`.

## Selection & hysteresis (deterministic, no unpredictable switching)

- Preference: fresh valid **C** > valid **B** > valid **A**.
- Hysteresis: the previously selected range is kept while it stays valid and its
  equilibrium is within `InpPdHysteresisATR` (default 0.25) × ATR of the preferred
  range's equilibrium. Switching is journalled with the delta; adjacency of bars
  cannot flip the regime.
- **Fail closed:** when NO range is valid the direction is refused on both paths
  with `no valid H1 dealing range (A/B/C all rejected)`. The protection is never
  silently bypassed; `dealPos` reads 0.5 (no location points) and the gate blocks.

## Enforcement

- **Market path** — new input `InpPDEnforceMarket` (default **true**): a hard gate
  in `ProcessSignal`, evaluated on the live quote (ask for BUY / bid for SELL).
  SELL only in premium / at the equilibrium; BUY only in discount / at the
  equilibrium. A blocked setup is journalled as `[QATS][PD] MARKET_BLOCKED ...`
  with the full reason, plus `outcome=BLOCKED reason=PD_MARKET` in the SCORED
  record. Setting the input to `false` is an explicit operator decision and
  removes the gate — it never loosens the limit path.
- **Limit path** — `InpLimitNeedPD` (default true, unchanged): same rule applied
  to the zone entry price via `LimitPriceInPD(analysis, dir, chartEntry, why)`.

## Journal contract (one line per evaluation)

```
[QATS][PD] LONG_EQ=.. SHORT_EQ=.. SWING_EQ=.. SELECTED=A|B|C|NONE POS=0.00..1.00 STATUS=OK | OK (hysteresis: ...) | OK (switch: ...) | REJECTED: ...
```

`POS` is the position of the last closed H1 close inside the SELECTED range
(0 = range low, 1 = range high) and feeds the existing `location` weight (10 pts).
The reason string now reads `P/D=0.62(C)` (SELECTED letter in parentheses).
`PD_MARKET` blocks appear as `outcome=BLOCKED` in SCORED, and
`[QATS][PD] MARKET_BLOCKED direction=.. price=.. reason=..` carries the full text.

## Honest behavioral consequences

In a sustained one-way market, after a break of structure the close of the BOS bar
sits at the top of the recent swing range — premium. Under this mandate, BUYs are
refused until a retest forms (or another range flips SELECTED with a material EQ
move). The offline dual-direction suites freeze `InpPDEnforceMarket=false` (like
`InpDisplaceM15=false`) so the v1.23-frozen scenario expectations keep their
meaning; new scenarios `pd_gate_buy/pd_gate_sell` enforce the gate and assert its
consistency with the journal. The symmetry study (`SIGNAL_STUDY`) likewise freezes
it to measure pure signal symmetry; the production preset ships it **true**.

With enforcement ON, on the synthetic `patternFullChain` market used in the
offline scenarios, the BUY is refused on every candidate bar (50/50) and the
mirror SELL likewise — that is the mandate working, not a bug. Expect genuinely
fewer market entries; entries come on discounts of the selected range.

## Rollback copies

- `MQL5/Experts/rollback/QuantumAutonomousTradingSystem_pre_phase2.mq5` — v1.23 exact.
- `MQL5/Experts/rollback/QuantumAutonomousTradingSystem_pre_phase3.mq5` — v1.23 + Phase 2 (reconstructed by replaying the Phase 2 edit set; the diff pre_phase3→worktree contains ONLY the Phase 3 hunks).
- `MQL5/Experts/rollback/QuantumAutonomousTradingSystem_pre_phase4.mq5` — v1.23 + Phase 2 + Phase 3 (reconstructed by replaying the Phase 4 edit set; the diff pre_phase4→worktree contains ONLY the Phase 4 hunks).
- `MQL5/Experts/rollback/qats_selftest_pre_phase4.inc` — Phase 3-exit selftest (pairs with the pre_phase4 EA; verified: the pre_phase4 EA builds against it).
- `MQL5/Experts/rollback/QuantumAutonomousTradingSystem_pre_phase5.mq5` — v1.23 + Phase 2 + Phase 3 + Phase 4 (reconstructed; the diff pre_phase5→worktree contains ONLY the Phase 5 hunks).
- `MQL5/Experts/rollback/qats_selftest_pre_phase5.inc` — Phase 4-exit selftest (verified: the pre_phase5 EA builds against it and reports `unit: 410 checks, 0 failed`).
- `MQL5/Experts/rollback/qats_scenarios_pre_phase5.inc` — Phase 4-exit scenarios (pairs with the above).

All were untracked (`MQL5/Experts/rollback/` is gitignored) and their copies are **ephemeral — they do not survive an ephemeral workspace snapshot**. If the directory is missing: v1.23 exact is commit `db025e9` (`git show db025e9:MQL5/Experts/QuantumAutonomousTradingSystem.mq5`); the Phase 2..5 boundaries are uncommitted working-tree state and can only be re-derived from the phase diffs recorded in `QATS_CHANGELOG.md` — durability requires committing the phase work.


## Known limitations

- No MetaEditor F7 compile has been run here. The host C++ transpile build
  (`tools/qats_native.py`) compiles and passes 348 unit checks + 57 scenarios.
- A sustained one-way tape rejects range A (ancient, distant low) → B/C govern;
  if the newest confirmed swing is also stale (> `InpPdSwingMaxAge`), ALL ranges
  reject and the EA stands aside entirely (fail closed) until a new confirmed
  swing forms. Set `InpPdSwingMaxAge=0` to disable age checks explicitly (journal
  still reports it).
- `g_pdLastSelected` hysteresis state is per attach (not persisted across
  restarts); the first bar after attach selects by preference and journals it.
- PD engine runs on the H1 clock only; M15/M5 do not get their own ranges
  (by design; the mandate scopes ranges to H1).
- The gate adds one `iBars` + a handful of series reads per evaluation
  (included in the Phase 15 memoization plan, NC-2).
