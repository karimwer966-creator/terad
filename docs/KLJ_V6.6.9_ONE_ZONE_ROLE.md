# QSMC v6.6.9 — one causal zone role (BUY/SELL direction fix)

Status: **one defect, four faces, fixed at the root.** No threshold was lowered,
no gate was disabled, and no gate was given less authority.

The report was: *"there are still problems with the BUY and SELL signals."*
This file records what was actually wrong, how it was reproduced without
MetaTrader, what changed, and what was **not** verified.

---

## 1. The defect in one sentence

The engine kept **two different definitions of "is this level support or
resistance right now?"** — one for the signal path, one for the arbiter
registry — and after a level broke they pointed in opposite directions.

| reader | fact used | file:line (before the fix) |
| --- | --- | --- |
| signal path (`ZRE_EffectiveSide`) | the break must happen **on the bar under test** (`ZRE_IsBrokenNow`) | `nadir2.mq5:31823-31832` |
| arbiter registry (`EffectiveRole`) | **any earlier closed bar** inside the lookback broke it (`flipped`) | `MQL5/Include/QSMC/QSMC_Zones.mqh:69` |
| chart/alert direction (`ZRE_AlertState`) | the sticky `flipped` flag | `nadir2.mq5:33151-33159` |
| independent reference (`tools/test_arbiter.py`) | the sticky `flipped` flag (`Zone.role`) | `tools/test_arbiter.py:113-122` |

Three readers agreed; the one that publishes the signal did not.

## 2. Defect table

| # | file:line | class | wrong behaviour | evidence | fix | test |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `nadir2.mq5:31823` (`ZRE_EffectiveSide`) + call at `:33434` | 1 (inverted direction) | after a break, the retest was traded with the **birth** role: a broken support still asked for a BUY at support instead of a SELL at the resistance it now is (and the mirror) | `ZRE_IsBrokenNow` needs `prev_close`/`close` to straddle the edge **on this bar**; `ZRE_IsFlipped` scans `[closed-lookback .. closed-1]`; the registry publishes the second fact (`QSMC_Zones.mqh:69`), the signal used the first | the flip fact is read **before** the side and both facts feed one resolver (`ZRE_EffectiveSide(...,flipped_closed)`) | `tools/test_zre_signal_role.py` R2 SELL/BUY; `test_arbiter.py` T11a/T11b |
| 2 | `nadir2.mq5:33458-33461` (and the same test at `:33505-33507`) | 1 + 6 (panel contradicts state) | `ZRE_ST_FLIPPED` could never be assigned: the condition required `zeff.side!=z.side` (which is only true when `ZRE_IsBrokenNow` fired) **and** `!ZRE_IsBrokenNow` at the same time. Dead branch, dead state name, dead `GetSignalDirection` FLIPPED arm — while the enum comment says *"broken on an EARLIER closed bar … traded with the OPPOSITE role"* (`nadir2.mq5:3722-3723`) | the two conditions are mutually exclusive by construction | after #1 the condition is satisfiable again; no change to the assignment itself | `tools/test_zre_signal_role.py` R4 (`state=7`) |
| 3 | `nadir2.mq5:33151-33159` (`ZRE_AlertState`) | 6 (panel contradicts state) | the alert/dashboard arrow derived its own direction from `flipped`, so on the break bar it pointed with the **birth** role while the published signal (buffers 7–12, signal log, verdict) already used the reversed one: a BUY arrow over a SELL signal | duplicated formula, no shared resolver | the alert now calls `ZRE_EffectiveSide(...)` through `ZRE_ZoneFlippedClosed(id)` | `tools/test_zre_signal_role.py` R5 + source check |
| 4 | `nadir2.mq5:36968` (`RXN_EvalZone`) | 1 | the reaction layer resolved the role with the same bar-only test, so its candidates carried the birth role too | same call site, no flip fact passed | it now passes `ZRE_ZoneFlippedClosed(z.id)`. Recovered RXN zones (`g_rxn_extra_zones`) are not in `g_zre_status`, so they still resolve the birth role — see §6 | `test_arbiter.py` T11 (gate level), source transcription |

**Not a defect, checked and cleared:** the two mirrored halves of
`ZRE_EvalRejection`, `ZRE_ComputeEntrySL`, `ZRE_StrictOrder`,
`ZRE_FinalizeGeometry` (RR uses `MathAbs`, order is enforced before it), the
stop zone (`stop_lo/stop_hi` are an exact reflection), `ZRE_ScoreSignal`
(`loc = buy ? close_loc : 1-close_loc`), the BUY/SELL `bias`/`state` points,
`AlertBaseKey` (direction is part of the key, so BUY and SELL do not suppress
each other), `SigLog_BufRegister`/`SigLog_FindBar` (12 buffers are
`ArraySetAsSeries(...,false)` and `g_buf_t` is chronological, so the index
matches the signal bar), and the `<=` / `<` comparisons in `QSMC_Gates.mqh`
(location, bias, room, volatility, cooldown, flip-flop, distance, session).

## 3. What changed

* `ZRE_EffectiveSide(z, close, prev_close, atr, p, flipped_closed)` — one
  resolver, two closed-bar facts, no reader may re-derive it.
* `ZRE_ProcessClosedBar()` reads `ZRE_IsFlipped(...)` **before** the side and
  reuses that single value for `st.flipped`.
* `ZRE_ZoneFlippedClosed(zone_id)` — the registry's own flip fact, looked up by
  id, used by `ZRE_AlertState()` and `RXN_EvalZone()`.
* Self-tests: `ZRE_SelfTest` gained the earlier-break expectations and
  `QSMC_Selftest.mqh` gained `T15_OneZoneRole()` (registry role + LOCATION gate
  refusal of the birth-role direction). `tools/test_arbiter.py` gained T11.

Nothing else was touched: no input, no default, no threshold, no gate order, no
gate verdict, no trade API.

## 4. Cost of the change (be honest)

A level that broke and is retested now produces signals **in the new role**. Two
consequences the operator will see:

1. Some BUY arrows that used to appear at a broken support are **gone** (they
   were buys into the level's underside).
2. Some SELL arrows that used to appear at a broken resistance are **gone**, and
   the mirrored retest trade appears instead.

That is the point of the fix, but it does change what the chart shows. Re-run
any observation window you rely on.

## 5. How to reproduce and verify offline

```bash
python3 tools/test_zre_signal_role.py     # the role/direction contract
python3 tools/test_arbiter.py             # R1-R7 independent implementation
python3 tools/mql5_rules.py --quiet
python3 tools/static_check.py
python3 tools/check_release_gate.py       # GO
```

## 6. What was NOT verified

* **Nothing was compiled.** There is no MetaEditor here; F7 remains the final
  judgement. Every check above is static analysis plus re-implementation.
* Nothing ran on a live chart, on a real symbol, or on history of your broker.
* RXN **recovered** zones (`g_rxn_extra_zones`, levels ZRE dropped for drawing
  reasons) have no `g_zre_status` entry, so they still resolve the birth role
  (defect #4 is fixed only for zones the registry knows). Left as-is: giving
  them a status row changes the RXN funnel and needs its own test.
* The "nearest opposing zone" obstacle used by the score (`nadir2.mq5` in
  `ZRE_TryBuildSignal`) compares the *traded* side against the **birth** side of
  every other zone. After this fix those two can differ, so `room` (10 points of
  the score) can be slightly conservative. Score only — it cannot flip a
  direction.
* No claim about profitability, win rate, or the quality of any of these
  signals. The score is evidence strength, not probability.
