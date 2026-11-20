//+------------------------------------------------------------------+
//| QSMC_OpportunityFunnel.mqh                                       |
//| Diagnostics-only opportunity funnel trace (Phase B).              |
//|                                                                  |
//| CONTRACT (non-negotiable)                                        |
//|  * This module NEVER decides anything. It exposes no value that a |
//|    gate, signal path, risk check, or order path may consult.     |
//|  * It sends no orders, publishes no signals, writes no            |
//|    GlobalVariables, touches no chart objects, no indicator        |
//|    buffers, no .set, no magic numbers, no breaker state.          |
//|  * When disabled (default) it records NOTHING and prints NOTHING.  |
//|  * When enabled it records to a fixed in-memory ring + counters;  |
//|    PrintSummary()/DumpRecent() are the only I/O, and they Print   |
//|    to the terminal journal. No file I/O, no network, no GVs.      |
//|  * Compile-time and runtime both: a non-invocation costs one      |
//|    call; an invocation costs one branch + fixed writes.           |
//|                                                                  |
//| Deterministic setup IDs (FNV-1a 64) make the same bar+family+     |
//| symbol+direction map to the same ID across runs of the same       |
//| history, so traces can be diffed between builds.                  |
//|                                                                  |
//| This file is C++-subset clean so it can be built natively by      |
//| tools/test_opportunity_funnel.py with MT5 stubs. It is NOT wired  |
//| into nadir2.mq5 or QSMC_AutoTrader.mq5 yet; wiring happens in a   |
//| later, separately reviewed phase with user-verified F7 logs.      |
//+------------------------------------------------------------------+
#ifndef QSMC_OPPORTUNITY_FUNNEL_MQH
#define QSMC_OPPORTUNITY_FUNNEL_MQH

#define QSMC_OF_VERSION       "1.0.0"
#define QSMC_OF_RING_SIZE     1024
#define QSMC_OF_STAGE_COUNT   13
#define QSMC_OF_REASON_COUNT  17
#define QSMC_OF_UNIT_COUNT    9
#define QSMC_OF_SYMBOL_MAX    32
#define QSMC_OF_FAMILY_MAX    24

//--- stages (funnel order; NOT_REACHED is a verdict, not a stage) ----
enum ENUM_QSMC_OF_STAGE
{
   QSMC_OF_DATA_READY = 0,
   QSMC_OF_MARKET_EVENT,
   QSMC_OF_CANDIDATE,
   QSMC_OF_HTF_CONTEXT,
   QSMC_OF_STRUCTURE_AND_LIQUIDITY,
   QSMC_OF_ZONE_AND_GEOMETRY,
   QSMC_OF_QUALITY,
   QSMC_OF_CORE_EXPORTED,
   QSMC_OF_EA_RECEIVED,
   QSMC_OF_SESSION_ALLOWED,
   QSMC_OF_RISK_ALLOWED,
   QSMC_OF_ORDER_ATTEMPTED,
   QSMC_OF_FILL_AND_PROTECTION_VERIFIED
};

//--- verdicts per stage -------------------------------------------
enum ENUM_QSMC_OF_VERDICT
{
   QSMC_OF_NOT_REACHED = 0,   // stage never evaluated for this case (earlier blocker)
   QSMC_OF_PASS             = 1,
   QSMC_OF_REJECT           = 2,
   QSMC_OF_DATA_UNAVAILABLE = 3
};

//--- units for measured value / threshold --------------------------
enum ENUM_QSMC_OF_UNIT
{
   QSMC_OF_UNIT_NONE = 0,
   QSMC_OF_UNIT_POINTS,
   QSMC_OF_UNIT_PRICE,
   QSMC_OF_UNIT_ATR,
   QSMC_OF_UNIT_PCT,
   QSMC_OF_UNIT_TICKS,
   QSMC_OF_UNIT_SECONDS,
   QSMC_OF_UNIT_LOTS,
   QSMC_OF_UNIT_R
};

//--- stable reason codes (grep-friendly names; do NOT reuse ints) ---
enum ENUM_QSMC_OF_REASON
{
   QSMC_OF_REASON_OK = 0,               // stage passed; reason not applicable
   QSMC_OF_REASON_NOT_REACHED,          // an earlier stage blocked the chain
   QSMC_OF_REASON_NO_SETUP,             // no market setup formed this bar
   QSMC_OF_REASON_INCOMPLETE_CHAIN,     // causal chain missing required link
   QSMC_OF_REASON_RULE_REJECT,          // setup formed, rejected by strategy rules
   QSMC_OF_REASON_DATA_UNAVAILABLE,     // required series absent/insufficient
   QSMC_OF_REASON_DATA_STALE,           // data present but not fresh enough
   QSMC_OF_REASON_DATA_SHORT_READ,      // CopyBuffer short/failed read (ABI-level)
   QSMC_OF_REASON_INDICATOR_INPUT_MISMATCH, // private iCustom inputs != EA chart inputs
   QSMC_OF_REASON_SESSION,              // outside configured session window
   QSMC_OF_REASON_GUARD_ACCOUNT_WIDE,   // account-wide guard (daily loss / equity HWM)
   QSMC_OF_REASON_GUARD_EA,             // EA-magic-scoped guard
   QSMC_OF_REASON_SPREAD_TOO_WIDE,      // spread above limit at fill check
   QSMC_OF_REASON_RR_INVALID,           // RR below minimum at fill check
   QSMC_OF_REASON_BROKER_REJECT,        // OrderSend/ retcode refusal
   QSMC_OF_REASON_PROTECTION_MISSING,   // SL/TP missing or not verified after send
   QSMC_OF_REASON_INTERNAL              // funnel usage error; must never be used for gating
};

struct SOpportunityEvent
{
   ulong      id;          // deterministic FNV-1a of symbol|family|direction|bar (0 = unset)
   string     symbol;      // e.g. "XAUUSD"
   string     family;      // "CORE" | "SWEEP_RECLAIM" | "TREND_PULLBACK" | "BREAKOUT_RETEST" | "QSVP_SHADOW"
   int        direction;   // 1 buy, -1 sell, 0 n/a
   datetime   bar;         // CLOSED M15 bar open time (broker/server)
   int        stage;       // ENUM_QSMC_OF_STAGE
   int        verdict;     // ENUM_QSMC_OF_VERDICT
   int        reason;      // ENUM_QSMC_OF_REASON
   double     value;       // measured, or EMPTY_VALUE when not applicable
   double     threshold;   // limit,   or EMPTY_VALUE when not applicable
   int        unit;        // ENUM_QSMC_OF_UNIT
};

//--- module state (fixed size; no heap growth after init) ----------
bool             g_qsmc_of_enabled   = false;
uint             g_qsmc_of_seq       = 0;   // total recorded since Reset/attach
bool             g_qsmc_of_overflow  = false; // ring overwrote older detail
int              g_qsmc_of_head      = 0;   // next write position in ring
uint             g_qsmc_of_total     = 0;   // monotonic event counter
uint             g_qsmc_of_stage_verdict[QSMC_OF_STAGE_COUNT][4];
uint             g_qsmc_of_reason[QSMC_OF_REASON_COUNT];
SOpportunityEvent g_qsmc_of_ring[QSMC_OF_RING_SIZE];

//--- small helpers ---------------------------------------------------
string QSMC_OF_StageName(const int stage)
{
   switch(stage)
   {
      case QSMC_OF_DATA_READY:                    return "DATA_READY";
      case QSMC_OF_MARKET_EVENT:                  return "MARKET_EVENT";
      case QSMC_OF_CANDIDATE:                     return "CANDIDATE";
      case QSMC_OF_HTF_CONTEXT:                   return "HTF_CONTEXT";
      case QSMC_OF_STRUCTURE_AND_LIQUIDITY:       return "STRUCTURE_AND_LIQUIDITY";
      case QSMC_OF_ZONE_AND_GEOMETRY:             return "ZONE_AND_GEOMETRY";
      case QSMC_OF_QUALITY:                       return "QUALITY";
      case QSMC_OF_CORE_EXPORTED:                 return "CORE_EXPORTED";
      case QSMC_OF_EA_RECEIVED:                   return "EA_RECEIVED";
      case QSMC_OF_SESSION_ALLOWED:               return "SESSION_ALLOWED";
      case QSMC_OF_RISK_ALLOWED:                  return "RISK_ALLOWED";
      case QSMC_OF_ORDER_ATTEMPTED:               return "ORDER_ATTEMPTED";
      case QSMC_OF_FILL_AND_PROTECTION_VERIFIED:  return "FILL_AND_PROTECTION_VERIFIED";
   }
   return "?STAGE";
}

string QSMC_OF_VerdictName(const int verdict)
{
   if(verdict==QSMC_OF_PASS)             return "PASS";
   if(verdict==QSMC_OF_REJECT)           return "REJECT";
   if(verdict==QSMC_OF_DATA_UNAVAILABLE) return "DATA_UNAVAILABLE";
   return "NOT_REACHED";
}

string QSMC_OF_UnitName(const int unit)
{
   switch(unit)
   {
      case QSMC_OF_UNIT_NONE:    return "none";
      case QSMC_OF_UNIT_POINTS:  return "points";
      case QSMC_OF_UNIT_PRICE:   return "price";
      case QSMC_OF_UNIT_ATR:     return "ATR";
      case QSMC_OF_UNIT_PCT:     return "pct";
      case QSMC_OF_UNIT_TICKS:   return "ticks";
      case QSMC_OF_UNIT_SECONDS: return "seconds";
      case QSMC_OF_UNIT_LOTS:    return "lots";
      case QSMC_OF_UNIT_R:       return "R";
   }
   return "?UNIT";
}

string QSMC_OF_ReasonName(const int reason)
{
   switch(reason)
   {
      case QSMC_OF_REASON_OK:                        return "OK";
      case QSMC_OF_REASON_NOT_REACHED:               return "NOT_REACHED";
      case QSMC_OF_REASON_NO_SETUP:                  return "NO_SETUP";
      case QSMC_OF_REASON_INCOMPLETE_CHAIN:          return "INCOMPLETE_CHAIN";
      case QSMC_OF_REASON_RULE_REJECT:               return "RULE_REJECT";
      case QSMC_OF_REASON_DATA_UNAVAILABLE:          return "DATA_UNAVAILABLE";
      case QSMC_OF_REASON_DATA_STALE:                return "DATA_STALE";
      case QSMC_OF_REASON_DATA_SHORT_READ:           return "DATA_SHORT_READ";
      case QSMC_OF_REASON_INDICATOR_INPUT_MISMATCH:  return "INDICATOR_INPUT_MISMATCH";
      case QSMC_OF_REASON_SESSION:                   return "SESSION";
      case QSMC_OF_REASON_GUARD_ACCOUNT_WIDE:        return "GUARD_ACCOUNT_WIDE";
      case QSMC_OF_REASON_GUARD_EA:                  return "GUARD_EA";
      case QSMC_OF_REASON_SPREAD_TOO_WIDE:           return "SPREAD_TOO_WIDE";
      case QSMC_OF_REASON_RR_INVALID:                return "RR_INVALID";
      case QSMC_OF_REASON_BROKER_REJECT:             return "BROKER_REJECT";
      case QSMC_OF_REASON_PROTECTION_MISSING:        return "PROTECTION_MISSING";
      case QSMC_OF_REASON_INTERNAL:                  return "INTERNAL";
   }
   return "INTERNAL";
}

void QSMC_OF_Reset()
{
   g_qsmc_of_seq=0; g_qsmc_of_overflow=false; g_qsmc_of_head=0; g_qsmc_of_total=0;
   for(int s=0;s<QSMC_OF_STAGE_COUNT;s++)
      for(int v=0;v<4;v++) g_qsmc_of_stage_verdict[s][v]=0;
   for(int r=0;r<QSMC_OF_REASON_COUNT;r++) g_qsmc_of_reason[r]=0;
}

bool QSMC_OF_SetEnabled(const bool enabled) { g_qsmc_of_enabled=enabled; if(!enabled) {} return g_qsmc_of_enabled; }
bool QSMC_OF_IsEnabled() { return g_qsmc_of_enabled; }
uint QSMC_OF_EventCount() { return g_qsmc_of_total; }
bool QSMC_OF_Overflowed() { return g_qsmc_of_overflow; }
uint QSMC_OF_StageVerdictCount(const int stage,const int verdict)
{
   if(stage<0 || stage>=QSMC_OF_STAGE_COUNT || verdict<0 || verdict>3) return 0;
   return g_qsmc_of_stage_verdict[stage][verdict];
}
uint QSMC_OF_ReasonCount(const int reason)
{
   if(reason<0 || reason>=QSMC_OF_REASON_COUNT) return 0;
   return g_qsmc_of_reason[reason];
}

// FNV-1a 64 over "symbol|family|direction|bar": deterministic, stable
// across runs of the same history. direction 0 renders as 0.
ulong QSMC_OF_MakeId(const string symbol,const string family,const int direction,const datetime bar)
{
   string key=symbol+"|"+family+"|"+IntegerToString(direction)+"|"+IntegerToString((long)bar);
   ulong h=14695981039346656037ULL;
   int n=StringLen(key);
   for(int i=0;i<n;i++)
   {
      h^=(ulong)(uchar)StringGetCharacter(key,i);
      h*=1099511628211ULL;
   }
   if(h==0) h=1;
   return h;
}

void QSMC_OF_Record(const ulong id,const string symbol,const string family,const int direction,
                    const datetime bar,const int stage,const int verdict,const int reason,
                    const double value,const double threshold,const int unit)
{
   if(!g_qsmc_of_enabled) return;               // disabled: no writes, no counters
   if(stage<0 || stage>=QSMC_OF_STAGE_COUNT) return;
   if(verdict<0 || verdict>3) return;
   if(reason<0 || reason>=QSMC_OF_REASON_COUNT) return;

   SOpportunityEvent ev;
   ev.id=id; ev.symbol=symbol; ev.family=family; ev.direction=direction; ev.bar=bar;
   ev.stage=stage; ev.verdict=verdict; ev.reason=reason;
   ev.value=value; ev.threshold=threshold; ev.unit=unit;

   g_qsmc_of_ring[g_qsmc_of_head]=ev;
   g_qsmc_of_head++;
   if(g_qsmc_of_head>=QSMC_OF_RING_SIZE) { g_qsmc_of_head=0; g_qsmc_of_overflow=true; }

   g_qsmc_of_total++;
   g_qsmc_of_seq++;
   g_qsmc_of_stage_verdict[stage][verdict]++;
   g_qsmc_of_reason[reason]++;
}

// Convenience wrappers (keep hook sites one-liners).
void QSMC_OF_Pass(ulong id,string symbol,string family,int direction,datetime bar,int stage,
                  double value,double threshold,int unit)
{ QSMC_OF_Record(id,symbol,family,direction,bar,stage,QSMC_OF_PASS,QSMC_OF_REASON_OK,value,threshold,unit); }
void QSMC_OF_Reject(ulong id,string symbol,string family,int direction,datetime bar,int stage,
                    int reason,double value,double threshold,int unit)
{ QSMC_OF_Record(id,symbol,family,direction,bar,stage,QSMC_OF_REJECT,reason,value,threshold,unit); }
void QSMC_OF_Unavailable(ulong id,string symbol,string family,int direction,datetime bar,int stage,
                         int reason,double value,int unit)
{ QSMC_OF_Record(id,symbol,family,direction,bar,stage,QSMC_OF_DATA_UNAVAILABLE,reason,value,EMPTY_VALUE,unit); }
void QSMC_OF_NotReached(ulong id,string symbol,string family,int direction,datetime bar,int stage)
{ QSMC_OF_Record(id,symbol,family,direction,bar,stage,QSMC_OF_NOT_REACHED,QSMC_OF_REASON_NOT_REACHED,EMPTY_VALUE,EMPTY_VALUE,QSMC_OF_UNIT_NONE); }

bool QSMC_OF_GetRecent(const int from_newest,SOpportunityEvent &ev)
{
   if(from_newest<0 || from_newest>=QSMC_OF_RING_SIZE) return false;
   uint written=(g_qsmc_of_overflow ? QSMC_OF_RING_SIZE : g_qsmc_of_total);
   if((uint)from_newest>=written) return false;
   int idx=g_qsmc_of_head-1-from_newest;
   while(idx<0) idx+=QSMC_OF_RING_SIZE;
   ev=g_qsmc_of_ring[idx];
   return true;
}

string QSMC_OF_Num(const double v)
{
   if(v==EMPTY_VALUE) return "EMPTY_VALUE";
   if(!MathIsValidNumber(v)) return "INVALID_NUMBER";
   return DoubleToString(v,10);
}

string QSMC_OF_FormatCSV(const SOpportunityEvent &ev)
{
   return IntegerToString((long)ev.bar)+","+ev.symbol+","+ev.family+","+
          IntegerToString(ev.direction)+","+QSMC_OF_StageName(ev.stage)+","+
          QSMC_OF_VerdictName(ev.verdict)+","+QSMC_OF_ReasonName(ev.reason)+","+
          QSMC_OF_Num(ev.value)+","+QSMC_OF_Num(ev.threshold)+","+QSMC_OF_UnitName(ev.unit)+","+
          IntegerToString((long)ev.id);
}

// Compact multi-line summary: one line per (stage) with PASS/REJECT/UNAV/NR
// counters, plus reason totals. Prints nothing when disabled.
string QSMC_OF_Summary()
{
   string out="[OF-FUNNEL] events="+IntegerToString((long)g_qsmc_of_total)+
              (g_qsmc_of_overflow?" (ring overflow: detail lossy)":"")+"\n";
   for(int s=0;s<QSMC_OF_STAGE_COUNT;s++)
   {
      out+="[OF-FUNNEL] "+QSMC_OF_StageName(s)+" pass="+IntegerToString((long)g_qsmc_of_stage_verdict[s][QSMC_OF_PASS])+
           " reject="+IntegerToString((long)g_qsmc_of_stage_verdict[s][QSMC_OF_REJECT])+
           " data_unavail="+IntegerToString((long)g_qsmc_of_stage_verdict[s][QSMC_OF_DATA_UNAVAILABLE])+
           " not_reached="+IntegerToString((long)g_qsmc_of_stage_verdict[s][QSMC_OF_NOT_REACHED])+"\n";
   }
   for(int r=0;r<QSMC_OF_REASON_COUNT;r++)
   {
      if(g_qsmc_of_reason[r]==0) continue;
      out+="[OF-FUNNEL] reason."+QSMC_OF_ReasonName(r)+"="+IntegerToString((long)g_qsmc_of_reason[r])+"\n";
   }
   return out;
}

void QSMC_OF_PrintSummary()
{
   if(!g_qsmc_of_enabled) return;
   Print(QSMC_OF_Summary());
}

//+------------------------------------------------------------------+
#endif // QSMC_OPPORTUNITY_FUNNEL_MQH
//+------------------------------------------------------------------+
