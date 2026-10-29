//+------------------------------------------------------------------+
//|                                          QSMC_ScannerProbe.mq5   |
//|  PART C, PHASE 7 - the live host for QSMC_Scanners.mqh.          |
//|                                                                   |
//|  WHY THIS FILE EXISTS                                             |
//|    QSMC_Scanners.mqh was a module with no host: nothing included  |
//|    it, so nothing forced MetaEditor to compile it and nothing     |
//|    called it with real data. A header that no build touches is    |
//|    not "deferred work", it is decay waiting to happen. This       |
//|    indicator is that host: it is deliberately the smallest thing  |
//|    that exercises all four scanners (universe -> top setups ->    |
//|    momentum -> volatility -> seasonality) through the real data   |
//|    path, and it draws nothing but text so that it cannot be       |
//|    mistaken for a signal panel.                                   |
//|                                                                   |
//|  WHAT IT IS NOT                                                   |
//|    It is NOT a signal source. It ranks and describes. It never    |
//|    authorises, loosens or replaces a PART A/B gate, it places no  |
//|    order, and it opens no file. Read it as "where to look next",  |
//|    never as "what to trade". The rows are swing-derived from price |
//|    alone, not the chart's ZRE zones.                               |
//|                                                                   |
//|  WHERE THE WORK HAPPENS                                            |
//|    OnTimer only. Scan() is time-boxed (InpProbeBudgetMs) and      |
//|    resumable: if the budget runs out mid-universe the next timer  |
//|    tick continues from the cursor. OnCalculate does nothing, so   |
//|    the probe costs nothing per tick.                              |
//|                                                                   |
//|  WHAT IT CANNOT PROVE                                              |
//|    It cannot prove the arithmetic of the scanners (that is        |
//|    tools/test_scanners.py, which re-derives the same numbers in   |
//|    Python) and it cannot prove F7. Compile it yourself.           |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0
#property version   "6.613"

#include <QSMC/QSMC_Preset.mqh>
#include <QSMC/QSMC_Scanners.mqh>

//--- universe: "EURUSD:FX,GBPUSD:FX,XAUUSD:METAL,US500:INDEX"
//--- The group suffix is optional; an unsuffixed symbol is OTHER, which is the
//--- honest answer when the broker's naming has been checked by nobody.
input string   InpProbeSymbols   = "EURUSD,GBPUSD,USDJPY,XAUUSD,US500,DE40";
input ENUM_TIMEFRAMES InpProbeTF = PERIOD_CURRENT;   // chart TF for the scan
input int      InpProbeBars      = 400;               // bars per symbol
input int      InpProbeAtr       = 14;                // ATR period
input bool     InpProbeUseBias   = false;             // HTF bias as context only
input int      InpProbeTimerSec  = 5;                 // pass cadence, seconds
input int      InpProbeBudgetMs  = 30;                // Scan() time box, ms
input int      InpProbeTop       = 8;                 // rows to print
input int      InpProbeMomLB     = 20;                // momentum lookback, bars
input int      InpProbeMomHist   = 100;               // z-score window, bars
input ENUM_SEAS_BUCKET InpProbeSeasonKind = QSEAS_MONTH;
input int      InpProbeMinN      = 30;                // withhold below this n
input bool     InpProbeUtc       = false;             // UTC basis (one offset)

CTopSetupsScanner    g_setup;
CAssetScanner        g_uni;
CMomentumHeatmap     g_mom;
CVolatilityHeatmap   g_vol;
CSeasonalityScanner  g_seas;
CMarketData         *g_md=NULL;
SQsmcArbConfig       g_cfg;

ENUM_TIMEFRAMES      g_tf=PERIOD_H1;
string               g_note="";
int                  g_passes=0;
int                  g_skipped=0;

//--------------------------------------------------------------------
// "FX" -> QGRP_FX, ... unknown words stay OTHER rather than being guessed.
ENUM_ASSET_GROUP ProbeGroup(const string word)
  {
   string u=word;
   StringToUpper(u);
   if(u=="FX" || u=="FOREX")     return QGRP_FX;
   if(u=="INDEX" || u=="INDICES")return QGRP_INDEX;
   if(u=="COMMODITY" || u=="ENERGY") return QGRP_COMMODITY;
   if(u=="METAL")                return QGRP_METAL;
   if(u=="RATE" || u=="RATES" || u=="BOND") return QGRP_RATE;
   return QGRP_OTHER;
  }

//--------------------------------------------------------------------
ENUM_TIMEFRAMES ProbeTf(const ENUM_TIMEFRAMES want)
  {
   if(want==PERIOD_CURRENT) return (ENUM_TIMEFRAMES)_Period;
   return want;
  }

//--------------------------------------------------------------------
int OnInit()
  {
   g_tf=ProbeTf(InpProbeTF);

   //--- the SAME config the indicator uses, so a row here is scored with the
   //--- same thresholds the arbiter would apply. Read-only: nothing in this
   //--- probe writes into g_cfg after Build().
   CPresetManager pm;
   pm.Build(g_cfg,g_tf);

   g_md=new CMarketData();
   if(g_md==NULL) return INIT_FAILED;

   //--- universe
   g_uni.Clear();
   string parts[];
   int n=StringSplit(InpProbeSymbols,',',parts);
   for(int i=0;i<n;i++)
     {
      string s=parts[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(StringLen(s)==0) continue;
      ENUM_ASSET_GROUP grp=QGRP_OTHER;
      int c=StringFind(s,":");
      if(c>=0)
        {
         grp=ProbeGroup(StringSubstr(s,c+1));
         s=StringSubstr(s,0,c);
         StringTrimLeft(s); StringTrimRight(s);
        }
      if(!g_uni.Add(s,grp)) g_skipped++;   // duplicate, empty or over capacity
     }
   if(g_uni.Count()<=0)
     {
      g_note="universe is empty - check InpProbeSymbols";
      Print("[QSMC_SCAN] ",g_note);
      return INIT_FAILED;
     }

   g_setup.Init(&g_uni,g_cfg,g_tf,InpProbeBars,InpProbeAtr,InpProbeUseBias);
   g_setup.BeginPass();
   g_mom.SetLookback(InpProbeMomLB);
   g_mom.SetHistory(InpProbeMomHist);
   g_seas.SetMinN(InpProbeMinN);
   g_seas.SetBasis(InpProbeUtc?QTB_UTC:QTB_SERVER);

   EventSetTimer((int)MathMax(1,InpProbeTimerSec));
   Print("[QSMC_SCAN] probe ON | ",g_uni.Count()," symbols | tf ",
         EnumToString(g_tf)," | bars ",IntegerToString(InpProbeBars),
         " | budget ",IntegerToString(InpProbeBudgetMs),"ms | basis ",
         (InpProbeUtc?"UTC":"SERVER"),
         " | observational only, no gate is decided here");
   return INIT_SUCCEEDED;
  }

//--------------------------------------------------------------------
void OnDeinit(const int reason)
  {
   EventKillTimer();
   g_setup.Shutdown();
   if(g_md!=NULL)
     {
      int a=g_md.AllocCalls(),f=g_md.FreeCalls();
      delete g_md;
      g_md=NULL;
      Print("[QSMC_SCAN] probe OFF after ",IntegerToString(g_passes),
            " pass(es) | alloc/free ",IntegerToString(a),"/",IntegerToString(f),
            (a==f?" => no leak":" => UNBALANCED, report this"));
     }
   else
      Print("[QSMC_SCAN] probe OFF after ",IntegerToString(g_passes)," pass(es)");
   Comment("");
  }

//--------------------------------------------------------------------
// Nothing per tick, on purpose: see the header of QSMC_Scanners.mqh.
int OnCalculate(const int rates_total,const int prev_calculated,
                const int begin,const double &price[])
  {
   return prev_calculated;
  }

//--------------------------------------------------------------------
void RenderSetupTable(string &txt)
  {
   int rows=g_setup.Rows();
   int shown=0;
   int top=(int)MathMax(1,MathMin(64,InpProbeTop));
   txt+="top setups by EVIDENCE SCORE (a ranking, not a signal):\n";
   for(int i=0;i<rows && shown<top;i++)
     {
      SSetupRow r;
      if(!g_setup.Row(i,r)) continue;
      if(r.status!=QSS_OK) continue;
      txt+=StringFormat("  %2d. %-12s %s  score %3d  %s  RR %.2f  n=%s\n",
                         shown+1,r.symbol,QScanGroupName(r.group),r.score,
                         (r.dir>0?"BUY-side":"SELL-side"),r.rr,r.zone_id);
      txt+=StringFormat("      zone %.5f-%.5f  strength %d  as of %s\n",
                         r.zone_lo,r.zone_hi,r.zone_strength,
                         TimeToString(r.as_of,TIME_DATE|TIME_MINUTES));
      if(r.evidence!="") txt+="      evidence: "+r.evidence+"\n";
      if(r.missing!="")  txt+="      missing:  "+r.missing+"\n";
      if(r.state!="")    txt+="      state:    "+r.state+"\n";
      shown++;
     }
   if(shown==0) txt+="  (no scannable setup in this pass - the rows below say why)\n";

   //--- every symbol that produced nothing is listed with its reason. Dropping
   //--- them would make an empty table look like "no opportunities".
   txt+="\nnot shown, and why:\n";
   for(int i=0;i<rows;i++)
     {
      SSetupRow r;
      if(!g_setup.Row(i,r)) continue;
      if(r.status==QSS_OK) continue;
      txt+=StringFormat("  %-12s %-18s %s\n",r.symbol,QScanStatusName(r.status),
                         r.note);
     }
  }

//--------------------------------------------------------------------
void RenderHeatmaps(string &txt)
  {
   if(g_md==NULL) return;
   if(!g_md.Init(_Symbol,g_tf,PERIOD_M1,(int)MathMax(120,InpProbeBars),InpProbeAtr))
     { txt+="\nheatmaps: market data init failed\n"; return; }
   if(!g_md.RefreshAll(0.0))
     { txt+="\nheatmaps: "+g_md.Reason()+"\n"; return; }

   const CBarSeries *ch=g_md.Chart();
   if(ch==NULL || !ch.Ready())
     { txt+="\nheatmaps: chart series not ready\n"; return; }

   //--- The heatmaps run on THIS chart's symbol only. The module holds one
   //--- CBarSeries per Evaluate() call and the probe owns one CMarketData, so a
   //--- universe-wide heatmap would mean one RefreshAll per symbol per tick -
   //--- a cost this file refuses to pay silently. It is a limitation, stated.
   g_mom.BeginPass();
   g_mom.Evaluate(_Symbol,QGRP_OTHER,*ch);
   g_vol.BeginPass();
   g_vol.Evaluate(_Symbol,QGRP_OTHER,*ch);

   txt+="\nmomentum ("+IntegerToString(g_mom.Lookback())+"-bar ROC, z-scored vs its own "
       +IntegerToString(g_mom.History())+" bars) - this chart only:\n";
   for(int i=0;i<g_mom.Rows();i++)
     {
      SMomentumRow m;
      if(!g_mom.Row(i,m)) continue;
      if(!m.valid) { txt+="  "+m.symbol+": "+m.note+"\n"; continue; }
      txt+=StringFormat("  %-12s ROC %+6.2f%%  ATR-normalised %+6.2f  z %+5.2f\n",
                         m.symbol,m.roc_pct,m.roc_atr,m.zscore);
     }
   txt+="  legend: "+g_mom.Legend()+"\n";

   txt+="\nvolatility regime (ATR percentile, own buckets - a second opinion, "
       "not the host's classifier):\n";
   for(int i=0;i<g_vol.Rows();i++)
     {
      SVolatilityRow v;
      if(!g_vol.Row(i,v)) continue;
      txt+=StringFormat("  %-12s ATR %5.2f%% of price  pct100 %5.1f  pct250 %5.1f  %s\n",
                         v.symbol,v.atr_pct,v.pct100,v.pct250,v.regime);
      if(v.note!="") txt+="      note: "+v.note+"\n";
     }
   txt+="  legend: "+g_vol.Legend()+"\n";

   txt+="\nseasonality - DESCRIPTIVE HISTORY over the loaded bars, not a forecast:\n";
   g_seas.Accumulate(*ch,InpProbeSeasonKind);
   int nb=g_seas.Buckets();
   int shown=0;
   for(int b=0;b<nb;b++)
     {
      SSeasonRow sr;
      if(!g_seas.Row(b,sr)) continue;
      if(sr.n<=0) continue;
      txt+=StringFormat("  %-6s n=%4d yrs=%2d mean %+7.3f%%  median %+7.3f%%  "
                         "std %6.3f%%  pos %5.1f%%  %s\n",
                         QSeasBucketName(b,InpProbeSeasonKind),sr.n,sr.years,
                         sr.mean_ret,sr.median_ret,sr.std_ret,sr.pos_share,
                         (sr.withheld?g_seas.WithheldNote(sr):""));
      shown++;
     }
   if(shown==0) txt+="  (every bucket is below the minimum n - nothing is printed "
                     "rather than printed unreliably)\n";
   txt+="  "+g_seas.Disclaimer()+"\n";
  }

//--------------------------------------------------------------------
void OnTimer()
  {
   bool done=g_setup.Scan((ulong)MathMax(1,InpProbeBudgetMs));
   if(!done)
     {
      Comment("[QSMC_SCAN] pass in progress - "+IntegerToString(g_setup.Rows())+
              " of "+IntegerToString(g_uni.Count())+" symbols, "+
              IntegerToString(InpProbeBudgetMs)+"ms per timer tick\n"+
              "This table is a ranking by evidence; no gate is decided here.");
      return;
     }

   g_setup.SortByScore();
   g_passes++;

   string txt="";
   RenderSetupTable(txt);
   RenderHeatmaps(txt);
   g_setup.BeginPass();

   txt+="\nprobe "+IntegerToString(g_passes)+" pass(es) | universe "+
        IntegerToString(g_uni.Count())+" | rows "+IntegerToString(g_setup.Rows())+
        " | scannable "+IntegerToString(g_setup.SetupCount())+
        (g_skipped>0?(" | skipped at Add(): "+IntegerToString(g_skipped)):"")+
        "\n"+(g_note!=""?("note: "+g_note+"\n"):"")+
        "OBSERVATIONAL ONLY: not a signal, not a probability, not an order.";
   Comment(txt);
  }
//+------------------------------------------------------------------+
