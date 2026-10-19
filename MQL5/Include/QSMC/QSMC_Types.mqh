//+------------------------------------------------------------------+
//|                                                  QSMC_Types.mqh  |
//|  Quantum SMC Intelligence Engine - Signal Arbitration subsystem   |
//|  v6.6.0                                                           |
//|                                                                   |
//|  PURPOSE                                                          |
//|  Plain-data types shared by every class of the arbitration layer. |
//|  Nothing in this file performs I/O, terminal calls, or logic.     |
//|                                                                   |
//|  MQL5 CONSTRAINTS OBSERVED (Phase 3 of the review brief)          |
//|  - No STL containers, no lambdas, no exceptions, no templates,    |
//|    no multiple inheritance, no operator overloading.              |
//|  - Structs are POD + string only. MQL5 does not allow arrays of   |
//|    class objects, therefore CZone is a POD struct (SQZone) owned   |
//|    by a class (CZoneRegistry) rather than an array of CZone.      |
//|    This is the one justified deviation from the proposed model.   |
//|  - No use of shift 0 for confirmed logic anywhere.                |
//+------------------------------------------------------------------+
#ifndef __QSMC_TYPES_MQH__
#define __QSMC_TYPES_MQH__

//--------------------------------------------------------------------
// Zone role. A role is a CAUSAL fact (birth-bar side); it is reversed
// only by a closed-bar break of the role edge followed by a retest.
//--------------------------------------------------------------------
enum ENUM_ZR_ROLE
  {
   ZR_SUPPORT    = 0,
   ZR_RESISTANCE = 1,
   ZR_NEUTRAL    = 2
  };

// Where the decision price sits relative to a zone band.
enum ENUM_ZR_LOC
  {
   ZLOC_NONE   = 0,
   ZLOC_BELOW  = 1,   // price < lo
   ZLOC_INSIDE = 2,   // lo <= price <= hi
   ZLOC_ABOVE  = 3    // price > hi
  };

enum ENUM_ZR_STATE
  {
   ZST_ACTIVE  = 0,
   ZST_TOUCHED = 1,   // a closed bar overlapped the band
   ZST_BROKEN  = 2,   // a closed bar closed beyond the ROLE edge
   ZST_FLIPPED = 3,   // broken AND retested -> role reversed
   ZST_EXPIRED = 4
  };

//--------------------------------------------------------------------
// Signal state. Terminology rule R7: SIG_CONFIRMED is reserved for a
// candidate that passed every gate (R1-R5). Everything else is
// WATCH / PREVIEW / TACTICAL-INFO / COUNTER-TREND / LIMITED-ROOM /
// NO-TRADE and must never be printed as "CONFIRMED".
//--------------------------------------------------------------------
enum ENUM_SIG_STATE
  {
   SIG_NONE           = 0,
   SIG_NO_TRADE       = 1,
   SIG_WATCH          = 2,
   SIG_PREVIEW        = 3,   // forming bar only, never alerted
   SIG_TACTICAL_INFO  = 4,
   SIG_COUNTER_TREND  = 5,
   SIG_LIMITED_ROOM   = 6,
   SIG_CONFIRMED      = 7
  };

enum ENUM_SIG_SOURCE
  {
   SRC_NONE     = 0,
   SRC_CORE     = 1,   // CalculateAITradeSetup / ManageSetupLifecycle
   SRC_ZRE      = 2,   // Zone Reaction Engine
   SRC_RXN      = 3,   // Reaction Signal Layer
   SRC_TACTICAL = 4    // fast MTF execution trigger (non-authoritative)
  };

// Independent evidence groups. Bit mask; >= InpArbMinEvidence required.
#define QEV_NONE         0
#define QEV_WICK         1    // rejection wick geometry
#define QEV_CANDLE       2    // rejection candle pattern (engulf/star/cloud)
#define QEV_VOLUME       4    // volume expansion on the reaction bar
#define QEV_DISPLACEMENT 8    // displacement away from the zone
#define QEV_SWEEP       16    // liquidity sweep beyond the edge + reclaim
#define QEV_MSS         32    // lower-timeframe market-structure shift
#define QEV_COUNT        6

enum ENUM_GATE_RESULT
  {
   GATE_PASS      = 0,
   GATE_FAIL      = 1,
   GATE_DOWNGRADE = 2   // allowed, but the state is demoted + reason recorded
  };

enum ENUM_VOL_REGIME
  {
   VREG_UNKNOWN = 0,
   VREG_DEAD    = 1,
   VREG_LOW     = 2,
   VREG_NORMAL  = 3,
   VREG_HIGH    = 4,
   VREG_EXTREME = 5
  };

#define QSMC_ARB_MAX_REASONS 8
#define QSMC_ARB_NAME_LEN    56

//--------------------------------------------------------------------
// One zone record. Fed by the existing ZRE zone list so there is
// exactly one zone source of truth in the indicator.
//--------------------------------------------------------------------
struct SQZone
  {
   string           id;             // deterministic: role|lo|hi (digits-rounded)
   double           lo;
   double           hi;
   ENUM_ZR_ROLE     role;           // causal role AFTER any confirmed flip
   ENUM_ZR_ROLE     birth_role;     // role at creation
   ENUM_ZR_STATE    state;
   int              strength;       // 0-100 evidence quality, NOT a win rate
   int              touches;        // closed-bar touch episodes
   int              birth_bar;      // -1 when the source carries no birth bar
   datetime         birth_time;
   bool             flipped;        // role reversed by a closed break + retest
   bool             broken_closed;  // a closed bar closed beyond the role edge
   datetime         broken_time;
   bool             retested;       // broken and price came back and held
   string           sources;        // '+' joined source tokens
   bool             valid;
  };

struct SQZoneHit
  {
   int              index;          // -1 when not found
   double           gap_atr;        // 0.0 when price is inside the band
   ENUM_ZR_LOC      loc;
  };

//--------------------------------------------------------------------
// Closed-bar reaction facts produced by CReactionDetector. Every field
// is derived from bars at index >= 1 (never from a forming bar).
//--------------------------------------------------------------------
struct SReactionFacts
  {
   bool             valid;
   bool             touched;              // bar range overlapped the band
   bool             penetration_bounded;  // penetration <= max_penetration_atr
   bool             closed_back;          // close returned to the rejection side
   bool             accepted;             // closed beyond the role edge = breakout
   bool             retest_held;          // breakout + a later closed retest holds
   int              dir;                  // +1 buy (at support), -1 sell (at resistance)
   int              evidence_mask;
   int              evidence_count;
   datetime         bar_time;
   double           penetration_atr;
   double           displacement_atr;
   string           missing;              // '+'-joined names of absent groups
   string           summary;              // one-line human readable evidence
  };

//--------------------------------------------------------------------
// Per-bar decision context. Built once per closed bar by the root.
//--------------------------------------------------------------------
struct SGateCtx
  {
   string           symbol;
   ENUM_TIMEFRAMES  tf;
   int              closed_index;      // index of the last CLOSED bar
   datetime         closed_time;       // open time of that closed bar
   int              bar_index;         // index of the bar the candidate cites
   datetime         bar_time;
   bool             bar_closed;        // false => forming bar (PREVIEW only)
   double           price;             // close of the decision bar
   double           atr;
   double           point;
   double           tick_size;
   int              digits;
   double           spread_points;
   bool             data_ready;        // every input series is COMPLETE
   string           data_reason;       // why not, when data_ready == false
   int              htf_bias;          // +1 / -1 / 0
   int              d1_bias;
   int              h4_bias;
   int              h1_bias;
   int              bias_score;        // signed weighted consensus, -100..+100
   ENUM_VOL_REGIME  regime;
   int              session_ok;        // 1 inside session, 0 outside, -1 disabled
  };

//--------------------------------------------------------------------
// One signal candidate. Every path (CORE / ZRE / RXN / tactical)
// submits this same record; nothing else reaches the alert sink.
//--------------------------------------------------------------------
struct SSignalCandidate
  {
   bool             valid;
   ENUM_SIG_SOURCE  source;
   int              dir;               // +1 buy, -1 sell
   int              score;             // 0-100 evidence quality
   int              state;             // ENUM_SIG_STATE
   bool             downgraded;
   string           zone_id;
   double           zone_lo;
   double           zone_hi;
   ENUM_ZR_ROLE     zone_role;
   int              zone_strength;
   double           entry;
   double           sl;                // invalidation
   double           tp1;
   double           tp2;
   double           tp3;
   double           rr;                // reward:risk to TP1
   double           room_atr;          // ATR of room to the opposing barrier
   double           distance_atr;      // ATR from the decision price to the zone
   datetime         bar_time;
   int              bar_index;
   bool             bar_closed;
   SReactionFacts   reaction;
   string           evidence_text;
   string           reason;            // why the state is what it is
   string           reject_text;       // '; '-joined gate failures, newest last
   int              reject_count;
   string           extra;             // path-specific provenance (tooltip only)
  };

struct SGateResult
  {
   string           name;
   ENUM_GATE_RESULT result;
   string           reason;
  };

//--------------------------------------------------------------------
// Configuration. Populated once per closed bar by CPresetManager from
// the preset enum + the user's explicit input overrides.
// Every field has a documented default; see QSMC_Preset.mqh.
//--------------------------------------------------------------------
struct SQsmcArbConfig
  {
   bool             enabled;
   bool             popup;
   bool             push;
   bool             sound;
   //--- location (R1)
   double           zone_reach_atr;      // beyond this: BETWEEN ZONES / NO TRADE
   double           merge_tol_atr;       // zone merge tolerance
   double           max_penetration_atr; // bounded penetration for a rejection
   double           break_atr;           // closed-bar break of the role edge
   int              min_zone_strength;
   int              min_evidence;
   int              retest_lookback_bars;
   //--- rejection geometry
   double           min_wick_ratio;
   double           volume_mult;
   double           displacement_atr;
   //--- bias (R2)
   int              w_d1;
   int              w_h4;
   int              w_h1;
   bool             allow_countertrend;
   int              countertrend_min_score;
   int              countertrend_extra_evidence;
   //--- room (R4)
   double           min_rr;
   double           max_stop_atr;
   double           sl_buffer_atr;
   //--- anti-spam (R5)
   int              cooldown_bars;
   double           min_alert_distance_atr;
   int              flipflop_bars;
   bool             use_global_vars;
   int              dedupe_ring;
   //--- data quality
   double           min_atr_points;      // dead-market floor, in points
   int              max_spread_points;   // 0 = no spread gate
   int              min_bars;
   //--- session
   int              session_start_hour;  // -1 = disabled
   int              session_end_hour;
  };

//--------------------------------------------------------------------
// Small helpers shared by the classes. Kept inline-static so no
// translation unit needs a forward declaration.
//--------------------------------------------------------------------
// Timeframe short name. Self-contained so the subsystem does not
// depend on the host indicator's TFName() (the Script harness has no
// access to it).
string QSMC_TFName(const ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M1:  return "M1";
      case PERIOD_M2:  return "M2";
      case PERIOD_M3:  return "M3";
      case PERIOD_M4:  return "M4";
      case PERIOD_M5:  return "M5";
      case PERIOD_M6:  return "M6";
      case PERIOD_M10: return "M10";
      case PERIOD_M12: return "M12";
      case PERIOD_M15: return "M15";
      case PERIOD_M20: return "M20";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H2:  return "H2";
      case PERIOD_H3:  return "H3";
      case PERIOD_H4:  return "H4";
      case PERIOD_H6:  return "H6";
      case PERIOD_H8:  return "H8";
      case PERIOD_H12: return "H12";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      case PERIOD_MN1: return "MN";
      default:         return "M"+IntegerToString(PeriodSeconds(tf)/60);
     }
   return "?";
  }

string QSMC_RoleName(const ENUM_ZR_ROLE r)
  {
   if(r==ZR_SUPPORT)    return "SUPPORT";
   if(r==ZR_RESISTANCE) return "RESISTANCE";
   return "NEUTRAL";
  }

string QSMC_StateName(const int s)
  {
   switch((ENUM_SIG_STATE)s)
     {
      case SIG_NO_TRADE:      return "NO TRADE";
      case SIG_WATCH:         return "WATCH";
      case SIG_PREVIEW:       return "PREVIEW";
      case SIG_TACTICAL_INFO: return "TACTICAL-INFO";
      case SIG_COUNTER_TREND: return "COUNTER-TREND / SCALP ONLY";
      case SIG_LIMITED_ROOM:  return "LIMITED ROOM";
      case SIG_CONFIRMED:     return "CONFIRMED";
      default:                return "NONE";
     }
   return "NONE";
  }

string QSMC_SourceName(const ENUM_SIG_SOURCE s)
  {
   switch(s)
     {
      case SRC_CORE:     return "CORE";
      case SRC_ZRE:      return "ZRE";
      case SRC_RXN:      return "RXN";
      case SRC_TACTICAL: return "MTF-TACTICAL";
      default:           return "NONE";
     }
   return "NONE";
  }

string QSMC_LocName(const ENUM_ZR_LOC l)
  {
   if(l==ZLOC_BELOW)  return "BELOW";
   if(l==ZLOC_INSIDE) return "INSIDE";
   if(l==ZLOC_ABOVE)  return "ABOVE";
   return "NONE";
  }

string QSMC_EvidenceName(const int bit)
  {
   if(bit==QEV_WICK)         return "wick";
   if(bit==QEV_CANDLE)       return "candle";
   if(bit==QEV_VOLUME)       return "volume";
   if(bit==QEV_DISPLACEMENT) return "displacement";
   if(bit==QEV_SWEEP)        return "sweep";
   if(bit==QEV_MSS)          return "ltf-MSS";
   return "";
  }

// Build a '+'-joined evidence list from a mask. Deterministic order.
string QSMC_EvidenceList(const int mask)
  {
   string out="";
   int bits[6];
   bits[0]=QEV_WICK; bits[1]=QEV_CANDLE; bits[2]=QEV_VOLUME;
   bits[3]=QEV_DISPLACEMENT; bits[4]=QEV_SWEEP; bits[5]=QEV_MSS;
   for(int i=0;i<6;i++)
     {
      if((mask & bits[i])==0) continue;
      out+=(out==""?"":"+")+QSMC_EvidenceName(bits[i]);
     }
   return (out==""?"none":out);
  }

int QSMC_EvidenceCount(const int mask)
  {
   int n=0;
   int bits[6];
   bits[0]=QEV_WICK; bits[1]=QEV_CANDLE; bits[2]=QEV_VOLUME;
   bits[3]=QEV_DISPLACEMENT; bits[4]=QEV_SWEEP; bits[5]=QEV_MSS;
   for(int i=0;i<6;i++)
      if((mask & bits[i])!=0) n++;
   return n;
  }

// Missing evidence groups as a human list (used in the alert "needs:" field).
string QSMC_MissingEvidence(const int mask)
  {
   string out="";
   int bits[6];
   bits[0]=QEV_WICK; bits[1]=QEV_CANDLE; bits[2]=QEV_VOLUME;
   bits[3]=QEV_DISPLACEMENT; bits[4]=QEV_SWEEP; bits[5]=QEV_MSS;
   for(int i=0;i<6;i++)
     {
      if((mask & bits[i])!=0) continue;
      out+=(out==""?"":"+")+QSMC_EvidenceName(bits[i]);
     }
   return (out==""?"none":out);
  }

#endif
//+------------------------------------------------------------------+
