//+------------------------------------------------------------------+
//|                                             QSMC_ChartLayers.mqh |
//|  AUDIT-CH2 - one visual hierarchy for every QSMC_ chart object.   |
//|                                                                   |
//|  WHY IT EXISTS                                                    |
//|  nadir2.mq5 owns about sixty object families behind forty-odd     |
//|  independent Show/Use switches, nearly all of them ON, and the    |
//|  display mode defaulted to FULL. The chart was drawn correctly    |
//|  and was unreadable. The draw primitives already pass through ONE |
//|  choke point - QSMC_DisplayAllowsObject() - but it only knew      |
//|  "MINIMAL or everything".                                         |
//|                                                                   |
//|  WHAT IT DOES                                                     |
//|  Every family is classified ONCE, by name, into a layer:          |
//|    PRIMARY   decision card, active setup, entry / SL / TP, the    |
//|              primary signal mark                                  |
//|    SECONDARY structure (BOS/CHoCH), liquidity, active OB/FVG,     |
//|              confluent S/R, PDH/PDL                               |
//|    VOLUME    POC / VAH / VAL lines and the HVN / LVN nodes        |
//|    VOLUME DETAIL  histogram, value-area box, naked POCs, legend   |
//|    OPTIONAL  previews, history, pivots, sessions, scenarios,      |
//|              research layers                                      |
//|    SYSTEM    the data-health banner (never hidden)                |
//|  InpChartProfile=CLEAN shows a layer only when its switch is on.  |
//|  InpChartProfile=LEGACY restores the previous behaviour exactly   |
//|  (InpDisplayMode and the individual switches decide).             |
//|                                                                   |
//|  DISPLAY ONLY. No buffer, no signal, no gate and no alert reads   |
//|  anything in this file. tools/test_qsmc_chart_hygiene.py asserts  |
//|  that every family nadir2.mq5 can create is classified here.      |
//+------------------------------------------------------------------+
#ifndef QSMC_CHART_LAYERS_MQH
#define QSMC_CHART_LAYERS_MQH

enum ENUM_QCL_PROFILE
{
   QCL_PROFILE_LEGACY = 0,   // Legacy: every layer, InpDisplayMode decides
   QCL_PROFILE_CLEAN  = 1    // Clean: layered professional chart
};

enum ENUM_QCL_LAYER
{
   QCL_LAYER_UNKNOWN       = 0,
   QCL_LAYER_PRIMARY       = 1,
   QCL_LAYER_SECONDARY     = 2,
   QCL_LAYER_VOLUME        = 3,
   QCL_LAYER_VOLUME_DETAIL = 4,
   QCL_LAYER_OPTIONAL      = 5,
   QCL_LAYER_SYSTEM        = 6
};

input group "====== v6.6.22 CHART PROFILE / VISUAL LAYERS (AUDIT-CH1/CH2, display only) ======"
input ENUM_QCL_PROFILE InpChartProfile         = QCL_PROFILE_CLEAN; // Chart profile (CLEAN = layered; LEGACY = previous behaviour)
input bool             InpLayerPrimary         = true;  // Primary: decision card, active setup, entry/SL/TP, primary signal
input bool             InpLayerSecondary       = true;  // Secondary: BOS/CHoCH, liquidity, active OB/FVG, S/R, PDH/PDL
input bool             InpLayerVolumeProfile   = true;  // Volume Profile: POC / VAH / VAL lines, HVN / LVN nodes
input bool             InpLayerVolumeDetail    = false; // Volume Profile detail: histogram, value-area box, naked POCs, legend
input bool             InpLayerOptional        = false; // Optional: previews, history, pivots, sessions, scenarios, research
input int              InpPrimaryMarkHistory   = 2;     // Previous primary-signal marks kept besides the current one (0-15)
input int              InpSignalEpisodeGapBars = 3;     // Closed bars without re-publication before the same zone is a NEW signal

bool QCL_ProfileActive()
{
   return (InpChartProfile==QCL_PROFILE_CLEAN);
}

string QCL_LayerName(const ENUM_QCL_LAYER layer)
{
   if(layer==QCL_LAYER_PRIMARY)       return "PRIMARY";
   if(layer==QCL_LAYER_SECONDARY)     return "SECONDARY";
   if(layer==QCL_LAYER_VOLUME)        return "VOLUME";
   if(layer==QCL_LAYER_VOLUME_DETAIL) return "VOLUME_DETAIL";
   if(layer==QCL_LAYER_OPTIONAL)      return "OPTIONAL";
   if(layer==QCL_LAYER_SYSTEM)        return "SYSTEM";
   return "UNKNOWN";
}

bool QCL_Starts(const string tail,const string family)
{
   return (StringFind(tail,family)==0);
}

// `tail` is the object name WITHOUT the "QSMC_" prefix. Longer families are
// tested before the families they begin with (ENTRY_PREVIEW before ENTRY).
ENUM_QCL_LAYER QCL_LayerOfTail(const string tail)
{
   if(tail=="") return QCL_LAYER_UNKNOWN;
   //--- system: must stay visible whatever the profile
   if(QCL_Starts(tail,"DH_BANNER")) return QCL_LAYER_SYSTEM;
   //--- optional families that begin like a primary / volume family
   if(QCL_Starts(tail,"ENTRY_PREVIEW") || QCL_Starts(tail,"ENTLVLPV")) return QCL_LAYER_OPTIONAL;
   //--- volume profile
   if(QCL_Starts(tail,"MVP_LEG") || QCL_Starts(tail,"MVP_H") || QCL_Starts(tail,"MVP_VA") ||
      QCL_Starts(tail,"MVP_NR") || QCL_Starts(tail,"MVP_NK"))
      return QCL_LAYER_VOLUME_DETAIL;
   if(QCL_Starts(tail,"MVP_L") || QCL_Starts(tail,"MVP_TG") || QCL_Starts(tail,"MVP_ND"))
      return QCL_LAYER_VOLUME;
   if(QCL_Starts(tail,"MVP_")) return QCL_LAYER_VOLUME_DETAIL;
   //--- primary: the decision, the active setup and its levels
   if(QCL_Starts(tail,"CORE_DASH_") || QCL_Starts(tail,"CORE_CURRENT_STATE") ||
      QCL_Starts(tail,"PRIMARY_") || QCL_Starts(tail,"SETUPZONE") ||
      QCL_Starts(tail,"TRADEBOX") || QCL_Starts(tail,"TRADE_BOX_BG") || QCL_Starts(tail,"TBOX_") ||
      QCL_Starts(tail,"TL_") || QCL_Starts(tail,"ENTLVL_") || QCL_Starts(tail,"EMARK_") ||
      QCL_Starts(tail,"ENTRY") || tail=="SL" || tail=="TP1" || tail=="TP2" || tail=="TP3")
      return QCL_LAYER_PRIMARY;
   //--- secondary: structure, liquidity, active zones, key levels
   if(QCL_Starts(tail,"STRUCT_") || QCL_Starts(tail,"STR_") || QCL_Starts(tail,"OB_") ||
      QCL_Starts(tail,"BRK_") || QCL_Starts(tail,"FVG") || QCL_Starts(tail,"LIQ_") ||
      QCL_Starts(tail,"ZONE_") || QCL_Starts(tail,"ZN_") || QCL_Starts(tail,"SR_") ||
      tail=="PDH" || tail=="PDL")
      return QCL_LAYER_SECONDARY;
   //--- optional: previews, history, session furniture, scenarios, research
   if(QCL_Starts(tail,"BATTLE_") || QCL_Starts(tail,"CAM_") || QCL_Starts(tail,"PIV_") ||
      QCL_Starts(tail,"KZ_") || QCL_Starts(tail,"SESSH_") || QCL_Starts(tail,"SESSL_") ||
      QCL_Starts(tail,"PD_") || QCL_Starts(tail,"PREM") || QCL_Starts(tail,"DISC") ||
      QCL_Starts(tail,"OTE") || QCL_Starts(tail,"FIB_") || QCL_Starts(tail,"PROVH_") ||
      QCL_Starts(tail,"PROVL_") || QCL_Starts(tail,"EARLYBREAK") || QCL_Starts(tail,"MTF_ENTRY") ||
      QCL_Starts(tail,"MTF_MARK") || QCL_Starts(tail,"JUDAS") || QCL_Starts(tail,"RXN_") ||
      QCL_Starts(tail,"ZRE_") || QCL_Starts(tail,"SCN_") || QCL_Starts(tail,"SNIPER_") ||
      QCL_Starts(tail,"SCALE_") || QCL_Starts(tail,"SBP3_") || QCL_Starts(tail,"WY_") ||
      QCL_Starts(tail,"PMI_") || QCL_Starts(tail,"PFR_") || QCL_Starts(tail,"CONNECT"))
      return QCL_LAYER_OPTIONAL;
   return QCL_LAYER_UNKNOWN;
}

ENUM_QCL_LAYER QCL_LayerOf(const string name,const string prefix)
{
   int plen=StringLen(prefix);
   if(plen<=0 || StringFind(name,prefix)!=0) return QCL_LAYER_UNKNOWN;
   return QCL_LayerOfTail(StringSubstr(name,plen));
}

// Pure policy (no input read): which layers a set of switches lets through. An
// unclassified family is treated as OPTIONAL, so a family added later is hidden
// by the clean profile until somebody decides where it belongs.
bool QCL_LayerVisible(const ENUM_QCL_LAYER layer,const bool primary,const bool secondary,
                      const bool volume,const bool volume_detail,const bool optional)
{
   if(layer==QCL_LAYER_SYSTEM)        return true;
   if(layer==QCL_LAYER_PRIMARY)       return primary;
   if(layer==QCL_LAYER_SECONDARY)     return secondary;
   if(layer==QCL_LAYER_VOLUME)        return volume;
   if(layer==QCL_LAYER_VOLUME_DETAIL) return (volume && volume_detail);
   return optional;
}

bool QCL_LayerEnabled(const ENUM_QCL_LAYER layer)
{
   return QCL_LayerVisible(layer,InpLayerPrimary,InpLayerSecondary,InpLayerVolumeProfile,
                           InpLayerVolumeDetail,InpLayerOptional);
}

// The single question QSMC_DisplayAllowsObject() asks while the clean profile is on.
bool QCL_AllowsName(const string name,const string prefix)
{
   return QCL_LayerEnabled(QCL_LayerOf(name,prefix));
}

// How many primary-signal marks may stay on the chart (the current one included).
int QCL_PrimaryMarkKeep(const int limit)
{
   if(limit<=1) return 1;
   if(!QCL_ProfileActive()) return limit;
   int history=InpPrimaryMarkHistory;
   if(history<0) history=0;
   if(history>limit-1) history=limit-1;
   return 1+history;
}

// A scenario that is not re-published for longer than this ends its episode.
int QCL_EpisodeIdleSeconds(const int period_seconds)
{
   int bars=InpSignalEpisodeGapBars;
   if(bars<1) bars=1;
   if(bars>500) bars=500;
   int sec=period_seconds;
   if(sec<60) sec=60;
   return bars*sec;
}

bool QCL_SelfTest(string &where)
{
   where="";
   if(QCL_LayerOfTail("PRIMARY_1731312000_ARROW")!=QCL_LAYER_PRIMARY) where="QCL-1 primary mark";
   else if(QCL_LayerOfTail("ENTRY_PREVIEW")!=QCL_LAYER_OPTIONAL) where="QCL-2 a preview is not the entry";
   else if(QCL_LayerOfTail("ENTRY_ARROW")!=QCL_LAYER_PRIMARY) where="QCL-3 entry arrow";
   else if(QCL_LayerOfTail("MVP_L0P")!=QCL_LAYER_VOLUME) where="QCL-4 POC line";
   else if(QCL_LayerOfTail("MVP_LEG")!=QCL_LAYER_VOLUME_DETAIL) where="QCL-5 the legend is detail";
   else if(QCL_LayerOfTail("MVP_H0T12")!=QCL_LAYER_VOLUME_DETAIL) where="QCL-6 histogram row";
   else if(QCL_LayerOfTail("STRUCT_120_BOS")!=QCL_LAYER_SECONDARY) where="QCL-7 structure";
   else if(QCL_LayerOfTail("PD_PREM_LINE")!=QCL_LAYER_OPTIONAL) where="QCL-8 premium/discount";
   else if(QCL_LayerOfTail("PDH")!=QCL_LAYER_SECONDARY) where="QCL-9 PDH is liquidity";
   else if(QCL_LayerOfTail("DH_BANNER")!=QCL_LAYER_SYSTEM) where="QCL-10 data health";
   else if(QCL_LayerOfTail("SOMETHING_NEW")!=QCL_LAYER_UNKNOWN) where="QCL-11 unknown stays unknown";
   else if(QCL_LayerOf("USER_LINE","QSMC_")!=QCL_LAYER_UNKNOWN) where="QCL-12 a foreign name has no layer";
   else if(!QCL_LayerVisible(QCL_LAYER_SYSTEM,false,false,false,false,false)) where="QCL-13 system is never hidden";
   else if(QCL_LayerVisible(QCL_LAYER_UNKNOWN,true,true,true,true,false)) where="QCL-14 unknown follows optional";
   else if(QCL_LayerVisible(QCL_LAYER_VOLUME_DETAIL,true,true,false,true,true)) where="QCL-15 detail needs the volume layer";
   return (where=="");
}

#endif
//+------------------------------------------------------------------+
