//+------------------------------------------------------------------+
//|                                                  QSMC_Root.mqh   |
//|  CQuantumRoot - the single root object. This is the ONLY global    |
//|  mutable state the v6.6.0 subsystem adds to the host indicator.   |
//|                                                                   |
//|  v6.6.1 - MetaEditor compile fixes for this layer (MQL5 dialect): |
//|   - no getter may RETURN a reference: sub-objects are handed out  |
//|     as pointers (GetPointer), the structs as snapshots/accessors. |
//|   - LeakReport() built its text with ',' (a Print argument list   |
//|     inside a declaration) -> it now uses StringFormat().          |
//|   - CAlertManager::HashHex() used integer literals with a 'u'     |
//|     suffix, which MQL5 does not have -> plain hex literals.       |
//|   - Refresh() no longer rebuilds a LOCKED config from the preset. |
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
#include <QSMC/QSMC_Structure.mqh>
#include <QSMC/QSMC_Zones.mqh>
#include <QSMC/QSMC_ZoneScorer.mqh>
#include <QSMC/QSMC_Reaction.mqh>
#include <QSMC/QSMC_Bias.mqh>
#include <QSMC/QSMC_Preset.mqh>
#include <QSMC/QSMC_Gates.mqh>
#include <QSMC/QSMC_AlertManager.mqh>
#include <QSMC/QSMC_Arbiter.mqh>
#include <QSMC/QSMC_Stats.mqh>
#include <QSMC/QSMC_EarlyBreakDetector.mqh>
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
   CZoneScorer       m_zone_scorer;
   CReactionDetector m_reaction;
   CBiasProvider     m_bias;
   CStructureEngine m_structure;
   CEarlyBreakDetector m_early_break;
   SEarlyBreakResult  m_early_result;
   SStructureEvent  m_structure_last;
   string            m_structure_last_event;
   bool              m_structure_has_event;
   bool              m_structure_ok;
   int               m_structure_left, m_structure_right;
   double            m_structure_equal_tolerance;
   double            m_structure_break_buffer;
   double            m_structure_sweep_penetration;
   datetime          m_structure_seen_time;
   int               m_market_direction;
   int               m_market_direction_score;
   string            m_market_direction_text;
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
   //--- INSTRUMENT IDENTITY. Set once in Init() from the caller's arguments and
   //--- read everywhere else. This root used to consult _Symbol/_Period inside
   //--- Refresh()/BuildContext(), which is harmless while one indicator instance
   //--- serves one chart and quietly wrong the moment the same object is reused
   //--- (a service EA, a chart-switching panel): the context would describe chart
   //--- A while the decision was made about symbol B, and the digits/point used
   //--- for a price comparison would be the *chart's*, not the instrument's.
   string            m_symbol;
   ENUM_TIMEFRAMES   m_chart_tf;
   ENUM_TIMEFRAMES   m_exec_tf;
   int               m_ext_d1, m_ext_h4, m_ext_h1;
   bool              m_ext_h1_known;

   bool              ConfigureStructure()
     {
      m_structure_left=2; m_structure_right=2;
      double point=SymbolInfoDouble(m_symbol,SYMBOL_POINT);
      if(!(point>0.0)) point=_Point;
      double tick=SymbolInfoDouble(m_symbol,SYMBOL_TRADE_TICK_SIZE);
      if(!(tick>0.0)) tick=point;
      m_structure_equal_tolerance=2.0*tick;
      m_structure_break_buffer=2.0*tick;
      m_structure_sweep_penetration=2.0*tick;
      m_structure_ok=m_structure.Init(m_symbol,m_chart_tf,m_structure_left,m_structure_right,
                                      m_structure_equal_tolerance,m_structure_break_buffer,
                                      m_structure_sweep_penetration,0.75,0.60);
      if(!m_early_break.Configure(0.08,0.50,3.50,0.05,55.0))
        { m_structure_ok=false; return false; }
      m_early_result=m_early_break.Result();
      m_structure_seen_time=0;
      m_structure_has_event=false;
      m_structure_last_event="waiting for closed-bar structure";
      m_market_direction=0; m_market_direction_score=0;
      m_market_direction_text="DIRECTION WAIT | awaiting closed-bar data";
      return m_structure_ok;
     }

   string            StructureEventName(const ENUM_MS_EVENT type) const
     {
      switch(type)
        {
         case MS_BOS_UP: return "BOS UP";
         case MS_BOS_DOWN: return "BOS DOWN";
         case MS_CHOCH_UP: return "CHoCH UP";
         case MS_CHOCH_DOWN: return "CHoCH DOWN";
         case MS_STRUCTURE_INVALIDATED: return "STRUCTURE INVALIDATED";
         case MS_LIQUIDITY_SWEEP_HIGH: return "BUY-SIDE SWEEP";
         case MS_LIQUIDITY_SWEEP_LOW: return "SELL-SIDE SWEEP";
         case MS_LIQUIDITY_BREAKOUT_HIGH: return "BUY-SIDE BREAKOUT";
         case MS_LIQUIDITY_BREAKOUT_LOW: return "SELL-SIDE BREAKOUT";
         case MS_BULL_DISPLACEMENT: return "BULL DISPLACEMENT";
         case MS_BEAR_DISPLACEMENT: return "BEAR DISPLACEMENT";
         case MS_HIGHER_HIGH: return "HIGHER HIGH";
         case MS_LOWER_HIGH: return "LOWER HIGH";
         case MS_HIGHER_LOW: return "HIGHER LOW";
         case MS_LOWER_LOW: return "LOWER LOW";
         case MS_EQUAL_HIGH: return "EQUAL HIGH";
         case MS_EQUAL_LOW: return "EQUAL LOW";
         case MS_SWING_HIGH: return "SWING HIGH";
         case MS_SWING_LOW: return "SWING LOW";
         default: return "STRUCTURE EVENT";
        }
     }

   // Consume only closed chart bars. Initial warm-up replays the retained
   // closed history chronologically; subsequent calls process only bars after
   // the engine's last timestamp. No MqlRates array or per-tick heap copy.
   void              UpdateStructure(const CBarSeries &series,const int closed_index)
     {
      if(!series.Ready() || closed_index<0 || closed_index>series.ClosedIndex())
         return;
      datetime latest=series.T(closed_index);
      if(!m_structure_ok)
        {
         if(latest==m_structure_seen_time) return;
         if(!m_structure.Init(m_symbol,m_chart_tf,m_structure_left,m_structure_right,
                              m_structure_equal_tolerance,m_structure_break_buffer,
                              m_structure_sweep_penetration,0.75,0.60)) return;
         if(!m_early_break.Configure(0.08,0.50,3.50,0.05,55.0)) return;
         m_structure_ok=true; m_structure_seen_time=0;
        }
      if(latest==m_structure_seen_time) return;
      int start=m_structure_left+m_structure_right;
      datetime prior=m_structure.LastProcessedTime();
      if(prior>0)
        {
         int prior_index=series.IndexOfTime(prior);
         if(prior_index>=0) start=prior_index+1;
         else
           {
            if(!m_structure.Init(m_symbol,m_chart_tf,m_structure_left,m_structure_right,
                                 m_structure_equal_tolerance,m_structure_break_buffer,
                                 m_structure_sweep_penetration,0.75,0.60))
              { m_structure_ok=false; return; }
            if(!m_early_break.Configure(0.08,0.50,3.50,0.05,55.0))
              { m_structure_ok=false; return; }
            m_structure_has_event=false;
            m_structure_last_event="structure history refreshed; rebuilding";
            start=m_structure_left+m_structure_right;
           }
        }
      SStructureEvent events[];
      for(int i=start;i<=closed_index;i++)
        {
         datetime available=series.T(i+1); // next bar is present as the forming bar
         // Use the ATR available at this historical bar, not the present ATR;
         // this keeps the initial chronological rebuild causal.
         double atr=series.ATRAt(i);
         if(!m_structure.ProcessClosed(series,i,available,atr,events))
           { m_structure_ok=false; m_structure_seen_time=latest; return; }
         bool early_ok=m_early_break.ProcessClosed(series,i,available,atr,m_ctx.spread_points,m_ctx.point,
                                                    m_structure.HasSwingHigh(),m_structure.LastSwingHigh(),
                                                    m_structure.HasSwingLow(),m_structure.LastSwingLow());
         m_early_result=m_early_break.Result();
         if(!early_ok) m_early_result.valid=false;
         for(int e=0;e<ArraySize(events);e++)
           {
            m_structure_last=events[e];
            m_structure_has_event=true;
            m_structure_last_event=StructureEventName(events[e].type)+" @ "+
                                   DoubleToString(events[e].level,m_ctx.digits)+
                                   " available "+TimeToString(events[e].available_time,TIME_DATE|TIME_MINUTES);
           }
        }
      m_structure_seen_time=latest;
      m_structure_ok=true;
     }

   void              UpdateMarketDirection()
     {
      if(!m_ctx.data_ready)
        {
         m_market_direction=0; m_market_direction_score=0;
         string unavailable="MARKET DIRECTION UNAVAILABLE | "+m_ctx.data_reason;
         if(unavailable!=m_market_direction_text)
           { m_market_direction_text=unavailable; m_render.DrawDirection(0,0,unavailable); }
         return;
        }
      int htf=m_ctx.htf_bias;
      int local=(m_structure_ok ? m_structure.Trend() : 0);
      double raw=0.0;
      if(htf!=0)
        {
         double htf_component=0.65*(double)m_ctx.bias_score;
         if(MathAbs(htf_component)<10.0) htf_component=10.0*(double)htf;
         raw+=htf_component;
        }
      if(local!=0) raw+=35.0*(double)local;
      int score=(int)MathRound(raw);
      if(score>100) score=100; if(score<-100) score=-100;
      bool conflict=(htf!=0 && local!=0 && htf!=local);
      int direction=0;
      if(!conflict)
        {
         if(htf!=0 && local!=0) direction=htf;
         else if(htf!=0) direction=htf;
         else if(local!=0) direction=local;
        }
      string label=(conflict?"MIXED / CONFLICT":(direction>0?"BULLISH":(direction<0?"BEARISH":"NEUTRAL / WAIT")));
      string htf_text=(htf>0?"BULLISH":(htf<0?"BEARISH":"NEUTRAL"));
      string local_text=(local>0?"UP":(local<0?"DOWN":"UNCONFIRMED"));
      string score_text=IntegerToString(score);
      if(score>0) score_text="+"+score_text;
      string text="MARKET "+label+" | heuristic "+score_text+"/100 (not probability)"+
                  " | HTF "+htf_text+" | chart structure "+local_text;
      if(!m_structure_ok) text+=" | structure data unavailable";
      if(m_early_result.valid) text+=" | "+m_early_result.label;
      else text+=" | EARLY BREAK DATA UNAVAILABLE";
      if((m_early_result.missing_mask & QEB_MISS_QUOTES)!=0) text+=" | quote-flow unavailable";
      if(m_structure_last_event!="") text+=" | last "+m_structure_last_event;
      m_market_direction=direction;
      m_market_direction_score=score;
      if(text!=m_market_direction_text)
        {
         m_market_direction_text=text;
         m_render.DrawDirection(direction,score,text);
        }
     }

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
       m_cfg_locked=false; m_bias_external=false; m_ext_h1_known=true;
       m_ext_d1=0; m_ext_h4=0; m_ext_h1=0;
       m_structure_has_event=false; m_structure_ok=false; m_structure_seen_time=0;
       m_structure_left=2; m_structure_right=2;
       m_structure_equal_tolerance=0.0; m_structure_break_buffer=0.0;
       m_structure_sweep_penetration=0.0; m_structure_last_event="";
       m_market_direction=0; m_market_direction_score=0;
       m_market_direction_text="DIRECTION WAIT";
       //--- bound to nothing until Init() says otherwise; Ready() is false, so
       //--- no pipeline can read these before a real instrument is set
       m_symbol=""; m_chart_tf=PERIOD_CURRENT; m_exec_tf=PERIOD_CURRENT; }

                    ~CQuantumRoot() { Deinit(); }

   bool              Ready() const { return m_ready; }
   int               Bars()  const { return m_bars;  }

   //------------------------------------------------------------------
   // ACCESSORS - MQL5 DIALECT NOTE (v6.6.1)
   //  MQL5 does not allow a function to RETURN a reference: `CMarketData
   //  &Market()` is a hard compile error ("reference cannot used"), even
   //  though a reference PARAMETER (`void F(CMarketData &md)`) is legal.
   //  So the sub-objects are handed out as POINTERS - member access with
   //  '.' is identical, so `root.Market().Bars()` keeps working - and the
   //  plain-data structs are handed out as read-only snapshots through
   //  narrow accessors instead of as a copyable struct reference.
   //------------------------------------------------------------------
   CZoneRegistry    *Zones()    { return GetPointer(m_zones);   }
   CMarketData      *Market()   { return GetPointer(m_md);      }
   CSignalArbiter   *Arbiter()  { return GetPointer(m_arbiter); }
   CStatsLogger     *Stats()    { return GetPointer(m_stats);   }
   CAlertManager    *Alerts()   { return GetPointer(m_alerts);  }
   CChartRenderer   *Renderer() { return GetPointer(m_render);  }

   //--- per-bar decision context (SGateCtx holds strings -> never copied)
   string            CtxSymbol()      const { return m_ctx.symbol;       }
   ENUM_TIMEFRAMES   CtxTF()          const { return m_ctx.tf;           }
   double            CtxAtr()         const { return m_ctx.atr;         }
   double            CtxPrice()       const { return m_ctx.price;        }
   double            CtxPoint()       const { return m_ctx.point;        }
   double            CtxTickSize()    const { return m_ctx.tick_size;    }
   double            CtxSpreadPoints()const { return m_ctx.spread_points;}
   int               CtxDigits()      const { return m_ctx.digits;       }
   int               CtxClosedIndex() const { return m_ctx.closed_index; }
   int               CtxBarIndex()    const { return m_ctx.bar_index;    }
   datetime          CtxClosedTime()  const { return m_ctx.closed_time;  }
   datetime          CtxBarTime()     const { return m_ctx.bar_time;     }
   bool              CtxBarClosed()   const { return m_ctx.bar_closed;   }
   int               CtxBiasScore()   const { return m_ctx.bias_score;   }
   int               CtxHtfBias()     const { return m_ctx.htf_bias;     }
   int               MarketDirection() const { return m_market_direction; }
   int               MarketDirectionScore() const { return m_market_direction_score; }
   string            MarketDirectionText() const { return m_market_direction_text; }
   void              GetEarlyBreakResult(SEarlyBreakResult &out) const { out=m_early_result; }
   int               StructureTrend() const { return (m_structure_ok?m_structure.Trend():0); }
   string            StructureLastEvent() const { return m_structure_last_event; }
   datetime          StructureLastEventTime() const { return (m_structure_has_event?m_structure_last.event_time:0); }
   datetime          StructureEventAvailableTime() const { return (m_structure_has_event?m_structure_last.available_time:0); }
   int               CtxD1Bias()      const { return m_ctx.d1_bias;      }
   int               CtxH4Bias()      const { return m_ctx.h4_bias;      }
   int               CtxH1Bias()      const { return m_ctx.h1_bias;      }
   int               CtxSessionOK()   const { return m_ctx.session_ok;   }
   ENUM_VOL_REGIME   CtxRegime()      const { return m_ctx.regime;       }
   bool              CtxDataReady()   const { return m_ctx.data_ready;   }
   string            CtxDataReason()  const { return m_ctx.data_reason;  }

   //--- the arbiter verdict for the last finalized bar (read-only)
   int               ReportSubmitted()  const { return m_rep.submitted;  }
   int               ReportEvaluated()  const { return m_rep.evaluated;  }
   int               ReportRejected()   const { return m_rep.rejected;   }
   int               ReportDowngraded() const { return m_rep.downgraded; }
   bool              ReportPublished()  const { return m_rep.published;  }
   string            ReportTrace()      const { return m_rep.trace;      }
   int               ReportGateLines()  const { return m_rep.gate_line_count; }
   string            ReportGateLine(const int i) const
     { return (i>=0 && i<m_rep.gate_line_count ? m_rep.gate_lines[i] : ""); }

   //--- the ONE published candidate of the last bar (valid=false => none)
   bool              PrimaryValid()     const { return m_rep.primary.valid;   }
   int               PrimaryDir()       const { return m_rep.primary.dir;     }
   int               PrimaryScore()     const { return m_rep.primary.score;   }
   int               PrimaryState()     const { return m_rep.primary.state;   }
   string            PrimaryZoneId()    const { return m_rep.primary.zone_id; }
   ENUM_ZR_ROLE      PrimaryZoneRole()  const { return m_rep.primary.zone_role; }
   double            PrimaryEntry()     const { return m_rep.primary.entry;   }
   double            PrimaryStop()      const { return m_rep.primary.sl;      }
   double            PrimaryTP1()       const { return m_rep.primary.tp1;     }
   double            PrimaryRR()        const { return m_rep.primary.rr;      }
   string            PrimaryReason()    const { return m_rep.primary.reason;  }
   string            PrimaryEvidence()  const { return m_rep.primary.evidence_text; }
   double            PrimaryZoneLo()    const { return m_rep.primary.zone_lo; }
   double            PrimaryZoneHi()    const { return m_rep.primary.zone_hi; }
   double            PrimaryDistanceATR() const { return m_rep.primary.distance_atr; }
   bool              PrimaryDowngraded()  const { return m_rep.primary.downgraded; }
   //--- Full snapshots for a host that wants everything at once. A struct IS
   //--- a value type in MQL5, so copying it out is legal (the arbiter does the
   //--- same thing internally); only RETURNING a reference is not.
   string            Instrument() const { return m_symbol; }
   ENUM_TIMEFRAMES   ChartTf()    const { return m_chart_tf; }
   ENUM_TIMEFRAMES   ExecTf()     const { return m_exec_tf;  }
   void              GetContext(SGateCtx &out) const { out=m_ctx; }
   void              GetPrimaryCandidate(SSignalCandidate &out) const { out=m_rep.primary; }

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
      m_symbol=(symbol==""?_Symbol:symbol);
      m_chart_tf=(chart_tf==PERIOD_CURRENT || (int)chart_tf==0
                  ?(ENUM_TIMEFRAMES)_Period:chart_tf);
      m_exec_tf=(exec_tf==PERIOD_CURRENT || (int)exec_tf==0
                 ?m_chart_tf:exec_tf);
      m_preset.Build(m_cfg,m_chart_tf);
      if(!m_md.Init(m_symbol,m_chart_tf,m_exec_tf,bars,atr_period)) return false;
      if(!ConfigureStructure()) return false;
      m_alerts.Init(m_cfg.dedupe_ring);
      m_arbiter.Init(GetPointer(m_alerts),tactical_may_confirm,gate_core);
      m_render.Init(0,0,draw);
      m_stats.Open(m_symbol,m_chart_tf,min_sample,csv_log);
      m_ready=true;
      m_bars=0;
      Print("[QSMC_ARB] v6.6.4 arbitration layer ON | preset ",m_preset.EffectiveName(),
            " | gates ",IntegerToString(m_arbiter.GateCount()),
            " | exec TF ",QSMC_TFName(m_exec_tf),
            " | tactical may confirm: ",(tactical_may_confirm?"YES":"NO (informational only)"),
            //--- the identity every threshold in this build is measured against.
            //--- It is in the first line on purpose: a wrong symbol, a wrong chart
            //--- timeframe or a stale copy of the layer is visible HERE, before it
            //--- becomes a signal that is quietly wrong by a factor of ten points.
            " | on ",m_symbol," ",QSMC_TFName(m_chart_tf));
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
   //--- MQL5 DIALECT NOTE: the ',' operator does not exist. A comma chain
   //--- is only legal inside a call's argument list or inside a declaration
   //--- list (`int a=1,b=2;`), which is why the old Print()-style body of
   //--- this function was parsed as a second variable NAMED IntegerToString.
   //--- Building text here therefore means '+' concatenation or StringFormat.
   string            LeakReport() const
     {
      int a=m_md.AllocCalls()+m_arbiter.AllocCalls();
      int f=m_md.FreeCalls()+m_arbiter.FreeCalls();
      string s=StringFormat("alloc/free: market %d/%d | gates %d/%d | chart objects created/deleted %d/%d",
                            m_md.AllocCalls(),m_md.FreeCalls(),
                            m_arbiter.AllocCalls(),m_arbiter.FreeCalls(),
                            m_render.Created(),m_render.Deleted());
      if(a==f) s+=" => no leak";
      else     s+=StringFormat(" => LEAK (alloc %d vs free %d)",a,f);
      return s;
     }

   //=================================================================
   // Per-bar pipeline
   //=================================================================

    //--- 1a. Refresh the series from the terminal, then build the context.
    bool              Refresh(const double external_atr,const double spread_points)
      {
       if(!m_ready) return false;
       //--- A LOCKED config is the host's, not the preset's. Rebuilding it
       //--- here used to silently discard whatever LockConfig() installed on
       //--- the very first bar, because BuildContext() honours the lock and
       //--- this line did not.
       if(!m_cfg_locked) m_preset.Build(m_cfg,m_chart_tf);
      if(!m_cfg.enabled)
        {
         ResetContext("arbitration disabled (InpArbEnabled=false)");
         return false;
        }
      if(!m_md.RefreshAll(external_atr))
        { ResetContext(m_md.Reason()); return false; }
      if(!BuildContext(spread_points))
        {
         string why=m_ctx.data_reason;
         if(why=="") why="context data incomplete";
         ResetContext(why);
         return false;
        }
      return true;
     }

   //--- 1b. Build the decision context from whatever the series hold.
   //--- Public so the offline self-test can drive the production path
   //--- after loading synthetic bars (see QSMC_Selftest.mqh).
   bool              BuildContext(const double spread_points)
     {
      if(!m_ready) return false;
      if(!m_cfg_locked) m_preset.Build(m_cfg,m_chart_tf);

      //--- reset the context; every field is set explicitly below
      m_ctx.symbol=m_symbol;
      m_ctx.tf=m_chart_tf;
      m_ctx.closed_index=-1;
      m_ctx.closed_time=0;
      m_ctx.bar_index=-1;
      m_ctx.bar_time=0;
      m_ctx.bar_closed=false;
      m_ctx.price=0.0;
      m_ctx.atr=0.0;
      {
       double pt=SymbolInfoDouble(m_symbol,SYMBOL_POINT);
       if(!(pt>0.0)) pt=_Point;                       // terminal fallback
       m_ctx.point=pt;
       m_ctx.tick_size=SymbolInfoDouble(m_symbol,SYMBOL_TRADE_TICK_SIZE);
       if(!(m_ctx.tick_size>0.0)) m_ctx.tick_size=pt;
       m_ctx.digits=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);
      }
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
      m_ctx.data_ready=true;
      m_ctx.data_reason="";

      m_bias.Update(m_md,m_cfg,ci);
      m_ctx.htf_bias=m_bias.Consensus();
      m_ctx.d1_bias=m_bias.D1();
      m_ctx.h4_bias=m_bias.H4();
      m_ctx.h1_bias=m_bias.H1();
      m_ctx.bias_score=m_bias.Score();

      ApplyExternalBias();
      UpdateStructure(*ch,ci);
      UpdateMarketDirection();
      m_bars++;
      return true;
     }

   void              ResetContext(const string reason)
     {
      m_ctx.symbol=m_symbol;
      m_ctx.tf=m_chart_tf;
      m_ctx.closed_index=-1; m_ctx.closed_time=0;
      m_ctx.bar_index=-1;    m_ctx.bar_time=0;   m_ctx.bar_closed=false;
      m_ctx.price=0.0; m_ctx.atr=0.0;
      {
       double pt=SymbolInfoDouble(m_symbol,SYMBOL_POINT);
       if(!(pt>0.0)) pt=_Point;                       // terminal fallback
       m_ctx.point=pt;
       m_ctx.tick_size=SymbolInfoDouble(m_symbol,SYMBOL_TRADE_TICK_SIZE);
       if(!(m_ctx.tick_size>0.0)) m_ctx.tick_size=pt;
       m_ctx.digits=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);
      }
      m_ctx.spread_points=0.0;
      m_ctx.data_ready=false;
      m_ctx.data_reason=reason;
      m_ctx.htf_bias=0; m_ctx.d1_bias=0; m_ctx.h4_bias=0; m_ctx.h1_bias=0;
      m_ctx.bias_score=0;
      m_ctx.regime=VREG_UNKNOWN;
      m_ctx.session_ok=-1;
      m_market_direction=0; m_market_direction_score=0;
      m_market_direction_text="MARKET DIRECTION UNAVAILABLE | "+reason;
      m_render.DrawDirection(0,0,m_market_direction_text);
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
   //--- Read/write the configuration WITHOUT returning a reference (illegal
   //--- in MQL5). Read into a caller-owned struct, change it, write it back:
   //---    SQsmcArbConfig c; root.CopyConfig(c); c.min_evidence=4; root.SetConfig(c);
   //--- SetConfig() is refused while the config is locked (LockConfig() or the
   //--- self-test); use UnlockConfig() first if a host really wants to edit a
   //--- locked config. An unlocked config is re-derived from the preset on
   //--- every closed bar, so edits made there are temporary by design.
   void              CopyConfig(SQsmcArbConfig &out) const { out=m_cfg; }
   bool              SetConfig(const SQsmcArbConfig &cfg)
     {
      if(m_cfg_locked) return false;
      m_cfg=cfg;
      return true;
     }

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
      UpdateMarketDirection();
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
         //--- compared against the chart this root was built for, not against
         //--- whatever chart happens to be current when the line runs
         const CBarSeries *ltf=(f.exec_tf==m_chart_tf ? NULL : ex);
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

      //--- Soft zone ranking is kept separate from hard structural validity.
      //--- Reaction evidence is scored independently below; zone strength is not
      //--- counted a second time inside that reaction component.
      if(!m_zone_scorer.Configure(2.5,2.5,0.15,m_cfg.min_zone_strength))
        { reason="DATA_NOT_READY: invalid zone-score configuration"; out.reason=reason; return (int)SIG_NO_TRADE; }
      SQZoneHit opposing;
      double room_for_score=-1.0;
      if(m_zones.NearestOpposing(px,dir,m_ctx.atr,opposing)) room_for_score=opposing.gap_atr;
      double spread_atr=(m_ctx.atr>0.0 ? m_ctx.spread_points*m_ctx.point/m_ctx.atr : -1.0);
      SZoneScore zone_score=m_zone_scorer.Score(z,dir,px,m_ctx.atr,hit.gap_atr,
                                                room_for_score,m_ctx.htf_bias,spread_atr);
      if(!zone_score.valid)
        {
         reason="NO_VALID_ZONE: "+zone_score.rejection;
         out.reason=reason; out.state=(int)SIG_NO_TRADE;
         out.zone_id=z.id; out.zone_role=z.role; out.distance_atr=hit.gap_atr;
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
      double reaction_independent=((double)rf.evidence_count/(double)QEV_COUNT*60.0+
                                   (rf.penetration_bounded?10.0:0.0));
      double reaction_normalized=reaction_independent/70.0*100.0;
      out.score=(int)MathRound(0.65*reaction_normalized+0.35*(double)zone_score.total);

      //--- 6) The requested state: CONFIRMED for a closed-bar fact.
      //--- The arbiter caps a tactical source at TACTICAL-INFO (R7).
      out.state=(int)SIG_CONFIRMED;
      out.extra="MTF trigger "+DoubleToString(f.trigger,m_ctx.digits)+
                " @ "+TimeToString(f.trigger_time,TIME_MINUTES)+
                (f.core_owned?" | owned by the CORE setup":" | from HTF bias / early break");
      if(f.chase_atr>0.0) out.extra+=" | chase "+DoubleToString(f.chase_atr,2)+" ATR";
      out.extra+=" | "+zone_score.breakdown;
      if(zone_score.penalties!="") out.extra+=" | penalties: "+zone_score.penalties;
      reason="";
      out.reason="closed-bar zone reaction validated";
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
             " | "+m_market_direction_text+
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
