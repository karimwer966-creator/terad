# QSMC v6.6.13 — seven strategy modules, operator guide & audit record

Status: **seven phases landed, all display-only, all OFF by default, zero new
buffers, zero deletions of working code.**

**F7 has now been run** — see §11.1. The first compile reported **42 errors, 0
warnings**, all traceable to a **single missing `//`** on one comment line, and
that is fixed. No MetaEditor exists in this environment, so every statement here
about compilation is a report of *your* F7 output, never a claim of my own.

Branch: `arena/643314e5-terad`, forked from `main` @ `e3c0b5b`. Pull request **#15**.

Every fact below was re-derived from the file at commit `ebc43bc`, not carried
forward from a plan. Line numbers are exact as of that commit and will drift if
the file changes.

---

## 1. What was added, in one table

| # | Module | Audit ID | Commit(s) | `nadir2.mq5` | Master switch | Default |
|---|---|---|---|---|---|---|
| 1 | Order Block lifecycle completion | `AUDIT-OB1` | `6224cdd` `a64f73b` | +153 / −1 | *(three opt-ins; the OB engine already ran)* | `false` |
| 2 | Power of 3 (A/M/D) + Silver Bullet | `AUDIT-SB1` | `9f8451c` `b9f3450` | +741 / −0 | `InpEnablePowerOf3` · `InpEnableSilverBullet` | `false` |
| 3 | Wyckoff Spring / Upthrust | `AUDIT-WY1` | `0906d8e` `877e1ee` | +543 / −0 | `InpEnableWyckoff` | `false` |
| 4 | Pure Price Action (unified) | `AUDIT-PA1` | `a16663a` | +523 / −0 | `InpEnablePriceAction` | `false` |
| 5 | Mean Reversion / Momentum | `AUDIT-MR1` | `b238dd7` `daed151` | +726 / −0 | `InpEnableMeanReversion` | `false` |
| 6 | Confluence Engine | `AUDIT-CF1` | `e176588` | +603 / −0 | `InpEnableConfluence` | `false` |
| 7 | Risk Model (advisory text) | `AUDIT-RM1` | `ebc43bc` | +694 / −0 | `InpEnableRiskModel` | `false` |
| | **Total** | | **11 commits** | **+3 983 / −1** | **67 new inputs** | |

The single deleted line in the whole pull request is Phase 1's order-block
geometry line, replaced by the opt-in body/wick rule (§8, C0).

This was verified PR-wide, not just for `nadir2.mq5`: a multiset comparison of
every one of the **10 changed files** between `e3c0b5b` and `f3309cb` shows
**exactly 1 real line lost in total**. The seven new `tools/` suites, this
document and the workflow are pure additions (+5 980 lines, −0). So the
"nothing that works was deleted" claim holds for the whole pull request, not
merely for the indicator.

> **On the diffstat.** `git diff e3c0b5b..ebc43bc -- nadir2.mq5` reports
> **+4 155 / −173**, which is misleading. A multiset comparison of the two file
> versions proves **exactly one** original line is absent. The other 172
> "deletions" are a diff-realignment artifact: inserted code resembles the
> existing object-management helpers, so the algorithm matched the new block
> against the old one and reported the old block as deleted. Corroboration: line
> count `40 848 → 44 830` = **+3 982** = 3 983 − 1, and the per-commit
> `--numstat` sum is **+3 983 / −1**. Use that figure.

---

## 2. Activation guide — read this before flipping any switch

### 2.1 The dependency chain

The seven modules are not independent. Two edges matter:

```
InpEnablePriceAction ──┐
                       ├──> InpEnableConfluence ──> InpEnableRiskModel
(the other four)  ─────┘
```

- **The Confluence Engine's candle leg (weight 15) reads Price Action.** Its
  guard is `InpEnablePriceAction && g_pa_pattern!="NONE"`. With Price Action
  off, that pillar is reported as **absent and scores 0** — which is correct
  behaviour (missing evidence is never a free point), but it means the highest
  score the engine can reach is **85**, not 100. Since `InpCFMinDisplayScore`
  defaults to 60, the engine can still name a side; it simply can never reach
  the top of its range. **Turn Price Action on before you judge the Confluence
  Engine's calibration.**
- **The Risk Model attaches to the Confluence verdict**, never to a raw signal.
  With `InpEnableConfluence` off, `g_cf_dir` is 0 and the Risk Model publishes
  `WAIT` on every bar. That is deliberate: it refuses to invent a direction.
  **The Risk Model is useless without the Confluence Engine.**

The five strategy modules (P3, SB, WY, PA, MR) feed the Confluence Engine's
"best active strategy" picker and, optionally, its
`InpCFRequireActiveStrategy` gate — but none of them is *required* for the
engine to run. They are independent of each other.

### 2.2 Recommended bring-up order

One at a time, confirming each in the dashboard **tooltip** before adding the
next. Nothing here touches the 11-row card.

| Step | Turn on | What should appear in the tooltip |
|---|---|---|
| 1 | `InpEnablePriceAction` + `InpPAShowOnDashboard` | `PA: <pattern> strength NN dir …` and the zone it was confirmed in |
| 2 | `InpEnableMeanReversion` + `InpMRShowOnDashboard` | `MR: <verdict> …` — direction **opposite** the stretch |
| 3 | `InpEnableWyckoff` + `InpWyckoffShowOnDashboard` | `WY: SPRING/UPTHRUST …` or `stand aside` |
| 4 | `InpEnablePowerOf3` + `InpP3ShowOnDashboard` | `P3: ACCUMULATION / MANIPULATION / DISTRIBUTION / NONE` |
| 5 | `InpEnableSilverBullet` + `InpSBShowOnDashboard` | `SB: …` inside a configured window only |
| 6 | `InpEnableConfluence` + `InpCFShowOnDashboard` | the CF summary block — best strategy, unified score, direction, or `NO TRADE: <reason>` |
| 7 | `InpEnableRiskModel` + `InpRMShowOnDashboard` | `RM: OK/REJECT_*/WAIT …` with entry, SL, TP1/2/3, R:R, advisory size |

Leave all seven `…ShowOnDashboard` switches **off** while you validate the logs;
turn them on only once the numbers in the Experts log look sane.

### 2.3 Two switches that change existing behaviour (not just display)

Every other switch in this work is additive. These two are not, and both default
**off**:

- **`InpPARequireZoneContext`** (Phase 4) — makes a zone a **prerequisite** for
  `ContextualCandleScore` rather than a bonus. Turning it on **tightens** an
  existing scoring path. Verified bit-identical over 1 920 input combinations
  while off.
- **`InpOBZoneBodyOnly`** (Phase 1) — changes order-block **identity**, because
  `GenerateOBId` hashes the zone top and bottom. Turning it on will produce
  different block IDs from the same history.

---

## 3. Complete input reference (67 inputs)

All defaults below are the shipped defaults. Nothing existing was retuned.

### 3.1 Phase 1 — Order Block lifecycle (4 inputs, L808–811)

Added to the **existing** OB group, so there is no new banner.

| Input | Type | Default | Meaning |
|---|---|---|---|
| `InpOBUseAgeExpiry` | bool | `false` | retire an OB after `InpOBMaxAgeBars` closed bars |
| `InpOBMaxAgeBars` | int | `200` | closed **chart** bars; `<=0` disables even when the switch is on |
| `InpOBZoneBodyOnly` | bool | `false` | zone = pure candle body instead of body + rejection wick |
| `InpOBShowLifecycleLabel` | bool | `false` | append `FRESH/MITIGATED/BROKEN/EXPIRED` to the OB box label |

**Precedence rule (deliberate):** a body close through the zone is a **price**
fact and outranks expiry, which is a **time** fact. The age check therefore runs
**last** within the closed bar, so a block that both breaks and ages out on the
same bar resolves to `MITIGATED`, never to `EXPIRED`. `ReplayClosedBarStates()`
applies the identical rule in the identical position, which is what its design
contract demands.

**Vocabulary offset — do not "fix" this.** The file's state words are shifted one
step from the brief's:

| Brief's word | File's word |
|---|---|
| Fresh | `ACTIVE` |
| Mitigated (first touch) | `TOUCHED` |
| Broken | `MITIGATED` |

Renaming them would have churned every consumer for no behavioural gain, so the
file's vocabulary was kept (operator decision, Phase 1).

### 3.2 Phase 2 — Power of 3 + Silver Bullet (14 inputs, L906–918)

| Input | Type | Default | Meaning |
|---|---|---|---|
| `InpEnablePowerOf3` | bool | `false` | derive A/M/D from the Asia range `DetectJudasSwing` already computes |
| `InpP3ShowOnDashboard` | bool | `false` | append the phase to the tooltip |
| `InpP3DistributionMinATR` | double | `1.00` | closed-bar move away from the manipulation extreme, in ATR |
| `InpEnableSilverBullet` | bool | `false` | windowed sweep → structure shift → FVG → retrace query |
| `InpSBShowOnDashboard` | bool | `false` | append the SB state to the tooltip |
| `InpSBShowEntryZone` | bool | `false` | draw the FVG retrace zone the window resolved to |
| `InpSBUseNYLocalTime` | bool | `true` | `true` = New York local windows, `false` = broker-server time |
| `InpSBWin1Start` | int | `180` | window 1 open, 03:00 |
| `InpSBWin1End` | int | `240` | window 1 close, 04:00 |
| `InpSBWin2Start` | int | `600` | window 2 open, 10:00 |
| `InpSBWin2End` | int | `660` | window 2 close, 11:00 |
| `InpSBWin3Start` | int | `840` | window 3 open, 14:00 |
| `InpSBWin3End` | int | `900` | window 3 close, 15:00 |
| `InpSBChainMaxAgeBars` | int | `240` | a chain element older than this cannot start a new chain |

Windows are **minutes from local midnight**, which makes them
timeframe-independent — the same window means the same wall-clock period on M1,
M5 and M15. This is why they are integers rather than `datetime`s.

`P3_Decide` is total: `!range_valid` → `NONE`; `invalidated` → `NONE`;
`judas==0` → `ACCUMULATION`; `min>0 && distribution_atr>=min` → `DISTRIBUTION`;
otherwise → `MANIPULATION`. There is no path that returns "unknown".

### 3.3 Phase 3 — Wyckoff Spring / Upthrust (10 inputs, L928–939)

| Input | Type | Default | Meaning |
|---|---|---|---|
| `InpEnableWyckoff` | bool | `false` | detect Spring / Upthrust at a structural range |
| `InpWyckoffShowOnDashboard` | bool | `false` | append the event to the tooltip |
| `InpWyckoffShowRange` | bool | `false` | draw the range box the event was measured against |
| `InpWyckoffMinRangeBars` | int | `16` | shorter than this is noise, not accumulation |
| `InpWyckoffMaxRangeBars` | int | `240` | leftward expansion stops here |
| `InpWyckoffMaxRangeATR` | double | `6.00` | above this it is a trend, not a range |
| `InpWyckoffMinTouches` | int | `2` | required tests of **each** boundary |
| `InpWyckoffTouchTolATR` | double | `0.25` | how close to a boundary still counts as touching |
| `InpWyckoffRequireVolume` | bool | `true` | require the existing displacement-or-volume confirmation |
| `InpWyckoffMaxAgeBars` | int | `96` | older than this many closed bars is stale |

The range expands **leftward from `closed-1`** and stops **before** accepting a
bar that would blow `InpWyckoffMaxRangeATR` — so an over-wide bar can never
silently widen the range it is being tested against. Confirmation reuses the
existing `SweepHasDisplacementOrVolume()`; **no new data source**.

A Judas conflict forces `dir=0, active=false, score=0` — the module will never
print a side next to a stand-aside.

### 3.4 Phase 4 — Pure Price Action (7 inputs, L949–959)

| Input | Type | Default | Meaning |
|---|---|---|---|
| `InpEnablePriceAction` | bool | `false` | unify patterns and require a zone for confirmation |
| `InpPAShowOnDashboard` | bool | `false` | append the PA verdict to the tooltip |
| `InpPARequireZoneContext` | bool | `false` | make the zone a **prerequisite**, not a bonus (§2.3) |
| `InpPAIncludeInsideBar` | bool | `true` | add `INSIDE_BAR` to the unified pattern set |
| `InpPAInsideBarStrength` | int | `45` | an inside bar carries no direction of its own |
| `InpPAZoneToleranceATR` | double | `0.15` | how close to a zone still counts as inside it |
| `InpPAIncludePOC` | bool | `true` | count the active volume-profile POC as a zone |

**The unification the brief asked for already existed.** `AnalyzeClosedCandle`
(def **L5650**) is already the single function returning pattern type plus
strength. What was genuinely missing was **Inside Bar** and the **zone rule**,
and those are what Phase 4 added. Three candle implementations still coexist in
the file — see §8, C1.

`PA_ResolveDirection`: `if(!in_zone) return 0;` → conflict → `0` →
`pattern_dir` → `zone_dir`. `PA_Score`: `if(!in_zone) return 0;` →
`25 + round(strength*0.45) + (agrees ? 30 : 0)`.

### 3.5 Phase 5 — Mean Reversion / Momentum (13 inputs, L969–984)

| Input | Type | Default | Meaning |
|---|---|---|---|
| `InpEnableMeanReversion` | bool | `false` | master switch; while off the module costs nothing |
| `InpMRShowOnDashboard` | bool | `false` | append the MR verdict to the tooltip |
| `InpMRStdDevPeriod` | int | `20` | closed bars used for the sigma of (close − VWAP) |
| `InpMRBandSigma` | double | `2.00` | band width in sigma |
| `InpMRDivLookback` | int | `200` | closed bars searched for the two confirmed swings |
| `InpMRDivMinRSIDelta` | double | `2.00` | minimum RSI gap that counts as divergence |
| `InpMRRSIOverbought` | double | `70.0` | at or above this, a stretched-up bar is exhausted |
| `InpMRRSIOversold` | double | `30.0` | at or below this, a stretched-down bar is exhausted |
| `InpMRUseMACD` | bool | `false` | use MACD as a **veto** on fading against momentum |
| `InpMRFastEMA` | int | `12` | MACD fast EMA |
| `InpMRSlowEMA` | int | `26` | MACD slow EMA |
| `InpMRSignalSMA` | int | `9` | MACD signal SMA |
| `InpMRMacdDeadZoneATR` | double | `0.05` | histogram must clear this fraction of ATR |

Bands are `BufVWAP ± InpMRBandSigma·σ` where σ is the **RMS distance from VWAP**
— deliberately *not* mean-centred, because centring it would shrink the bands
whenever price trends away from VWAP, exactly when an overextension signal is
most likely to be a false one. The existing VWAP (buffer 2, `FillEMAAndVWAP`) is
reused; **`iBands` was not added**.

Divergence delegates to `IsFractalHigh` / `IsFractalLow` + `FractalRightBars`
(which were **dead code** before this phase) with the guard `i+n > total-2`.
**Regular divergence only**; if both regular and hidden fire, the module reports
`CONFLICT` rather than picking one. RSI `0.0` means unavailable, not neutral.

**MACD is structurally veto-only.** `MR_Score` contains exactly two `s+=`
statements (`+45` divergence, `+20` RSI) — MACD can only subtract a candidate,
never award points. That is enforced by the test suite, not by convention.

The printed direction is always **opposite** the stretch: an overextension above
the upper band prints a SELL-side fade.

### 3.6 Phase 6 — Confluence Engine (11 inputs, L994–1005)

| Input | Type | Default | Meaning |
|---|---|---|---|
| `InpEnableConfluence` | bool | `false` | master switch for the ONE unified score |
| `InpCFShowOnDashboard` | bool | `false` | show the confluence block in the tooltip |
| `InpCFWeightStructure` | int | `20` | MSS / BOS / CHoCH alignment |
| `InpCFWeightLiquidity` | int | `20` | swept-pool alignment |
| `InpCFWeightZone` | int | `20` | price inside a live OB / FVG / SR / POC |
| `InpCFWeightSession` | int | `10` | kill zone / London / NY / Asia |
| `InpCFWeightCandle` | int | `15` | unified pattern strength (**needs Price Action**, §2.1) |
| `InpCFWeightMTF` | int | `15` | higher-timeframe closed structure |
| `InpCFMinDisplayScore` | int | `60` | below this the engine stands aside |
| `InpCFVetoOnConflict` | bool | `true` | `NO TRADE` when a source **with** evidence contradicts |
| `InpCFRequireActiveStrategy` | bool | `false` | additionally require one strategy module active |

**Weights sum to exactly 100** (20+20+20+10+15+15). If an operator breaks that
sum, the engine **refuses** — `NO TRADE: confluence weights sum to N…` — rather
than silently renormalising. A silent renormalisation would quietly change what
every weight means.

The six legs read, in order: `ScoreStructure(rates_total, side)`,
`ScoreLiquidity(side, -1)`, `PA_ZoneAt(price, closed, atr, …)`, the session leg
below, the PA candle leg, and `g_htf_bias` directly.

**This is a new column beside the existing scoring, not a replacement.** The
existing `final_score`, `setup_quality_score` and `g_score` are untouched (§9).

### 3.7 Phase 7 — Risk Model (8 inputs, L1006–1013)

| Input | Type | Default | Meaning |
|---|---|---|---|
| `InpEnableRiskModel` | bool | `false` | master switch for the advisory Entry/SL/TP/R:R readout |
| `InpRMShowOnDashboard` | bool | `false` | show the readout in the tooltip |
| `InpRMSLBufferATR` | double | `0.30` | ATR buffer beyond the zone or pool the stop sits behind |
| `InpRMSLMaxATR` | double | `2.00` | hard cap on stop distance in ATR; beyond it the plan is rejected |
| `InpRMNoZoneSLATR` | double | `1.50` | stop distance when no zone and no pool sits behind entry |
| `InpRMUseRRFloor` | bool | `true` | reject when TP1's R:R is below `InpTopDownMinRR` |
| `InpRMPreferTopDownPlan` | bool | `true` | adopt the TopDown chain's own entry/SL/TP1 when it agrees |
| `InpRMMaxPoolScan` | int | `40` | how many recent liquidity pools to scan |

**⚠️ The brief named `InpMinRR` (2.0) and `InpRiskPercent` (1%). Neither exists
in this file**, and neither was invented. The module reuses the real
equivalents:

| Brief's name | Actual input reused | Default |
|---|---|---|
| `InpMinRR` | `InpTopDownMinRR` (**L1202**) — *"hard R:R floor (policy: never below 1:2)"* | `2.0` |
| `InpRiskPercent` | `InpSniperMaxRiskPct` (**L1851**) — *"Advisory equity risk % per trade (1.0–2.0%)"* | **`1.50`** |

**So the risk percentage the module reports defaults to 1.50, not 1.0.** That is
the single most consequential deviation from the brief, and it is deliberate:
a second R:R floor and a second risk percentage would put two knobs in one file
that can disagree with each other. The value is clamped to 1.0–2.0 by the same
`MathMax/MathMin` the Sniper model uses. Changing that default would change the
Sniper model too, which is out of scope.

---

## 4. Where each module lives

| Module | State globals | Declarations | Section | Definition range | Self-test |
|---|---|---|---|---|---|
| OB1 | *(existing OB structs)* | L5530 | L18145 | inline in the detection loop | *(none — reuses the OB suite)* |
| SB1 / P3 | L1966 / L1981 | L5741 | L25193 | L25321 / L25497 | `PASS (9/9)` @L15509 |
| WY1 | L1996 | L5768 | L25772 | L25961 | `PASS (9/9)` @L15513 |
| PA1 | L2020 | L5787 | L26211 | L26437 | `PASS (9/9)` @L15517 |
| MR1 | L2039 | L5805 | L26634 | L26892 | `PASS (9/9)` @L15521 |
| CF1 | L2064 | L5824 | L27235 | L27400 | `PASS (10/10)` @L15525 |
| RM1 | L2097 | L5842 | L27731 | L27957 | `PASS (10/10)` @L15529 |

**Six self-tests, 56 in-file checks** (9+9+9+9+10+10), all gated by the existing
`InpMTEERunSelfTest` — no new gate was introduced. Phase 1 added no self-test
because it completed an existing engine rather than adding one.

Supporting anchors, all verified at `ebc43bc`:

| Thing | Line |
|---|---|
| `#property indicator_buffers 19` / `indicator_plots 7` | L627 / L628 |
| `enum ENUM_P3_PHASE` / `enum ENUM_WYCKOFF_EVENT` | L747 / L757 |
| `SNIPER_SL_BUFFER_ATR 0.30` / `SL_HARD_MAX_H1_ATR 2.00` / `BE_DISP_ATR 2.00` / `TRAIL_M15_ATR 0.50` | L1895–1898 |
| `struct STopDownState` | L1929 |
| `InpUseHTFBias` / `InpTopDownMinRR` / `InpMTEERunSelfTest` / `InpSniperMaxRiskPct` | L1187 / L1202 / L1841 / L1851 |
| `InpLogLifecycleTransitions` | L1298 |
| `ScoreStructure` / `ScoreLiquidity` / `ScoreSession` / `ScoreHTF` (defs) | L18104 / L18125 / L18256 / L18265 |
| `CalculateAITradeSetup` (def) — the only writer of `g_score` | L21198 |
| `TheoreticalRiskMoney` (def) | L23441 |
| `PA_ZoneAt` (def) | L26367 |
| `TopDown_Evaluate` (def); its existing R:R gate | L34409; L34601–34603 |
| `TopDown_Update` (def) | L34640 |
| Module self-tests (SB / WY / PA / MR / CF / RM) | L25634 / L26105 / L26509 / L27049 / L27553 / L28154 |

Every self-test exercises **pure cores with local values only**. None reads
series data, account data or tick data, so all six are deterministic in the
Strategy Tester and on any symbol.

---

## 5. The causal order inside `OnCalculate`

`OnCalculate` begins at **L15709**. The relevant call order, verified:

```
L15953  OB age bound            inline, LAST within the closed bar (price outranks time)
L16067  P3_Update(closed)
L16068  SB_Update(closed)
L16072  WY_Update(closed)
L16128  TopDown_Update(rates_total,false)   <-- publishes the plan RM may adopt
L16150  PMI_Update()
L16300  MVP_Update(...)                     <-- volume profile / POC
L16309  PA_Update(closed)
L16317  MR_Update(closed,rates_total,full_indicators)
L16323  CF_Update(closed,rates_total)       <-- reads PA, MR, WY, P3, SB
L16328  RM_Update(closed,rates_total)       <-- reads CF's verdict + TopDown's plan
L16335  ZRE_Update(...)
```

Two properties this order guarantees:

1. **`RM_Update` runs after both `CF_Update` and `TopDown_Update`**, so the
   verdict it attaches to and the plan it may adopt are both fresh for this bar.
2. **Every module call is under `if(is_new_bar || detection_updated)`**, so no
   module recomputes on every tick. Combined with the `prev_calculated` delta
   approach, there is no full-history loop per tick anywhere in this work.

Each module's driver calls its own `Clear()` **as its first statement**, then
early-exits. A disabled or blocked module can therefore never leave a previous
bar's verdict on the dashboard. `RM_Clear()` is also called in `OnInit` (L15496)
after `CF_Clear()`.

Every module refuses the forming bar with the file's own idiom,
`closed > rates_total-2`, before touching any series array.

---

## 6. What you see on the dashboard

**No module added a card row.** The 11-row card is hard-capped
(`if(ln>11) ln=11;`) and already has **13 candidate assignments**, so it
truncates today. A display-only extra must not be able to push a Core row off
it. All new content therefore goes into the **tooltip**, in this order:

| Guard line | Block |
|---|---|
| L33704 | CF summary — **first**, ahead of the per-module detail |
| L33735 | RM advisory |
| L33763 | Power of 3 |
| L33775 | Silver Bullet |
| L33792 | Wyckoff |
| L33812 | Price Action |
| L33830 | Mean Reversion |

Each is guarded by its own `InpEnable… && Inp…ShowOnDashboard` pair, so with the
switches off the tooltip is byte-identical to before this work.

Two drawing opt-ins exist and default off: `InpSBShowEntryZone` (the FVG retrace
zone) and `InpWyckoffShowRange` (the range box). `InpOBShowLifecycleLabel`
changes only the OB box's **label text**.

---

## 7. The Risk Model's output, precisely

Verdicts: `OK`, `REJECT_RR`, `REJECT_SL`, `WAIT`.

- **`WAIT`** — the Confluence Engine named no side. The Risk Model publishes
  nothing further and **never invents a direction**.
- **`REJECT_SL`** — `NO PLAN: stop is N ATR away, beyond the 2.00 ATR cap`. The
  entry is in the wrong place. **The stop is never widened to make the trade
  fit.**
- **`REJECT_RR`** — `NO PLAN: R:R N.NN below the required 2.00 (<target source>)`.
- **`OK`** — `plan_src` is `TOPDOWN` when the chain's plan was adopted, or
  `DERIVED` when this module built its own.

Targets are pushed to non-decreasing distance
(`d2=MathMax(d2,d1)`, `d3=MathMax(d3,d2)`) and then **re-checked live** by
`RM_TPsOrdered`, which tests the **side** — a target that ends up behind entry is
rejected as a second stop rather than being printed as a profit target.

**Sizing is text only.** It reaches the user through exactly one formatter,
`RM_SizeText`, and **both** of its branches state that no order is placed. The
unavailable branch says **"units"**, never "lots". Sizing refuses
`TheoreticalRiskMoney()==0.0` **before dividing**, so a symbol with no tick
value yields `unavailable` rather than a fabricated number.

**Trade API in the indicator: zero.** `OrderSend`, `OrderSendAsync`, `CTrade`,
`PositionOpen` all appear 0 times after comment-stripping. Execution remains
solely in `MQL5/Experts/QSMC_AutoTrader.mq5`, which reads only buffers 7–12 and
ships inert.

---

## 8. The nine conflicts found, with evidence

These are observations about code that already existed, recorded rather than
silently "fixed". Changing them would have altered live trading behaviour.

**C0 — `AUDIT-OB1`: the order-block geometry was ambiguous.** The one deleted
line, `if(st.bullish){ob_top=MathMax(o[ob_bar],c[ob_bar]); ob_bottom=l[ob_bar];}`,
mixed a body edge with a wick edge. `InpOBZoneBodyOnly` now makes that a choice,
**defaulting to the existing hybrid**, so nothing changes unless you opt in.

**C1 — three candle implementations coexist, and they disagree.**
`AnalyzeClosedCandle` (def **L5650**), `AnalyzeCandleIntelligence` (decl L2657,
def **L20179**) and `MTF_SniperEvaluateEntryTriggers` (decl L7071, def **L44923** —
the **C1 gate**)
classify the same bar differently. With body/range `(95,100,90,95)` the C1 gate
returns **TRUE** while the ACC label reads **DOJI**. **Pinned, not repaired** —
unifying them would have **tightened** an existing entry gate, which the task
rules forbid.

**C2 — `g_score` is stale by design.** `SScoreBreakdown g_score` is written in
exactly one place (the end of `CalculateAITradeSetup`, called from one
conditional site) and **nothing in the file ever resets it**. Phase 6 therefore
does not read it; it calls the pillar scorers itself on the closed bar. The
state those scorers read *is* fresh: `BuildCausalEventGraph` (which also clears
`g_selected_structure_event`) and `ComputeHTFBias` both run before the call site.

**C3 — `AUDIT-CF1`: the existing weights sum to 1.1000, not 1.0000.** Both
`final_score` branches (assignments at **L21662–21686**) do this — the default branch
(`.18/.12/.14/.10/.08/.12/.16/.10/.10`) and the institutional branch
(`.22/.14/.16/.10/.10/.18/.10/.05/.05`). **Reported, not fixed.** The new
engine's weights sum to exactly 100 and are validated every bar.

**C4 — `AUDIT-CF1`: two free points contradict "missing evidence = 0".**
`ScoreSession()` returns **30.0** when no session matched at all, and
`ScoreHTF()` returns **50.0** both when `InpUseHTFBias` is off **and** when
`g_htf_bias==0` — i.e. for a total absence of evidence. Both feed the existing
score, so editing either would have **silently re-priced every trade in the
file**. They are therefore zeroed **locally inside `CF_Update`** (the MTF leg
reads `g_htf_bias` directly and never calls `ScoreHTF()`), and the two existing
functions are pinned byte-for-byte by the test suite.

**C5 — `AUDIT-MR1`: two divergence helpers were dead code.** `IsFractalHigh` (def **L35132**),
`IsFractalLow` (def **L35143**) and `FractalRightBars` (def **L24180**) had a declaration and a definition and **no caller**. Phase 5 wired them
in rather than writing a fourth swing detector.

**C6 — `AUDIT-RM1`: the named inputs do not exist.** See §3.7. Reused, not
invented; the reported risk percentage is **1.50, not 1.0**.

**C7 — `AUDIT-RM1`: a complete risk model already existed.**
`MTF_SniperComputeTradeManagement` (decl L7072, def **L45076–45187**) already computes entry, a stop
behind the zone or the opposing swing, a hard ATR cap that yields
`SKIP_SL_MAX`, TP1/2/3 from the nearest opposing zone / HTF zone / D1-W1
liquidity with 1R/2R/3R fallback, break-even, trailing and `rec_lot_size`. The
TopDown chain already builds opposing targets and rejects below
`InpTopDownMinRR`. `STopDownState`'s own header comment says its published tuple
exists so a downstream planner can *"reconcile ITS zone with the chain's zone
instead of re-deriving (and possibly contradicting) it"*. **Phase 7 is that
planner**, and adopts the chain's plan verbatim when directions agree.

**C8 — buffers 7–12 already carry Entry/SL/TP1/TP2/TP3** per signal, via
`SigLog_BufWrite` (def **L14512**), with ZRE using 13–18. Phase 7 did not need a buffer
and did not add one.

---

## 9. Invariants guaranteed mechanically

| Invariant | Value | Enforced by |
|---|---|---|
| New buffers | **zero** — `indicator_buffers` 19, `indicator_plots` 7, indices 0–18 | all seven suites |
| Trade API in the indicator | **zero** after comment-stripping | `check_release_gate.py` G4 + Phase 7 suite |
| Existing score state | `g_score.` 74, `final_score` 21, `setup_quality_score` 6 — unchanged | Phase 6 suite |
| Closed-bar idioms | `rates_total-2` ×12, `ArraySize(g_buf_c)-2` ×3, `g_rates_total-2` ×8 — unchanged | Phases 5 & 6 suites |
| Dashboard card | **13 candidate rows under the 11-row cap** — no module added a row | `test_dashboard_clarity.py` + Phases 6 & 7 |
| Version triple | `v6.6.9` / `"6.69"` — unchanged | `check_release_gate.py` G1 |
| Sizing | text only; one formatter; both branches disclaim; no division by zero | Phase 7 suite |
| Symbol-agnostic | no literal price level in any module core | Phases 2, 3, 5, 7 suites |
| Enums | 43, all appended — none renumbered | Phase 5 suite |
| Inputs | 583 total, 67 new, all new ones default `false` where behavioural | release gate + suites |

Line-ending discipline: pure CRLF, **0 bare LF** (`*.mq5`/`*.mqh` are byte-exact
via `.gitattributes`). Braces **3740/3740**; paren balance verified on
comment-stripped text.

---

## 10. Verification evidence

### 10.1 Offline suites (all re-run against the final file)

| Suite | Checks | Failures |
|---|---|---|
| `tools/test_orderblock_lifecycle.py` | 103 | 0 |
| `tools/test_phase2_modules.py` | 204 | 0 |
| `tools/test_phase3_wyckoff.py` | 182 | 0 |
| `tools/test_phase4_priceaction.py` | 234 | 0 |
| `tools/test_phase5_meanreversion.py` | 256 | 0 |
| `tools/test_phase6_confluence.py` | 286 | 0 |
| `tools/test_phase7_riskmodel.py` | 292 | 0 |
| **Seven phase suites** | **1 557** | **0** |
| `tools/test_docs_freshness.py` | 294 | 0 |
| `tools/test_comment_integrity.py` | 19 | 0 |
| **This document's own guard + the F7 defect guard** | **313** | **0** |
| `tools/test_decision_journal.py` | 299 | 0 |

Full gate: **5 static tools PASS · 28 suites · 3 253 PASS lines · 0 failures**.
CI: **35 steps**, `.github/workflows/qsmc-verify.yml` (step 32 = `tools/test_resolver.py`, step 33 = `tools/test_weighted_gates.py`, step 34 = `tools/test_scalping.py`, step 35 = `tools/test_decision_journal.py`).

### 10.1b This document is itself under test

`tools/test_docs_freshness.py` (CI step 29) exists because the 101 line
citations above are the most fragile thing in this file: any edit to
`nadir2.mq5` above a citation silently invalidates every citation below it, and
nothing complains. Nine citations carried forward from earlier phase notes were
**already stale** when this document was first written (§1 records the
corrections), so the citations are now a contract rather than a comment.

It checks, in both directions:

| Part | What it pins |
|---|---|
| A | 87 citations resolve against source; for definitions the *computed* definition line must equal the citation, so a **wrong** citation fails too, not only a drifted source |
| B | the §5 call order is real and ascending, plus the three claims it argues for |
| C | the §6 tooltip guards are where stated, in the stated order |
| D | every countable fact above is **recomputed** from source and compared to this text — 67 inputs, 548 total, 44 enums, buffers 19, plots 7, the version triple, 56 in-file self-test checks, zero trade API |
| D2 | the §2.1 dependency is **derived**: weights must sum to exactly 100, the reachable maximum is computed as `100 − InpCFWeightCandle` = 85, this document must state that number, and CF's candle leg must really be guarded by `InpEnablePriceAction &&` |
| E | no citation past EOF, the nine stale numbers absent, disclaimers present, all 13 sections present |
| F | **two-way binding** — every line the test pins must also be cited here, directly or inside a range. Without F, this document and the test could disagree while both stayed green |

It reads **no git state**; every assertion is a pure function of two files on
disk. Commit hashes named in this document are therefore *not* verified, because
CI checks out with `fetch-depth: 1` and the base commit is absent.

### 10.2 Mutation testing

Each suite was adversarially checked by injecting deliberate defects into the
source and confirming the suite turns red.

| Phase | Mutations | Caught |
|---|---|---|
| 4 | 25 | 24 (M13b is a documented semantic question, not a miss) |
| 5 | 28 | 28 |
| 6 | 45 | 45 after hardening |
| 7 | 43 | 43 after hardening |
| this doc | 43 | 43 after hardening (33 original + 10 added with §11.1) |
| comment integrity | 8 | 8 (incl. re-introducing the original 42-error defect) |

The documentation guard's own mutation run found **three real gaps**, all closed:

- `"1.50" in DOC_TEXT` was a **weak substring pin** — `InpRMNoZoneSLATR`'s 1.50
  default satisfied it too, so deleting the 1.50-vs-1.0 disclosure passed. Now
  derived from source and pinned to its actual sentences.
- Parts A–C verified source against hard-coded pins, which left this document
  free to cite a **different** line while both stayed green. Part F closes that.
- The 85-not-100 activation claim was unpinned. Part D2 derives it.

Two classes of real weakness were found this way and closed, both worth knowing
because they apply to any future suite in this repo:

- **A behavioural model can pass while its source transcription drifts.** All
  three Phase 6 round-1 misses were re-derivations that were correct in the
  model but no longer pinned to the source. Every transcription now has a source
  pin.
- **`call_count("Name(")` leaks multi-line declarations.** A declaration's first
  line starts with a return type but ends with a comma, not a semicolon, so the
  declaration exclusion never fires and the count is inflated — a `>= 2`
  threshold silently passed a removed call. Counts are now scoped to the calling
  function's own body.

The source was restored **byte-identical** after every mutation run.

### 10.3 What these suites are not

They are contract tests over the text of the file. They prove structure,
ordering, reuse, absence of trade API, buffer safety and default values. They
**do not** prove the code compiles, and they **do not** constitute a backtest.
No backtest result is claimed anywhere in this work.

---

## 11. F7 checklist — the only gate that remains

Run in MetaEditor on `nadir2.mq5`:

1. **Compile.** Expect **0 errors, 0 warnings**. Report anything else verbatim.
2. **With every new switch off**, the chart, the 11-row card and the tooltip must
   be **identical** to `e3c0b5b` behaviour.
3. **Enable `InpMTEERunSelfTest`** and confirm **six** new PASS lines in the
   Experts log, in this order:
   `Power-of-3 / Silver-Bullet self-test: PASS (9/9)` ·
   `Wyckoff Spring/Upthrust self-test: PASS (9/9)` ·
   `Pure Price Action self-test: PASS (9/9)` ·
   `Mean-reversion / momentum self-test: PASS (9/9)` ·
   `Confluence Engine self-test: PASS (10/10)` ·
   `Risk model self-test: PASS (10/10)`.
4. **XAUUSD M1, M5, M15**, then **one non-gold symbol** (EURUSD M15) and one JPY
   pair. Every threshold is in ATR or normalised units; no hard-coded price
   exists in any module. Check that `RM plan:` prices render at the correct
   `_Digits` and that `RM size:` names your **account** currency.
5. **No-repaint test.** Run live on M1 with `InpLogLifecycleTransitions=true`,
   record each module line with its bar timestamp, then reload the same window
   and diff. Verdicts must match bar-for-bar, and the plan for bar *N* must
   never change after *N+1* opens.
6. **Break the weights on purpose.** Set `InpCFWeightStructure` to 30 and confirm
   the engine prints `NO TRADE: confluence weights sum to 110…` rather than
   renormalising or scoring normally.
7. **Confirm the Risk Model never invents a side.** With `InpEnableConfluence`
   off and `InpEnableRiskModel` on, every bar must publish `WAIT`.
8. **Confirm sizing refuses bad data.** In the Strategy Tester, or on a symbol
   without a tick value, expect
   `RM size: unavailable (tick value or equity not reported)` — never a number.

---

## 11.1 What F7 actually found (first compile of the merged build)

The first compile of the merged seven-phase build reported **42 errors, 0
warnings**. Every one of them came from **one missing comment marker**.

```
24911  // Reset BOTH modules to their inert state.
24912   Called when a new symbol/day context        <-- the "//" was gone
24913  // arrives so a stale phase or window can never be displayed against fresh bars.
```

The compiler read line 24912 as code — `'Called' - unexpected token, probably
type is missing?` at 24912:2, `'when' - semicolon expected` at 24912:9 — then
mis-parsed the entire `SBP3_Clear()` body as a run of **global-scope
declarations**. That produced 40 further errors: `variable already defined` for
`g_p3_dir`, `g_p3_score`, `g_p3_reason`, `g_p3_invalidation`, `g_sb_active`,
`g_sb_window`, `g_sb_dir`, `g_sb_fvg`, `g_sb_entry_high`, `g_sb_entry_low`,
`g_sb_reason`, `g_sb_score` and `g_sb_invalidation` — each pointing back at its
real declaration near L1977–1994 — and finally `expressions are not allowed on a
global scope` on the closing brace at 24921.

**One missing `//` became 42 errors.** Fixed by restoring the marker; the
three-line comment is now intact and pinned by a test (§11.2).

### Why all 22 existing suites passed anyway

This is worth recording precisely, because it is the honest limit of offline
verification:

- **Braces stayed 3740/3740 and parens stayed balanced.** A comment marker is
  neither, so every balance check was still true.
- **`strip_comments`-based checks were actively blind to it.** With no `//` there
  is nothing to strip, so the prose simply became part of the "code" those checks
  counted — and it counted fine.
- **`mql5_rules.py` covers StringFormat arity, duplicate globals, the version
  triple, pointers to structs, `->`, and unbraced declarations.** None of those is
  a comment.
- The suites assert structure, ordering, reuse, defaults and absence of trade
  API — **all of which were still true**. The file was structurally perfect and
  lexically broken.

### Scope of the search for more of these

After the fix, the whole 44 831-line file was rescanned lexically — tracking
comment, string and character-literal state character by character — for any
other line the compiler would have to parse as code but which is really English
prose. Result: **zero**. Also verified: **0 duplicate function definitions**, all
**73** module functions of the seven phases defined or declared where they are
called, `/*` and `*/` balanced at **0/0** (this file uses no block comments at
all, which is what makes a lost marker fatal rather than silently swallowing a
region), and the lexical scanner terminates in `code` state — so no unterminated
comment or string.

**What this does not prove.** MQL5 may have stopped reporting at the first
broken construct. The 42 errors were one cascade, so clearing it is *expected* to
clear the build — but only a second F7 can confirm that. Type errors, arity
slips, undeclared identifiers and shadowing remain invisible here.

## 11.2 The gap is now owned by a test

`tools/test_comment_integrity.py` (**19 checks**, CI step **30**) exists because
this defect class had no owner. It decides what is comment and what is code by
tracking lexical state character by character, then asserts:

| Part | What it pins |
|---|---|
| A | no line outside a comment or string is English prose — detected by requiring **two English function words** in a punctuation-free code view, which is what separates the defect from the file's 100+ legal punctuation-free headers (`enum ENUM_X`, `struct SX`, `input group "..."`) |
| B | the **comment-neighbour rule**: no punctuation-free line sits between two `//` comments — the exact shape of the real defect |
| C | lexical state terminates cleanly; `/*` and `*/` balance; pure CRLF; **no block comments at all** |
| D | no function defined twice; all 73 module functions resolved |
| E | the historical defect pinned directly — the three-line comment above `SBP3_Clear()` must be intact |

**Mutation-tested 8/8**, including re-introducing the original defect (which trips
A, B and E — 4 checks). Two bugs in the suite itself were found and fixed while
building it: rule B false-positived on every `input group "..."` banner, and one
check was a **tautology** (`len(x)==0 or FINAL_STATE=="code"`, where the second
half was already asserted above, so it could never fail) — replaced with the real
invariant that the file contains no block comments.

---

## 11.3 AUDIT-RS1 — the final resolver (Phase 2, commit 1)

**Why.** Phase 1 read the code and found the direction conflict is real, not a
rendering artefact: `AlertDispatcherFinalize` writes `g_alert_primary`, the
dashboard STATUS card reads it, and `UpdateMTFExecutionEntry` derives its own
`bull` for the label, the arrow and the hline colour — nothing in the file ever
compares the two. The tactical state word printed `CONFIRMED` although the rule
printed three lines above it says only the arbiter may say that.

**What.** `ResolveFinalSignal()` (**L6146**, inputs **L852–L860**) — one function, called once from `OnCalculate`
after `AlertDispatcherFinalize`, and only on a closed-bar or detection event. Four
layers vote (HTF/D1 bias, zone role, reaction level, tactical entry) weighted
**25 / 25 / 30 / 20 = 100**. `OnInit` refuses to initialise if they do not sum to
100 and never renormalises silently. Both sides voting ⇒ CONFLICT → WAIT (the
resolver never picks a side to look useful); the winning side below
`InpResMinScore` (60) ⇒ WAIT; otherwise it writes `g_final_signal` /
`g_res_score` / `g_final_why`, and that why-text always states the score is a
confluence count, **not** a probability.

**Off by default, and provably inert.** `InpUseFinalResolver = false`: with it off
the dashboard, the tooltip and the tactical word behave exactly as before. With it
on all three read the same `g_final_signal`, and the tactical word is demoted
`CONFIRMED` → `INFO`, so `CONFIRMED` can only come from the resolver.

**Verify.** F7, drag onto M5, set `InpUseFinalResolver = true`, then compare the
STATUS card with the tactical label on the same bar: they must agree, or both must
say WAIT / CONFLICT. Then set the four weights to 40/40/40/40 — `OnInit` must
refuse with a weight-sum message rather than quietly renormalise.

**Contract suite.** `tools/test_resolver.py` pins all of the above (CI step 32):
the flag's default, the call site's position and its closed-bar gate, the
weight-sum refusal, the CONFLICT branch, the demotion of the tactical word, the
reuse of `PA_ZoneAt(` instead of a second zone scan, the absence of any
`g_final_score` substring collision, and — as always — that no order API appears.


## 11.4 AUDIT-GS1 — weighted evidence gates, hard vetoes first (Phase 2, item 2)

**Why.** Publication was a conjunction: `alert_eligible` (which carries the level
minimum) AND proximity AND channels AND cooldown AND ranking. Phase 1 ranked this
B/C HIGH — every extra gate multiplied the miss rate, and a candidate that failed
one weak leg was indistinguishable from one with no evidence at all, because the
reason was never written down anywhere the operator could read.

**What.** `WeightedGateAllows()` (**L42242**, inputs **L861–L871**, flag
`InpUseWeightedGates` at **L862**) is called from the dispatcher's selection loop.
It tests the vetoes that must never be traded away **first**, and returns
immediately with a `HARD VETO: …` reason:

| veto | rule reused |
|---|---|
| invalid candidate data | `!valid`, `direction==0`, `bar_time<=0`, `closed_index<0` |
| spread | `g_spread > InpMaxSpreadPts`, keeping the `InpIgnoreSpreadInBacktest` exemption |
| high-impact news | `MTF_SniperIsNewsBlackout(bar_time)` — the existing Golden Rule 6, not a second news rule |

Only then does it weigh **evidence**, at **25 / 25 / 20 / 15 / 15 = 100**: level
(reusing the same `MathMax(2,MathMin(5,InpRXNAlertMinLevel))` clamp as the
existing eligibility rule), evidence score (`InpWGMinEvidenceScore = 68`, a
*mirror* of the existing floor, not a change to it), proximity (reusing
`InpAlertMaxDistanceATR` and its documented fallback), HTF+D1 alignment, and room
to the opposing zone in ATR units (`InpWGMinRoomATR = 1.0`). Below
`InpWGMinScore = 60` the answer is WAIT, and the why-text lists **both** the legs
earned and the legs missed. The score is a weighted confluence count, not a probability — the same rule the resolver's why-text follows. `OnInit` refuses to initialise if the weights do not
sum to 100, or if the minimum is outside 0–100 — it never renormalises.

**What stays hard.** Channels, cooldown and ranking are delivery and
de-duplication, not evidence, so they are outside the flag's scope and unchanged.
`RXN_LevelEx` and its 1:1 self-tests are untouched, and no `InpWG*` input appears
inside that function: the scorer wraps the decision, it does not rewrite the
pinned level promotion. No shipped threshold moved (68 / STRICT / cooldown 5 /
CF 60 / resolver 60).

**Off by default, and provably inert.** With `InpUseWeightedGates = false` the
selection is the original conjunction token for token — the ternary's OFF branch
is literally `:(c.alert_eligible && c.distance_atr<=maxd);` — and the tooltip
carries no gate line.

**Verify.** F7, drag onto M5, set `InpUseWeightedGates = true`, then read the
tooltip's `Weighted gate:` line on a bar with no alert: it must name either a
`HARD VETO` or the missed legs. Then set the weights to 30/30/30/30/30 —
`OnInit` must refuse with *"Invalid Quantum SMC weighted-gate weights: they must
sum to exactly 100"*.

**Contract suite.** `tools/test_weighted_gates.py` (CI step 33) pins all of the
above, including the ordering that makes a veto un-outvotable: every veto line
must precede the first `got+=`, and no weight may be accumulated above the news
veto.

## 11.5 AUDIT-SC1 — six scalping strategies for M1–M5 (advisory, display only)

**Why.** The engine already had a scalper profile — `QSMC_PRESET_SCALPER` in
`QSMC_Preset.mqh`, auto-selected when the chart is M1–M5 — but nothing *used* it
as a strategy layer: no scalping verdict, no scalping reason, and no cost model.
Scalping dies on spread, and the file had no place that said so.

**What.** `SCALP_Update()` (**L6310**) behind `InpEnableScalping = false`
(**L873**), with a separate display opt-in `InpScalpShowOnDashboard` (**L874**).
Six strategies vote, each reading state the existing modules **already published**
for the same closed bar — the overlay re-derives nothing and re-runs no module:

| leg | strategy | reads | weight |
|---|---|---|---|
| `MOM` | momentum burst | one closed bar displacing ≥ `InpScalpDispATR` (0.40 ATR) from the mirrored close buffer | 20 |
| `EDGE` | zone-edge fade | `g_mr_ext_dir` stretched **into** a zone whose role opposes it, via the one `PA_ZoneAt(` scan | 20 |
| `SB` | Silver Bullet window | `g_sb_active` + `g_sb_dir` | 15 |
| `P3` | Power of 3 / Judas | `g_p3_dir` | 15 |
| `WY` | Wyckoff spring/upthrust | `g_wy_active` + `g_wy_dir` | 15 |
| `CF` | Confluence Engine | the stronger of `g_cf_buy_score` / `g_cf_sell_score` **at CF's own `InpCFMinDisplayScore`** | 15 |

**20 / 20 / 15 / 15 / 15 / 15 = 100**, and `OnInit` refuses to initialise on any
other sum. The geometry is the SCALPER preset's own numbers, not new ones:
displacement 0.40 ATR (`p_disp`), RR floor 1.20 (`p_minrr`), advisory stop 0.80 ATR
and target 1.20 ATR ⇒ RR 1.50. A scalp that cannot clear the RR floor is
**refused**, not published with a bad shape.

**Vetoes first, inherited from AUDIT-GS1.** Four vetoes are tested before any
weight is counted, each writing `HARD VETO: …` and returning at once: no ATR (no
cost model), **spread cost above `InpScalpMaxSpreadATR` = 0.10 ATR** — the veto
that is specific to scalping, expressed as a ratio of ATR so it is symbol-agnostic
— outside the London/New York kill zones (`IsInSession`, on the closed bar's own
time), and high-impact news (`MTF_SniperIsNewsBlackout`, the existing Golden
Rule 6).

**Verdict.** `SCALP_Decide()` uses the resolver's rule verbatim: both sides voting
⇒ CONFLICT (2) and the score is zeroed; nothing voting ⇒ WAIT with the abstained
legs named; a lone side below `InpScalpMinScore = 60` ⇒ WAIT naming the legs it
missed. A published line reads
`SCALP BUY 75/100 from MOM+SB+CF | stop 0.80 ATR @ … | target 1.20 ATR @ … | RR 1.50
- a weighted confluence count, not a probability`, and records `g_sc_bar` so it
can never be read as live on the next tick.

**What it is not.** Advisory: it writes only the nine `g_sc_*` globals. It never
writes `g_final_signal`, `g_alert_primary`, `g_res_score`, `g_wgate_score` or any
setup, it sends no order, it draws no object, it never touches the forming bar,
and it is deliberately **not** folded into `InpEnableAllModules` — that switch is
pinned to the seven strategy modules, and an advisory overlay is not an eighth
one. With the flag off, the only difference is 320 lines that never execute.

**Self-test.** `SCALP_SelfTest()` runs inside the file's existing
`InpMTEERunSelfTest` block and reports `Scalping strategies self-test: PASS
(10/10)`. Its ten checks exercise the pure cores with values relative to `_Point`,
so they hold on XAUUSD and on any FX pair: no ATR ⇒ veto, zero spread ⇒ no veto,
0.20 ATR spread against a 0.10 cap ⇒ veto, exactly at the cap ⇒ allowed, RR
arithmetic, the weight sum, side scoring both ways, and the three outcomes of the
decide rule.

**Verify.** F7, drop it on **M1 or M5**, set `InpEnableScalping = true` and
`InpScalpShowOnDashboard = true`, then read the tooltip's `Scalp:` line: on a
quiet bar it must say `no scalping strategy voted - abstained: …`; widen the
symbol's spread and it must say `HARD VETO: spread … is … ATR, above the 0.100 ATR
cap - the move would pay the broker`. Set the weights to 25/25/25/25/25/25 and
`OnInit` must refuse with *"Invalid Quantum SMC scalping weights: they must sum to
exactly 100"*.

**Contract suite.** `tools/test_scalping.py` (**CI step 34**) pins all of the
above, including the veto ordering (every veto line must sit above the first
scored point), the reuse claims (no `*_Update(` call inside the vote builder, one
`PA_ZoneAt(` scan, CF's own threshold), the advisory boundary (no write to any
verdict another layer owns) and the preset provenance read straight out of
`QSMC_Preset.mqh`.

## 11.6 AUDIT-OBS1 — the per-bar decision journal (display and audit only)

**The defect this closes.** Phase 1 item F: the file could explain why the *last*
alert was suppressed (`AlertWhyNoPopup`) and could count gate outcomes in
aggregate (`SSignalGateAudit`), but nothing kept a per-bar transcript. On a live
chart an operator could not ask *"what did each layer say on the 09:45 bar, and
which one said no?"* — which is exactly the question the five missed XAUUSD M15
setups of 2026-10-27..29 needed answered. Guessing at a missed setup and
auditing one are different activities; this makes the second one possible.

**What.** `OBS_Record()` (**L6534**) behind `InpEnableDecisionJournal = false`
(**L889**), writing rows of `SObsJournalRow` (**L4785**) into a bounded
**ring buffer** `g_obs_rows[]`. One row per **closed** bar, ten columns:

| Column | Source it is read from | Never re-derived |
|---|---|---|
| `bar_time` | `g_buf_t[closed]` | the bar's own time, so a row cannot be mistaken for *now* |
| `final_signal` / `res_score` | `g_final_signal`, `g_res_score` (AUDIT-RS1) | gated by `InpUseFinalResolver` |
| `gate_state` / `gate_score` | `g_wgate_veto`, `g_wgate_score`, `InpWGMinScore` (AUDIT-GS1) | gated by `InpUseWeightedGates` |
| `scalp_dir` / `scalp_score` | `g_sc_dir`, `g_sc_score` (AUDIT-SC1) | gated by `InpEnableScalping` |
| `primary_dir` / `primary_src` | `g_alert_primary.valid/.direction/.source` | gated by `.valid` |
| `why` | `OBS_Reason()` over the layers' own why-texts | the layers' words, not new ones |

`gate_state` is an `int` (0 not run, 1 PUBLISHED, 2 BELOW-MIN, 3 HARD-VETO) named
by `OBS_GateStateName()`, so the module adds **no new enum** and the pinned enum
count stays at 44. A veto outranks a strong score in `OBS_GateState()` on purpose:
the journal must never read as *95/100 but no trade* without also naming the veto.

**Where it runs, and why that is the load-bearing detail.** Measured order inside
`OnCalculate`: `CF_Update` (L16323) → `RM_Update` (L16328) → `SCALP_Update`
(L16332) → `AlertDispatcherFinalize` (L16348) → `g_final_signal=ResolveFinalSignal`
(L16354) → `g_final_why=rs_why` (L16355) → **`OBS_Record(closed,rates_total)`
(L16361)**. It is recorded LAST, not next to `SCALP_Update`, which would have
transcribed the *previous* bar's resolver verdict and reproduced the stale-citation
defect this module exists to end. The call gate mirrors the resolver's own:
`is_new_bar || detection_updated || prev_calculated==0`.

**The reason precedence** (`OBS_Reason()`, **L6507**) is the order an operator
asks in: a hard veto's own text → thin evidence → `resolver CONFLICT - …` →
`scalp CONFLICT - …` → the resolver's verdict → the overlay's verdict → the
published gate's text → and, when nothing spoke,
`no layer produced a verdict this bar`. Silence is reported as silence.

**One honesty fix, recorded because it was mine.** The first draft mapped the
alert source as `3=CORE, 2=RXN, else ZRE`. The `else` was an assumption and it was
wrong: the dispatcher's own field says `int source; // 1=ZRE, 2=RXN, 3=CORE legacy`
(L4223) and `AlertCandidateInit` sets `source=0` for an unused candidate. So the
mapping became a pure core, `OBS_SourceName()` (**L6524**): 3=CORE, 2=RXN, 1=ZRE,
anything else `unset`. A transcript that invents a source is worse than no
transcript.

**Bounds.** `InpObsJournalBars` keeps 10–500 rows and `InpObsTooltipBars` shows at
most that many, newest first; `OnInit` **refuses** an impossible combination with
`INIT_PARAMETERS_INCORRECT` rather than clamping silently, because a tooltip asking
for more rows than the buffer keeps would display rows that do not exist.
`InpObsLogEvents` (default `false`) prints `QSMC OBS …` **only** for a bar where
something actually decided, so it cannot become the per-bar flood the release gate
forbids.

**What it is NOT.** It decides nothing, draws no object, holds no price series,
adds no plot buffer, authorises no entry and sends no order. It assigns only its
own four `g_obs_*` globals and reads only state the layers already published — a
**transcript, not a voter**, and never a fifth opinion. It is deliberately *not*
folded into `InpEnableAllModules`, which stays pinned to the seven strategy modules.

**Self-test.** `OBS_SelfTest()` (**L6612**) runs eleven deterministic checks
(OBS-1…OBS-11) over the pure cores only — ring wrap, non-positive cap, all four
state names plus an unknown one, not-run beating 95 points, a veto beating 95
points, the inclusive minimum from both sides, veto text outranking a resolver
verdict, both conflict labels, silence, and the source names. It touches no chart,
no series and no journal state, and it is hooked into the file's existing general
switch `InpMTEERunSelfTest` (L15537, after the scalping hook).

**Contract suite.** `tools/test_decision_journal.py` (**CI step 35**) pins all of
the above: the exact input lines, the struct's ten columns and their order, the
five pure cores line by line, the reuse claims (no `PA_ZoneAt(`, no `IsInSession(`,
no `ResolveFinalSignal(`, no `WeightedGateAllows(`, no ATR of its own), the record
discipline, the advisory boundary, the OnCalculate ordering chain, the eleven
self-test checks, and the counts (45 664 lines · **583** inputs · 3 821 braces ·
44 enums).

**What this does NOT prove.** A transcript makes a missed setup explainable; it
does not make the strategy profitable, and it does not detect the five setups by
itself. That still needs the user's F7 compile and a Strategy Tester log on real
XAUUSD M15 data. This module was never compiled here — no MetaEditor exists in the
sandbox — so every claim above is a claim about the source text, measured.

## 12. Known risks and what is NOT implemented

**Compilation.** F7 has now been run once (§11.1): 42 errors from a single
missing `//`, fixed, and the file rescanned lexically with zero further prose
lines found. **A second F7 is still required to confirm the build is clean** —
MQL5 may have stopped reporting at the first broken construct, and type errors,
arity slips and undeclared identifiers remain invisible offline. This is still
the single largest outstanding risk.

**Risk percentage is 1.50, not 1.0** (§3.7). Deliberate, and the most
consequential deviation from the brief.

**Two switches change existing behaviour** (§2.3): `InpPARequireZoneContext` and
`InpOBZoneBodyOnly`. Both default off and both are verified inert while off, but
they are not purely additive.

**`InpRMUseRRFloor` and `InpRMPreferTopDownPlan` default `true`.** The module
itself is behind `InpEnableRiskModel=false`, so nothing changes until you enable
it — but once enabled, those two behaviours are on by default. Flagged because
the standing rule is that new flags default false.

**Not implemented, by design:**

- TP2/TP3 are **not** chain-derived. TopDown publishes only `tp1`, so on the
  `TOPDOWN` path TP2/TP3 extend as 2R/3R.
- Break-even and trailing are **not** republished by the Risk Model. The Sniper
  model computes them; they describe post-entry management, outside the brief.
- No order placement, no bracket management, no partial-close simulation.
- No spread, commission or swap in the R:R calculation.
- No volatility-adjusted or Kelly-style sizing; no per-symbol lot-step
  normalisation (output is advisory text, so raw units are reported).
- Wyckoff: no PS/SC/AR/ST/SOS/LPS/UTAD phases, no retest logic, no entry/SL/TP.
- Mean reversion: hidden divergence is detected but reported only as `CONFLICT`,
  never traded.
- Confluence: no renormalisation of bad weights, by design (§3.6).

**Deliberately abandoned** — retrying any of these would violate the standing
constraints: unifying the three candle implementations (C1), "fixing" the 1.1000
weight sums (C3), modifying the `ScoreSession`/`ScoreHTF` floors globally (C4),
adding `iBands` or mean-centring σ, letting MACD award points, adding a CF or RM
row to the saturated 11-row card, inventing `InpMinRR`/`InpRiskPercent`, or
building a second SL/TP model beside `MTF_SniperComputeTradeManagement`.

---

## 13. Open decisions for the operator

1. **`v6.6.13` marker vs a real version bump.** The release triple is still
   `v6.6.9` / `"6.69"`. Sixty-seven inputs and seven modules shipped without a
   version change. Bumping it is a release decision, and `check_release_gate.py`
   G1 requires the `#property version`, `QSMC_VERSION_TEXT`, the
   `QSMC_Root.mqh` banner **and** `docs/QSMC_BUILD_AND_RUN.md`'s title to move
   together — all four, or the gate fails.
2. **C1** — the doji/bullish-pin-bar divergence in the C1 entry gate. Pinned, not
   repaired.
3. **C3** — the existing weights summing to 1.1000.
4. **C4** — the two free-point floors. Neutralised locally in the new engine; the
   existing score still carries them.
5. **C6** — accept 1.50% as the advisory risk percentage, or decide to change
   `InpSniperMaxRiskPct` (which would also change the Sniper model).
6. **`InpPARequireZoneContext`** — whether to turn the soft zone gate into a hard
   one, which tightens existing behaviour.

---

## 14. Reference

- Pull request **#15** — `karimwer966-creator/terad`, 11 commits, `mergeable_state: clean`
- Prior deliverable: `docs/QSMC_V6.6.10_TACTICAL_AUTHORITY.md`
- Operational runbook: `docs/QSMC_BUILD_AND_RUN.md` (titled **v6.6.9** — matches the triple)
- Production checklist: `docs/QSMC_PRODUCTION_CHECKLIST.md`
- Execution companion (the only file permitted to reach the trade API):
  `MQL5/Experts/QSMC_AutoTrader.mq5`
