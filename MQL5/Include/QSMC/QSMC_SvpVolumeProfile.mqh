//+------------------------------------------------------------------+
//|                                        QSMC_SvpVolumeProfile.mqh |
//|  Volume Profile engine: POC, VAH, VAL, HVN, LVN, histogram.       |
//|                                                                   |
//|  WHAT THE NUMBERS ARE                                             |
//|  A volume-at-price estimate rebuilt from CLOSED OHLC bars: each   |
//|  bar's volume is spread uniformly over the price bins its range   |
//|  touches. It is an approximation of where trading happened, not   |
//|  a record of trades at each price.                                |
//|                                                                   |
//|  WHAT THE VOLUME IS                                               |
//|  XAUUSD and every other OTC FX/CFD symbol has NO centralized      |
//|  volume. The default source is the broker's TICK volume - a count |
//|  of price changes at one broker. It is not exchange volume and it |
//|  is not bid/ask order flow. Real volume is used only when asked   |
//|  for AND present on every bar of the profile; the profile always  |
//|  states which one it used (SSvpProfile.basis).                    |
//|                                                                   |
//|  DESIGN                                                           |
//|  * bins are a multiple of the tick size and sit on a fixed grid;  |
//|    the row height of a profile is set from the ATR that existed   |
//|    when its window OPENED, so a finished profile never changes    |
//|    and a developing one does not wobble with volatility;          |
//|  * POC = heaviest bin (lowest on a tie); the value area grows     |
//|    from the POC towards the heavier neighbour (down on a tie)     |
//|    until it holds the requested share - the same rules as         |
//|    CVolumeProfile in QSMC_Stats.mqh, asserted by a parity test;   |
//|  * HVN / LVN are local extremes of the 3-bin smoothed histogram;  |
//|  * session / daily / weekly / explicit-range windows, a small     |
//|    cache keyed by window + newest bar, and SVP_VpValidate().      |
//|                                                                   |
//|  The profile is CONTEXT. It never produces BUY or SELL by itself. |
//+------------------------------------------------------------------+
#ifndef QSMC_SVP_VOLUME_PROFILE_MQH
#define QSMC_SVP_VOLUME_PROFILE_MQH

#include <QSMC/QSMC_SvpCore.mqh>

#define SVP_VP_CACHE 6

struct SSvpProfile
{
   bool             valid;
   ENUM_SVP_VP_KIND kind;
   datetime         from_time;        // requested window [from, to)
   datetime         to_time;
   datetime         first_bar;        // bars actually used
   datetime         last_bar;
   int              bars;
   double           bin_size;
   double           origin;           // lower edge of bin 0
   int              bin_count;
   double           total_volume;
   bool             real_volume;      // true only when every bar carried real volume
   double           poc;
   double           vah;
   double           val;
   double           poc_volume;
   double           va_fraction;      // share of volume actually inside VAL..VAH
   int              poc_bin;          // middle row of the point of control (the lower one of an even run)
   int              poc_lo_bin;       // the point of control is the run of equally heavy rows lo..hi
   int              poc_hi_bin;
   int              vah_bin;
   int              val_bin;
   int              hvn_count;
   double           hvn[SVP_MAX_NODES];
   double           hvn_volume[SVP_MAX_NODES];
   int              lvn_count;
   double           lvn[SVP_MAX_NODES];
   double           lvn_volume[SVP_MAX_NODES];
   double           bins[SVP_VP_MAX_BINS];
   string           basis;
   string           reason;
};

struct SSvpVpContext
{
   bool                valid;
   ENUM_SVP_VP_CONTEXT state;
   int                 support;       // +1 supports longs, -1 supports shorts, 0 neither
   int                 location;      // +1 above value, 0 inside, -1 below
   double              level;         // the level the state refers to
   string              text;
};

SSvpProfile g_svp_vp_cache[SVP_VP_CACHE];
string      g_svp_vp_cache_key[SVP_VP_CACHE];
int         g_svp_vp_cache_next=0;
int         g_svp_vp_builds=0;        // profiles actually computed
int         g_svp_vp_hits=0;          // requests answered from the cache

void SVP_VpReset(SSvpProfile &p)
{
   p.valid=false; p.kind=SVP_VP_RANGE; p.from_time=0; p.to_time=0; p.first_bar=0; p.last_bar=0;
   p.bars=0; p.bin_size=0.0; p.origin=0.0; p.bin_count=0; p.total_volume=0.0; p.real_volume=false;
   p.poc=0.0; p.vah=0.0; p.val=0.0; p.poc_volume=0.0; p.va_fraction=0.0;
   p.poc_bin=-1; p.poc_lo_bin=-1; p.poc_hi_bin=-1; p.vah_bin=-1; p.val_bin=-1; p.hvn_count=0; p.lvn_count=0;
   for(int i=0;i<SVP_MAX_NODES;i++) { p.hvn[i]=0.0; p.hvn_volume[i]=0.0; p.lvn[i]=0.0; p.lvn_volume[i]=0.0; }
   for(int i=0;i<SVP_VP_MAX_BINS;i++) p.bins[i]=0.0;
   p.basis="N/A"; p.reason="not built";
}

void SVP_VpCacheReset()
{
   for(int i=0;i<SVP_VP_CACHE;i++) { SVP_VpReset(g_svp_vp_cache[i]); g_svp_vp_cache_key[i]=""; }
   g_svp_vp_cache_next=0; g_svp_vp_builds=0; g_svp_vp_hits=0;
}

string SVP_VpKindText(const ENUM_SVP_VP_KIND kind)
{
   if(kind==SVP_VP_SESSION) return "SESSION";
   if(kind==SVP_VP_DAILY)   return "DAILY";
   if(kind==SVP_VP_WEEKLY)  return "WEEKLY";
   return "VISIBLE RANGE";
}

string SVP_VpContextText(const ENUM_SVP_VP_CONTEXT s)
{
   if(s==SVP_VPC_POC_ACCEPTANCE) return "POC acceptance";
   if(s==SVP_VPC_POC_REJECTION)  return "POC rejection";
   if(s==SVP_VPC_VAH_REJECTION)  return "VAH rejection";
   if(s==SVP_VPC_VAL_REJECTION)  return "VAL rejection";
   if(s==SVP_VPC_VAH_ACCEPTANCE) return "acceptance above VAH";
   if(s==SVP_VPC_VAL_ACCEPTANCE) return "acceptance below VAL";
   if(s==SVP_VPC_HVN_ACCEPTANCE) return "HVN acceptance";
   if(s==SVP_VPC_LVN_REJECTION)  return "LVN rejection";
   if(s==SVP_VPC_LVN_TRAVERSAL)  return "LVN traversal";
   return "no volume-profile reaction";
}

// Row height: a whole number of ticks, never less than one tick.
double SVP_VpBinSize(const double tick,const double atr,const double row_atr,const int row_ticks)
{
   double t=(tick>0.0?tick:0.01);
   double want=(row_ticks>0?(double)row_ticks*t:row_atr*atr);
   if(!(want>=t) || !MathIsValidNumber(want)) want=t;
   double steps=MathRound(want/t);
   if(steps<1.0) steps=1.0;
   return steps*t;
}

double SVP_VpBinCenter(const SSvpProfile &p,const int b)
{
   return p.origin+((double)b+0.5)*p.bin_size;
}

int SVP_VpBinOf(const SSvpProfile &p,const double price)
{
   if(!p.valid || !(p.bin_size>0.0)) return -1;
   int b=(int)MathFloor((price-p.origin)/p.bin_size);
   if(b<0 || b>=p.bin_count) return -1;
   return b;
}

// Order of two nodes in their list: heaviest first for HVN, thinnest first for
// LVN. Equal volumes are ordered by distance from the POC, so the order does
// not depend on which end of the histogram was scanned first.
bool SVP_VpNodeBefore(const double va,const double pa,const double vb,const double pb,
                      const bool heaviest_first,const double poc)
{
   if(va>vb) return heaviest_first;
   if(va<vb) return !heaviest_first;
   return (MathAbs(pa-poc)<MathAbs(pb-poc));
}

// Keep a node in the bounded, ordered HVN (hvn=true) or LVN list.
void SVP_VpKeepNode(SSvpProfile &p,const bool hvn,const double price,const double volume)
{
   if(hvn)
   {
      int pos=p.hvn_count;
      if(pos>=SVP_MAX_NODES)
      {
         if(!SVP_VpNodeBefore(volume,price,p.hvn_volume[SVP_MAX_NODES-1],p.hvn[SVP_MAX_NODES-1],true,p.poc)) return;
         pos=SVP_MAX_NODES-1;
      }
      else p.hvn_count++;
      while(pos>0 && SVP_VpNodeBefore(volume,price,p.hvn_volume[pos-1],p.hvn[pos-1],true,p.poc))
      { p.hvn[pos]=p.hvn[pos-1]; p.hvn_volume[pos]=p.hvn_volume[pos-1]; pos--; }
      p.hvn[pos]=price; p.hvn_volume[pos]=volume;
      return;
   }
   int pos=p.lvn_count;
   if(pos>=SVP_MAX_NODES)
   {
      if(!SVP_VpNodeBefore(volume,price,p.lvn_volume[SVP_MAX_NODES-1],p.lvn[SVP_MAX_NODES-1],false,p.poc)) return;
      pos=SVP_MAX_NODES-1;
   }
   else p.lvn_count++;
   while(pos>0 && SVP_VpNodeBefore(volume,price,p.lvn_volume[pos-1],p.lvn[pos-1],false,p.poc))
   { p.lvn[pos]=p.lvn[pos-1]; p.lvn_volume[pos]=p.lvn_volume[pos-1]; pos--; }
   p.lvn[pos]=price; p.lvn_volume[pos]=volume;
}

// HVN / LVN from the 3-row smoothed histogram. A flat top (or a flat bottom) is
// ONE node at the centre of the flat run, so a level never leans towards the
// lower or the upper end of it.
void SVP_VpNodes(const SSvpParams &prm,SSvpProfile &p)
{
   p.hvn_count=0; p.lvn_count=0;
   int n=p.bin_count;
   if(n<5) return;
   double s[SVP_VP_MAX_BINS];
   double sorted[SVP_VP_MAX_BINS];
   double smax=0.0;
   for(int b=0;b<n;b++)
   {
      double sum=p.bins[b]; int k=1;
      if(b>0) { sum+=p.bins[b-1]; k++; }
      if(b<n-1) { sum+=p.bins[b+1]; k++; }
      s[b]=sum/(double)k;
      sorted[b]=s[b];
      if(s[b]>smax) smax=s[b];
   }
   if(!(smax>0.0)) return;
   for(int i=1;i<n;i++)
   {
      double key=sorted[i]; int j=i-1;
      while(j>=0 && sorted[j]>key) { sorted[j+1]=sorted[j]; j--; }
      sorted[j+1]=key;
   }
   double median=((n%2)==1?sorted[n/2]:0.5*(sorted[n/2-1]+sorted[n/2]));
   //--- peaks: a run of equal rows that is higher than both neighbours (the
   //--- ends of the histogram count as lower)
   int first_peak_end=-1,last_peak_start=-1;
   for(int b=0;b<n;b++)
   {
      int from=b,e=b;
      while(e+1<n && s[e+1]==s[from]) e++;
      b=e;
      bool up_left=(from==0 || s[from]>s[from-1]);
      bool up_right=(e==n-1 || s[e]>s[e+1]);
      if(!up_left || !up_right) continue;
      if(first_peak_end<0) first_peak_end=e;
      last_peak_start=from;
      if(s[from]<prm.vp_hvn_fraction*smax) continue;
      int away=(from>p.poc_hi_bin ? from-p.poc_hi_bin : (e<p.poc_lo_bin ? p.poc_lo_bin-e : 0));
      if(away<=1) continue;                       // that peak IS the point of control
      SVP_VpKeepNode(p,true,p.origin+(0.5*(double)(from+e)+0.5)*p.bin_size,s[from]);
   }
   if(first_peak_end<0 || last_peak_start<=first_peak_end) return;
   //--- valleys between the outermost peaks
   for(int b=first_peak_end+1;b<last_peak_start;b++)
   {
      int from=b,e=b;
      while(e+1<last_peak_start && s[e+1]==s[from]) e++;
      b=e;
      if(!(s[from]<s[from-1] && s[e]<s[e+1])) continue;
      if(s[from]>prm.vp_lvn_fraction*median) continue;
      SVP_VpKeepNode(p,false,p.origin+(0.5*(double)(from+e)+0.5)*p.bin_size,s[from]);
   }
}

// Build the profile of the bars whose open time lies in [from_time, to_time).
// Only bars with index < n are read. `bin_size` must be a positive tick multiple;
// it is doubled as often as needed to keep the histogram inside its fixed size.
bool SVP_VpBuild(const MqlRates &r[],const int n,const datetime from_time,const datetime to_time,
                 const double bin_size,const ENUM_SVP_VP_KIND kind,const SSvpParams &prm,SSvpProfile &p)
{
   SVP_VpReset(p);
   p.kind=kind; p.from_time=from_time; p.to_time=to_time;
   int have=ArraySize(r);
   int m=(n<have?n:have);
   if(m<=0 || to_time<=from_time || !(bin_size>0.0) || !MathIsValidNumber(bin_size))
   { p.reason="invalid window or row height"; return false; }
   int first=-1,last=-1;
   double lo=0.0,hi=0.0;
   bool all_real=prm.vp_use_real_volume;
   for(int i=0;i<m;i++)
   {
      if(r[i].time<from_time) continue;
      if(r[i].time>=to_time) break;
      if(!SVP_BarValid(r[i]) || r[i].tick_volume<=0) continue;
      if(first<0) { first=i; lo=r[i].low; hi=r[i].high; }
      last=i;
      if(r[i].low<lo) lo=r[i].low;
      if(r[i].high>hi) hi=r[i].high;
      if(r[i].real_volume<=0) all_real=false;
      p.bars++;
   }
   if(first<0 || p.bars<=0) { p.reason="no bars with volume in the window"; return false; }
   double bin=bin_size;
   double phase=prm.vp_grid_phase;
   double origin=MathFloor((lo-phase)/bin)*bin+phase;
   double top=MathFloor((hi-origin)/bin);
   int guard=0;
   while(top>=(double)SVP_VP_MAX_BINS && guard<40)
   {
      bin*=2.0;
      origin=MathFloor((lo-phase)/bin)*bin+phase;
      top=MathFloor((hi-origin)/bin);
      guard++;
   }
   if(!MathIsValidNumber(origin) || !MathIsValidNumber(top) || top<0.0 || top>=(double)SVP_VP_MAX_BINS)
   { p.reason="price range does not fit the histogram"; p.bars=0; return false; }
   int count=(int)top+1;
   double total=0.0;
   for(int i=first;i<=last;i++)
   {
      if(r[i].time<from_time || r[i].time>=to_time) continue;
      if(!SVP_BarValid(r[i]) || r[i].tick_volume<=0) continue;
      double vol=(all_real?(double)r[i].real_volume:(double)r[i].tick_volume);
      int b0=(int)MathFloor((r[i].low-origin)/bin);
      int b1=(int)MathFloor((r[i].high-origin)/bin);
      if(b0<0) b0=0;
      if(b1>=count) b1=count-1;
      if(b1<b0) continue;
      double each=vol/(double)(b1-b0+1);
      for(int b=b0;b<=b1;b++) p.bins[b]+=each;
      total+=vol;
   }
   if(!(total>0.0)) { p.reason="no positive volume in the window"; p.bars=0; return false; }
   // Point of control. Rows tie EXACTLY whenever the same bars cover them, and
   // that is common (about one profile in four on XAUUSD M15). The heaviest RUN
   // of rows is the point of control and its price is the centre of that run;
   // among several heaviest runs the one nearest to the volume-weighted mean
   // row wins. Taking the lowest tied row instead would pull the POC down.
   double vmax=0.0,mass=0.0,sum=0.0;
   for(int b=0;b<count;b++)
   {
      if(p.bins[b]>vmax) vmax=p.bins[b];
      mass+=((double)b+0.5)*p.bins[b];
      sum+=p.bins[b];
   }
   double mean_row=(sum>0.0?mass/sum:0.5*(double)count);
   int run_lo=-1,run_hi=-1;
   double best_gap=0.0;
   for(int b=0;b<count;b++)
   {
      if(p.bins[b]<vmax) continue;
      int e=b;
      while(e+1<count && !(p.bins[e+1]<vmax)) e++;
      double gap=MathAbs(0.5*(double)(b+e)+0.5-mean_row);
      if(run_lo<0 || gap<best_gap) { run_lo=b; run_hi=e; best_gap=gap; }
      b=e;
   }
   // Value area: grow towards the heavier neighbour. Equal neighbours are taken
   // together, so the area has no preferred side.
   int left=run_lo,right=run_hi;
   double included=0.0;
   for(int b=run_lo;b<=run_hi;b++) included+=p.bins[b];
   while(included/total+1.0e-12<prm.vp_value_fraction && (left>0 || right<count-1))
   {
      double lv=(left>0?p.bins[left-1]:-1.0);
      double rv=(right<count-1?p.bins[right+1]:-1.0);
      if(lv>rv)      { left--;  included+=p.bins[left]; }
      else if(rv>lv) { right++; included+=p.bins[right]; }
      else           { left--;  included+=p.bins[left]; right++; included+=p.bins[right]; }
   }
   p.bin_size=bin; p.origin=origin; p.bin_count=count; p.total_volume=total;
   p.real_volume=all_real;
   p.first_bar=r[first].time; p.last_bar=r[last].time;
   p.poc_bin=(run_lo+run_hi)/2; p.poc_lo_bin=run_lo; p.poc_hi_bin=run_hi; p.val_bin=left; p.vah_bin=right;
   p.poc=origin+(0.5*(double)(run_lo+run_hi)+0.5)*bin;
   p.val=origin+(double)left*bin;
   p.vah=origin+(double)(right+1)*bin;
   p.poc_volume=vmax;
   p.va_fraction=included/total;
   p.basis=(all_real ? "REAL volume as reported by the broker feed"
                     : "BROKER TICK VOLUME (price-change count at this broker; not centralized exchange volume, not bid/ask order flow)");
   p.reason=(prm.vp_use_real_volume && !all_real ? "real volume requested but absent on some bars: tick volume used"
                                                 : "valid");
   p.valid=true;
   SVP_VpNodes(prm,p);
   return true;
}

// Every invariant a profile must satisfy. Used by the self-test and by the
// replay, so a historical profile is checked, not assumed.
bool SVP_VpValidate(const SSvpProfile &p,string &why)
{
   why="";
   if(!p.valid) { why="profile is not valid"; return false; }
   if(p.bin_count<1 || p.bin_count>SVP_VP_MAX_BINS || !(p.bin_size>0.0)) { why="bin geometry"; return false; }
   double sum=0.0,vmax=0.0;
   for(int b=0;b<p.bin_count;b++)
   {
      if(!(p.bins[b]>=0.0) || !MathIsValidNumber(p.bins[b])) { why="negative or invalid bin"; return false; }
      sum+=p.bins[b];
      if(p.bins[b]>vmax) vmax=p.bins[b];
   }
   if(MathAbs(sum-p.total_volume)>1.0e-6*MathMax(1.0,p.total_volume)) { why="bins do not sum to the total volume"; return false; }
   if(p.poc_lo_bin<0 || p.poc_hi_bin>=p.bin_count || p.poc_lo_bin>p.poc_hi_bin ||
      p.poc_bin<p.poc_lo_bin || p.poc_bin>p.poc_hi_bin) { why="POC rows"; return false; }
   for(int b=p.poc_lo_bin;b<=p.poc_hi_bin;b++)
      if(p.bins[b]<vmax) { why="POC is not the heaviest row"; return false; }
   if((p.poc_lo_bin>0 && !(p.bins[p.poc_lo_bin-1]<vmax)) || (p.poc_hi_bin<p.bin_count-1 && !(p.bins[p.poc_hi_bin+1]<vmax)))
   { why="POC does not cover its whole run of equal rows"; return false; }
   if(MathAbs(p.poc-(p.origin+(0.5*(double)(p.poc_lo_bin+p.poc_hi_bin)+0.5)*p.bin_size))>1.0e-9*MathMax(1.0,MathAbs(p.poc)))
   { why="POC price is not the centre of its rows"; return false; }
   if(!(p.val<=p.poc && p.poc<=p.vah)) { why="VAL <= POC <= VAH violated"; return false; }
   if(p.val_bin<0 || p.vah_bin>=p.bin_count || p.val_bin>p.poc_lo_bin || p.vah_bin<p.poc_hi_bin) { why="value-area bins"; return false; }
   double inside=0.0;
   for(int b=p.val_bin;b<=p.vah_bin;b++) inside+=p.bins[b];
   if(MathAbs(inside/p.total_volume-p.va_fraction)>1.0e-9) { why="value-area share is inconsistent"; return false; }
   if(p.hvn_count<0 || p.hvn_count>SVP_MAX_NODES || p.lvn_count<0 || p.lvn_count>SVP_MAX_NODES) { why="node count"; return false; }
   for(int i=0;i<p.hvn_count;i++)
      if(p.hvn[i]<p.origin || p.hvn[i]>p.origin+(double)p.bin_count*p.bin_size) { why="HVN outside the profile"; return false; }
   for(int i=0;i<p.lvn_count;i++)
      if(p.lvn[i]<p.origin || p.lvn[i]>p.origin+(double)p.bin_count*p.bin_size) { why="LVN outside the profile"; return false; }
   return true;
}

datetime SVP_DayStart(const datetime t)
{
   return t-(t%86400);
}

datetime SVP_WeekStart(const datetime t)
{
   datetime day=t/86400;
   datetime monday=day-((day+3)%7);          // 1970-01-01 was a Thursday
   return monday*86400;
}

// The session window that contains t. Server hours come from the parameters.
void SVP_SessionWindow(const datetime t,const SSvpParams &prm,datetime &from_time,datetime &to_time)
{
   datetime day=SVP_DayStart(t);
   int hour=(int)((t-day)/3600);
   int a=prm.sess_asia_start,l=prm.sess_london_start,ny=prm.sess_ny_start,e=prm.sess_ny_end;
   if(hour>=a && hour<l)        { from_time=day+(datetime)a*3600;  to_time=day+(datetime)l*3600; }
   else if(hour>=l && hour<ny)  { from_time=day+(datetime)l*3600;  to_time=day+(datetime)ny*3600; }
   else if(hour>=ny && hour<e)  { from_time=day+(datetime)ny*3600; to_time=day+(datetime)e*3600; }
   else if(hour>=e)             { from_time=day+(datetime)e*3600;  to_time=day+86400+(datetime)a*3600; }
   else                         { from_time=day-86400+(datetime)e*3600; to_time=day+(datetime)a*3600; }
}

// Window of the profile `shift` periods back (0 = the one the newest bar is in).
// Earlier periods are found in the DATA, so weekends and holidays are skipped.
bool SVP_VpWindow(const MqlRates &r[],const int n,const ENUM_SVP_VP_KIND kind,const int shift,
                  const SSvpParams &prm,datetime &from_time,datetime &to_time)
{
   from_time=0; to_time=0;
   if(n<=0 || shift<0 || kind==SVP_VP_RANGE) return false;
   int i=n-1;
   for(int step=0;step<=shift;step++)
   {
      if(i<0) return false;
      datetime t=r[i].time;
      if(kind==SVP_VP_DAILY)       { from_time=SVP_DayStart(t);  to_time=from_time+86400; }
      else if(kind==SVP_VP_WEEKLY) { from_time=SVP_WeekStart(t); to_time=from_time+7*86400; }
      else                         SVP_SessionWindow(t,prm,from_time,to_time);
      while(i>=0 && r[i].time>=from_time) i--;   // step to the newest bar BEFORE this window
   }
   return (to_time>from_time);
}

// Cached build. The row height comes from the ATR at the bar just before the
// window opened, so it is fixed for the whole life of the profile.
bool SVP_VpGet(const MqlRates &r[],const int n,const double &atr[],const datetime from_time,
               const datetime to_time,const ENUM_SVP_VP_KIND kind,const SSvpParams &prm,SSvpProfile &out)
{
   SVP_VpReset(out);
   out.kind=kind; out.from_time=from_time; out.to_time=to_time;
   if(n<=0 || ArraySize(atr)<n || to_time<=from_time) { out.reason="invalid window"; return false; }
   int first=-1,last=-1;
   // fingerprint of the bars the profile is built from: a cached profile is
   // reused only for the SAME data, so a re-synchronised history (the broker
   // corrected a bar) or another symbol can never be served a stale profile
   int    fp_bars=0;
   double fp_high=0.0,fp_low=0.0;
   long   fp_tick=0,fp_real=0;
   for(int i=n-1;i>=0;i--)
   {
      if(r[i].time>=to_time) continue;
      if(r[i].time<from_time) break;
      if(last<0) last=i;
      first=i;
      fp_bars++; fp_high+=r[i].high; fp_low+=r[i].low;
      fp_tick+=r[i].tick_volume; fp_real+=r[i].real_volume;
   }
   if(first<0) { out.reason="no bars in the window"; return false; }
   double a=atr[first>0?first-1:first];
   double bin=SVP_VpBinSize(prm.tick_size,a,prm.vp_row_atr,prm.vp_row_ticks);
   string key=IntegerToString((int)kind)+"|"+IntegerToString((long)from_time)+"|"+
              IntegerToString((long)to_time)+"|"+IntegerToString((long)r[last].time)+"|"+
              DoubleToString(bin,8)+"|"+DoubleToString(prm.vp_grid_phase,8)+"|"+DoubleToString(prm.vp_value_fraction,4)+"|"+
              (prm.vp_use_real_volume?"R":"T")+"|"+IntegerToString(fp_bars)+"|"+
              DoubleToString(fp_high,8)+"|"+DoubleToString(fp_low,8)+"|"+
              IntegerToString(fp_tick)+"|"+IntegerToString(fp_real);
   for(int c=0;c<SVP_VP_CACHE;c++)
      if(g_svp_vp_cache_key[c]==key && g_svp_vp_cache[c].valid)
      { out=g_svp_vp_cache[c]; g_svp_vp_hits++; return true; }
   g_svp_vp_builds++;
   if(!SVP_VpBuild(r,n,from_time,to_time,bin,kind,prm,out)) return false;
   // a developing profile replaces its own older snapshot instead of filling the cache
   string stem=IntegerToString((int)kind)+"|"+IntegerToString((long)from_time)+"|";
   int slot=-1;
   for(int c=0;c<SVP_VP_CACHE && slot<0;c++)
      if(StringFind(g_svp_vp_cache_key[c],stem)==0) slot=c;
   if(slot<0) { slot=g_svp_vp_cache_next; g_svp_vp_cache_next=(g_svp_vp_cache_next+1)%SVP_VP_CACHE; }
   g_svp_vp_cache[slot]=out;
   g_svp_vp_cache_key[slot]=key;
   return true;
}

// The profile the decision reads: the developing one of the configured kind,
// or - while that is still thinner than vp_min_bars - the previous complete one.
bool SVP_VpReference(const MqlRates &r[],const int n,const double &atr[],const SSvpParams &prm,
                     SSvpProfile &out,bool &is_previous)
{
   is_previous=false;
   datetime f=0,t=0;
   bool have=false;
   if(prm.vp_kind==SVP_VP_RANGE)
   {
      // an explicit (visible / selected) range has no "previous" profile
      if(prm.vp_range_to>prm.vp_range_from)
         return SVP_VpGet(r,n,atr,prm.vp_range_from,prm.vp_range_to,SVP_VP_RANGE,prm,out);
      SVP_VpReset(out);
      out.reason="no range selected";
      return false;
   }
   if(SVP_VpWindow(r,n,prm.vp_kind,0,prm,f,t)) have=SVP_VpGet(r,n,atr,f,t,prm.vp_kind,prm,out);
   if(have && out.bars>=prm.vp_min_bars) return true;
   SSvpProfile prev;
   datetime pf=0,pt=0;
   if(SVP_VpWindow(r,n,prm.vp_kind,1,prm,pf,pt) && SVP_VpGet(r,n,atr,pf,pt,prm.vp_kind,prm,prev) &&
      prev.bars>=prm.vp_min_bars)
   { out=prev; is_previous=true; return true; }
   if(have) { out.reason="developing profile has only "+IntegerToString(out.bars)+" bars and no previous one exists"; }
   return have;
}

// Numeric self-test on a hand-computable profile: six bars, one-unit rows.
//   rows  100 101 102 103 104 105
//   vol    10  30  60  40  20  10   (bar k covers exactly row k)
// POC = row 102 (centre 102.5). 70% of 170 = 119: 60 -> +40 (103) = 100 -> +30
// (101) = 130 >= 119, so the value area is rows 101..103 = 101.0 .. 104.0.
bool SVP_VpSelfTest(string &where)
{
   where="";
   MqlRates r[];
   ArrayResize(r,6);
   long vols[6]={10,30,60,40,20,10};
   for(int i=0;i<6;i++)
   {
      r[i].time=(datetime)(86400*20000+i*900);
      r[i].open=100.25+(double)i; r[i].close=100.75+(double)i;
      r[i].low=100.25+(double)i;  r[i].high=100.75+(double)i;
      r[i].tick_volume=vols[i]; r[i].real_volume=0; r[i].spread=0;
   }
   SSvpParams prm;
   SVP_DefaultParams(prm);
   SSvpProfile p;
   string why="";
   if(!SVP_VpBuild(r,6,r[0].time,r[5].time+900,1.0,SVP_VP_RANGE,prm,p)) where="VP-1 build failed: "+p.reason;
   else if(!SVP_VpValidate(p,why)) where="VP-2 invariants: "+why;
   else if(p.bin_count!=6 || MathAbs(p.total_volume-170.0)>1.0e-9) where="VP-3 bins / total";
   else if(MathAbs(p.poc-102.5)>1.0e-9) where="VP-4 POC must be 102.5";
   else if(MathAbs(p.val-101.0)>1.0e-9 || MathAbs(p.vah-104.0)>1.0e-9) where="VP-5 value area must be 101.0 .. 104.0";
   else if(MathAbs(p.va_fraction-130.0/170.0)>1.0e-9) where="VP-6 value-area share must be 130/170";
   else if(p.real_volume || StringFind(p.basis,"TICK VOLUME")<0) where="VP-7 the basis must say tick volume";
   if(where=="")
   {
      // real volume is used only when asked for AND present on every bar
      prm.vp_use_real_volume=true;
      SVP_VpBuild(r,6,r[0].time,r[5].time+900,1.0,SVP_VP_RANGE,prm,p);
      if(p.real_volume) where="VP-8 real volume claimed without real volume";
      for(int i=0;i<6;i++) r[i].real_volume=1000-100*i;
      SVP_VpBuild(r,6,r[0].time,r[5].time+900,1.0,SVP_VP_RANGE,prm,p);
      if(where=="" && (!p.real_volume || MathAbs(p.poc-100.5)>1.0e-9)) where="VP-9 real volume must drive the profile when present";
   }
   if(where=="" && MathAbs(SVP_VpBinSize(0.01,3.0,0.10,0)-0.30)>1.0e-9) where="VP-10 row = 0.10 ATR on the tick grid";
   if(where=="" && MathAbs(SVP_VpBinSize(0.25,0.3,0.10,0)-0.25)>1.0e-9) where="VP-11 a row is never smaller than one tick";
   if(where=="" && MathAbs(SVP_VpBinSize(0.01,3.0,0.10,7)-0.07)>1.0e-9) where="VP-12 fixed row in ticks";
   return (where=="");
}

// How the last closed bars relate to the profile. Directional states carry a
// `support` sign; acceptance at the POC or at a HVN is balance and supports
// neither side.
void SVP_VpContext(const SSvpProfile &p,const MqlRates &r[],const int n,const double atr,
                   const SSvpParams &prm,SSvpVpContext &c)
{
   c.valid=false; c.state=SVP_VPC_NONE; c.support=0; c.location=0; c.level=0.0; c.text="N/A";
   int look=prm.vp_accept_bars;
   if(!p.valid || n<look+2 || !(atr>0.0)) return;
   int last=n-1;
   double tol=prm.vp_tol_atr*atr;
   if(tol<p.bin_size) tol=p.bin_size;
   double cl=r[last].close;
   c.valid=true;
   c.location=(cl>p.vah?1:(cl<p.val?-1:0));
   c.text=SVP_VpContextText(SVP_VPC_NONE);
   //--- 1. a body that crosses a low-volume node: fast traversal, continuation
   double body=r[last].close-r[last].open;
   for(int i=0;i<p.lvn_count;i++)
   {
      double lv=p.lvn[i];
      bool crossed_up=(r[last].open<lv-tol && r[last].close>lv+tol);
      bool crossed_dn=(r[last].open>lv+tol && r[last].close<lv-tol);
      if((crossed_up || crossed_dn) && MathAbs(body)>=prm.disp_body_atr*atr)
      {
         c.state=SVP_VPC_LVN_TRAVERSAL; c.support=(crossed_up?1:-1); c.level=lv;
         c.text="LVN "+DoubleToString(lv,prm.digits)+" traversed "+(crossed_up?"up":"down");
         return;
      }
   }
   //--- 2. rejection at an edge of value / at the POC / at an LVN: the level was
   //---    traded inside the last `look` bars and the newest close left it again
   //---    on the side price CAME from
   int before=last-look;
   double came=r[before].close;
   bool hit_vah=false,hit_val=false,hit_poc=false;
   int vah_bar=-1,val_bar=-1;                     // newest bar that traded each edge
   for(int j=before+1;j<=last;j++)
   {
      if(r[j].high>=p.vah-tol && r[j].low<=p.vah+tol) { hit_vah=true; vah_bar=j; }
      if(r[j].low<=p.val+tol && r[j].high>=p.val-tol) { hit_val=true; val_bar=j; }
      if(r[j].low<=p.poc+tol && r[j].high>=p.poc-tol) hit_poc=true;
   }
   bool rej_vah=(hit_vah && came<p.vah-tol && cl<p.vah-tol);
   bool rej_val=(hit_val && came>p.val+tol && cl>p.val+tol);
   // A narrow value area can have BOTH edges traded and left inside the same few
   // bars. The edge traded last is the one price is leaving; when one bar traded
   // both, the bars cannot say which came last and neither side is claimed.
   if(rej_vah && rej_val)
   {
      if(vah_bar>val_bar) rej_val=false;
      else if(val_bar>vah_bar) rej_vah=false;
      else { rej_vah=false; rej_val=false; }
   }
   if(rej_vah)
   { c.state=SVP_VPC_VAH_REJECTION; c.support=-1; c.level=p.vah;
     c.text="rejected at VAH "+DoubleToString(p.vah,prm.digits); return; }
   if(rej_val)
   { c.state=SVP_VPC_VAL_REJECTION; c.support=1; c.level=p.val;
     c.text="rejected at VAL "+DoubleToString(p.val,prm.digits); return; }
   // the mirror cases: an edge of value retested from OUTSIDE and held
   if(hit_vah && came>p.vah+tol && cl>p.vah+tol)
   { c.state=SVP_VPC_VAH_ACCEPTANCE; c.support=1; c.level=p.vah;
     c.text="VAH "+DoubleToString(p.vah,prm.digits)+" retested and held as support"; return; }
   if(hit_val && came<p.val-tol && cl<p.val-tol)
   { c.state=SVP_VPC_VAL_ACCEPTANCE; c.support=-1; c.level=p.val;
     c.text="VAL "+DoubleToString(p.val,prm.digits)+" retested and held as resistance"; return; }
   if(hit_poc && came>p.poc+tol && cl>p.poc+tol)
   { c.state=SVP_VPC_POC_REJECTION; c.support=1; c.level=p.poc;
     c.text="held above POC "+DoubleToString(p.poc,prm.digits); return; }
   if(hit_poc && came<p.poc-tol && cl<p.poc-tol)
   { c.state=SVP_VPC_POC_REJECTION; c.support=-1; c.level=p.poc;
     c.text="rejected below POC "+DoubleToString(p.poc,prm.digits); return; }
   for(int i=0;i<p.lvn_count;i++)
   {
      double lv=p.lvn[i];
      bool hit=false;
      for(int j=before+1;j<=last && !hit;j++)
         if(r[j].low<=lv+tol && r[j].high>=lv-tol) hit=true;
      if(!hit) continue;
      if(came>lv+tol && cl>lv+tol)
      { c.state=SVP_VPC_LVN_REJECTION; c.support=1; c.level=lv;
        c.text="rejected from LVN "+DoubleToString(lv,prm.digits)+" (up)"; return; }
      if(came<lv-tol && cl<lv-tol)
      { c.state=SVP_VPC_LVN_REJECTION; c.support=-1; c.level=lv;
        c.text="rejected from LVN "+DoubleToString(lv,prm.digits)+" (down)"; return; }
   }
   //--- 3. acceptance: `look` consecutive closes beyond value, at the POC, or at a HVN
   bool above=true,below=true,at_poc=true;
   for(int j=before+1;j<=last;j++)
   {
      if(!(r[j].close>p.vah+tol)) above=false;
      if(!(r[j].close<p.val-tol)) below=false;
      if(MathAbs(r[j].close-p.poc)>tol) at_poc=false;
   }
   if(above)
   { c.state=SVP_VPC_VAH_ACCEPTANCE; c.support=1; c.level=p.vah;
     c.text="accepted above VAH "+DoubleToString(p.vah,prm.digits); return; }
   if(below)
   { c.state=SVP_VPC_VAL_ACCEPTANCE; c.support=-1; c.level=p.val;
     c.text="accepted below VAL "+DoubleToString(p.val,prm.digits); return; }
   if(at_poc)
   { c.state=SVP_VPC_POC_ACCEPTANCE; c.support=0; c.level=p.poc;
     c.text="accepted at POC "+DoubleToString(p.poc,prm.digits)+" (balance)"; return; }
   for(int i=0;i<p.hvn_count;i++)
   {
      bool at=true;
      for(int j=before+1;j<=last && at;j++)
         if(MathAbs(r[j].close-p.hvn[i])>tol) at=false;
      if(at)
      { c.state=SVP_VPC_HVN_ACCEPTANCE; c.support=0; c.level=p.hvn[i];
        c.text="accepted at HVN "+DoubleToString(p.hvn[i],prm.digits)+" (balance)"; return; }
   }
}

// Volume-profile levels that sit inside (or within tol of) a price zone.
// Returns how many SUPPORTIVE levels were found for `direction`:
//   POC and HVN (accepted prices act as support / resistance) on either side,
//   VAL for a long zone, VAH for a short zone.
// An LVN inside the zone is reported separately: thin volume is not support.
int SVP_VpConfluence(const SSvpProfile &p,const double lo,const double hi,const double tol,
                     const int direction,const int digits,string &what,bool &lvn_inside)
{
   what=""; lvn_inside=false;
   if(!p.valid || !(hi>=lo)) return 0;
   double a=lo-tol,b=hi+tol;
   int count=0;
   if(p.poc>=a && p.poc<=b) { what+="POC "+DoubleToString(p.poc,digits); count++; }
   if(direction>0 && p.val>=a && p.val<=b) { what+=(what==""?"":", ")+"VAL "+DoubleToString(p.val,digits); count++; }
   if(direction<0 && p.vah>=a && p.vah<=b) { what+=(what==""?"":", ")+"VAH "+DoubleToString(p.vah,digits); count++; }
   for(int i=0;i<p.hvn_count;i++)
      if(p.hvn[i]>=a && p.hvn[i]<=b) { what+=(what==""?"":", ")+"HVN "+DoubleToString(p.hvn[i],digits); count++; }
   for(int i=0;i<p.lvn_count;i++)
      if(p.lvn[i]>=lo && p.lvn[i]<=hi) lvn_inside=true;
   return count;
}

// The profile's vote on a candidate: +1 supportive, 0 neutral, -1 opposing.
// Opposing context always wins: a zone at a HVN does not excuse buying into a
// VAH rejection.
int SVP_VpVerdict(const SSvpProfile &p,const SSvpVpContext &c,const double zone_lo,const double zone_hi,
                  const int direction,const double tol,const int digits,string &text)
{
   if(!p.valid) { text="N/A (no volume profile)"; return 0; }
   string what="";
   bool lvn_inside=false;
   int conf=SVP_VpConfluence(p,zone_lo,zone_hi,tol,direction,digits,what,lvn_inside);
   if(c.valid && c.support==-direction && direction!=0)
   { text="OPPOSING: "+c.text; return -1; }
   if(c.valid && c.support==direction && direction!=0)
   { text="SUPPORTIVE: "+c.text+(conf>0?" + zone at "+what:""); return 1; }
   if(conf>0)
   { text="SUPPORTIVE: zone at "+what; return 1; }
   text="NEUTRAL: "+(c.valid?c.text:"no context")+(lvn_inside?" (LVN inside the zone: thin volume, weak support)":"")+
        " | POC "+DoubleToString(p.poc,digits);
   return 0;
}

#endif
//+------------------------------------------------------------------+
