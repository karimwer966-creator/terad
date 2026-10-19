//+------------------------------------------------------------------+
//|                                                  QSMC_Root.mqh   |
//|  CQuantumRoot - the single root object. This is the ONLY global    |
//|  mutable state the v6.6.0 subsystem adds to the host indicator.   |
//|                                                                   |
//|  Ownership: every member is created in Init() and destroyed in    |
//|  Deinit()/the destructor. AllocCalls()/FreeCalls() counters let   |
//|  the user verify there is no leak (printed on Deinit).            |
//|                                                                   |
//|  CALL ORDER per closed bar (host side)                            |
//|   1. root.Refresh(ext_atr, spread_points)  -> data + context      |
//|   2. root.SetZones(arr,n)                  -> fresh ZRE zones     |
//|   3. root.TacticalObserve(fact)            -> record a tactical   |
//|      fact whenever the host's tactical path fires (no decision)   |
//|   4. root.FinalizeBar(auth_pending)        -> gates + at most one |
//|      alert + chart + CSV                                          |
//|                                                                   |
//|  COMPLEXITY: Refresh O(sum of series), SetZones O(N log N),        |
//|  FinalizeBar O(C*G*(log N + k)). All once per closed bar.          |
//+------------------------------------------------------------------+
#ifndef __QSMC_ROOT_MQH__
#define __QSMC_ROOT_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_MarketData.mqh>
#include <QSMC/QSMC_Zones.mqh>
#include <QSMC/QSMC_Reaction.mqh>
#include <QSMC/QSMC_Bias.mqh>
#include <QSMC/QSMC_Preset.mqh>
#include <QSMC/QSMC_Gates.mqh>
#include <QSMC/QSMC_AlertManager.mqh>
#include <QSMC/QSMC_Arbiter.mqh>
#include <QSMC/QSMC_Stats.mqh>
#include <QSMC/QSMC_Renderer.mqh>

//--------------------------------------------------------------------
// What the host's MTF tactical path observed. Recorded as a FACT;
// the arbiter decides what (if anything) it means.
//--------------------------------------------------------------------
struct STacticalFact
  {
   bool              valid;
   bool              bull;
   bool              closed_confirm;   // the fact came from a CLOSED exec bar
   double            entry_price;      // ep (close of the exec bar for CONFIRMED)
   datetime          exec_bar_time;    // et
   ENUM_TIMEFRAMES   exec_tf;
   double            trigger;          // structure price that triggered it
   datetime          trigger_time;
   bool              core_owned;
   double            chase_atr;        // distance from close to the trigger, ATR
  };

#define QSMC_TACTICAL_MAX_FACTS 4

//+------------------------------------------------------------------+
class CQuantumRoot
  {
private:
   bool              m_ready;
   CMarketData       m_md;
   CZoneRegistry     m_zones;
   CReactionDetector m_reaction;
   CBiasProvider     m_bias;
   CPresetManager    m_preset;
   CSignalArbiter    m_arbiter;
   CAlertManager     m_alerts;
   CStatsLogger      m_stats;
   CChartRenderer    m_render;

   SQsmcArbConfig    m_cfg;
   SGateCtx          m_ctx;
   SArbiterReport    m_rep;

   SQZone             m_zone_src[];
   int               m_zone_src_n;

   STacticalFact     m_tac[QSMC_TACTICAL_MAX_FACTS];
   int               m_tac_n;
   datetime          m_tac_bar_time;

   int               m_last_state;
   string            m_last_text;
   int               m_bars;
   bool              m_deinit_done;
   bool              m_cfg_locked;
   bool              m_bias_external;
   int               m_ext_d1, m_ext_h4, m_ext_h1;
   bool              m_ext_h1_known;

   //------------------------------------------------------------------
   ENUM_VOL_REGIME   VolRegime() const
     {
      const CBarSeries *ch=m_md.Chart();
      if(ch==NULL) return VREG_UNKNOWN;
      int ci=ch.ClosedIndex();
      if(ci<20) return VREG_UNKNOWN;
      double short_tr=ch.MeanTrueRange(ci,14);
      double long_tr =ch.MeanTrueRange(ci,100);
      if(!(short_tr>0.0) || !(long_tr>0.0)) return VREG_UNKNOWN;
      double ratio=short_tr/long_tr;
      if(ratio<0.35) return VREG_DEAD;
      if(ratio<0.70) return VREG_LOW;
      if(ratio<=1.40) return VREG_NORMAL;
      if(ratio<=2.20) return VREG_HIGH;
      return VREG_EXTREME;
     }

   int               SessionOK(const datetime bar_time) const
     {
      if(m_cfg.session_start_hour<0 || m_cfg.session_end_hour<0) return -1;
      MqlDateTime dt;
      TimeToStruct(bar_time,dt);
      int h=dt.hour;
      int a=m_cfg.session_start_hour, b=m_cfg.session_end_hour;
      if(a==b) return 1;
      if(a<b) return ((h>=a && h<b)?1:0);
      //--- window wraps midnight
      return ((h>=a || h<b)?1:0);
     }

public:
                     CQuantumRoot()
     { m_ready=false; m_zone_src_n=0; m_tac_n=0; m_tac_bar_time=0;
       m_last_state=(int)SIG_NONE; m_last_text=""; m_bars=0; m_deinit_done=false;
       m_cfg_locked=false; m_bias_external=false; m_ext_h1_known=true; }

                    ~CQuantumRoot() { Deinit(); }

   bool              Ready() const { return m_ready; }
   int               Bars()  const { return m_bars;  }
   const SGateCtx   &Ctx()   const { return m_ctx;   }
   const SQsmcArbConfig &Cfg() const { return m_cfg; }
   const SArbiterReport &Report() const { return m_rep; }
   CZoneRegistry    &Zones() { return m_zones; }
   CMarketData      &Market() { return m_md; }
   CSignalArbiter   &Arbiter() { return m_arbiter; }
   CStatsLogger     &Stats() { return m_stats; }

   //=================================================================
   // Init / Deinit
   //=================================================================
   bool              Init(const string symbol,const ENUM_TIMEFRAMES chart_tf,
                          const ENUM_TIMEFRAMES exec_tf,const int bars,
                          const int atr_period,const bool tactical_may_confirm,
                          const bool gate_core,const bool csv_log,
                          const int min_sample,const bool draw)
     {
      m_deinit_done=false;
      m_preset.Build(m_cfg,chart_tf);
      if(!m_md.Init(symbol,chart_tf,exec_tf,bars,atr_period)) return false;
      m_alerts.Init(m_cfg.dedupe_ring);
      m_arbiter.Init(GetPointer(m_alerts),tactical_may_confirm,gate_core);
      m_render.Init(0,0,draw);
      if(csv_log) m_stats.Open(symbol,chart_tf,min_sample);
      m_ready=true;
      m_bars=0;
      Print("[QSMC_ARB] v6.6.0 arbitration layer ON | preset ",m_preset.EffectiveName(),
            " | gates ",IntegerToString(m_arbiter.GateCount()),
            " | exec TF ",QSMC_TFName(exec_tf),
            " | tactical may confirm: ",(tactical_may_confirm?"YES":"NO (informational only)"));
      return true;
     }

   void              Deinit()
     {
      if(m_deinit_done) return;         // idempotent: Init/Deinit/Destructor
      m_deinit_done=true;
      if(m_bars>0 || m_ready)
        {
         Print("[QSMC_ARB] stop | bars ",IntegerToString(m_bars),
               " | published ",IntegerToString(m_alerts.Published()),
               " | suppressed ",IntegerToString(m_alerts.Suppressed()));
         Print("[QSMC_ARB] outcomes: ",m_stats.Summary());
        }
      //--- Release the gates FIRST so the counters balance before the
      //--- leak report is printed (the destructor must not be the only
      //--- place a `new` is matched).
      m_arbiter.Shutdown();
      if(m_bars>0 || m_ready) Print("[QSMC_ARB] ",LeakReport());
      if(m_cfg.use_global_vars) m_alerts.CleanupGlobalVars();
      m_render.Clear();
      m_stats.Close();
      m_ready=false;
     }

   //--- Leak verification: every `new` must be matched by a `delete`.
   //--- Called AFTER Shutdown(), so alloc == free when this returns
   //--- "no leak".
   string            LeakReport() const
     {
      int a=m_md.AllocCalls()+m_arbiter.AllocCalls();
      int f=m_md.FreeCalls()+m_arbiter.FreeCalls();
      string s="alloc/free: market ",IntegerToString(m_md.AllocCalls()),"/",
             IntegerToString(m_md.FreeCalls()),
             " | gates ",IntegerToString(m_arbiter.AllocCalls()),"/",
             IntegerToString(m_arbiter.FreeCalls()),
             " | chart objects created/deleted ",IntegerToString(m_render.Created()),"/",
             IntegerToString(m_render.Deleted());
      s+=(a==f ? " => no leak" : " => LEAK (alloc "+IntegerToString(a)+
          " vs free "+IntegerToString(f)+")");
      return s;
     }

   //=================================================================
   // Per-bar pipeline
   //=================================================================

   //--- 1a. Refresh the series from the terminal, then build the context.
   bool              Refresh(const double external_atr,const double spread_points)
     {
      if(!m_ready) return false;
      m_preset.Build(m_cfg,(ENUM_TIMEFRAMES)_Period);
      if(!m_cfg.enabled)
        {
         ResetContext("arbitration disabled (InpArbEnabled=false)");
         return false;
        }
      if(!m_md.RefreshAll(external_atr))
        { ResetContext(m_md.Reason()); return false; }
      return BuildContext(spread_points);
     }

   //--- 1b. Build the decision context from whatever the series hold.
   //--- Public so the offline self-test can drive the production path
   //--- after loading synthetic bars (see QSMC_Selftest.mqh).
   bool              BuildContext(const double spread_points)
     {
      if(!m_ready) return false;
      if(!m_cfg_locked) m_preset.Build(m_cfg,(ENUM_TIMEFRAMES)_Period);

      //--- reset the context; every field is set explicitly below
      m_ctx.symbol=_Symbol;
      m_ctx.tf=(ENUM_TIMEFRAMES)_Period;
      m_ctx.closed_index=-1;
      m_ctx.closed_time=0;
      m_ctx.bar_index=-1;
      m_ctx.bar_time=0;
      m_ctx.bar_closed=false;
      m_ctx.price=0.0;
      m_ctx.atr=0.0;
      m_ctx.point=_Point;
      m_ctx.tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      if(!(m_ctx.tick_size>0.0)) m_ctx.tick_size=_Point;
      m_ctx.digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
      m_ctx.spread_points=spread_points;
      m_ctx.data_ready=false;
      m_ctx.data_reason="context not built";
      m_ctx.htf_bias=0; m_ctx.d1_bias=0; m_ctx.h4_bias=0; m_ctx.h1_bias=0;
      m_ctx.bias_score=0;
      m_ctx.regime=VREG_UNKNOWN;
      m_ctx.session_ok=-1;

      if(!m_cfg.enabled)
        { m_ctx.data_reason="arbitration disabled (InpArbEnabled=false)"; return false; }

      const CBarSeries *ch=m_md.Chart();
      if(ch==NULL || !ch.Ready()) { m_ctx.data_reason="chart series not ready"; return false; }
      int ci=ch.ClosedIndex();
      if(ci<2) { m_ctx.data_reason="fewer than 3 closed bars"; return false; }
      double atr=ch.ATR();
      if(!(atr>0.0) || !MathIsValidNumber(atr))
        { m_ctx.data_reason="ATR unavailable"; return false; }

      m_ctx.closed_index=ci;
      m_ctx.closed_time=ch.T(ci);
      m_ctx.bar_index=ci;
      m_ctx.bar_time=ch.T(ci);
      m_ctx.bar_closed=true;
      m_ctx.price=ch.C(ci);
      m_ctx.atr=atr;
      m_ctx.regime=VolRegime();
      m_ctx.session_ok=SessionOK(m_ctx.bar_time);

      m_bias.Update(m_md,m_cfg,ci);
      m_ctx.htf_bias=m_bias.Consensus();
      m_ctx.d1_bias=m_bias.D1();
      m_ctx.h4_bias=m_bias.H4();
      m_ctx.h1_bias=m_bias.H1();
      m_ctx.bias_score=m_bias.Score();

      ApplyExternalBias();

      m_ctx.data_ready=true;
      m_ctx.data_reason="";
      m_bars++;
      return true;
     }

   void              ResetContext(const string reason)
     {
      m_ctx.symbol=_Symbol;
      m_ctx.tf=(ENUM_TIMEFRAMES)_Period;
      m_ctx.closed_index=-1; m_ctx.closed_time=0;
      m_ctx.bar_index=-1;    m_ctx.bar_time=0;   m_ctx.bar_closed=false;
      m_ctx.price=0.0; m_ctx.atr=0.0;
      m_ctx.point=_Point;
      m_ctx.tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      if(!(m_ctx.tick_size>0.0)) m_ctx.tick_size=_Point;
      m_ctx.digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
      m_ctx.spread_points=0.0;
      m_ctx.data_ready=false;
      m_ctx.data_reason=reason;
      m_ctx.htf_bias=0; m_ctx.d1_bias=0; m_ctx.h4_bias=0; m_ctx.h1_bias=0;
      m_ctx.bias_score=0;
      m_ctx.regime=VREG_UNKNOWN;
      m_ctx.session_ok=-1;
     }

   //------------------------------------------------------------------
   // TEST SEAM ONLY. Load synthetic bars into the chart and execution
   // series so QSMC_Selftest can drive the production code path.
   // Production must never call this.
   //------------------------------------------------------------------
   bool              LoadSynthetic(const double &o[],const double &h[],const double &l[],
                                   const double &c[],const datetime &t[],const long &v[],
                                   const int n,
                                   const double &eo[],const double &eh[],const double &el[],
                                   const double &ec[],const datetime &et[],const long &ev[],
                                   const int en)
     {
      if(!m_ready) return false;
      CBarSeries *ch=m_md.MutableChart();
      CBarSeries *ex=m_md.MutableExec();
      if(ch==NULL || ex==NULL) return false;
      bool a=ch.LoadSynthetic(o,h,l,c,t,v,n);
      bool b=ex.LoadSynthetic(eo,eh,el,ec,et,ev,en);
      if(!a || !b) { Print("[QSMC_ARB] synthetic load failed: ",ch.NotReadyReason()," / ",ex.NotReadyReason()); return false; }
      //--- the D1/H4/H1 series stay empty: an unknown HTF must never be
      //--- reported as agreement, which is what the bias gate asserts.
      return true;
     }

   //--- 2. Feed the fresh ZRE zone list. `src` may be empty.
   //------------------------------------------------------------------
   // Configuration control.
   //  LockConfig(): freeze an explicit configuration (used by the host
   //  when it supplies its own, and by the offline self-test). While
   //  locked, BuildContext() will not overwrite it from the presets.
   //  SetExternalBias(): let a host that already computes D1/H4/H1 bias
   //  publish it here, so the indicator keeps ONE bias on every panel.
   //------------------------------------------------------------------
   void              LockConfig(const SQsmcArbConfig &cfg) { m_cfg=cfg; m_cfg_locked=true; }
   void              UnlockConfig() { m_cfg_locked=false; }
   bool              ConfigLocked() const { return m_cfg_locked; }
   SQsmcArbConfig   &MutableConfig() { return m_cfg; }

   //--- d1/h4/h1 are +1 / -1 / 0. `h1_known=false` removes H1 from the
   //--- weight sum instead of counting an unknown timeframe as neutral
   //--- agreement: an unknown TF must never license a signal.
   void              SetExternalBias(const int d1,const int h4,const int h1,
                                     const bool h1_known=true)
     {
      m_ext_d1=d1; m_ext_h4=h4; m_ext_h1=h1; m_ext_h1_known=h1_known;
      m_bias_external=true;
      ApplyExternalBias();
     }

   //--- Applied at the end of every BuildContext() so a host that feeds
   //--- its own bias never has to remember the call order.
   void              ApplyExternalBias()
     {
      if(!m_bias_external) return;
      int d1=m_ext_d1, h4=m_ext_h4, h1=m_ext_h1;
      int wsum=MathAbs(m_cfg.w_d1)+MathAbs(m_cfg.w_h4)+(m_ext_h1_known?MathAbs(m_cfg.w_h1):0);
      if(wsum<1) wsum=1;
      int score=(int)MathRound((double)(m_cfg.w_d1*d1+m_cfg.w_h4*h4+
                (m_ext_h1_known?m_cfg.w_h1*h1:0))*100.0/(double)wsum);
      if(score>100)  score=100;
      if(score<-100) score=-100;
      m_ctx.d1_bias=d1;
      m_ctx.h4_bias=h4;
      m_ctx.h1_bias=h1;
      m_ctx.bias_score=score;
      if(score>0)          m_ctx.htf_bias=1;
      else if(score<0)     m_ctx.htf_bias=-1;
      else if(d1!=0)       m_ctx.htf_bias=d1;
      else if(h4!=0)       m_ctx.htf_bias=h4;
      else                 m_ctx.htf_bias=h1;
     }
   bool              BiasExternal() const { return m_bias_external; }

   void              SetZones(const SQZone &src[],const int n)
     {
      if(!m_ready) return;
      m_zone_src_n=(int)MathMax(0,MathMin(QSMC_ZONE_MAX,n));
      ArrayResize(m_zone_src,QSMC_ZONE_MAX);
      for(int i=0;i<QSMC_ZONE_MAX;i++)
        {
         if(i<m_zone_src_n) m_zone_src[i]=src[i];
        }
      if(!m_ctx.data_ready || !(m_ctx.atr>0.0)) return;

      //--- R1: a zone broken by a CLOSED bar earns its new role only
      //--- AFTER a retest. Resolve that here, once per closed bar, from
      //--- the chart series (never from the forming bar).
      const CBarSeries *ch=m_md.Chart();
      if(ch!=NULL && ch.Ready())
        {
         int look=(int)MathMax(4,m_cfg.retest_lookback_bars);
         for(int i=0;i<m_zone_src_n;i++)
           {
            if(!m_zone_src[i].broken_closed) continue;
            if(m_zone_src[i].birth_role==ZR_NEUTRAL) continue;
            int brk=(m_zone_src[i].birth_role==ZR_SUPPORT ? -1 : +1);
            if(m_reaction.DetectRetest(m_zone_src[i],*ch,m_ctx.closed_index,
                                       look,m_ctx.atr,brk))
               m_zone_src[i].retested=true;
           }
        }

      m_zones.Rebuild(m_zone_src,m_zone_src_n,m_ctx.atr,
                      m_cfg.merge_tol_atr,m_cfg.min_zone_strength);
     }

   //--- 3. Record a tactical fact (no decision is taken here).
   void              TacticalObserve(const STacticalFact &f)
     {
      if(!m_ready || !m_cfg.enabled) return;
      if(!f.valid) return;
      if(m_ctx.bar_time!=m_tac_bar_time)
        { m_tac_n=0; m_tac_bar_time=m_ctx.bar_time; }
      if(m_tac_n>=QSMC_TACTICAL_MAX_FACTS) return;
      m_tac[m_tac_n]=f;
      m_tac_n++;
     }

   //=================================================================
   // Build one candidate from a tactical fact, evaluate it against the
   // current registry, and return the resulting state.
   // `out` carries the full candidate (for the chart label + arbiter).
   // `reason` is always populated (R6).
   //=================================================================
   int               BuildTacticalCandidate(const STacticalFact &f,
                                            SSignalCandidate &out,string &reason)
     {
      out.valid=false;
      out.source=SRC_TACTICAL;
      out.reject_text=""; out.reject_count=0; out.downgraded=false;
      out.reason=""; out.extra="";

      if(!m_ctx.data_ready) { reason="data not ready: "+m_ctx.data_reason; out.reason=reason; return (int)SIG_NO_TRADE; }
      if(m_zones.Count()<=0) { reason="no zone in the registry"; out.reason=reason; return (int)SIG_NO_TRADE; }

      //--- Which price decided? For a CONFIRMED fact the closed exec bar
      //--- close; for a live PREVIEW the forming exec bar close. Shift 0
      //--- may be READ for a PREVIEW but can never produce CONFIRMED.
      double px=f.entry_price;
      if(!(px>0.0)) { reason="no decision price"; out.reason=reason; return (int)SIG_NO_TRADE; }

      //--- 1) LOCATION FIRST (R1). Direction comes from the zone, never
      //--- from the HTF bias alone. This single change removes the
      //--- "SELL inside support / BUY into resistance" defect.
      SQZoneHit hit;
      if(!m_zones.Nearest(px,hit))
        { reason="BETWEEN ZONES - no zone in the registry"; out.reason=reason; return (int)SIG_NO_TRADE; }
      if(hit.gap_atr>m_cfg.zone_reach_atr)
        {
         reason="BETWEEN ZONES - nearest zone is "+DoubleToString(hit.gap_atr,2)+
                " ATR away (limit "+DoubleToString(m_cfg.zone_reach_atr,2)+" ATR)";
         out.reason=reason;
         return (int)SIG_NO_TRADE;
        }
      SQZone z;
      if(!m_zones.At(hit.index,z))
        { reason="zone lookup failed"; out.reason=reason; return (int)SIG_NO_TRADE; }

      //--- 2) The closed-bar fact at that zone. Evaluated on the
      //--- EXECUTION series, because that is the bar that produced it.
      SReactionFacts rf;
      const CBarSeries *ex=m_md.Exec();
      int eidx=-1;
      if(ex!=NULL && ex.Ready())
        {
         int i=ex.IndexOfTime(f.exec_bar_time);
         if(i>=1 && i<=ex.ClosedIndex()) eidx=i;
        }
      bool have_fact=false;
      if(eidx>=0)
        {
         double ex_atr=ex.ATRAt(eidx);
         if(!(ex_atr>0.0)) ex_atr=m_ctx.atr;
         const CBarSeries *ltf=(f.exec_tf==(ENUM_TIMEFRAMES)_Period ? NULL : ex);
         have_fact=m_reaction.Evaluate(z,*ex,eidx,ex_atr,m_cfg,ltf,rf);
        }

      //--- 3) Direction. It is taken from the ZONE ROLE + the closed-bar
      //--- fact, and the tactical hint is only allowed to agree with it.
      int dir=0;
      if(have_fact && rf.dir!=0) dir=rf.dir;
      else
        {
         //--- No accepted/rejected fact at the zone: the tactical hint is
         //--- NOT a reason to trade. Report it and stop.
         reason="the execution bar did not reject or accept "+z.id+
                " - the MTF trigger alone is not a location fact";
         out.reason=reason;
         out.zone_id=z.id;
         out.zone_lo=z.lo; out.zone_hi=z.hi;
         out.zone_role=z.role; out.zone_strength=z.strength;
         out.distance_atr=hit.gap_atr;
         out.dir=(f.bull?+1:-1);
         out.state=(int)SIG_NO_TRADE;
         out.bar_time=m_ctx.bar_time;
         out.bar_index=m_ctx.closed_index;
         out.bar_closed=true;
         out.valid=true;
         return (int)SIG_NO_TRADE;
        }

      //--- 4) Fill the candidate
      out.valid=true;
      out.source=SRC_TACTICAL;
      out.dir=dir;
      out.zone_id=z.id;
      out.zone_lo=z.lo;
      out.zone_hi=z.hi;
      out.zone_role=z.role;
      out.zone_strength=z.strength;
      out.reaction=rf;
      out.distance_atr=hit.gap_atr;
      out.bar_time=m_ctx.bar_time;
      out.bar_index=m_ctx.closed_index;
      out.bar_closed=f.closed_confirm;      // R3: PREVIEW cannot confirm
      out.evidence_text=QSMC_EvidenceList(rf.evidence_mask);

      //--- 5) Geometry: entry / stop / TP1 / RR / room. Shared with the
      //--- offline self-test so the two implementations cannot diverge.
      double atr=m_ctx.atr;
      double entry=px;
      double sl=0.0,tp1=0.0,tp2=0.0,tp3=0.0,rr=0.0,room_atr=-1.0;
      if(!QSMC_BuildGeometry(z,dir,entry,atr,m_zones,m_cfg,m_ctx.tick_size,
                             sl,tp1,tp2,tp3,rr,room_atr))
        {
         reason="STOP GEOMETRY - stop "+DoubleToString(MathAbs(entry-sl)/atr,2)+
                " ATR exceeds the "+DoubleToString(m_cfg.max_stop_atr,2)+" ATR limit";
         out.reason=reason;
         out.state=(int)SIG_NO_TRADE;
         return (int)SIG_NO_TRADE;
        }

      out.entry=entry;
      out.sl=sl;
      out.tp1=tp1;
      out.tp2=tp2;
      out.tp3=tp3;
      out.rr=rr;
      out.room_atr=room_atr;
      out.score=m_reaction.Score(rf,z.strength);

      //--- 6) The requested state: CONFIRMED for a closed-bar fact.
      //--- The arbiter caps a tactical source at TACTICAL-INFO (R7).
      out.state=(int)SIG_CONFIRMED;
      out.extra="MTF trigger "+DoubleToString(f.trigger,m_ctx.digits)+
                " @ "+TimeToString(f.trigger_time,TIME_MINUTES)+
                (f.core_owned?" | owned by the CORE setup":" | from HTF bias / early break");
      if(f.chase_atr>0.0) out.extra+=" | chase "+DoubleToString(f.chase_atr,2)+" ATR";
      reason="";
      out.reason="";
      return out.state;
     }

   //--- Round to the symbol tick grid so TP/SL are always placeable.
   double            RoundNear(const double anchor,const double v) const
     {
      double tick=m_ctx.tick_size;
      if(!(tick>0.0)) tick=_Point;
      double r=MathRound(v/tick)*tick;
      if(!(r>0.0)) r=v;
      return r;
     }

   //=================================================================
   // 4. Finalize: evaluate everything recorded for this bar, publish
   // at most one signal, draw it, and journal it.
   //=================================================================
   bool              FinalizeBar(const bool auth_pending)
     {
      m_rep.submitted=0; m_rep.evaluated=0; m_rep.published=false;
      m_rep.trace=""; m_rep.gate_line_count=0; m_rep.primary.valid=false;

      if(!m_ready || !m_cfg.enabled) return false;
      if(!m_ctx.data_ready)
        {
         m_last_state=(int)SIG_NO_TRADE;
         m_last_text="data not ready: "+m_ctx.data_reason;
         if(InpArbVerboseLog) Print("[QSMC_ARB] ",m_last_text);
         m_render.DrawSuppressed(m_last_text,m_ctx.bar_time,m_ctx.price,
                                 m_ctx.atr,m_ctx.point,m_ctx.digits);
         return false;
        }

      //--- submit every tactical fact recorded this bar
      for(int i=0;i<m_tac_n;i++)
        {
         SSignalCandidate c;
         string why="";
         BuildTacticalCandidate(m_tac[i],c,why);
         if(c.valid && c.dir!=0)
            m_arbiter.Submit(c,m_ctx.bar_time);
        }
      m_tac_n=0;

      m_arbiter.SetAuthoritativePending(auth_pending);
      bool ok=m_arbiter.Finalize(m_ctx,m_cfg,m_zones,m_alerts,m_rep);

      if(ok && m_rep.primary.valid)
        {
         m_stats.Log(m_rep.primary,m_ctx,true);
         m_render.DrawPrimary(m_rep.primary,m_ctx,m_ctx.atr);
         m_last_state=m_rep.primary.state;
         m_last_text=QSMC_StateName(m_rep.primary.state)+" "+
                     (m_rep.primary.dir>0?"BUY":"SELL")+" "+m_rep.primary.zone_id;
        }
      else
        {
         m_render.ClearPrimary();
         //--- Explain the silence. Never a bare "NO TRADE".
         string why=m_rep.trace;
         if(why=="") why="no candidate survived the gates";
         m_last_state=(int)SIG_NO_TRADE;
         m_last_text=why;
         m_render.DrawSuppressed(why,m_ctx.bar_time,m_ctx.price,
                                 m_ctx.atr,m_ctx.point,m_ctx.digits);
        }

      //--- outcome tracking, strictly forward-looking
      const CBarSeries *ch=m_md.Chart();
      if(ch!=NULL) m_stats.Advance(*ch,m_ctx.closed_index);

      if(InpArbVerboseLog)
        {
         Print("[QSMC_ARB] ",m_ctx.symbol," ",QSMC_TFName(m_ctx.tf),
               " bar ",TimeToString(m_ctx.bar_time,TIME_MINUTES),
               " | zones ",IntegerToString(m_zones.Count()),
               " | ",m_bias.Text(),
               " | ",m_rep.trace);
         for(int i=0;i<m_rep.gate_line_count;i++) Print("[QSMC_ARB]   ",m_rep.gate_lines[i]);
        }
      return ok;
     }

   int               LastState() const { return m_last_state; }
   string            LastText()  const { return m_last_text;  }
   int               Published() const { return m_alerts.Published(); }
   int               Suppressed() const { return m_alerts.Suppressed(); }

   //--- One-line dashboard row for the host panel (optional).
   string            StatusLine() const
     {
      return "ARB "+m_preset.EffectiveName()+" | zones "+IntegerToString(m_zones.Count())+
             " | "+m_bias.ShortText()+
             " | published "+IntegerToString(m_alerts.Published())+
             " suppressed "+IntegerToString(m_alerts.Suppressed())+
             " | last: "+m_last_text;
     }
  };

//====================================================================
// THE one global. Everything else lives inside CQuantumRoot.
//====================================================================
CQuantumRoot *g_qsmc_root=NULL;

bool QSMC_RootCreate(const ENUM_TIMEFRAMES exec_tf,const int bars,const int atr_period)
  {
   if(g_qsmc_root!=NULL) return true;
   g_qsmc_root=new CQuantumRoot();
   if(g_qsmc_root==NULL) { Print("[QSMC_ARB] root allocation failed"); return false; }
   return g_qsmc_root.Init(_Symbol,(ENUM_TIMEFRAMES)_Period,exec_tf,bars,atr_period,
                           InpArbTacticalMayConfirm,InpArbGateCore,InpArbCSVLog,
                           InpArbMinSample,true);
  }

void QSMC_RootDestroy()
  {
   if(g_qsmc_root==NULL) return;
   delete g_qsmc_root;
   g_qsmc_root=NULL;
  }

CQuantumRoot *QSMC_Root() { return g_qsmc_root; }

#endif
//+------------------------------------------------------------------+
