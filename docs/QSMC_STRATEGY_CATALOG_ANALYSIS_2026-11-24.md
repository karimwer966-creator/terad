# QSMC × the TradeZella strategy library — a cross-map and adoption assessment

**Date:** 2026-11-24 · **Branch:** `arena/d1c9ca46-terad` · **Status:** analysis only — no code changed, nothing compiled, no trading-authority claim
**Trigger:** the owner attached the strategy catalog of the TradeZella library (49 strategy pages; the pasted listing also names the `_listing` index page) together with `strategies.csv` (full bodies) and `digest_01…05.md` (extractions). This document is the engineering review of that material against this repository.
**Source data (not in this repo, intentionally):** `strategies.csv` — 49 rows, ≈906,617 characters of page text; each row carries slug, author, title, `tradezella.com/strategies/<slug>` URL, card description, extracted timeframes/R-multiples and the entry/exit/stop/risk/context bodies.

## 1. What this document is — and is not

- It **is** a map from every cataloged strategy onto what QSMC CORE v6.6.24 (this repository) already has, a ranked shortlist of what is worth specifying, and a rejection list with reasons.
- It is **not** evidence that any of these playbooks is profitable. Nothing here was backtested on XAUUSD; nothing here was compiled; no MQL5 file was modified by this analysis.
- It is **not** a specification for any module. Any candidate below gets its own spec + owner approval before implementation.
- Strategy bodies are **not republished** here. Descriptions are condensed paraphrase with slug/author/URL for identification; the reader is pointed at the sources. The texts are third-party commercial content; see §8.
- QSMC facts are cited by file and module name (stable), not by line number, except where a boundary was quoted in an existing committed audit doc.

## 2. The condition of the source data (read this before trusting any number)

Automated audit of `strategies.csv`:

- **49 rows, 49 unique slugs.** The pasted listing has 50 lines: 49 strategies + `_listing` (an index page titled "Jumpstart profitability with ready-made Strategies"), which is not a strategy and is excluded from the map.
- **40 of 49 rows carry "lorem ipsum …" boilerplate** in the `other` column (scraped page chrome). In **9 rows** the placeholder text appears **inside the MARKETS section itself**: `institutional-order-flow-iceberg-trading-strategy`, `price-cycle-continuation-failed-base-strategy`, `futures-trading-strategy`, `universal-strategy`, `structure-ote`, `nexus-blast-strategy`, `buyer-led-directional-auction`, `auction-market-theory` (Rajan Dhall), `low-volume-node`.
- Several MARKETS sections contain **cross-promo copy for a different strategy or an "Overview Lorem ipsum" template** (e.g. the iceberg playbook's MARKETS section pitches "The Vix Futures Strategy"; the index-fingerprinted cross-links repeat across pages). The library appears to be assembled automatically, not hand-verified.
- `5-stage-trading-framework` has an **empty CONTEXT section** (it is a mindset/curriculum page, not a setup).
- **All 49 pages contain the string "win rate"** — overwhelmingly as TradeZella's boilerplate FAQ ("your win rate, profit factor, and expectancy"), never as verified, source-linked statistics. The only concrete win-rate-style numbers in the library are author claims: `unique-high-rr` (TG Capital) "around 90% when all rules are followed"; `trendline-break-pocket-strategy` and `episode-pivot-strategy` ~58% (the ~58% figure appears on 2/49 pages); `multiple-edge-trading-system` 40–50%; `super-stock-momentum-trading-strategy` ~30–50%; `price-cycle-continuation-failed-base-strategy` ~70% reaction rate. These are vendor marketing claims with no verifiable sample size or methodology attached; none has been backtested here.
- **35 of 49 pages carry the identical "11+ years" backtesting FAQ boilerplate**; 3 of 49 carry Chart Academy cross-promo (`momentum-model-performance-development`, `small-cap-short-strategy`, `auction-market-strategy`). Other `90%` occurrences in the data are not win rates (e.g. `the-vix-futures-strategy`: "About 90% of ES volume is algorithms"; `po3-ote-adr`: stop "at the 0.90 level (90%)"; `trendline-break-pocket-strategy`: removes "90% of the 'fake trendline breaks'"). This pattern confirms the library is template-assembled, not individually authored/verified.
- **No verified performance statistics exist anywhere in the data** — only author-claimed R-multiples and the marketing/boilerplate above, plus timeframe/time tags (`TF seen` / `R seen`) extracted by regex. Where the table below mentions sessions/kill zones, that is the *playbook's* claim about when it trades, not a measured result.
- Conclusion for any future work: the catalog can supply **mechanics and vocabulary**, never evidence. Anything adopted must be specified, built, and measured inside this repository (demo first), or not adopted at all.

## 3. How to read the map (§4)

**Coverage** (how much of the strategy's *idea* exists as working QSMC surface):

| Class | Meaning |
|---|---|
| **S** | Substantially built — QSMC already has the engine/module; adoption is wiring and naming, not research |
| **P** | Partial — an engine exists, but a named model state/leg is missing |
| **W** | Weak proxy only — approximations exist (candle-body "signed" volume, tick volume), not the real evidence |
| **N** | Absent — the domain or the data does not exist in this build |

**Fit for XAUUSD on MT5** (this repo's instrument and platform): **H** high · **M** moderate · **L** low · **—** not applicable.

Neither column is a trading opinion. `H` means "implementable and meaningful here", nothing more.

## 4. The full map (49/49)

| # | Strategy (author) | Venue · style | What it is — own words | QSMC surface | Cov | Fit | Disposition |
|---|---|---|---|---|---|---|---|
| 1 | [volume-profile-order-flow-trading-strategy](https://www.tradezella.com/strategies/volume-profile-order-flow-trading-strategy) (Casper) | index futures · scalp/day | forced-participation entries at high-activity prices: absorption or a 2-minute structure shift, structure-based stop, **no fixed take-profit** — manage at significant levels and trail by structure; volume profile as the map | `QSMC_SvpVolumeProfile.mqh` (POC/VAH/VAL/HVN/LVN, session/daily windows, tick-volume basis), `absorption_behavior` (Candle Intelligence), `AnalyzeClosedCandle` structure shifts, EA partials/break-even | P | M | **A1** |
| 2 | [auction-market-theory-institutional-order-flow-trading-strategy](https://www.tradezella.com/strategies/auction-market-theory-institutional-order-flow-trading-strategy) (Imre Gams) | index futures · scalp/day | balanced market → value-area rotation; failed auction or confirmed breakout continuation, order-flow absorption confirmation | same stack; no failed-auction state, no delta | P | M | **A1** |
| 3 | [institutional-order-flow-iceberg-trading-strategy](https://www.tradezella.com/strategies/institutional-order-flow-iceberg-trading-strategy) (Scott Pulcini) | liquid index futures · day | iceberg/stop-run detection; ATR-extension entries reverting toward the event zone | no order book; stop-run/pool machinery exists; absorption is candle-body proxy | N/W | L | **Reject** — order-book leg impossible; steal only the ATR-extension idea via #21 if wanted |
| 4 | [multiple-edge-trading-system](https://www.tradezella.com/strategies/multiple-edge-trading-system) (Jlaw) | stocks · swing | never one reason: independently aligned edges (catalyst, momentum, RS, base breakout) at the same area | QSMC's gate architecture is multi-edge mechanically; the catalyst/RS legs are equity-only | P/N | L | **Reject** |
| 5 | [super-stock-momentum-trading-strategy](https://www.tradezella.com/strategies/super-stock-momentum-trading-strategy) (Connor Bates) | stocks · position | multi-week bases in high-RS thematic names, six entry setups | none | N | L | **Reject** |
| 6 | [fair-pricing-theory-strategy](https://www.tradezella.com/strategies/fair-pricing-theory-strategy) (JJ Simon) | index futures · 1m | displacement candle around session opens/news; revert-or-continue decision, prop-style fixed ratios | displacement axis in ranking; sessions; MTF news blackout | P | M | **A3** (pattern only) |
| 7 | [nq-liquidity-sweep-reversal-scalping-strategy](https://www.tradezella.com/strategies/nq-liquidity-sweep-reversal-scalping-strategy) (Candace Lau) | NQ futures · scalp | HTF context → premium/discount → liquidity pool sweep → IFVG + displacement + speed → ≥1:2 | premium/discount (price-location vector), sweep, FVG, OTE engine | P | M | **B1/A2** |
| 8 | [price-cycle-continuation-failed-base-strategy](https://www.tradezella.com/strategies/price-cycle-continuation-failed-base-strategy) (Clement Ang) | stocks · swing | RS-driven cycle: continuation out of bases; short leaders into failed bases | none (equity universe) | N | L | **Reject** |
| 9 | [trading-first-principles-framework](https://www.tradezella.com/strategies/trading-first-principles-framework) (Pavel) | framework | where an edge comes from; market/horizon selection | not a setup | N | — | **Reference-only** |
| 10 | [price-action-strategy](https://www.tradezella.com/strategies/price-action-strategy) (Gala Trades) | stocks/options/futures · intraday | HTF direction + hourly key levels + LTF confirmation at the level | `AUDIT-PA1` zones + reaction scoring | P/S | H | **Overlap audit** — reuse PA1, do not build a parallel module |
| 11 | [momentum-model-performance-development](https://www.tradezella.com/strategies/momentum-model-performance-development) (Jeff Holden) | meta | feedback loop for trading development (track → five whys → fix → stack wins) | not a setup | N | — | **Reference-only** |
| 12 | [liquidity-inversion-model](https://www.tradezella.com/strategies/liquidity-inversion-model) (Dhesi) | futures · day | D1/monthly draw on liquidity → sweep → FVG inversion (HTF) → LTF inversion entry | causal chain covers sweep→FVG; **inversion as a first-class state does not exist**; OTE exists | P | H | **B1** |
| 13 | [small-cap-short-strategy](https://www.tradezella.com/strategies/small-cap-short-strategy) (Steven Dux) | small-cap equities · day | short hype exhaustion: gap-up short / bounce short / first red day; statistics-first | equity/borrow mechanics | N | L | **Reject** |
| 14 | [stage-analysis](https://www.tradezella.com/strategies/stage-analysis) (Ted Zhang) | stocks · swing/position | Weinstein stages + 10/20/30/40-week MAs; buy Stage 2 bases | not this horizon; no MA-10w/20w concept | W | L | **Reject** |
| 15 | [nasdaq-ict-and-order-flow-scalping-strategy](https://www.tradezella.com/strategies/nasdaq-ict-and-order-flow-scalping-strategy) (Abraham Perez) | NQ futures · scalp | ICT trigger (sweep → IFVG/retest) + Bookmap absorption/aggression confirm | ICT chain present; **Bookmap/footprint leg unavailable**; absorption = candle-body proxy | P/W | M | **A2** (Bookmap leg excluded, proxy noted) |
| 16 | [order-flow-strategy](https://www.tradezella.com/strategies/order-flow-strategy) (Trader Yush) | futures · scalp | rotation framework: range edges, trapped participants, add-to-winners, BE early | VP edges; Wyckoff ranges; absorption proxy; no delta | W | M | **A1** (observation only; delta unavailable) |
| 17 | [80-20-nasdaq-strategy](https://www.tradezella.com/strategies/80-20-nasdaq-strategy) (Okala) | NQ · intraday | reactions at .20/.80 prices ("Fork" reversal etc.) | no psychological-level grid | W/N | L | **Reject** (instrument-specific tick pattern) |
| 18 | [auction-market-theory-strategy](https://www.tradezella.com/strategies/auction-market-theory-strategy) (Andrea Cimitan) | futures · day | acceptance vs rejection at the value edge; aggressive vs passive behavior; 2R | vp engine + reactions; accept/reject classification absent | P | M | **A1** |
| 19 | [measured-move-trend-strategy](https://www.tradezella.com/strategies/measured-move-trend-strategy) (Marci Silfrain) | stocks/futures · swing | measured-move projections ("Little RZY") + Bollinger context | no projection tool; Bollinger absent | N | L | **Reject** |
| 20 | [parabolic-short-strategy](https://www.tradezella.com/strategies/parabolic-short-strategy) (Marios Stamatoudis) | stocks · day | exhaustion top shorts; confirmation entries; round-number context | equity-specific | N | L | **Reject** |
| 21 | [mean-reversion-strategy](https://www.tradezella.com/strategies/mean-reversion-strategy) (Lance Breitstein) | stocks · day | capitulation: calm → violent extension → equilibrium (20-MA / Bollinger center); EV framing | `AUDIT-MR1` (VWAP-σ stretch + RSI divergence + MACD veto); `absorption_behavior` | P | H | **A3** |
| 22 | [futures-trading-strategy](https://www.tradezella.com/strategies/futures-trading-strategy) (Anthony Crudele) | index futures · swing | Bollinger(20,3σ) environment → consolidation/expansion/pullback posture | volatility regime exists (`g_sc_*` scaling); **Bollinger absent** | P | M | **B3** |
| 23 | [volume-profile-strategy](https://www.tradezella.com/strategies/volume-profile-strategy) (Forrest Knight) | options/futures · day/swing | VAH/VAL/POC edge touch + high-volume rejection candle; HVN = sticky, LVN = fast travel | vp engine; no edge-touch playbook | P | H | **A1** |
| 24 | [episode-pivot-strategy](https://www.tradezella.com/strategies/episode-pivot-strategy) (Pradeep Bonde) | stocks · swing | episodic pivot: catalyst gap reprices ignored stock 50–300% | needs news/fundamental screener | N | L | **Reject** |
| 25 | [shorting-strategy](https://www.tradezella.com/strategies/shorting-strategy) (Kris Verma) | small-cap equities · day | fade post-hype gap-ups; wide stops, structured management | equity squeeze mechanics | N | L | **Reject** |
| 26 | [universal-strategy](https://www.tradezella.com/strategies/universal-strategy) (Traveling Trader) | any market · framework | liquidity → displacement → retrace → continue; checklist not setup | **this is the QSMC causal chain verbatim** (Sweep → Displacement → MSS → OB/FVG → Retest → LTF) | S | H | **No code action** — validates the architecture |
| 27 | [trendline-break-pocket-strategy](https://www.tradezella.com/strategies/trendline-break-pocket-strategy) (Ali Crooks) | forex · 4H swing | trendline break + final-swing break → 21-EMA pullback, fixed 2R | drawn trendlines absent by design; EMA overlay exists | N | M | **Reject** (fragile lines; fixed 2R) |
| 28 | [market-dna-strategy](https://www.tradezella.com/strategies/market-dna-strategy) (Jay Awtani) | stocks · day/swing | "DNA zone" + tape aggression on catalyst; ≥3:1 RR | needs L2/tape data | N | L | **Reject** |
| 29 | [auction-market-strategy](https://www.tradezella.com/strategies/auction-market-strategy) (Fabio Valentini) | futures · day | two models: imbalance breakout-continuation; balance reversion to POC | A1 family | P | M | **A1** |
| 30 | [structure-ote](https://www.tradezella.com/strategies/structure-ote) (Trader Mayne) | forex/futures · swing | HTF BOS → POI (OB, premium/discount) → OTE pullback entry | BOS/OB/OTE engines all exist; no named playbook | S | H | **A2** |
| 31 | [po3-ote-adr](https://www.tradezella.com/strategies/po3-ote-adr) (NBB Trader) | forex · swing | market-maker model (acc/manip/dist) + OTE + ADR playbook; London/NY sessions | P3/SB1 exists; OTE exists; **ADR projection absent** | S/P | H | **A2** (ADR optional) |
| 32 | [first-red-day-2](https://www.tradezella.com/strategies/first-red-day-2) (Kyle Wiiliams) | small caps · day | first red day after parabolic advance | equity | N | L | **Reject** |
| 33 | [first-red-day](https://www.tradezella.com/strategies/first-red-day) (Alex Temiz) | small caps · day | first red day after multi-day run | equity | N | L | **Reject** |
| 34 | [nexus-blast-strategy](https://www.tradezella.com/strategies/nexus-blast-strategy) (Joshua Cutler) | ES · 5m | NY/London session liquidity grab + BOS + FVG limit entry; 1R/2R | session H/L, FVG, retest machinery; named playbook absent | S | H | **A2** |
| 35 | [ifvg-trading-model](https://www.tradezella.com/strategies/ifvg-trading-model) (Joshua Cutler) | NQ+ES · NY only | SMT divergence + FVG inversion from sweep | **IFVG inversion absent; SMT needs a correlated pair — XAUUSD has none** | N/W | L | **Reject** the pair requirement; IFVG leg via **B1** |
| 36 | [buyer-led-directional-auction](https://www.tradezella.com/strategies/buyer-led-directional-auction) (Nouman Asjad) | futures/indices · day | directional auction (trend day) out of balance; delta + absorption confirm | imbalance mechanics; absorption proxy; no delta | P/W | M | **A1** (confirmation variant) |
| 37 | [5-stage-trading-framework](https://www.tradezella.com/strategies/5-stage-trading-framework) (Umar Ashraf) | framework | 5-stage trader development roadmap | not a setup; source CONTEXT is empty | N | — | **Reference-only** |
| 38 | [intraday-liquidity-volatility-model](https://www.tradezella.com/strategies/intraday-liquidity-volatility-model) (Jade Cap) | futures/forex · day | session-level liquidity raid + FVG/MSS/divergence confirmation | causal chain + sessions + SB1/P3 | S | H | **A2** |
| 39 | [auction-market-theory](https://www.tradezella.com/strategies/auction-market-theory) (Rajan Dhall) | stocks/futures · scalp/day | prior-day value rejected on 5m after daily bias aligned | A1 family | P | M | **A1** |
| 40 | [low-volume-node](https://www.tradezella.com/strategies/low-volume-node) (Carmine Rosato) | liquid futures · scalp | LVN reload/defense confirm by footprint/delta/heatmap | **LVN exists in the profile engine**; confirmation needs book/footprint | W | M | **A1** (level tag only, no confirmation claim) |
| 41 | [smt-divergence-po3](https://www.tradezella.com/strategies/smt-divergence-po3) (Trader kane) | NQ/ES · scalp | D→4H→1H PO3 + SMT divergence; 50%-of-range targets | PO3 exists; **SMT absent** (needs pair); 50% target = OTE equilibrium | W | L | **Reject** SMT leg; OTE equilibrium covers the target |
| 42 | [unique-high-rr](https://www.tradezella.com/strategies/unique-high-rr) (TG Capital) | **gold futures** · 30m | London kill zone "Trident": FVG + doji wick into FVG 50%; stop below the FVG candle's low; the author uses **no hard stop on gold**; daily-EMA trend exit; claims 10R+ | London session exists; FVG/OTE present; Trident pattern specifiable; **the stop rule contradicts QSMC's risk model — see §7.3** | P | H | **B2 — spec only, owner decision** |
| 43 | [real-simple-strategy](https://www.tradezella.com/strategies/real-simple-strategy) (Real Simple Ariel) | stocks · swing | ORB + high-volume close + sector RS | needs universe screener | N | L | **Reject** |
| 44 | [amd-model](https://www.tradezella.com/strategies/amd-model) (Tanja Trades) | NQ futures · day | AMD manipulation → retrace into valid FVG; "macro windows" ≈ news blackout; correlation check | AMD/P3 engine; FVG; MTF news blackout; correlation feed absent | S/P | H | **A2** (XAU adaptation; correlation leg optional) |
| 45 | [trendline-strategy](https://www.tradezella.com/strategies/trendline-strategy) (Tori Trades) | 4H · swing | trendline touch entry (2–3 touchpoints) | trendlines absent by design | N | M | **Reject** |
| 46 | [support-and-resistance](https://www.tradezella.com/strategies/support-and-resistance) (Brando Elite) | options · swing | HTF S/R + catalyst; "size for zero" sizing | options/catalyst; absent | N | L | **Reject** |
| 47 | [break-retest](https://www.tradezella.com/strategies/break-retest) (Vincent Desiano) | stocks/futures · day | PDH/level break → retest "battle zone" → confirmation candle; partial at TP1 | retest leg exists; PDH/PDL canonical refs exist; EA partial logic | S | H | **A2** |
| 48 | [the-vix-futures-strategy](https://www.tradezella.com/strategies/the-vix-futures-strategy) (Dylan O'Neil) | futures (VIX/ES/NQ) · day | VIX double-bottom + failed ES/NQ breakout reversion; EOW seasonality | needs a VIX feed | N | L | **Reject** |
| 49 | [liquidity-strategy](https://www.tradezella.com/strategies/liquidity-strategy) (Marco Trades) | futures/forex/crypto · day | sweep → trap → reversal; target next respected liquidity; partials only at liquidity | sweep/trap machinery; liquidity targeting; EA partials | S | H | **A2** |

*(Rows 10 and 26 have near-full overlap with existing QSMC behavior; they are listed for completeness, not as work.)*

## 5. What QSMC already embodies — module cross-walk

The catalog is largely the public, discretionary restatement of the same SMC/AMT concepts QSMC has been engineered around. The cross-walk (catalog ids refer to §4):

| QSMC surface (file/module) | Role | Catalog strategies living there |
|---|---|---|
| **Power of 3 / Silver Bullet** (`AUDIT-SB1`, `DetectJudasSwing`, Silver Bullet query) | Asia accumulation → London/NY manipulation → distribution; Judas-swing skip | #31 PO3+OTE+ADR, #34 Nexus Blast, #38 Intraday Liquidity & Volatility, #41 SMT+PO3 (partial), #42 unique-high-rr (kill zone), #44 AMD Model |
| **Causal chain + retest** (Sweep → Displacement → MSS → OB/FVG → Retest → LTF; ranking axes) | The pipeline every entry candidate passes | #7 NQ Sweep, #12 Liquidity Inversion, #15 Perez (ICT leg), #26 Universal, #38, #47 Break & Retest, #49 Liquidity Strategy |
| **FVG / OB engines** (`TryDetectFVGAt`, OB lifecycle) | The imbalance legs | #7, #12, #30 Structure+OTE, #31, #34, #44, #47; **inversion state missing** (#7, #12, #35) |
| **OTE tool** (`InpOTEFibStart=0.618`…`0.79`, `InpShowOTE`, OTE inputs) | OTE pullback entries | #30, #31, #44, and the 50%-target of #41 (via equilibrium, not SMT) |
| **Volume Profile (SVP)** (`QSMC_SvpVolumeProfile.mqh`; Master Volume Profile, observational) | Volume-at-price context; POC/VAH/VAL/HVN/LVN | #1 Casper, #2 Gams, #18 Cimitan, #23 Knight, #29 Valentini, #36 Asjad, #39 R. Dhall, #40 LVN (tag only) |
| **Mean Reversion (MR1)** (VWAP-σ stretch + RSI divergence + MACD veto) | Stretch-then-revert evidence | #6 Simon (displacement pattern leg), #21 Breitstein, #22 Crudele (B3 environment tag proposal) |
| **Price Action (PA1)** (zones + reaction scoring) | Key-level reactions | #10 Gala (reuse; do not duplicate) |
| **Wyckoff (WY1)** (range spring/upthrust) | Range-edge reversion in a tight range | #16 Yush (partially; the absorption leg) |
| **Reaction Confluence / Confluence Engine** | Weighted evidence fusion | #26 (umbrella), #15 (as weighting, Bookmap leg excluded) |
| **Causal invariant + replay audit** (v6.6.24 P0-3: tri-state verdicts) | The measurement discipline any adoption must pass | applies to every candidate; nothing ships without it |
| **Risk Model (RM1)** & EA partials/BE (`InpPartialCloseAtR`, `InpBreakEvenAtR`, `InpPartialClosePercent`) | Risk budget mechanics | contradicted by #42's no-hard-stop rule (§7.3) — that rule must NOT ship |
| **Sessions + news blackout** (SB1 sessions, `MTF_SniperIsNewsBlackout`, Golden Rule 6 ±30m) | When trading is allowed | #6, #31, #38, #42 (London kill zone), #44 ("macro windows"), #47 |
| **Gates & ceilings** | Hard stops on risk | #4 (concept only; equity legs absent) |
| **Opportunity Funnel (P0-5, pending owner approval)** | Per-bar staged rejection trace | **the measurement prerequisite for wiring any A-tier playbook into authority** |

## 6. Ranked candidates — what is actually worth building

Ordering is by (value × fit × risk), not by the catalog's popularity. Everything is **display-only first**; entry-authority wiring is a separate, owner-approved step gated by P0-5 measurement and demo observation.

### Tier A — adoptable after specification

**A1 · "Value-Rotation Board" (observational).** One dashboard row family reporting, per closed bar: whether price is at/through POC/VAH/VAL/HVN/LVN, whether the `absorption_behavior` flag fired at that node, HVN/LVN proximity, and a one-line balance-vs-imbalance tag (range position + POC migration). Sources: #1, #2, #18, #23, #29, #36, #39 (+#40 as a level tag). Engines already exist; this is **one board + tests**, not a new signal engine.
- Effort: small (board + self-tests + mirror sync + docs).
- Risk: none on authority (display-only; `InpEnable*` gate; never bumps a verdict).
- Open question for owner: is tick-volume basis acceptable for the tag, with `basis` printed (as the SVP module already does)? Real volume on XAUUSD rarely exists; the board must say which one it used.

**A2 · "ICT Pullback Playbook" wiring (observational).** Name the existing engines as explicit playbooks on the board: (i) Structure+OTE (#30), (ii) Market-maker/AMD + OTE (#31/#44), (iii) session liquidity-grab + FVG (#34), (iv) session-raid + confirm (#38), (v) break→retest (#47/#49). Each is a **predicate over existing graph state** printed as a row (met / not met — reason). No new detection logic.
- Effort: small-medium (predicates + journal lines + tests).
- Risk: none on authority (display-only).
- Payoff: turns the catalog's most-tested composite patterns into *measurable* QSMC rows, feeding the opportunity funnel.

**A3 · "Capitulation / calm→extreme" tag.** Extend Candle Intelligence with a capitulation note: bar volume expansion ≥ k× median + body_range_ratio ≤ 0.40 (the existing absorption definition, already computed) **plus** a σ-stretch condition vs 20-period MA (#21) and optionally vs Bollinger(20, 3σ) environment tag (#22). Feeds MR1 as *observational evidence only*.
- Effort: small; deterministic, offline-testable (pure geometry).
- Risk: none on authority; MR1 already exists and stays display-only.

### Tier B — real work, owner decision first

**B1 · First-class FVG "inversion" substate.** Add `INVERTED` to the FVG lifecycle (gap traded through in the displacement direction opposite its creation, then tradable as continuation). Enables #7 and #12 exactly as written (minus NQ-specifics), and the *legal* core of #35. Pure engine extension, fully unit-testable offline.
- Effort: medium (state machine + merge rules + replay-audit hooks + golden tests).
- Risk: touches the FVG lifecycle the causal invariant and replay audit depend on; needs the v6.6.24 replay harness green (it is the audit's own SW-grade machinery) and owner sign-off.

**B2 · London "Trident" spec for gold (#42) — specification only.** Worth writing because it is the one catalog entry **written for gold specifically**, and it overlaps Silver Bullet by design. Must be specified **with the §7.3 stop-rule correction** (structural stop stays; the author's "no hard stop on gold" is refused).
- Effort: small (spec); implementation only if the owner wants it afterwards.
- Risk: none at spec stage; the spec exists to make the owner's decision cheap.

**B3 · Bollinger(20, 3σ) environment tag (#22).** One observational input line: contracting / expanding / contracting-after-expansion. Useful context for MR1 and the scalping regime logic.
- Effort: trivial. Risk: none.

**B4 · Absorption strengthening — measurement only.** Use the decision journal/funnel to report how often `absorption_behavior` co-occurs with node touches and setup promotion. No new behaviour; just statistics.

### Tier C — rejected (with the reason, once, so it does not come back)

1. **Equity-universe & catalyst-dependent:** #4, #5, #8, #13, #14, #20, #24, #25, #28, #32, #33, #43 — need a stock universe, catalysts, borrow, RS screens; not expressible on XAUUSD bars.
2. **Correlated-pair required:** #35 (NQ+ES SMT), #41 (SMT+PO3), #48 (VIX), #17 (NQ .20/.80 tick-pattern), partly #44 (correlation check optional — see A2).
3. **Order-book / footprint / delta required for their *evidence* leg:** #3 (icebergs), #16 (delta absorption), #36/#39 (delta confirm), #40 (footprint confirm) — QSMC's tick-volume absorption flag is a weak proxy and must be labeled as one wherever it appears.
4. **Curriculum / meta, not setups:** #9 (first-principles framework), #11 (momentum/dev loop), #37 (5-stage; source CONTEXT empty).
5. **Drawn trendlines / fragile fixed-RR rules:** #27, #45 (trendlines absent in QSMC by design; fixed 2R is not the repo's exit model), #19 (measured-move projection is commentary-grade, and QSMC already projects structural TP1/TP2/TP3).
6. **Validated as-is, no action:** #26 — its content *is* the QSMC pipeline; #10 — overlap with PA1; write an overlap audit before touching anything.

## 7. Cross-cutting cautions

### 7.1 Instrument personality
Six entries are NQ/ES-native (#1, #3, #6, #7, #15, #17, #44, and #35 by requirement). XAUUSD's trend/retrace frequency, spread behaviour and session liquidity differ; A2 rows must be **backtest-blind first** (spec + offline geometry tests), then demo-observed, never assumed equivalent to NQ results. No comparison is claimed.

### 7.2 Data honesty
Wherever an A-tier row would surface evidence derived from tick volume, the row must print the basis (`basis="tick"|"real"`) exactly as the SVP engine already does. Nothing may print bid/ask delta, footprint or book depth — they do not exist on this feed.

### 7.3 The one rule we must refuse verbatim
`unique-high-rr` instructs gold traders to use **no hard stop** (rely on a candle-close filter). QSMC's risk model and the EA's `InpBreakEvenAtR` exist precisely to prevent that. **No QSMC output may implement, hint at, or soften that rule**; B2 is the spec vehicle for the owner to decide a compliant variant (structural stop + time stop), if any.

### 7.4 Measurement before authority
Any A-tier board is a *candidate generator*. Promotion to entry authority requires: (i) the opportunity-funnel instrumentation (P0-5, owner-approved) measuring it on demo, (ii) the replay/audit invariants green, (iii) an explicit owner decision. Until then it is a chart and a log line.

### 7.5 What this repository does not get from the catalog
No performance numbers, no "verified" claims, no weights, no position sizing rules. Those require XAUUSD-specific measurement and are out of scope here.

## 8. IP & licensing note

The strategy texts are third-party commercial content of the source library. This document (i) paraphrases mechanics in original words, (ii) preserves attribution (slug/author/URL) for identification, (iii) quotes at most a few words, and (iv) does **not** reproduce the playbook bodies. The catalog files themselves (`strategies.csv`, `digest_*.md`) **must not be committed** to this repository. Any implementation will encode general, unprotectable ideas (SMC/AMT/ICT concepts, volume profile) in original code — never a transcription of a playbook's prose.

## 9. Decisions I need from the owner

1. **Scope of work:** build/spec which of A1, A2, A3, B1, B2, B3? (Recommendation: A2 → A1 → A3 → B3 in that order; B1 only after the replay-audit gates pass on demo.)
2. **#42 unique-high-rr (B2):** authorise a spec with the stop-rule corrected to structural stops? Or drop it?
3. **Correlated-pair research** (DXY / US500 as a loose XAUUSD correlation proxy for #35/#41/#44 legs): wanted or explicitly out of scope?
4. **P0-5 opportunity funnel:** approve it as the measurement vehicle for any adopted playbook? (It is also the audit's pending PR; approval unblocks both.)
5. **A2 wiring authority:** confirm display-only (no authority) until §7.4 is satisfied.
6. **Priority vs the audit sequence:** should A-tier work pre-empt the remaining audit PRs (P0-2, P0-1, P0-4, P1-1, P1-2), or follow them? Default if unspecified: audit PRs stay first.
7. **Anything else from the library you specifically want evaluated** (I mapped all 49; nothing was cherry-picked).

## Appendix A — index with URLs (attribution)

See §4 for the full table; every row carries its author and `tradezella.com/strategies/<slug>` link. The catalog's index page (`_listing`, "Jumpstart profitability with ready-made Strategies") was used for completeness checks only and is not a strategy.

*Analysis performed 2026-11-24 against `strategies.csv` (49 rows, 906,617 chars), `digest_01…05.md`, and the pasted catalog. QSMC references: `MQL5/Indicators/nadir2.mq5` @ 12a9eed (v6.6.24), `MQL5/Include/QSMC/*.mqh`, `docs/QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md`, `docs/AUDIT_v6.6.24.md`. No MQL5 was compiled; no file outside `docs/` was modified by this analysis.*
