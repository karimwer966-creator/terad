//+------------------------------------------------------------------+
//|                                             QSMC_SvpDecision.mqh |
//|  The unified decision engine of the SMC + Volume Profile pipeline |
//|                                                                   |
//|   H4 bias -> H1 structure -> M15 liquidity -> liquidity sweep ->  |
//|   displacement -> BOS/CHoCH -> OB/FVG -> volume profile ->        |
//|   entry validation -> risk/reward validation                      |
//|                                                                   |
//|  ONE function evaluates a direction (SVP_EvaluateSide); it is run |
//|  for BUY and for SELL with the sign flipped, and only then is the |
//|  result resolved into exactly one state:                          |
//|     BUY SETUP   every step passed for the long side only          |
//|     SELL SETUP  every step passed for the short side only         |
//|     WAIT        anything else - incomplete, conflicting,          |
//|                 invalidated, or risk/reward insufficient          |
//|  Every step reports PASS / FAIL / PENDING / N/A with the numbers  |
//|  it used. Nothing is scored, weighted or averaged: a missing      |
//|  confirmation cannot be bought back by another one.               |
//|                                                                   |
//|  The stop is structural (beyond the swept extreme and the far     |
//|  edge of the entry zone, plus a volatility buffer, never closer   |
//|  than the broker minimum). The target is a real level (resting    |
//|  liquidity, an H1 swing, a volume-profile level) - never a        |
//|  multiple of the risk. No level, no plan, no setup.               |
//|                                                                   |
//|  It decides and explains. It places no order.                     |
//+------------------------------------------------------------------+
#ifndef QSMC_SVP_DECISION_MQH
#define QSMC_SVP_DECISION_MQH

#include <QSMC/QSMC_SvpCore.mqh>
#include <QSMC/QSMC_SvpLiquidity.mqh>
#include <QSMC/QSMC_SvpZones.mqh>
#include <QSMC/QSMC_SvpVolumeProfile.mqh>

#define SVP_STEP_H4        0
#define SVP_STEP_H1        1
#define SVP_STEP_LIQUIDITY 2
#define SVP_STEP_SWEEP     3
#define SVP_STEP_DISPLACE  4
#define SVP_STEP_STRUCTURE 5
#define SVP_STEP_ZONE      6
#define SVP_STEP_VOLUME    7
#define SVP_STEP_ENTRY     8
#define SVP_STEP_RR        9

#define SVP_MIN_H4_BARS  40
#define SVP_MIN_H1_BARS  60
#define SVP_MIN_M15_BARS 200

struct SSvpSide
{
   int                  direction;
   ENUM_SVP_STEP_STATUS status[SVP_MAX_STEPS];
   string               text[SVP_MAX_STEPS];
   int                  progress;        // leading PASS count, in pipeline order
   int                  blocking;        // first step that is not PASS, -1 = none
   int                  sweep_index;     // into g_svp_sweeps, -1 = none
   int                  zone_index;      // into g_svp_zones, -1 = none
   int                  entry_index;     // bar that confirmed the retest, -1 = none
   bool                 plan_valid;
   double               entry;
   double               stop;
   double               target;
   double               risk;
   double               reward;
   double               rr;
   string               stop_source;
   string               target_source;
};

struct SSvpDecision
{
   bool                 ready;           // false: history missing, every field is N/A
   datetime             bar_time;        // the closed M15 bar this decision belongs to
   ENUM_SVP_DECISION    state;
   int                  focus;           // side the explanation describes, 0 = none
   string               headline;        // BUY SETUP / SELL SETUP / WAIT
   string               reason;
   ENUM_SVP_STEP_STATUS status[SVP_MAX_STEPS];
   string               text[SVP_MAX_STEPS];
   bool                 plan_valid;
   double               entry;
   double               stop;
   double               target;
   double               risk;
   double               reward;
   double               rr;
   string               stop_source;
   string               target_source;
   bool                 tracked;         // a setup candidate exists (trigger + entry zone)
   int                  direction;
   string               setup_type;
   datetime             origin_time;     // the bar that took the liquidity
   string               anchor_id;       // the liquidity event (sweep id)
   double               zone_lo;
   double               zone_hi;
   int                  h4_bias;
   string               h4_text;
   string               h1_text;
   string               liq_text;
   string               sweep_text;
   string               zone_text;
   string               vp_text;
   bool                 vp_valid;
   double               poc;
   double               vah;
   double               val;
};

//--- the analysis snapshot of the newest closed M15 bar ------------------------
SSvpStructure   g_svp_h4;
SSvpStructure   g_svp_h1;        // external (major)
SSvpStructure   g_svp_h1_int;    // internal
SSvpStructure   g_svp_m15;
SSvpSwing       g_svp_sw_h4[];
SSvpSwing       g_svp_sw_h1[];
SSvpSwing       g_svp_sw_h1_int[];
SSvpSwing       g_svp_sw_m15[];
SSvpStructEvent g_svp_ev_h4[];
SSvpStructEvent g_svp_ev_h1[];
SSvpStructEvent g_svp_ev_h1_int[];
SSvpStructEvent g_svp_ev_m15[];
double          g_svp_atr_m15[];
SSvpLiqZone     g_svp_liq[];
SSvpSweep       g_svp_sweeps[];
SSvpZone        g_svp_zones[];
SSvpProfile     g_svp_profile;
bool            g_svp_profile_previous=false;
SSvpVpContext   g_svp_vpc;
SSvpSide        g_svp_buy;
SSvpSide        g_svp_sell;
SSvpDecision    g_svp;

string SVP_StepName(const int step)
{
   if(step==SVP_STEP_H4)        return "H4 BIAS";
   if(step==SVP_STEP_H1)        return "H1 STRUCTURE";
   if(step==SVP_STEP_LIQUIDITY) return "M15 LIQUIDITY";
   if(step==SVP_STEP_SWEEP)     return "LIQUIDITY SWEEP";
   if(step==SVP_STEP_DISPLACE)  return "DISPLACEMENT";
   if(step==SVP_STEP_STRUCTURE) return "BOS/CHoCH";
   if(step==SVP_STEP_ZONE)      return "OB/FVG";
   if(step==SVP_STEP_VOLUME)    return "VOLUME PROFILE";
   if(step==SVP_STEP_ENTRY)     return "ENTRY";
   if(step==SVP_STEP_RR)        return "RISK/REWARD";
   return "?";
}

string SVP_StatusText(const ENUM_SVP_STEP_STATUS s)
{
   if(s==SVP_STEP_PASS)    return "PASS";
   if(s==SVP_STEP_FAIL)    return "FAIL";
   if(s==SVP_STEP_PENDING) return "PENDING";
   return "N/A";
}

string SVP_DecisionText(const ENUM_SVP_DECISION d)
{
   if(d==SVP_DECISION_BUY)  return "BUY SETUP";
   if(d==SVP_DECISION_SELL) return "SELL SETUP";
   return "WAIT";
}

void SVP_SideReset(SSvpSide &s,const int direction)
{
   s.direction=direction;
   for(int i=0;i<SVP_MAX_STEPS;i++) { s.status[i]=SVP_STEP_NA; s.text[i]="N/A"; }
   s.progress=0; s.blocking=0; s.sweep_index=-1; s.zone_index=-1; s.entry_index=-1;
   s.plan_valid=false; s.entry=0.0; s.stop=0.0; s.target=0.0; s.risk=0.0; s.reward=0.0; s.rr=0.0;
   s.stop_source=""; s.target_source="";
}

void SVP_DecisionReset(SSvpDecision &d)
{
   d.ready=false; d.bar_time=0; d.state=SVP_DECISION_WAIT; d.focus=0;
   d.headline="WAIT"; d.reason="N/A";
   for(int i=0;i<SVP_MAX_STEPS;i++) { d.status[i]=SVP_STEP_NA; d.text[i]="N/A"; }
   d.plan_valid=false; d.entry=0.0; d.stop=0.0; d.target=0.0; d.risk=0.0; d.reward=0.0; d.rr=0.0;
   d.stop_source=""; d.target_source="";
   d.tracked=false; d.direction=0; d.setup_type=""; d.origin_time=0; d.anchor_id="";
   d.zone_lo=0.0; d.zone_hi=0.0;
   d.h4_bias=0; d.h4_text="N/A"; d.h1_text="N/A"; d.liq_text="N/A"; d.sweep_text="N/A";
   d.zone_text="N/A"; d.vp_text="N/A"; d.vp_valid=false; d.poc=0.0; d.vah=0.0; d.val=0.0;
}

void SVP_SetStep(SSvpSide &s,const int step,const ENUM_SVP_STEP_STATUS status,const string text)
{
   if(step<0 || step>=SVP_MAX_STEPS) return;
   s.status[step]=status;
   s.text[step]=text;
}

// direction < 0 rounds down to the tick grid, > 0 rounds up, 0 to the nearest tick
double SVP_RoundTick(const double price,const double tick,const int direction)
{
   if(!(tick>0.0)) return price;
   double steps=price/tick;
   if(direction<0) steps=MathFloor(steps+1.0e-9);
   else if(direction>0) steps=MathCeil(steps-1.0e-9);
   else steps=MathRound(steps);
   return steps*tick;
}

// The newest liquidity event on `side` that is still young enough to matter:
// an actionable one first, then one awaiting confirmation, then any other.
int SVP_PickSweep(const int side,const int last,const SSvpParams &p)
{
   int n=ArraySize(g_svp_sweeps);
   int detected=-1,other=-1;
   for(int i=0;i<n;i++)
   {
      if(g_svp_sweeps[i].side!=side || last-g_svp_sweeps[i].take_index>p.sw_max_age) continue;
      if(SVP_SweepActionable(g_svp_sweeps[i])) return i;
      if(detected<0 && g_svp_sweeps[i].state==SVP_SWEEP_DETECTED) detected=i;
      if(other<0) other=i;
   }
   return (detected>=0?detected:other);
}

// Nearest INTACT liquidity zone of `side` lying beyond `price` on that side.
int SVP_NearestLiquidity(const int side,const double price)
{
   int n=ArraySize(g_svp_liq);
   int best=-1;
   for(int i=0;i<n;i++)
   {
      if(g_svp_liq[i].side!=side || g_svp_liq[i].taken_index>=0) continue;
      if((double)side*(g_svp_liq[i].level-price)<=0.0) continue;
      if(best<0 || MathAbs(g_svp_liq[i].level-price)<MathAbs(g_svp_liq[best].level-price)) best=i;
   }
   return best;
}

// The entry zone of a reversal: created by the leg that followed the sweep.
int SVP_PickZone(const int direction,const SSvpSweep &sw)
{
   int n=ArraySize(g_svp_zones);
   int ready=SVP_SweepReadyIndex(sw);
   if(ready<0) return -1;
   int best=-1,best_score=-1;
   for(int i=0;i<n;i++)
   {
      if(g_svp_zones[i].direction!=direction) continue;
      if(g_svp_zones[i].origin_index<sw.take_index-1 || g_svp_zones[i].avail_index<sw.take_index) continue;
      if(g_svp_zones[i].avail_index>ready+2) continue;
      int score=(g_svp_zones[i].backed?2:0)+(g_svp_zones[i].kind==SVP_ZONE_BOTH?2:1);
      // zones are newest first: `>=` keeps the EARLIEST zone among equals
      if(score>=best_score) { best=i; best_score=score; }
   }
   return best;
}

// Target bookkeeping: remembers the best reward:risk seen and keeps `level` as
// the pick when it pays at least min_rr and is nearer to the entry than the
// current pick. Returns true when `level` became the pick.
bool SVP_ConsiderTarget(const int d,const double entry,const double risk,const double min_rr,
                        const double level,double &pick_level,double &best_rr)
{
   double reward=(double)d*(level-entry);
   if(!(reward>0.0) || !(risk>0.0)) return false;
   double rr=reward/risk;
   if(rr>best_rr) best_rr=rr;
   if(rr<min_rr) return false;
   if(pick_level>0.0 && MathAbs(level-entry)>=MathAbs(pick_level-entry)) return false;
   pick_level=level;
   return true;
}

// One direction through the whole pipeline. Reads the snapshot globals.
void SVP_EvaluateSide(const int d,const MqlRates &m15[],const int n,const SSvpParams &p,SSvpSide &s)
{
   SVP_SideReset(s,d);
   int last=n-1;
   double atr=g_svp_atr_m15[last];
   double close_now=m15[last].close;
   string side_word=(d>0?"bullish":"bearish");
   //--- 0. H4 bias --------------------------------------------------------------
   if(!g_svp_h4.valid) SVP_SetStep(s,SVP_STEP_H4,SVP_STEP_NA,"N/A (H4 structure unavailable)");
   else if(g_svp_h4.bias==d)
      SVP_SetStep(s,SVP_STEP_H4,SVP_STEP_PASS,SVP_DirText(g_svp_h4.bias)+" (swings "+
                  SVP_LabelText(g_svp_h4.high_label)+"/"+SVP_LabelText(g_svp_h4.low_label)+
                  ", last "+SVP_EventText(g_svp_h4.last_kind)+")");
   else
      SVP_SetStep(s,SVP_STEP_H4,SVP_STEP_FAIL,"H4 is "+SVP_DirText(g_svp_h4.bias)+", a "+side_word+" setup needs "+SVP_DirText(d));
   //--- 1. H1 structure (external) ----------------------------------------------
   if(!g_svp_h1.valid) SVP_SetStep(s,SVP_STEP_H1,SVP_STEP_NA,"N/A (H1 structure unavailable)");
   else if(g_svp_h1.trend==d)
      SVP_SetStep(s,SVP_STEP_H1,SVP_STEP_PASS,side_word+" "+SVP_EventText(g_svp_h1.last_kind)+" @ "+
                  SVP_PriceText(g_svp_h1.last_level,p.digits)+
                  (g_svp_h1_int.valid && g_svp_h1_int.trend==-d?" (internal pullback in progress)":""));
   else
      SVP_SetStep(s,SVP_STEP_H1,SVP_STEP_FAIL,"H1 external structure is "+SVP_DirText(g_svp_h1.trend));
   //--- 2. liquidity and 3. sweep -------------------------------------------------
   // a long needs SELL-side liquidity (below lows) taken; a short needs buy-side
   int need=-d;
   string liq_word=(need>0?"buy-side (BSL)":"sell-side (SSL)");
   int si=SVP_PickSweep(need,last,p);
   s.sweep_index=si;
   if(si<0)
   {
      int resting=SVP_NearestLiquidity(need,close_now);
      if(resting>=0)
      {
         SVP_SetStep(s,SVP_STEP_LIQUIDITY,SVP_STEP_PASS,liq_word+" "+g_svp_liq[resting].label+" resting at "+
                     SVP_PriceText(g_svp_liq[resting].level,p.digits));
         SVP_SetStep(s,SVP_STEP_SWEEP,SVP_STEP_PENDING,"not swept yet");
      }
      else
         SVP_SetStep(s,SVP_STEP_LIQUIDITY,SVP_STEP_FAIL,"no "+liq_word+" liquidity mapped");
   }
   else
   {
      SSvpSweep sw=g_svp_sweeps[si];
      bool in_window=(last-sw.take_index<p.sw_confirm_bars);
      SVP_SetStep(s,SVP_STEP_LIQUIDITY,SVP_STEP_PASS,liq_word+" "+sw.zone_label+" "+SVP_PriceText(sw.level,p.digits)+
                  " (strength "+IntegerToString(sw.strength)+")");
      string st=SVP_SweepStateText(sw.state)+" - taken "+SVP_ClockText(sw.take_time)+", "+sw.note;
      if(SVP_SweepActionable(sw)) SVP_SetStep(s,SVP_STEP_SWEEP,SVP_STEP_PASS,st);
      else if(sw.state==SVP_SWEEP_DETECTED) SVP_SetStep(s,SVP_STEP_SWEEP,SVP_STEP_PENDING,st);
      else if(sw.state==SVP_SWEEP_FALSE_BREAKOUT && in_window) SVP_SetStep(s,SVP_STEP_SWEEP,SVP_STEP_PENDING,st);
      else SVP_SetStep(s,SVP_STEP_SWEEP,SVP_STEP_FAIL,st);
      bool waiting=(in_window && (sw.state==SVP_SWEEP_DETECTED || sw.state==SVP_SWEEP_FALSE_BREAKOUT));
      //--- 4. displacement -------------------------------------------------------
      if(sw.displacement)
         SVP_SetStep(s,SVP_STEP_DISPLACE,SVP_STEP_PASS,side_word+" displacement "+SVP_ClockText(m15[sw.disp_index].time));
      else
         SVP_SetStep(s,SVP_STEP_DISPLACE,(waiting?SVP_STEP_PENDING:SVP_STEP_FAIL),"no "+side_word+" displacement after the sweep");
      //--- 5. structure shift ----------------------------------------------------
      if(sw.structure)
         SVP_SetStep(s,SVP_STEP_STRUCTURE,SVP_STEP_PASS,"M15 "+side_word+" break of "+SVP_PriceText(sw.struct_level,p.digits)+
                     " "+SVP_ClockText(m15[sw.struct_index].time));
      else
         SVP_SetStep(s,SVP_STEP_STRUCTURE,(waiting?SVP_STEP_PENDING:SVP_STEP_FAIL),"no M15 "+side_word+" BOS/CHoCH after the sweep");
      //--- 6. entry zone ---------------------------------------------------------
      if(SVP_SweepActionable(sw))
      {
         int zi=SVP_PickZone(d,sw);
         s.zone_index=zi;
         if(zi<0) SVP_SetStep(s,SVP_STEP_ZONE,SVP_STEP_FAIL,"no "+side_word+" OB/FVG left by the displacement leg");
         else if(!SVP_ZoneAlive(g_svp_zones[zi]))
            SVP_SetStep(s,SVP_STEP_ZONE,SVP_STEP_FAIL,SVP_ZoneText(g_svp_zones[zi],p.digits));
         else
            SVP_SetStep(s,SVP_STEP_ZONE,SVP_STEP_PASS,SVP_ZoneText(g_svp_zones[zi],p.digits)+
                        (g_svp_zones[zi].touches==0?" (fresh)":""));
      }
   }
   //--- 7. volume profile -----------------------------------------------------------
   bool zone_ok=(s.zone_index>=0 && s.status[SVP_STEP_ZONE]==SVP_STEP_PASS);
   double vp_tol=p.vp_tol_atr*atr;
   if(g_svp_profile.valid && vp_tol<g_svp_profile.bin_size) vp_tol=g_svp_profile.bin_size;
   if(zone_ok)
   {
      string vt="";
      int verdict=SVP_VpVerdict(g_svp_profile,g_svp_vpc,g_svp_zones[s.zone_index].lo,g_svp_zones[s.zone_index].hi,
                                d,vp_tol,p.digits,vt);
      if(!g_svp_profile.valid)
         SVP_SetStep(s,SVP_STEP_VOLUME,(p.vp_required?SVP_STEP_FAIL:SVP_STEP_PASS),
                     (p.vp_required?"N/A - no volume profile, and confirmation is required":"N/A (not required by the settings)"));
      else if(verdict>0) SVP_SetStep(s,SVP_STEP_VOLUME,SVP_STEP_PASS,vt);
      else if(verdict<0) SVP_SetStep(s,SVP_STEP_VOLUME,SVP_STEP_FAIL,vt);
      else SVP_SetStep(s,SVP_STEP_VOLUME,(p.vp_required?SVP_STEP_FAIL:SVP_STEP_PASS),
                       vt+(p.vp_required?" - no confluence, no setup":" (not required by the settings)"));
   }
   else if(g_svp_profile.valid && g_svp_vpc.valid)
      SVP_SetStep(s,SVP_STEP_VOLUME,SVP_STEP_NA,g_svp_vpc.text+" (no entry zone to test)");
   //--- 8. entry: the zone must be retested and the retest must close back out ---
   if(zone_ok)
   {
      SSvpZone z=g_svp_zones[s.zone_index];
      double proximal=(d>0?z.hi:z.lo);
      int touch=-1,confirm=-1;
      for(int j=z.avail_index+1;j<=last;j++)
      {
         bool inside=(d>0 ? m15[j].low<=z.hi : m15[j].high>=z.lo);
         if(inside && touch<0) touch=j;
         if(touch<0) continue;
         bool out_again=(d>0 ? m15[j].close>z.hi : m15[j].close<z.lo);
         bool with_side=(d>0 ? m15[j].close>m15[j].open : m15[j].close<m15[j].open);
         if(out_again && with_side) { confirm=j; break; }
      }
      s.entry=proximal;
      if(touch<0)
         SVP_SetStep(s,SVP_STEP_ENTRY,SVP_STEP_PENDING,"awaiting a retest of "+DoubleToString(z.lo,p.digits)+"-"+
                     DoubleToString(z.hi,p.digits));
      else if(confirm<0)
         SVP_SetStep(s,SVP_STEP_ENTRY,SVP_STEP_PENDING,"retest in progress since "+SVP_ClockText(m15[touch].time)+
                     ", awaiting a "+side_word+" close back outside the zone");
      else
      {
         s.entry_index=confirm;
         s.entry=m15[confirm].close;
         double chase=(double)d*(close_now-proximal);
         if(last-confirm>p.entry_valid_bars)
            SVP_SetStep(s,SVP_STEP_ENTRY,SVP_STEP_FAIL,"entry window passed (retest confirmed "+SVP_ClockText(m15[confirm].time)+")");
         else if(chase>p.entry_max_chase_atr*atr)
            SVP_SetStep(s,SVP_STEP_ENTRY,SVP_STEP_FAIL,"price is already "+DoubleToString(chase/atr,2)+" ATR beyond the zone");
         else
            SVP_SetStep(s,SVP_STEP_ENTRY,SVP_STEP_PASS,"retest confirmed "+SVP_ClockText(m15[confirm].time)+", entry "+
                        DoubleToString(s.entry,p.digits));
      }
   }
   //--- 9. stop, target, risk/reward ----------------------------------------------
   if(zone_ok && s.status[SVP_STEP_ENTRY]==SVP_STEP_PASS && s.sweep_index>=0)
   {
      SSvpZone z=g_svp_zones[s.zone_index];
      SSvpSweep sw=g_svp_sweeps[s.sweep_index];
      double far_edge=(d>0?z.lo:z.hi);
      double structural=far_edge;
      if((double)d*(sw.extreme-structural)<0.0) structural=sw.extreme;     // whichever is further from the entry
      // the buffer uses the volatility of the CONFIRMATION bar, so the plan of a
      // setup is the same number on every bar it stays actionable
      double atr_entry=g_svp_atr_m15[s.entry_index];
      double stop=SVP_RoundTick(structural-(double)d*(p.sl_buffer_atr*atr_entry+p.spread),p.tick_size,-d);
      s.stop_source=(structural==far_edge?"beyond the entry zone":"beyond the swept extreme")+" + "+
                    DoubleToString(p.sl_buffer_atr,2)+" ATR";
      if(p.min_stop_distance>0.0 && (double)d*(s.entry-stop)<p.min_stop_distance)
      {
         stop=SVP_RoundTick(s.entry-(double)d*p.min_stop_distance,p.tick_size,-d);
         s.stop_source+=" (widened to the broker minimum stop distance)";
      }
      s.stop=stop;
      s.risk=(double)d*(s.entry-stop);
      if(!(s.risk>0.0) || !MathIsValidNumber(s.risk))
         SVP_SetStep(s,SVP_STEP_RR,SVP_STEP_FAIL,"the stop cannot be placed beyond the structure");
      else
      {
         // candidate targets on the profit side, each a real level; the NEAREST one
         // that pays at least min_rr is taken (the same rule for both directions)
         double pick_level=0.0,best_rr=0.0;
         string pick_source="";
         int nc=0;
         int ln=ArraySize(g_svp_liq);
         for(int i=0;i<ln;i++)
         {
            // a level that was still resting when the retest was confirmed stays the
            // candidate afterwards: if it has traded since, the plan is over (below),
            // it is not silently replaced by a further one
            if(g_svp_liq[i].side!=d) continue;
            if(g_svp_liq[i].taken_index>=0 && g_svp_liq[i].taken_index<=s.entry_index) continue;
            if(SVP_ConsiderTarget(d,s.entry,s.risk,p.min_rr,g_svp_liq[i].level,pick_level,best_rr))
               pick_source=(d>0?"BSL ":"SSL ")+g_svp_liq[i].label;
            if((double)d*(g_svp_liq[i].level-s.entry)>0.0) nc++;
         }
         if(g_svp_h1.valid)
         {
            double lvl=(d>0?g_svp_h1.high_price:g_svp_h1.low_price);
            bool standing=(d>0?g_svp_h1.high_standing:g_svp_h1.low_standing);
            if(standing && lvl>0.0 && (double)d*(lvl-s.entry)>0.0)
            {
               nc++;
               if(SVP_ConsiderTarget(d,s.entry,s.risk,p.min_rr,lvl,pick_level,best_rr))
                  pick_source=(d>0?"H1 swing high":"H1 swing low");
            }
         }
         if(g_svp_profile.valid)
         {
            double edge=(d>0?g_svp_profile.vah:g_svp_profile.val);
            if((double)d*(g_svp_profile.poc-s.entry)>0.0)
            {
               nc++;
               if(SVP_ConsiderTarget(d,s.entry,s.risk,p.min_rr,g_svp_profile.poc,pick_level,best_rr)) pick_source="POC";
            }
            if((double)d*(edge-s.entry)>0.0)
            {
               nc++;
               if(SVP_ConsiderTarget(d,s.entry,s.risk,p.min_rr,edge,pick_level,best_rr)) pick_source=(d>0?"VAH":"VAL");
            }
         }
         // what happened between the confirmation and now: a plan whose stop or
         // target has already traded is finished, whatever the levels say
         bool stop_traded=false,target_traded=false;
         for(int j=s.entry_index+1;j<=last;j++)
         {
            if(d>0 ? m15[j].low<=stop : m15[j].high>=stop) stop_traded=true;
            if(pick_level>0.0 && (d>0 ? m15[j].high>=pick_level : m15[j].low<=pick_level)) target_traded=true;
         }
         if(nc==0)
            SVP_SetStep(s,SVP_STEP_RR,SVP_STEP_FAIL,"no target: no liquidity, structure or volume level beyond the entry");
         else if(!(pick_level>0.0))
            SVP_SetStep(s,SVP_STEP_RR,SVP_STEP_FAIL,"best available R:R is 1:"+DoubleToString(best_rr,2)+", minimum 1:"+
                        DoubleToString(p.min_rr,2));
         else if(stop_traded)
            SVP_SetStep(s,SVP_STEP_RR,SVP_STEP_FAIL,"the stop level "+DoubleToString(stop,p.digits)+
                        " has traded since the retest was confirmed: the setup is over");
         else if(target_traded)
            SVP_SetStep(s,SVP_STEP_RR,SVP_STEP_FAIL,"the target "+DoubleToString(pick_level,p.digits)+
                        " has traded since the retest was confirmed: the setup is over");
         else
         {
            s.target=pick_level;
            s.target_source=pick_source;
            s.reward=(double)d*(s.target-s.entry);
            s.rr=s.reward/s.risk;
            s.plan_valid=true;
            SVP_SetStep(s,SVP_STEP_RR,SVP_STEP_PASS,"1:"+DoubleToString(s.rr,2)+" (risk "+DoubleToString(s.risk,p.digits)+
                        ", reward "+DoubleToString(s.reward,p.digits)+", target "+s.target_source+")");
         }
      }
   }
   //--- progress ---------------------------------------------------------------------
   s.progress=0; s.blocking=-1;
   for(int i=0;i<SVP_MAX_STEPS;i++)
   {
      if(s.status[i]==SVP_STEP_PASS) { if(s.blocking<0) s.progress++; }
      else if(s.blocking<0) s.blocking=i;
   }
}

// Exactly one outcome. A side qualifies only when all ten steps passed and its
// plan is valid; when both qualify at once the evidence conflicts: WAIT.
ENUM_SVP_DECISION SVP_Resolve(const bool buy_ok,const bool sell_ok)
{
   if(buy_ok && !sell_ok) return SVP_DECISION_BUY;
   if(sell_ok && !buy_ok) return SVP_DECISION_SELL;
   return SVP_DECISION_WAIT;
}

string SVP_LiquidityText(const double price,const int digits)
{
   int up=SVP_NearestLiquidity(1,price);
   int dn=SVP_NearestLiquidity(-1,price);
   string a=(up>=0?"BSL "+DoubleToString(g_svp_liq[up].level,digits)+" "+g_svp_liq[up].label:"BSL N/A");
   string b=(dn>=0?"SSL "+DoubleToString(g_svp_liq[dn].level,digits)+" "+g_svp_liq[dn].label:"SSL N/A");
   return a+" | "+b;
}

void SVP_CopySide(const SSvpSide &s,SSvpDecision &d)
{
   for(int i=0;i<SVP_MAX_STEPS;i++) { d.status[i]=s.status[i]; d.text[i]=s.text[i]; }
   d.focus=s.direction;
}

// Run the whole pipeline for the newest closed M15 bar. The higher-timeframe
// series are trimmed to bars that had CLOSED by that moment, so a forming H1 or
// H4 bar handed in by mistake still cannot leak into the decision.
bool SVP_Analyze(const MqlRates &h4[],const int n4_in,const MqlRates &h1[],const int n1_in,
                 const MqlRates &m15[],const int n15_in,const SSvpParams &params)
{
   SSvpParams p=params;
   SVP_SanitizeParams(p);
   SVP_DecisionReset(g_svp);
   SVP_SideReset(g_svp_buy,1);
   SVP_SideReset(g_svp_sell,-1);
   SVP_StructureReset(g_svp_h4); SVP_StructureReset(g_svp_h1);
   SVP_StructureReset(g_svp_h1_int); SVP_StructureReset(g_svp_m15);
   ArrayResize(g_svp_liq,0); ArrayResize(g_svp_sweeps,0); ArrayResize(g_svp_zones,0);
   SVP_VpReset(g_svp_profile);
   g_svp_profile_previous=false;
   g_svp_vpc.valid=false; g_svp_vpc.state=SVP_VPC_NONE; g_svp_vpc.support=0; g_svp_vpc.location=0;
   g_svp_vpc.level=0.0; g_svp_vpc.text="N/A";
   int n15=SVP_UsableBars(m15,n15_in);
   int n1=SVP_UsableBars(h1,n1_in);
   int n4=SVP_UsableBars(h4,n4_in);
   if(n15>0)
   {
      datetime closed_at=m15[n15-1].time+900;
      while(n1>0 && h1[n1-1].time+3600>closed_at) n1--;
      while(n4>0 && h4[n4-1].time+14400>closed_at) n4--;
      g_svp.bar_time=m15[n15-1].time;
   }
   if(n15<SVP_MIN_M15_BARS || n1<SVP_MIN_H1_BARS || n4<SVP_MIN_H4_BARS)
   {
      g_svp.reason="WAIT - history not ready: M15 "+IntegerToString(n15)+"/"+IntegerToString(SVP_MIN_M15_BARS)+
                   ", H1 "+IntegerToString(n1)+"/"+IntegerToString(SVP_MIN_H1_BARS)+
                   ", H4 "+IntegerToString(n4)+"/"+IntegerToString(SVP_MIN_H4_BARS)+" closed bars";
      return false;
   }
   int last=n15-1;
   //--- structure on three timeframes
   SVP_TrackStructure(h4,n4,p.h4_swing,p.h4_swing,g_svp_sw_h4,g_svp_ev_h4,g_svp_h4);
   SVP_TrackStructure(h1,n1,p.h1_swing_ext,p.h1_swing_ext,g_svp_sw_h1,g_svp_ev_h1,g_svp_h1);
   SVP_TrackStructure(h1,n1,p.h1_swing_int,p.h1_swing_int,g_svp_sw_h1_int,g_svp_ev_h1_int,g_svp_h1_int);
   SVP_TrackStructure(m15,n15,p.m15_swing,p.m15_swing,g_svp_sw_m15,g_svp_ev_m15,g_svp_m15);
   if(!SVP_ATR(m15,n15,p.atr_period,g_svp_atr_m15) || !(g_svp_atr_m15[last]>0.0))
   {
      g_svp.reason="WAIT - M15 volatility unavailable";
      return false;
   }
   //--- liquidity, sweeps, zones, volume profile
   SVP_BuildLiquidity(m15,n15,g_svp_atr_m15,g_svp_sw_m15,p,g_svp_liq);
   SVP_BuildSweeps(m15,n15,g_svp_atr_m15,g_svp_ev_m15,g_svp_liq,p,g_svp_sweeps);
   SVP_BuildZones(m15,n15,g_svp_atr_m15,g_svp_ev_m15,p,g_svp_zones);
   SVP_VpReference(m15,n15,g_svp_atr_m15,p,g_svp_profile,g_svp_profile_previous);
   SVP_VpContext(g_svp_profile,m15,n15,g_svp_atr_m15[last],p,g_svp_vpc);
   //--- both directions, the same code
   SVP_EvaluateSide(1,m15,n15,p,g_svp_buy);
   SVP_EvaluateSide(-1,m15,n15,p,g_svp_sell);
   //--- resolve
   g_svp.ready=true;
   bool buy_ok=(g_svp_buy.blocking<0 && g_svp_buy.plan_valid);
   bool sell_ok=(g_svp_sell.blocking<0 && g_svp_sell.plan_valid);
   int focus=0;
   g_svp.state=SVP_Resolve(buy_ok,sell_ok);
   if(g_svp.state==SVP_DECISION_BUY) focus=1;
   else if(g_svp.state==SVP_DECISION_SELL) focus=-1;
   else
   {
      if(g_svp_buy.progress>g_svp_sell.progress) focus=1;
      else if(g_svp_sell.progress>g_svp_buy.progress) focus=-1;
      else if(g_svp_h4.bias!=0) focus=g_svp_h4.bias;
   }
   g_svp.headline=SVP_DecisionText(g_svp.state);
   if(focus>0) SVP_CopySide(g_svp_buy,g_svp);
   else if(focus<0) SVP_CopySide(g_svp_sell,g_svp);
   g_svp.focus=focus;
   if(buy_ok && sell_ok)
      g_svp.reason="WAIT - both sides qualify at once: conflicting evidence";
   else if(g_svp.state!=SVP_DECISION_WAIT)
      g_svp.reason=g_svp.headline+" - all "+IntegerToString(SVP_MAX_STEPS)+" confirmations hold";
   else if(focus==0)
      g_svp.reason="WAIT - H4 is NEUTRAL and neither side has a confirmed sequence";
   else
   {
      int blk=(focus>0?g_svp_buy.blocking:g_svp_sell.blocking);
      if(blk<0) blk=SVP_STEP_RR;
      g_svp.reason="WAIT - "+(focus>0?"BUY":"SELL")+" candidate "+
                   IntegerToString(focus>0?g_svp_buy.progress:g_svp_sell.progress)+"/"+IntegerToString(SVP_MAX_STEPS)+
                   ", "+SVP_StatusText(g_svp.status[blk])+" at "+SVP_StepName(blk)+": "+g_svp.text[blk];
   }
   //--- plan and tracked setup come from the focus side only
   if(focus!=0)
   {
      SSvpSide f;
      if(focus>0) f=g_svp_buy; else f=g_svp_sell;
      g_svp.entry=f.entry; g_svp.stop=f.stop; g_svp.target=f.target;
      g_svp.risk=f.risk; g_svp.reward=f.reward; g_svp.rr=f.rr;
      g_svp.stop_source=f.stop_source; g_svp.target_source=f.target_source;
      g_svp.plan_valid=(f.plan_valid && g_svp.state!=SVP_DECISION_WAIT);
      if(f.zone_index>=0 && f.sweep_index>=0 && f.progress>=SVP_STEP_ZONE+1)
      {
         g_svp.tracked=true;
         g_svp.direction=focus;
         g_svp.setup_type=(g_svp_sweeps[f.sweep_index].state==SVP_SWEEP_CONFIRMED?"SWEEP_MSS_RETEST":"FAILED_BREAKOUT_RETEST");
         g_svp.origin_time=g_svp_sweeps[f.sweep_index].take_time;
         g_svp.anchor_id=g_svp_sweeps[f.sweep_index].id;   // the liquidity event: it can never change
         g_svp.zone_lo=g_svp_zones[f.zone_index].lo;
         g_svp.zone_hi=g_svp_zones[f.zone_index].hi;
      }
      if(f.zone_index>=0) g_svp.zone_text=SVP_ZoneText(g_svp_zones[f.zone_index],p.digits);
   }
   //--- context lines for the dashboard
   g_svp.h4_bias=g_svp_h4.bias;
   g_svp.h4_text=(g_svp_h4.valid?SVP_DirText(g_svp_h4.bias)+" | "+SVP_StructureText(g_svp_h4,p.digits):"N/A");
   g_svp.h1_text=SVP_StructureText(g_svp_h1,p.digits);
   g_svp.liq_text=SVP_LiquidityText(m15[last].close,p.digits);
   int newest=-1;
   for(int i=0;i<ArraySize(g_svp_sweeps) && newest<0;i++)
      if(last-g_svp_sweeps[i].take_index<=p.sw_max_age) newest=i;
   // the event the focus side is built on, else simply the newest one
   if(focus>0 && g_svp_buy.sweep_index>=0) newest=g_svp_buy.sweep_index;
   if(focus<0 && g_svp_sell.sweep_index>=0) newest=g_svp_sell.sweep_index;
   g_svp.sweep_text=(newest>=0?SVP_SweepText(g_svp_sweeps[newest],p.digits):"none in the last "+IntegerToString(p.sw_max_age)+" bars");
   if(g_svp.zone_text=="N/A")
   {
      for(int i=0;i<ArraySize(g_svp_zones);i++)
         if(SVP_ZoneAlive(g_svp_zones[i])) { g_svp.zone_text=SVP_ZoneText(g_svp_zones[i],p.digits); break; }
   }
   g_svp.vp_valid=g_svp_profile.valid;
   if(g_svp_profile.valid)
   {
      g_svp.poc=g_svp_profile.poc; g_svp.vah=g_svp_profile.vah; g_svp.val=g_svp_profile.val;
      g_svp.vp_text=(g_svp_vpc.valid?g_svp_vpc.text:"N/A");
   }
   return true;
}

#endif
//+------------------------------------------------------------------+
