//+------------------------------------------------------------------+
//|                                                 QSMC_Stats.mqh   |
//|  CStatsLogger - signal CSV journal + optional durable EdgeBook.    |
//|                                                                   |
//|  NO LOOK-AHEAD: outcome observation begins on the first closed bar |
//|  after the signal time. The signal bar itself can never improve a  |
//|  row, and exit-bar MFE/MAE are excluded when OHLC order is unknown.|
//|                                                                   |
//|  HONESTY RULE: no rate, percentage or "win rate" is printed until  |
//|  n >= min_sample. Below that the logger prints "n=K (insufficient  |
//|  sample - no rate shown)". A count is never presented as a         |
//|  probability.                                                      |
//|                                                                   |
//|  COMPLEXITY: Log O(open_rows) for duplicate-pending check. Advance |
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
   datetime          signal_time;
   datetime          last_advanced_time;
   string            setup_id;         // deterministic per published setup
   string            strategy_key;    // source|timeframe|direction|role
   string            symbol;
   string            timeframe;
   double            spread_points;
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
  };

//+------------------------------------------------------------------+
// Numerically stable, terminal-independent statistics used by optional
// range-analysis features. These do not imply a trading edge.
//+------------------------------------------------------------------+
#define QSMC_VP_MAX_BINS 2048

struct SEWState
  {
   bool   initialized;
   long   count;
   double mean;
   double variance;
  };

// Exponentially weighted population moments. For 0 < alpha <= 1:
// mean' = mean + alpha*delta; var' = (1-alpha)*(var + alpha*delta^2).
// This is stable for large-offset/small-dispersion data; variance is the
// weighted population variance, not a sample/unbiased estimate.
class CEWStatistics
  {
public:
   static void Reset(SEWState &s)
     { s.initialized=false; s.count=0; s.mean=0.0; s.variance=0.0; }

   static bool Update(SEWState &s,const double x,const double alpha)
     {
      if(!MathIsValidNumber(x) || !MathIsValidNumber(alpha) || alpha<=0.0 || alpha>1.0)
         return false;
      if(!s.initialized)
        { s.initialized=true; s.count=1; s.mean=x; s.variance=0.0; return true; }
      double delta=x-s.mean;
      double next_mean=s.mean+alpha*delta;
      double next_var=(1.0-alpha)*(s.variance+alpha*delta*delta);
      if(!MathIsValidNumber(next_mean) || !MathIsValidNumber(next_var) || next_var<0.0)
         return false;
      s.mean=next_mean; s.variance=next_var; s.count++;
      return true;
     }
  };

// Two-sided Page CUSUM on standardized observations. `k` is the reference
// allowance (in standard deviations) and `h` the alarm threshold. An alarm
// latches until Reset(); updating continues to report the current side.
class CCUSUM
  {
private:
   double m_positive;
   double m_negative;
   bool   m_alarm;
   int    m_side;
   long   m_count;
public:
                     CCUSUM() { Reset(); }
   void              Reset()
     { m_positive=0.0; m_negative=0.0; m_alarm=false; m_side=0; m_count=0; }
   bool              Update(const double x,const double reference,const double sigma,
                             const double k,const double h)
     {
      if(!MathIsValidNumber(x) || !MathIsValidNumber(reference) ||
         !MathIsValidNumber(sigma) || !MathIsValidNumber(k) || !MathIsValidNumber(h) ||
         sigma<=0.0 || k<0.0 || h<=0.0) return false;
      double z=(x-reference)/sigma;
      if(!MathIsValidNumber(z)) return false;
      double next_positive=MathMax(0.0,m_positive+z-k);
      double next_negative=MathMax(0.0,m_negative-z-k);
      if(!MathIsValidNumber(next_positive) || !MathIsValidNumber(next_negative)) return false;
      m_positive=next_positive; m_negative=next_negative;
      m_count++;
      if(m_positive>=h) { m_alarm=true; m_side=1; }
      else if(m_negative>=h) { m_alarm=true; m_side=-1; }
      return true;
     }
   bool              Alarm() const { return m_alarm; }
   int               Side() const { return m_side; }
   long              Count() const { return m_count; }
   double            PositiveSum() const { return m_positive; }
   double            NegativeSum() const { return m_negative; }
  };

// Wilson score interval for an observed binomial proportion. It quantifies
// sampling uncertainty in success rate only; it says nothing about payoff,
// costs, or profitability. Returns false for invalid counts or z-score.
bool QSMC_WilsonInterval(const long successes,const long trials,const double z,
                         double &lower,double &upper)
  {
   lower=0.0; upper=0.0;
   if(trials<=0 || successes<0 || successes>trials || !MathIsValidNumber(z) || z<=0.0)
      return false;
   double n=(double)trials, p=(double)successes/n, z2=z*z;
   if(!MathIsValidNumber(z2)) return false;
   double den=1.0+z2/n;
   double center=(p+z2/(2.0*n))/den;
   double half=z*MathSqrt((p*(1.0-p)+z2/(4.0*n))/n)/den;
   if(!MathIsValidNumber(center) || !MathIsValidNumber(half)) return false;
   double lo=MathMax(0.0,center-half);
   double hi=MathMin(1.0,center+half);
   if(!MathIsValidNumber(lo) || !MathIsValidNumber(hi) || lo>hi) return false;
   lower=lo; upper=hi;
   return true;
  }

struct SVolumeProfileResult
  {
   bool     valid;
   int      requested_bars;
   int      accepted_bars;
   int      bin_count;
   double   coverage;
   double   total_tick_volume;
   double   poc;
   double   vah;
   double   val;
   datetime from_time;
   datetime to_time;
   bool     session_profile;
   string   profile_kind;
   string   volume_basis;
   string   reason;
  };

// Fixed-resolution rolling/session profile. Each bar's tick volume is spread
// uniformly across bins intersecting [low,high]; this is an OHLC approximation,
// not trade-at-price data. Complexity O(sum of per-bar intersected bins), capped
// by QSMC_VP_MAX_BINS and intended only for requested, bounded ranges.
class CVolumeProfile
  {
private:
   double m_bins[];
   double m_origin;
   double m_bin_size;
   int    m_count;
   SVolumeProfileResult m_result;
public:
                     CVolumeProfile() { Reset(); }
   void              Reset()
     {
      ArrayResize(m_bins,0); m_origin=0.0; m_bin_size=0.0; m_count=0;
      m_result.valid=false; m_result.requested_bars=0; m_result.accepted_bars=0;
      m_result.bin_count=0; m_result.coverage=0.0; m_result.total_tick_volume=0.0;
      m_result.poc=0.0; m_result.vah=0.0; m_result.val=0.0;
      m_result.from_time=0; m_result.to_time=0; m_result.session_profile=false;
      m_result.profile_kind="UNSET";
      m_result.volume_basis="broker tick_volume (not centralized exchange volume)";
      m_result.reason="not built";
     }
   SVolumeProfileResult Result() const { return m_result; }
   double            BinVolume(const int i) const
     { return (i>=0 && i<m_count ? m_bins[i] : 0.0); }
   double            BinLower(const int i) const
     { return (i>=0 && i<m_count ? m_origin+(double)i*m_bin_size : 0.0); }

   bool              Build(const MqlRates &rates[],const int start,const int count,
                           const double bin_size,const double value_fraction,
                           const bool session_profile)
     {
      Reset();
      m_result.requested_bars=count; m_result.session_profile=session_profile;
      m_result.profile_kind=(session_profile ? "SESSION_RANGE" : "ROLLING_RANGE");
      int rates_n=ArraySize(rates);
      if(start<0 || count<=0 || count>rates_n || start>rates_n-count ||
         !MathIsValidNumber(bin_size) || bin_size<=0.0 ||
         !MathIsValidNumber(value_fraction) || value_fraction<=0.0 || value_fraction>1.0)
        { m_result.reason="invalid range or parameters"; return false; }
      double lo=DBL_MAX, hi=-DBL_MAX;
      for(int i=start;i<start+count;i++)
        {
         if(!MathIsValidNumber(rates[i].low) || !MathIsValidNumber(rates[i].high) ||
            rates[i].high<rates[i].low || rates[i].tick_volume<=0) continue;
         lo=MathMin(lo,rates[i].low); hi=MathMax(hi,rates[i].high);
        }
      if(lo==DBL_MAX || hi<lo) { m_result.reason="no valid price bars"; return false; }
      m_bin_size=bin_size;
      m_origin=MathFloor(lo/bin_size)*bin_size;
      if(!MathIsValidNumber(m_origin)) { m_result.reason="invalid bin origin"; return false; }
      double max_index=MathFloor((hi-m_origin)/bin_size);
      if(!MathIsValidNumber(max_index) || max_index<0.0 || max_index>=QSMC_VP_MAX_BINS)
        { m_result.reason="range exceeds bin limit"; return false; }
      m_count=(int)max_index+1;
      if(ArrayResize(m_bins,m_count)!=m_count)
        { m_count=0; m_result.reason="bin allocation failed"; return false; }
      ArrayInitialize(m_bins,0.0);
      double total=0.0; datetime tmin=0,tmax=0;
      for(int i=start;i<start+count;i++)
        {
         MqlRates r=rates[i];
         if(!MathIsValidNumber(r.low) || !MathIsValidNumber(r.high) || r.high<r.low || r.tick_volume<=0)
            continue;
         int first=(int)MathFloor((r.low-m_origin)/bin_size);
         int last=(int)MathFloor((r.high-m_origin)/bin_size);
         if(first<0) first=0; if(last>=m_count) last=m_count-1;
         if(last<first) continue;
         double each=(double)r.tick_volume/(double)(last-first+1);
         for(int b=first;b<=last;b++) m_bins[b]+=each;
         total+=(double)r.tick_volume;
         m_result.accepted_bars++;
         if(tmin==0 || r.time<tmin) tmin=r.time;
         if(tmax==0 || r.time>tmax) tmax=r.time;
        }
      m_result.bin_count=m_count; m_result.total_tick_volume=total;
      m_result.coverage=(double)m_result.accepted_bars/(double)count;
      m_result.from_time=tmin; m_result.to_time=tmax;
      if(total<=0.0) { m_result.reason="no positive tick volume"; return false; }
      int poc_i=0;
      for(int b=1;b<m_count;b++) if(m_bins[b]>m_bins[poc_i]) poc_i=b;
      int left=poc_i,right=poc_i; double included=m_bins[poc_i];
      while(included/total+1.0e-12<value_fraction && (left>0 || right<m_count-1))
        {
         double lv=(left>0 ? m_bins[left-1] : -1.0);
         double rv=(right<m_count-1 ? m_bins[right+1] : -1.0);
         // Deterministic tie: expand down (lower price) first.
         if(lv>=rv) { if(left>0) { left--; included+=m_bins[left]; } else { right++; included+=m_bins[right]; } }
         else { right++; included+=m_bins[right]; }
        }
      m_result.poc=m_origin+((double)poc_i+0.5)*bin_size;
      m_result.val=m_origin+(double)left*bin_size;
      m_result.vah=m_origin+(double)(right+1)*bin_size;
      m_result.valid=true; m_result.reason="valid tick-volume profile";
      return true;
     }
  };

//--------------------------------------------------------------------
#define QEDGE_WIN      1
#define QEDGE_LOSS     2
#define QEDGE_BREAKEVEN 3
#define QEDGE_AMBIGUOUS 4
#define QEDGE_MAX_RECORDS 12000
#define QEDGE_HASH_SLOTS 32768
#define QEDGE_MAX_KEYS 128
#define QEDGE_SCHEMA_VERSION 1

struct SEdgeOutcomeRecord
  {
   string   record_type;          // PENDING or OUTCOME
   string   setup_id;
   string   strategy_key;
   string   symbol;
   string   timeframe;
   datetime entry_time;
   int      direction;
   double   entry;
   double   stop;
   double   target;
   int      outcome;
   double   outcome_r;
   double   mfe_r;
   double   mae_r;
   double   spread_points;
   string   resolution;
  };

struct SEdgeAggregate
  {
   string key;
   int    n;
   int    wins;
   int    losses;
   int    breakeven;
   int    ambiguous;
   double sum_r;
  };

// Versioned pending/outcome ledger. Uses the terminal-local MQL5/Files sandbox
// by default (FILE_COMMON is opt-in). Existing files are trusted only after
// exact header + row validation; malformed or duplicate rows disable disk
// writes and mark the loaded statistics UNTRUSTED instead of silently using
// a partial sample. Each completed setup ID is persisted once.
class CEdgeBook
  {
private:
   int    m_handle;
   string m_file;
   bool   m_open;
   bool   m_trusted;
   bool   m_write_enabled;
   bool   m_common;
   int    m_min_sample;
   int    m_record_count;
   int    m_key_count;
   int    m_flush_pending;
   int    m_parse_errors;
   int    m_duplicates;
   string m_ids[];
   bool   m_id_pending[];
   SEdgeOutcomeRecord m_pending[QSMC_STATS_MAX_ROWS];
   int    m_pending_count;
   string m_expected_symbol;
   string m_expected_timeframe;
   SEdgeAggregate m_keys[QEDGE_MAX_KEYS];

   string HeaderField(const int i) const
     {
      switch(i)
        {
         case 0: return "schema_version";
         case 1: return "record_type";
         case 2: return "setup_id";
         case 3: return "strategy_key";
         case 4: return "symbol";
         case 5: return "timeframe";
         case 6: return "entry_time";
         case 7: return "direction";
         case 8: return "entry";
         case 9: return "stop";
         case 10:return "target";
         case 11:return "outcome";
         case 12:return "outcome_r";
         case 13:return "mfe_r";
         case 14:return "mae_r";
         case 15:return "spread_points";
         default:return "resolution";
        }
     }

   bool NumericToken(const string v) const
     {
      int n=StringLen(v);
      if(n<=0) return false;
      int dots=0,digits=0;
      for(int i=0;i<n;i++)
        {
         ushort c=StringGetCharacter(v,i);
         if(c>='0' && c<='9') { digits++; continue; }
         if(c=='.' && dots==0) { dots++; continue; }
         if((c=='-' || c=='+') && i==0) continue;
         return false;
        }
      return digits>0;
     }

   bool ParseDouble(const string v,double &out) const
     {
      out=0.0;
      if(!NumericToken(v)) return false;
      out=StringToDouble(v);
      return MathIsValidNumber(out);
     }

   int HashStart(const string id) const
     {
      uint hash=(uint)0x811C9DC5;
      for(int i=0;i<StringLen(id);i++)
         hash=(hash^(uint)StringGetCharacter(id,i))*16777619;
      return (int)(hash%(uint)QEDGE_HASH_SLOTS);
     }

   int FindId(const string id) const
     {
      if(id=="" || ArraySize(m_ids)!=QEDGE_HASH_SLOTS) return -1;
      int slot=HashStart(id);
      for(int probe=0;probe<QEDGE_HASH_SLOTS;probe++)
        {
         if(m_ids[slot]=="") return -1;
         if(m_ids[slot]==id) return slot;
         slot++; if(slot>=QEDGE_HASH_SLOTS) slot=0;
        }
      return -1;
     }

   int FindPending(const string id) const
     {
      for(int i=0;i<m_pending_count;i++) if(m_pending[i].setup_id==id) return i;
      return -1;
     }

   int ReserveId(const string id,const bool pending)
     {
      if(id=="" || ArraySize(m_ids)!=QEDGE_HASH_SLOTS || ArraySize(m_id_pending)!=QEDGE_HASH_SLOTS ||
         m_record_count>=QEDGE_MAX_RECORDS || FindId(id)>=0) return -1;
      int slot=HashStart(id);
      for(int probe=0;probe<QEDGE_HASH_SLOTS;probe++)
        {
         if(m_ids[slot]=="")
           { m_ids[slot]=id; m_id_pending[slot]=pending; m_record_count++; return slot; }
         slot++; if(slot>=QEDGE_HASH_SLOTS) slot=0;
        }
      return -1;
     }

   int FindKey(const string key) const
     {
      for(int i=0;i<m_key_count;i++) if(m_keys[i].key==key) return i;
      return -1;
     }

   bool AddAggregate(const SEdgeOutcomeRecord &r)
     {
      int k=FindKey(r.strategy_key);
      if(k<0)
        {
         if(m_key_count>=QEDGE_MAX_KEYS) return false;
         k=m_key_count++;
         m_keys[k].key=r.strategy_key; m_keys[k].n=0; m_keys[k].wins=0;
         m_keys[k].losses=0; m_keys[k].breakeven=0; m_keys[k].ambiguous=0; m_keys[k].sum_r=0.0;
        }
      if(r.outcome==QEDGE_AMBIGUOUS) { m_keys[k].ambiguous++; return true; }
      m_keys[k].n++; m_keys[k].sum_r+=r.outcome_r;
      if(r.outcome==QEDGE_WIN) m_keys[k].wins++;
      else if(r.outcome==QEDGE_LOSS) m_keys[k].losses++;
      else if(r.outcome==QEDGE_BREAKEVEN) m_keys[k].breakeven++;
      return true;
     }

   bool SameSetup(const SEdgeOutcomeRecord &a,const SEdgeOutcomeRecord &b) const
     {
      return a.setup_id==b.setup_id && a.strategy_key==b.strategy_key &&
             a.symbol==b.symbol && a.timeframe==b.timeframe &&
             a.entry_time==b.entry_time && a.direction==b.direction &&
             a.entry==b.entry && a.stop==b.stop && a.target==b.target &&
             a.spread_points==b.spread_points;
     }

   bool AddPendingMemory(const SEdgeOutcomeRecord &r)
     {
      if(m_pending_count>=QSMC_STATS_MAX_ROWS) return false;
      int slot=ReserveId(r.setup_id,true);
      if(slot<0) return false;
      m_pending[m_pending_count]=r; m_pending_count++;
      return true;
     }

   bool AddCompletedMemory(const SEdgeOutcomeRecord &r)
     {
      int slot=FindId(r.setup_id);
      if(slot>=0) return false;
      slot=ReserveId(r.setup_id,false);
      if(slot<0) return false;
      return AddAggregate(r);
     }

   bool FinalizePendingMemory(const SEdgeOutcomeRecord &r)
     {
      int slot=FindId(r.setup_id);
      if(slot>=0 && !m_id_pending[slot]) return false;
      if(slot<0)
        {
         slot=ReserveId(r.setup_id,false);
         if(slot<0) return false;
        }
      else
        {
         int p=FindPending(r.setup_id);
         if(p<0 || !SameSetup(m_pending[p],r)) return false;
         m_id_pending[slot]=false;
         for(int i=p;i<m_pending_count-1;i++) m_pending[i]=m_pending[i+1];
         m_pending_count--;
        }
      return AddAggregate(r);
     }

   bool ValidateRecord(const SEdgeOutcomeRecord &r) const
     {
      if((r.record_type!="PENDING" && r.record_type!="OUTCOME") ||
         r.setup_id=="" || r.strategy_key=="" || r.symbol=="" || r.timeframe=="" ||
         r.entry_time<=0 || (r.direction!=1 && r.direction!=-1) ||
         !MathIsValidNumber(r.entry) || !MathIsValidNumber(r.stop) ||
         !MathIsValidNumber(r.target) || !MathIsValidNumber(r.outcome_r) ||
         !MathIsValidNumber(r.mfe_r) || !MathIsValidNumber(r.mae_r) ||
         !MathIsValidNumber(r.spread_points) || r.spread_points<0.0 ||
         r.mfe_r<0.0 || r.mae_r>0.0 || r.resolution=="") return false;
      if(r.record_type=="PENDING")
        {
         if(r.outcome!=0 || r.resolution!="PENDING" || r.outcome_r!=0.0 ||
            r.mfe_r!=0.0 || r.mae_r!=0.0) return false;
        }
      else if(r.outcome<QEDGE_WIN || r.outcome>QEDGE_AMBIGUOUS || r.resolution=="PENDING")
         return false;
      double risk=(r.direction>0 ? r.entry-r.stop : r.stop-r.entry);
      double reward=(r.direction>0 ? r.target-r.entry : r.entry-r.target);
      if(!(risk>0.0) || !(reward>0.0) || !MathIsValidNumber(risk) || !MathIsValidNumber(reward)) return false;
      return true;
     }

   bool ReadRecord(SEdgeOutcomeRecord &r)
     {
      string f[17];
      for(int i=0;i<17;i++)
        {
         if(FileIsEnding(m_handle)) return false;
         f[i]=FileReadString(m_handle);
         if(f[i]=="") return false;
        }
      if(f[0]!=IntegerToString(QEDGE_SCHEMA_VERSION) ||
         (f[1]!="PENDING" && f[1]!="OUTCOME")) return false;
      r.record_type=f[1];
      r.setup_id=f[2]; r.strategy_key=f[3]; r.symbol=f[4]; r.timeframe=f[5];
      r.entry_time=StringToTime(f[6]);
      long direction_value=StringToInteger(f[7]);
      r.direction=(int)direction_value;
      if(direction_value!=r.direction || IntegerToString(direction_value)!=f[7] ||
         r.entry_time<=0 || TimeToString(r.entry_time,TIME_DATE|TIME_SECONDS)!=f[6]) return false;
      if(!ParseDouble(f[8],r.entry) || !ParseDouble(f[9],r.stop) ||
         !ParseDouble(f[10],r.target) || !ParseDouble(f[12],r.outcome_r) ||
         !ParseDouble(f[13],r.mfe_r) || !ParseDouble(f[14],r.mae_r) ||
         !ParseDouble(f[15],r.spread_points)) return false;
      long outcome_value=StringToInteger(f[11]);
      r.outcome=(int)outcome_value;
      if(outcome_value!=r.outcome || IntegerToString(outcome_value)!=f[11]) return false;
      r.resolution=f[16];
      if(r.symbol!=m_expected_symbol || r.timeframe!=m_expected_timeframe) return false;
      return ValidateRecord(r);
     }

   bool WriteHeader()
     {
      uint n=FileWrite(m_handle,"schema_version","record_type","setup_id","strategy_key",
                       "symbol","timeframe","entry_time","direction","entry","stop",
                       "target","outcome","outcome_r","mfe_r","mae_r","spread_points","resolution");
      if(n==0) return false;
      FileFlush(m_handle);
      return true;
     }

   bool WriteRecord(const SEdgeOutcomeRecord &r)
     {
      uint n=FileWrite(m_handle,IntegerToString(QEDGE_SCHEMA_VERSION),r.record_type,r.setup_id,
                       r.strategy_key,r.symbol,r.timeframe,
                       TimeToString(r.entry_time,TIME_DATE|TIME_SECONDS),
                       IntegerToString(r.direction),DoubleToString(r.entry,10),
                       DoubleToString(r.stop,10),DoubleToString(r.target,10),
                       IntegerToString(r.outcome),DoubleToString(r.outcome_r,8),
                       DoubleToString(r.mfe_r,8),DoubleToString(r.mae_r,8),
                       DoubleToString(r.spread_points,4),r.resolution);
      if(n==0) return false;
      // Outcomes are rare relative to per-bar processing; flush each complete
      // record before marking it counted so a restart cannot replay it twice.
      FileFlush(m_handle);
      m_flush_pending=0;
      return true;
     }

   void MarkUntrusted(const string why)
     {
      m_trusted=false; m_write_enabled=false; m_parse_errors++;
      Print("[QSMC_EDGE] file untrusted: ",m_file," | ",why);
     }

   bool ClearMemory()
     {
      m_record_count=0; m_key_count=0; m_pending_count=0;
      if(ArraySize(m_ids)!=QEDGE_HASH_SLOTS && ArrayResize(m_ids,QEDGE_HASH_SLOTS)!=QEDGE_HASH_SLOTS)
        { m_trusted=false; return false; }
      if(ArraySize(m_id_pending)!=QEDGE_HASH_SLOTS && ArrayResize(m_id_pending,QEDGE_HASH_SLOTS)!=QEDGE_HASH_SLOTS)
        { m_trusted=false; return false; }
      for(int i=0;i<QEDGE_HASH_SLOTS;i++) { m_ids[i]=""; m_id_pending[i]=false; }
      for(int i=0;i<QEDGE_MAX_KEYS;i++)
        { m_keys[i].key=""; m_keys[i].n=0; m_keys[i].wins=0; m_keys[i].losses=0;
          m_keys[i].breakeven=0; m_keys[i].ambiguous=0; m_keys[i].sum_r=0.0; }
      return true;
     }

public:
                     CEdgeBook()
     { m_handle=INVALID_HANDLE; m_file=""; m_open=false; m_trusted=true;
       m_write_enabled=false; m_common=false; m_min_sample=30; m_record_count=0;
       m_expected_symbol=""; m_expected_timeframe="";
       m_key_count=0; m_pending_count=0; m_flush_pending=0; m_parse_errors=0; m_duplicates=0; }

                    ~CEdgeBook() { Close(); }

   bool              Trusted() const { return m_trusted; }
   int               Records() const { return m_record_count; }
   int               PendingCount() const { return m_pending_count; }
   bool              PendingAt(const int index,SEdgeOutcomeRecord &out) const
     { if(index<0 || index>=m_pending_count) return false; out=m_pending[index]; return true; }
   int               ParseErrors() const { return m_parse_errors; }
   int               Duplicates() const { return m_duplicates; }
   string            FileName() const { return m_file; }
   bool              Seen(const string setup_id) const { return FindId(setup_id)>=0; }

   bool              Open(const string symbol,const ENUM_TIMEFRAMES tf,
                          const int min_sample,const bool common=false)
     {
      Close();
      if(!ClearMemory()) { m_trusted=false; m_write_enabled=false; return false; }
      m_trusted=true; m_write_enabled=false; m_common=common;
      m_min_sample=(int)MathMax(1,min_sample); m_parse_errors=0; m_duplicates=0;
      m_expected_symbol=symbol; m_expected_timeframe=QSMC_TFName(tf);
      string safe_symbol=symbol;
      for(int i=0;i<StringLen(safe_symbol);i++)
        {
         ushort c=StringGetCharacter(safe_symbol,i);
         if(!((c>='A' && c<='Z') || (c>='a' && c<='z') || (c>='0' && c<='9') || c=='_' || c=='-'))
            StringSetCharacter(safe_symbol,i,'_');
        }
      m_file="QSMC_EDGE_V1_"+safe_symbol+"_"+QSMC_TFName(tf)+".csv";
      int flags=FILE_CSV|FILE_READ|FILE_WRITE|FILE_SHARE_READ|FILE_ANSI;
      if(common) flags|=FILE_COMMON;
      m_handle=FileOpen(m_file,flags,',');
      if(m_handle==INVALID_HANDLE)
        {
         Print("[QSMC_EDGE] open failed: ",m_file," err=",GetLastError());
         m_open=false; m_trusted=false; return false;
        }
      m_open=true;
      if(FileSize(m_handle)==0)
        {
         if(!WriteHeader()) { MarkUntrusted("could not write schema header"); return false; }
         m_write_enabled=true;
        }
      else
        {
         if(!FileSeek(m_handle,0,SEEK_SET))
           { MarkUntrusted("could not seek to schema header"); return false; }
         for(int i=0;i<17;i++)
           {
            if(FileIsEnding(m_handle) || FileReadString(m_handle)!=HeaderField(i))
              { MarkUntrusted("header mismatch or incomplete header"); return false; }
           }
         while(!FileIsEnding(m_handle))
           {
            SEdgeOutcomeRecord r;
            if(!ReadRecord(r)) { MarkUntrusted("malformed or partially written outcome row"); break; }
            int slot=FindId(r.setup_id);
            if(r.record_type=="PENDING")
              {
               if(slot>=0 || !AddPendingMemory(r))
                 { m_duplicates++; MarkUntrusted("duplicate or excess pending setup_id"); break; }
              }
            else if(slot>=0)
              {
               if(!m_id_pending[slot] || !FinalizePendingMemory(r))
                 { m_duplicates++; MarkUntrusted("duplicate completed setup_id"); break; }
              }
            else if(!AddCompletedMemory(r))
              { MarkUntrusted("edge-book capacity exceeded"); break; }
           }
         if(m_trusted) m_write_enabled=true;
        }
      if(!FileSeek(m_handle,0,SEEK_END))
        { MarkUntrusted("could not seek to append position"); return false; }
      if(!m_trusted) Print("[QSMC_EDGE] persisted statistics withheld; repair/archive the malformed file before reuse");
      return m_trusted;
     }

   bool              ResetMemory(const int min_sample)
     {
      Close();
      if(!ClearMemory()) { m_trusted=false; m_write_enabled=false; return false; }
      m_trusted=true; m_write_enabled=false; m_min_sample=(int)MathMax(1,min_sample);
      m_parse_errors=0; m_duplicates=0; m_file="";
      return true;
     }

   void              Close()
     {
      if(m_open && m_handle!=INVALID_HANDLE)
        {
         if(m_flush_pending>0) FileFlush(m_handle);
         FileClose(m_handle);
        }
      m_handle=INVALID_HANDLE; m_open=false; m_flush_pending=0;
     }

   bool              RecordPending(const SEdgeOutcomeRecord &r)
     {
      if(r.record_type!="PENDING" || !ValidateRecord(r)) return false;
      if(FindId(r.setup_id)>=0) { m_duplicates++; return false; }
      if(m_pending_count>=QSMC_STATS_MAX_ROWS || m_record_count>=QEDGE_MAX_RECORDS)
        { m_trusted=false; m_write_enabled=false; return false; }
      if(m_write_enabled && m_handle!=INVALID_HANDLE && !WriteRecord(r))
         MarkUntrusted("pending setup write failed");
      if(!AddPendingMemory(r)) { m_trusted=false; m_write_enabled=false; return false; }
      return true;
     }

   bool              RecordOutcome(const SEdgeOutcomeRecord &r)
     {
      if(r.record_type!="OUTCOME" || !ValidateRecord(r)) return false;
      int slot=FindId(r.setup_id);
      if(slot>=0 && !m_id_pending[slot]) { m_duplicates++; return false; }
      if(slot<0 && m_record_count>=QEDGE_MAX_RECORDS)
        { m_trusted=false; m_write_enabled=false; return false; }
      if(m_write_enabled && m_handle!=INVALID_HANDLE && !WriteRecord(r))
         MarkUntrusted("outcome write failed");
      bool stored=(slot>=0 ? FinalizePendingMemory(r) : AddCompletedMemory(r));
      if(!stored) { m_trusted=false; m_write_enabled=false; return false; }
      return true;
     }

   string            StrategySummary(const string key) const
     {
      if(!m_trusted) return "EdgeBook UNTRUSTED; no persisted rate shown";
      int i=FindKey(key);
      if(i<0) return key+" | n=0";
      string s=key+" | n="+IntegerToString(m_keys[i].n)+
               " | wins/loss/BE/ambiguous="+IntegerToString(m_keys[i].wins)+"/"+
               IntegerToString(m_keys[i].losses)+"/"+IntegerToString(m_keys[i].breakeven)+"/"+
               IntegerToString(m_keys[i].ambiguous);
      if(m_keys[i].n<m_min_sample)
         return s+" | insufficient sample; no rate shown";
      double lo,hi;
      int decisions=m_keys[i].wins+m_keys[i].losses+m_keys[i].breakeven;
      if(decisions<=0 || !QSMC_WilsonInterval(m_keys[i].wins,decisions,1.96,lo,hi))
         return s+" | Wilson interval unavailable";
      s+=" | observed win-rate "+DoubleToString(100.0*(double)m_keys[i].wins/(double)decisions,1)+"%"+
         " Wilson95 ["+DoubleToString(100.0*lo,1)+"%, "+DoubleToString(100.0*hi,1)+"%]"+
         " | avg R "+DoubleToString(m_keys[i].sum_r/(double)m_keys[i].n,2)+
         " (rate uncertainty only; not profitability forecast)";
      return s;
     }

   string            Summary() const
     {
      if(!m_trusted) return "EdgeBook UNTRUSTED | parse errors="+IntegerToString(m_parse_errors)+
                                  " duplicates="+IntegerToString(m_duplicates)+" | no persisted rate shown";
      string s="EdgeBook records="+IntegerToString(m_record_count)+" keys="+IntegerToString(m_key_count)+
               " duplicate attempts="+IntegerToString(m_duplicates)+
               " file="+(m_open?m_file:"memory only");
      for(int i=0;i<m_key_count;i++) s+=" || "+StrategySummary(m_keys[i].key);
      return s;
     }
  };


//+------------------------------------------------------------------+
class CStatsLogger
  {
private:
   int               m_handle;
   string            m_file;
   bool              m_open;
   bool              m_tracking;
   int               m_row_id;
   int               m_written;

   SSigRow           m_rows[QSMC_STATS_MAX_ROWS];
   CEdgeBook         m_edgebook;
   int               m_row_count;
   int               m_dropped_open_rows;
   int               m_edge_errors;
   bool              m_pending_restored;

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

   static string     SetupId(const SSignalCandidate &c,const SGateCtx &ctx)
     {
      return StringFormat("%s|%s|%I64d|%d|%d|%s",ctx.symbol,QSMC_TFName(ctx.tf),
                          (long)c.bar_time,(int)c.source,c.dir,c.zone_id);
     }

   static string     StrategyKey(const SSignalCandidate &c,const SGateCtx &ctx)
     {
      return "QSMC_V1|"+QSMC_SourceName(c.source)+"|"+QSMC_TFName(ctx.tf)+"|"+
             (c.dir>0?"BUY":"SELL")+"|"+QSMC_RoleName(c.zone_role);
     }

   bool              PendingSetup(const string setup_id) const
     {
      for(int i=0;i<m_row_count;i++)
         if(m_rows[i].open && m_rows[i].setup_id==setup_id) return true;
      return false;
     }

   bool              WriteSignalHeader()
     {
      uint n=FileWrite(m_handle,"schema_version","record_type","seq","signal_time","symbol","tf",
                       "source","state","dir","setup_id","zone_id","zone_lo","zone_hi",
                       "zone_role","zone_strength","evidence","evidence_count","entry","sl","tp1",
                       "rr","room_atr","distance_atr","score","published","reason","blocked_by","extra");
      if(n==0) return false;
      FileFlush(m_handle);
      return true;
     }

   bool              ValidateSignalHeader()
     {
      string h[28];
      h[0]="schema_version"; h[1]="record_type"; h[2]="seq"; h[3]="signal_time";
      h[4]="symbol"; h[5]="tf"; h[6]="source"; h[7]="state"; h[8]="dir";
      h[9]="setup_id"; h[10]="zone_id"; h[11]="zone_lo"; h[12]="zone_hi";
      h[13]="zone_role"; h[14]="zone_strength"; h[15]="evidence"; h[16]="evidence_count";
      h[17]="entry"; h[18]="sl"; h[19]="tp1"; h[20]="rr"; h[21]="room_atr";
      h[22]="distance_atr"; h[23]="score"; h[24]="published"; h[25]="reason";
      h[26]="blocked_by"; h[27]="extra";
      if(!FileSeek(m_handle,0,SEEK_SET)) return false;
      for(int i=0;i<28;i++) if(FileIsEnding(m_handle) || FileReadString(m_handle)!=h[i]) return false;
      while(!FileIsEnding(m_handle))
        {
         if(FileIsEnding(m_handle)) break;
         string version=FileReadString(m_handle);
         if(FileIsEnding(m_handle)) return false;
         string kind=FileReadString(m_handle);
         if(version!="2" || kind!="SIGNAL" || FileIsEnding(m_handle)) return false;
         string seq_text=FileReadString(m_handle);
         long seq=StringToInteger(seq_text);
         if(seq_text=="" || IntegerToString(seq)!=seq_text || seq<0) return false;
         if(seq>m_row_id) m_row_id=(int)seq;
         for(int f=3;f<28;f++)
           {
            if(FileIsEnding(m_handle)) return false;
            string cell=FileReadString(m_handle);
           }
        }
      return true;
     }

   bool              ProcessOutcomeBar(SSigRow &r,const CBarSeries &bars,
                                       const int bar_index,bool &resolved)
     {
      resolved=false;
      datetime bar_time=bars.T(bar_index);
      if(!r.open || bar_time<=r.signal_time || bar_time<=r.last_advanced_time) return true;
      double h=bars.H(bar_index), l=bars.L(bar_index), close=bars.C(bar_index);
      if(!MathIsValidNumber(h) || !MathIsValidNumber(l) || !MathIsValidNumber(close) || h<l)
         return false;
      if(!(r.risk>0.0) || !MathIsValidNumber(r.risk))
        { r.open=false; r.result=QRES_STALE; resolved=true; return true; }

      bool hit_tp=(r.dir>0 ? h>=r.tp1 : l<=r.tp1);
      bool hit_sl=(r.dir>0 ? l<=r.sl  : h>=r.sl);
      r.bars_held++;
      // Exit-bar ordering is unknown from OHLC. Exclude that bar from MFE/MAE.
      if(!hit_tp && !hit_sl)
        {
         double fav,adv;
         if(r.dir>0){ fav=(h-r.entry)/r.risk; adv=(l-r.entry)/r.risk; }
         else       { fav=(r.entry-l)/r.risk; adv=(r.entry-h)/r.risk; }
         if(fav>r.mfe_r) r.mfe_r=fav;
         if(adv<r.mae_r) r.mae_r=adv;
        }
      r.last_advanced_time=bar_time;

      string resolution="";
      if(hit_sl && hit_tp) { r.open=false; r.result=QRES_SL; resolution="BOTH_TOUCH_STOP_FIRST"; }
      else if(hit_sl)      { r.open=false; r.result=QRES_SL; resolution="STOP_TOUCHED"; }
      else if(hit_tp)      { r.open=false; r.result=QRES_TP1; resolution="TARGET_TOUCHED"; }
      else if(r.bars_held>=QSMC_STATS_MAX_BARS)
        { r.open=false; r.result=QRES_TIMEOUT; resolution="TIMEOUT_CLOSE_R"; }
      if(r.open) return true;

      double outcome_r=0.0;
      int outcome=QEDGE_AMBIGUOUS;
      if(r.result==QRES_TP1)
        { outcome_r=(double)r.dir*(r.tp1-r.entry)/r.risk; outcome=QEDGE_WIN; }
      else if(r.result==QRES_SL)
        { outcome_r=-1.0; outcome=QEDGE_LOSS; }
      else if(r.result==QRES_TIMEOUT)
        {
         outcome_r=(double)r.dir*(close-r.entry)/r.risk;
         if(outcome_r>0.05) outcome=QEDGE_WIN;
         else if(outcome_r< -0.05) outcome=QEDGE_LOSS;
         else outcome=QEDGE_BREAKEVEN;
        }

      SEdgeOutcomeRecord edge;
      edge.record_type="OUTCOME"; edge.setup_id=r.setup_id;
      edge.strategy_key=r.strategy_key; edge.symbol=r.symbol; edge.timeframe=r.timeframe;
      edge.entry_time=r.signal_time; edge.direction=r.dir;
      edge.entry=r.entry; edge.stop=r.sl; edge.target=r.tp1;
      edge.outcome=outcome; edge.outcome_r=outcome_r;
      edge.mfe_r=r.mfe_r; edge.mae_r=r.mae_r;
      edge.spread_points=r.spread_points; edge.resolution=resolution;
      if(m_edgebook.RecordOutcome(edge))
        {
         if(r.result==QRES_TP1) m_n_tp1++;
         else if(r.result==QRES_SL) m_n_sl++;
         else m_n_timeout++;
         m_n++; m_sum_mfe+=r.mfe_r; m_sum_mae+=r.mae_r;
         m_sum_bars+=(double)r.bars_held;
        }
      else m_edge_errors++;
      resolved=true;
      return true;
     }

   void              RecordRestartGap(const SEdgeOutcomeRecord &pending)
     {
      SEdgeOutcomeRecord edge=pending;
      edge.record_type="OUTCOME"; edge.outcome=QEDGE_AMBIGUOUS;
      edge.outcome_r=0.0; edge.mfe_r=0.0; edge.mae_r=0.0;
      edge.resolution="RESTART_HISTORY_GAP";
      if(!m_edgebook.RecordOutcome(edge)) m_edge_errors++;
     }

   void              RestorePendingRows(const CBarSeries &bars,const int closed_index)
     {
      if(m_pending_restored || !m_edgebook.Trusted()) return;
      bool complete=true;
      datetime latest=bars.T(closed_index);
      int pending_n=m_edgebook.PendingCount();
      // Reverse traversal allows completed records to be removed from the
      // EdgeBook's pending array without skipping earlier entries.
      for(int p=pending_n-1;p>=0;p--)
        {
         SEdgeOutcomeRecord item;
         if(!m_edgebook.PendingAt(p,item)) continue;
         if(PendingSetup(item.setup_id)) continue;
         if(m_row_count>=QSMC_STATS_MAX_ROWS) { complete=false; break; }
         int signal_index=bars.IndexOfTime(item.entry_time);
         if(signal_index<0)
           {
            if(item.entry_time>latest) { complete=false; continue; }
            // History no longer contains the setup bar; preserve the ID as an
            // ambiguous outcome rather than inventing a stop/target result.
            RecordRestartGap(item);
            continue;
           }
         if(signal_index>closed_index) { complete=false; continue; }

         SSigRow r;
         r.open=true; r.setup_id=item.setup_id; r.strategy_key=item.strategy_key;
         r.symbol=item.symbol; r.timeframe=item.timeframe; r.spread_points=item.spread_points;
         r.signal_time=item.entry_time; r.last_advanced_time=item.entry_time;
         r.dir=item.direction; r.state=(int)SIG_WATCH; r.source=SRC_NONE;
         r.zone_id=""; r.entry=item.entry; r.sl=item.stop; r.tp1=item.target;
         r.risk=(r.dir>0 ? r.entry-r.sl : r.sl-r.entry);
         r.mfe_r=0.0; r.mae_r=0.0; r.bars_held=0; r.result=QRES_OPEN;
         bool resolved=false;
         for(int b=signal_index+1;b<=closed_index && r.open;b++)
           {
            bool processed=ProcessOutcomeBar(r,bars,b,resolved);
            if(!processed)
              { RecordRestartGap(item); r.open=false; break; }
           }
         if(r.open)
           {
            if(m_row_count<QSMC_STATS_MAX_ROWS) m_rows[m_row_count++]=r;
            else complete=false;
           }
        }
      m_pending_restored=complete;
     }

public:
                     CStatsLogger()
     { m_handle=INVALID_HANDLE; m_file=""; m_open=false; m_tracking=false; m_row_id=0; m_written=0;
       m_row_count=0; m_n=0; m_n_tp1=0; m_n_sl=0; m_n_timeout=0;
       m_sum_mfe=0.0; m_sum_mae=0.0; m_sum_bars=0.0; m_min_sample=30;
       m_dropped_open_rows=0; m_edge_errors=0; m_pending_restored=false; }

                    ~CStatsLogger() { Close(); }

   int               MinSample() const { return m_min_sample; }
   int               Rows() const { return m_row_count; }
   int               Closed() const { return m_n; }
   string            FileName() const { return m_file; }
   int               Written() const { return m_written; }
   string            EdgeSummary() const { return m_edgebook.Summary(); }
   string            EdgeStrategySummary(const string key) const { return m_edgebook.StrategySummary(key); }

   //------------------------------------------------------------------
   bool              Open(const string symbol,const ENUM_TIMEFRAMES tf,const int min_sample,
                          const bool csv_enabled=true)
     {
      Close();
      m_min_sample=(int)MathMax(1,min_sample);
      m_tracking=true;
      m_row_id=0; m_written=0; m_row_count=0;
      m_n=0; m_n_tp1=0; m_n_sl=0; m_n_timeout=0;
      m_sum_mfe=0.0; m_sum_mae=0.0; m_sum_bars=0.0;
      m_dropped_open_rows=0; m_edge_errors=0; m_pending_restored=false;
      if(!m_edgebook.ResetMemory(m_min_sample))
        { m_tracking=false; m_edge_errors++; Print("[QSMC_EDGE] memory index allocation failed"); return false; }
      if(!csv_enabled) return true; // in-memory outcome tracking only; no files created

      MqlDateTime dt;
      TimeToStruct(TimeCurrent(),dt);
      // Versioned filename avoids silently treating legacy/unversioned CSV as V2.
      m_file="QSMC_ARB_V2_"+symbol+"_"+QSMC_TFName(tf)+"_"+
             StringFormat("%04d%02d%02d",dt.year,dt.mon,dt.day)+".csv";
      bool exists=FileIsExist(m_file);
      int flags=FILE_CSV|FILE_SHARE_READ|FILE_ANSI;
      flags|=(exists ? (FILE_READ|FILE_WRITE) : FILE_WRITE);
      m_handle=FileOpen(m_file,flags,',');
      if(m_handle==INVALID_HANDLE)
        {
         Print("[QSMC_ARB] CSV open failed: ",m_file," err=",GetLastError());
         m_open=false;
         bool edge_ok=m_edgebook.Open(symbol,tf,m_min_sample,false);
         if(!edge_ok) Print("[QSMC_EDGE] persistent book unavailable; stored statistics are not trusted");
         return false;
        }
      m_open=true;
      if(FileSize(m_handle)==0)
        {
         if(!WriteSignalHeader())
           { Print("[QSMC_ARB] CSV header write failed: ",m_file," err=",GetLastError()); FileClose(m_handle); m_handle=INVALID_HANDLE; m_open=false; }
        }
      else if(!ValidateSignalHeader())
        {
         Print("[QSMC_ARB] CSV schema/header invalid; refusing append: ",m_file);
         FileClose(m_handle); m_handle=INVALID_HANDLE; m_open=false;
        }
      if(m_open && !FileSeek(m_handle,0,SEEK_END))
        { Print("[QSMC_ARB] CSV append seek failed: ",m_file," err=",GetLastError()); FileClose(m_handle); m_handle=INVALID_HANDLE; m_open=false; }
      bool edge_open=m_edgebook.Open(symbol,tf,m_min_sample,false);
      if(!edge_open) Print("[QSMC_EDGE] persistent book unavailable; stored statistics are not trusted");
      return m_open;
     }

   void              Close()
     {
      m_edgebook.Close();
      if(m_open && m_handle!=INVALID_HANDLE) FileClose(m_handle);
      m_handle=INVALID_HANDLE;
      m_open=false;
      m_tracking=false;
     }

   //------------------------------------------------------------------
   void              Log(const SSignalCandidate &c,const SGateCtx &ctx,const bool published)
     {
      if(!m_tracking) return;
      string setup_id=SetupId(c,ctx);
      if(m_open && m_handle!=INVALID_HANDLE)
        {
      m_row_id++;
      uint written=FileWrite(m_handle,
                "2","SIGNAL",
                IntegerToString(m_row_id),
                TimeToString(c.bar_time,TIME_DATE|TIME_MINUTES),
                ctx.symbol,
                QSMC_TFName(ctx.tf),
                QSMC_SourceName(c.source),
                QSMC_StateName(c.state),
                IntegerToString(c.dir),
                setup_id,
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
                c.reject_text,
                c.extra);
      if(written==0)
        {
         m_edge_errors++;
         Print("[QSMC_ARB] signal CSV write failed: ",m_file," err=",GetLastError());
         FileClose(m_handle); m_handle=INVALID_HANDLE; m_open=false;
        }
      else { FileFlush(m_handle); m_written++; }
        }

      //--- Open each setup once. Never evict an unresolved record: capacity
      //--- exhaustion is reported and the new outcome is not silently lost.
      if(published)
        {
         if(PendingSetup(setup_id) || m_edgebook.Seen(setup_id))
           { m_edge_errors++; return; }
         if(m_row_count>=QSMC_STATS_MAX_ROWS)
           { m_dropped_open_rows++; return; }
         SSigRow r;
         r.open=true; r.setup_id=setup_id;
         r.strategy_key=StrategyKey(c,ctx); r.symbol=ctx.symbol;
         r.timeframe=QSMC_TFName(ctx.tf); r.spread_points=ctx.spread_points;
         r.signal_time=c.bar_time; r.last_advanced_time=c.bar_time;
         r.dir=c.dir; r.state=c.state;
         r.source=c.source; r.zone_id=c.zone_id;
         r.entry=c.entry; r.sl=c.sl; r.tp1=c.tp1;
         r.risk=(c.dir>0 ? c.entry-c.sl : c.sl-c.entry);
         r.mfe_r=0.0; r.mae_r=0.0; r.bars_held=0;
         r.result=QRES_OPEN;
         if(!(r.risk>0.0) || !MathIsValidNumber(r.risk))
           { m_edge_errors++; return; }
         SEdgeOutcomeRecord pending;
         pending.record_type="PENDING"; pending.setup_id=r.setup_id;
         pending.strategy_key=r.strategy_key; pending.symbol=r.symbol;
         pending.timeframe=r.timeframe; pending.entry_time=r.signal_time;
         pending.direction=r.dir; pending.entry=r.entry; pending.stop=r.sl; pending.target=r.tp1;
         pending.outcome=0; pending.outcome_r=0.0; pending.mfe_r=0.0; pending.mae_r=0.0;
         pending.spread_points=r.spread_points; pending.resolution="PENDING";
         if(!m_edgebook.RecordPending(pending)) m_edge_errors++;
         m_rows[m_row_count]=r;
         m_row_count++;
        }
     }

   //------------------------------------------------------------------
   // Advance every open row with one newly CLOSED bar.
   // `closed_index` is the index of that bar in the CHART series.
   // NO LOOK-AHEAD: timestamps must be strictly later than the signal and the
   // last processed closed bar (indices are stable-window offsets, not clocks).
   //------------------------------------------------------------------
   void              Advance(const CBarSeries &bars,const int closed_index)
     {
      if(!bars.Ready() || closed_index<0 || closed_index>bars.ClosedIndex()) return;
      double h=bars.H(closed_index), l=bars.L(closed_index), close=bars.C(closed_index);
      if(!MathIsValidNumber(h) || !MathIsValidNumber(l) || !MathIsValidNumber(close) || h<l) return;
      RestorePendingRows(bars,closed_index);
      if(m_row_count<=0) return;

      for(int i=m_row_count-1;i>=0;i--)
        {
         SSigRow r=m_rows[i];
         bool resolved=false;
         if(!ProcessOutcomeBar(r,bars,closed_index,resolved))
           { m_edge_errors++; m_rows[i]=r; continue; }
         if(resolved)
           {
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
      string s="outcomes recorded="+IntegerToString(m_n_tp1+m_n_sl+m_n_timeout);
      s+=" | rows written="+IntegerToString(m_written);
      s+=" | open="+IntegerToString(m_row_count);
      s+=" | n="+IntegerToString(m_n);
      s+=" | dropped-open="+IntegerToString(m_dropped_open_rows);
      s+=" | edge-errors="+IntegerToString(m_edge_errors);
      if(m_n<m_min_sample)
        {
         s+=" -> insufficient sample (need "+IntegerToString(m_min_sample)+
            ") - NO rate shown";
         return s+" | "+m_edgebook.Summary();
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
      s+=" | "+m_edgebook.Summary();
      return s;
     }
  };

#endif
//+------------------------------------------------------------------+
