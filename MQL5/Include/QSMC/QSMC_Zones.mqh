//+------------------------------------------------------------------+
//|                                                 QSMC_Zones.mqh   |
//|  CZoneRegistry - the single indexed zone store consumed by every  |
//|  gate. Zones are FED BY the existing Zone Reaction Engine (ZRE)   |
//|  so the indicator keeps ONE zone source of truth: ZRE detects and |
//|  scores them, this class indexes and queries them.                |
//|                                                                   |
//|  WHY SQZone IS A STRUCT, NOT A CLASS                               |
//|  MQL5 does not permit arrays of class objects. The brief's CZone  |
//|  is therefore a POD struct with the exact requested fields        |
//|  (id, lo/hi, role, sources, strength, touches, state, birth bar,  |
//|  flipped flag) and CZoneRegistry is the owning class that gives   |
//|  it identity, ordering and O(log N) lookup. Behaviour is          |
//|  identical; only the storage idiom differs.                       |
//|                                                                   |
//|  COMPLEXITY                                                       |
//|  Rebuild: O(N log N) (N <= 64).                                   |
//|  Nearest: O(log N + k) - binary search on the sorted midpoint     |
//|  index, then a bounded outward scan that stops as soon as the     |
//|  lower bound on the gap of the next candidate exceeds the best    |
//|  gap found. Worst case O(N) with N <= 64.                         |
//|  Find/At: O(log N) / O(1) after Rebuild.                          |
//+------------------------------------------------------------------+
#ifndef __QSMC_ZONES_MQH__
#define __QSMC_ZONES_MQH__

#include <QSMC/QSMC_Types.mqh>

#define QSMC_ZONE_MAX         64
#define QSMC_ZONE_ID_DIGITS   8

//+------------------------------------------------------------------+
class CZoneRegistry
  {
private:
   SQZone             m_zones[];      // merged, sorted by midpoint ascending
   int               m_mid_idx[];    // insertion-sorted index into m_zones
   int               m_count;
   double            m_merge_tol;    // absolute price tolerance used by Rebuild
   double            m_atr_used;
   int               m_digits;
   //--- provenance for the tooltip / audit
   int               m_src_count;
   int               m_merged_count;
   int               m_dropped_count;

   static double     Mid(const SQZone &z) { return (z.lo+z.hi)*0.5; }

   //--- Gap from a price to a band. 0.0 when the price is inside.
   static double     GapTo(const SQZone &z,const double price)
     { return MathMax(0.0, MathMax(z.lo-price, price-z.hi)); }

   static ENUM_ZR_LOC LocOf(const SQZone &z,const double price)
     {
      if(price<z.lo) return ZLOC_BELOW;
      if(price>z.hi) return ZLOC_ABOVE;
      return ZLOC_INSIDE;
     }

   static ENUM_ZR_ROLE OppositeRole(const ENUM_ZR_ROLE r)
     {
      if(r==ZR_SUPPORT)    return ZR_RESISTANCE;
      if(r==ZR_RESISTANCE) return ZR_SUPPORT;
      return ZR_NEUTRAL;
     }

   //--- Role is the CAUSAL birth role, reversed only by a confirmed flip.
   static ENUM_ZR_ROLE EffectiveRole(const SQZone &z)
     { return (z.flipped ? OppositeRole(z.birth_role) : z.birth_role); }

   //--- insertion sort on the midpoint; N <= 64 so no need for a heap.
   void              SortByMid()
     {
      ArrayResize(m_mid_idx,m_count);
      for(int i=0;i<m_count;i++) m_mid_idx[i]=i;
      for(int a=1;a<m_count;a++)
        {
         int key=m_mid_idx[a];
         double km=Mid(m_zones[key]);
         int b=a-1;
         while(b>=0 && Mid(m_zones[m_mid_idx[b]])>km)
           { m_mid_idx[b+1]=m_mid_idx[b]; b--; }
         m_mid_idx[b+1]=key;
        }
     }

   //--- Merge two zones of the SAME birth role. Roles are never mixed:
   //--- fusing a support with a resistance is exactly the role-inversion
   //--- bug class the review looked for and it is refused here.
   void              MergeInto(SQZone &dst,const SQZone &src)
     {
      if(src.lo<dst.lo) dst.lo=src.lo;
      if(src.hi>dst.hi) dst.hi=src.hi;
      if(src.strength>dst.strength) dst.strength=src.strength;
      dst.touches+=src.touches;
      if(dst.sources!="" && src.sources!="")
        {
         if(StringFind(dst.sources,src.sources)<0)
            dst.sources+="+"+src.sources;
        }
      else if(src.sources!="") dst.sources=src.sources;
      //--- birth = the OLDEST known origin; -1 (unknown) never wins.
      if(dst.birth_bar<0 || (src.birth_bar>=0 && src.birth_bar<dst.birth_bar))
        { dst.birth_bar=src.birth_bar; dst.birth_time=src.birth_time; }
      if(src.broken_closed)
        { dst.broken_closed=true; if(src.broken_time>dst.broken_time) dst.broken_time=src.broken_time; }
      if(src.flipped) dst.flipped=true;
      if(src.retested) dst.retested=true;
      //--- the most advanced lifecycle state wins
      if((int)src.state>(int)dst.state) dst.state=src.state;
      dst.role=EffectiveRole(dst);
      dst.valid=true;
     }

public:
                     CZoneRegistry()
     { m_count=0; m_merge_tol=0.0; m_atr_used=0.0; m_digits=_Digits;
       m_src_count=0; m_merged_count=0; m_dropped_count=0;
       ArrayResize(m_zones,0); ArrayResize(m_mid_idx,0); }

                    ~CZoneRegistry()
     { ArrayResize(m_zones,0); ArrayResize(m_mid_idx,0); m_count=0; }

   int               Count() const { return m_count; }
   double            MergeTol() const { return m_merge_tol; }
   int               SourceCount() const { return m_src_count; }
   int               MergedCount() const { return m_merged_count; }
   int               DroppedCount() const { return m_dropped_count; }

   void              Clear()
     { m_count=0; ArrayResize(m_zones,0); ArrayResize(m_mid_idx,0);
       m_src_count=0; m_merged_count=0; m_dropped_count=0; }

   //------------------------------------------------------------------
   // Rebuild from the ZRE zone list.
   // `src`        : zone candidates (ZRE published + recovered tail).
   // `atr`        : current ATR, used to express tol_atr in price units.
   // `tol_atr`    : merge tolerance in ATR.
   // `min_strength`: zones below this are kept in a hidden pool (they can
   //                 still block a trade) but never become a PRIMARY zone.
   // Returns the number of published zones.
   //------------------------------------------------------------------
   int               Rebuild(const SQZone &src[],const int n,const double atr,
                             const double tol_atr,const int min_strength)
     {
      Clear();
      if(n<=0 || !(atr>0.0)) return 0;
      m_atr_used=atr;
      m_digits=_Digits;
      m_merge_tol=MathMax(0.0,tol_atr)*atr;
      m_src_count=n;

      SQZone acc[];
      ArrayResize(acc,QSMC_ZONE_MAX);
      int acc_n=0;

      for(int i=0;i<n && i<ArraySize(src);i++)
        {
         SQZone z=src[i];
         //--- hard input validation: reject NaN / inverted / empty bands
         if(!z.valid) { m_dropped_count++; continue; }
         if(!MathIsValidNumber(z.lo) || !MathIsValidNumber(z.hi)) { m_dropped_count++; continue; }
         if(!(z.hi>=z.lo)) { m_dropped_count++; continue; }
         if(!(z.hi>0.0))   { m_dropped_count++; continue; }
         if(z.birth_role==ZR_NEUTRAL) { m_dropped_count++; continue; }
         if(acc_n>=QSMC_ZONE_MAX) { m_dropped_count++; continue; }

         z.role=EffectiveRole(z);

         //--- linear merge pass; N <= 64 so O(N^2) is bounded and exact.
         bool merged=false;
         for(int k=0;k<acc_n;k++)
           {
            if(acc[k].birth_role!=z.birth_role) continue;
            if(MathAbs(Mid(acc[k])-Mid(z))>m_merge_tol) continue;
            MergeInto(acc[k],z);
            merged=true;
            break;
           }
         if(merged) { m_merged_count++; continue; }
         acc[acc_n]=z; acc_n++;
        }

      if(acc_n<=0) return 0;
      ArrayResize(m_zones,acc_n);
      for(int i=0;i<acc_n;i++) m_zones[i]=acc[i];
      m_count=acc_n;
      SortByMid();
      return m_count;
     }

   //------------------------------------------------------------------
   // Nearest zone by GAP (0.0 when the price is inside the band).
   // Binary search on the sorted midpoint index, then a bounded outward
   // scan with a correct lower-bound early exit.
   //------------------------------------------------------------------
   bool              Nearest(const double price,SQZoneHit &hit) const
     {
      hit.index=-1; hit.gap_atr=0.0; hit.loc=ZLOC_NONE;
      if(m_count<=0 || m_atr_used<=0.0) return false;

      //--- 1) binary search: leftmost index whose midpoint >= price
      int lo=0, hi=m_count-1, pos=m_count;
      while(lo<=hi)
        {
         int mid=(lo+hi)/2;
         if(Mid(m_zones[m_mid_idx[mid]])>=price){ pos=mid; hi=mid-1; }
         else                                    lo=mid+1;
        }

      double best=DBL_MAX;
      int    best_i=-1;
      //--- 2) expand outward from the insertion point in both directions
      int left=pos-1, right=pos;
      for(int step=0; step<m_count; step++)
        {
         bool took=false;
         //--- alternate directions so the scan stays balanced
         if(left>=0)
           {
            int idx=m_mid_idx[left];
            double lb=MathMax(0.0, MathAbs(Mid(m_zones[idx])-price)
                                    - (m_zones[idx].hi-m_zones[idx].lo)*0.5);
            if(lb<=best)
              {
               double g=GapTo(m_zones[idx],price);
               if(g<best){ best=g; best_i=idx; }
               left--; took=true;
              }
            else left=-1;    // no zone further left can beat `best`
           }
         if(right<m_count)
           {
            int idx=m_mid_idx[right];
            double lb=MathMax(0.0, MathAbs(Mid(m_zones[idx])-price)
                                    - (m_zones[idx].hi-m_zones[idx].lo)*0.5);
            if(lb<=best)
              {
               double g=GapTo(m_zones[idx],price);
               if(g<best){ best=g; best_i=idx; }
               right++; took=true;
              }
            else right=m_count;
           }
         if(!took) break;
         if(left<0 && right>=m_count) break;
        }

      if(best_i<0) return false;
      hit.index=best_i;
      hit.gap_atr=best/m_atr_used;
      hit.loc=LocOf(m_zones[best_i],price);
      return true;
     }

   //------------------------------------------------------------------
   // Nearest OPPOSING barrier in the direction of travel. Used by the
   // room gate (R4) and by the "LIMITED ROOM" state.
   //------------------------------------------------------------------
   bool              NearestOpposing(const double price,const int dir,
                                     const double atr,SQZoneHit &hit) const
     {
      hit.index=-1; hit.gap_atr=0.0; hit.loc=ZLOC_NONE;
      if(m_count<=0 || !(atr>0.0) || dir==0) return false;
      double best=DBL_MAX;
      int    best_i=-1;
      for(int i=0;i<m_count;i++)
        {
         const SQZone z=m_zones[i];
         ENUM_ZR_ROLE role=EffectiveRole(z);
         bool opposing = (dir>0 ? role==ZR_RESISTANCE : role==ZR_SUPPORT);
         if(!opposing) continue;
         double dist;
         if(dir>0)
           {
            if(z.hi<price) continue;              // already behind us
            dist=(z.lo>price ? z.lo-price : 0.0);
           }
         else
           {
            if(z.lo>price) continue;
            dist=(z.hi<price ? price-z.hi : 0.0);
           }
         if(dist<best){ best=dist; best_i=i; }
        }
      if(best_i<0) return false;
      hit.index=best_i;
      hit.gap_atr=best/atr;
      hit.loc=LocOf(m_zones[best_i],price);
      return true;
     }

   //------------------------------------------------------------------
   bool              At(const int i,SQZone &out) const
     {
      if(i<0 || i>=m_count) return false;
      out=m_zones[i];
      out.role=EffectiveRole(out);
      return true;
     }

   bool              Find(const string id,SQZone &out) const
     {
      if(id=="" || m_count<=0) return false;
      for(int i=0;i<m_count;i++)
         if(m_zones[i].id==id){ out=m_zones[i]; out.role=EffectiveRole(out); return true; }
      return false;
     }

   ENUM_ZR_ROLE      RoleOf(const int i) const
     { return (i>=0 && i<m_count ? EffectiveRole(m_zones[i]) : ZR_NEUTRAL); }

   int               StrengthOf(const int i) const
     { return (i>=0 && i<m_count ? m_zones[i].strength : 0); }

   //--- Deterministic zone id. Role-aware: a support and a resistance at
   //--- the same prices can never collide.
   static string     MakeId(const ENUM_ZR_ROLE role,const double lo,const double hi)
     {
      return "Z|"+(role==ZR_SUPPORT?"S":(role==ZR_RESISTANCE?"R":"N"))+"|"+
             DoubleToString(lo,QSMC_ZONE_ID_DIGITS)+"|"+
             DoubleToString(hi,QSMC_ZONE_ID_DIGITS);
     }

   //--- One-line zone description used in every alert / tooltip.
   string            ZoneText(const int i) const
     {
      if(i<0 || i>=m_count) return "no zone";
      const SQZone z=m_zones[i];
      return QSMC_RoleName(EffectiveRole(z))+" "+
             DoubleToString(z.lo,_Digits)+"-"+DoubleToString(z.hi,_Digits)+
             " str "+IntegerToString(z.strength)+"/100"+
             " touch "+IntegerToString(z.touches)+
             (z.flipped?" FLIPPED":"")+
             (z.broken_closed?" BROKEN":"")+
             (z.retested?" RETESTED":"");
     }
  };

//====================================================================
// Shared trade geometry. Used by CQuantumRoot (production) and by
// QSMC_Selftest (offline) so the two can never drift apart.
//
//   dir      : +1 buy / -1 sell
//   entry    : the decision price
// Returns false when the zone cannot produce a valid risk.
// TP1 is placed at min_rr x risk and capped at the opposing barrier,
// so a candidate can never claim more room than the market has (R4).
//====================================================================
bool QSMC_BuildGeometry(const SQZone &z,const int dir,const double entry,
                        const double atr,const CZoneRegistry &zones,
                        const SQsmcArbConfig &cfg,const double tick,
                        double &sl,double &tp1,double &tp2,double &tp3,
                        double &rr,double &room_atr)
  {
   sl=0.0; tp1=0.0; tp2=0.0; tp3=0.0; rr=0.0; room_atr=-1.0;
   if(dir==0 || !(entry>0.0) || !(atr>0.0)) return false;
   double t=(tick>0.0?tick:_Point);
   double buf=cfg.sl_buffer_atr*atr;

   if(dir>0) sl=MathMin(z.lo,entry)-buf;
   else      sl=MathMax(z.hi,entry)+buf;
   if(!(sl>0.0)) return false;

   double risk=(dir>0 ? entry-sl : sl-entry);
   if(!(risk>0.0) || !MathIsValidNumber(risk)) return false;
   if(risk>cfg.max_stop_atr*atr) return false;

   SQZoneHit opp;
   double barrier=0.0;
   if(zones.NearestOpposing(entry,dir,atr,opp))
     {
      SQZone oz;
      if(zones.At(opp.index,oz)) barrier=(dir>0 ? oz.lo : oz.hi);
     }
   room_atr=(barrier>0.0 ? MathAbs(barrier-entry)/atr : -1.0);

   //--- TP1 is rounded AWAY from the entry so tick rounding can never
   //--- push RR below min_rr. (Nearest-tick rounding was observed to
   //--- produce RR = 1.4999 against a 1.50 floor, which the room gate
   //--- then correctly - but surprisingly - rejected.)
   //--- If the opposing barrier caps TP1, RR may legitimately fall
   //--- below min_rr; that is exactly the "LIMITED ROOM" case (R4).
   double t1=entry+(double)dir*risk*cfg.min_rr;
   bool capped=false;
   if(barrier>0.0)
     {
      if(dir>0 && t1>barrier) { t1=barrier; capped=true; }
      if(dir<0 && t1<barrier) { t1=barrier; capped=true; }
     }
   if(!capped)
     {
      if(dir>0) t1=MathCeil(t1/t)*t;
      else      t1=MathFloor(t1/t)*t;
     }
   else
      t1=MathRound(t1/t)*t;
   if(!(t1>0.0)) return false;

   sl=MathRound(sl/t)*t;
   double r2=(dir>0 ? entry-sl : sl-entry);
   if(!(r2>0.0)) return false;

   tp1=t1;
   tp2=(barrier>0.0 ? barrier : entry+(double)dir*r2*(cfg.min_rr+1.0));
   tp3=(barrier>0.0 ? barrier : entry+(double)dir*r2*(cfg.min_rr+2.0));
   rr=MathAbs(tp1-entry)/r2;
   return true;
  }

#endif
//+------------------------------------------------------------------+
