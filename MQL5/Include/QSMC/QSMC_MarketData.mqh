//+------------------------------------------------------------------+
//|                                             QSMC_MarketData.mqh  |
//|  CBarSeries / CMarketData - cached closed-bar OHLCV + ATR access  |
//|  per timeframe. Single source of truth for every bar fact used by |
//|  the arbitration layer.                                           |
//|                                                                   |
//|  CONTRACT                                                         |
//|  1. All internal arrays are CHRONOLOGICAL: index 0 = oldest,      |
//|     index Count()-1 = newest. The forming bar is ALWAYS the last  |
//|     index and is never used for confirmed logic.                  |
//|  2. Ready() is true only when a CopyRates call returned EXACTLY   |
//|     the number of bars requested (partial copy = retry, never     |
//|     "success"). This is the Phase-3 rule applied to the layer     |
//|     that previously read iHigh/iLow/iClose without any check.     |
//|  3. ATR: external (already validated by the host indicator) wins; |
//|     otherwise a Wilder ATR is computed from the closed bars in    |
//|     this series. Either way ATR() returns 0.0 when unavailable.   |
//|                                                                   |
//|  COMPLEXITY: Refresh() O(n) on first call / history change,       |
//|  O(1) when the newest bar time is unchanged. ATR() O(n) once per  |
//|  closed bar, then O(1) from cache. Every getter O(1).             |
//+------------------------------------------------------------------+
#ifndef __QSMC_MARKETDATA_MQH__
#define __QSMC_MARKETDATA_MQH__

#include <QSMC/QSMC_Types.mqh>

#define QSMC_SERIES_MAX_BARS 4096

//+------------------------------------------------------------------+
class CBarSeries
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   int               m_need;            // bars requested per Refresh
   int               m_count;           // bars actually held
   double            m_o[];
   double            m_h[];
   double            m_l[];
   double            m_c[];
   datetime          m_t[];
   long              m_v[];
   bool              m_ready;
   string            m_not_ready_reason;
   datetime          m_last_closed_time;
   datetime          m_last_new_time;
   //--- ATR cache
   int               m_atr_period;
   double            m_atr_cache;
   int               m_atr_cache_index; // closed index the cache was built for
   double            m_atr_external;    // host-supplied, validated ATR
   bool              m_atr_external_valid;
   //--- diagnostics
   int               m_copy_calls;
   int               m_copy_short;
   int               m_copy_fail;

   void              Reset()
     {
      m_count=0; m_ready=false; m_atr_cache=0.0; m_atr_cache_index=-1;
      m_last_closed_time=0; m_last_new_time=0;
      ArrayResize(m_o,0); ArrayResize(m_h,0); ArrayResize(m_l,0);
      ArrayResize(m_c,0); ArrayResize(m_t,0); ArrayResize(m_v,0);
     }

   double            TrueRange(const int i) const
     {
      if(i<=0 || i>=m_count) return 0.0;
      double h=m_h[i], l=m_l[i], pc=m_c[i-1];
      double r=h-l;
      double r1=MathAbs(h-pc);
      double r2=MathAbs(l-pc);
      if(r1>r) r=r1;
      if(r2>r) r=r2;
      return r;
     }

   //--- Wilder ATR over the CLOSED bars ending at closed_index.
   //--- Seed = simple mean of the first `period` true ranges, then the
   //--- classic Wilder recursion forward to closed_index. Only bars
   //--- i >= 1 are used, so no bar-0 (forming) data can enter.
   double            ComputeWilderATR(const int closed_index) const
     {
      if(m_atr_period<1) return 0.0;
      if(closed_index<m_atr_period+1) return 0.0;
      int seed_end=(int)MathMax(1, m_atr_period);          // earliest usable bar
      if(seed_end>closed_index) return 0.0;

      double sum=0.0;
      int seeded=0;
      for(int i=1;i<=seed_end;i++){ sum+=TrueRange(i); seeded++; }
      if(seeded<m_atr_period) return 0.0;
      double atr=sum/(double)m_atr_period;
      if(!(atr>0.0) || !MathIsValidNumber(atr)) return 0.0;

      for(int i=seed_end+1;i<=closed_index;i++)
        {
         if(i<1 || i>=m_count) continue;
         atr=(atr*(double)(m_atr_period-1)+TrueRange(i))/(double)m_atr_period;
        }
      if(!(atr>0.0) || !MathIsValidNumber(atr)) return 0.0;
      return atr;
     }

public:
                     CBarSeries()
     { m_symbol=""; m_tf=PERIOD_CURRENT; m_need=300; m_count=0; m_ready=false;
       m_atr_period=14; m_atr_cache=0.0; m_atr_cache_index=-1;
       m_atr_external=0.0; m_atr_external_valid=false;
       m_copy_calls=0; m_copy_short=0; m_copy_fail=0;
       m_not_ready_reason="not refreshed yet"; }

                    ~CBarSeries() { Reset(); }

   //--- No copy constructor semantics: MQL5 forbids deep copies of
   //--- classes with dynamic arrays being returned by value. Init once.
   void              Init(const string symbol,const ENUM_TIMEFRAMES tf,
                          const int need_bars,const int atr_period)
     {
      m_symbol=(symbol==""?_Symbol:symbol);
      m_tf=(tf==PERIOD_CURRENT?(ENUM_TIMEFRAMES)_Period:tf);
      m_need=(int)MathMax(60,MathMin(QSMC_SERIES_MAX_BARS,need_bars));
      m_atr_period=(int)MathMax(1,atr_period);
      Reset();
      m_not_ready_reason="not refreshed yet";
     }

   const string      Symbol()      const { return m_symbol; }
   ENUM_TIMEFRAMES   Timeframe()   const { return m_tf;    }
   int               Count()       const { return m_count;  }
   bool              Ready()       const { return m_ready;  }
   string            NotReadyReason() const { return m_not_ready_reason; }
   int               CopyCalls()   const { return m_copy_calls; }
   int               CopyShort()   const { return m_copy_short; }
   int               CopyFail()    const { return m_copy_fail; }

   //--- Index of the last CLOSED bar. -1 when the series is unusable.
   int               ClosedIndex() const
     { return (m_count>=2 ? m_count-2 : -1); }

   //--- Index of the forming bar (never used by confirmed logic).
   int               FormingIndex() const
     { return (m_count>=1 ? m_count-1 : -1); }

   datetime          ClosedTime() const
     { int i=ClosedIndex(); return (i>=0 ? m_t[i] : 0); }

   //------------------------------------------------------------------
   // Refresh. Returns the number of bars now held; m_ready is set only
   // when the copy was COMPLETE. A short copy keeps the previous data
   // and reports the reason, it never publishes a partial truth.
   //------------------------------------------------------------------
   int               Refresh()
     {
      MqlRates tmp[];
      //--- CopyRates orientation: as_series=TRUE means index 0 = the
      //--- current (forming) bar. We re-write into chronological arrays
      //--- so the rest of the subsystem never has to think about it.
      ArraySetAsSeries(tmp,true);
      int got=CopyRates(m_symbol,m_tf,0,m_need,tmp);
      m_copy_calls++;
      if(got<0)
        {
         m_copy_fail++;
         m_ready=false;
         m_not_ready_reason="CopyRates failed (rc="+IntegerToString(got)+")";
         return m_count;
        }
      if(got<m_need)
        {
         m_copy_short++;
         m_ready=false;
         m_not_ready_reason="CopyRates returned "+IntegerToString(got)+
                            " of "+IntegerToString(m_need)+" bars (incomplete)";
         //--- Keep the previous snapshot rather than publishing a
         //--- truncated history under the same indexes.
         if(m_count<=0) return 0;
         return m_count;
        }
      if(ArraySize(tmp)<m_need)
        {
         m_ready=false;
         m_not_ready_reason="CopyRates destination size mismatch";
         return m_count;
        }
      //--- Fast path: nothing closed since the last successful copy.
      datetime newest=tmp[0].time;
      if(m_ready && m_count==m_need && newest==m_last_new_time)
        {
         //--- Only the forming bar can have moved.
         int k=m_count-1;
         m_o[k]=tmp[0].open; m_h[k]=tmp[0].high;
         m_l[k]=tmp[0].low;  m_c[k]=tmp[0].close;
         m_t[k]=tmp[0].time; m_v[k]=tmp[0].tick_volume;
         return m_count;
        }

      ArrayResize(m_o,m_need); ArrayResize(m_h,m_need); ArrayResize(m_l,m_need);
      ArrayResize(m_c,m_need); ArrayResize(m_t,m_need); ArrayResize(m_v,m_need);
      //--- Explicit chronological orientation (see contract 1).
      ArraySetAsSeries(m_o,false); ArraySetAsSeries(m_h,false);
      ArraySetAsSeries(m_l,false); ArraySetAsSeries(m_c,false);
      ArraySetAsSeries(m_t,false); ArraySetAsSeries(m_v,false);

      for(int k=0;k<m_need;k++)
        {
         int src=m_need-1-k;              // tmp[0] = newest
         m_o[k]=tmp[src].open;
         m_h[k]=tmp[src].high;
         m_l[k]=tmp[src].low;
         m_c[k]=tmp[src].close;
         m_t[k]=tmp[src].time;
         m_v[k]=tmp[src].tick_volume;
        }
      m_count=m_need;
      m_last_new_time=m_t[m_count-1];
      m_last_closed_time=(m_count>=2 ? m_t[m_count-2] : 0);
      m_ready=true;
      m_not_ready_reason="";
      m_atr_cache_index=-1;               // invalidate the ATR cache
      return m_count;
     }

   //------------------------------------------------------------------
   // TEST SEAM. Feed synthetic bars directly (used by QSMC_Selftest and
   // by the Script harness, where no terminal history exists). The data
   // is validated exactly like a CopyRates result: n must be >= 3,
   // every bar must have high>=low>0 and a strictly increasing time.
   // Returns true when the series is usable. PRODUCTION CODE MUST NOT
   // CALL THIS - it exists so the gate logic is testable offline.
   //------------------------------------------------------------------
   bool              LoadSynthetic(const double &so[],const double &sh[],
                                   const double &sl[],const double &sc[],
                                   const datetime &st[],const long &sv[],const int n)
     {
      Reset();
      if(n<3) { m_not_ready_reason="synthetic: fewer than 3 bars"; return false; }
      if(ArraySize(so)<n || ArraySize(sh)<n || ArraySize(sl)<n ||
         ArraySize(sc)<n || ArraySize(st)<n) { m_not_ready_reason="synthetic: short input"; return false; }
      ArrayResize(m_o,n); ArrayResize(m_h,n); ArrayResize(m_l,n);
      ArrayResize(m_c,n); ArrayResize(m_t,n); ArrayResize(m_v,n);
      ArraySetAsSeries(m_o,false); ArraySetAsSeries(m_h,false);
      ArraySetAsSeries(m_l,false); ArraySetAsSeries(m_c,false);
      ArraySetAsSeries(m_t,false); ArraySetAsSeries(m_v,false);
      for(int i=0;i<n;i++)
        {
         if(!(sh[i]>=sl[i]) || !(sh[i]>0.0)) { Reset(); m_not_ready_reason="synthetic: bad bar "+IntegerToString(i); return false; }
         if(i>0 && !(st[i]>st[i-1]))         { Reset(); m_not_ready_reason="synthetic: time not increasing at "+IntegerToString(i); return false; }
         m_o[i]=so[i]; m_h[i]=sh[i]; m_l[i]=sl[i]; m_c[i]=sc[i]; m_t[i]=st[i];
         m_v[i]=(ArraySize(sv)>=n ? sv[i] : 1000);
        }
      m_count=n;
      m_ready=true;
      m_not_ready_reason="";
      m_last_new_time=m_t[n-1];
      m_last_closed_time=m_t[n-2];
      m_atr_cache_index=-1;
      m_atr_external_valid=false;
      m_atr_external=0.0;
      WarmATR();
      return true;
     }

   //--- Host indicator pushes its already-validated ATR (AUDIT-01 fixed
   //--- that path). External wins; 0.0 means "unavailable", not "zero".
   void              SetExternalATR(const double atr)
     {
      if(atr>0.0 && MathIsValidNumber(atr)) { m_atr_external=atr; m_atr_external_valid=true; }
      else                                  { m_atr_external=0.0; m_atr_external_valid=false; }
     }

   //--- Cached ATR for the CURRENT closed bar only. Const: it reads the
   //--- cache, it never writes one. WarmATR() fills the cache.
   double            ATR() const
     {
      if(m_atr_external_valid && m_atr_external>0.0) return m_atr_external;
      int ci=ClosedIndex();
      if(ci<0) return 0.0;
      if(m_atr_cache_index==ci && m_atr_cache>0.0) return m_atr_cache;
      return 0.0;
     }

   //--- Fill the cache for the current closed bar. Non-const by design.
   void              WarmATR()
     {
      int ci=ClosedIndex();
      if(ci<0) return;
      if(m_atr_external_valid && m_atr_external>0.0) return;
      double a=ComputeWilderATR(ci);
      if(a>0.0 && MathIsValidNumber(a)) { m_atr_cache=a; m_atr_cache_index=ci; }
      else                              { m_atr_cache=0.0; m_atr_cache_index=ci; }
     }

   //--- ATR for ANY closed index, computed on demand without touching
   //--- the cache (MQL5 has no `mutable`). O(period*4); used at most a
   //--- few times per closed bar.
   double            ATRAt(const int closed_index) const
     {
      int current_closed=ClosedIndex();
      if(closed_index<0 || closed_index>current_closed) return 0.0;
      // The host-provided ATR describes only the current closed bar. Never
      // reuse it when replaying historical indices; compute their causal ATR.
      if(closed_index==current_closed && m_atr_external_valid && m_atr_external>0.0)
         return m_atr_external;
      if(m_atr_cache_index==closed_index && m_atr_cache>0.0) return m_atr_cache;
      double a=ComputeWilderATR(closed_index);
      if(!(a>0.0) || !MathIsValidNumber(a)) return 0.0;
      return a;
     }

   //--- Bounds-guarded accessors. Out of range => 0.0 / 0, never a crash.
   double            O(const int i) const { return (i>=0 && i<m_count ? m_o[i] : 0.0); }
   double            H(const int i) const { return (i>=0 && i<m_count ? m_h[i] : 0.0); }
   double            L(const int i) const { return (i>=0 && i<m_count ? m_l[i] : 0.0); }
   double            C(const int i) const { return (i>=0 && i<m_count ? m_c[i] : 0.0); }
   datetime          T(const int i) const { return (i>=0 && i<m_count ? m_t[i] : 0);  }
   long              V(const int i) const { return (i>=0 && i<m_count ? m_v[i] : 0);  }

   //--- Index of the bar that owns a given open time. -1 when absent.
   int               IndexOfTime(const datetime t) const
     {
      if(t<=0 || m_count<=0) return -1;
      for(int i=m_count-1;i>=0;i--)
        {
         if(m_t[i]==t) return i;
         if(m_t[i]<t)  break;
        }
      return -1;
     }

   //--- Median tick volume of the `lookback` closed bars ending at `end_index`
   //--- (inclusive). Volume evidence for CReactionDetector. O(n log n) but
   //--- only when a reaction is actually being evaluated.
   double            MedianVolume(const int end_index,const int lookback) const
     {
      int n=(int)MathMax(2,MathMin(lookback,64));
      if(end_index-n+1<0) return 0.0;
      double arr[];
      ArrayResize(arr,n);
      ArraySetAsSeries(arr,false);
      for(int k=0;k<n;k++) arr[k]=(double)m_v[end_index-n+1+k];
      //--- insertion sort: n <= 64, no allocation, deterministic
      for(int a=1;a<n;a++)
        {
         double key=arr[a];
         int b=a-1;
         while(b>=0 && arr[b]>key){ arr[b+1]=arr[b]; b--; }
         arr[b+1]=key;
        }
      if((n%2)==1) return arr[n/2];
      return (arr[n/2-1]+arr[n/2])*0.5;
     }

   //--- Mean true range over the `period` closed bars ending at end_index
   //--- (inclusive). Used for the volatility regime. O(period).
   double            MeanTrueRange(const int end_index,const int period) const
     {
      if(period<1 || end_index<1 || end_index>=m_count) return 0.0;
      int from=(int)MathMax(1, end_index-period+1);
      int n=(int)(end_index-from+1);
      if(n<1) return 0.0;
      double sum=0.0;
      for(int i=from;i<=end_index;i++) sum+=TrueRange(i);
      return sum/(double)n;
     }

   //--- Highest high / lowest low over [from..to] (inclusive, closed bars).
   double            HighestHigh(const int from,const int to) const
     {
      double r=0.0;
      int a=(int)MathMax(0,MathMin(from,to));
      int b=(int)MathMax(0,MathMax(from,to));
      if(b>=m_count) b=m_count-1;
      for(int i=a;i<=b;i++){ if(m_h[i]>r) r=m_h[i]; }
      return r;
     }
   double            LowestLow(const int from,const int to) const
     {
      double r=0.0;
      int a=(int)MathMax(0,MathMin(from,to));
      int b=(int)MathMax(0,MathMax(from,to));
      if(b>=m_count) b=m_count-1;
      for(int i=a;i<=b;i++){ if(r<=0.0 || m_l[i]<r) r=m_l[i]; }
      return r;
     }
  };

//+------------------------------------------------------------------+
//| CMarketData - owns every timeframe the arbitration layer reads:   |
//| the chart series (context), the execution series (the tactical    |
//| trigger) and the three bias series (D1 / H4 / H1).                |
//| One RefreshAll() per closed bar; no per-tick full recomputation.  |
//+------------------------------------------------------------------+
class CMarketData
  {
private:
   CBarSeries       *m_chart;        // owned
   CBarSeries       *m_exec;         // owned
   CBarSeries       *m_d1;           // owned
   CBarSeries       *m_h4;           // owned
   CBarSeries       *m_h1;           // owned
   bool              m_ready;
   string            m_reason;
   int               m_alloc_calls;  // leak-verification counter
   int               m_free_calls;

   void              SafeDelete(CBarSeries *p)
     {
      if(CheckPointer(p)==POINTER_DYNAMIC){ delete p; m_free_calls++; }
     }

public:
                     CMarketData()
     { m_chart=NULL; m_exec=NULL; m_d1=NULL; m_h4=NULL; m_h1=NULL;
       m_ready=false; m_reason="not initialised";
       m_alloc_calls=0; m_free_calls=0; }

                    ~CMarketData()
     {
      SafeDelete(m_chart); SafeDelete(m_exec);
      SafeDelete(m_d1); SafeDelete(m_h4); SafeDelete(m_h1);
      m_chart=NULL; m_exec=NULL; m_d1=NULL; m_h4=NULL; m_h1=NULL;
     }

   int               AllocCalls() const { return m_alloc_calls; }
   int               FreeCalls()  const { return m_free_calls;  }

   //--- RAII: every allocation made here is released by the destructor.
   //--- Verify with CMarketData::AllocCalls() == FreeCalls() on Deinit.
   bool              Init(const string symbol,const ENUM_TIMEFRAMES chart_tf,
                          const ENUM_TIMEFRAMES exec_tf,const int bars,
                          const int atr_period)
     {
      SafeDelete(m_chart); SafeDelete(m_exec);
      SafeDelete(m_d1); SafeDelete(m_h4); SafeDelete(m_h1);

      m_chart=new CBarSeries(); m_alloc_calls++;
      m_exec =new CBarSeries(); m_alloc_calls++;
      m_d1   =new CBarSeries(); m_alloc_calls++;
      m_h4   =new CBarSeries(); m_alloc_calls++;
      m_h1   =new CBarSeries(); m_alloc_calls++;

      m_chart.Init(symbol,chart_tf,bars,atr_period);
      m_exec.Init(symbol,exec_tf,bars,atr_period);
      m_d1.Init(symbol,PERIOD_D1,120,atr_period);
      m_h4.Init(symbol,PERIOD_H4,200,atr_period);
      m_h1.Init(symbol,PERIOD_H1,300,atr_period);
      m_ready=false;
      m_reason="not refreshed yet";
      return true;
     }

   //--- Const accessors: consumers (bias, gates) hold a const reference
   //--- to CMarketData and must not be able to mutate the series.
   const CBarSeries *Chart() const { return m_chart; }
   const CBarSeries *Exec()  const { return m_exec;  }
   const CBarSeries *D1()    const { return m_d1;    }
   const CBarSeries *H4()    const { return m_h4;    }
   const CBarSeries *H1()    const { return m_h1;    }
   //--- Non-const access is reserved for the owner (the root) and for
   //--- the TEST SEAM (synthetic bars). Production must not mutate a
   //--- series outside RefreshAll().
   CBarSeries       *MutableChart() { return m_chart; }
   CBarSeries       *MutableExec()  { return m_exec;  }

   //--- Called once per closed bar from the root. Never per tick.
   bool              RefreshAll(const double external_atr)
     {
      m_ready=false;
      if(m_chart==NULL || m_exec==NULL || m_d1==NULL || m_h4==NULL || m_h1==NULL)
        { m_reason="market data not initialised"; return false; }

      m_chart.SetExternalATR(external_atr);
      m_exec.SetExternalATR(0.0);      // exec TF gets its own ATR

      m_chart.Refresh();
      m_exec.Refresh();
      m_chart.WarmATR();
      m_exec.WarmATR();
      m_d1.Refresh();
      m_h4.Refresh();
      m_h1.Refresh();

      //--- READY requires: the chart series and the execution series are
      //--- COMPLETE and each carries at least one closed bar. The bias
      //--- series are optional (a missing HTF downgrades, it never
      //--- silently produces a fake "aligned" verdict).
      if(!m_chart.Ready())
        { m_reason="chart series: "+m_chart.NotReadyReason(); return false; }
      if(m_chart.ClosedIndex()<2)
        { m_reason="chart series has fewer than 3 bars"; return false; }
      if(!m_exec.Ready())
        { m_reason="execution series: "+m_exec.NotReadyReason(); return false; }
      if(m_exec.ClosedIndex()<2)
        { m_reason="execution series has fewer than 3 bars"; return false; }

      double atr=m_chart.ATR();
      if(!(atr>0.0) || !MathIsValidNumber(atr))
        { m_reason="ATR unavailable (0 or NaN)"; return false; }

      m_ready=true;
      m_reason="";
      return true;
     }

   bool              Ready() const        { return m_ready; }
   string            Reason() const       { return m_reason; }
  };

#endif
//+------------------------------------------------------------------+
