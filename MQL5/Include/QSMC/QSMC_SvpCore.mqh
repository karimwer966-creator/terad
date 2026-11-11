//+------------------------------------------------------------------+
//|                                                 QSMC_SvpCore.mqh |
//|  SMC + Volume Profile pipeline - types, parameters, ATR, swings,  |
//|  market structure (HH/HL/LH/LL, BOS, CHoCH) and displacement.     |
//|                                                                   |
//|  CONTRACT (every function in the QSMC_Svp* modules)               |
//|  * Bars arrive OLDEST FIRST in an MqlRates array of CLOSED bars;  |
//|    index n-1 is the newest closed bar. The forming bar is never   |
//|    passed in, so nothing here can repaint.                        |
//|  * A value attached to bar i is computed from bars 0..i only. A   |
//|    swing is usable from its CONFIRMATION bar (pivot + right), not |
//|    from its pivot bar. tools/test_qsmc_smcvp.py replays every     |
//|    engine on a growing prefix and asserts the past never changes. |
//|  * PURE: no terminal call, no chart object, no order, no global   |
//|    state. Direction is never derived from a moving average.       |
//|  * Bullish and bearish paths are the same code with the sign      |
//|    flipped; the test suite mirrors every scenario to prove it.    |
//+------------------------------------------------------------------+
#ifndef QSMC_SVP_CORE_MQH
#define QSMC_SVP_CORE_MQH

#define SVP_MAX_STEPS    10
#define SVP_MAX_NODES    6
#define SVP_VP_MAX_BINS  600

enum ENUM_SVP_SWING_LABEL
{
   SVP_SW_NONE = 0,
   SVP_SW_HH   = 1,   // higher high
   SVP_SW_LH   = 2,   // lower high
   SVP_SW_HL   = 3,   // higher low
   SVP_SW_LL   = 4    // lower low
};

enum ENUM_SVP_EVENT
{
   SVP_EV_NONE  = 0,
   SVP_EV_BOS   = 1,  // break of structure: continuation
   SVP_EV_CHOCH = 2   // change of character: the first break against the trend
};

enum ENUM_SVP_SWEEP_STATE
{
   SVP_SWEEP_NONE               = 0,
   SVP_SWEEP_DETECTED           = 1,  // wick through the level, closed back, awaiting confirmation
   SVP_SWEEP_CONFIRMED          = 2,  // + displacement + structure shift
   SVP_SWEEP_BREAKOUT_CONFIRMED = 3,  // closes held beyond the level: genuine breakout
   SVP_SWEEP_FALSE_BREAKOUT     = 4,  // closed beyond, then closed back inside
   SVP_SWEEP_UNCONFIRMED        = 5   // penetration without either confirmation
};

enum ENUM_SVP_ZONE_STATE
{
   SVP_ZS_NONE        = 0,
   SVP_ZS_DETECTED    = 1,  // geometry exists, no structural backing yet
   SVP_ZS_VALIDATED   = 2,  // fresh and backed by displacement / a structure break
   SVP_ZS_PARTIAL     = 3,  // price entered the zone without consuming it
   SVP_ZS_MITIGATED   = 4,  // retested (OB) / fully filled (FVG), not closed through
   SVP_ZS_INVALIDATED = 5,  // closed through the far edge
   SVP_ZS_EXPIRED     = 6   // too old to matter
};

enum ENUM_SVP_VP_KIND
{
   SVP_VP_SESSION = 1,   // Session (Asia / London / New York, server hours)
   SVP_VP_DAILY   = 2,   // Daily
   SVP_VP_WEEKLY  = 3,   // Weekly
   SVP_VP_RANGE   = 4    // Visible range (what the chart shows)
};

enum ENUM_SVP_VP_CONTEXT
{
   SVP_VPC_NONE           = 0,
   SVP_VPC_POC_ACCEPTANCE = 1,
   SVP_VPC_POC_REJECTION  = 2,
   SVP_VPC_VAH_REJECTION  = 3,
   SVP_VPC_VAL_REJECTION  = 4,
   SVP_VPC_VAH_ACCEPTANCE = 5,
   SVP_VPC_VAL_ACCEPTANCE = 6,
   SVP_VPC_HVN_ACCEPTANCE = 7,
   SVP_VPC_LVN_REJECTION  = 8,
   SVP_VPC_LVN_TRAVERSAL  = 9
};

enum ENUM_SVP_DECISION
{
   SVP_DECISION_SELL = -1,
   SVP_DECISION_WAIT = 0,
   SVP_DECISION_BUY  = 1
};

enum ENUM_SVP_STEP_STATUS
{
   SVP_STEP_NA      = 0,   // could not be evaluated (a prerequisite is missing)
   SVP_STEP_PASS    = 1,
   SVP_STEP_FAIL    = 2,
   SVP_STEP_PENDING = 3    // the condition is forming; nothing is wrong yet
};

struct SSvpParams
{
   //--- swings / structure
   int    h4_swing;            // bars each side of an H4 pivot
   int    h1_swing_ext;        // H1 external (major) structure
   int    h1_swing_int;        // H1 internal structure
   int    m15_swing;           // M15 liquidity pivots and M15 structure
   int    atr_period;
   //--- liquidity map
   int    liq_lookback;        // M15 bars searched for resting liquidity
   double liq_eq_tol_atr;      // equal highs / lows tolerance, ATR multiple
   double liq_merge_atr;       // nearby levels merge into one zone, ATR multiple
   int    liq_tol_ticks;       // floor for both tolerances, in ticks
   //--- sweep engine
   double sw_pen_min_atr;      // minimum penetration to count as "taken"
   int    sw_pen_min_ticks;
   double sw_pen_max_atr;      // deeper than this is a breakout attempt, not a sweep
   double sw_reject_min;       // (extreme - close) / range of the taking bar
   int    sw_confirm_bars;     // bars allowed for displacement + structure shift
   int    sw_accept_bars;      // consecutive closes beyond the level = breakout
   double sw_accept_atr;       // buffer for "closed beyond", ATR multiple
   int    sw_max_age;          // an older event no longer drives a setup
   //--- displacement
   double disp_body_atr;       // body >= this multiple of the PREVIOUS bar's ATR
   double disp_body_ratio;     // body / range
   //--- order blocks / fair value gaps
   int    ob_lookback;
   double fvg_min_atr;
   int    zone_max_age;
   double zone_merge_atr;
   int    zone_validate_bars;
   //--- volume profile
   ENUM_SVP_VP_KIND vp_kind;
   double vp_value_fraction;
   double vp_row_atr;
   int    vp_row_ticks;        // > 0 overrides vp_row_atr
   int    vp_min_bars;         // a developing profile thinner than this defers to the previous one
   double vp_hvn_fraction;     // HVN >= fraction of the POC row
   double vp_lvn_fraction;     // LVN <= fraction of the median row
   bool   vp_use_real_volume;
   double vp_tol_atr;
   int    vp_accept_bars;
   bool   vp_required;         // true: a setup needs supportive volume context
   int    sess_asia_start;     // server hours
   int    sess_london_start;
   int    sess_ny_start;
   int    sess_ny_end;
   datetime vp_range_from;     // explicit window, used when vp_kind is SVP_VP_RANGE
   datetime vp_range_to;
   double vp_grid_phase;       // price offset of the row lattice; 0 = rows start on multiples of the row height
   //--- entry / risk
   int    entry_valid_bars;    // a confirmed retest stays actionable this many bars
   double entry_max_chase_atr; // further than this from the zone = missed
   double sl_buffer_atr;
   double min_rr;
   //--- symbol
   double tick_size;
   double point;
   int    digits;
   double min_stop_distance;   // broker stops level, in price
   double spread;              // in price
};

void SVP_DefaultParams(SSvpParams &p)
{
   p.h4_swing=3; p.h1_swing_ext=5; p.h1_swing_int=2; p.m15_swing=3; p.atr_period=14;
   p.liq_lookback=320; p.liq_eq_tol_atr=0.10; p.liq_merge_atr=0.25; p.liq_tol_ticks=5;
   p.sw_pen_min_atr=0.02; p.sw_pen_min_ticks=2; p.sw_pen_max_atr=1.50; p.sw_reject_min=0.50;
   p.sw_confirm_bars=8; p.sw_accept_bars=3; p.sw_accept_atr=0.05; p.sw_max_age=32;
   p.disp_body_atr=1.00; p.disp_body_ratio=0.60;
   p.ob_lookback=5; p.fvg_min_atr=0.10; p.zone_max_age=96; p.zone_merge_atr=0.10; p.zone_validate_bars=6;
   p.vp_kind=SVP_VP_DAILY; p.vp_value_fraction=0.70; p.vp_row_atr=0.10; p.vp_row_ticks=0;
   p.vp_min_bars=16; p.vp_hvn_fraction=0.70; p.vp_lvn_fraction=0.50; p.vp_use_real_volume=false;
   p.vp_tol_atr=0.15; p.vp_accept_bars=3; p.vp_required=true;
   p.sess_asia_start=0; p.sess_london_start=7; p.sess_ny_start=13; p.sess_ny_end=22;
   p.vp_range_from=0; p.vp_range_to=0; p.vp_grid_phase=0.0;
   p.entry_valid_bars=2; p.entry_max_chase_atr=1.00; p.sl_buffer_atr=0.20; p.min_rr=2.00;
   p.tick_size=0.01; p.point=0.01; p.digits=2; p.min_stop_distance=0.0; p.spread=0.0;
}

// Clamp every tunable into a range in which the engines are well defined, so a
// mistyped input can degrade a setting but can never divide by zero or loop.
void SVP_SanitizeParams(SSvpParams &p)
{
   if(p.h4_swing<1) p.h4_swing=1;             if(p.h4_swing>20) p.h4_swing=20;
   if(p.h1_swing_ext<1) p.h1_swing_ext=1;     if(p.h1_swing_ext>20) p.h1_swing_ext=20;
   if(p.h1_swing_int<1) p.h1_swing_int=1;     if(p.h1_swing_int>p.h1_swing_ext) p.h1_swing_int=p.h1_swing_ext;
   if(p.m15_swing<1) p.m15_swing=1;           if(p.m15_swing>20) p.m15_swing=20;
   if(p.atr_period<2) p.atr_period=2;         if(p.atr_period>200) p.atr_period=200;
   if(p.liq_lookback<40) p.liq_lookback=40;   if(p.liq_lookback>2000) p.liq_lookback=2000;
   if(!(p.liq_eq_tol_atr>=0.0)) p.liq_eq_tol_atr=0.10;
   if(!(p.liq_merge_atr>=0.0)) p.liq_merge_atr=0.25;
   if(p.liq_tol_ticks<0) p.liq_tol_ticks=0;
   if(!(p.sw_pen_min_atr>=0.0)) p.sw_pen_min_atr=0.02;
   if(p.sw_pen_min_ticks<1) p.sw_pen_min_ticks=1;
   if(!(p.sw_pen_max_atr>0.0)) p.sw_pen_max_atr=1.50;
   if(!(p.sw_reject_min>=0.0) || p.sw_reject_min>1.0) p.sw_reject_min=0.50;
   if(p.sw_confirm_bars<1) p.sw_confirm_bars=1;   if(p.sw_confirm_bars>64) p.sw_confirm_bars=64;
   if(p.sw_accept_bars<1) p.sw_accept_bars=1;     if(p.sw_accept_bars>p.sw_confirm_bars) p.sw_accept_bars=p.sw_confirm_bars;
   if(!(p.sw_accept_atr>=0.0)) p.sw_accept_atr=0.05;
   if(p.sw_max_age<p.sw_confirm_bars) p.sw_max_age=p.sw_confirm_bars;
   if(!(p.disp_body_atr>0.0)) p.disp_body_atr=1.00;
   if(!(p.disp_body_ratio>0.0) || p.disp_body_ratio>1.0) p.disp_body_ratio=0.60;
   if(p.ob_lookback<1) p.ob_lookback=1;       if(p.ob_lookback>20) p.ob_lookback=20;
   if(!(p.fvg_min_atr>=0.0)) p.fvg_min_atr=0.10;
   if(p.zone_max_age<8) p.zone_max_age=8;
   if(!(p.zone_merge_atr>=0.0)) p.zone_merge_atr=0.10;
   if(p.zone_validate_bars<1) p.zone_validate_bars=1;
   if(!(p.vp_value_fraction>=0.50) || p.vp_value_fraction>0.95) p.vp_value_fraction=0.70;
   if(!(p.vp_row_atr>0.0)) p.vp_row_atr=0.10;
   if(p.vp_row_ticks<0) p.vp_row_ticks=0;
   if(p.vp_min_bars<2) p.vp_min_bars=2;
   if(!(p.vp_hvn_fraction>0.0) || p.vp_hvn_fraction>1.0) p.vp_hvn_fraction=0.70;
   if(!(p.vp_lvn_fraction>0.0) || p.vp_lvn_fraction>1.0) p.vp_lvn_fraction=0.50;
   if(!(p.vp_tol_atr>=0.0)) p.vp_tol_atr=0.15;
   if(p.vp_accept_bars<2) p.vp_accept_bars=2;
   if(!MathIsValidNumber(p.vp_grid_phase)) p.vp_grid_phase=0.0;
   if(p.sess_asia_start<0 || p.sess_asia_start>23) p.sess_asia_start=0;
   if(p.sess_london_start<=p.sess_asia_start || p.sess_london_start>23) p.sess_london_start=p.sess_asia_start+7;
   if(p.sess_ny_start<=p.sess_london_start || p.sess_ny_start>23) p.sess_ny_start=p.sess_london_start+6;
   if(p.sess_ny_end<=p.sess_ny_start || p.sess_ny_end>24) p.sess_ny_end=24;
   if(p.entry_valid_bars<0) p.entry_valid_bars=0;
   if(!(p.entry_max_chase_atr>0.0)) p.entry_max_chase_atr=1.00;
   if(!(p.sl_buffer_atr>=0.0)) p.sl_buffer_atr=0.20;
   if(!(p.min_rr>0.0)) p.min_rr=2.00;
   if(!(p.tick_size>0.0)) p.tick_size=(p.point>0.0?p.point:0.01);
   if(!(p.point>0.0)) p.point=p.tick_size;
   if(p.digits<0) p.digits=0;                 if(p.digits>8) p.digits=8;
   if(!(p.min_stop_distance>=0.0)) p.min_stop_distance=0.0;
   if(!(p.spread>=0.0)) p.spread=0.0;
}

struct SSvpSwing
{
   int                  index;       // pivot bar
   int                  confirm;     // first bar on which the pivot is known (index + right)
   datetime             time;
   double               price;
   bool                 is_high;
   ENUM_SVP_SWING_LABEL label;
   int                  broken_at;   // bar whose CLOSE went beyond it, -1 while it stands
};

struct SSvpStructEvent
{
   ENUM_SVP_EVENT kind;
   int            direction;         // +1 bullish, -1 bearish
   int            break_index;       // the closed bar that broke the level
   datetime       break_time;
   double         level;             // the broken swing price
   int            swing_index;
   datetime       swing_time;
};

struct SSvpStructure
{
   bool                 valid;
   int                  bars;
   int                  swing_count;
   int                  event_count;
   int                  trend;             // +1 / -1 / 0 from BOS and CHoCH only
   int                  bias;              // trend refined by the swing sequence, 0 = neutral
   ENUM_SVP_EVENT       last_kind;
   int                  last_direction;
   int                  last_index;
   datetime             last_time;
   double               last_level;
   double               high_price;        // latest confirmed swing high
   datetime             high_time;
   ENUM_SVP_SWING_LABEL high_label;
   bool                 high_standing;     // not yet closed through
   double               low_price;         // latest confirmed swing low
   datetime             low_time;
   ENUM_SVP_SWING_LABEL low_label;
   bool                 low_standing;
   double               invalidation;      // a close beyond it is a CHoCH against the trend; 0 = none
   string               text;
};

string SVP_PriceText(const double price,const int digits)
{
   if(!(price>0.0) || !MathIsValidNumber(price)) return "N/A";
   return DoubleToString(price,digits);
}

string SVP_ClockText(const datetime t)
{
   if(t<=0) return "N/A";
   return TimeToString(t,TIME_DATE|TIME_MINUTES);
}

string SVP_DirText(const int direction)
{
   if(direction>0) return "BULLISH";
   if(direction<0) return "BEARISH";
   return "NEUTRAL";
}

string SVP_LabelText(const ENUM_SVP_SWING_LABEL label)
{
   if(label==SVP_SW_HH) return "HH";
   if(label==SVP_SW_LH) return "LH";
   if(label==SVP_SW_HL) return "HL";
   if(label==SVP_SW_LL) return "LL";
   return "--";
}

string SVP_EventText(const ENUM_SVP_EVENT kind)
{
   if(kind==SVP_EV_BOS) return "BOS";
   if(kind==SVP_EV_CHOCH) return "CHoCH";
   return "none";
}

bool SVP_BarValid(const MqlRates &b)
{
   return (MathIsValidNumber(b.open) && MathIsValidNumber(b.high) && MathIsValidNumber(b.low) &&
           MathIsValidNumber(b.close) && b.low>0.0 && b.high>=b.low && b.time>0);
}

// Bars usable by the engines: n clamped to the array. One malformed or
// out-of-order bar makes the whole series unusable (0), so a damaged history
// produces N/A instead of an analysis built on garbage.
int SVP_UsableBars(const MqlRates &r[],const int n)
{
   int have=ArraySize(r);
   int m=(n<have?n:have);
   if(m<0) m=0;
   for(int i=0;i<m;i++)
   {
      if(!SVP_BarValid(r[i])) return 0;
      if(i>0 && r[i].time<=r[i-1].time) return 0;
   }
   return m;
}

double SVP_TrueRange(const MqlRates &r[],const int i)
{
   double tr=r[i].high-r[i].low;
   if(i>0)
   {
      double a=MathAbs(r[i].high-r[i-1].close);
      double b=MathAbs(r[i].low-r[i-1].close);
      if(a>tr) tr=a;
      if(b>tr) tr=b;
   }
   return tr;
}

// Simple moving average of the true range. atr[i] uses bars i-period+1..i only
// (and the close of the bar before them); before a full window exists it
// averages what there is, so it is never zero on a valid bar and never looks
// ahead. Each value is summed afresh from its own window: the result does not
// depend on where the series starts, so the same bars always give the same
// number (a running sum would carry rounding from the start of the history).
bool SVP_ATR(const MqlRates &r[],const int n,const int period,double &atr[])
{
   if(n<=0 || period<1 || ArrayResize(atr,n)!=n) return false;
   double tr[];
   if(ArrayResize(tr,n)!=n) return false;
   for(int i=0;i<n;i++) tr[i]=SVP_TrueRange(r,i);
   for(int i=0;i<n;i++)
   {
      int first=i-period+1;
      if(first<0) first=0;
      double sum=0.0;
      for(int k=first;k<=i;k++) sum+=tr[k];
      atr[i]=sum/(double)(i-first+1);
      if(!(atr[i]>0.0)) atr[i]=(i>0?atr[i-1]:0.0);
   }
   return true;
}

// Fractal pivots. A high needs `left` strictly lower highs before it and
// `right` lower-or-equal highs after it (ties resolve to the EARLIER bar, once).
// Only pivots whose confirmation bar exists are returned.
int SVP_FindSwings(const MqlRates &r[],const int n,const int left,const int right,SSvpSwing &out[])
{
   ArrayResize(out,0);
   if(n<left+right+1 || left<1 || right<1) return 0;
   int count=0;
   double prev_high=0.0,prev_low=0.0;
   bool have_high=false,have_low=false;
   for(int i=left;i<n-right;i++)
   {
      bool is_high=true,is_low=true;
      for(int k=1;k<=left && (is_high || is_low);k++)
      {
         if(r[i-k].high>=r[i].high) is_high=false;
         if(r[i-k].low<=r[i].low) is_low=false;
      }
      for(int k=1;k<=right && (is_high || is_low);k++)
      {
         if(r[i+k].high>r[i].high) is_high=false;
         if(r[i+k].low<r[i].low) is_low=false;
      }
      if(!is_high && !is_low) continue;
      for(int pass=0;pass<2;pass++)
      {
         bool high_pass=(pass==0);
         if(high_pass && !is_high) continue;
         if(!high_pass && !is_low) continue;
         if(ArrayResize(out,count+1,64)!=count+1) return count;
         out[count].index=i;
         out[count].confirm=i+right;
         out[count].time=r[i].time;
         out[count].is_high=high_pass;
         out[count].broken_at=-1;
         if(high_pass)
         {
            out[count].price=r[i].high;
            out[count].label=(have_high?(r[i].high>prev_high?SVP_SW_HH:SVP_SW_LH):SVP_SW_NONE);
            prev_high=r[i].high; have_high=true;
         }
         else
         {
            out[count].price=r[i].low;
            out[count].label=(have_low?(r[i].low>prev_low?SVP_SW_HL:SVP_SW_LL):SVP_SW_NONE);
            prev_low=r[i].low; have_low=true;
         }
         count++;
      }
   }
   return count;
}

void SVP_StructureReset(SSvpStructure &st)
{
   st.valid=false; st.bars=0; st.swing_count=0; st.event_count=0; st.trend=0; st.bias=0;
   st.last_kind=SVP_EV_NONE; st.last_direction=0; st.last_index=-1; st.last_time=0; st.last_level=0.0;
   st.high_price=0.0; st.high_time=0; st.high_label=SVP_SW_NONE; st.high_standing=false;
   st.low_price=0.0; st.low_time=0; st.low_label=SVP_SW_NONE; st.low_standing=false;
   st.invalidation=0.0; st.text="N/A";
}

// Market structure of one timeframe at one swing length.
//   * the latest CONFIRMED swing high / low are the structural levels;
//   * a CLOSE beyond one is a break: CHoCH when it is against the current trend,
//     BOS otherwise (a wick through a level is liquidity being taken, not a break);
//   * every level breaks at most once.
// `swings` and `events` are filled oldest first.
bool SVP_TrackStructure(const MqlRates &r[],const int n,const int left,const int right,
                        SSvpSwing &swings[],SSvpStructEvent &events[],SSvpStructure &st)
{
   SVP_StructureReset(st);
   ArrayResize(events,0);
   int sc=SVP_FindSwings(r,n,left,right,swings);
   st.bars=n;
   st.swing_count=sc;
   if(n<left+right+2) { st.text="N/A (history too short)"; return false; }
   int next=0;            // next swing (by confirmation) not yet activated
   int cur_high=-1,cur_low=-1;
   int trend=0,ec=0;
   for(int i=0;i<n;i++)
   {
      while(next<sc && swings[next].confirm<=i)
      {
         if(swings[next].is_high) cur_high=next; else cur_low=next;
         next++;
      }
      int dir=0,broken=-1;
      if(cur_high>=0 && swings[cur_high].broken_at<0 && r[i].close>swings[cur_high].price) { dir=1; broken=cur_high; }
      else if(cur_low>=0 && swings[cur_low].broken_at<0 && r[i].close<swings[cur_low].price) { dir=-1; broken=cur_low; }
      if(dir==0) continue;
      swings[broken].broken_at=i;
      if(ArrayResize(events,ec+1,32)!=ec+1) break;
      events[ec].kind=((trend!=0 && trend!=dir)?SVP_EV_CHOCH:SVP_EV_BOS);
      events[ec].direction=dir;
      events[ec].break_index=i;
      events[ec].break_time=r[i].time;
      events[ec].level=swings[broken].price;
      events[ec].swing_index=swings[broken].index;
      events[ec].swing_time=swings[broken].time;
      ec++;
      trend=dir;
   }
   st.event_count=ec;
   st.trend=trend;
   if(ec>0)
   {
      st.last_kind=events[ec-1].kind; st.last_direction=events[ec-1].direction;
      st.last_index=events[ec-1].break_index; st.last_time=events[ec-1].break_time;
      st.last_level=events[ec-1].level;
   }
   if(cur_high>=0)
   {
      st.high_price=swings[cur_high].price; st.high_time=swings[cur_high].time;
      st.high_label=swings[cur_high].label; st.high_standing=(swings[cur_high].broken_at<0);
   }
   if(cur_low>=0)
   {
      st.low_price=swings[cur_low].price; st.low_time=swings[cur_low].time;
      st.low_label=swings[cur_low].label; st.low_standing=(swings[cur_low].broken_at<0);
   }
   // Bias: the trend counts only when the swing sequence agrees with it, or the
   // last event was a continuation break. A fresh CHoCH is a warning, not a bias.
   st.bias=0;
   if(trend>0 && (st.last_kind==SVP_EV_BOS || (st.high_label==SVP_SW_HH && st.low_label==SVP_SW_HL))) st.bias=1;
   if(trend<0 && (st.last_kind==SVP_EV_BOS || (st.high_label==SVP_SW_LH && st.low_label==SVP_SW_LL))) st.bias=-1;
   if(trend>0 && st.low_standing) st.invalidation=st.low_price;
   if(trend<0 && st.high_standing) st.invalidation=st.high_price;
   st.valid=(sc>=2);
   return st.valid;
}

string SVP_StructureText(const SSvpStructure &st,const int digits)
{
   if(!st.valid) return "N/A";
   string s=SVP_DirText(st.trend);
   if(st.last_kind!=SVP_EV_NONE)
      s+=" | "+(st.last_direction>0?"bullish ":"bearish ")+SVP_EventText(st.last_kind)+" @ "+
         SVP_PriceText(st.last_level,digits)+" ("+SVP_ClockText(st.last_time)+")";
   else
      s+=" | no break yet";
   s+=" | "+SVP_LabelText(st.high_label)+"/"+SVP_LabelText(st.low_label);
   return s;
}

// A displacement candle: a body that is large against the volatility that
// existed BEFORE it (the previous bar's ATR, so the candle cannot inflate its
// own yardstick) and that fills most of its range.
bool SVP_IsDisplacement(const MqlRates &r[],const double &atr[],const int i,const int direction,
                        const double body_atr,const double body_ratio)
{
   if(i<1 || i>=ArraySize(r) || i>=ArraySize(atr) || direction==0) return false;
   double body=r[i].close-r[i].open;
   if(direction<0) body=-body;
   double range=r[i].high-r[i].low;
   if(!(body>0.0) || !(range>0.0) || !(atr[i-1]>0.0)) return false;
   return (body>=body_atr*atr[i-1] && body/range>=body_ratio);
}

// First structure event of `direction` whose break bar lies in [from,to]. -1 = none.
int SVP_FindEvent(const SSvpStructEvent &events[],const int direction,const int from,const int to)
{
   int n=ArraySize(events);
   for(int i=0;i<n;i++)
      if(events[i].direction==direction && events[i].break_index>=from && events[i].break_index<=to) return i;
   return -1;
}

#endif
//+------------------------------------------------------------------+
