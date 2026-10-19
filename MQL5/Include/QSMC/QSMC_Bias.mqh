//+------------------------------------------------------------------+
//|                                                 QSMC_Bias.mqh    |
//|  CBiasProvider - higher-timeframe bias as a FILTER (R2), never as |
//|  a signal generator.                                              |
//|                                                                   |
//|  WEIGHTS: D1 50 / H4 30 / H1 20, HTF-wins tie-break. These are    |
//|  the values already documented and displayed by the host          |
//|  indicator's v6.5.3 "weighted bias" row, so the panel and the     |
//|  gate can no longer disagree.                                     |
//|                                                                   |
//|  CLOSED BARS ONLY: a swing pivot needs `right` confirmed bars     |
//|  AFTER it, and every bar it uses is at index <= ClosedIndex().    |
//|  A future HTF candle can never be read (no look-ahead).           |
//|                                                                   |
//|  COMPLEXITY: StructureBias O(n) over the closed lookback once per |
//|  closed bar, cached. Update() is O(D1+H4+H1 lookbacks).           |
//+------------------------------------------------------------------+
#ifndef __QSMC_BIAS_MQH__
#define __QSMC_BIAS_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_MarketData.mqh>

//+------------------------------------------------------------------+
class CBiasProvider
  {
private:
   int               m_d1;
   int               m_h4;
   int               m_h1;
   int               m_score;        // signed weighted consensus, -100..+100
   int               m_consensus;    // +1 / -1 / 0 after the tie-break
   bool              m_d1_ok, m_h4_ok, m_h1_ok;
   double            m_d1_eq, m_h4_eq, m_h1_eq;    // last pivot equilibrium
   int               m_last_update_index;

   //------------------------------------------------------------------
   // Closed-bar structure bias from swing pivots.
   //   +1 : last pivot high > previous pivot high AND last pivot low >
   //        previous pivot low  (higher highs + higher lows)
   //   -1 : mirror image
   //    0 : mixed / not enough closed pivots
   // A pivot at index i is confirmed only when `right` bars exist after
   // it AND all of them are closed (i + right <= ClosedIndex()).
   //------------------------------------------------------------------
   int               StructureBias(const CBarSeries *s,const int left,const int right,
                                   double &eq_out) const
     {
      eq_out=0.0;
      if(s==NULL) return 0;
      if(!s.Ready()) return 0;
      int last=s.ClosedIndex();
      if(last<left+right+4) return 0;

      double ph1=0.0, ph2=0.0;   // last and previous pivot high
      double pl1=0.0, pl2=0.0;   // last and previous pivot low
      bool  have_h1=false, have_h2=false, have_l1=false, have_l2=false;

      int start=last-right;                       // newest bar that can be a pivot
      int stop=(int)MathMax(left, last-(left+right)*12);
      for(int i=start;i>=stop;i--)
        {
         if(i+right>last) continue;               // pivot not fully closed
         if(i-left<0)     break;
         //--- pivot high: i is strictly the highest of [i-left, i+right]
         bool is_h=true, is_l=true;
         for(int k=i-left;k<=i+right;k++)
           {
            if(k==i) continue;
            if(s.H(k)>=s.H(i)) { is_h=false; break; }
           }
         if(is_h)
           {
            if(!have_h1){ ph1=s.H(i); have_h1=true; }
            else if(!have_h2){ ph2=s.H(i); have_h2=true; }
           }
         for(int k=i-left;k<=i+right;k++)
           {
            if(k==i) continue;
            if(s.L(k)<=s.L(i)) { is_l=false; break; }
           }
         if(is_l)
           {
            if(!have_l1){ pl1=s.L(i); have_l1=true; }
            else if(!have_l2){ pl2=s.L(i); have_l2=true; }
           }
         if(have_h2 && have_l2) break;
        }

      if(have_h1 && have_h2 && have_l1 && have_l2)
        {
         eq_out=(ph1+pl1)*0.5;
         if(ph1>ph2 && pl1>pl2) return +1;
         if(ph1<ph2 && pl1<pl2) return -1;
         return 0;
        }
      //--- Fallback with ONE pivot of each kind: compare the last pivot
      //--- against the close of the last closed bar. Weaker, but it is
      //--- still a closed-bar fact and it is reported as such.
      if(have_h1 && have_l1)
        {
         double c=s.C(last);
         eq_out=(ph1+pl1)*0.5;
         if(c>ph1) return +1;
         if(c<pl1) return -1;
         return 0;
        }
      return 0;
     }

public:
                     CBiasProvider()
     { m_d1=0; m_h4=0; m_h1=0; m_score=0; m_consensus=0;
       m_d1_ok=false; m_h4_ok=false; m_h1_ok=false;
       m_d1_eq=0.0; m_h4_eq=0.0; m_h1_eq=0.0; m_last_update_index=-1; }

                    ~CBiasProvider() {}

   void              Reset()
     { m_d1=0; m_h4=0; m_h1=0; m_score=0; m_consensus=0;
       m_d1_ok=false; m_h4_ok=false; m_h1_ok=false; m_last_update_index=-1; }

   //------------------------------------------------------------------
   // Recompute. `closed_index` is the chart's closed-bar index; the
   // result is cached so a per-tick caller cannot force a recompute.
   //------------------------------------------------------------------
   void              Update(const CMarketData &md,const SQsmcArbConfig &cfg,
                            const int closed_index)
     {
      if(closed_index==m_last_update_index) return;
      m_last_update_index=closed_index;

      int wsum=(int)MathMax(1, MathAbs(cfg.w_d1)+MathAbs(cfg.w_h4)+MathAbs(cfg.w_h1));

      m_d1=StructureBias(md.D1(),3,2,m_d1_eq);
      m_h4=StructureBias(md.H4(),3,2,m_h4_eq);
      m_h1=StructureBias(md.H1(),3,2,m_h1_eq);

      //--- A bias is "known" only when its series was COMPLETE. A missing
      //--- HTF must never be counted as agreement.
      m_d1_ok=(md.D1()!=NULL && md.D1().Ready());
      m_h4_ok=(md.H4()!=NULL && md.H4().Ready());
      m_h1_ok=(md.H1()!=NULL && md.H1().Ready());
      if(!m_d1_ok) m_d1=0;
      if(!m_h4_ok) m_h4=0;
      if(!m_h1_ok) m_h1=0;

      double num=(double)(cfg.w_d1*m_d1 + cfg.w_h4*m_h4 + cfg.w_h1*m_h1);
      m_score=(int)MathRound(num*100.0/(double)wsum);
      if(m_score>100)  m_score=100;
      if(m_score<-100) m_score=-100;

      if(m_score>0)      m_consensus=+1;
      else if(m_score<0) m_consensus=-1;
      else
        {
         //--- HTF-wins tie-break, documented on the panel (v6.5.3 D7)
         if(m_d1!=0)      m_consensus=m_d1;
         else if(m_h4!=0) m_consensus=m_h4;
         else if(m_h1!=0) m_consensus=m_h1;
         else             m_consensus=0;
        }
     }

   int               D1() const { return m_d1; }
   int               H4() const { return m_h4; }
   int               H1() const { return m_h1; }
   int               Score() const { return m_score; }
   int               Consensus() const { return m_consensus; }
   bool              D1Known() const { return m_d1_ok; }
   bool              H4Known() const { return m_h4_ok; }
   bool              H1Known() const { return m_h1_ok; }
   int               KnownCount() const
     { return (m_d1_ok?1:0)+(m_h4_ok?1:0)+(m_h1_ok?1:0); }

   //--- +1 aligned, -1 opposed, 0 neutral/unknown
   int               Agreement(const int dir) const
     {
      if(dir==0 || m_consensus==0) return 0;
      return (m_consensus==dir ? +1 : -1);
     }

   string            Text() const
     {
      string s="D1 ";
      s+=(m_d1>0?"BULL":(m_d1<0?"BEAR":(m_d1_ok?"NEUTRAL":"n/a")));
      s+=" / H4 ";
      s+=(m_h4>0?"BULL":(m_h4<0?"BEAR":(m_h4_ok?"NEUTRAL":"n/a")));
      s+=" / H1 ";
      s+=(m_h1>0?"BULL":(m_h1<0?"BEAR":(m_h1_ok?"NEUTRAL":"n/a")));
      s+=" -> consensus "+(m_consensus>0?"BULLISH":(m_consensus<0?"BEARISH":"NEUTRAL"))+
          " ("+IntegerToString(m_score)+")";
      return s;
     }

   //--- Short form for the alert line (R6 wants the reason, always).
   string            ShortText() const
     {
      return "bias D1"+IntegerToString(m_d1)+"/H4"+IntegerToString(m_h4)+
             "/H1"+IntegerToString(m_h1)+"="+IntegerToString(m_score);
     }
  };

#endif
//+------------------------------------------------------------------+
