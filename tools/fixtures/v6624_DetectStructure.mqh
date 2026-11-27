// FROZEN COPY of DetectStructure() from nadir2.mq5 v6.6.24 (commit 4bba08e).
// Reference for tools/test_missed_trade_fixes_native.py: with every v6.6.25
// switch OFF the live function must reproduce this one bar for bar. Do not edit.
void DetectStructure(const int total,const double &o[],const double &h[],const double &l[],const double &c[],const datetime &t[],const bool incremental=false)
{
   int n=MathMax(1,InpSwingFractalN);
   int closed=total-2;
   if(closed<2*n+1) return;

   if(!incremental)
   {
      g_struct_last_high=0.0;
      g_struct_last_low=0.0;
      g_struct_trend=0;
      g_struct_last_processed_bar=-1;
      g_struct_last_break_bar=-1;
      ArrayResize(g_structures,0,32);
   }

   int start=MathMax(g_struct_last_processed_bar+1,n);
   bool seeded=false;
   for(int b=start;b<=closed;b++)
   {
      // 1) register newly confirmed fractals with LEFT edge at b-n
      int f=b-n;
      if(f-n>=0)
      {
         bool is_high=true,is_low=true;
         for(int k=f-n;k<=f+n;k++)
         {
            if(k==f) continue;
            if(k<0 || k>=total) {is_high=false; is_low=false; break;}
            if(k<f && h[k]>h[f]) is_high=false;
            if(k>f && h[k]>=h[f]) is_high=false;
            if(k<f && l[k]<l[f]) is_low=false;
            if(k>f && l[k]<=l[f]) is_low=false;
         }
         if(is_high && (g_struct_last_high<=0.0 || h[f]!=g_struct_last_high))
            g_struct_last_high=h[f];
         if(is_low && (g_struct_last_low<=0.0 || l[f]!=g_struct_last_low))
            g_struct_last_low=l[f];
      }

      // 2) first seeding pass establishes a baseline without events
      if(!seeded && g_struct_last_high>0.0 && g_struct_last_low>0.0 &&
         g_struct_trend==0 && g_struct_last_break_bar<0)
      {
         seeded=true;
         if(ArraySize(g_structures)==0)
         {
            SStructureBreak init;
            init.bar=b; init.time=t[b];
            init.price=(MathAbs(c[b]-g_struct_last_high)<MathAbs(c[b]-g_struct_last_low) ?
                        g_struct_last_high : g_struct_last_low);
            init.bullish=(c[b]>init.price);
            init.type="INIT";
            init.ob_bar=-1; init.strength=1; init.priority=0;
            int idx=ArraySize(g_structures);
            ArrayResize(g_structures,idx+1,32);
            g_structures[idx]=init;
            g_struct_trend=(c[b]>init.price ? 1 : -1);
         }
      }

      // 3) close-based break detection
      if(g_struct_last_high>0.0 && c[b]>g_struct_last_high)
      {
         bool with_trend=(g_struct_trend>=0);
         bool displacement=false;
         double body=MathAbs(c[b]-o[b]);
         double atr=(b<ArraySize(g_atr_buf) && g_atr_buf[b]>0.0) ? g_atr_buf[b] : g_atr;
         if(atr>0.0 && body>=atr*InpDisplacementATR) displacement=true;
         SStructureBreak br;
         br.bar=b; br.time=t[b]; br.price=g_struct_last_high;
         br.bullish=true;
         if(with_trend) br.type="BOS";
         else br.type=(displacement ? "MSS" : "CHoCH");
         br.ob_bar=b; br.strength=(br.type=="MSS"?5:(br.type=="BOS"?4:3));
         br.priority=(br.type=="MSS"?5:(br.type=="BOS"?4:3));
         int idx=ArraySize(g_structures);
         ArrayResize(g_structures,idx+1,32);
         g_structures[idx]=br;
         g_struct_trend=1;
         g_struct_last_break_bar=b;
         g_struct_last_high=0.0; // consumed; next confirmed fractal re-arms
         if(InpLogLifecycleTransitions)
            LogLifecycle(StringFormat("STRUCT %s bull @ %s",br.type,TimeToString(t[b])));
      }
      else if(g_struct_last_low>0.0 && c[b]<g_struct_last_low)
      {
         bool with_trend=(g_struct_trend<=0);
         bool displacement=false;
         double body=MathAbs(c[b]-o[b]);
         double atr=(b<ArraySize(g_atr_buf) && g_atr_buf[b]>0.0) ? g_atr_buf[b] : g_atr;
         if(atr>0.0 && body>=atr*InpDisplacementATR) displacement=true;
         SStructureBreak br;
         br.bar=b; br.time=t[b]; br.price=g_struct_last_low;
         br.bullish=false;
         if(with_trend) br.type="BOS";
         else br.type=(displacement ? "MSS" : "CHoCH");
         br.ob_bar=b; br.strength=(br.type=="MSS"?5:(br.type=="BOS"?4:3));
         br.priority=(br.type=="MSS"?5:(br.type=="BOS"?4:3));
         int idx=ArraySize(g_structures);
         ArrayResize(g_structures,idx+1,32);
         g_structures[idx]=br;
         g_struct_trend=-1;
         g_struct_last_break_bar=b;
         g_struct_last_low=0.0;
         if(InpLogLifecycleTransitions)
            LogLifecycle(StringFormat("STRUCT %s bear @ %s",br.type,TimeToString(t[b])));
      }
      g_struct_last_processed_bar=b;
   }

   // deterministic contradictory-break suppression: the state machine cannot
   // emit both directions on one bar, but if it ever did, keep the last.
   int ns=ArraySize(g_structures);
   if(ns>=2 && g_structures[ns-1].bar==g_structures[ns-2].bar &&
      g_structures[ns-1].bullish!=g_structures[ns-2].bullish)
   {
      for(int i=ns-2;i<ns-1;i++) g_structures[i]=g_structures[i+1];
      ArrayResize(g_structures,ns-1,32);
      ns--;
   }
   // chronological cap: drop the OLDEST entries beyond the limit
   if(ns>InpMaxStructuresKeep)
   {
      int excess=ns-InpMaxStructuresKeep;
      for(int i=0;i<ns-excess;i++)
         g_structures[i]=g_structures[i+excess];
      ArrayResize(g_structures,InpMaxStructuresKeep,32);
   }
}
