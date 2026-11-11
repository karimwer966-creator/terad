//+------------------------------------------------------------------+
//|                                                QSMC_SvpZones.mqh |
//|  Order blocks and fair value gaps with a lifecycle.               |
//|                                                                   |
//|  FVG   three-candle imbalance of at least fvg_min_atr; "backed"   |
//|        when its middle candle is a displacement candle.           |
//|  OB    the LAST opposite candle before a displacement candle that |
//|        closes beyond it; "backed" when a BOS/CHoCH in the same    |
//|        direction follows within zone_validate_bars.               |
//|  An OB and the FVG of the same leg are merged into ONE zone       |
//|  (OB+FVG) whose identity is the earliest origin, so the zone is   |
//|  updated in place when the gap appears - never drawn twice.       |
//|                                                                   |
//|  LIFECYCLE (closed bars only)                                     |
//|   DETECTED -> VALIDATED -> PARTIAL -> MITIGATED                   |
//|                      \-> INVALIDATED (close through the far edge) |
//|                      \-> EXPIRED (older than zone_max_age)        |
//+------------------------------------------------------------------+
#ifndef QSMC_SVP_ZONES_MQH
#define QSMC_SVP_ZONES_MQH

#include <QSMC/QSMC_SvpCore.mqh>

#define SVP_ZONE_OB   1
#define SVP_ZONE_FVG  2
#define SVP_ZONE_BOTH 3
#define SVP_ZONE_MAX  160

struct SSvpZone
{
   int                 kind;           // SVP_ZONE_OB / _FVG / _BOTH
   int                 direction;      // +1 bullish (demand), -1 bearish (supply)
   double              lo;
   double              hi;
   int                 origin_index;   // OB candle / middle candle of the gap
   datetime            origin_time;
   int                 avail_index;    // first bar on which the zone is known
   datetime            avail_time;
   bool                backed;         // displacement / structure behind it
   ENUM_SVP_ZONE_STATE state;
   int                 state_index;
   int                 touches;        // separate retest episodes
   int                 first_touch;    // bar of the first retest, -1 = fresh
   double              fill;           // deepest penetration, 0..1
   string              id;             // "Z|BUY|<origin time>"
};

string SVP_ZoneStateText(const ENUM_SVP_ZONE_STATE s)
{
   if(s==SVP_ZS_DETECTED)    return "DETECTED";
   if(s==SVP_ZS_VALIDATED)   return "VALIDATED";
   if(s==SVP_ZS_PARTIAL)     return "PARTIALLY MITIGATED";
   if(s==SVP_ZS_MITIGATED)   return "MITIGATED";
   if(s==SVP_ZS_INVALIDATED) return "INVALIDATED";
   if(s==SVP_ZS_EXPIRED)     return "EXPIRED";
   return "NONE";
}

string SVP_ZoneKindText(const int kind)
{
   if(kind==SVP_ZONE_OB) return "OB";
   if(kind==SVP_ZONE_FVG) return "FVG";
   if(kind==SVP_ZONE_BOTH) return "OB+FVG";
   return "ZONE";
}

bool SVP_ZoneAlive(const SSvpZone &z)
{
   return (z.state!=SVP_ZS_NONE && z.state!=SVP_ZS_INVALIDATED && z.state!=SVP_ZS_EXPIRED);
}

string SVP_ZoneText(const SSvpZone &z,const int digits)
{
   return (z.direction>0?"Bullish ":"Bearish ")+SVP_ZoneKindText(z.kind)+" "+
          DoubleToString(z.lo,digits)+"-"+DoubleToString(z.hi,digits)+" "+SVP_ZoneStateText(z.state);
}

bool SVP_AddZone(SSvpZone &zones[],int &count,const MqlRates &r[],const int kind,const int direction,
                 const double lo,const double hi,const int origin,const int avail,const bool backed)
{
   if(count>=SVP_ZONE_MAX || !(hi>lo) || !(lo>0.0)) return false;
   if(ArrayResize(zones,count+1,32)!=count+1) return false;
   zones[count].kind=kind; zones[count].direction=direction;
   zones[count].lo=lo; zones[count].hi=hi;
   zones[count].origin_index=origin; zones[count].origin_time=r[origin].time;
   zones[count].avail_index=avail; zones[count].avail_time=r[avail].time;
   zones[count].backed=backed;
   zones[count].state=SVP_ZS_DETECTED; zones[count].state_index=avail;
   zones[count].touches=0; zones[count].first_touch=-1; zones[count].fill=0.0;
   zones[count].id="Z|"+(direction>0?"BUY":"SELL")+"|"+IntegerToString((long)r[origin].time);
   count++;
   return true;
}

// Fair value gaps formed on bars [from, n-1].
void SVP_DetectFVG(const MqlRates &r[],const int n,const double &atr[],const SSvpParams &p,
                   const int from,SSvpZone &zones[],int &count)
{
   int start=(from<2?2:from);
   for(int i=start;i<n;i++)
   {
      double min_gap=p.fvg_min_atr*atr[i-1];
      if(min_gap<p.tick_size) min_gap=p.tick_size;
      double up=r[i].low-r[i-2].high;
      double dn=r[i-2].low-r[i].high;
      if(up>=min_gap)
         SVP_AddZone(zones,count,r,SVP_ZONE_FVG,1,r[i-2].high,r[i].low,i-1,i,
                     SVP_IsDisplacement(r,atr,i-1,1,p.disp_body_atr,p.disp_body_ratio));
      else if(dn>=min_gap)
         SVP_AddZone(zones,count,r,SVP_ZONE_FVG,-1,r[i].high,r[i-2].low,i-1,i,
                     SVP_IsDisplacement(r,atr,i-1,-1,p.disp_body_atr,p.disp_body_ratio));
   }
}

// Order blocks whose displacement candle lies on bars [from, n-1].
void SVP_DetectOB(const MqlRates &r[],const int n,const double &atr[],const SSvpStructEvent &events[],
                  const SSvpParams &p,const int from,SSvpZone &zones[],int &count)
{
   int start=(from<1?1:from);
   int first_ob=count;
   for(int k=start;k<n;k++)
   {
      int d=0;
      if(SVP_IsDisplacement(r,atr,k,1,p.disp_body_atr,p.disp_body_ratio)) d=1;
      else if(SVP_IsDisplacement(r,atr,k,-1,p.disp_body_atr,p.disp_body_ratio)) d=-1;
      if(d==0) continue;
      int found=-1;
      for(int j=k-1;j>=k-p.ob_lookback && j>=0;j--)
      {
         bool opposite=(d>0 ? r[j].close<r[j].open : r[j].close>r[j].open);
         if(!opposite) continue;
         bool beyond=(d>0 ? r[k].close>r[j].high : r[k].close<r[j].low);
         if(beyond) found=j;
         break;                               // only the LAST opposite candle can be the block
      }
      if(found<0) continue;
      bool dup=false;
      for(int q=first_ob;q<count && !dup;q++)
         if(zones[q].kind==SVP_ZONE_OB && zones[q].direction==d && zones[q].origin_index==found) dup=true;
      if(dup) continue;
      bool backed=(SVP_FindEvent(events,d,k,k+p.zone_validate_bars)>=0);
      SVP_AddZone(zones,count,r,SVP_ZONE_OB,d,r[found].low,r[found].high,found,k,backed);
   }
}

// Walk the closed bars after the zone became known and derive its state.
void SVP_ZoneLifecycle(const MqlRates &r[],const int n,const SSvpParams &p,SSvpZone &z)
{
   z.touches=0; z.first_touch=-1; z.fill=0.0;
   z.state=(z.backed?SVP_ZS_VALIDATED:SVP_ZS_DETECTED);
   z.state_index=z.avail_index;
   double height=z.hi-z.lo;
   if(!(height>0.0)) { z.state=SVP_ZS_INVALIDATED; return; }
   bool was_in=false;
   for(int j=z.avail_index+1;j<n;j++)
   {
      bool closed_through=(z.direction>0 ? r[j].close<z.lo : r[j].close>z.hi);
      bool inside=(z.direction>0 ? r[j].low<=z.hi : r[j].high>=z.lo);
      if(inside)
      {
         if(!was_in) { z.touches++; if(z.first_touch<0) z.first_touch=j; }
         double depth=(z.direction>0 ? z.hi-r[j].low : r[j].high-z.lo)/height;
         if(depth>1.0) depth=1.0;
         if(depth>z.fill) z.fill=depth;
      }
      was_in=inside;
      if(closed_through) { z.state=SVP_ZS_INVALIDATED; z.state_index=j; return; }
   }
   if(n-1-z.avail_index>p.zone_max_age) { z.state=SVP_ZS_EXPIRED; z.state_index=n-1; return; }
   if(z.touches>0)
   {
      z.state=(z.fill>=1.0?SVP_ZS_MITIGATED:SVP_ZS_PARTIAL);
      z.state_index=z.first_touch;
   }
}

// All order blocks and fair value gaps of the recent window, merged per leg,
// with their lifecycle as of bar n-1. Newest first.
int SVP_BuildZones(const MqlRates &r[],const int n,const double &atr[],const SSvpStructEvent &events[],
                   const SSvpParams &p,SSvpZone &zones[])
{
   ArrayResize(zones,0);
   if(n<5 || ArraySize(atr)<n) return 0;
   int from=n-1-p.zone_max_age-p.ob_lookback-2;
   if(from<0) from=0;
   SSvpZone raw[];
   int rc=0;
   SVP_DetectOB(r,n,atr,events,p,from,raw,rc);
   SVP_DetectFVG(r,n,atr,p,from,raw,rc);
   if(rc<=0) return 0;
   // merge the block and the gap(s) of one leg: same direction, origins at most
   // three bars apart, price ranges touching or overlapping inside the tolerance
   bool gone[SVP_ZONE_MAX];
   for(int i=0;i<SVP_ZONE_MAX;i++) gone[i]=false;
   bool changed=true;
   while(changed)
   {
      changed=false;
      for(int a=0;a<rc && !changed;a++)
      {
         if(gone[a]) continue;
         for(int b=a+1;b<rc;b++)
         {
            if(gone[b] || raw[a].direction!=raw[b].direction) continue;
            int gap_bars=raw[a].origin_index-raw[b].origin_index;
            if(gap_bars<0) gap_bars=-gap_bars;
            if(gap_bars>3) continue;
            int early=(raw[a].avail_index<raw[b].avail_index?raw[a].avail_index:raw[b].avail_index);
            double tol=p.zone_merge_atr*atr[early];
            double apart=MathMax(raw[a].lo,raw[b].lo)-MathMin(raw[a].hi,raw[b].hi);
            if(apart>tol) continue;
            bool a_first=(raw[a].origin_index<=raw[b].origin_index);
            if(raw[b].lo<raw[a].lo) raw[a].lo=raw[b].lo;
            if(raw[b].hi>raw[a].hi) raw[a].hi=raw[b].hi;
            if(raw[b].avail_index>raw[a].avail_index)
            { raw[a].avail_index=raw[b].avail_index; raw[a].avail_time=raw[b].avail_time; }
            if(!a_first)
            { raw[a].origin_index=raw[b].origin_index; raw[a].origin_time=raw[b].origin_time; raw[a].id=raw[b].id; }
            raw[a].backed=(raw[a].backed || raw[b].backed);
            raw[a].kind=(raw[a].kind==raw[b].kind?raw[a].kind:SVP_ZONE_BOTH);
            gone[b]=true;
            changed=true;
            break;
         }
      }
   }
   int count=0;
   for(int i=0;i<rc;i++)
   {
      if(gone[i]) continue;
      if(ArrayResize(zones,count+1,16)!=count+1) break;
      zones[count]=raw[i];
      SVP_ZoneLifecycle(r,n,p,zones[count]);
      count++;
   }
   for(int i=1;i<count;i++)
   {
      SSvpZone key=zones[i]; int j=i-1;
      while(j>=0 && (zones[j].avail_index<key.avail_index ||
            (zones[j].avail_index==key.avail_index && zones[j].direction<key.direction)))
      { zones[j+1]=zones[j]; j--; }
      zones[j+1]=key;
   }
   return count;
}

#endif
//+------------------------------------------------------------------+
