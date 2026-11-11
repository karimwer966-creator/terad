//+------------------------------------------------------------------+
//|                                            QSMC_SvpLiquidity.mqh |
//|  M15 liquidity map and the Liquidity Sweep Detection Engine.      |
//|                                                                   |
//|  LIQUIDITY MAP                                                    |
//|   * swing highs / lows  -> BSL above, SSL below                   |
//|   * EQH / EQL           -> two or more pivots inside a tolerance  |
//|   * PDH / PDL, PWH / PWL -> previous COMPLETE day / week          |
//|   Tolerances are max(ATR multiple, ticks), so they follow both    |
//|   volatility and symbol precision. Levels that sit inside the     |
//|   merge tolerance AND share the same fate (both intact, or taken  |
//|   by the same bar) are ONE zone - one object, not five lines.     |
//|                                                                   |
//|  SWEEP ENGINE - a penetration is not a sweep until proven         |
//|   SWEEP_DETECTED      wick through the level, close back inside,  |
//|                       bounded depth, real rejection               |
//|   SWEEP_CONFIRMED     + displacement away + structure shift       |
//|   UNCONFIRMED         a poke / a close beyond that is unresolved  |
//|   BREAKOUT_CONFIRMED  N consecutive closes beyond the level       |
//|   FALSE_BREAKOUT      closed beyond, then closed back inside      |
//|   Every threshold that decides a PAST event uses the ATR that     |
//|   existed at that event, so a classification never changes with   |
//|   later volatility (no repaint).                                  |
//+------------------------------------------------------------------+
#ifndef QSMC_SVP_LIQUIDITY_MQH
#define QSMC_SVP_LIQUIDITY_MQH

#include <QSMC/QSMC_SvpCore.mqh>

#define SVP_LIQ_SWING 1
#define SVP_LIQ_EQ    2
#define SVP_LIQ_PD    4
#define SVP_LIQ_PW    8
#define SVP_LIQ_MAX_SWINGS 120
#define SVP_LIQ_MAX_POOLS  160
#define SVP_LIQ_MAX_ZONES  160

struct SSvpLiqPool
{
   int      side;           // +1 buy-side (above highs), -1 sell-side (below lows)
   double   price;          // the extreme to exceed
   double   lo;             // extent of the pool (a cluster of equal pivots has one)
   double   hi;
   int      kinds;          // SVP_LIQ_* mask
   int      strength;
   int      formed_index;   // first bar on which the level is known
   datetime ref_time;       // time of the pivot / start of the reference period
   int      taken_index;    // first bar that traded through it, -1 = intact
};

struct SSvpLiqZone
{
   int      side;
   double   lo;
   double   hi;
   double   level;          // the extreme to exceed: hi for BSL, lo for SSL
   int      kinds;
   int      strength;
   int      members;
   string   label;          // e.g. "EQH+PDH"
   int      formed_index;
   datetime formed_time;
   int      taken_index;
   datetime taken_time;
   string   id;             // stable identity: side | earliest member | level
};

struct SSvpSweep
{
   bool                 valid;
   int                  side;            // side of the liquidity that was taken
   int                  direction;       // trade direction a reversal would imply (-side)
   ENUM_SVP_SWEEP_STATE state;
   int                  take_index;
   datetime             take_time;
   double               level;
   double               extreme;         // furthest price beyond the level during the event
   double               penetration;
   double               reject_ratio;    // rejection of the taking bar, 0..1
   bool                 closed_back;     // the taking bar closed back inside
   bool                 displacement;
   int                  disp_index;
   bool                 structure;
   int                  struct_index;
   double               struct_level;
   int                  state_index;     // bar on which the current state was reached
   datetime             state_time;
   int                  strength;
   string               zone_label;
   string               zone_id;
   string               id;              // "SW|BSL|<take time>": never changes once it exists
   string               note;
};

double SVP_Tolerance(const double atr,const double atr_mult,const int ticks,const double tick)
{
   double a=(atr>0.0?atr*atr_mult:0.0);
   double b=(double)ticks*tick;
   return (a>b?a:b);
}

string SVP_SweepStateText(const ENUM_SVP_SWEEP_STATE s)
{
   if(s==SVP_SWEEP_DETECTED)           return "SWEEP_DETECTED";
   if(s==SVP_SWEEP_CONFIRMED)          return "SWEEP_CONFIRMED";
   if(s==SVP_SWEEP_BREAKOUT_CONFIRMED) return "BREAKOUT_CONFIRMED";
   if(s==SVP_SWEEP_FALSE_BREAKOUT)     return "FALSE_BREAKOUT";
   if(s==SVP_SWEEP_UNCONFIRMED)        return "UNCONFIRMED";
   return "NONE";
}

string SVP_LiqKindsText(const int kinds,const int side)
{
   string s="";
   if((kinds&SVP_LIQ_PW)!=0) s+=(side>0?"PWH":"PWL");
   if((kinds&SVP_LIQ_PD)!=0) s+=(s==""?"":"+")+(side>0?"PDH":"PDL");
   if((kinds&SVP_LIQ_EQ)!=0) s+=(s==""?"":"+")+(side>0?"EQH":"EQL");
   if(s=="") s=(side>0?"swing high":"swing low");
   return s;
}

// First bar >= from that trades THROUGH the level by at least the minimum
// penetration. The threshold of bar j uses atr[j-1]: only what was known then.
int SVP_TakenIndex(const MqlRates &r[],const int n,const double &atr[],const int from,
                   const int side,const double price,const SSvpParams &p)
{
   int start=(from<1?1:from);
   for(int j=start;j<n;j++)
   {
      double pen_min=SVP_Tolerance(atr[j-1],p.sw_pen_min_atr,p.sw_pen_min_ticks,p.tick_size);
      if(side>0 && r[j].high>price+pen_min) return j;
      if(side<0 && r[j].low<price-pen_min) return j;
   }
   return -1;
}

int SVP_DayId(const datetime t)  { return (int)(t/86400); }
int SVP_WeekId(const datetime t) { return (int)((t/86400+3)/7); }   // weeks start on Monday

// Period ids (day or week) present in the series, newest first, at most `want`.
int SVP_RecentPeriods(const MqlRates &r[],const int n,const bool weekly,int &ids[],int &first_bar[],const int want)
{
   ArrayResize(ids,0); ArrayResize(first_bar,0);
   int count=0;
   int prev=-1;
   for(int i=n-1;i>=0 && count<=want;i--)
   {
      int id=(weekly?SVP_WeekId(r[i].time):SVP_DayId(r[i].time));
      if(id!=prev)
      {
         if(count==want) break;
         ArrayResize(ids,count+1); ArrayResize(first_bar,count+1);
         ids[count]=id; first_bar[count]=i;
         count++;
         prev=id;
      }
      else first_bar[count-1]=i;
   }
   return count;
}

bool SVP_AddPool(SSvpLiqPool &pools[],int &count,const int side,const double price,const double other,
                 const int kinds,const int strength,const int formed_index,const datetime ref_time,
                 const int taken_index)
{
   if(count>=SVP_LIQ_MAX_POOLS || !(price>0.0) || !(other>0.0)) return false;
   if(ArrayResize(pools,count+1,32)!=count+1) return false;
   pools[count].side=side; pools[count].price=price; pools[count].kinds=kinds;
   pools[count].lo=(price<other?price:other); pools[count].hi=(price>other?price:other);
   pools[count].strength=strength; pools[count].formed_index=formed_index;
   pools[count].ref_time=ref_time; pools[count].taken_index=taken_index;
   count++;
   return true;
}

// Previous COMPLETE day / week highs and lows. A reference period counts only
// when the series also holds a bar from the period before it, i.e. when the
// reference period is certainly complete; otherwise the level is simply absent.
void SVP_AddPeriodPools(const MqlRates &r[],const int n,const double &atr[],const SSvpParams &p,
                        const bool weekly,SSvpLiqPool &pools[],int &count)
{
   int ids[],first[];
   int have=SVP_RecentPeriods(r,n,weekly,ids,first,4);
   // k = 0: levels of the previous period, valid during the current one
   // k = 1: the same one period earlier, so an event that straddles the roll
   //        keeps the level it was measured against
   for(int k=0;k<2;k++)
   {
      if(have<k+3) break;                 // need current(k), reference(k+1), and one older bar (k+2)
      int from=first[k+1];
      int to=first[k]-1;
      if(to<from) continue;
      double hi=r[from].high,lo=r[from].low;
      for(int i=from+1;i<=to;i++)
      {
         if(r[i].high>hi) hi=r[i].high;
         if(r[i].low<lo) lo=r[i].low;
      }
      int formed=first[k];
      int kind=(weekly?SVP_LIQ_PW:SVP_LIQ_PD);
      int strength=(weekly?4:3);
      SVP_AddPool(pools,count,1,hi,hi,kind,strength,formed,r[from].time,
                  SVP_TakenIndex(r,n,atr,formed,1,hi,p));
      SVP_AddPool(pools,count,-1,lo,lo,kind,strength,formed,r[from].time,
                  SVP_TakenIndex(r,n,atr,formed,-1,lo,p));
   }
}

// The liquidity map as of the newest closed bar. `swings` are the M15 pivots.
int SVP_BuildLiquidity(const MqlRates &r[],const int n,const double &atr[],const SSvpSwing &swings[],
                       const SSvpParams &p,SSvpLiqZone &zones[])
{
   ArrayResize(zones,0);
   if(n<10 || ArraySize(atr)<n) return 0;
   int last=n-1;
   int oldest=last-p.liq_lookback;
   if(oldest<0) oldest=0;
   SSvpLiqPool pools[];
   int pc=0;
   //--- 1. previous day / week first: they are never the ones a full list drops
   SVP_AddPeriodPools(r,n,atr,p,false,pools,pc);
   SVP_AddPeriodPools(r,n,atr,p,true,pools,pc);
   //--- 2. pivots inside the look-back (the newest SVP_LIQ_MAX_SWINGS), with their own fate
   int sc=ArraySize(swings);
   int sidx[];
   int taken[];
   int cluster[];
   int m=0;
   int in_window=0;
   for(int i=0;i<sc;i++)
      if(swings[i].index>=oldest && swings[i].confirm<=last) in_window++;
   int skip=in_window-SVP_LIQ_MAX_SWINGS;
   for(int i=0;i<sc;i++)
   {
      if(swings[i].index<oldest || swings[i].confirm>last) continue;
      if(skip>0) { skip--; continue; }
      ArrayResize(sidx,m+1,64); ArrayResize(taken,m+1,64); ArrayResize(cluster,m+1,64);
      sidx[m]=i;
      taken[m]=SVP_TakenIndex(r,n,atr,swings[i].confirm+1,(swings[i].is_high?1:-1),swings[i].price,p);
      cluster[m]=m;
      m++;
   }
   //--- 3. equal highs / lows: same type, inside the tolerance that existed when
   //---    the later pivot confirmed, and nothing between them traded beyond BOTH
   //---    by more than that tolerance (then the earlier one was already swept)
   for(int j=1;j<m;j++)
   {
      SSvpSwing b=swings[sidx[j]];
      double tol=SVP_Tolerance(atr[b.confirm],p.liq_eq_tol_atr,p.liq_tol_ticks,p.tick_size);
      for(int i=0;i<j;i++)
      {
         SSvpSwing a=swings[sidx[i]];
         if(a.is_high!=b.is_high || MathAbs(a.price-b.price)>tol) continue;
         bool swept=false;
         for(int q=a.index+1;q<b.index && !swept;q++)
         {
            if(a.is_high) swept=(r[q].high>MathMax(a.price,b.price)+tol);
            else          swept=(r[q].low<MathMin(a.price,b.price)-tol);
         }
         if(swept) continue;
         int ga=cluster[i],gb=cluster[j];
         if(ga==gb) continue;
         int keep=(ga<gb?ga:gb),drop=(ga<gb?gb:ga);
         for(int k=0;k<m;k++) if(cluster[k]==drop) cluster[k]=keep;
      }
   }
   for(int g=0;g<m;g++)
   {
      if(cluster[g]!=g) continue;                    // g is the representative (earliest member)
      SSvpSwing first=swings[sidx[g]];
      int members=0,formed=first.confirm;
      double extreme=first.price,inner=first.price;
      for(int k=g;k<m;k++)
      {
         if(cluster[k]!=g) continue;
         SSvpSwing s=swings[sidx[k]];
         members++;
         if(members==2) formed=s.confirm;          // an equal level exists from its second pivot
         if(first.is_high ? s.price>extreme : s.price<extreme) extreme=s.price;
         if(first.is_high ? s.price<inner : s.price>inner) inner=s.price;
      }
      int side=(first.is_high?1:-1);
      if(members>=2)
         SVP_AddPool(pools,pc,side,extreme,inner,SVP_LIQ_EQ,members+1,formed,first.time,
                     SVP_TakenIndex(r,n,atr,formed+1,side,extreme,p));
      else
         SVP_AddPool(pools,pc,side,first.price,first.price,SVP_LIQ_SWING,1,first.confirm,first.time,taken[g]);
   }
   if(pc<=0) return 0;
   //--- 4. merge by price within one side, only between levels that share a fate
   int order[];
   ArrayResize(order,pc);
   for(int i=0;i<pc;i++) order[i]=i;
   for(int i=1;i<pc;i++)
   {
      int key=order[i]; int j=i-1;
      while(j>=0 && (pools[order[j]].side>pools[key].side ||
            (pools[order[j]].side==pools[key].side && pools[order[j]].price>pools[key].price)))
      { order[j+1]=order[j]; j--; }
      order[j+1]=key;
   }
   bool used[SVP_LIQ_MAX_POOLS];
   for(int i=0;i<SVP_LIQ_MAX_POOLS;i++) used[i]=false;
   int zc=0;
   int horizon=last-p.sw_max_age-p.sw_confirm_bars;
   for(int a=0;a<pc;a++)
   {
      int ia=order[a];
      if(used[ia]) continue;
      used[ia]=true;
      SSvpLiqPool base=pools[ia];
      // an old, long-taken level is history: it neither rests nor drives an event
      if(base.taken_index>=0 && base.taken_index<horizon) continue;
      double tol_atr=(base.taken_index>=1?atr[base.taken_index-1]:atr[last]);
      double tol=SVP_Tolerance(tol_atr,p.liq_merge_atr,p.liq_tol_ticks,p.tick_size);
      double lo=base.lo,hi=base.hi;
      int kinds=base.kinds,strength=base.strength,members=1;
      int formed=base.formed_index;
      datetime ref=base.ref_time;
      // single linkage among the levels of this side that share the same fate:
      // repeat until nothing more joins, so the result does not depend on order
      bool grew=true;
      while(grew)
      {
         grew=false;
         for(int b=0;b<pc;b++)
         {
            int ib=order[b];
            if(used[ib] || pools[ib].side!=base.side || pools[ib].taken_index!=base.taken_index) continue;
            double apart=MathMax(pools[ib].lo,lo)-MathMin(pools[ib].hi,hi);
            if(apart>tol) continue;
            used[ib]=true;
            if(pools[ib].hi>hi) hi=pools[ib].hi;
            if(pools[ib].lo<lo) lo=pools[ib].lo;
            kinds|=pools[ib].kinds; strength+=pools[ib].strength; members++;
            if(pools[ib].formed_index>formed) formed=pools[ib].formed_index;
            if(pools[ib].ref_time<ref) ref=pools[ib].ref_time;
            grew=true;
         }
      }
      if(zc>=SVP_LIQ_MAX_ZONES) break;
      if(ArrayResize(zones,zc+1,16)!=zc+1) break;
      zones[zc].side=base.side; zones[zc].lo=lo; zones[zc].hi=hi;
      zones[zc].level=(base.side>0?hi:lo);
      zones[zc].kinds=kinds; zones[zc].strength=strength; zones[zc].members=members;
      zones[zc].label=SVP_LiqKindsText(kinds,base.side);
      zones[zc].formed_index=formed;
      zones[zc].formed_time=(formed>=0 && formed<n?r[formed].time:0);
      zones[zc].taken_index=base.taken_index;
      zones[zc].taken_time=(base.taken_index>=0?r[base.taken_index].time:0);
      zones[zc].id=(base.side>0?"BSL|":"SSL|")+IntegerToString((long)ref)+"|"+
                   DoubleToString(zones[zc].level,p.digits);
      zc++;
   }
   return zc;
}

void SVP_SweepReset(SSvpSweep &sw)
{
   sw.valid=false; sw.side=0; sw.direction=0; sw.state=SVP_SWEEP_NONE;
   sw.take_index=-1; sw.take_time=0; sw.level=0.0; sw.extreme=0.0; sw.penetration=0.0;
   sw.reject_ratio=0.0; sw.closed_back=false;
   sw.displacement=false; sw.disp_index=-1; sw.structure=false; sw.struct_index=-1; sw.struct_level=0.0;
   sw.state_index=-1; sw.state_time=0; sw.strength=0;
   sw.zone_label=""; sw.zone_id=""; sw.id=""; sw.note="";
}

// Classify what happened after a liquidity zone was traded through. `events`
// is the M15 structure-event list (SVP_TrackStructure). Reads bars <= n-1 only.
bool SVP_ClassifySweep(const MqlRates &r[],const int n,const double &atr[],const SSvpStructEvent &events[],
                       const SSvpLiqZone &z,const SSvpParams &p,SSvpSweep &sw)
{
   SVP_SweepReset(sw);
   int t=z.taken_index;
   if(t<1 || t>=n || z.side==0) return false;
   int s=z.side;
   int d=-s;
   double a=(atr[t-1]>0.0?atr[t-1]:atr[t]);
   if(!(a>0.0)) return false;
   double buf=p.sw_accept_atr*a;
   double ext=(s>0?r[t].high:r[t].low);
   double range=r[t].high-r[t].low;
   double close_rel=(double)s*(r[t].close-z.level);           // > 0: closed beyond the level
   sw.valid=true; sw.side=s; sw.direction=d;
   sw.take_index=t; sw.take_time=r[t].time; sw.level=z.level;
   sw.penetration=(double)s*(ext-z.level);
   sw.reject_ratio=(range>0.0?(double)s*(ext-r[t].close)/range:0.0);
   sw.closed_back=(close_rel<0.0);
   sw.strength=z.strength; sw.zone_label=z.label; sw.zone_id=z.id;
   sw.id="SW|"+(s>0?"BSL":"SSL")+"|"+IntegerToString((long)r[t].time);
   ENUM_SVP_SWEEP_STATE state=SVP_SWEEP_UNCONFIRMED;
   int state_index=t;
   string note="penetration without a qualifying rejection";
   if(sw.closed_back && sw.penetration<=p.sw_pen_max_atr*a && sw.reject_ratio>=p.sw_reject_min)
   { state=SVP_SWEEP_DETECTED; note="wick through the level, closed back inside; awaiting displacement + structure shift"; }
   else if(!sw.closed_back) note="closed beyond the level; breakout not yet accepted";
   else if(sw.penetration>p.sw_pen_max_atr*a) note="penetration too deep for a sweep";
   int beyond_run=0;
   bool was_beyond=false;
   if(close_rel>buf) { beyond_run=1; was_beyond=true; }
   bool disp=false,strc=false;
   int disp_i=-1,str_i=-1;
   double str_level=0.0;
   if(sw.closed_back && SVP_IsDisplacement(r,atr,t,d,p.disp_body_atr,p.disp_body_ratio)) { disp=true; disp_i=t; }
   int ev=SVP_FindEvent(events,d,t,t);
   if(ev>=0) { strc=true; str_i=events[ev].break_index; str_level=events[ev].level; }
   bool done=false;
   if(state==SVP_SWEEP_DETECTED && disp && strc)
   { state=SVP_SWEEP_CONFIRMED; note="swept, displaced and broke structure on the same bar"; done=true; }
   if(!done && beyond_run>=p.sw_accept_bars)
   { state=SVP_SWEEP_BREAKOUT_CONFIRMED; note="closes held beyond the level"; done=true; }
   int stop=t+p.sw_confirm_bars;
   if(stop>n-1) stop=n-1;
   for(int j=t+1;j<=stop && !done;j++)
   {
      double ej=(s>0?r[j].high:r[j].low);
      if((double)s*(ej-ext)>0.0) ext=ej;
      double cr=(double)s*(r[j].close-z.level);
      if(cr>buf)
      {
         beyond_run++; was_beyond=true;
         if(state==SVP_SWEEP_DETECTED || state==SVP_SWEEP_FALSE_BREAKOUT)
         { state=SVP_SWEEP_UNCONFIRMED; state_index=j; note="closed beyond the level again; rejection failed"; }
         if(beyond_run>=p.sw_accept_bars)
         {
            state=SVP_SWEEP_BREAKOUT_CONFIRMED; state_index=j; done=true;
            note=IntegerToString(p.sw_accept_bars)+" consecutive closes beyond the level: genuine breakout";
         }
         continue;
      }
      beyond_run=0;
      if(cr<0.0 && was_beyond && state==SVP_SWEEP_UNCONFIRMED)
      { state=SVP_SWEEP_FALSE_BREAKOUT; state_index=j; note="closed beyond, then closed back inside: failed breakout"; }
      if(!disp && SVP_IsDisplacement(r,atr,j,d,p.disp_body_atr,p.disp_body_ratio)) { disp=true; disp_i=j; }
      if(!strc)
      {
         ev=SVP_FindEvent(events,d,t,j);
         if(ev>=0) { strc=true; str_i=events[ev].break_index; str_level=events[ev].level; }
      }
      if(state==SVP_SWEEP_DETECTED && disp && strc)
      { state=SVP_SWEEP_CONFIRMED; state_index=j; done=true; note="rejection + displacement + structure shift"; }
   }
   if(!done && state==SVP_SWEEP_DETECTED && n-1>=t+p.sw_confirm_bars)
   {
      state=SVP_SWEEP_UNCONFIRMED; state_index=t+p.sw_confirm_bars;
      note="no displacement + structure shift within "+IntegerToString(p.sw_confirm_bars)+" bars";
   }
   sw.state=state; sw.state_index=state_index; sw.state_time=r[state_index].time;
   sw.extreme=ext;
   sw.displacement=disp; sw.disp_index=disp_i;
   sw.structure=strc; sw.struct_index=str_i; sw.struct_level=str_level;
   sw.note=note;
   return true;
}

// A reversal trigger: a confirmed sweep, or a failed breakout that ALSO
// produced displacement and a structure shift back inside.
bool SVP_SweepActionable(const SSvpSweep &sw)
{
   if(!sw.valid) return false;
   if(sw.state==SVP_SWEEP_CONFIRMED) return true;
   return (sw.state==SVP_SWEEP_FALSE_BREAKOUT && sw.displacement && sw.structure);
}

// Bar on which a reversal trigger became complete (-1 when it is not).
int SVP_SweepReadyIndex(const SSvpSweep &sw)
{
   if(!SVP_SweepActionable(sw)) return -1;
   int i=sw.state_index;
   if(sw.disp_index>i) i=sw.disp_index;
   if(sw.struct_index>i) i=sw.struct_index;
   return i;
}

// Order of the event list. It uses only facts of the price action, so the
// event a decision is built on cannot flip with the size of the look-back:
// newest take first; on one bar and side a confirmed sweep, then a completed
// failed breakout, then a pending one; then the level that was reached last.
int SVP_SweepRank(const SSvpSweep &sw)
{
   if(sw.state==SVP_SWEEP_CONFIRMED) return 0;
   if(SVP_SweepActionable(sw)) return 1;
   if(sw.state==SVP_SWEEP_DETECTED) return 2;
   if(sw.state==SVP_SWEEP_FALSE_BREAKOUT) return 3;
   return 4;
}

bool SVP_SweepBefore(const SSvpSweep &a,const SSvpSweep &b)
{
   if(a.take_index!=b.take_index) return (a.take_index>b.take_index);
   if(a.side!=b.side) return (a.side>b.side);
   int ra=SVP_SweepRank(a),rb=SVP_SweepRank(b);
   if(ra!=rb) return (ra<rb);
   return ((double)a.side*(a.level-b.level)>0.0);
}

// One event per taken zone.
int SVP_BuildSweeps(const MqlRates &r[],const int n,const double &atr[],const SSvpStructEvent &events[],
                    const SSvpLiqZone &zones[],const SSvpParams &p,SSvpSweep &sweeps[])
{
   ArrayResize(sweeps,0);
   int zc=ArraySize(zones);
   int count=0;
   for(int i=0;i<zc;i++)
   {
      if(zones[i].taken_index<0) continue;
      SSvpSweep sw;
      if(!SVP_ClassifySweep(r,n,atr,events,zones[i],p,sw)) continue;
      if(ArrayResize(sweeps,count+1,16)!=count+1) break;
      sweeps[count]=sw;
      count++;
   }
   for(int i=1;i<count;i++)
   {
      SSvpSweep key=sweeps[i]; int j=i-1;
      while(j>=0 && SVP_SweepBefore(key,sweeps[j]))
      { sweeps[j+1]=sweeps[j]; j--; }
      sweeps[j+1]=key;
   }
   return count;
}

string SVP_SweepText(const SSvpSweep &sw,const int digits)
{
   if(!sw.valid) return "N/A";
   return (sw.side>0?"BSL ":"SSL ")+sw.zone_label+" "+SVP_PriceText(sw.level,digits)+" taken "+
          SVP_ClockText(sw.take_time)+" -> "+SVP_SweepStateText(sw.state);
}

#endif
//+------------------------------------------------------------------+
