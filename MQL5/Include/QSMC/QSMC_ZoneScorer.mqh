//+------------------------------------------------------------------+
//|                                               QSMC_ZoneScore.mqh |
//| Hard validity gates + transparent, non-probabilistic zone rank.  |
//+------------------------------------------------------------------+
#ifndef __QSMC_ZONESCORE_MQH__
#define __QSMC_ZONESCORE_MQH__

#include <QSMC/QSMC_Types.mqh>

#define QZS_MISSING_HTF       1
#define QZS_MISSING_ROOM      2
#define QZS_MISSING_SPREAD    4
#define QZS_MISSING_FRESHNESS 8

struct SZoneScore
  {
   bool   valid;                // hard gates only
   int    total;                // 0..100 heuristic rank, never probability
   int    missing_mask;
   double htf_alignment;
   double structural_quality;
   double freshness;
   double distance;
   double available_room;
   double spread_condition;
   string rejection;
   string penalties;
   string breakdown;
  };

// Factors are intentionally limited to zone context. Reaction evidence
// (wick/candle/volume/sweep/displacement) remains in CReactionDetector and is
// not repeated here. The caller combines independent scores once, avoiding
// strength/reaction or sweep/displacement double-counting.
class CZoneScorer
  {
private:
   double m_max_distance_atr;
   double m_room_full_atr;
   double m_spread_bad_atr;
   int    m_min_strength;

   double Clip(const double x,const double lo,const double hi) const
     { return MathMax(lo,MathMin(hi,x)); }

public:
                     CZoneScorer()
     { m_max_distance_atr=2.5; m_room_full_atr=2.5; m_spread_bad_atr=0.15; m_min_strength=1; }

   bool              Configure(const double max_distance_atr,const double room_full_atr,
                               const double spread_bad_atr,const int min_strength)
     {
      if(!MathIsValidNumber(max_distance_atr) || max_distance_atr<=0.0 ||
         !MathIsValidNumber(room_full_atr) || room_full_atr<=0.0 ||
         !MathIsValidNumber(spread_bad_atr) || spread_bad_atr<=0.0 ||
         min_strength<0 || min_strength>100) return false;
      m_max_distance_atr=max_distance_atr; m_room_full_atr=room_full_atr;
      m_spread_bad_atr=spread_bad_atr; m_min_strength=min_strength;
      return true;
     }

   SZoneScore        Score(const SQZone &z,const int dir,const double price,
                           const double atr,const double distance_atr,
                           const double room_atr,const int htf_bias,
                           const double spread_atr) const
     {
      SZoneScore s;
      s.valid=false; s.total=0; s.missing_mask=0;
      s.htf_alignment=0.0; s.structural_quality=0.0; s.freshness=0.0;
      s.distance=0.0; s.available_room=0.0; s.spread_condition=0.0;
      s.rejection=""; s.penalties=""; s.breakdown="";
      if(!z.valid) s.rejection="zone invalid";
      else if(z.id=="") s.rejection="zone has no stable id";
      else if(!MathIsValidNumber(z.lo) || !MathIsValidNumber(z.hi) || z.hi<z.lo)
         s.rejection="zone boundaries malformed";
      else if(z.role==ZR_NEUTRAL || z.birth_role==ZR_NEUTRAL)
         s.rejection="neutral zone role";
      else if(z.state<ZST_ACTIVE || z.state>ZST_EXPIRED)
         s.rejection="zone lifecycle state malformed";
      else if(z.state==ZST_EXPIRED) s.rejection="zone expired";
      else if((z.broken_closed || z.state==ZST_BROKEN || z.state==ZST_FLIPPED) &&
              !(z.flipped && z.retested))
         s.rejection="closed-bar invalidation has no confirmed flip/retest";
      else if(dir==0 || (dir>0 && z.role!=ZR_SUPPORT) || (dir<0 && z.role!=ZR_RESISTANCE))
         s.rejection="zone role conflicts with candidate direction";
      else if(!(atr>0.0) || !MathIsValidNumber(atr) || !MathIsValidNumber(price))
         s.rejection="price/ATR data invalid";
      else if(!MathIsValidNumber(distance_atr) || distance_atr<0.0 || distance_atr>m_max_distance_atr)
         s.rejection="zone outside configured reach";
      else if(z.strength<m_min_strength)
         s.rejection="zone below minimum structural strength";
      if(s.rejection!="") return s;

      s.valid=true;
      // Weighted 100-point context model:
      // HTF alignment 12, structural quality 25, freshness 15,
      // proximity 20, room 15, spread 13. A missing feature contributes
      // zero and is named; it is never silently treated as confirmation.
      if(htf_bias==0) s.missing_mask|=QZS_MISSING_HTF;
      else s.htf_alignment=(htf_bias==dir ? 12.0 : -12.0);

      s.structural_quality=25.0*Clip((double)z.strength/100.0,0.0,1.0);
      if(z.touches<0) s.missing_mask|=QZS_MISSING_FRESHNESS;
      else if(z.touches<=1) s.freshness=15.0;
      else if(z.touches==2) s.freshness=11.0;
      else if(z.touches<=4) s.freshness=6.0;
      else
        {
         s.freshness=0.0;
         s.penalties+="repeated prior touches; ";
        }
      s.distance=20.0*Clip(1.0-distance_atr/m_max_distance_atr,0.0,1.0);
      if(room_atr<0.0 || !MathIsValidNumber(room_atr))
         s.missing_mask|=QZS_MISSING_ROOM;
      else
        {
         s.available_room=15.0*Clip(room_atr/m_room_full_atr,0.0,1.0);
         if(room_atr<0.5) s.penalties+="limited room to opposing barrier; ";
        }
      if(spread_atr<0.0 || !MathIsValidNumber(spread_atr))
         s.missing_mask|=QZS_MISSING_SPREAD;
      else
        {
         s.spread_condition=13.0*Clip(1.0-spread_atr/m_spread_bad_atr,0.0,1.0);
         if(spread_atr>=m_spread_bad_atr) s.penalties+="spread/ATR at penalty ceiling; ";
        }
      double total=s.htf_alignment+s.structural_quality+s.freshness+s.distance+
                   s.available_room+s.spread_condition;
      s.total=(int)MathRound(Clip(total,0.0,100.0));
      s.breakdown=StringFormat("zone=%d [HTF %.1f, structure %.1f, fresh %.1f, distance %.1f, room %.1f, spread %.1f]",
                               s.total,s.htf_alignment,s.structural_quality,s.freshness,
                               s.distance,s.available_room,s.spread_condition);
      if(s.missing_mask!=0) s.breakdown+=" missing=0x"+IntegerToString(s.missing_mask);
      return s;
     }
  };

#endif
