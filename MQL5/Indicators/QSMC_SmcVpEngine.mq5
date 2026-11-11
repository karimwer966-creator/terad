//+------------------------------------------------------------------+
//|                                             QSMC_SmcVpEngine.mq5 |
//|  QSMC - unified SMC + Volume Profile decision engine (v1.00)      |
//|                                                                   |
//|  H4 bias -> H1 structure -> M15 liquidity -> liquidity sweep ->   |
//|  displacement -> BOS/CHoCH -> OB/FVG -> volume profile -> entry   |
//|  validation -> risk/reward  =>  BUY SETUP / SELL SETUP / WAIT     |
//|                                                                   |
//|  WHAT IT IS                                                       |
//|  A thin host for the QSMC_Svp* include modules. All analysis runs |
//|  on CLOSED M15 / H1 / H4 bars of the chart symbol, whatever the   |
//|  chart timeframe, exactly once per closed M15 bar. Between two    |
//|  M15 closes it does nothing: no recalculation, no object touched. |
//|                                                                   |
//|  WHAT IT DRAWS (every object through the Chart Object Manager)    |
//|   primary    compact dashboard, tracked setup, entry zone, SL/TP  |
//|   secondary  last BOS/CHoCH per timeframe, nearest intact         |
//|              liquidity, nearest active OB/FVG                     |
//|   volume     POC, VAH, VAL, selected HVN / LVN                    |
//|   detail     volume histogram (off by default)                    |
//|   optional   finished signals, old sweeps, older structure (off)  |
//|  Its objects are named QSVP_*; it never touches any other object. |
//|                                                                   |
//|  WHAT IT IS NOT                                                   |
//|  It places no order and reads no account. The volume profile is   |
//|  built from the broker's TICK volume unless real volume is asked  |
//|  for and present - it is not centralized exchange volume and not  |
//|  bid/ask order flow. A setup is a description of conditions that  |
//|  held on closed bars; it is not a forecast and carries no         |
//|  statement about profitability.                                   |
//|                                                                   |
//|  Buffers (DRAW_NONE, for the Data Window and iCustom/CopyBuffer), |
//|  written on the newest CLOSED chart bar with the decision of the  |
//|  newest closed M15 bar:                                           |
//|   0 decision (+1 BUY SETUP, -1 SELL SETUP, 0 WAIT)                |
//|   1 entry   2 stop loss   3 take profit   4 risk:reward           |
//|  Bars before the indicator was attached stay empty: the buffers   |
//|  are a live feed, not a back-filled history.                      |
//+------------------------------------------------------------------+
#property copyright "QSMC"
#property version   "1.00"
#property description "QSMC unified SMC + Volume Profile engine: H4 bias, H1 structure, M15 liquidity, sweep classification,"
#property description "OB/FVG lifecycle, POC/VAH/VAL/HVN/LVN, one BUY SETUP / SELL SETUP / WAIT decision. Display only: no orders."
#property indicator_chart_window
#property indicator_buffers 5
#property indicator_plots   5
#property indicator_label1  "Decision (+1 BUY SETUP, -1 SELL SETUP, 0 WAIT)"
#property indicator_type1   DRAW_NONE
#property indicator_label2  "Entry"
#property indicator_type2   DRAW_NONE
#property indicator_label3  "Stop loss"
#property indicator_type3   DRAW_NONE
#property indicator_label4  "Take profit"
#property indicator_type4   DRAW_NONE
#property indicator_label5  "Risk:Reward"
#property indicator_type5   DRAW_NONE

#include <QSMC/QSMC_SvpChart.mqh>

#define SVE_VERSION "1.00"
#define SVE_PREFIX  "QSVP_"

input group "====== Market structure (closed bars, no moving average) ======"
input int    InpSveH4Swing          = 3;     // H4 pivot: bars each side
input int    InpSveH1SwingExt       = 5;     // H1 external (major) pivot: bars each side
input int    InpSveH1SwingInt       = 2;     // H1 internal pivot: bars each side
input int    InpSveM15Swing         = 3;     // M15 pivot (liquidity and M15 structure)
input int    InpSveAtrPeriod        = 14;    // ATR period (M15)
input group "====== M15 liquidity map ======"
input int    InpSveLiqLookback      = 320;   // M15 bars searched for resting liquidity
input double InpSveEqTolATR         = 0.10;  // Equal highs / lows tolerance (ATR)
input double InpSveLiqMergeATR      = 0.25;  // Merge nearby levels into one zone (ATR)
input int    InpSveLiqTolTicks      = 5;     // Floor for both tolerances (ticks)
input group "====== Liquidity sweep engine ======"
input double InpSvePenMinATR        = 0.02;  // Minimum penetration to count as taken (ATR)
input int    InpSvePenMinTicks      = 2;     // Minimum penetration (ticks)
input double InpSvePenMaxATR        = 1.50;  // Deeper than this is a breakout attempt (ATR)
input double InpSveRejectMin        = 0.50;  // Minimum rejection of the taking bar (0-1)
input int    InpSveConfirmBars      = 8;     // Bars allowed for displacement + structure shift
input int    InpSveAcceptBars       = 3;     // Consecutive closes beyond the level = breakout
input double InpSveAcceptATR        = 0.05;  // Buffer for "closed beyond" (ATR)
input int    InpSveSweepMaxAge      = 32;    // An older event no longer drives a setup (bars)
input group "====== Displacement / order blocks / fair value gaps ======"
input double InpSveDispBodyATR      = 1.00;  // Displacement body (multiple of the previous ATR)
input double InpSveDispBodyRatio    = 0.60;  // Displacement body / range
input int    InpSveObLookback       = 5;     // Bars searched back for the order-block candle
input double InpSveFvgMinATR        = 0.10;  // Minimum fair value gap (ATR)
input int    InpSveZoneMaxAge       = 96;    // Zones older than this expire (bars)
input double InpSveZoneMergeATR     = 0.10;  // Merge an OB with the FVG of the same leg (ATR)
input int    InpSveZoneValidateBars = 6;     // Bars for a structure break to back an OB
input group "====== Volume profile (context only, never a signal) ======"
input ENUM_SVP_VP_KIND InpSveProfileKind = SVP_VP_DAILY; // Profile: session / daily / weekly / visible range
input double InpSveValueAreaPct     = 70.0;  // Value area (percent of volume)
input double InpSveRowATR           = 0.10;  // Row height (ATR at the window open)
input int    InpSveRowTicks         = 0;     // Fixed row height in ticks (0 = ATR)
input int    InpSveProfileMinBars   = 16;    // A thinner developing profile defers to the previous one
input double InpSveHvnFraction      = 0.70;  // HVN: at least this share of the POC row
input double InpSveLvnFraction      = 0.50;  // LVN: at most this share of the median row
input bool   InpSveUseRealVolume    = false; // Use real volume when present on EVERY bar (else tick volume)
input double InpSveVpTolATR         = 0.15;  // Level tolerance (ATR)
input int    InpSveVpAcceptBars     = 3;     // Closes that count as acceptance
input bool   InpSveVpRequired       = true;  // A setup needs supportive volume context
input int    InpSveAsiaStart        = 0;     // Session profile: Asia start (server hour)
input int    InpSveLondonStart      = 7;     // Session profile: London start (server hour)
input int    InpSveNYStart          = 13;    // Session profile: New York start (server hour)
input int    InpSveNYEnd            = 22;    // Session profile: New York end (server hour)
input group "====== Entry / stop / target ======"
input int    InpSveEntryValidBars   = 2;     // A confirmed retest stays actionable (bars)
input double InpSveMaxChaseATR      = 1.00;  // Further than this from the zone = missed (ATR)
input double InpSveSlBufferATR      = 0.20;  // Stop buffer beyond the structure (ATR)
input double InpSveMinRR            = 2.00;  // Minimum reward : risk to a REAL level
input group "====== History ======"
input int    InpSveM15Bars          = 1500;  // M15 closed bars analysed
input int    InpSveH1Bars           = 600;   // H1 closed bars analysed
input int    InpSveH4Bars           = 300;   // H4 closed bars analysed
input int    InpSveBackfillBars     = 96;    // M15 bars replayed at start to rebuild signal state
input group "====== Chart layers ======"
input bool   InpSveShowPrimary      = true;  // Primary: dashboard, tracked setup, entry zone, SL / TP
input bool   InpSveShowSecondary    = true;  // Secondary: BOS/CHoCH, liquidity, active OB/FVG
input bool   InpSveShowVolume       = true;  // Volume profile: POC, VAH, VAL, HVN / LVN
input bool   InpSveShowHistogram    = false; // Volume histogram (up to 40 rows)
input bool   InpSveShowOptional     = false; // Optional: finished signals, old sweeps, older structure
input bool   InpSveChartShift       = true;  // Turn Chart Shift on when it is off (captions sit right of the newest bar)
input int    InpSveLiqPerSide       = 2;     // Liquidity zones drawn per side
input int    InpSveZonesPerSide     = 2;     // OB/FVG zones drawn per side
input int    InpSveNodes            = 2;     // HVN and LVN drawn (each)
input int    InpSveLiveSignals      = 2;     // Live setups drawn in full (older live ones: one mark)
input int    InpSveHistorySignals   = 8;     // Finished signals kept (optional layer)
input int    InpSveMaxActiveBars    = 96;    // An active signal older than this expires (bars)
input group "====== Dashboard / colours ======"
input int    InpSveCorner           = 0;     // Dashboard corner (0 LU, 1 LL, 2 RL, 3 RU)
input int    InpSveX                = 10;    // Dashboard X distance
input int    InpSveY                = 20;    // Dashboard Y distance
input int    InpSveFontSize         = 9;     // Font size
input bool   InpSveShowReason       = true;  // Show the WHY row
input color  InpSveColorBull        = clrMediumSeaGreen; // Bullish
input color  InpSveColorBear        = clrTomato;         // Bearish
input color  InpSveColorNeutral     = clrSilver;         // Neutral / WAIT
input color  InpSveColorText        = clrWhite;          // Dashboard text
input color  InpSveColorPanel       = clrBlack;          // Dashboard background
input color  InpSveColorPOC         = clrGold;           // POC
input color  InpSveColorValueArea   = clrDodgerBlue;     // VAH / VAL
input color  InpSveColorLiquidity   = clrOrange;         // Liquidity
input color  InpSveColorStop        = clrCrimson;        // Stop loss
input color  InpSveColorTarget      = clrLimeGreen;      // Take profit
input group "====== Diagnostics ======"
input bool   InpSveAlerts           = false; // Alert once when a setup is confirmed
input bool   InpSveLog              = true;  // Journal: one line per decision change
input bool   InpSveRunSelfTest      = true;  // Run the numeric self-tests at start

double     g_sve_decision[];
double     g_sve_entry[];
double     g_sve_stop[];
double     g_sve_target[];
double     g_sve_rr[];
SSvpParams g_sve_params;
SSvvStyle  g_sve_style;
MqlRates   g_sve_h4[];
MqlRates   g_sve_h1[];
MqlRates   g_sve_m15[];
datetime   g_sve_done=0;          // open time of the newest closed M15 bar already analysed
datetime   g_sve_retry_at=0;      // history not ready: next tick-driven attempt
datetime   g_sve_published=0;     // chart bar that carries the current decision
bool       g_sve_started=false;   // the first full pass (with backfill) has run
bool       g_sve_force=false;     // a chart event may have moved the visible range
bool       g_sve_republish=false; // the decision changed outside OnCalculate
bool       g_sve_loading_shown=false;
int        g_sve_m15_bars=1500;
int        g_sve_h1_bars=600;
int        g_sve_h4_bars=300;
int        g_sve_backfill=96;
int        g_sve_runs=0;          // engine passes
int        g_sve_idle=0;          // OnCalculate / OnTimer calls that did nothing
string     g_sve_last_log="";

void SVE_LoadParams()
{
   SVP_DefaultParams(g_sve_params);
   g_sve_params.h4_swing=InpSveH4Swing; g_sve_params.h1_swing_ext=InpSveH1SwingExt;
   g_sve_params.h1_swing_int=InpSveH1SwingInt; g_sve_params.m15_swing=InpSveM15Swing;
   g_sve_params.atr_period=InpSveAtrPeriod;
   g_sve_params.liq_lookback=InpSveLiqLookback; g_sve_params.liq_eq_tol_atr=InpSveEqTolATR;
   g_sve_params.liq_merge_atr=InpSveLiqMergeATR; g_sve_params.liq_tol_ticks=InpSveLiqTolTicks;
   g_sve_params.sw_pen_min_atr=InpSvePenMinATR; g_sve_params.sw_pen_min_ticks=InpSvePenMinTicks;
   g_sve_params.sw_pen_max_atr=InpSvePenMaxATR; g_sve_params.sw_reject_min=InpSveRejectMin;
   g_sve_params.sw_confirm_bars=InpSveConfirmBars; g_sve_params.sw_accept_bars=InpSveAcceptBars;
   g_sve_params.sw_accept_atr=InpSveAcceptATR; g_sve_params.sw_max_age=InpSveSweepMaxAge;
   g_sve_params.disp_body_atr=InpSveDispBodyATR; g_sve_params.disp_body_ratio=InpSveDispBodyRatio;
   g_sve_params.ob_lookback=InpSveObLookback; g_sve_params.fvg_min_atr=InpSveFvgMinATR;
   g_sve_params.zone_max_age=InpSveZoneMaxAge; g_sve_params.zone_merge_atr=InpSveZoneMergeATR;
   g_sve_params.zone_validate_bars=InpSveZoneValidateBars;
   g_sve_params.vp_kind=InpSveProfileKind; g_sve_params.vp_value_fraction=InpSveValueAreaPct/100.0;
   g_sve_params.vp_row_atr=InpSveRowATR; g_sve_params.vp_row_ticks=InpSveRowTicks;
   g_sve_params.vp_min_bars=InpSveProfileMinBars; g_sve_params.vp_hvn_fraction=InpSveHvnFraction;
   g_sve_params.vp_lvn_fraction=InpSveLvnFraction; g_sve_params.vp_use_real_volume=InpSveUseRealVolume;
   g_sve_params.vp_tol_atr=InpSveVpTolATR; g_sve_params.vp_accept_bars=InpSveVpAcceptBars;
   g_sve_params.vp_required=InpSveVpRequired;
   g_sve_params.sess_asia_start=InpSveAsiaStart; g_sve_params.sess_london_start=InpSveLondonStart;
   g_sve_params.sess_ny_start=InpSveNYStart; g_sve_params.sess_ny_end=InpSveNYEnd;
   g_sve_params.entry_valid_bars=InpSveEntryValidBars; g_sve_params.entry_max_chase_atr=InpSveMaxChaseATR;
   g_sve_params.sl_buffer_atr=InpSveSlBufferATR; g_sve_params.min_rr=InpSveMinRR;
   g_sve_params.point=_Point; g_sve_params.digits=_Digits;
   g_sve_params.tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   SVP_SanitizeParams(g_sve_params);
}

// Broker-side values that can change while the terminal runs.
void SVE_RefreshSymbol()
{
   g_sve_params.min_stop_distance=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   g_sve_params.spread=(double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD)*_Point;
   if(!(g_sve_params.spread>=0.0) || !MathIsValidNumber(g_sve_params.spread)) g_sve_params.spread=0.0;
}

void SVE_LoadStyle()
{
   SVV_DefaultStyle(g_sve_style);
   g_sve_style.bull=InpSveColorBull; g_sve_style.bear=InpSveColorBear; g_sve_style.neutral=InpSveColorNeutral;
   g_sve_style.text=InpSveColorText; g_sve_style.panel_bg=InpSveColorPanel;
   g_sve_style.poc=InpSveColorPOC; g_sve_style.value_area=InpSveColorValueArea;
   g_sve_style.liquidity=InpSveColorLiquidity; g_sve_style.stop=InpSveColorStop; g_sve_style.target=InpSveColorTarget;
   g_sve_style.font_size=(InpSveFontSize<6?6:(InpSveFontSize>20?20:InpSveFontSize));
   g_sve_style.corner=(InpSveCorner<0 || InpSveCorner>3?0:InpSveCorner);
   g_sve_style.x=(InpSveX<0?0:InpSveX); g_sve_style.y=(InpSveY<0?0:InpSveY);
   g_sve_style.liq_per_side=(InpSveLiqPerSide<0?0:(InpSveLiqPerSide>6?6:InpSveLiqPerSide));
   g_sve_style.zones_per_side=(InpSveZonesPerSide<0?0:(InpSveZonesPerSide>6?6:InpSveZonesPerSide));
   g_sve_style.nodes=(InpSveNodes<0?0:(InpSveNodes>SVP_MAX_NODES?SVP_MAX_NODES:InpSveNodes));
   g_sve_style.live_signals=(InpSveLiveSignals<1?1:(InpSveLiveSignals>4?4:InpSveLiveSignals));
   g_sve_style.history_signals=(InpSveHistorySignals<0?0:(InpSveHistorySignals>32?32:InpSveHistorySignals));
   g_sve_style.max_active_bars=(InpSveMaxActiveBars<8?8:InpSveMaxActiveBars);
   g_sve_style.show_reason=InpSveShowReason;
}

void SVE_ApplyLayers()
{
   SVC_SetLayer(SVC_LAYER_PRIMARY,InpSveShowPrimary,48);
   SVC_SetLayer(SVC_LAYER_SECONDARY,InpSveShowSecondary,40);
   SVC_SetLayer(SVC_LAYER_VOLUME,InpSveShowVolume,24);
   SVC_SetLayer(SVC_LAYER_DETAIL,InpSveShowHistogram && InpSveShowVolume,48);
   SVC_SetLayer(SVC_LAYER_OPTIONAL,InpSveShowOptional,48);
}

int SVE_Clamp(const int value,const int lo,const int hi)
{
   if(value<lo) return lo;
   if(value>hi) return hi;
   return value;
}

int OnInit()
{
   SVE_LoadParams();
   SVE_RefreshSymbol();
   SVE_LoadStyle();
   g_sve_backfill=SVE_Clamp(InpSveBackfillBars,0,500);
   g_sve_m15_bars=SVE_Clamp(InpSveM15Bars,SVP_MIN_M15_BARS+g_sve_backfill+100,5000);
   g_sve_h1_bars=SVE_Clamp(InpSveH1Bars,2*SVP_MIN_H1_BARS,3000);
   g_sve_h4_bars=SVE_Clamp(InpSveH4Bars,2*SVP_MIN_H4_BARS,2000);
   SetIndexBuffer(0,g_sve_decision,INDICATOR_DATA);
   SetIndexBuffer(1,g_sve_entry,INDICATOR_DATA);
   SetIndexBuffer(2,g_sve_stop,INDICATOR_DATA);
   SetIndexBuffer(3,g_sve_target,INDICATOR_DATA);
   SetIndexBuffer(4,g_sve_rr,INDICATOR_DATA);
   for(int i=0;i<5;i++) PlotIndexSetDouble(i,PLOT_EMPTY_VALUE,EMPTY_VALUE);
   IndicatorSetString(INDICATOR_SHORTNAME,"QSMC SMC+VP Engine "+SVE_VERSION);
   SVV_ResetSignals();
   SVP_VpCacheReset();
   SVP_DecisionReset(g_svp);
   SVC_Init(SVE_PREFIX,ChartID());
   SVE_ApplyLayers();
   g_sve_done=0; g_sve_retry_at=0; g_sve_published=0;
   g_sve_started=false; g_sve_force=false; g_sve_republish=false; g_sve_loading_shown=false;
   g_sve_runs=0; g_sve_idle=0; g_sve_last_log="";
   if(InpSveRunSelfTest)
   {
      string where="";
      bool a=QSR_SelfTest(where);
      if(!a) Print("[QSVP] signal-registry self-test FAILED: ",where);
      bool b=SVP_VpSelfTest(where);
      if(!b) Print("[QSVP] volume-profile self-test FAILED: ",where);
      if(a && b) Print("[QSVP] v",SVE_VERSION," self-tests PASS (signal registry, volume profile)");
      else return INIT_FAILED;
      SVV_ResetSignals();
      SVP_VpCacheReset();
   }
   Print("[QSVP] v",SVE_VERSION," ",_Symbol," | analysis M15 + H1 + H4 on closed bars | display only, no orders | ",
         "volume source: ",(InpSveUseRealVolume?"real volume when present on every bar, else broker tick volume":"broker tick volume"));
   // The captions of the levels sit to the RIGHT of the newest bar, where no line
   // reaches them. That is the chart's right margin: without Chart Shift it does
   // not exist and the captions are outside the window (the lines, the boxes and
   // the dashboard are not affected).
   if(ChartGetInteger(0,CHART_SHIFT)==0)
   {
      if(InpSveChartShift)
      {
         ChartSetInteger(0,CHART_SHIFT,true);
         Print("[QSVP] Chart Shift was off: turned ON so the level captions (right of the newest bar) are visible. ",
               "Set InpSveChartShift=false to keep your setting.");
      }
      else
         Print("[QSVP] Chart Shift is off: the level captions sit right of the newest bar, outside the window. ",
               "Lines, zones and the dashboard are complete; press the Chart Shift button to see the captions.");
   }
   // a closed market sends no ticks: the timer finishes the start-up, then stops
   EventSetTimer(2);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   SVC_Shutdown();
}

// Visible-range profile: the window is whatever the chart currently shows.
// Returns true when the window moved.
bool SVE_UpdateVisibleRange()
{
   datetime from=0,to=0;
   if(InpSveProfileKind==SVP_VP_RANGE)
   {
      int first=(int)ChartGetInteger(0,CHART_FIRST_VISIBLE_BAR);
      int bars=(int)ChartGetInteger(0,CHART_VISIBLE_BARS);
      if(first>=0 && bars>0)
      {
         int right=first-bars+1;
         if(right<0) right=0;
         datetime a=iTime(_Symbol,_Period,first);
         datetime b=iTime(_Symbol,_Period,right);
         if(a>0 && b>=a) { from=a; to=b+(datetime)PeriodSeconds(); }
      }
   }
   bool changed=(from!=g_sve_params.vp_range_from || to!=g_sve_params.vp_range_to);
   g_sve_params.vp_range_from=from;
   g_sve_params.vp_range_to=to;
   return changed;
}

void SVE_Publish(const datetime &time[],const int rates_total)
{
   int idx=rates_total-2;
   if(idx<0 || idx>=ArraySize(g_sve_decision) || idx>=ArraySize(time)) return;
   bool known=(g_sve_started && g_svp.ready);
   g_sve_decision[idx]=(known?(double)((int)g_svp.state):EMPTY_VALUE);
   g_sve_entry[idx]=(known && g_svp.plan_valid?g_svp.entry:EMPTY_VALUE);
   g_sve_stop[idx]=(known && g_svp.plan_valid?g_svp.stop:EMPTY_VALUE);
   g_sve_target[idx]=(known && g_svp.plan_valid?g_svp.target:EMPTY_VALUE);
   g_sve_rr[idx]=(known && g_svp.plan_valid?g_svp.rr:EMPTY_VALUE);
   g_sve_published=time[idx];
   g_sve_republish=false;
}

void SVE_Journal()
{
   if(!InpSveLog) return;
   string line=g_svp.reason;
   if(g_svp.plan_valid)
      line+=" | entry "+DoubleToString(g_svp.entry,_Digits)+" SL "+DoubleToString(g_svp.stop,_Digits)+
            " TP "+DoubleToString(g_svp.target,_Digits)+" RR 1:"+DoubleToString(g_svp.rr,2);
   if(line==g_sve_last_log) return;
   g_sve_last_log=line;
   Print("[QSVP] ",TimeToString(g_svp.bar_time,TIME_DATE|TIME_MINUTES)," ",line);
}

// The dashboard while there is nothing to analyse yet: every row N/A.
void SVE_ShowLoading(const string why)
{
   SVP_DecisionReset(g_svp);
   g_svp.reason=why;
   SVV_Render(g_sve_m15,0,_Symbol,g_sve_params,g_sve_style);
}

// One engine pass for the newest closed M15 bar. Returns false while the
// history of any of the three timeframes is not available yet.
bool SVE_Pass()
{
   int n15=CopyRates(_Symbol,PERIOD_M15,1,g_sve_m15_bars,g_sve_m15);
   int n1=CopyRates(_Symbol,PERIOD_H1,1,g_sve_h1_bars,g_sve_h1);
   int n4=CopyRates(_Symbol,PERIOD_H4,1,g_sve_h4_bars,g_sve_h4);
   if(n15<=0 || n1<=0 || n4<=0)
   {
      SVE_ShowLoading("WAIT - history is loading (M15 "+IntegerToString(n15)+", H1 "+IntegerToString(n1)+
                      ", H4 "+IntegerToString(n4)+" bars)");
      return false;
   }
   SVE_RefreshSymbol();
   SVE_UpdateVisibleRange();
   if(!g_sve_started)
   {
      // rebuild the signal state the chart would have if it had been open all along:
      // replay the last bars one closed M15 bar at a time (never announced). A retry
      // after "history not ready" starts from a clean registry, never on top of a
      // half-finished replay.
      SVV_ResetSignals();
      int from=n15-g_sve_backfill;
      if(from<SVP_MIN_M15_BARS) from=SVP_MIN_M15_BARS;
      for(int k=from;k<n15;k++)
      {
         if(SVP_Analyze(g_sve_h4,n4,g_sve_h1,n1,g_sve_m15,k,g_sve_params))
            SVV_UpdateSignals(g_sve_m15,k,_Symbol,(int)PERIOD_M15,g_sve_style,false);
      }
   }
   bool ready=SVP_Analyze(g_sve_h4,n4,g_sve_h1,n1,g_sve_m15,n15,g_sve_params);
   if(ready)
   {
      SVV_UpdateSignals(g_sve_m15,n15,_Symbol,(int)PERIOD_M15,g_sve_style,InpSveAlerts && g_sve_started);
      SVV_AlignDecision(_Symbol,(int)PERIOD_M15,g_sve_params);
      // the ONE place of the whole program that talks to the operator: a setup
      // that confirmed on this closed bar, once, and only with InpSveAlerts on
      string message="";
      while(SVV_NextAnnouncement(message)) Alert(message);
   }
   SVV_Render(g_sve_m15,n15,_Symbol,g_sve_params,g_sve_style);
   SVE_Journal();
   g_sve_runs++;
   return ready;
}

// Is there anything new to know? If so run one pass. Called from OnCalculate
// (ticks) and from OnTimer (start-up in a closed market, visible-range mode).
bool SVE_Step(const bool from_timer)
{
   datetime closed=iTime(_Symbol,PERIOD_M15,1);
   bool force=false;
   if(g_sve_force)
   {
      // a chart event that did not move the window is not news
      g_sve_force=false;
      force=(closed>0 && g_sve_started && SVE_UpdateVisibleRange());
   }
   // nothing closed since the last pass: there is nothing new to know
   if(closed>0 && closed==g_sve_done && !force) return false;
   // history pending: try again, but not on every tick
   if(g_sve_retry_at>0 && !from_timer && !force && TimeCurrent()<g_sve_retry_at) return false;
   if(closed<=0)
   {
      if(!g_sve_loading_shown) SVE_ShowLoading("WAIT - M15 history is loading");
      g_sve_loading_shown=true;
      g_sve_retry_at=TimeCurrent()+5;
      return false;
   }
   bool ready=SVE_Pass();
   if(ready)
   {
      g_sve_done=closed;
      g_sve_started=true;
      g_sve_retry_at=0;
   }
   else
      g_sve_retry_at=TimeCurrent()+5;      // not ready is not "done": the same bar is analysed again
   g_sve_republish=true;
   return true;
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   if(prev_calculated==0)
   {
      ArrayInitialize(g_sve_decision,EMPTY_VALUE);
      ArrayInitialize(g_sve_entry,EMPTY_VALUE);
      ArrayInitialize(g_sve_stop,EMPTY_VALUE);
      ArrayInitialize(g_sve_target,EMPTY_VALUE);
      ArrayInitialize(g_sve_rr,EMPTY_VALUE);
      g_sve_published=0;
   }
   bool ran=SVE_Step(false);
   // the decision in force is carried on every closed chart bar, whatever the
   // chart timeframe; five buffer cells, written once per bar
   bool new_bar=(rates_total>=2 && time[rates_total-2]!=g_sve_published);
   if(ran || g_sve_republish || new_bar) SVE_Publish(time,rates_total);
   if(!ran) g_sve_idle++;
   return rates_total;
}

void OnTimer()
{
   if(!SVE_Step(true)) g_sve_idle++;
   if(g_sve_started && InpSveProfileKind!=SVP_VP_RANGE) EventKillTimer();
}

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
{
   // a visible-range profile follows the chart; every other profile ignores scrolling
   if(id==CHARTEVENT_CHART_CHANGE && InpSveProfileKind==SVP_VP_RANGE) g_sve_force=true;
}
//+------------------------------------------------------------------+
