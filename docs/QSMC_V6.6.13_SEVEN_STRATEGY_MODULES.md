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

### 3.2 Phase 2 — Power of 3 + Silver Bullet (14 inputs, L870–882)

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

### 3.3 Phase 3 — Wyckoff Spring / Upthrust (10 inputs, L892–903)

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

### 3.4 Phase 4 — Pure Price Action (7 inputs, L913–923)

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
(def **L5577**) is already the single function returning pattern type plus
strength. What was genuinely missing was **Inside Bar** and the **zone rule**,
and those are what Phase 4 added. Three candle implementations still coexist in
the file — see §8, C1.

`PA_ResolveDirection`: `if(!in_zone) return 0;` → conflict → `0` →
`pattern_dir` → `zone_dir`. `PA_Score`: `if(!in_zone) return 0;` →
`25 + round(strength*0.45) + (agrees ? 30 : 0)`.

### 3.5 Phase 5 — Mean Reversion / Momentum (13 inputs, L933–948)

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

### 3.6 Phase 6 — Confluence Engine (11 inputs, L958–969)

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

### 3.7 Phase 7 — Risk Model (8 inputs, L970–977)

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
| `InpMinRR` | `InpTopDownMinRR` (**L1166**) — *"hard R:R floor (policy: never below 1:2)"* | `2.0` |
| `InpRiskPercent` | `InpSniperMaxRiskPct` (**L1815**) — *"Advisory equity risk % per trade (1.0–2.0%)"* | **`1.50`** |

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
| OB1 | *(existing OB structs)* | L5457 | L17540 | inline in the detection loop | *(none — reuses the OB suite)* |
| SB1 / P3 | L1930 / L1945 | L5668 | L24588 | L24716 / L24892 | `PASS (9/9)` @L14921 |
| WY1 | L1960 | L5695 | L25167 | L25356 | `PASS (9/9)` @L14925 |
| PA1 | L1984 | L5714 | L25606 | L25832 | `PASS (9/9)` @L14929 |
| MR1 | L2003 | L5732 | L26029 | L26287 | `PASS (9/9)` @L14933 |
| CF1 | L2028 | L5751 | L26630 | L26795 | `PASS (10/10)` @L14937 |
| RM1 | L2061 | L5769 | L27126 | L27352 | `PASS (10/10)` @L14941 |

**Six self-tests, 56 in-file checks** (9+9+9+9+10+10), all gated by the existing
`InpMTEERunSelfTest` — no new gate was introduced. Phase 1 added no self-test
because it completed an existing engine rather than adding one.

Supporting anchors, all verified at `ebc43bc`:

| Thing | Line |
|---|---|
| `#property indicator_buffers 19` / `indicator_plots 7` | L627 / L628 |
| `enum ENUM_P3_PHASE` / `enum ENUM_WYCKOFF_EVENT` | L747 / L757 |
| `SNIPER_SL_BUFFER_ATR 0.30` / `SL_HARD_MAX_H1_ATR 2.00` / `BE_DISP_ATR 2.00` / `TRAIL_M15_ATR 0.50` | L1859–1862 |
| `struct STopDownState` | L1893 |
| `InpUseHTFBias` / `InpTopDownMinRR` / `InpMTEERunSelfTest` / `InpSniperMaxRiskPct` | L1151 / L1166 / L1805 / L1815 |
| `InpLogLifecycleTransitions` | L1262 |
| `ScoreStructure` / `ScoreLiquidity` / `ScoreSession` / `ScoreHTF` (defs) | L17499 / L17520 / L17651 / L17660 |
| `CalculateAITradeSetup` (def) — the only writer of `g_score` | L20593 |
| `TheoreticalRiskMoney` (def) | L22836 |
| `PA_ZoneAt` (def) | L25762 |
| `TopDown_Evaluate` (def); its existing R:R gate | L33798; L33990–33992 |
| `TopDown_Update` (def) | L34029 |
| Module self-tests (SB / WY / PA / MR / CF / RM) | L25029 / L25500 / L25904 / L26444 / L26948 / L27549 |

Every self-test exercises **pure cores with local values only**. None reads
series data, account data or tick data, so all six are deterministic in the
Strategy Tester and on any symbol.

---

## 5. The causal order inside `OnCalculate`

`OnCalculate` begins at **L15113**. The relevant call order, verified:

```
L15357  OB age bound            inline, LAST within the closed bar (price outranks time)
L15471  P3_Update(closed)
L15472  SB_Update(closed)
L15476  WY_Update(closed)
L15532  TopDown_Update(rates_total,false)   <-- publishes the plan RM may adopt
L15554  PMI_Update()
L15704  MVP_Update(...)                     <-- volume profile / POC
L15713  PA_Update(closed)
L15721  MR_Update(closed,rates_total,full_indicators)
L15727  CF_Update(closed,rates_total)       <-- reads PA, MR, WY, P3, SB
L15732  RM_Update(closed,rates_total)       <-- reads CF's verdict + TopDown's plan
L15735  ZRE_Update(...)
```

Two properties this order guarantees:

1. **`RM_Update` runs after both `CF_Update` and `TopDown_Update`**, so the
   verdict it attaches to and the plan it may adopt are both fresh for this bar.
2. **Every module call is under `if(is_new_bar || detection_updated)`**, so no
   module recomputes on every tick. Combined with the `prev_calculated` delta
   approach, there is no full-history loop per tick anywhere in this work.

Each module's driver calls its own `Clear()` **as its first statement**, then
early-exits. A disabled or blocked module can therefore never leave a previous
bar's verdict on the dashboard. `RM_Clear()` is also called in `OnInit` (L14908)
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
| L33093 | CF summary — **first**, ahead of the per-module detail |
| L33124 | RM advisory |
| L33152 | Power of 3 |
| L33164 | Silver Bullet |
| L33181 | Wyckoff |
| L33201 | Price Action |
| L33219 | Mean Reversion |

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
`AnalyzeClosedCandle` (def **L5577**), `AnalyzeCandleIntelligence` (decl L2621,
def **L19574**) and `MTF_SniperEvaluateEntryTriggers` (decl L6531, def **L44217** —
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
`final_score` branches (assignments at **L21057–21081**) do this — the default branch
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

**C5 — `AUDIT-MR1`: two divergence helpers were dead code.** `IsFractalHigh` (def **L34521**),
`IsFractalLow` (def **L34532**) and `FractalRightBars` (def **L23575**) had a declaration and a definition and **no caller**. Phase 5 wired them
in rather than writing a fourth swing detector.

**C6 — `AUDIT-RM1`: the named inputs do not exist.** See §3.7. Reused, not
invented; the reported risk percentage is **1.50, not 1.0**.

**C7 — `AUDIT-RM1`: a complete risk model already existed.**
`MTF_SniperComputeTradeManagement` (decl L6532, def **L44370–44483**) already computes entry, a stop
behind the zone or the opposing swing, a hard ATR cap that yields
`SKIP_SL_MAX`, TP1/2/3 from the nearest opposing zone / HTF zone / D1-W1
liquidity with 1R/2R/3R fallback, break-even, trailing and `rec_lot_size`. The
TopDown chain already builds opposing targets and rejects below
`InpTopDownMinRR`. `STopDownState`'s own header comment says its published tuple
exists so a downstream planner can *"reconcile ITS zone with the chain's zone
instead of re-deriving (and possibly contradicting) it"*. **Phase 7 is that
planner**, and adopts the chain's plan verbatim when directions agree.

**C8 — buffers 7–12 already carry Entry/SL/TP1/TP2/TP3** per signal, via
`SigLog_BufWrite` (def **L13972**), with ZRE using 13–18. Phase 7 did not need a buffer
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
| Inputs | 548 total, 67 new, all new ones default `false` where behavioural | release gate + suites |

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

Full gate: **5 static tools PASS · 23 suites · 2 437 PASS lines · 0 failures**.
CI: **30 steps**, `.github/workflows/qsmc-verify.yml`.

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
real declaration near L1941–1958 — and finally `expressions are not allowed on a
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
