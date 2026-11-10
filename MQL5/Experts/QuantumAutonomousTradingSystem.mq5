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
//|  H1 structure -> liquidity -> sweep -> displacement -> MSS/BOS ->|
//|  order block / fair value gap -> premium/discount -> M15         |
//|  confirmation -> M5 entry trigger), scores the confluence, and   |
//|  executes REAL market orders with server-side SL and TP on a     |
//|  verified DEMO account via CTrade. Every position is sized from  |
//|  the ACCOUNT'S CURRENT EQUITY, never from a fixed balance.       |
//|                                                                  |
//|  DEMO-ONLY ENFORCEMENT (MANDATORY)                               |
//|  ---------------------------------                               |
//|  - ACCOUNT_TRADE_MODE must be ACCOUNT_TRADE_MODE_DEMO.           |
//|  - REAL and CONTEST accounts are REFUSED; the EA stays on the    |
//|    chart but is permanently execution-blocked.                    |
//|  - If the account mode cannot be verified, execution is BLOCKED. |
//|  - Terminal, EA and symbol trade permissions are verified every  |
//|    entry decision; broker stops/freeze levels are respected.     |
//|  - There is NO input that switches this EA to a real account.    |
//|                                                                  |
//|  WHAT IT WILL NOT DO                                             |
//|  -------------------                                             |
//|  - No martingale. No grid. No averaging down. No widening stops. |
//|  - No trade without a stop loss. No fixed account size.          |
//|  - No decisions on forming candles: every structural decision    |
//|    uses CLOSED bars only (shift >= 1). No look-ahead bias.       |
//|                                                                  |
//|  SETUP                                                           |
//|  ----                                                            |
//|  1. Copy this ONE file to MQL5\Experts\ and press F7 in          |
//|     MetaEditor. Zero errors / zero warnings expected.            |
//|  2. Attach to the symbol chart you want to trade (any timeframe; |
//|     analysis always runs on D1/H4/H1/M15/M5 internally).          |
//|  3. Enable Algo Trading in the terminal toolbar.                 |
//|  4. Read the [QATS] journal lines at attach: account mode,       |
//|     symbol specification, risk model and guard state are printed |
//|     there. If any protection check fails the EA says so loudly   |
//|     and refuses to trade.                                        |
//|                                                                  |
//|  v1.00 - consolidated production build (2026-11-09).             |
//+------------------------------------------------------------------+
#property copyright "KLJ / Quantum"
#property version   "1.11"
#property description "Autonomous SMC trading EA. DEMO-only execution enforced. Standalone: no external dependencies."
#property description "Trades the chart symbol with dynamic equity-risk sizing and full protection guards."

#include <Trade/Trade.mqh>

#define QATS_GV_PREFIX   "QATS_"
#define QATS_MAX_SWINGS  64
#define QATS_HARD_CAP_RISK_PCT   2.0    // absolute per-trade risk ceiling, % of equity
#define QATS_HARD_CAP_DAILY_PCT  5.0    // absolute daily-loss ceiling, % of baseline
#define QATS_HARD_CAP_DD_PCT     15.0   // absolute drawdown ceiling, % from high-water mark
#define QATS_VERSION            "1.11"

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

//--- 1. switches -------------------------------------------------------
// v6.6.21 unified signal execution profile. QATS computes its own confluence
// score, so it also needs its own ceiling: STRICT keeps only STRONG, BALANCED
// adds MODERATE, PERMISSIVE adds WEAK. Applied in ExecuteSignal() BEFORE any
// sizing, so a refused class never reaches CalcPositionVolume().
input ENUM_SIGNAL_EXECUTION_PROFILE InpSignalExecutionProfile = SIGNAL_PROFILE_PERMISSIVE; // classification ceiling for entries (PERMISSIVE = all classes)
input bool     InpEnableTrading        = true;    // MASTER SWITCH: false = never sends an order
input bool     InpDryRun               = false;   // true = log the order it would send, send nothing
input bool     InpDemoOnly             = true;    // refuse any non-DEMO account (mandatory protection)
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
input int      InpStopAfterConsecLoss  = 3;       // stand down after this many losing closes in a row
input int      InpCooldownAfterLossMin = 60;      // minutes to stand down after the loss threshold is hit
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
input int      InpSwingLookback        = 120;     // H1 bars scanned for swings / dealing range
input int      InpSwingK               = 2;       // fractal wing (bars each side), closed bars only
input double   InpDisplaceATR          = 0.8;     // displacement: body >= this x H1 ATR
input double   InpDisplaceBodyRatio    = 0.65;    // ... or body/range >= this with range >= 1.3 x ATR
input double   InpLiquidityToleranceATR= 0.10;    // equal-level tolerance as fraction of H1 ATR
input int      InpMinScore             = 65;      // minimum confluence score (0-100) to take a trade
input bool     InpUseEMAAlignmentVeto  = true;    // block when D1 AND H4 both oppose the direction
input bool     InpAllowCounterBias     = false;   // true = trade counter-D1-bias setups (score penalty only)
input int      InpATRPeriod            = 14;      // ATR period (H1 for structure/stops context, M5 for stop distance)

//--- 5. position management ---------------------------------------------
input double   InpBreakEvenAtR         = 1.0;     // move SL to entry after +1R (0 = off); one direction only
input double   InpPartialCloseAtR      = 1.5;     // close InpPartialClosePercent at this R (0 = off)
input double   InpPartialClosePercent  = 50.0;    // percent of the position volume banked at that R
input bool     InpCloseOnOpposite      = true;    // close this magic's position on an opposite signal

//--- 6. diagnostics -----------------------------------------------------
input int      InpHeartbeatSeconds     = 300;     // diagnostic journal line every N seconds (0 = off)
input bool     InpVerbose              = true;    // print every skipped signal and why

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

//--- internal structures -------------------------------------------------
struct SSwing
{
   double price;
   int    shift;     // bar shift on the analysed timeframe (0 = forming bar; we use >=1)
   bool   isHigh;
};

struct SLiquidityPool
{
   double price;
   string kind;      // "PDH","PDL","EQH","EQL","PWH","PWL"
   int    shift;     // where the level was formed (bigger = older)
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
   double h1Fast, h1Slow, h1Close;
   double m15Fast, m15Close, m15Open;
   double atrH1, atrM5;
   double vwap;
   double volM5Last, volM5Avg;
   bool   ready;
};

struct SAnalysis       // complete result of one analysis pass
{
   int      dir;            // +1 buy, -1 sell, 0 stand aside
   int      score;          // 0..100 confluence score
   int      d1Bias;         // +1/-1/0
   int      h4Bias;         // +1/-1/0
   int      h1Struct;       // +1 bullish break / -1 bearish break / 0 undecided
   int      sweepBar;       // H1 shift of the sweep bar (-1 none)
   string   sweepKind;      // "BULL_SWEEP","BEAR_SWEEP",""
   bool     displaced;
   bool     hasOB;
   bool     hasFVG;
   SZone    ob;
   SZone    fvg;
   double   dealPos;        // 0..1 location inside the dealing range (0 = range low)
   double   entry;
   double   sl;
   double   tp;
   double   stopDist;
   string   tpSource;       // "LIQUIDITY","RR"
   string   reason;         // human readable decision path for the journal
   bool     zoneTouched;    // price inside/near the entry zone now
   bool     triggerM5;      // M5 closed-bar trigger candle present
   bool     confirmM15;     // M15 closed candle confirms direction
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
datetime    g_cooldownUntil    = 0;
double      g_dayBase          = 0.0;
double      g_dayPnL           = 0.0;
double      g_equityHWM        = 0.0;
double      g_accountDDPct     = 0.0;
int         g_tradesToday      = 0;
int         g_consecLosses     = 0;
bool        g_dayLocked        = false;
bool        g_ddHalted         = false;
bool        g_inCooldown       = false;
bool        g_execBlocked      = false;   // set when ANY protection check fails
string      g_blockReason      = "";
int         g_lastScore        = 0;
int         g_lastDir          = 0;
string      g_lastReason       = "";
ulong       g_pendingRetryAt   = 0;        // 0 = no pending retry
int         g_pendingRetries   = 0;
int         g_pendingDir       = 0;
double      g_pendingEntry     = 0.0;
double      g_pendingSL        = 0.0;
double      g_pendingTP        = 0.0;

int         g_hD1Fast = INVALID_HANDLE, g_hD1Slow = INVALID_HANDLE;
int         g_hH4Fast = INVALID_HANDLE, g_hH4Slow = INVALID_HANDLE;
int         g_hH1Fast = INVALID_HANDLE, g_hH1Slow = INVALID_HANDLE;
int         g_hM15Fast= INVALID_HANDLE;
int         g_hATRH1  = INVALID_HANDLE, g_hATRM5  = INVALID_HANDLE;

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
   spec.name = _Symbol;
   if(!SymbolSelect(_Symbol, true))
   {
      PrintFormat("[QATS][FATAL] SymbolSelect(%s) failed, error=%d", _Symbol, GetLastError());
      return false;
   }
   spec.digits       = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   spec.point        = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   spec.tickSize     = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   spec.tickValue    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   spec.contractSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   spec.volMin       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   spec.volMax       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   spec.volStep      = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   spec.volLimit     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT);
   spec.stopsLevel   = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   spec.freezeLevel  = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   spec.tradeMode    = (long)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   spec.fillingMode  = (long)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   spec.tradeExec    = (long)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_EXEMODE);
   spec.profitCcy    = AccountInfoString(ACCOUNT_CURRENCY);
   spec.marginCcy    = AccountInfoString(ACCOUNT_CURRENCY);

   bool ok = spec.point > 0.0 && spec.tickSize > 0.0 && spec.tickValue > 0.0 &&
             spec.volMin > 0.0 && spec.volMax >= spec.volMin && spec.volStep > 0.0;
   if(!ok)
   {
      PrintFormat("[QATS][FATAL] Incomplete symbol specification for %s (point=%.10f tickSize=%.10f tickValue=%.5f volMin=%.2f volMax=%.2f volStep=%.2f)",
                  _Symbol, spec.point, spec.tickSize, spec.tickValue, spec.volMin, spec.volMax, spec.volStep);
      return false;
   }
   spec.ok = true;
   return true;
}

void PrintSymbolSpec()
{
   Print("[QATS]==================== SYMBOL SPECIFICATION ====================");
   PrintFormat("[QATS] Symbol=%s digits=%d point=%.10f tickSize=%.10f tickValue=%.5f contractSize=%.2f",
               g_spec.name, g_spec.digits, g_spec.point, g_spec.tickSize, g_spec.tickValue, g_spec.contractSize);
   PrintFormat("[QATS] Volume: min=%.2f max=%.2f step=%.2f limit=%.8f",
               g_spec.volMin, g_spec.volMax, g_spec.volStep, g_spec.volLimit);
   PrintFormat("[QATS] Stops level=%d pts | Freeze level=%d pts | TradeMode=%I64d (FULL=4) | Filling=%I64d | ExecMode=%I64d",
               g_spec.stopsLevel, g_spec.freezeLevel, g_spec.tradeMode, g_spec.fillingMode, g_spec.tradeExec);
   PrintFormat("[QATS] Account ccy=%s leverage=1:%I64d", g_spec.profitCcy, AccountInfoInteger(ACCOUNT_LEVERAGE));
}

//+------------------------------------------------------------------+
//| SECTION 9 - ACCOUNT SNAPSHOT / MANDATORY DEMO GUARD              |
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
   if(InpDemoOnly && mode != ACCOUNT_TRADE_MODE_DEMO)
   {
      reason = (mode == ACCOUNT_TRADE_MODE_REAL)
               ? "REAL account detected - execution REFUSED (DEMO only)"
               : "CONTEST account detected - execution REFUSED (DEMO only)";
      return false;
   }
   // terminal permission to trade from MQL5
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      reason = "terminal Algo Trading is DISABLED";
      return false;
   }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
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
   ok = BufValue(g_hM15Fast, 1, r.m15Fast)&& ok;
   ok = BufValue(g_hATRH1, 1, r.atrH1)    && ok;
   ok = BufValue(g_hATRM5, 1, r.atrM5)    && ok;
   r.d1Close = iClose(_Symbol, PERIOD_D1, 1);
   r.h4Close = iClose(_Symbol, PERIOD_H4, 1);
   r.h1Close = iClose(_Symbol, PERIOD_H1, 1);
   r.m15Close= iClose(_Symbol, PERIOD_M15, 1);
   r.m15Open = iOpen(_Symbol, PERIOD_M15, 1);
   r.vwap    = SessionVWAP(_Symbol);
   r.volM5Last = (double)iVolume(_Symbol, PERIOD_M5, 1);
   r.volM5Avg  = SmaVolume(_Symbol, PERIOD_M5, 1, 20);
   r.ready = ok && r.atrH1 > 0.0 && r.atrM5 > 0.0 && iBars(_Symbol, PERIOD_M5) > 30;
   return r.ready;
}

int BiasFrom(const double close, const double fast, const double slow)
{
   if(close > fast && fast > slow) return +1;
   if(close < fast && fast < slow) return -1;
   return 0;
}

//+------------------------------------------------------------------+
//| SECTION 11 - MARKET STRUCTURE ENGINE (closed bars only)          |
//+------------------------------------------------------------------+
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
      double ref = wantHigh ? iHigh(symbol, tf, s) : iLow(symbol, tf, s);
      bool ok = true;
      for(int j = 1; j <= k; j++)
      {
         double leftPrice  = wantHigh ? iHigh(symbol, tf, s - j) : iLow(symbol, tf, s - j);
         double rightPrice = wantHigh ? iHigh(symbol, tf, s + j) : iLow(symbol, tf, s + j);
         if(wantHigh) { if(ref <= leftPrice || ref <= rightPrice) { ok = false; break; } }
         else         { if(ref >= leftPrice || ref >= rightPrice) { ok = false; break; } }
      }
      if(!ok) continue;
      int n = ArraySize(swings);
      if(n >= QATS_MAX_SWINGS) break;
      ArrayResize(swings, n + 1);
      swings[n].price  = ref;
      swings[n].shift  = s;
      swings[n].isHigh = wantHigh;
   }
   return ArraySize(swings);
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

// dealing range position for the last CLOSED price: 0 = range low, 1 = range high
double DealingRangePosition(const string symbol, const ENUM_TIMEFRAMES tf, const int lookback)
{
   double hh = 0.0, ll = 0.0;
   if(!HighestHigh(symbol, tf, 1, lookback, hh)) return 0.5;
   if(!LowestLow(symbol, tf, 1, lookback, ll))   return 0.5;
   double range = hh - ll;
   if(range <= 0.0) return 0.5;
   double close1 = iClose(symbol, tf, 1);
   double pos = (close1 - ll) / range;
   if(pos < 0.0) pos = 0.0;
   if(pos > 1.0) pos = 1.0;
   return pos;
}

//+------------------------------------------------------------------+
//| SECTION 12 - LIQUIDITY MAPPING ENGINE                            |
//| Pools: prior day high/low, prior week high/low, equal highs/lows |
//+------------------------------------------------------------------+
int BuildLiquidityPools(const string symbol, const SSwing &highs[], const SSwing &lows[],
                        const double atr, SLiquidityPool &pools[])
{
   ArrayResize(pools, 0);
   // prior day levels
   double pdh = iHigh(symbol, PERIOD_D1, 1);
   double pdl = iLow(symbol, PERIOD_D1, 1);
   int n = 0;
   if(pdh > 0.0)
   {
      ArrayResize(pools, n + 1); pools[n].price = pdh; pools[n].kind = "PDH"; pools[n].shift = 1; n++;
   }
   if(pdl > 0.0)
   {
      ArrayResize(pools, n + 1); pools[n].price = pdl; pools[n].kind = "PDL"; pools[n].shift = 1; n++;
   }
   // prior week levels
   double pwh = iHigh(symbol, PERIOD_W1, 1);
   double pwl = iLow(symbol, PERIOD_W1, 1);
   if(pwh > 0.0)
   {
      ArrayResize(pools, n + 1); pools[n].price = pwh; pools[n].kind = "PWH"; pools[n].shift = 1; n++;
   }
   if(pwl > 0.0)
   {
      ArrayResize(pools, n + 1); pools[n].price = pwl; pools[n].kind = "PWL"; pools[n].shift = 1; n++;
   }
   // equal highs / equal lows (tolerance as fraction of ATR)
   double tol = MathMax(atr * InpLiquidityToleranceATR, _Point * 2);
   int nh = ArraySize(highs), nl = ArraySize(lows);
   for(int i = 0; i < nh - 1; i++)
      for(int j = i + 1; j < nh; j++)
         if(MathAbs(highs[i].price - highs[j].price) <= tol)
         {
            ArrayResize(pools, n + 1);
            pools[n].price = (highs[i].price + highs[j].price) / 2.0;
            pools[n].kind  = "EQH";
            pools[n].shift = MathMin(highs[i].shift, highs[j].shift);
            n++;
            break;
         }
   for(int i = 0; i < nl - 1; i++)
      for(int j = i + 1; j < nl; j++)
         if(MathAbs(lows[i].price - lows[j].price) <= tol)
         {
            ArrayResize(pools, n + 1);
            pools[n].price = (lows[i].price + lows[j].price) / 2.0;
            pools[n].kind  = "EQL";
            pools[n].shift = MathMin(lows[i].shift, lows[j].shift);
            n++;
            break;
         }
   return n;
}

// a sweep = a closed bar trading THROUGH a pool and closing back INSIDE it
bool DetectSweep(const string symbol, const ENUM_TIMEFRAMES tf, const bool wantBull,
                 const SSwing &highs[], const SSwing &lows[], const SLiquidityPool &pools[],
                 int &barOut)
{
   barOut = -1;
   for(int s = 1; s <= 4; s++)
   {
      double lo = iLow(symbol, tf, s);
      double hi = iHigh(symbol, tf, s);
      double cl = iClose(symbol, tf, s);
      if(wantBull)
      {
         // swept a swing low (strictly older than bar s)
         for(int j = 0; j < ArraySize(lows); j++)
         {
            if(lows[j].shift <= s) continue;
            if(lo < lows[j].price && cl > lows[j].price)
            {
               barOut = s; return true;
            }
         }
         // swept a liquidity pool below (PDL / PWL / EQL)
         for(int j = 0; j < ArraySize(pools); j++)
         {
            if(pools[j].kind == "PDL" || pools[j].kind == "PWL" || pools[j].kind == "EQL")
               if(lo < pools[j].price && cl > pools[j].price)
               {
                  barOut = s; return true;
               }
         }
      }
      else
      {
         for(int j = 0; j < ArraySize(highs); j++)
         {
            if(highs[j].shift <= s) continue;
            if(hi > highs[j].price && cl < highs[j].price)
            {
               barOut = s; return true;
            }
         }
         for(int j = 0; j < ArraySize(pools); j++)
         {
            if(pools[j].kind == "PDH" || pools[j].kind == "PWH" || pools[j].kind == "EQH")
               if(hi > pools[j].price && cl < pools[j].price)
               {
                  barOut = s; return true;
               }
         }
      }
   }
   return false;
}

// displacement = a strong directional closed bar (impulse) near the sweep
bool DetectDisplacement(const string symbol, const ENUM_TIMEFRAMES tf, const bool wantBull,
                        const double atr, int &barOut)
{
   barOut = -1;
   for(int s = 1; s <= 4; s++)
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
//| SECTION 15 - ANALYSIS PIPELINE & CONFLUENCE SCORING              |
//+------------------------------------------------------------------+
SAnalysis AnalyzeMarket()
{
   SAnalysis a;
   a.dir = 0; a.score = 0; a.d1Bias = 0; a.h4Bias = 0; a.h1Struct = 0;
   a.sweepBar = -1; a.sweepKind = ""; a.displaced = false;
   a.hasOB = false; a.hasFVG = false;
   a.dealPos = DealingRangePosition(_Symbol, PERIOD_H1, InpSwingLookback);
   a.entry = 0.0; a.sl = 0.0; a.tp = 0.0; a.stopDist = 0.0;
   a.tpSource = ""; a.reason = ""; a.zoneTouched = false;
   a.triggerM5 = false; a.confirmM15 = false;
   a.ob.found = false; a.fvg.found = false;

   SReading r;
   if(!LoadReading(r))
   {
      a.reason = "MARKET_DATA_NOT_READY";
      return a;
   }

   // D1 bias and H4 context
   a.d1Bias = BiasFrom(r.d1Close, r.d1Fast, r.d1Slow);
   a.h4Bias = BiasFrom(r.h4Close, r.h4Fast, r.h4Slow);

   // H1 structure: most recent confirmed swing high/low, break by closed close
   SSwing highs[], lows[];
   int nh = FindSwings(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, highs, true);
   int nl = FindSwings(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, lows, false);
   double h1Close1 = r.h1Close;
   if(nh > 0 && h1Close1 > highs[0].price) a.h1Struct = +1;
   else if(nl > 0 && h1Close1 < lows[0].price) a.h1Struct = -1;
   else a.h1Struct = 0;

   // liquidity map
   SLiquidityPool pools[];
   BuildLiquidityPools(_Symbol, highs, lows, r.atrH1, pools);

   // sweep on either side (closed bars only); bull and bear tracked separately
   int sweepBarBull = -1, sweepBarBear = -1;
   bool sweepBull = DetectSweep(_Symbol, PERIOD_H1, true,  highs, lows, pools, sweepBarBull);
   bool sweepBear = DetectSweep(_Symbol, PERIOD_H1, false, highs, lows, pools, sweepBarBear);

   // pick the setup direction: the side with an active sweep wins;
   // with no sweep, fall back to the dominant structure/bias alignment
   int dir = 0;
   if(sweepBull && !sweepBear)      dir = +1;
   else if(sweepBear && !sweepBull) dir = -1;
   else if(a.h1Struct != 0 && a.h4Bias != 0 && ((a.h1Struct > 0) == (a.h4Bias > 0))) dir = a.h1Struct;
   else if(a.d1Bias != 0)           dir = a.d1Bias;
   else if(a.h4Bias != 0)           dir = a.h4Bias;

   // hard alignment veto: D1 and H4 both explicitly opposed
   if(InpUseEMAAlignmentVeto && dir != 0 && a.d1Bias == -dir && a.h4Bias == -dir)
      dir = 0;

   // counter-bias control
   if(!InpAllowCounterBias && dir != 0 && a.d1Bias != 0 && a.d1Bias == -dir)
      dir = 0;

   if(dir != 0)
   {
      a.dir = dir;
      if(dir > 0 && sweepBull)      { a.sweepBar = sweepBarBull; a.sweepKind = "BULL_SWEEP"; }
      else if(dir < 0 && sweepBear) { a.sweepBar = sweepBarBear; a.sweepKind = "BEAR_SWEEP"; }
      else                          { a.sweepBar = -1; }

      // displacement
      int dispBar = -1;
      a.displaced = DetectDisplacement(_Symbol, PERIOD_H1, dir > 0, r.atrH1, dispBar);

      // order block / FVG around the impulse
      int impulse = (a.sweepBar > 0) ? a.sweepBar : ((dispBar > 0) ? dispBar : 1);
      a.hasOB  = FindOrderBlock(_Symbol, PERIOD_H1, dir > 0, impulse, 12, a.ob);
      a.hasFVG = FindFVG(_Symbol, PERIOD_H1, dir > 0, MathMax(1, impulse - 1), a.fvg);
      a.zoneTouched = (PriceNearZone(_Symbol, a.ob, r.atrH1, 0.30) ||
                       PriceNearZone(_Symbol, a.fvg, r.atrH1, 0.30));
      a.confirmM15 = M15Confirms(r, dir);
      a.triggerM5  = M5Trigger(_Symbol, dir);

      // ---- confluence score (0..100) ----
      int score = 0;
      if(a.d1Bias == dir)                 score += 20;
      if(a.h4Bias == dir)                 score += 15;
      if(a.h1Struct == dir)               score += 20;
      else if(a.h1Struct == 0)            score += 10;
      if(a.sweepBar > 0)                  score += 15;
      if(a.displaced)                     score += 10;
      if(a.zoneTouched)                   score += 10;
      else if(a.hasOB || a.hasFVG)        score += 5;
      if((dir > 0 && a.dealPos < 0.5) || (dir < 0 && a.dealPos > 0.5)) score += 5;
      if(r.volM5Avg > 0.0 && r.volM5Last > 1.2 * r.volM5Avg)           score += 5;
      double pxNow = iClose(_Symbol, PERIOD_M5, 1);
      if((dir > 0 && pxNow > r.vwap) || (dir < 0 && pxNow < r.vwap))    score += 5;
      if(a.confirmM15)                    score += 5;
      if(a.triggerM5)                     score += 5;
      if(score > 100) score = 100;
      a.score = score;
   }
   else
   {
      a.dir = 0;
      a.score = 0;
   }

   // reason line for the journal
   a.reason = StringFormat(
      "D1=%+d H4=%+d H1=%+d sweep=%s disp=%s OB=%s FVG=%s zoneTouch=%s P/D=%.2f VWAP=%.5f M15=%s M5=%s",
      a.d1Bias, a.h4Bias, a.h1Struct,
      (a.sweepKind == "" ? "none" : a.sweepKind),
      (a.displaced ? "yes" : "no"),
      (a.hasOB ? "yes" : "no"),
      (a.hasFVG ? "yes" : "no"),
      (a.zoneTouched ? "yes" : "no"),
      a.dealPos,
      r.vwap,
      (a.confirmM15 ? "yes" : "no"),
      (a.triggerM5 ? "yes" : "no"));
   return a;
}

//+------------------------------------------------------------------+
//| SECTION 16 - TRADE PLAN (entry / SL / TP / RR)                   |
//+------------------------------------------------------------------+
bool BuildTradePlan(const SAnalysis &in, SAnalysis &out)
{
   out = in;
   if(out.dir == 0) return false;

   double atr = 0.0, atrH1 = 0.0;
   if(!BufValue(g_hATRM5, 1, atr)) return false;
   if(!BufValue(g_hATRH1, 1, atrH1)) return false;
   if(atr <= 0.0 || atrH1 <= 0.0) return false;

   double point = g_spec.point;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double entry = (out.dir > 0) ? ask : bid;

   //--- stop-loss: the WIDER of (ATR-based) and (structure-based), plus a buffer
   double atrStop = 1.5 * atr;
   double structStop = 0.0;
   if(out.dir > 0)
   {
      // below the lowest low of the last 3 M5 bars and below the sweep low region
      double ll;
      if(LowestLow(_Symbol, PERIOD_M5, 1, 3, ll)) structStop = entry - ll;
   }
   else
   {
      double hh;
      if(HighestHigh(_Symbol, PERIOD_M5, 1, 3, hh)) structStop = hh - entry;
   }
   double stopDist = MathMax(atrStop, structStop > 0.0 ? structStop : atrStop);
   // buffer: one broker stop-level beyond, so the broker never rejects it
   double stopsBuf = (double)MathMax(g_spec.stopsLevel, 1) * point;
   stopDist += stopsBuf;

   double sl = (out.dir > 0) ? entry - stopDist : entry + stopDist;

   //--- validate against integer stop inputs
   double minStopPts = MathMax(MathMax((double)InpMinStopPoints, (double)g_spec.stopsLevel), 1.0) * point;
   double maxStopPts = (double)InpMaxStopPoints * point;
   if(stopDist < minStopPts)
   {
      stopDist = minStopPts;
      sl = (out.dir > 0) ? entry - stopDist : entry + stopDist;
   }
   if(stopDist > maxStopPts)
   {
      PrintFormat("[QATS][PLAN] stop too wide %.5f (max %.5f) - trade refused", stopDist, maxStopPts);
      return false;
   }

   //--- take-profit: nearest opposing liquidity if it pays >= InpMinRR, else RR multiple
   double tp = 0.0;
   string tpSource = "RR";
   double bestTarget = 0.0;
   if(out.dir > 0)
   {
      double hh;
      if(HighestHigh(_Symbol, PERIOD_H1, 1, InpSwingLookback, hh) && hh > entry) bestTarget = hh;
   }
   else
   {
      double ll;
      if(LowestLow(_Symbol, PERIOD_H1, 1, InpSwingLookback, ll) && ll < entry) bestTarget = ll;
   }
   if(bestTarget > 0.0)
   {
      double reward = MathAbs(bestTarget - entry);
      if(reward / stopDist >= InpMinRR)
      {
         tp = bestTarget;
         tpSource = "LIQUIDITY";
      }
   }
   if(tp == 0.0)
   {
      tp = (out.dir > 0) ? entry + stopDist * InpRewardRisk : entry - stopDist * InpRewardRisk;
      tpSource = "RR";
   }

   //--- broker stops-level validation for both SL and TP
   long stopsLvl = (long)g_spec.stopsLevel;
   double minDist = (double)MathMax(stopsLvl, 1) * point;
   if(MathAbs(entry - sl) < minDist || MathAbs(tp - entry) < minDist)
   {
      PrintFormat("[QATS][PLAN] broker stops level violated (need >= %I64d pts) - trade refused", stopsLvl);
      return false;
   }
   //--- freeze-level awareness for later modifications is handled in management
   double rr = MathAbs(tp - entry) / stopDist;
   if(rr < InpMinRR)
   {
      PrintFormat("[QATS][PLAN] reward:risk %.2f below minimum %.2f - trade refused", rr, InpMinRR);
      return false;
   }

   out.entry    = entry;
   out.sl       = sl;
   out.tp       = tp;
   out.stopDist = stopDist;
   out.tpSource = tpSource;
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
      PrintFormat("[QATS][SIZE] equity %.2f unavailable - trade refused", equity);
      return false;
   }
   double riskPct = EffectiveRiskPercent();
   double riskMoney = equity * riskPct / 100.0;
   if(riskMoney <= 0.0)
   {
      PrintFormat("[QATS][SIZE] risk money %.2f <= 0 - trade refused", riskMoney);
      return false;
   }
   if(slDist <= 0.0)
   {
      PrintFormat("[QATS][SIZE] stop distance %.10f invalid - trade refused", slDist);
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
      PrintFormat("[QATS][SIZE] no quote (ref %.5f) - trade refused", refPrice);
      return false;
   }
   double lossPerLot = 0.0;
   if(!OrderCalcProfit(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol, 1.0,
                       refPrice, slPrice, lossPerLot))
   {
      PrintFormat("[QATS][SIZE] OrderCalcProfit failed at stop %.5f from %.5f, error=%d - trade refused",
                  slPrice, refPrice, GetLastError());
      return false;
   }
   // OrderCalcProfit returns a NEGATIVE number for a losing exit.
   lossPerLot = -lossPerLot;
   if(lossPerLot <= 0.0)
   {
      PrintFormat("[QATS][SIZE] lossPerLot %.5f invalid (ref %.5f stop %.5f) - trade refused",
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

   // margin check with shrink loop: reduce to what free margin can carry
   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double margin = 0.0;
   if(!OrderCalcMargin(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol, vol, price, margin))
   {
      PrintFormat("[QATS][SIZE] OrderCalcMargin failed, error=%d - trade refused", GetLastError());
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
         PrintFormat("[QATS][SIZE] OrderCalcMargin failed during shrink, error=%d", GetLastError());
         return false;
      }
   }
   if(vol < g_spec.volMin)
   {
      PrintFormat("[QATS][SIZE] volume %.2f below broker minimum %.2f after margin fitting (free margin %.2f) - trade refused",
                  vol, g_spec.volMin, freeMargin);
      return false;
   }
   volumeOut    = vol;
   riskMoneyOut = vol * lossPerLot;
   return true;
}

//+------------------------------------------------------------------+
//| SECTION 18 - GUARD CHAIN (everything that can veto an entry)     |
//+------------------------------------------------------------------+
bool EntriesAllowed(string &blockReason)
{
   blockReason = "";
   if(!InpEnableTrading) { blockReason = "MASTER SWITCH off (InpEnableTrading=false)"; return false; }
   if(g_execBlocked)     { blockReason = g_blockReason; return false; }
   // re-verify account/terminal/EA/symbol permissions at decision time
   string pr = "";
   if(!VerifyAccountProtection(pr)) { blockReason = "PROTECTION: " + pr; return false; }
   if(g_dayLocked)       { blockReason = "DAILY LOSS LIMIT reached - locked until tomorrow"; return false; }
   if(g_ddHalted)        { blockReason = StringFormat("ACCOUNT DRAWDOWN %.2f%% from equity high-water - halted", g_accountDDPct); return false; }
   if(g_inCooldown)      { blockReason = "CONSECUTIVE-LOSS cooldown active"; return false; }
   if(InpMaxTradesPerDay > 0 && g_tradesToday >= InpMaxTradesPerDay)
                           { blockReason = StringFormat("daily trade cap reached (%d/%d)", g_tradesToday, InpMaxTradesPerDay); return false; }
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
      if(!inSession) { blockReason = "outside trading session"; return false; }
   }
   // stale data guard
   if(InpMaxDataAgeSeconds > 0)
   {
      long tickTime = (long)SymbolInfoInteger(_Symbol, SYMBOL_TIME);
      long age = (long)TimeTradeServer() - tickTime;
      if(age > InpMaxDataAgeSeconds) { blockReason = StringFormat("stale tick (%I64ds old)", age); return false; }
   }
   // spread guard (absolute)
   double spreadPts = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point;
   if(spreadPts > (double)InpMaxSpreadPoints)
   { blockReason = StringFormat("spread %.0f pts > max %d", spreadPts, InpMaxSpreadPoints); return false; }
   // position cap (this magic + symbol)
   if(CountMyPositions() >= InpMaxOpenPositions)
   { blockReason = StringFormat("max open positions reached (%d)", InpMaxOpenPositions); return false; }
   // duplicate order prevention: a pending retry is already in flight
   if(g_pendingRetryAt != 0)
   { blockReason = "order retry pending"; return false; }
   return true;
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

bool ExecuteSignal(const SAnalysis &plan)
{
   // v6.6.21: classify from QATS's own confluence score and RR, then apply the
   // profile ceiling BEFORE any sizing work. A class this EA's profile does not
   // allow is refused outright - never quietly sized to zero.
   double plan_rr = (plan.stopDist > 0.0 ? MathAbs(plan.tp - plan.entry) / plan.stopDist : 0.0);
   int plan_cls = QATS_Classify((double)plan.score, plan_rr);
   if(!QATS_ProfileAllows(plan_cls))
   {
      QATS_Audit("EXEC", plan_cls, (double)plan.score, plan_rr, "REFUSED",
                 "class not allowed by profile " + QATS_ProfileName(InpSignalExecutionProfile));
      return false;
   }

   double volume = 0.0, riskMoney = 0.0;
   if(!CalcPositionVolume(plan.stopDist, plan.dir > 0, volume, riskMoney))
   {
      QATS_Audit("SIZE", plan_cls, (double)plan.score, plan_rr, "REFUSED",
                 "position volume could not be sized");
      return false;
   }
   QATS_Audit("EXEC", plan_cls, (double)plan.score, plan_rr, "SIZED",
              "volume " + DoubleToString(volume, 2) + " risk " + DoubleToString(riskMoney, 2));

   double spreadPts = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point;
   if(spreadPts > plan.stopDist / g_spec.point * InpMaxSpreadFracOfStop)
   {
      PrintFormat("[QATS][EXEC] spread %.0f pts is more than %.0f%% of the stop distance - refused",
                  spreadPts, InpMaxSpreadFracOfStop * 100.0);
      return false;
   }

   double sl = plan.sl, tp = plan.tp;
   string side = (plan.dir > 0) ? "BUY" : "SELL";
   PrintFormat("[QATS][ORDER] %s %.2f lots %s @ %.5f | SL %.5f | TP %.5f (%s) | risk %.2f%% (%.2f %s) | score %d",
               side, volume, _Symbol, plan.entry, sl, tp, plan.tpSource,
               EffectiveRiskPercent(), riskMoney, g_spec.profitCcy, plan.score);

   if(InpDryRun)
   {
      PrintFormat("[QATS][DRY RUN] order NOT sent (InpDryRun=true). Skipping execution.");
      return false;
   }

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
      // A successful retcode is NOT proof of a position: verify it exists.
      ulong positionTicket = 0;
      if(VerifyPositionOpened(plan.dir, positionTicket))
         PrintFormat("[QATS][VERIFY] POSITION CONFIRMED on server: ticket=%I64u %s %.2f lots", positionTicket, side, volume);
      else
         PrintFormat("[QATS][VERIFY][CRITICAL] retcode=%u but NO open position found for %s %s - check terminal/journal NOW", rc, side, _Symbol);

      // count the trade for the daily cap
      string dk = TodayKey();
      GVSet(GVKey("trades_" + dk), (double)(g_tradesToday + 1));
      g_tradesToday++;
      g_pendingRetryAt = 0;
      g_pendingRetries = 0;
      return true;
   }

   if(IsTransientRetcode(rc) && g_pendingRetries < 3)
   {
      g_pendingRetryAt = (ulong)TimeTradeServer();
      g_pendingRetries++;
      g_pendingDir     = plan.dir;
      g_pendingEntry   = plan.entry;
      g_pendingSL      = sl;
      g_pendingTP      = tp;
      PrintFormat("[QATS][EXEC] transient failure - queued retry %d/3 after next tick", g_pendingRetries);
      return false;
   }

   PrintFormat("[QATS][EXEC][FAIL] %s rejected: retcode=%u (%s). Signal abandoned.", side, rc, rcDesc);
   g_pendingRetryAt = 0;
   g_pendingRetries = 0;
   return false;
}

// retry a previously queued transient rejection, at most once every 5 seconds
void ProcessPendingRetry()
{
   if(g_pendingRetryAt == 0) return;
   if(TimeTradeServer() < (datetime)g_pendingRetryAt + 5) return;
   if(g_pendingRetries >= 3)
   {
      PrintFormat("[QATS][RETRY] retry budget exhausted - signal abandoned");
      g_pendingRetryAt = 0;
      g_pendingRetries = 0;
      return;
   }
   g_pendingRetryAt = (ulong)TimeTradeServer(); // re-stamp so we retry at most once per 5s
   SAnalysis plan;
   plan.dir = g_pendingDir;
   plan.entry = g_pendingEntry;
   plan.sl = g_pendingSL;
   plan.tp = g_pendingTP;
   plan.stopDist = MathAbs(plan.entry - plan.sl);
   plan.score = 0;
   plan.tpSource = "RETRY";
   plan.reason = "pending retry";
   // refresh entry to the live price; keep the original stop geometry
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double liveEntry = (plan.dir > 0) ? ask : bid;
   plan.entry = liveEntry;
   PrintFormat("[QATS][RETRY] re-submitting %s (retry %d/3)", (plan.dir > 0 ? "BUY" : "SELL"), g_pendingRetries + 1);
   ExecuteSignal(plan);
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
         if(needMove && IsStopValid(beSL, price))
         {
            if(g_trade.PositionModify(ticket, beSL, tp))
               PrintFormat("[QATS][MANAGE] ticket=%I64u SL -> BREAK-EVEN @ %.5f (+%.2fR)", ticket, beSL, rMultiple);
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
//| SECTION 21 - DAILY GUARDS & CLOSED-DEAL PROCESSING               |
//+------------------------------------------------------------------+
void UpdateDailyGuards()
{
   string dk = TodayKey();
   string baseKey = GVKey("daybase_" + dk);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

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
   g_ddHalted = (ddCap > 0.0 && g_accountDDPct >= ddCap);

   g_tradesToday   = (int)GVGet(GVKey("trades_" + dk), 0.0);
   g_cooldownUntil = (datetime)GVGet(GVKey("cooldown_until"), 0.0);
   g_inCooldown    = (TimeTradeServer() < g_cooldownUntil);
   g_consecLosses  = (int)GVGet(GVKey("consec_losses"), 0.0);
}

// scan newly closed deals for this magic to update the consecutive-loss breaker
void ProcessClosedDeals()
{
   datetime from = TimeTradeServer() - 7 * 86400;
   if(!HistorySelect(from, TimeTradeServer())) return;
   int total = HistoryDealsTotal();
   ulong lastSeen = (ulong)GVGet(GVKey("last_deal"), 0.0);
   ulong maxSeen  = lastSeen;
   double consec  = GVGet(GVKey("consec_losses"), 0.0);

   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0 || ticket <= lastSeen) continue;
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagic) continue;
      long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY) continue;
      double dealProfit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      long posId = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      if(posId > 0) GVDel(GVKey("pc_" + IntegerToString(posId)));  // position closed: drop partial-bank marker
      if(ticket > maxSeen) maxSeen = ticket;
      // DEAL_PROFIT==0 (breakeven / commission-only) is NEUTRAL: never counts as a loss
      if(dealProfit < 0.0)
      {
         consec += 1.0;
         if(InpStopAfterConsecLoss > 0 && consec >= (double)InpStopAfterConsecLoss)
         {
            datetime until = TimeTradeServer() + (datetime)InpCooldownAfterLossMin * 60;
            GVSet(GVKey("cooldown_until"), (double)until);
            PrintFormat("[QATS][GUARD] %d consecutive losing closes - standing down for %d minutes (until %s)",
                        (int)consec, InpCooldownAfterLossMin, TimeToString(until, TIME_DATE | TIME_MINUTES));
            consec = 0.0;
         }
      }
      else if(dealProfit > 0.0)
      {
         consec = 0.0;
      }
   }
   if(maxSeen > lastSeen)
   {
      GVSet(GVKey("last_deal"), (double)maxSeen);
      GVSet(GVKey("consec_losses"), consec);
      g_consecLosses = (int)consec;
   }
}

// on attach, adopt the current history watermark so ancient deals are never re-counted
void InitDealWatermark()
{
   if(GlobalVariableCheck(GVKey("last_deal"))) return;
   datetime from = TimeTradeServer() - 7 * 86400;
   ulong maxSeen = 0;
   if(HistorySelect(from, TimeTradeServer()))
   {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket != 0 && HistoryDealGetInteger(ticket, DEAL_MAGIC) == InpMagic && ticket > maxSeen)
            maxSeen = ticket;
      }
   }
   GVSet(GVKey("last_deal"), (double)maxSeen);
   PrintFormat("[QATS] deal watermark initialised at ticket %I64u", maxSeen);
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
   PrintFormat("[QATS][HB] equity=%.2f %s dayPnL=%+.2f (%.2f%%) HWM=%.2f DD=%.2f%% tradesToday=%d consecLosses=%d dayLocked=%s ddHalted=%s cooldown=%s spread=%.0fpts lastScore=%d lastDir=%+d | %s",
               AccountInfoDouble(ACCOUNT_EQUITY), g_spec.profitCcy,
               g_dayPnL, (g_dayBase > 0 ? g_dayPnL / g_dayBase * 100.0 : 0.0),
               g_equityHWM, g_accountDDPct, g_tradesToday, g_consecLosses,
               (g_dayLocked ? "YES" : "no"), (g_ddHalted ? "YES" : "no"), (g_inCooldown ? "YES" : "no"),
               (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_spec.point,
               g_lastScore, g_lastDir, g_lastReason);
}

void DrawPanel()
{
   string status = g_execBlocked ? "BLOCKED" : (InpDryRun ? "DRY RUN" : "ARMED (DEMO)");
   string text = StringFormat(
      "QuantumAutonomousTradingSystem v%s | %s\nSymbol: %s | %s\nEquity: %.2f %s | Risk/trade: %.2f%% | Day P/L: %+.2f\nGuards: dayLock=%s ddHalt=%s cooldown=%s | Trades today: %d/%d\nLast analysis: dir=%+d score=%d | %s",
      QATS_VERSION, status, _Symbol, (g_execBlocked ? g_blockReason : "all protection checks passed"),
      AccountInfoDouble(ACCOUNT_EQUITY), g_spec.profitCcy, EffectiveRiskPercent(), g_dayPnL,
      (g_dayLocked ? "ON" : "off"), (g_ddHalted ? "ON" : "off"), (g_inCooldown ? "ON" : "off"),
      g_tradesToday, InpMaxTradesPerDay,
      g_lastDir, g_lastScore, g_lastReason);
   Comment(text);
}

//+------------------------------------------------------------------+
//| SECTION 23 - Lifecycle: OnInit / OnDeinit                        |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[QATS]====================================================");
   PrintFormat("[QATS] QuantumAutonomousTradingSystem v%s attaching to %s", QATS_VERSION, _Symbol);
   Print("[QATS]====================================================");

   if(InpResetBreakersAtInit) ResetBreakers();

   //--- 1. symbol specification (broker-provided, never assumed)
   if(!LoadSymbolSpec(g_spec))
   {
      g_execBlocked = true;
      g_blockReason = "symbol specification unavailable";
      return INIT_FAILED;   // without specs no risk math is possible; refuse to run
   }
   PrintSymbolSpec();

   //--- 2. MANDATORY demo / permission protection
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
      PrintFormat("[QATS][PROTECTION] PASS: ACCOUNT_TRADE_MODE=DEMO confirmed, terminal/EA/symbol permissions OK.");
   }

   //--- 3. effective risk banner (what the code will ACTUALLY enforce)
   PrintFormat("[QATS][RISK] per-trade risk = %.2f%% of equity (input %.2f%%, ceiling %.2f%%, hard cap %.2f%%)",
               EffectiveRiskPercent(), InpRiskPercent, InpMaxRiskPercent, QATS_HARD_CAP_RISK_PCT);
   PrintFormat("[QATS][RISK] daily loss stop = %.2f%% (money stop %.2f) | drawdown halt = %.2f%% from equity HWM | trades/day cap = %d",
               EffectiveDailyLossPercent(), InpMaxDailyLossMoney, EffectiveDrawdownPercent(), InpMaxTradesPerDay);
   PrintFormat("[QATS][RISK] max positions = %d | consec-loss stand-down = %d (%d min) | dry run = %s | demo only = %s",
               InpMaxOpenPositions, InpStopAfterConsecLoss, InpCooldownAfterLossMin,
               (InpDryRun ? "ON" : "off"), (InpDemoOnly ? "YES (mandatory)" : "NO - REFUSED AT RUNTIME"));

   //--- 4. indicator handles (native built-ins)
   g_hD1Fast  = iMA(_Symbol, PERIOD_D1, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hD1Slow  = iMA(_Symbol, PERIOD_D1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_hH4Fast  = iMA(_Symbol, PERIOD_H4, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hH4Slow  = iMA(_Symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_hH1Fast  = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hH1Slow  = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_hM15Fast = iMA(_Symbol, PERIOD_M15, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_hATRH1   = iATR(_Symbol, PERIOD_H1, InpATRPeriod);
   g_hATRM5   = iATR(_Symbol, PERIOD_M5, InpATRPeriod);

   if(g_hD1Fast == INVALID_HANDLE || g_hD1Slow == INVALID_HANDLE ||
      g_hH4Fast == INVALID_HANDLE || g_hH4Slow == INVALID_HANDLE ||
      g_hH1Fast == INVALID_HANDLE || g_hH1Slow == INVALID_HANDLE ||
      g_hM15Fast == INVALID_HANDLE || g_hATRH1 == INVALID_HANDLE || g_hATRM5 == INVALID_HANDLE)
   {
      PrintFormat("[QATS][FATAL] Failed to create indicator handles, error=%d", GetLastError());
      ReleaseHandles();
      return INIT_FAILED;
   }

   //--- 5. persisted guard state
   InitDealWatermark();
   UpdateDailyGuards();

   //--- 6. sanity: probe the data pipeline once (non-fatal if not ready yet)
   SReading r;
   if(LoadReading(r))
      PrintFormat("[QATS] data pipeline OK | ATR(H1)=%.5f ATR(M5)=%.5f VWAP=%.5f", r.atrH1, r.atrM5, r.vwap);
   else
      PrintFormat("[QATS] data pipeline not ready yet (normal on a cold start); entries wait for closed bars");

   PrintFormat("[QATS] attach complete | mode=%s | waiting for new M5 bars", (g_execBlocked ? "BLOCKED" : (InpDryRun ? "DRY RUN" : "LIVE ON DEMO")));
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
   if(g_hATRM5  != INVALID_HANDLE) IndicatorRelease(g_hATRM5);
   g_hD1Fast = g_hD1Slow = g_hH4Fast = g_hH4Slow = g_hH1Fast = g_hH1Slow = INVALID_HANDLE;
   g_hM15Fast = g_hATRH1 = g_hATRM5 = INVALID_HANDLE;
}

void OnDeinit(const int reason)
{
   ReleaseHandles();
   Comment("");
   PrintFormat("[QATS] deinit (reason=%d) - handles released, guards persisted", reason);
}

//+------------------------------------------------------------------+
//| SECTION 24 - Tick handling                                       |
//+------------------------------------------------------------------+
void OnTick()
{
   UpdateDailyGuards();
   ManagePositions();
   ProcessPendingRetry();

   bool newBar = false;
   datetime barTime = iTime(_Symbol, PERIOD_M5, 0);
   if(barTime != g_lastBarM5)
   {
      g_lastBarM5 = barTime;
      newBar = true;
   }

   if(newBar)
   {
      ProcessClosedDeals();
      SAnalysis raw = AnalyzeMarket();
      g_lastReason = raw.reason;
      g_lastScore  = raw.score;
      g_lastDir    = raw.dir;

      // trade management decision first: an opposite signal closes our position
      if(raw.dir != 0 && raw.score >= InpMinScore)
         ClosePositionOnOpposite(raw.dir);

      // entry decision
      string blockReason = "";
      if(raw.dir == 0)
      {
         if(InpVerbose) PrintFormat("[QATS][SKIP] no trade: %s | %s", raw.reason, "alignment veto or conflicting structure");
      }
      else if(raw.score < InpMinScore)
      {
         if(InpVerbose) PrintFormat("[QATS][SKIP] score %d < minimum %d | %s", raw.score, InpMinScore, raw.reason);
      }
      else if(!EntriesAllowed(blockReason))
      {
         if(InpVerbose) PrintFormat("[QATS][SKIP] blocked: %s | score=%d | %s", blockReason, raw.score, raw.reason);
      }
      else
      {
         if(InpRequireZoneTouch && !raw.zoneTouched)
            PrintFormat("[QATS][SKIP] zone touch required but price is not at the entry zone | %s", raw.reason);
         else
         {
            SAnalysis plan;
            if(!BuildTradePlan(raw, plan))
               PrintFormat("[QATS][SKIP] invalid trade plan (stop cannot be calculated/validated) | %s", raw.reason);
            else
            {
               plan.reason = raw.reason;
               ExecuteSignal(plan);
            }
         }
      }
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
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      ulong dealTicket = trans.deal;
      if(HistoryDealSelect(dealTicket))
      {
         long magic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);
         if(magic == InpMagic)
         {
            long dtype = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
            PrintFormat("[QATS][DEAL] ticket=%I64u entry=%I64d symbol=%s type=%I64u volume=%.2f price=%.5f profit=%.2f",
                        dealTicket, dtype,
                        HistoryDealGetString(dealTicket, DEAL_SYMBOL),
                        (ulong)HistoryDealGetInteger(dealTicket, DEAL_TYPE),
                        HistoryDealGetDouble(dealTicket, DEAL_VOLUME),
                        HistoryDealGetDouble(dealTicket, DEAL_PRICE),
                        HistoryDealGetDouble(dealTicket, DEAL_PROFIT));
         }
      }
   }
}
//+------------------------------------------------------------------+
