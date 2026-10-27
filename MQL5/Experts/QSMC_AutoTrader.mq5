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
//|  WHAT IT REFUSES TO DO                                            |
//|  ---------------------                                            |
//|  - It ships INERT: InpEnableTrading=false, and a first switch-on  |
//|    is still a dry run because InpDryRun=true.                     |
//|  - It refuses a real-money account while InpDemoOnly=true.        |
//|  - It refuses a signal with no stop, a stop on the wrong side, a  |
//|    stop wider than InpMaxStopPoints, or geometry the broker's     |
//|    stops level rejects. No stop means no trade, ever.             |
//|  - It refuses to exceed InpMaxRiskPercent (hard ceiling = 1% of    |
//|    equity) or InpMaxOpenPositions.                                |
//|  - It stops opening trades for the rest of the day after a        |
//|    InpMaxDailyLossPercent drawdown on equity.                     |
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
//|  3. Tick "Allow Algo Trading" in the terminal and in the EA.      |
//|  4. Leave it inert for a session and read the journal lines it    |
//|     prints (they say INERT / DRY RUN and why each signal was      |
//|     skipped). Only then decide whether InpEnableTrading=true.      |
//|  5. InpIndicatorName must match the compiled indicator file name  |
//|     ("nadir2"). If the indicator keeps InpExportSignalBuffers     |
//|     true (its default), the buffers exist; if that default is      |
//|     ever changed, this EA stops seeing signals - and the contract |
//|     test in tools/test_autotrader_contract.py fails, on purpose.  |
//+------------------------------------------------------------------+
#property copyright "KLJ / QSMC"
#property version   "6.66"
#property description "Companion execution EA for the QSMC indicator. Ships inert; no strategy claim."
#property strict

#include <Trade/Trade.mqh>

//--- Buffer indices of the CORE signal export (nadir2.mq5 OnInit).
//--- A contract test asserts the indicator still binds these exact slots.
#define QSMC_BUF_CORE_DIR    7
#define QSMC_BUF_CORE_ENTRY  8
#define QSMC_BUF_CORE_SL     9
#define QSMC_BUF_CORE_TP1   10
#define QSMC_BUF_CORE_TP2   11
#define QSMC_BUF_CORE_TP3   12

#define QSMC_AT_SEEN_RING   64

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

//--- 4. filters ------------------------------------------------------
input int    InpMaxSpreadPoints      = 30;     // refuse a signal while the spread is wider
input int    InpMaxOpenPositions     = 1;      // positions of this magic and symbol
input double InpMaxDailyLossPercent  = 3.00;   // stop for the day after this equity drawdown; 0 = off
input int    InpMaxSignalAgeBars     = 2;      // ignore a signal older than this many closed bars
input int    InpMinStopPoints        = 20;     // refuse a stop closer than this
input int    InpMaxStopPoints        = 5000;   // refuse a stop wider than this
input bool   InpCloseOnOpposite      = false;  // close this magic's position on an opposite signal

//--- 5. runtime ------------------------------------------------------
input int    InpPollSeconds          = 2;      // timer period, seconds
input bool   InpVerbose              = false;  // print every skipped signal and why

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
   return (LongToString((long)bar_time)+"|"+DirText(dir));
  }

string GlobName(const datetime bar_time,const int dir)
  {
   return ("QSMC_AT_"+LongToString(InpMagic)+"_"+LongToString((long)bar_time)+"_"+
           (dir>0 ? "B" : "S"));
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
   if(InpRealAccountConfirm!=LongToString(AccountInfoInteger(ACCOUNT_LOGIN)))
      return "real account: set InpRealAccountConfirm to this account number ("+
             LongToString(AccountInfoInteger(ACCOUNT_LOGIN))+") to allow live orders";
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
//| Day guard: a new equity high-water day resets it; a drawdown      |
//| beyond InpMaxDailyLossPercent blocks new entries until tomorrow.  |
//+------------------------------------------------------------------+
void DayGuardUpdate()
  {
   int day=(int)(TimeCurrent()/86400);
   if(day!=g_day_index)
     {
      g_day_index=day;
      g_day_start_equity=AccountInfoDouble(ACCOUNT_EQUITY);
      g_day_blocked=false;
     }
   if(InpMaxDailyLossPercent>0.0 && g_day_start_equity>0.0)
     {
      double floor_eq=g_day_start_equity*(1.0-InpMaxDailyLossPercent/100.0);
      double eq=AccountInfoDouble(ACCOUNT_EQUITY);
      if(eq<=floor_eq && !g_day_blocked)
        {
         g_day_blocked=true;
         Print("[QSMC_AT] daily loss guard: equity ",DoubleToString(eq,2),
               " <= ",DoubleToString(floor_eq,2)," - no new entries today");
        }
     }
  }

//+------------------------------------------------------------------+
//| Copy the CORE export buffers. 0 = no signal.                     |
//+------------------------------------------------------------------+
bool CopySignalBuffers(const int count)
  {
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
   return true;
  }

double PickTP(const int shift)
  {
   if(InpTPLevel==QSMC_TP_LEVEL3) return g_tp3[shift];
   if(InpTPLevel==QSMC_TP_LEVEL2) return g_tp2[shift];
   return g_tp1[shift];
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
         Print("[QSMC_AT] closed opposite position #",LongToString((long)opposite));
      else
         Note(key,"closing the opposite position failed");
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
      g_sent++;
     }
   else
     {
      Print("[QSMC_AT] ORDER FAILED retcode=",LongToString((long)g_trade.ResultRetcode()),
            " ",g_trade.ResultRetcodeDescription());
      // Not marked: the next poll may succeed if the refusal was transient.
      MarkSeen(key,s.bar_time,s.dir);
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
//| Break-even only. The stop never moves away from the entry.       |
//+------------------------------------------------------------------+
void ManageOpenPositions()
  {
   if(InpBreakEvenAtR<=0.0) return;
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
      double risk=(buy ? entry-sl : sl-entry);
      if(risk<=0.0) continue;
      double moved=(buy ? cur-entry : entry-cur);
      if(moved<InpBreakEvenAtR*risk) continue;
      if(buy && sl>=entry) continue;
      if(!buy && sl<=entry) continue;
      double new_sl=NormalizeDouble(entry,_Digits);
      if(!StopsDistanceOK(_Symbol,cur,new_sl,0.0)) continue;
      if(g_trade.PositionModify(ticket,new_sl,tp))
         Print("[QSMC_AT] stop moved to break-even on #",LongToString((long)ticket));
     }
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

   g_seen_n=0;
   g_last_note="";
   g_note_count=0;

   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints(10);
   g_trade.SetAsyncMode(false);
   long fill=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
   if((fill&SYMBOL_FILLING_FOK)!=0)      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((fill&SYMBOL_FILLING_IOC)!=0) g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else                                  g_trade.SetTypeFilling(ORDER_FILLING_RETURN);

   g_handle=iCustom(_Symbol,_Period,InpIndicatorName);
   if(g_handle==INVALID_HANDLE)
     {
      Print("[QSMC_AT] could not create an instance of `",InpIndicatorName,
            "` (error ",IntegerToString(GetLastError()),"). Copy nadir2.mq5 to MQL5\\Indicators and press F7.");
      return INIT_FAILED;
     }
   g_start_bar=iTime(_Symbol,_Period,0);
   if(g_start_bar<=0) g_start_bar=(datetime)TimeCurrent();
   g_day_index=-1;
   DayGuardUpdate();

   Print("[QSMC_AT] QSMC v6.66 execution companion ON | ",_Symbol," ",EnumToString((ENUM_TIMEFRAMES)_Period),
         " | magic ",LongToString(InpMagic),
         " | mode ",(InpLotMode==QSMC_LOT_FIXED ? "FIXED" : "RISK%"),
         " risk ",DoubleToString(MathMin(InpRiskPercent,InpMaxRiskPercent),2),"%",
         " | tp ",IntegerToString((int)InpTPLevel)," | break-even ",DoubleToString(InpBreakEvenAtR,2),"R",
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

   EventSetTimer(InpPollSeconds);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
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
  }

void OnTimer()
  {
   // The timer keeps the EA responsive on a quiet symbol where no tick arrives
   // for minutes; it reads the same closed-bar buffers, so it adds no new signal.
   DayGuardUpdate();
   ProcessSignals();
   ManageOpenPositions();
  }
//+------------------------------------------------------------------+
