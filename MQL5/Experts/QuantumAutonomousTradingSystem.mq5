//+------------------------------------------------------------------+
//|                        QuantumAutonomousTradingSystem.mq5        |
//|        Standalone, self-contained autonomous SMC trading EA      |
//|                                                                  |
//|  ONE FILE. No indicator dependencies, no presets, no DLLs, no    |
//|  external includes except <Trade/Trade.mqh> (standard library).  |
//|                                                                  |
//|  WHAT IT DOES                                                    |
//|  --------------                                                  |
//|  Analyses the chart symbol top-down (D1 bias -> H4 context ->    |
//|  H1 structure -> liquidity -> sweep -> displacement -> BOS/CHoCH |
//|  -> order block / fair value gap -> premium/discount -> VWAP ->  |
//|  M15 confirmation -> M5 entry trigger) for BOTH directions on    |
//|  every closed M5 bar, scores BUY and SELL independently, and     |
//|  executes REAL market orders with server-side SL and TP on a     |
//|  verified DEMO account via CTrade. Every position is sized from  |
//|  the ACCOUNT'S CURRENT EQUITY, never from a fixed balance.       |
//|                                                                  |
//|  DIRECTION POLICY (v1.20)                                        |
//|  ------------------------                                        |
//|  - Neither side is a default. BUY and SELL evidence is collected |
//|    by ONE function called twice, with mirrored comparisons.      |
//|  - A liquidity sweep alone never opens a trade: the strategy     |
//|    profile names the core confirmation (displacement, BOS/CHoCH) |
//|    a setup needs before its score is even considered.            |
//|  - When both sides qualify, a fixed priority list decides; when  |
//|    it cannot, the EA stands aside. It never holds both sides.    |
//|  - Every bar prints both scores, the evidence behind each point, |
//|    and the exact reason nothing was sent.                        |
//|                                                                  |
//|  ACCOUNT AUTHORIZATION (MANDATORY)                               |
//|  ---------------------------------                               |
//|  - DEMO is allowed by default. CONTEST and unknown are refused.  |
//|  - REAL requires opt-in AND the exact login and server identity. |
//|  - Authorization and trading permissions are checked at entry.   |
//|  - Risk, broker and execution protections apply to both modes.   |
//|                                                                  |
//|  WHAT IT WILL NOT DO                                             |
//|  -------------------                                             |
//|  - No martingale. No grid. No averaging down. No widening stops. |
//|  - No trade without a stop loss. No fixed account size.          |
//|  - No decisions on forming candles: every structural decision    |
//|    uses CLOSED bars only (shift >= 1). No look-ahead bias.       |
//|  - No second entry on a setup that was already traded.           |
//|                                                                  |
//|  SETUP                                                           |
//|  ----                                                            |
//|  1. Copy this ONE file to MQL5\Experts\ and press F7 in          |
//|     MetaEditor. Zero errors / zero warnings expected.            |
//|  2. Attach to the symbol chart you want to trade (any timeframe; |
//|     analysis always runs on D1/H4/H1/M15/M5 internally).         |
//|  3. Enable Algo Trading in the terminal toolbar.                 |
//|  4. Read the [QATS] journal lines at attach: account mode,       |
//|     symbol specification, risk model and guard state are printed |
//|     there. If any protection check fails the EA says so loudly   |
//|     and refuses to trade.                                        |
//|                                                                  |
//|  v1.00 - consolidated production build (2026-11-09).             |
//|  v1.20 - dual-direction evidence engine, core confirmation gate, |
//|          liquidity map, explicit cooldown state (2026-11-11).    |
//|  v1.21 - LIMIT entry at the OB/FVG zone (InpUseLimitEntry=true). |
//|          The setup is detected as before; the ENTRY rests a      |
//|          limit at the zone instead of buying mid-move. Every     |
//|          guard is unchanged, and InpUseLimitEntry=false is the   |
//|          previous market-entry path, byte for byte in behaviour. |
//|  v1.22 - F7 fixes for v1.21: CTrade::OrderOpen now names the     |
//|          symbol first and passes limit_price=0.0 BEFORE the      |
//|          execution price (v1.21 built a StopLimit request); the  |
//|          C-only `(void)x;` silencing idiom is gone. No behaviour |
//|          change on the limit path, only a build that compiles.   |
//|  v1.23 - displacement may also confirm on M15. H1 is checked     |
//|          first, exactly as before; only when H1 shows no impulse |
//|          is M15 scanned with the M15 ATR. The M15 result never   |
//|          borrows the H1 clock: OB/FVG zone work stays on H1      |
//|          bars, anchored at the closed H1 bar containing the M15  |
//|          impulse. Score, thresholds, sweep requirement and every |
//|          other guard are unchanged.                              |
//+------------------------------------------------------------------+
#property copyright "KLJ / Quantum"
#property version   "1.23"
#property description "Autonomous SMC trading EA. REAL requires explicit account and server authorization."
#property description "Scores BUY and SELL independently on every bar; dynamic equity-risk sizing and full protection guards."

#include <Trade/Trade.mqh>

#define QATS_GV_PREFIX   "QATS_"
#define QATS_MAX_SWINGS  64
#define QATS_MAX_POOLS   160
#define QATS_MAX_CLOSED_POS 256
#define QATS_HARD_CAP_RISK_PCT   2.0    // absolute per-trade risk ceiling, % of equity
#define QATS_HARD_CAP_DAILY_PCT  5.0    // absolute daily-loss ceiling, % of baseline
#define QATS_HARD_CAP_DD_PCT     15.0   // absolute drawdown ceiling, % from high-water mark
#define QATS_VERSION            "1.23"

// PD engine range selection codes (v1.24 adaptive premium/discount)
#define QATS_PD_NONE  -1     // every range rejected: fail closed, never trade a gate bypass
#define QATS_PD_A      0     // long-term range (InpSwingLookback closed H1 bars)
#define QATS_PD_B      1     // short-term range (InpPdShortLookback closed H1 bars)
#define QATS_PD_C      2     // confirmed swing range (fresh, validated swings)

// Confluence weights. They sum to exactly 100 and absent evidence scores 0, so a
// score is a plain percentage of the evidence present. BUY and SELL use the SAME
// table. The zone weights are alternatives (touched OR merely present), never added.
#define QATS_W_BIAS_D1       17     // optional confluence: D1 EMA bias agrees
#define QATS_W_BIAS_H4       13     // optional confluence: H4 EMA bias agrees
#define QATS_W_STRUCTURE     17     // core: fresh H1 BOS / CHoCH in the trade direction
#define QATS_W_SWEEP         13     // core: opposing liquidity swept and rejected
#define QATS_W_DISPLACEMENT   9     // core: impulsive H1 candle in the trade direction
#define QATS_W_ZONE_TOUCH     9     // optional confluence: price is at the order block / FVG
#define QATS_W_ZONE_PRESENT   4     // ... or the zone merely exists (instead of the touch weight)
#define QATS_W_LOCATION       4     // optional confluence: discount for BUY, premium for SELL
#define QATS_W_VWAP           4     // optional confluence: price on the trade side of session VWAP
#define QATS_W_VOLUME         4     // optional confluence: above-average M5 bar closing our way
#define QATS_W_M15            5     // optional confluence (core in CONSERVATIVE): M15 confirmation
#define QATS_W_M5             5     // optional confluence (core in CONSERVATIVE): M5 trigger candle

// market regime classification (v1.24, Phase 7  -  REPORT-ONLY: never a veto)
#define QATS_REGIME_UNCLEAR    0
#define QATS_REGIME_TREND_BULL 1
#define QATS_REGIME_TREND_BEAR 2
#define QATS_REGIME_RANGE      3
#define QATS_REGIME_HIGH_VOL   4
#define QATS_REGIME_LOW_VOL    5

// liquidity pool life cycle
#define QATS_POOL_INTACT   0       // never traded through: a liquidity TARGET
#define QATS_POOL_SWEPT    1       // run and rejected inside the window: reversal EVIDENCE
#define QATS_POOL_ACCEPTED 2       // run and accepted (two closes beyond): a BREAKOUT
#define QATS_POOL_SPENT    3       // run earlier, or the rejection failed: no longer liquidity

enum ENUM_SIGNAL_EXECUTION_PROFILE
{
   SIGNAL_PROFILE_STRICT     = 0,   // STRONG only
   SIGNAL_PROFILE_BALANCED   = 1,   // MODERATE + STRONG
   SIGNAL_PROFILE_PERMISSIVE = 2    // WEAK + MODERATE + STRONG
};

enum ENUM_SIGNAL_CLASS
{
   QSMC_CLASS_NONE           = 0,
   QSMC_CLASS_WEAK_VALID     = 1,
   QSMC_CLASS_MODERATE_VALID = 2,
   QSMC_CLASS_STRONG_VALID   = 3,
   QSMC_CLASS_REJECTED       = 4
};

// Core strategy confirmation. A liquidity sweep on its own passes NONE of these.
enum ENUM_QATS_STRATEGY_PROFILE
{
   QATS_PROFILE_CONSERVATIVE = 0,   // sweep + displacement + BOS/CHoCH + one of M15/M5
   QATS_PROFILE_BALANCED     = 1,   // displacement + BOS/CHoCH (sweep and M15/M5 add score)
   QATS_PROFILE_ACTIVE       = 2    // any two of sweep / displacement / BOS-CHoCH
};

//--- 1. switches -------------------------------------------------------
// Non-XAUUSD symbols retain the original profile ceiling. For XAUUSD the
// profile and directional veto inputs are diagnostic only, never entry gates.
input ENUM_SIGNAL_EXECUTION_PROFILE InpSignalExecutionProfile = SIGNAL_PROFILE_PERMISSIVE; // classification ceiling for entries (PERMISSIVE = all classes)
input bool     InpEnableTrading        = true;    // MASTER SWITCH: false = never sends an order
input bool     InpDryRun               = false;   // true = log the order it would send, send nothing
input bool     InpDemoOnly             = true;    // true = block all non-DEMO accounts
input bool     InpAllowRealTrading     = false;   // explicit REAL opt-in; other authorization checks still apply
input string   InpRealAccountConfirm   = "";      // exact numeric login of authorized REAL account
input string   InpRealServerConfirm    = "";      // exact broker server of authorized REAL account
input long     InpMagic                = 26011091;// magic number; this EA manages only its own positions
input string   InpTradeComment         = "QATS";  // comment stamped on every order
input int      InpDeviationPoints      = 30;      // max slippage in points on market orders
input bool     InpResetBreakersAtInit  = false;   // operator reset of persisted guard state at attach

//--- 2. risk model (dynamic, equity based) ------------------------------
input double   InpRiskPercent          = 0.50;    // % of equity risked at the stop, per trade
input double   InpMaxRiskPercent       = 1.00;    // input ceiling; code hard cap 2.0% always wins
input double   InpRewardRisk           = 2.0;     // fallback TP = stop distance x this multiple
input double   InpMinRR                = 1.5;     // refuse targets worse than this reward:risk
input int      InpMaxOpenPositions     = 1;       // max simultaneous positions (this magic + symbol)
input int      InpMaxTradesPerDay      = 4;       // entries per server day, persisted
input double   InpMaxDailyLossPercent  = 2.0;     // stop for the day beyond this % of day baseline
input double   InpMaxDailyLossMoney    = 0.0;     // same guard in account currency; non-zero WINS
input double   InpMaxAccountDrawdownPct= 8.0;     // halt new entries beyond this % from equity HIGH-WATER
input int      InpStopAfterConsecLoss  = 3;       // stand down after this many losing positions in a row
input int      InpCooldownAfterLossMin = 60;      // minutes to stand down after the loss threshold is hit
input double   InpNeutralCloseR        = 0.0;     // a close within +/- this fraction of 1R is neutral for the loss streak (0 = every net loss counts)
input double   InpMaxMarginUse         = 0.90;    // never commit more than this fraction of free margin

//--- 3. entry filters ---------------------------------------------------
input int      InpMaxSpreadPoints      = 50;      // refuse entries while the spread is wider (points)
input double   InpMaxSpreadFracOfStop  = 0.20;    // ... or wider than this fraction of the stop distance
input int      InpMinStopPoints        = 20;      // refuse a stop closer than this (0 = broker stops level)
input int      InpMaxStopPoints        = 5000;    // refuse a stop wider than this
input int      InpSessionStartHour     = 0;       // server hour to start trading (start == end = 24h)
input int      InpSessionEndHour       = 0;       // server hour to stop (wrap over midnight allowed)
input int      InpMaxDataAgeSeconds    = 60;      // refuse entries when the last tick is older (0 = off)
input bool     InpRequireZoneTouch     = false;   // true = price MUST be at the OB/FVG zone; false = score only

//--- 4. SMC strategy engine ---------------------------------------------
input ENUM_QATS_STRATEGY_PROFILE InpStrategyProfile = QATS_PROFILE_BALANCED; // core confirmation a setup needs before its score counts
input int      InpSetupWindowBars      = 6;       // H1 bars a sweep / displacement / structure break stays valid
input int      InpConflictMargin       = 10;      // both sides eligible: the higher score must lead by this many points
input int      InpSwingLookback        = 120;     // H1 bars scanned for swings / dealing range
input int      InpSwingK               = 2;       // fractal wing (bars each side), closed bars only
input double   InpDisplaceATR          = 0.8;     // displacement: body >= this x ATR of the timeframe scanned
input double   InpDisplaceBodyRatio    = 0.65;    // ... or body/range >= this with range >= 1.3 x ATR
input bool     InpDisplaceM15          = true;    // v1.23: when H1 shows no displacement, scan M15 with the M15 ATR
input double   InpLiquidityToleranceATR= 0.10;    // equal-level tolerance as fraction of H1 ATR
input int      InpMinScore             = 55;      // minimum confluence score (0-100) to take a trade
input bool     InpUseEMAAlignmentVeto  = true;    // non-XAUUSD: block when D1 and H4 both oppose
input bool     InpAllowCounterBias     = false;   // non-XAUUSD: permit counter-D1 direction
input int      InpATRPeriod            = 14;      // ATR period (H1 for structure/stops context, M15 for the v1.23 fallback, M5 for stop distance)

//--- 5. position management ---------------------------------------------
input double   InpBreakEvenAtR         = 1.0;     // move SL to entry after +1R (0 = off); one direction only
input double   InpPartialCloseAtR      = 1.5;     // close InpPartialClosePercent at this R (0 = off)
input double   InpPartialClosePercent  = 50.0;    // percent of the position volume banked at that R
input bool     InpCloseOnOpposite      = true;    // close this magic's position on an opposite ELIGIBLE setup

//--- 5b. limit entry at the OB / FVG zone (v1.21) -------------------------
// The setup is still detected and scored exactly as before; only the ENTRY
// changes: instead of buying mid-move the EA rests a LIMIT order at a strong
// SMC zone and waits for the retracement into it. Every guard above still runs.
input bool     InpUseLimitEntry        = true;    // Limit order at OB/FVG zone; false = old market entry
input double   InpLimitMaxDistATR      = 3.0;     // refuse/cancel when zone is farther than this x H1 ATR
input int      InpLimitExpiryMin       = 180;     // pending order lifetime in minutes
input int      InpLimitEntryMode       = 0;       // 0 = 50% of zone, 1 = near edge
input double   InpLimitSLBufferATR     = 0.30;    // stop beyond the zone, x H1 ATR
input double   InpLimitMinRR           = 2.0;     // min RR measured from the LIMIT price
input bool     InpLimitNeedPD          = true;    // SELL only in premium, BUY only in discount

//--- 5c. adaptive premium / discount (v1.24) ------------------------------
// Three H1 dealing ranges, closed bars only, compared on every evaluation:
//   A long-term  = InpSwingLookback closed H1 bars (default 120)
//   B short-term = InpPdShortLookback closed H1 bars (default 48)
//   C swing      = most recent confirmed swing high -> most recent confirmed
//                  swing low, both no older than InpPdSwingMaxAge bars
// The EQ of A/B/C are always journalled; the SELECTED range gates direction
// (SELL in premium / BUY in discount) on BOTH entry paths. Never relaxed.
input bool     InpPDEnforceMarket      = true;    // hard premium/discount gate on MARKET entries (limit path keeps InpLimitNeedPD)
input int      InpPdShortLookback      = 48;      // range B: short-term H1 bars (range A = InpSwingLookback)
input int      InpPdSwingMaxAge        = 60;      // range C: most recent of the two defining confirmed swings, max age in H1 bars (0 = no age limit)

//--- 5d. regime + sessions + calendar (v1.24, Phase 7) ---------------------
// REGIME IS REPORT-ONLY: it is computed every evaluation and journalled, never
// used to veto an entry. Sessions stay BROKER-SERVER hours; the offset input is
// advisory (journal + operator documentation), the guard itself is unchanged.
// The news filter is OPT-IN (default false): a high-impact event inside the
// window blocks entries; an UNREACHABLE calendar blocks NOTHING (fail open for
// trading, never fabricate events, log once per attach).
input bool     InpRegimeEnable         = true;    // compute + journal the regime line (report-only)
input int      InpRegimeAtrWindow      = 100;     // H1 ATR percentile window (its own median, closed bars)
input double   InpRegimeHighVolMult    = 1.5;     // ATR >= this x median -> HIGH_VOL
input double   InpRegimeLowVolMult     = 0.5;     // ATR <= this x median -> LOW_VOL
input int      InpBrokerUtcOffsetMinutes = 0;     // broker server -> UTC offset in minutes (advisory; e.g. +120/+180 for NY-close brokers, DST follows the broker's server clock)
input bool     InpNewsFilterEnable     = false;   // block entries around high-impact calendar events (opt-in)
input int      InpNewsBlockBeforeMin   = 30;      // block this many minutes BEFORE the event
input int      InpNewsBlockAfterMin    = 30;      // ... and AFTER it
input string   InpNewsCurrencies       = "USD,XAU";// comma-separated currencies to watch
input long     InpNewsMinImportance    = 3;       // 3 = CALENDAR_IMPORTANCE_HIGH, 2 = moderate too (0 none .. 3 high)
input double   InpPdSwingMinATR        = 0.5;     // range C: minimum width in H1 ATRs
input double   InpPdStaleBufferATR     = 0.5;     // a range whose extreme is older than InpPdSwingMaxAge AND is more than this x ATR from price is rejected (stale extremes dominating)
input double   InpPdHysteresisATR      = 0.25;    // keep the previously selected range while its EQ is within this x ATR of the preferred EQ (0 = always switch)

//--- 6. diagnostics -----------------------------------------------------
input int      InpHeartbeatSeconds     = 300;     // diagnostic journal line every N seconds (0 = off)
input bool     InpVerbose              = true;    // true = one scored line per bar; false = only when the outcome changes

//--- order / result codes we treat as transient -------------------------
bool IsTransientRetcode(const uint rc)
{
   switch(rc)
   {
      case TRADE_RETCODE_REQUOTE:         // 10004 price moved, retry
      case TRADE_RETCODE_TIMEOUT:         // 10012 execution timeout
      case TRADE_RETCODE_PRICE_CHANGED:   // 10020 price changed
      case TRADE_RETCODE_PRICE_OFF:       // 10021 prices off
      case TRADE_RETCODE_TOO_MANY_REQUESTS: // 10024 trade server busy
      case TRADE_RETCODE_CONNECTION:      // 10031 no connection
         return true;
      default:
         return false;
   }
}

bool IsSuccessRetcode(const uint rc)
{
   return (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL);
}

// Filled-with-report accounting (Phase 8, market path): a DONE_PARTIAL (or a
// DONE whose reported volume is short of the request) is a FILL, and it must be
// journalled as such - never silently treated as the full requested size.
bool QATS_FillShort(const double requested, const double filled)
{
   return filled < requested - 1e-8;
}

//--- internal structures -------------------------------------------------
struct SSwing
{
   double price;
   int    shift;     // bar shift on the analysed timeframe (0 = forming bar; we use >=1)
   bool   isHigh;
};

struct SLiquidityPool
{
   double price;     // the level stops rest behind
   string kind;      // "SWING","EQH","EQL","PDH","PDL","PWH","PWL"
   bool   buySide;   // true = buy-side liquidity (above a high), false = sell-side (below a low)
   int    shift;     // H1 shift where the level formed (0 = prior day / week extreme)
   int    state;     // QATS_POOL_INTACT / SWEPT / ACCEPTED / SPENT
   int    eventBar;  // H1 shift of the rejection bar (SWEPT) or of the second close beyond (ACCEPTED)
   double extreme;   // furthest price reached beyond the level while it was run
};

struct SZone
{
   double top;
   double bottom;
   int    shift;     // origin bar of the zone
   bool   isFVG;     // true = fair value gap, false = order block
   bool   found;
};

struct SReading        // one indicator snapshot used by the scoring engine
{
   double d1Fast, d1Slow, d1Close;
   double h4Fast, h4Slow, h4Close;
   double h1Fast, h1Slow, h1Close, h1Slow200;
   double m15Fast, m15Close, m15Open;
   double atrH1, atrM15, atrM5;
   double vwap;
   double volM5Last, volM5Avg;
   bool   ready;
};

struct SStructure      // H1 market structure from a causal walk over closed bars
{
   int    trend;          // +1 bullish, -1 bearish, 0 undefined
   int    breakDir;       // direction of the most recent break of structure (0 = none)
   int    breakBar;       // H1 shift of the bar whose CLOSE made that break (-1 = none)
   bool   breakIsChoch;   // true = it reversed the prior trend (CHoCH); false = continuation (BOS)
   double breakLevel;     // price of the swing that was broken
};

struct SSweep          // liquidity run that was rejected (the stop hunt a reversal feeds on)
{
   bool   found;
   int    bar;            // H1 shift of the rejection bar (closed back inside the level)
   ENUM_TIMEFRAMES tf;    // timeframe the run was detected on (PERIOD_H1 today; stored like dispTF)
   int    poolShift;      // shift of the pool's formation bar (SWING/EQ*: H1 shift; PDH/PDL/PWH/PWL: 0 = day/week boundary)
   datetime eventTime;    // server time of the rejection bar, frozen at detection (never re-read)
   double level;          // price of the swept pool
   double extreme;        // furthest price reached beyond the pool
   string pool;           // kind of the pool that was run
   bool   breakout;       // a pool on this side was ACCEPTED through instead (informational)
};

struct SRegime         // report-only market regime (Phase 7)
{
   int    kind;            // QATS_REGIME_*
   double volRatio;        // ATR(1) / median ATR(1..window)
   double rangeRatio;      // (HH20-LL20) / (HH100-LL100), closed H1 bars
};

struct SSide           // the complete evidence for ONE direction
{
   int      dir;            // +1 buy, -1 sell
   bool     biasD1;         // D1 EMA bias agrees
   bool     biasH4;         // H4 EMA bias agrees
   bool     structure;      // fresh H1 BOS / CHoCH in this direction
   bool     structChoch;    // ... and it was a change of character
   int      structBar;      // H1 shift of the break bar (-1 none)
   double   structLevel;    // broken swing price
   SSweep   sweep;          // opposing liquidity swept and rejected
   bool     displaced;      // impulsive candle in this direction (H1, else M15)
   int      dispBar;        // shift of the displacement candle in dispTF (-1 none)
   ENUM_TIMEFRAMES dispTF;  // timeframe that confirmed the displacement (PERIOD_CURRENT = none)
   bool     hasOB;
   bool     hasFVG;
   SZone    ob;
   SZone    fvg;
   bool     zoneTouched;    // price inside/near the entry zone now
   bool     location;       // discount for a BUY, premium for a SELL
   bool     vwapSide;       // price on the trade side of session VWAP
   bool     volume;         // above-average M5 bar that closed in this direction
   bool     confirmM15;     // M15 closed candle confirms direction
   bool     triggerM5;      // M5 closed-bar trigger candle present
   int      score;          // 0..100 confluence score of THIS side
   int      coreCount;      // how many of sweep / displacement / structure are present
   bool     corePass;       // core confirmation of the active strategy profile
   string   coreWhy;        // why the core gate failed ("" when it passed)
   int      veto;           // non-XAUUSD directional veto (0 none, 1 EMA alignment, 2 counter-D1)
   bool     eligible;       // corePass && no veto && score >= minimum
   datetime setupTime;      // setup identity: H1 open time of the BOS/CHoCH bar, else of the sweep rejection bar
};

struct SAnalysis       // complete result of one analysis pass
{
   datetime signalBar;      // M5 bar identifying this analysis
   bool     dataReady;      // false = market data not ready, nothing was evaluated
   int      dir;            // tradable direction after conflict resolution (+1 / -1 / 0)
   int      candidate;      // side closest to trading, for the journal (+1 / -1 / 0)
   int      score;          // score of the tradable side (or of the candidate)
   int      d1Bias;         // +1/-1/0
   int      h4Bias;         // +1/-1/0
   int      h1Struct;       // H1 structure trend: +1 bullish / -1 bearish / 0 undefined
   double   dealPos;        // 0..1 location inside the SELECTED adaptive dealing range (0 = range low)
   double   pdEq;           // equilibrium of the SELECTED range (0 when no valid range)
   double   pdLongEq;       // equilibrium of range A (LONG, 120 closed H1 bars); 0 when invalid
   double   pdShortEq;      // equilibrium of range B (SHORT, 48 closed H1 bars); 0 when invalid
   double   pdSwingEq;      // equilibrium of range C (confirmed swings); 0 when invalid
   bool     pdLongValid;    // range A usable (enough bars, non-flat, no dominating stale extreme)
   bool     pdShortValid;   // range B usable
   bool     pdSwingValid;   // range C usable (fresh, relevant, confirmed swings)
   int      pdSelected;     // QATS_PD_A / QATS_PD_B / QATS_PD_C, or QATS_PD_NONE when everything rejected
   string   pdStatus;       // OK | OK (hysteresis ...) | REJECTED: ...  (never silent)
   string   regime;         // QATS_REGIME_* label  -  report only, never a veto
   double   regimeVolRatio;   // H1 ATR(1) / median H1 ATR(1..InpRegimeAtrWindow)  -  >1 expansion, <1 compression
   double   regimeRangeRatio; // (HH20-LL20) / (HH100-LL100), closed H1 bars  -  share of the 100-bar range the last 20 bars span
   double   vwap;
   SSide    buy;            // BUY evidence and score
   SSide    sell;           // SELL evidence and score
   bool     conflict;       // both sides were eligible on this bar
   string   resolution;     // rule that picked the direction
   datetime setupTime;      // setup identity of the tradable side
   double   entry;
   double   sl;
   double   tp;
   double   stopDist;
   string   tpSource;       // "LIQUIDITY:<pool>@<level>" or "RR"
   double   tpLevel;        // the liquidity pool level the TP is anchored to (0 = RR fallback)
   string   reason;         // human readable context for the heartbeat / panel
};

struct SClosedPos      // one position reconstructed from the deal history
{
   long     id;
   double   net;            // profit + swap + commission + fee over ALL deals of the position
   ulong    lastOut;        // highest closing deal ticket
   datetime lastOutTime;
   bool     ours;           // the entry deal (or a closing deal) carries this magic
   bool     hasOut;
   int      dir;            // +1 buy, -1 sell, 0 unknown (entry older than the history window)
};

struct SRiskStatus     // RISK_STATUS exposure map (Phase 8): account-side risk posture (read-only)
{
   double equity;
   double dayPnl;           // money vs the server-day baseline
   double dayPnlPct;        // vs the baseline, percent
   double hwm;              // equity high-water mark (persisted)
   double ddPct;            // current drawdown from the HWM, percent
   double ddCapPct;         // effective drawdown cap, percent (0 = disabled)
   double ddUsedPct;        // ddPct as a percent of the cap (0 when no cap)
   int    consecLosses;
   int    streakMax;        // InpStopAfterConsecLoss
   int    tradesToday;      // fills counted against the daily cap
   int    tradesMax;        // InpMaxTradesPerDay (0 = no cap)
   double dailyLossPct;     // day loss as a percent of the baseline (0 when flat/green)
   double dailyLossCapPct;  // effective daily loss cap, percent
   bool   dayLocked;
   bool   ddHalted;
   bool   cooldownActive;
   datetime cooldownUntil;
   double marginUsedPct;    // used / (used + free) * 100
};

struct SSymbolSpec
{
   string name;
   int    digits;
   double point;
   double tickSize;
   double tickValue;
   double contractSize;
   double volMin;
   double volMax;
   double volStep;
   double volLimit;
   int    stopsLevel;    // points
   int    freezeLevel;   // points
   long   tradeMode;
   long   fillingMode;
   long   tradeExec;
   string profitCcy;
   string marginCcy;
   bool   ok;
};

//--- global state --------------------------------------------------------
SSymbolSpec g_spec;
CTrade      g_trade;
datetime    g_lastBarM5        = 0;
datetime    g_lastHeartbeat    = 0;
datetime    g_cooldownUntil    = 0;        // stand-down expiry (0 = none)
datetime    g_cooldownStart    = 0;        // close time of the loss that started it
int         g_cooldownTrigger  = 0;        // consecutive losses that started it
double      g_dayBase          = 0.0;
double      g_dayPnL           = 0.0;
double      g_equityHWM        = 0.0;
double      g_accountDDPct     = 0.0;
int         g_tradesToday      = 0;
int         g_consecLosses     = 0;        // losing positions in a row since the last win or stand-down
bool        g_dayLocked        = false;
bool        g_ddHalted         = false;
bool        g_inCooldown       = false;
bool        g_execBlocked      = false;   // set when ANY protection check fails
string      g_blockReason      = "";
int         g_lastScore        = 0;
int         g_lastScoreBuy     = 0;
int         g_lastScoreSell    = 0;
// NC-2 per-bar memoization: swings + the liquidity map are pure functions of the
// closed H1 series (shift >= 1) with constant inputs; the analysis, the trade plan
// and the limit plan consume them on the same bar. Keyed on the newest closed H1
// bar's time; a new H1 bar rebuilds. Closed bars never change, so the cache is
// exact, not approximate.
SSwing         g_mHighs[];
SSwing         g_mLows[];
SLiquidityPool g_mPools[];
datetime       g_mH1Bar = 0;
int            g_mH1Bars = 0;
double         g_mH1Close = 0.0;
double         g_mH1High = 0.0;
double         g_mH1Low = 0.0;
int         g_lastDir          = 0;
string      g_lastReason       = "";
string      g_executionReason  = "";
string      g_executionStage   = "";       // PLAN / PRECHECK / SIZE / SPREAD_VS_STOP / DRY_RUN / RESERVE / BROKER
long        g_boundLogin       = 0;
long        g_boundMode        = -1;
string      g_boundServer      = "";
ulong       g_pendingRetryAt   = 0;        // 0 = no pending retry
int         g_pendingRetries   = 0;
SAnalysis   g_pendingPlan;                 // the plan a queued retry re-submits
ulong       g_lastLoggedDeal   = 0;
// Per-ticket throttle for refused break-even modifications (CR-4). A refused modify
// used to throttle EVERY position for 10s via one global; now only the refused ticket waits.
#define QATS_MANAGE_FAIL_MAX 32
datetime    g_manageFailAt[QATS_MANAGE_FAIL_MAX];
ulong       g_manageFailTicket[QATS_MANAGE_FAIL_MAX];
// audit log-once flags (each critical silence prints at most one line per attach)
bool        g_loggedZoneHistoryFail = false;
bool        g_newsUnavailableLogged = false;
bool        g_newsReadyLogged       = false;
bool        g_loggedDoubleBreak     = false;
string      g_lastBlockKey     = "";
string      g_lastRejectKey    = "";
string      g_lastScoredKey    = "";
string      g_lastAnalysisKey[2];  // Phase 9 single-record dedup: setup|outcome|reason per side
string      g_lastGuardKey[2];     // Phase 9 high-score rejection record dedup
string      g_lastConflictKey  = "";
string      g_statsDay         = "";
datetime    g_announcedSetup[2];           // newest setup announced per side (0 = BUY, 1 = SELL)
int         g_statDetected[2];
int         g_statEligibleBars[2];
int         g_statBlockedBars[2];
int         g_statRejected[2];
int         g_statApproved[2];
int         g_statExecuted[2];
int         g_statWins[2];
int         g_statLosses[2];
int         g_statNeutral[2];
double      g_statNet[2];
int         g_statConflicts    = 0;

int         g_hD1Fast = INVALID_HANDLE, g_hD1Slow = INVALID_HANDLE;
int         g_hH4Fast = INVALID_HANDLE, g_hH4Slow = INVALID_HANDLE;
int         g_hH1Fast = INVALID_HANDLE, g_hH1Slow = INVALID_HANDLE;
int         g_hM15Fast= INVALID_HANDLE;
int         g_hATRH1  = INVALID_HANDLE, g_hATRM15 = INVALID_HANDLE, g_hATRM5  = INVALID_HANDLE;
int         g_hH1Slow200 = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| SECTION 7 - PERSISTED GUARD STATE (terminal global variables)    |
//| Survives chart reloads so a mid-day reload cannot re-base the    |
//| loss baseline. Keys embed the account login and this magic.      |
//+------------------------------------------------------------------+
string GVKey(const string tail)
{
   return QATS_GV_PREFIX + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_" + IntegerToString(InpMagic) + "_" + _Symbol + "_" + tail;
}

double GVGet(const string key, const double def = 0.0)
{
   if(!GlobalVariableCheck(key)) return def;
   return GlobalVariableGet(key);
}

void GVSet(const string key, const double value)
{
   GlobalVariableSet(key, value);
}

void GVDel(const string key)
{
   if(GlobalVariableCheck(key)) GlobalVariableDel(key);
}

string TodayKey()
{
   MqlDateTime dt;
   TimeToStruct(TimeTradeServer(), dt);
   return StringFormat("%04d%02d%02d", dt.year, dt.mon, dt.day);
}

void ResetBreakers()
{
   GVDel(GVKey("daylock_" + TodayKey()));
   GVDel(GVKey("consec_losses"));
   GVDel(GVKey("cooldown_until"));
   GVDel(GVKey("cooldown_start"));
   GVDel(GVKey("cooldown_trigger"));
   GVDel(GVKey("hwm"));
   GVDel(GVKey("trades_" + TodayKey()));
   PrintFormat("[QATS][RESET] Operator reset of persisted guard state for login=%I64d magic=%I64d symbol=%s",
               AccountInfoInteger(ACCOUNT_LOGIN), InpMagic, _Symbol);
}

//+------------------------------------------------------------------+
//| SECTION 8 - SYMBOL / ACCOUNT SPECIFICATION (never hardcoded)     |
//+------------------------------------------------------------------+
bool LoadSymbolSpec(SSymbolSpec &spec)
{
   // Read into a scratch copy and publish it only when it is complete. A reading
   // that fails validation must never replace the last good specification: the
   // guards and the heartbeat divide by its point size on every tick, and a zero
   // divide is a critical error that stops the EA.
   SSymbolSpec s;
   s.ok = false;
   s.name = _Symbol;
   if(!SymbolSelect(_Symbol, true))
   {
      PrintFormat("[QATS][FATAL] SymbolSelect(%s) failed, error=%d", _Symbol, GetLastError());
      return false;
   }
   s.digits       = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   s.point        = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   s.tickSize     = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   s.tickValue    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   s.contractSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   s.volMin       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   s.volMax       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   s.volStep      = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   s.volLimit     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT);
   s.stopsLevel   = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   s.freezeLevel  = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   s.tradeMode    = (long)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   s.fillingMode  = (long)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   s.tradeExec    = (long)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_EXEMODE);
   s.profitCcy    = AccountInfoString(ACCOUNT_CURRENCY);
   s.marginCcy    = AccountInfoString(ACCOUNT_CURRENCY);

   bool ok = MathIsValidNumber(s.point) && MathIsValidNumber(s.tickSize) &&
             MathIsValidNumber(s.tickValue) && MathIsValidNumber(s.volMin) &&
             MathIsValidNumber(s.volMax) && MathIsValidNumber(s.volStep) &&
             s.point > 0.0 && s.tickSize > 0.0 && s.tickValue > 0.0 &&
             s.volMin > 0.0 && s.volMax >= s.volMin && s.volStep > 0.0;
   if(ok && IsXAUUSD())
      ok = MathAbs(s.volMin / s.volStep - MathRound(s.volMin / s.volStep)) < 1e-7 &&
           MathAbs(s.volMax / s.volStep - MathRound(s.volMax / s.volStep)) < 1e-7 &&
           s.digits >= 0 && s.digits <= 8 && s.stopsLevel >= 0 && s.freezeLevel >= 0 &&
           s.contractSize > 0.0 && MathIsValidNumber(s.contractSize);
   if(!ok)
   {
      PrintFormat("[QATS][FATAL] Incomplete symbol specification for %s (point=%.10f tickSize=%.10f tickValue=%.5f volMin=%.2f volMax=%.2f volStep=%.2f)",
                  _Symbol, s.point, s.tickSize, s.tickValue, s.volMin, s.volMax, s.volStep);
      return false;
   }
   s.ok = true;
   spec = s;
   return true;
}

void PrintSymbolSpec()
{
   Print("[QATS]==================== SYMBOL SPECIFICATION ====================");
   PrintFormat("[QATS] Symbol=%s digits=%d point=%.10f tickSize=%.10f tickValue=%.5f contractSize=%.2f",
               g_spec.name, g_spec.digits, g_spec.point, g_spec.tickSize, g_spec.tickValue, g_spec.contractSize);
   PrintFormat("[QATS] Volume: min=%.8f max=%.8f step=%.8f limit=%.8f",
               g_spec.volMin, g_spec.volMax, g_spec.volStep, g_spec.volLimit);
   PrintFormat("[QATS] Stops level=%d pts | Freeze level=%d pts | TradeMode=%I64d (FULL=4) | Filling=%I64d | ExecMode=%I64d",
               g_spec.stopsLevel, g_spec.freezeLevel, g_spec.tradeMode, g_spec.fillingMode, g_spec.tradeExec);
   PrintFormat("[QATS] Account ccy=%s leverage=1:%I64d", g_spec.profitCcy, AccountInfoInteger(ACCOUNT_LEVERAGE));
}

//+------------------------------------------------------------------+
//| SECTION 9 - ACCOUNT SNAPSHOT / MANDATORY ACCOUNT GUARD              |
//+------------------------------------------------------------------+
bool VerifyAccountProtection(string &reason)
{
   reason = "";
   long mode = (long)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode != ACCOUNT_TRADE_MODE_DEMO && mode != ACCOUNT_TRADE_MODE_CONTEST && mode != ACCOUNT_TRADE_MODE_REAL)
   {
      reason = "ACCOUNT_TRADE_MODE unreadable - execution BLOCKED";
      return false;
   }
   long currentLogin = AccountInfoInteger(ACCOUNT_LOGIN);
   string currentServer = AccountInfoString(ACCOUNT_SERVER);
   if(currentLogin <= 0 || currentServer == "" || currentLogin != g_boundLogin ||
      currentServer != g_boundServer || mode != g_boundMode)
   { reason = "account identity or mode changed since attach, or is unavailable"; return false; }
   if(mode == ACCOUNT_TRADE_MODE_CONTEST)
   { reason = "CONTEST account detected - execution REFUSED"; return false; }
   if(mode == ACCOUNT_TRADE_MODE_REAL)
   {
      if(InpDemoOnly) { reason = "REAL account blocked by InpDemoOnly"; return false; }
      if(!InpAllowRealTrading) { reason = "REAL account requires InpAllowRealTrading=true"; return false; }
      if(InpRealAccountConfirm == "" || InpRealAccountConfirm != IntegerToString(currentLogin))
      { reason = "REAL account login is unavailable or does not match InpRealAccountConfirm"; return false; }
      if(InpRealServerConfirm == "" || InpRealServerConfirm != currentServer)
      { reason = "REAL account server is unavailable or does not match InpRealServerConfirm"; return false; }
   }
   // terminal permission to trade from MQL5
   if(!(bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      reason = "terminal Algo Trading is DISABLED";
      return false;
   }
   if(!(bool)MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      reason = "this EA is not allowed to trade (MQL trade permission)";
      return false;
   }
   // account-level trade permission
   long acctAllowed = (long)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED);
   if(acctAllowed == 0)
   {
      reason = "ACCOUNT_TRADE_ALLOWED reports trading DISABLED on this account";
      return false;
   }
   // symbol permission
   if(g_spec.tradeMode != SYMBOL_TRADE_MODE_FULL)
   {
      reason = StringFormat("symbol %s trade mode = %I64d (requires SYMBOL_TRADE_MODE_FULL=4)", _Symbol, g_spec.tradeMode);
      return false;
   }
   return true;
}

double EffectiveRiskPercent()
{
   double ceiling = InpMaxRiskPercent;
   if(ceiling <= 0.0 || ceiling > QATS_HARD_CAP_RISK_PCT) ceiling = QATS_HARD_CAP_RISK_PCT;
   double risk = InpRiskPercent;
   if(risk <= 0.0) risk = 0.01;
   if(risk > ceiling) risk = ceiling;
   return risk;
}

double EffectiveDailyLossPercent()
{
   double v = InpMaxDailyLossPercent;
   if(v <= 0.0) return 0.0;
   if(v > QATS_HARD_CAP_DAILY_PCT) v = QATS_HARD_CAP_DAILY_PCT;
   return v;
}

double EffectiveDrawdownPercent()
{
   double v = InpMaxAccountDrawdownPct;
   if(v <= 0.0) return 0.0;
   if(v > QATS_HARD_CAP_DD_PCT) v = QATS_HARD_CAP_DD_PCT;
   return v;
}

//+------------------------------------------------------------------+
//| SECTION 10 - INDICATOR SNAPSHOT (native built-ins, closed bars)  |
//+------------------------------------------------------------------+
bool BufValue(const int handle, const int shift, double &value)
{
   value = 0.0;
   if(handle == INVALID_HANDLE) return false;
   double buf[];
   if(CopyBuffer(handle, 0, shift, 1, buf) != 1) return false;
   value = buf[0];
   return true;
}

double SmaVolume(const string symbol, const ENUM_TIMEFRAMES tf, const int shift, const int count)
{
   double sum = 0.0;
   int n = 0;
   int bars = iBars(symbol, tf);
   for(int i = shift; i < shift + count && i < bars; i++)
   {
      long v = iVolume(symbol, tf, i);
      if(v > 0) { sum += (double)v; n++; }
   }
   return (n > 0) ? sum / (double)n : 0.0;
}

double SessionVWAP(const string symbol)
{
   datetime now = TimeTradeServer();
   MqlDateTime dt;
   TimeToStruct(now, dt);
   datetime dayStart = now - (datetime)(dt.hour * 3600 + dt.min * 60 + dt.sec);
   double pv = 0.0, vv = 0.0;
   int bars = iBars(symbol, PERIOD_M5);
   // iterate from the NEWEST closed bar backwards; stop at the day boundary.
   // (bars-1 is the oldest bar - looping from it would scan all history.)
   for(int i = 1; i < bars; i++)
   {
      datetime t = iTime(symbol, PERIOD_M5, i);
      if(t < dayStart) break;
      double tp = (iHigh(symbol, PERIOD_M5, i) + iLow(symbol, PERIOD_M5, i) + iClose(symbol, PERIOD_M5, i)) / 3.0;
      long v = (long)iVolume(symbol, PERIOD_M5, i);
      pv += tp * (double)v;
      vv += (double)v;
   }
   if(vv <= 0.0) return iClose(symbol, PERIOD_M5, 1);
   return pv / vv;
}

bool LoadReading(SReading &r)
{
   bool ok = true;
   ok = BufValue(g_hD1Fast, 1, r.d1Fast)  && ok;
   ok = BufValue(g_hD1Slow, 1, r.d1Slow)  && ok;
   ok = BufValue(g_hH4Fast, 1, r.h4Fast)  && ok;
   ok = BufValue(g_hH4Slow, 1, r.h4Slow)  && ok;
   ok = BufValue(g_hH1Fast, 1, r.h1Fast)  && ok;
   ok = BufValue(g_hH1Slow, 1, r.h1Slow)  && ok;
   ok = BufValue(g_hH1Slow200, 1, r.h1Slow200) && ok;
   ok = BufValue(g_hM15Fast, 1, r.m15Fast)&& ok;
   ok = BufValue(g_hATRH1, 1, r.atrH1)    && ok;
   ok = BufValue(g_hATRM15, 1, r.atrM15)  && ok;
   ok = BufValue(g_hATRM5, 1, r.atrM5)    && ok;
   r.d1Close = iClose(_Symbol, PERIOD_D1, 1);
   r.h4Close = iClose(_Symbol, PERIOD_H4, 1);
   r.h1Close = iClose(_Symbol, PERIOD_H1, 1);
   r.m15Close= iClose(_Symbol, PERIOD_M15, 1);
   r.m15Open = iOpen(_Symbol, PERIOD_M15, 1);
   r.vwap    = SessionVWAP(_Symbol);
   r.volM5Last = (double)iVolume(_Symbol, PERIOD_M5, 1);
   r.volM5Avg  = SmaVolume(_Symbol, PERIOD_M5, 1, 20);
   r.ready = ok && r.atrH1 > 0.0 && r.atrM15 > 0.0 && r.atrM5 > 0.0 && iBars(_Symbol, PERIOD_M5) > 30;
   return r.ready;
}

int BiasFrom(const double close, const double fast, const double slow)
{
   if(close > fast && fast > slow) return +1;
   if(close < fast && fast < slow) return -1;
   return 0;
}

//+------------------------------------------------------------------+
//| REGIME (v1.24, Phase 7)  -  REPORT-ONLY                            |
//| Class: HIGH_VOL / LOW_VOL (ATR percentile vs its own median),      |
//| TREND_BULL / TREND_BEAR (EMA20>EMA50>EMA200 ordered structure),    |
//| RANGE (fast/slow pair flat vs ATR), else UNCLEAR.                  |
//| The class NEVER changes an entry decision; it is journalled so a   |
//| future phase can gather evidence before any gate is considered.    |
//+------------------------------------------------------------------+
string RegimeName(const int kind)
{
   switch(kind)
   {
      case QATS_REGIME_TREND_BULL: return "TREND_BULL";
      case QATS_REGIME_TREND_BEAR: return "TREND_BEAR";
      case QATS_REGIME_RANGE:      return "RANGE";
      case QATS_REGIME_HIGH_VOL:   return "HIGH_VOL";
      case QATS_REGIME_LOW_VOL:    return "LOW_VOL";
      default:                     return "UNCLEAR";
   }
}

// pure classification  -  unit-tested without handles
int ClassifyRegime(const double atrNow, const double atrMedian,
                   const double h1Close, const double emaFast, const double emaMid,
                   const double emaSlow200, const double atr,
                   double &volRatio)
{
   volRatio = (atrMedian > 0.0) ? atrNow / atrMedian : 0.0;
   if(atrMedian <= 0.0 || atrNow <= 0.0) return QATS_REGIME_UNCLEAR;   // fail closed: unverifiable -> UNCLEAR
   if(volRatio >= InpRegimeHighVolMult) return QATS_REGIME_HIGH_VOL;
   if(volRatio <= InpRegimeLowVolMult)  return QATS_REGIME_LOW_VOL;
   if(h1Close > emaFast && emaFast > emaMid && emaMid > emaSlow200 && emaSlow200 > 0.0) return QATS_REGIME_TREND_BULL;
   if(h1Close < emaFast && emaFast < emaMid && emaMid < emaSlow200) return QATS_REGIME_TREND_BEAR;
   if(MathAbs(emaFast - emaMid) <= 0.5 * atr) return QATS_REGIME_RANGE;   // fast/slow pair flat vs one ATR
   return QATS_REGIME_UNCLEAR;
}

// breadth of the last fastBars vs the last slowBars, closed H1 bars (1 = newest).
// report-only context, never a classifier input
double RangeRatio(const string symbol, const int fastBars, const int slowBars)
{
   int bars = iBars(symbol, PERIOD_H1) - 1;              // closed bars only
   int fb = MathMin(MathMax(2, fastBars), bars);
   int sb = MathMin(MathMax(2, slowBars), bars);
   if(fb < 2 || sb < 2) return 0.0;
   double hhf = iHigh(symbol, PERIOD_H1, 1), llf = iLow(symbol, PERIOD_H1, 1);
   double hhs = hhf, lls = llf;
   for(int s = 2; s <= sb; s++)
   {
      double h = iHigh(symbol, PERIOD_H1, s), l = iLow(symbol, PERIOD_H1, s);
      if(s <= fb) { if(h > hhf) hhf = h; if(l < llf) llf = l; }
      if(h > hhs) hhs = h;
      if(l < lls) lls = l;
   }
   double span = hhs - lls;
   return (span > 0.0) ? (hhf - llf) / span : 0.0;
}

void ComputeRegime(const string symbol, const double atrH1, const double h1Close,
                   const double h1Fast, const double h1Slow, const double h1Slow200, SRegime &out)
{
   out.kind = QATS_REGIME_UNCLEAR; out.volRatio = 0.0; out.rangeRatio = 0.0;
   int want = MathMax(10, InpRegimeAtrWindow);
   double atrBuf[];
   if(CopyBuffer(g_hATRH1, 0, 1, want, atrBuf) != want)
   {
      if(CopyBuffer(g_hATRH1, 0, 1, iBars(symbol, PERIOD_H1) - 1, atrBuf) <= 0) return;   // fail closed: UNCLEAR
   }
   int n = ArraySize(atrBuf);
   if(n < 2) return;
   // insertion sort on a copy (n <= InpRegimeAtrWindow, once per evaluation)
   double atrSorted[];
   ArrayResize(atrSorted, n);
   for(int i = 0; i < n; i++) atrSorted[i] = atrBuf[i];
   for(int i = 1; i < n; i++)
   {
      double keyV = atrSorted[i];
      int j = i - 1;
      while(j >= 0 && atrSorted[j] > keyV) { atrSorted[j + 1] = atrSorted[j]; j--; }
      atrSorted[j + 1] = keyV;
   }
   double med = (n % 2 == 1) ? atrSorted[n / 2] : 0.5 * (atrSorted[n / 2 - 1] + atrSorted[n / 2]);
   out.kind = ClassifyRegime(atrH1, med, h1Close, h1Fast, h1Slow, h1Slow200, atrH1, out.volRatio);
   out.rangeRatio = RangeRatio(symbol, 20, 100);
}

//+------------------------------------------------------------------+
//| SECTION 11 - MARKET STRUCTURE ENGINE (closed bars only)          |
//+------------------------------------------------------------------+
// A fractal swing: strictly beyond k closed bars on each side.
bool IsFractal(const string symbol, const ENUM_TIMEFRAMES tf, const int s, const int k, const bool wantHigh)
{
   int bars = iBars(symbol, tf);
   if(k < 1 || s - k < 1 || s + k >= bars) return false;   // both wings must be closed bars
   double ref = wantHigh ? iHigh(symbol, tf, s) : iLow(symbol, tf, s);
   for(int j = 1; j <= k; j++)
   {
      double leftPrice  = wantHigh ? iHigh(symbol, tf, s - j) : iLow(symbol, tf, s - j);
      double rightPrice = wantHigh ? iHigh(symbol, tf, s + j) : iLow(symbol, tf, s + j);
      if(wantHigh) { if(ref <= leftPrice || ref <= rightPrice) return false; }
      else         { if(ref >= leftPrice || ref >= rightPrice) return false; }
   }
   return true;
}

int FindSwings(const string symbol, const ENUM_TIMEFRAMES tf, const int lookback,
               const int k, SSwing &swings[], const bool wantHigh)
{
   ArrayResize(swings, 0);
   int bars = iBars(symbol, tf);
   if(bars < 2 * k + 2) return 0;
   int from = k + 1;                       // shift of the newest usable bar
   int to   = MathMin(lookback, bars - k - 1);
   for(int s = from; s <= to; s++)
   {
      if(!IsFractal(symbol, tf, s, k, wantHigh)) continue;
      int n = ArraySize(swings);
      if(n >= QATS_MAX_SWINGS) break;
      ArrayResize(swings, n + 1);
      swings[n].price  = wantHigh ? iHigh(symbol, tf, s) : iLow(symbol, tf, s);
      swings[n].shift  = s;
      swings[n].isHigh = wantHigh;
   }
   return ArraySize(swings);
}

// Break of structure, walked causally from the oldest bar to the newest.
// The reference levels are the most recent CONFIRMED swing high and swing low.
// A close beyond one of them is a break: in the direction of the prevailing trend
// it is a BOS (continuation), against it a CHoCH (change of character). A level
// is consumed by the break that crosses it, so one swing yields one event.
// The bullish and the bearish branch are mirror images; if a bar ever satisfied
// both (inconsistent data), neither side is credited.
void BuildStructure(const string symbol, const ENUM_TIMEFRAMES tf, const int lookback, const int k, SStructure &st)
{
   st.trend = 0; st.breakDir = 0; st.breakBar = -1; st.breakIsChoch = false; st.breakLevel = 0.0;
   int bars = iBars(symbol, tf);
   int oldest = MathMin(lookback, bars - 1);
   double activeHigh = 0.0, activeLow = 0.0;
   bool hasHigh = false, hasLow = false;
   for(int s = oldest; s >= 1; s--)
   {
      // the fractal at shift s+k becomes known when bar s (its k-th bar to the right) closes
      int c = s + k;
      if(IsFractal(symbol, tf, c, k, true))  { activeHigh = iHigh(symbol, tf, c); hasHigh = true; }
      if(IsFractal(symbol, tf, c, k, false)) { activeLow  = iLow(symbol, tf, c);  hasLow  = true; }
      double cl = iClose(symbol, tf, s);
      bool upBreak = (hasHigh && cl > activeHigh);
      bool dnBreak = (hasLow && cl < activeLow);
      if(upBreak && dnBreak)
      {
         hasHigh = false; hasLow = false;
         st.trend = 0; st.breakDir = 0; st.breakBar = -1; st.breakIsChoch = false; st.breakLevel = 0.0;
         if(!g_loggedDoubleBreak)
         {
            g_loggedDoubleBreak = true;
            PrintFormat("[QATS][STRUCTURE] same closed bar %s satisfies BOTH break branches - contradictory data, neither side credited (trend reset)",
                        TimeToString(iTime(symbol, tf, s), TIME_DATE | TIME_MINUTES));
         }
      }
      else if(upBreak)
      {
         st.breakIsChoch = (st.trend < 0);
         st.trend = +1; st.breakDir = +1; st.breakBar = s; st.breakLevel = activeHigh;
         hasHigh = false;
      }
      else if(dnBreak)
      {
         st.breakIsChoch = (st.trend > 0);
         st.trend = -1; st.breakDir = -1; st.breakBar = s; st.breakLevel = activeLow;
         hasLow = false;
      }
   }
}

bool HighestHigh(const string symbol, const ENUM_TIMEFRAMES tf, const int fromShift, const int count, double &hh)
{
   int bars = iBars(symbol, tf);
   int n = MathMin(count, bars - fromShift);
   if(n <= 0) return false;
   double m = iHigh(symbol, tf, fromShift);
   for(int i = fromShift + 1; i < fromShift + n; i++)
   {
      double h = iHigh(symbol, tf, i);
      if(h > m) m = h;
   }
   hh = m;
   return true;
}

bool LowestLow(const string symbol, const ENUM_TIMEFRAMES tf, const int fromShift, const int count, double &ll)
{
   int bars = iBars(symbol, tf);
   int n = MathMin(count, bars - fromShift);
   if(n <= 0) return false;
   double m = iLow(symbol, tf, fromShift);
   for(int i = fromShift + 1; i < fromShift + n; i++)
   {
      double l = iLow(symbol, tf, i);
      if(l < m) m = l;
   }
   ll = m;
   return true;
}

//+------------------------------------------------------------------+
//| Adaptive premium / discount engine (QATS_PD_ADAPTIVE, v1.24)      |
//|                                                                  |
//| Three H1 dealing ranges, CLOSED bars only, compared on every      |
//| evaluation:                                                       |
//|   A long-term  - highest high / lowest low of InpSwingLookback    |
//|                  closed H1 bars (default 120)                     |
//|   B short-term - the same over InpPdShortLookback closed H1 bars  |
//|                  (default 48)                                     |
//|   C swing      - most recent CONFIRMED swing high down to the     |
//|                  most recent CONFIRMED swing low; the defining    |
//|                  swings must be no older than InpPdSwingMaxAge    |
//|                  and the range must be at least InpPdSwingMinATR  |
//|                  x ATR(H1) wide                                   |
//| A range is REJECTED (never silently patched) when:                |
//|   * the closed H1 history cannot cover the full window (incomplete)|
//|   * it is flat (high <= low, or narrower than 0.25 x ATR)          |
//|   * an extreme older than InpPdSwingMaxAge anchors the equilibrium |
//|     more than InpPdStaleBufferATR x ATR away from price            |
//|     (a stale extreme dominating the range)                        |
//| Range C additionally requires the NEWER of its two defining        |
//| swings to be no older than InpPdSwingMaxAge (freshness).           |
//|                                                                  |
//| Selection is deterministic: fresh valid C > valid B > valid A.     |
//| Hysteresis keeps the previously selected range while it stays      |
//| valid and its equilibrium is within InpPdHysteresisATR x ATR of    |
//| the preferred equilibrium - adjacent bars cannot flip the regime.  |
//| If NOTHING is valid the direction is refused (fail closed): the    |
//| premium/discount protection is never silently bypassed.            |
//+------------------------------------------------------------------+
int g_pdLastSelected = QATS_PD_NONE;   // previous selection (hysteresis anchor), per attach

struct SPdRange
{
   bool   valid;
   double high, low, eq;
   int    highShift, lowShift;
};

struct SPdAdaptive
{
   SPdRange a, b, c;
   int      selected;    // QATS_PD_A / B / C, or QATS_PD_NONE (everything rejected)
   double   eq;          // equilibrium of the SELECTED range (0 when none)
   double   position;    // (close - low) / (high - low) of the SELECTED range, 0..1 (0.5 when none)
   string   status;      // OK | OK (hysteresis: ...) | OK (switch: ...) | REJECTED: ...
};

void PdResetRange(SPdRange &r)
{
   r.valid = false; r.high = 0.0; r.low = 0.0; r.eq = 0.0; r.highShift = -1; r.lowShift = -1;
}

// window extremes + the shift they were made on; requires the FULL window of closed bars
bool HighestHighShift(const string symbol, const ENUM_TIMEFRAMES tf, const int fromShift, const int count, double &hh, int &hhShift)
{
   int bars = iBars(symbol, tf);
   if(fromShift < 1 || count <= 0) return false;
   if(bars - fromShift < count) return false;      // incomplete coverage: rejected
   hh = iHigh(symbol, tf, fromShift);
   hhShift = fromShift;
   for(int i = fromShift + 1; i < fromShift + count; i++)
   {
      double v = iHigh(symbol, tf, i);
      if(v > hh) { hh = v; hhShift = i; }
   }
   return (MathIsValidNumber(hh) && hh > 0.0);
}

bool LowestLowShift(const string symbol, const ENUM_TIMEFRAMES tf, const int fromShift, const int count, double &ll, int &llShift)
{
   int bars = iBars(symbol, tf);
   if(fromShift < 1 || count <= 0) return false;
   if(bars - fromShift < count) return false;      // incomplete coverage: rejected
   ll = iLow(symbol, tf, fromShift);
   llShift = fromShift;
   for(int i = fromShift + 1; i < fromShift + count; i++)
   {
      double v = iLow(symbol, tf, i);
      if(v < ll) { ll = v; llShift = i; }
   }
   return (MathIsValidNumber(ll) && ll > 0.0);
}

// A range is STALE when an extreme older than InpPdSwingMaxAge pins the equilibrium
// far away from price: the range no longer describes where the market is trading.
bool PdStaleExtreme(const SPdRange &r, const double close1, const double atr)
{
   if(atr <= 0.0 || InpPdStaleBufferATR <= 0.0 || InpPdSwingMaxAge <= 0) return false;
   if(r.highShift > InpPdSwingMaxAge && (r.high - close1) > InpPdStaleBufferATR * atr) return true;
   if(r.lowShift  > InpPdSwingMaxAge && (close1 - r.low)  > InpPdStaleBufferATR * atr) return true;
   return false;
}

bool PdRangeFromWindow(const string symbol, const int count, const double atr, SPdRange &r)
{
   PdResetRange(r);
   double close1 = iClose(symbol, PERIOD_H1, 1);
   if(!MathIsValidNumber(close1) || close1 <= 0.0) return false;
   if(count < 2) return false;
   if(!HighestHighShift(symbol, PERIOD_H1, 1, count, r.high, r.highShift)) return false;
   if(!LowestLowShift(symbol, PERIOD_H1, 1, count, r.low, r.lowShift))     return false;
   double width = r.high - r.low;
   if(width <= 0.0) return false;                          // flat / degenerate
   if(atr > 0.0 && width < 0.25 * atr) return false;       // flat in ATR terms
   r.eq = (r.high + r.low) * 0.5;
   if(PdStaleExtreme(r, close1, atr)) return false;        // stale extreme dominating
   r.valid = true;
   return true;
}

bool PdSwingRange(const string symbol, const int lookback, const int k, const double atr, SPdRange &r)
{
   PdResetRange(r);
   double close1 = iClose(symbol, PERIOD_H1, 1);
   if(!MathIsValidNumber(close1) || close1 <= 0.0) return false;
   SSwing highs[], lows[];
   int nh = FindSwings(symbol, PERIOD_H1, lookback, k, highs, true);
   int nl = FindSwings(symbol, PERIOD_H1, lookback, k, lows, false);
   if(nh < 1 || nl < 1) return false;
   // FindSwings scans from the newest closed bar backwards: swings[0] is the newest
   r.high = highs[0].price;  r.highShift = highs[0].shift;
   r.low  = lows[0].price;   r.lowShift  = lows[0].shift;
   if(!MathIsValidNumber(r.high) || !MathIsValidNumber(r.low)) return false;
   if(r.high <= r.low) return false;                       // degenerate overlay range
   double width = r.high - r.low;
   if(atr > 0.0 && width < InpPdSwingMinATR * atr) return false;   // too narrow to be a range
   // freshness: even the NEWER of the two defining swings must not be ancient
   int newest = MathMin(r.highShift, r.lowShift);
   if(InpPdSwingMaxAge > 0 && newest > InpPdSwingMaxAge) return false;
   r.eq = (r.high + r.low) * 0.5;
   if(PdStaleExtreme(r, close1, atr)) return false;        // stale extreme dominating
   r.valid = true;
   return true;
}

string PdLetter(const int sel)
{
   if(sel == QATS_PD_A) return "A";
   if(sel == QATS_PD_B) return "B";
   if(sel == QATS_PD_C) return "C";
   return "NONE";
}

// One evaluation of the three ranges + the deterministic selection. Resets nothing;
// pure READ of closed bars plus the hysteresis anchor g_pdLastSelected.
void ComputePdAdaptive(const string symbol, const double atrH1, SPdAdaptive &pd)
{
   double close1 = iClose(symbol, PERIOD_H1, 1);
   PdRangeFromWindow(symbol, InpSwingLookback,   atrH1, pd.a);
   PdRangeFromWindow(symbol, InpPdShortLookback, atrH1, pd.b);
   PdSwingRange(symbol, InpSwingLookback, InpSwingK, atrH1, pd.c);

   int preferred = QATS_PD_NONE;
   if(pd.c.valid)      preferred = QATS_PD_C;
   else if(pd.b.valid) preferred = QATS_PD_B;
   else if(pd.a.valid) preferred = QATS_PD_A;

   int sel = preferred;
   string note = "";
   int prev = g_pdLastSelected;
   if(prev != preferred)
   {
      bool prevValid = (prev == QATS_PD_A && pd.a.valid) ||
                       (prev == QATS_PD_B && pd.b.valid) ||
                       (prev == QATS_PD_C && pd.c.valid);
      double prevEq = (prev == QATS_PD_A) ? pd.a.eq : ((prev == QATS_PD_B) ? pd.b.eq : pd.c.eq);
      double prefEq = (preferred == QATS_PD_A) ? pd.a.eq : ((preferred == QATS_PD_B) ? pd.b.eq : ((preferred == QATS_PD_C) ? pd.c.eq : 0.0));
      if(prev != QATS_PD_NONE && prevValid && preferred != QATS_PD_NONE && atrH1 > 0.0 &&
         InpPdHysteresisATR > 0.0 && MathAbs(prevEq - prefEq) <= InpPdHysteresisATR * atrH1)
      {
         sel = prev;   // keep the old regime while the EQs have not materially moved
         note = StringFormat("hysteresis: kept %s (EQ %s) over preferred %s (EQ %s), delta %.2f ATR",
                             PdLetter(prev), PriceText(prevEq), PdLetter(preferred), PriceText(prefEq),
                             MathAbs(prevEq - prefEq) / atrH1);
      }
      else if(prev != QATS_PD_NONE)
      {
         if(preferred == QATS_PD_NONE)
            note = StringFormat("switch: %s -> NONE (previous range still %s, nothing else valid)",
                                PdLetter(prev), (prevValid ? "valid but superseded" : "no longer valid"));
         else if(!prevValid)
            note = StringFormat("switch: %s -> %s (previous range no longer valid)", PdLetter(prev), PdLetter(preferred));
         else if(atrH1 > 0.0)
            note = StringFormat("switch: %s -> %s (EQ delta %.2f ATR)", PdLetter(prev), PdLetter(preferred),
                                MathAbs(prevEq - prefEq) / atrH1);
      }
   }

   pd.selected = sel;
   if(sel == QATS_PD_NONE)
   {
      pd.eq = 0.0;
      pd.position = 0.5;
      pd.status = StringFormat("REJECTED: no valid H1 dealing range (A %s, B %s, C %s)",
                               (pd.a.valid ? "ok" : "rejected"), (pd.b.valid ? "ok" : "rejected"), (pd.c.valid ? "ok" : "rejected"));
   }
   else
   {
      SPdRange r = (sel == QATS_PD_A) ? pd.a : ((sel == QATS_PD_B) ? pd.b : pd.c);
      pd.eq = r.eq;
      double width = r.high - r.low;
      double pos = (close1 - r.low) / width;
      if(!MathIsValidNumber(pos)) pos = 0.5;
      if(pos < 0.0) pos = 0.0;
      if(pos > 1.0) pos = 1.0;
      pd.position = pos;
      pd.status = (note == "" ? "OK" : "OK (" + note + ")");
   }
   g_pdLastSelected = sel;
}

// one comparison line per evaluation: all THREE equilibriums, the selection, the
// position and the reason - the journal always shows the comparison, never just the verdict
string PdLine(const SPdAdaptive &pd)
{
   string eqA = pd.a.valid ? PriceText(pd.a.eq) : "n/a";
   string eqB = pd.b.valid ? PriceText(pd.b.eq) : "n/a";
   string eqC = pd.c.valid ? PriceText(pd.c.eq) : "n/a";
   return StringFormat("LONG_EQ=%s SHORT_EQ=%s SWING_EQ=%s SELECTED=%s POS=%.2f STATUS=%s",
                       eqA, eqB, eqC, PdLetter(pd.selected), pd.position, pd.status);
}

// Shared side check for BOTH entry paths: is `price` on the allowed side of the
// SELECTED range's equilibrium? Fails closed when no range is valid (protection
// is never silently bypassed); exact equality of price and EQ allows both sides.
bool PdPriceOnSide(const int pdSelected, const double pdEq, const string pdStatus,
                   const int dir, const double price, const string tag, string &why)
{
   if(pdSelected == QATS_PD_NONE)
   {
      why = tag + ": no valid H1 dealing range (A/B/C all rejected) - premium/discount cannot be verified (" + pdStatus + ")";
      return false;
   }
   if(!MathIsValidNumber(price) || price <= 0.0)
   {
      why = tag + ": invalid price for the premium/discount check";
      return false;
   }
   const double eps = pdEq * 1e-9;
   if(dir < 0 && price < pdEq - eps)
   {
      why = StringFormat("%s: SELL at %s is below the selected (%s) equilibrium %s (needs premium) [%s]",
                         tag, PriceText(price), PdLetter(pdSelected), PriceText(pdEq), pdStatus);
      return false;
   }
   if(dir > 0 && price > pdEq + eps)
   {
      why = StringFormat("%s: BUY at %s is above the selected (%s) equilibrium %s (needs discount) [%s]",
                         tag, PriceText(price), PdLetter(pdSelected), PriceText(pdEq), pdStatus);
      return false;
   }
   why = "";
   return true;
}

//+------------------------------------------------------------------+
//| SECTION 12 - LIQUIDITY ENGINE                                    |
//| Buy-side liquidity (BSL) rests above swing highs, equal highs,   |
//| the prior day high and the prior week high. Sell-side liquidity  |
//| (SSL) is the mirror image below lows. Each pool is classified:   |
//|   INTACT   never traded through        -> a liquidity target     |
//|   SWEPT    run, then closed back inside -> reversal evidence     |
//|   ACCEPTED run, two closes beyond       -> breakout, no reversal |
//|   SPENT    run earlier / rejection failed                        |
//| A BUY feeds on swept SSL, a SELL on swept BSL. Both sides are    |
//| built by the same loop body with the comparisons mirrored.       |
//+------------------------------------------------------------------+
// First closed bar NEWER than fromShift that traded through the level
// (below it when wantLow, above it otherwise). 0 = never.
int FirstPierceShift(const string symbol, const ENUM_TIMEFRAMES tf, const int fromShift,
                     const double level, const bool wantLow)
{
   for(int t = fromShift - 1; t >= 1; t--)
   {
      if(wantLow) { if(iLow(symbol, tf, t) < level) return t; }
      else        { if(iHigh(symbol, tf, t) > level) return t; }
   }
   return 0;
}

// Oldest closed bar opened at or after `since` that traded through the level (0 = none).
int FirstPierceSince(const string symbol, const ENUM_TIMEFRAMES tf, const datetime since,
                     const double level, const bool wantLow)
{
   int pierce = 0;
   int bars = iBars(symbol, tf);
   for(int t = 1; t < bars; t++)
   {
      if(iTime(symbol, tf, t) < since) break;
      if(wantLow) { if(iLow(symbol, tf, t) < level) pierce = t; }
      else        { if(iHigh(symbol, tf, t) > level) pierce = t; }
   }
   return pierce;
}

// What happened after a pool was first traded through at `pierce`:
//   +1 swept and rejected: the pierce bar, or the bar right after it, closed back
//      inside, and no later bar has closed beyond the sweep extreme
//   -1 accepted: two consecutive closes beyond the level (a breakout)
//    0 too old, still undecided, or a rejection that later failed
int EvaluatePool(const string symbol, const ENUM_TIMEFRAMES tf, const int pierce, const double level,
                 const bool wantLow, const int window, int &rejectBar, double &extreme)
{
   rejectBar = -1;
   extreme = level;
   if(pierce < 1 || pierce > window + 1) return 0;
   double c0 = iClose(symbol, tf, pierce);
   extreme = wantLow ? iLow(symbol, tf, pierce) : iHigh(symbol, tf, pierce);
   bool inside0 = wantLow ? (c0 > level) : (c0 < level);
   if(inside0)
      rejectBar = pierce;
   else
   {
      if(pierce < 2) return 0;               // closed beyond on the newest bar: not decided yet
      double c1 = iClose(symbol, tf, pierce - 1);
      double x1 = wantLow ? iLow(symbol, tf, pierce - 1) : iHigh(symbol, tf, pierce - 1);
      bool inside1 = wantLow ? (c1 > level) : (c1 < level);
      if(!inside1) return -1;                // second close beyond: accepted
      rejectBar = pierce - 1;
      if(wantLow) { if(x1 < extreme) extreme = x1; }
      else        { if(x1 > extreme) extreme = x1; }
   }
   if(rejectBar > window) return 0;
   for(int t = rejectBar - 1; t >= 1; t--)
   {
      double ct = iClose(symbol, tf, t);
      if(wantLow) { if(ct < extreme) return 0; }
      else        { if(ct > extreme) return 0; }
   }
   return +1;
}

// Classify one level and append it to the map. `pierce` = H1 shift of the first
// closed bar that traded through it since it formed (0 = never).
void AddPool(SLiquidityPool &pools[], const string symbol, const ENUM_TIMEFRAMES tf, const double price,
             const string kind, const bool buySide, const int shift, const int pierce, const int window)
{
   int n = ArraySize(pools);
   if(n >= QATS_MAX_POOLS || price <= 0.0) return;
   ArrayResize(pools, n + 1);
   pools[n].price    = price;
   pools[n].kind     = kind;
   pools[n].buySide  = buySide;
   pools[n].shift    = shift;
   pools[n].state    = QATS_POOL_INTACT;
   pools[n].eventBar = -1;
   pools[n].extreme  = price;
   if(pierce < 1) return;
   int rejectBar = -1;
   double extreme = price;
   // sell-side liquidity is run by LOWS, buy-side liquidity by HIGHS
   int verdict = EvaluatePool(symbol, tf, pierce, price, !buySide, window, rejectBar, extreme);
   pools[n].extreme = extreme;
   if(verdict > 0)      { pools[n].state = QATS_POOL_SWEPT;    pools[n].eventBar = rejectBar; }
   else if(verdict < 0) { pools[n].state = QATS_POOL_ACCEPTED; pools[n].eventBar = pierce - 1; }
   else                   pools[n].state = QATS_POOL_SPENT;
}

// duplicate resolution for pools at the same level: stronger kind wins; on equal
// rank keep the newer formation (shift 0 = day/week boundary counts as newest);
// fully equal = keep the first.
bool PoolBetter(const SLiquidityPool &a, const SLiquidityPool &b)
{
   int ra = PoolRank(a.kind), rb = PoolRank(b.kind);
   if(ra != rb) return ra > rb;
   if(a.shift == b.shift) return false;
   if(a.shift == 0) return true;
   if(b.shift == 0) return false;
   return a.shift < b.shift;
}

// how decisive a pool state is, for folding merged duplicates: a consumed level
// must never read INTACT just because the twin that got run had the weaker kind.
// ACCEPTED (breakout accepted) > SWEPT (sweep confirmed) > SPENT (pierced, evidence
// unusable) > INTACT (never touched).
int PoolStateDecision(const int state)
{
   if(state == QATS_POOL_ACCEPTED) return 3;
   if(state == QATS_POOL_SWEPT)    return 2;
   if(state == QATS_POOL_SPENT)    return 1;
   return 0;
}

// fold a removed member's evidence into the survivor: the most decided state wins
// (with that member's event bar); on equal conviction keep the further reach and the
// later (nearest) event bar. Kind, price and shift stay the winner's identity.
void PoolFoldState(SLiquidityPool &into, const SLiquidityPool &from)
{
   int di = PoolStateDecision(into.state), df = PoolStateDecision(from.state);
   if(df > di)
   {
      into.state    = from.state;
      into.eventBar = from.eventBar;
   }
   else if(df == di && di >= 2 && from.eventBar >= 1)
   {
      if(into.eventBar < 1 || from.eventBar > into.eventBar) into.eventBar = from.eventBar;
   }
   if(from.buySide) into.extreme = MathMax(into.extreme, from.extreme);
   else             into.extreme = MathMin(into.extreme, from.extreme);
}

// merge ONE side in-place; every group is anchored at its first (oldest-in-creation)
// member and everything within tolerance of the ANCHOR level is removed except the
// winner. Deterministic, side-local and replay-symmetric. The survivor carries the
// most DECIDED state of the group (see PoolFoldState), so a consumed level can never
// re-enter the map as INTACT.
void MergeSideDuplicates(SLiquidityPool &pools[], const double tol, int &merged)
{
   for(int i = 0; i < ArraySize(pools);)
   {
      int winner = i;
      bool hasDup = false;
      for(int j = i + 1; j < ArraySize(pools); j++)
         if(MathAbs(pools[j].price - pools[i].price) <= tol)
         { hasDup = true; if(PoolBetter(pools[j], pools[winner])) winner = j; }
      if(!hasDup) { i++; continue; }
      double refPrice = pools[i].price;             // the anchor's level defines the group
      if(winner != i)
      {
         // promote the winner to the anchor; the anchor (now at winner's slot) is
         // removed by the erase below because it is within tolerance of itself
         SLiquidityPool win = pools[winner];
         pools[winner] = pools[i];
         pools[i] = win;
      }
      int j = ArraySize(pools) - 1;
      while(j > i)
      {
         if(MathAbs(pools[j].price - refPrice) <= tol)
         {
            merged++;
            PoolFoldState(pools[i], pools[j]);
            pools[j] = pools[ArraySize(pools) - 1];
            ArrayResize(pools, ArraySize(pools) - 1);
            j = MathMin(j, ArraySize(pools) - 1);
         }
         else j--;
      }
      i++;
   }
}

string PoolStateName(const int state)
{
   if(state == QATS_POOL_INTACT)   return "INTACT";
   if(state == QATS_POOL_SWEPT)    return "SWEPT";
   if(state == QATS_POOL_ACCEPTED) return "ACCEPTED";
   if(state == QATS_POOL_SPENT)    return "SPENT";
   return "UNKNOWN";
}

int BuildLiquidityMap(const string symbol, const ENUM_TIMEFRAMES tf, const SSwing &highs[], const SSwing &lows[],
                      const double tol, const int window, SLiquidityPool &pools[])
{
   ArrayResize(pools, 0);
   for(int side = 0; side < 2; side++)
   {
      bool buySide = (side == 0);
      int n = buySide ? ArraySize(highs) : ArraySize(lows);
      for(int j = 0; j < n; j++)
      {
         double price = buySide ? highs[j].price : lows[j].price;
         int shift    = buySide ? highs[j].shift : lows[j].shift;
         // equal highs / equal lows: an OLDER swing of the same kind within tolerance
         bool equal = false;
         for(int m = j + 1; m < n && !equal; m++)
         {
            double other = buySide ? highs[m].price : lows[m].price;
            if(MathAbs(other - price) <= tol) equal = true;
         }
         string kind = "SWING";
         if(equal) kind = (buySide ? "EQH" : "EQL");
         AddPool(pools, symbol, tf, price, kind, buySide, shift,
                 FirstPierceShift(symbol, tf, shift, price, !buySide), window);
      }
      // prior day / prior week extremes are liquidity for the CURRENT day / week
      double pd = buySide ? iHigh(symbol, PERIOD_D1, 1) : iLow(symbol, PERIOD_D1, 1);
      datetime daySince = iTime(symbol, PERIOD_D1, 0);
      if(pd > 0.0 && daySince > 0)
         AddPool(pools, symbol, tf, pd, (buySide ? "PDH" : "PDL"), buySide, 0,
                 FirstPierceSince(symbol, tf, daySince, pd, !buySide), window);
      double pw = buySide ? iHigh(symbol, PERIOD_W1, 1) : iLow(symbol, PERIOD_W1, 1);
      datetime weekSince = iTime(symbol, PERIOD_W1, 0);
      if(pw > 0.0 && weekSince > 0)
         AddPool(pools, symbol, tf, pw, (buySide ? "PWH" : "PWL"), buySide, 0,
                 FirstPierceSince(symbol, tf, weekSince, pw, !buySide), window);
   }
   // v1.24: merge duplicate pools on the same side inside the tolerance - one level,
   // one identity (PDH/PWH may coincide with a swing or an equal-high). Keep the
   // stronger kind, then the NEWER level (shift 0 = the day/week boundary counts
   // as newest). Each side is merged INDEPENDENTLY (the shared array's BSL block
   // comes first, so a cross-side swap-with-last here would reorder the SSL block
   // and break replay symmetry); the two blocks are recombined afterwards in their
   // original order. Scoring and target selection are boolean/nearest, so behaviour
   // is unchanged apart from the de-duplication itself.
   SLiquidityPool buyPools[], sellPools[];
   for(int i = 0; i < ArraySize(pools); i++)
   {
      int n = 0;
      if(pools[i].buySide)
      {
         n = ArraySize(buyPools);
         ArrayResize(buyPools, n + 1);
         buyPools[n] = pools[i];
      }
      else
      {
         n = ArraySize(sellPools);
         ArrayResize(sellPools, n + 1);
         sellPools[n] = pools[i];
      }
   }
   int merged = 0;
   MergeSideDuplicates(buyPools, tol, merged);
   MergeSideDuplicates(sellPools, tol, merged);
   int idx = 0;
   ArrayResize(pools, ArraySize(buyPools) + ArraySize(sellPools));
   for(int i = 0; i < ArraySize(buyPools); i++, idx++) pools[idx] = buyPools[i];
   for(int i = 0; i < ArraySize(sellPools); i++, idx++) pools[idx] = sellPools[i];
   if(merged > 0)
      PrintFormat("[QATS][LIQUIDITY] merged %d duplicate level(s) within tolerance (one level = one identity)", merged);
   return ArraySize(pools);
}

// Transition memory for the liquidity journal (per attach). Pools are rebuilt from
// closed bars every evaluation, so a verdict change is visible exactly once - when
// the new bar changes it. One line per transition, with the bar and the level.
SLiquidityPool g_prevPools[];
int            g_prevPoolCount = 0;

void JournalLiquidityTransitions(const SLiquidityPool &pools[], const int n, const double tol)
{
   for(int i = 0; i < n; i++)
   {
      int prev = -1;
      for(int j = 0; j < g_prevPoolCount && j < ArraySize(g_prevPools); j++)
      {
         if(g_prevPools[j].buySide == pools[i].buySide &&
            MathAbs(g_prevPools[j].price - pools[i].price) <= MathMax(tol, _Point))
         { prev = j; break; }
      }
      if(prev < 0) continue;                          // a new pool appearance is not a transition
      int prevState = g_prevPools[prev].state;
      if(prevState == pools[i].state) continue;
      PrintFormat("[QATS][LIQUIDITY] TRANSITION side=%s kind=%s level=%s state=%s->%s %s extreme=%s",
                  (pools[i].buySide ? "BSL" : "SSL"), pools[i].kind, PriceText(pools[i].price),
                  PoolStateName(prevState), PoolStateName(pools[i].state),
                  (pools[i].eventBar >= 1
                     ? ("bar=" + TimeToString(iTime(_Symbol, PERIOD_H1, pools[i].eventBar), TIME_DATE | TIME_MINUTES))
                     : "bar=-"),
                  PriceText(pools[i].extreme));
   }
   ArrayResize(g_prevPools, n);
   for(int i = 0; i < n; i++) g_prevPools[i] = pools[i];
   g_prevPoolCount = n;
}

int PoolRank(const string kind)
{
   if(kind == "PWH" || kind == "PWL") return 4;
   if(kind == "PDH" || kind == "PDL") return 3;
   if(kind == "EQH" || kind == "EQL") return 2;
   if(kind == "SWING") return 1;
   return 0;
}

// The newest standing sweep of the liquidity a trade in `dir` feeds on:
// a BUY needs SELL-side liquidity run and rejected, a SELL needs BUY-side.
void SweepForDirection(const SLiquidityPool &pools[], const int dir, SSweep &out)
{
   out.found = false; out.bar = -1; out.tf = PERIOD_CURRENT; out.poolShift = -1; out.eventTime = 0;
   out.level = 0.0; out.extreme = 0.0; out.pool = ""; out.breakout = false;
   bool wantBuySide = (dir < 0);
   int n = ArraySize(pools);
   for(int i = 0; i < n; i++)
   {
      if(pools[i].buySide != wantBuySide) continue;
      if(pools[i].state == QATS_POOL_ACCEPTED) { out.breakout = true; continue; }
      if(pools[i].state != QATS_POOL_SWEPT) continue;
      if(!out.found || pools[i].eventBar < out.bar)
      {
         out.found = true;
         out.bar = pools[i].eventBar;
         out.tf = PERIOD_H1;                       // the map is H1-built; stored explicitly like dispTF
         out.poolShift = pools[i].shift;
         out.eventTime = iTime(_Symbol, PERIOD_H1, pools[i].eventBar);
         out.level = pools[i].price;
         out.extreme = pools[i].extreme;
         out.pool = pools[i].kind;
      }
      else if(pools[i].eventBar == out.bar)
      {
         // one bar ran several pools: keep the deepest extreme and the strongest label
         if(wantBuySide) { if(pools[i].extreme > out.extreme) out.extreme = pools[i].extreme; }
         else            { if(pools[i].extreme < out.extreme) out.extreme = pools[i].extreme; }
         if(PoolRank(pools[i].kind) > PoolRank(out.pool)) { out.pool = pools[i].kind; out.level = pools[i].price; out.poolShift = pools[i].shift; }
      }
   }
}

// Nearest INTACT pool beyond the entry on the side a trade in `dir` targets
// (buy-side liquidity for a BUY, sell-side for a SELL) that pays at least minRR.
// Charts are drawn from the BID. A BUY is closed on the bid, so its target is the
// level itself; a SELL is closed on the ASK, which reaches the level one spread
// later, so its target is the level plus the spread. Both then fill on the same touch.
bool NearestLiquidityTarget(const SLiquidityPool &pools[], const int dir, const double entry,
                            const double stopDist, const double minRR, const double spread,
                            double &target, string &kind, double &poolLevel)
{
   target = 0.0;
   kind = "";
   poolLevel = 0.0;
   if(stopDist <= 0.0) return false;
   bool wantBuySide = (dir > 0);
   bool have = false;
   double bestReward = 0.0;
   int n = ArraySize(pools);
   for(int i = 0; i < n; i++)
   {
      if(pools[i].buySide != wantBuySide || pools[i].state != QATS_POOL_INTACT) continue;
      double tpPrice = wantBuySide ? pools[i].price : pools[i].price + spread;
      double reward  = wantBuySide ? (tpPrice - entry) : (entry - tpPrice);
      if(reward <= 0.0 || reward / stopDist < minRR) continue;
      if(!have || reward < bestReward)
      {
         have = true;
         bestReward = reward;
         target = tpPrice;
         kind = pools[i].kind;
         poolLevel = pools[i].price;   // the POOL's own level, not the spread-shifted tpPrice
      }
   }
   return have;
}

// Shift of the newest CLOSED bar (shift >= 1) whose open time is at or before t.
// Bars with missing timestamps (weekends, holidays) are skipped naturally because
// the loop reads actual bar times. Returns -1 when t is older than maxShift.
// Replaces iBarShift so the closed-bar clock stays explicit (and the offline
// host build does not need a bar-shift primitive).
int ShiftOfTime(const string symbol, const ENUM_TIMEFRAMES tf, const datetime t, const int maxShift)
{
   if(t <= 0 || maxShift < 1) return -1;
   for(int s = 1; s <= maxShift; s++)
   {
      datetime bt = iTime(symbol, tf, s);
      if(bt == 0) return -1;
      if(bt <= t) return s;
   }
   return -1;
}

// displacement = a strong directional closed bar (impulse), searched from the newest
// closed bar back to maxShift (the sweep's rejection bar when the side has a sweep,
// so an impulse that came BEFORE the stop run is never counted as its confirmation)
bool DetectDisplacement(const string symbol, const ENUM_TIMEFRAMES tf, const bool wantBull,
                        const double atr, const int maxShift, int &barOut)
{
   barOut = -1;
   for(int s = 1; s <= maxShift; s++)
   {
      double o = iOpen(symbol, tf, s);
      double c = iClose(symbol, tf, s);
      double h = iHigh(symbol, tf, s);
      double l = iLow(symbol, tf, s);
      double body = MathAbs(c - o);
      double range = h - l;
      if(body <= 0.0 || range <= 0.0) continue;
      bool dirOk = wantBull ? (c > o) : (c < o);
      if(!dirOk) continue;
      bool byAtr  = body >= InpDisplaceATR * atr;
      bool byBody = (body / range >= InpDisplaceBodyRatio) && (range >= 1.3 * atr);
      if(byAtr || byBody) { barOut = s; return true; }
   }
   return false;
}

//+------------------------------------------------------------------+
//| SECTION 13 - ORDER BLOCKS & FAIR VALUE GAPS                      |
//+------------------------------------------------------------------+
bool FindOrderBlock(const string symbol, const ENUM_TIMEFRAMES tf, const bool wantBull,
                    const int impulseShift, const int maxBack, SZone &zone)
{
   zone.found = false;
   zone.isFVG = false;
   int bars = iBars(symbol, tf);
   int start = impulseShift + 1;
   int stop  = MathMin(impulseShift + maxBack, bars - 1);
   for(int s = start; s <= stop; s++)
   {
      double o = iOpen(symbol, tf, s);
      double c = iClose(symbol, tf, s);
      if(wantBull && c < o)
      {
         zone.bottom = iLow(symbol, tf, s);
         zone.top    = MathMax(o, c);
         zone.shift  = s;
         zone.found  = true;
         return true;
      }
      if(!wantBull && c > o)
      {
         zone.top    = iHigh(symbol, tf, s);
         zone.bottom = MathMin(o, c);
         zone.shift  = s;
         zone.found  = true;
         return true;
      }
   }
   return false;
}

bool FindFVG(const string symbol, const ENUM_TIMEFRAMES tf, const bool wantBull,
             const int fromShift, SZone &zone)
{
   zone.found = false;
   zone.isFVG = true;
   int bars = iBars(symbol, tf);
   int newest = MathMax(2, fromShift);   // triple (s+1, s, s-1), all closed bars
   for(int s = newest; s >= 1; s--)
   {
      int older = s + 1;
      if(older >= bars) continue;
      int newer = s - 1;
      if(newer < 1) continue;
      double hOlder = iHigh(symbol, tf, older);
      double lOlder = iLow(symbol, tf, older);
      double hNewer = iHigh(symbol, tf, newer);
      double lNewer = iLow(symbol, tf, newer);
      if(wantBull && hOlder < lNewer)          // gap up: imbalance
      {
         zone.bottom = hOlder;
         zone.top    = lNewer;
         zone.shift  = s;
         zone.found  = true;
         return true;
      }
      if(!wantBull && lOlder > hNewer)         // gap down: imbalance
      {
         zone.bottom = hNewer;
         zone.top    = lOlder;
         zone.shift  = s;
         zone.found  = true;
         return true;
      }
   }
   return false;
}

bool PriceNearZone(const string symbol, const SZone &zone, const double atr, const double toleranceATR)
{
   if(!zone.found) return false;
   double price = iClose(symbol, PERIOD_M5, 1);
   double pad = atr * toleranceATR;
   return (price >= zone.bottom - pad && price <= zone.top + pad);
}

// A demand zone is spent once a later bar CLOSES below it, a supply zone once one
// closes above it. fromShift = the first bar after the zone's impulse.
// CR-7: never trust a zone whose post-formation bars cannot be verified. A close
// beyond the zone used to read as 0.0 on missing history and therefore PASS.
// Now the check fails closed (the zone is rejected) and journals once per attach.
bool ZoneStillValid(const string symbol, const ENUM_TIMEFRAMES tf, const bool wantBull,
                    const SZone &zone, const int fromShift)
{
   if(!zone.found) return false;
   if(!MathIsValidNumber(zone.bottom) || !MathIsValidNumber(zone.top) ||
      zone.top <= 0.0 || zone.bottom <= 0.0 || zone.bottom > zone.top)
   {
      if(!g_loggedZoneHistoryFail)
      {
         g_loggedZoneHistoryFail = true;
         Print("[QATS][ZONE] invalid zone numbers - zone rejected (fail closed)");
      }
      return false;
   }
   if(fromShift < 1) return true;   // nothing closed after the zone yet: it just formed
   int bars = iBars(symbol, tf);
   if(bars < 2 || fromShift >= bars)
   {
      if(!g_loggedZoneHistoryFail)
      {
         g_loggedZoneHistoryFail = true;
         Print("[QATS][ZONE] insufficient closed-bar history to verify zone survival - zone rejected (fail closed)");
      }
      return false;
   }
   for(int t = fromShift; t >= 1; t--)
   {
      double c = iClose(symbol, tf, t);
      if(c <= 0.0 || !MathIsValidNumber(c))
      {
         if(!g_loggedZoneHistoryFail)
         {
            g_loggedZoneHistoryFail = true;
            Print("[QATS][ZONE] unreadable closed bar at shift " + IntegerToString(t) + " - zone rejected (fail closed)");
         }
         return false;
      }
      if(wantBull) { if(c < zone.bottom) return false; }
      else         { if(c > zone.top) return false; }
   }
   return true;
}

//+------------------------------------------------------------------+
//| SECTION 14 - M15 CONFIRMATION & M5 ENTRY TRIGGERS                |
//+------------------------------------------------------------------+
bool M15Confirms(const SReading &r, const int dir)
{
   if(dir > 0) return (r.m15Close > r.m15Open && r.m15Close >= r.m15Fast);
   if(dir < 0) return (r.m15Close < r.m15Open && r.m15Close <= r.m15Fast);
   return false;
}

bool M5Trigger(const string symbol, const int dir)
{
   double o1 = iOpen(symbol, PERIOD_M5, 1);
   double c1 = iClose(symbol, PERIOD_M5, 1);
   double h1 = iHigh(symbol, PERIOD_M5, 1);
   double l1 = iLow(symbol, PERIOD_M5, 1);
   double o2 = iOpen(symbol, PERIOD_M5, 2);
   double c2 = iClose(symbol, PERIOD_M5, 2);
   double body = MathAbs(c1 - o1);
   double range = h1 - l1;
   if(range <= 0.0) return false;
   double upperWick = h1 - MathMax(o1, c1);
   double lowerWick = MathMin(o1, c1) - l1;

   if(dir > 0)
   {
      // bullish engulfing
      if(c1 > o1 && c2 < o2 && c1 >= o2 && o1 <= c2) return true;
      // bullish pin bar (long lower wick)
      if(lowerWick >= 2.0 * body && lowerWick >= 0.5 * range) return true;
      // bullish marubozu / strong close
      if((c1 - o1) / range >= 0.65) return true;
      return false;
   }
   // bearish engulfing
   if(c1 < o1 && c2 > o2 && o1 >= c2 && c1 <= o2) return true;
   // bearish pin bar (long upper wick)
   if(upperWick >= 2.0 * body && upperWick >= 0.5 * range) return true;
   // bearish marubozu / strong close
   if((o1 - c1) / range >= 0.65) return true;
   return false;
}

//+------------------------------------------------------------------+
//| SECTION 15 - DUAL-DIRECTION ANALYSIS & CONFLUENCE SCORING        |
//| Filter classes:                                                  |
//|   MANDATORY RISK PROTECTION  - section 18, never configurable    |
//|                                away below the code hard caps     |
//|   CORE STRATEGY CONFIRMATION - sweep / displacement / BOS-CHoCH  |
//|                                as required by InpStrategyProfile |
//|   OPTIONAL CONFLUENCE        - D1/H4 bias, zone, premium/discount|
//|                                VWAP, volume, M15, M5: score only |
//|   INFORMATIONAL ONLY         - breakout acceptance, signal class |
//+------------------------------------------------------------------+
// XAUUSD broker suffixes are supported; unrelated symbols keep their profile policy.
bool IsXAUUSD()
{
   string symbol = _Symbol;
   StringToUpper(symbol);
   return StringFind(symbol, "XAUUSD") == 0;
}

int QATS_DirectionVeto(const bool isGold, const int dir, const int d1, const int h4,
                       const bool emaVeto, const bool allowCounter)
{
   if(isGold || dir == 0) return 0;
   if(emaVeto && d1 == -dir && h4 == -dir) return 1;
   if(!allowCounter && d1 == -dir) return 2;
   return 0;
}

bool QATS_ScoreEligible(const int dir, const int score, const int minimum)
{
   return (dir == 1 || dir == -1) && score >= minimum;
}

// Stop distances use the closing quote, not the opening quote.
bool QATS_StopsValid(const int dir, const double bid, const double ask,
                     const double sl, const double tp, const double minDist)
{
   if((dir != 1 && dir != -1) || !MathIsValidNumber(bid) || !MathIsValidNumber(ask) ||
      !MathIsValidNumber(sl) || !MathIsValidNumber(tp) || !MathIsValidNumber(minDist) ||
      bid <= 0.0 || ask < bid || sl <= 0.0 || tp <= 0.0 || minDist <= 0.0)
      return false;
   if(dir == 1) return sl < bid && tp > ask && bid - sl >= minDist && tp - bid >= minDist;
   return sl > ask && tp < bid && sl - ask >= minDist && ask - tp >= minDist;
}

// Snap a price to the tick grid: up=true rounds up, false rounds down. A price that
// already sits on the grid (within a millionth of a tick) is left where it is.
double QATS_SnapToTick(const double price, const double tick, const int digits, const bool up)
{
   if(tick <= 0.0) return price;
   double q = price / tick;
   double snapped = up ? MathCeil(q - 0.000001) : MathFloor(q + 0.000001);
   return NormalizeDouble(snapped * tick, digits);
}

// Sum of the confluence weights for one side. One table, both directions.
int QATS_ScoreSide(const SSide &e)
{
   int score = 0;
   if(e.biasD1)                    score += QATS_W_BIAS_D1;
   if(e.biasH4)                    score += QATS_W_BIAS_H4;
   if(e.structure)                 score += QATS_W_STRUCTURE;
   if(e.sweep.found)               score += QATS_W_SWEEP;
   if(e.displaced)                 score += QATS_W_DISPLACEMENT;
   if(e.zoneTouched)               score += QATS_W_ZONE_TOUCH;
   else if(e.hasOB || e.hasFVG)    score += QATS_W_ZONE_PRESENT;
   if(e.location)                  score += QATS_W_LOCATION;
   if(e.vwapSide)                  score += QATS_W_VWAP;
   if(e.volume)                    score += QATS_W_VOLUME;
   if(e.confirmM15)                score += QATS_W_M15;
   if(e.triggerM5)                 score += QATS_W_M5;
   return score;
}

// Core strategy confirmation. A liquidity sweep on its own passes NO profile.
bool QATS_CoreGate(const int profile, const bool sweep, const bool displaced, const bool structure,
                   const bool ltfConfirm, string &why)
{
   why = "";
   int count = (sweep ? 1 : 0) + (displaced ? 1 : 0) + (structure ? 1 : 0);
   if(profile == QATS_PROFILE_CONSERVATIVE)
   {
      if(!sweep)           why = "no liquidity sweep";
      else if(!displaced)  why = "no displacement after the sweep";
      else if(!structure)  why = "no BOS/CHoCH";
      else if(!ltfConfirm) why = "no M15/M5 confirmation";
      return (why == "");
   }
   if(profile == QATS_PROFILE_BALANCED)
   {
      if(!displaced && !structure) why = (sweep ? "sweep alone: no displacement and no BOS/CHoCH" : "no displacement and no BOS/CHoCH");
      else if(!displaced)          why = "no displacement";
      else if(!structure)          why = "no BOS/CHoCH";
      return (why == "");
   }
   // ACTIVE: any two of the three core events
   if(count >= 2) return true;
   if(count == 0)      why = "no sweep, no displacement, no BOS/CHoCH";
   else if(sweep)      why = "sweep alone: no displacement and no BOS/CHoCH";
   else if(displaced)  why = "displacement alone";
   else                why = "BOS/CHoCH alone";
   return false;
}

// Deterministic direction policy. Returns +1 / -1 / 0 and names the rule used.
// The rules are symmetric: swapping the two sides (and the sign of every bias)
// swaps the answer.
int QATS_ResolveDirection(const bool buyOk, const bool sellOk, const int buyScore, const int sellScore,
                          const int margin, const int h1Trend, const int d1Bias, const int h4Bias, string &rule)
{
   if(buyOk && !sellOk)   { rule = "ONLY_BUY_ELIGIBLE";  return +1; }
   if(sellOk && !buyOk)   { rule = "ONLY_SELL_ELIGIBLE"; return -1; }
   if(!buyOk && !sellOk)  { rule = "NONE_ELIGIBLE";      return 0; }
   int diff = buyScore - sellScore;
   if(diff > 0 && diff >= margin)   { rule = "CONFLICT_HIGHER_SCORE"; return +1; }
   if(diff < 0 && -diff >= margin)  { rule = "CONFLICT_HIGHER_SCORE"; return -1; }
   if(h1Trend > 0) { rule = "CONFLICT_H1_STRUCTURE"; return +1; }
   if(h1Trend < 0) { rule = "CONFLICT_H1_STRUCTURE"; return -1; }
   if(d1Bias > 0)  { rule = "CONFLICT_D1_BIAS"; return +1; }
   if(d1Bias < 0)  { rule = "CONFLICT_D1_BIAS"; return -1; }
   if(h4Bias > 0)  { rule = "CONFLICT_H4_BIAS"; return +1; }
   if(h4Bias < 0)  { rule = "CONFLICT_H4_BIAS"; return -1; }
   rule = "CONFLICT_UNRESOLVED";
   return 0;
}

// The side closest to trading, for the journal only: a side whose core passed
// beats one whose core failed; otherwise the higher score; a tie names nobody.
int QATS_Candidate(const bool buyCore, const bool sellCore, const int buyScore, const int sellScore)
{
   if(buyCore && !sellCore) return +1;
   if(sellCore && !buyCore) return -1;
   if(buyScore > sellScore) return +1;
   if(sellScore > buyScore) return -1;
   return 0;
}

// +1 winning position, -1 losing position, 0 neutral. band = money tolerance.
int QATS_ClassifyClose(const double net, const double band)
{
   double b = (band > 0.0 ? band : 0.0);
   if(net > b)  return +1;
   if(net < -b) return -1;
   return 0;
}

long QATS_CooldownRemaining(const datetime now, const datetime until)
{
   if(until <= 0 || now >= until) return 0;
   return (long)(until - now);
}

string QATS_StrategyProfileName(const int profile)
{
   if(profile == QATS_PROFILE_CONSERVATIVE) return "CONSERVATIVE";
   if(profile == QATS_PROFILE_ACTIVE)       return "ACTIVE";
   return "BALANCED";
}

int SideIndex(const int dir)
{
   return (dir > 0 ? 0 : 1);
}

string SideName(const int dir)
{
   if(dir > 0) return "BUY";
   if(dir < 0) return "SELL";
   return "NONE";
}

string VetoName(const int veto)
{
   if(veto == 1) return "EMA_ALIGNMENT_VETO";
   if(veto == 2) return "COUNTER_D1_BIAS_VETO";
   return "none";
}

// Setup identity as one token: side + H1 open time of the structural event.
string SetupId(const int dir, const datetime t)
{
   if(dir == 0 || t <= 0) return "none";
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%s-%04d%02d%02d-%02d%02d", (dir > 0 ? "B" : "S"), dt.year, dt.mon, dt.day, dt.hour, dt.min);
}

string PriceText(const double price)
{
   return DoubleToString(price, g_spec.digits);
}

// Short timeframe name for journal lines (the offline shim has no TimeframeToString).
string TFName(const ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      default:         return "TF?";
   }
}

string BarText(const ENUM_TIMEFRAMES tf, const int shift)
{
   if(shift < 1) return "none";
   return TimeToString(iTime(_Symbol, tf, shift), TIME_DATE | TIME_MINUTES);
}

string H1BarText(const int shift)
{
   return BarText(PERIOD_H1, shift);
}

void ResetSide(SSide &e, const int dir)
{
   e.dir = dir;
   e.biasD1 = false; e.biasH4 = false;
   e.structure = false; e.structChoch = false; e.structBar = -1; e.structLevel = 0.0;
   e.sweep.found = false; e.sweep.bar = -1; e.sweep.tf = PERIOD_CURRENT; e.sweep.poolShift = -1;
   e.sweep.eventTime = 0; e.sweep.level = 0.0; e.sweep.extreme = 0.0;
   e.sweep.pool = ""; e.sweep.breakout = false;
   e.displaced = false; e.dispBar = -1; e.dispTF = PERIOD_CURRENT;
   e.hasOB = false; e.hasFVG = false;
   e.ob.top = 0.0; e.ob.bottom = 0.0; e.ob.shift = 0; e.ob.isFVG = false; e.ob.found = false;
   e.fvg.top = 0.0; e.fvg.bottom = 0.0; e.fvg.shift = 0; e.fvg.isFVG = true; e.fvg.found = false;
   e.zoneTouched = false; e.location = false; e.vwapSide = false; e.volume = false;
   e.confirmM15 = false; e.triggerM5 = false;
   e.score = 0; e.coreCount = 0; e.corePass = false; e.coreWhy = "not evaluated";
   e.veto = 0; e.eligible = false; e.setupTime = 0;
}

void ResetAnalysis(SAnalysis &a)
{
   a.signalBar = 0; a.dataReady = false;
   a.dir = 0; a.candidate = 0; a.score = 0;
   a.d1Bias = 0; a.h4Bias = 0; a.h1Struct = 0;
   a.dealPos = 0.5;
   a.regime = "UNCLEAR"; a.regimeVolRatio = 0.0; a.regimeRangeRatio = 0.0;
   a.pdEq = 0.0; a.pdLongEq = 0.0; a.pdShortEq = 0.0; a.pdSwingEq = 0.0;
   a.pdLongValid = false; a.pdShortValid = false; a.pdSwingValid = false;
   a.pdSelected = QATS_PD_NONE; a.pdStatus = "UNCOMPUTED";
   a.vwap = 0.0;
   ResetSide(a.buy, +1);
   ResetSide(a.sell, -1);
   a.conflict = false; a.resolution = ""; a.setupTime = 0;
   a.entry = 0.0; a.sl = 0.0; a.tp = 0.0; a.stopDist = 0.0;
   a.tpSource = ""; a.tpLevel = 0.0; a.reason = "";
}

// Evidence for ONE direction. BUY and SELL are both produced by this function;
// `bull` flips every comparison, nothing else differs between the two calls.
void EvaluateSide(const int dir, const SReading &r, const SStructure &st, const SLiquidityPool &pools[],
                  const int d1Bias, const int h4Bias, const double dealPos, const double pxNow, SSide &e)
{
   ResetSide(e, dir);
   bool bull = (dir > 0);
   int window = MathMax(1, InpSetupWindowBars);

   // optional confluence: higher-timeframe bias
   e.biasD1 = (d1Bias == dir);
   e.biasH4 = (h4Bias == dir);

   // core: the most recent H1 break of structure is in this direction and still fresh
   e.structure   = (st.breakDir == dir && st.breakBar >= 1 && st.breakBar <= window);
   e.structChoch = (e.structure && st.breakIsChoch);
   e.structBar   = (e.structure ? st.breakBar : -1);
   e.structLevel = (e.structure ? st.breakLevel : 0.0);

   // core: opposing liquidity run and rejected
   SweepForDirection(pools, dir, e.sweep);

   // core: displacement - at or after the sweep when there is one, else inside the window.
   // H1 is checked first, exactly as before. Only when H1 shows no impulse is M15
   // scanned, with the M15 ATR. An M15 displacement is reported as its own timeframe
   // (e.dispTF/e.dispBar) and is NEVER used as if it were an H1 bar index.
   int dispBar = -1;
   int dispFrom = (e.sweep.found ? e.sweep.bar : window);
   e.displaced = DetectDisplacement(_Symbol, PERIOD_H1, bull, r.atrH1, dispFrom, dispBar);
   e.dispTF = PERIOD_CURRENT;

   if(e.displaced)
   {
      e.dispTF = PERIOD_H1;
      e.dispBar = dispBar;
   }
   else if(InpDisplaceM15)
   {
      // M15 fallback (v1.23, switchable with InpDisplaceM15). The search starts at
      // the M15 bar that CONTAINS the sweep rejection H1 bar's open, so an impulse
      // strictly before the sweep is never counted - the same "at or after the
      // sweep" rule the H1 path enforces.
      int dispFromM15 = window * 4;
      if(e.sweep.found)
      {
         datetime sweepOpen = iTime(_Symbol, PERIOD_H1, e.sweep.bar);
         int m15From = ShiftOfTime(_Symbol, PERIOD_M15, sweepOpen, window * 4 + 16);
         if(m15From >= 1) dispFromM15 = m15From;
      }
      int m15Bar = -1;
      e.displaced = DetectDisplacement(_Symbol, PERIOD_M15, bull, r.atrM15, dispFromM15, m15Bar);
      if(e.displaced)
      {
         e.dispTF = PERIOD_M15;
         e.dispBar = m15Bar;
      }
   }
   if(!e.displaced) e.dispBar = -1;

   // optional confluence: order block / fair value gap LEFT BY THE IMPULSE, still
   // unmitigated. Zone work runs on H1 bars only: an H1 displacement anchors at its
   // own bar; an M15 displacement anchors at the closed H1 bar containing it, never
   // at the raw M15 index. A setup WITHOUT a displacement (sweep-only or
   // structure-only) yields NO zones: a gap that did not form around an impulse is
   // not displacement-validated and is never scored (mandate: FVG must be
   // displacement-validated). Mitigated zones are rejected by ZoneStillValid.
   int impulse = 0;
   if(e.displaced && e.dispTF == PERIOD_H1) impulse = e.dispBar;
   else if(e.displaced && e.dispTF == PERIOD_M15)
   {
      datetime impTime = iTime(_Symbol, PERIOD_M15, e.dispBar);
      int h1 = ShiftOfTime(_Symbol, PERIOD_H1, impTime, window + 4);
      if(h1 >= 1) impulse = h1;               // without the containing H1 bar there is no anchor and no zone
   }
   if(impulse > 0)
   {
      e.hasOB = FindOrderBlock(_Symbol, PERIOD_H1, bull, impulse, 12, e.ob);
      if(e.hasOB && !ZoneStillValid(_Symbol, PERIOD_H1, bull, e.ob, impulse - 1))
      { e.hasOB = false; e.ob.found = false; }
      e.hasFVG = FindFVG(_Symbol, PERIOD_H1, bull, impulse, e.fvg);
      if(e.hasFVG && !ZoneStillValid(_Symbol, PERIOD_H1, bull, e.fvg, e.fvg.shift - 2))
      { e.hasFVG = false; e.fvg.found = false; }
      e.zoneTouched = (PriceNearZone(_Symbol, e.ob, r.atrH1, 0.30) ||
                       PriceNearZone(_Symbol, e.fvg, r.atrH1, 0.30));
   }

   // optional confluence: location, VWAP, lower timeframes, participation
   e.location   = bull ? (dealPos < 0.5) : (dealPos > 0.5);
   e.vwapSide   = bull ? (pxNow > r.vwap) : (pxNow < r.vwap);
   e.confirmM15 = M15Confirms(r, dir);
   e.triggerM5  = M5Trigger(_Symbol, dir);
   double m5Open = iOpen(_Symbol, PERIOD_M5, 1);
   bool closedOurWay = bull ? (pxNow > m5Open) : (pxNow < m5Open);
   e.volume = (closedOurWay && r.volM5Avg > 0.0 && r.volM5Last > 1.2 * r.volM5Avg);

   e.score = QATS_ScoreSide(e);

   // core confirmation of the active profile; the zone-touch switch is an extra core demand
   e.coreCount = (e.sweep.found ? 1 : 0) + (e.displaced ? 1 : 0) + (e.structure ? 1 : 0);
   string why = "";
   e.corePass = QATS_CoreGate((int)InpStrategyProfile, e.sweep.found, e.displaced, e.structure,
                              (e.confirmM15 || e.triggerM5), why);
   if(e.corePass && InpRequireZoneTouch && !e.zoneTouched)
   {
      e.corePass = false;
      why = "zone touch required but absent";
   }
   e.coreWhy = why;

   // For XAUUSD the directional controls are diagnostic only, even if enabled in a saved preset.
   e.veto = QATS_DirectionVeto(IsXAUUSD(), dir, d1Bias, h4Bias, InpUseEMAAlignmentVeto, InpAllowCounterBias);
   e.eligible = (e.corePass && e.veto == 0 && QATS_ScoreEligible(dir, e.score, InpMinScore));

   // Setup identity = the structural EVENT the trade is built on: the bar of the
   // BOS / CHoCH when there is one, otherwise the bar that rejected the sweep.
   // Displacement confirms a setup but does not define it, so a run of impulsive
   // candles after one break of structure is still one setup, traded once.
   // The displacement anchor only applies when there is no structure and no sweep;
   // it is read from the timeframe that confirmed the displacement, never from
   // the wrong clock.
   datetime anchorTime = 0;
   if(e.structure)        anchorTime = iTime(_Symbol, PERIOD_H1, e.structBar);
   else if(e.sweep.found) anchorTime = iTime(_Symbol, PERIOD_H1, e.sweep.bar);
   else if(e.displaced)   anchorTime = iTime(_Symbol, e.dispTF, e.dispBar);
   e.setupTime = anchorTime;
}

// One side as text: the core verdict, then every weight with the points it earned.
// The points listed always add up to the side's score - nothing is scored off the page.
string SideTrace(const SSide &e)
{
   string core = "PASS";
   if(!e.corePass) core = "FAIL(" + e.coreWhy + ")";
   string structTag = "";
   if(e.structure) structTag = (e.structChoch ? "(CHOCH)" : "(BOS)");
   string sweepTag = "";
   if(e.sweep.found) sweepTag = "(" + (e.dir > 0 ? "SSL:" : "BSL:") + e.sweep.pool + ")";
   int zonePts = 0;
   if(e.zoneTouched)             zonePts = QATS_W_ZONE_TOUCH;
   else if(e.hasOB || e.hasFVG)  zonePts = QATS_W_ZONE_PRESENT;
   string tail = "";
   if(e.veto != 0)       tail += " veto=" + VetoName(e.veto);
   if(e.sweep.breakout)  tail += " liquidityAccepted=yes";
   return StringFormat("%s core=%s %d/3 [D1:%d H4:%d STRUCT:%d%s SWEEP:%d%s DISP:%d ZONE:%d PD:%d VWAP:%d VOL:%d M15:%d M5:%d]%s",
                       SideName(e.dir), core, e.coreCount,
                       (e.biasD1 ? QATS_W_BIAS_D1 : 0), (e.biasH4 ? QATS_W_BIAS_H4 : 0),
                       (e.structure ? QATS_W_STRUCTURE : 0), structTag,
                       (e.sweep.found ? QATS_W_SWEEP : 0), sweepTag,
                       (e.displaced ? QATS_W_DISPLACEMENT : 0), zonePts,
                       (e.location ? QATS_W_LOCATION : 0), (e.vwapSide ? QATS_W_VWAP : 0),
                       (e.volume ? QATS_W_VOLUME : 0), (e.confirmM15 ? QATS_W_M15 : 0),
                       (e.triggerM5 ? QATS_W_M5 : 0), tail);
}

// The core chain of a detected setup, with the bars and prices behind each event.
string ChainText(const SSide &e)
{
   string s = "";
   if(e.sweep.found)
      s += StringFormat("sweep=%s:%s@%s(detected %s shift %d @ %s; level formed shift %d; extreme %s)",
                        (e.dir > 0 ? "SSL" : "BSL"), e.sweep.pool,
                        PriceText(e.sweep.level),
                        TFName(e.sweep.tf), e.sweep.bar,
                        TimeToString(e.sweep.eventTime, TIME_DATE | TIME_MINUTES),
                        e.sweep.poolShift, PriceText(e.sweep.extreme));
   else
      s += "sweep=none";
   if(e.displaced)
   {
      if(e.dispTF == PERIOD_M15) s += " displacement=bar " + BarText(PERIOD_M15, e.dispBar) + " (M15)";
      else                       s += " displacement=bar " + H1BarText(e.dispBar);
   }
   else            s += " displacement=none";
   if(e.structure)
      s += StringFormat(" structure=%s@%s(bar %s)", (e.structChoch ? "CHOCH" : "BOS"),
                        PriceText(e.structLevel), H1BarText(e.structBar));
   else
      s += " structure=none";
   string zone = "none";
   if(e.hasOB && e.hasFVG) zone = "OB+FVG";
   else if(e.hasOB)        zone = "OB";
   else if(e.hasFVG)       zone = "FVG";
   s += " zone=" + zone + (e.zoneTouched ? "(touched)" : "");
   return s;
}

// One scored record per analysis: both scores, the candidate, the outcome and its
// reason code, the shared context, then the evidence of each side.
void LogSignal(const SAnalysis &signal, const string outcome, const string reason)
{
   int cand = (signal.dir != 0 ? signal.dir : signal.candidate);
   bool eligible = false;
   if(cand > 0) eligible = signal.buy.eligible;
   if(cand < 0) eligible = signal.sell.eligible;
   datetime setup = 0;
   if(cand > 0) setup = signal.buy.setupTime;
   if(cand < 0) setup = signal.sell.setupTime;
   // Phase 9: the single-record ANALYSIS/FINAL (own per-setup per-outcome dedup)
   JournalSetupRecord(signal, outcome, reason);
   string key = SideName(cand) + "|" + outcome + "|" + reason;
   if(!InpVerbose && key == g_lastScoredKey) return;
   g_lastScoredKey = key;
   PrintFormat("[QATS][SIGNAL][SCORED] symbol=%s bar=%s BUY=%d/100 SELL=%d/100 minimum=%d profile=%s candidate=%s eligible=%s outcome=%s reason=%s setup=%s | D1=%+d H4=%+d H1trend=%+d P/D=%.2f VWAP=%.5f REGIME=%s volRatio=%.2f rangeRatio=%.2f | %s | %s",
               _Symbol, TimeToString(signal.signalBar, TIME_DATE | TIME_MINUTES),
               signal.buy.score, signal.sell.score, InpMinScore,
               QATS_StrategyProfileName((int)InpStrategyProfile),
               SideName(cand), (eligible ? "yes" : "no"), outcome, reason, SetupId(cand, setup),
               signal.d1Bias, signal.h4Bias, signal.h1Struct, signal.dealPos, signal.vwap,
               signal.regime, signal.regimeVolRatio, signal.regimeRangeRatio,
               SideTrace(signal.buy), SideTrace(signal.sell));
}

// [QATS][BUY][DETECTED] / [QATS][SELL][DETECTED]: printed once per setup, the first
// time a side's core confirmation passes, whether or not the score then qualifies.
void AnnounceSide(const SAnalysis &a, const SSide &e)
{
   if(!e.corePass || e.setupTime <= 0) return;
   int i = SideIndex(e.dir);
   if(g_announcedSetup[i] == e.setupTime) return;
   g_announcedSetup[i] = e.setupTime;
   g_statDetected[i]++;
   PrintFormat("[QATS][%s][DETECTED] symbol=%s bar=%s setup=%s score=%d/100 minimum=%d eligible=%s profile=%s core=PASS %d/3 | %s | D1=%+d H4=%+d H1trend=%+d M15=%s M5=%s",
               SideName(e.dir), _Symbol, TimeToString(a.signalBar, TIME_DATE | TIME_MINUTES),
               SetupId(e.dir, e.setupTime), e.score, InpMinScore, (e.eligible ? "yes" : "no"),
               QATS_StrategyProfileName((int)InpStrategyProfile), e.coreCount, ChainText(e),
               a.d1Bias, a.h4Bias, a.h1Struct, (e.confirmM15 ? "yes" : "no"), (e.triggerM5 ? "yes" : "no"));
}

// v1.24 Phase 9 diagnostics: the outcome -> terminal decision vocabulary.
string QATS_DecisionName(const string outcome)
{
   if(outcome == "EXECUTED")      return "ENTER_MARKET";
   if(outcome == "LIMIT_PLACED")  return "ENTER_LIMIT";
   if(outcome == "DRY_RUN")       return "NO_ORDER";
   return outcome;
}

// which layer refused the setup, for the high-score explanation record
string QATS_RejectAt(const string outcome, const string reason)
{
   if(outcome == "BLOCKED")       return (reason == "PD_MARKET") ? "PD_GATE" : "RISK_GUARD";
   if(outcome == "REJECTED")      return reason;    // PLAN / SIZE / SPREAD_VS_STOP / RESERVE / BROKER / ...
   if(outcome == "NOT_PLACED")    return (reason == "LIMIT") ? "LIMIT_GATE" : reason;
   if(outcome == "BELOW_MINIMUM") return "SCORE_GATE";
   if(outcome == "VETOED")        return "VETO";
   if(outcome == "CONFLICT")      return "CONFLICT";
   if(outcome == "DRY_RUN")       return "DRY_RUN";
   return outcome;
}

string QATS_CoreText(const SSide &e)
{
   return StringFormat("%s %d/3", (e.corePass ? "PASS" : "FAIL"), e.coreCount);
}

string QATS_StructureText(const SSide &e)
{
   if(!e.structure) return "none";
   return StringFormat("%s@%s(shift %d)", (e.structChoch ? "CHOCH" : "BOS"),
                       PriceText(e.structLevel), e.structBar);
}

string QATS_SweepText(const SSide &e)
{
   if(!e.sweep.found) return "sweep=none";
   return StringFormat("sweep=%s:%s@%s(shift %d)", (e.dir > 0 ? "SSL" : "BSL"),
                       e.sweep.pool, PriceText(e.sweep.level), e.sweep.bar);
}

string QATS_DisplacementText(const SSide &e)
{
   if(!e.displaced) return "TF=none shift=-1 STATUS=NONE";
   return StringFormat("TF=%s shift=%d STATUS=OK", TFName(e.dispTF), e.dispBar);
}

// [QATS][ANALYSIS] single record + [QATS][FINAL], once per setup per outcome.
// Emitted for every side whose core chain passed; a refused setup that still
// scored >= InpMinScore is additionally explained by a [QATS][GUARD] line.
// Field order follows the mandated contract (master audit Phase 9):
//   bar side BUY_SCORE SELL_SCORE CORE_STATUS STRUCTURE_STATUS LIQUIDITY_STATUS
//   DISPLACEMENT_STATUS=TF=.. STATUS=.. PD_STATUS EXECUTION_STATUS FINAL_DECISION REASON
void JournalSetupRecord(const SAnalysis &signal, const string outcome, const string reason)
{
   for(int dir = -1; dir <= 1; dir += 2)
   {
      SSide e = (dir > 0) ? signal.buy : signal.sell;   // MQL5 has no reference locals
      if(!e.corePass || e.setupTime <= 0) continue;      // no setup, no single record
      int i = SideIndex(dir);
      string key = SetupId(dir, e.setupTime) + "|" + outcome + "|" + reason;
      if(key == g_lastAnalysisKey[i]) continue;          // dedup: once per setup per outcome
      g_lastAnalysisKey[i] = key;
      SRiskStatus risk;
      BuildRiskStatus(risk);
      string cooldown = (risk.cooldownActive && risk.cooldownUntil > 0)
                        ? ("until " + TimeToString(risk.cooldownUntil, TIME_DATE | TIME_MINUTES))
                        : (risk.cooldownActive ? "active" : "no");
      PrintFormat("[QATS][ANALYSIS] bar=%s side=%s BUY_SCORE=%d SELL_SCORE=%d SCORE=%d CORE_STATUS=%s STRUCTURE_STATUS=%s LIQUIDITY_STATUS=%s DISPLACEMENT_STATUS=%s PD_STATUS=%s EXECUTION_STATUS=%s FINAL_DECISION=%s REASON=%s | RISK equity=%.2f dayPnL=%+.2f(%+.1f%%) DD=%.2f%% streak=%d/%d cap=%d/%d dayLocked=%s ddHalted=%s cooldown=%s",
                  TimeToString(signal.signalBar, TIME_DATE | TIME_MINUTES), SideName(dir),
                  signal.buy.score, signal.sell.score, e.score,
                  QATS_CoreText(e), QATS_StructureText(e), QATS_SweepText(e),
                  QATS_DisplacementText(e), signal.pdStatus, outcome,
                  QATS_DecisionName(outcome), reason,
                  risk.equity, risk.dayPnl, risk.dayPnlPct, risk.ddPct,
                  risk.consecLosses, risk.streakMax, risk.tradesToday, risk.tradesMax,
                  (risk.dayLocked ? "yes" : "no"), (risk.ddHalted ? "yes" : "no"), cooldown);
      PrintFormat("[QATS][FINAL] DECISION=%s REASON=%s side=%s SCORE=%d setup=%s",
                  QATS_DecisionName(outcome), reason, SideName(dir), e.score, SetupId(dir, e.setupTime));
      if(e.score >= InpMinScore && outcome != "EXECUTED" && outcome != "LIMIT_PLACED")
      {
         string gkey = key + "|GUARD";
         if(gkey != g_lastGuardKey[i])
         {
            g_lastGuardKey[i] = gkey;
            PrintFormat("[QATS][GUARD] SCORE=%d REJECTED AT=%s REASON=%s side=%s setup=%s",
                        e.score, QATS_RejectAt(outcome, reason), reason, SideName(dir), SetupId(dir, e.setupTime));
         }
      }
   }
}

// The lock protects first creation of persistent CAS keys across chart instances.
bool InitSignalKeys()
{
   string lock = GVKey("sig_init_lock");
   if(!GlobalVariableTemp(lock) || !GlobalVariableSetOnCondition(lock, 1.0, 0.0)) return false;
   bool ok = true;
   for(int dir = -1; dir <= 1; dir += 2)
   {
      string key = GVKey(dir > 0 ? "sig_buy" : "sig_sell");
      if(!GlobalVariableCheck(key) && GlobalVariableSet(key, 0.0) == 0) ok = false;
   }
   GlobalVariablesFlush();
   // verify the keys persisted, same contract as ReserveSignal
   for(int dir = -1; dir <= 1; dir += 2)
      if(!GlobalVariableCheck(GVKey(dir > 0 ? "sig_buy" : "sig_sell"))) ok = false;
   if(!GlobalVariableSetOnCondition(lock, 0.0, 1.0)) ok = false;
   return ok;
}

// Reserve BEFORE submission; ambiguous or rejected sends are not retried.
// Identity is account + magic + symbol + direction + current M5 bar.
// CR-3: the keys are account + magic + symbol namespaced via GVKey
// (XAUUSD keeps the exact legacy key names). Reservation is created for
// EVERY symbol, not only XAUUSD.
bool ReserveSignal(const SAnalysis &signal, string &reason)
{
   string key = GVKey(signal.dir > 0 ? "sig_buy" : "sig_sell");
   if(signal.signalBar <= 0 || !GlobalVariableCheck(key))
   { reason = "signal identity or persistent reservation unavailable"; return false; }
   double previous = GlobalVariableGet(key);
   if(previous >= (double)signal.signalBar)
   { reason = "duplicate or older signal bar already reserved"; return false; }
   if(!GlobalVariableSetOnCondition(key, (double)signal.signalBar, previous))
   { reason = "duplicate signal or reservation contention"; return false; }
   GlobalVariablesFlush();
   // Verify the reservation persisted (Phase 8): a reservation that did not make
   // it to disk must not authorize an order - fail closed instead of trusting RAM.
   double persisted = GlobalVariableCheck(key) ? GlobalVariableGet(key) : -1.0;
   if(persisted < (double)signal.signalBar)
   { reason = "reservation did not persist (GV flush verification failed)"; return false; }
   return true;
}

// One entry per setup: the identity of the last setup that became a position is
// persisted per direction, so stale evidence can never be traded twice.
bool SetupAlreadyTraded(const int dir, const datetime setupTime)
{
   if(setupTime <= 0) return false;
   double last = GVGet(GVKey(dir > 0 ? "setup_buy" : "setup_sell"), 0.0);
   return (last >= (double)setupTime);
}

void MarkSetupTraded(const int dir, const datetime setupTime)
{
   if(setupTime <= 0) return;
   GVSet(GVKey(dir > 0 ? "setup_buy" : "setup_sell"), (double)setupTime);
}

// Fill swings/pools from the per-bar cache, rebuilding when the H1 context moved.
// The key is the closed-bar context itself (bar time + bar count + shift-1 H/L/C), so a
// re-read of the same series hits and anything else rebuilds. Closed bars never change
// inside a decision; the offline harness additionally clears the cache on tape swaps.
void LiquidityContext(const string symbol, const double atrH1,
                      SSwing &highs[], SSwing &lows[], SLiquidityPool &pools[])
{
   datetime h1Bar = iTime(symbol, PERIOD_H1, 1);
   int h1Bars = iBars(symbol, PERIOD_H1);
   double h1Close = iClose(symbol, PERIOD_H1, 1);
   double h1High = iHigh(symbol, PERIOD_H1, 1);
   double h1Low  = iLow(symbol, PERIOD_H1, 1);
   if(g_mH1Bar == 0
      || h1Bar != g_mH1Bar || h1Bars != g_mH1Bars
      || h1Close != g_mH1Close || h1High != g_mH1High || h1Low != g_mH1Low)
   {
      double tol = MathMax(atrH1 * InpLiquidityToleranceATR, _Point * 2);
      FindSwings(symbol, PERIOD_H1, InpSwingLookback, InpSwingK, g_mHighs, true);
      FindSwings(symbol, PERIOD_H1, InpSwingLookback, InpSwingK, g_mLows, false);
      BuildLiquidityMap(symbol, PERIOD_H1, g_mHighs, g_mLows, tol, MathMax(1, InpSetupWindowBars), g_mPools);
      g_mH1Bar = h1Bar; g_mH1Bars = h1Bars;
      g_mH1Close = h1Close; g_mH1High = h1High; g_mH1Low = h1Low;
   }
   ArrayResize(highs, ArraySize(g_mHighs));
   for(int i = 0; i < ArraySize(g_mHighs); i++) highs[i] = g_mHighs[i];
   ArrayResize(lows, ArraySize(g_mLows));
   for(int i = 0; i < ArraySize(g_mLows); i++) lows[i] = g_mLows[i];
   ArrayResize(pools, ArraySize(g_mPools));
   for(int i = 0; i < ArraySize(g_mPools); i++) pools[i] = g_mPools[i];
}

SAnalysis AnalyzeMarket()
{
   SAnalysis a;
   ResetAnalysis(a);
   a.signalBar = iTime(_Symbol, PERIOD_M5, 0);

   SReading r;
   if(!LoadReading(r))
   {
      a.reason = "MARKET_DATA_NOT_READY";
      return a;
   }
   a.dataReady = true;
   a.vwap = r.vwap;

   // v1.24 regime: report-only. Classification never gates an entry; it is
   // journalled so evidence can accumulate before any rule is considered.
   SRegime regime;
   if(InpRegimeEnable) ComputeRegime(_Symbol, r.atrH1, r.h1Close, r.h1Fast, r.h1Slow, r.h1Slow200, regime);
   else { regime.kind = QATS_REGIME_UNCLEAR; regime.volRatio = 0.0; regime.rangeRatio = 0.0; }
   a.regime = RegimeName(regime.kind);
   a.regimeVolRatio = regime.volRatio;
   a.regimeRangeRatio = regime.rangeRatio;

   // v1.24 adaptive premium / discount: three H1 ranges, one deterministic
   // selection, one journal line per evaluation (never a silent 0.5)
   SPdAdaptive pd;
   ComputePdAdaptive(_Symbol, r.atrH1, pd);
   a.dealPos = pd.position;
   a.pdEq = pd.eq;
   a.pdLongEq = pd.a.valid ? pd.a.eq : 0.0;
   a.pdShortEq = pd.b.valid ? pd.b.eq : 0.0;
   a.pdSwingEq = pd.c.valid ? pd.c.eq : 0.0;
   a.pdLongValid = pd.a.valid; a.pdShortValid = pd.b.valid; a.pdSwingValid = pd.c.valid;
   a.pdSelected = pd.selected;
   a.pdStatus = pd.status;
   PrintFormat("[QATS][PD] %s", PdLine(pd));

   // D1 bias and H4 context
   a.d1Bias = BiasFrom(r.d1Close, r.d1Fast, r.d1Slow);
   a.h4Bias = BiasFrom(r.h4Close, r.h4Fast, r.h4Slow);

   // H1 structure: confirmed swings, then BOS / CHoCH from closed closes
   SSwing highs[], lows[];
   SLiquidityPool pools[];
   LiquidityContext(_Symbol, r.atrH1, highs, lows, pools);
   SStructure st;
   BuildStructure(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, st);
   a.h1Struct = st.trend;

   // liquidity map: every pool on both sides with its state (cached per bar)
   double tol = MathMax(r.atrH1 * InpLiquidityToleranceATR, _Point * 2);
   JournalLiquidityTransitions(pools, ArraySize(pools), tol);

   // BOTH directions, every bar, through the same function
   double pxNow = iClose(_Symbol, PERIOD_M5, 1);
   EvaluateSide(+1, r, st, pools, a.d1Bias, a.h4Bias, a.dealPos, pxNow, a.buy);
   EvaluateSide(-1, r, st, pools, a.d1Bias, a.h4Bias, a.dealPos, pxNow, a.sell);

   // direction: only an eligible side can trade; two eligible sides go to the policy
   string rule = "";
   a.dir = QATS_ResolveDirection(a.buy.eligible, a.sell.eligible, a.buy.score, a.sell.score,
                                 InpConflictMargin, st.trend, a.d1Bias, a.h4Bias, rule);
   a.resolution = rule;
   a.conflict = (a.buy.eligible && a.sell.eligible);
   a.candidate = (a.dir != 0 ? a.dir
                             : QATS_Candidate(a.buy.corePass, a.sell.corePass, a.buy.score, a.sell.score));
   if(a.candidate > 0)      { a.score = a.buy.score;  a.setupTime = a.buy.setupTime; }
   else if(a.candidate < 0) { a.score = a.sell.score; a.setupTime = a.sell.setupTime; }

   a.reason = StringFormat("D1=%+d H4=%+d H1trend=%+d P/D=%.2f(%s) VWAP=%.5f BUY=%d SELL=%d",
                           a.d1Bias, a.h4Bias, a.h1Struct, a.dealPos, PdLetter(a.pdSelected), r.vwap, a.buy.score, a.sell.score);
   return a;
}

//+------------------------------------------------------------------+
//| SECTION 16 - TRADE PLAN (entry / SL / TP / RR)                   |
//| Charts are drawn from the BID. A BUY is opened on the ask and    |
//| closed on the bid; a SELL is opened on the bid and closed on the |
//| ASK. Every chart level a SELL order sits on is therefore shifted |
//| by one spread, so that a SELL stop and a SELL target trigger on  |
//| the same chart touch as their BUY mirror images would.           |
//+------------------------------------------------------------------+
bool BuildTradePlan(const SAnalysis &in, SAnalysis &out)
{
   out = in;
   g_executionStage = "PLAN";
   g_executionReason = "invalid direction";
   if(out.dir != 1 && out.dir != -1) return false;

   double atr = 0.0, atrH1 = 0.0;
   g_executionReason = "M5 ATR unavailable";
   if(!BufValue(g_hATRM5, 1, atr)) return false;
   g_executionReason = "H1 ATR unavailable";
   if(!BufValue(g_hATRH1, 1, atrH1)) return false;
   g_executionReason = "ATR is nonpositive";
   if(atr <= 0.0 || atrH1 <= 0.0) return false;

   double point = g_spec.point;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   g_executionReason = "invalid bid/ask quote";
   if(bid <= 0.0 || ask < bid) return false;
   double spread = ask - bid;
   double entry = (out.dir > 0) ? ask : bid;

   //--- stop-loss: the WIDER of (ATR-based) and (M5 structure-based), plus a buffer
   double atrStop = 1.5 * atr;
   double structStop = 0.0;
   if(out.dir > 0)
   {
      // beyond the lowest low of the last 3 closed M5 bars (a bid level, hit by the bid)
      double ll;
      if(LowestLow(_Symbol, PERIOD_M5, 1, 3, ll)) structStop = entry - ll;
   }
   else
   {
      // beyond the highest high of the last 3 closed M5 bars; the stop is hit by the
      // ASK, so it sits one spread above the chart level
      double hh;
      if(HighestHigh(_Symbol, PERIOD_M5, 1, 3, hh)) structStop = (hh + spread) - entry;
   }
   double stopDist = MathMax(atrStop, structStop > 0.0 ? structStop : atrStop);
   // buffer: one broker stop-level beyond, so the broker never rejects it
   double stopsBuf = (double)MathMax(g_spec.stopsLevel, 1) * point;
   stopDist += stopsBuf;

   //--- validate against integer stop inputs
   double minStopPts = MathMax(MathMax((double)InpMinStopPoints, (double)g_spec.stopsLevel), 1.0) * point;
   double maxStopPts = (double)InpMaxStopPoints * point;
   if(stopDist < minStopPts) stopDist = minStopPts;
   if(stopDist > maxStopPts)
   {
      g_executionReason = StringFormat("stop too wide %.5f (max %.5f)", stopDist, maxStopPts);
      return false;
   }
   // the stop is snapped AWAY from the entry, never closer than planned
   double sl = (out.dir > 0) ? QATS_SnapToTick(entry - stopDist, g_spec.tickSize, g_spec.digits, false)
                             : QATS_SnapToTick(entry + stopDist, g_spec.tickSize, g_spec.digits, true);
   stopDist = MathAbs(entry - sl);

   //--- take-profit: NEAREST intact opposing liquidity that pays >= InpMinRR, else RR multiple
   SSwing highs[], lows[];
   SLiquidityPool pools[];
   LiquidityContext(_Symbol, atrH1, highs, lows, pools);
   double tp = 0.0;
   string tpSource = "RR";
   double target = 0.0;
   string targetKind = "";
   double targetLevel = 0.0;
   bool snapUp = false;
   if(NearestLiquidityTarget(pools, out.dir, entry, stopDist, InpMinRR, spread, target, targetKind, targetLevel))
   {
      // a liquidity target is snapped TOWARD the entry: never beyond the level it aims at
      tp = target;
      tpSource = "LIQUIDITY:" + targetKind + "@" + PriceText(targetLevel);
      out.tpLevel = targetLevel;
      snapUp = (out.dir < 0);
   }
   else
   {
      // an RR target is snapped AWAY from the entry: never less than the requested multiple
      tp = (out.dir > 0) ? entry + stopDist * InpRewardRisk : entry - stopDist * InpRewardRisk;
      out.tpLevel = 0.0;
      snapUp = (out.dir > 0);
   }
   tp = QATS_SnapToTick(tp, g_spec.tickSize, g_spec.digits, snapUp);

   //--- broker stops-level validation for both SL and TP
   long stopsLvl = (long)g_spec.stopsLevel;
   double minDist = (double)MathMax(stopsLvl, 1) * point;
   if(MathAbs(entry - sl) < minDist || MathAbs(tp - entry) < minDist)
   {
      g_executionReason = StringFormat("broker stops level violated (need >= %I64d pts)", stopsLvl);
      return false;
   }
   //--- freeze-level awareness for later modifications is handled in management
   double rr = MathAbs(tp - entry) / stopDist;
   if(rr + 0.000000001 < InpMinRR)
   {
      g_executionReason = StringFormat("reward:risk %.2f below minimum %.2f", rr, InpMinRR);
      return false;
   }

   out.entry    = entry;
   out.sl       = sl;
   out.tp       = tp;
   out.stopDist = stopDist;
   out.tpSource = tpSource;
   g_executionReason = "";
   return true;
}

//+------------------------------------------------------------------+
//| SECTION 17 - DYNAMIC POSITION SIZING (from CURRENT equity)       |
//+------------------------------------------------------------------+
bool CalcPositionVolume(const double slDist, const bool isBuy, double &volumeOut, double &riskMoneyOut)
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0)
   {
      g_executionReason = StringFormat("equity %.2f unavailable", equity);
      return false;
   }
   double riskPct = EffectiveRiskPercent();
   double riskMoney = equity * riskPct / 100.0;
   if(riskMoney <= 0.0)
   {
      g_executionReason = StringFormat("risk money %.2f <= 0", riskMoney);
      return false;
   }
   if(slDist <= 0.0)
   {
      g_executionReason = StringFormat("stop distance %.10f invalid", slDist);
      return false;
   }
   // v6.6.21: monetary loss at the stop for 1.0 lot, asked of the TERMINAL.
   //
   // The old identity (slDist / tickSize) * tickValue assumes the tick value is
   // quoted per PRICE tick and that the contract multiplier is 1.0. Both are
   // usually true on FX and routinely false on gold, indices and anything with a
   // non-trivial contract size - and this number decides the lot, so a wrong
   // identity is a wrong position. OrderCalcProfit() answers the question with
   // the broker's own contract specification instead.
   double refPrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                           : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double slPrice  = isBuy ? refPrice - slDist : refPrice + slDist;
   if(refPrice <= 0.0 || slPrice <= 0.0)
   {
      g_executionReason = StringFormat("no quote (ref %.5f)", refPrice);
      return false;
   }
   double lossPerLot = 0.0;
   if(!OrderCalcProfit(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol, 1.0,
                       refPrice, slPrice, lossPerLot))
   {
      g_executionReason = StringFormat("OrderCalcProfit failed at stop %.5f from %.5f, error=%d",
                  slPrice, refPrice, GetLastError());
      return false;
   }
   // OrderCalcProfit returns a NEGATIVE number for a losing exit.
   lossPerLot = -lossPerLot;
   if(lossPerLot <= 0.0)
   {
      g_executionReason = StringFormat("lossPerLot %.5f invalid (ref %.5f stop %.5f)",
                  lossPerLot, refPrice, slPrice);
      return false;
   }
   double vol = riskMoney / lossPerLot;

   // normalize to broker volume step
   vol = MathFloor(vol / g_spec.volStep) * g_spec.volStep;
   // never exceed broker bounds
   if(vol > g_spec.volMax)   vol = MathFloor(g_spec.volMax / g_spec.volStep) * g_spec.volStep;
   if(g_spec.volLimit > 0 && vol > g_spec.volLimit)
      vol = MathFloor(g_spec.volLimit / g_spec.volStep) * g_spec.volStep;

   if(vol < g_spec.volMin)
   {
      g_executionReason = StringFormat("risk-sized volume %.8f below broker minimum %.8f", vol, g_spec.volMin);
      return false;
   }
   // margin check with shrink loop: reduce to what free margin can carry
   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double margin = 0.0;
   if(!OrderCalcMargin(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol, vol, price, margin))
   {
      g_executionReason = StringFormat("OrderCalcMargin failed, error=%d", GetLastError());
      return false;
   }
   double maxMargin = freeMargin * InpMaxMarginUse;
   while(vol >= g_spec.volMin && margin > maxMargin)
   {
      vol -= g_spec.volStep;
      if(vol < g_spec.volMin) break;
      vol = MathFloor(vol / g_spec.volStep) * g_spec.volStep;
      if(!OrderCalcMargin(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol, vol, price, margin))
      {
         g_executionReason = StringFormat("OrderCalcMargin failed during shrink, error=%d", GetLastError());
         return false;
      }
   }
   if(vol < g_spec.volMin)
   {
      g_executionReason = StringFormat("volume %.2f below broker minimum %.2f after margin fitting (free margin %.2f)",
                  vol, g_spec.volMin, freeMargin);
      return false;
   }
   volumeOut    = vol;
   riskMoneyOut = vol * lossPerLot;
   return true;
}

//+------------------------------------------------------------------+
//| NEWS / CALENDAR GUARD (v1.24, Phase 7, CR-6)  -  OPT-IN            |
//| Entries are blocked while a high-impact calendar event (importance |
//| >= InpNewsMinImportance) for a watched currency sits within the    |
//| [now - InpNewsBlockAfterMin, now + InpNewsBlockBeforeMin] window.  |
//| An UNREACHABLE calendar blocks NOTHING: no events are ever          |
//| fabricated; the miss is journalled once per attach.                 |
//| NOTE: whether the calendar is populated on THIS terminal can only   |
//| be verified in MetaEditor on the operator's platform (Phase 10).    |
//+------------------------------------------------------------------+
string NewsTrimToken(const string text)
{
   // trim spaces/tabs/CR/LF from a comma-separated token (shim has no StringTrim*)
   int len = StringLen(text);
   int a = 0, b = len - 1;
   while(a <= b)
   {
      string ch = StringSubstr(text, a, 1);
      if(ch != " " && ch != "\t" && ch != "\r" && ch != "\n") break;
      a++;
   }
   while(b >= a)
   {
      string ch = StringSubstr(text, b, 1);
      if(ch != " " && ch != "\t" && ch != "\r" && ch != "\n") break;
      b--;
   }
   return (a > b) ? "" : StringSubstr(text, a, b - a + 1);
}

// One unfiltered CalendarValueHistory read of the window, joined to the event
// library by event_id - MqlCalendarValue carries no importance/currency of its
// own (importance lives on MqlCalendarEvent; the terminal's own calendar
// consumer in this codebase uses the same History -> CalendarEventById -> join,
// verified when nadir2 compiled). Each watched currency is matched against
// CalendarEventByCurrency; a currency lookup that fails is treated as
// unverifiable for THAT currency only (fail-open, never fabricated). Returns
// -1 when the calendar itself is unreachable or when no watched currency can
// be verified; partial reachability enforces the reachable currencies.
int NewsHighImpactInWindow(const datetime from, const datetime to, string &why)
{
   int events = 0;
   int calls = 0, ok = 0;
   MqlCalendarValue vals[];
   int total = CalendarValueHistory(vals, from, to);
   if(total < 0) return -1;                      // terminal calendar unreachable: never block
   string list = InpNewsCurrencies;
   while(StringLen(list) > 0)
   {
      int comma = StringFind(list, ",");
      string cur = NewsTrimToken((comma >= 0) ? StringSubstr(list, 0, comma) : list);
      list = (comma >= 0) ? StringSubstr(list, comma + 1) : "";
      if(StringLen(cur) == 0) continue;
      calls++;
      MqlCalendarEvent evs[];
      int evN = CalendarEventByCurrency(cur, evs);
      if(evN < 0) continue;                      // this currency cannot be verified -> fail-open for it
      ok++;
      for(int j = 0; j < evN; j++)
      {
         if((long)evs[j].importance < InpNewsMinImportance) continue;
         ulong evId = (ulong)evs[j].id;
         for(int i = 0; i < total; i++)
            if((ulong)vals[i].event_id == evId)
            {
               events++;   // one count per (event, window); a currency never shares an event with another
               break;
            }
      }
   }
   why = "";
   if(calls == 0) return 0;                      // nothing watched -> nothing to block
   if(ok == 0) return -1;                        // no watched currency could be verified
   return events;
}

// true = entries may proceed; false = blocked. Never blocks on an unverifiable calendar.
bool NewsEntriesAllowed(const datetime now, string &why)
{
   why = "";
   datetime from = now - (datetime)InpNewsBlockAfterMin * 60;
   datetime to   = now + (datetime)InpNewsBlockBeforeMin * 60;
   int events = NewsHighImpactInWindow(from, to, why);
   if(events < 0)
   {
      if(!g_newsUnavailableLogged)
      {
         g_newsUnavailableLogged = true;
         Print("[QATS][NEWS] CALENDAR_UNAVAILABLE - no events assumed, entries NOT blocked by unverifiable data");
      }
      return true;                                // fail open for TRADING, never invent events
   }
   if(!g_newsReadyLogged)
   {
      g_newsReadyLogged = true;
      PrintFormat("[QATS][NEWS] enabled: importance>=%I64d around %s, window -%dm/+%dm (server time); entries blocked while a matching event sits inside it",
                  InpNewsMinImportance, InpNewsCurrencies, InpNewsBlockAfterMin, InpNewsBlockBeforeMin);
   }
   if(events > 0)
   {
      why = StringFormat("high-impact calendar event inside the block window (%d event(s), importance>=%I64d, %s)",
                         events, InpNewsMinImportance, InpNewsCurrencies);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| SECTION 18 - GUARD CHAIN (MANDATORY RISK PROTECTION)             |
//| Every guard that can veto an entry is evaluated on every pass,   |
//| so the journal names ALL active blocks, not just the first one.  |
//| None of them depends on the trade direction.                     |
//+------------------------------------------------------------------+
void AddBlock(string &codes, string &detail, string &first, int &count, const string code, const string text)
{
   if(count > 0) { codes += ","; detail += "; "; }
   else          first = text;
   codes += code;
   detail += text;
   count++;
}

string CooldownText()
{
   if(!g_inCooldown) return "no";
   return StringFormat("YES(trigger=%d losses,start=%s,until=%s,remaining=%I64ds)", g_cooldownTrigger,
                       TimeToString(g_cooldownStart, TIME_DATE | TIME_SECONDS),
                       TimeToString(g_cooldownUntil, TIME_DATE | TIME_SECONDS),
                       QATS_CooldownRemaining(TimeTradeServer(), g_cooldownUntil));
}

// Account / market / risk guards. Returns how many are active.
int GuardBlocks(string &codes, string &detail, string &first)
{
   codes = ""; detail = ""; first = "";
   int count = 0;
   if(!InpEnableTrading) AddBlock(codes, detail, first, count, "MASTER_SWITCH_OFF", "MASTER SWITCH off (InpEnableTrading=false)");
   if(g_execBlocked)     AddBlock(codes, detail, first, count, "EXEC_BLOCKED", g_blockReason);
      // re-verify account/terminal/EA/symbol permissions at decision time
   string pr = "";
   if(!VerifyAccountProtection(pr)) AddBlock(codes, detail, first, count, "PROTECTION", "PROTECTION: " + pr);
   if(g_dayLocked)
      AddBlock(codes, detail, first, count, "DAILY_LOSS_LOCK",
               StringFormat("DAILY LOSS LIMIT reached - locked until tomorrow (day P/L %+.2f on baseline %.2f)", g_dayPnL, g_dayBase));
   if(g_ddHalted)
      AddBlock(codes, detail, first, count, "DRAWDOWN_HALT",
               StringFormat("ACCOUNT DRAWDOWN %.2f%% from equity high-water %.2f - halted until equity recovers or the operator resets the breakers",
                            g_accountDDPct, g_equityHWM));
   if(g_inCooldown)
      AddBlock(codes, detail, first, count, "LOSS_COOLDOWN", "CONSECUTIVE-LOSS cooldown active " + CooldownText());
   if(InpMaxTradesPerDay > 0 && g_tradesToday >= InpMaxTradesPerDay)
      AddBlock(codes, detail, first, count, "DAILY_TRADE_CAP",
               StringFormat("daily trade cap reached (%d/%d)", g_tradesToday, InpMaxTradesPerDay));
   // session filter
   if(InpSessionStartHour != InpSessionEndHour)
   {
      MqlDateTime dt;
      TimeToStruct(TimeTradeServer(), dt);
      int hour = dt.hour;
      bool inSession;
      if(InpSessionStartHour < InpSessionEndHour)
         inSession = (hour >= InpSessionStartHour && hour < InpSessionEndHour);
      else
         inSession = (hour >= InpSessionStartHour || hour < InpSessionEndHour);
      if(!inSession) AddBlock(codes, detail, first, count, "OUTSIDE_SESSION", "outside trading session");
   }
   // news / calendar blackout (opt-in)
   if(InpNewsFilterEnable)
   {
      string why = "";
      if(!NewsEntriesAllowed(TimeTradeServer(), why))
         AddBlock(codes, detail, first, count, "NEWS_BLACKOUT", why);
   }
   // stale data guard
   if(InpMaxDataAgeSeconds > 0)
   {
      long tickTime = (long)SymbolInfoInteger(_Symbol, SYMBOL_TIME);
      long age = (long)TimeTradeServer() - tickTime;
      if(age > InpMaxDataAgeSeconds)
         AddBlock(codes, detail, first, count, "STALE_TICK", StringFormat("stale tick (%I64ds old)", age));
   }
   // spread guard (absolute)
   double spreadPts = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point;
   if(spreadPts > (double)InpMaxSpreadPoints)
      AddBlock(codes, detail, first, count, "SPREAD", StringFormat("spread %.0f pts > max %d", spreadPts, InpMaxSpreadPoints));
   // position cap (this magic + symbol). A working LIMIT is capacity the same
   // way an open position is: with InpUseLimitEntry a resting order already
   // occupies the slot, and the engine can never stack two of them.
   if(CountMyPositions() + CountMyPending() >= InpMaxOpenPositions)
      AddBlock(codes, detail, first, count, "MAX_POSITIONS",
               StringFormat("max open positions reached (%d: %d filled + %d pending)",
                            InpMaxOpenPositions, CountMyPositions(), CountMyPending()));
   // duplicate order prevention: a pending retry is already in flight
   if(g_pendingRetryAt != 0)
      AddBlock(codes, detail, first, count, "RETRY_PENDING", "order retry pending");
   return count;
}

bool EntriesAllowed(string &blockReason)
{
   string codes = "", detail = "";
   blockReason = "";
   return (GuardBlocks(codes, detail, blockReason) == 0);
}

int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      count++;
   }
   return count;
}

// A position of this magic on this symbol in the direction OPPOSITE to dir.
bool OppositePositionOpen(const int dir)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      long type = PositionGetInteger(POSITION_TYPE);
      int posDir = (type == POSITION_TYPE_BUY) ? +1 : -1;
      if(posDir == -dir) return true;
   }
   return false;
}

// The guard chain plus the two signal-specific guards. Returns the number of blocks.
int CollectEntryBlocks(const SAnalysis &signal, string &codes, string &detail)
{
   string first = "";
   int count = GuardBlocks(codes, detail, first);
   // never hold both sides: an opposite position that is still open blocks the entry
   if(OppositePositionOpen(signal.dir))
      AddBlock(codes, detail, first, count, "OPPOSITE_POSITION",
               "an opposite position of this EA is still open (never hold both sides)");
   // one entry per setup: stale evidence is not traded twice
   if(SetupAlreadyTraded(signal.dir, signal.setupTime))
      AddBlock(codes, detail, first, count, "DUPLICATE_SETUP",
               "setup " + SetupId(signal.dir, signal.setupTime) + " was already traded; waiting for new core evidence");
   return count;
}

//+------------------------------------------------------------------+
//| SECTION 19 - EXECUTION ENGINE (CTrade, retcode handling, verify) |
//+------------------------------------------------------------------+
void ConfigureTrade()
{
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints((ulong)InpDeviationPoints);
   // choose a filling mode the symbol supports: FOK > IOC > RETURN
   long filling = (long)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      g_trade.SetTypeFilling(ORDER_FILLING_RETURN);
}

bool VerifyPositionOpened(const int dir, ulong &ticketOut)
{
   ticketOut = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if((int)PositionGetInteger(POSITION_TYPE) != (dir > 0 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL)) continue;
      datetime ctime = (datetime)PositionGetInteger(POSITION_TIME);
      if(TimeTradeServer() - ctime <= 120)
      {
         ticketOut = ticket;
         PrintFormat("[QATS][VERIFY] server-side SL=%.5f TP=%.5f | openPrice=%.5f volume=%.2f",
                     PositionGetDouble(POSITION_SL), PositionGetDouble(POSITION_TP),
                     PositionGetDouble(POSITION_PRICE_OPEN), PositionGetDouble(POSITION_VOLUME));
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| v6.6.21 unified signal audit + class helpers                     |
//|                                                                  |
//| QATS computes its own confluence score, so the class it reports   |
//| is derived from THAT score and its own RR - never from the        |
//| indicator's buffers (it has no handle). Emitting the same line    |
//| shape as nadir2 and QSMC_AutoTrader is what lets one parser read  |
//| all three sides of the pipeline.                                  |
//+------------------------------------------------------------------+
string QATS_ClassName(const int cls)
{
   if(cls == QSMC_CLASS_WEAK_VALID)     return "WEAK_VALID";
   if(cls == QSMC_CLASS_MODERATE_VALID) return "MODERATE_VALID";
   if(cls == QSMC_CLASS_STRONG_VALID)   return "STRONG_VALID";
   if(cls == QSMC_CLASS_REJECTED)       return "REJECTED";
   return "NONE";
}

string QATS_ProfileName(const ENUM_SIGNAL_EXECUTION_PROFILE p)
{
   if(p == SIGNAL_PROFILE_STRICT) return "STRICT";
   if(p == SIGNAL_PROFILE_BALANCED) return "BALANCED";
   return "PERMISSIVE";
}

// Same three floors the indicator uses, applied to QATS's own numbers.
int QATS_Classify(const double score, const double rr)
{
   if(score >= 75.0 && rr + 1e-9 >= 1.50) return QSMC_CLASS_STRONG_VALID;
   if(score >= 60.0 && rr + 1e-9 >= 1.50) return QSMC_CLASS_MODERATE_VALID;
   if(score >= 40.0 && rr + 1e-9 >= 1.20) return QSMC_CLASS_WEAK_VALID;
   return QSMC_CLASS_REJECTED;
}

// The profile ceiling. STRICT keeps only STRONG, exactly like the indicator.
bool QATS_ProfileAllows(const int cls)
{
   if(cls == QSMC_CLASS_STRONG_VALID) return true;
   if(cls == QSMC_CLASS_MODERATE_VALID) return (InpSignalExecutionProfile != SIGNAL_PROFILE_STRICT);
   if(cls == QSMC_CLASS_WEAK_VALID) return (InpSignalExecutionProfile == SIGNAL_PROFILE_PERMISSIVE);
   return false;
}

void QATS_Audit(const string stage, const int cls, const double score, const double rr,
                const string result, const string why)
{
   PrintFormat("[QATS][AUDIT] stage=%s class=%s score=%.0f rr=%.2f profile=%s result=%s why=%s",
               stage, QATS_ClassName(cls), score, rr,
               QATS_ProfileName(InpSignalExecutionProfile), result, why);
}

// reserved=true is used ONLY by ProcessPendingRetry: the reservation was already
// consumed by the initial send; re-reserving would brick the retry by design.
bool ExecuteSignal(const SAnalysis &inputPlan, const bool reserved=false)
{
   SAnalysis plan = inputPlan;
   g_executionReason = "";
   g_executionStage = "PRECHECK";
   // Class is diagnostic for XAUUSD; other symbols retain their profile gate.
   double plan_rr = (plan.stopDist > 0.0 ? MathAbs(plan.tp - plan.entry) / plan.stopDist : 0.0);
   int plan_cls = QATS_Classify((double)plan.score, plan_rr);
   if(!IsXAUUSD() && !QATS_ProfileAllows(plan_cls))
   {
      g_executionReason = "class not allowed by profile " + QATS_ProfileName(InpSignalExecutionProfile);
      QATS_Audit("EXEC", plan_cls, (double)plan.score, plan_rr, "REFUSED", g_executionReason);
      return false;
   }

   // Live re-validation at the moment of sending, for every symbol: the score,
   // the broker specification, the whole guard chain, and the stop geometry
   // against the CURRENT quote.
   if(!QATS_ScoreEligible(plan.dir, plan.score, InpMinScore))
   { g_executionReason = "invalid direction or score below minimum"; return false; }
   if(!LoadSymbolSpec(g_spec))
   { g_executionReason = "broker symbol specification unavailable or invalid"; return false; }
   string guard = "";
   if(!EntriesAllowed(guard)) { g_executionReason = guard; return false; }
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double minDist = MathMax((double)g_spec.stopsLevel, 1.0) * g_spec.point;
   if(!QATS_StopsValid(plan.dir, bid, ask, plan.sl, plan.tp, minDist))
   {
      if(bid <= 0.0 || ask < bid || !MathIsValidNumber(bid) || !MathIsValidNumber(ask))
         g_executionReason = "invalid bid/ask quote";
      else if(!MathIsValidNumber(plan.sl) || plan.sl <= 0.0 ||
              (plan.dir > 0 ? plan.sl >= bid || bid - plan.sl < minDist : plan.sl <= ask || plan.sl - ask < minDist))
         g_executionReason = "invalid SL direction or broker stop distance";
      else
         g_executionReason = "invalid TP direction or broker stop distance";
      return false;
   }
   if(MathAbs(plan.sl / g_spec.tickSize - MathRound(plan.sl / g_spec.tickSize)) > 1e-7 ||
      MathAbs(plan.tp / g_spec.tickSize - MathRound(plan.tp / g_spec.tickSize)) > 1e-7)
   { g_executionReason = "SL or TP not aligned to current broker tick size"; return false; }
   plan.entry = (plan.dir > 0 ? ask : bid);
   plan.stopDist = MathAbs(plan.entry - plan.sl);
   if(plan.stopDist < InpMinStopPoints * g_spec.point || plan.stopDist > InpMaxStopPoints * g_spec.point)
   { g_executionReason = "live stop distance outside configured risk limits"; return false; }
   if(MathAbs(plan.tp - plan.entry) / plan.stopDist + 0.000000001 < InpMinRR)
   { g_executionReason = "live reward:risk below minimum"; return false; }
   plan_rr = MathAbs(plan.tp - plan.entry) / plan.stopDist;
   // never hold both sides, never trade the same setup twice (re-checked at send time)
   if(OppositePositionOpen(plan.dir))
   { g_executionReason = "an opposite position of this EA is still open"; return false; }
   if(SetupAlreadyTraded(plan.dir, plan.setupTime))
   { g_executionReason = "setup " + SetupId(plan.dir, plan.setupTime) + " was already traded"; return false; }

   g_executionStage = "SIZE";
   double volume = 0.0, riskMoney = 0.0;
   if(!CalcPositionVolume(plan.stopDist, plan.dir > 0, volume, riskMoney))
   {
      QATS_Audit("SIZE", plan_cls, (double)plan.score, plan_rr, "REFUSED", g_executionReason);
      return false;
   }
   QATS_Audit("EXEC", plan_cls, (double)plan.score, plan_rr, "SIZED",
              "volume " + DoubleToString(volume, 2) + " risk " + DoubleToString(riskMoney, 2));

   g_executionStage = "SPREAD_VS_STOP";
   double spreadPts = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point;
   if(spreadPts > plan.stopDist / g_spec.point * InpMaxSpreadFracOfStop)
   {
      g_executionReason = StringFormat("spread %.2f pts exceeds %.2f%% of stop distance", spreadPts, InpMaxSpreadFracOfStop * 100.0);
      return false;
   }

   double sl = plan.sl, tp = plan.tp;
   string side = (plan.dir > 0) ? "BUY" : "SELL";
   string setupId = SetupId(plan.dir, plan.setupTime);
   g_statApproved[SideIndex(plan.dir)]++;
   PrintFormat("[QATS][EXECUTION][APPROVED] symbol=%s bar=%s direction=%s setup=%s score=%d class=%s entry=%s sl=%s tp=%s tpSource=%s rr=%.2f lots=%.2f risk=%.2f %s (%.2f%%)",
               _Symbol, TimeToString(plan.signalBar, TIME_DATE | TIME_MINUTES), side, setupId, plan.score,
               QATS_ClassName(plan_cls), PriceText(plan.entry), PriceText(sl), PriceText(tp), plan.tpSource,
               plan_rr, volume, riskMoney, g_spec.profitCcy, EffectiveRiskPercent());
   PrintFormat("[QATS][ORDER] %s %.2f lots %s @ %.5f | SL %.5f | TP %.5f (%s) | risk %.2f%% (%.2f %s) | score %d",
               side, volume, _Symbol, plan.entry, sl, tp, plan.tpSource,
               EffectiveRiskPercent(), riskMoney, g_spec.profitCcy, plan.score);

   if(InpDryRun)
   {
      g_executionStage = "DRY_RUN";
      g_executionReason = "dry run: order not sent";
      Print("[QATS][DRY RUN] " + g_executionReason);
      return false;
   }

   g_executionStage = "RESERVE";
   if(reserved)
      PrintFormat("[QATS][EXEC] reservation carried from the initial send (retry)");
   else if(!ReserveSignal(plan, g_executionReason))
      return false;
   g_executionStage = "BROKER";
   ConfigureTrade();
   bool sent = (plan.dir > 0)
      ? g_trade.Buy(volume, _Symbol, 0.0, sl, tp, InpTradeComment)
      : g_trade.Sell(volume, _Symbol, 0.0, sl, tp, InpTradeComment);

   uint rc  = (uint)g_trade.ResultRetcode();
   ulong deal   = g_trade.ResultDeal();
   ulong order  = g_trade.ResultOrder();
   string rcDesc= g_trade.ResultRetcodeDescription();

   PrintFormat("[QATS][EXEC] sent=%s retcode=%u (%s) deal=%I64u order=%I64u volume=%.2f price=%.5f",
               (sent ? "true" : "false"), rc, rcDesc, deal, order,
               g_trade.ResultVolume(), g_trade.ResultPrice());

   if(sent && IsSuccessRetcode(rc))
   {
      // filled-with-report (Phase 8): a fill short of the request is a fill, journalled as one
      double filledVol = g_trade.ResultVolume();
      if(QATS_FillShort(volume, filledVol))
         PrintFormat("[QATS][EXECUTION][PARTIAL] symbol=%s direction=%s requested=%.2f filled=%.2f shortfall=%.2f retcode=%u (%s) - filled-with-report; the verified position carries the filled volume",
                     _Symbol, side, volume, filledVol, volume - filledVol, rc, rcDesc);
      // A successful retcode is NOT proof of a position: verify it exists.
      ulong positionTicket = 0;
      bool positionVerified = VerifyPositionOpened(plan.dir, positionTicket);
      if(positionVerified)
         PrintFormat("[QATS][VERIFY] POSITION CONFIRMED on server: ticket=%I64u %s %.2f lots", positionTicket, side, volume);
      else
         PrintFormat("[QATS][VERIFY][CRITICAL] retcode=%u but NO open position found for %s %s - check terminal/journal NOW", rc, side, _Symbol);

      // count the trade for the daily cap
      string dk = TodayKey();
      GVSet(GVKey("trades_" + dk), (double)(g_tradesToday + 1));
      g_tradesToday++;
      // this setup is spent: it cannot open a second position
      MarkSetupTraded(plan.dir, plan.setupTime);
      g_statExecuted[SideIndex(plan.dir)]++;
      g_pendingRetryAt = 0;
      g_pendingRetries = 0;
      g_executionStage = "FILLED";
      g_executionReason = StringFormat("server accepted retcode=%u (%s); position %s", rc, rcDesc,
                                       (positionVerified ? "confirmed" : "NOT VERIFIED - inspect journal"));
      PrintFormat("[QATS][EXECUTION][FILLED] symbol=%s direction=%s setup=%s retcode=%u deal=%I64u order=%I64u price=%s requested=%.2f volume=%.2f position=%s ticket=%I64u",
                  _Symbol, side, setupId, rc, deal, order, PriceText(g_trade.ResultPrice()), volume, g_trade.ResultVolume(),
                  (positionVerified ? "verified" : "UNVERIFIED"), positionTicket);
      return true;
   }

   if(IsXAUUSD() || AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL)
   {
      g_executionReason = StringFormat("order not confirmed: sent=%s retcode=%u (%s); signal reserved, no automatic retry", (sent ? "true" : "false"), rc, rcDesc);
      return false;
   }
   if(IsTransientRetcode(rc) && g_pendingRetries < 3)
   {
      g_pendingRetryAt = (ulong)TimeTradeServer();
      g_pendingRetries++;
      g_pendingPlan    = plan;
      g_executionReason = StringFormat("transient retcode=%u (%s); retry queued", rc, rcDesc);
      PrintFormat("[QATS][EXEC] transient failure - queued retry %d/3 after next tick", g_pendingRetries);
      return false;
   }

   g_executionReason = StringFormat("server rejected retcode=%u (%s)", rc, rcDesc);
   PrintFormat("[QATS][EXEC][FAIL] %s rejected: retcode=%u (%s). Signal abandoned.", side, rc, rcDesc);
   g_pendingRetryAt = 0;
   g_pendingRetries = 0;
   return false;
}

// Retry a previously queued transient rejection, at most once every 5 seconds.
// The pending flag is cleared BEFORE the attempt: every exit path of ExecuteSignal
// then either queues the next retry (still transient, budget left) or leaves the
// flag cleared. A retry can therefore never lock entries out, and it passes through
// the complete guard chain like any other order.
void ProcessPendingRetry()
{
   if(g_pendingRetryAt == 0) return;
   if(TimeTradeServer() < (datetime)g_pendingRetryAt + 5) return;
   g_pendingRetryAt = 0;
   if(g_pendingRetries > 3)
   {
      PrintFormat("[QATS][RETRY] retry budget exhausted - signal abandoned");
      g_pendingRetries = 0;
      return;
   }
   SAnalysis plan = g_pendingPlan;
   // refresh the entry to the live price; the stop geometry is kept and re-validated
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   plan.entry = (plan.dir > 0) ? ask : bid;
   plan.stopDist = MathAbs(plan.entry - plan.sl);
   PrintFormat("[QATS][RETRY] re-submitting %s (retry %d/3)", (plan.dir > 0 ? "BUY" : "SELL"), g_pendingRetries);
   bool accepted = ExecuteSignal(plan, true);   // reservation already consumed by the initial send
   if(!accepted && g_pendingRetryAt == 0)
   {
      g_statRejected[SideIndex(plan.dir)]++;
      PrintFormat("[QATS][EXECUTION][REJECTED] symbol=%s bar=%s direction=%s setup=%s score=%d stage=RETRY/%s reason=%s",
                  _Symbol, TimeToString(plan.signalBar, TIME_DATE | TIME_MINUTES), SideName(plan.dir),
                  SetupId(plan.dir, plan.setupTime), plan.score, g_executionStage, g_executionReason);
      g_pendingRetries = 0;
   }
}

// Per-ticket refused-modify throttle (CR-4): the cooldown applies to the ticket that was
// actually refused, never to the account's other positions. Fixed slots, oldest evicted.
bool ManageFailRecent(const ulong ticket)
{
   datetime now = TimeTradeServer();
   for(int i = 0; i < QATS_MANAGE_FAIL_MAX; i++)
      if(g_manageFailTicket[i] == ticket && g_manageFailAt[i] > 0 && now - g_manageFailAt[i] < 10)
         return true;
   return false;
}

void ManageFailRecord(const ulong ticket)
{
   datetime now = TimeTradeServer();
   int slot = -1, oldest = -1;
   for(int i = 0; i < QATS_MANAGE_FAIL_MAX; i++)
   {
      if(g_manageFailTicket[i] == ticket) { slot = i; break; }
      if(g_manageFailAt[i] == 0) { slot = i; break; }
      if(oldest < 0 || g_manageFailAt[i] < g_manageFailAt[oldest]) oldest = i;
   }
   if(slot < 0) slot = oldest;
   g_manageFailTicket[slot] = ticket;
   g_manageFailAt[slot] = now;
}

//+------------------------------------------------------------------+
//| SECTION 20 - POSITION MANAGEMENT                                 |
//| Break-even move, partial bank at +R, opposite-signal exit.       |
//| Every position MUST carry a protective stop; one that lost its   |
//| stop gets one rebuilt from ATR immediately.                      |
//+------------------------------------------------------------------+
void ManagePositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;

      long type   = PositionGetInteger(POSITION_TYPE);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      double vol  = PositionGetDouble(POSITION_VOLUME);
      int dir     = (type == POSITION_TYPE_BUY) ? +1 : -1;
      double price= (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      //--- emergency protection: a position without SL is re-protected now
      if(sl <= 0.0)
      {
         double atr = 0.0;
         if(!BufValue(g_hATRM5, 1, atr) || atr <= 0.0) atr = 100.0 * g_spec.point;
         double newSL = (dir > 0) ? price - 1.5 * atr : price + 1.5 * atr;
         if(g_trade.PositionModify(ticket, newSL, tp))
            PrintFormat("[QATS][PROTECT] ticket=%I64u had NO stop - rebuilt SL @ %.5f", ticket, newSL);
         else
            PrintFormat("[QATS][PROTECT][CRITICAL] ticket=%I64u has NO stop and modification FAILED retcode=%u",
                        ticket, (uint)g_trade.ResultRetcode());
         continue;
      }

      double riskDist = MathAbs(open - sl);
      if(riskDist <= 0.0) continue;
      double gain = (dir > 0) ? (price - open) : (open - price);
      double rMultiple = gain / riskDist;

      //--- break-even: move SL to entry once, never widen it
      if(InpBreakEvenAtR > 0.0 && rMultiple >= InpBreakEvenAtR)
      {
         double beSL = open;
         bool needMove = (dir > 0) ? (sl < beSL - g_spec.point) : (sl > beSL + g_spec.point);
         // a refused modify is journalled and not re-sent for 10 seconds
         if(needMove && IsStopValid(beSL, price) && !ManageFailRecent(ticket))
         {
            if(g_trade.PositionModify(ticket, beSL, tp))
               PrintFormat("[QATS][MANAGE] ticket=%I64u SL -> BREAK-EVEN @ %.5f (+%.2fR)", ticket, beSL, rMultiple);
            else
            {
               ManageFailRecord(ticket);
               PrintFormat("[QATS][MANAGE] ticket=%I64u break-even modify REFUSED retcode=%u (%s) - this ticket retries in 10s (other positions unaffected)",
                           ticket, (uint)g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
            }
         }
      }

      //--- partial bank at +R (once per position, persisted)
      if(InpPartialCloseAtR > 0.0 && rMultiple >= InpPartialCloseAtR && InpPartialClosePercent > 0.0)
      {
         string pcKey = GVKey("pc_" + IntegerToString((long)ticket));
         if(!GlobalVariableCheck(pcKey))
         {
            double closeVol = MathFloor(vol * InpPartialClosePercent / 100.0 / g_spec.volStep) * g_spec.volStep;
            if(closeVol >= g_spec.volMin && closeVol < vol)
            {
               if(PartialClose(ticket, closeVol, dir))
               {
                  GVSet(pcKey, 1.0);
                  PrintFormat("[QATS][MANAGE] ticket=%I64u PARTIAL CLOSE %.2f lots @ +%.2fR (banked)", ticket, closeVol, rMultiple);
               }
            }
            else
            {
               GVSet(pcKey, 1.0); // nothing sane to close (e.g. volume too small) - mark done
               PrintFormat("[QATS][MANAGE] ticket=%I64u partial close skipped: computed %.2f lots vs min %.2f",
                           ticket, closeVol, g_spec.volMin);
            }
         }
      }
   }
}

bool IsStopValid(const double newSL, const double price)
{
   double minDist = (double)MathMax(MathMax(g_spec.stopsLevel, g_spec.freezeLevel), 1) * g_spec.point;
   return MathAbs(price - newSL) >= minDist;
}

bool PartialClose(const ulong ticket, const double volume, const int dir)
{
   MqlTradeRequest req = {};
   MqlTradeResult  res = {};
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = _Symbol;
   req.volume    = volume;
   req.type      = (dir > 0) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.magic     = InpMagic;
   req.comment   = InpTradeComment + "-PC";
   req.deviation = (ulong)InpDeviationPoints;
   // hedging accounts: target the specific position ticket.
   // netting/exchange accounts: the opposite deal reduces the net position
   // automatically; MqlTradeRequest.position is not used there.
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      req.position = ticket;
   long filling  = (long)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) req.type_filling = ORDER_FILLING_FOK;
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) req.type_filling = ORDER_FILLING_IOC;
   else req.type_filling = ORDER_FILLING_RETURN;
   req.price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   ResetLastError();
   if(!OrderSend(req, res))
   {
      PrintFormat("[QATS][MANAGE] partial close OrderSend failed error=%d retcode=%u", GetLastError(), res.retcode);
      return false;
   }
   if(res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_DONE_PARTIAL)
   {
      PrintFormat("[QATS][MANAGE] partial close refused retcode=%u", res.retcode);
      return false;
   }
   return true;
}

void ClosePositionOnOpposite(const int newSignalDir)
{
   if(!InpCloseOnOpposite || newSignalDir == 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      long type = PositionGetInteger(POSITION_TYPE);
      int dir = (type == POSITION_TYPE_BUY) ? +1 : -1;
      if(dir == newSignalDir) continue;
      if(g_trade.PositionClose(ticket, (ulong)InpDeviationPoints))
         PrintFormat("[QATS][MANAGE] ticket=%I64u closed on OPPOSITE signal (%s)", ticket, (newSignalDir > 0 ? "BUY" : "SELL"));
      else
         PrintFormat("[QATS][MANAGE] opposite-close failed for ticket=%I64u retcode=%u", ticket, (uint)g_trade.ResultRetcode());
   }
}

//+------------------------------------------------------------------+
//| SECTION 20b - LIMIT ENTRY AT THE SMC ZONE (v1.21)                |
//|                                                                  |
//| The evidence engine, the scoring, the guard chain and the trade  |
//| plan are unchanged. What changes is WHERE the order sits: with   |
//| InpUseLimitEntry the EA rests a BUY LIMIT / SELL LIMIT at a      |
//| strong, UNMITIGATED order block or fair value gap and lets the   |
//| retracement come to it, instead of paying the market mid-move.   |
//|                                                                  |
//| Rules that are never bent here:                                   |
//|  - every structural input comes from CLOSED bars (shift >= 1);   |
//|  - every order carries a server-side stop loss;                   |
//|  - the stop is the far edge of the zone plus a buffer: it is      |
//|    derived from the zone, never widened to make a setup fit;      |
//|  - a pending order is NOT a trade: it never consumes the daily    |
//|    trade cap. Only a FILLED entry does, exactly once.             |
//+------------------------------------------------------------------+
#define QATS_LIMIT_PREFIX  "[QATS][LIMIT]"

// Zone sources, in the order BuildLimitPlan prefers them.
#define QATS_ZONE_OB_FVG   0     // order block and fair value gap overlap
#define QATS_ZONE_OB       1
#define QATS_ZONE_FVG      2

int    g_limitZoneSource = -1;   // source of the last limit plan (journal + tests)

string ZoneSourceName(const int src)
{
   if(src == QATS_ZONE_OB_FVG) return "OB+FVG";
   if(src == QATS_ZONE_OB)     return "OB";
   if(src == QATS_ZONE_FVG)    return "FVG";
   return "NONE";
}

// BUY LIMIT / SELL LIMIT orders of this EA on this symbol.
int CountMyPending()
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      long type = OrderGetInteger(ORDER_TYPE);
      if(type != ORDER_TYPE_BUY_LIMIT && type != ORDER_TYPE_SELL_LIMIT) continue;
      count++;
   }
   return count;
}

// A zone is MITIGATED when a closed H1 bar has already traded through it: for a
// supply zone (dir < 0) the first bar after the zone whose HIGH is above the top
// has taken the orders resting in it; for a demand zone (dir > 0) the first bar
// whose LOW is below the bottom has. Closed bars only: shift from z.shift-1 to 1.
bool ZoneUnmitigated(const SZone &z, const int dir)
{
   if(!z.found || z.top <= z.bottom || dir == 0) return false;
   int bars = iBars(_Symbol, PERIOD_H1);
   if(bars < 2) return false;
   int from = z.shift - 1;
   if(from > bars - 1) from = bars - 1;
   for(int s = from; s >= 1; s--)
   {
      if(dir < 0)
      {
         if(iHigh(_Symbol, PERIOD_H1, s) > z.top) return false;
      }
      else
      {
         if(iLow(_Symbol, PERIOD_H1, s) < z.bottom) return false;
      }
   }
   return true;
}

// Union of an order block and a fair value gap, when they share prices.
bool ZoneOverlaps(const SZone &a, const SZone &b)
{
   if(!a.found || !b.found) return false;
   return (a.bottom <= b.top && b.bottom <= a.top);
}

// The limit price inside a zone. Mode 0 = the 50% of the zone (the usual
// refinement), mode 1 = the near edge, i.e. the first price the retracement
// meets. Both are snapped to the broker tick grid, always INTO the zone so a
// limit can never sit outside the zone it is named after.
double LimitEntryPrice(const SZone &z, const int dir, const double tick, const int digits)
{
   double mid = (z.top + z.bottom) / 2.0;
   double near = (dir > 0) ? z.bottom : z.top;      // the edge the retracement meets first
   double px = (InpLimitEntryMode == 1) ? near : mid;
   bool roundUp = (dir > 0);       // BUY rounds up (stays inside), SELL rounds down
   px = QATS_SnapToTick(px, tick, digits, roundUp);
   if(dir > 0) { if(px < z.bottom) px = QATS_SnapToTick(z.bottom, tick, digits, true);
                 if(px > z.top)    px = QATS_SnapToTick(z.top, tick, digits, false); }
   else        { if(px > z.top)    px = QATS_SnapToTick(z.top, tick, digits, false);
                 if(px < z.bottom) px = QATS_SnapToTick(z.bottom, tick, digits, true); }
   return px;
}

// The candidate zone for one direction, in preference order:
//   OB+FVG overlap -> OB -> FVG, skipping any zone that is already mitigated.
bool PickEntryZone(const SSide &side, const int dir, SZone &out, int &source, string &why)
{
   SZone overlap;
   overlap.found = false;
   if(side.hasOB && side.hasFVG && ZoneOverlaps(side.ob, side.fvg))
   {
      overlap.found  = true;
      overlap.isFVG  = false;
      overlap.top    = MathMin(side.ob.top, side.fvg.top);
      overlap.bottom = MathMax(side.ob.bottom, side.fvg.bottom);
      overlap.shift  = MathMin(side.ob.shift, side.fvg.shift);
   }
   int order[3] = {QATS_ZONE_OB_FVG, QATS_ZONE_OB, QATS_ZONE_FVG};
   why = "no OB and no FVG for this direction";
   for(int i = 0; i < 3; i++)
   {
      SZone z;
      z.found  = false;
      z.top    = 0.0;
      z.bottom = 0.0;
      z.shift  = 0;
      z.isFVG  = false;
      if(order[i] == QATS_ZONE_OB_FVG) z = overlap;
      if(order[i] == QATS_ZONE_OB)     z = side.ob;
      if(order[i] == QATS_ZONE_FVG)    z = side.fvg;
      if(!z.found) continue;
      if(!ZoneUnmitigated(z, dir))
      {
         why = ZoneSourceName(order[i]) + " zone already mitigated by a closed H1 bar";
         continue;
      }
      out    = z;
      source = order[i];
      why    = "";
      return true;
   }
   return false;
}

// TRUE when a price is on the allowed side of the SELECTED adaptive range's midpoint.
// The SAME rule the market path enforces, evaluated on the chart entry price; the
// range and the selection come from the analysis, nothing is re-derived here.
// Fails closed when no range is valid - PD is never silently bypassed.
bool LimitPriceInPD(const SAnalysis &a, const int dir, const double price, string &why)
{
   return PdPriceOnSide(a.pdSelected, a.pdEq, a.pdStatus, dir, price, "PD_LIMIT", why);
}

// The LIMIT plan: entry at the zone, stop beyond the FAR edge of the zone, target
// at the nearest range liquidity, reward:risk measured from the LIMIT price.
bool BuildLimitPlan(const SAnalysis &a, SAnalysis &out)
{
   out = a;
   g_executionStage  = "LIMIT_PLAN";
   g_executionReason = "invalid direction";
   if(out.dir != 1 && out.dir != -1) return false;

   double atrH1 = 0.0;
   g_executionReason = "H1 ATR unavailable";
   if(!BufValue(g_hATRH1, 1, atrH1)) return false;
   g_executionReason = "H1 ATR is nonpositive";
   if(atrH1 <= 0.0) return false;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   g_executionReason = "invalid bid/ask quote";
   if(bid <= 0.0 || ask < bid) return false;
   double spread = ask - bid;
   double point  = g_spec.point;
   double tick   = g_spec.tickSize;
   if(point <= 0.0 || tick <= 0.0 || g_spec.digits < 0)
   {
      g_executionReason = "broker tick size unavailable";
      return false;
   }

   SSide side = (out.dir > 0) ? out.buy : out.sell;   // a copy: MQL5 has no struct pointers
   SZone zone;
   int source = 0;
   string why = "";
   g_executionReason = "no unmitigated OB/FVG zone for this direction";
   if(!PickEntryZone(side, out.dir, zone, source, why))
   {
      g_executionReason = why;
      return false;
   }

   //--- the entry: 50% of the zone, or the near edge, on the tick grid.
   // Charts are drawn from the BID (see SECTION 16). A BUY LIMIT fills on the ASK,
   // a SELL LIMIT on the BID, so the SELL price of a chart level sits one spread
   // higher - exactly the convention BuildTradePlan already uses for SELL stops
   // and targets. Without it a SELL limit would fill one spread LATE and the
   // whole plan would stop being the mirror image of its BUY twin.
   double chartEntry = LimitEntryPrice(zone, out.dir, tick, g_spec.digits);
   double entry = (out.dir > 0) ? chartEntry : QATS_SnapToTick(chartEntry + spread, tick, g_spec.digits, true);
   g_executionReason = "zone entry is not a valid price";
   if(entry <= 0.0) return false;

   //--- distance guards: broker freeze/stops level, already passed, too far away
   double minGap = (double)MathMax(MathMax(g_spec.stopsLevel, g_spec.freezeLevel), 1) * point;
   if(out.dir > 0)
   {
      if(entry >= ask - minGap)
      {
         g_executionReason = StringFormat("BUY zone entry %s is at/above the ask %s minus the stops level - already passed",
                                          PriceText(entry), PriceText(ask));
         return false;
      }
   }
   else
   {
      if(entry <= bid + minGap)
      {
         g_executionReason = StringFormat("SELL zone entry %s is at/below the bid %s plus the stops level - already passed",
                                          PriceText(entry), PriceText(bid));
         return false;
      }
   }
   double dist = (out.dir > 0) ? (ask - entry) : (entry - bid);
   double maxDist = MathMax(InpLimitMaxDistATR, 0.0) * atrH1;
   if(dist > maxDist)
   {
      g_executionReason = StringFormat("zone is %.1f pts away, more than %.1f x H1 ATR (%.1f pts)",
                                       dist / point, InpLimitMaxDistATR, maxDist / point);
      return false;
   }

   //--- premium / discount: never BUY into premium, never SELL into discount
   if(InpLimitNeedPD && !LimitPriceInPD(out, out.dir, chartEntry, why))
   {
      g_executionReason = why;
      return false;
   }

   //--- the stop: BEYOND THE FAR EDGE of the zone, plus buffer and current spread.
   // It is snapped AWAY from the entry, so the stop can only get wider than the
   // computed distance, never closer - and it is the zone that defines it.
   double buffer = MathMax(InpLimitSLBufferATR, 0.0) * atrH1 + spread;
   double chartSL = 0.0;
   if(out.dir > 0) chartSL = QATS_SnapToTick(zone.bottom - buffer, tick, g_spec.digits, false);
   else            chartSL = QATS_SnapToTick(zone.top + buffer,    tick, g_spec.digits, true);
   // the BUY stop is hit by the BID (the chart level itself); the SELL stop is hit
   // by the ASK, which reaches the same chart level one spread later
   double sl = (out.dir > 0) ? chartSL : QATS_SnapToTick(chartSL + spread, tick, g_spec.digits, true);
   double stopDist = MathAbs(entry - sl);
   if(stopDist <= 0.0)
   {
      g_executionReason = "zone stop distance is zero";
      return false;
   }
   double minStopPts = MathMax(MathMax((double)InpMinStopPoints, (double)g_spec.stopsLevel), 1.0) * point;
   double maxStopPts = (double)InpMaxStopPoints * point;
   if(stopDist < minStopPts)
   {
      g_executionReason = StringFormat("zone stop %.1f pts is below the minimum %.1f pts (zone too tight to protect the entry)",
                                       stopDist / point, minStopPts / point);
      return false;
   }
   if(stopDist > maxStopPts)
   {
      g_executionReason = StringFormat("zone stop %.1f pts is above the maximum %.1f pts", stopDist / point, maxStopPts / point);
      return false;
   }
   // the stop must be at least a freezone/stops level away from the zone edge at
   // the broker, or the pending order carries a stop the server will refuse
   if(MathAbs(entry - sl) < minGap)
   {
      g_executionReason = StringFormat("zone stop is inside the broker stops/freeze level (%.1f pts)", minGap / point);
      return false;
   }

   //--- the target: the nearest INTACT range liquidity the trade runs into,
   // offset 0.10 x H1 ATR back inside the range; otherwise the RR fallback.
   SSwing highs[], lows[];
   SLiquidityPool pools[];
   LiquidityContext(_Symbol, atrH1, highs, lows, pools);
   double inside = 0.10 * atrH1;
   double tp = 0.0;
   string tpSource = "RR";
   double target = 0.0;
   string targetKind = "";
   double minRR = MathMax(InpLimitMinRR, 0.0);
   double targetLevel = 0.0;
   if(NearestLiquidityTarget(pools, out.dir, entry, stopDist, minRR, spread, target, targetKind, targetLevel))
   {
      tp = (out.dir > 0) ? QATS_SnapToTick(target - inside, tick, g_spec.digits, false)
                         : QATS_SnapToTick(target + inside, tick, g_spec.digits, true);
      tpSource = "LIQUIDITY:" + targetKind + "@" + PriceText(targetLevel);
      out.tpLevel = targetLevel;
   }
   else
   {
      double rrMult = MathMax(InpRewardRisk, minRR);
      tp = (out.dir > 0) ? entry + stopDist * rrMult : entry - stopDist * rrMult;
      tp = QATS_SnapToTick(tp, tick, g_spec.digits, (out.dir > 0));
      out.tpLevel = 0.0;
   }
   if(MathAbs(tp - entry) < minGap)
   {
      g_executionReason = StringFormat("target %s is inside the broker stops level from the limit price %s",
                                       PriceText(tp), PriceText(entry));
      return false;
   }
   double rr = MathAbs(tp - entry) / stopDist;
   if(rr + 0.000000001 < minRR)
   {
      g_executionReason = StringFormat("reward:risk %.2f from the limit price %s is below InpLimitMinRR %.2f",
                                       rr, PriceText(entry), minRR);
      return false;
   }
   // geometry sanity: a BUY limit needs the target above it and the stop below it
   if(out.dir > 0 && !(tp > entry && sl < entry))
   {
      g_executionReason = "BUY limit geometry is inverted (target/stop)";
      return false;
   }
   if(out.dir < 0 && !(tp < entry && sl > entry))
   {
      g_executionReason = "SELL limit geometry is inverted (target/stop)";
      return false;
   }

   out.entry    = entry;
   out.sl       = sl;
   out.tp       = tp;
   out.stopDist = stopDist;
   out.tpSource = tpSource;
   g_limitZoneSource = source;
   g_executionReason = "";
   g_executionStage  = "LIMIT_PLAN";
   return true;
}

// Retcodes a pending order request can come back with when the FILLING POLICY is
// the problem: the order is then re-sent with the next policy in line.
bool IsInvalidFillRetcode(const uint rc)
{
   return (rc == TRADE_RETCODE_INVALID_FILL);
}

bool IsPlacedOrDone(const uint rc)
{
   return (rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL);
}

// Place the zone limit. Same guard chain as a market entry, same sizing identity,
// same XAUUSD duplicate reservation, same dry-run path - only the ORDER TYPE and
// the price are different.
bool PlaceLimitOrder(const SAnalysis &raw)
{
   g_executionReason = "";
   g_executionStage  = "LIMIT_PRECHECK";
   if(!InpUseLimitEntry) return false;
   if(raw.dir != 1 && raw.dir != -1)
   {
      g_executionReason = "invalid direction";
      return false;
   }
   if(!QATS_ScoreEligible(raw.dir, raw.score, InpMinScore))
   {
      g_executionReason = "invalid direction or score below minimum";
      return false;
   }
   if(!LoadSymbolSpec(g_spec))
   {
      g_executionReason = "broker symbol specification unavailable or invalid";
      return false;
   }
   // the whole guard chain, unchanged: authorization, locks, cooldown, daily cap,
   // spread, session, stale tick, position cap (positions + pending)
   string guard = "";
   if(!EntriesAllowed(guard))
   {
      g_executionReason = guard;
      PrintFormat("%s NOT_PLACED direction=%s reason=%s", QATS_LIMIT_PREFIX, SideName(raw.dir), guard);
      return false;
   }
   // never hold both sides, never re-trade a spent setup - re-checked at send time
   if(OppositePositionOpen(raw.dir))
   {
      g_executionReason = "an opposite position of this EA is still open";
      PrintFormat("%s NOT_PLACED direction=%s reason=%s", QATS_LIMIT_PREFIX, SideName(raw.dir), g_executionReason);
      return false;
   }
   if(SetupAlreadyTraded(raw.dir, raw.setupTime))
   {
      g_executionReason = "setup " + SetupId(raw.dir, raw.setupTime) + " was already traded";
      PrintFormat("%s NOT_PLACED direction=%s reason=%s", QATS_LIMIT_PREFIX, SideName(raw.dir), g_executionReason);
      return false;
   }

   SAnalysis plan;
   if(!BuildLimitPlan(raw, plan))
   {
      PrintFormat("%s REJECTED direction=%s bar=%s reason=%s",
                  QATS_LIMIT_PREFIX, SideName(raw.dir),
                  TimeToString(raw.signalBar, TIME_DATE | TIME_MINUTES), g_executionReason);
      return false;
   }
   if(CountMyPending() >= MathMax(1, InpMaxOpenPositions))
   {
      g_executionReason = "a pending order of this EA is already working";
      PrintFormat("%s NOT_PLACED direction=%s reason=%s", QATS_LIMIT_PREFIX, SideName(raw.dir), g_executionReason);
      return false;
   }

   // spread versus the stop the limit order will carry
   g_executionStage = "LIMIT_SPREAD_VS_STOP";
   double spreadPts = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point;
   if(spreadPts > plan.stopDist / g_spec.point * InpMaxSpreadFracOfStop)
   {
      g_executionReason = StringFormat("spread %.2f pts exceeds %.2f%% of the zone stop distance",
                                       spreadPts, InpMaxSpreadFracOfStop * 100.0);
      PrintFormat("%s NOT_PLACED direction=%s reason=%s", QATS_LIMIT_PREFIX, SideName(raw.dir), g_executionReason);
      return false;
   }

   // sizing from the SL distance OF THE LIMIT PRICE, exactly as a market entry is
   // sized from its own stop distance
   g_executionStage = "LIMIT_SIZE";
   double volume = 0.0, riskMoney = 0.0;
   if(!CalcPositionVolume(plan.stopDist, plan.dir > 0, volume, riskMoney))
   {
      PrintFormat("%s NOT_PLACED direction=%s reason=%s", QATS_LIMIT_PREFIX, SideName(raw.dir), g_executionReason);
      return false;
   }

   double rr = MathAbs(plan.tp - plan.entry) / plan.stopDist;
   datetime expiry = TimeTradeServer() + (datetime)MathMax(InpLimitExpiryMin, 1) * 60;
   string side  = (plan.dir > 0) ? "BUY" : "SELL";
   string zsrc  = ZoneSourceName(g_limitZoneSource);
   g_statApproved[SideIndex(plan.dir)]++;
   PrintFormat("%s PLAN direction=%s symbol=%s bar=%s setup=%s score=%d type=%s_LIMIT entry=%s sl=%s tp=%s tpSource=%s rr=%.2f stopPts=%.1f zone=%s volume=%.2f risk=%.2f %s expiry=%s",
               QATS_LIMIT_PREFIX, side, _Symbol, TimeToString(plan.signalBar, TIME_DATE | TIME_MINUTES),
               SetupId(plan.dir, plan.setupTime), plan.score, side,
               PriceText(plan.entry), PriceText(plan.sl), PriceText(plan.tp), plan.tpSource, rr,
               plan.stopDist / g_spec.point, zsrc, volume, riskMoney, g_spec.profitCcy,
               TimeToString(expiry, TIME_DATE | TIME_MINUTES));

   if(InpDryRun)
   {
      g_executionStage  = "DRY_RUN";
      g_executionReason = "dry run: pending order not sent";
      PrintFormat("%s DRY_RUN NOT_PLACED direction=%s entry=%s sl=%s tp=%s volume=%.2f risk=%.2f %s zone=%s",
                  QATS_LIMIT_PREFIX, side, PriceText(plan.entry), PriceText(plan.sl), PriceText(plan.tp),
                  volume, riskMoney, g_spec.profitCcy, zsrc);
      return false;
   }

   // CR-3 duplicate protection, identical on every symbol: reserve BEFORE sending
   g_executionStage = "LIMIT_RESERVE";
   if(!ReserveSignal(plan, g_executionReason))
   {
      PrintFormat("%s NOT_PLACED direction=%s reason=%s", QATS_LIMIT_PREFIX, side, g_executionReason);
      return false;
   }

   g_executionStage = "LIMIT_BROKER";
   ConfigureTrade();
   ENUM_ORDER_TYPE otype = (plan.dir > 0) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
   long fillingMode = (long)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   ENUM_ORDER_TYPE_FILLING policies[3];
   int npol = 0;
   policies[npol++] = ORDER_FILLING_RETURN;                     // first choice: a resting limit
   if((fillingMode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) policies[npol++] = ORDER_FILLING_IOC;
   if((fillingMode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) policies[npol++] = ORDER_FILLING_FOK;

   bool sent = false;
   uint rc = TRADE_RETCODE_ERROR;
   ulong orderTicket = 0;
   string rcDesc = "";
   for(int attempt = 0; attempt < npol; attempt++)
   {
      g_trade.SetTypeFilling(policies[attempt]);
      // CTrade::OrderOpen(symbol, type, volume, LIMIT_PRICE, PRICE, sl, tp,
      // type_time, expiration, comment). Two things MetaEditor caught in v1.21:
      //   * the SYMBOL is the first parameter. The 9-argument form resolved to this
      //     overload and reported "cannot convert enum" on the order type.
      //   * LIMIT_PRICE (the StopLimit trigger) comes BEFORE PRICE. A plain limit
      //     passes 0.0 there and its execution price in `price`; passing them the
      //     other way round sends a StopLimit order that never works as a limit.
      sent = g_trade.OrderOpen(_Symbol, otype, volume, 0.0, plan.entry, plan.sl, plan.tp,
                               ORDER_TIME_SPECIFIED, expiry, InpTradeComment);
      rc      = (uint)g_trade.ResultRetcode();
      orderTicket = g_trade.ResultOrder();
      rcDesc  = g_trade.ResultRetcodeDescription();
      PrintFormat("%s SEND direction=%s filling=%s sent=%s retcode=%u (%s) order=%I64u price=%s volume=%.2f",
                  QATS_LIMIT_PREFIX, side,
                  (policies[attempt] == ORDER_FILLING_RETURN ? "RETURN" : (policies[attempt] == ORDER_FILLING_IOC ? "IOC" : "FOK")),
                  (sent ? "true" : "false"), rc, rcDesc, orderTicket, PriceText(plan.entry), volume);
      if(!IsInvalidFillRetcode(rc)) break;
   }
   // the market path's filling policy is restored for every later send
   ConfigureTrade();

   if(sent && IsPlacedOrDone(rc))
   {
      // a PLACED retcode is not proof of an order: confirm it is on the server
      bool onServer = (orderTicket != 0);
      if(onServer)
      {
         for(int i = OrdersTotal() - 1; i >= 0; i--)
         {
            ulong t = OrderGetTicket(i);
            if(t == 0) continue;
            if(OrderGetInteger(ORDER_TICKET) != (long)orderTicket) continue;
            if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
            if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
            onServer = true;
            break;
         }
      }
      if(!onServer)
         PrintFormat("%s VERIFY[CRITICAL] retcode=%u but no pending order was found for %s %s - inspect the journal NOW",
                     QATS_LIMIT_PREFIX, rc, side, _Symbol);
      // The setup is NOT spent here: a placement is not a trade, and a limit that
      // expires or is cancelled must leave the setup tradable. The identity is
      // persisted so the FILL (which may come hours later, or after a restart)
      // can spend it exactly once - see OnTradeTransaction.
      if(plan.setupTime > 0)
         GVSet(GVKey(plan.dir > 0 ? "limit_setup_buy" : "limit_setup_sell"), (double)plan.setupTime);
      g_executionStage  = "LIMIT_PLACED";
      g_executionReason = StringFormat("server accepted retcode=%u (%s); order %s", rc, rcDesc,
                                       (onServer ? "confirmed" : "NOT VERIFIED - inspect journal"));
      PrintFormat("%s PLACED direction=%s setup=%s order=%I64u entry=%s sl=%s tp=%s volume=%.2f risk=%.2f %s rr=%.2f zone=%s (pending orders are not counted against the daily trade cap)",
                  QATS_LIMIT_PREFIX, side, SetupId(plan.dir, plan.setupTime), orderTicket,
                  PriceText(plan.entry), PriceText(plan.sl), PriceText(plan.tp),
                  volume, riskMoney, g_spec.profitCcy, rr, zsrc);
      return true;
   }

   g_executionStage  = "LIMIT_BROKER";
   g_executionReason = StringFormat("pending order not accepted: sent=%s retcode=%u (%s); no automatic retry",
                                    (sent ? "true" : "false"), rc, rcDesc);
   PrintFormat("%s NOT_PLACED direction=%s retcode=%u (%s) reason=%s",
               QATS_LIMIT_PREFIX, side, rc, rcDesc, g_executionReason);
   return false;
}

// Cancellation reasons, journalled with every delete.
#define QATS_CANCEL_EXPIRED    0
#define QATS_CANCEL_SL_CLOSED  1
#define QATS_CANCEL_OPPOSITE   2
#define QATS_CANCEL_RAN_AWAY   3
#define QATS_CANCEL_MANUAL     4
#define QATS_CANCEL_SETUP_GONE 5

string CancelReasonName(const int code)
{
   if(code == QATS_CANCEL_EXPIRED)   return "EXPIRED";
   if(code == QATS_CANCEL_SL_CLOSED) return "M5_CLOSED_BEYOND_SL";
   if(code == QATS_CANCEL_OPPOSITE)  return "OPPOSITE_SIGNAL";
   if(code == QATS_CANCEL_RAN_AWAY)  return "PRICE_RAN_AWAY";
   if(code == QATS_CANCEL_SETUP_GONE) return "SETUP_GONE";
   return "OPERATOR_OR_BROKER";
}

// The setup that produced a resting limit, as persisted at placement.
datetime PendingOrderSetupTime(const int dir)
{
   return (datetime)GVGet(GVKey(dir > 0 ? "limit_setup_buy" : "limit_setup_sell"), 0.0);
}

bool DeletePendingOrder(const ulong ticket, const int reasonCode, const string detail)
{
   // position management must never run on an unauthorized terminal: the cancel
   // is part of the same account, so re-verify before touching the server
   string why = "";
   if(!VerifyAccountProtection(why))
   {
      PrintFormat("%s CANCEL_DEFERRED ticket=%I64u reason=%s detail=%s (protection: %s)",
                  QATS_LIMIT_PREFIX, ticket, CancelReasonName(reasonCode), detail, why);
      return false;
   }
   ConfigureTrade();
   bool ok = g_trade.OrderDelete(ticket);
   uint rc = (uint)g_trade.ResultRetcode();
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL || rc == TRADE_RETCODE_PLACED))
   {
      PrintFormat("%s CANCELLED ticket=%I64u reason=%s detail=%s (no trade was opened: the daily trade cap is untouched)",
                  QATS_LIMIT_PREFIX, ticket, CancelReasonName(reasonCode), detail);
      return true;
   }
   PrintFormat("%s CANCEL_FAILED ticket=%I64u reason=%s detail=%s retcode=%u (%s)",
               QATS_LIMIT_PREFIX, ticket, CancelReasonName(reasonCode), detail, rc, g_trade.ResultRetcodeDescription());
   return false;
}

// Housekeeping for this EA's pending limits. Each order is deleted for exactly
// one named reason, and the journal always says which.
void ManagePendingOrders(const SAnalysis &raw)
{
   if(!InpUseLimitEntry) return;
   if(OrdersTotal() == 0) return;
   double atrH1 = 0.0;
   bool haveAtr = BufValue(g_hATRH1, 1, atrH1) && atrH1 > 0.0;
   datetime now  = TimeTradeServer();
   int oppositeDir = (raw.dataReady && raw.dir != 0 &&
                      QATS_ScoreEligible(raw.dir, raw.score, InpMinScore)) ? -raw.dir : 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      long type = OrderGetInteger(ORDER_TYPE);
      bool isBuyLimit  = (type == ORDER_TYPE_BUY_LIMIT);
      bool isSellLimit = (type == ORDER_TYPE_SELL_LIMIT);
      if(!isBuyLimit && !isSellLimit) continue;
      int dir = isBuyLimit ? +1 : -1;
      double price = OrderGetDouble(ORDER_PRICE_OPEN);
      double sl    = OrderGetDouble(ORDER_SL);
      datetime expiration = (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION);

      // 1. expired. The server also expires it; this keeps the journal exact.
      if(expiration > 0 && now >= expiration)
      {
         DeletePendingOrder(ticket, QATS_CANCEL_EXPIRED,
                            StringFormat("expiry %s reached", TimeToString(expiration, TIME_DATE | TIME_MINUTES)));
         continue;
      }

      // 2. an M5 bar CLOSED beyond the order's stop: the idea is invalidated
      double m5 = iClose(_Symbol, PERIOD_M5, 1);
      if(sl > 0.0 && m5 > 0.0)
      {
         if((dir > 0 && m5 < sl) || (dir < 0 && m5 > sl))
         {
            DeletePendingOrder(ticket, QATS_CANCEL_SL_CLOSED,
                               StringFormat("M5 close %s is beyond SL %s", PriceText(m5), PriceText(sl)));
            continue;
         }
      }

      // 3. an opposite, eligible signal: never hold both sides
      if(oppositeDir != 0 && dir == oppositeDir)
      {
         DeletePendingOrder(ticket, QATS_CANCEL_OPPOSITE,
                            StringFormat("opposite %s signal score=%d", SideName(raw.dir), raw.score));
         continue;
      }

      // 4. price ran away from the zone: the retracement is not coming
      if(haveAtr)
      {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double away = (dir > 0) ? (ask - price) : (price - bid);
         double limit = 1.5 * MathMax(InpLimitMaxDistATR, 0.0) * atrH1;
         if(away > limit)
         {
            DeletePendingOrder(ticket, QATS_CANCEL_RAN_AWAY,
                               StringFormat("price moved %.1f pts from the zone, limit %.1f pts",
                                            away / g_spec.point, limit / g_spec.point));
            continue;
         }
      }
      // 5. the SET for which the order was placed is gone: the signal source now
      //    shows a different, newer setup of this direction (or none at all), so
      //    the resting limit no longer belongs to anything the EA believes in.
      if(raw.dataReady)
      {
         // MQL5 has no pointer dereference on structures: take a COPY of the side
         datetime liveSetup = (dir > 0) ? raw.buy.setupTime : raw.sell.setupTime;
         datetime placed = PendingOrderSetupTime(dir);
         if(placed > 0 && liveSetup > 0 && liveSetup != placed)
         {
            DeletePendingOrder(ticket, QATS_CANCEL_SETUP_GONE,
                               StringFormat("setup changed from %s to %s", SetupId(dir, placed), SetupId(dir, liveSetup)));
            continue;
         }
      }
      // otherwise the order is still valid and keeps working until one of the
      // conditions above, or its own expiry, says otherwise
   }
}

//+------------------------------------------------------------------+
//| SECTION 21 - DAILY GUARDS, LOSS STREAK & COOLDOWN                |
//| The loss streak counts POSITIONS, from the actual deal history:  |
//| all deals of a position (partial closes, commission, swap, fee)  |
//| are netted, and a position belongs to this EA when its ENTRY     |
//| deal carries this magic - whoever closed it.                     |
//| Cooldown state is explicit and persisted: start, expiry, the     |
//| number of losses that triggered it. The streak restarts at zero  |
//| when the stand-down begins, so "consecLosses=0 cooldown=YES" is  |
//| a running timer, not a stuck flag - and the journal now says so. |
//+------------------------------------------------------------------+
bool BoundAccountActive()
{
   return g_boundLogin > 0 && g_boundServer != "" &&
          AccountInfoInteger(ACCOUNT_LOGIN) == g_boundLogin &&
          AccountInfoString(ACCOUNT_SERVER) == g_boundServer &&
          AccountInfoInteger(ACCOUNT_TRADE_MODE) == g_boundMode;
}

// Money tolerance around zero inside which a closed position is neutral.
double NeutralBandMoney()
{
   if(InpNeutralCloseR <= 0.0) return 0.0;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0) return 0.0;
   return equity * EffectiveRiskPercent() / 100.0 * InpNeutralCloseR;
}

void ClearCooldownState()
{
   GVDel(GVKey("cooldown_until"));
   GVDel(GVKey("cooldown_start"));
   GVDel(GVKey("cooldown_trigger"));
   g_cooldownUntil = 0;
   g_cooldownStart = 0;
   g_cooldownTrigger = 0;
   g_inCooldown = false;
}

// Begin a stand-down anchored at the close time of the loss that triggered it.
void StartCooldown(const datetime lossTime, const int losses)
{
   datetime nowTs = TimeTradeServer();
   datetime start = lossTime;
   if(start <= 0 || start > nowTs) start = nowTs;
   datetime until = start + (datetime)InpCooldownAfterLossMin * 60;
   GVSet(GVKey("cooldown_start"), (double)start);
   GVSet(GVKey("cooldown_until"), (double)until);
   GVSet(GVKey("cooldown_trigger"), (double)losses);
   g_cooldownStart = start;
   g_cooldownUntil = until;
   g_cooldownTrigger = losses;
   g_inCooldown = (nowTs < until);
   PrintFormat("[QATS][GUARD] %d consecutive losing closes - standing down for %d minutes (until %s)",
               losses, InpCooldownAfterLossMin, TimeToString(until, TIME_DATE | TIME_MINUTES));
   PrintFormat("[QATS][COOLDOWN] state=STARTED trigger=%d losses start=%s until=%s remaining=%I64ds lossStreak restarts at 0",
               losses, TimeToString(start, TIME_DATE | TIME_SECONDS), TimeToString(until, TIME_DATE | TIME_SECONDS),
               QATS_CooldownRemaining(nowTs, until));
}

// Validate the persisted loss-streak / cooldown state and expire the timer.
// Runs on every tick; every repair and every transition is journalled once.
void UpdateCooldownState()
{
   datetime nowTs = TimeTradeServer();
   long duration = (long)InpCooldownAfterLossMin * 60;
   bool breakerOn = (InpStopAfterConsecLoss > 0 && duration > 0);

   // loss streak: a whole number, never negative
   double rawConsec = GVGet(GVKey("consec_losses"), 0.0);
   if(!MathIsValidNumber(rawConsec) || rawConsec < 0.0 || rawConsec > 100000.0)
   {
      PrintFormat("[QATS][COOLDOWN] state=REPAIRED persisted loss streak %.2f is invalid - reset to 0", rawConsec);
      rawConsec = 0.0;
      GVSet(GVKey("consec_losses"), 0.0);
   }
   g_consecLosses = (int)rawConsec;

   double rawUntil = GVGet(GVKey("cooldown_until"), 0.0);
   if(!MathIsValidNumber(rawUntil) || rawUntil <= 0.0)
   {
      if(GlobalVariableCheck(GVKey("cooldown_until")) || GlobalVariableCheck(GVKey("cooldown_start")))
         ClearCooldownState();
      g_cooldownUntil = 0; g_cooldownStart = 0; g_cooldownTrigger = 0; g_inCooldown = false;
   }
   else if(!breakerOn)
   {
      PrintFormat("[QATS][COOLDOWN] state=CLEARED the consecutive-loss breaker is disabled by input - persisted stand-down dropped");
      ClearCooldownState();
   }
   else
   {
      datetime until = (datetime)rawUntil;
      double rawStart = GVGet(GVKey("cooldown_start"), 0.0);
      datetime start = 0;
      if(MathIsValidNumber(rawStart) && rawStart > 0.0) start = (datetime)rawStart;
      int trigger = (int)GVGet(GVKey("cooldown_trigger"), 0.0);
      // a state written by an older build has no start time: derive it from the expiry
      if(start <= 0 || start > until)
      {
         start = until - (datetime)duration;
         GVSet(GVKey("cooldown_start"), (double)start);
         PrintFormat("[QATS][COOLDOWN] state=REPAIRED start time missing or after the expiry - derived start=%s from until=%s",
                     TimeToString(start, TIME_DATE | TIME_SECONDS), TimeToString(until, TIME_DATE | TIME_SECONDS));
      }
      // an expiry further away than one full configured stand-down cannot be legitimate
      if(QATS_CooldownRemaining(nowTs, until) > duration + 60)
      {
         PrintFormat("[QATS][COOLDOWN] state=REPAIRED persisted expiry %s is more than %d minutes away - clamped to one full stand-down from now",
                     TimeToString(until, TIME_DATE | TIME_SECONDS), InpCooldownAfterLossMin);
         start = nowTs;
         until = nowTs + (datetime)duration;
         GVSet(GVKey("cooldown_start"), (double)start);
         GVSet(GVKey("cooldown_until"), (double)until);
      }
      if(nowTs >= until)
      {
         PrintFormat("[QATS][COOLDOWN] state=EXPIRED trigger=%d losses start=%s until=%s - entries re-enabled, lossStreak=%d",
                     trigger, TimeToString(start, TIME_DATE | TIME_SECONDS), TimeToString(until, TIME_DATE | TIME_SECONDS),
                     g_consecLosses);
         ClearCooldownState();
      }
      else
      {
         g_cooldownStart = start;
         g_cooldownUntil = until;
         g_cooldownTrigger = trigger;
         g_inCooldown = true;
      }
   }

   // a streak at or over the threshold with no stand-down running (threshold lowered
   // by the operator, or state restored): the protection applies now
   if(breakerOn && !g_inCooldown && g_consecLosses >= InpStopAfterConsecLoss)
   {
      StartCooldown(nowTs, g_consecLosses);
      GVSet(GVKey("consec_losses"), 0.0);
      g_consecLosses = 0;
   }
}

void PrintStats(const string scope)
{
   PrintFormat("[QATS][STATS] scope=%s BUY detected=%d eligibleBars=%d approved=%d executed=%d blockedBars=%d rejected=%d closed=W%d/L%d/N%d net=%+.2f | SELL detected=%d eligibleBars=%d approved=%d executed=%d blockedBars=%d rejected=%d closed=W%d/L%d/N%d net=%+.2f | conflicts=%d",
               scope,
               g_statDetected[0], g_statEligibleBars[0], g_statApproved[0], g_statExecuted[0], g_statBlockedBars[0],
               g_statRejected[0], g_statWins[0], g_statLosses[0], g_statNeutral[0], g_statNet[0],
               g_statDetected[1], g_statEligibleBars[1], g_statApproved[1], g_statExecuted[1], g_statBlockedBars[1],
               g_statRejected[1], g_statWins[1], g_statLosses[1], g_statNeutral[1], g_statNet[1],
               g_statConflicts);
}

void UpdateDailyGuards()
{
   string dk = TodayKey();
   string baseKey = GVKey("daybase_" + dk);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

   if(dk != g_statsDay)
   {
      if(g_statsDay != "") PrintStats("session-to-" + g_statsDay);
      g_statsDay = dk;
   }

   if(!GlobalVariableCheck(baseKey)) GVSet(baseKey, equity);
   g_dayBase = GVGet(baseKey, equity);
   g_dayPnL  = equity - g_dayBase;

   g_dayLocked = GlobalVariableCheck(GVKey("daylock_" + dk));
   if(!g_dayLocked && g_dayBase > 0.0)
   {
      double loss = g_dayBase - equity;
      double lossPct = loss / g_dayBase * 100.0;
      double capPct = EffectiveDailyLossPercent();
      bool hitPct   = (capPct > 0.0 && lossPct >= capPct);
      bool hitMoney = (InpMaxDailyLossMoney > 0.0 && loss >= InpMaxDailyLossMoney);
      if(hitPct || hitMoney)
      {
         GVSet(GVKey("daylock_" + dk), 1.0);
         g_dayLocked = true;
         PrintFormat("[QATS][GUARD] DAILY LOSS LIMIT HIT (loss %.2f %s | %.2f%%) - new entries LOCKED for %s",
                     loss, g_spec.profitCcy, lossPct, dk);
      }
   }

   // account drawdown from equity high-water mark (baseline PERSISTED at first sight)
   string hwmKey = GVKey("hwm");
   if(!GlobalVariableCheck(hwmKey)) GVSet(hwmKey, equity);
   double hwm = GVGet(hwmKey, equity);
   if(equity > hwm) { hwm = equity; GVSet(hwmKey, hwm); }
   g_equityHWM = hwm;
   g_accountDDPct = (hwm > 0.0) ? (hwm - equity) / hwm * 100.0 : 0.0;
   double ddCap = EffectiveDrawdownPercent();
   bool wasHalted = g_ddHalted;
   g_ddHalted = (ddCap > 0.0 && g_accountDDPct >= ddCap);
   if(g_ddHalted && !wasHalted)
      PrintFormat("[QATS][GUARD] ACCOUNT DRAWDOWN HALT: equity %.2f is %.2f%% below the high-water mark %.2f (limit %.2f%%). New entries stay halted until equity recovers above the limit or the operator resets the breakers (InpResetBreakersAtInit).",
                  equity, g_accountDDPct, hwm, ddCap);
   if(!g_ddHalted && wasHalted)
      PrintFormat("[QATS][GUARD] ACCOUNT DRAWDOWN HALT released: equity %.2f is %.2f%% below the high-water mark %.2f (limit %.2f%%)",
                  equity, g_accountDDPct, hwm, ddCap);

   g_tradesToday = (int)GVGet(GVKey("trades_" + dk), 0.0);
   UpdateCooldownState();
}

bool PositionStillOpen(const long positionId)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_IDENTIFIER) == positionId) return true;
   }
   return false;
}

int FindClosedPos(const SClosedPos &list[], const int count, const long id)
{
   for(int i = 0; i < count; i++)
      if(list[i].id == id) return i;
   return -1;
}

// Rebuild this EA's closed positions from the deal history and feed every position
// that finished since the last pass, oldest first, into the loss streak.
void ProcessClosedDeals()
{
   datetime nowTs = TimeTradeServer();
   // CR-5: the scan is bounded by the watermark of what was already counted -
   // from the time of the last counted deal minus a 6h slack, never worse than the
   // old fixed 30-day window. The ticket filter below (lastOut <= maxSeen) prevents
   // double counting regardless of the window.
   datetime wmTime = (datetime)GVGet(GVKey("last_deal_time"), 0.0);
   datetime from = (wmTime > 0) ? MathMax(wmTime - 6 * 3600, nowTs - 30 * 86400) : (nowTs - 30 * 86400);
   if(from > nowTs) from = nowTs;
   if(!HistorySelect(from, nowTs + 86400)) return;
   int total = HistoryDealsTotal();
   ulong lastSeen = (ulong)GVGet(GVKey("last_deal"), 0.0);

   SClosedPos list[];
   int count = 0;
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol) continue;
      long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      bool isIn  = (entry == DEAL_ENTRY_IN);
      bool isOut = (entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY);
      if(!isIn && !isOut) continue;
      long posId = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      if(posId <= 0) continue;
      int k = FindClosedPos(list, count, posId);
      if(k < 0)
      {
         if(count >= QATS_MAX_CLOSED_POS) continue;
         ArrayResize(list, count + 1);
         k = count;
         count++;
         list[k].id = posId;
         list[k].net = 0.0;
         list[k].lastOut = 0;
         list[k].lastOutTime = 0;
         list[k].ours = false;
         list[k].hasOut = false;
         list[k].dir = 0;
      }
      bool mine = (HistoryDealGetInteger(ticket, DEAL_MAGIC) == InpMagic);
      // ownership comes from the ENTRY deal: a manual close or a stop-out carries no magic
      if(mine) list[k].ours = true;
      if(isIn) list[k].dir = (HistoryDealGetInteger(ticket, DEAL_TYPE) == DEAL_TYPE_BUY) ? +1 : -1;
      list[k].net += HistoryDealGetDouble(ticket, DEAL_PROFIT) + HistoryDealGetDouble(ticket, DEAL_SWAP) +
                     HistoryDealGetDouble(ticket, DEAL_COMMISSION) + HistoryDealGetDouble(ticket, DEAL_FEE);
      if(isOut)
      {
         list[k].hasOut = true;
         if(ticket > list[k].lastOut)
         {
            list[k].lastOut = ticket;
            list[k].lastOutTime = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
         }
      }
   }

   double consec = GVGet(GVKey("consec_losses"), 0.0);
   if(!MathIsValidNumber(consec) || consec < 0.0) consec = 0.0;
   double band = NeutralBandMoney();
   ulong maxSeen = lastSeen;
   datetime maxOutTime = 0;
   bool changed = false;
   for(int pass = 0; pass < count; pass++)
   {
      // the oldest finished position that has not been counted yet
      int pick = -1;
      for(int i = 0; i < count; i++)
      {
         if(!list[i].ours || !list[i].hasOut || list[i].lastOut <= maxSeen) continue;
         if(PositionStillOpen(list[i].id)) continue;          // partially closed: counted when it is flat
         if(pick < 0 || list[i].lastOut < list[pick].lastOut) pick = i;
      }
      if(pick < 0) break;
      maxSeen = list[pick].lastOut;
      if(list[pick].lastOutTime > maxOutTime) maxOutTime = list[pick].lastOutTime;
      changed = true;
      GVDel(GVKey("pc_" + IntegerToString(list[pick].id)));    // position closed: drop partial-bank marker
      int outcome = QATS_ClassifyClose(list[pick].net, band);
      if(list[pick].dir != 0)
      {
         int si = SideIndex(list[pick].dir);
         g_statNet[si] += list[pick].net;
         if(outcome > 0)      g_statWins[si]++;
         else if(outcome < 0) g_statLosses[si]++;
         else                 g_statNeutral[si]++;
      }
      if(outcome < 0) consec += 1.0;
      else if(outcome > 0) consec = 0.0;
      PrintFormat("[QATS][GUARD] position %I64d %s closed %s net=%+.2f %s (neutral band %.2f) -> lossStreak=%d/%d",
                  list[pick].id, SideName(list[pick].dir),
                  (outcome > 0 ? "WIN" : (outcome < 0 ? "LOSS" : "NEUTRAL")),
                  list[pick].net, g_spec.profitCcy, band, (int)consec, InpStopAfterConsecLoss);
      if(outcome < 0 && InpStopAfterConsecLoss > 0 && consec >= (double)InpStopAfterConsecLoss)
      {
         StartCooldown(list[pick].lastOutTime, (int)consec);
         consec = 0.0;
      }
   }
   if(changed)
   {
      GVSet(GVKey("last_deal"), (double)maxSeen);
      if(maxOutTime > 0) GVSet(GVKey("last_deal_time"), (double)maxOutTime);
      GVSet(GVKey("consec_losses"), consec);
      g_consecLosses = (int)consec;
   }
}

// on attach, adopt the current history watermark so ancient deals are never re-counted
void InitDealWatermark()
{
   // CR-5: seed BOTH watermarks from one 30-day lookback (once per account/symbol/magic),
   // so an upgrade from a pre-CR-5 tree never rescans 30 days every M5 bar.
   bool needTicket = !GlobalVariableCheck(GVKey("last_deal"));
   bool needTime   = !GlobalVariableCheck(GVKey("last_deal_time"));
   if(!needTicket && !needTime) return;
   datetime from = TimeTradeServer() - 30 * 86400;
   ulong maxSeen = 0;
   datetime maxSeenTime = 0;
   if(HistorySelect(from, TimeTradeServer() + 86400))
   {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0) continue;
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol) continue;
         if(ticket > maxSeen)
         {
            maxSeen = ticket;
            maxSeenTime = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
         }
      }
   }
   if(needTicket) GVSet(GVKey("last_deal"), (double)maxSeen);
   if(needTime)   GVSet(GVKey("last_deal_time"), (double)maxSeenTime);
   PrintFormat("[QATS] deal watermark initialised at ticket %I64u time %s", maxSeen, TimeToString(maxSeenTime, TIME_DATE | TIME_SECONDS));
}

// RISK_STATUS exposure map (Phase 8): read-only snapshot of the account-side risk
// posture. Computed from live + persisted state; the guard chain enforces it, the
// journal ([QATS][RISK]) reports it, Phase 9 folds it into the ANALYSIS record.
void BuildRiskStatus(SRiskStatus &st)
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   st.equity = equity;
   st.dayPnl = g_dayPnL;
   st.dayPnlPct = (g_dayBase > 0.0) ? g_dayPnL / g_dayBase * 100.0 : 0.0;
   st.hwm = g_equityHWM;
   st.ddPct = g_accountDDPct;
   st.ddCapPct = EffectiveDrawdownPercent();
   st.ddUsedPct = (st.ddCapPct > 0.0) ? st.ddPct / st.ddCapPct * 100.0 : 0.0;
   st.consecLosses = g_consecLosses;
   st.streakMax = InpStopAfterConsecLoss;
   st.tradesToday = g_tradesToday;
   st.tradesMax = InpMaxTradesPerDay;
   st.dailyLossPct = (g_dayBase > 0.0 && equity < g_dayBase) ? (g_dayBase - equity) / g_dayBase * 100.0 : 0.0;
   st.dailyLossCapPct = EffectiveDailyLossPercent();
   st.dayLocked = g_dayLocked;
   st.ddHalted = g_ddHalted;
   st.cooldownActive = g_inCooldown || (g_cooldownUntil > TimeTradeServer());
   st.cooldownUntil = g_cooldownUntil;
   double used = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   st.marginUsedPct = (used + freeMargin > 0.0) ? used / (used + freeMargin) * 100.0 : 0.0;
}

string RiskStatusText(const SRiskStatus &st)
{
   string cooldown = (st.cooldownActive && st.cooldownUntil > 0)
                     ? ("until " + TimeToString(st.cooldownUntil, TIME_DATE | TIME_MINUTES))
                     : (st.cooldownActive ? "active" : "no");
   return StringFormat("equity=%.2f %s dayPnL=%+.2f (%+.2f%%) HWM=%.2f DD=%.2f%% (cap %.2f%%, %.0f%% used) streak=%d/%d tradesToday=%d/%d dayLoss=%.2f%% (cap %.2f%%) dayLocked=%s ddHalted=%s cooldown=%s marginUsed=%.1f%%",
                      st.equity, g_spec.profitCcy, st.dayPnl, st.dayPnlPct, st.hwm, st.ddPct, st.ddCapPct, st.ddUsedPct,
                      st.consecLosses, st.streakMax, st.tradesToday, st.tradesMax,
                      st.dailyLossPct, st.dailyLossCapPct,
                      (st.dayLocked ? "yes" : "no"), (st.ddHalted ? "yes" : "no"), cooldown,
                      st.marginUsedPct);
}

//+------------------------------------------------------------------+
//| SECTION 22 - HEARTBEAT & CHART PANEL                             |
//+------------------------------------------------------------------+
void Heartbeat()
{
   if(InpHeartbeatSeconds <= 0) return;
   datetime now = TimeTradeServer();
   if(g_lastHeartbeat != 0 && now - g_lastHeartbeat < InpHeartbeatSeconds) return;
   g_lastHeartbeat = now;
   {
      SRiskStatus risk;
      BuildRiskStatus(risk);
      PrintFormat("[QATS][RISK] %s", RiskStatusText(risk));
   }
   PrintFormat("[QATS][HB] equity=%.2f %s dayPnL=%+.2f (%.2f%%) HWM=%.2f DD=%.2f%% tradesToday=%d/%d consecLosses=%d/%d dayLocked=%s ddHalted=%s cooldown=%s spread=%.0fpts lastBUY=%d lastSELL=%d lastDir=%+d | %s",
               AccountInfoDouble(ACCOUNT_EQUITY), g_spec.profitCcy,
               g_dayPnL, (g_dayBase > 0 ? g_dayPnL / g_dayBase * 100.0 : 0.0),
               g_equityHWM, g_accountDDPct, g_tradesToday, InpMaxTradesPerDay,
               g_consecLosses, InpStopAfterConsecLoss,
               (g_dayLocked ? "YES" : "no"), (g_ddHalted ? "YES" : "no"), CooldownText(),
               (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point,
               g_lastScoreBuy, g_lastScoreSell, g_lastDir, g_lastReason);
}

void DrawPanel()
{
   string status = g_execBlocked ? "BLOCKED" : (!InpEnableTrading ? "INERT" : (InpDryRun ? "DRY RUN" : (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "ARMED (REAL)" : "ARMED (DEMO)")));
   string text = StringFormat(
      "QuantumAutonomousTradingSystem v%s | %s\nSymbol: %s | %s\nEquity: %.2f %s | Risk/trade: %.2f%% | Day P/L: %+.2f\nGuards: dayLock=%s ddHalt=%s cooldown=%s | Trades today: %d/%d | Loss streak: %d/%d\nLast analysis: BUY %d/100 | SELL %d/100 | candidate=%s | %s",
      QATS_VERSION, status, _Symbol, (g_execBlocked ? g_blockReason : "all protection checks passed"),
      AccountInfoDouble(ACCOUNT_EQUITY), g_spec.profitCcy, EffectiveRiskPercent(), g_dayPnL,
      (g_dayLocked ? "ON" : "off"), (g_ddHalted ? "ON" : "off"), (g_inCooldown ? "ON" : "off"),
      g_tradesToday, InpMaxTradesPerDay, g_consecLosses, InpStopAfterConsecLoss,
      g_lastScoreBuy, g_lastScoreSell, SideName(g_lastDir), g_lastReason);
   Comment(text);
}

//+------------------------------------------------------------------+
//| SECTION 23 - Lifecycle: OnInit / OnDeinit                        |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[QATS]====================================================");
   PrintFormat("[QATS] QuantumAutonomousTradingSystem v%s attaching to %s", QATS_VERSION, _Symbol);
   PrintFormat("[QATS][SESSION] trading windows are BROKER SERVER hours (%02d:00..%02d:00 server); broker->UTC offset input = %+d min (advisory only - the guard enforces server time; the broker's DST follows its own server clock, not this input)",
               InpSessionStartHour, InpSessionEndHour, InpBrokerUtcOffsetMinutes);
   Print("[QATS]====================================================");

   g_boundLogin = AccountInfoInteger(ACCOUNT_LOGIN);
   g_boundServer = AccountInfoString(ACCOUNT_SERVER);
   g_boundMode = AccountInfoInteger(ACCOUNT_TRADE_MODE);

   //--- 1. symbol specification (broker-provided, never assumed)
   if(!LoadSymbolSpec(g_spec))
   {
      g_execBlocked = true;
      g_blockReason = "symbol specification unavailable";
      return INIT_FAILED;   // without specs no risk math is possible; refuse to run
   }
   PrintSymbolSpec();
   // CR-3: the atomic reservation is required on EVERY symbol (the keys are
   // account + magic + symbol namespaced; XAUUSD keys keep their legacy names).
   // An account/terminal that cannot persist the reservation refuses to run.
   if(!InitSignalKeys())
   {
      Print("[QATS][FATAL] Cannot initialize persistent signal reservations; execution disabled");
      return INIT_FAILED;
   }
   if(IsXAUUSD())
      Print("[QATS][POLICY] XAUUSD: core confirmation gate + score threshold decide; EMA veto, counter-D1 restriction and classification profile are diagnostic, not entry vetoes");
   PrintFormat("[QATS][POLICY] direction: BUY and SELL are scored independently on every closed M5 bar; profile=%s (core confirmation), minimum score=%d, setup window=%d H1 bars, conflict margin=%d",
               QATS_StrategyProfileName((int)InpStrategyProfile), InpMinScore, MathMax(1, InpSetupWindowBars), InpConflictMargin);
   PrintFormat("[QATS][POLICY] weights: D1=%d H4=%d structure=%d sweep=%d displacement=%d zone=%d/%d location=%d VWAP=%d volume=%d M15=%d M5=%d (sum 100; a liquidity sweep alone never opens a trade)",
               QATS_W_BIAS_D1, QATS_W_BIAS_H4, QATS_W_STRUCTURE, QATS_W_SWEEP, QATS_W_DISPLACEMENT,
               QATS_W_ZONE_TOUCH, QATS_W_ZONE_PRESENT, QATS_W_LOCATION, QATS_W_VWAP, QATS_W_VOLUME,
               QATS_W_M15, QATS_W_M5);

   //--- 2. MANDATORY account authorization / permission protection
   string protectionReason = "";
   if(!VerifyAccountProtection(protectionReason))
   {
      g_execBlocked = true;
      g_blockReason = protectionReason;
      PrintFormat("[QATS][PROTECTION] EXECUTION BLOCKED: %s", protectionReason);
      PrintFormat("[QATS][PROTECTION] The EA stays attached for analysis only. It will NOT send orders.");
   }
   else
   {
      g_execBlocked = false;
      g_blockReason = "";
      PrintFormat("[QATS][PROTECTION] PASS: %s account authorized; terminal/EA/symbol permissions OK.",
                  (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "REAL" : "DEMO"));
   }

   if(InpResetBreakersAtInit)
   {
      if(!g_execBlocked) ResetBreakers();
      else Print("[QATS][PROTECTION] Breaker reset skipped: account is not authorized");
   }

   //--- 3. effective risk banner (what the code will ACTUALLY enforce)
   PrintFormat("[QATS][RISK] per-trade risk = %.2f%% of equity (input %.2f%%, ceiling %.2f%%, hard cap %.2f%%)",
               EffectiveRiskPercent(), InpRiskPercent, InpMaxRiskPercent, QATS_HARD_CAP_RISK_PCT);
   PrintFormat("[QATS][RISK] daily loss stop = %.2f%% (money stop %.2f) | drawdown halt = %.2f%% from equity HWM | trades/day cap = %d",
               EffectiveDailyLossPercent(), InpMaxDailyLossMoney, EffectiveDrawdownPercent(), InpMaxTradesPerDay);
   PrintFormat("[QATS][RISK] max positions = %d | consec-loss stand-down = %d (%d min) | dry run = %s | demo only = %s",
               InpMaxOpenPositions, InpStopAfterConsecLoss, InpCooldownAfterLossMin,
               (InpDryRun ? "ON" : "off"), (InpDemoOnly ? "YES" : "NO (REAL requires explicit authorization)"));
   PrintFormat("[QATS][RISK] loss streak counts closed POSITIONS net of commission/swap; neutral band = %.2f R; the daily-loss and drawdown guards read ACCOUNT equity, so other positions on this account move them",
               InpNeutralCloseR);

   //--- 4. indicator handles (native built-ins)
   g_hD1Fast  = iMA(_Symbol, PERIOD_D1, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hD1Slow  = iMA(_Symbol, PERIOD_D1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_hH4Fast  = iMA(_Symbol, PERIOD_H4, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hH4Slow  = iMA(_Symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_hH1Fast  = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hH1Slow  = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_hM15Fast = iMA(_Symbol, PERIOD_M15, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hH1Slow200 = iMA(_Symbol, PERIOD_H1, 200, 0, MODE_EMA, PRICE_CLOSE);
   g_hATRH1   = iATR(_Symbol, PERIOD_H1, InpATRPeriod);
   g_hATRM15  = iATR(_Symbol, PERIOD_M15, InpATRPeriod);
   g_hATRM5   = iATR(_Symbol, PERIOD_M5, InpATRPeriod);

   if(g_hD1Fast == INVALID_HANDLE || g_hD1Slow == INVALID_HANDLE ||
      g_hH4Fast == INVALID_HANDLE || g_hH4Slow == INVALID_HANDLE ||
      g_hH1Fast == INVALID_HANDLE || g_hH1Slow == INVALID_HANDLE ||
      g_hM15Fast == INVALID_HANDLE || g_hH1Slow200 == INVALID_HANDLE || g_hATRH1 == INVALID_HANDLE || g_hATRM15 == INVALID_HANDLE || g_hATRM5 == INVALID_HANDLE)
   {
      PrintFormat("[QATS][FATAL] Failed to create indicator handles, error=%d", GetLastError());
      ReleaseHandles();
      return INIT_FAILED;
   }

   //--- 5. trade object: magic, deviation and a filling mode this symbol supports.
   // Management can close or modify a position before the first entry of this session
   // (a restart with a position open), so the object is configured here, not lazily.
   ConfigureTrade();

   //--- 6. persisted guard state
   InitDealWatermark();
   UpdateDailyGuards();
   ProcessClosedDeals();
   PrintFormat("[QATS][COOLDOWN] state=%s at attach | lossStreak=%d/%d | cooldown=%s",
               (g_inCooldown ? "ACTIVE" : "IDLE"), g_consecLosses, InpStopAfterConsecLoss, CooldownText());

   //--- 7. sanity: probe the data pipeline once (non-fatal if not ready yet)
   SReading r;
   if(LoadReading(r))
      PrintFormat("[QATS] data pipeline OK | ATR(H1)=%.5f ATR(M15)=%.5f ATR(M5)=%.5f VWAP=%.5f", r.atrH1, r.atrM15, r.atrM5, r.vwap);
   else
      PrintFormat("[QATS] data pipeline not ready yet (normal on a cold start); entries wait for closed bars");
   double spreadNow = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point;
   if(spreadNow > (double)InpMaxSpreadPoints)
      PrintFormat("[QATS][CONFIG] current spread %.0f pts is above InpMaxSpreadPoints=%d: entries stay blocked (reason SPREAD) until it narrows. On a symbol quoted with an extra digit the limit must be scaled by 10.",
                  spreadNow, InpMaxSpreadPoints);

   PrintFormat("[QATS] attach complete | mode=%s | waiting for new M5 bars", (g_execBlocked ? "BLOCKED" : (!InpEnableTrading ? "INERT" : (InpDryRun ? "DRY RUN" : (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "LIVE ON REAL" : "LIVE ON DEMO")))));
   return INIT_SUCCEEDED;
}

void ReleaseHandles()
{
   if(g_hD1Fast != INVALID_HANDLE) IndicatorRelease(g_hD1Fast);
   if(g_hD1Slow != INVALID_HANDLE) IndicatorRelease(g_hD1Slow);
   if(g_hH4Fast != INVALID_HANDLE) IndicatorRelease(g_hH4Fast);
   if(g_hH4Slow != INVALID_HANDLE) IndicatorRelease(g_hH4Slow);
   if(g_hH1Fast != INVALID_HANDLE) IndicatorRelease(g_hH1Fast);
   if(g_hH1Slow != INVALID_HANDLE) IndicatorRelease(g_hH1Slow);
   if(g_hM15Fast != INVALID_HANDLE) IndicatorRelease(g_hM15Fast);
   if(g_hATRH1  != INVALID_HANDLE) IndicatorRelease(g_hATRH1);
   if(g_hH1Slow200 != INVALID_HANDLE) IndicatorRelease(g_hH1Slow200);
   if(g_hATRM15 != INVALID_HANDLE) IndicatorRelease(g_hATRM15);
   if(g_hATRM5  != INVALID_HANDLE) IndicatorRelease(g_hATRM5);
   g_hD1Fast = g_hD1Slow = g_hH4Fast = g_hH4Slow = g_hH1Fast = g_hH1Slow = INVALID_HANDLE;
   g_hM15Fast = g_hATRH1 = g_hATRM15 = g_hATRM5 = INVALID_HANDLE;
   g_hH1Slow200 = INVALID_HANDLE;
}

void OnDeinit(const int reason)
{
   PrintStats("session");
   ReleaseHandles();
   Comment("");
   PrintFormat("[QATS] deinit (reason=%d) - handles released, guards persisted", reason);
}

//+------------------------------------------------------------------+
//| SECTION 24 - Tick handling & the signal life cycle               |
//|   [QATS][BUY][DETECTED] / [QATS][SELL][DETECTED]  setup found    |
//|   [QATS][SIGNAL][SCORED]        both scores + outcome, per bar   |
//|   [QATS][BLOCK][REASON]         a risk guard vetoed the entry    |
//|   [QATS][EXECUTION][REJECTED]   plan / size / broker refused it  |
//|   [QATS][EXECUTION][APPROVED]   every check passed, order sent   |
//|   [QATS][EXECUTION][FILLED]     server accepted, position found  |
//+------------------------------------------------------------------+
void LogBlock(const SAnalysis &signal, const string codes, const string detail)
{
   string key = SetupId(signal.dir, signal.setupTime) + "|" + codes;
   if(key == g_lastBlockKey) return;          // the per-bar SCORED record keeps naming the block
   g_lastBlockKey = key;
   PrintFormat("[QATS][BLOCK][REASON] symbol=%s bar=%s direction=%s setup=%s score=%d reasons=%s detail=%s",
               _Symbol, TimeToString(signal.signalBar, TIME_DATE | TIME_MINUTES), SideName(signal.dir),
               SetupId(signal.dir, signal.setupTime), signal.score, codes, detail);
}

void LogRejected(const SAnalysis &signal, const string stage, const string reason)
{
   // a refusal that repeats bar after bar for the same setup (plan, size, spread) is
   // printed once; every order the SERVER refused is printed, because each was sent
   string key = SetupId(signal.dir, signal.setupTime) + "|" + stage + "|" + reason;
   bool sentToServer = (stage == "BROKER" || stage == "RESERVE");
   if(!sentToServer && key == g_lastRejectKey) return;
   g_lastRejectKey = key;
   PrintFormat("[QATS][EXECUTION][REJECTED] symbol=%s bar=%s direction=%s setup=%s score=%d stage=%s reason=%s",
               _Symbol, TimeToString(signal.signalBar, TIME_DATE | TIME_MINUTES), SideName(signal.dir),
               SetupId(signal.dir, signal.setupTime), signal.score, stage, reason);
}

// Turn one analysis into exactly one outcome, and say which.
void ProcessSignal(const SAnalysis &raw, const bool canManage)
{
   if(!raw.dataReady)
   {
      LogSignal(raw, "NO_DATA", raw.reason);
      return;
   }
   AnnounceSide(raw, raw.buy);
   AnnounceSide(raw, raw.sell);
   if(raw.buy.eligible)  g_statEligibleBars[0]++;
   if(raw.sell.eligible) g_statEligibleBars[1]++;
   if(raw.conflict)
   {
      // both sides qualified: the decision and the rule behind it, once per pair of setups
      g_statConflicts++;
      string conflictKey = SetupId(+1, raw.buy.setupTime) + "|" + SetupId(-1, raw.sell.setupTime) + "|" + raw.resolution;
      if(conflictKey != g_lastConflictKey)
      {
         g_lastConflictKey = conflictKey;
         PrintFormat("[QATS][SIGNAL][CONFLICT] symbol=%s bar=%s BUY=%d/100 (%s) SELL=%d/100 (%s) margin=%d rule=%s decision=%s",
                     _Symbol, TimeToString(raw.signalBar, TIME_DATE | TIME_MINUTES),
                     raw.buy.score, SetupId(+1, raw.buy.setupTime), raw.sell.score, SetupId(-1, raw.sell.setupTime),
                     InpConflictMargin, raw.resolution, SideName(raw.dir));
      }
   }

   if(raw.dir == 0)
   {
      // nothing tradable on this bar: name the reason for the side that came closest
      if(raw.conflict)
         LogSignal(raw, "CONFLICT", "CONFLICT_UNRESOLVED");
      else if(raw.candidate == 0)
         LogSignal(raw, "NO_SETUP", "CORE_NOT_CONFIRMED");
      else
      {
         bool corePass = (raw.candidate > 0 ? raw.buy.corePass : raw.sell.corePass);
         int veto = (raw.candidate > 0 ? raw.buy.veto : raw.sell.veto);
         if(!corePass)      LogSignal(raw, "NO_SETUP", "CORE_NOT_CONFIRMED");
         else if(veto != 0) LogSignal(raw, "VETOED", VetoName(veto));
         else               LogSignal(raw, "BELOW_MINIMUM", "SCORE_BELOW_MINIMUM");
      }
      return;
   }

   // Exit rule first, only on the bound authorized account: an eligible opposite
   // setup closes this magic's position.
   if(canManage && raw.dir != 0)
      ClosePositionOnOpposite(raw.dir);
   // a resting LIMIT belongs to the same account and the same guards: expiring,
   // invalidated and stale limits are cancelled right after the exit rule
   if(canManage && InpUseLimitEntry)
      ManagePendingOrders(raw);

   // MANDATORY RISK PROTECTION: every active guard is named.
   string codes = "", detail = "";
   if(CollectEntryBlocks(raw, codes, detail) > 0)
   {
      g_statBlockedBars[SideIndex(raw.dir)]++;
      LogBlock(raw, codes, detail);
      LogSignal(raw, "BLOCKED", codes);
      return;
   }

   // v1.21: with a LIMIT entry the order rests at the zone instead of paying the
   // market. Everything above this line - the evidence, the score, the guard
   // chain, the opposite-side exit - is exactly the same code.
   if(InpUseLimitEntry)
   {
      if(PlaceLimitOrder(raw))
      {
         LogSignal(raw, "LIMIT_PLACED", "ORDER_PLACED");
         return;
      }
      if(g_executionStage == "DRY_RUN")
      {
         LogSignal(raw, "DRY_RUN", "ORDER_NOT_SENT");
         return;
      }
      g_statRejected[SideIndex(raw.dir)]++;
      LogRejected(raw, g_executionStage, g_executionReason);
      LogSignal(raw, "NOT_PLACED", "LIMIT");
      return;
   }

   // v1.24: the SAME premium/discount protection on MARKET entries. The limit path
   // enforces it at the zone price (InpLimitNeedPD); here it enforces on the live
   // quote (ask for BUY / bid for SELL). SELL premium / BUY discount - never
   // relaxed; a high-scoring setup that fails premium/discount is blocked and
   // journalled, never re-routed silently.
   if(InpPDEnforceMarket)
   {
      double px = (raw.dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      string why = "";
      if(!PdPriceOnSide(raw.pdSelected, raw.pdEq, raw.pdStatus, raw.dir, px, "PD_MARKET", why))
      {
         g_statBlockedBars[SideIndex(raw.dir)]++;
         LogSignal(raw, "BLOCKED", "PD_MARKET");
         PrintFormat("[QATS][PD] MARKET_BLOCKED direction=%s bar=%s price=%s reason=%s",
                     SideName(raw.dir), TimeToString(raw.signalBar, TIME_DATE | TIME_MINUTES),
                     PriceText(px), why);
         return;
      }
   }

   SAnalysis plan;
   if(!BuildTradePlan(raw, plan))
   {
      g_statRejected[SideIndex(raw.dir)]++;
      LogRejected(raw, "PLAN", g_executionReason);
      LogSignal(raw, "REJECTED", "PLAN");
      return;
   }
   bool accepted = ExecuteSignal(plan);
   if(accepted)
   {
      LogSignal(raw, "EXECUTED", "ORDER_FILLED");
      return;
   }
   if(g_executionStage == "DRY_RUN")
   {
      LogSignal(raw, "DRY_RUN", "ORDER_NOT_SENT");
      return;
   }
   g_statRejected[SideIndex(raw.dir)]++;
   LogRejected(raw, g_executionStage, g_executionReason);
   LogSignal(raw, "REJECTED", g_executionStage);
}

void OnTick()
{
   bool sameAccount = BoundAccountActive();
   if(sameAccount) UpdateDailyGuards();
   // Management and retries can send orders too; never run them on an
   // unauthorized/account-switched terminal, or while inert / in dry run.
   string managementReason = "";
   bool canManage = !g_execBlocked && InpEnableTrading && !InpDryRun && VerifyAccountProtection(managementReason);
   if(canManage)
   {
      ManagePositions();
      ProcessPendingRetry();
   }

   bool newBar = false;
   datetime barTime = iTime(_Symbol, PERIOD_M5, 0);
   if(barTime != g_lastBarM5)
   {
      g_lastBarM5 = barTime;
      newBar = true;
   }

   if(newBar)
   {
      if(sameAccount) ProcessClosedDeals();
      SAnalysis raw = AnalyzeMarket();
      g_lastReason    = raw.reason;
      g_lastScore     = raw.score;
      g_lastScoreBuy  = raw.buy.score;
      g_lastScoreSell = raw.sell.score;
      g_lastDir       = raw.candidate;
      // Every analysis ends in one explicit, journalled outcome.
      ProcessSignal(raw, canManage);
   }

   Heartbeat();
   DrawPanel();
}

//+------------------------------------------------------------------+
//| SECTION 25 - Trade transaction log (execution audit trail)       |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   ulong dealTicket = trans.deal;
   // the terminal can deliver the same deal more than once
   if(dealTicket == 0 || dealTicket == g_lastLoggedDeal) return;
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   long magic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);
   long dtype = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   bool closing = (dtype == DEAL_ENTRY_OUT || dtype == DEAL_ENTRY_OUT_BY);
   if(magic != InpMagic && !closing) return;
   g_lastLoggedDeal = dealTicket;
   if(magic == InpMagic)
   {
      PrintFormat("[QATS][DEAL] ticket=%I64u entry=%I64d symbol=%s type=%I64u volume=%.2f price=%.5f profit=%.2f",
                  dealTicket, dtype,
                  HistoryDealGetString(dealTicket, DEAL_SYMBOL),
                  (ulong)HistoryDealGetInteger(dealTicket, DEAL_TYPE),
                  HistoryDealGetDouble(dealTicket, DEAL_VOLUME),
                  HistoryDealGetDouble(dealTicket, DEAL_PRICE),
                  HistoryDealGetDouble(dealTicket, DEAL_PROFIT));
      // v1.21 LIMIT entry: the daily cap counts FILLED orders only. A placement or
      // a cancellation produces no DEAL_ENTRY_IN deal and therefore never counts.
      // The market path increments in ExecuteSignal, so it must NOT increment here.
      if(InpUseLimitEntry && dtype == DEAL_ENTRY_IN)
      {
         // the setup that produced this fill is spent now, at the FILL - never at
         // the placement - so a cancelled limit leaves the setup tradable
         int fillDir = ((long)HistoryDealGetInteger(dealTicket, DEAL_TYPE) == DEAL_TYPE_BUY) ? +1 : -1;
         double fillSetup = GVGet(GVKey(fillDir > 0 ? "limit_setup_buy" : "limit_setup_sell"), 0.0);
         if(fillSetup > 0.0) MarkSetupTraded(fillDir, (datetime)fillSetup);
         string limitDay = TodayKey();
         int limitPersisted = (int)GVGet(GVKey("trades_" + limitDay), (double)g_tradesToday);
         int limitCount = MathMax(limitPersisted, g_tradesToday) + 1;
         GVSet(GVKey("trades_" + limitDay), (double)limitCount);
         g_tradesToday = limitCount;
         PrintFormat("%s FILLED entry=%s setup=%s deal=%I64u price=%s volume=%.2f - daily trade counter %d/%d (filled orders only)",
                     QATS_LIMIT_PREFIX, SideName(fillDir), SetupId(fillDir, (datetime)fillSetup),
                     dealTicket, PriceText(HistoryDealGetDouble(dealTicket, DEAL_PRICE)),
                     HistoryDealGetDouble(dealTicket, DEAL_VOLUME), g_tradesToday, InpMaxTradesPerDay);
      }
   }
   // a closing deal updates the loss streak and the cooldown now, not at the next M5 bar
   if(closing && BoundAccountActive())
   {
      ProcessClosedDeals();
      UpdateCooldownState();
   }
}
//+------------------------------------------------------------------+
