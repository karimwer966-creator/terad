# Phase 5 — Execution / risk / config / diagnostic defects in `QSMC_AutoTrader.mq5`

Status: **source-level complete and green. NOT a completion claim.**
Compilation (F7), Strategy Tester and live-demo tiers are **operator-supplied and
still outstanding** — see §6. Nothing in this document is evidence of either.

- Target: `MQL5/Experts/QSMC_AutoTrader.mq5` (CRLF, 3,264 lines)
- Signal logic touched: **none**. `nadir2.mq5` is byte-identical
  (`dfaf31dc6681214a936e7627d3537255`), and no sweep / displacement / MSS /
  causal-graph / OB / FVG / no-lookahead rule was relaxed.
- Defaults unchanged: `InpEnableTrading=false`, `InpDryRun=true`.
- No martingale, no averaging down, no stop widening was introduced anywhere.

Line numbers below are in the **post-patch** file.

---

## 1. The single theme

The EA could **tell the operator one number and enforce another**. Thirteen
verified defects, and every fix removes a second source of truth rather than
adding a check alongside it.

| # | Location (post-patch) | Defect | Fix |
|---|---|---|---|
| 1 | `CalcLots` L770–790 | `if(step<=0.0 \|\| tick_size<=0.0 \|\| tick_value<=0.0) return fixed_v;` returned a **tradable** volume exactly when the metadata needed to price its risk was missing — fail-open. | Refuses, and names the numbers: `FIXED_LOT_REPORT` prints requested volume, normalised volume, estimated SL loss, account currency, effective risk % and the cap. |
| 2 | `CalcLots` L744–748 | A second, undocumented `if(vmax_cap>1.0) vmax_cap=1.0;` silently overrode both `OnInit` and `HardMaxRiskPercent()`=5.00. A 3% plan was accepted, logged, and sized at 1%. | Literal removed; exactly one ceiling, `if(vmax_cap>HardMaxRiskPercent()) vmax_cap=HardMaxRiskPercent();`. |
| 3 | `CalcLots` L791–799 | `HardMaxRiskPercent()` was never applied on the FIXED path, and `guard_pct<=0` meant **no cap at all** (unbounded). | `if(guard_pct<=0.0 \|\| guard_pct>HardMaxRiskPercent()) guard_pct=HardMaxRiskPercent();` then `cap_money=eq*guard_pct/100.0`. 0 ⇒ HARD, never “off”. |
| 4 | `EstimateLossAtSL` L714 (+ call L778) | Loss estimated by a `tick_value` identity, not measured at the real SL. | `OrderCalcProfit()` at the real SL; unmeasurable ⇒ `if(!measured)` ⇒ refuse. |
| 5 | `OnInit` L2606 | Validated `InpMaxRiskPercent` against a literal `1.0` while enforcing 5.00. | Validates against `HardMaxRiskPercent()`. |
| 6 | `OnInit` banner L3006, 3021–3023 | Printed the HARD cap for a stop the operator had **disabled**. | `EffectiveRiskPercent()` / `EffectiveDailyPercent()` / `EffectiveDDPct()`; 0 ⇒ `DISABLED (0 = off)`. |
| 7 | `DayGuardUpdate` L2333 | `InpMaxDailyLossPercent=0` silently became the 10% HARD cap — a disabled guard enforced as the loosest live guard. | `_effDaily=EffectiveDailyPercent()`; 0 ⇒ OFF. |
| 8 | `SessionGuardUpdate` L1108 | Same for drawdown: 0% silently became the 20% HARD cap. | `EffectiveDDPct()`. |
| 9 | `DayFloorEquity` L986/L999, `DayStopState` L973, `DayStopDescription` L1037 | Cap arithmetic duplicated in four places, free to drift. | All four read the resolvers; `DayStopState()` returns `MONEY` / `PERCENT` / `DISABLED`. |
| 10 | `HandleSignal` ≈L1446 | `g_day_blocked` was tested twice; the second test was unreachable. | Duplicate deleted; the surviving latch says “EA restart required to resume”. |
| 11 | `ProcessSignals` L1684–1688 | An aged-out signal was skipped by a bare `continue` — it disappeared from **every** count, so “signals” and “refused” could not be reconciled. | EXPIRED class, `MarkSeen()`, `g_expired++`, reported at `OnDeinit` L3212 and in the heartbeat L2359. |
| 12 | 17 refusal sites, e.g. L1312–1453 | One flat `skip` stream: a permanent geometry failure was retried forever, and a transient one could be dropped. | `NoteClass(key,msg,REJECT_TRANSIENT\|PERMANENT\|EXPIRED)`; enum L479–481, `RejectClassText` L484. |
| 13 | attach banner L2884, heartbeat L2373 | The log never named **which** `iCustom` instance, timeframe or build/ABI was being read. A stale `nadir2.ex5` answers `CopyBuffer()` happily from an older buffer map. | `IndicatorIdentityLine()` L1718 probes slots 7..12 + VCODE and prints instance, timeframe, symbol, ABI status — at attach and on every heartbeat. |

---

## 2. What the operator now sees that they did not before

- `DAY_STOP_STATE=MONEY|PERCENT|DISABLED` (L1037, L2348–2350) — the heartbeat can
  no longer disagree with the enforcement.
- `FIXED_LOT_REPORT … ACCEPTED|REFUSED` with the same five fields on both paths,
  so an acceptance and a refusal are comparable in the log.
- `INDICATOR_ABI=7..12 PRESENT|INCOMPLETE (probe …)` plus
  `INDICATOR_TIMEFRAME=` / `INDICATOR_SYMBOL=`, at attach and per heartbeat.
- `signals` / `refused` / `dry` / `sent` / `expired` as five separate counters.

---

## 3. Regression suites — all repaired probes are *stricter*, never looser

Standing rule from Phase 4, applied to every probe that pinned a defect: replace
it with a stronger statement of the invariant **plus** an explicit “the old form
must be absent”.

| Suite | Checks | Result |
|---|---|---|
| `tools/test_at_risk_audit.py` (new) | 96 (A–F + **G structural**) | **96 / 0** |
| `tools/test_execution_safety.py` | 105 | 105 / 0 |
| `tools/test_autotrader_contract.py` | 112 | pass |
| `tools/check_release_gate.py` (G8) | — | **GO, 0 warnings** |
| `tools/test_gate_profile.py` | 61 | pass |
| `tools/test_causal_chain_regressions.py` | 84 | pass |
| `tools/check_production_ready.py` | 43 curated | **43/43 GO** |
| `python3 -m py_compile tools/*.py` | — | clean |
| `tools/static_check.py` | — | 0 errors, 5 pre-existing warnings |

Section **G** of the new suite is structural on purpose: it runs an MQL-aware
lexer (strips `//`, `/* */`, strings, char literals), walks brace/paren balance,
asserts depth never goes negative, and requires **exactly one definition** of
each new helper (`EffectiveRiskPercent`, `EffectiveDailyPercent`,
`EffectiveDDPct`, `EstimateLossAtSL`, `DayStopState`, `RejectClassText`,
`NoteClass`, `IndicatorIdentityLine`). A source assertion against a file that
does not parse is worth nothing; a duplicated opening brace introduced during
patching was caught by exactly this walk.

### Probe repairs worth naming

- **The 1.0% ceiling** (`test_autotrader_contract`, `check_release_gate` G8,
  `test_gate_profile`) — asserted the *defect*. Now assert that the sizing path
  is bounded by `HardMaxRiskPercent()`, that `OnInit` validates against the same
  value, **and** that `if(vmax_cap>1.0) vmax_cap=1.0;` is absent.
- **`test_gate_profile`** was red on `main` for an independent reason:
  `EffMinRR1()`/`EffMaxStopATR()` read the **sanitised** `g_cfgMinRR1` /
  `g_cfgMaxStopATR`, not the raw inputs, because that is what the gate compares
  against. The probe now accepts the stronger source and still requires the
  STRICT branch to return it untouched.
- **`test_autotrader_contract`** “daily loss guard” — the refusal now says it is
  a **latch** and names the only way out; the probe matches the new message.
- **`test_execution_safety` D8g** — refusal sites became `NoteClass(...)`, so the
  ordering probe anchors to the message string instead of the call form.
- **`test_contextual fix`**: the companion *names* `InpGateProfile` inside an
  operator message. The probe now inspects **code only** (literals and comments
  stripped) — a mention in a string is not a read.

---

## 4. Known pre-existing red suites (not caused by this work)

`test_resolver`, `test_weighted_gates`, `test_decision_journal`,
`test_declutter_cap`, `test_tactical_authority`, `test_phase5_meanreversion` are
**red on `main` as well**. They pin literal line numbers / brace counts / enum
counts in `nadir2.mq5`, which has grown ~800 lines since; `pinmap.py --check`
reports the same **8 unresolvable pins** on `main`. `nadir2.mq5` is
byte-identical to `main` in this branch, so these cannot be regressions from
this patch. They run in the non-blocking `pin-drift` job, which reports them as
failed **steps** with logs attached while the job itself stays green.

---

## 5. Evidence tiers — kept deliberately separate

| Tier | Status | Basis |
|---|---|---|
| **Source-level** | ✅ done | 96 + 105 + 112 + 61 + 84 assertions, structural lexer/brace walk, 43/43 curated gate |
| **Compilation (MetaEditor F7)** | ❌ **not done** | no MetaEditor/MQL5 compiler in this environment. `static_check` explicitly states it does not prove compilation. |
| **Strategy Tester** | ❌ **not done** | requires the compiled `.ex5` and a tick model. |
| **Live demo** | ❌ **not done** | requires a terminal, a demo account and the `.set` load described in §7. |

No claim of completion rests on the source-level tier alone.

---

## 6. What the operator must do next (the outstanding tiers)

1. **F7 in MetaEditor.** Expect 0 errors. The suite cannot cover
   `OrderCalcProfit()` signature mismatches or `CopyBuffer` overload resolution.
2. **Strategy Tester**, one week, M15, `InpDryRun=true`: confirm
   `INDICATOR_ABI=7..12 PRESENT` in the journal and that
   `DAY_STOP_STATE=DISABLED` matches the inputs actually compiled in.
3. **Demo attach**: verify the five counters reconcile
   (`signals = refused + dry + sent + expired`, with transient retries not
   double-counted), and that a FIXED-mode refusal prints `FIXED_LOT_REPORT …
   REFUSED` with a currency-denominated loss.

---

## 7. Note on the demo preset

`presets/QSMC_AutoTrader_DEMO_0.10_200.set` sets
`InpFixedLotsMaxRiskPercent=6.00`. That is **above** the 5.00 HARD ceiling, so it
now clamps to 5.00 and is reported as such at attach. This is the intended
behaviour of defect #3's fix, not a new refusal: the cap that decides is the
displayed cap. If a wider fixed-lot risk is genuinely wanted, the HARD ceiling in
`HardMaxRiskPercent()` is the one place to change, deliberately.
