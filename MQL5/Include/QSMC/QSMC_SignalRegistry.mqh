//+------------------------------------------------------------------+
//|                                          QSMC_SignalRegistry.mqh |
//|  AUDIT-CH1 - one signal, one identity, one record, one lifecycle. |
//|                                                                   |
//|  WHY IT EXISTS                                                    |
//|  The primary scenario mark used to be named after the bar it was  |
//|  PUBLISHED on (QSMC_PRIMARY_<bar time>). A scenario that stayed   |
//|  primary for N closed bars therefore left N arrows and N labels   |
//|  behind ("[BUY] STRONG REACTION ..." repeated bar after bar). The |
//|  alert cool-down only ever gated the popup, never the drawing.    |
//|                                                                   |
//|  WHAT IT DOES                                                     |
//|  A signal is identified by WHAT it is, never by WHEN it was last  |
//|  seen:  symbol | timeframe | direction | setup type | anchor id   |
//|         (the zone or structural event) | originating bar time.    |
//|  Re-publishing a live signal UPDATES its record in place. A new   |
//|  record is created only for a genuinely new setup. States move    |
//|  forward only:                                                    |
//|     DETECTED -> CONFIRMED -> ACTIVE -> MITIGATED                  |
//|                         \-> INVALIDATED / EXPIRED (from any live) |
//|  A terminal record is never resurrected and never re-emitted.     |
//|                                                                   |
//|  PURE: no terminal call, no chart object, no order. Bounded:      |
//|  QSR_CAPACITY records, O(capacity) per call, no dynamic memory.   |
//|  Shared by nadir2.mq5 (primary marks) and QSMC_SmcVpEngine.mq5.   |
//+------------------------------------------------------------------+
#ifndef QSMC_SIGNAL_REGISTRY_MQH
#define QSMC_SIGNAL_REGISTRY_MQH

#define QSR_CAPACITY 64

enum ENUM_QSR_STATE
{
   QSR_STATE_NONE        = 0,   // empty slot
   QSR_STATE_DETECTED    = 1,   // candidate seen, confirmation incomplete
   QSR_STATE_CONFIRMED   = 2,   // every required confirmation held on a closed bar
   QSR_STATE_ACTIVE      = 3,   // confirmed and still in play
   QSR_STATE_MITIGATED   = 4,   // objective reached / zone consumed (terminal)
   QSR_STATE_INVALIDATED = 5,   // structural invalidation (terminal)
   QSR_STATE_EXPIRED     = 6    // aged out or no longer published (terminal)
};

struct SQsrSignal
{
   bool           used;
   string         key;           // family + originating bar: the stable identity
   string         family;        // symbol|timeframe|direction|setup type|anchor id
   string         symbol;
   int            timeframe;     // ENUM_TIMEFRAMES value of the signal timeframe
   int            direction;     // +1 BUY, -1 SELL
   string         setup_type;
   string         anchor_id;     // zone id or structural event id
   datetime       origin_time;   // originating bar (open time)
   ENUM_QSR_STATE state;
   datetime       first_seen;
   datetime       last_seen;
   datetime       state_time;    // when the current state was entered
   int            updates;       // in-place updates since creation
   int            level;         // host grade, latest value
   int            score;         // host score, latest value
   double         entry;
   double         stop;
   double         target;
   string         note;          // why the last transition happened
};

SQsrSignal g_qsr[QSR_CAPACITY];
int g_qsr_created=0;       // records created (genuinely new signals)
int g_qsr_updated=0;       // re-publications folded into an existing record
int g_qsr_rejected=0;      // attempts to re-emit a terminal signal
int g_qsr_evicted=0;       // records dropped to make room
int g_qsr_transitions=0;   // accepted state changes

void QSR_ClearSlot(const int i)
{
   if(i<0 || i>=QSR_CAPACITY) return;
   g_qsr[i].used=false;
   g_qsr[i].key=""; g_qsr[i].family=""; g_qsr[i].symbol="";
   g_qsr[i].timeframe=0; g_qsr[i].direction=0;
   g_qsr[i].setup_type=""; g_qsr[i].anchor_id="";
   g_qsr[i].origin_time=0;
   g_qsr[i].state=QSR_STATE_NONE;
   g_qsr[i].first_seen=0; g_qsr[i].last_seen=0; g_qsr[i].state_time=0;
   g_qsr[i].updates=0; g_qsr[i].level=0; g_qsr[i].score=0;
   g_qsr[i].entry=0.0; g_qsr[i].stop=0.0; g_qsr[i].target=0.0;
   g_qsr[i].note="";
}

void QSR_Reset()
{
   for(int i=0;i<QSR_CAPACITY;i++) QSR_ClearSlot(i);
   g_qsr_created=0; g_qsr_updated=0; g_qsr_rejected=0; g_qsr_evicted=0; g_qsr_transitions=0;
}

string QSR_StateName(const ENUM_QSR_STATE s)
{
   if(s==QSR_STATE_DETECTED)    return "DETECTED";
   if(s==QSR_STATE_CONFIRMED)   return "CONFIRMED";
   if(s==QSR_STATE_ACTIVE)      return "ACTIVE";
   if(s==QSR_STATE_MITIGATED)   return "MITIGATED";
   if(s==QSR_STATE_INVALIDATED) return "INVALIDATED";
   if(s==QSR_STATE_EXPIRED)     return "EXPIRED";
   return "NONE";
}

bool QSR_IsLive(const ENUM_QSR_STATE s)
{
   return (s==QSR_STATE_DETECTED || s==QSR_STATE_CONFIRMED || s==QSR_STATE_ACTIVE);
}

bool QSR_IsTerminal(const ENUM_QSR_STATE s)
{
   return (s==QSR_STATE_MITIGATED || s==QSR_STATE_INVALIDATED || s==QSR_STATE_EXPIRED);
}

// Forward only. A closed-bar confirmation is a fact: it is never downgraded,
// and a terminal record never comes back to life.
bool QSR_TransitionAllowed(const ENUM_QSR_STATE from,const ENUM_QSR_STATE to)
{
   if(to==QSR_STATE_NONE || from==to) return false;
   if(from==QSR_STATE_NONE) return QSR_IsLive(to);
   if(QSR_IsTerminal(from)) return false;
   if(from==QSR_STATE_DETECTED)
      return (to==QSR_STATE_CONFIRMED || to==QSR_STATE_INVALIDATED || to==QSR_STATE_EXPIRED);
   if(from==QSR_STATE_CONFIRMED)
      return (to==QSR_STATE_ACTIVE || QSR_IsTerminal(to));
   if(from==QSR_STATE_ACTIVE)
      return QSR_IsTerminal(to);
   return false;
}

string QSR_Family(const string symbol,const int timeframe,const int direction,
                  const string setup_type,const string anchor_id)
{
   return symbol+"|"+IntegerToString(timeframe)+"|"+(direction>0?"BUY":"SELL")+"|"+
          setup_type+"|"+anchor_id;
}

string QSR_Key(const string family,const datetime origin_time)
{
   return family+"|"+IntegerToString((long)origin_time);
}

int QSR_FindKey(const string key)
{
   if(key=="") return -1;
   for(int i=0;i<QSR_CAPACITY;i++)
      if(g_qsr[i].used && g_qsr[i].key==key) return i;
   return -1;
}

// The live record of a family, newest origin first. -1 when the family has none.
int QSR_FindLiveFamily(const string family)
{
   int best=-1;
   for(int i=0;i<QSR_CAPACITY;i++)
   {
      if(!g_qsr[i].used || g_qsr[i].family!=family || !QSR_IsLive(g_qsr[i].state)) continue;
      if(best<0 || g_qsr[i].origin_time>g_qsr[best].origin_time) best=i;
   }
   return best;
}

int QSR_Count()
{
   int n=0;
   for(int i=0;i<QSR_CAPACITY;i++) if(g_qsr[i].used) n++;
   return n;
}

int QSR_CountLive()
{
   int n=0;
   for(int i=0;i<QSR_CAPACITY;i++) if(g_qsr[i].used && QSR_IsLive(g_qsr[i].state)) n++;
   return n;
}

int QSR_CountState(const ENUM_QSR_STATE s)
{
   int n=0;
   for(int i=0;i<QSR_CAPACITY;i++) if(g_qsr[i].used && g_qsr[i].state==s) n++;
   return n;
}

// Room for one more record: a free slot, else the oldest TERMINAL record, else
// (every record still live) the live record that was seen longest ago.
int QSR_AcquireSlot()
{
   for(int i=0;i<QSR_CAPACITY;i++) if(!g_qsr[i].used) return i;
   int victim=-1;
   for(int i=0;i<QSR_CAPACITY;i++)
   {
      if(!QSR_IsTerminal(g_qsr[i].state)) continue;
      if(victim<0 || g_qsr[i].state_time<g_qsr[victim].state_time) victim=i;
   }
   if(victim<0)
   {
      victim=0;
      for(int i=1;i<QSR_CAPACITY;i++)
         if(g_qsr[i].last_seen<g_qsr[victim].last_seen) victim=i;
   }
   g_qsr_evicted++;
   QSR_ClearSlot(victim);
   return victim;
}

bool QSR_SetState(const int idx,const ENUM_QSR_STATE to,const datetime now,const string note)
{
   if(idx<0 || idx>=QSR_CAPACITY || !g_qsr[idx].used) return false;
   if(!QSR_TransitionAllowed(g_qsr[idx].state,to)) return false;
   g_qsr[idx].state=to;
   g_qsr[idx].state_time=now;
   g_qsr[idx].note=note;
   g_qsr_transitions++;
   return true;
}

// Create-or-update by FULL identity. `created` is true only for a new record.
// Returns the slot, or -1 when the request is invalid or the identity already
// reached a terminal state (a finished signal is never emitted twice).
int QSR_Upsert(const string symbol,const int timeframe,const int direction,
               const string setup_type,const string anchor_id,const datetime origin_time,
               const datetime now,const ENUM_QSR_STATE state,bool &created)
{
   created=false;
   if(symbol=="" || setup_type=="" || anchor_id=="" || origin_time<=0 ||
      (direction!=1 && direction!=-1) || !QSR_IsLive(state))
      return -1;
   string family=QSR_Family(symbol,timeframe,direction,setup_type,anchor_id);
   string key=QSR_Key(family,origin_time);
   int idx=QSR_FindKey(key);
   if(idx>=0)
   {
      if(QSR_IsTerminal(g_qsr[idx].state)) { g_qsr_rejected++; return -1; }
      if(now>g_qsr[idx].last_seen) g_qsr[idx].last_seen=now;
      g_qsr[idx].updates++;
      g_qsr_updated++;
      if(g_qsr[idx].state!=state) QSR_SetState(idx,state,now,"re-published");
      return idx;
   }
   idx=QSR_AcquireSlot();
   g_qsr[idx].used=true;
   g_qsr[idx].key=key; g_qsr[idx].family=family; g_qsr[idx].symbol=symbol;
   g_qsr[idx].timeframe=timeframe; g_qsr[idx].direction=direction;
   g_qsr[idx].setup_type=setup_type; g_qsr[idx].anchor_id=anchor_id;
   g_qsr[idx].origin_time=origin_time;
   g_qsr[idx].state=state;
   g_qsr[idx].first_seen=now; g_qsr[idx].last_seen=now; g_qsr[idx].state_time=now;
   g_qsr[idx].updates=0;
   g_qsr[idx].note="created";
   g_qsr_created++;
   created=true;
   return idx;
}

void QSR_SetPlan(const int idx,const int level,const int score,
                 const double entry,const double stop,const double target)
{
   if(idx<0 || idx>=QSR_CAPACITY || !g_qsr[idx].used) return;
   g_qsr[idx].level=level; g_qsr[idx].score=score;
   g_qsr[idx].entry=entry; g_qsr[idx].stop=stop; g_qsr[idx].target=target;
}

// Live records that nobody re-published for longer than idle_seconds expire.
int QSR_ExpireIdle(const datetime now,const int idle_seconds)
{
   if(idle_seconds<=0) return 0;
   int n=0;
   for(int i=0;i<QSR_CAPACITY;i++)
   {
      if(!g_qsr[i].used || !QSR_IsLive(g_qsr[i].state)) continue;
      if(now-g_qsr[i].last_seen>(datetime)idle_seconds)
         if(QSR_SetState(i,QSR_STATE_EXPIRED,now,"not re-published")) n++;
   }
   return n;
}

// EPISODE identity, for a host that re-submits the same candidate on every
// closed bar and carries no originating bar of its own (the alert dispatcher).
// The origin is the bar on which the family first appeared in the current
// episode; the episode ends when the family is not re-published for more than
// idle_seconds, and the next appearance is then a NEW signal. Returns true when
// a new record was created; `origin` is always the bar the mark belongs to.
bool QSR_Episode(const string symbol,const int timeframe,const int direction,
                 const string setup_type,const string anchor_id,const datetime now,
                 const int idle_seconds,const ENUM_QSR_STATE state,datetime &origin)
{
   origin=now;
   if(symbol=="" || setup_type=="" || anchor_id=="" || now<=0 ||
      (direction!=1 && direction!=-1) || !QSR_IsLive(state))
      return false;
   string family=QSR_Family(symbol,timeframe,direction,setup_type,anchor_id);
   int idx=QSR_FindLiveFamily(family);
   if(idx>=0 && idle_seconds>0 && now-g_qsr[idx].last_seen>(datetime)idle_seconds)
   {
      QSR_SetState(idx,QSR_STATE_EXPIRED,now,"not re-published");
      idx=-1;
   }
   if(idx>=0)
   {
      if(now>g_qsr[idx].last_seen) g_qsr[idx].last_seen=now;
      g_qsr[idx].updates++;
      g_qsr_updated++;
      // forward only: a later, weaker reading never downgrades the record
      if(QSR_TransitionAllowed(g_qsr[idx].state,state) && !QSR_IsTerminal(state))
         QSR_SetState(idx,state,now,"upgraded");
      origin=g_qsr[idx].origin_time;
      return false;
   }
   bool created=false;
   int slot=QSR_Upsert(symbol,timeframe,direction,setup_type,anchor_id,now,now,state,created);
   if(slot<0) return false;
   origin=g_qsr[slot].origin_time;
   return created;
}

//--- helpers for the alert dispatcher of nadir2.mq5 ----------------------------
string QSR_SourceTag(const int source)
{
   if(source==1) return "ZRE";
   if(source==2) return "RXN";
   if(source==3) return "CORE";
   return "SRC"+IntegerToString(source);
}

// source 3 is a Core confirmation; an RXN/ZRE candidate is confirmed from the
// host's own CONFIRMED rank (4) upwards. Below that it is a detected candidate.
ENUM_QSR_STATE QSR_StateForLevel(const int source,const int level)
{
   if(source==3 || level>=4) return QSR_STATE_CONFIRMED;
   return QSR_STATE_DETECTED;
}

// Ring bookkeeping: when a NEW mark is written at ring position `pos` and only
// the newest `keep` marks may stay, this is the slot whose mark must go.
int QSR_RingEvictSlot(const int pos,const int limit,const int keep)
{
   if(limit<=0) return 0;
   int k=keep;
   if(k<1) k=1;
   if(k>limit) k=limit;
   int slot=(pos-k)%limit;
   if(slot<0) slot+=limit;
   return slot;
}

// Index of the origin bar in an oldest-first time array, walking back from
// `from_index` at most max_back bars. Falls back to from_index (and reports the
// time actually used) when the origin is no longer in the array.
int QSR_OriginIndex(const datetime &t[],const int from_index,const datetime origin,
                    const int max_back,datetime &used_time)
{
   int n=ArraySize(t);
   used_time=origin;
   if(from_index<0 || from_index>=n) return from_index;
   for(int back=0;back<=max_back && from_index-back>=0;back++)
   {
      if(t[from_index-back]==origin) return from_index-back;
      if(t[from_index-back]<origin) break;
   }
   used_time=t[from_index];
   return from_index;
}

//--- deterministic self-test (no terminal state, no chart) ---------------------
bool QSR_SelfTest(string &where)
{
   where="";
   SQsrSignal keep[QSR_CAPACITY];
   int c0=g_qsr_created,u0=g_qsr_updated,r0=g_qsr_rejected,e0=g_qsr_evicted,t0=g_qsr_transitions;
   for(int i=0;i<QSR_CAPACITY;i++) keep[i]=g_qsr[i];
   QSR_Reset();
   bool created=false;
   datetime origin=0;
   // 1. one identity, one record, however often it is re-published
   int a=QSR_Upsert("XAUUSD",15,1,"SWEEP_MSS","Z1",1000,1000,QSR_STATE_DETECTED,created);
   if(a<0 || !created) where="QSR-1 first publication must create a record";
   for(int k=1;k<=20 && where=="";k++)
   {
      int b=QSR_Upsert("XAUUSD",15,1,"SWEEP_MSS","Z1",1000,1000+k*900,QSR_STATE_DETECTED,created);
      if(b!=a || created) where="QSR-2 re-publication must update the same record";
   }
   if(where=="" && (QSR_Count()!=1 || g_qsr_created!=1 || g_qsr_updated!=20))
      where="QSR-3 twenty re-publications must leave exactly one record";
   // 2. a different direction / anchor / origin is a different signal
   if(where=="")
   {
      QSR_Upsert("XAUUSD",15,-1,"SWEEP_MSS","Z1",1000,1000,QSR_STATE_DETECTED,created);
      if(!created) where="QSR-4 the opposite direction is a new signal";
   }
   if(where=="")
   {
      QSR_Upsert("XAUUSD",15,1,"SWEEP_MSS","Z2",1000,1000,QSR_STATE_DETECTED,created);
      if(!created) where="QSR-5 another anchor is a new signal";
   }
   // 3. lifecycle is forward only and terminal states are final
   if(where=="" && !QSR_SetState(a,QSR_STATE_CONFIRMED,2000,"t")) where="QSR-6 DETECTED->CONFIRMED";
   if(where=="" && QSR_SetState(a,QSR_STATE_DETECTED,2100,"t")) where="QSR-7 no downgrade";
   if(where=="" && !QSR_SetState(a,QSR_STATE_ACTIVE,2200,"t")) where="QSR-8 CONFIRMED->ACTIVE";
   if(where=="" && !QSR_SetState(a,QSR_STATE_MITIGATED,2300,"t")) where="QSR-9 ACTIVE->MITIGATED";
   if(where=="" && QSR_SetState(a,QSR_STATE_ACTIVE,2400,"t")) where="QSR-10 terminal is final";
   if(where=="")
   {
      int b=QSR_Upsert("XAUUSD",15,1,"SWEEP_MSS","Z1",1000,5000,QSR_STATE_DETECTED,created);
      if(b>=0 || created || g_qsr_rejected!=1) where="QSR-11 a finished signal is never re-emitted";
   }
   // 4. episodes: same family within the idle gap is ONE signal, after it a new one
   if(where=="")
   {
      QSR_Reset();
      bool n1=QSR_Episode("XAUUSD",15,1,"RXN","ZA",9000,2700,QSR_STATE_DETECTED,origin);
      bool n2=QSR_Episode("XAUUSD",15,1,"RXN","ZA",9900,2700,QSR_STATE_DETECTED,origin);
      bool n3=QSR_Episode("XAUUSD",15,1,"RXN","ZA",10800,2700,QSR_STATE_CONFIRMED,origin);
      if(!n1 || n2 || n3 || origin!=9000 || QSR_Count()!=1)
         where="QSR-12 consecutive bars of one scenario are one episode";
      int live=QSR_FindLiveFamily(QSR_Family("XAUUSD",15,1,"RXN","ZA"));
      if(where=="" && (live<0 || g_qsr[live].state!=QSR_STATE_CONFIRMED))
         where="QSR-13 an episode upgrades in place";
      bool n4=QSR_Episode("XAUUSD",15,1,"RXN","ZA",10800+3600,2700,QSR_STATE_DETECTED,origin);
      if(where=="" && (!n4 || origin!=10800+3600 || QSR_Count()!=2 ||
         QSR_CountState(QSR_STATE_EXPIRED)!=1))
         where="QSR-14 after the idle gap the same zone starts a NEW signal";
   }
   // 5. bounded: the registry never grows past its capacity
   if(where=="")
   {
      QSR_Reset();
      for(int k=0;k<QSR_CAPACITY+10;k++)
         QSR_Upsert("XAUUSD",15,1,"T","A"+IntegerToString(k),1000+k,1000+k,QSR_STATE_DETECTED,created);
      if(QSR_Count()!=QSR_CAPACITY || g_qsr_evicted!=10) where="QSR-15 capacity is a hard bound";
   }
   // 6. ring window arithmetic used by the primary-mark ring
   if(where=="" && (QSR_RingEvictSlot(0,16,16)!=0 || QSR_RingEvictSlot(5,16,3)!=2 ||
      QSR_RingEvictSlot(1,16,3)!=14 || QSR_RingEvictSlot(7,16,99)!=7 || QSR_RingEvictSlot(7,16,0)!=6))
      where="QSR-16 ring eviction window";
   for(int i=0;i<QSR_CAPACITY;i++) g_qsr[i]=keep[i];
   g_qsr_created=c0; g_qsr_updated=u0; g_qsr_rejected=r0; g_qsr_evicted=e0; g_qsr_transitions=t0;
   return (where=="");
}

#endif
//+------------------------------------------------------------------+
