# QATS M5 / M1 scalping (`QATS_SCALPING_RESEARCH`) — v1.24 module, Phase 6

**Status:** research verdict delivered. **NO M1 module exists and none was enabled.**
**NOT** compile-verified in MetaEditor, **NOT** backtested, **NOT** demo-forward-tested.
No production claim is made by this document.

Scope: the M5/M1 mandate (master audit §6, Phase 6). Companion to
`QATS_ADAPTIVE_PD_V124.md`, `QATS_LIQUIDITY_V124.md`, `QATS_DISPLACEMENT_FVG_V124.md`.

QATS_VERSION remains `1.23`; the v1.24 tag names the Phase 2–10 upgrade track,
not a released version.

## The contract as it exists (and is now pinned by tests)

**M5 trigger candle** (`M5Trigger`) — M5 *closed* bars 1–2 only (causal, no
look-ahead), three shapes per side (engulfing, pin bar, strong close ≥ 65% of
range), direction-symmetric. Its entire authority:

- **weight 5** of 100 (`QATS_W_M5`), and `M15Confirms` is identical with
  `QATS_W_M15 = 5` — both are *optional confluence* in the score;
- **never** core on BALANCED (default) or ACTIVE;
- on CONSERVATIVE only, the core gate demands `M15 OR M5` (`ltfConfirm`);
  it is an OR — neither is ever a sole gate — and CONSERVATIVE additionally
  requires sweep + displacement + BOS/CHoCH on its own;
- never touches the mandatory risk guards, the PD gate, net-tick fills, or the
  one-setup-once identity; a high score with no trigger is still a high score.

`unit.m5_trigger_authority` (new, 20 checks) pins: the trigger geometry on the
live sim tape (engulfing/pin/marubozu, each in bullish and mirrored bearish
form, plus a neutral tape), the core-gate authority per profile (CONSERVATIVE
refuses without M15/M5 and passes with it; BALANCED passes with neither;
ACTIVE counts sweep+displacement regardless of M5/M15, and a lone sweep stays
refused even with M15/M5 present), and the weight contract (`W_M5 = W_M15 = 5`).

## The M1 verdict — no edge, not implemented, not enabled

The mandate: *M1 trigger module stays opt-in, never overrides HTF protection,
evaluated only behind `InpUseM1Trigger=false` default. Compare M1 vs M5
triggers historically (walk-forward); accept M1 only if out-of-sample evidence
shows an edge — otherwise document "no edge, disabled".*

State of the world:

1. **There is no M1 trigger module in the EA.** No input, no code path, no
   journal field. The nearest in-repo evidence on sub-H1 confluence (the
   recorded 2026-11-11 real-data study, `QATS_BACKTEST_STUDY_2026-11-11.md`)
   already ends in the verdict **"no demonstrated edge"** for the engine as a
   whole — out-of-sample, on real M1-derived bars.
2. **The dataset needed to run the mandated walk-forward is not available in
   this environment.** The study's source is `Dypoi/XAUUSD_Dataset`
   (M1 bid+ask, 2016-09-01 .. 2026-09-01, 10 files, ~470 MB, SHA-256 recorded
   in `tools/qats_backtest.py::DATASET`). It is not committed, not fetchable
   from this sandbox (outbound restricted), and cannot be re-downloaded here.
3. **Synthetic bars cannot produce the mandated evidence.** The offline
   `synthetic_m1` tape exists to prove determinism and mirror symmetry, not
   expectancy. Publishing a synthetic "edge" would be fabricated evidence —
   it is not produced.

**Verdict: M1 stays unimplemented and DISABLED. Nothing about M1 changes
entries by default — or at all. `InpUseM1Trigger` deliberately does NOT exist
yet: an input for a module that does not exist would be dead code (the NC-5
class this codebase removes).** The only way to get an M1 module is the
readiness gate below, and it must start with real data.

## Readiness gate for any future M1 module

An M1 trigger may enter the codebase only when ALL of the following hold:

1. `InpUseM1Trigger=false` by default; opt-in only; if enabled, an explicit
   operator decision is journalled at first use.
2. **Additive-only.** It may add confluence points and (at most) satisfy the
   same OR-shaped slot `ltfConfirm` already occupies in CONSERVATIVE. It may
   NEVER: be required for BALANCED/ACTIVE; override the PD gate, any guard,
   sizing, SL/TP rules, or the setup identity reservation; or act as its own
   core on any profile.
3. **Real-data evidence.** Walk-forward comparison M1 vs M5 on raw M1 bars
   (1s-equivalent fidelity), covering at least one full IS→OOS boundary pair
   (e.g. IS 2017–2023, OOS 2023–2026), per profile, per direction, with both
   the recorded mirror feed. Report: trades, win rate, PF, expectancy in R,
   max DD, and planned R:R.
4. **Acceptance** (pre-registered before the OOS window is looked at):
   M1 must beat the matched M5 baseline out-of-sample — PF ≥ M5's PF and
   expectancy ≥ M5's expectancy + 0.05 R, on ≥ 200 OOS trades, in BOTH
   directions, with max DD no worse than M5's. Otherwise the module is not
   merged (the mandate's "otherwise document 'no edge, disabled'").
5. **Compile & forward test.** MetaEditor F7 + Strategy Tester configuration
   and a demo forward test (Phase 10) before any production claim.

## What would NOT change even if M1 passed the gate

Guards, mandatory protection, the adaptive PD gate, sizing, the one-setup-once
identity, the limit-entry path, and the mirror-symmetry property (an M1 layer
must pass the same origin↔mirror replay with 0 mismatching bars) are untouched
by definition of the gate above.

## Limitations & open items

- No M1-vs-M5 comparison was executed; the mandated walk-forward requires the
  absent dataset. This document is the decision record, not the evidence.
- The M5 trigger itself was not re-evidenced against real data in this phase
  (no dataset); its 2026-11-11 real-data role is unchanged.
- Not compile-verified in MetaEditor (F7), not Strategy-Tester verified, not
  demo-forward tested. Readiness stays **MODIFIED**.
- QATS_VERSION stays `1.23`.
- Phase 5 note that also applies here: `MQL5/Experts/rollback/` is gitignored
  and its untracked copies can vanish with ephemeral workspaces — re-derive or
  commit to preserve them (see `QATS_CHANGELOG.md`).
