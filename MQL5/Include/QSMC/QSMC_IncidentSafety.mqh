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
#endif
