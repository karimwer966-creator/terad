//+------------------------------------------------------------------+
//|                                             QSMC_Renderer.mqh    |
//|  CChartRenderer - owns every chart object the arbitration layer   |
//|  creates. One naming prefix, one Clear(), no orphans.            |
//|                                                                   |
//|  It is deliberately self-contained (it calls ObjectCreate/Object- |
//|  SetString directly) so the subsystem can also be exercised from  |
//|  the Script harness, where the host indicator's label helpers do  |
//|  not exist.                                                       |
//|                                                                   |
//|  LABEL COLLISION: the renderer owns two stacked text slots and    |
//|  keeps them apart by an ATR-scaled vertical offset. It never      |
//|  deletes an object it did not create.                             |
//|                                                                   |
//|  COMPLEXITY: O(1) per draw; Clear() is O(objects) once per Deinit. |
//+------------------------------------------------------------------+
#ifndef __QSMC_RENDERER_MQH__
#define __QSMC_RENDERER_MQH__

#include <QSMC/QSMC_Types.mqh>

#define QSMC_ARB_PFX "QSMC_ARB_"

//+------------------------------------------------------------------+
class CChartRenderer
  {
private:
   long              m_chart;
   int               m_subwin;
   bool              m_enabled;
   int               m_created;
   int               m_deleted;

   void              Make(const string name,const ENUM_OBJECT type,
                          const datetime tm,const double price)
     {
      if(ObjectFind(m_chart,name)<0)
        {
         if(ObjectCreate(m_chart,name,type,m_subwin,tm,price)) m_created++;
        }
     }

public:
                     CChartRenderer()
     { m_chart=0; m_subwin=0; m_enabled=true; m_created=0; m_deleted=0; }

                    ~CChartRenderer() { Clear(); }

   int               Created() const { return m_created; }
   int               Deleted() const { return m_deleted; }

   void              Init(const long chart_id,const int subwin,const bool enabled)
     { m_chart=chart_id; m_subwin=subwin; m_enabled=enabled; }

   //--- Delete every object this class owns (prefix-scoped, never a
   //--- blanket ObjectsDeleteAll over the host's objects).
   int               Clear()
     {
      int n=0;
      int total=ObjectsTotal(m_chart,-1,-1);
      for(int i=total-1;i>=0;i--)
        {
         string nm=ObjectName(m_chart,i,-1,-1);
         if(StringFind(nm,QSMC_ARB_PFX)!=0) continue;
         if(ObjectDelete(m_chart,nm)) { n++; m_deleted++; }
        }
      return n;
     }

   //------------------------------------------------------------------
   // Draw the published primary signal: arrow + two stacked labels.
   //------------------------------------------------------------------
   void              DrawPrimary(const SSignalCandidate &c,const SGateCtx &ctx,
                                 const double atr)
     {
      if(!m_enabled) return;
      if(!c.valid || c.dir==0) return;
      if(c.bar_time<=0) return;

      double off=MathMax(4.0*ctx.point, atr*0.12);
      double y=(c.dir>0 ? c.entry-off*1.6 : c.entry+off*1.6);
      color  col=clrAqua;
      if(c.state==(int)SIG_CONFIRMED)     col=(c.dir>0?clrLime:clrTomato);
      if(c.state==(int)SIG_COUNTER_TREND) col=clrOrange;
      if(c.state==(int)SIG_TACTICAL_INFO) col=clrAqua;

      string ar=QSMC_ARB_PFX+"PRIMARY_ARROW";
      Make(ar,OBJ_ARROW,c.bar_time,y);
      ObjectMove(m_chart,ar,0,c.bar_time,y);
      ObjectSetInteger(m_chart,ar,OBJPROP_ARROWCODE,(c.dir>0?233:234));
      ObjectSetInteger(m_chart,ar,OBJPROP_COLOR,col);
      ObjectSetInteger(m_chart,ar,OBJPROP_WIDTH,2);
      ObjectSetInteger(m_chart,ar,OBJPROP_ANCHOR,(c.dir>0?ANCHOR_TOP:ANCHOR_BOTTOM));
      ObjectSetInteger(m_chart,ar,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(m_chart,ar,OBJPROP_HIDDEN,true);
      ObjectSetInteger(m_chart,ar,OBJPROP_BACK,false);

      string l1=QSMC_ARB_PFX+"PRIMARY_L1";
      string t1=QSMC_StateName(c.state)+" "+(c.dir>0?"BUY":"SELL")+" @ "+
                DoubleToString(c.entry,ctx.digits)+
                " | SL "+DoubleToString(c.sl,ctx.digits)+
                " | TP1 "+DoubleToString(c.tp1,ctx.digits)+
                " | RR "+DoubleToString(c.rr,2)+
                " | ev "+QSMC_EvidenceList(c.reaction.evidence_mask);
      Make(l1,OBJ_TEXT,c.bar_time,y);
      ObjectMove(m_chart,l1,0,c.bar_time,y);
      ObjectSetString(m_chart,l1,OBJPROP_TEXT,t1);
      ObjectSetString(m_chart,l1,OBJPROP_FONT,"Consolas");
      ObjectSetInteger(m_chart,l1,OBJPROP_FONTSIZE,8);
      ObjectSetInteger(m_chart,l1,OBJPROP_COLOR,col);
      ObjectSetInteger(m_chart,l1,OBJPROP_ANCHOR,(c.dir>0?ANCHOR_TOP:ANCHOR_BOTTOM));
      ObjectSetInteger(m_chart,l1,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(m_chart,l1,OBJPROP_HIDDEN,true);

      //--- second slot: WHY. R4 of the brief: the user must be able to
      //--- understand a signal without opening anything.
      string l2=QSMC_ARB_PFX+"PRIMARY_L2";
      double y2=(c.dir>0 ? y-off*0.55 : y+off*0.55);
      string t2="why: "+(c.reason!=""?c.reason:"all gates passed");
      if(c.reject_text!="") t2+=" | also blocked: "+c.reject_text;
      if(StringLen(t2)>180) t2=StringSubstr(t2,0,180);
      Make(l2,OBJ_TEXT,c.bar_time,y2);
      ObjectMove(m_chart,l2,0,c.bar_time,y2);
      ObjectSetString(m_chart,l2,OBJPROP_TEXT,t2);
      ObjectSetString(m_chart,l2,OBJPROP_FONT,"Consolas");
      ObjectSetInteger(m_chart,l2,OBJPROP_FONTSIZE,7);
      ObjectSetInteger(m_chart,l2,OBJPROP_COLOR,clrSilver);
      ObjectSetInteger(m_chart,l2,OBJPROP_ANCHOR,(c.dir>0?ANCHOR_TOP:ANCHOR_BOTTOM));
      ObjectSetInteger(m_chart,l2,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(m_chart,l2,OBJPROP_HIDDEN,true);
     }

   //------------------------------------------------------------------
   // Draw the last suppression so "nothing happened" is explainable.
   //------------------------------------------------------------------
   void              DrawSuppressed(const string text,const datetime tm,const double price,
                                    const double atr,const double point,const int digits)
     {
      if(!m_enabled) return;
      if(text=="") return;
      string nm=QSMC_ARB_PFX+"SUPPRESSED";
      double y=price+MathMax(6.0*point,atr*0.35);
      Make(nm,OBJ_TEXT,tm,y);
      ObjectMove(m_chart,nm,0,tm,y);
      string t="no signal: "+text;
      if(StringLen(t)>200) t=StringSubstr(t,0,200);
      ObjectSetString(m_chart,nm,OBJPROP_TEXT,t);
      ObjectSetString(m_chart,nm,OBJPROP_FONT,"Consolas");
      ObjectSetInteger(m_chart,nm,OBJPROP_FONTSIZE,7);
      ObjectSetInteger(m_chart,nm,OBJPROP_COLOR,clrDarkGray);
      ObjectSetInteger(m_chart,nm,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(m_chart,nm,OBJPROP_HIDDEN,true);
     }

   void              ClearPrimary()
     {
      string names[3];
      names[0]=QSMC_ARB_PFX+"PRIMARY_ARROW";
      names[1]=QSMC_ARB_PFX+"PRIMARY_L1";
      names[2]=QSMC_ARB_PFX+"PRIMARY_L2";
      for(int i=0;i<3;i++)
         if(ObjectFind(m_chart,names[i])>=0) { ObjectDelete(m_chart,names[i]); m_deleted++; }
     }
  };

#endif
//+------------------------------------------------------------------+
