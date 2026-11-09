//+------------------------------------------------------------------+
//|                                               QSMC_Arbiter.mqh   |
//|  CSignalArbiter - ONE dispatcher. Every path (CORE / ZRE / RXN /  |
//|  MTF-tactical) submits the same SSignalCandidate here; it ranks   |
//|  them, runs every gate, and emits AT MOST ONE primary signal per  |
//|  closed bar.                                                      |
//|                                                                   |
//|  PRIORITY                                                         |
//|   1. An authoritative source (CORE / ZRE / RXN) always outranks   |
//|      the tactical path.                                           |
//|   2. If the host dispatcher already holds an eligible directional |
//|      candidate for this bar (SetAuthoritativePending(true)), the  |
//|      tactical path is suppressed outright - it must never steal   |
//|      the one-alert-per-bar slot from the authoritative engine.    |
//|   3. Within a priority class: higher state, then higher evidence  |
//|      score, then more evidence groups, then nearer to the price.  |
//|                                                                   |
//|  COMPLEXITY: Finalize is O(C * G * (log N + k)); C <= 32          |
//|  candidates, G = 10 gates, N <= 64 zones. Runs once per closed    |
//|  bar, never per tick.                                             |
//+------------------------------------------------------------------+
#ifndef __QSMC_ARBITER_MQH__
#define __QSMC_ARBITER_MQH__

#include <QSMC/QSMC_Types.mqh>
#include <QSMC/QSMC_Gates.mqh>
#include <QSMC/QSMC_Zones.mqh>
#include <QSMC/QSMC_Reaction.mqh>
#include <QSMC/QSMC_AlertManager.mqh>

#define QSMC_ARB_MAX_CANDIDATES  32

//--------------------------------------------------------------------
struct SArbiterReport
  {
   int               submitted;
   int               evaluated;
   int               rejected;
   int               downgraded;
   bool              published;
   SSignalCandidate  primary;
   string            gate_lines[QSMC_ARB_MAX_REASONS];
   int               gate_line_count;
   string            trace;      // one-line summary for the journal
  };

//+------------------------------------------------------------------+
class CSignalArbiter
  {
private:
   IGate            *m_gates[];
   int               m_gate_count;
   int               m_alloc_calls;
   int               m_free_calls;
   //--- concrete handles to the history-consuming gates (no RTTI in MQL5)
   CCooldownGate    *m_g_cd;
   CFlipFlopGate    *m_g_ff;
   CDistanceGate    *m_g_di;

   SSignalCandidate  m_cands[QSMC_ARB_MAX_CANDIDATES];
   int               m_cand_count;
   datetime          m_cand_bar_time;

   bool              m_auth_pending;     // host dispatcher owns this bar
   bool              m_tactical_may_confirm;
   bool              m_gate_core;

   void              PushGate(IGate *g)
     {
      if(m_gate_count>=16 || g==NULL) return;
      m_gates[m_gate_count]=g;
      m_gate_count++;
     }

   //------------------------------------------------------------------
   // State rank: higher = stronger. Used for ordering and for taking
   // the weakest downgrade a gate imposes.
   //------------------------------------------------------------------
   static int        StateRank(const int s)
     {
      switch((ENUM_SIG_STATE)s)
        {
         case SIG_CONFIRMED:     return 7;
         case SIG_LIMITED_ROOM:  return 6;
         case SIG_COUNTER_TREND: return 5;
         case SIG_TACTICAL_INFO: return 4;
         case SIG_PREVIEW:       return 3;
         case SIG_WATCH:         return 2;
         case SIG_NO_TRADE:      return 1;
         default:                return 0;
        }
      return 0;
     }

   static bool       Better(const SSignalCandidate &a,const SSignalCandidate &b)
     {
      if(!a.valid) return false;
      if(!b.valid) return true;
      int ra=StateRank(a.state), rb=StateRank(b.state);
      if(ra!=rb) return ra>rb;
      if(a.score!=b.score) return a.score>b.score;
      if(a.reaction.evidence_count!=b.reaction.evidence_count)
         return a.reaction.evidence_count>b.reaction.evidence_count;
      if(MathAbs(a.distance_atr-b.distance_atr)>1.0e-6)
         return a.distance_atr<b.distance_atr;
      return a.rr>b.rr;
     }

   static bool       Alertable(const int state)
     {
      switch((ENUM_SIG_STATE)state)
        {
         case SIG_CONFIRMED:     return true;
         case SIG_COUNTER_TREND: return true;   // allowed, labelled, gated
         case SIG_TACTICAL_INFO: return true;   // informational, gated
         default:                return false;  // WATCH / PREVIEW / NO TRADE / LIMITED ROOM
        }
      return false;
     }

public:
                     CSignalArbiter()
     { m_gate_count=0; m_alloc_calls=0; m_free_calls=0;
       m_cand_count=0; m_cand_bar_time=0;
       m_auth_pending=false; m_tactical_may_confirm=false; m_gate_core=false;
       m_g_cd=NULL; m_g_ff=NULL; m_g_di=NULL;
       ArrayResize(m_gates,16); }

   //--- RAII: every gate allocated in Init() is released here.
                    ~CSignalArbiter()
     {
      for(int i=0;i<m_gate_count;i++)
        {
         if(CheckPointer(m_gates[i])==POINTER_DYNAMIC) { delete m_gates[i]; m_free_calls++; }
         m_gates[i]=NULL;
        }
      m_gate_count=0;
      m_g_cd=NULL; m_g_ff=NULL; m_g_di=NULL;
      ArrayResize(m_gates,0);
     }

   //--- Explicit release. Called from CQuantumRoot::Deinit() so the
   //--- alloc/free counters balance BEFORE the leak report is printed.
   //--- The destructor is idempotent: it only frees what is still there.
   void              Shutdown()
     {
      for(int i=0;i<m_gate_count;i++)
        {
         if(CheckPointer(m_gates[i])==POINTER_DYNAMIC) { delete m_gates[i]; m_free_calls++; }
         m_gates[i]=NULL;
        }
      m_gate_count=0;
      m_g_cd=NULL; m_g_ff=NULL; m_g_di=NULL;
     }

   //--- Re-attach the history after a rebuild (never needed in normal
   //--- operation; exposed so the self-test can rebuild the gate set).
   void              AttachHistory(IAlertHistory *history)
     {
      if(m_g_cd!=NULL) m_g_cd.Attach(history);
      if(m_g_ff!=NULL) m_g_ff.Attach(history);
      if(m_g_di!=NULL) m_g_di.Attach(history);
     }

   int               AllocCalls() const { return m_alloc_calls; }
   int               FreeCalls()  const { return m_free_calls;  }
   int               GateCount()  const { return m_gate_count;  }
   int               Pending()    const { return m_cand_count;  }

   //------------------------------------------------------------------
   // Init. `history` is CAlertManager (it implements IAlertHistory).
   //------------------------------------------------------------------
   void              Init(IAlertHistory *history,const bool tactical_may_confirm,
                          const bool gate_core)
     {
      for(int i=0;i<m_gate_count;i++)
        {
         if(CheckPointer(m_gates[i])==POINTER_DYNAMIC) { delete m_gates[i]; m_free_calls++; }
         m_gates[i]=NULL;
        }
      m_gate_count=0;
      ArrayResize(m_gates,16);

      CClosedBarGate   *g1=new CClosedBarGate();     m_alloc_calls++;
      CDataQualityGate *g2=new CDataQualityGate();   m_alloc_calls++;
      CLocationGate    *g3=new CLocationGate();      m_alloc_calls++;
      CBiasGate        *g4=new CBiasGate();          m_alloc_calls++;
      CRoomGate        *g5=new CRoomGate();          m_alloc_calls++;
      CVolatilityGate  *g6=new CVolatilityGate();    m_alloc_calls++;
      CCooldownGate    *g7=new CCooldownGate();      m_alloc_calls++;
      CFlipFlopGate    *g8=new CFlipFlopGate();      m_alloc_calls++;
      CDistanceGate    *g9=new CDistanceGate();      m_alloc_calls++;
      CSessionGate     *g10=new CSessionGate();      m_alloc_calls++;

      PushGate(g1); PushGate(g2); PushGate(g3); PushGate(g4); PushGate(g5);
      PushGate(g6); PushGate(g7); PushGate(g8); PushGate(g9); PushGate(g10);

      //--- The three anti-spam gates need the alert history. MQL5 has no
      //--- RTTI (no dynamic_cast), so the concrete pointers are kept and
      //--- attached here at construction time - no type probing at all.
      if(history!=NULL)
        {
         g7.Attach(history);
         g8.Attach(history);
         g9.Attach(history);
        }
      m_g_cd=g7; m_g_ff=g8; m_g_di=g9;

      m_tactical_may_confirm=tactical_may_confirm;
      m_gate_core=gate_core;
      m_cand_count=0;
      m_cand_bar_time=0;
     }

   void              SetAuthoritativePending(const bool v) { m_auth_pending=v; }

   //------------------------------------------------------------------
   // Submit. Candidates older than the current bar are dropped.
   //------------------------------------------------------------------
   void              Submit(const SSignalCandidate &c,const datetime bar_time)
     {
      if(!c.valid) return;
      if(bar_time<=0) return;
      if(m_cand_bar_time!=bar_time)
        {
         for(int i=0;i<QSMC_ARB_MAX_CANDIDATES;i++)
           {
            m_cands[i].valid=false;
           }
         m_cand_count=0;
         m_cand_bar_time=bar_time;
        }
      //--- dedupe inside the bar: same zone + direction + source
      for(int i=0;i<m_cand_count;i++)
        {
         if(m_cands[i].source!=c.source) continue;
         if(m_cands[i].zone_id!=c.zone_id) continue;
         if(m_cands[i].dir!=c.dir) continue;
         if(Better(c,m_cands[i])) m_cands[i]=c;
         return;
        }
      if(m_cand_count>=QSMC_ARB_MAX_CANDIDATES) return;
      m_cands[m_cand_count]=c;
      m_cand_count++;
     }

   //------------------------------------------------------------------
   // Run every gate on one candidate. Returns false when rejected.
   //------------------------------------------------------------------
   bool              EvaluateCandidate(const SSignalCandidate &in,const SGateCtx &ctx,
                                       const SQsmcArbConfig &cfg,const CZoneRegistry &zones,
                                       SSignalCandidate &out,SArbiterReport &rep)
     {
      out=in;
      out.reject_text="";
      out.reject_count=0;
      out.downgraded=false;
      int final_state=in.state;

      for(int g=0;g<m_gate_count;g++)
        {
         string reason="";
         int    ds=(int)SIG_WATCH;
         ENUM_GATE_RESULT r=m_gates[g].Evaluate(out,ctx,cfg,zones,reason,ds);
         if(r==GATE_PASS) continue;
         if(r==GATE_FAIL)
           {
            out.reject_count++;
            out.reject_text+=(out.reject_text==""?"":"; ")+m_gates[g].Name()+": "+reason;
            rep.rejected++;
            return false;
           }
         //--- DOWNGRADE
         if(StateRank((int)ds)<StateRank(final_state))
           {
            final_state=(int)ds;
            out.downgraded=true;
            out.reason=reason;
           }
         else if(out.reason=="") out.reason=reason;
         rep.downgraded++;
         if(rep.gate_line_count<QSMC_ARB_MAX_REASONS)
           {
            rep.gate_lines[rep.gate_line_count]=m_gates[g].Name()+" DOWNGRADE -> "+
                                                 QSMC_StateName((int)ds)+": "+reason;
            rep.gate_line_count++;
           }
        }

      //--- Source cap (terminology rule R7). The tactical path is
      //--- informational by construction.
      if(out.source==SRC_TACTICAL && !m_tactical_may_confirm)
        {
         if(StateRank(final_state)>StateRank((int)SIG_TACTICAL_INFO))
           {
            final_state=(int)SIG_TACTICAL_INFO;
            out.downgraded=true;
            if(out.reason=="")
               out.reason="MTF tactical path - informational only, it cannot publish CONFIRMED (R7)";
           }
        }
      out.state=final_state;
      return true;
     }

   //------------------------------------------------------------------
   // Finalize. Emits at most one signal for the bar.
   //------------------------------------------------------------------
   bool              Finalize(const SGateCtx &ctx,const SQsmcArbConfig &cfg,
                              const CZoneRegistry &zones,CAlertManager &alerts,
                              SArbiterReport &rep)
     {
      rep.submitted=m_cand_count;
      rep.evaluated=0; rep.rejected=0; rep.downgraded=0;
      rep.published=false; rep.gate_line_count=0; rep.trace="";
      rep.primary.valid=false;

      if(!cfg.enabled) { rep.trace="arbitration disabled"; m_cand_count=0; return false; }
      if(m_cand_count<=0) { rep.trace="no candidate"; return false; }
      if(!ctx.data_ready) { rep.trace="data not ready: "+ctx.data_reason; m_cand_count=0; return false; }

      //--- Pass 1: authoritative sources only (CORE / ZRE / RXN).
      //--- Pass 2: tactical, and only if the bar is not already claimed.
      SSignalCandidate best;
      best.valid=false;
      bool have_best=false;

      for(int pass=0;pass<2 && !have_best;pass++)
        {
         if(pass==1)
           {
            if(m_auth_pending)
              {
               rep.trace="tactical suppressed: the authoritative dispatcher owns this bar";
               break;
              }
           }
         for(int i=0;i<m_cand_count;i++)
           {
            SSignalCandidate c=m_cands[i];
            if(c.source==SRC_TACTICAL)
              {
               if(pass==0) continue;
              }
            else
              {
               if(pass==1) continue;
               if(!m_gate_core && c.source==SRC_CORE)
                 {
                  //--- CORE keeps its own validated gates and its own
                  //--- publisher; the arbiter only needs to know that the
                  //--- bar is claimed. Default = do not re-gate CORE.
                  continue;
                 }
              }
            rep.evaluated++;
            SSignalCandidate ev;
            if(!EvaluateCandidate(c,ctx,cfg,zones,ev,rep)) continue;
            if(!Alertable(ev.state)) continue;
            if(!have_best || Better(ev,best)) { best=ev; have_best=true; }
           }
        }

      m_cand_count=0;   // the bar is consumed either way

      if(!have_best)
        {
         if(rep.trace=="") rep.trace="no candidate survived the gates";
         return false;
        }

      //--- anti-spam pre-check (the gates already ran; this is the
      //--- final lock closest to the terminal call).
      string why="";
      if(!alerts.Allows(best,ctx,cfg,why))
        {
         rep.trace="suppressed by "+why+" | "+QSMC_StateName(best.state)+" "+
                   (best.dir>0?"BUY":"SELL")+" "+best.zone_id;
         return false;
        }

      bool ok=alerts.Publish(best,ctx,cfg);
      rep.published=ok;
      rep.primary=best;
      rep.trace=(ok?"PUBLISHED":"suppressed at publish")+" | "+
                QSMC_StateName(best.state)+" "+(best.dir>0?"BUY":"SELL")+
                " "+best.zone_id;
      return ok;
     }

   //--- Read-only view of the pending candidate list (dashboard/tooling).
   bool              PendingAt(const int i,SSignalCandidate &out) const
     {
      if(i<0 || i>=m_cand_count) return false;
      out=m_cands[i];
      return true;
     }
  };

#endif
//+------------------------------------------------------------------+
