# The five risk inputs that size the order

`MQL5/Experts/QSMC_AutoTrader.mq5` has 71 inputs. Five of them decide **how big the
position is** or **whether a class of signal may trade at all**, and until v6.6.25
none of the five appeared in any document in this repository.

Every statement below was read out of the shipped source. Line numbers are for
`MQL5/Experts/QSMC_AutoTrader.mq5` at v6.6.25. Nothing here is a recommendation
about what the values *should* be; the safe ranges are the ranges the code itself
enforces.

> **Status: source-contract ready. No F7 compile and no Strategy Tester evidence
> exists for this file. Do not read this document as validation.**

---

## 1. The sizing chain, end to end

```
CalcLots(sym, entry, sl, buy, cls)                       L1440
  ├─ class_mult = RiskMultiplierForClass(cls)            L1447
  │     └─ <= 0.0  -> REFUSE, return 0.0                 L1448-1453
  │        > 1.0   -> clamped to 1.0                     L1454
  ├─ vmax_cap  (profile ceiling, see §2)                 L1471-1487
  ├─ pct = REAL ? vmax_cap : min(InpRiskPercent, vmax_cap)   L1567
  ├─ pct = min(pct * class_mult, HardMaxRiskPercent())   L1571   <-- multiplier applied HERE
  ├─ risk_money = equity * pct / 100                     L1574
  ├─ loss_per_lot via OrderCalcProfit()                  L1589
  │     └─ cannot price the stop -> REFUSE, no order     L1590-1594
  └─ lots = risk_money / loss_per_lot, normalized
```

Two hard ceilings bound everything and are **not inputs**:

| constant | value | line |
|---|---|---|
| `HardMaxRiskPercent()` | **0.50 %** of equity per trade | `:1310` |
| `HardMaxAggregateRiskPercent()` | **2.00 %** of equity across all open EA positions | `:1138` |

No input, preset or profile can widen either one. `:1462-1466` records that a
second undocumented 1.0 % clamp used to sit here and was removed on purpose —
there is now exactly one per-trade ceiling.

---

## 2. `InpMaxAggregateRiskPercent`

| | |
|---|---|
| Declared | `:326` |
| Type / default | `double` = **1.00** |
| Units | percent of account **equity** |
| Read by | `EffectiveAggregateRiskPct()` `:1140` |
| Enforced at | `HandleSignal()` `:2859-2877` |

**Meaning.** The per-trade cap bounds *one* position. This bounds the *book* —
the sum of the risk of every open position this EA owns, measured to its
server-side stop.

**Exact behaviour** (`:1140-1146`):

```
v = RealProfileActive() ? InpRealMaxAggregateRiskPercent : InpMaxAggregateRiskPercent
if (v <= 0.0)                      return 0.0     // 0 = OFF, the check is skipped entirely
if (v > 2.00)                      v = 2.00       // HardMaxAggregateRiskPercent()
```

So this input **only applies on the DEMO profile**. On a REAL account
(detected *and* authorized — `RealProfileActive()`, `:1131`) the EA reads
`InpRealMaxAggregateRiskPercent` instead (`:321`, default **0.50**).

**Enforcement** (`:2859-2877`), in order:

1. `open_risk = OpenRiskMoney()`. If it returns `< 0`, an EA position is open
   **without** a server-side stop, and *all* new entries are blocked until it is
   protected.
2. `new_risk = risk_money / equity * 100` for the candidate trade.
3. `used = open_risk / equity * 100` for the book.
4. If `used + new_risk > agg_cap` → refuse, with a journal line naming both
   halves: `aggregate open risk would become X% of equity (book Y% + this trade
   Z%) > cap C% - refusing`.

The refusal is **transient**: the signal is not marked seen, so it is
reconsidered once an open position closes and the book fits again.

**Safe range.** `0` (off) to `2.00`. Values above 2.00 are silently clamped to
2.00 — there is no error and no warning, only the attach banner at `:4974`
printing the effective value. **This input is not validated in `OnInit()`**; a
negative value is not rejected, it just evaluates to "OFF".

---

## 3. `InpRequireProfileMatch`

| | |
|---|---|
| Declared | `:433` |
| Type / default | `bool` = **true** |
| Read by | `ProcessSignals()` `:3429` → `ClassAllowed()` `:2155` |

**Meaning.** The indicator publishes a class per signal in **buffer 22**
(`QSMC_BUF_CORE_CLASS`). `InpSignalExecutionProfile` (`:431`, default
`SIGNAL_PROFILE_PERMISSIVE`) is a second, independent ceiling on which classes
this EA will execute. `InpRequireProfileMatch=true` turns that ceiling on.

```
:3429   if(InpRequireProfileMatch && !ClassAllowed(s.cls, class_why))  -> refuse
```

`ClassAllowed()` (`:2155-2175`) can **only narrow**. The comment at `:2152-2154` is
explicit: *"The indicator's own profile already rejected anything it did not
allow; this is the second, independent ceiling. It can only narrow."* It never re-decides a class.

Profiles (`:199-201`):

| value | allows |
|---|---|
| `SIGNAL_PROFILE_STRICT` = 0 | STRONG only |
| `SIGNAL_PROFILE_BALANCED` = 1 | MODERATE + STRONG |
| `SIGNAL_PROFILE_PERMISSIVE` = 2 | WEAK + MODERATE + STRONG (`InpAllowWeakSignals` still required) |

`WEAK_VALID` additionally needs `InpAllowWeakSignals=true` (`:2160`, default
`false`), so the shipped default is: PERMISSIVE profile, but WEAK still refused
by its own switch.

**Setting it to `false` removes the EA-side ceiling entirely** — the EA then
executes whatever class the indicator published, sized by §4. That is the one
setting of this input that widens behaviour. It does not change lot size.

**Not validated in `OnInit()`** (it is a `bool`; there is nothing to range-check).

---

## 4. `InpWeakRiskMultiplier`, `InpModerateRiskMultiplier`, `InpStrongRiskMultiplier`

| Input | Line | Default | Class it applies to | Buffer-22 value |
|---|---|---|---|---|
| `InpWeakRiskMultiplier` | `:434` | **0.25** | `QSMC_CLASS_WEAK_VALID` | 1 |
| `InpModerateRiskMultiplier` | `:435` | **0.50** | `QSMC_CLASS_MODERATE_VALID` | 2 |
| `InpStrongRiskMultiplier` | `:436` | **1.00** | `QSMC_CLASS_STRONG_VALID` | 3 |

All three are read in exactly one place, `RiskMultiplierForClass()` (`:2144`):

```
WEAK_VALID     -> InpWeakRiskMultiplier
MODERATE_VALID -> InpModerateRiskMultiplier
STRONG_VALID   -> InpStrongRiskMultiplier
anything else  -> 0.0        // NONE, REJECTED, INVALIDATED, EXPIRED
```

**Units.** A pure multiplier on the effective per-trade risk percent. Not a
percent, not a lot count.

**Effect on lot size.** With the shipped `InpRiskPercent = 0.10` (`:330`) on the
DEMO profile:

| class | multiplier | `pct` after `min(pct*mult, 0.50)` | risk on a 10 000 account |
|---|---|---|---|
| STRONG | 1.00 | 0.10 % | 10.00 |
| MODERATE | 0.50 | 0.05 % | 5.00 |
| WEAK | 0.25 | 0.025 % | 2.50 |
| anything else | 0.00 | — | **no order** |

The multiplier is applied to the **cap before any volume is derived**
(`:1443-1446`: *"a weak signal can never be sized off the full base risk even for
one intermediate calculation"*), and the hard ceiling is re-applied **after**
scaling (`:1569-1571`), so a multiplier can never be used to climb above 0.50 %.

**A value above 1.0 does not increase risk.** Both `CalcLots()` (`:1454`) and
`ScaledRiskPercent()` (`:2185`) clamp `m > 1.0` down to `1.0`. The only effect of
setting `InpWeakRiskMultiplier = 5.0` is that WEAK trades at the same size as
STRONG.

**A value of 0 or below means "do not execute this class".**
`CalcLots()` `:1448-1453` returns `0.0` and prints
`[QSMC_AT SIZING] REFUSED: class <name> has no risk multiplier - a
non-executable class never reaches sizing`. The comment at `:2143` is the
design rule: *"0 = do not execute (never 'size it small')."*

**Safe range.** `0.00` to `1.00`. Anything above 1.00 is clamped; anything at or
below 0.00 disables that class. **None of the three is validated in
`OnInit()`** — an out-of-range value is corrected silently at sizing time rather
than rejected at attach.

`ScaledRiskPercent()` (`:2179`) recomputes the same number for the journal and
the entry-review line, so what the log prints and what the order uses come from
one formula.

---

## 5. What is enforced at attach, and what is still only clamped at use

Verified by searching `OnInit()` (`:4490-5232`) for each name. Four of the five
were **clamped at use only** until v6.6.25, which was safe but silent: an
operator who typed `InpWeakRiskMultiplier = 3` got WEAK sized as STRONG and saw
no error at attach — only a `risk_mult=1.00` in the per-signal line (`:2277`,
`:2541`). That is now refused at attach instead, at `:4548-4582`.

| Input | Accepted at attach | What the enforcement does |
|---|---|---|
| `InpWeakRiskMultiplier` | `0.00` … `1.00` | `CalcLots()` caps a class multiplier at `1.0`; `0.00` means that class is not executed |
| `InpModerateRiskMultiplier` | `0.00` … `1.00` | same cap, same meaning for `0.00` |
| `InpStrongRiskMultiplier` | `0.00` … `1.00` | same cap, same meaning for `0.00` |
| `InpMaxAggregateRiskPercent` | `0.00` … `HardMaxAggregateRiskPercent()` | `EffectiveAggregateRiskPct()` caps at the same bound; `0.00` switches the cap OFF |
| `InpRequireProfileMatch` | any value — it is a `bool` | no range exists to fail; `ClassAllowed()` reads it directly |

The bounds the attach accepts are **the same numbers the enforcement applies** —
`1.0` for a class multiplier, `HardMaxAggregateRiskPercent()` for the aggregate
cap. That is deliberate: a validation that invented its own bound would be worse
than none, because "accepted at attach" and "clamped at use" would then disagree
in a way the operator could not predict. Nothing about a size changed — every
value the check accepts is sized exactly as it was sized before. What changed is
that a value the enforcement would have silently rewritten now refuses the attach
with `INIT_PARAMETERS_INCORRECT` and prints all four numbers it was given.

Contrast `InpRiskPercent` / `InpMaxRiskPercent`, which were always rejected at
attach (`:4506-4512`), and `InpSessionStartHour` / `InpSessionEndHour`, added at
`:4523-4540`. **All ten shipped presets load under the new check**: the four that
set these inputs use `0.25 / 0.50 / 1.00` and an aggregate cap of `1.00` or
`0.50`, so nothing that worked before now refuses.

Still deliberately *not* checked at attach, and still clamped at use:

- `InpRealMaxRiskPercent` (`:318`) and `InpRealMaxAggregateRiskPercent` (`:321`)
  — the REAL profile's counterparts have **zero** occurrences inside `OnInit()`,
  so they carry exactly the silent-clamp behaviour the four above just lost.
  `CalcLots()` bounds the first with `MathMin(InpRealMaxRiskPercent,
  HardMaxRiskPercent())` and `EffectiveAggregateRiskPct()` bounds the second.
  REAL is the higher-stakes profile, so this is the next one to close; it was
  left alone here because widening the check to the REAL inputs changes which
  presets load on a live account, and that needs its own go-ahead.

---

## 6. Cross-references

- Buffer 22 and the rest of the indicator→EA contract: [`BUFFER_CONTRACT.md`](BUFFER_CONTRACT.md)
- The demo trial these defaults ship with: [`DEMO_TRIAL_RUNBOOK.md`](DEMO_TRIAL_RUNBOOK.md)
- Execution-profile behaviour contracts: `tools/test_signal_execution_profiles.py`
- Send-path safety contracts: `tools/test_execution_safety.py` (D9 unified
  DEMO/REAL, D11 buffer garbage can never become an order)
