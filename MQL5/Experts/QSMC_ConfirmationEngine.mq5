//+------------------------------------------------------------------+
//| QSMC_ConfirmationEngine.mq5                                      |
//| Zone-centric confirmation score engine. Dry-run by default.      |
//| Adds a new order boundary; QSMC_AutoTrader.mq5 is unchanged.     |
//+------------------------------------------------------------------+
#property copyright "Arena"
#property version   "6.625"
#property description "Confirmation-score zone engine, UTC clock, replayable logs"

#include <Trade/Trade.mqh>

#define CE_STATE_DETECTED          0
#define CE_STATE_VALIDATED         1
#define CE_STATE_TESTED_MITIGATED  2
#define CE_STATE_TRIGGERED         3
#define CE_STATE_EXPIRED           4
#define CE_STATE_INVALIDATED       5

#define CE_SESSION_ASIA            0
#define CE_SESSION_LONDON          1
#define CE_SESSION_NEWYORK         2
#define CE_SESSION_OFFPEAK         3

#define CE_MODE_RETEST             0
#define CE_MODE_MOMENTUM           1
#define CE_MODE_REVERSAL           2

#define CE_KIND_FVG                1
#define CE_KIND_OB                 2
#define CE_KIND_OB_FVG             3

#define CE_MAX_ZONES               256
#define CE_HASH_BUCKETS            512

// ---------------------------------------------------------------- inputs
input bool   InpMasterEnable                 = true;   // master evaluation switch
input bool   InpDryRun                      = true;    // demo/dry-run default ON
input bool   InpAllowLiveOrders             = false;   // explicit opt-in for orders
input bool   InpAllowRealTrading            = false;   // REAL is always refused
input bool   InpKillSwitch                  = false;   // operator kill switch
input int    InpMagic                       = 20261125; // order magic
input int    InpDeviationPoints             = 20;     // CTrade deviation
input string InpTradeComment                = "CE";    // order comment
input int    InpMaxOrderRetries             = 2;      // transient retcode retries
input bool   InpUseLimitOrders              = true;   // retest uses limit orders

input int    InpBrokerUtcOffsetWinterMinutes = 120;   // server = UTC + winter
input int    InpBrokerUtcOffsetSummerMinutes = 180;   // server = UTC + summer
input bool   InpBrokerUsesEuDst              = true;   // EU DST broker offset
input bool   InpRequireSessionPermission     = true;   // session entry permission
input bool   InpAllowAsiaEntries             = false;  // Asia entries
input bool   InpAllowOffPeakEntries          = false;  // off-peak entries

input int    InpTierA                        = 75;     // full risk at or above
input int    InpTierB                        = 55;     // reduced risk at or above
input int    InpMinHtfPoints                 = 3;      // HTF component floor
input double InpTierBRiskScale               = 0.50;   // B-tier risk scale
input double InpHtfCounterRiskScale          = 0.60;   // counter-H4 risk scale
input double InpRiskPercent                  = 0.25;   // equity risk per trade
input double InpMinLots                      = 0.01;   // minimum lots
input double InpMaxLots                      = 1.00;   // maximum lots
input double InpLotStep                      = 0.01;   // lot step
input int    InpMinStopPoints                = 20;     // minimum stop points
input double InpAtrBuffer                    = 0.30;   // SL ATR buffer
input double InpInvalidationATR              = 1.00;   // invalidation beyond zone
input double InpTpRRMultiple                 = 2.00;   // final TP in R
input double InpPartialTpFraction            = 0.50;   // partial close fraction
input double InpBreakEvenAtR                 = 1.00;   // trail to BE after 1R
input double InpMinRRAtFill                  = 1.20;   // minimum RR at fill
input double InpMaxSpreadPoints              = 60.0;   // maximum spread points
input double InpAtrPercentileLow             = 20.0;   // ATR percentile low
input double InpAtrPercentileHigh            = 80.0;   // ATR percentile high
input int    InpAtrPeriod                    = 14;     // ATR period
input int    InpAtrPercentileLookback        = 100;    // ATR percentile window
input int    InpHtfLookbackBars              = 50;     // H1/H4 bias lookback
input int    InpLiquidityLookbackBars        = 50;     // opposing liquidity lookback
input int    InpProfileLookbackBars          = 50;     // volume profile lookback
input int    InpMaxZoneAgeHours              = 48;     // zone lifecycle TTL

input int    InpEntryMode                    = 0;      // 0 retest, 1 momentum, 2 reversal
input double InpRetestEntryPercent           = 50.0;   // 0 edge, 50 midpoint
input double InpMaxChaseATR                  = 1.50;   // momentum max chase

input bool   InpUseAIAgent                   = false;  // optional opinion component
input string InpAIFile                       = "QSMC\\ai_opinion.json"; // opinion JSON
input int    InpAITimeoutMs                  = 250;    // file-read deadline
input int    InpAIMaxAgeSec                  = 60;     // opinion max age

input double InpMaxDailyLossPercent          = 0.50;   // hard daily loss lock
input int    InpMaxConcurrentTrades          = 1;      // hard max positions
input int    InpMaxTradesPerDay              = 3;      // hard daily trade cap
input int    InpCooldownMinutes              = 60;     // minutes after any entry

input bool   InpCsvLog                       = true;   // structured CSV
input string InpCsvFile                      = "QSMC\\confirmation_evaluations.csv";
input string InpRegistryFile                 = "QSMC\\confirmation_registry.txt";

// ---------------------------------------------------------------- structs
struct SZoneRecord
{
   string   id;
   int      direction;
   int      kind;
   int      state;
   double   lo;
   double   hi;
   datetime born_utc;
   datetime last_seen_utc;
   int      touches;
   bool     triggered;
   bool     invalidated;
   double   last_score;
   int      last_tier;
   string   last_decision;
   string   last_reject;
};

struct SZoneFacts
{
   int      direction;
   int      kind;
   int      state;
   double   lo;
   double   hi;
   datetime born_utc;
   datetime now_utc;
   double   age_hours;
   int      touches;
   double   zone_atr_ratio;
   double   atr_m1;
   double   atr_percentile;
   double   spread_points;
   double   spread_price;
   double   spread_atr_pct;
   double   room_to_liquidity;
   double   rr_at_fill;
   double   nearest_liquidity;
   double   invalidation;
   double   bid;
   double   ask;
   double   current_price;
   double   point;
   double   tick_value;
   double   equity;
   int      stops_level;
   int      freeze_level;
   int      min_stop_points;
   int      session;
   bool     session_entry_allowed;
   int      h1_bias;
   int      h4_bias;
   double   htf_alignment;
   bool     asia_sweep;
   bool     london_sweep;
   bool     bsl_ssl;
   bool     eqh_eql;
   bool     sweep_before_reaction;
   bool     m1_choch;
   bool     m5_bos;
   bool     confirmation_close;
   bool     second_reaction;
   bool     sweep;
   bool     closed_beyond_zone;
   bool     micro_bos;
   bool     first_pullback;
   bool     poc_reaction;
   bool     vah_val_reaction;
   bool     volume_expansion;
   int      mode;
   double   retest_percent;
   double   max_chase_atr;
   double   momentum_close;
   double   pullback_price;
   double   second_reaction_price;
   double   chase_distance;
   bool     ai_used;
   int      ai_direction;
   double   ai_confidence;
   string   ai_reasons;
   string   ai_invalidation;
   string   ai_why;
   datetime ai_as_of;
};

struct SScoreResult
{
   double   q_pts;
   double   liq_pts;
   double   struct_pts;
   double   htf_pts;
   double   vol_pts;
   double   session_pts;
   double   exec_pts;
   double   ai_pts;
   double   ai_max;
   double   available_max;
   double   raw_total;
   int      total;
   int      tier;
   string   tier_text;
   double   htf_penalty;
   double   risk_scale;
   int      session;
   bool     session_permission;
   bool     account_ok;
   string   account_why;
   string   decision;
   string   reject_code;
   string   reject_values;
   string   order_action;
   string   entry_mode;
   string   plan_why;
   bool     plan_ready;
   double   entry_price;
   double   sl;
   double   tp;
   double   partial_tp;
   double   trail_sl;
   double   risk;
   double   lots;
   string   ai_why;
   string   ai_reasons;
   string   ai_invalidation;
};

struct SAccountState
{
   bool     master_enable;
   bool     dry_run;
   bool     allow_live;
   bool     allow_real;
   bool     kill_switch;
   bool     daily_lock;
   bool     real_account;
   int      positions;
   int      trades_today;
   int      max_concurrent;
   int      max_trades;
   double   equity;
   double   day_start_equity;
   double   max_daily_loss_pct;
   datetime now_utc;
   datetime last_entry_utc;
   int      cooldown_minutes;
};

struct SAIOpinion
{
   int      direction;
   double   confidence;
   string   reasons;
   string   invalidation;
   datetime as_of;
   bool     valid;
   string   why;
};

// C++ host harness needs these free functions declared before the classes
// that call them; MQL5 accepts the same prototypes.
uint CE_HashId(const string &id);
bool CE_CanTransition(const int from_state, const int to_state);
bool CE_ParseZoneObject(const string &name, const string &tooltip, const double lo,
                        const double hi, const datetime anchor_utc, SZoneRecord &out);

// ---------------------------------------------------------------- registry
class CZoneRegistry
{
private:
   int         m_buckets[CE_HASH_BUCKETS];
   int         m_next[CE_MAX_ZONES];
   SZoneRecord m_zones[CE_MAX_ZONES];
   int         m_count;

public:
   void ZR_Init()
   {
      for(int b=0; b<CE_HASH_BUCKETS; b++)
      {
         m_buckets[b]=-1;
      }
      for(int z=0; z<CE_MAX_ZONES; z++)
      {
         m_next[z]=-1;
      }
      m_count=0;
   }

   int ZR_Count()
   {
      return m_count;
   }

   int ZR_Find(const string &id)
   {
      uint h=CE_HashId(id);
      int b=(int)(h%(uint)CE_HASH_BUCKETS);
      int idx=m_buckets[b];
      while(idx>=0)
      {
         if(m_zones[idx].id==id)
         {
            return idx;
         }
         idx=m_next[idx];
      }
      return -1;
   }

   bool ZR_Upsert(const SZoneRecord &z)
   {
      int idx=ZR_Find(z.id);
      if(idx>=0)
      {
         int old_state=m_zones[idx].state;
         if(CE_CanTransition(old_state,z.state))
         {
            m_zones[idx].state=z.state;
         }
         m_zones[idx].kind=z.kind;
         m_zones[idx].lo=z.lo;
         m_zones[idx].hi=z.hi;
         m_zones[idx].last_seen_utc=z.last_seen_utc;
         m_zones[idx].touches=z.touches;
         m_zones[idx].triggered=z.triggered;
         m_zones[idx].invalidated=z.invalidated;
         return true;
      }
      if(m_count>=CE_MAX_ZONES)
      {
         return false;
      }
      int new_idx=m_count;
      m_count++;
      m_zones[new_idx]=z;
      uint h=CE_HashId(z.id);
      int b=(int)(h%(uint)CE_HASH_BUCKETS);
      m_next[new_idx]=m_buckets[b];
      m_buckets[b]=new_idx;
      return true;
   }

   bool ZR_Get(const int idx, SZoneRecord &out)
   {
      if(idx<0 || idx>=m_count)
      {
         return false;
      }
      out=m_zones[idx];
      return true;
   }

   bool ZR_Transition(const string &id, const int new_state, const datetime now_utc, const string &reason)
   {
      int idx=ZR_Find(id);
      if(idx<0)
      {
         return false;
      }
      if(CE_CanTransition(m_zones[idx].state,new_state)==false)
      {
         return false;
      }
      m_zones[idx].state=new_state;
      m_zones[idx].last_seen_utc=now_utc;
      m_zones[idx].last_reject=reason;
      if(new_state==CE_STATE_TRIGGERED)
      {
         m_zones[idx].triggered=true;
      }
      if(new_state==CE_STATE_EXPIRED || new_state==CE_STATE_INVALIDATED)
      {
         m_zones[idx].invalidated=true;
      }
      return true;
   }

   void ZR_MarkEvaluated(const string &id, const double score, const int tier,
                         const string &decision, const string &reject, const datetime now_utc)
   {
      int idx=ZR_Find(id);
      if(idx<0)
      {
         return;
      }
      m_zones[idx].last_score=score;
      m_zones[idx].last_tier=tier;
      m_zones[idx].last_decision=decision;
      m_zones[idx].last_reject=reject;
      m_zones[idx].last_seen_utc=now_utc;
   }

   void ZR_Expire(const datetime now_utc, const long max_age_sec)
   {
      for(int idx=0; idx<m_count; idx++)
      {
         if(m_zones[idx].state==CE_STATE_EXPIRED || m_zones[idx].state==CE_STATE_INVALIDATED)
         {
            continue;
         }
         long age=now_utc-m_zones[idx].born_utc;
         if(age>max_age_sec)
         {
            m_zones[idx].state=CE_STATE_EXPIRED;
            m_zones[idx].invalidated=true;
            m_zones[idx].last_reject="AGE_TTL";
         }
      }
   }
};

// ---------------------------------------------------------------- parser
class CZoneParser
{
public:
   bool ZP_ParseZoneObject(const string &name, const string &tooltip, const double lo,
                           const double hi, const datetime anchor_utc, SZoneRecord &out)
   {
      return CE_ParseZoneObject(name,tooltip,lo,hi,anchor_utc,out);
   }
};

// ---------------------------------------------------------------- globals
CTrade          g_trade;
CZoneRegistry   g_reg;
datetime        g_last_bar=0;
long            g_day_key=0;
double          g_day_start_equity=0.0;
bool            g_daily_lock=false;
int             g_trades_today=0;
datetime        g_last_entry_utc=0;
string          g_csv_buffer="";
string          g_top_zone[3];
int             g_top_score[3];
string          g_top_breakdown[3];
string          g_last_decision="NONE";
string          g_last_reject="NONE";
int             g_last_score=0;
string          g_last_zone="";

// ---------------------------------------------------------------- small pure helpers
string CE_BoolText(const bool b)
{
   if(b)
   {
      return "true";
   }
   return "false";
}

string CE_StateText(const int state)
{
   if(state==CE_STATE_DETECTED)         { return "DETECTED"; }
   if(state==CE_STATE_VALIDATED)        { return "VALIDATED"; }
   if(state==CE_STATE_TESTED_MITIGATED) { return "TESTED_MITIGATED"; }
   if(state==CE_STATE_TRIGGERED)        { return "TRIGGERED"; }
   if(state==CE_STATE_EXPIRED)          { return "EXPIRED"; }
   if(state==CE_STATE_INVALIDATED)      { return "INVALIDATED"; }
   return "NONE";
}

string CE_KindText(const int kind)
{
   if(kind==CE_KIND_OB_FVG) { return "OB+FVG"; }
   if(kind==CE_KIND_OB)     { return "OB"; }
   if(kind==CE_KIND_FVG)    { return "FVG"; }
   return "ZONE";
}

string CE_DirectionText(const int dir)
{
   if(dir>0)  { return "BUY"; }
   if(dir<0)  { return "SELL"; }
   return "FLAT";
}

string CE_TierText(const int tier)
{
   if(tier>=2) { return "A"; }
   if(tier==1) { return "B"; }
   return "C";
}

string CE_SessionName(const int session)
{
   if(session==CE_SESSION_ASIA)    { return "ASIA"; }
   if(session==CE_SESSION_LONDON)  { return "LONDON"; }
   if(session==CE_SESSION_NEWYORK) { return "NEWYORK"; }
   return "OFFPEAK";
}

string CE_EntryModeName(const int mode)
{
   if(mode==CE_MODE_MOMENTUM) { return "MOMENTUM"; }
   if(mode==CE_MODE_REVERSAL) { return "REVERSAL_AFTER_MITIGATION"; }
   return "RETEST";
}

uint CE_HashId(const string &id)
{
   uint h=0x811C9DC5;
   int n=StringLen(id);
   for(int i=0; i<n; i++)
   {
      ushort ch=StringGetCharacter(id,i);
      if(ch==0)
      {
         break;
      }
      h=(h^(uint)ch)*0x01000193;
   }
   return h;
}

bool CE_CanTransition(const int from_state, const int to_state)
{
   if(from_state==to_state)                         { return true; }
   if(to_state==CE_STATE_EXPIRED)                  { return true; }
   if(to_state==CE_STATE_INVALIDATED)              { return true; }
   if(from_state==CE_STATE_EXPIRED)                { return false; }
   if(from_state==CE_STATE_INVALIDATED)            { return false; }
   if(from_state==CE_STATE_TRIGGERED)              { return false; }
   if(from_state==CE_STATE_DETECTED)
   {
      if(to_state==CE_STATE_VALIDATED)             { return true; }
      if(to_state==CE_STATE_TESTED_MITIGATED)     { return true; }
      if(to_state==CE_STATE_TRIGGERED)            { return true; }
      return false;
   }
   if(from_state==CE_STATE_VALIDATED)
   {
      if(to_state==CE_STATE_TESTED_MITIGATED)     { return true; }
      if(to_state==CE_STATE_TRIGGERED)            { return true; }
      return false;
   }
   if(from_state==CE_STATE_TESTED_MITIGATED)
   {
      if(to_state==CE_STATE_TRIGGERED)            { return true; }
      return false;
   }
   return false;
}

// ---------------------------------------------------------------- civil date and UTC
void CE_CivilFromDays(const long days, int &year, int &month, int &day)
{
   long z=days+719468;
   long era=(z>=0 ? z : z-146096)/146097;
   long doe=z-era*146097;
   long yoe=(doe-doe/1460+doe/36524-doe/146096)/365;
   long yy=yoe+era*400;
   long doy=doe-(365*yoe+yoe/4-yoe/100);
   long mp=(5*doy+2)/153;
   long dd=doy-(153*mp+2)/5+1;
   long mm=mp+(mp<10 ? 3 : -9);
   yy+=(mm<=2 ? 1 : 0);
   year=(int)yy;
   month=(int)mm;
   day=(int)dd;
}

long CE_DaysFromCivil(const int year, const int month, const int day)
{
   long yy=(long)year;
   yy-=(month<=2 ? 1 : 0);
   long era=(yy>=0 ? yy : yy-399)/400;
   long yoe=yy-era*400;
   long mp=(long)month+(month>2 ? -3 : 9);
   long doy=(153*mp+2)/5+(long)day-1;
   long doe=yoe*365+yoe/4-yoe/100+doy;
   return era*146097+doe-719468;
}

int CE_DayOfWeek(const long days)
{
   long w=(days+4)%7;
   if(w<0)
   {
      w+=7;
   }
   return (int)w;
}

long CE_LastSundayOfMonthDays(const int year, const int month)
{
   int ny=year;
   int nm=month+1;
   if(nm>12)
   {
      nm=1;
      ny++;
   }
   long last=CE_DaysFromCivil(ny,nm,1)-1;
   int dow=CE_DayOfWeek(last);
   return last-(long)dow;
}

long CE_FirstSundayOfMonthDays(const int year, const int month)
{
   long first=CE_DaysFromCivil(year,month,1);
   int dow=CE_DayOfWeek(first);
   long offset=(long)((7-dow)%7);
   return first+offset;
}

long CE_NthSundayOfMonthDays(const int year, const int month, const int nth)
{
   long first=CE_FirstSundayOfMonthDays(year,month);
   return first+7*(long)(nth-1);
}

bool CE_IsEuDst(const datetime utc)
{
   long days=utc/86400;
   int y=0;
   int m=0;
   int d=0;
   CE_CivilFromDays(days,y,m,d);
   datetime start=CE_LastSundayOfMonthDays(y,3)*86400+3600;
   datetime end=CE_LastSundayOfMonthDays(y,10)*86400+3600;
   return (utc>=start && utc<end);
}

bool CE_IsUsDst(const datetime utc)
{
   long days=utc/86400;
   int y=0;
   int m=0;
   int d=0;
   CE_CivilFromDays(days,y,m,d);
   datetime start=CE_NthSundayOfMonthDays(y,3,2)*86400+7*3600;
   datetime end=CE_FirstSundayOfMonthDays(y,11)*86400+6*3600;
   return (utc>=start && utc<end);
}

int CE_BrokerOffsetMinutes(const datetime utc, const int winter, const int summer, const bool use_dst)
{
   if(use_dst && CE_IsEuDst(utc))
   {
      return summer;
   }
   return winter;
}

datetime CE_ServerToUtc(const datetime server, const int winter, const int summer, const bool use_dst)
{
   if(use_dst==false || winter==summer)
   {
      return server-(long)winter*60;
   }
   datetime cand_w=server-(long)winter*60;
   datetime cand_s=server-(long)summer*60;
   bool w_ok=(CE_IsEuDst(cand_w)==false);
   bool s_ok=(CE_IsEuDst(cand_s)==true);
   if(w_ok && s_ok==false)
   {
      return cand_w;
   }
   if(s_ok && w_ok==false)
   {
      return cand_s;
   }
   if(w_ok && s_ok)
   {
      return cand_w;
   }
   return cand_s;
}

datetime CE_UtcToBrokerServer(const datetime utc, const int winter, const int summer, const bool use_dst)
{
   int off=CE_BrokerOffsetMinutes(utc,winter,summer,use_dst);
   return utc+(long)off*60;
}

int CE_UtcToAlgeriaHour(const datetime utc)
{
   datetime shifted=utc+3600;
   long h=(shifted/3600)%24;
   if(h<0)
   {
      h+=24;
   }
   return (int)h;
}

int CE_SessionOfUtc(const datetime utc)
{
   long day=utc%86400;
   if(day<0)
   {
      day+=86400;
   }
   int minute=(int)(day/60);
   if(minute>=1380 || minute<420)
   {
      return CE_SESSION_ASIA;
   }
   if(minute>=480 && minute<660)
   {
      return CE_SESSION_LONDON;
   }
   if(minute>=870 && minute<1080)
   {
      return CE_SESSION_NEWYORK;
   }
   return CE_SESSION_OFFPEAK;
}

double CE_SessionScore(const int session)
{
   if(session==CE_SESSION_LONDON)  { return 10.0; }
   if(session==CE_SESSION_NEWYORK) { return 8.0; }
   if(session==CE_SESSION_ASIA)    { return 2.0; }
   return 0.0;
}

bool CE_SessionEntryAllowed(const int session, const bool allow_asia, const bool allow_offpeak)
{
   if(session==CE_SESSION_LONDON || session==CE_SESSION_NEWYORK)
   {
      return true;
   }
   if(session==CE_SESSION_ASIA)
   {
      return allow_asia;
   }
   return allow_offpeak;
}

// ---------------------------------------------------------------- init helpers
void CE_InitZone(SZoneRecord &z)
{
   z.id="";
   z.direction=0;
   z.kind=CE_KIND_OB;
   z.state=CE_STATE_DETECTED;
   z.lo=0.0;
   z.hi=0.0;
   z.born_utc=0;
   z.last_seen_utc=0;
   z.touches=0;
   z.triggered=false;
   z.invalidated=false;
   z.last_score=0.0;
   z.last_tier=0;
   z.last_decision="NONE";
   z.last_reject="NONE";
}

void CE_InitFacts(SZoneFacts &f)
{
   f.direction=1;
   f.kind=CE_KIND_OB;
   f.state=CE_STATE_DETECTED;
   f.lo=0.0;
   f.hi=0.0;
   f.born_utc=0;
   f.now_utc=0;
   f.age_hours=0.0;
   f.touches=0;
   f.zone_atr_ratio=0.0;
   f.atr_m1=0.0;
   f.atr_percentile=50.0;
   f.spread_points=0.0;
   f.spread_price=0.0;
   f.spread_atr_pct=0.0;
   f.room_to_liquidity=0.0;
   f.rr_at_fill=0.0;
   f.nearest_liquidity=0.0;
   f.invalidation=0.0;
   f.bid=0.0;
   f.ask=0.0;
   f.current_price=0.0;
   f.point=0.01;
   f.tick_value=1.0;
   f.equity=10000.0;
   f.stops_level=0;
   f.freeze_level=0;
   f.min_stop_points=20;
   f.session=CE_SESSION_OFFPEAK;
   f.session_entry_allowed=false;
   f.h1_bias=0;
   f.h4_bias=0;
   f.htf_alignment=0.0;
   f.asia_sweep=false;
   f.london_sweep=false;
   f.bsl_ssl=false;
   f.eqh_eql=false;
   f.sweep_before_reaction=false;
   f.m1_choch=false;
   f.m5_bos=false;
   f.confirmation_close=false;
   f.second_reaction=false;
   f.sweep=false;
   f.closed_beyond_zone=false;
   f.micro_bos=false;
   f.first_pullback=false;
   f.poc_reaction=false;
   f.vah_val_reaction=false;
   f.volume_expansion=false;
   f.mode=CE_MODE_RETEST;
   f.retest_percent=0.5;
   f.max_chase_atr=1.5;
   f.momentum_close=0.0;
   f.pullback_price=0.0;
   f.second_reaction_price=0.0;
   f.chase_distance=0.0;
   f.ai_used=false;
   f.ai_direction=0;
   f.ai_confidence=0.0;
   f.ai_reasons="";
   f.ai_invalidation="";
   f.ai_why="AI_DISABLED";
   f.ai_as_of=0;
}

void CE_InitScore(SScoreResult &r)
{
   r.q_pts=0.0;
   r.liq_pts=0.0;
   r.struct_pts=0.0;
   r.htf_pts=0.0;
   r.vol_pts=0.0;
   r.session_pts=0.0;
   r.exec_pts=0.0;
   r.ai_pts=0.0;
   r.ai_max=0.0;
   r.available_max=95.0;
   r.raw_total=0.0;
   r.total=0;
   r.tier=0;
   r.tier_text="C";
   r.htf_penalty=0.0;
   r.risk_scale=0.0;
   r.session=CE_SESSION_OFFPEAK;
   r.session_permission=false;
   r.account_ok=false;
   r.account_why="NONE";
   r.decision="NEAR_MISS";
   r.reject_code="NONE";
   r.reject_values="";
   r.order_action="NONE";
   r.entry_mode="RETEST";
   r.plan_why="NONE";
   r.plan_ready=false;
   r.entry_price=0.0;
   r.sl=0.0;
   r.tp=0.0;
   r.partial_tp=0.0;
   r.trail_sl=0.0;
   r.risk=0.0;
   r.lots=0.0;
   r.ai_why="AI_DISABLED";
   r.ai_reasons="";
   r.ai_invalidation="";
}

void CE_InitAccount(SAccountState &a)
{
   a.master_enable=true;
   a.dry_run=true;
   a.allow_live=false;
   a.allow_real=false;
   a.kill_switch=false;
   a.daily_lock=false;
   a.real_account=false;
   a.positions=0;
   a.trades_today=0;
   a.max_concurrent=1;
   a.max_trades=3;
   a.equity=10000.0;
   a.day_start_equity=10000.0;
   a.max_daily_loss_pct=0.50;
   a.now_utc=0;
   a.last_entry_utc=0;
   a.cooldown_minutes=60;
}

void CE_InitAIOpinion(SAIOpinion &ai)
{
   ai.direction=0;
   ai.confidence=0.0;
   ai.reasons="";
   ai.invalidation="";
   ai.as_of=0;
   ai.valid=false;
   ai.why="AI_MISSING";
}

void CE_InitPanel()
{
   for(int k=0; k<3; k++)
   {
      g_top_zone[k]="";
      g_top_score[k]=-1;
      g_top_breakdown[k]="";
   }
   g_last_decision="NONE";
   g_last_reject="NONE";
   g_last_score=0;
   g_last_zone="";
}

// ---------------------------------------------------------------- tokens and JSON
string CE_LogToken(const string &src)
{
   string s=src;
   StringReplace(s,"|",";");
   StringReplace(s,",",";");
   StringReplace(s,"\t",";");
   StringReplace(s,"\r",";");
   StringReplace(s,"\n",";");
   return s;
}

string CE_CsvToken(const string &src)
{
   string s=src;
   StringReplace(s,",",";");
   StringReplace(s,"\t",";");
   StringReplace(s,"\r",";");
   StringReplace(s,"\n",";");
   return s;
}

bool CE_IsSpaceOnly(const ushort c)
{
   if(c==32 || c==9 || c==13 || c==10)
   {
      return true;
   }
   return false;
}

bool CE_IsSpaceOrQuote(const ushort c)
{
   if(CE_IsSpaceOnly(c) || c==34)
   {
      return true;
   }
   return false;
}

string CE_TrimJson(const string &raw)
{
   int n=StringLen(raw);
   int a=0;
   int b=n-1;
   while(a<n && CE_IsSpaceOnly(StringGetCharacter(raw,a)))
   {
      a++;
   }
   while(b>=a && CE_IsSpaceOnly(StringGetCharacter(raw,b)))
   {
      b--;
   }
   if(a>b)
   {
      return "";
   }
   if(b>a && StringGetCharacter(raw,a)==34 && StringGetCharacter(raw,b)==34)
   {
      a++;
      b--;
   }
   if(a>b)
   {
      return "";
   }
   return StringSubstr(raw,a,b-a+1);
}

bool CE_JsonField(const string &json, const string &key, string &out)
{
   out="";
   string needle="\""+key+"\"";
   int p=StringFind(json,needle);
   if(p<0)
   {
      return false;
   }
   int colon=StringFind(json,":",p+StringLen(needle));
   if(colon<0)
   {
      return false;
   }
   int i=colon+1;
   int n=StringLen(json);
   while(i<n)
   {
      ushort c=StringGetCharacter(json,i);
      if(c!=32 && c!=9 && c!=13 && c!=10)
      {
         break;
      }
      i++;
   }
   if(i>=n)
   {
      return false;
   }
   string raw="";
   ushort first=StringGetCharacter(json,i);
   if(first==34)
   {
      i++;
      while(i<n)
      {
         ushort c2=StringGetCharacter(json,i);
         if(c2==34)
         {
            break;
         }
         raw+=StringSubstr(json,i,1);
         i++;
      }
   }
   else
   {
      while(i<n)
      {
         ushort c3=StringGetCharacter(json,i);
         if(c3==44 || c3==125)
         {
            break;
         }
         raw+=StringSubstr(json,i,1);
         i++;
      }
   }
   out=CE_TrimJson(raw);
   return (StringLen(out)>0);
}

bool CE_ParseAIOpinion(const string &json, const datetime now_utc, const int max_age_sec, SAIOpinion &ai)
{
   CE_InitAIOpinion(ai);
   if(StringLen(json)<=0)
   {
      ai.why="AI_MISSING_OR_EMPTY";
      return false;
   }
   string field="";
   if(CE_JsonField(json,"direction",field)==false)
   {
      ai.why="AI_DIRECTION_MISSING";
      return false;
   }
   ai.direction=(int)StringToInteger(field);
   if(ai.direction!=1 && ai.direction!=-1)
   {
      ai.why="AI_DIRECTION_INVALID";
      return false;
   }
   if(CE_JsonField(json,"confidence",field)==false)
   {
      ai.why="AI_CONFIDENCE_MISSING";
      return false;
   }
   ai.confidence=StringToDouble(field);
   if(ai.confidence<0.0 || ai.confidence>1.0 || MathIsValidNumber(ai.confidence)==false)
   {
      ai.why="AI_CONFIDENCE_INVALID";
      return false;
   }
   if(CE_JsonField(json,"reasons",field)==false)
   {
      ai.why="AI_REASONS_MISSING";
      return false;
   }
   ai.reasons=field;
   if(CE_JsonField(json,"invalidation",field)==false)
   {
      ai.why="AI_INVALIDATION_MISSING";
      return false;
   }
   ai.invalidation=field;
   if(CE_JsonField(json,"as_of",field)==false)
   {
      ai.why="AI_AS_OF_MISSING";
      return false;
   }
   ai.as_of=(datetime)StringToInteger(field);
   if(ai.as_of<=0)
   {
      ai.why="AI_AS_OF_INVALID";
      return false;
   }
   if(now_utc-ai.as_of>(long)max_age_sec || ai.as_of>now_utc+60)
   {
      ai.why="AI_STALE_OR_FUTURE";
      return false;
   }
   ai.valid=true;
   ai.why="AI_OK";
   return true;
}

// ---------------------------------------------------------------- parser helpers
bool CE_ReadNumberAt(const string &s, const int start, double &val, int &end)
{
   int n=StringLen(s);
   int i=start;
   string buf="";
   if(i<n && StringGetCharacter(s,i)==45)
   {
      buf+="-";
      i++;
   }
   bool dot=false;
   while(i<n)
   {
      ushort c=StringGetCharacter(s,i);
      if(c>=48 && c<=57)
      {
         buf+=StringSubstr(s,i,1);
         i++;
         continue;
      }
      if(c==46 && dot==false)
      {
         buf+=StringSubstr(s,i,1);
         dot=true;
         i++;
         continue;
      }
      break;
   }
   if(buf=="" || buf=="-" || buf=="." || buf=="-.")
   {
      return false;
   }
   val=StringToDouble(buf);
   end=i;
   return true;
}

bool CE_ExtractTwoPrices(const string &text, double &lo, double &hi)
{
   int n=StringLen(text);
   int i=0;
   while(i<n)
   {
      ushort c=StringGetCharacter(text,i);
      if((c>=48 && c<=57) || c==45)
      {
         double first=0.0;
         int after=0;
         if(CE_ReadNumberAt(text,i,first,after))
         {
            int j=after;
            while(j<n && StringGetCharacter(text,j)!=45)
            {
               j++;
            }
            if(j<n)
            {
               int k=j+1;
               while(k<n)
               {
                  ushort sep=StringGetCharacter(text,k);
                  if(sep!=32 && sep!=9 && sep!=13 && sep!=10)
                  {
                     break;
                  }
                  k++;
               }
               double second=0.0;
               int end2=0;
               if(CE_ReadNumberAt(text,k,second,end2))
               {
                  lo=MathMin(first,second);
                  hi=MathMax(first,second);
                  return true;
               }
            }
         }
      }
      i++;
   }
   return false;
}

bool CE_ParseId(const string &id, SZoneRecord &z)
{
   CE_InitZone(z);
   if(StringFind(id,"Z|BUY|")==0)
   {
      z.direction=1;
   }
   else if(StringFind(id,"Z|SELL|")==0)
   {
      z.direction=-1;
   }
   else
   {
      return false;
   }
   int p=StringFind(id,"|",0);
   int q=StringFind(id,"|",p+1);
   if(p<0 || q<0)
   {
      return false;
   }
   string epoch=StringSubstr(id,q+1);
   if(StringLen(epoch)<=0)
   {
      return false;
   }
   long t=StringToInteger(epoch);
   if(t<=0)
   {
      return false;
   }
   z.id=id;
   z.born_utc=(datetime)t;
   z.state=CE_STATE_DETECTED;
   return true;
}

bool CE_ExtractObjectDirection(const string &name, int &dir, int &index)
{
   dir=0;
   index=-1;
   int p=StringFind(name,"ZN_");
   if(p<0)
   {
      return false;
   }
   string tail=StringSubstr(name,p+3);
   if(StringLen(tail)<=0)
   {
      return false;
   }
   ushort c=StringGetCharacter(tail,0);
   if(c==66)
   {
      dir=1;
   }
   else if(c==83)
   {
      dir=-1;
   }
   else
   {
      return false;
   }
   string num=StringSubstr(tail,1);
   index=(int)StringToInteger(num);
   return true;
}

bool CE_ParseZoneObject(const string &name, const string &tooltip, const double lo,
                        const double hi, const datetime anchor_utc, SZoneRecord &out)
{
   CE_InitZone(out);
   string tip=tooltip;
   StringReplace(tip,"–","-");
   StringReplace(tip,"—","-");
   string canonical="";
   int p=StringFind(tip,"Z|BUY|");
   if(p<0)
   {
      p=StringFind(tip,"Z|SELL|");
   }
   if(p>=0)
   {
      int e=p;
      int n=StringLen(tip);
      while(e<n)
      {
         ushort c=StringGetCharacter(tip,e);
         if(c==32 || c==9 || c==13 || c==10 || c==44 || c==41 || c==93 || c==59)
         {
            break;
         }
         e++;
      }
      canonical=StringSubstr(tip,p,e-p);
   }
   if(StringLen(canonical)>0 && CE_ParseId(canonical,out))
   {
      // canonical id wins
   }
   else if(StringFind(name,"Z|")==0 && CE_ParseId(name,out))
   {
      // legacy object name
   }
   else
   {
      int dir=0;
      int idx=-1;
      if(CE_ExtractObjectDirection(name,dir,idx)==false)
      {
         return false;
      }
      out.direction=dir;
      long epoch=(long)anchor_utc;
      if(epoch<=0)
      {
         epoch=(long)(lo*100.0);
      }
      out.id="Z|"+CE_DirectionText(dir)+"|"+IntegerToString(epoch);
      out.born_utc=(datetime)epoch;
   }
   double parsed_lo=0.0;
   double parsed_hi=0.0;
   if(CE_ExtractTwoPrices(tip,parsed_lo,parsed_hi))
   {
      out.lo=parsed_lo;
      out.hi=parsed_hi;
   }
   else
   {
      out.lo=MathMin(lo,hi);
      out.hi=MathMax(lo,hi);
   }
   if(out.lo<=0.0 || out.hi<=out.lo)
   {
      return false;
   }
   if(StringFind(tip,"OB+FVG")>=0)
   {
      out.kind=CE_KIND_OB_FVG;
   }
   else if(StringFind(tip,"OB")>=0)
   {
      out.kind=CE_KIND_OB;
   }
   else if(StringFind(tip,"FVG")>=0)
   {
      out.kind=CE_KIND_FVG;
   }
   if(StringFind(tip,"MITIGATED")>=0)
   {
      out.state=CE_STATE_TESTED_MITIGATED;
      out.touches=1;
   }
   else if(StringFind(tip,"VALIDATED")>=0)
   {
      out.state=CE_STATE_VALIDATED;
   }
   else if(StringFind(tip,"TRIGGERED")>=0)
   {
      out.state=CE_STATE_TRIGGERED;
      out.triggered=true;
   }
   else if(StringFind(tip,"EXPIRED")>=0)
   {
      out.state=CE_STATE_EXPIRED;
      out.invalidated=true;
   }
   else if(StringFind(tip,"INVALIDATED")>=0)
   {
      out.state=CE_STATE_INVALIDATED;
      out.invalidated=true;
   }
   out.last_seen_utc=anchor_utc;
   return true;
}

// ---------------------------------------------------------------- persistence
void CE_NextField(string &rest, string &field)
{
   int p=StringFind(rest,"\t");
   if(p<0)
   {
      field=rest;
      rest="";
   }
   else
   {
      field=StringSubstr(rest,0,p);
      rest=StringSubstr(rest,p+1);
   }
}

void CE_NextLine(string &rest, string &line)
{
   int p=StringFind(rest,"\n");
   if(p<0)
   {
      line=rest;
      rest="";
   }
   else
   {
      line=StringSubstr(rest,0,p);
      rest=StringSubstr(rest,p+1);
   }
}

void CE_SerializeZone(const SZoneRecord &z, string &out)
{
   out=z.id+"\t"+IntegerToString((long)z.direction)+"\t"+IntegerToString((long)z.kind)+"\t"+
       IntegerToString((long)z.state)+"\t"+DoubleToString(z.lo,5)+"\t"+DoubleToString(z.hi,5)+"\t"+
       IntegerToString((long)z.born_utc)+"\t"+IntegerToString((long)z.last_seen_utc)+"\t"+
       IntegerToString((long)z.touches)+"\t"+CE_BoolText(z.triggered)+"\t"+CE_BoolText(z.invalidated)+"\t"+
       DoubleToString(z.last_score,2)+"\t"+IntegerToString((long)z.last_tier)+"\t"+
       CE_CsvToken(z.last_decision)+"\t"+CE_CsvToken(z.last_reject);
}

bool CE_DeserializeZone(const string &line, SZoneRecord &z)
{
   CE_InitZone(z);
   string rest=line;
   string f="";
   CE_NextField(rest,f); z.id=f;
   if(StringLen(rest)<=0) { return false; }
   CE_NextField(rest,f); z.direction=(int)StringToInteger(f);
   CE_NextField(rest,f); z.kind=(int)StringToInteger(f);
   CE_NextField(rest,f); z.state=(int)StringToInteger(f);
   CE_NextField(rest,f); z.lo=StringToDouble(f);
   CE_NextField(rest,f); z.hi=StringToDouble(f);
   CE_NextField(rest,f); z.born_utc=(datetime)StringToInteger(f);
   CE_NextField(rest,f); z.last_seen_utc=(datetime)StringToInteger(f);
   CE_NextField(rest,f); z.touches=(int)StringToInteger(f);
   CE_NextField(rest,f); z.triggered=(f=="true");
   CE_NextField(rest,f); z.invalidated=(f=="true");
   CE_NextField(rest,f); z.last_score=StringToDouble(f);
   CE_NextField(rest,f); z.last_tier=(int)StringToInteger(f);
   CE_NextField(rest,f); z.last_decision=f;
   CE_NextField(rest,f); z.last_reject=f;
   return (StringLen(z.id)>0 && z.hi>z.lo);
}

void CE_SaveRegistrySnapshot(CZoneRegistry &reg, string &out)
{
   out="";
   int n=reg.ZR_Count();
   for(int idx=0; idx<n; idx++)
   {
      SZoneRecord one;
      CE_InitZone(one);
      if(reg.ZR_Get(idx,one)==false)
      {
         continue;
      }
      string line="";
      CE_SerializeZone(one,line);
      out+=line+"\n";
   }
}

int CE_LoadRegistrySnapshot(CZoneRegistry &reg, const string &snapshot)
{
   string rest=snapshot;
   int loaded=0;
   while(StringLen(rest)>0)
   {
      string line="";
      CE_NextLine(rest,line);
      if(StringLen(line)<=0)
      {
         continue;
      }
      SZoneRecord z;
      CE_InitZone(z);
      if(CE_DeserializeZone(line,z))
      {
         if(reg.ZR_Upsert(z))
         {
            loaded++;
         }
      }
   }
   return loaded;
}

// ---------------------------------------------------------------- account / score
bool CE_AccountAllowsEntry(const SAccountState &a, string &why)
{
   why="NONE";
   if(a.master_enable==false)                         { why="MASTER_DISABLED"; return false; }
   if(a.kill_switch)                                  { why="KILL_SWITCH"; return false; }
   if(a.real_account && a.allow_real==false)          { why="REAL_REFUSED"; return false; }
   if(a.real_account)                                 { why="REAL_REFUSED"; return false; }
   if(a.daily_lock)                                   { why="DAILY_LOSS_LOCK"; return false; }
   if(a.equity<=0.0 || a.day_start_equity<=0.0)      { why="ACCOUNT_QUOTE_INVALID"; return false; }
   double dd=(a.day_start_equity-a.equity)/a.day_start_equity*100.0;
   if(dd>=a.max_daily_loss_pct)                       { why="DAILY_LOSS_LOCK"; return false; }
   if(a.positions>=a.max_concurrent)                  { why="MAX_CONCURRENT"; return false; }
   if(a.trades_today>=a.max_trades)                   { why="MAX_TRADES_PER_DAY"; return false; }
   if(a.last_entry_utc>0 && a.cooldown_minutes>0)
   {
      long gap=a.now_utc-a.last_entry_utc;
      if(gap<(long)a.cooldown_minutes*60)             { why="COOLDOWN"; return false; }
   }
   why="ACCOUNT_OK";
   return true;
}

double CE_HtfAlignment(const int h1, const int h4, const int dir)
{
   double v=0.0;
   if(h4==dir)          { v+=0.60; }
   else if(h4==0)       { v+=0.20; }
   if(h1==dir)          { v+=0.40; }
   else if(h1==0)       { v+=0.10; }
   return MathMin(1.0,v);
}

void CE_SetReject(SScoreResult &r, const string &code)
{
   r.decision="NEAR_MISS";
   r.reject_code=code;
   r.order_action="NONE";
}

void CE_ScoreComponents(const SZoneFacts &f, SScoreResult &r)
{
   double q=0.0;
   if(f.kind==CE_KIND_OB_FVG)      { q+=10.0; }
   else if(f.kind==CE_KIND_OB)     { q+=7.0; }
   else                             { q+=5.0; }
   if(f.state==CE_STATE_VALIDATED)           { q+=3.0; }
   if(f.state==CE_STATE_TESTED_MITIGATED)    { q+=4.0; }
   if(f.touches==0)                          { q+=4.0; }
   else                                      { q+=1.0; }
   if(f.zone_atr_ratio>=0.5 && f.zone_atr_ratio<=2.5) { q+=4.0; }
   if(f.age_hours>=0.0 && f.age_hours<4.0)  { q+=4.0; }
   else if(f.age_hours<12.0)                { q+=2.0; }
   r.q_pts=MathMin(20.0,q);

   double liq=0.0;
   if(f.asia_sweep)               { liq+=3.0; }
   if(f.london_sweep)             { liq+=3.0; }
   if(f.bsl_ssl)                  { liq+=3.0; }
   if(f.eqh_eql)                  { liq+=3.0; }
   if(f.sweep_before_reaction)    { liq+=3.0; }
   r.liq_pts=MathMin(15.0,liq);

   double st=0.0;
   if(f.m1_choch)                 { st+=6.0; }
   if(f.m5_bos)                   { st+=6.0; }
   if(f.confirmation_close)       { st+=4.0; }
   if(f.second_reaction)          { st+=4.0; }
   r.struct_pts=MathMin(20.0,st);

   double htf=0.0;
   if(f.h4_bias==f.direction)     { htf+=7.0; }
   else if(f.h4_bias==0)          { htf+=2.0; }
   if(f.h1_bias==f.direction)     { htf+=4.0; }
   else if(f.h1_bias==0)          { htf+=1.0; }
   htf+=f.htf_alignment*4.0;
   r.htf_pts=MathMin(15.0,htf);
   bool counter=(f.h4_bias!=0 && f.h4_bias!=f.direction);
   r.htf_penalty=(counter ? 8.0 : 0.0);

   double vol=0.0;
   if(f.poc_reaction)             { vol+=4.0; }
   if(f.vah_val_reaction)         { vol+=3.0; }
   if(f.volume_expansion)         { vol+=3.0; }
   r.vol_pts=MathMin(10.0,vol);

   r.session=f.session;
   r.session_pts=CE_SessionScore(f.session);

   bool spread_ok=(MathIsValidNumber(f.spread_points) && f.spread_points>=0.0 && f.spread_points<=InpMaxSpreadPoints);
   bool atr_ok=(f.atr_percentile>=InpAtrPercentileLow && f.atr_percentile<=InpAtrPercentileHigh);
   bool rr_ok=(MathIsValidNumber(f.rr_at_fill) && f.rr_at_fill>=InpMinRRAtFill);
   double ex=0.0;
   if(spread_ok)                  { ex+=3.0; }
   if(atr_ok)                     { ex+=2.0; }
   if(rr_ok)                      { ex+=5.0; }
   r.exec_pts=MathMin(10.0,ex);

   double ai_pts=0.0;
   double ai_max=0.0;
   string ai_why=f.ai_why;
   if(f.ai_used)
   {
      ai_max=5.0;
      ai_why="AI_OK";
      if(f.ai_direction==f.direction && MathIsValidNumber(f.ai_confidence))
      {
         ai_pts=5.0*MathMax(0.0,MathMin(1.0,f.ai_confidence));
      }
      else
      {
         ai_why="AI_DIRECTION_MISMATCH";
      }
   }
   r.ai_pts=ai_pts;
   r.ai_max=ai_max;
   r.ai_why=ai_why;
   r.ai_reasons=f.ai_reasons;
   r.ai_invalidation=f.ai_invalidation;
   r.available_max=95.0+ai_max;

   double raw=r.q_pts+r.liq_pts+r.struct_pts+r.htf_pts+r.vol_pts+r.session_pts+r.exec_pts+ai_pts;
   r.raw_total=raw;
   int total=(int)MathRound(raw*100.0/r.available_max);
   if(total<0)   { total=0; }
   if(total>100) { total=100; }
   r.total=total;
   r.tier=(r.total>=InpTierA ? 2 : (r.total>=InpTierB ? 1 : 0));
   r.tier_text=CE_TierText(r.tier);
}

string CE_BuildRejectValues(const SZoneFacts &f, const SScoreResult &r)
{
   string s="total="+IntegerToString((long)r.total);
   s+=";tier="+r.tier_text;
   s+=";A="+IntegerToString((long)InpTierA);
   s+=";B="+IntegerToString((long)InpTierB);
   s+=";htf="+DoubleToString(r.htf_pts,2);
   s+=";htf_min="+IntegerToString((long)InpMinHtfPoints);
   s+=";session="+CE_SessionName(f.session);
   s+=";spread="+DoubleToString(f.spread_points,2);
   s+=";spread_max="+DoubleToString(InpMaxSpreadPoints,2);
   s+=";rr="+DoubleToString(f.rr_at_fill,2);
   s+=";rr_min="+DoubleToString(InpMinRRAtFill,2);
   s+=";age_h="+DoubleToString(f.age_hours,2);
   s+=";touches="+IntegerToString((long)f.touches);
   s+=";ai="+DoubleToString(r.ai_pts,2);
   s+=";ai_why="+CE_LogToken(r.ai_why);
   s+=";mode="+CE_EntryModeName(f.mode);
   return s;
}

void CE_ApplyDecision(const SZoneFacts &f, const SAccountState &a, SScoreResult &r)
{
   bool session_ok=true;
   if(InpRequireSessionPermission)
   {
      session_ok=CE_SessionEntryAllowed(f.session,InpAllowAsiaEntries,InpAllowOffPeakEntries);
   }
   r.session_permission=session_ok;
   bool htf_ok=(r.htf_pts>=(double)InpMinHtfPoints);
   bool score_ok=(r.tier>0);
   bool spread_ok=(MathIsValidNumber(f.spread_points) && f.spread_points>=0.0 && f.spread_points<=InpMaxSpreadPoints);
   bool rr_ok=(MathIsValidNumber(f.rr_at_fill) && f.rr_at_fill>=InpMinRRAtFill);
   string account_why="";
   bool account_ok=CE_AccountAllowsEntry(a,account_why);
   r.account_ok=account_ok;
   r.account_why=account_why;
   r.risk_scale=(r.tier==2 ? 1.0 : (r.tier==1 ? InpTierBRiskScale : 0.0));
   bool counter=(f.h4_bias!=0 && f.h4_bias!=f.direction);
   if(counter)
   {
      r.risk_scale*=InpHtfCounterRiskScale;
   }
   bool all_ok=(score_ok && session_ok && htf_ok && spread_ok && rr_ok && account_ok);
   if(all_ok)
   {
      r.decision=(a.dry_run || a.allow_live==false ? "ENTER_DRY_RUN" : "ENTER");
      r.reject_code="NONE";
      r.order_action="NONE";
      return;
   }
   r.decision="NEAR_MISS";
   r.order_action="NONE";
   if(account_ok==false)                 { r.reject_code=account_why; return; }
   if(score_ok==false)                   { r.reject_code="SCORE_BELOW_B"; return; }
   if(session_ok==false)                 { r.reject_code="SESSION_PERMISSION"; return; }
   if(htf_ok==false)                     { r.reject_code="HTF_BELOW_MIN"; return; }
   if(spread_ok==false)                  { r.reject_code="SPREAD_INVALID"; return; }
   if(rr_ok==false)                      { r.reject_code="RR_BELOW_MIN"; return; }
   r.reject_code="UNKNOWN_GATE";
}

// ---------------------------------------------------------------- entry modes
bool CE_ModeRetest(const SZoneFacts &f, double &entry, string &why)
{
   if(f.confirmation_close==false)
   {
      why="RETEST_NO_CONFIRMED_CLOSE";
      return false;
   }
   double pct=MathMax(0.0,MathMin(0.5,f.retest_percent));
   double width=f.hi-f.lo;
   if(f.direction>0)
   {
      entry=f.lo+width*pct;
   }
   else
   {
      entry=f.hi-width*pct;
   }
   why="RETEST_READY";
   return true;
}

bool CE_ModeMomentum(const SZoneFacts &f, double &entry, string &why)
{
   if(f.closed_beyond_zone==false)
   {
      why="MOMENTUM_NO_CLOSE_BEYOND";
      return false;
   }
   if(f.micro_bos==false && f.first_pullback==false)
   {
      why="MOMENTUM_NO_PULLBACK_OR_MICRO_BOS";
      return false;
   }
   double max_chase=f.max_chase_atr*f.atr_m1;
   if(f.atr_m1<=0.0 || f.chase_distance>max_chase)
   {
      why="MOMENTUM_CHASE_TOO_FAR";
      return false;
   }
   if(f.first_pullback && f.pullback_price>0.0)
   {
      entry=f.pullback_price;
   }
   else
   {
      entry=f.current_price;
   }
   why="MOMENTUM_READY";
   return true;
}

bool CE_ModeReversal(const SZoneFacts &f, double &entry, string &why)
{
   if(f.sweep==false || f.m1_choch==false || f.second_reaction==false)
   {
      why="REVERSAL_NEEDS_SWEEP_CHOCH_SECOND_REACTION";
      return false;
   }
   if(f.second_reaction_price>0.0)
   {
      entry=f.second_reaction_price;
   }
   else
   {
      entry=f.current_price;
   }
   why="REVERSAL_READY";
   return true;
}

bool CE_ModeEvaluate(const int mode, const SZoneFacts &f, double &entry, string &why)
{
   if(mode==CE_MODE_MOMENTUM)
   {
      return CE_ModeMomentum(f,entry,why);
   }
   if(mode==CE_MODE_REVERSAL)
   {
      return CE_ModeReversal(f,entry,why);
   }
   return CE_ModeRetest(f,entry,why);
}

double CE_CalcLots(const SZoneFacts &f, const double risk_scale, const double entry, const double sl)
{
   double risk=MathAbs(entry-sl);
   if(risk<=0.0 || f.point<=0.0 || f.tick_value<=0.0 || f.equity<=0.0)
   {
      return 0.0;
   }
   double risk_money=f.equity*InpRiskPercent/100.0*risk_scale;
   double per_lot=risk/f.point*f.tick_value;
   if(per_lot<=0.0 || InpLotStep<=0.0)
   {
      return 0.0;
   }
   double lots=risk_money/per_lot;
   lots=MathFloor(lots/InpLotStep)*InpLotStep;
   lots=MathMax(InpMinLots,MathMin(InpMaxLots,lots));
   return lots;
}

double CE_BreakEvenSl(const double entry, const int dir, const double spread)
{
   if(dir>0)
   {
      return entry-spread;
   }
   return entry+spread;
}

void CE_BuildPlan(const SZoneFacts &f, SScoreResult &r)
{
   r.entry_mode=CE_EntryModeName(f.mode);
   double entry=0.0;
   string mode_why="";
   bool mode_ok=CE_ModeEvaluate(f.mode,f,entry,mode_why);
   r.plan_why=mode_why;
   if(mode_ok==false)
   {
      r.plan_ready=false;
      CE_SetReject(r,"ENTRY_MODE_NOT_READY");
      r.reject_values=CE_BuildRejectValues(f,r)+";mode_why="+CE_LogToken(mode_why);
      return;
   }
   double buffer=f.atr_m1*InpAtrBuffer;
   if(buffer<=0.0)
   {
      buffer=f.point*10.0;
   }
   double sl=0.0;
   if(f.direction>0)
   {
      sl=f.lo-buffer;
      if(f.invalidation>0.0)
      {
         sl=MathMin(sl,f.invalidation-buffer);
      }
   }
   else
   {
      sl=f.hi+buffer;
      if(f.invalidation>0.0)
      {
         sl=MathMax(sl,f.invalidation+buffer);
      }
   }
   double min_stop=((double)f.min_stop_points+(double)f.stops_level+(double)f.freeze_level)*f.point;
   if(MathAbs(entry-sl)<min_stop)
   {
      sl=(f.direction>0 ? entry-min_stop : entry+min_stop);
   }
   double risk=MathAbs(entry-sl);
   double reward=risk*InpTpRRMultiple;
   double final_tp=(f.direction>0 ? entry+reward : entry-reward);
   double partial=final_tp;
   if(f.nearest_liquidity>0.0)
   {
      double rr_liq=MathAbs(f.nearest_liquidity-entry)/risk;
      bool right_side=(f.direction>0 ? f.nearest_liquidity>entry : f.nearest_liquidity<entry);
      if(rr_liq>=InpMinRRAtFill && right_side)
      {
         partial=f.nearest_liquidity;
      }
      else
      {
         partial=(f.direction>0 ? entry+risk*InpMinRRAtFill : entry-risk*InpMinRRAtFill);
      }
   }
   if(f.direction>0)
   {
      partial=MathMin(partial,final_tp);
   }
   else
   {
      partial=MathMax(partial,final_tp);
   }
   double trail=CE_BreakEvenSl(entry,f.direction,f.spread_price);
   double lots=CE_CalcLots(f,r.risk_scale,entry,sl);
   r.plan_ready=true;
   r.entry_price=entry;
   r.sl=sl;
   r.tp=final_tp;
   r.partial_tp=partial;
   r.trail_sl=trail;
   r.risk=risk;
   r.lots=lots;
   if(lots<=0.0)
   {
      CE_SetReject(r,"LOT_SIZE_INVALID");
   }
   r.reject_values=CE_BuildRejectValues(f,r)+";lots="+DoubleToString(lots,2)+";entry="+DoubleToString(entry,2);
}

void CE_EvaluateZone(const SZoneFacts &f, const SAccountState &a, SScoreResult &r)
{
   CE_ScoreComponents(f,r);
   CE_ApplyDecision(f,a,r);
   CE_BuildPlan(f,r);
   r.reject_values=CE_BuildRejectValues(f,r);
}

// ---------------------------------------------------------------- log / CSV / panel
string CE_FormatLogLine(const SZoneRecord &z, const SScoreResult &r, const datetime utc)
{
   string s="CE|utc="+IntegerToString((long)utc);
   s+="|dza_hour="+IntegerToString((long)CE_UtcToAlgeriaHour(utc));
   s+="|session="+CE_SessionName(r.session);
   s+="|zone="+CE_LogToken(z.id);
   s+="|state="+CE_StateText(z.state);
   s+="|dir="+CE_DirectionText(z.direction);
   s+="|kind="+CE_KindText(z.kind);
   s+="|q="+DoubleToString(r.q_pts,2)+"/20";
   s+="|liq="+DoubleToString(r.liq_pts,2)+"/15";
   s+="|struct="+DoubleToString(r.struct_pts,2)+"/20";
   s+="|htf="+DoubleToString(r.htf_pts,2)+"/15";
   s+="|vol="+DoubleToString(r.vol_pts,2)+"/10";
   s+="|sess="+DoubleToString(r.session_pts,2)+"/10";
   s+="|exec="+DoubleToString(r.exec_pts,2)+"/10";
   s+="|ai="+DoubleToString(r.ai_pts,2)+"/"+DoubleToString(r.ai_max,2);
   s+="|raw="+DoubleToString(r.raw_total,2);
   s+="|avail="+DoubleToString(r.available_max,2);
   s+="|total="+IntegerToString((long)r.total);
   s+="|tier="+r.tier_text;
   s+="|decision="+r.decision;
   s+="|reject="+r.reject_code;
   s+="|values="+CE_LogToken(r.reject_values);
   s+="|action="+r.order_action;
   s+="|mode="+r.entry_mode;
   s+="|plan="+CE_BoolText(r.plan_ready);
   s+="|plan_why="+CE_LogToken(r.plan_why);
   s+="|entry="+DoubleToString(r.entry_price,2);
   s+="|sl="+DoubleToString(r.sl,2);
   s+="|tp="+DoubleToString(r.tp,2);
   s+="|partial_tp="+DoubleToString(r.partial_tp,2);
   s+="|trail_sl="+DoubleToString(r.trail_sl,2);
   s+="|risk="+DoubleToString(r.risk,2);
   s+="|risk_scale="+DoubleToString(r.risk_scale,2);
   s+="|lots="+DoubleToString(r.lots,2);
   s+="|account_ok="+CE_BoolText(r.account_ok);
   s+="|account_why="+CE_LogToken(r.account_why);
   s+="|htf_penalty="+DoubleToString(r.htf_penalty,2);
   s+="|ai_used="+CE_BoolText(r.ai_max>0.0);
   s+="|ai_why="+CE_LogToken(r.ai_why);
   s+="|ai_reasons="+CE_LogToken(r.ai_reasons);
   s+="|ai_invalidation="+CE_LogToken(r.ai_invalidation);
   return s;
}

string CE_CsvHeader()
{
   return "utc,dza_hour,session,zone,state,dir,kind,q,liq,struct,htf,vol,sess,exec,ai,ai_max,raw,avail,total,tier,decision,reject,values,action,mode,plan,plan_why,entry,sl,tp,partial_tp,trail_sl,risk,risk_scale,lots,account_ok,account_why,htf_penalty,ai_used,ai_why,ai_reasons,ai_invalidation";
}

string CE_FormatCsvRow(const SZoneRecord &z, const SScoreResult &r, const datetime utc)
{
   string s="";
   s+=CE_CsvToken(IntegerToString((long)utc)); s+=",";
   s+=CE_CsvToken(IntegerToString((long)CE_UtcToAlgeriaHour(utc))); s+=",";
   s+=CE_CsvToken(CE_SessionName(r.session)); s+=",";
   s+=CE_CsvToken(z.id); s+=",";
   s+=CE_CsvToken(CE_StateText(z.state)); s+=",";
   s+=CE_CsvToken(CE_DirectionText(z.direction)); s+=",";
   s+=CE_CsvToken(CE_KindText(z.kind)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.q_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.liq_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.struct_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.htf_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.vol_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.session_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.exec_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.ai_pts,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.ai_max,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.raw_total,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.available_max,2)); s+=",";
   s+=CE_CsvToken(IntegerToString((long)r.total)); s+=",";
   s+=CE_CsvToken(r.tier_text); s+=",";
   s+=CE_CsvToken(r.decision); s+=",";
   s+=CE_CsvToken(r.reject_code); s+=",";
   s+=CE_CsvToken(r.reject_values); s+=",";
   s+=CE_CsvToken(r.order_action); s+=",";
   s+=CE_CsvToken(r.entry_mode); s+=",";
   s+=CE_CsvToken(CE_BoolText(r.plan_ready)); s+=",";
   s+=CE_CsvToken(r.plan_why); s+=",";
   s+=CE_CsvToken(DoubleToString(r.entry_price,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.sl,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.tp,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.partial_tp,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.trail_sl,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.risk,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.risk_scale,2)); s+=",";
   s+=CE_CsvToken(DoubleToString(r.lots,2)); s+=",";
   s+=CE_CsvToken(CE_BoolText(r.account_ok)); s+=",";
   s+=CE_CsvToken(r.account_why); s+=",";
   s+=CE_CsvToken(DoubleToString(r.htf_penalty,2)); s+=",";
   s+=CE_CsvToken(CE_BoolText(r.ai_max>0.0)); s+=",";
   s+=CE_CsvToken(r.ai_why); s+=",";
   s+=CE_CsvToken(r.ai_reasons); s+=",";
   s+=CE_CsvToken(r.ai_invalidation);
   return s;
}

string CE_PanelBreakdown(const SScoreResult &r)
{
   string s="q="+DoubleToString(r.q_pts,1);
   s+=" liq="+DoubleToString(r.liq_pts,1);
   s+=" str="+DoubleToString(r.struct_pts,1);
   s+=" htf="+DoubleToString(r.htf_pts,1);
   s+=" vol="+DoubleToString(r.vol_pts,1);
   s+=" sess="+DoubleToString(r.session_pts,1);
   s+=" exec="+DoubleToString(r.exec_pts,1);
   s+=" ai="+DoubleToString(r.ai_pts,1);
   return s;
}

void CE_UpdatePanel(const SZoneRecord &z, const SScoreResult &r)
{
   g_last_decision=r.decision;
   g_last_reject=r.reject_code;
   g_last_score=r.total;
   g_last_zone=z.id;
   if(r.total<=g_top_score[2])
   {
      return;
   }
   int slot=2;
   if(r.total>g_top_score[0])      { slot=0; }
   else if(r.total>g_top_score[1]) { slot=1; }
   for(int k=2; k>slot; k--)
   {
      g_top_score[k]=g_top_score[k-1];
      g_top_zone[k]=g_top_zone[k-1];
      g_top_breakdown[k]=g_top_breakdown[k-1];
   }
   g_top_score[slot]=r.total;
   g_top_zone[slot]=z.id;
   g_top_breakdown[slot]=CE_PanelBreakdown(r);
}

void CE_RenderPanel(const datetime utc)
{
   string panel="CONFIRMATION SCORE ENGINE\n";
   panel+="UTC="+IntegerToString((long)utc)+"  DZA="+IntegerToString((long)CE_UtcToAlgeriaHour(utc))+
          "  session="+CE_SessionName(CE_SessionOfUtc(utc))+"\n";
   panel+="dry_run="+CE_BoolText(InpDryRun)+"  live_orders="+CE_BoolText(InpAllowLiveOrders)+
          "  kill="+CE_BoolText(InpKillSwitch)+"  daily_lock="+CE_BoolText(g_daily_lock)+"\n";
   for(int k=0; k<3; k++)
   {
      panel+="TOP"+IntegerToString((long)(k+1))+"="+CE_LogToken(g_top_zone[k])+
             " score="+IntegerToString((long)g_top_score[k])+" | "+g_top_breakdown[k]+"\n";
   }
   panel+="LAST="+CE_LogToken(g_last_zone)+" score="+IntegerToString((long)g_last_score)+
          " decision="+g_last_decision+" reject="+g_last_reject;
   Comment(panel);
   ChartRedraw(0);
}

// ---------------------------------------------------------------- terminal file helpers
bool CE_ReadWholeFile(const string &path, string &out)
{
   out="";
   int h=FileOpen(path,FILE_READ|FILE_TXT|FILE_COMMON);
   if(h==INVALID_HANDLE)
   {
      return false;
   }
   while(!FileIsEnding(h))
   {
      out+=FileReadString(h);
      if(!FileIsEnding(h))
      {
         out+="\n";
      }
   }
   if(StringLen(out)>0 && StringGetCharacter(out,StringLen(out)-1)!=10)
   {
      out+="\n";
   }
   FileClose(h);
   return true;
}

bool CE_ReadWholeFileWithTimeout(const string &path, const int timeout_ms, string &out, string &why)
{
   out="";
   why="AI_FILE_READ_OK";
   int h=FileOpen(path,FILE_READ|FILE_TXT|FILE_COMMON);
   if(h==INVALID_HANDLE)
   {
      why="AI_FILE_MISSING";
      return false;
   }
   uint start=GetTickCount();
   while(!FileIsEnding(h))
   {
      out+=FileReadString(h);
      if(!FileIsEnding(h))
      {
         out+="\n";
      }
   }
   if(StringLen(out)>0 && StringGetCharacter(out,StringLen(out)-1)!=10)
   {
      out+="\n";
   }
   uint elapsed=GetTickCount()-start;
   FileClose(h);
   if(elapsed>(uint)timeout_ms)
   {
      why="AI_TIMEOUT";
      return false;
   }
   return true;
}

void CE_WriteWholeFile(const string &path, const string &data)
{
   int h=FileOpen(path,FILE_WRITE|FILE_TXT|FILE_COMMON);
   if(h==INVALID_HANDLE)
   {
      return;
   }
   FileWriteString(h,data);
   FileFlush(h);
   FileClose(h);
}

// ---------------------------------------------------------------- terminal market helpers
double CE_TrueRangeAtShift(const ENUM_TIMEFRAMES tf, const int shift)
{
   double h=iHigh(_Symbol,tf,shift);
   double l=iLow(_Symbol,tf,shift);
   double pc=iClose(_Symbol,tf,shift+1);
   double a=h-l;
   double b=MathAbs(h-pc);
   double c=MathAbs(l-pc);
   return MathMax(a,MathMax(b,c));
}

double CE_AtrFromTerminal(const ENUM_TIMEFRAMES tf, const int period)
{
   double sum=0.0;
   for(int k=1; k<=period; k++)
   {
      sum+=CE_TrueRangeAtShift(tf,k);
   }
   if(period<=0)
   {
      return 0.0;
   }
   return sum/(double)period;
}

double CE_Percentile(const double &values[], const int count, const double current)
{
   if(count<=0)
   {
      return 50.0;
   }
   int below=0;
   for(int k=0; k<count; k++)
   {
      if(values[k]<=current)
      {
         below++;
      }
   }
   return (double)below*100.0/(double)count;
}

double CE_AtrPercentileTerminal(const int period, const int lookback)
{
   double values[];
   ArrayResize(values,lookback);
   for(int k=0; k<lookback; k++)
   {
      values[k]=CE_TrueRangeAtShift(PERIOD_M1,k+1);
   }
   return CE_Percentile(values,lookback,CE_TrueRangeAtShift(PERIOD_M1,1));
}

int CE_BiasOf(const ENUM_TIMEFRAMES tf, const int lookback)
{
   double atr=CE_AtrFromTerminal(tf,CE_AtrPeriodFromInput());
   double c1=iClose(_Symbol,tf,1);
   double c2=iClose(_Symbol,tf,lookback);
   double diff=c1-c2;
   double threshold=atr*0.5;
   if(threshold<=0.0)
   {
      return 0;
   }
   if(diff>threshold)  { return 1; }
   if(diff<-threshold) { return -1; }
   return 0;
}

int CE_AtrPeriodFromInput()
{
   return InpAtrPeriod;
}

bool CE_EqualHighs(const int lookback, const double tol, double &level)
{
   level=0.0;
   double h1=iHigh(_Symbol,PERIOD_M5,1);
   for(int k=2; k<=lookback; k++)
   {
      double h2=iHigh(_Symbol,PERIOD_M5,k);
      if(MathAbs(h1-h2)<=tol)
      {
         level=MathMax(h1,h2);
         return true;
      }
   }
   return false;
}

bool CE_EqualLows(const int lookback, const double tol, double &level)
{
   level=0.0;
   double l1=iLow(_Symbol,PERIOD_M5,1);
   for(int k=2; k<=lookback; k++)
   {
      double l2=iLow(_Symbol,PERIOD_M5,k);
      if(MathAbs(l1-l2)<=tol)
      {
         level=MathMin(l1,l2);
         return true;
      }
   }
   return false;
}

void CE_LiquidityContext(const int dir, const double price, const double lo, const double hi,
                         const double atr, bool &asia_sweep, bool &london_sweep,
                         bool &bsl_ssl, bool &eqh_eql, bool &sweep_before_reaction)
{
   asia_sweep=false;
   london_sweep=false;
   bsl_ssl=false;
   eqh_eql=false;
   sweep_before_reaction=false;
   double tol=atr*0.25;
   if(tol<=0.0)
   {
      tol=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   }
   double eq_high=0.0;
   double eq_low=0.0;
   bool eqh=CE_EqualHighs(20,tol,eq_high);
   bool eql=CE_EqualLows(20,tol,eq_low);
   eqh_eql=(eqh || eql);
   double recent_high=iHigh(_Symbol,PERIOD_M15,1);
   double recent_low=iLow(_Symbol,PERIOD_M15,1);
   for(int k=2; k<=24; k++)
   {
      recent_high=MathMax(recent_high,iHigh(_Symbol,PERIOD_M15,k));
      recent_low=MathMin(recent_low,iLow(_Symbol,PERIOD_M15,k));
   }
   double last_close=iClose(_Symbol,PERIOD_M1,1);
   if((dir>0 && last_close>recent_high) || (dir<0 && last_close<recent_low))
   {
      bsl_ssl=true;
   }
   datetime bar_server=iTime(_Symbol,PERIOD_M1,1);
   datetime bar_utc=CE_ServerToUtc(bar_server,InpBrokerUtcOffsetWinterMinutes,
                                   InpBrokerUtcOffsetSummerMinutes,InpBrokerUsesEuDst);
   int sess=CE_SessionOfUtc(bar_utc);
   if(sess==CE_SESSION_ASIA && bsl_ssl)     { asia_sweep=true; }
   if(sess==CE_SESSION_LONDON && bsl_ssl)   { london_sweep=true; }
   if(bsl_ssl && ((dir>0 && last_close>hi) || (dir<0 && last_close<lo)))
   {
      sweep_before_reaction=true;
   }
}

void CE_StructureContext(const int dir, const double lo, const double hi, const double atr,
                         bool &m1_choch, bool &m5_bos, bool &confirmation_close,
                         bool &second_reaction, bool &sweep, bool &closed_beyond,
                         bool &micro_bos, bool &first_pullback, double &pullback_price,
                         double &second_reaction_price, double &chase_distance, double &momentum_close)
{
   m1_choch=false;
   m5_bos=false;
   confirmation_close=false;
   second_reaction=false;
   sweep=false;
   closed_beyond=false;
   micro_bos=false;
   first_pullback=false;
   pullback_price=0.0;
   second_reaction_price=0.0;
   chase_distance=0.0;
   momentum_close=iClose(_Symbol,PERIOD_M1,1);
   double c1=iClose(_Symbol,PERIOD_M1,1);
   double c2=iClose(_Symbol,PERIOD_M1,2);
   double c3=iClose(_Symbol,PERIOD_M1,3);
   if((dir>0 && c2<c3 && c1>c2) || (dir<0 && c2>c3 && c1<c2))
   {
      m1_choch=true;
   }
   double h1=iHigh(_Symbol,PERIOD_M5,1);
   double h2=iHigh(_Symbol,PERIOD_M5,2);
   double l1=iLow(_Symbol,PERIOD_M5,1);
   double l2=iLow(_Symbol,PERIOD_M5,2);
   if((dir>0 && h1>h2) || (dir<0 && l1<l2))
   {
      m5_bos=true;
   }
   double bar_low=iLow(_Symbol,PERIOD_M1,1);
   double bar_high=iHigh(_Symbol,PERIOD_M1,1);
   if((dir>0 && bar_low<=hi && c1>hi) || (dir<0 && bar_high>=lo && c1<lo))
   {
      confirmation_close=true;
   }
   if((dir>0 && momentum_close>hi) || (dir<0 && momentum_close<lo))
   {
      closed_beyond=true;
      chase_distance=MathAbs(momentum_close-(dir>0 ? hi : lo));
   }
   for(int k=1; k<=3; k++)
   {
      double kh=iHigh(_Symbol,PERIOD_M1,k);
      double kl=iLow(_Symbol,PERIOD_M1,k);
      if((dir>0 && kl<lo) || (dir<0 && kh>hi))
      {
         sweep=true;
      }
   }
   if(sweep)
   {
      for(int j=2; j<=6; j++)
      {
         double jc=iClose(_Symbol,PERIOD_M1,j);
         if((dir>0 && jc>hi) || (dir<0 && jc<lo))
         {
            second_reaction=true;
            second_reaction_price=jc;
            break;
         }
      }
   }
   double prior_high=iHigh(_Symbol,PERIOD_M1,2);
   double prior_low=iLow(_Symbol,PERIOD_M1,2);
   for(int m=3; m<=5; m++)
   {
      prior_high=MathMax(prior_high,iHigh(_Symbol,PERIOD_M1,m));
      prior_low=MathMin(prior_low,iLow(_Symbol,PERIOD_M1,m));
   }
   if((dir>0 && c1>prior_high) || (dir<0 && c1<prior_low))
   {
      micro_bos=true;
   }
   if(closed_beyond)
   {
      double zone_edge=(dir>0 ? hi : lo);
      double dist=MathAbs(momentum_close-zone_edge);
      if(dist<=MathMax(atr*0.5,SymbolInfoDouble(_Symbol,SYMBOL_POINT)))
      {
         first_pullback=true;
         pullback_price=momentum_close;
      }
   }
   if(second_reaction_price<=0.0)
   {
      second_reaction_price=c1;
   }
}

void CE_ProfileLevels(const int lookback, double &poc, double &vah, double &val)
{
   poc=0.0;
   vah=0.0;
   val=0.0;
   double total_vol=0.0;
   double weighted=0.0;
   for(int k1=1; k1<=lookback; k1++)
   {
      double v=(double)iVolume(_Symbol,PERIOD_M5,k1);
      if(v<0.0)
      {
         v=0.0;
      }
      total_vol+=v;
      weighted+=iClose(_Symbol,PERIOD_M5,k1)*v;
   }
   if(total_vol<=0.0)
   {
      return;
   }
   poc=weighted/total_vol;
   double dev=0.0;
   for(int k2=1; k2<=lookback; k2++)
   {
      double v2=(double)iVolume(_Symbol,PERIOD_M5,k2);
      if(v2<0.0)
      {
         v2=0.0;
      }
      dev+=MathAbs(iClose(_Symbol,PERIOD_M5,k2)-poc)*v2;
   }
   double spread=dev/total_vol*0.5;
   val=poc-spread;
   vah=poc+spread;
}

void CE_ProfileReaction(const double price, const double atr, bool &poc_reaction, bool &vah_val_reaction)
{
   poc_reaction=false;
   vah_val_reaction=false;
   double poc=0.0;
   double vah=0.0;
   double val=0.0;
   CE_ProfileLevels(InpProfileLookbackBars,poc,vah,val);
   double tol=atr*0.25;
   if(tol<=0.0)
   {
      tol=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   }
   if(poc>0.0 && MathAbs(price-poc)<=tol)
   {
      poc_reaction=true;
   }
   if(vah>0.0 && (MathAbs(price-vah)<=tol || MathAbs(price-val)<=tol))
   {
      vah_val_reaction=true;
   }
}

bool CE_VolumeExpansion()
{
   double recent=0.0;
   double base=0.0;
   for(int k=1; k<=3; k++)
   {
      recent+=(double)iVolume(_Symbol,PERIOD_M1,k);
   }
   for(int j=4; j<=23; j++)
   {
      base+=(double)iVolume(_Symbol,PERIOD_M1,j);
   }
   base/=20.0;
   if(base<=0.0)
   {
      return false;
   }
   return (recent/3.0>base*1.5);
}

double CE_NearestLiquidity(const int dir, const double price, const int lookback, const double atr)
{
   double best=0.0;
   for(int k=1; k<=lookback; k++)
   {
      double h=iHigh(_Symbol,PERIOD_M5,k);
      double l=iLow(_Symbol,PERIOD_M5,k);
      if(dir>0 && h>price)
      {
         if(best==0.0 || h<best)
         {
            best=h;
         }
      }
      if(dir<0 && l<price)
      {
         if(best==0.0 || l>best)
         {
            best=l;
         }
      }
   }
   if(best==0.0)
   {
      best=price+(double)dir*atr*3.0;
   }
   return best;
}

void CE_LoadAIOpinion(const datetime utc, SZoneFacts &f)
{
   f.ai_used=false;
   f.ai_direction=0;
   f.ai_confidence=0.0;
   f.ai_reasons="";
   f.ai_invalidation="";
   f.ai_as_of=0;
   if(InpUseAIAgent==false)
   {
      f.ai_why="AI_DISABLED";
      return;
   }
   string json="";
   string read_why="";
   bool read_ok=CE_ReadWholeFileWithTimeout(InpAIFile,InpAITimeoutMs,json,read_why);
   if(read_ok==false)
   {
      f.ai_why=read_why;
      return;
   }
   SAIOpinion ai;
   CE_InitAIOpinion(ai);
   CE_ParseAIOpinion(json,utc,InpAIMaxAgeSec,ai);
   f.ai_why=ai.why;
   f.ai_used=ai.valid;
   f.ai_direction=ai.direction;
   f.ai_confidence=ai.confidence;
   f.ai_reasons=ai.reasons;
   f.ai_invalidation=ai.invalidation;
   f.ai_as_of=ai.as_of;
}

void CE_BuildFacts(const SZoneRecord &z, const datetime utc, SZoneFacts &f)
{
   CE_InitFacts(f);
   f.direction=z.direction;
   f.kind=z.kind;
   f.state=z.state;
   f.lo=z.lo;
   f.hi=z.hi;
   f.born_utc=z.born_utc;
   f.now_utc=utc;
   f.age_hours=(double)(utc-z.born_utc)/3600.0;
   f.touches=z.touches;
   f.mode=InpEntryMode;
   f.retest_percent=InpRetestEntryPercent/100.0;
   f.max_chase_atr=InpMaxChaseATR;
   f.min_stop_points=InpMinStopPoints;
   f.stops_level=(int)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL);
   f.freeze_level=(int)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   f.point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   f.tick_value=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   f.equity=AccountInfoDouble(ACCOUNT_EQUITY);
   f.bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   f.ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   f.current_price=(f.direction>0 ? f.ask : f.bid);
   f.spread_points=(double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD);
   f.spread_price=f.ask-f.bid;
   f.atr_m1=CE_AtrFromTerminal(PERIOD_M1,InpAtrPeriod);
   if(f.atr_m1<=0.0)
   {
      f.atr_m1=f.point*10.0;
   }
   f.atr_percentile=CE_AtrPercentileTerminal(InpAtrPeriod,InpAtrPercentileLookback);
   f.zone_atr_ratio=(f.hi-f.lo)/f.atr_m1;
   f.spread_atr_pct=f.spread_price/f.atr_m1*100.0;
   f.invalidation=(f.direction>0 ? f.lo-f.atr_m1*InpInvalidationATR : f.hi+f.atr_m1*InpInvalidationATR);
   f.nearest_liquidity=CE_NearestLiquidity(f.direction,f.current_price,InpLiquidityLookbackBars,f.atr_m1);
   f.room_to_liquidity=MathAbs(f.nearest_liquidity-f.current_price);
   double prelim_risk=MathAbs(f.current_price-f.invalidation)+f.atr_m1*InpAtrBuffer;
   if(prelim_risk<=0.0)
   {
      prelim_risk=f.atr_m1;
   }
   f.rr_at_fill=f.room_to_liquidity/prelim_risk;
   f.session=CE_SessionOfUtc(utc);
   f.session_entry_allowed=CE_SessionEntryAllowed(f.session,InpAllowAsiaEntries,InpAllowOffPeakEntries);
   f.h1_bias=CE_BiasOf(PERIOD_H1,InpHtfLookbackBars);
   f.h4_bias=CE_BiasOf(PERIOD_H4,InpHtfLookbackBars);
   f.htf_alignment=CE_HtfAlignment(f.h1_bias,f.h4_bias,f.direction);
   CE_LiquidityContext(f.direction,f.current_price,f.lo,f.hi,f.atr_m1,
                       f.asia_sweep,f.london_sweep,f.bsl_ssl,f.eqh_eql,f.sweep_before_reaction);
   CE_StructureContext(f.direction,f.lo,f.hi,f.atr_m1,f.m1_choch,f.m5_bos,
                       f.confirmation_close,f.second_reaction,f.sweep,f.closed_beyond_zone,
                       f.micro_bos,f.first_pullback,f.pullback_price,f.second_reaction_price,
                       f.chase_distance,f.momentum_close);
   CE_ProfileReaction(f.current_price,f.atr_m1,f.poc_reaction,f.vah_val_reaction);
   f.volume_expansion=CE_VolumeExpansion();
   CE_LoadAIOpinion(utc,f);
}

// ---------------------------------------------------------------- persistent state
void CE_LoadPersistentState()
{
   g_day_key=0;
   g_day_start_equity=0.0;
   g_daily_lock=false;
   g_trades_today=0;
   g_last_entry_utc=0;
   if(GlobalVariableCheck("CE_DailyLock"))
   {
      g_daily_lock=(GlobalVariableGet("CE_DailyLock")>0.5);
   }
   if(GlobalVariableCheck("CE_DayKey"))
   {
      g_day_key=(long)GlobalVariableGet("CE_DayKey");
   }
   if(GlobalVariableCheck("CE_DayStartEquity"))
   {
      g_day_start_equity=GlobalVariableGet("CE_DayStartEquity");
   }
   if(GlobalVariableCheck("CE_TradesToday"))
   {
      g_trades_today=(int)GlobalVariableGet("CE_TradesToday");
   }
   if(GlobalVariableCheck("CE_LastEntryUtc"))
   {
      g_last_entry_utc=(datetime)GlobalVariableGet("CE_LastEntryUtc");
   }
}

void CE_RefreshDailyState(const datetime utc, const double equity)
{
   long day=utc/86400;
   if(day!=g_day_key)
   {
      g_day_key=day;
      g_day_start_equity=equity;
      g_daily_lock=false;
      g_trades_today=0;
      g_last_entry_utc=0;
      GlobalVariableSet("CE_DayKey",(double)day);
      GlobalVariableSet("CE_DayStartEquity",equity);
      GlobalVariableSet("CE_DailyLock",0.0);
      GlobalVariableSet("CE_TradesToday",0.0);
      GlobalVariableSet("CE_LastEntryUtc",0.0);
   }
   if(g_day_start_equity<=0.0 && equity>0.0)
   {
      g_day_start_equity=equity;
      GlobalVariableSet("CE_DayStartEquity",equity);
   }
   if(g_day_start_equity>0.0 && equity>0.0)
   {
      double dd=(g_day_start_equity-equity)/g_day_start_equity*100.0;
      if(dd>=InpMaxDailyLossPercent)
      {
         g_daily_lock=true;
         GlobalVariableSet("CE_DailyLock",1.0);
      }
   }
}

void CE_RecordEntry(const datetime utc)
{
   g_trades_today++;
   g_last_entry_utc=utc;
   GlobalVariableSet("CE_TradesToday",(double)g_trades_today);
   GlobalVariableSet("CE_LastEntryUtc",(double)utc);
}

void CE_RecordPositionPlan(const ulong ticket, const double final_tp, const double partial_tp)
{
   string key_final="CE_FinalTP_"+IntegerToString((long)ticket);
   string key_partial="CE_PartialTP_"+IntegerToString((long)ticket);
   GlobalVariableSet(key_final,final_tp);
   GlobalVariableSet(key_partial,partial_tp);
}

void CE_BuildAccountState(const datetime utc, SAccountState &a)
{
   CE_InitAccount(a);
   a.master_enable=InpMasterEnable;
   a.dry_run=InpDryRun;
   a.allow_live=InpAllowLiveOrders;
   a.allow_real=InpAllowRealTrading;
   a.kill_switch=InpKillSwitch;
   a.daily_lock=g_daily_lock;
   a.real_account=(AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL);
   a.positions=PositionsTotal();
   a.trades_today=g_trades_today;
   a.max_concurrent=InpMaxConcurrentTrades;
   a.max_trades=InpMaxTradesPerDay;
   a.equity=AccountInfoDouble(ACCOUNT_EQUITY);
   a.day_start_equity=g_day_start_equity;
   a.max_daily_loss_pct=InpMaxDailyLossPercent;
   a.now_utc=utc;
   a.last_entry_utc=g_last_entry_utc;
   a.cooldown_minutes=InpCooldownMinutes;
}

bool CE_AccountPermissionsOk(string &why)
{
   why="PERMISSIONS_OK";
   if(InpAllowLiveOrders==false)                                  { why="LIVE_ORDERS_DISABLED"; return false; }
   if(InpAllowRealTrading==false && AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL)
   {
      why="REAL_REFUSED"; return false;
   }
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL) { why="REAL_REFUSED"; return false; }
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_CONTEST) { why="CONTEST_REFUSED"; return false; }
   if(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)!=1)            { why="ACCOUNT_TRADE_DISABLED"; return false; }
   if(AccountInfoInteger(ACCOUNT_TRADE_EXPERT)!=1)             { why="EXPERTS_DISABLED"; return false; }
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)!=1)          { why="TERMINAL_TRADE_DISABLED"; return false; }
   if(MQLInfoInteger(MQL_TRADE_ALLOWED)!=1)                    { why="MQL_TRADE_DISABLED"; return false; }
   return true;
}

bool CE_IsSuccessRetcode(const uint rc)
{
   if(rc==TRADE_RETCODE_DONE)         { return true; }
   if(rc==TRADE_RETCODE_PLACED)       { return true; }
   if(rc==TRADE_RETCODE_DONE_PARTIAL) { return true; }
   return false;
}

bool CE_IsTransientRetcode(const uint rc)
{
   if(rc==TRADE_RETCODE_REQUOTE)          { return true; }
   if(rc==TRADE_RETCODE_TIMEOUT)          { return true; }
   if(rc==TRADE_RETCODE_PRICE_CHANGED)    { return true; }
   if(rc==TRADE_RETCODE_PRICE_OFF)        { return true; }
   if(rc==TRADE_RETCODE_TOO_MANY_REQUESTS){ return true; }
   if(rc==TRADE_RETCODE_CONNECTION)       { return true; }
   if(rc==TRADE_RETCODE_LOCKED)           { return true; }
   if(rc==TRADE_RETCODE_FROZEN)           { return true; }
   if(rc==TRADE_RETCODE_INVALID_FILL)     { return true; }
   return false;
}

void CE_PlaceOrder(const SZoneFacts &f, const SAccountState &a, SScoreResult &r, const datetime utc)
{
   if(r.decision=="ENTER_DRY_RUN" || a.dry_run || a.allow_live==false)
   {
      r.order_action="DRY_RUN";
      return;
   }
   if(r.decision!="ENTER")
   {
      return;
   }
   string perm_why="";
   if(CE_AccountPermissionsOk(perm_why)==false)
   {
      CE_SetReject(r,perm_why);
      r.reject_values=CE_BuildRejectValues(f,r)+";perm_why="+CE_LogToken(perm_why);
      return;
   }
   if(r.plan_ready==false || r.lots<=0.0)
   {
      CE_SetReject(r,"PLAN_NOT_READY");
      r.reject_values=CE_BuildRejectValues(f,r);
      return;
   }
   bool use_limit=(f.mode==CE_MODE_RETEST && InpUseLimitOrders);
   bool placed=false;
   uint rc=0;
   for(int attempt=0; attempt<=InpMaxOrderRetries; attempt++)
   {
      bool ok=false;
      if(use_limit)
      {
         ENUM_ORDER_TYPE order_type=(f.direction>0 ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT);
         ok=g_trade.OrderOpen(_Symbol,order_type,r.lots,0.0,r.entry_price,r.sl,r.partial_tp,
                              ORDER_TIME_GTC,0,InpTradeComment);
      }
      else
      {
         if(f.direction>0)
         {
            ok=g_trade.Buy(r.lots,_Symbol,0.0,r.sl,r.partial_tp,InpTradeComment);
         }
         else
         {
            ok=g_trade.Sell(r.lots,_Symbol,0.0,r.sl,r.partial_tp,InpTradeComment);
         }
      }
      rc=g_trade.ResultRetcode();
      if(ok==false && rc==0)
      {
         rc=TRADE_RETCODE_ERROR;
      }
      if(CE_IsSuccessRetcode(rc))
      {
         placed=true;
         break;
      }
      if(CE_IsTransientRetcode(rc)==false)
      {
         break;
      }
   }
   if(placed)
   {
      ulong ticket=g_trade.ResultOrder();
      CE_RecordPositionPlan(ticket,r.tp,r.partial_tp);
      CE_RecordEntry(utc);
      r.decision="ENTER";
      r.reject_code="NONE";
      r.order_action=(use_limit ? "LIMIT_PLACED" : "MARKET_FILLED");
      r.reject_values=CE_BuildRejectValues(f,r)+";ticket="+IntegerToString((long)ticket);
      return;
   }
   CE_SetReject(r,"ORDER_REJECTED_"+IntegerToString((long)rc));
   r.reject_values=CE_BuildRejectValues(f,r)+";retcode="+IntegerToString((long)rc)+
                    ";perm_why="+CE_LogToken(perm_why);
}

void CE_ManagePositions(const datetime utc)
{
   // The executor is disarmed by default; managing an existing same-magic
   // position is still a mutating trade action. Dry-run and no-live-orders
   // must short-circuit the whole path before PositionModify/ClosePartial.
   if(InpDryRun || InpAllowLiveOrders==false)
   {
      return;
   }
   double point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   double tick_value=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   double spread=SymbolInfoDouble(_Symbol,SYMBOL_ASK)-SymbolInfoDouble(_Symbol,SYMBOL_BID);
   int total=PositionsTotal();
   for(int idx=total-1; idx>=0; idx--)
   {
      ulong ticket=PositionGetTicket(idx);
      if(ticket==0)
      {
         continue;
      }
      if(PositionSelectByTicket(ticket)==false)
      {
         continue;
      }
      if(PositionGetInteger(POSITION_MAGIC)!=(long)InpMagic)
      {
         continue;
      }
      int type=(int)PositionGetInteger(POSITION_TYPE);
      int dir=(type==POSITION_TYPE_BUY ? 1 : -1);
      double open=PositionGetDouble(POSITION_PRICE_OPEN);
      double vol=PositionGetDouble(POSITION_VOLUME);
      double sl=PositionGetDouble(POSITION_SL);
      double tp_now=PositionGetDouble(POSITION_TP);
      double profit=PositionGetDouble(POSITION_PROFIT);
      double current=PositionGetDouble(POSITION_PRICE_CURRENT);
      double risk=MathAbs(open-sl);
      if(risk<=0.0 || point<=0.0 || tick_value<=0.0)
      {
         continue;
      }
      double risk_money=risk/point*tick_value*vol;
      if(risk_money<=0.0)
      {
         continue;
      }
      double r_mult=profit/risk_money;
      double be=CE_BreakEvenSl(open,dir,spread);
      if(r_mult>=InpBreakEvenAtR)
      {
         if(dir>0 && sl<be)
         {
            g_trade.PositionModify(ticket,be,tp_now);
         }
         if(dir<0 && (sl==0.0 || sl>be))
         {
            g_trade.PositionModify(ticket,be,tp_now);
         }
      }
      string key_done="CE_PartialDone_"+IntegerToString((long)ticket);
      string key_final="CE_FinalTP_"+IntegerToString((long)ticket);
      string key_partial="CE_PartialTP_"+IntegerToString((long)ticket);
      bool done=(GlobalVariableGet(key_done)>0.5);
      double partial_tp=GlobalVariableGet(key_partial);
      double final_tp=GlobalVariableGet(key_final);
      bool reached=(dir>0 ? current>=partial_tp : current<=partial_tp);
      if(done==false && partial_tp>0.0 && reached)
      {
         double part=MathMin(vol*InpPartialTpFraction,vol*0.90);
         if(part>0.0)
         {
            g_trade.PositionClosePartial(ticket,part);
            GlobalVariableSet(key_done,1.0);
            if(final_tp>0.0 && PositionSelectByTicket(ticket))
            {
               double sl_now=PositionGetDouble(POSITION_SL);
               g_trade.PositionModify(ticket,sl_now,final_tp);
            }
         }
      }
   }
}

void CE_CollectZones(const datetime utc)
{
   int total=ObjectsTotal(0,0,-1);
   for(int idx=0; idx<total; idx++)
   {
      string name=ObjectName(0,idx,0,-1);
      bool is_qsvp=(StringFind(name,"QSVP_ZN_")>=0);
      bool is_legacy=(StringFind(name,"Z|")==0);
      if(is_qsvp==false && is_legacy==false)
      {
         continue;
      }
      string tooltip=ObjectGetString(0,name,OBJPROP_TOOLTIP);
      double p1=ObjectGetDouble(0,name,OBJPROP_PRICE,0);
      double p2=ObjectGetDouble(0,name,OBJPROP_PRICE,1);
      long anchor_server=ObjectGetInteger(0,name,OBJPROP_TIME,0);
      datetime anchor_utc=utc;
      if(anchor_server>0)
      {
         anchor_utc=CE_ServerToUtc((datetime)anchor_server,InpBrokerUtcOffsetWinterMinutes,
                                   InpBrokerUtcOffsetSummerMinutes,InpBrokerUsesEuDst);
      }
      SZoneRecord z;
      CE_InitZone(z);
      CZoneParser parser;
      if(parser.ZP_ParseZoneObject(name,tooltip,MathMin(p1,p2),MathMax(p1,p2),anchor_utc,z))
      {
         g_reg.ZR_Upsert(z);
      }
   }
   g_reg.ZR_Expire(utc,(long)InpMaxZoneAgeHours*3600);
   string snap="";
   CE_SaveRegistrySnapshot(g_reg,snap);
   CE_WriteWholeFile(InpRegistryFile,snap);
}

void CE_EvaluateAllZones(const datetime utc)
{
   int n=g_reg.ZR_Count();
   for(int idx=0; idx<n; idx++)
   {
      SZoneRecord z;
      CE_InitZone(z);
      if(g_reg.ZR_Get(idx,z)==false)
      {
         continue;
      }
      SZoneFacts f;
      CE_InitFacts(f);
      CE_BuildFacts(z,utc,f);
      SAccountState a;
      CE_InitAccount(a);
      CE_BuildAccountState(utc,a);
      SScoreResult r;
      CE_InitScore(r);
      CE_EvaluateZone(f,a,r);
      CE_PlaceOrder(f,a,r,utc);
      string line=CE_FormatLogLine(z,r,utc);
      Print(line);
      if(InpCsvLog)
      {
         g_csv_buffer+=CE_FormatCsvRow(z,r,utc)+"\n";
      }
      g_reg.ZR_MarkEvaluated(z.id,(double)r.total,r.tier,r.decision,r.reject_code,utc);
      CE_UpdatePanel(z,r);
   }
   CE_RenderPanel(utc);
   if(InpCsvLog)
   {
      CE_WriteWholeFile(InpCsvFile,g_csv_buffer);
   }
   string snap="";
   CE_SaveRegistrySnapshot(g_reg,snap);
   CE_WriteWholeFile(InpRegistryFile,snap);
}

// ---------------------------------------------------------------- event handlers
int OnInit()
{
   long account_mode=AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(account_mode==ACCOUNT_TRADE_MODE_REAL || account_mode==ACCOUNT_TRADE_MODE_CONTEST)
   {
      Print("[CE] INIT REFUSED: REAL or CONTEST account detected - DEMO/dry-run only");
      return INIT_FAILED;
   }
   g_reg.ZR_Init();
   CE_InitPanel();
   g_last_bar=0;
   g_csv_buffer="";
   CE_LoadPersistentState();
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints((ulong)InpDeviationPoints);
   g_trade.SetTypeFilling(ORDER_FILLING_RETURN);
   string snap="";
   if(CE_ReadWholeFile(InpRegistryFile,snap))
   {
      CE_LoadRegistrySnapshot(g_reg,snap);
   }
   string csv="";
   if(CE_ReadWholeFile(InpCsvFile,csv))
   {
      g_csv_buffer=csv;
   }
   if(StringLen(g_csv_buffer)==0)
   {
      g_csv_buffer=CE_CsvHeader()+"\n";
   }
   Print("[CE] confirmation engine ON dry_run=",CE_BoolText(InpDryRun),
         " live_orders=",CE_BoolText(InpAllowLiveOrders),
         " real_refused=true csv=",CE_BoolText(InpCsvLog));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   string snap="";
   CE_SaveRegistrySnapshot(g_reg,snap);
   CE_WriteWholeFile(InpRegistryFile,snap);
   if(InpCsvLog)
   {
      CE_WriteWholeFile(InpCsvFile,g_csv_buffer);
   }
   Print("[CE] deinit reason=",IntegerToString((long)reason));
}

void OnTick()
{
   datetime bar=iTime(_Symbol,PERIOD_M1,0);
   if(bar==g_last_bar)
   {
      return;
   }
   g_last_bar=bar;
   datetime utc=CE_ServerToUtc(TimeCurrent(),InpBrokerUtcOffsetWinterMinutes,
                               InpBrokerUtcOffsetSummerMinutes,InpBrokerUsesEuDst);
   CE_RefreshDailyState(utc,AccountInfoDouble(ACCOUNT_EQUITY));
   CE_ManagePositions(utc);
   CE_CollectZones(utc);
   CE_EvaluateAllZones(utc);
}
