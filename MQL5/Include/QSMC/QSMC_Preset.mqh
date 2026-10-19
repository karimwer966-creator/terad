//+------------------------------------------------------------------+
//|                                                QSMC_Preset.mqh   |
//|  CPresetManager - SCALPER / INTRADAY / SWING presets plus the     |
//|  user's explicit overrides.                                       |
//|                                                                   |
//|  OVERRIDE RULE (same convention as the host's QSMC_PresetDouble)  |
//|  A preset value is applied only while the corresponding input      |
//|  still equals its documented DEFAULT. Any non-default value is     |
//|  treated as the user's explicit override and always wins. This     |
//|  keeps saved .set files meaningful.                                |
//|                                                                   |
//|  NO PUBLIC INPUT IS RENAMED BY THIS RELEASE. Every input added    |
//|  here is new and prefixed InpArb; see docs/CHANGELOG for the      |
//|  full list with defaults.                                         |
//+------------------------------------------------------------------+
#ifndef __QSMC_PRESET_MQH__
#define __QSMC_PRESET_MQH__

#include <QSMC/QSMC_Types.mqh>

//--------------------------------------------------------------------
// Preset selector. AUTO picks from the chart timeframe:
//   M1..M5   -> SCALPER
//   M15..H1  -> INTRADAY
//   H4..D1   -> SWING
//--------------------------------------------------------------------
enum ENUM_QSMC_PRESET
  {
   QSMC_PRESET_AUTO     = 0,
   QSMC_PRESET_SCALPER  = 1,
   QSMC_PRESET_INTRADAY = 2,
   QSMC_PRESET_SWING    = 3,
   QSMC_PRESET_CUSTOM   = 4     // user values only; no preset is applied
  };

//====================================================================
// INPUTS (new in v6.6.0 - none of them replace an existing input)
//====================================================================
input bool   InpArbEnabled              = true;    // master switch for the signal arbitration layer
input ENUM_QSMC_PRESET InpArbPreset     = QSMC_PRESET_AUTO;
input bool   InpArbGateTactical         = true;    // route the MTF tactical path through every gate (fix for symptoms 1-4)
input bool   InpArbTacticalMayConfirm   = false;   // false: the tactical path can never publish CONFIRMED (terminology rule R7)
input bool   InpArbGateCore             = false;   // true: also gate the CORE path (default off - Core keeps its own validated gates)
input bool   InpArbPopup                = true;    // Alert() popup on a published arbitration signal
input bool   InpArbPush                 = false;   // SendNotification() push
input bool   InpArbSound                = false;   // PlaySound()
input bool   InpArbVerboseLog           = false;   // Print() every gate verdict per closed bar
input bool   InpArbCSVLog               = false;   // write the signal CSV journal (MQL5/Files)

//--- location (R1)
input double InpArbZoneReachATR         = 1.50;    // beyond this many ATR from the nearest zone => BETWEEN ZONES / NO TRADE
input double InpArbMergeTolATR          = 0.50;    // zone merge tolerance
input double InpArbMaxPenetrationATR    = 0.35;    // a rejection may pierce the role edge by at most this x ATR
input double InpArbBreakATR             = 0.30;    // a CLOSED bar beyond the role edge by this x ATR = breakout/acceptance
input int    InpArbMinZoneStrength      = 60;      // minimum ZONE STRENGTH that may own a signal (0-100)
input int    InpArbMinEvidence          = 2;       // independent evidence groups required for CONFIRMED (of 6)
input int    InpArbRetestLookback       = 24;      // closed bars a broken zone has to be retested within

//--- rejection geometry
input double InpArbMinWickRatio         = 0.50;    // rejection wick as a fraction of the bar range
input double InpArbVolumeMult           = 1.60;    // volume expansion over the 20-bar median
input double InpArbDispATR              = 0.50;    // displacement away from the level, in ATR

//--- bias (R2)
input int    InpArbBiasW_D1             = 50;      // D1 weight in the consensus
input int    InpArbBiasW_H4             = 30;      // H4 weight
input int    InpArbBiasW_H1             = 20;      // H1 weight
input bool   InpArbAllowCounterTrend    = true;    // true: a counter-trend signal is DOWNGRADED, not deleted
input int    InpArbCounterTrendMinScore = 70;      // evidence score a counter-trend signal needs to survive
input int    InpArbCounterTrendExtraEv  = 1;       // extra evidence group a counter-trend signal needs

//--- room (R4)
input double InpArbMinRR                = 1.50;    // minimum reward:risk to TP1
input double InpArbMaxStopATR           = 4.00;    // stop wider than this x ATR = no signal
input double InpArbSLBufferATR          = 0.20;    // invalidation buffer beyond the zone edge

//--- anti-spam (R5)
input int    InpArbCooldownBars         = 10;      // closed bars between two alerts of the same (symbol,zone,direction,state)
input double InpArbMinAlertDistanceATR  = 0.50;    // minimum price move (ATR) from the previous alert on the same zone+direction
input int    InpArbFlipFlopBars         = 10;      // suppress the OPPOSITE direction on the same zone for this many bars
input bool   InpArbUseGlobalVars        = true;    // share the last-alert claim across charts of the same symbol
input int    InpArbDedupeRing           = 256;     // retained exact alert keys (64..4096)

//--- data quality / session
input double InpArbMinATRPoints         = 0.0;     // dead-market ATR floor in points (0 = one tick)
input int    InpArbMaxSpreadPoints      = 0;       // 0 = no spread gate
input int    InpArbMinBars              = 120;     // minimum closed bars before any arbitration
input int    InpArbSessionStartHour     = -1;      // -1 = no session filter (server hours 0-23)
input int    InpArbSessionEndHour       = -1;      // -1 = no session filter
input int    InpArbMinSample            = 30;      // CStatsLogger withholds every rate below this n

//====================================================================
// Documented defaults. Used ONLY to detect a user override.
//====================================================================
#define ARB_DEF_ZONE_REACH        1.50
#define ARB_DEF_MERGE_TOL         0.50
#define ARB_DEF_MAX_PEN           0.35
#define ARB_DEF_BREAK             0.30
#define ARB_DEF_MIN_STRENGTH      60
#define ARB_DEF_MIN_EVIDENCE      2
#define ARB_DEF_RETEST            24
#define ARB_DEF_MIN_WICK          0.50
#define ARB_DEF_VOL_MULT          1.60
#define ARB_DEF_DISP              0.50
#define ARB_DEF_MIN_RR            1.50
#define ARB_DEF_MAX_STOP          4.00
#define ARB_DEF_SL_BUF            0.20
#define ARB_DEF_COOLDOWN          10
#define ARB_DEF_MIN_DIST          0.50
#define ARB_DEF_FLIPFLOP          10

//+------------------------------------------------------------------+
class CPresetManager
  {
private:
   ENUM_QSMC_PRESET  m_effective;

   static bool       IsDefault(const double v,const double d)
     { return (MathAbs(v-d)<=1.0e-8); }
   static bool       IsDefault(const int v,const int d)
     { return (v==d); }

public:
                     CPresetManager() { m_effective=QSMC_PRESET_AUTO; }
                    ~CPresetManager() {}

   //--- Resolve AUTO from the chart timeframe.
   ENUM_QSMC_PRESET  Resolve(const ENUM_QSMC_PRESET requested,const ENUM_TIMEFRAMES tf)
     {
      if(requested!=QSMC_PRESET_AUTO) { m_effective=requested; return m_effective; }
      int sec=PeriodSeconds(tf);
      if(sec<=PeriodSeconds(PERIOD_M5))  m_effective=QSMC_PRESET_SCALPER;
      else if(sec<=PeriodSeconds(PERIOD_H1)) m_effective=QSMC_PRESET_INTRADAY;
      else m_effective=QSMC_PRESET_SWING;
      return m_effective;
     }

   ENUM_QSMC_PRESET  Effective() const { return m_effective; }

   string            EffectiveName() const
     {
      switch(m_effective)
        {
         case QSMC_PRESET_SCALPER:  return "SCALPER (M1-M5)";
         case QSMC_PRESET_INTRADAY: return "INTRADAY (M15-H1)";
         case QSMC_PRESET_SWING:    return "SWING (H4-D1)";
         case QSMC_PRESET_CUSTOM:   return "CUSTOM (user values only)";
         default:                   return "AUTO";
        }
      return "AUTO";
     }

   //------------------------------------------------------------------
   // Build the configuration for one evaluation.
   //------------------------------------------------------------------
   void              Build(SQsmcArbConfig &cfg,const ENUM_TIMEFRAMES tf)
     {
      cfg.enabled=InpArbEnabled;
      cfg.popup=InpArbPopup;
      cfg.push=InpArbPush;
      cfg.sound=InpArbSound;
      cfg.allow_countertrend=InpArbAllowCounterTrend;
      cfg.countertrend_min_score=(int)MathMax(0,MathMin(100,InpArbCounterTrendMinScore));
      cfg.countertrend_extra_evidence=(int)MathMax(0,MathMin(QEV_COUNT,InpArbCounterTrendExtraEv));
      cfg.w_d1=InpArbBiasW_D1; cfg.w_h4=InpArbBiasW_H4; cfg.w_h1=InpArbBiasW_H1;
      cfg.min_atr_points=MathMax(0.0,InpArbMinATRPoints);
      cfg.max_spread_points=(int)MathMax(0,InpArbMaxSpreadPoints);
      cfg.min_bars=(int)MathMax(30,InpArbMinBars);
      cfg.session_start_hour=InpArbSessionStartHour;
      cfg.session_end_hour=InpArbSessionEndHour;
      cfg.use_global_vars=InpArbUseGlobalVars;
      cfg.dedupe_ring=(int)MathMax(64,MathMin(4096,InpArbDedupeRing));
      cfg.retest_lookback_bars=(int)MathMax(4,InpArbRetestLookback);

      //--- preset defaults
      double p_zone_reach=1.50, p_merge=0.50, p_pen=0.35, p_break=0.30;
      int    p_strength=60, p_evidence=2, p_retest=24;
      double p_wick=0.50, p_vol=1.60, p_disp=0.50;
      double p_minrr=1.50, p_maxstop=4.00, p_slbuf=0.20;
      int    p_cooldown=10, p_flipflop=10;
      double p_mindist=0.50;

      Resolve(InpArbPreset,tf);
      switch(m_effective)
        {
         case QSMC_PRESET_SCALPER:
            p_zone_reach=1.20; p_merge=0.40; p_pen=0.25; p_break=0.20;
            p_strength=55; p_evidence=2; p_retest=16;
            p_wick=0.45; p_vol=1.40; p_disp=0.40;
            p_minrr=1.20; p_maxstop=3.00; p_slbuf=0.15;
            p_cooldown=20; p_mindist=0.35; p_flipflop=20;
            break;
         case QSMC_PRESET_INTRADAY:
            p_zone_reach=1.50; p_merge=0.50; p_pen=0.35; p_break=0.30;
            p_strength=60; p_evidence=2; p_retest=24;
            p_wick=0.50; p_vol=1.60; p_disp=0.50;
            p_minrr=1.50; p_maxstop=4.00; p_slbuf=0.20;
            p_cooldown=10; p_mindist=0.50; p_flipflop=10;
            break;
         case QSMC_PRESET_SWING:
            p_zone_reach=2.00; p_merge=0.75; p_pen=0.50; p_break=0.40;
            p_strength=65; p_evidence=3; p_retest=40;
            p_wick=0.55; p_vol=1.80; p_disp=0.60;
            p_minrr=2.00; p_maxstop=6.00; p_slbuf=0.30;
            p_cooldown=3;  p_mindist=1.00; p_flipflop=3;
            break;
         case QSMC_PRESET_CUSTOM:
            p_zone_reach=ARB_DEF_ZONE_REACH; p_merge=ARB_DEF_MERGE_TOL;
            p_pen=ARB_DEF_MAX_PEN; p_break=ARB_DEF_BREAK;
            p_strength=ARB_DEF_MIN_STRENGTH; p_evidence=ARB_DEF_MIN_EVIDENCE;
            p_retest=ARB_DEF_RETEST;
            p_wick=ARB_DEF_MIN_WICK; p_vol=ARB_DEF_VOL_MULT; p_disp=ARB_DEF_DISP;
            p_minrr=ARB_DEF_MIN_RR; p_maxstop=ARB_DEF_MAX_STOP; p_slbuf=ARB_DEF_SL_BUF;
            p_cooldown=ARB_DEF_COOLDOWN; p_mindist=ARB_DEF_MIN_DIST;
            p_flipflop=ARB_DEF_FLIPFLOP;
            break;
         default:
            break;
        }

      //--- explicit user override wins (non-default input => user value)
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbZoneReachATR,ARB_DEF_ZONE_REACH))
         p_zone_reach=MathMax(0.05,InpArbZoneReachATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMergeTolATR,ARB_DEF_MERGE_TOL))
         p_merge=MathMax(0.0,InpArbMergeTolATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMaxPenetrationATR,ARB_DEF_MAX_PEN))
         p_pen=MathMax(0.0,InpArbMaxPenetrationATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbBreakATR,ARB_DEF_BREAK))
         p_break=MathMax(0.0,InpArbBreakATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMinZoneStrength,ARB_DEF_MIN_STRENGTH))
         p_strength=(int)MathMax(0,MathMin(100,InpArbMinZoneStrength));
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMinEvidence,ARB_DEF_MIN_EVIDENCE))
         p_evidence=(int)MathMax(1,MathMin(QEV_COUNT,InpArbMinEvidence));
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbRetestLookback,ARB_DEF_RETEST))
         p_retest=(int)MathMax(4,InpArbRetestLookback);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMinWickRatio,ARB_DEF_MIN_WICK))
         p_wick=MathMax(0.0,MathMin(0.95,InpArbMinWickRatio));
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbVolumeMult,ARB_DEF_VOL_MULT))
         p_vol=MathMax(0.0,InpArbVolumeMult);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbDispATR,ARB_DEF_DISP))
         p_disp=MathMax(0.0,InpArbDispATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMinRR,ARB_DEF_MIN_RR))
         p_minrr=MathMax(0.1,InpArbMinRR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMaxStopATR,ARB_DEF_MAX_STOP))
         p_maxstop=MathMax(0.1,InpArbMaxStopATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbSLBufferATR,ARB_DEF_SL_BUF))
         p_slbuf=MathMax(0.0,InpArbSLBufferATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbCooldownBars,ARB_DEF_COOLDOWN))
         p_cooldown=(int)MathMax(0,InpArbCooldownBars);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbMinAlertDistanceATR,ARB_DEF_MIN_DIST))
         p_mindist=MathMax(0.0,InpArbMinAlertDistanceATR);
      if(m_effective==QSMC_PRESET_CUSTOM || !IsDefault(InpArbFlipFlopBars,ARB_DEF_FLIPFLOP))
         p_flipflop=(int)MathMax(0,InpArbFlipFlopBars);

      cfg.zone_reach_atr=p_zone_reach;
      cfg.merge_tol_atr=p_merge;
      cfg.max_penetration_atr=p_pen;
      cfg.break_atr=p_break;
      cfg.min_zone_strength=p_strength;
      cfg.min_evidence=p_evidence;
      cfg.retest_lookback_bars=p_retest;
      cfg.min_wick_ratio=p_wick;
      cfg.volume_mult=p_vol;
      cfg.displacement_atr=p_disp;
      cfg.min_rr=p_minrr;
      cfg.max_stop_atr=p_maxstop;
      cfg.sl_buffer_atr=p_slbuf;
      cfg.cooldown_bars=p_cooldown;
      cfg.min_alert_distance_atr=p_mindist;
      cfg.flipflop_bars=p_flipflop;
     }
  };

#endif
//+------------------------------------------------------------------+
