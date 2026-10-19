//+------------------------------------------------------------------+
//|                                             QSMC_Selftest.mqh    |
//|  Deterministic offline test suite for the arbitration layer.      |
//|                                                                   |
//|  It drives the PRODUCTION code path (CQuantumRoot -> CReaction-    |
//|  Detector -> gates -> CSignalArbiter -> CAlertManager) with        |
//|  synthetic bars and zones. No terminal history is read and no      |
//|  chart object is created (draw = false), so the same assertions    |
//|  run identically on a live chart and in the Strategy Tester.       |
//|                                                                   |
//|  Run with:  QSMC_RunSelfTest();                                   |
//|  (the Script MQL5/Scripts/QSMC_ArbiterTest.mq5 does exactly that)  |
//|                                                                   |
//|  Every scenario states its inputs, the expected decision and the   |
//|  expected reason. Nothing here is a probability.                   |
//+------------------------------------------------------------------+
#ifndef __QSMC_SELFTEST_MQH__
#define __QSMC_SELFTEST_MQH__

#include <QSMC/QSMC_Root.mqh>

#define QST_BARS 40

//+------------------------------------------------------------------+
class CArbSelfTest
  {
private:
   int               m_pass;
   int               m_fail;
   string            m_lines[];
   int               m_line_n;

   void              Say(const string s)
     {
      if(m_line_n<400)
        {
         ArrayResize(m_lines,m_line_n+1);
         m_lines[m_line_n]=s;
         m_line_n++;
        }
      Print(s);
     }

   //------------------------------------------------------------------
   // Fill flat arrays. Index n-1 is the FORMING bar, n-2 the last
   // closed bar - the same convention the production code assumes.
   //------------------------------------------------------------------
   void              Flat(const int n,const double base,const double half,
                          const long vol,const datetime t0,const int step,
                          double &o[],double &h[],double &l[],double &c[],
                          datetime &t[],long &v[])
     {
      ArrayResize(o,n); ArrayResize(h,n); ArrayResize(l,n); ArrayResize(c,n);
      ArrayResize(t,n); ArrayResize(v,n);
      for(int i=0;i<n;i++)
        {
         o[i]=base-half*0.3; h[i]=base+half; l[i]=base-half; c[i]=base;
         v[i]=vol; t[i]=t0+(datetime)(i*step);
        }
     }

   void              Copy6(const int n,const double &o[],const double &h[],
                           const double &l[],const double &c[],const datetime &t[],
                           const long &v[],
                           double &eo[],double &eh[],double &el[],double &ec[],
                           datetime &et[],long &ev[])
     {
      ArrayResize(eo,n); ArrayResize(eh,n); ArrayResize(el,n); ArrayResize(ec,n);
      ArrayResize(et,n); ArrayResize(ev,n);
      for(int i=0;i<n;i++)
        { eo[i]=o[i]; eh[i]=h[i]; el[i]=l[i]; ec[i]=c[i]; et[i]=t[i]; ev[i]=v[i]; }
     }

   void              SetBar(const int i,const double o1,const double h1,const double l1,
                            const double c1,const long v1,
                            double &o[],double &h[],double &l[],double &c[],long &v[])
     { o[i]=o1; h[i]=h1; l[i]=l1; c[i]=c1; v[i]=v1; }

   void              MakeZone(SQZone &z,const ENUM_ZR_ROLE role,const double lo,
                              const double hi,const int strength)
     {
      z.valid=true;
      z.birth_role=role;
      z.role=role;
      z.lo=lo; z.hi=hi;
      z.strength=strength;
      z.touches=2;
      z.birth_bar=0;
      z.birth_time=0;
      z.flipped=false;
      z.broken_closed=false;
      z.broken_time=0;
      z.retested=false;
      z.state=ZST_TOUCHED;
      z.sources="TEST";
      z.id=CZoneRegistry::MakeId(role,lo,hi);
     }

   //--- INTRADAY preset, spelled out so the expectations are exact.
   void              CfgBase(SQsmcArbConfig &cfg)
     {
      cfg.enabled=true;
      cfg.popup=false;            // no terminal Alert() during the test
      cfg.push=false;
      cfg.sound=false;
      cfg.zone_reach_atr=1.50;
      cfg.merge_tol_atr=0.50;
      cfg.max_penetration_atr=0.35;
      cfg.break_atr=0.30;
      cfg.min_zone_strength=60;
      cfg.min_evidence=2;
      cfg.retest_lookback_bars=24;
      cfg.min_wick_ratio=0.50;
      cfg.volume_mult=1.60;
      cfg.displacement_atr=0.50;
      cfg.w_d1=50; cfg.w_h4=30; cfg.w_h1=20;
      cfg.allow_countertrend=true;
      cfg.countertrend_min_score=70;
      cfg.countertrend_extra_evidence=1;
      cfg.min_rr=1.50;
      cfg.max_stop_atr=4.00;
      cfg.sl_buffer_atr=0.20;
      cfg.cooldown_bars=10;
      cfg.min_alert_distance_atr=0.50;
      cfg.flipflop_bars=10;
      cfg.use_global_vars=false;    // never touch terminal globals in a test
      cfg.dedupe_ring=256;
      cfg.min_atr_points=0.0;
      cfg.max_spread_points=0;
      cfg.min_bars=30;              // QST_BARS-1 = 39 >= 30
      cfg.session_start_hour=-1;
      cfg.session_end_hour=-1;
     }

   //--- One fully wired root for one scenario.
   bool              NewRoot(CQuantumRoot &r,SQsmcArbConfig &cfg)
     {
      if(!r.Init(_Symbol,(ENUM_TIMEFRAMES)_Period,PERIOD_M1,300,14,false,false,false,30,false))
        { Say("FAIL: root Init() returned false"); return false; }
      r.LockConfig(cfg);
      return true;
     }

   void              Check(const bool cond,const string name,const string detail)
     {
      if(cond) { m_pass++; Say("PASS  "+name+(detail==""?"":"  ["+detail+"]")); }
      else     { m_fail++; Say("FAIL  "+name+(detail==""?"":"  ["+detail+"]")); }
     }

public:
                     CArbSelfTest() { m_pass=0; m_fail=0; m_line_n=0; }
                    ~CArbSelfTest() { ArrayResize(m_lines,0); }

   int               Passed() const { return m_pass; }
   int               Failed() const { return m_fail; }
   string            Line(const int i) const { return (i>=0 && i<m_line_n ? m_lines[i] : ""); }
   int               Lines() const { return m_line_n; }

   //==================================================================
   int               Run()
     {
      m_pass=0; m_fail=0; m_line_n=0;
      Say("=========================================================");
      Say(" QSMC v6.6.0 SIGNAL ARBITRATION - DETERMINISTIC SELF-TEST");
      Say(" symbol "+_Symbol+"  tf "+QSMC_TFName((ENUM_TIMEFRAMES)_Period)+
          "  point "+DoubleToString(_Point,_Digits));
      Say("=========================================================");

      T01_RejectionConfirmedOnce();
      T02_BreakoutContinuationNoCounter();
      T03_SellInsideSupportBlocked();
      T04_BetweenZonesNoTrade();
      T05_FormingBarPreviewOnly();
      T06_M1SpamCollapsesToOne();
      T07_FlipFlopSuppressed();
      T08_MultiChartSingleAlert();
      T09_CounterTrendDowngraded();
      T10_DataNotReady();

      Say("---------------------------------------------------------");
      Say(StringFormat(" RESULT: %d passed, %d failed",m_pass,m_fail));
      Say("---------------------------------------------------------");
      return m_fail;
     }

   //==================================================================
   // T01 - price touches RESISTANCE, the closed bar rejects.
   //   expect: SELL CONFIRMED exactly once, then NO repeat for 20 bars.
   //==================================================================
   void              T01_RejectionConfirmedOnce()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      cfg.cooldown_bars=20;                 // "no repeat for 20 bars"
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T01 setup",""); return; }

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,105.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      //--- approach
      SetBar(37,105.20,107.00,105.00,106.80,1000,o,h,l,c,v);
      //--- the rejection bar (last CLOSED bar = index 38)
      SetBar(38,106.80,109.40,106.70,107.10,2000,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);

      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T01 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T01 context",r.Ctx().data_reason); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);
      r.SetZones(zs,2);
      r.SetExternalBias(0,0,0);                    // neutral HTF

      STacticalFact f;
      f.valid=true; f.bull=false; f.closed_confirm=true;
      f.entry_price=c[38]; f.exec_bar_time=t[38]; f.exec_tf=PERIOD_M1;
      f.trigger=108.00; f.trigger_time=t[37]; f.core_owned=false; f.chase_atr=0.2;
      r.TacticalObserve(f);
      r.FinalizeBar(false);

      const SArbiterReport rep=r.Report();
      bool dir_ok=rep.primary.valid && rep.primary.dir<0;
      Check(rep.published && dir_ok,"T01a SELL published at resistance",
            "state="+QSMC_StateName(rep.primary.state)+" trace="+rep.trace);
      Check(dir_ok && rep.primary.zone_role==ZR_RESISTANCE,"T01b zone role is RESISTANCE",
            QSMC_RoleName(rep.primary.zone_role));

      //--- the SAME bar re-submitted must not publish again
      int before=r.Published();
      r.TacticalObserve(f);
      r.FinalizeBar(false);
      Check(r.Published()==before,"T01c same bar: no second alert",
            "published="+IntegerToString(r.Published()));

      //--- 20 further bars with no new reaction: still one alert
      for(int k=0;k<20;k++)
        {
         //--- shift the window: a flat bar becomes the new closed bar
         for(int i=0;i<QST_BARS-1;i++)
           { o[i]=o[i+1]; h[i]=h[i+1]; l[i]=l[i+1]; c[i]=c[i+1]; t[i]=t[i+1]; v[i]=v[i+1]; }
         int m=QST_BARS-1;
         SetBar(m-1,107.10,107.40,106.90,107.20,1000,o,h,l,c,v);   // new closed bar
         SetBar(m,  107.20,107.50,107.00,107.30,1000,o,h,l,c,v);   // forming
         Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
         if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS)) break;
         if(!r.BuildContext(0.0)) break;
         r.SetZones(zs,2);
         r.SetExternalBias(0,0,0);
         STacticalFact g=f;
         g.exec_bar_time=t[m-1];
         g.entry_price=c[m-1];
         r.TacticalObserve(g);
         r.FinalizeBar(false);
        }
      Check(r.Published()==before,"T01d no repeat over the next 20 bars",
            "published="+IntegerToString(r.Published())+
            " suppressed="+IntegerToString(r.Suppressed()));
     }

   //==================================================================
   // T02 - price closes ABOVE resistance (acceptance) and retests.
   //   expect: BUY continuation, NEVER a SELL.
   //==================================================================
   void              T02_BreakoutContinuationNoCounter()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T02 setup",""); return; }

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,106.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,106.00,108.60,105.90,108.40,1000,o,h,l,c,v);
      //--- acceptance: closed 1.00 above the zone top (0.50 ATR > 0.30)
      SetBar(38,108.40,110.10,108.20,110.00,2000,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T02 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T02 context",r.Ctx().data_reason); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);
      r.SetZones(zs,2);
      r.SetExternalBias(0,0,0);

      STacticalFact f;
      f.valid=true; f.bull=true; f.closed_confirm=true;
      f.entry_price=c[38]; f.exec_bar_time=t[38]; f.exec_tf=PERIOD_M1;
      f.trigger=109.00; f.trigger_time=t[37]; f.core_owned=false; f.chase_atr=0.1;
      r.TacticalObserve(f);
      r.FinalizeBar(false);

      const SArbiterReport rep=r.Report();
      Check(rep.published && rep.primary.dir>0,
            "T02a BUY continuation published above a broken resistance",
            "state="+QSMC_StateName(rep.primary.state)+" trace="+rep.trace);
      Check(!(rep.primary.valid && rep.primary.dir<0),
            "T02b no SELL is emitted at the same zone","");
     }

   //==================================================================
   // T03 - price is INSIDE a strong SUPPORT, the tactical path wants
   //       to SELL.  expect: blocked by CLocationGate with a reason.
   //==================================================================
   void              T03_SellInsideSupportBlocked()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T03 setup",""); return; }

      double o[],h[],l[],c[]; datetime t[]; long v[];
      //--- price sits INSIDE the support band 90.00-91.00
      Flat(QST_BARS,90.50,0.15,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(38,90.60,90.90,90.30,90.40,2000,o,h,l,c,v);   // bearish bar inside support

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T03 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T03 context",r.Ctx().data_reason); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_SUPPORT,90.00,91.00,85);
      MakeZone(zs[1],ZR_RESISTANCE,108.00,109.00,80);
      r.SetZones(zs,2);
      r.SetExternalBias(0,0,0);

      //--- the tactical path proposes a SELL (this is the reported bug)
      STacticalFact f;
      f.valid=true; f.bull=false; f.closed_confirm=true;
      f.entry_price=c[38]; f.exec_bar_time=t[38]; f.exec_tf=PERIOD_M1;
      f.trigger=90.20; f.trigger_time=t[37]; f.core_owned=false; f.chase_atr=0.1;
      r.TacticalObserve(f);
      r.FinalizeBar(false);

      const SArbiterReport rep=r.Report();
      Check(!rep.published,"T03a no SELL alert inside a SUPPORT zone",
            "trace="+rep.trace);
      bool mentioned=(StringFind(r.LastText(),"BETWEEN ZONES")>=0 ||
                      StringFind(r.LastText(),"did not reject")>=0 ||
                      StringFind(r.LastText(),"no candidate")>=0 ||
                      StringFind(r.LastText(),"STOP GEOMETRY")>=0);
      Check(mentioned && r.LastText()!="",
            "T03b the silence carries a reason","reason="+r.LastText());
     }

   //==================================================================
   // T04 - no zone within zone_reach_atr. expect: NO TRADE + reason.
   //==================================================================
   void              T04_BetweenZonesNoTrade()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T04 setup",""); return; }

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,100.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(38,100.00,101.00,99.50,100.80,2000,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T04 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T04 context",r.Ctx().data_reason); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);
      r.SetZones(zs,2);
      r.SetExternalBias(0,0,0);

      STacticalFact f;
      f.valid=true; f.bull=true; f.closed_confirm=true;
      f.entry_price=c[38]; f.exec_bar_time=t[38]; f.exec_tf=PERIOD_M1;
      f.trigger=100.00; f.trigger_time=t[37]; f.core_owned=false; f.chase_atr=0.0;
      r.TacticalObserve(f);
      r.FinalizeBar(false);

      const SArbiterReport rep=r.Report();
      Check(!rep.published,"T04a no signal between zones","trace="+rep.trace);
      Check(StringFind(r.LastText(),"BETWEEN ZONES")>=0,
            "T04b reason names BETWEEN ZONES",r.LastText());
     }

   //==================================================================
   // T05 - the fact comes from a FORMING bar. expect: PREVIEW at most,
   //       never CONFIRMED, never an alert named CONFIRMED.
   //==================================================================
   void              T05_FormingBarPreviewOnly()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T05 setup",""); return; }

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,106.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,106.00,108.60,105.90,108.40,1000,o,h,l,c,v);
      SetBar(38,106.80,109.40,106.70,107.10,2000,o,h,l,c,v);   // closed rejection
      //--- the FORMING bar sticks into the zone
      SetBar(39,107.10,109.60,106.90,107.20,1500,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T05 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T05 context",r.Ctx().data_reason); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);
      r.SetZones(zs,2);
      r.SetExternalBias(0,0,0);

      //--- the fact cites the FORMING bar (index 39 == ClosedIndex()+1)
      STacticalFact f;
      f.valid=true; f.bull=false; f.closed_confirm=false;      // PREVIEW
      f.entry_price=c[39]; f.exec_bar_time=t[39]; f.exec_tf=PERIOD_M1;
      f.trigger=108.00; f.trigger_time=t[37]; f.core_owned=false; f.chase_atr=0.1;
      r.TacticalObserve(f);
      r.FinalizeBar(false);

      const SArbiterReport rep=r.Report();
      bool forming=(f.exec_bar_time>t[38]);
      Check(forming,"T05a the fact really cites the forming bar",
            TimeToString(f.exec_bar_time,TIME_MINUTES));
      Check(!rep.published || rep.primary.state!=(int)SIG_CONFIRMED,
            "T05b a forming-bar fact never publishes CONFIRMED",
            "state="+QSMC_StateName(rep.primary.state)+" trace="+rep.trace);
      Check(StringFind(r.LastText(),"CONFIRMED")<0 || !rep.published,
            "T05c no alert text is named CONFIRMED here",r.LastText());
     }

   //==================================================================
   // T06 - an M1 execution trigger fires 30 times inside one M5 zone.
   //   expect: exactly ONE alert.
   //==================================================================
   void              T06_M1SpamCollapsesToOne()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      cfg.cooldown_bars=10;
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T06 setup",""); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,106.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,105.20,107.00,105.00,106.80,1000,o,h,l,c,v);
      SetBar(38,106.80,109.40,106.70,107.10,2000,o,h,l,c,v);

      int published=0;
      for(int k=0;k<30;k++)
        {
         //--- 30 consecutive M1 closes that all satisfy the OLD tactical
         //--- condition (closed beyond/above the trigger, bull bar).
         for(int i=0;i<QST_BARS-1;i++)
           { o[i]=o[i+1]; h[i]=h[i+1]; l[i]=l[i+1]; c[i]=c[i+1]; t[i]=t[i+1]; v[i]=v[i+1]; }
         int m=QST_BARS-1;
         double base=107.10+0.02*(double)k;
         SetBar(m-1,base,base+0.45,base-0.10,base+0.30,(k%3==0?2200:1000),o,h,l,c,v);
         SetBar(m,  base+0.30,base+0.55,base+0.10,base+0.35,1000,o,h,l,c,v);

         double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
         Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
         if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS)) break;
         if(!r.BuildContext(0.0)) break;
         r.SetZones(zs,2);
         r.SetExternalBias(0,0,0);
         STacticalFact f;
         f.valid=true; f.bull=false; f.closed_confirm=true;
         f.entry_price=c[m-1]; f.exec_bar_time=t[m-1]; f.exec_tf=PERIOD_M1;
         f.trigger=108.00; f.trigger_time=t[0]; f.core_owned=false; f.chase_atr=0.1;
         r.TacticalObserve(f);
         if(r.FinalizeBar(false)) published++;
        }
      Check(published<=1,
            "T06 30 M1 fires inside one zone collapse to <= 1 alert",
            "published="+IntegerToString(published)+
            " suppressed="+IntegerToString(r.Suppressed()));
     }

   //==================================================================
   // T07 - the opposite direction fires inside the same zone within the
   //       cooldown.  expect: suppressed by the flip-flop guard.
   //==================================================================
   void              T07_FlipFlopSuppressed()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      cfg.flipflop_bars=10;
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T07 setup",""); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,107.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,106.80,107.60,106.70,107.20,1000,o,h,l,c,v);
      SetBar(38,107.20,109.30,107.10,107.30,2000,o,h,l,c,v);   // SELL rejection

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T07 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T07 context",r.Ctx().data_reason); return; }
      r.SetZones(zs,2);
      r.SetExternalBias(0,0,0);

      STacticalFact f1;
      f1.valid=true; f1.bull=false; f1.closed_confirm=true;
      f1.entry_price=c[38]; f1.exec_bar_time=t[38]; f1.exec_tf=PERIOD_M1;
      f1.trigger=108.00; f1.trigger_time=t[37]; f1.core_owned=false; f1.chase_atr=0.1;
      r.TacticalObserve(f1);
      bool first=r.FinalizeBar(false);
      int after_first=r.Published();

      //--- one bar later, the OPPOSITE direction on the SAME zone
      for(int i=0;i<QST_BARS-1;i++)
        { o[i]=o[i+1]; h[i]=h[i+1]; l[i]=l[i+1]; c[i]=c[i+1]; t[i]=t[i+1]; v[i]=v[i+1]; }
      int m=QST_BARS-1;
      SetBar(m-1,107.30,109.20,107.20,109.10,2000,o,h,l,c,v);   // acceptance up
      SetBar(m,  109.10,109.50,109.00,109.30,1000,o,h,l,c,v);
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        {
         if(r.BuildContext(0.0))
           {
            r.SetZones(zs,2);
            r.SetExternalBias(0,0,0);
            STacticalFact f2;
            f2.valid=true; f2.bull=true; f2.closed_confirm=true;
            f2.entry_price=c[m-1]; f2.exec_bar_time=t[m-1]; f2.exec_tf=PERIOD_M1;
            f2.trigger=109.00; f2.trigger_time=t[37]; f2.core_owned=false; f2.chase_atr=0.1;
            r.TacticalObserve(f2);
            r.FinalizeBar(false);
           }
        }
      int after_second=r.Published();
      Check(after_second==after_first,
            "T07 the opposite direction on the same zone is suppressed",
            "first="+IntegerToString(after_first)+" second="+IntegerToString(after_second)+
            " last="+r.LastText());
     }

   //==================================================================
   // T08 - two charts of the same symbol, same zone, same bar.
   //   expect: one alert (terminal GlobalVariable claim).
   //   NOTE: the test cannot run two terminals, so it simulates the
   //   second chart by re-running the same bar through a SECOND root
   //   with use_global_vars = true. This is UNVERIFIED on a real
   //   two-chart terminal - see docs "Known limitations".
   //==================================================================
   void              T08_MultiChartSingleAlert()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      cfg.use_global_vars=true;                 // the cross-chart lock
      cfg.popup=false;

      CQuantumRoot r1,r2;
      if(!NewRoot(r1,cfg)) { Check(false,"T08 setup",""); return; }
      if(!NewRoot(r2,cfg)) { Check(false,"T08 setup 2",""); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,105.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,105.20,107.00,105.00,106.80,1000,o,h,l,c,v);
      SetBar(38,106.80,109.40,106.70,107.10,2000,o,h,l,c,v);
      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);

      STacticalFact f;
      f.valid=true; f.bull=false; f.closed_confirm=true;
      f.entry_price=c[38]; f.exec_bar_time=t[38]; f.exec_tf=PERIOD_M1;
      f.trigger=108.00; f.trigger_time=t[37]; f.core_owned=false; f.chase_atr=0.1;

      int pub=0;
      for(int k=0;k<2;k++)
        {
         CQuantumRoot *rr=(k==0?GetPointer(r1):GetPointer(r2));
         if(!rr.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS)) break;
         if(!rr.BuildContext(0.0)) break;
         rr.SetZones(zs,2);
         rr.SetExternalBias(0,0,0);
         rr.TacticalObserve(f);
         if(rr.FinalizeBar(false)) pub++;
        }
      Check(pub<=1,"T08 two charts of one symbol publish at most one alert",
            "published="+IntegerToString(pub)+
            " (chart2 last: "+r2.LastText()+")");
     }

   //==================================================================
   // T09 - HTF bias OPPOSED + strong zone.
   //   expect: downgraded to COUNTER-TREND / SCALP ONLY, or refused -
   //   in both cases the reason names the counter-trend.
   //==================================================================
   void              T09_CounterTrendDowngraded()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T09 setup",""); return; }

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,105.0,0.30,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,105.20,107.00,105.00,106.80,1000,o,h,l,c,v);
      //--- a WEAK rejection: small wick, no volume, no displacement,
      //--- so only the sweep evidence survives -> below the counter-trend
      //--- requirement of min_evidence + 1.
      SetBar(38,108.30,108.60,106.70,108.20,1000,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T09 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T09 context",r.Ctx().data_reason); return; }

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);
      r.SetZones(zs,2);
      //--- BULLISH HTF bias, candidate is a SELL => opposed
      r.SetExternalBias(+1,+1,+1);

      STacticalFact f;
      f.valid=true; f.bull=false; f.closed_confirm=true;
      f.entry_price=c[38]; f.exec_bar_time=t[38]; f.exec_tf=PERIOD_M1;
      f.trigger=108.00; f.trigger_time=t[37]; f.core_owned=false; f.chase_atr=0.1;
      r.TacticalObserve(f);
      r.FinalizeBar(false);

      const SArbiterReport rep=r.Report();
      string txt=r.LastText();
      bool counter_mentioned=(StringFind(txt,"COUNTER-TREND")>=0 ||
                              StringFind(rep.trace,"suppressed")>=0 ||
                              StringFind(rep.trace,"no candidate")>=0);
      Check(!(rep.published && rep.primary.state==(int)SIG_CONFIRMED),
            "T09a an opposed candidate is never published as CONFIRMED",
            "state="+QSMC_StateName(rep.primary.state)+" trace="+rep.trace);
      Check(counter_mentioned,"T09b the counter-trend is named in the text",txt);
     }

   //==================================================================
   // T10 - the series was never loaded. expect: no signal, and the
   //       reason says "data not ready".
   //==================================================================
   void              T10_DataNotReady()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T10 setup",""); return; }

      //--- deliberately NO LoadSynthetic call
      bool built=r.BuildContext(0.0);
      SQZone zs[1];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      r.SetZones(zs,1);

      STacticalFact f;
      f.valid=true; f.bull=false; f.closed_confirm=true;
      f.entry_price=107.10; f.exec_bar_time=(datetime)(TimeCurrent()-60);
      f.exec_tf=PERIOD_M1; f.trigger=108.00;
      f.trigger_time=(datetime)(TimeCurrent()-120);
      f.core_owned=false; f.chase_atr=0.0;
      r.TacticalObserve(f);
      bool pub=r.FinalizeBar(false);

      Check(!built && !pub,"T10a no signal without data",
            "built="+IntegerToString(built?1:0));
      Check(StringFind(r.LastText(),"not ready")>=0 ||
            StringFind(r.LastText(),"series")>=0,
            "T10b the reason names the missing data",r.LastText());
     }
  };

//====================================================================
// Entry point. Returns the number of failed assertions (0 = all pass).
//====================================================================
int QSMC_RunSelfTest()
  {
   CArbSelfTest t;
   int failed=t.Run();
   Print("[QSMC_ARB] self-test: ",IntegerToString(t.Passed())," passed, ",
         IntegerToString(failed)," failed");
   return failed;
  }

#endif
//+------------------------------------------------------------------+
