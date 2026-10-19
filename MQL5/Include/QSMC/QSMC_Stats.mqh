//+------------------------------------------------------------------+
//|                                                 QSMC_Stats.mqh   |
//|  CStatsLogger - signal CSV journal + outcome tracking.            |
//|                                                                   |
//|  NO LOOK-AHEAD: a row is opened on the bar AFTER the signal bar    |
//|  and MFE/MAE are accumulated with bars strictly later than the     |
//|  signal bar. The signal bar itself can never improve a row.        |
//|                                                                   |
//|  HONESTY RULE: no rate, percentage or "win rate" is printed until  |
//|  n >= min_sample. Below that the logger prints "n=K (insufficient  |
//|  sample - no rate shown)". A count is never presented as a         |
//|  probability.                                                      |
//|                                                                   |
//|  COMPLEXITY: Log O(1). Advance O(open_rows) per closed bar with    |
//|  open_rows <= 512.                                                 |
//+------------------------------------------------------------------+
#ifndef __QSMC_STATS_MQH__
#define __QSMC_STATS_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_MarketData.mqh>

#define QSMC_STATS_MAX_ROWS   512
#define QSMC_STATS_MAX_BARS   240      // outcome horizon, closed bars

//--------------------------------------------------------------------
#define QRES_OPEN     0
#define QRES_TP1      1
#define QRES_SL       2
#define QRES_TIMEOUT  3
#define QRES_STALE    4     // history shifted under the row: excluded

//--------------------------------------------------------------------
struct SSigRow
  {
   bool              open;
   int               id;
   datetime          signal_time;
   int               signal_bar;      // index at publish time
   int               dir;
   int               state;
   ENUM_SIG_SOURCE   source;
   string            zone_id;
   double            entry;
   double            sl;
   double            tp1;
   double            risk;
   double            mfe_r;           // max favourable excursion, in R
   double            mae_r;           // max adverse excursion, in R (<= 0)
   int               bars_held;
   int               result;
   int               bars_to_result;
  };

//+------------------------------------------------------------------+
class CStatsLogger
  {
private:
   int               m_handle;
   string            m_file;
   bool              m_open;
   int               m_row_id;
   int               m_written;

   SSigRow           m_rows[QSMC_STATS_MAX_ROWS];
   int               m_row_count;

   int               m_n;               // closed rows
   int               m_n_tp1;
   int               m_n_sl;
   int               m_n_timeout;
   double            m_sum_mfe;
   double            m_sum_mae;
   double            m_sum_bars;

   int               m_min_sample;

   static string     SafeNum(const double v)
     {
      if(!MathIsValidNumber(v)) return "";
      return DoubleToString(v,8);
     }

public:
                     CStatsLogger()
     { m_handle=INVALID_HANDLE; m_file=""; m_open=false; m_row_id=0; m_written=0;
       m_row_count=0; m_n=0; m_n_tp1=0; m_n_sl=0; m_n_timeout=0;
       m_sum_mfe=0.0; m_sum_mae=0.0; m_sum_bars=0.0; m_min_sample=30; }

                    ~CStatsLogger() { Close(); }

   int               MinSample() const { return m_min_sample; }
   int               Rows() const { return m_row_count; }
   int               Closed() const { return m_n; }
   string            FileName() const { return m_file; }
   int               Written() const { return m_written; }

   //------------------------------------------------------------------
   bool              Open(const string symbol,const ENUM_TIMEFRAMES tf,const int min_sample)
     {
      Close();
      m_min_sample=(int)MathMax(1,min_sample);
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(),dt);
      m_file="QSMC_ARB_"+symbol+"_"+QSMC_TFName(tf)+"_"+
             StringFormat("%04d%02d%02d",dt.year,dt.mon,dt.day)+".csv";
      //--- FILE_WRITE opens (or creates) the journal for appending;
      //--- FILE_SHARE_READ lets an external tool tail it while MT5 runs.
      //--- FILE_READ is deliberately NOT combined with FILE_WRITE.
      m_handle=FileOpen(m_file,FILE_CSV|FILE_WRITE|FILE_SHARE_READ|FILE_ANSI,',');
      if(m_handle==INVALID_HANDLE)
        {
         Print("[QSMC_ARB] CSV open failed: ",m_file," err=",GetLastError());
         m_open=false;
         return false;
        }
      m_open=true;
      m_row_id=0; m_written=0;
      //--- header (one row, documented field order)
      FileWrite(m_handle,
                "seq","signal_time","symbol","tf","source","state","dir",
                "zone_id","zone_lo","zone_hi","zone_role","zone_strength",
                "evidence","evidence_count","entry","sl","tp1","rr",
                "room_atr","distance_atr","score","published","reason","blocked_by");
      return true;
     }

   void              Close()
     {
      if(m_open && m_handle!=INVALID_HANDLE) FileClose(m_handle);
      m_handle=INVALID_HANDLE;
      m_open=false;
     }

   //------------------------------------------------------------------
   void              Log(const SSignalCandidate &c,const SGateCtx &ctx,const bool published)
     {
      if(!m_open || m_handle==INVALID_HANDLE) return;
      m_row_id++;
      FileWrite(m_handle,
                IntegerToString(m_row_id),
                TimeToString(c.bar_time,TIME_DATE|TIME_MINUTES),
                ctx.symbol,
                QSMC_TFName(ctx.tf),
                QSMC_SourceName(c.source),
                QSMC_StateName(c.state),
                IntegerToString(c.dir),
                c.zone_id,
                SafeNum(c.zone_lo),
                SafeNum(c.zone_hi),
                QSMC_RoleName(c.zone_role),
                IntegerToString(c.zone_strength),
                QSMC_EvidenceList(c.reaction.evidence_mask),
                IntegerToString(c.reaction.evidence_count),
                SafeNum(c.entry),
                SafeNum(c.sl),
                SafeNum(c.tp1),
                SafeNum(c.rr),
                SafeNum(c.room_atr),
                SafeNum(c.distance_atr),
                IntegerToString(c.score),
                (published?"1":"0"),
                c.reason,
                c.reject_text);
      FileFlush(m_handle);
      m_written++;

      //--- open an outcome row for the tracker
      if(m_row_count<QSMC_STATS_MAX_ROWS && published)
        {
         SSigRow r;
         r.open=true; r.id=m_row_id; r.signal_time=c.bar_time;
         r.signal_bar=ctx.closed_index; r.dir=c.dir; r.state=c.state;
         r.source=c.source; r.zone_id=c.zone_id;
         r.entry=c.entry; r.sl=c.sl; r.tp1=c.tp1;
         r.risk=(c.dir>0 ? c.entry-c.sl : c.sl-c.entry);
         r.mfe_r=0.0; r.mae_r=0.0; r.bars_held=0;
         r.result=QRES_OPEN; r.bars_to_result=0;
         m_rows[m_row_count]=r;
         m_row_count++;
        }
      else if(m_row_count>=QSMC_STATS_MAX_ROWS)
        {
         //--- oldest row is compacted out; recorded as STALE, never as a
         //--- win or a loss (a truncated sample must not bias the count).
         for(int i=0;i<m_row_count-1;i++) m_rows[i]=m_rows[i+1];
         m_row_count=QSMC_STATS_MAX_ROWS-1;
        }
     }

   //------------------------------------------------------------------
   // Advance every open row with one newly CLOSED bar.
   // `closed_index` is the index of that bar in the CHART series.
   // NO LOOK-AHEAD: rows are only advanced for closed_index > signal_bar.
   //------------------------------------------------------------------
   void              Advance(const CBarSeries &bars,const int closed_index)
     {
      if(m_row_count<=0) return;
      if(closed_index<0 || closed_index>=bars.Count()) return;
      double h=bars.H(closed_index), l=bars.L(closed_index);

      for(int i=m_row_count-1;i>=0;i--)
        {
         SSigRow r=m_rows[i];
         if(!r.open) continue;
         if(closed_index<=r.signal_bar) continue;      // not yet tradable
         if(!(r.risk>0.0)) { r.open=false; r.result=QRES_STALE; m_rows[i]=r; continue; }

         r.bars_held++;
         double fav, adv;
         if(r.dir>0){ fav=(h-r.entry)/r.risk; adv=(l-r.entry)/r.risk; }
         else       { fav=(r.entry-l)/r.risk; adv=(r.entry-h)/r.risk; }
         if(fav>r.mfe_r) r.mfe_r=fav;
         if(adv<r.mae_r) r.mae_r=adv;

         bool hit_tp=(r.dir>0 ? h>=r.tp1 : l<=r.tp1);
         bool hit_sl=(r.dir>0 ? l<=r.sl  : h>=r.sl);
         //--- Conservative: on a bar that touched both, the STOP is
         //--- assumed to have been hit first. Never assume the best case.
         if(hit_sl)        { r.open=false; r.result=QRES_SL;  r.bars_to_result=r.bars_held; }
         else if(hit_tp)   { r.open=false; r.result=QRES_TP1; r.bars_to_result=r.bars_held; }
         else if(r.bars_held>=QSMC_STATS_MAX_BARS)
                           { r.open=false; r.result=QRES_TIMEOUT; r.bars_to_result=r.bars_held; }

         if(!r.open)
           {
            if(r.result==QRES_TP1)    m_n_tp1++;
            if(r.result==QRES_SL)     m_n_sl++;
            if(r.result==QRES_TIMEOUT)m_n_timeout++;
            if(r.result!=QRES_STALE)
              {
               m_n++;
               m_sum_mfe+=r.mfe_r;
               m_sum_mae+=r.mae_r;
               m_sum_bars+=(double)r.bars_to_result;
              }
            //--- compact
            for(int k=i;k<m_row_count-1;k++) m_rows[k]=m_rows[k+1];
            m_row_count--;
           }
         else m_rows[i]=r;
        }
     }

   //------------------------------------------------------------------
   // Human summary. Every rate is withheld below min_sample.
   //------------------------------------------------------------------
   string            Summary() const
     {
      string s="signals published="+IntegerToString(m_n_tp1+m_n_sl+m_n_timeout+m_n);
      s+=" | rows written="+IntegerToString(m_written);
      s+=" | open="+IntegerToString(m_row_count);
      s+=" | n="+IntegerToString(m_n);
      if(m_n<m_min_sample)
        {
         s+=" -> insufficient sample (need "+IntegerToString(m_min_sample)+
            ") - NO rate shown";
         return s;
        }
      double p_tp=100.0*(double)m_n_tp1/(double)m_n;
      double p_sl=100.0*(double)m_n_sl/(double)m_n;
      double p_to=100.0*(double)m_n_timeout/(double)m_n;
      s+=" | TP1 first "+DoubleToString(p_tp,1)+"%";
      s+=" | SL first "+DoubleToString(p_sl,1)+"%";
      s+=" | timeout "+DoubleToString(p_to,1)+"%";
      s+=" | avg MFE "+DoubleToString(m_sum_mfe/(double)m_n,2)+"R";
      s+=" | avg MAE "+DoubleToString(m_sum_mae/(double)m_n,2)+"R";
      s+=" | avg bars "+DoubleToString(m_sum_bars/(double)m_n,1);
      s+="  (historical counts, NOT a forecast)";
      return s;
     }
  };

#endif
//+------------------------------------------------------------------+
