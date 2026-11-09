//+------------------------------------------------------------------+
//|                                    QSMC_EarlyBreakDetector.mqh   |
//| Closed-bar early-move warning. Heuristic only; never an entry.   |
//+------------------------------------------------------------------+
#ifndef __QSMC_EARLYBREAKDETECTOR_MQH__
#define __QSMC_EARLYBREAKDETECTOR_MQH__

#include <QSMC/QSMC_Stats.mqh>
#include <QSMC/QSMC_Structure.mqh>

#define QEB_MISS_VOLATILITY  1
#define QEB_MISS_HISTORY     2
#define QEB_MISS_ACTIVITY    4
#define QEB_MISS_LEVELS      8
#define QEB_MISS_QUOTES     16
#define QEB_ACTIVITY_LOOKBACK 20
#define QEB_MIN_BASELINE      12

struct SEarlyBreakResult
  {
   bool     valid;
   bool     warning;
   int      direction;              // +1 up, -1 down, 0 no directional warning
   int      heuristic_score;       // 0..100, explicitly not probability
   int      missing_mask;
   bool     cusum_alarm;
   int      cusum_side;
   double   zscore;
   double   displacement_atr;
   double   activity_ratio;
   double   close_location_proxy;  // -1..+1 from candle close within range
   double   distance_to_high_atr;
   double   distance_to_low_atr;
   double   spread_atr;
   datetime event_time;
   datetime available_time;
   string   label;
   string   reason;
  };

// This detector is deliberately a warning-only feature. Inputs are closed
// broker OHLC/tick-volume bars, ATR, spread and confirmed structure levels.
// There is no historical bid/ask aggressor or exchange order-book feed here;
// close-location is a candle proxy, not order flow. Scores are deterministic
// normalized heuristics, never calibrated probabilities.
class CEarlyBreakDetector
  {
private:
   SEWState           m_returns;
   CCUSUM             m_cusum;
   datetime           m_last_time;
   int                m_cooldown_until;
   SEarlyBreakResult  m_result;
   double             m_alpha;
   double             m_cusum_k;
   double             m_cusum_h;
   double             m_min_sigma;
   double             m_warning_threshold;

   void               ClearResult()
     {
      m_result.valid=false; m_result.warning=false; m_result.direction=0;
      m_result.heuristic_score=0; m_result.missing_mask=0;
      m_result.cusum_alarm=false; m_result.cusum_side=0;
      m_result.zscore=0.0; m_result.displacement_atr=0.0;
      m_result.activity_ratio=0.0; m_result.close_location_proxy=0.0;
      m_result.distance_to_high_atr=0.0; m_result.distance_to_low_atr=0.0;
      m_result.spread_atr=0.0; m_result.event_time=0; m_result.available_time=0;
      m_result.label="EARLY BREAK: DATA NOT READY"; m_result.reason="not processed";
     }

   double             Clip01(const double x) const
     { return MathMax(0.0,MathMin(1.0,x)); }

public:
                     CEarlyBreakDetector()
     {
      m_alpha=0.08; m_cusum_k=0.50; m_cusum_h=3.50;
      m_min_sigma=0.05; m_warning_threshold=55.0;
      Reset();
     }

   void               Reset()
     {
      CEWStatistics::Reset(m_returns);
      m_cusum.Reset(); m_last_time=0; m_cooldown_until=-1;
      ClearResult();
     }

   bool               Configure(const double alpha,const double cusum_k,
                                const double cusum_h,const double min_sigma,
                                const double warning_threshold)
     {
      if(!MathIsValidNumber(alpha) || alpha<=0.0 || alpha>1.0 ||
         !MathIsValidNumber(cusum_k) || cusum_k<0.0 ||
         !MathIsValidNumber(cusum_h) || cusum_h<=0.0 ||
         !MathIsValidNumber(min_sigma) || min_sigma<=0.0 ||
         !MathIsValidNumber(warning_threshold) || warning_threshold<1.0 || warning_threshold>100.0)
         return false;
      m_alpha=alpha; m_cusum_k=cusum_k; m_cusum_h=cusum_h;
      m_min_sigma=min_sigma; m_warning_threshold=warning_threshold;
      Reset();
      return true;
     }

   SEarlyBreakResult Result() const { return m_result; }
   datetime           LastProcessedTime() const { return m_last_time; }

   // Call in chronological order, once per CLOSED bar. `availability_time`
   // is normally the next bar's open. ATR and spread refer to this decision
   // boundary. Historical warm-up uses the caller's current known ATR only to
   // normalize past returns; no warm-up warning is emitted.
   bool               ProcessClosed(const CBarSeries &bars,const int closed_index,
                                     const datetime availability_time,
                                     const double atr,const double spread_points,
                                     const double point,const bool have_swing_high,
                                     const double last_swing_high,const bool have_swing_low,
                                     const double last_swing_low)
     {
      if(!bars.Ready() || closed_index<1 || closed_index>bars.ClosedIndex() ||
         availability_time<=bars.T(closed_index)) return false;
      datetime tm=bars.T(closed_index);
      if(tm<=m_last_time) return true;
      ClearResult();
      m_result.event_time=tm; m_result.available_time=availability_time;
      if(!(atr>0.0) || !MathIsValidNumber(atr) || !(point>0.0) ||
         !MathIsValidNumber(point) || !MathIsValidNumber(spread_points) || spread_points<0.0)
        {
         m_result.missing_mask|=QEB_MISS_VOLATILITY;
         m_result.reason="ATR/point/spread unavailable";
         m_result.label="EARLY BREAK: DATA NOT READY";
         return false;
        }
      double close=bars.C(closed_index), previous=bars.C(closed_index-1);
      double open=bars.O(closed_index), high=bars.H(closed_index), low=bars.L(closed_index);
      if(!MathIsValidNumber(close) || !MathIsValidNumber(previous) ||
         !MathIsValidNumber(open) || !MathIsValidNumber(high) || !MathIsValidNumber(low) ||
         high<low || open>high || open<low || close>high || close<low) return false;

      double x=(close-previous)/atr;
      if(!MathIsValidNumber(x)) return false;
      bool baseline=(m_returns.initialized && m_returns.count>=QEB_MIN_BASELINE);
      double reference=(baseline?m_returns.mean:0.0);
      double sigma=(baseline?MathSqrt(MathMax(0.0,m_returns.variance)):0.0);
      if(baseline && sigma<m_min_sigma) sigma=m_min_sigma;
      if(baseline && closed_index>=m_cooldown_until)
        {
         bool was_alarm=m_cusum.Alarm();
         int prior_side=m_cusum.Side();
         if(!m_cusum.Update(x,reference,sigma,m_cusum_k,m_cusum_h)) return false;
         if(!was_alarm && m_cusum.Alarm())
           {
            m_result.cusum_alarm=true;
            m_result.cusum_side=m_cusum.Side();
            m_cusum.Reset();
            m_cooldown_until=closed_index+3;
           }
         else if(was_alarm && prior_side!=0)
            m_result.cusum_side=prior_side;
        }
      if(baseline && sigma>0.0)
         m_result.zscore=(x-reference)/sigma;
      else
         m_result.missing_mask|=QEB_MISS_HISTORY;

      double body=close-open;
      double range=high-low;
      m_result.displacement_atr=body/atr;
      if(range>0.0) m_result.close_location_proxy=2.0*(close-low)/range-1.0;
      else m_result.close_location_proxy=0.0;

      long vol=bars.V(closed_index);
      double vol_sum=0.0; int vol_n=0;
      int first=(int)MathMax(0,closed_index-QEB_ACTIVITY_LOOKBACK);
      for(int i=first;i<closed_index;i++)
        {
         long v=bars.V(i);
         if(v>0) { vol_sum+=(double)v; vol_n++; }
        }
      if(vol>0 && vol_n>=5 && vol_sum>0.0)
         m_result.activity_ratio=(double)vol/(vol_sum/(double)vol_n);
      else
         m_result.missing_mask|=QEB_MISS_ACTIVITY;

      if(have_swing_high && MathIsValidNumber(last_swing_high))
         m_result.distance_to_high_atr=MathAbs(last_swing_high-close)/atr;
      else
         m_result.missing_mask|=QEB_MISS_LEVELS;
      if(have_swing_low && MathIsValidNumber(last_swing_low))
         m_result.distance_to_low_atr=MathAbs(close-last_swing_low)/atr;
      else
         m_result.missing_mask|=QEB_MISS_LEVELS;
      // Bid/ask aggressor or order-book pressure are not available from this
      // OHLCV API. Expose that absence explicitly; close location is not a substitute.
      m_result.missing_mask|=QEB_MISS_QUOTES;
      m_result.spread_atr=(spread_points*point)/atr;

      // Normalized components: each is a bounded heuristic contribution.
      double z_part=Clip01(MathAbs(m_result.zscore)/3.0)*15.0;
      double disp_part=Clip01(MathAbs(body)/atr/0.80)*20.0;
      double activity_part=Clip01(MathMax(0.0,m_result.activity_ratio-1.0)/1.5)*15.0;
      double location_part=Clip01(MathAbs(m_result.close_location_proxy))*10.0;
      double cusum_part=(m_result.cusum_alarm?25.0:0.0);
      double high_prox=Clip01(1.0-m_result.distance_to_high_atr/2.0);
      double low_prox=Clip01(1.0-m_result.distance_to_low_atr/2.0);
      double directional_move=(x>0.0?1.0:(x<0.0?-1.0:0.0));
      double level_part=0.0;
      if(directional_move>0.0) level_part=high_prox*15.0;
      else if(directional_move<0.0) level_part=low_prox*15.0;
      double spread_penalty=Clip01((m_result.spread_atr-0.03)/0.15)*10.0;

      double bull=0.0,bear=0.0;
      int impulse=(body>0.0?1:(body<0.0?-1:0));
      if(m_result.cusum_alarm && m_result.cusum_side>0) bull+=cusum_part;
      if(m_result.cusum_alarm && m_result.cusum_side<0) bear+=cusum_part;
      if(m_result.zscore>0.0) bull+=z_part; else if(m_result.zscore<0.0) bear+=z_part;
      if(impulse>0) bull+=disp_part+activity_part;
      else if(impulse<0) bear+=disp_part+activity_part;
      if(m_result.close_location_proxy>0.0) bull+=location_part;
      else if(m_result.close_location_proxy<0.0) bear+=location_part;
      if(directional_move>0.0) bull+=level_part;
      else if(directional_move<0.0) bear+=level_part;
      bull=MathMax(0.0,bull-spread_penalty);
      bear=MathMax(0.0,bear-spread_penalty);
      int dir=(bull>bear?1:(bear>bull?-1:0));
      int score=(int)MathRound(MathMin(100.0,MathAbs(bull-bear)));
      m_result.valid=true;
      m_result.direction=dir;
      m_result.heuristic_score=score;
      m_result.warning=(dir!=0 && (double)score>=m_warning_threshold &&
                        (m_result.cusum_alarm || MathAbs(m_result.displacement_atr)>=0.50));
      if(m_result.warning)
         m_result.label="EARLY BREAK WATCH "+(dir>0?"UP":"DOWN")+" | "+IntegerToString(score)+"/100 heuristic (not probability)";
      else
         m_result.label="NO EARLY BREAK WARNING | heuristic "+IntegerToString(score)+"/100";
      m_result.reason=(m_result.warning?"statistical/price-action warning only; not an executable entry":"warning threshold/confirmation conditions not met");

      // Update the EW baseline only after scoring this observation, so x is
      // never used to normalize itself. Invalid update leaves the prior state.
      if(!CEWStatistics::Update(m_returns,x,m_alpha))
        { m_result.valid=false; m_result.reason="EW baseline update rejected observation"; return false; }
      m_last_time=tm;
      return true;
     }
  };

#endif
