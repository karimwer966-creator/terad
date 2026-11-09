//+------------------------------------------------------------------+
//|                                                 QSMC_Gates.mqh   |
//|  IGate + the concrete gates. One gate per domain rule.            |
//|                                                                   |
//|  RESULT CONTRACT                                                  |
//|   GATE_PASS      : the candidate keeps the state it asked for.    |
//|   GATE_FAIL      : the candidate is rejected; `reason` is shown.  |
//|   GATE_DOWNGRADE : the candidate survives but is demoted to       |
//|                    `downgrade_state` (>= WATCH) and the reason    |
//|                    is mandatory in the published text (R6).       |
//|  A downgraded candidate is NOT alerted: per R5 an alert is sent   |
//|  only for a signal that survived every gate at its final state.   |
//|                                                                   |
//|  COMPLEXITY: every gate is O(1) except CLocationGate and          |
//|  CRoomGate, which are O(log N + k) via CZoneRegistry.             |
//+------------------------------------------------------------------+
#ifndef __QSMC_GATES_MQH__
#define __QSMC_GATES_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_Zones.mqh>

//--------------------------------------------------------------------
// Read-only view of the alert history, so the anti-spam gates do not
// have to include (and therefore be included by) CAlertManager.
// Implemented by CAlertManager.
//--------------------------------------------------------------------
interface IAlertHistory
  {
   //--- closed bars since the exact key was last alerted; -1 = never
   virtual int       BarsSince(const string key,const int now_index)=0;
   //--- ATR distance from the price stored for the base key; -1 = never
   virtual double    PriceDistanceATR(const string key,const double price,const double atr)=0;
   //--- closed bars since the OPPOSITE direction was alerted on this zone
   virtual int       BarsSinceOpposite(const string zone_id,const int dir,const int now_index)=0;
  };

//--------------------------------------------------------------------
interface IGate
  {
   virtual string           Name()=0;
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,
                                     const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,
                                     const CZoneRegistry &zones,
                                     string &reason,
                                     int &downgrade_state)=0;
  };

//====================================================================
// 1. CLOSED-BAR GATE  (R3)
//====================================================================
class CClosedBarGate : public IGate
  {
public:
   virtual string    Name() { return "CLOSED_BAR"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_WATCH;
      if(!ctx.data_ready) { reason="data not ready: "+ctx.data_reason; return GATE_FAIL; }
      if(ctx.closed_index<2) { reason="fewer than 3 closed bars"; return GATE_FAIL; }
      if(c.bar_index<1) { reason="candidate cites bar 0 (forming) - CONFIRMED is impossible there"; return GATE_FAIL; }
      if(c.bar_index>ctx.closed_index) { reason="candidate cites a bar in the future"; return GATE_FAIL; }
      if(c.state==(int)SIG_CONFIRMED && !c.bar_closed)
        {
         downgrade_state=(int)SIG_PREVIEW;
         reason="forming bar - CONFIRMED requires a closed bar (R3)";
         return GATE_DOWNGRADE;
        }
      if(!c.bar_closed && c.state!=(int)SIG_PREVIEW && c.state!=(int)SIG_WATCH)
        {
         downgrade_state=(int)SIG_PREVIEW;
         reason="forming bar - demoted to PREVIEW";
         return GATE_DOWNGRADE;
        }
      return GATE_PASS;
     }
  };

//====================================================================
// 2. DATA-QUALITY GATE
//====================================================================
class CDataQualityGate : public IGate
  {
public:
   virtual string    Name() { return "DATA_QUALITY"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_NO_TRADE;
      if(!ctx.data_ready) { reason="data not ready: "+ctx.data_reason; return GATE_FAIL; }
      if(!(ctx.atr>0.0) || !MathIsValidNumber(ctx.atr)) { reason="ATR unavailable"; return GATE_FAIL; }
      double floor_pts=(cfg.min_atr_points>0.0 ? cfg.min_atr_points : 1.0);
      if(ctx.atr < floor_pts*ctx.point)
        { reason="ATR below the dead-market floor ("+DoubleToString(ctx.atr,ctx.digits)+")"; return GATE_FAIL; }
      if(cfg.max_spread_points>0 && ctx.spread_points>cfg.max_spread_points)
        { reason="spread "+IntegerToString((int)ctx.spread_points)+" pts > max "+
                 IntegerToString(cfg.max_spread_points); return GATE_FAIL; }
      if(ctx.closed_index+1 < cfg.min_bars)
        { reason="only "+IntegerToString(ctx.closed_index+1)+" closed bars, "+
                 IntegerToString(cfg.min_bars)+" required"; return GATE_FAIL; }
      if(!MathIsValidNumber(c.entry) || !MathIsValidNumber(c.sl) || !(c.entry>0.0) || !(c.sl>0.0))
        { reason="entry or stop is not a valid price"; return GATE_FAIL; }
      if(zones.Count()<=0)
        { reason="no zone in the registry (ZRE published none)"; return GATE_FAIL; }
      return GATE_PASS;
     }
  };

//====================================================================
// 3. LOCATION GATE  (R1) - the gate the tactical path never had.
//====================================================================
class CLocationGate : public IGate
  {
public:
   virtual string    Name() { return "LOCATION"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_WATCH;
      if(c.dir==0) { reason="no direction"; return GATE_FAIL; }

      //--- 3.0 the candidate must cite a zone that exists
      SQZone z;
      if(!zones.Find(c.zone_id,z))
        { reason="zone '"+c.zone_id+"' is not in the registry"; return GATE_FAIL; }

      //--- 3.1 BETWEEN ZONES -> NO TRADE (R1, last bullet)
      SQZoneHit hit;
      if(!zones.Nearest(ctx.price,hit))
        { reason="BETWEEN ZONES - the registry holds no zone"; return GATE_FAIL; }
      if(hit.gap_atr>cfg.zone_reach_atr)
        {
         reason="BETWEEN ZONES - nearest zone is "+
                DoubleToString(hit.gap_atr,2)+" ATR away, limit is "+
                DoubleToString(cfg.zone_reach_atr,2)+" ATR";
         return GATE_FAIL;
        }
      SQZone nz;
      zones.At(hit.index,nz);

      //--- 3.2 the trade must be AT the zone it cites
      if(nz.id!=c.zone_id)
        {
         reason="a nearer zone ("+zones.ZoneText(hit.index)+" @ "+
                DoubleToString(hit.gap_atr,2)+" ATR) owns this price, not "+
                c.zone_id;
         return GATE_FAIL;
        }

      //--- 3.3 zone strength is a GATE, not decoration
      if(nz.strength<cfg.min_zone_strength)
        {
         reason="zone strength "+IntegerToString(nz.strength)+" < "+
                IntegerToString(cfg.min_zone_strength)+" (weak level)";
         return GATE_FAIL;
        }

      //--- 3.4 ROLE. A signal against the role is forbidden (this is the
      //--- exact defect reported in symptom 2).
      bool want_buy=(c.dir>0);
      if(want_buy && nz.role==ZR_RESISTANCE && !c.reaction.accepted)
        {
         reason="BUY at RESISTANCE "+nz.id+" without a closed-bar breakout "+
                "(counter-trade into the level is forbidden by R1)";
         return GATE_FAIL;
        }
      if(!want_buy && nz.role==ZR_SUPPORT && !c.reaction.accepted)
        {
         reason="SELL at SUPPORT "+nz.id+" without a closed-bar breakout "+
                "(counter-trade into the level is forbidden by R1)";
         return GATE_FAIL;
        }

      //--- 3.5 a zone broken by a closed bar flips role only after a
      //--- retest; before that, trades against the break are forbidden.
      if(nz.broken_closed && !nz.retested)
        {
         int break_dir=(nz.birth_role==ZR_SUPPORT ? -1 : +1);
         if(c.dir==-break_dir)
           {
            reason="zone "+nz.id+" was broken by a closed bar and has not "+
                   "been retested yet - no counter-break trade (R1)";
            return GATE_FAIL;
           }
        }

      //--- 3.6 the reaction facts must exist and agree with the direction
      if(!c.reaction.valid)
        { reason="no closed-bar reaction/acceptance at "+nz.id; return GATE_FAIL; }
      if(c.reaction.dir!=c.dir)
        {
         reason="the closed-bar fact at this zone points "+
                (c.reaction.dir>0?"BUY":"SELL")+", the candidate points "+
                (c.dir>0?"BUY":"SELL");
         return GATE_FAIL;
        }
      if(!c.reaction.accepted && !c.reaction.closed_back)
        { reason="the bar touched the zone but neither rejected nor accepted it"; return GATE_FAIL; }
      if(!c.reaction.accepted && !c.reaction.penetration_bounded)
        {
         reason="penetration "+DoubleToString(c.reaction.penetration_atr,2)+
                " ATR exceeds the bounded limit "+DoubleToString(cfg.max_penetration_atr,2)+" ATR";
         return GATE_FAIL;
        }

      //--- 3.7 evidence count. Below the minimum the candidate is a
      //--- WATCH, never a CONFIRMED (terminology rule R7).
      if(!c.reaction.accepted && c.reaction.evidence_count<cfg.min_evidence)
        {
         downgrade_state=(int)SIG_WATCH;
         reason="only "+IntegerToString(c.reaction.evidence_count)+"/"+
                IntegerToString(QEV_COUNT)+" evidence groups, "+
                IntegerToString(cfg.min_evidence)+" required; missing: "+
                c.reaction.missing;
         return GATE_DOWNGRADE;
        }
      return GATE_PASS;
     }
  };

//====================================================================
// 4. BIAS GATE  (R2) - filter, not decoration.
//====================================================================
class CBiasGate : public IGate
  {
public:
   virtual string    Name() { return "HTF_BIAS"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_COUNTER_TREND;
      if(c.dir==0) { reason="no direction"; return GATE_FAIL; }

      int agree=0;
      if(ctx.bias_score>0)      agree=(c.dir>0 ? +1 : -1);
      else if(ctx.bias_score<0) agree=(c.dir>0 ? -1 : +1);
      else if(ctx.d1_bias!=0)   agree=(ctx.d1_bias==c.dir ? +1 : -1);
      else if(ctx.h4_bias!=0)   agree=(ctx.h4_bias==c.dir ? +1 : -1);
      else if(ctx.h1_bias!=0)   agree=(ctx.h1_bias==c.dir ? +1 : -1);
      //--- agree == 0 means NEUTRAL OR UNKNOWN. Unknown is never counted
      //--- as agreement, so a missing HTF cannot license a signal.
      if(agree>=0) return GATE_PASS;

      if(!cfg.allow_countertrend)
        {
         reason="HTF bias opposes this direction (consensus "+
                IntegerToString(ctx.bias_score)+") and counter-trend is disabled";
         return GATE_FAIL;
        }
      int need_ev=cfg.min_evidence+cfg.countertrend_extra_evidence;
      if(c.reaction.evidence_count<need_ev)
        {
         reason="COUNTER-TREND: only "+IntegerToString(c.reaction.evidence_count)+
                " evidence groups, "+IntegerToString(need_ev)+
                " required against the HTF bias (consensus "+
                IntegerToString(ctx.bias_score)+"); missing: "+c.reaction.missing;
         return GATE_FAIL;
        }
      if(c.score<cfg.countertrend_min_score)
        {
         reason="COUNTER-TREND: evidence score "+IntegerToString(c.score)+" < "+
                IntegerToString(cfg.countertrend_min_score)+
                " required against the HTF bias (consensus "+
                IntegerToString(ctx.bias_score)+")";
         return GATE_FAIL;
        }
      downgrade_state=(int)SIG_COUNTER_TREND;
      reason="COUNTER-TREND / SCALP ONLY - HTF consensus "+
             IntegerToString(ctx.bias_score)+" opposes this direction";
      return GATE_DOWNGRADE;
     }
  };

//====================================================================
// 5. ROOM / RR GATE  (R4)
//====================================================================
class CRoomGate : public IGate
  {
public:
   virtual string    Name() { return "ROOM_RR"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_LIMITED_ROOM;
      if(c.dir==0) { reason="no direction"; return GATE_FAIL; }
      double risk=(c.dir>0 ? c.entry-c.sl : c.sl-c.entry);
      if(!(risk>0.0) || !MathIsValidNumber(risk))
        { reason="STOP GEOMETRY - the stop is not on the risk side of the entry"; return GATE_FAIL; }
      if(ctx.atr>0.0 && risk>cfg.max_stop_atr*ctx.atr)
        {
         reason="STOP "+DoubleToString(risk/ctx.atr,2)+" ATR > max "+
                DoubleToString(cfg.max_stop_atr,2)+" ATR";
         return GATE_FAIL;
        }
      if(c.rr<cfg.min_rr-1.0e-9)
        {
         reason="LIMITED ROOM - RR to TP1 is "+DoubleToString(c.rr,2)+
                ", minimum is "+DoubleToString(cfg.min_rr,2);
         return GATE_FAIL;
        }
      //--- the nearest opposing barrier must leave the room the RR needs
      if(c.room_atr>=0.0)
        {
         double need=(c.rr+1.0)*risk/ctx.atr;
         if(c.room_atr<need-1.0e-9)
           {
            reason="LIMITED ROOM - nearest opposing barrier is "+
                   DoubleToString(c.room_atr,2)+" ATR away, TP1 needs "+
                   DoubleToString(need,2)+" ATR";
            return GATE_FAIL;
           }
        }
      return GATE_PASS;
     }
  };

//====================================================================
// 6. VOLATILITY-REGIME GATE
//====================================================================
class CVolatilityGate : public IGate
  {
public:
   virtual string    Name() { return "VOLATILITY"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_WATCH;
      if(ctx.regime==VREG_DEAD)
        { reason="volatility regime DEAD - no signal in a dead market"; return GATE_FAIL; }
      if(ctx.regime==VREG_EXTREME)
        {
         int need=cfg.min_evidence+1;
         if(c.reaction.evidence_count<need)
           {
            downgrade_state=(int)SIG_WATCH;
            reason="EXTREME volatility: "+IntegerToString(c.reaction.evidence_count)+
                   " evidence groups, "+IntegerToString(need)+" required; missing: "+
                   c.reaction.missing;
            return GATE_DOWNGRADE;
           }
        }
      return GATE_PASS;
     }
  };

//====================================================================
// 7. COOLDOWN GATE  (R5)
//====================================================================
class CCooldownGate : public IGate
  {
private:
   IAlertHistory    *m_hist;
public:
                     CCooldownGate() { m_hist=NULL; }
   void              Attach(IAlertHistory *h) { m_hist=h; }
   virtual string    Name() { return "COOLDOWN"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_WATCH;
      if(m_hist==NULL) return GATE_PASS;    // no history => nothing to suppress
      if(cfg.cooldown_bars<=0) return GATE_PASS;
      string key=c.zone_id+"|"+IntegerToString(c.dir)+"|"+IntegerToString(c.state);
      int since=m_hist.BarsSince(key,ctx.closed_index);
      if(since>=0 && since<cfg.cooldown_bars)
        {
         reason="cooldown: "+IntegerToString(since)+" of "+
                IntegerToString(cfg.cooldown_bars)+" bars since the last "+
                QSMC_StateName(c.state)+" on this zone";
         return GATE_FAIL;
        }
      return GATE_PASS;
     }
  };

//====================================================================
// 8. FLIP-FLOP GATE  (R5) - opposite direction in the same zone.
//====================================================================
class CFlipFlopGate : public IGate
  {
private:
   IAlertHistory    *m_hist;
public:
                     CFlipFlopGate() { m_hist=NULL; }
   void              Attach(IAlertHistory *h) { m_hist=h; }
   virtual string    Name() { return "FLIPFLOP"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_WATCH;
      if(m_hist==NULL) return GATE_PASS;
      if(cfg.flipflop_bars<=0) return GATE_PASS;
      int since=m_hist.BarsSinceOpposite(c.zone_id,c.dir,ctx.closed_index);
      if(since>=0 && since<cfg.flipflop_bars)
        {
         reason="flip-flop guard: the opposite direction fired "+
                IntegerToString(since)+" bars ago on the same zone (guard "+
                IntegerToString(cfg.flipflop_bars)+" bars)";
         return GATE_FAIL;
        }
      return GATE_PASS;
     }
  };

//====================================================================
// 9. MINIMUM-PRICE-DISTANCE GATE  (R5)
//====================================================================
class CDistanceGate : public IGate
  {
private:
   IAlertHistory    *m_hist;
public:
                     CDistanceGate() { m_hist=NULL; }
   void              Attach(IAlertHistory *h) { m_hist=h; }
   virtual string    Name() { return "DISTANCE"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_WATCH;
      if(m_hist==NULL) return GATE_PASS;
      if(cfg.min_alert_distance_atr<=0.0 || !(ctx.atr>0.0)) return GATE_PASS;
      string key=c.zone_id+"|"+IntegerToString(c.dir);
      double d=m_hist.PriceDistanceATR(key,c.entry,ctx.atr);
      if(d>=0.0 && d<cfg.min_alert_distance_atr-1.0e-9)
        {
         reason="only "+DoubleToString(d,2)+" ATR from the previous alert on this "+
                "zone+direction, minimum is "+
                DoubleToString(cfg.min_alert_distance_atr,2)+" ATR";
         return GATE_FAIL;
        }
      return GATE_PASS;
     }
  };

//====================================================================
// 10. SESSION GATE (optional; disabled by default)
//====================================================================
class CSessionGate : public IGate
  {
public:
   virtual string    Name() { return "SESSION"; }
   virtual ENUM_GATE_RESULT Evaluate(const SSignalCandidate &c,const SGateCtx &ctx,
                                     const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                     string &reason,int &downgrade_state)
     {
      reason=""; downgrade_state=(int)SIG_WATCH;
      if(ctx.session_ok<0) return GATE_PASS;      // filter disabled
      if(ctx.session_ok==0)
        {
         MqlDateTime dt;
         TimeToStruct(ctx.bar_time,dt);
         reason="outside the configured session ("+IntegerToString(dt.hour)+"h)";
         return GATE_FAIL;
        }
      return GATE_PASS;
     }
  };

#endif
//+------------------------------------------------------------------+
