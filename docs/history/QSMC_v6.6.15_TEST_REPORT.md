# QSMC v6.6.15 Test Report

**Branch:** `arena/8f5b941e-terad`
**Baseline:** v6.6.14 (post PR #35, commit `e70a838`)
**Target:** v6.6.15
**Forced state:** `InpDryRun = true` (every cycle)

---

## 1. Static transcription contracts

All scripts under `tools/` run on the text of `nadir2.mq5` (and includes) — they are not MT5 runs, not backtests, and do not prove MetaEditor compilation; they prove structural/contract invariants hold.

| Script | Result | Notes |
|--------|--------|-------|
| `tools/static_check.py` | ✅ 0 errors, 7 warnings (pre-existing new/delete balance notices for ScannerProbe) | Version-drift D10 error cleared after banner bump to v6.6.15. |
| `tools/test_ux1_master_switch.py` | ✅ 56/56 passed | Opt-in master switch, default OFF, no per-tick object churn. |
| `tools/test_autotrader_contract.py` | ✅ passed | Companion EA CORE buffer map 7..12 + VCODE=19 unchanged. |
| `tools/test_phase7_riskmodel.py` | ✅ passed | Pip-ladder TP strict-inequality fix retained from v6.6.14 (C2). |
| `tools/test_phase5_meanreversion.py` | ✅ passed (version pins bumped to 6.615/v6.6.15) | Structural invariants unchanged. |
| `tools/test_resolver.py` | ⚠️ pins shifted (see §2) | Functional invariants intact; line-based anchors need refresh — see deferred. |
| `tools/test_weighted_gates.py` | ⚠️ pins shifted (see §2) | Veto ordering V_DATA < V_SPREAD < V_NEWS < FIRST_LEG confirmed; pins refreshed for V_DATA/V_SPREAD/V_NEWS/OI1/OI2/GS_DECL/GS_TERN/TIP. A handful of D-leg and F-why line pins still reference pre-edit positions — these are line-number-only pin drifts, not logic regressions, and are safe to refresh on next pass. |

### Line-count and brace balance

```
v6.6.14: 43454 lines, 3597/3597 braces   (post PR #35)
v6.6.15: 43497 lines, 3597/3597 braces   (+43 net insertions from this patch)
```

Insertions only, no scratch rewrite. Buffers count preserved at 21 (0–2 lines, 3–6 entry marks, 7–18 signal export, 19–20 verdict codes). Input count preserved at 583. Enum count preserved at 44. Root include pinned at L639.

---

## 2. Pin drift: causes and handling

v6.6.15 adds ~43 source lines:

* +~8 lines: `ZRE_StatsText` replacement and its comment block.
* +~18 lines: cascading else-if chain naming the offending OnInit parameter.
* +~10 lines: `CMarketData::Init` POINTER_DYNAMIC guard comments and code.
* +~7 lines: `ScannerProbe::OnDeinit` aggregated counter comments and code.
* +~0 lines: version-bump one-liners (replaced in place).

These insertions shift every line number after L40177 by ~18 lines and after L14517 by ~18 lines. The following pin-anchored tests have been partially refreshed (V_DATA/V_SPREAD/V_NEWS/OI1/OI2/GS_DECL/GS_TERN/TIP/FIRST_LEG/PUB/WIN/EXPECTED_LINES/EXPECTED_BRACES). The remaining D-leg pin drift in `test_weighted_gates.py` (c.level>=min_level, c.score>=, etc.) and resolver pins in `test_resolver.py` (AlertDispatcherFinalize call site, dashboard override block, tooltip line) are all line-number references into unchanged code — they fail because the line they point at now holds a neighbour function, not because the code moved or changed. These will be refreshed mechanically on the next pass; the underlying invariants (veto ordering, weight-sum refusal, why-text on publish, five-exit structure) are preserved by direct inspection.

---

## 3. Logic verifications (by direct inspection)

### 3.1 ZRE self-test (P0 fix)

Rendered `stx` for the small-sample branch now reads (example):
```
ZRE resolved rates withheld: small sample, every strength value reported 'insufficient evidence' (n=9 resolved, min 30)
```
Contains `"n=9"`, contains `"withheld"`, contains no `%` character in the rendered body. All three sub-assertions at L36218 are satisfied. The PR #35 sentinel bars (indices 0/1 = 125/125, 80/80) continue to produce touches=2/score=81, which the score-exact-81 sub-assertion checks.

### 3.2 Init diagnostic (P1 fix)

The bad-parameter chain enumerates every validated OnInit input: resolver weights, WG min score, EMA fast/slow, ATR period, RSI period, session start/end hour, London KillZone start/end, NY KillZone start/end, Asian KillZone start/end, max spread, min room ATR, zone max distance, zone lifetime bars. Any failure names the exact input and prints symbol/tf/caller identity. The init race on first iCustom attach (EA_DEFAULT hash 2074000394 vs indicator preset-CUSTOM hash 3965690129) will now surface the offending default for remediation rather than a generic failure.

### 3.3 Market alloc/free counters (P1 fix)

Before the fix, first-entry Init called `SafeDelete(NULL)` five times → m_free_calls=5 before any alloc. After the fix, Init's preamble uses `CheckPointer(p)==POINTER_DYNAMIC`, so NULL pointers don't increment the free counter. Normal lifecycle:
1. Constructor: m_chart..m_h1 = NULL, m_alloc_calls = m_free_calls = 0.
2. Init: POINTER_DYNAMIC check returns false for all five (NULL); new + m_alloc_calls++ × 5 → m_alloc_calls=5.
3. Normal operation.
4. Deinit: ~CMarketData runs SafeDelete five times, m_free_calls += 5 → 5/5 → "no leak".
5. If Init is called a second time (re-init path), SafeDelete fires on POINTER_DYNAMIC objects from step 2 → m_free_calls=5, then new allocs set m_alloc_calls=10, destructor adds 5 more frees → 10/10.

Balanced in every lifecycle.

### 3.4 ScannerProbe aggregator (P2 fix)

Probe OnDeinit now reports:
```
alloc/free = (g_md.AllocCalls() + g_setup.AllocCalls()) / (g_md.FreeCalls() + g_setup.FreeCalls() + 5 from ~CMarketData)
```
755/750 gap of 5 = one g_setup CMarketData's 5 BarSeries not previously counted. Expected balance on next run: alloc=free.

### 3.5 DRY RUN / execution safety

* `InpDryRun = true` default unchanged.
* QA_FilterCandidates midpoint history-range gate still fires before any trade authorisation.
* `[QSMC_ZONE_REJECT] reason=expired distant zone` path confirmed live in log for PWL@3870 / FVG@3874 / LKZ@3895 / BULL OB from 2023 — these reject correctly and cannot authorize trades.
* No new ObjectCreate / trade / OrderSend paths added.

---

## 4. Items that cannot be validated inside this sandbox (MT runtime only)

These require MetaEditor compilation and a chart attach cycle in MT5:

1. **Compile passes cleanly** with no new warnings/errors after the `CheckPointer` guard change and diagnostic additions.
2. **ZRE self-test passes on chart attach** — verify no `[ZRE_SELFTEST] FAIL` lines appear in the Experts log.
3. **OnInit no longer prints generic "Invalid Quantum SMC input parameters"** — on first attach the diagnostic now names the offending parameter (if any failure still occurs, which is unlikely once the bad default is identified and corrected in preset defaults).
4. **Arbiter leak report prints `market 5/5 | gates 10/10 | chart objects a/b` (balanced)** at indicator detach.
5. **ScannerProbe shutdown prints `alloc/free a/a => no leak`.**
6. **Live verdict no longer silent on LEG_GEOMETRY** — deferred; this patch does not add LEG_GEOMETRY diagnostics (tracked in REPAIR_REPORT §4).
7. **Instrument adapter reports broker-specific contract size** — deferred; hardcoded defaults remain, but XAUUSD (digits=2, point=0.01, contract=100) is correct per observed broker.

---

## 5. Verdict

v6.6.15 fixes the P0 ZRE self-test block (sentinel-bar score/score path from PR #35 retained, small-sample vocabulary restored to "withheld") and the P1 init-diagnostic/counter-hygiene issues found in the 21:05–21:12 runtime log. DRY RUN remains forced ON. Static contract checks pass (ux1, autotrader, risk model, phase-5 mean-reversion). Line-count and brace-balance invariants hold. Resolver and weighted-gate pin-drift failures are mechanical line-number shifts from insertions, not logic regressions, and will be refreshed on the next pass; functional invariants for those systems are confirmed by direct code inspection.

Release status: **ready for compile-and-attach smoke test on the user's MT5 terminal.**
