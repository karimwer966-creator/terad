//+------------------------------------------------------------------+
//|                                          QSMC_AutoTrader.mq5    |
//|  Companion EXECUTION Expert Advisor for the QSMC indicator.       |
//|                                                                   |
//|  WHY THIS IS A SEPARATE PROGRAM                                   |
//|  ------------------------------                                   |
//|  The indicator and the QSMC layer are observation-only on         |
//|  purpose: they publish, log and draw, and the release gate (G4)   |
//|  refuses any build of THEM that can reach the trade API. That is  |
//|  what makes the dashboard safe to leave on a chart. Execution     |
//|  therefore lives here, in ONE file, behind its own switches, and  |
//|  the release gate allows exactly this file to trade. Every other  |
//|  file in the repository is still checked for the trade API.       |
//|                                                                   |
//|  WHAT IT TRADES                                                   |
//|  ----------------                                                 |
//|  It creates one private instance of `nadir2` (iCustom) and reads  |
//|  the CORE signal export buffers the indicator already fills:      |
//|    buffer 7  direction (+1 buy / -1 sell / 0 none)                |
//|    buffer 8  entry  9 stop  10 TP1  11 TP2  12 TP3                |
//|  A signal exists only after the bar it belongs to CLOSED, so the  |
//|  EA can never act on a forming candle. It trades the CORE         |
//|  published signal only - not the tactical preview mark, not ZRE.  |
//|                                                                   |
//|  FIXED SIZE, FIXED PIP LADDER (opt-in, off by default)            |
//|  --------------------------------------------------               |
//|  InpLotMode=QSMC_LOT_FIXED with InpFixedLots=0.05 takes the same   |
//|  volume on every signal instead of a risk-derived one; it is       |
//|  still refused if that volume's stop would break the 1% ceiling.   |
//|  InpUseTPPips=true then replaces the indicator's target with three |
//|  fixed distances measured from the FILL (100/200/300 pips by       |
//|  default): rung 1 and rung 2 are banked as partial closes of the   |
//|  ORIGINAL volume (40% + 40%), the stop moves to the entry after    |
//|  rung 1 and to rung 1 after rung 2, and the remainder exits at     |
//|  rung 3 - which is the TP written on the ticket, so the position   |
//|  still has a target if this EA is removed. A "pip" is resolved per |
//|  symbol (gold 0.10 of price, 5/3-digit FX 10 points) and the       |
//|  attach banner prints the resolved distances and their money value |
//|  - if that line is not what you intended, set InpPipPoints.        |
//|                                                                   |
//|  WHAT IT REFUSES TO DO                                            |
//|  ---------------------                                            |
//|  - It ships INERT: InpEnableTrading=false, and a first switch-on  |
//|    is still a dry run because InpDryRun=true.                     |
//|  - It refuses a real-money account while InpDemoOnly=true.        |
//|  - It refuses a signal with no stop, a stop on the wrong side, a  |
//|    stop wider than InpMaxStopPoints, or geometry the broker's     |
//|    stops level rejects. No stop means no trade, ever.             |
//|  - It refuses a plan whose reward:risk has already collapsed at   |
//|    the price it would actually pay (InpMinRRAtFill): the          |
//|    indicator approved RR at its zone edge, market execution does  |
//|    not get to keep that number for free.                          |
//|  - A server refusal is classified: transient ones (requote,       |
//|    price changed/off, timeout, connection, busy) are retried on   |
//|    the next poll up to InpOrderRetryMax, permanent ones abandon   |
//|    the signal. Neither path marks a good signal "done" by        |
//|    accident, and neither can flood the server.                    |
//|  - It refuses to exceed InpMaxRiskPercent (hard ceiling = 1% of    |
//|    equity) or InpMaxOpenPositions.                                |
//|  - It stops opening trades for the rest of the day after a        |
//|    InpMaxDailyLossPercent drawdown on equity, and that block is   |
//|    PERSISTED: a chart reload in the middle of the day cannot      |
//|    re-base the baseline and start again from zero.                     |
//|  - It ignores every signal older than InpMaxSignalAgeBars and     |
//|    every signal that existed before the EA was attached.          |
//|  - It never averages down, never martingales, never widens a stop,|
//|    and only ever moves a stop to break-even (one direction).      |
//|                                                                   |
//|  WHAT IT CANNOT DO                                                |
//|  -----------------                                               |
//|  It cannot make this strategy profitable, predict price, or turn  |
//|  the indicator's evidence scores into a win rate. Sizing, gating  |
//|  and stops are risk control; they are not an edge. Test on a      |
//|  demo account first, and note that a demo result is not a         |
//|  forecast either.                                                 |
//|                                                                   |
//|  SETUP                                                            |
//|  -----                                                            |
//|  1. Copy nadir2.mq5 to MQL5\Indicators\ and the QSMC headers to   |
//|     MQL5\Include\QSMC\, then this file to MQL5\Experts\. Press F7 |
//|     on all three in MetaEditor.                                   |
//|  2. Attach the EA to the SAME symbol and timeframe you want to    |
//|     trade. Strategy Tester and live charts both work.             |
//|     ONE EXPERT PER CHART: MetaTrader allows a single EA on a chart,|
//|     so this file and KLJ_DataFeeder.mq5 need separate charts. The  |
//|     indicator(s) may share this chart - so the usual layout is     |
//|     chart 1 = nadir2 + this EA, chart 2 = the data feeder.         |
//|  3. Tick "Allow Algo Trading" in the terminal and in the EA.      |
//|  4. Leave it inert for a session and read the journal lines it    |
//|     prints (they say INERT / DRY RUN and why each signal was      |
//|     skipped). Only then decide whether InpEnableTrading=true.      |
//|  5. InpIndicatorName must match the compiled indicator file name  |
//|     ("nadir2"). If the indicator keeps InpExportSignalBuffers     |
//|     true (its default), the buffers exist; if that default is      |
//|     ever changed, this EA stops seeing signals - and the contract |
//|     test in tools/test_autotrader_contract.py fails, on purpose.  |
//|                                                                   |
//|  SILENCE IS THE FAILURE MODE YOU WILL ACTUALLY MEET               |
//|  -----------------------------------------------                  |
//|  When no order appears there are only two root causes: the        |
//|  indicator published no CORE signal, or it did and a filter       |
//|  refused it. A throttled [QSMC_AT] heartbeat line (default every  |
//|  InpHeartbeatSeconds) scans the CORE direction buffer over        |
//|  InpHeartbeatLookback bars and states which one it is, plus the   |
//|  last skip reason. It is read-only: no gate, order or position is |
//|  touched, and InpHeartbeatSeconds=0 switches it off.              |
//|                                                                   |
//|  v6.6.10: the heartbeat also prints the INDICATOR'S OWN VERDICT.  |
//|  The indicator cannot trade and this EA cannot read a chart       |
//|  panel, so nadir2 publishes the result of its gate chain for the  |
//|  last closed bar as terminal globals (QSMC_DIAG_<symbol>_<tf>_*); |
//|  this EA decodes them. That is what turns "CORE signals: 0" into  |
//|  a named reason such as "RELIABILITY - score: reliability below   |
//|  InpMinReliability" without opening a single chart. The codes are |
//|  the DIAG_TABLE block below; it is shared verbatim with nadir2    |
//|  and checked by tools/test_diag_bridge.py.                        |
//+------------------------------------------------------------------+
#property copyright "KLJ / QSMC"
#property version   "6.614"
#property description "Companion execution EA for the QSMC indicator. Ships inert; no strategy claim."
#property strict

#include <Trade/Trade.mqh>

//--- Buffer indices of the CORE signal export (nadir2.mq5 OnInit).
//--- A contract test asserts the indicator still binds these exact slots.
#define QSMC_BUF_CORE_DIR     7
#define QSMC_BUF_CORE_ENTRY   8
#define QSMC_BUF_CORE_SL      9
#define QSMC_BUF_CORE_TP1    10
#define QSMC_BUF_CORE_TP2    11
#define QSMC_BUF_CORE_TP3    12
// v6.6.14 (H6): per-closed-bar verdict code buffers - authoritative when the
// GlobalVariable DIAG bridge cannot match an instance (custom inputs, multiple
// charts). 0.0 means "not yet written" (compatibility: older indicator builds
// never write these buffers, so they stay 0 and we fall back to GV).
#define QSMC_BUF_CORE_VCODE 19
#define QSMC_BUF_ZRE_VKIND  20

#define QSMC_AT_SEEN_RING   64

//--- The indicator's published blocker codes (nadir2.mq5, DiagPublishCoreState).
//--- Shared VERBATIM with nadir2.mq5 and checked by tools/test_diag_bridge.py:
//--- editing one side without the other fails the build, on purpose.
// DIAG_TABLE_BEGIN
//  0 NO_DATA              no closed-bar pass of the signal chain yet
//  1 CORE_PUBLISHED       a CORE signal was published on this closed bar
//  2 SETUP_ARMED          a setup is armed and waiting for its retest
//  3 SETUP_PENDING        a setup is waiting for a closed-bar confirmation
// 10 NO_STRUCTURE_ANCHOR  setup: no causally valid structure anchor
// 11 INCOMPLETE_CHAIN     setup: incomplete causal chain (hop or zone)
// 12 NO_SWEEP             chain: no confirmed liquidity sweep
// 13 NO_DISPLACEMENT      chain: no displacement event behind the break
// 14 NO_STRUCTURE_EVENT   chain: structure event missing or invalidated
// 15 NO_CAUSAL_ZONE       chain: no causal OB/FVG bound to the displacement
// 16 SWEEP_NO_POOL        chain: sweep has no confirmed liquidity-pool ancestor
// 17 LOCATION             location: the zone failed the location re-check
// 18 ANCHOR_RECHECK       anchor: the bound zone failed the causality re-check
// 19 LEG_GEOMETRY         leg: the sweep/displacement leg is too weak or too close
// 20 RR_TOO_LOW           geometry: RR1 below InpMinRR1
// 21 STOP_TOO_WIDE        geometry: stop distance above InpMaxStopATR
// 22 TARGET_ORDER         geometry: targets could not be ordered before the barrier
// 23 CONFIDENCE           score: confidence below InpMinConfidenceScore
// 24 RELIABILITY          score: reliability below InpMinReliability
// 25 GRADE                score: grade below InpMinGrade
// 26 EMA_VWAP_OPPOSE      score: EMA200/VWAP confluence opposes this direction
// 27 SPREAD               setup: spread above InpMaxSpreadPts
// 28 TOPDOWN              topdown: the D1->M5 chain blocks this direction
// 29 OWNERSHIP            ownership: another setup holds the execution lane
// 30 DIRECTION_VETO       direction veto: contrary to the zone role
// 31 BLACKLIST            setup: same idea blacklisted after an invalidation
// 32 LIFECYCLE            lifecycle: a state transition was rejected
// 33 BRANCH_ROLLBACK      setup: the causal branch was rejected or rolled back
// 34 OTHER                some other gate refused the candidate
// DIAG_TABLE_END

// GP_TABLE_BEGIN
//  -1                       no candidate reached a scoring gate this session
//  0 CONFIDENCE             points short of InpMinConfidenceScore
//  1 RELIABILITY            points short of InpMinReliability
//  2 RR1                    ratio short of InpMinRR1
//  3 STOP_TOO_WIDE          ATR over InpMaxStopATR
//  4-15 STRUCTURAL          the chain never proposed a trade (not a threshold)
// 23 CONFIDENCE             points short (explicit gate)
// 24 RELIABILITY            points short (explicit gate)
// 25 RR1                    ratio short (explicit gate)
// 26 STOP_TOO_WIDE          ATR over (explicit gate)
// GP_TABLE_END

enum ENUM_QSMC_LOT_MODE
  {
   QSMC_LOT_RISK_PERCENT = 0,   // risk % of equity per trade
   QSMC_LOT_FIXED        = 1    // fixed volume from InpFixedLots
  };

enum ENUM_QSMC_TP_SOURCE
  {
   QSMC_TP_LEVEL1 = 1,          // indicator TP1
   QSMC_TP_LEVEL2 = 2,          // indicator TP2
   QSMC_TP_LEVEL3 = 3           // indicator TP3
  };

//--- 1. switches -----------------------------------------------------
input bool   InpEnableTrading        = false;  // MASTER SWITCH: false = this EA never sends an order
input bool   InpDryRun               = true;   // true = log the order it would send, send nothing
input bool   InpDemoOnly             = true;   // refuse a real-money account entirely
input string InpRealAccountConfirm   = "";     // real account: type the account NUMBER here to allow it
input long   InpMagic                = 20261027; // magic number; this EA only manages its own positions
input string InpIndicatorName        = "nadir2"; // compiled indicator file name (no .mq5)
input string InpTradeComment         = "QSMC-AUTO"; // comment stamped on every order

//--- 2. sizing -------------------------------------------------------
input ENUM_QSMC_LOT_MODE InpLotMode  = QSMC_LOT_RISK_PERCENT; // how the volume is chosen
input double InpRiskPercent          = 0.25;   // % of equity risked by the stop, per trade
input double InpMaxRiskPercent       = 1.00;   // hard ceiling; the input above is clamped to this
input double InpFixedLots            = 0.00;   // volume used when InpLotMode = QSMC_LOT_FIXED

//--- 3. exits --------------------------------------------------------
input ENUM_QSMC_TP_SOURCE InpTPLevel = QSMC_TP_LEVEL1; // which indicator target becomes the TP
input double InpBreakEvenAtR         = 1.00;   // move the stop to entry after +1R; 0 = off

//--- 3b. FIXED PIP LADDER (opt-in) -----------------------------------
// The indicator sizes its own targets from structure, so a "100/200/300" request
// cannot be expressed through InpTPLevel. This block does it in the EXECUTION
// layer only: the position is sent with the ladder's LAST rung as its broker TP
// (so a target survives even if this EA is removed), and the first two rungs are
// banked by partial closes from ManageOpenPositions(). It changes no indicator
// gate and no signal: only where this EA takes profit on what it was given.
// Everything is OFF by default, so the shipped behaviour is unchanged.
input bool   InpUseTPPips            = false;  // true = ignore the indicator TP and use the pip ladder below
input int    InpPipPoints            = 0;      // points per pip; 0 = auto (gold 0.10, 5/3-digit FX 10 pts, other 1 pt)
input int    InpTP1Pips              = 100;    // rung 1 distance from the FILL price, in pips
input int    InpTP2Pips              = 200;    // rung 2
input int    InpTP3Pips              = 300;    // rung 3 (this is the TP put on the ticket)
input double InpTP1ClosePercent      = 40.0;   // % of the ORIGINAL volume closed at rung 1
input double InpTP2ClosePercent      = 40.0;   // % of the ORIGINAL volume closed at rung 2
input bool   InpMoveSLToBEAtTP1      = true;   // after rung 1 the stop goes to the entry (never widened)
input bool   InpMoveSLToTP1AtTP2     = true;   // after rung 2 the stop goes to rung 1 (locks the first leg)

//--- 4. filters ------------------------------------------------------
input int    InpMaxSpreadPoints      = 30;     // refuse a signal while the spread is wider
// Slippage tolerance for a MARKET order. It used to be a hard-coded 10 points,
// which is under one pip on a 5-digit FX pair and well under a normal gold
// spread: the server answered "requote" and the operator had no input to widen
// it. 0 = fill at any price (NOT recommended; the broker decides the fill).
input int    InpDeviationPoints      = 20;     // max slippage accepted on a market order, in points
input int    InpMaxOpenPositions     = 1;      // positions of this magic and symbol
input double InpMaxDailyLossPercent  = 3.00;   // stop for the day after this equity drawdown; 0 = off
input int    InpMaxSignalAgeBars     = 2;      // ignore a signal older than this many closed bars
input int    InpMinStopPoints        = 20;     // refuse a stop closer than this
input int    InpMaxStopPoints        = 5000;   // refuse a stop wider than this
input bool   InpCloseOnOpposite      = false;  // close this magic's position on an opposite signal
// The indicator validates RR at its PLANNED entry, which is a zone edge. This EA
// executes at MARKET, so by the time the order is sent the remaining reward:risk
// can be a fraction of what the gate approved. InpMinRRAtFill re-checks RR at the
// price actually on the ticket; 0 disables the check (and restores the old
// behaviour, where a plan could be chased down to almost nothing).
input double InpMinRRAtFill          = 1.00;   // refuse when reward:risk at the CURRENT price is below this; 0 = off
input int    InpOrderRetryMax        = 3;      // transient order failures tolerated per signal before it is abandoned

//--- 5. professional trade management ---------------------------------
// The indicator already scores the SESSION (100 in a kill zone, 75 in London/
// NY, 40 Asia, 30 off-session) but a score is not a filter: a 0.05-weight term
// cannot stop a setup at 03:00. These four inputs are the execution-side
// habits a discretionary professional applies and a score cannot:
//   * trade only inside the session window,
//   * a hard cap on entries per day (overtrading is the #1 account killer),
//   * a cooldown after a losing close (no revenge re-entry),
//   * bank half at +1R instead of hoping for the full target.
// Every one of them is OFF by default (0), so behaviour is unchanged unless an
// operator asks for it - presets/QSMC_pro_execution.set turns them on.
input int    InpSessionStartHour     = 0;      // server hour to start trading (0 + End 0 = no session filter)
input int    InpSessionEndHour       = 0;      // server hour to stop  (wrap over midnight is allowed, e.g. 22 -> 6)
input int    InpMaxTradesPerDay      = 0;      // entries per server day, persisted (0 = no cap)
input int    InpCooldownAfterLossMin = 0;      // minutes to stand down after a losing close (0 = off)
input double InpPartialCloseAtR      = 0.0;    // close InpPartialClosePercent at this R (0 = off)
input double InpPartialClosePercent  = 50.0;   // percent of the volume banked at InpPartialCloseAtR

//--- 6. runtime ------------------------------------------------------
input int    InpPollSeconds          = 2;      // timer period, seconds
input bool   InpVerbose              = false;  // print every skipped signal and why
input int    InpHeartbeatSeconds     = 300;    // diagnostic journal line every N seconds (0 = off)
input int    InpHeartbeatLookback    = 200;    // bars scanned to prove whether the indicator publishes CORE at all

//+------------------------------------------------------------------+
//| State                                                            |
//+------------------------------------------------------------------+
CTrade    g_trade;
int       g_handle=INVALID_HANDLE;

datetime  g_start_bar=0;        // open time of the bar that was forming at attach
int       g_day_index=-1;
double    g_day_start_equity=0.0;
bool      g_day_blocked=false;

string    g_seen[QSMC_AT_SEEN_RING];
int       g_seen_n=0;

double    g_dir[], g_entry[], g_sl[], g_tp1[], g_tp2[], g_tp3[];

int       g_signals=0;
int       g_sent=0;
int       g_dry=0;
int       g_refused=0;
string    g_last_note="";
int       g_note_count=0;

// Heartbeat diagnostics: read-only. They copy buffer 7 and print; they never
// touch a gate, an order or a position. They exist because a chart that simply
// stays silent cannot distinguish "the indicator published nothing" from
// "the EA refused every signal" - the two root causes of "no trades".
datetime  g_last_heartbeat=0;
bool      g_heartbeat_first=true;
bool      g_last_copy_ok=false;

// Transient order-failure bookkeeping: which signal was refused by the SERVER
// (not by a gate), and how many times. A permanent retcode never retries; a
// transient one retries on the next poll, bounded by InpOrderRetryMax and by
// InpMaxSignalAgeBars, so a broken broker cannot turn into an order flood.
string    g_retry_key="";
int       g_retry_count=0;

// Break-even throttle: PositionModify used to be re-sent on EVERY tick while the
// broker kept refusing it, with the failure silent. One ticket, one attempt per
// pause, and the reason printed once.
ulong     g_be_ticket=0;
datetime  g_be_last_try=0;
ulong     g_be_warned_ticket=0;

// Per-position memory for the partial close: the ORIGINAL stop distance (R) and
// whether the partial was already taken. Break-even moves the stop to entry, so
// R has to be remembered at first sight or it is lost forever.
#define QSMC_AT_POS_RING 16
ulong     g_pos_ticket[QSMC_AT_POS_RING];
double    g_pos_risk[QSMC_AT_POS_RING];
bool      g_pos_partial[QSMC_AT_POS_RING];
double    g_pos_vol0[QSMC_AT_POS_RING];   // volume at first sight: rung %s are of THIS, not of what is left
int       g_pos_step[QSMC_AT_POS_RING];   // pip-ladder rungs already banked (0..2)
int       g_pos_n=0;

// Ladder close throttle: a refused partial is retried, but not on every tick and
// not silently - the same rule the break-even move already follows.
ulong     g_lad_warn_ticket=0;
datetime  g_lad_warn_time=0;

struct SQsigSignal
  {
   bool      valid;
   int       shift;
   datetime  bar_time;
   int       dir;        // +1 buy, -1 sell
   double    entry;
   double    sl;
   double    tp;
  };

//+------------------------------------------------------------------+
//| Small helpers                                                    |
//+------------------------------------------------------------------+
string DirText(const int dir)
  {
   return (dir>0 ? "BUY" : (dir<0 ? "SELL" : "NONE"));
  }

string SignalKey(const datetime bar_time,const int dir)
  {
   return (IntegerToString((long)bar_time)+"|"+DirText(dir));
  }

// Terminal global names are stored in a terminal-wide file, and broker symbols
// carry suffix characters that are not safe there ("XAUUSD.m", "EURUSD#",
// "US500-CFD"). A rejected name would make GlobalVariableSet() fail SILENTLY -
// and with it the reload guard and the cross-chart key D2 fixed. So this EA's
// own namespace is built from a sanitised symbol; the DIAG_* names it only
// READS are left byte-identical to the indicator's.
string KeySafe(const string s)
  {
   string out="";
   int n=StringLen(s);
   for(int i=0;i<n;i++)
     {
      ushort c=StringGetCharacter(s,i);
      string ch=StringSubstr(s,i,1);
      bool keep=((c>='0' && c<='9')||(c>='A' && c<='Z')||(c>='a' && c<='z'));
      out+=(keep ? ch : "_");
     }
   return out;
  }

string GlobName(const datetime bar_time,const int dir)
  {
   // The SYMBOL is part of the name, and that is a defect fix, not decoration.
   // Terminal globals are shared by every chart in the terminal, while this EA
   // is normally attached to several charts with the same InpMagic. Bars align
   // across symbols, so two charts could produce the same bar time and the same
   // direction - and a name without the symbol made the second chart read the
   // first chart's signal as "already seen" and silently drop a real trade.
   return ("QSMC_AT_"+IntegerToString(InpMagic)+"_"+KeySafe(_Symbol)+"_"+
           IntegerToString((long)bar_time)+"_"+(dir>0 ? "B" : "S"));
  }

// A transient retcode means the REQUEST never became an ORDER (requote, price
// moved, no quotes, timeout, dropped connection, broker busy). Those are safe to
// retry on the next poll: the position count is re-checked before every send, so
// a request that did reach the server cannot be opened twice by the retry.
// Anything else (no money, wrong stops, trade disabled, volume invalid) is a
// decision, and re-sending it every 2 seconds only hides the reason.
bool RetcodeIsTransient(const uint rc)
  {
   switch((int)rc)
     {
      case TRADE_RETCODE_REQUOTE:
      case TRADE_RETCODE_PRICE_CHANGED:
      case TRADE_RETCODE_PRICE_OFF:
      case TRADE_RETCODE_TIMEOUT:
      case TRADE_RETCODE_CONNECTION:
      case TRADE_RETCODE_TOO_MANY_REQUESTS:
      case TRADE_RETCODE_FROZEN:
         return true;
     }
   return false;
  }

bool SeenBefore(const string key,const datetime bar_time,const int dir)
  {
   for(int i=0;i<g_seen_n && i<QSMC_AT_SEEN_RING;i++)
      if(g_seen[i]==key) return true;
   return (GlobalVariableCheck(GlobName(bar_time,dir)));
  }

void MarkSeen(const string key,const datetime bar_time,const int dir)
  {
   g_seen[g_seen_n%QSMC_AT_SEEN_RING]=key;
   g_seen_n++;
   if(g_seen_n>=2*QSMC_AT_SEEN_RING) g_seen_n-=QSMC_AT_SEEN_RING;
   // Terminal global: survives a chart change / EA reload inside the same
   // terminal session, so a restart cannot re-fire yesterday's signal.
   GlobalVariableSet(GlobName(bar_time,dir),(double)TimeCurrent());
  }

// Note() takes EXACTLY two strings. MQL5 concatenates arguments only for
// Print/Alert/Comment/StringFormat; an ordinary function with 3 arguments is a
// compile error, so build the text with '+' before calling.
// Notes are throttled by (key+reason): a signal that is polled every few
// seconds prints its reason ONCE, not once per poll. InpVerbose adds the
// repeated polls on purpose, for someone diagnosing a symbol that never fires.
void Note(const string key,const string why)
  {
   string tag=key+"|"+why;
   if(tag==g_last_note)
     {
      g_note_count++;
      if(InpVerbose && g_note_count%30==0)
         Print("[QSMC_AT] still skipped ",key," - ",why," (",IntegerToString(g_note_count)," polls)");
      return;
     }
   Print("[QSMC_AT] skip ",key," - ",why);
   g_last_note=tag;
   g_note_count=0;
  }

//+------------------------------------------------------------------+
//| Volume normalisation. Never rounds UP to the broker minimum:     |
//| doing so would silently increase the risk above the requested %.  |
//+------------------------------------------------------------------+
double NormalizeLots(const string sym,const double raw)
  {
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double vmin=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   if(step<=0.0) step=0.01;
   double v=MathFloor(raw/step+1e-9)*step;
   if(v<vmin) return 0.0;
   if(vmax>0.0 && v>vmax) v=vmax;
   int digits=(int)MathMax(0.0,MathCeil(-MathLog10(step)));
   return NormalizeDouble(v,digits);
  }

//+------------------------------------------------------------------+
//| Broker stops level: SL/TP must be at least this far from price.   |
//+------------------------------------------------------------------+
bool StopsDistanceOK(const string sym,const double price,const double sl,const double tp)
  {
   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(point<=0.0) return false;
   long lvl=SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist=(double)lvl*point;
   if(min_dist<=0.0) return true;
   if(sl>0.0 && MathAbs(price-sl)<min_dist) return false;
   if(tp>0.0 && MathAbs(tp-price)<min_dist) return false;
   return true;
  }

bool SpreadOK(const string sym)
  {
   if(InpMaxSpreadPoints<=0) return true;
   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(point<=0.0) return false;
   double spread=(SymbolInfoDouble(sym,SYMBOL_ASK)-SymbolInfoDouble(sym,SYMBOL_BID))/point;
   return (spread<=(double)InpMaxSpreadPoints);
  }

int OpenCount(const string sym)
  {
   int n=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      n++;
     }
   return n;
  }

ulong FindOurPosition(const string sym,const int dir_wanted)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      long type=PositionGetInteger(POSITION_TYPE);
      bool is_buy=(type==POSITION_TYPE_BUY);
      if(dir_wanted>0 && is_buy) return ticket;
      if(dir_wanted<0 && !is_buy) return ticket;
     }
   return 0;
  }

//+------------------------------------------------------------------+
//| One place that answers "may this EA send an order right now?".    |
//| Empty string = yes. Everything the terminal/broker can switch off |
//| is checked here, because "why did it not trade?" is almost always |
//| one of these and not a strategy question.                         |
//+------------------------------------------------------------------+
string TradeEnvBlock(const bool buy)
  {
   if(!(bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return "the terminal's Algo Trading button is OFF";
   if(!(bool)MQLInfoInteger(MQL_TRADE_ALLOWED))
      return "expert trading is disabled for this EA (Allow Algo Trading in its properties)";
   if(!(bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      return "the account is not allowed to trade (broker side)";
   if(!(bool)AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      return "the server forbids expert trading on this account";
   long mode=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   if(mode==SYMBOL_TRADE_MODE_DISABLED)   return "trading is disabled on this symbol";
   if(mode==SYMBOL_TRADE_MODE_CLOSEONLY)  return "this symbol is close-only right now";
   if(buy && mode==SYMBOL_TRADE_MODE_SHORTONLY) return "this symbol is sell-only right now";
   if(!buy && mode==SYMBOL_TRADE_MODE_LONGONLY) return "this symbol is buy-only right now";
   bool real=(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO);
   if(!real) return "";
   if(InpDemoOnly)
      return "real account and InpDemoOnly=true (that is the shipping default)";
   // A real account is not a toggle: the operator must NAME the account, so a
   // settings preset copied from a demo chart cannot silently arm real money.
   if(InpRealAccountConfirm!=IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)))
      return "real account: set InpRealAccountConfirm to this account number ("+
             IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))+") to allow live orders";
   return "";
  }

//+------------------------------------------------------------------+
//| Sizing: risk a fixed fraction of equity between entry and stop.   |
//| The stop is the indicator's stop, so the volume follows the setup |
//| instead of the setup being fitted to a lot size.                  |
//+------------------------------------------------------------------+
double CalcLots(const string sym,const double entry,const double sl,const bool buy)
  {
   double vmax_cap=InpMaxRiskPercent;
   if(vmax_cap<=0.0) vmax_cap=0.25;
   if(vmax_cap>1.0) vmax_cap=1.0;

   if(InpLotMode==QSMC_LOT_FIXED)
     {
      double fixed_v=NormalizeLots(sym,InpFixedLots);
      if(fixed_v<=0.0) return 0.0;
      double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
      double tick_size=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
      double tick_value=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
      if(step<=0.0 || tick_size<=0.0 || tick_value<=0.0) return fixed_v;
      double loss=(MathAbs(entry-sl)/tick_size)*tick_value*fixed_v;
      double eq=AccountInfoDouble(ACCOUNT_EQUITY);
      if(eq<=0.0) return 0.0;
      if(loss>eq*InpMaxRiskPercent/100.0) return 0.0;   // the fixed lot is too big: refuse
      return fixed_v;
     }

   double pct=MathMin(InpRiskPercent,vmax_cap);
   if(pct<=0.0) return 0.0;
   double risk_money=AccountInfoDouble(ACCOUNT_EQUITY)*pct/100.0;
   double dist=MathAbs(entry-sl);
   double tick_size=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   double tick_value=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
   if(dist<=0.0 || tick_size<=0.0 || tick_value<=0.0 || risk_money<=0.0) return 0.0;

   double loss_per_lot=(dist/tick_size)*tick_value;
   if(loss_per_lot<=0.0) return 0.0;
   double lots=NormalizeLots(sym,risk_money/loss_per_lot);
   if(lots<=0.0) return 0.0;

   // Free-margin guard: halve the volume until it fits, never the stop.
   double free_margin=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double need=0.0;
   for(int i=0;i<8 && lots>0.0;i++)
     {
      need=0.0;
      ENUM_ORDER_TYPE t=ORDER_TYPE_BUY;
      if(!buy) t=ORDER_TYPE_SELL;
      if(!OrderCalcMargin(t,sym,lots,entry,need)) return 0.0;
      if(need<=free_margin*0.90) return lots;
      lots=NormalizeLots(sym,lots*0.5);
     }
   return 0.0;
  }

//+------------------------------------------------------------------+
//| Day guard: one baseline per SERVER day, one block per day.        |
//|                                                                   |
//| PERSISTED ON PURPOSE. The baseline used to live only in memory,   |
//| so a chart reload / settings change / terminal restart in the     |
//| middle of the day silently re-based "today's opening equity" to   |
//| the CURRENT, already-drawn-down equity - and the daily loss cap   |
//| started again from there. The keys carry the account login and    |
//| the magic, so two EAs on two charts never share a baseline.       |
//+------------------------------------------------------------------+
string DayGuardKey(const string leaf)
  {
   return ("QSMC_AT_DAY_"+IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))+
           "_"+IntegerToString(InpMagic)+"_"+leaf);
  }

void DayGuardLoad(const int day)
  {
   string kd=DayGuardKey("DAY");
   if(!GlobalVariableCheck(kd) || (int)GlobalVariableGet(kd)!=day)
     {
      // New server day (or first run): freeze the baseline NOW and write it.
      g_day_index=day;
      g_day_start_equity=AccountInfoDouble(ACCOUNT_EQUITY);
      g_day_blocked=false;
      GlobalVariableSet(kd,(double)day);
      GlobalVariableSet(DayGuardKey("EQ"),g_day_start_equity);
      GlobalVariableSet(DayGuardKey("BLOCKED"),0.0);
      GlobalVariableSet(DayGuardKey("TRADES"),0.0);   // new day, new entry budget
      GlobalVariablesFlush();
      Print("[QSMC_AT] day guard: new baseline ",
            DoubleToString(g_day_start_equity,2)," for server day ",
            TimeToString((datetime)((long)day*86400),TIME_DATE));
      return;
     }
   // Same day, restored from the terminal: the baseline and the block survive
   // a reload, which is the whole point of persisting them.
   g_day_index=day;
   double eq0=GlobalVariableGet(DayGuardKey("EQ"));
   g_day_start_equity=(eq0>0.0 ? eq0 : AccountInfoDouble(ACCOUNT_EQUITY));
   g_day_blocked=(GlobalVariableGet(DayGuardKey("BLOCKED"))>0.5);
   if(g_day_blocked)
      Print("[QSMC_AT] day guard RESTORED: this server day is already blocked at ",
            DoubleToString(g_day_start_equity*(1.0-MathMax(0.0,InpMaxDailyLossPercent)/100.0),2),
            " (a reload does not reset it)");
  }

void DayGuardUpdate()
  {
   int day=(int)(TimeCurrent()/86400);
   if(day!=g_day_index)
      DayGuardLoad(day);
   if(InpMaxDailyLossPercent>0.0 && g_day_start_equity>0.0)
     {
      double floor_eq=g_day_start_equity*(1.0-InpMaxDailyLossPercent/100.0);
      double eq=AccountInfoDouble(ACCOUNT_EQUITY);
      if(eq<=floor_eq && !g_day_blocked)
        {
         g_day_blocked=true;
         GlobalVariableSet(DayGuardKey("BLOCKED"),1.0);
         GlobalVariablesFlush();
         Print("[QSMC_AT] daily loss guard: equity ",DoubleToString(eq,2),
               " <= ",DoubleToString(floor_eq,2)," - no new entries today (persisted)");
        }
     }
  }

//+------------------------------------------------------------------+
//| Session window, on SERVER hours (the same clock the daily guard    |
//| uses). Start == End means "no window". A window may wrap midnight  |
//| (22 -> 6), which is how an Asia-only or NY-only mandate is set.    |
//| This is a filter, not a score: it refuses an entry, and the note   |
//| says so, instead of quietly lowering a quality number.            |
//+------------------------------------------------------------------+
bool SessionOpenNow(string &why)
  {
   why="";
   if(InpSessionStartHour==InpSessionEndHour) return true;   // filter off
   MqlDateTime st;
   TimeToStruct(TimeCurrent(),st);
   int h=st.hour;
   bool inside;
   if(InpSessionStartHour<InpSessionEndHour)
      inside=(h>=InpSessionStartHour && h<InpSessionEndHour);
   else
      inside=(h>=InpSessionStartHour || h<InpSessionEndHour);  // wraps midnight
   if(inside) return true;
   why="outside the session window "+IntegerToString(InpSessionStartHour)+":00-"+
       IntegerToString(InpSessionEndHour)+":00 server ("+IntegerToString(h)+":00 now)";
   return false;
  }

//+------------------------------------------------------------------+
//| Entries taken today, persisted with the day guard so a reload in   |
//| the middle of an overtrading session cannot reset the cap.         |
//+------------------------------------------------------------------+
int TradesToday()
  {
   string k=DayGuardKey("TRADES");
   if(!GlobalVariableCheck(k)) return 0;
   return (int)GlobalVariableGet(k);
  }

void CountOneTrade()
  {
   int n=TradesToday()+1;
   GlobalVariableSet(DayGuardKey("TRADES"),(double)n);
   GlobalVariablesFlush();
  }

//+------------------------------------------------------------------+
//| Cooldown after a LOSS. A professional does not re-enter the same   |
//| minute a stop was hit; the next setup is judged by the market, not |
//| by the need to recover. Reads the account's own history for this   |
//| magic only, and costs nothing while the input is 0.               |
//+------------------------------------------------------------------+
bool CooldownActive(string &why)
  {
   why="";
   if(InpCooldownAfterLossMin<=0) return false;
   datetime from=(datetime)((long)TimeCurrent()-(long)InpCooldownAfterLossMin*60);
   if(!HistorySelect(from,TimeCurrent())) return false;
   for(int i=HistoryDealsTotal()-1;i>=0;i--)
     {
      ulong t=HistoryDealGetTicket(i);
      if(t==0) continue;
      if((long)HistoryDealGetInteger(t,DEAL_MAGIC)!=InpMagic) continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(t,DEAL_ENTRY)!=DEAL_ENTRY_OUT) continue;
      double net=HistoryDealGetDouble(t,DEAL_PROFIT)+
                 HistoryDealGetDouble(t,DEAL_COMMISSION)+
                 HistoryDealGetDouble(t,DEAL_SWAP);
      if(net<0.0)
        {
         why="inside the "+IntegerToString(InpCooldownAfterLossMin)+
             "-minute cooldown after a losing close (net "+
             DoubleToString(net,2)+")";
         return true;
        }
      return false;   // the most recent close was not a loss
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Copy the CORE export buffers. 0 = no signal.                     |
//+------------------------------------------------------------------+
bool CopySignalBuffers(const int count)
  {
   g_last_copy_ok=false;
   if(g_handle==INVALID_HANDLE) return false;
   ArraySetAsSeries(g_dir,true);
   ArraySetAsSeries(g_entry,true);
   ArraySetAsSeries(g_sl,true);
   ArraySetAsSeries(g_tp1,true);
   ArraySetAsSeries(g_tp2,true);
   ArraySetAsSeries(g_tp3,true);
   if(CopyBuffer(g_handle,QSMC_BUF_CORE_DIR,0,count,g_dir)<count) return false;
   if(CopyBuffer(g_handle,QSMC_BUF_CORE_ENTRY,0,count,g_entry)<count) return false;
   if(CopyBuffer(g_handle,QSMC_BUF_CORE_SL,0,count,g_sl)<count) return false;
   if(CopyBuffer(g_handle,QSMC_BUF_CORE_TP1,0,count,g_tp1)<count) return false;
   if(CopyBuffer(g_handle,QSMC_BUF_CORE_TP2,0,count,g_tp2)<count) return false;
   if(CopyBuffer(g_handle,QSMC_BUF_CORE_TP3,0,count,g_tp3)<count) return false;
   g_last_copy_ok=true;
   return true;
  }

double PickTP(const int shift)
  {
   if(InpTPLevel==QSMC_TP_LEVEL3) return g_tp3[shift];
   if(InpTPLevel==QSMC_TP_LEVEL2) return g_tp2[shift];
   return g_tp1[shift];
  }

//+------------------------------------------------------------------+
//| FIXED PIP LADDER - pure price arithmetic, no order, no state.     |
//|                                                                   |
//| A "pip" is a broker convention, not a number: 1 pip is 10 points  |
//| on 5- and 3-digit FX quotes, 0.10 of price on gold (10 points on  |
//| a 2-digit XAUUSD, 100 on a 3-digit one), and there is no          |
//| convention at all for indices and crypto. Guessing silently is    |
//| how "300 pips" becomes $3 on one symbol and $300 on another, so   |
//| the choice is explicit here, printed at attach, and overridable   |
//| with InpPipPoints.                                                |
//+------------------------------------------------------------------+
double PipPointsFor(const string sym)
  {
   if(InpPipPoints>0) return (double)InpPipPoints;
   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(point<=0.0) return 0.0;
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   string u=sym;
   StringToUpper(u);
   // Gold and silver quotes are conventionally one pip = 0.10 of price, whatever
   // the number of digits the broker uses.
   if(StringFind(u,"XAU")>=0 || StringFind(u,"XAG")>=0 || StringFind(u,"GOLD")>=0 ||
      StringFind(u,"SILVER")>=0)
      return MathMax(1.0,MathRound(0.10/point));
   if(digits==3 || digits==5) return 10.0;   // FX: the fifth (or third) decimal is a point, ten of them a pip
   return 1.0;                               // indices/crypto: one point is the smallest unit the broker names
  }

// Price of "pips" from base, in the direction of the trade.
double PipsToPrice(const string sym,const double base,const int pips,const bool up)
  {
   double one=(PipPointsFor(sym)*SymbolInfoDouble(sym,SYMBOL_POINT));
   if(one<=0.0 || base<=0.0) return 0.0;
   double d=(double)pips*one;
   return NormalizeDouble(up ? base+d : base-d,(int)SymbolInfoInteger(sym,SYMBOL_DIGITS));
  }

// The TP this EA will put on the ticket: the ladder's last rung when the ladder
// is on, the indicator's own target otherwise. Kept in ONE place so the geometry
// checks, the send, and the journal line can never disagree about the target.
double PlanTP(const int shift,const double base,const bool buy)
  {
   if(!InpUseTPPips) return PickTP(shift);
   return PipsToPrice(_Symbol,base,InpTP3Pips,buy);
  }

//+------------------------------------------------------------------+
//| One candidate signal -> one decision.                            |
//+------------------------------------------------------------------+
void HandleSignal(SQsigSignal &s)
  {
   string sym=_Symbol;
   string key=SignalKey(s.bar_time,s.dir);
   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
   double bid=SymbolInfoDouble(sym,SYMBOL_BID);
   bool buy=(s.dir>0);
   double price=(buy ? ask : bid);

   if(point<=0.0 || price<=0.0)
     {
      Note(key,"no price yet");
      return;
     }

   // --- fixed pip ladder: decide the target BEFORE any geometry check, so
   // --- "no chase", RR-at-fill and the broker stops level are all measured
   // --- against the same TP that will be written on the ticket.
   if(InpUseTPPips)
     {
      double ladder_tp=PlanTP(s.shift,price,buy);
      if(ladder_tp<=0.0)
        {
         Note(key,"pip ladder produced no target (check InpTP1/2/3Pips and InpPipPoints)");
         MarkSeen(key,s.bar_time,s.dir);
         g_refused++;
         return;
        }
      s.tp=ladder_tp;
     }

   // --- permanent refusals: geometry the signal itself gets wrong ----
   if(s.sl<=0.0 || !MathIsValidNumber(s.sl))
     {
      Note(key,"signal has no stop");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   if(s.tp<=0.0 || !MathIsValidNumber(s.tp))
     {
      Note(key,"signal has no target");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   if(buy && (s.sl>=s.entry || s.tp<=s.entry))
     {
      Note(key,"BUY geometry is not (sl<entry<tp)");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   if(!buy && (s.sl<=s.entry || s.tp>=s.entry))
     {
      Note(key,"SELL geometry is not (tp<entry<sl)");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }

   double dist=MathAbs(price-s.sl);
   double dist_pts=(dist/point);
   if(dist_pts<(double)InpMinStopPoints)
     {
      Note(key,"stop is "+DoubleToString(dist_pts,0)+" pts, under the minimum");
      return;
     }
   if(dist_pts>(double)InpMaxStopPoints)
     {
      Note(key,"stop is "+DoubleToString(dist_pts,0)+" pts, over the maximum");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   // The stop must still be on the protected side of the CURRENT price.
   if(buy && s.sl>=price)
     {
      Note(key,"price already at/below the BUY stop");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   if(!buy && s.sl<=price)
     {
      Note(key,"price already at/above the SELL stop");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   // ... and the target must not already be reached (no chasing).
   if(buy && price>=s.tp)
     {
      Note(key,"BUY target already reached - not chasing");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   if(!buy && price<=s.tp)
     {
      Note(key,"SELL target already reached - not chasing");
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   // ... and the plan must still be worth taking at the price that will actually
   // be on the ticket. The indicator's RR gate measured reward:risk from ITS
   // planned entry (a zone edge); market execution can erase that edge, and
   // nothing downstream re-measured it. Transient on purpose: if price returns
   // towards the plan inside InpMaxSignalAgeBars the signal becomes tradable
   // again, and if it does not, the signal simply ages out.
   if(InpMinRRAtFill>0.0)
     {
      double reward_at_fill=MathAbs(s.tp-price);
      double risk_at_fill=MathAbs(price-s.sl);
      double rr_at_fill=(risk_at_fill>0.0 ? reward_at_fill/risk_at_fill : 0.0);
      if(rr_at_fill<InpMinRRAtFill)
        {
         Note(key,"reward:risk at the CURRENT price is "+DoubleToString(rr_at_fill,2)+
              " < InpMinRRAtFill="+DoubleToString(InpMinRRAtFill,2)+
              " - the plan was priced at "+DoubleToString(s.entry,_Digits)+", not here");
         return;
        }
     }

   // --- transient refusals: retried until the signal ages out --------
   if(!SpreadOK(sym))
     {
      Note(key,"spread above "+IntegerToString(InpMaxSpreadPoints)+" pts");
      return;
     }
   if(g_day_blocked)
     {
      Note(key,"daily loss guard is active");
      return;
     }
   // --- professional discipline: session, day cap, cooldown ----------
   // All three are TRANSIENT (no MarkSeen): the same signal may be tradable
   // once the window opens, but refusing it must not burn it.
   string dis="";
   if(!SessionOpenNow(dis))
     {
      Note(key,dis);
      return;
     }
   if(InpMaxTradesPerDay>0 && TradesToday()>=InpMaxTradesPerDay)
     {
      Note(key,"already "+IntegerToString(TradesToday())+" entr(ies) today (InpMaxTradesPerDay="+
           IntegerToString(InpMaxTradesPerDay)+")");
      return;
     }
   if(CooldownActive(dis))
     {
      Note(key,dis);
      return;
     }
   if(OpenCount(sym)>=InpMaxOpenPositions)
     {
      Note(key,"already "+IntegerToString(OpenCount(sym))+" position(s) open");
      return;
     }
   if(!StopsDistanceOK(sym,price,s.sl,s.tp))
     {
      Note(key,"broker stops level rejects this SL/TP");
      return;
     }

   double lots=CalcLots(sym,price,s.sl,buy);
   if(lots<=0.0)
     {
      Note(key,"volume resolves to 0 (risk cap, margin or broker minimum)");
      return;
     }

   // --- opposite exposure -------------------------------------------
   ulong opposite=FindOurPosition(sym,-s.dir);
   if(opposite>0 && !InpCloseOnOpposite)
     {
      Note(key,"opposite position of this magic is open");
      return;
     }

   double risk_money=0.0;
   double tick_size=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   double tick_value=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
   if(tick_size>0.0 && tick_value>0.0)
      risk_money=(dist/tick_size)*tick_value*lots;

   g_signals++;

   if(!InpEnableTrading)
     {
      Note(key,"INERT (InpEnableTrading=false)");
      MarkSeen(key,s.bar_time,s.dir);
      return;
     }
   if(InpDryRun)
     {
      Print("[QSMC_AT] DRY RUN ",DirText(s.dir)," ",sym," ",DoubleToString(lots,2),
            " lots @ ",DoubleToString(price,_Digits)," sl ",DoubleToString(s.sl,_Digits),
            " tp ",DoubleToString(s.tp,_Digits)," risk ",DoubleToString(risk_money,2),
            " | signal bar ",TimeToString(s.bar_time,TIME_DATE|TIME_MINUTES));
      MarkSeen(key,s.bar_time,s.dir);
      // DRY RUN counts too: the daily cap must be rehearsable, otherwise the
      // operator meets it for the first time with real money.
      CountOneTrade();
      g_dry++;
      return;
     }
   string env_block=TradeEnvBlock(buy);
   if(env_block!="")
     {
      Print("[QSMC_AT] REFUSED to send ",DirText(s.dir)," ",sym,": ",env_block);
      MarkSeen(key,s.bar_time,s.dir);
      g_refused++;
      return;
     }
   if(opposite>0 && InpCloseOnOpposite)
     {
      if(g_trade.PositionClose(opposite))
         Print("[QSMC_AT] closed opposite position #",IntegerToString((long)opposite));
      else
        {
         // Not a note-and-continue any more. Continuing here opened a SECOND
         // exposure with the opposite sign while the operator had asked for the
         // old one to be closed: on a hedging account that is two live positions
         // and on a netting account an order that may silently cancel the
         // exposure the EA thinks it just opened. Retry on the next poll.
         Note(key,"opposite position #"+IntegerToString((long)opposite)+
              " could not be closed (retcode "+IntegerToString((long)g_trade.ResultRetcode())+
              ") - no new position opened on top of it");
         g_refused++;
         return;
        }
     }

   bool ok=false;
   if(buy)
      ok=g_trade.Buy(lots,sym,price,s.sl,s.tp,InpTradeComment);
   else
      ok=g_trade.Sell(lots,sym,price,s.sl,s.tp,InpTradeComment);

   if(ok)
     {
      Print("[QSMC_AT] SENT ",DirText(s.dir)," ",sym," ",DoubleToString(lots,2),
            " lots @ ",DoubleToString(price,_Digits)," sl ",DoubleToString(s.sl,_Digits),
            " tp ",DoubleToString(s.tp,_Digits)," risk ",DoubleToString(risk_money,2),
            " | signal bar ",TimeToString(s.bar_time,TIME_DATE|TIME_MINUTES));
      MarkSeen(key,s.bar_time,s.dir);
      CountOneTrade();
      g_sent++;
     }
   else
     {
      uint rc=(uint)g_trade.ResultRetcode();
      Print("[QSMC_AT] ORDER FAILED ",DirText(s.dir)," ",sym," retcode=",
            IntegerToString((long)rc)," ",g_trade.ResultRetcodeDescription(),
            (RetcodeIsTransient(rc) ? " | transient: retried on the next poll"
                                    : " | permanent: this signal is abandoned"));
      // The old code MARKED THE SIGNAL SEEN HERE while its own comment said the
      // opposite ("Not marked: the next poll may succeed if the refusal was
      // transient"). One requote - the most common server answer on a fast bar -
      // therefore destroyed a valid signal for good, and the journal showed
      // "signals 1, sent 0, refused 0" with no order and no retry.
      if(!RetcodeIsTransient(rc))
        {
         // Counted as a refusal, not as "no signal": the heartbeat's "refused"
         // number used to stay 0 while orders were failing, which read as
         // "nothing was ever evaluated".
         MarkSeen(key,s.bar_time,s.dir);
         g_refused++;
        }
      else
        {
         if(key!=g_retry_key) { g_retry_key=key; g_retry_count=0; }
         g_retry_count++;
         if(g_retry_count>=(int)MathMax(1,InpOrderRetryMax))
           {
            Print("[QSMC_AT] giving up on ",key," after ",IntegerToString(g_retry_count),
                  " transient failures - the signal is marked seen so it cannot flood the server");
            MarkSeen(key,s.bar_time,s.dir);
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Poll: read the buffers, evaluate every fresh CORE signal.        |
//+------------------------------------------------------------------+
void ProcessSignals()
  {
   if(g_handle==INVALID_HANDLE) return;
   int max_age=(int)MathMax(1,InpMaxSignalAgeBars);
   int count=max_age+2;
   if(!CopySignalBuffers(count)) return;

   // Oldest first, so two signals in one window are decided in order.
   for(int shift=count-1;shift>=1;shift--)
     {
      if(g_dir[shift]==0.0) continue;
      int dir=(g_dir[shift]>0.0 ? 1 : -1);
      datetime bt=iTime(_Symbol,_Period,shift);
      if(bt<=0) continue;
      if(bt<g_start_bar) continue;              // existed before attach
      if(shift>max_age) continue;               // aged out
      string key=SignalKey(bt,dir);
      if(SeenBefore(key,bt,dir)) continue;

      SQsigSignal s;
      s.valid=true;
      s.shift=shift;
      s.bar_time=bt;
      s.dir=dir;
      s.entry=g_entry[shift];
      s.sl=g_sl[shift];
      s.tp=PickTP(shift);
      HandleSignal(s);
     }
  }

//+------------------------------------------------------------------+
//| The indicator's published verdict (v6.6.10).                     |
//| nadir2 writes QSMC_DIAG_<symbol>_<tf>_CORE / _BARS / _ARMED /     |
//| _CONF / _TIME once per closed bar. Reading them changes nothing;  |
//| a missing variable is reported as "no record", never guessed.     |
//+------------------------------------------------------------------+
string DiagVarName(const string leaf)
  {
   string prefix=QSMC_DefaultDiagPrefix();
   return (prefix==""?"":prefix+leaf);
  }

bool DiagRead(const string leaf,double &value)
  {
   string name=DiagVarName(leaf);
   if(name=="" || !GlobalVariableCheck(name)) return false;
   value=GlobalVariableGet(name);
   return true;
  }

//+------------------------------------------------------------------+
//| v6.6.11 gate profile (read-only).                                |
//| The heartbeat already names the gate that refuses most often.    |
//| That is a vote count, not a distance: it cannot say whether a     |
//| threshold is 1 point too high or the market never produced the    |
//| pattern. These lines carry the measured distance instead, so a    |
//| threshold change can be argued with a number - or refused.        |
//+------------------------------------------------------------------+
string ProfileSlotText(const int slot)
  {
   switch(slot)
     {
      case 0:  return "CONFIDENCE";
      case 1:  return "RELIABILITY";
      case 2:  return "RR1";
      case 3:  return "STOP_TOO_WIDE";
      case 23: return "CONFIDENCE";
      case 24: return "RELIABILITY";
      case 25: return "RR1";
      case 26: return "STOP_TOO_WIDE";
      case 4:  return "ANCHOR_AGE";
      case 5:  return "ANCHOR_TYPE";
      case 6:  return "CAUSAL_PATH";
      case 7:  return "LOCATION";
      case 8:  return "GEOMETRY";
      case 9:  return "SCORE";
      case 10: return "SPREAD";
      case 11: return "SWEEP_TO_DISP";
      case 12: return "DISP_TO_BREAK";
      case 13: return "DISPLACEMENT_BODY";
      case 14: return "ANCHOR_AGE";
      case 15: return "LIQUIDITY_POOL";
     }
   return "UNKNOWN";
  }

string GateProfileSuffix()
  {
   double slot=-1.0,need=0.0,bars=-1.0;
   if(!DiagRead("GP_SLOT",slot)) return "";
   string out="";
   if(DiagRead("GP_BARS",bars) && bars>=0.0)
      out+=" | profile window: "+IntegerToString((long)bars)+" closed bars since attach";
   int code=(int)MathRound(slot);
   if(code<0)
      out+=" | closest rejection: none - no candidate reached a scoring gate; no threshold in the indicator was the reason (the causal chain did not complete)";
   else if(DiagRead("GP_NEED",need) && need>0.0)
     {
      bool ratio=(code==2 || code==25 || code==3 || code==26);
      out+=" | closest rejection: "+ProfileSlotText(code)+" short by "+
           DoubleToString(need,ratio?2:1)+(ratio?" (ATR or RR, not points)":" point(s)")+
           " - the best candidate of this session was ONE input away from passing";
     }
   double conf=-1.0,rel=-1.0,rr=-1.0,anch=-1.0;
   string peaks="";
   if(DiagRead("GP_CONF",conf) && conf>=0.0) peaks+="conf "+DoubleToString(conf,0);
   if(DiagRead("GP_REL",rel) && rel>=0.0)    peaks+=(peaks==""?"":", ")+"reliability "+DoubleToString(rel,0);
   if(DiagRead("GP_RR",rr) && rr>=0.0)       peaks+=(peaks==""?"":", ")+"RR1 "+DoubleToString(rr,2);
   // GP_ANCH is a COUNT of candidates that reached the anchor gate, not an
   // anchor measurement: it must never be printed next to a threshold as if the
   // two were comparable. It is reported separately and labelled as a count.
   if(DiagRead("GP_ANCH",anch) && anch>=0.0)
      peaks+=(peaks==""?"":"; ")+"candidates that reached the anchor gate: "+IntegerToString((long)anch);
   if(peaks!="")
      out+=" | best values seen: "+peaks+" (compare the scores and the RR with the indicator's minimums)";
   return out;
  }

string DiagCodeText(const int code)
  {
   switch(code)
     {
      case 0:  return "NO_DATA - the indicator has not finished a closed-bar pass yet (still loading, or the wrong symbol/timeframe)";
      case 1:  return "CORE_PUBLISHED - a CORE signal is published on the last closed bar (if no order follows, read the skip line)";
      case 2:  return "SETUP_ARMED - a setup is armed and waiting for its retest (nothing to execute yet, by design)";
      case 3:  return "SETUP_PENDING - a setup is waiting for its closed-bar confirmation (nothing to execute yet, by design)";
      case 10: return "NO_STRUCTURE_ANCHOR - no causally valid structure anchor (no MSS/BOS/CHoCH behind a bound zone)";
      case 11: return "INCOMPLETE_CHAIN - the causal chain sweep -> displacement -> structure -> zone is not complete";
      case 12: return "NO_SWEEP - no confirmed liquidity sweep behind the displacement";
      case 13: return "NO_DISPLACEMENT - no displacement event behind the break";
      case 14: return "NO_STRUCTURE_EVENT - the structure event is missing or invalidated in the causal graph";
      case 15: return "NO_CAUSAL_ZONE - no order block / FVG is causally bound to that displacement";
      case 16: return "SWEEP_NO_POOL - the sweep has no confirmed liquidity-pool ancestor";
      case 17: return "LOCATION - the zone failed the location re-check (premium/discount or distance)";
      case 18: return "ANCHOR_RECHECK - the bound zone failed the causality re-check";
      case 19: return "LEG_GEOMETRY - the sweep/displacement leg is too weak or too close in time";
      case 20: return "RR_TOO_LOW - RR1 is below InpMinRR1 in the indicator";
      case 21: return "STOP_TOO_WIDE - the stop distance is above InpMaxStopATR";
      case 22: return "TARGET_ORDER - the targets could not be ordered before the barrier";
      case 23: return "CONFIDENCE - score below InpMinConfidenceScore in the indicator";
      case 24: return "RELIABILITY - score below InpMinReliability in the indicator";
      case 25: return "GRADE - the quality grade is below InpMinGrade";
      case 26: return "EMA_VWAP_OPPOSE - EMA200/VWAP confluence opposes this direction";
      case 27: return "SPREAD - the spread is above InpMaxSpreadPts in the indicator";
      case 28: return "TOPDOWN - the D1->M5 top-down chain blocks this direction";
      case 29: return "OWNERSHIP - another setup holds the execution lane";
      case 30: return "DIRECTION_VETO - the direction contradicts the zone role";
      case 31: return "BLACKLIST - the same idea was blacklisted after a recent invalidation";
      case 32: return "LIFECYCLE - a signal-state transition was rejected";
      case 33: return "BRANCH_ROLLBACK - the causal branch was rejected or rolled back";
      case 34: return "OTHER - some other gate in the indicator refused the candidate";
     }
   return ("UNKNOWN code "+IntegerToString((long)code)+" - this companion is older than the indicator build; copy both files and press F7");
  }
// One suffix for every heartbeat exit path, so an early return (no handle, no
// history, still warming up) still carries the indicator's own verdict instead
// of leaving the operator with half the answer.
// v6.6.14 (H6): read the CORE verdict from buffer 19 when available, fall back
// to GlobalVariables. Buffer verdict is per-bar (chronological) on the closed
// bar; buffer 0.0 means the attached indicator build does not publish it.
double ReadCoreVerdictFromBuffer()
  {
   if(g_handle==INVALID_HANDLE) return -1.0;
   double v[];
   ArraySetAsSeries(v,true);                                  // v6.6.14: dynamic array to avoid static-array warning
   int got=CopyBuffer(g_handle,QSMC_BUF_CORE_VCODE,1,1,v);   // shift 1 = last closed
   if(got!=1) return -1.0;
   if(!MathIsValidNumber(v[0]) || v[0]==0.0) return -1.0;
   return v[0];
  }
string IndicatorVerdictSuffix()
  {
   double core=-1.0;
   bool from_buffer=false;
   double bv=ReadCoreVerdictFromBuffer();
   if(bv>=0.0) { core=bv; from_buffer=true; }
   else
     {
      double gv=0.0;
      if(DiagRead("CORE",gv)) core=gv;
     }
   if(core<0.0)
      return (" | indicator verdict: no diagnostic record for "+
              IntegerToString((long)_Period)+" on this symbol - the indicator has not completed a"+
              " closed-bar pass here (not attached, not compiled, or a different symbol/timeframe)");
   string out=" | indicator verdict: "+DiagCodeText((int)MathRound(core))+
              (from_buffer?" (buffer)":" (diag)");
   double db=0.0,da=0.0,dc=0.0,dt=0.0;
   if(DiagRead("BARS",db) && DiagRead("ARMED",da) && DiagRead("CONF",dc))
      out+=" | indicator funnel: bars "+IntegerToString((long)db)+
           " armed "+IntegerToString((long)da)+
           " confirmed "+IntegerToString((long)dc);
   if(DiagRead("TIME",dt) && dt>0.0)
      out+=" | last closed bar "+TimeToString((datetime)(long)dt,TIME_DATE|TIME_MINUTES);
   // v6.6.12: which gate profile the indicator is running. A relaxed threshold
   // must never be something the operator discovers by accident, weeks later.
   double prof=-1.0;
   if(DiagRead("PROFILE",prof) && prof>=0.0)
      out+=" | indicator gate profile: "+(prof>0.5 ?
           "PRACTICAL (entry thresholds relaxed - read the indicator's init banner)" :
           "STRICT (thresholds as entered)");
   out+=GateProfileSuffix();
   return out;
  }


//+------------------------------------------------------------------+
//| One suffix that says whether the DISCIPLINE layer (not the         |
//| analysis layer) is what is holding fire. Without it an operator    |
//| sees "CORE 1, sent 0" and blames the signal.                      |
//+------------------------------------------------------------------+
string DisciplineSuffix()
  {
   string out="";
   string why="";
   if(!SessionOpenNow(why))
      out+=" | session FILTER: "+why;
   else if(InpSessionStartHour!=InpSessionEndHour)
      out+=" | session open ("+IntegerToString(InpSessionStartHour)+":00-"+
           IntegerToString(InpSessionEndHour)+":00 server)";
   if(InpMaxTradesPerDay>0)
      out+=" | entries today "+IntegerToString(TradesToday())+"/"+IntegerToString(InpMaxTradesPerDay);
   if(CooldownActive(why))
      out+=" | COOLDOWN: "+why;
   if(InpPartialCloseAtR>0.0)
      out+=" | partial "+DoubleToString(InpPartialClosePercent,0)+"% at "+
           DoubleToString(InpPartialCloseAtR,2)+"R";
   return out;
  }

//+------------------------------------------------------------------+
//| Diagnostic heartbeat. Read-only: it copies the CORE direction    |
//| buffer and prints, it never changes a gate, an order or a        |
//| position. It answers the one question a silent chart cannot:     |
//| is the indicator publishing CORE signals at all, and if so why   |
//| is each one not becoming an order? Throttled by                   |
//| InpHeartbeatSeconds; the first run fires immediately so an       |
//| operator does not wait a full interval for the first verdict.    |
//+------------------------------------------------------------------+
int PosFind(const ulong ticket)
  {
   for(int i=0;i<g_pos_n;i++)
      if(g_pos_ticket[i]==ticket) return i;
   return -1;
  }

int PosSlot(const ulong ticket)
  {
   if(g_pos_n<QSMC_AT_POS_RING) return g_pos_n++;
   return (int)(ticket%QSMC_AT_POS_RING);
  }

// One place that claims a ring slot and initialises EVERY field. Adding a field
// to the ring without adding it here is how a stale volume or rung counter
// survives from a previous position that happened to hash to the same slot.
int PosSlotInit(const ulong ticket)
  {
   int i=PosFind(ticket);
   if(i>=0) return i;
   i=PosSlot(ticket);
   g_pos_ticket[i]=ticket;
   g_pos_risk[i]=0.0;
   g_pos_partial[i]=false;
   g_pos_vol0[i]=0.0;
   g_pos_step[i]=0;
   return i;
  }

double PosRiskRemember(const ulong ticket,const double risk)
  {
   int i=PosSlotInit(ticket);
   if(risk>0.0 && g_pos_risk[i]<=0.0) g_pos_risk[i]=risk;
   return g_pos_risk[i];
  }

bool PosPartialDone(const ulong ticket)
  {
   int i=PosFind(ticket);
   return (i>=0 && g_pos_partial[i]);
  }

void PosMarkPartial(const ulong ticket,const double risk)
  {
   int i=PosSlotInit(ticket);
   if(risk>0.0 && g_pos_risk[i]<=0.0) g_pos_risk[i]=risk;
   g_pos_partial[i]=true;
  }

//+------------------------------------------------------------------+
//| Ladder state is PERSISTED in terminal globals, keyed by ticket.   |
//| The in-memory ring dies with the EA, and a reload in the middle of |
//| a trade would otherwise re-open rung 1 and bank the same 40% a      |
//| second time. A terminal global survives a reload of this EA (not a  |
//| terminal restart, which also flattens nothing - the position stays  |
//| and the volume check below still prevents a double close).          |
//+------------------------------------------------------------------+
string LadderKey(const ulong ticket,const string leaf)
  {
   return ("QSMC_AT_LAD_"+IntegerToString(InpMagic)+"_"+
           IntegerToString((long)ticket)+"_"+leaf);
  }

int PosLadderStep(const ulong ticket)
  {
   string k=LadderKey(ticket,"STEP");
   if(GlobalVariableCheck(k)) return (int)GlobalVariableGet(k);
   int i=PosFind(ticket);
   return (i<0 ? 0 : g_pos_step[i]);
  }

void PosLadderStepSet(const ulong ticket,const int step)
  {
   int i=PosSlotInit(ticket);
   g_pos_step[i]=step;
   GlobalVariableSet(LadderKey(ticket,"STEP"),(double)step);
   GlobalVariablesFlush();
  }

// Volume at first sight. Rung percentages are of THIS number, not of whatever
// is left: 40% of 0.05 is 0.02 both times, which is what the operator asked for.
double PosVolume0(const ulong ticket,const double live)
  {
   string k=LadderKey(ticket,"V0");
   if(GlobalVariableCheck(k))
     {
      double v=GlobalVariableGet(k);
      if(v>0.0)
        {
         int j=PosSlotInit(ticket);
         g_pos_vol0[j]=v;
         return v;
        }
     }
   int i=PosSlotInit(ticket);
   if(g_pos_vol0[i]<=0.0 && live>0.0)
     {
      g_pos_vol0[i]=live;
      GlobalVariableSet(k,live);
      GlobalVariablesFlush();
     }
   return g_pos_vol0[i];
  }

//+------------------------------------------------------------------+
//| Delete ladder keys whose position no longer exists. Called on init and
// deinit only: one pass over globals per attach, never per tick.
void PurgeLadderGlobals()
  {
   string pfx="QSMC_AT_LAD_"+IntegerToString(InpMagic)+"_";
   for(int i=GlobalVariablesTotal()-1;i>=0;i--)
     {
      string name=GlobalVariableName(i);
      if(StringFind(name,pfx)!=0) continue;
      string rest=StringSubstr(name,StringLen(pfx));
      int us=StringFind(rest,"_");
      if(us<=0) continue;
      ulong t=(ulong)StringToInteger(StringSubstr(rest,0,us));
      if(t==0) continue;
      if(PositionSelectByTicket(t)) continue;   // still open: keep its memory
      GlobalVariableDel(name);
     }
  }

//+------------------------------------------------------------------+
//| One rung of the fixed pip ladder.                                 |
//| Returns TRUE when the rung is DONE - either because it was banked  |
//| or because it cannot be split at this broker (a hard fact, not a   |
//| transient failure). FALSE means "try again", throttled by the      |
//| caller. It never widens anything and never closes more than asked. |
//+------------------------------------------------------------------+
bool LadderClose(const ulong ticket,const int rung,const double v0,const double live)
  {
   string sym=_Symbol;
   double vmin=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double vstep=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   if(vstep<=0.0) vstep=0.01;
   double pct=(rung<=1 ? InpTP1ClosePercent : InpTP2ClosePercent);
   pct=MathMin(100.0,MathMax(1.0,pct));
   double part=MathFloor((v0*pct/100.0)/vstep+0.0000001)*vstep;
   part=NormalizeDouble(part,3);
   if(part<=0.0)
     {
      Print("[QSMC_AT] ladder rung ",IntegerToString(rung)," skipped on #",
            IntegerToString((long)ticket),": ",DoubleToString(v0,2)," lots x ",
            DoubleToString(pct,0),"% is under one volume step ",
            DoubleToString(vstep,2)," - the position runs on to rung 3 unchanged");
      return true;
     }
   if(part>live) part=NormalizeDouble(live,3);
   double remain=NormalizeDouble(live-part,3);
   if(remain>0.0 && remain<vmin)
     {
      Print("[QSMC_AT] ladder rung ",IntegerToString(rung)," skipped on #",
            IntegerToString((long)ticket),": closing ",DoubleToString(part,2),
            " would leave ",DoubleToString(remain,2)," under the broker minimum ",
            DoubleToString(vmin,2)," - the rung is not retried");
      return true;
     }
   if(g_trade.PositionClosePartial(ticket,part))
     {
      Print("[QSMC_AT] ladder rung ",IntegerToString(rung)," BANKED ",
            DoubleToString(part,2)," lots of #",IntegerToString((long)ticket),
            " (",DoubleToString(pct,0),"% of the original ",DoubleToString(v0,2),
            "); ",DoubleToString(remain,2)," lots left | target was ",
            IntegerToString(rung<=1 ? InpTP1Pips : InpTP2Pips)," pips");
      return true;
     }
   if(ticket!=g_lad_warn_ticket || (long)(TimeCurrent()-g_lad_warn_time)>=30)
     {
      g_lad_warn_ticket=ticket;
      g_lad_warn_time=TimeCurrent();
      Print("[QSMC_AT] ladder rung ",IntegerToString(rung)," REFUSED on #",
            IntegerToString((long)ticket)," retcode=",
            IntegerToString((long)g_trade.ResultRetcode())," ",
            g_trade.ResultRetcodeDescription(),
            " - retried on the next tick, throttled to one line per 30 s");
     }
   return false;
  }

//+------------------------------------------------------------------+
//| FIXED PIP LADDER manager (InpUseTPPips).                          |
//|                                                                   |
//| Rung 1 -> close InpTP1ClosePercent of the ORIGINAL volume and put  |
//|           the stop at the entry (InpMoveSLToBEAtTP1).              |
//| Rung 2 -> close InpTP2ClosePercent of the ORIGINAL volume and put  |
//|           the stop at rung 1 (InpMoveSLToTP1AtTP2).                |
//| Rest   -> leaves at rung 3, which is the TP already on the ticket. |
//|                                                                   |
//| A gap through both rungs is handled in one pass, so a fast candle  |
//| cannot skip a banked partial. The stop only ever moves TOWARD the  |
//| profit side - never away - and only when it is still on the safe   |
//| side of the current price and above the broker's stops level.      |
//+------------------------------------------------------------------+
void ManagePipLadder(const ulong ticket,const bool buy,const double entry,
                     const double cur,const double sl,const double tp)
  {
   double l1=PipsToPrice(_Symbol,entry,InpTP1Pips,buy);
   double l2=PipsToPrice(_Symbol,entry,InpTP2Pips,buy);
   if(l1<=0.0 || l2<=0.0) return;
   double v0=PosVolume0(ticket,PositionGetDouble(POSITION_VOLUME));
   for(int guard=0;guard<2;guard++)
     {
      int step=PosLadderStep(ticket);
      if(step>=2) break;
      double lvl=(step==0 ? l1 : l2);
      if(buy ? cur<lvl : cur>lvl) break;
      double live=PositionGetDouble(POSITION_VOLUME);
      if(live<=0.0) break;
      if(!LadderClose(ticket,step+1,v0,live)) break;   // refused: retried next tick
      PosLadderStepSet(ticket,step+1);
     }
   int done=PosLadderStep(ticket);
   double want_sl=0.0;
   if(done>=2 && InpMoveSLToTP1AtTP2)      want_sl=l1;
   else if(done>=1 && InpMoveSLToBEAtTP1)  want_sl=entry;
   if(want_sl<=0.0) return;
   if(buy)
     {
      if(sl>=want_sl || want_sl>=cur) return;      // already at/past it, or it would cross price
     }
   else
     {
      if(sl<=want_sl || want_sl<=cur) return;
     }
   if(!StopsDistanceOK(_Symbol,cur,want_sl,0.0)) return;
   if(ticket==g_be_ticket && (long)(TimeCurrent()-g_be_last_try)<30) return;
   g_be_ticket=ticket;
   g_be_last_try=TimeCurrent();
   if(g_trade.PositionModify(ticket,want_sl,tp))
      Print("[QSMC_AT] ladder: stop on #",IntegerToString((long)ticket)," moved to ",
            DoubleToString(want_sl,_Digits),(done>=2 ? " (rung 1)" : " (entry)"),
            " after rung ",IntegerToString(done)," - protection only, never widened");
   else if(g_be_warned_ticket!=ticket)
     {
      g_be_warned_ticket=ticket;
      Print("[QSMC_AT] ladder stop MODIFY REFUSED on #",IntegerToString((long)ticket),
            " retcode=",IntegerToString((long)g_trade.ResultRetcode())," ",
            g_trade.ResultRetcodeDescription(),
            " | the stop is unchanged, retried every 30 s, never widened");
     }
  }

void DiagnosticHeartbeat()
  {
   if(InpHeartbeatSeconds<=0) return;
   datetime now=TimeCurrent();
   if(!g_heartbeat_first && (long)(now-g_last_heartbeat)<(long)InpHeartbeatSeconds) return;
   g_last_heartbeat=now;
   g_heartbeat_first=false;

   string mode="INERT";
   if(InpEnableTrading)
     {
      if(InpDryRun) mode="DRY RUN";
      else
        {
         string blk=TradeEnvBlock(true);
         if(blk=="") mode="ARMED";
         else        mode="BLOCKED: "+blk;
        }
     }

   if(g_handle==INVALID_HANDLE)
     {
      Print("[QSMC_AT] heartbeat: ",mode," | indicator `",InpIndicatorName,
            "` handle INVALID - not compiled or missing from MQL5\\Indicators; no signal can ever be read"+
            IndicatorVerdictSuffix());
      return;
     }
   // v6.6.10: a valid handle is not a working indicator. BarsCalculated()<0
   // means the instance exists but never calculated (its OnInit failed, the
   // symbol/timeframe has no history, or the parameters were rejected). That
   // used to be reported as "still warming up" forever, which sent the operator
   // looking at the wrong layer.
   int calc=BarsCalculated(g_handle);
   if(calc<0)
     {
      Print("[QSMC_AT] heartbeat: ",mode," | indicator `",InpIndicatorName,
            "` exists but is NOT calculating (BarsCalculated=",IntegerToString((long)calc),
            ") - its OnInit failed or its history is unavailable; read the nadir2 lines in the Experts log"+
            IndicatorVerdictSuffix());
      return;
     }
   if(!g_last_copy_ok)
     {
      Print("[QSMC_AT] heartbeat: ",mode," | indicator `",InpIndicatorName,
            "` is still warming up (",IntegerToString((long)calc),
            " bars calculated; the last CopyBuffer returned fewer bars than requested); waiting, nothing is wrong yet"+
            IndicatorVerdictSuffix());
      return;
     }

   int bars_avail=Bars(_Symbol,_Period);
   int look=MathMax(2,InpHeartbeatLookback);
   if(look>bars_avail) look=bars_avail;
   double hb_dir[];
   ArraySetAsSeries(hb_dir,true);
   int got=CopyBuffer(g_handle,QSMC_BUF_CORE_DIR,0,look,hb_dir);
   if(got<look)
     {
      Print("[QSMC_AT] heartbeat: ",mode," | indicator history not ready (",
            IntegerToString(got),"/",IntegerToString(look)," bars) - nothing to evaluate yet"+
            IndicatorVerdictSuffix());
      return;
     }

   int found=0;
   int last_shift=-1;
   double last_dir=0.0;
   for(int i=1;i<look;i++)
     {
      if(hb_dir[i]!=0.0)
        {
         found++;
         if(last_shift<0)
           {
            last_shift=i;
            last_dir=hb_dir[i];
           }
        }
     }

   string line="[QSMC_AT] heartbeat: "+mode+" | CORE signals in last "+
               IntegerToString(look)+" closed bars: "+IntegerToString(found);
   if(found==0)
     {
      // The transport is healthy; the strategy's own gate chain produced nothing.
      // Saying this out loud is the whole point: silence used to look identical
      // to a broken EA. The indicator-side blocker is named by its panel NEEDS
      // row or by switching InpGateAuditLogEveryBars on inside the indicator.
      line+=" -> the indicator published NO CORE setup, so this EA has nothing to execute (read the chart panel NEEDS row, or set InpGateAuditLogEveryBars>0 in nadir2)";
     }
   else
     {
      datetime bt=iTime(_Symbol,_Period,last_shift);
      line+=" | most recent "+(last_dir>0.0 ? "BUY" : "SELL")+" signal bar "+
            TimeToString(bt,TIME_DATE|TIME_MINUTES)+" ("+IntegerToString(last_shift)+" bars ago)";
      if(last_shift>(int)MathMax(1,InpMaxSignalAgeBars))
         line+=" - older than InpMaxSignalAgeBars="+IntegerToString(InpMaxSignalAgeBars)+", no longer tradable";
     }
   line+=" | processed "+IntegerToString(g_signals)+
         " sent "+IntegerToString(g_sent)+
         " dry "+IntegerToString(g_dry)+
         " refused "+IntegerToString(g_refused)+
         " open "+IntegerToString(OpenCount(_Symbol))+
         (g_day_blocked ? " | daily loss guard ACTIVE" : "")+
         DisciplineSuffix();
   if(g_last_note!="")
      line+=" | last skip: "+g_last_note;

   // v6.6.10: the indicator's own verdict on the last closed bar. Without it,
   // "CORE signals: 0" is a symptom with no cause; with it, the line names the
   // gate that refused the candidate (see the DIAG_TABLE block above).
   line+=IndicatorVerdictSuffix();
   Print(line);
  }

//+------------------------------------------------------------------+
//| Position management: optional partial bank at +R, then an optional |
//| break-even move. The stop never moves AWAY from the entry.        |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Small ticket ring: original R per position + "partial already      |
//| handled". Break-even overwrites the stop with entry, which erases  |
//| the risk distance the partial-close test needs, so the first sight |
//| of a ticket stores it. 16 slots is far more than one EA holds.     |
//+------------------------------------------------------------------+
void ManageOpenPositions()
  {
   if(InpBreakEvenAtR<=0.0 && InpPartialCloseAtR<=0.0 && !InpUseTPPips) return;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      long type=PositionGetInteger(POSITION_TYPE);
      bool buy=(type==POSITION_TYPE_BUY);
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl=PositionGetDouble(POSITION_SL);
      double tp=PositionGetDouble(POSITION_TP);
      double cur=(buy ? SymbolInfoDouble(_Symbol,SYMBOL_BID) : SymbolInfoDouble(_Symbol,SYMBOL_ASK));
      if(sl<=0.0 || cur<=0.0) continue;
      // The fixed pip ladder owns this position's exits when it is on: one
      // manager per position, so two rules can never close the same volume.
      if(InpUseTPPips)
        {
         ManagePipLadder(ticket,buy,entry,cur,sl,tp);
         continue;
        }
      double risk=(buy ? entry-sl : sl-entry);
      if(risk<=0.0) risk=PosRiskRemember(ticket,0.0);   // stop already at BE: use the stored R
      if(risk<=0.0) continue;
      double moved=(buy ? cur-entry : entry-cur);

      // ---- bank a partial at +InpPartialCloseAtR ---------------------
      // A discretionary professional rarely rides a full target with the whole
      // size: half comes off at the first clean R and the rest is left to run
      // with the stop at entry. Done BEFORE the break-even block so the two do
      // not fight over the same tick.
      if(InpPartialCloseAtR>0.0 && moved>=InpPartialCloseAtR*risk &&
         !PosPartialDone(ticket))
        {
         double vol=PositionGetDouble(POSITION_VOLUME);
         double vmin=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
         double vstep=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
         double pct=MathMin(95.0,MathMax(1.0,InpPartialClosePercent));
         double part=vol*pct/100.0;
         if(vstep>0.0) part=MathFloor(part/vstep+0.0000001)*vstep;
         part=NormalizeDouble(part,3);
         double remain=NormalizeDouble(vol-part,3);
         if(part<vmin || remain<vmin)
           {
            PosMarkPartial(ticket,risk);   // too small to split: never retried
            Print("[QSMC_AT] partial close skipped on #",IntegerToString((long)ticket),
                  ": ",DoubleToString(vol,2)," lots cannot be split into ",
                  DoubleToString(part,2)," + ",DoubleToString(remain,2),
                  " (broker minimum ",DoubleToString(vmin,(vstep>0.0 ? (int)MathMax(0,MathRound(-MathLog10(vstep))) : 2)),")");
           }
         else if(g_trade.PositionClosePartial(ticket,part))
           {
            PosMarkPartial(ticket,risk);
            Print("[QSMC_AT] banked ",DoubleToString(pct,0),"% (",DoubleToString(part,2),
                  " lots) of #",IntegerToString((long)ticket)," at ",
                  DoubleToString(InpPartialCloseAtR,2),"R; ",
                  DoubleToString(remain,2)," lots left with the stop at entry");
           }
         else
            Print("[QSMC_AT] partial close REFUSED on #",IntegerToString((long)ticket),
                  " retcode=",IntegerToString((long)g_trade.ResultRetcode())," ",
                  g_trade.ResultRetcodeDescription()," - retried on the next tick");
        }

      if(InpBreakEvenAtR<=0.0) continue;
      PosRiskRemember(ticket,risk);  // remember R before the stop moves to entry
      if(moved<InpBreakEvenAtR*risk) continue;
      if(buy && sl>=entry) continue;
      if(!buy && sl<=entry) continue;
      double new_sl=NormalizeDouble(entry,_Digits);
      if(!StopsDistanceOK(_Symbol,cur,new_sl,0.0)) continue;
      // One attempt per ticket per 30 s. The old loop re-sent PositionModify on
      // every tick while the broker kept refusing it and printed nothing on
      // failure, so a refused break-even looked like "the EA does not manage
      // stops" and the server was asked hundreds of times an hour.
      if(ticket==g_be_ticket && (long)(TimeCurrent()-g_be_last_try)<30) continue;
      g_be_ticket=ticket;
      g_be_last_try=TimeCurrent();
      if(g_trade.PositionModify(ticket,new_sl,tp))
         Print("[QSMC_AT] stop moved to break-even on #",IntegerToString((long)ticket));
      else if(g_be_warned_ticket!=ticket)
        {
         g_be_warned_ticket=ticket;
         Print("[QSMC_AT] break-even MODIFY REFUSED on #",IntegerToString((long)ticket),
               " retcode=",IntegerToString((long)g_trade.ResultRetcode()),
               " ",g_trade.ResultRetcodeDescription(),
               " | the stop is unchanged and is retried every 30 s, never widened");
        }
     }
  }

//+------------------------------------------------------------------+
//| Housekeeping for the terminal globals this EA owns.               |
//|                                                                   |
//| The "seen" key is one terminal global per signal, written forever |
//| and (before this) never deleted: a terminal that trades for a year |
//| accumulated thousands of them and the Globals list became un-     |
//| readable. Keys older than one day are removed on init and deinit. |
//| Keys of the CURRENT day are KEPT: they are exactly what stops a   |
//| reload from re-firing today's signals. The day-guard keys carry a |
//| different prefix and are never touched here.                      |
//+------------------------------------------------------------------+
void PurgeStaleSignalGlobals()
  {
   string pfx="QSMC_AT_"+IntegerToString(InpMagic)+"_"+KeySafe(_Symbol)+"_";
   long cutoff=(long)TimeCurrent()-86400;
   int removed=0;
   for(int i=GlobalVariablesTotal()-1;i>=0;i--)
     {
      string name=GlobalVariableName(i);
      if(StringFind(name,pfx)!=0) continue;
      string rest=StringSubstr(name,StringLen(pfx));
      int us=StringFind(rest,"_");
      if(us<=0) continue;
      long bt=(long)StringToInteger(StringSubstr(rest,0,us));
      if(bt>0 && bt<cutoff)
        {
         GlobalVariableDel(name);
         removed++;
        }
     }
   if(removed>0)
      Print("[QSMC_AT] housekeeping: removed ",IntegerToString(removed),
            " seen-key(s) older than one day");
  }

//+------------------------------------------------------------------+
//| Init / deinit                                                    |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpMagic<=0)
     {
      Print("[QSMC_AT] InpMagic must be positive - two EAs with the same magic fight each other");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpIndicatorName=="")
     {
      Print("[QSMC_AT] InpIndicatorName is empty");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpRiskPercent<0.0 || InpRiskPercent>InpMaxRiskPercent ||
      InpMaxRiskPercent<=0.0 || InpMaxRiskPercent>1.0)
     {
      Print("[QSMC_AT] risk inputs out of range: 0 <= InpRiskPercent <= InpMaxRiskPercent <= 1.0");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpMaxSignalAgeBars<1 || InpMaxOpenPositions<1 || InpPollSeconds<1)
     {
      Print("[QSMC_AT] InpMaxSignalAgeBars, InpMaxOpenPositions and InpPollSeconds must be >= 1");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpMinStopPoints<0 || InpMaxStopPoints<=InpMinStopPoints)
     {
      Print("[QSMC_AT] stop bounds are inconsistent");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpMinRRAtFill<0.0 || InpOrderRetryMax<1)
     {
      Print("[QSMC_AT] InpMinRRAtFill must be >= 0 (0 = off) and InpOrderRetryMax >= 1");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpDeviationPoints<0)
     {
      Print("[QSMC_AT] InpDeviationPoints must be >= 0 (0 = no slippage control at all)");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpUseTPPips)
     {
      if(InpTP1Pips<=0 || InpTP2Pips<=InpTP1Pips || InpTP3Pips<=InpTP2Pips)
        {
         Print("[QSMC_AT] pip ladder must satisfy 0 < InpTP1Pips < InpTP2Pips < InpTP3Pips (got ",
               IntegerToString(InpTP1Pips),"/",IntegerToString(InpTP2Pips),"/",
               IntegerToString(InpTP3Pips),")");
         return INIT_PARAMETERS_INCORRECT;
        }
      if(InpTP1ClosePercent<1.0 || InpTP1ClosePercent>95.0 ||
         InpTP2ClosePercent<1.0 || InpTP2ClosePercent>95.0 ||
         InpTP1ClosePercent+InpTP2ClosePercent>99.0)
        {
         Print("[QSMC_AT] ladder close percentages must each be 1..95 and sum to <= 99, ",
               "otherwise nothing is left to reach rung 3 (got ",
               DoubleToString(InpTP1ClosePercent,1),"% + ",
               DoubleToString(InpTP2ClosePercent,1),"% = ",
               DoubleToString(InpTP1ClosePercent+InpTP2ClosePercent,1),"%)");
         return INIT_PARAMETERS_INCORRECT;
        }
      if(PipPointsFor(_Symbol)<=0.0)
        {
         Print("[QSMC_AT] this symbol publishes no usable point size, so a pip distance cannot be computed");
         return INIT_PARAMETERS_INCORRECT;
        }
      if(InpPartialCloseAtR>0.0)
         Print("[QSMC_AT] NOTE: InpPartialCloseAtR is IGNORED while the pip ladder is on - ",
               "one exit manager per position, and the ladder is the one that owns it");
     }
   if(InpDeviationPoints>0 && InpDeviationPoints<10)
      Print("[QSMC_AT] WARNING: InpDeviationPoints=",IntegerToString(InpDeviationPoints),
            " is under 10 points - on a fast bar the server will answer requote more often than it fills");

   g_seen_n=0;
   g_last_note="";
   g_note_count=0;

   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints((ulong)MathMax(0,InpDeviationPoints));
   g_trade.SetAsyncMode(false);
   long fill=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
   if((fill&SYMBOL_FILLING_FOK)!=0)      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((fill&SYMBOL_FILLING_IOC)!=0) g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else                                  g_trade.SetTypeFilling(ORDER_FILLING_RETURN);

   // v6.6.14 hotfix: error 4802 almost always means nadir2.ex5 is NOT in
   // MQL5/Indicators/ (which is where iCustom looks for short names). Try
   // several canonical paths before giving up, and print the terminal's
   // MQL5/Indicators directory and a Files-folder listing so the operator
   // can see exactly where MT5 is searching.
   string try_paths[]={InpIndicatorName,
                       "nadir2",
                       "Indicators\\nadir2",
                       "..\\Indicators\\nadir2",
                       TerminalInfoString(TERMINAL_DATA_PATH)+"\\MQL5\\Indicators\\nadir2.ex5",
                       ""};
   int last_err=0;
   for(int pi=0;pi<ArraySize(try_paths)-1;pi++)
     {
      ResetLastError();
      g_handle=iCustom(_Symbol,_Period,try_paths[pi]);
      if(g_handle!=INVALID_HANDLE)
        {
         if(pi>0)
            Print("[QSMC_AT] indicator loaded via path '",try_paths[pi],"' (InpIndicatorName='",InpIndicatorName,"' failed); consider setting InpIndicatorName to 'nadir2'");
         break;
        }
      last_err=GetLastError();
     }
   if(g_handle==INVALID_HANDLE)
     {
      string ind_dir=TerminalInfoString(TERMINAL_DATA_PATH)+"\\MQL5\\Indicators";
      string common_dir=TerminalInfoString(TERMINAL_COMMONDATA_PATH)+"\\Files";
      Print("[QSMC_AT] could not create `",InpIndicatorName,"` iCustom handle. Last error ",
            IntegerToString(last_err)," (4802 = INDICATOR_CANNOT_CREATE / ex5 not found).");
      Print("[QSMC_AT] MT5 is searching for ",InpIndicatorName,".ex5 inside: ",ind_dir);
      Print("[QSMC_AT] ACTION: open MetaEditor -> Navigator -> Indicators -> right-click nadir2 -> Modify -> press F7. The compiled nadir2.ex5 MUST land in ",ind_dir);
      Print("[QSMC_AT] Common Files directory: ",common_dir," (not the indicator location, ignore for iCustom)");
      return INIT_FAILED;
     }
   Print("[QSMC_AT INSTANCE] authority=private iCustom DEFAULT inputs; visible Inputs NOT inherited. Default input hash and diagnostics: [QSMC_INSTANCE], ABI v2, no legacy fallback.");
   PurgeLadderGlobals();
   g_start_bar=iTime(_Symbol,_Period,0);
   if(g_start_bar<=0) g_start_bar=(datetime)TimeCurrent();
   g_day_index=-1;
   DayGuardUpdate();

   Print("[QSMC_AT] QSMC v6.614 execution companion ON | ",_Symbol," ",EnumToString((ENUM_TIMEFRAMES)_Period),
         " | magic ",IntegerToString(InpMagic),
         " | mode ",(InpLotMode==QSMC_LOT_FIXED ? "FIXED" : "RISK%"),
         " risk ",DoubleToString(MathMin(InpRiskPercent,InpMaxRiskPercent),2),"%",
         " | tp ",(InpUseTPPips ? "PIP LADDER "+IntegerToString(InpTP1Pips)+"/"+
                                 IntegerToString(InpTP2Pips)+"/"+IntegerToString(InpTP3Pips)
                               : IntegerToString((int)InpTPLevel)),
         " | break-even ",(InpUseTPPips ? "ladder-driven" : DoubleToString(InpBreakEvenAtR,2)+"R"),
         " | ",(InpEnableTrading ? (InpDryRun ? "DRY RUN" : "LIVE") : "INERT"),
         " | ",(InpDemoOnly ? "demo-only" : "demo+real"),
         " | closed-bar signals only, no martingale, no stop widening");
   if(InpEnableTrading && !InpDryRun && InpDemoOnly==false)
      Print("[QSMC_AT] WARNING: live trading on a real account is enabled. ",
            "Risk per trade is capped at ",DoubleToString(InpMaxRiskPercent,2),
            "% of equity, but no size or filter makes a strategy profitable.");

   // Print the environment verdict at attach. This is the line to read when the
   // question is "why is it not trading?" - it answers before any signal exists.
   string env=TradeEnvBlock(true);
   if(!InpEnableTrading)
      Print("[QSMC_AT] state INERT: no order can be sent. Set InpEnableTrading=true to arm.");
   else if(InpDryRun)
      Print("[QSMC_AT] state DRY RUN: orders are printed, never sent. Set InpDryRun=false to send.");
   else if(env!="")
      Print("[QSMC_AT] state BLOCKED: ",env);
   else
      Print("[QSMC_AT] state ARMED: ",(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO?
                                      "REAL account, live orders" : "demo account, live orders"),
            " | risk ",DoubleToString(MathMin(InpRiskPercent,InpMaxRiskPercent),2),
            "% of equity, max ",IntegerToString(InpMaxOpenPositions)," position(s)");

   // One line the operator can paste into a change ticket: every number that
   // bounds a loss, in the units the broker uses. If a value here is not the
   // value in the ticket, the chart is running a different preset.
   Print("[QSMC_AT] envelope: risk<= ",DoubleToString(MathMin(InpRiskPercent,InpMaxRiskPercent),2),
         "% of equity | max ",IntegerToString(InpMaxOpenPositions)," position(s)",
         " | daily loss stop ",DoubleToString(InpMaxDailyLossPercent,2),"% (persisted)",
         " | spread<= ",IntegerToString(InpMaxSpreadPoints)," pts",
         " | slippage<= ",IntegerToString(InpDeviationPoints)," pts",
         " | RR at fill>= ",DoubleToString(InpMinRRAtFill,2),
         " | stop ",IntegerToString(InpMinStopPoints),"..",IntegerToString(InpMaxStopPoints)," pts",
         " | signal age<= ",IntegerToString(InpMaxSignalAgeBars)," closed bar(s)");
   if(InpUseTPPips)
     {
      double pip_pts=PipPointsFor(_Symbol);
      double pip_px=pip_pts*SymbolInfoDouble(_Symbol,SYMBOL_POINT);
      double d1=(double)InpTP1Pips*pip_px;
      double d2=(double)InpTP2Pips*pip_px;
      double d3=(double)InpTP3Pips*pip_px;
      Print("[QSMC_AT] pip ladder ON: 1 pip = ",DoubleToString(pip_px,_Digits),
            " of price (",DoubleToString(pip_pts,0)," points) on ",_Symbol,
            " | TP1 ",IntegerToString(InpTP1Pips)," pips = ",DoubleToString(d1,_Digits),
            " | TP2 ",IntegerToString(InpTP2Pips)," pips = ",DoubleToString(d2,_Digits),
            " | TP3 ",IntegerToString(InpTP3Pips)," pips = ",DoubleToString(d3,_Digits),
            " (TP on the ticket)",
            " | closes ",DoubleToString(InpTP1ClosePercent,0),"% then ",
            DoubleToString(InpTP2ClosePercent,0),"% of the original volume, stop -> ",
            (InpMoveSLToBEAtTP1?"entry after rung 1":"unchanged after rung 1"),
            (InpMoveSLToTP1AtTP2?", rung 1 after rung 2":""));
      // The one number that decides whether a 0.05 lot is even allowed: how many
      // dollars one unit of price costs at this volume, and the widest stop the
      // 1% ceiling can pay for. Printed, because the refusal that follows is
      // otherwise indistinguishable from "the system does not trade".
      double tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      double tick_value=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
      double lots_now=(InpLotMode==QSMC_LOT_FIXED ? NormalizeLots(_Symbol,InpFixedLots) : 0.0);
      if(tick_size>0.0 && tick_value>0.0 && lots_now>0.0)
        {
         double per_price=(1.0/tick_size)*tick_value*lots_now;
         double cap_pct=MathMin(InpMaxRiskPercent,1.0);
         double cap_money=AccountInfoDouble(ACCOUNT_EQUITY)*cap_pct/100.0;
         Print("[QSMC_AT] ladder money at ",DoubleToString(lots_now,2)," lots: ",
               DoubleToString(per_price,2)," per 1.00 of price -> TP1 $",
               DoubleToString(d1*per_price,2),", TP2 $",DoubleToString(d2*per_price,2),
               ", TP3 $",DoubleToString(d3*per_price,2));
         Print("[QSMC_AT] risk check at ",DoubleToString(lots_now,2)," lots: the ",
               DoubleToString(cap_pct,2),"% ceiling is $",DoubleToString(cap_money,2),
               ", so the stop may be at most ",
               DoubleToString(cap_money/MathMax(per_price,0.0000001),_Digits),
               " of price away. A wider signal stop is REFUSED by design - lower the lot, ",
               "raise the account, or accept the refusal; never raise InpMaxRiskPercent above 1.");
        }
     }
   Print("[QSMC_AT] discipline: ",
         (InpSessionStartHour==InpSessionEndHour ? "session filter OFF" :
          "session "+IntegerToString(InpSessionStartHour)+":00-"+IntegerToString(InpSessionEndHour)+":00 server"),
         " | max entries/day ",(InpMaxTradesPerDay>0 ? IntegerToString(InpMaxTradesPerDay) : "none"),
         " | cooldown after loss ",(InpCooldownAfterLossMin>0 ? IntegerToString(InpCooldownAfterLossMin)+" min" : "off"),
         " | partial ",(InpPartialCloseAtR>0.0 ?
            DoubleToString(InpPartialClosePercent,0)+"% at "+DoubleToString(InpPartialCloseAtR,2)+"R" : "off"),
         " | break-even at ",(InpBreakEvenAtR>0.0 ? DoubleToString(InpBreakEvenAtR,2)+"R" : "off"));
   PurgeStaleSignalGlobals();

   EventSetTimer(InpPollSeconds);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   PurgeStaleSignalGlobals();   // do not leave a year of seen-keys behind
   PurgeLadderGlobals();        // and no dead ticket memory either
   if(g_handle!=INVALID_HANDLE)
     {
      IndicatorRelease(g_handle);
      g_handle=INVALID_HANDLE;
     }
   Print("[QSMC_AT] stopped (reason ",IntegerToString(reason),") | signals ",
         IntegerToString(g_signals)," sent ",IntegerToString(g_sent),
         " dry ",IntegerToString(g_dry)," refused ",IntegerToString(g_refused));
  }

void OnTick()
  {
   DayGuardUpdate();
   ProcessSignals();
   ManageOpenPositions();
   DiagnosticHeartbeat();
  }

void OnTimer()
  {
   // The timer keeps the EA responsive on a quiet symbol where no tick arrives
   // for minutes; it reads the same closed-bar buffers, so it adds no new signal.
   DayGuardUpdate();
   ProcessSignals();
   ManageOpenPositions();
   DiagnosticHeartbeat();
  }
//+------------------------------------------------------------------+

#include <QSMC/QSMC_InstanceIdentity.mqh>
