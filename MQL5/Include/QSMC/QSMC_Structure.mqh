//+------------------------------------------------------------------+
//|                                              QSMC_Structure.mqh  |
//| Causal, closed-bar market-structure event engine.                |
//+------------------------------------------------------------------+
#ifndef __QSMC_STRUCTURE_MQH__
#define __QSMC_STRUCTURE_MQH__

#include <QSMC/QSMC_MarketData.mqh>

#define QSMC_MS_MAX_EVENTS_PER_BAR 16

enum ENUM_MS_EVENT
  {
   MS_SWING_HIGH=1,
   MS_SWING_LOW=2,
   MS_HIGHER_HIGH=3,
   MS_LOWER_HIGH=4,
   MS_HIGHER_LOW=5,
   MS_LOWER_LOW=6,
   MS_EQUAL_HIGH=7,
   MS_EQUAL_LOW=8,
   MS_BUY_SIDE_LIQUIDITY=9,
   MS_SELL_SIDE_LIQUIDITY=10,
   MS_BOS_UP=11,
   MS_BOS_DOWN=12,
   MS_CHOCH_UP=13,
   MS_CHOCH_DOWN=14,
   MS_LIQUIDITY_SWEEP_HIGH=15,
   MS_LIQUIDITY_SWEEP_LOW=16,
   MS_LIQUIDITY_BREAKOUT_HIGH=17,
   MS_LIQUIDITY_BREAKOUT_LOW=18,
   MS_BULL_DISPLACEMENT=19,
   MS_BEAR_DISPLACEMENT=20,
   MS_STRUCTURE_INVALIDATED=21
  };

struct SStructureEvent
  {
   string         id;
   ENUM_MS_EVENT  type;
   int            direction;       // +1 bullish, -1 bearish, 0 descriptive
   double         price;           // pivot/close price associated with event
   double         level;           // reference structure/liquidity price
   datetime       event_time;      // pivot/event bar open time
   datetime       available_time;  // supplied next-bar/open availability time
   datetime       reference_time;  // source pivot/pool time, when applicable
   string         reason;
  };

// Causal definitions:
// * A swing is a strict local extremum across left+right bars. Equal-value
//   plateaus are deliberately not swings. It is emitted only when all right
//   bars are closed, i.e. while processing the confirmation bar.
// * BOS/CHoCH require a CLOSED close outside the latest confirmed opposite
//   pivot by break_buffer. Wick-only penetration is not a structure break.
// * CHoCH is the first confirmed break opposite the current directional state;
//   otherwise a confirmed structural close break is BOS. Initial neutral ->
//   directional break is BOS and establishes the state.
// * Buy/sell-side liquidity is intentionally restricted to a pair/cluster of
//   confirmed equal swing highs/lows within equal_tolerance. A single swing is
//   not labelled an institutional liquidity pool.
// * A sweep requires wick penetration of an active equal-pivot pool and a close
//   back at/inside its boundary. A close beyond break_buffer is a breakout.
// * An uptrend is structurally invalidated by a close below the latest confirmed
//   swing low; a downtrend by a close above the latest confirmed swing high.
// * event_time and available_time are separate. Caller provides the actual
//   availability boundary (normally the next bar open); no future bars are read.
// Complexity per closed bar: O(left+right) for pivot confirmation + O(1) state.
class CStructureEngine
  {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   int             m_left;
   int             m_right;
   double          m_equal_tolerance;
   double          m_break_buffer;
   double          m_sweep_penetration;
   double          m_displacement_atr;
   double          m_min_body_fraction;
   int             m_trend;                 // -1 down, 0 unknown, +1 up
   datetime        m_last_processed;

   bool            m_have_high;
   double          m_last_high;
   datetime        m_last_high_time;
   bool            m_have_low;
   double          m_last_low;
   datetime        m_last_low_time;

   bool            m_equal_high_active;
   double          m_equal_high_level;
   int             m_equal_high_count;
   datetime        m_equal_high_time;
   bool            m_equal_high_consumed;
   bool            m_equal_low_active;
   double          m_equal_low_level;
   int             m_equal_low_count;
   datetime        m_equal_low_time;
   bool            m_equal_low_consumed;
   datetime        m_last_break_high_time;
   datetime        m_last_break_low_time;

   void            Emit(SStructureEvent &out[],const ENUM_MS_EVENT type,
                        const int direction,const double price,const double level,
                        const datetime event_time,const datetime available_time,
                        const datetime reference_time,const string reason)
     {
      int n=ArraySize(out);
      if(n>=QSMC_MS_MAX_EVENTS_PER_BAR) return;
      if(ArrayResize(out,n+1)!=n+1) return;
      out[n].type=type;
      out[n].direction=direction;
      out[n].price=price;
      out[n].level=level;
      out[n].event_time=event_time;
      out[n].available_time=available_time;
      out[n].reference_time=reference_time;
      out[n].reason=reason;
      out[n].id=StringFormat("MS|%s|%d|%d|%I64d|%I64d",
                             m_symbol,(int)m_tf,(int)type,(long)event_time,(long)reference_time);
     }

   bool            IsSwingHigh(const MqlRates &rates[],const int pivot) const
     {
      double p=rates[pivot].high;
      for(int j=pivot-m_left;j<=pivot+m_right;j++)
        {
         if(j==pivot) continue;
         if(rates[j].high>=p) return false;
        }
      return true;
     }

   bool            IsSwingLow(const MqlRates &rates[],const int pivot) const
     {
      double p=rates[pivot].low;
      for(int j=pivot-m_left;j<=pivot+m_right;j++)
        {
         if(j==pivot) continue;
         if(rates[j].low<=p) return false;
        }
      return true;
     }

   bool            IsSwingHighSeries(const CBarSeries &bars,const int pivot) const
     {
      double p=bars.H(pivot);
      for(int j=pivot-m_left;j<=pivot+m_right;j++)
         if(j!=pivot && bars.H(j)>=p) return false;
      return true;
     }

   bool            IsSwingLowSeries(const CBarSeries &bars,const int pivot) const
     {
      double p=bars.L(pivot);
      for(int j=pivot-m_left;j<=pivot+m_right;j++)
         if(j!=pivot && bars.L(j)<=p) return false;
      return true;
     }

   bool            ValidWindow(const MqlRates &rates[],const int first,const int last) const
     {
      for(int i=first;i<=last;i++)
        {
         if(!MathIsValidNumber(rates[i].open) || !MathIsValidNumber(rates[i].high) ||
            !MathIsValidNumber(rates[i].low) || !MathIsValidNumber(rates[i].close) ||
            rates[i].high<rates[i].low || rates[i].open>rates[i].high ||
            rates[i].open<rates[i].low || rates[i].close>rates[i].high ||
            rates[i].close<rates[i].low) return false;
         if(i>first && rates[i].time<=rates[i-1].time) return false;
        }
      return true;
     }

   bool            ValidSeriesWindow(const CBarSeries &bars,const int first,const int last) const
     {
      for(int i=first;i<=last;i++)
        {
         double o=bars.O(i),h=bars.H(i),l=bars.L(i),c=bars.C(i);
         if(!MathIsValidNumber(o) || !MathIsValidNumber(h) || !MathIsValidNumber(l) ||
            !MathIsValidNumber(c) || h<l || o>h || o<l || c>h || c<l) return false;
         if(i>first && bars.T(i)<=bars.T(i-1)) return false;
        }
      return true;
     }

   void            ProcessHigh(const double value,const datetime tm,
                               const datetime available,SStructureEvent &out[])
     {
      Emit(out,MS_SWING_HIGH,0,value,value,tm,available,tm,"strict pivot high confirmed");
      if(m_have_high)
        {
         double delta=value-m_last_high;
         if(delta>m_equal_tolerance)
            Emit(out,MS_HIGHER_HIGH,1,value,m_last_high,tm,available,m_last_high_time,"confirmed high above prior swing high");
         else if(delta < -m_equal_tolerance)
            Emit(out,MS_LOWER_HIGH,-1,value,m_last_high,tm,available,m_last_high_time,"confirmed high below prior swing high");
         else
           {
            Emit(out,MS_EQUAL_HIGH,0,value,m_last_high,tm,available,m_last_high_time,"confirmed swing highs within configured tolerance");
            if(!m_equal_high_active || m_equal_high_consumed || MathAbs(value-m_equal_high_level)>m_equal_tolerance)
              {
               m_equal_high_level=(value+m_last_high)*0.5;
               m_equal_high_count=2;
               m_equal_high_time=tm;
               m_equal_high_active=true;
               m_equal_high_consumed=false;
               Emit(out,MS_BUY_SIDE_LIQUIDITY,1,m_equal_high_level,m_equal_high_level,
                    tm,available,m_last_high_time,"equal-high pool; broker OHLC structure only");
              }
            else
              {
               m_equal_high_level=(m_equal_high_level*(double)m_equal_high_count+value)/(double)(m_equal_high_count+1);
               m_equal_high_count++;
               m_equal_high_time=tm;
              }
           }
        }
      m_last_high=value; m_last_high_time=tm; m_have_high=true;
     }

   void            ProcessLow(const double value,const datetime tm,
                              const datetime available,SStructureEvent &out[])
     {
      Emit(out,MS_SWING_LOW,0,value,value,tm,available,tm,"strict pivot low confirmed");
      if(m_have_low)
        {
         double delta=value-m_last_low;
         if(delta>m_equal_tolerance)
            Emit(out,MS_HIGHER_LOW,1,value,m_last_low,tm,available,m_last_low_time,"confirmed low above prior swing low");
         else if(delta < -m_equal_tolerance)
            Emit(out,MS_LOWER_LOW,-1,value,m_last_low,tm,available,m_last_low_time,"confirmed low below prior swing low");
         else
           {
            Emit(out,MS_EQUAL_LOW,0,value,m_last_low,tm,available,m_last_low_time,"confirmed swing lows within configured tolerance");
            if(!m_equal_low_active || m_equal_low_consumed || MathAbs(value-m_equal_low_level)>m_equal_tolerance)
              {
               m_equal_low_level=(value+m_last_low)*0.5;
               m_equal_low_count=2;
               m_equal_low_time=tm;
               m_equal_low_active=true;
               m_equal_low_consumed=false;
               Emit(out,MS_SELL_SIDE_LIQUIDITY,-1,m_equal_low_level,m_equal_low_level,
                    tm,available,m_last_low_time,"equal-low pool; broker OHLC structure only");
              }
            else
              {
               m_equal_low_level=(m_equal_low_level*(double)m_equal_low_count+value)/(double)(m_equal_low_count+1);
               m_equal_low_count++;
               m_equal_low_time=tm;
              }
           }
        }
      m_last_low=value; m_last_low_time=tm; m_have_low=true;
     }

   void            ProcessCloseBreaks(const MqlRates &bar,const datetime available,
                                      const double atr,SStructureEvent &out[])
     {
      bool up=m_have_high && bar.close>m_last_high+m_break_buffer;
      bool down=m_have_low && bar.close<m_last_low-m_break_buffer;
      if(up && m_last_break_high_time!=m_last_high_time)
        {
         bool choch=(m_trend<0);
         if(choch)
            Emit(out,MS_STRUCTURE_INVALIDATED,1,bar.close,m_last_high,bar.time,available,m_last_high_time,"bearish structure invalidated by closed close above swing high");
         Emit(out,(choch?MS_CHOCH_UP:MS_BOS_UP),1,bar.close,m_last_high,bar.time,available,m_last_high_time,
              choch?"first confirmed break against bearish state":"confirmed close above latest swing high");
         m_trend=1; m_last_break_high_time=m_last_high_time;
        }
      else if(down && m_last_break_low_time!=m_last_low_time)
        {
         bool choch=(m_trend>0);
         if(choch)
            Emit(out,MS_STRUCTURE_INVALIDATED,-1,bar.close,m_last_low,bar.time,available,m_last_low_time,"bullish structure invalidated by closed close below swing low");
         Emit(out,(choch?MS_CHOCH_DOWN:MS_BOS_DOWN),-1,bar.close,m_last_low,bar.time,available,m_last_low_time,
              choch?"first confirmed break against bullish state":"confirmed close below latest swing low");
         m_trend=-1; m_last_break_low_time=m_last_low_time;
        }

      // Liquidity is limited to active equal-pivot pools, not every swing.
      if(m_equal_high_active && !m_equal_high_consumed && bar.time>m_equal_high_time)
        {
         if(bar.close>m_equal_high_level+m_break_buffer)
           {
            Emit(out,MS_LIQUIDITY_BREAKOUT_HIGH,1,bar.close,m_equal_high_level,bar.time,available,m_equal_high_time,"closed breakout through equal-high pool");
            m_equal_high_consumed=true;
           }
         else if(bar.high>m_equal_high_level+m_sweep_penetration && bar.close<=m_equal_high_level)
           {
            Emit(out,MS_LIQUIDITY_SWEEP_HIGH,-1,bar.high,m_equal_high_level,bar.time,available,m_equal_high_time,"wick penetrated equal highs and closed back at/below pool");
            m_equal_high_consumed=true;
           }
        }
      if(m_equal_low_active && !m_equal_low_consumed && bar.time>m_equal_low_time)
        {
         if(bar.close<m_equal_low_level-m_break_buffer)
           {
            Emit(out,MS_LIQUIDITY_BREAKOUT_LOW,-1,bar.close,m_equal_low_level,bar.time,available,m_equal_low_time,"closed breakout through equal-low pool");
            m_equal_low_consumed=true;
           }
         else if(bar.low<m_equal_low_level-m_sweep_penetration && bar.close>=m_equal_low_level)
           {
            Emit(out,MS_LIQUIDITY_SWEEP_LOW,1,bar.low,m_equal_low_level,bar.time,available,m_equal_low_time,"wick penetrated equal lows and closed back at/above pool");
            m_equal_low_consumed=true;
           }
        }

      if(atr>0.0 && MathIsValidNumber(atr))
        {
         double range=bar.high-bar.low;
         double body=MathAbs(bar.close-bar.open);
         if(range>0.0 && body>=m_displacement_atr*atr && body/range>=m_min_body_fraction)
           {
            if(bar.close>bar.open)
               Emit(out,MS_BULL_DISPLACEMENT,1,bar.close,bar.open,bar.time,available,0,"closed bullish body exceeds ATR and body-fraction thresholds");
            else if(bar.close<bar.open)
               Emit(out,MS_BEAR_DISPLACEMENT,-1,bar.close,bar.open,bar.time,available,0,"closed bearish body exceeds ATR and body-fraction thresholds");
           }
        }
     }

public:
                     CStructureEngine() { Reset(); }
   void              Reset()
     {
      m_symbol=""; m_tf=PERIOD_CURRENT; m_left=2; m_right=2;
      m_equal_tolerance=0.0; m_break_buffer=0.0; m_sweep_penetration=0.0;
      m_displacement_atr=1.0; m_min_body_fraction=0.60;
      m_trend=0; m_last_processed=0;
      m_have_high=false; m_last_high=0.0; m_last_high_time=0;
      m_have_low=false; m_last_low=0.0; m_last_low_time=0;
      m_equal_high_active=false; m_equal_high_level=0.0; m_equal_high_count=0;
      m_equal_high_time=0; m_equal_high_consumed=false;
      m_equal_low_active=false; m_equal_low_level=0.0; m_equal_low_count=0;
      m_equal_low_time=0; m_equal_low_consumed=false;
      m_last_break_high_time=0; m_last_break_low_time=0;
     }

   bool              Init(const string symbol,const ENUM_TIMEFRAMES tf,
                           const int left_bars,const int right_bars,
                           const double equal_tolerance,const double break_buffer,
                           const double sweep_penetration,const double displacement_atr,
                           const double min_body_fraction)
     {
      if(symbol=="" || left_bars<1 || right_bars<1 || equal_tolerance<0.0 ||
         break_buffer<0.0 || sweep_penetration<0.0 || displacement_atr<=0.0 ||
         min_body_fraction<0.0 || min_body_fraction>1.0 ||
         !MathIsValidNumber(equal_tolerance) || !MathIsValidNumber(break_buffer) ||
         !MathIsValidNumber(sweep_penetration) || !MathIsValidNumber(displacement_atr) ||
         !MathIsValidNumber(min_body_fraction)) return false;
      Reset(); m_symbol=symbol; m_tf=tf; m_left=left_bars; m_right=right_bars;
      m_equal_tolerance=equal_tolerance; m_break_buffer=break_buffer;
      m_sweep_penetration=sweep_penetration; m_displacement_atr=displacement_atr;
      m_min_body_fraction=min_body_fraction;
      return true;
     }

   int               Trend() const { return m_trend; }
   datetime          LastProcessedTime() const { return m_last_processed; }
   bool              HasSwingHigh() const { return m_have_high; }
   bool              HasSwingLow() const { return m_have_low; }
   double            LastSwingHigh() const { return m_last_high; }
   double            LastSwingLow() const { return m_last_low; }

   // rates must be chronological (oldest first); closed_index must refer to a
   // closed bar. availability_time is normally the next bar's open time. Calls
   // for the same/older closed-bar time are successful no-ops (empty out[]).
   bool              ProcessClosed(const MqlRates &rates[],const int closed_index,
                                    const datetime availability_time,const double atr,
                                    SStructureEvent &out[])
     {
      ArrayResize(out,0);
      int n=ArraySize(rates);
      if(closed_index<0 || closed_index>=n || closed_index<m_left+m_right ||
         availability_time<=rates[closed_index].time) return false;
      int pivot=closed_index-m_right;
      if(!ValidWindow(rates,pivot-m_left,closed_index)) return false;
      if(rates[closed_index].time<=m_last_processed) return true;
      if(IsSwingHigh(rates,pivot)) ProcessHigh(rates[pivot].high,rates[pivot].time,availability_time,out);
      if(IsSwingLow(rates,pivot)) ProcessLow(rates[pivot].low,rates[pivot].time,availability_time,out);
      ProcessCloseBreaks(rates[closed_index],availability_time,atr,out);
      m_last_processed=rates[closed_index].time;
      return true;
     }

   // Zero-copy adapter for the production market-data cache. It only reads
   // bounded getters in the pivot window; no per-bar MqlRates allocation/copy.
   bool              ProcessClosed(const CBarSeries &bars,const int closed_index,
                                    const datetime availability_time,const double atr,
                                    SStructureEvent &out[])
     {
      ArrayResize(out,0);
      if(!bars.Ready() || closed_index<0 || closed_index>bars.ClosedIndex() ||
         closed_index<m_left+m_right || availability_time<=bars.T(closed_index)) return false;
      if(bars.T(closed_index)<=m_last_processed) return true;
      int pivot=closed_index-m_right;
      if(!ValidSeriesWindow(bars,pivot-m_left,closed_index)) return false;
      if(IsSwingHighSeries(bars,pivot)) ProcessHigh(bars.H(pivot),bars.T(pivot),availability_time,out);
      if(IsSwingLowSeries(bars,pivot)) ProcessLow(bars.L(pivot),bars.T(pivot),availability_time,out);
      MqlRates bar;
      bar.time=bars.T(closed_index); bar.open=bars.O(closed_index);
      bar.high=bars.H(closed_index); bar.low=bars.L(closed_index);
      bar.close=bars.C(closed_index);
      ProcessCloseBreaks(bar,availability_time,atr,out);
      m_last_processed=bars.T(closed_index);
      return true;
     }
  };

#endif
