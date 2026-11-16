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

//--- The synthetic ATR the scenarios are designed against. Flat() builds
//--- bars with a true range of exactly 2*half, so half = QST_ATR/2 makes
//--- the Wilder ATR converge to QST_ATR. Every distance in every scenario
//--- below is expressed in these ATR units; T00 asserts the assumption so
//--- a mismatch between the data and the thresholds cannot pass silently.
#define QST_ATR   2.00
#define QST_HALF  (QST_ATR/2.0)
#define QST_ATR_TOL 0.05   // tolerated relative error of the measured ATR

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
      //--- v6.6.23 T1: a KNOWN-NEUTRAL consensus passes only when the config
      //--- says so. The scenarios below drive synthetic bars that carry no D1/
      //--- H4/H1 series, and they deliberately set a neutral external bias
      //--- (SetExternalBias(0,0,0)); they test location, geometry and timing,
      //--- not the HTF policy, so they keep the permissive config. T16 asserts
      //--- the two stricter paths with the shipped value (false).
      cfg.allow_neutral_bias=true;
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

      T00_HarnessAtrAssumption();
      T11_QuantitativePrimitives();
      T12_StructureCausality();
      T14_ZoneScorer();
      T01_RejectionConfirmedOnce();
      T02_BreakoutContinuationNoCounter();
      T03_SellInsideSupportBlocked();
      T04_BetweenZonesNoTrade();
      T05_FormingBarPreviewOnly();
      T06_M1SpamCollapsesToOne();
      T07_FlipFlopSuppressed();
      T08_MultiChartSingleAlert();
      T09_CounterTrendDowngraded();
      T15_OneZoneRole();
      T16_BiasUnknownIsNotNeutral();
      T17_ExternalBiasContract();
      T18_ReportNamesTheLoser();
      T19_RefusedFactsAreNotCandidates();
      T10_DataNotReady();

      Say("---------------------------------------------------------");
      Say(StringFormat(" RESULT: %d passed, %d failed",m_pass,m_fail));
      Say("---------------------------------------------------------");
      return m_fail;
     }

   //==================================================================
   // T14 - zone scorer hard gates, context factors, and missing data.
   //==================================================================
   void              T14_ZoneScorer()
     {
      CZoneScorer scorer;
      SQZone z; MakeZone(z,ZR_SUPPORT,99.0,101.0,80);
      z.touches=2;
      SZoneScore aligned=scorer.Score(z,1,100.0,1.0,0.0,2.0,1,0.02);
      Check(aligned.valid && aligned.total>=80 && aligned.total<=100,
            "T14 valid aligned support gets a bounded zone rank",aligned.breakdown);
      SZoneScore wrong_role=scorer.Score(z,-1,100.0,1.0,0.0,2.0,-1,0.02);
      Check(!wrong_role.valid && StringFind(wrong_role.rejection,"role conflicts")>=0,
            "T14 failed role gate cannot be overridden by score",wrong_role.rejection);
      z.broken_closed=true;
      SZoneScore broken=scorer.Score(z,1,100.0,1.0,0.0,2.0,1,0.02);
      Check(!broken.valid,"T14 closed-break zone is rejected without flip/retest",broken.rejection);
      z.broken_closed=false; z.state=ZST_BROKEN;
      SZoneScore lifecycle=scorer.Score(z,1,100.0,1.0,0.0,2.0,1,0.02);
      Check(!lifecycle.valid,"T14 broken lifecycle state cannot bypass its close flag",lifecycle.rejection);
      z.flipped=true; z.retested=true; z.state=ZST_FLIPPED; z.role=ZR_RESISTANCE;
      SZoneScore missing=scorer.Score(z,-1,100.0,1.0,0.0,-1.0,0,-1.0);
      Check(missing.valid && (missing.missing_mask&QZS_MISSING_HTF)!=0 &&
            (missing.missing_mask&QZS_MISSING_ROOM)!=0 &&
            (missing.missing_mask&QZS_MISSING_SPREAD)!=0,
            "T14 missing confluence inputs are explicit, not treated as agreement",missing.breakdown);
     }

   //==================================================================
   // T12 - causal swing confirmation, BOS/CHoCH close semantics, and
   //       once-per-closed-bar processing in the new structure engine.
   //==================================================================
   void              T12_StructureCausality()
     {
      CStructureEngine engine;
      bool init=engine.Init(_Symbol,(ENUM_TIMEFRAMES)_Period,2,2,0.15,0.25,0.20,1.0,0.60);
      MqlRates r[11];
      for(int i=0;i<11;i++)
        {
         r[i].time=(datetime)(1000+i*60);
         r[i].open=10.0; r[i].high=12.0; r[i].low=9.0; r[i].close=10.0;
         r[i].tick_volume=100;
        }
      r[2].high=15.0; r[2].low=8.0;
      r[6].high=18.0; r[6].low=7.0;
      r[9].open=19.5; r[9].high=22.0; r[9].low=7.0; r[9].close=20.0;
      r[10].open=7.0; r[10].high=8.0; r[10].low=6.0; r[10].close=6.5;
      if(!init) { Check(false,"T12 structure engine init",""); return; }

      SStructureEvent ev[];
      bool causal=true, higher_high=false, bos=false, choch=false, invalidated=false;
      datetime swing_available=0;
      for(int i=4;i<11;i++)
        {
         if(!engine.ProcessClosed(r,i,r[i].time+(datetime)60,100.0,ev))
           { causal=false; break; }
         for(int e=0;e<ArraySize(ev);e++)
           {
            if(ev[e].type==MS_SWING_HIGH && ev[e].event_time==r[2].time)
              {
               if(i<4 || ev[e].available_time!=r[i].time+(datetime)60) causal=false;
               swing_available=ev[e].available_time;
              }
            if(ev[e].type==MS_HIGHER_HIGH && ev[e].event_time==r[6].time) higher_high=true;
            if(ev[e].type==MS_BOS_UP && ev[e].event_time==r[9].time) bos=true;
            if(ev[e].type==MS_CHOCH_DOWN && ev[e].event_time==r[10].time) choch=true;
            if(ev[e].type==MS_STRUCTURE_INVALIDATED && ev[e].event_time==r[10].time) invalidated=true;
           }
        }
      Check(causal && swing_available==r[5].time,"T12 swing event is available only after right bars close","");
      Check(higher_high,"T12 confirmed HH compares only with prior confirmed swing","");
      Check(bos && engine.Trend()==-1,"T12 BOS requires a close beyond confirmed structure and state flips on CHoCH","");
      Check(choch && invalidated,"T12 opposite close emits CHoCH and structural invalidation","");
      bool duplicate_ok=engine.ProcessClosed(r,10,r[10].time+(datetime)60,100.0,ev);
      Check(duplicate_ok && ArraySize(ev)==0 && engine.LastProcessedTime()==r[10].time,
            "T12 duplicate closed-bar call is a no-op","");

      CStructureEngine sweep_engine,break_engine;
      bool init_s=sweep_engine.Init(_Symbol,(ENUM_TIMEFRAMES)_Period,2,2,0.15,0.25,0.20,1.0,0.60);
      bool init_b=break_engine.Init(_Symbol,(ENUM_TIMEFRAMES)_Period,2,2,0.15,0.25,0.20,1.0,0.60);
      MqlRates liq[10];
      for(int j=0;j<10;j++)
        {
         liq[j].time=(datetime)(2000+j*60);
         liq[j].open=10.0; liq[j].high=12.0; liq[j].low=9.0; liq[j].close=10.0;
         liq[j].tick_volume=100;
        }
      liq[2].high=15.0; liq[6].high=15.0;
      liq[9].open=15.5; liq[9].high=16.0; liq[9].low=14.0; liq[9].close=15.0;
      bool saw_sweep=false,saw_equal_pool=false,saw_breakout_in_sweep=false;
      if(init_s)
        for(int j=4;j<10;j++)
          {
           if(!sweep_engine.ProcessClosed(liq,j,liq[j].time+(datetime)60,100.0,ev)) break;
           for(int e=0;e<ArraySize(ev);e++)
             {
              if(ev[e].type==MS_BUY_SIDE_LIQUIDITY) saw_equal_pool=true;
              if(ev[e].type==MS_LIQUIDITY_SWEEP_HIGH) saw_sweep=true;
              if(ev[e].type==MS_LIQUIDITY_BREAKOUT_HIGH) saw_breakout_in_sweep=true;
             }
          }
      bool break_scenario=false,break_sweep=false;
      if(init_b)
        {
         liq[9].open=15.2; liq[9].high=16.0; liq[9].low=14.8; liq[9].close=15.5;
         for(int j=4;j<10;j++)
           {
            if(!break_engine.ProcessClosed(liq,j,liq[j].time+(datetime)60,100.0,ev)) break;
            if(j==9)
              for(int e=0;e<ArraySize(ev);e++)
              {
               if(ev[e].type==MS_LIQUIDITY_BREAKOUT_HIGH) break_scenario=true;
               if(ev[e].type==MS_LIQUIDITY_SWEEP_HIGH) break_sweep=true;
              }
           }
        }
      Check(saw_equal_pool,"T12 buy-side liquidity requires confirmed equal highs","");
      Check(saw_sweep && !saw_breakout_in_sweep,
            "T12 wick penetration plus close-back is a sweep, not breakout","");
      Check(break_scenario && !break_sweep,
            "T12 close beyond equal-high pool is a confirmed breakout, not a sweep","");
     }

   //==================================================================
   // T11 - independent quantitative primitives: weighted moments, CUSUM,
   //       Wilson boundary cases, and broker tick-volume profile semantics.
   //==================================================================
   void              T11_QuantitativePrimitives()
     {
      SEWState ew; CEWStatistics::Reset(ew);
      bool u1=CEWStatistics::Update(ew,10.0,0.5);
      bool u2=CEWStatistics::Update(ew,12.0,0.5);
      Check(u1 && u2 && MathAbs(ew.mean-11.0)<1e-10 &&
            MathAbs(ew.variance-1.0)<1e-10,"T11 EW mean and stable weighted variance","");
      CEWStatistics::Reset(ew);
      Check(!ew.initialized && ew.count==0 && ew.mean==0.0 && ew.variance==0.0,
            "T11 EW reset clears all state","");

      CCUSUM cusum;
      bool updates=true;
      for(int i=0;i<4;i++) updates=updates && cusum.Update(1.0,0.0,1.0,0.5,2.0);
      Check(updates && cusum.Alarm() && cusum.Side()==1,"T11 CUSUM detects positive shift","");
      cusum.Reset();
      Check(!cusum.Alarm() && cusum.Side()==0 && cusum.Count()==0,
            "T11 CUSUM reset clears sums and alarm","");

      double lower,upper;
      bool w0=QSMC_WilsonInterval(0,10,1.96,lower,upper);
      Check(w0 && lower==0.0 && upper>0.0 && upper<1.0,
            "T11 Wilson interval handles zero successes","");
      bool w1=QSMC_WilsonInterval(10,10,1.96,lower,upper);
      Check(w1 && upper==1.0 && lower>0.0 && lower<1.0,
            "T11 Wilson interval handles all successes","");
      Check(!QSMC_WilsonInterval(11,10,1.96,lower,upper),
            "T11 Wilson rejects impossible counts","");

      MqlRates rates[3];
      rates[0].time=100; rates[0].low=100.0; rates[0].high=102.0; rates[0].tick_volume=20;
      rates[1].time=200; rates[1].low=101.0; rates[1].high=103.0; rates[1].tick_volume=50;
      rates[2].time=300; rates[2].low=103.0; rates[2].high=103.0; rates[2].tick_volume=30;
      CVolumeProfile vp;
      bool built=vp.Build(rates,0,3,1.0,0.70,false);
      SVolumeProfileResult pr=vp.Result();
      Check(built && pr.valid && pr.accepted_bars==3 && pr.coverage==1.0 &&
            MathAbs(pr.total_tick_volume-100.0)<1e-10 && MathAbs(pr.poc-103.5)<1e-10 &&
            MathAbs(pr.val-102.0)<1e-10 && MathAbs(pr.vah-104.0)<1e-10,
            "T11 volume profile POC/value area/coverage",pr.volume_basis);
      bool invalid_profile=vp.Build(rates,0,3,0.0,0.70,false);
      pr=vp.Result();
      Check(!invalid_profile && !pr.valid,
            "T11 volume profile rejects invalid bin size","");
     }

   //==================================================================
   // T00 - GUARD: the synthetic series must actually produce the ATR the
   //       scenarios are written against. Every distance below is in ATR
   //       units, so if this drifts the other assertions become meaningless
   //       (they can even pass for the wrong reason). This turns a silent
   //       unit error into a loud failure.
   //==================================================================
   void              T00_HarnessAtrAssumption()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T00 setup",""); return; }

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,105.0,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T00 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T00 context",r.CtxDataReason()); return; }

      double measured=r.CtxAtr();
      double err=MathAbs(measured-QST_ATR)/QST_ATR;
      Check(err<=QST_ATR_TOL,"T00 the synthetic ATR matches QST_ATR",
            StringFormat("expected %.2f measured %.4f err %.1f%%",
                         QST_ATR,measured,err*100.0));
      Check(r.MarketDirection()==0 && StringFind(r.MarketDirectionText(),"NEUTRAL / WAIT")>=0 &&
            StringFind(r.MarketDirectionText(),"not probability")>=0,
            "T00 direction integration reports neutral without confirmed evidence",r.MarketDirectionText());
      SEarlyBreakResult early;
      r.GetEarlyBreakResult(early);
      Check(early.valid && !early.warning && (early.missing_mask & QEB_MISS_QUOTES)!=0,
            "T00 early-break feature stays warning-only and reports unavailable quote flow",early.label);
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
      Flat(QST_BARS,105.0,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      //--- approach
      SetBar(37,105.20,107.00,105.00,106.80,1000,o,h,l,c,v);
      //--- the rejection bar (last CLOSED bar = index 38)
      SetBar(38,106.80,109.40,106.70,107.10,2000,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);

      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T01 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T01 context",r.CtxDataReason()); return; }

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

      bool dir_ok=r.PrimaryValid() && r.PrimaryDir()<0;
      Check(r.ReportPublished() && dir_ok,"T01a SELL published at resistance",
            "state="+QSMC_StateName(r.PrimaryState())+" trace="+r.ReportTrace());
      Check(dir_ok && r.PrimaryZoneRole()==ZR_RESISTANCE,"T01b zone role is RESISTANCE",
            QSMC_RoleName(r.PrimaryZoneRole()));

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
      Flat(QST_BARS,106.0,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,106.00,108.60,105.90,108.40,1000,o,h,l,c,v);
      //--- acceptance: closed 1.00 above the zone top (0.50 ATR > 0.30)
      SetBar(38,108.40,110.10,108.20,110.00,2000,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T02 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T02 context",r.CtxDataReason()); return; }

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

      Check(r.ReportPublished() && r.PrimaryDir()>0,
            "T02a BUY continuation published above a broken resistance",
            "state="+QSMC_StateName(r.PrimaryState())+" trace="+r.ReportTrace());
      Check(!(r.PrimaryValid() && r.PrimaryDir()<0),
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
      Flat(QST_BARS,90.50,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(38,90.60,90.90,90.30,90.40,2000,o,h,l,c,v);   // bearish bar inside support

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T03 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T03 context",r.CtxDataReason()); return; }

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

      Check(!r.ReportPublished(),"T03a no SELL alert inside a SUPPORT zone",
            "trace="+r.ReportTrace());
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
      Flat(QST_BARS,100.0,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(38,100.00,101.00,99.50,100.80,2000,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T04 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T04 context",r.CtxDataReason()); return; }

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

      Check(!r.ReportPublished(),"T04a no signal between zones","trace="+r.ReportTrace());
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
      Flat(QST_BARS,106.0,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,106.00,108.60,105.90,108.40,1000,o,h,l,c,v);
      SetBar(38,106.80,109.40,106.70,107.10,2000,o,h,l,c,v);   // closed rejection
      //--- the FORMING bar sticks into the zone
      SetBar(39,107.10,109.60,106.90,107.20,1500,o,h,l,c,v);

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T05 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T05 context",r.CtxDataReason()); return; }

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

      bool forming=(f.exec_bar_time>t[38]);
      Check(forming,"T05a the fact really cites the forming bar",
            TimeToString(f.exec_bar_time,TIME_MINUTES));
      Check(!r.ReportPublished() || r.PrimaryState()!=(int)SIG_CONFIRMED,
            "T05b a forming-bar fact never publishes CONFIRMED",
            "state="+QSMC_StateName(r.PrimaryState())+" trace="+r.ReportTrace());
      Check(StringFind(r.LastText(),"CONFIRMED")<0 || !r.ReportPublished(),
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
      Flat(QST_BARS,106.0,QST_HALF,1000,
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
         //--- A genuine closed-bar rejection every single iteration: the
         //--- bar spikes through 108.00-109.00 and closes back below it.
         //--- (The previous data only touched the band for k>=23, so the
         //--- assertion passed even with the anti-spam locks removed.)
         double base=107.20+0.01*(double)k;
         SetBar(m-1,base-0.10,109.30,107.00,base,(k%3==0?2200:1000),o,h,l,c,v);
         SetBar(m,  base,base+0.25,base-0.20,base+0.15,1000,o,h,l,c,v);

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
      Flat(QST_BARS,107.0,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,106.80,107.60,106.70,107.20,1000,o,h,l,c,v);
      SetBar(38,107.20,109.30,107.10,107.30,2000,o,h,l,c,v);   // SELL rejection

      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T07 synthetic load",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T07 context",r.CtxDataReason()); return; }
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
      //--- break_atr(0.30) x QST_ATR(2.00) = 0.60, so the close must exceed
      //--- 109.60 for this to be an ACCEPTANCE rather than another rejection.
      SetBar(m-1,107.30,110.30,107.20,110.00,2000,o,h,l,c,v);   // acceptance up
      SetBar(m,  110.00,110.40,109.80,110.20,1000,o,h,l,c,v);
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
      Flat(QST_BARS,105.0,QST_HALF,1000,
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
      Flat(QST_BARS,105.0,QST_HALF,1000,
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
      if(!r.BuildContext(0.0)) { Check(false,"T09 context",r.CtxDataReason()); return; }

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

      string txt=r.LastText();
      bool counter_mentioned=(StringFind(txt,"COUNTER-TREND")>=0 ||
                              StringFind(r.ReportTrace(),"suppressed")>=0 ||
                              StringFind(r.ReportTrace(),"no candidate")>=0);
      Check(!(r.ReportPublished() && r.PrimaryState()==(int)SIG_CONFIRMED),
            "T09a an opposed candidate is never published as CONFIRMED",
            "state="+QSMC_StateName(r.PrimaryState())+" trace="+r.ReportTrace());
      Check(counter_mentioned,"T09b the counter-trend is named in the text",txt);
     }

   //==================================================================
   // T15 - ONE ROLE (v6.6.9 AUDIT-SIG1). A level broken by a CLOSED bar is
   //       published with its REVERSED role, and the LOCATION gate reads
   //       exactly that role. A candidate that still trades the birth role
   //       is therefore refused, and the mirrored candidate in the reversed
   //       role is not refused by the role test. Mirrors T11 in
   //       tools/test_arbiter.py: the two implementations must agree.
   //==================================================================
   void              T15_OneZoneRole()
     {
      SQZone in[2];
      MakeZone(in[0],ZR_SUPPORT,90.00,91.00,85);       // broken support
      in[0].flipped=true;
      MakeZone(in[1],ZR_RESISTANCE,108.00,109.00,80);  // broken resistance
      in[1].flipped=true;

      //--- the registry is the publisher: Rebuild() resolves
      //--- role = EffectiveRole(birth_role, flipped), and every gate reads
      //--- THAT role, never the birth role.
      CZoneRegistry reg;
      int n=reg.Rebuild(in,2,2.0,0.50,60);
      SQZone a,b;
      bool fa=reg.Find(in[0].id,a);
      bool fb=reg.Find(in[1].id,b);
      Check(n==2 && fa && a.role==ZR_RESISTANCE,
            "T15a a support broken by a closed bar is published as RESISTANCE",
            "role="+IntegerToString((int)a.role));
      Check(fb && b.role==ZR_SUPPORT,
            "T15b a resistance broken by a closed bar is published as SUPPORT",
            "role="+IntegerToString((int)b.role));

      //--- and the gate that reads it refuses the birth-role direction.
      SQsmcArbConfig cfg; CfgBase(cfg);
      SSignalCandidate cand;
      cand.valid=true;
      cand.dir=+1;                       // BUY = the BIRTH role of in[0]
      cand.zone_id=in[0].id;
      cand.bar_closed=true;
      SGateCtx ctx;
      ctx.data_ready=true;
      ctx.atr=2.0;
      ctx.point=_Point;
      ctx.price=90.50;                   // inside the band
      string why="";
      int ds=(int)SIG_WATCH;
      CLocationGate lg;
      ENUM_GATE_RESULT gr=lg.Evaluate(cand,ctx,cfg,reg,why,ds);
      Check(gr==GATE_FAIL && StringFind(why,"RESISTANCE")>=0,
            "T15c a BUY in the BIRTH role at that level is refused by LOCATION",
            why);
      cand.dir=-1;                       // SELL = the role it now carries
      string why2="";
      ENUM_GATE_RESULT gr2=lg.Evaluate(cand,ctx,cfg,reg,why2,ds);
      Check(gr2==GATE_FAIL && StringFind(why2,"RESISTANCE")<0,
            "T15d the mirrored direction is not refused for its ROLE",
            why2);
     }

   //==================================================================
   // T16 - UNKNOWN bias is not NEUTRAL bias (v6.6.23 T1).
   //       Old behaviour: agree==0 returned GATE_PASS, so a chart with no
   //       higher-timeframe information at all could publish CONFIRMED.
   //       New behaviour: no known bias -> DOWNGRADE to WATCH; a known but
   //       neutral consensus -> DOWNGRADE unless cfg.allow_neutral_bias.
   //==================================================================
   void              T16_BiasUnknownIsNotNeutral()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      SSignalCandidate cand;
      cand.valid=true;
      cand.dir=+1;
      cand.state=(int)SIG_CONFIRMED;
      cand.bar_closed=true;
      cand.score=90;
      cand.zone_id="T16";
      SGateCtx ctx;
      ctx.data_ready=true;
      ctx.atr=QST_ATR;
      ctx.point=_Point;
      ctx.price=100.0;
      ctx.bias_score=0; ctx.d1_bias=0; ctx.h4_bias=0; ctx.h1_bias=0;
      string why="";
      int ds=(int)SIG_CONFIRMED;
      CBiasGate gate;
      CZoneRegistry reg;                 // the bias gate never reads it, but a
                                         // reference parameter needs a real object

      //--- (a) nothing known at all -> not PASS, capped at WATCH
      ctx.bias_known=false;
      ENUM_GATE_RESULT a=gate.Evaluate(cand,ctx,cfg,reg,why,ds);
      Check(a==GATE_DOWNGRADE && ds==(int)SIG_WATCH && StringFind(why,"unknown")>=0,
            "T16a no HTF information is never agreement: DOWNGRADE to WATCH",why);

      //--- (b) known but neutral with the shipped policy (allow=false)
      ctx.bias_known=true;
      cfg.allow_neutral_bias=false;
      why=""; ds=(int)SIG_CONFIRMED;
      ENUM_GATE_RESULT b=gate.Evaluate(cand,ctx,cfg,reg,why,ds);
      Check(b==GATE_DOWNGRADE && ds==(int)SIG_WATCH && StringFind(why,"neutral")>=0,
            "T16b a known-neutral consensus does not license CONFIRMED either",why);

      //--- (c) the same neutral consensus passes only when explicitly allowed
      cfg.allow_neutral_bias=true;
      why=""; ds=(int)SIG_CONFIRMED;
      ENUM_GATE_RESULT c=gate.Evaluate(cand,ctx,cfg,reg,why,ds);
      Check(c==GATE_PASS,"T16c neutral PASS requires an explicit config switch",why);

      //--- (d) agreement still passes, and opposition still fails
      ctx.d1_bias=+1;
      ctx.bias_score=+50;
      why=""; ds=(int)SIG_CONFIRMED;
      ENUM_GATE_RESULT d=gate.Evaluate(cand,ctx,cfg,reg,why,ds);
      Check(d==GATE_PASS,"T16d an agreeing known consensus still passes",why);

      cfg.allow_countertrend=false;
      ctx.bias_score=-50;
      why="";
      ENUM_GATE_RESULT e=gate.Evaluate(cand,ctx,cfg,reg,why,ds);
      Check(e==GATE_FAIL && StringFind(why,"opposes")>=0,
            "T16e an opposed consensus still fails with counter-trend disabled",why);
     }

   //==================================================================
   // T17 - the external bias contract carries a known-flag per timeframe
   //       (v6.6.23 T2). A host with no D1/H4/H1 data can now say so,
   //       an unknown timeframe is removed from the weight sum instead of
   //       voting neutral, and "nothing known" is UNKNOWN - not 0.
   //==================================================================
   void              T17_ExternalBiasContract()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);   // w_d1=50 w_h4=30 w_h1=20
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) return;
      SGateCtx ctx;

      //--- (a) D1 and H4 agree short, H1 absent (the host's own call shape:
      //---     h1_known=false), so the H1 weight must not enter the sum.
      r.SetExternalBias(-1,-1,0,false);
      r.GetContext(ctx);
      Check(ctx.bias_known && ctx.htf_bias==-1 && ctx.bias_score==-100 &&
            ctx.d1_bias==-1 && ctx.h4_bias==-1 && ctx.h1_bias==0,
            "T17a D1+H4 short with H1 absent: known, -100, htf -1",
            "known="+(string)ctx.bias_known+" score="+IntegerToString(ctx.bias_score)+
            " htf="+IntegerToString(ctx.htf_bias));

      //--- (b) H4 is NOT known: its +1 must be dropped from the numerator.
      //---     with it: (-50+30+20)/100 = 0. without it: (-50+20)/70 = -43.
      r.SetExternalBias(-1,+1,+1,true,true,false);
      r.GetContext(ctx);
      Check(ctx.bias_known && ctx.h4_bias==0 && ctx.h1_bias==1 &&
            ctx.bias_score==-43,
            "T17b an unknown H4 is excluded from the weight sum",
            "score="+IntegerToString(ctx.bias_score)+
            " h4="+IntegerToString(ctx.h4_bias));

      //--- (c) nothing known at all -> UNKNOWN (T1 then refuses to license)
      r.SetExternalBias(0,0,0,false,false,false);
      r.GetContext(ctx);
      Check(!ctx.bias_known && ctx.bias_score==0 && ctx.htf_bias==0,
            "T17c no known timeframe is UNKNOWN, not a neutral consensus",
            "known="+(string)ctx.bias_known+" htf="+IntegerToString(ctx.htf_bias));

      //--- (d) one known timeframe that is neutral -> known-neutral
      r.SetExternalBias(0,0,0,true,false,false);
      r.GetContext(ctx);
      Check(ctx.bias_known && ctx.bias_score==0 && ctx.htf_bias==0,
            "T17d a known-neutral H1 stays KNOWN with a 0 consensus",
            "known="+(string)ctx.bias_known+" score="+IntegerToString(ctx.bias_score));

      //--- (e) the legacy 4-argument call keeps its meaning: value defaults
      //---     to known, so the consensus is still computed.
      r.SetExternalBias(+1,0,0);
      r.GetContext(ctx);
      Check(ctx.bias_known && ctx.htf_bias==1 && ctx.bias_score==50,
            "T17e a 4-argument call is still D1/H4 known (50/100=+50)",
            "score="+IntegerToString(ctx.bias_score));
     }

   //==================================================================
   // T18 - the report names the loser (v6.6.23 T3).
   //       Finalize() used to discard ev.reject_text and leave trace as
   //       "no candidate survived the gates", so a silent bar could not
   //       be explained from the journal at all.
   //==================================================================
   void              T18_ReportNamesTheLoser()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);
      CSignalArbiter arb;
      arb.Init(NULL,false,false);      // no history: the anti-spam gates are unused
      SGateCtx ctx;
      ctx.data_ready=true;
      ctx.atr=QST_ATR;
      ctx.point=_Point;
      ctx.price=100.0;
      ctx.tick_size=_Point;
      ctx.closed_index=39;              // CfgBase.min_bars = 30
      ctx.digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
      ctx.bar_time=D'2024.01.02 10:00';
      ctx.bias_known=true;
      ctx.bias_score=0; ctx.d1_bias=0; ctx.h4_bias=0; ctx.h1_bias=0;
      ctx.session_ok=-1;

      SSignalCandidate c;
      c.valid=true;
      c.dir=+1;
      c.source=SRC_CORE;
      c.state=(int)SIG_CONFIRMED;
      c.bar_closed=true;
      c.score=90;
      c.zone_id="T18-NOT-IN-REGISTRY";
      c.bar_index=38;
      c.entry=100.00;
      c.sl=99.00;
      c.tp1=102.00;
      c.rr=2.0;
      arb.Submit(c,D'2024.01.02 10:00');

      CZoneRegistry zones;             // deliberately empty: LOCATION refuses
      CAlertManager alerts;            // never touched - nothing survives
      SArbiterReport rep;
      bool ok=arb.Finalize(ctx,cfg,zones,alerts,rep);
      Check(!ok && rep.rejected==1 &&
            StringFind(rep.trace,"first: DATA_QUALITY:")>=0,
            "T18a the report keeps the first refusal instead of a bare no-survivor line",
            rep.trace);
      Check(StringFind(rep.trace,"1 rejected")>=0 && rep.reject_first!="",
            "T18b the report counts the refusals",rep.trace);

      //--- a bar without candidates still says exactly that, and the
      //--- reject fields stay empty (no stale text from the previous bar).
      SArbiterReport rep2;
      arb.SetAuthoritativePending(false);
      bool ok2=arb.Finalize(ctx,cfg,zones,alerts,rep2);
      Check(!ok2 && rep2.trace=="no candidate" && rep2.reject_first=="",
            "T18c a bar with no candidate keeps its own trace",rep2.trace);
      arb.Shutdown();
     }

   //==================================================================
   // T19 - a refused fact is not a candidate (v6.6.23 T4).
   //       BuildTacticalCandidate() used to leave out.valid=true on two
   //       rejection paths (no location fact / stop geometry), and
   //       FinalizeBar() submits on (valid && dir!=0). A fact that never
   //       had a direction from the market therefore reached the arbiter,
   //       was counted as evaluated, and was refused with a message about
   //       entry/stop prices it never had. The label also lost the real
   //       reason. Both halves are asserted here: the refused fact must
   //       not be submitted, and a real rejection must still publish.
   //==================================================================
   void              T19_RefusedFactsAreNotCandidates()
     {
      SQsmcArbConfig cfg; CfgBase(cfg);

      double o[],h[],l[],c[]; datetime t[]; long v[];
      Flat(QST_BARS,105.0,QST_HALF,1000,
           (datetime)(TimeCurrent()-(QST_BARS*60)),60,o,h,l,c,t,v);
      SetBar(37,105.20,107.00,105.00,106.80,1000,o,h,l,c,v);   // approach
      SetBar(38,106.80,109.40,106.70,107.10,2000,o,h,l,c,v);   // rejection bar
      double eo[],eh[],el[],ec[]; datetime et[]; long ev[];
      Copy6(QST_BARS,o,h,l,c,t,v,eo,eh,el,ec,et,ev);

      SQZone zs[2];
      MakeZone(zs[0],ZR_RESISTANCE,108.00,109.00,80);
      MakeZone(zs[1],ZR_SUPPORT,90.00,91.00,78);

      //--- (a) the fact cites a bar that never touched the zone
      CQuantumRoot r;
      if(!NewRoot(r,cfg)) { Check(false,"T19 setup a",""); return; }
      if(!r.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T19 synthetic load a",""); return; }
      if(!r.BuildContext(0.0)) { Check(false,"T19 context a",r.CtxDataReason()); return; }
      r.SetZones(zs,2);
      r.SetExternalBias(0,0,0);
      STacticalFact f;
      f.valid=true; f.bull=false; f.closed_confirm=true;
      f.entry_price=108.50; f.exec_bar_time=t[37]; f.exec_tf=PERIOD_M1;
      f.trigger=108.00; f.trigger_time=t[36]; f.core_owned=false; f.chase_atr=0.2;
      r.TacticalObserve(f);
      r.FinalizeBar(false);
      Check(!r.ReportPublished() && r.ReportEvaluated()==0,
            "T19a a fact with no location evidence is never submitted to the arbiter",
            "evaluated="+IntegerToString(r.ReportEvaluated())+" trace="+r.ReportTrace());
      Check(StringFind(r.LastText(),"did not reject or accept")>=0,
            "T19b the chart says why the fact was refused, not 'no candidate survived'",
            r.LastText());

      //--- (b) the SAME data with the real rejection bar still publishes:
      //---     the filter must not swallow legitimate candidates.
      CQuantumRoot r2;
      if(!NewRoot(r2,cfg)) { Check(false,"T19 setup b",""); return; }
      if(!r2.LoadSynthetic(o,h,l,c,t,v,QST_BARS,eo,eh,el,ec,et,ev,QST_BARS))
        { Check(false,"T19 synthetic load b",""); return; }
      if(!r2.BuildContext(0.0)) { Check(false,"T19 context b",r2.CtxDataReason()); return; }
      r2.SetZones(zs,2);
      r2.SetExternalBias(0,0,0);
      STacticalFact f2;
      f2.valid=true; f2.bull=false; f2.closed_confirm=true;
      f2.entry_price=c[38]; f2.exec_bar_time=t[38]; f2.exec_tf=PERIOD_M1;
      f2.trigger=108.00; f2.trigger_time=t[37]; f2.core_owned=false; f2.chase_atr=0.2;
      r2.TacticalObserve(f2);
      r2.FinalizeBar(false);
      Check(r2.ReportPublished() && r2.ReportEvaluated()==1,
            "T19c a real closed-bar rejection is still submitted and published",
            "evaluated="+IntegerToString(r2.ReportEvaluated())+" trace="+r2.ReportTrace());
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
