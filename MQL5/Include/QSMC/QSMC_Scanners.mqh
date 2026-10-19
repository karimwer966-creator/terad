//+------------------------------------------------------------------+
//|                                          QSMC_Scanners.mqh       |
//|  PART C, PHASE 7 - scanners and heatmaps.                         |
//|                                                                   |
//|  EVERY MODULE HERE IS OBSERVATIONAL. None of them authorises,     |
//|  loosens or replaces a PART A/B entry gate. They rank and         |
//|  describe; they never confirm.                                    |
//|                                                                   |
//|  Source of data: MT5 only. No external feed is required and none  |
//|  is read here.                                                    |
//|                                                                   |
//|  HONESTY RULES ENFORCED IN THIS FILE                              |
//|  - Rankings are by EVIDENCE SCORE. The word "probability" appears |
//|    nowhere, and no score is presented as one.                     |
//|  - Seasonality shows n, years covered and dispersion, is          |
//|    withheld below a minimum n, and is labelled descriptive        |
//|    history - never a forecast.                                    |
//|  - A symbol that cannot be scanned is reported as MISSING / NO    |
//|    DATA with a reason. It is never silently dropped.              |
//|                                                                   |
//|  PERFORMANCE CONTRACT                                             |
//|  - Scan() is time-boxed (InpBudgetMs, default 30) and RESUMABLE:  |
//|    it keeps a cursor and returns false when the budget runs out,  |
//|    so the next OnTimer continues where it stopped.                |
//|  - Never called from OnCalculate.                                 |
//|  - Memory is O(1) in the symbol count: one CMarketData is reused  |
//|    for every symbol instead of one per symbol.                    |
//+------------------------------------------------------------------+
#ifndef __QSMC_SCANNERS_MQH__
#define __QSMC_SCANNERS_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_MarketData.mqh>
#include <QSMC/QSMC_Zones.mqh>
#include <QSMC/QSMC_Reaction.mqh>
#include <QSMC/QSMC_Bias.mqh>

#define QSC_MAX_SYMBOLS    64
#define QSC_MAX_ZONES      12     // zones kept per symbol for ranking
#define QSC_MAX_LOOKBACKS  6
#define QSC_MAX_ROWS       (QSC_MAX_SYMBOLS)
#define QSC_SEAS_MONTHS    12
#define QSC_SEAS_WEEKS     53
#define QSC_SEAS_DOW       7
#define QSC_SEAS_HOURS     24
#define QSC_SEAS_SAMPLE    512      // median sample per bucket: 512 x 64 doubles
                                    // = 256 KB static, and the bound the reservoir
                                    // in CSeasonalityScanner enforces

//--------------------------------------------------------------------
enum ENUM_ASSET_GROUP
  {
   QGRP_FX = 0,
   QGRP_INDEX = 1,
   QGRP_COMMODITY = 2,
   QGRP_METAL = 3,
   QGRP_RATE = 4,
   QGRP_OTHER = 5
  };

enum ENUM_SCAN_STATUS
  {
   QSS_PENDING = 0,    // not scanned yet this pass
   QSS_OK = 1,         // scanned, data present
   QSS_NO_SETUP = 2,   // scanned, no closed-bar setup
   QSS_MISSING = 3,    // symbol unknown to the terminal
   QSS_NOT_SYNCED = 4, // known, but history not loaded yet
   QSS_NO_DATA = 5     // known and synced, but not enough bars
  };

enum ENUM_SEAS_BUCKET
  {
   QSEAS_MONTH = 0,
   QSEAS_WEEK = 1,
   QSEAS_DOW = 2,
   QSEAS_HOUR = 3
  };

//--- UTC handling. SERVER is the bar timestamp as the broker stored it;
//--- UTC applies a single offset sampled now (see CSeasonalityScanner).
enum ENUM_TIME_BASIS
  {
   QTB_SERVER = 0,
   QTB_UTC = 1
  };

//--------------------------------------------------------------------
// One row of the top-setups table.
struct SSetupRow
  {
   string            symbol;
   ENUM_ASSET_GROUP  group;
   ENUM_SCAN_STATUS  status;
   string            note;        // why it is not scannable, or ""
   int               dir;         // +1 buy, -1 sell, 0 none
   string            state;       // text, not an enum: honest wording
   string            zone_id;
   double            zone_lo;
   double            zone_hi;
   int               zone_role;
   int               zone_strength;
   double            entry;
   double            sl;
   double            tp1;
   double            rr;
   int               score;       // EVIDENCE score 0-100, not a probability
   string            evidence;    // "+"-joined group names
   string            missing;     // groups NOT present
   datetime          as_of;       // closed bar the row describes
  };

struct SMomentumRow
  {
   string            symbol;
   ENUM_ASSET_GROUP  group;
   bool              valid;
   double            roc_pct;     // raw return over the lookback
   double            roc_atr;     // the same move, ATR-normalised
   double            zscore;      // vs this symbol's own history
   string            note;
  };

struct SVolatilityRow
  {
   string            symbol;
   ENUM_ASSET_GROUP  group;
   bool              valid;
   double            atr_pct;     // ATR as % of price
   double            pct100;      // percentile within 100 bars, 0..100
   double            pct250;      // percentile within 250 bars, 0..100
   string            regime;      // LOW / NORMAL / HIGH / EXTREME / UNKNOWN
   string            note;
  };

struct SSeasonRow
  {
   int               bucket;      // month 1-12, week 1-53, dow 0-6, hour 0-23
   int               n;           // SAMPLE SIZE - always shown
   int               years;       // distinct years covered
   double            mean_ret;    // average return in the bucket, %
   double            median_ret;
   double            std_ret;     // DISPERSION - always shown
   double            pos_share;   // share of positive observations, %
   bool              withheld;    // true when n < minimum
  };

//--------------------------------------------------------------------
string QScanGroupName(const ENUM_ASSET_GROUP g)
  {
   switch(g)
     {
      case QGRP_FX:        return "FX";
      case QGRP_INDEX:     return "Index";
      case QGRP_COMMODITY: return "Commodity";
      case QGRP_METAL:     return "Metal";
      case QGRP_RATE:      return "Rates";
      default:             return "Other";
     }
  }

string QScanStatusName(const ENUM_SCAN_STATUS s)
  {
   switch(s)
     {
      case QSS_PENDING:    return "PENDING";
      case QSS_OK:         return "OK";
      case QSS_NO_SETUP:   return "NO SETUP";
      case QSS_MISSING:    return "MISSING SYMBOL";
      case QSS_NOT_SYNCED: return "HISTORY NOT SYNCED";
      default:             return "NO DATA";
     }
  }

string QSeasBucketName(const int bucket,const ENUM_SEAS_BUCKET kind)
  {
   if(kind==QSEAS_MONTH)
     { string m[12]={"Jan","Feb","Mar","Apr","May","Jun",
                     "Jul","Aug","Sep","Oct","Nov","Dec"};
       return (bucket>=0 && bucket<12 ? m[bucket] : "?"); }   // buckets are 0-based
   if(kind==QSEAS_DOW)
     { string d[7]={"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
       return (bucket>=0 && bucket<7 ? d[bucket] : "?"); }
   if(kind==QSEAS_WEEK) return "W"+IntegerToString(bucket+1);   // display is 1-based
   return IntegerToString(bucket)+"h";
  }

//+------------------------------------------------------------------+
//| CAssetScanner - the universe.                                     |
//|                                                                   |
//| The broker's symbol naming is not standardised, so the mapping    |
//| is an INPUT, not a guess: Add() takes the broker name and the     |
//| group. A symbol the terminal does not know is reported, never     |
//| skipped in silence.                                               |
//+------------------------------------------------------------------+
class CAssetScanner
  {
private:
   struct SEntry
     {
      string            symbol;
      ENUM_ASSET_GROUP  group;
      bool              enabled;
     };
   SEntry            m_e[QSC_MAX_SYMBOLS];
   int               m_n;

public:
                     CAssetScanner() { m_n=0; }
                    ~CAssetScanner() { }

   int               Count() const { return m_n; }
   void              Clear() { m_n=0; }

   bool              Add(const string symbol,const ENUM_ASSET_GROUP group)
     {
      if(symbol=="" || m_n>=QSC_MAX_SYMBOLS) return false;
      for(int i=0;i<m_n;i++)
         if(m_e[i].symbol==symbol) return false;     // no duplicates
      m_e[m_n].symbol=symbol;
      m_e[m_n].group=group;
      m_e[m_n].enabled=true;
      m_n++;
      return true;
     }

   string            Symbol(const int i) const
     { return (i>=0 && i<m_n ? m_e[i].symbol : ""); }
   ENUM_ASSET_GROUP  Group(const int i) const
     { return (i>=0 && i<m_n ? m_e[i].group : QGRP_OTHER); }

   //--- Validate() checks the terminal, not the network. It therefore
   //--- belongs in OnTimer, not OnCalculate.
   ENUM_SCAN_STATUS  Validate(const int i,string &note)
     {
      note="";
      if(i<0 || i>=m_n) { note="index out of range"; return QSS_MISSING; }
      string s=m_e[i].symbol;
      if(!SymbolSelect(s,true))
        { note=s+" is not in this terminal's symbol list"; return QSS_MISSING; }
      long synced=0;
      if(!SeriesInfoInteger(s,(ENUM_TIMEFRAMES)_Period,SERIES_SYNCHRONIZED,synced)
         || synced==0)
        { note=s+" history is not synchronised yet"; return QSS_NOT_SYNCED; }
      return QSS_PENDING;
     }
  };

//+------------------------------------------------------------------+
//| CTopSetupsScanner                                                 |
//|                                                                   |
//| For each symbol: build swing zones from its OWN bars, run the     |
//| PART A CReactionDetector and CBiasProvider READ-ONLY over the     |
//| last CLOSED bar, and rank by evidence score.                      |
//|                                                                   |
//| IMPORTANT, AND STATED PLAINLY: the zones here are swing-derived   |
//| from price alone. They are NOT the chart's ZRE zones, which use   |
//| the host's structure/order-block/FVG machinery. This scanner is  |
//| a triage tool that tells you WHERE TO LOOK; it is not a signal   |
//| source and its rows must not be traded from.                     |
//+------------------------------------------------------------------+
class CTopSetupsScanner
  {
private:
   CAssetScanner    *m_universe;   // not owned
   CMarketData      *m_md;         // owned; REUSED for every symbol
   CZoneRegistry     m_zones;
   CReactionDetector m_react;
   CBiasProvider     m_bias;
   SQsmcArbConfig    m_cfg;
   ENUM_TIMEFRAMES   m_tf;
   int               m_bars;
   int               m_atr_period;
   int               m_pivot_left;
   int               m_pivot_right;
   double            m_zone_half_atr;
   bool              m_use_bias;

   SSetupRow         m_rows[QSC_MAX_ROWS];
   int               m_rows_n;
   int               m_cursor;
   bool              m_pass_done;
   int               m_alloc_calls;
   int               m_free_calls;

   void              SafeDeleteMd()
     { if(m_md!=NULL) { delete m_md; m_md=NULL; m_free_calls++; } }

   //--- Swing zones from price alone. Bounded: at most QSC_MAX_ZONES.
   int               BuildScanZones(const CBarSeries &bars,const double atr,
                                    SQZone &out[],int &n)
     {
      n=0;
      int ci=bars.ClosedIndex();
      if(ci<0 || !(atr>0.0)) return 0;
      int from=(int)MathMax(1,m_pivot_left);
      int to=(int)MathMax(from,ci-m_pivot_right);
      double half=m_zone_half_atr*atr;

      for(int i=to;i>=from;i--)
        {
         if(n>=QSC_MAX_ZONES) break;
         double hh=bars.HighestHigh(i-m_pivot_left,i+m_pivot_right);
         double ll=bars.LowestLow(i-m_pivot_left,i+m_pivot_right);
         if(!(hh>0.0) || !(ll>0.0)) continue;

         SQZone z;
         z.valid=true;
         z.lo=0.0; z.hi=0.0;
         if(bars.H(i)>=hh-1e-12)      { z.hi=bars.H(i)+half; z.lo=bars.H(i)-half; z.birth_role=ZR_RESISTANCE; }
         else if(bars.L(i)<=ll+1e-12){ z.hi=bars.L(i)+half; z.lo=bars.L(i)-half; z.birth_role=ZR_SUPPORT; }
         else continue;
         if(!(z.hi>z.lo)) continue;

         z.role=z.birth_role;
         //--- Strength = touch count, mapped to 0-100. It measures how
         //--- often price respected the band. It is NOT a win rate.
         int touches=0;
         for(int b=1;b<=ci;b++)
           {
            if(bars.L(b)<=z.hi && bars.H(b)>=z.lo) touches++;
           }
         z.touches=touches;
         z.strength=(int)MathMax(0.0,MathMin(100.0,20.0+8.0*(double)touches));
         z.birth_bar=i;
         z.birth_time=bars.T(i);
         z.flipped=false;
         z.broken_closed=false;
         z.broken_time=0;
         z.retested=false;
         z.state=ZST_TOUCHED;
         z.sources="SCAN-SWING";
         z.id=CZoneRegistry::MakeId(z.birth_role,z.lo,z.hi);
         out[n]=z; n++;
        }
      return n;
     }

   void              Push(const SSetupRow &r)
     { if(m_rows_n<QSC_MAX_ROWS) { m_rows[m_rows_n]=r; m_rows_n++; } }

public:
                     CTopSetupsScanner()
     { m_universe=NULL; m_md=NULL; m_tf=PERIOD_H1; m_bars=300;
       m_atr_period=14; m_pivot_left=3; m_pivot_right=3;
       m_zone_half_atr=0.25; m_use_bias=false;
       m_rows_n=0; m_cursor=0; m_pass_done=false;
       m_alloc_calls=0; m_free_calls=0; }

                    ~CTopSetupsScanner() { Shutdown(); }

   bool              Init(CAssetScanner *uni,const SQsmcArbConfig &cfg,
                          const ENUM_TIMEFRAMES tf,const int bars,
                          const int atr_period,const bool use_bias)
     {
      Shutdown();
      m_universe=uni;
      m_cfg=cfg;
      m_tf=tf;
      m_bars=(int)MathMax(120,MathMin(5000,bars));
      m_atr_period=(int)MathMax(2,MathMin(200,atr_period));
      m_use_bias=use_bias;
      m_md=new CMarketData(); m_alloc_calls++;
      return true;
     }

   void              Shutdown()
     { SafeDeleteMd(); m_rows_n=0; m_cursor=0; m_pass_done=false; }

   int               AllocCalls() const { return m_alloc_calls; }
   int               FreeCalls()  const { return m_free_calls; }
   int               Rows() const { return m_rows_n; }
   bool              PassDone() const { return m_pass_done; }

   //--- Row access. MQL5 has NO pointer to a structure - only to class objects -
   //--- so returning &m_rows[i] was never compilable. Reference-out is the form
   //--- this file already uses for CZoneRegistry::At() and for a seasonality row,
   //--- and it is the form rule D12 in tools/mql5_rules.py now enforces.
   bool              Row(const int i,SSetupRow &out) const
     { if(i<0 || i>=m_rows_n) return false; out=m_rows[i]; return true; }

   void              BeginPass()
     { m_rows_n=0; m_cursor=0; m_pass_done=false; }

   //------------------------------------------------------------------
   // Scan() - processes symbols from the cursor until the time budget
   // is spent. Returns true when the whole universe is done.
   // Resumable: call it again from the next OnTimer.
   //------------------------------------------------------------------
   bool              Scan(const ulong budget_ms)
     {
      if(m_universe==NULL || m_md==NULL) { m_pass_done=true; return true; }
      ulong t0=GetTickCount64();
      int total=m_universe.Count();

      while(m_cursor<total)
        {
         //--- Budget check BEFORE the work, so an expensive symbol can
         //--- never blow the frame.
         if(GetTickCount64()-t0>=budget_ms) return false;

         int i=m_cursor;
         m_cursor++;

         SSetupRow r;
         r.symbol=m_universe.Symbol(i);
         r.group=m_universe.Group(i);
         r.dir=0; r.score=0; r.rr=0.0;
         r.entry=0.0; r.sl=0.0; r.tp1=0.0;
         r.zone_lo=0.0; r.zone_hi=0.0; r.zone_role=0;
         r.zone_strength=0; r.zone_id=""; r.as_of=0;
         r.evidence=""; r.missing=""; r.state="";

         string note="";
         ENUM_SCAN_STATUS st=m_universe.Validate(i,note);
         if(st!=QSS_PENDING) { r.status=st; r.note=note; Push(r); continue; }

         //--- Reuse the single CMarketData for this symbol.
         if(!m_md.Init(r.symbol,m_tf,PERIOD_M1,m_bars,m_atr_period))
           { r.status=QSS_NO_DATA; r.note="market data init failed";
             Push(r); continue; }
         if(!m_md.RefreshAll(0.0))
           { r.status=QSS_NO_DATA; r.note=m_md.Reason(); Push(r); continue; }

         const CBarSeries *ch=m_md.Chart();
         if(ch==NULL || !ch.Ready())
           { r.status=QSS_NO_DATA; r.note="chart series not ready";
             Push(r); continue; }

         double atr=ch.ATR();
         if(!(atr>0.0))
           { r.status=QSS_NO_DATA; r.note="ATR unavailable"; Push(r); continue; }

         int ci=ch.ClosedIndex();
         if(ci<1)
           { r.status=QSS_NO_DATA; r.note="no closed bar"; Push(r); continue; }
         double price=ch.C(ci);
         if(!(price>0.0))
           { r.status=QSS_NO_DATA; r.note="no price"; Push(r); continue; }
         if(ch.Count()<m_cfg.min_bars)
           { r.status=QSS_NO_DATA; r.note="not enough bars"; Push(r); continue; }

         //--- Zones
         SQZone zs[QSC_MAX_ZONES]; int zn=0;
         BuildScanZones(*ch,atr,zs,zn);
         if(zn<=0)
           { r.status=QSS_NO_SETUP; r.note="no swing zone found";
             Push(r); continue; }
         m_zones.Rebuild(zs,zn,atr,m_cfg.merge_tol_atr,m_cfg.min_zone_strength);

         //--- Nearest zone to price
         SQZoneHit hit;
         if(!m_zones.Nearest(price,hit) || hit.index<0)
           { r.status=QSS_NO_SETUP; r.note="no zone in reach";
             Push(r); continue; }
         //--- The zone comes back from the REGISTRY, not from zs[]. Rebuild()  
         //--- drops invalid bands, merges nearby ones and then sorts by      
         //--- midpoint, so hit.index indexes m_zones and has NO relationship  
         //--- to the order in which the swing bands were built. Reading        
         //--- zs[hit.index] returned a plausible but different zone (band,     
         //--- role, strength and id all from another band) whenever a merge    
         //--- or a reorder happened - which is most of the time, and exactly   
         //--- the case that survives a manual glance. This is the same pattern  
         //--- the arbiter path uses in CQuantumRoot::BuildContext().             
         SQZone z;
         if(!m_zones.At(hit.index,z))
           { r.status=QSS_NO_SETUP; r.note="zone vanished between rebuild and read";
             Push(r); continue; }

         //--- Reaction on the CLOSED bar only. Shift 0 is refused by the
         //--- detector itself; this is the read-only use of PART A.
         SReactionFacts f;
         if(!m_react.Evaluate(z,*ch,ci,atr,m_cfg,m_md.Exec(),f) || !f.valid
            || f.dir==0)
           { r.status=QSS_NO_SETUP; r.note=f.summary; Push(r); continue; }

         //--- Optional HTF bias, used as CONTEXT for the row, never to
         //--- create a signal (that is the arbiter's job, not the
         //--- scanner's).
         string bias_txt="";
         if(m_use_bias)
           {
            //--- Caches on closed_index ONLY, and this scanner reuses one
            //--- provider for every symbol: two symbols with the same bar
            //--- count share a closed index, so without this Reset() the
            //--- second row would show the first symbol's bias.
            m_bias.Reset();
            m_bias.Update(*m_md,m_cfg,ci);
            bias_txt=m_bias.ShortText();
           }

         //--- Display floor, and it is only that. Score() is 0..60 evidence
         //--- points + 0..30 zone-strength points + 0..10 bounded-penetration
         //--- points, so min_evidence*10 can be reached with FEWER groups than
         //--- the arbiter's gate requires if the zone is strong. A row that
         //--- survives this line has therefore NOT passed the evidence gate, and
         //--- must not be labelled as if it had - see the gate in
         //--- CGateEvidence (QSMC_Gates.mqh), which compares evidence_count
         //--- itself and is the only place that decides.
         int score=m_react.Score(f,z.strength);
         if(score<m_cfg.min_evidence*10)
           { r.status=QSS_NO_SETUP; r.note="evidence below the display floor";
             Push(r); continue; }

         r.status=QSS_OK;
         r.dir=f.dir;
         r.zone_id=z.id;
         r.zone_lo=z.lo; r.zone_hi=z.hi;
         r.zone_role=(int)z.role;
         r.zone_strength=z.strength;
         r.entry=price;
         r.score=score;
         r.as_of=ch.T(ci);
         r.evidence=QSMC_EvidenceList(f.evidence_mask);
         r.missing=f.missing;      // already computed by the detector

         //--- Geometry uses the SAME helper the arbiter uses, with the
         //--- same zone registry, so the RR shown here is the RR the
         //--- arbiter would test. It is still only a ranking number:
         //--- the scanner does not decide anything.
         double sl=0.0,tp1=0.0,tp2=0.0,tp3=0.0,rr=0.0,room=0.0;
         double tick=SymbolInfoDouble(r.symbol,SYMBOL_TRADE_TICK_SIZE);
         if(!(tick>0.0)) tick=SymbolInfoDouble(r.symbol,SYMBOL_POINT);
         if(!(tick>0.0)) tick=_Point;
         if(QSMC_BuildGeometry(z,f.dir,price,atr,m_zones,m_cfg,tick,
                               sl,tp1,tp2,tp3,rr,room))
           { r.sl=sl; r.tp1=tp1; r.rr=rr; }

         r.state=(f.accepted ? "ACCEPTANCE" : "REJECTION");
         if(f.accepted) r.state+=" (continuation)";
         if(bias_txt!="") r.state+=" | bias "+bias_txt;
         r.note="";
         Push(r);
        }

      m_pass_done=true;
      return true;
     }

   //--- Rank by evidence score, descending. Insertion sort: the row
   //--- count is bounded and this is O(n^2) on at most 64 items.
   void              SortByScore()
     {
      for(int i=1;i<m_rows_n;i++)
        {
         SSetupRow key=m_rows[i];
         int j=i-1;
         while(j>=0 && m_rows[j].score<key.score)
           { m_rows[j+1]=m_rows[j]; j--; }
         m_rows[j+1]=key;
        }
     }

   int               SetupCount() const
     {
      int n=0;
      for(int i=0;i<m_rows_n;i++) if(m_rows[i].status==QSS_OK) n++;
      return n;
     }
  };

//+------------------------------------------------------------------+
//| CMomentumHeatmap                                                  |
//|  ROC over a selectable lookback, ATR-normalised, and z-scored     |
//|  against the symbol's OWN history (never against the universe).   |
//+------------------------------------------------------------------+
class CMomentumHeatmap
  {
private:
   SMomentumRow      m_rows[QSC_MAX_ROWS];
   int               m_rows_n;
   int               m_lookback;
   int               m_hist;      // history window for the z-score

   double            Mean(const double &a[],const int n) const
     { if(n<=0) return 0.0; double s=0.0;
       for(int i=0;i<n;i++) s+=a[i]; return s/(double)n; }

   double            StdDev(const double &a[],const int n) const
     {
      if(n<2) return 0.0;
      double mu=Mean(a,n), s=0.0;
      for(int i=0;i<n;i++){ double d=a[i]-mu; s+=d*d; }
      return MathSqrt(s/(double)(n-1));
     }

public:
                     CMomentumHeatmap()
     { m_rows_n=0; m_lookback=20; m_hist=100; }

   void              SetLookback(const int lookback)
     { m_lookback=(int)MathMax(2,MathMin(500,lookback)); }
   void              SetHistory(const int hist)
     { m_hist=(int)MathMax(10,MathMin(1000,hist)); }
   int               Lookback() const { return m_lookback; }
   int               History()  const { return m_hist; }
   int               Rows() const { return m_rows_n; }
   //--- No pointer to a struct in MQL5: reference-out (see D12).
   bool              Row(const int i,SMomentumRow &out) const
     { if(i<0 || i>=m_rows_n) return false; out=m_rows[i]; return true; }

   void              BeginPass() { m_rows_n=0; }

   bool              Evaluate(const string symbol,const ENUM_ASSET_GROUP group,
                              const CBarSeries &bars)
     {
      if(m_rows_n>=QSC_MAX_ROWS) return false;
      SMomentumRow r;
      r.symbol=symbol; r.group=group; r.valid=false;
      r.roc_pct=0.0; r.roc_atr=0.0; r.zscore=0.0; r.note="";

      int ci=bars.ClosedIndex();
      if(ci<m_lookback+2)
        { r.note="not enough bars"; m_rows[m_rows_n]=r; m_rows_n++; return false; }

      double now=bars.C(ci);
      double then=bars.C(ci-m_lookback);
      if(!(now>0.0) || !(then>0.0))
        { r.note="no price"; m_rows[m_rows_n]=r; m_rows_n++; return false; }

      r.roc_pct=(now-then)/then*100.0;

      double atr=bars.ATR();
      r.roc_atr=(atr>0.0 ? (now-then)/atr : 0.0);

      //--- z-score against this symbol's own ROC history over m_hist
      //--- bars. No look-ahead: every sample uses bars strictly at or
      //--- before the bar it describes.
      int first=(int)MathMax(m_lookback+1, ci-m_hist+1);
      int cnt=0;
      double hist[];
      int cap=ci-first+1;
      if(cap>0) ArrayResize(hist,cap);
      for(int i=first;i<=ci;i++)
        {
         double a=bars.C(i), b=bars.C(i-m_lookback);
         if(!(a>0.0) || !(b>0.0)) continue;
         hist[cnt]=(a-b)/b*100.0; cnt++;
        }
      if(cnt>=8)
        {
         double mu=Mean(hist,cnt), sd=StdDev(hist,cnt);
         //--- Degenerate-distribution guard. A near-constant series leaves
         //--- a std dev of ~1e-13 through floating-point noise, which is
         //--- >0.0 and therefore passes the obvious `sd>0.0` test - but
         //--- dividing by it turns rounding noise into an O(1) number.
         //--- (Observed: a constant +1%/bar ramp reported z = -1.13
         //--- instead of 0.) Only a std dev that is meaningfully non-zero
         //--- relative to the mean produces a z-score; otherwise 0.
         double scale=MathMax(MathAbs(mu),1e-8);
         r.zscore=(sd>scale*1e-6 ? (r.roc_pct-mu)/sd : 0.0);
         r.valid=true;
        }
      else
        r.note="n<8 for z-score";

      ArrayResize(hist,0);
      m_rows[m_rows_n]=r; m_rows_n++;
      return r.valid;
     }

   //--- 5-bucket legend, consistent with the host's colour legend.
   string            Legend() const
     { return "<= -2s   -2..-0.5   -0.5..+0.5   +0.5..+2   >= +2s"; }
  };

//+------------------------------------------------------------------+
//| CVolatilityHeatmap                                                |
//|  ATR percentile within 100 and 250 bars, plus a regime label.     |
//|                                                                   |
//|  DEVIATION FROM THE BRIEF, STATED: the brief asks to "reuse the   |
//|  existing g_quant.vol_class". That global lives in nadir2.mq5 and |
//|  is not visible from an include without coupling this header to   |
//|  the host's globals, which would break encapsulation and make the |
//|  module untestable. The percentile is therefore computed here and |
//|  mapped onto the SAME five bucket names the host uses             |
//|  (LOW / NORMAL / HIGH / EXTREME / UNKNOWN). The numbers will not  |
//|  be identical to the host's classifier, which uses its own        |
//|  thresholds. Treat this as a second opinion, not a mirror.        |
//+------------------------------------------------------------------+
class CVolatilityHeatmap
  {
private:
   SVolatilityRow    m_rows[QSC_MAX_ROWS];
   int               m_rows_n;

   double            Percentile(const CBarSeries &bars,const int ci,
                                const int window,const double value) const
     {
      int from=(int)MathMax(1,ci-window+1);
      int n=ci-from+1;
      if(n<10 || !(value>0.0)) return -1.0;
      int below=0, valid=0;
      for(int i=from;i<=ci;i++)
        {
         double a=bars.ATRAt(i);
         if(!(a>0.0)) continue;
         valid++;
         if(a<value) below++;
        }
      //--- Divide by the ATRs actually compared, not by the window. Counting
      //--- the bars where ATR is not defined yet in the denominator diluted the
      //--- result toward zero (a 100-bar window with 20 warm-up bars reported a
      //--- true 80th percentile as 64th - still plausible, still wrong).
      if(valid<10) return -1.0;
      return (double)below/(double)valid*100.0;
     }

public:
                     CVolatilityHeatmap() { m_rows_n=0; }
   int               Rows() const { return m_rows_n; }
   //--- No pointer to a struct in MQL5: reference-out (see D12).
   //--- No pointer to a struct in MQL5: reference-out (see D12).
   //--- No pointer to a struct in MQL5: reference-out (see D12).
   bool              Row(const int i,SVolatilityRow &out) const
     { if(i<0 || i>=m_rows_n) return false; out=m_rows[i]; return true; }
   void              BeginPass() { m_rows_n=0; }

   bool              Evaluate(const string symbol,const ENUM_ASSET_GROUP group,
                              const CBarSeries &bars)
     {
      if(m_rows_n>=QSC_MAX_ROWS) return false;
      SVolatilityRow r;
      r.symbol=symbol; r.group=group; r.valid=false;
      r.atr_pct=0.0; r.pct100=-1.0; r.pct250=-1.0;
      r.regime="UNKNOWN"; r.note="";

      int ci=bars.ClosedIndex();
      if(ci<20) { r.note="not enough bars"; m_rows[m_rows_n]=r; m_rows_n++;
                  return false; }
      double atr=bars.ATR();
      double px=bars.C(ci);
      if(!(atr>0.0) || !(px>0.0))
        { r.note="no ATR/price"; m_rows[m_rows_n]=r; m_rows_n++; return false; }

      r.atr_pct=atr/px*100.0;
      r.pct100=Percentile(bars,ci,100,atr);
      r.pct250=Percentile(bars,ci,250,atr);

      double p=(r.pct250>=0.0 ? r.pct250 : r.pct100);
      if(p<0.0)          { r.regime="UNKNOWN"; }
      else if(p<20.0)    { r.regime="LOW"; }
      else if(p<70.0)    { r.regime="NORMAL"; }
      else if(p<90.0)    { r.regime="HIGH"; }
      else               { r.regime="EXTREME"; }

      if(r.pct250<0.0) r.note="pct250 needs 250 bars; pct100 shown";
      r.valid=true;
      m_rows[m_rows_n]=r; m_rows_n++;
      return true;
     }

   string            Legend() const
     { return "LOW <20p   NORMAL 20-70p   HIGH 70-90p   EXTREME >90p"; }
  };

//+------------------------------------------------------------------+
//| CSeasonalityScanner                                               |
//|  Average return by month / week-of-year / day-of-week / hour.     |
//|                                                                   |
//|  THIS IS DESCRIPTIVE HISTORY, NOT A FORECAST. Every row carries   |
//|  its sample size n, the number of distinct years covered and the  |
//|  dispersion. Rows are WITHHELD below the minimum n rather than    |
//|  shown with a warning, because a seasonality table with n=2 is    |
//|  actively misleading.                                             |
//|                                                                   |
//|  TIME BASIS, STATED EXPLICITLY:                                   |
//|   QTB_SERVER - bucket by the bar's server timestamp as stored.    |
//|   QTB_UTC    - apply a single offset = TimeGMT() - TimeCurrent()  |
//|                sampled at scan time. Broker servers usually run   |
//|                on a fixed offset, but some shift with DST. This   |
//|                scanner applies ONE offset to the whole history    |
//|                and therefore does NOT retroactively correct       |
//|                historical DST transitions. Where a broker's       |
//|                offset has changed in the past, hour-of-day rows   |
//|                spanning that change are approximations. This is a |
//|                known limitation, not a hidden one.                |
//+------------------------------------------------------------------+
class CSeasonalityScanner
  {
private:
   int               m_min_n;
   ENUM_TIME_BASIS   m_basis;
   long              m_utc_offset;   // seconds

   //--- accumulators per bucket, bounded and flat
   double            m_sum[64];
   double            m_sq[64];
   int               m_cnt[64];
   int               m_pos[64];
   int               m_year_mask[64];   // bit i = year (base + i) present
   int               m_base_year;
   double            m_vals[64][512];   // median sample - see Accumulate()
   int               m_vals_n[64];
   int               m_buckets;
   uint              m_rng;             // reservoir RNG, same seed every pass

   void              Reset()
     {
      m_rng=0x811C9DC5;                // FNV-1a basis as a fixed seed: same bars,
                                       // same sample, same median, every pass
      for(int i=0;i<64;i++)
        { m_sum[i]=0.0; m_sq[i]=0.0; m_cnt[i]=0; m_pos[i]=0;
          m_year_mask[i]=0; m_vals_n[i]=0; }
     }

   int               BucketCount(const ENUM_SEAS_BUCKET kind) const
     {
      switch(kind)
        { case QSEAS_MONTH: return QSC_SEAS_MONTHS;
          case QSEAS_WEEK:  return QSC_SEAS_WEEKS;
          case QSEAS_DOW:   return QSC_SEAS_DOW;
          default:          return QSC_SEAS_HOURS; }
     }

   //--- Buckets are 0-based, because they index a fixed array of
   //--- BucketCount() slots. That is a rule, not a style choice: the first
   //--- version returned st.mon (1..12) and (day_of_year+6)/7 (1..53), so every
   //--- December and every 53rd week fell outside 0..buckets-1 and was
   //--- discarded by the range test in Accumulate() - silently, in a file whose
   //--- own header promises nothing is dropped in silence. Bucket 0 was then a
   //--- phantom empty row. Months are now 0..11, weeks 0..52, dow 0..6,
   //--- hour 0..23, and QSeasBucketName() adds the +1 back for display.
   int               BucketOf(const datetime t,const ENUM_SEAS_BUCKET kind) const
     {
      datetime tt=t+(datetime)m_utc_offset;
      MqlDateTime st;
      TimeToStruct(tt,st);
      switch(kind)
        { case QSEAS_MONTH: return st.mon-1;               // 0..11
          case QSEAS_DOW:   return st.day_of_week;         // 0..6
          case QSEAS_HOUR:  return st.hour;                // 0..23
          default:          return ((st.day_of_year+6)/7)-1; // 0..52 (all of W53)
        }
     }

   //--- Insertion sort on a bounded array. No recursion.
   void              SortSmall(double &a[],const int n) const
     {
      for(int i=1;i<n;i++)
        { double k=a[i]; int j=i-1;
          while(j>=0 && a[j]>k) { a[j+1]=a[j]; j--; }
          a[j+1]=k; }
     }

public:
                     CSeasonalityScanner()
     { m_min_n=30; m_basis=QTB_SERVER; m_utc_offset=0; m_buckets=12;
       m_base_year=0; Reset(); }

   void              SetMinN(const int n) { m_min_n=(int)MathMax(2,MathMin(10000,n)); }
   void              SetBasis(const ENUM_TIME_BASIS b) { m_basis=b; UpdateOffset(); }
   int               MinN() const { return m_min_n; }
   ENUM_TIME_BASIS   Basis() const { return m_basis; }

   void              UpdateOffset()
     {
      if(m_basis==QTB_UTC)
        { long gmt=(long)TimeGMT(); long cur=(long)TimeCurrent();
          m_utc_offset=gmt-cur; }
      else
        m_utc_offset=0;
     }

   //--- Accumulate bar-to-bar returns bucketed by time. Closed bars
   //--- only: bar i uses close(i) vs close(i-1), both known at i.
   bool              Accumulate(const CBarSeries &bars,
                                const ENUM_SEAS_BUCKET kind)
     {
      int ci=bars.ClosedIndex();
      if(ci<2) return false;
      m_buckets=BucketCount(kind);
      Reset();
      if(m_buckets>64) m_buckets=64;

      m_base_year=0;
      MqlDateTime st0; TimeToStruct(bars.T(1),st0);
      m_base_year=st0.year;

      for(int i=1;i<=ci;i++)
        {
         double prev=bars.C(i-1);
         double cur =bars.C(i);
         if(!(prev>0.0) || !(cur>0.0)) continue;
         double ret=(cur-prev)/prev*100.0;

         int b=BucketOf(bars.T(i),kind);
         if(b<0 || b>=m_buckets) continue;

         m_sum[b]+=ret;
         m_sq[b]+=ret*ret;
         m_cnt[b]++;
         if(ret>0.0) m_pos[b]++;

         MqlDateTime st; TimeToStruct(bars.T(i)+(datetime)m_utc_offset,st);
         int yr=st.year-m_base_year;
         if(yr>=0 && yr<31) m_year_mask[b]|=(1<<yr);

         //--- Median sample. Keeping the FIRST 512 observations of a bucket would
         //--- make the median the median of the OLDEST slice of that bucket - a
         //--- time-window bias, not a sample. Algorithm R (Vitter) with a fixed
         //--- seed keeps an unbiased 512-sized sample of the whole bucket, and it
         //--- is deterministic: identical bars produce an identical median, which
         //--- is the property every other part of this layer is built on.
         //--- n, mean, std and pos_share are streaming and therefore exact.
         if(m_vals_n[b]<QSC_SEAS_SAMPLE)
           { m_vals[b][m_vals_n[b]]=ret; m_vals_n[b]++; }
         else
           {
            //--- No 'u' suffix anywhere: MQL5 has none (D3). The LCG constants are
            //--- plain literals and m_rng is a uint, so the wrap is the modulus.
            m_rng=1664525*m_rng+1013904223;   // Numerical Recipes / ANSI C LCG
            ulong span=(ulong)m_cnt[b];
            if(span>0)
              {
               ulong j=((ulong)m_rng>>1)%span;
               if(j<(ulong)QSC_SEAS_SAMPLE) m_vals[b][(int)j]=ret;
              }
           }
        }
      return true;
     }

   int               Buckets() const { return m_buckets; }

   bool              Row(const int b,SSeasonRow &out) const
     {
      out.bucket=b; out.n=0; out.years=0; out.mean_ret=0.0;
      out.median_ret=0.0; out.std_ret=0.0; out.pos_share=0.0;
      out.withheld=true;
      if(b<0 || b>=m_buckets) return false;

      int n=m_cnt[b];
      out.n=n;
      int yr=0;
      for(int k=0;k<31;k++) if((m_year_mask[b]&(1<<k))!=0) yr++;
      out.years=yr;

      if(n<=0) { out.withheld=true; return true; }
      if(n<m_min_n) { out.withheld=true; out.mean_ret=m_sum[b]/(double)n;
                      return true; }

      double mu=m_sum[b]/(double)n;
      out.mean_ret=mu;
      //--- Dispersion. E[X^2]-E[X]^2 cancels badly when the mean is of the same
      //--- order as the spread (daily returns in a quiet month: mean 0.03%,
      //--- std 0.05%), and it can even land slightly negative. When the reservoir
      //--- holds the whole bucket the exact two-pass form costs nothing, so use
      //--- it there and fall back to the streaming form - clamped - otherwise.
      double var=0.0;
      if(n==m_vals_n[b] && n>0)
        {
         double s2=0.0;
         for(int i=0;i<n;i++){ double d=m_vals[b][i]-mu; s2+=d*d; }
         var=s2/(double)n;
        }
      else
        {
         var=m_sq[b]/(double)n-mu*mu;
         if(!(var>0.0)) var=0.0;
        }
      out.std_ret=MathSqrt(var);
      out.pos_share=(double)m_pos[b]/(double)n*100.0;

      //--- Median over the sample. When n > QSC_SEAS_SAMPLE this is the median
      //--- of a 512-sized unbiased sample, not of the full bucket: state it, do
      //--- not let the number look exact.
      int vn=m_vals_n[b];
      if(vn>0)
        {
         double tmp[]; ArrayResize(tmp,vn);
         for(int i=0;i<vn;i++) tmp[i]=m_vals[b][i];
         SortSmall(tmp,vn);
         out.median_ret=(vn%2==1 ? tmp[vn/2] : (tmp[vn/2-1]+tmp[vn/2])/2.0);
         ArrayResize(tmp,0);
        }
      out.withheld=false;
      return true;
     }

   string            WithheldNote(const SSeasonRow &r) const
     { return "WITHHELD: n="+IntegerToString(r.n)+
              " < minimum "+IntegerToString(m_min_n); }

   //--- Footer that must be printed next to every seasonality table.
   string            Disclaimer() const
     { return "Descriptive history over the loaded bars. Sample sizes and "
              "dispersion are shown. This is NOT a forecast and NOT a "
              "probability."; }
  };

#endif
//+------------------------------------------------------------------+
