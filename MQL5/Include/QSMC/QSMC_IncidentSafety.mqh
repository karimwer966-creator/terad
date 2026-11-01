#ifndef QSMC_INCIDENT_SAFETY_MQH
#define QSMC_INCIDENT_SAFETY_MQH
// Appended after existing Inputs: no positional iCustom argument is shifted.
input double InpZoneMaxDistanceATR = 12.0;
input int InpZoneLifetimeBars = 120;

void QA_FilterCandidates(SZRECand &cands[],const SZREContext &ctx)
{
   double low=DBL_MAX,high=0;
   if(ctx.closed>=ArraySize(g_buf_h) || ctx.closed>=ArraySize(g_buf_l) || ctx.closed>=ArraySize(g_buf_t)) { ArrayResize(cands,0); return; }
   for(int b=0;b<=ctx.closed;b++)
   {
      if(!MathIsValidNumber(g_buf_l[b]) || !MathIsValidNumber(g_buf_h[b]) || g_buf_l[b]<=0 || g_buf_h[b]<g_buf_l[b]) { ArrayResize(cands,0); return; }
      low=MathMin(low,g_buf_l[b]); high=MathMax(high,g_buf_h[b]);
   }
   double distance=(MathIsValidNumber(InpZoneMaxDistanceATR) && InpZoneMaxDistanceATR>=1.0?InpZoneMaxDistanceATR:12.0);
   int lifetime=(InpZoneLifetimeBars>0?InpZoneLifetimeBars:120);
   int keep=0;
   for(int i=0;i<ArraySize(cands);i++)
   {
      int born=cands[i].born_bar;
      int age=(born>=0 && born<=ctx.closed?ctx.closed-born:-1);
      string why=QSMC_ZoneRangeReason(cands[i].lo,cands[i].hi,ctx.close_px,low,high,ctx.atr,age,lifetime,distance);
      if(why!="")
      {
         if(UD_LogAllows("ZONE_REJECT|"+cands[i].tokens+"|"+why))
            Print("[QSMC_ZONE_REJECT] symbol=",_Symbol," tf=",EnumToString((ENUM_TIMEFRAMES)_Period),
                  " source=",cands[i].tokens," created=",(born>=0 && born<=ctx.closed?TimeToString(g_buf_t[born]):"unknown"),
                  " lo=",cands[i].lo," hi=",cands[i].hi," closed=",ctx.close_px," history=",low,"..",high,
                  " ATR=",ctx.atr," point=",_Point," digits=",_Digits," scale=raw-price reason=",why);
         continue;
      }
      cands[keep++]=cands[i];
   }
   ArrayResize(cands,keep);
}
input double InpAdvisoryLabelMaxDistanceATR = 3.0; // display expiry only, not an entry gate
input int InpAdvisoryLabelLifetimeBars = 12;

struct SQA_CoreDisplay
{
   datetime bar;
   int direction;
   string reason;
};
SQA_CoreDisplay g_qa_core;

void QA_CoreDisplayRefresh(const int closed)
{
   g_qa_core.bar=0; g_qa_core.direction=0; g_qa_core.reason="no published Core buffer on this close";
   if(closed<0 || closed>=g_rates_total-1 || closed>=ArraySize(g_buf_t) ||
      closed>=ArraySize(BufSigCoreDir)) return;
   g_qa_core.bar=g_buf_t[closed];
   double d=BufSigCoreDir[closed];
   if(d!=1.0 && d!=-1.0) return;
   g_qa_core.direction=(int)d;
   g_qa_core.reason="published Core buffer 7; closed bar "+TimeToString(g_qa_core.bar);
}

string QA_CoreStatus()
{
   return (g_qa_core.direction==1?"BUY":(g_qa_core.direction==-1?"SELL":"WAIT"));
}

void QA_DrawCoreStatus()
{
   string name=PFX+"CORE_CURRENT_STATE";
   if(ObjectFind(0,name)<0 && !ObjectCreate(0,name,OBJ_LABEL,0,0,0)) return;
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_LOWER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,12); ObjectSetInteger(0,name,OBJPROP_YDISTANCE,30);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,name,OBJPROP_COLOR,(g_qa_core.direction==0?clrSilver:clrGold));
   ObjectSetString(0,name,OBJPROP_TEXT,"CORE "+QA_CoreStatus()+(g_qa_core.direction!=0?" ENTRY CONFIRMED":" - no current entry"));
   ObjectSetString(0,name,OBJPROP_TOOLTIP,g_qa_core.reason);
}

bool QA_LabelAlive(const double lo,const double hi,const datetime born,const bool invalid)
{
   if(invalid || born<=0 || lo<=0 || hi<lo) return false;
   int closed=g_rates_total-2;
   if(closed<0 || closed>=ArraySize(g_buf_c) || closed>=ArraySize(g_atr_buf)) return false;
   double atr=g_atr_buf[closed],price=g_buf_c[closed];
   if(!MathIsValidNumber(atr) || atr<=0 || atr==EMPTY_VALUE || price<=0) return false;
   int shift=iBarShift(_Symbol,(ENUM_TIMEFRAMES)_Period,born,false);
   int lifetime=(InpAdvisoryLabelLifetimeBars>0?InpAdvisoryLabelLifetimeBars:12);
   double distance=(MathIsValidNumber(InpAdvisoryLabelMaxDistanceATR) && InpAdvisoryLabelMaxDistanceATR>0?InpAdvisoryLabelMaxDistanceATR:3.0);
   if(shift<1 || shift-1>lifetime) return false;
   return MathMax(0.0,MathMax(lo-price,price-hi))<=distance*atr;
}

void QA_ClearTacticalPaint()
{
   ObjectDelete(0,PFX+"MTF_ENTRY"); ObjectDelete(0,PFX+"MTF_ENTRY_TX");
   EntryMarkClearTactical(); // only visual buffers, never Core 7..12
}

#endif
