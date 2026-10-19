//+------------------------------------------------------------------+
//|                                              QSMC_Reaction.mqh   |
//|  CReactionDetector - closed-bar rejection / acceptance detection  |
//|  with independent evidence groups.                                |
//|                                                                   |
//|  DOMAIN RULE R1 IMPLEMENTED HERE                                  |
//|   At RESISTANCE:                                                  |
//|     SELL only after a CLOSED-bar rejection: touch + bounded       |
//|     penetration + close back below + >= min_evidence independent   |
//|     evidence groups.                                              |
//|     BUY only after a CLOSED-bar acceptance: close beyond the zone |
//|     plus (optionally) a retest that holds - continuation, never a  |
//|     counter-trade.                                                |
//|   At SUPPORT: mirror image.                                       |
//|   A zone broken by a closed bar flips role only after a retest;   |
//|   before that, signals against the break direction are forbidden. |
//|                                                                   |
//|  NO LOOK-AHEAD: bar_index must be >= 1 and <= ClosedIndex().       |
//|  Shift 0 (the forming bar) is refused by contract.                 |
//|                                                                   |
//|  COMPLEXITY: O(1) per evaluation for the five bar-local groups,    |
//|  O(lookback) for the LTF MSS scan and for the retest scan. Both    |
//|  are bounded (<= 64 bars) and run only when a candidate exists.    |
//+------------------------------------------------------------------+
#ifndef __QSMC_REACTION_MQH__
#define __QSMC_REACTION_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_MarketData.mqh>

#define QSMC_MSS_LOOKBACK 12

//+------------------------------------------------------------------+
class CReactionDetector
  {
private:
   //--- Candle geometry thresholds. These mirror the host engine's
   //--- candle analysis (v6.4.x SCandleIntel) so the two layers agree.
   double            m_body_ratio_strong;  // 0.55
   double            m_doji_ratio;         // 0.12
   double            m_wick_mult;          // 2.0
   double            m_engulf_ratio;       // 0.90
   int               m_volume_lookback;    // 20 closed bars

   static bool       Gt(const double a,const double b,const double eps)
     { return (a > b + eps); }
   static bool       Lt(const double a,const double b,const double eps)
     { return (a < b - eps); }

   //------------------------------------------------------------------
   // Rejection candle geometry on a CLOSED bar.
   //   buy == true  : we want a bullish rejection at SUPPORT
   //   buy == false : we want a bearish rejection at RESISTANCE
   // Returns true only for a NAMED reversal pattern, never for an
   // ordinary candle (an unnamed bar earns no candle evidence).
   //------------------------------------------------------------------
   bool              CandleRejects(const CBarSeries &bars,const int i,const bool buy) const
     {
      if(i<1) return false;
      double r_o=bars.O(i), r_h=bars.H(i), r_l=bars.L(i), r_c=bars.C(i);
      double p_o=bars.O(i-1), p_c=bars.C(i-1);
      double range=r_h-r_l;
      if(!(range>0.0)) return false;
      double body=MathAbs(r_c-r_o);
      double upper=r_h-MathMax(r_o,r_c);
      double lower=MathMin(r_o,r_c)-r_l;
      double pbody=MathAbs(p_c-p_o);
      double body_ratio=body/range;
      bool up=(r_c>r_o), dn=(r_c<r_o);
      bool strong_body=(body_ratio>=m_body_ratio_strong);

      if(buy)
        {
         //--- bullish engulfing: the bar must contain the previous body
         bool bull_engulf=(up && r_c>=p_o && r_o<=p_c && r_c>p_c &&
                           body>=pbody*m_engulf_ratio);
         //--- hammer: long lower wick, tiny upper wick, close in the top
         bool hammer=(lower>=body*m_wick_mult &&
                      upper<=MathMax(body*0.75,DBL_EPSILON) &&
                      (r_c-r_l)/range>=0.62);
         //--- piercing: opens below the prior close, closes above the
         //--- midpoint of the prior bearish body
         bool piercing=(p_c<p_o && up && r_c>p_o && r_c<(p_o+p_c)*0.5);
         //--- three-bar morning star
         if(i<2) return (bull_engulf || hammer || piercing);
         double b2o=bars.O(i-2), b2c=bars.C(i-2);
         double m_o=bars.O(i-1), m_h=bars.H(i-1), m_l=bars.L(i-1), m_c=bars.C(i-1);
         double m_range=m_h-m_l;
         bool middle_small=(m_range>0.0 && (MathAbs(m_c-m_o)<=m_range*0.35));
         bool morning=(b2c<b2o && middle_small && up && strong_body &&
                       r_c>(b2o+b2c)*0.5);
         return (bull_engulf || hammer || piercing || morning);
        }
      else
        {
         bool bear_engulf=(dn && r_o>=p_c && r_c<=p_o && r_c<p_c &&
                           body>=pbody*m_engulf_ratio);
         bool shooting=(upper>=body*m_wick_mult &&
                        lower<=MathMax(body*0.75,DBL_EPSILON) &&
                        (r_c-r_l)/range<=0.38);
         bool dark_cloud=(p_c>p_o && dn && r_c<p_o && r_c>(p_o+p_c)*0.5);
         if(i<2) return (bear_engulf || shooting || dark_cloud);
         double b2o=bars.O(i-2), b2c=bars.C(i-2);
         double m_o=bars.O(i-1), m_h=bars.H(i-1), m_l=bars.L(i-1), m_c=bars.C(i-1);
         double m_range=m_h-m_l;
         bool middle_small=(m_range>0.0 && (MathAbs(m_c-m_o)<=m_range*0.35));
         bool evening=(b2c>b2o && middle_small && dn && strong_body &&
                       r_c<(b2o+b2c)*0.5);
         return (bear_engulf || shooting || dark_cloud || evening);
        }
     }

   //------------------------------------------------------------------
   // Lower-timeframe market-structure shift, closed bars only.
   //   dir < 0 : a swing high formed, then a later CLOSED bar closed
   //             below the LOW of the bar that made that high.
   //   dir > 0 : mirror image.
   // No forming bar is ever consulted.
   //------------------------------------------------------------------
   bool              LTF_MSS(const CBarSeries *ltf,const datetime since_time,
                             const int dir) const
     {
      if(ltf==NULL) return false;
      if(!ltf.Ready()) return false;
      int last=ltf.ClosedIndex();
      if(last<1) return false;
      int first=-1;
      for(int i=last;i>=1;i--)
        {
         if(ltf.T(i)<since_time) break;
         first=i;
        }
      if(first<0) return false;
      int span=last-first+1;
      if(span<2) return false;
      if(span>QSMC_MSS_LOOKBACK) span=QSMC_MSS_LOOKBACK;
      int from=last-span+1;

      if(dir<0)
        {
         int hi_i=from;
         for(int i=from;i<=last;i++) if(ltf.H(i)>ltf.H(hi_i)) hi_i=i;
         double ref=ltf.L(hi_i);
         for(int i=hi_i+1;i<=last;i++)
            if(ltf.C(i)<ref) return true;      // closed through the swing low
         return false;
        }
      else
        {
         int lo_i=from;
         for(int i=from;i<=last;i++) if(ltf.L(i)<ltf.L(lo_i)) lo_i=i;
         double ref=ltf.H(lo_i);
         for(int i=lo_i+1;i<=last;i++)
            if(ltf.C(i)>ref) return true;      // closed through the swing high
         return false;
        }
     }

public:
                     CReactionDetector()
     { m_body_ratio_strong=0.55; m_doji_ratio=0.12; m_wick_mult=2.0;
       m_engulf_ratio=0.90; m_volume_lookback=20; }

                    ~CReactionDetector() {}

   //------------------------------------------------------------------
   // Evaluate one CLOSED bar against one zone.
   //   z         : the zone (role already resolved by CZoneRegistry)
   //   bars      : the series the bar belongs to
   //   bar_index : the CLOSED bar to evaluate (>= 1, <= ClosedIndex())
   //   atr       : ATR in price units for that series
   //   cfg       : thresholds
   //   ltf       : optional lower timeframe for the MSS evidence group
   //   out       : facts + evidence mask + missing-evidence text
   //------------------------------------------------------------------
   bool              Evaluate(const SQZone &z,const CBarSeries &bars,const int bar_index,
                              const double atr,const SQsmcArbConfig &cfg,
                              const CBarSeries *ltf,SReactionFacts &out) const
     {
      out.valid=false;
      out.touched=false; out.penetration_bounded=false; out.closed_back=false;
      out.accepted=false; out.retest_held=false; out.dir=0;
      out.evidence_mask=QEV_NONE; out.evidence_count=0;
      out.bar_time=0; out.penetration_atr=0.0; out.displacement_atr=0.0;
      out.missing=""; out.summary="";

      //--- CONTRACT: shift 0 is never evaluated.
      int last_closed=bars.ClosedIndex();
      if(bar_index<1 || bar_index>last_closed) return false;
      if(!z.valid || !(atr>0.0) || !MathIsValidNumber(atr)) return false;
      if(z.birth_role==ZR_NEUTRAL) return false;

      double h=bars.H(bar_index), l=bars.L(bar_index);
      double o=bars.O(bar_index), c=bars.C(bar_index);
      if(!(h>=l) || !(h>0.0)) return false;

      //--- Float-tolerant comparisons: prices are compared on a tick grid,
      //--- never with ==. BTCUSD (2 digits, 0.01 tick) and XAUUSD (2-3
      //--- digits, 0.01 tick) both resolve to a 1-tick epsilon here.
      double eps=MathMax(_Point, atr*0.0005);
      if(!(eps>0.0)) eps=_Point;

      ENUM_ZR_ROLE role=z.role;
      bool is_support=(role==ZR_SUPPORT);

      out.bar_time=bars.T(bar_index);

      //--- 1) TOUCH: the bar's range must overlap the band.
      out.touched=(l<=z.hi+eps && h>=z.lo-eps);
      if(!out.touched) { out.summary="no touch"; return false; }

      //--- 2) PENETRATION, measured beyond the ROLE edge, in ATR units.
      double pen=0.0;
      if(is_support) pen=MathMax(0.0, z.lo-l);        // pierced below support
      else           pen=MathMax(0.0, h-z.hi);        // pierced above resistance
      out.penetration_atr=pen/atr;
      out.penetration_bounded=(out.penetration_atr<=cfg.max_penetration_atr+1.0e-9);

      //--- 3) ACCEPTANCE (breakout) vs CLOSE-BACK (rejection).
      double break_dist=cfg.break_atr*atr;
      if(is_support)
        {
         out.accepted   = Lt(c, z.lo-break_dist, eps);
         out.closed_back= Gt(c, z.lo, eps);
        }
      else
        {
         out.accepted   = Gt(c, z.hi+break_dist, eps);
         out.closed_back= Lt(c, z.hi, eps);
        }

      //--- 4) DIRECTION. This is the R1 decision, and it comes from the
      //--- zone ROLE plus the type of bar fact - never from bias alone.
      bool reject=false, accept=false;
      if(out.accepted)
        {
         //--- continuation in the break direction
         out.dir=(is_support ? -1 : +1);
         accept=true;
        }
      else if(out.closed_back && out.penetration_bounded)
        {
         //--- rejection off the zone: fade the role
         out.dir=(is_support ? +1 : -1);
         reject=true;
        }
      else
        {
         //--- Neither. Price is standing inside a band it did not reject
         //--- and did not break: NO TRADE (this is the case the tactical
         //--- path used to trade blindly).
         out.dir=0;
         out.summary="touch without rejection or acceptance";
         return false;
        }

      if(out.dir==0) return false;
      bool buy=(out.dir>0);

      //--- 5) EVIDENCE GROUPS. Each is independent; each is closed-bar.
      int mask=QEV_NONE;

      //--- E1 wick (rejection only)
      if(reject)
        {
         double range=h-l;
         if(range>0.0)
           {
            double wick=(buy ? (MathMin(o,c)-l) : (h-MathMax(o,c)));
            if(wick/range>=cfg.min_wick_ratio) mask|=QEV_WICK;
           }
         //--- E2 candle pattern (rejection only)
         if(CandleRejects(bars,bar_index,buy)) mask|=QEV_CANDLE;
        }
      else
        {
         //--- An acceptance/breakout earns its structure evidence from the
         //--- displacement and the LTF shift instead. It cannot claim a
         //--- "rejection wick" it does not have.
         double body=MathAbs(c-o);
         if(atr>0.0 && body>=cfg.displacement_atr*atr) mask|=QEV_CANDLE;
        }

      //--- E3 volume expansion
      double med=bars.MedianVolume(bar_index-1,m_volume_lookback);
      if(med>0.0 && (double)bars.V(bar_index)>=med*cfg.volume_mult) mask|=QEV_VOLUME;
      else if(med<=0.0 && bars.V(bar_index)>0) mask|=QEV_VOLUME;   // no baseline: not refuted

      //--- E4 displacement away from the level
      if(reject)
        {
         double disp=(buy ? (c-l) : (h-c));
         out.displacement_atr=disp/atr;
         if(disp>=cfg.displacement_atr*atr) mask|=QEV_DISPLACEMENT;
        }
      else
        {
         double disp=(buy ? (c-z.hi) : (z.lo-c));
         out.displacement_atr=disp/atr;
         if(disp>=cfg.displacement_atr*atr) mask|=QEV_DISPLACEMENT;
        }

      //--- E5 liquidity sweep: the bar pierced the role edge and closed
      //--- back on the rejection side (swept and reclaimed).
      if(reject && pen>0.0 && pen>=atr*0.02) mask|=QEV_SWEEP;

      //--- E6 lower-timeframe market-structure shift
      if(ltf!=NULL && LTF_MSS(ltf,bars.T(bar_index),out.dir)) mask|=QEV_MSS;

      out.evidence_mask=mask;
      out.evidence_count=QSMC_EvidenceCount(mask);
      out.missing=QSMC_MissingEvidence(mask);
      out.valid=true;
      out.summary=(reject?"rejection":"acceptance")+" at "+
                  QSMC_RoleName(role)+" | evidence "+
                  QSMC_EvidenceList(mask)+" ("+IntegerToString(out.evidence_count)+
                  "/"+IntegerToString(QEV_COUNT)+")";
      if(accept) out.summary+=" | continuation";
      return true;
     }

   //------------------------------------------------------------------
   // A BROKEN zone only earns its new role after a closed-bar RETEST:
   // price returns to the band and closes back on the break side.
   // `dir` is the break direction (+1 broke up, -1 broke down).
   //------------------------------------------------------------------
   bool              DetectRetest(const SQZone &z,const CBarSeries &bars,
                                  const int upto_bar,const int lookback,
                                  const double atr,const int dir) const
     {
      if(!z.valid || !(atr>0.0) || dir==0) return false;
      int last=bars.ClosedIndex();
      if(upto_bar<1 || upto_bar>last) return false;
      int from=(int)MathMax(1,upto_bar-lookback+1);
      double eps=MathMax(_Point, atr*0.0005);
      for(int i=from;i<=upto_bar;i++)
        {
         double h=bars.H(i), l=bars.L(i), c=bars.C(i);
         bool touch=(l<=z.hi+eps && h>=z.lo-eps);
         if(!touch) continue;
         //--- closed back on the FAR side of the broken role edge
         if(dir>0 && c>z.hi+eps) return true;    // broke up, retest held above
         if(dir<0 && c<z.lo-eps) return true;    // broke down, retest held below
        }
      return false;
     }

   //------------------------------------------------------------------
   // Evidence quality score, 0-100. NOT a probability and NOT a win
   // rate: it is the weighted count of independent evidence groups
   // combined with the zone's own strength, exactly as documented.
   //------------------------------------------------------------------
   int               Score(const SReactionFacts &f,const int zone_strength) const
     {
      if(!f.valid) return 0;
      int ev=(int)MathMax(0,MathMin(QEV_COUNT,f.evidence_count));
      double ev_pts=(double)ev/(double)QEV_COUNT*60.0;      // 0..60
      double zs_pts=((double)MathMax(0,MathMin(100,zone_strength)))*0.30; // 0..30
      double pen_pts=0.0;
      if(f.penetration_bounded) pen_pts=10.0;                // 0..10
      double s=ev_pts+zs_pts+pen_pts;
      return (int)MathMax(0.0,MathMin(100.0,s+0.5));
     }
  };

#endif
//+------------------------------------------------------------------+
