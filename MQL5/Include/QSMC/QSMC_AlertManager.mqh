//+------------------------------------------------------------------+
//|                                           QSMC_AlertManager.mqh  |
//|  The ONLY class allowed to call Alert() / PlaySound() /           |
//|  SendNotification(). Every user-visible arbitration string is     |
//|  built here so the wording can never drift between the popup, the |
//|  journal, the CSV and the chart label.                            |
//|                                                                   |
//|  ANTI-SPAM (R5) - four independent locks, all must open:          |
//|   1. exact key       (symbol,TF,zoneId,direction,state,barTime)   |
//|   2. cooldown bars   (symbol,zoneId,direction,state)              |
//|   3. price distance  (symbol,zoneId,direction) in ATR             |
//|   4. flip-flop       (opposite direction, same zone, N bars)      |
//|  plus a terminal GlobalVariable so two charts of the same symbol  |
//|  cannot publish the same event twice.                             |
//|                                                                   |
//|  COMPLEXITY: O(ring) per publish with ring <= 4096; linear scans  |
//|  are bounded and run at most once per closed bar.                 |
//+------------------------------------------------------------------+
#ifndef __QSMC_ALERTMANAGER_MQH__
#define __QSMC_ALERTMANAGER_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_Gates.mqh>

#define QSMC_GV_PREFIX  "QSMC_ARB_"
#define QSMC_GV_TTL_SEC 604800      // 7 days

//+------------------------------------------------------------------+
class CAlertManager : public IAlertHistory
  {
private:
   //--- lock 1: exact keys (dedupe ring)
   string            m_ring_key[];
   int               m_ring_bar[];
   int               m_ring_pos;
   int               m_ring_cap;
   int               m_ring_count;
   //--- lock 2: cooldown per (zone,direction,state)
   string            m_cd_key[];
   int               m_cd_bar[];
   string            m_cd_event[];
   int               m_cd_pos;
   //--- lock 3: last published price per (zone,direction)
   string            m_pd_key[];
   double            m_pd_price[];
   int               m_pd_pos;
   //--- lock 4: last direction per zone
   string            m_ff_zone[];
   int               m_ff_dir[];
   int               m_ff_bar[];
   int               m_ff_pos;

   int               m_history_cap;
   string            m_last_message;
   string            m_last_reject;
   int               m_published;
   int               m_suppressed;
   bool              m_enabled_channels;

   //--- deterministic FNV-1a 32-bit hash -> hex, for GlobalVariable names
   string            HashHex(const string s) const
     {
      uint h=2166136261u;
      int n=StringLen(s);
      for(int i=0;i<n;i++)
        {
         uint c=(uint)StringGetCharacter(s,i);
         h=(h ^ (c & 0xFFu))*16777619u;
        }
      return StringFormat("%08X",h);
     }

   int               FindRing(const string key) const
     {
      for(int i=0;i<m_ring_count;i++)
         if(m_ring_key[i]==key) return i;
      return -1;
     }
   int               FindCd(const string key) const
     {
      int n=ArraySize(m_cd_key);
      for(int i=0;i<n;i++)
         if(m_cd_key[i]==key) return i;
      return -1;
     }
   int               FindPd(const string key) const
     {
      int n=ArraySize(m_pd_key);
      for(int i=0;i<n;i++)
         if(m_pd_key[i]==key) return i;
      return -1;
     }
   int               FindFf(const string zone,const int dir) const
     {
      int n=ArraySize(m_ff_zone);
      for(int i=0;i<n;i++)
         if(m_ff_zone[i]==zone && m_ff_dir[i]==dir) return i;
      return -1;
     }

public:
                     CAlertManager()
     { m_ring_pos=0; m_ring_cap=256; m_ring_count=0;
       m_cd_pos=0; m_pd_pos=0; m_ff_pos=0;
       m_history_cap=256;
       m_last_message=""; m_last_reject="";
       m_published=0; m_suppressed=0; m_enabled_channels=true;
       ArrayResize(m_cd_key,0); ArrayResize(m_cd_bar,0); ArrayResize(m_cd_event,0);
       ArrayResize(m_pd_key,0); ArrayResize(m_pd_price,0);
       ArrayResize(m_ff_zone,0); ArrayResize(m_ff_dir,0); ArrayResize(m_ff_bar,0); }

                    ~CAlertManager()
     {
      ArrayResize(m_ring_key,0); ArrayResize(m_ring_bar,0);
      ArrayResize(m_cd_key,0); ArrayResize(m_cd_bar,0); ArrayResize(m_cd_event,0);
      ArrayResize(m_pd_key,0); ArrayResize(m_pd_price,0);
      ArrayResize(m_ff_zone,0); ArrayResize(m_ff_dir,0); ArrayResize(m_ff_bar,0);
     }

   void              Init(const int ring_cap)
     {
      m_ring_cap=(int)MathMax(64,MathMin(4096,ring_cap));
      m_history_cap=m_ring_cap;
      ArrayResize(m_ring_key,m_ring_cap);
      ArrayResize(m_ring_bar,m_ring_cap);
      for(int i=0;i<m_ring_cap;i++){ m_ring_key[i]=""; m_ring_bar[i]=-1; }
      ArrayResize(m_cd_key,m_history_cap);
      ArrayResize(m_cd_bar,m_history_cap);
      ArrayResize(m_cd_event,m_history_cap);
      for(int i=0;i<m_history_cap;i++){ m_cd_key[i]=""; m_cd_bar[i]=-1; m_cd_event[i]=""; }
      ArrayResize(m_pd_key,m_history_cap);
      ArrayResize(m_pd_price,m_history_cap);
      for(int i=0;i<m_history_cap;i++){ m_pd_key[i]=""; m_pd_price[i]=0.0; }
      ArrayResize(m_ff_zone,m_history_cap);
      ArrayResize(m_ff_dir,m_history_cap);
      ArrayResize(m_ff_bar,m_history_cap);
      for(int i=0;i<m_history_cap;i++){ m_ff_zone[i]=""; m_ff_dir[i]=0; m_ff_bar[i]=-1; }
      m_ring_pos=0; m_ring_count=0; m_cd_pos=0; m_pd_pos=0; m_ff_pos=0;
      m_published=0; m_suppressed=0;
     }

   int               Published() const { return m_published; }
   int               Suppressed() const { return m_suppressed; }
   string            LastMessage() const { return m_last_message; }
   string            LastReject() const { return m_last_reject; }

   //=================================================================
   // IAlertHistory - consumed by the cooldown / distance / flip-flop
   // gates. Read-only: querying never mutates the history.
   //=================================================================
   virtual int       BarsSince(const string key,const int now_index)
     {
      int i=FindCd(key);
      if(i<0 || m_cd_bar[i]<0) return -1;
      if(now_index<m_cd_bar[i]) return 0;
      return now_index-m_cd_bar[i];
     }

   virtual double    PriceDistanceATR(const string key,const double price,const double atr)
     {
      int i=FindPd(key);
      if(i<0 || !(m_pd_price[i]>0.0)) return -1.0;
      if(!(atr>0.0)) return -1.0;
      return MathAbs(price-m_pd_price[i])/atr;
     }

   virtual int       BarsSinceOpposite(const string zone_id,const int dir,const int now_index)
     {
      int n=ArraySize(m_ff_zone);
      int best=-1;
      for(int i=0;i<n;i++)
        {
         if(m_ff_zone[i]!=zone_id) continue;
         if(m_ff_dir[i]==dir) continue;
         if(m_ff_dir[i]==0) continue;
         if(m_ff_bar[i]<0) continue;
         int d=now_index-m_ff_bar[i];
         if(d<0) d=0;
         if(best<0 || d<best) best=d;
        }
      return best;
     }

   //=================================================================
   // Key builders. The exact key carries the BAR TIME so a stable
   // signal cannot re-fire on every execution bar; the base key does
   // NOT, so cooldown works across bar times.
   //=================================================================
   string            ExactKey(const SSignalCandidate &c,const SGateCtx &ctx) const
     {
      return ctx.symbol+"|"+IntegerToString((int)ctx.tf)+"|"+c.zone_id+"|"+
             IntegerToString(c.dir)+"|"+IntegerToString(c.state)+"|"+
             IntegerToString((long)c.bar_time);
     }
   string            BaseKey(const SSignalCandidate &c,const SGateCtx &ctx) const
     {
      return ctx.symbol+"|"+IntegerToString((int)ctx.tf)+"|"+c.zone_id+"|"+
             IntegerToString(c.dir)+"|"+IntegerToString(c.state);
     }
   string            ZoneDirKey(const SSignalCandidate &c,const SGateCtx &ctx) const
     {
      return ctx.symbol+"|"+IntegerToString((int)ctx.tf)+"|"+c.zone_id+"|"+
             IntegerToString(c.dir);
     }

   //=================================================================
   // Gate-level pre-check. Used by the arbiter BEFORE it decides, so a
   // suppressed candidate is never ranked into the primary slot.
   // Returns true when every lock is open; `why` says which one shut.
   //=================================================================
   bool              Allows(const SSignalCandidate &c,const SGateCtx &ctx,
                            const SQsmcArbConfig &cfg,string &why)
     {
      why="";
      string exact=ExactKey(c,ctx);
      if(FindRing(exact)>=0) { why="duplicate exact key"; return false; }

      string base=BaseKey(c,ctx);
      int i=FindCd(base);
      if(i>=0 && cfg.cooldown_bars>0)
        {
         int since=ctx.closed_index-m_cd_bar[i];
         if(since<0) since=0;
         if(since<cfg.cooldown_bars)
           { why="cooldown "+IntegerToString(since)+"/"+IntegerToString(cfg.cooldown_bars); return false; }
        }
      string zd=ZoneDirKey(c,ctx);
      int p=FindPd(zd);
      if(p>=0 && cfg.min_alert_distance_atr>0.0 && ctx.atr>0.0)
        {
         double d=MathAbs(c.entry-m_pd_price[p])/ctx.atr;
         if(d<cfg.min_alert_distance_atr-1.0e-9)
           { why="distance "+DoubleToString(d,2)+" ATR < "+DoubleToString(cfg.min_alert_distance_atr,2); return false; }
        }
      int opp=BarsSinceOpposite(c.zone_id,c.dir,ctx.closed_index);
      if(opp>=0 && cfg.flipflop_bars>0 && opp<cfg.flipflop_bars)
        { why="flip-flop guard "+IntegerToString(opp)+"/"+IntegerToString(cfg.flipflop_bars); return false; }

      //--- cross-chart claim
      if(cfg.use_global_vars)
        {
         string gv=QSMC_GV_PREFIX+HashHex(exact);
         if(GlobalVariableCheck(gv))
           {
            double v=0.0;
            if(GlobalVariableGet(gv,v) && v>=(double)c.bar_time)
              { why="already published by another chart of this symbol"; return false; }
           }
        }
      return true;
     }

   //=================================================================
   // Build the alert text. R6: symbol, TF, direction, state, zone id
   // and range, zone strength, evidence list, invalidation (SL), TP1,
   // RR and the exact reason when downgraded. Every field is present
   // or explicitly "-" - never silently omitted.
   //=================================================================
   string            BuildMessage(const SSignalCandidate &c,const SGateCtx &ctx) const
     {
      string dir=(c.dir>0?"BUY":"SELL");
      string side=(c.dir>0?"S":"R");
      string st=QSMC_StateName(c.state);
      string ev=QSMC_EvidenceList(c.reaction.evidence_mask);
      string room=(c.room_atr>=0.0?DoubleToString(c.room_atr,2)+" ATR":"no barrier");
      string reason=(c.downgraded && c.reason!="" ? c.reason : (c.reason!=""?c.reason:"all gates passed"));

      string s="["+dir+"] "+ctx.symbol+" "+QSMC_TFName(ctx.tf)+" | "+st+
               " | "+side+" "+DoubleToString(c.zone_lo,ctx.digits)+"-"+
               DoubleToString(c.zone_hi,ctx.digits)+
               " | zone "+c.zone_id+
               " | strength "+IntegerToString(c.zone_strength)+"/100"+
               " | evidence "+ev+" ("+IntegerToString(c.reaction.evidence_count)+
               "/"+IntegerToString(QEV_COUNT)+")"+
               " | entry "+DoubleToString(c.entry,ctx.digits)+
               " | invalidation/SL "+DoubleToString(c.sl,ctx.digits)+
               " | TP1 "+DoubleToString(c.tp1,ctx.digits)+
               " | RR "+DoubleToString(c.rr,2)+
               " | room "+room+
               " | "+QSMC_TFName(ctx.tf)+" bar "+TimeToString(c.bar_time,TIME_MINUTES)+
               (c.bar_closed?" (closed)":" (FORMING)")+
               " | src "+QSMC_SourceName(c.source)+
               " | score "+IntegerToString(c.score)+"/100"+
               " | reason: "+reason;
      if(c.reject_text!="") s+=" | blocked-by: "+c.reject_text;
      return s;
     }

   //=================================================================
   // Publish. Returns true only when the alert was actually emitted.
   //=================================================================
   bool              Publish(const SSignalCandidate &c,const SGateCtx &ctx,
                             const SQsmcArbConfig &cfg)
     {
      string why="";
      if(!Allows(c,ctx,cfg,why))
        { m_last_reject=why; m_suppressed++; return false; }

      string exact=ExactKey(c,ctx);
      string base=BaseKey(c,ctx);
      string zd=ZoneDirKey(c,ctx);
      string msg=BuildMessage(c,ctx);

      //--- cross-chart claim (taken BEFORE the terminal call so two
      //--- charts cannot both pass the window)
      if(cfg.use_global_vars)
        {
         string gv=QSMC_GV_PREFIX+HashHex(exact);
         if(StringLen(gv)<=63) GlobalVariableSet(gv,(double)c.bar_time);
        }

      if(cfg.popup) Alert(msg);
      if(cfg.push)
        {
         string pm=msg;
         if(StringLen(pm)>240) pm=StringSubstr(pm,0,240);
         SendNotification(pm);
        }
      if(cfg.sound) PlaySound("alert.wav");

      //--- commit every lock
      m_ring_key[m_ring_pos]=exact;
      m_ring_bar[m_ring_pos]=ctx.closed_index;
      m_ring_pos=(m_ring_pos+1)%m_ring_cap;
      if(m_ring_count<m_ring_cap) m_ring_count++;

      int ci=FindCd(base);
      if(ci<0){ ci=m_cd_pos; m_cd_pos=(m_cd_pos+1)%m_history_cap; }
      m_cd_key[ci]=base; m_cd_bar[ci]=ctx.closed_index; m_cd_event[ci]=exact;

      int pi=FindPd(zd);
      if(pi<0){ pi=m_pd_pos; m_pd_pos=(m_pd_pos+1)%m_history_cap; }
      m_pd_key[pi]=zd; m_pd_price[pi]=c.entry;

      int fi=FindFf(c.zone_id,c.dir);
      if(fi<0){ fi=m_ff_pos; m_ff_pos=(m_ff_pos+1)%m_history_cap; }
      m_ff_zone[fi]=c.zone_id; m_ff_dir[fi]=c.dir; m_ff_bar[fi]=ctx.closed_index;

      m_last_message=msg;
      m_last_reject="";
      m_published++;
      return true;
     }

   //=================================================================
   // Terminal global-variable sweep. Called from OnDeinit so a long
   // running terminal does not accumulate claim keys. Only entries
   // OLDER than the TTL are removed, so a chart that is still running
   // never loses a live claim.
   //=================================================================
   int               CleanupGlobalVars(const datetime now=0)
     {
      datetime t=(now>0?now:TimeCurrent());
      int removed=0;
      int total=GlobalVariablesTotal();
      for(int i=total-1;i>=0;i--)
        {
         string nm=GlobalVariableName(i);
         if(StringFind(nm,QSMC_GV_PREFIX)!=0) continue;
         double v=0.0;
         if(!GlobalVariableGet(nm,v)) continue;
         if(v<=0.0) { GlobalVariableDel(nm); removed++; continue; }
         if((double)t-v>(double)QSMC_GV_TTL_SEC) { GlobalVariableDel(nm); removed++; }
        }
      return removed;
     }
  };

#endif
//+------------------------------------------------------------------+
