#ifndef QSMC_LIQUIDITY_VALUE_MQH
#define QSMC_LIQUIDITY_VALUE_MQH
// Inputs live here to preserve the host's audited source-line citations.
#ifndef QSMC_LV_NATIVE_TEST
input group "====== Liquidity + Value (monitor only) ======"
input bool InpEnableLiquidityValue = false; // requires Master VP, no entry authority
input bool InpLVJournal = false; // each closed-bar observation in Experts log
#endif
// Observational only. No signal buffers, arbiter writes, alerts or trade API.
// Snapshot from the preceding closed bar, never the sweep bar's profile.
datetime g_lv_last=0;
bool g_lv_profile=false;
double g_lv_val=0,g_lv_vah=0,g_lv_poc=0;
int g_lv_phase=0,g_lv_dir=0,g_lv_age=0;
double g_lv_edge=0,g_lv_target=0,g_lv_extreme=0,g_lv_trigger=0,g_lv_atr=0;
string g_lv_status="WARMUP";
bool g_lv_visible=false;

bool LV_PriceOK(const double value)
{
   return MathIsValidNumber(value) && value!=EMPTY_VALUE && value>0.0;
}

bool LV_ProfileOK(const int a)
{
   return a>=0 && a<g_mvp_count && a<ArraySize(g_mvp) && g_mvp[a].valid &&
      LV_PriceOK(g_mvp[a].val) && LV_PriceOK(g_mvp[a].poc) &&
      LV_PriceOK(g_mvp[a].vah) && g_mvp[a].val<g_mvp[a].poc && g_mvp[a].poc<g_mvp[a].vah;
}

void LV_Hide()
{
   if(g_lv_visible) ObjectDelete(0,PFX+"LV_STATUS");
   g_lv_visible=false;
}

void LV_ClearSetup(const string reason)
{
   g_lv_phase=0; g_lv_dir=0; g_lv_age=0; g_lv_status=reason;
   g_lv_edge=0; g_lv_target=0; g_lv_extreme=0; g_lv_trigger=0; g_lv_atr=0;
}

void LV_Publish()
{
   string name=PFX+"LV_STATUS";
   if(ObjectFind(0,name)<0 && !ObjectCreate(0,name,OBJ_LABEL,0,0,0)) return;
   g_lv_visible=true;
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_LOWER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,12);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,65);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrSilver);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetString(0,name,OBJPROP_TEXT,"Liquidity + Value [MONITOR]: "+g_lv_status);
   ObjectSetString(0,name,OBJPROP_TOOLTIP,
      "Closed bars only. Frozen pre-sweep value area. Confirmation = break of sweep candle, not a full MSS. No order.");
   if(InpLVJournal && InpArbVerboseLog) Print("LV_MONITOR | ",TimeToString(g_lv_last)," | ",g_lv_status);
}

void LV_Update(const int closed,const bool reset)
{
   if(reset)
   {
      g_lv_last=0; g_lv_profile=false; LV_ClearSetup("WARMUP");
   }
   if(!InpEnableLiquidityValue)
   {
      LV_Hide();
      g_lv_last=0; g_lv_profile=false; LV_ClearSetup("DISABLED"); return;
   }
   if(closed<2 || closed>=g_rates_total-1 || closed>=ArraySize(g_buf_t) || closed>=ArraySize(g_buf_c) ||
      closed>=ArraySize(g_buf_o) || closed>=ArraySize(g_buf_h) || closed>=ArraySize(g_buf_l))
   {
      g_lv_profile=false; LV_ClearSetup("DATA UNAVAILABLE / BAR BOUNDS");
      LV_Hide(); return;
   }
   datetime now=g_buf_t[closed];
   if(now==g_lv_last) return;
   // A skipped bar/history refresh must not carry a setup across unseen candles.
   if(g_lv_last!=0 && g_lv_last!=g_buf_t[closed-1])
   { g_lv_profile=false; LV_ClearSetup("WARMUP / HISTORY GAP"); }
   g_lv_last=now;
   double c=g_buf_c[closed],h=g_buf_h[closed],l=g_buf_l[closed];
   // PMI_ATRAt reads the whole trailing window: validate every input first.
   int period=(int)MathMax(2,InpATRPeriod);
   bool bars_ok=(closed>=period);
   int first=(int)MathMax(1,closed-period+1);
   for(int b=first;b<=closed && bars_ok;b++)
      bars_ok=LV_PriceOK(g_buf_o[b]) && LV_PriceOK(g_buf_h[b]) &&
         LV_PriceOK(g_buf_l[b]) && LV_PriceOK(g_buf_c[b]) && LV_PriceOK(g_buf_c[b-1]) &&
         g_buf_h[b]>=MathMax(g_buf_o[b],g_buf_c[b]) &&
         g_buf_l[b]<=MathMin(g_buf_o[b],g_buf_c[b]) && g_buf_h[b]>=g_buf_l[b];
   double atr=(bars_ok?PMI_ATRAt(closed,InpATRPeriod):0.0);
   bool feed=InpUseMasterVolumeProfile && LV_PriceOK(atr) &&
      LV_PriceOK(InpTopDownMinRR) && g_mvp_built_time==now && LV_ProfileOK(g_mvp_active);
   if(!feed) { g_lv_profile=false; LV_ClearSetup("DATA UNAVAILABLE / ENABLE MASTER VP"); }
   else if(g_lv_phase>0)
   {
      g_lv_age++;
      double stop=g_lv_extreme-g_lv_dir*0.15*g_lv_atr;
      if((g_lv_dir>0 ? l<=stop : h>=stop)) LV_ClearSetup("INVALIDATED / STOP");
      else if(g_lv_age>12) LV_ClearSetup("EXPIRED");
      else if(g_lv_dir*(c-g_lv_edge)<0) LV_ClearSetup("INVALIDATED / VALUE LOST");
      else if(g_lv_dir>0 ? h>=g_lv_target : l<=g_lv_target) LV_ClearSetup("TARGET REACHED / NO CHASE");
      else if(g_lv_phase==3) LV_ClearSetup("WAIT / NEW SWEEP");
      else if(g_lv_phase==1 && g_lv_dir*(c-g_lv_trigger)>0 &&
              g_lv_dir*(c-g_buf_o[closed])>=0.5*g_lv_atr)
      { g_lv_phase=2; g_lv_status="CONFIRMED / WAIT RETEST"; }
      else if(g_lv_phase==2 && (g_lv_dir>0 ? l<=g_lv_trigger+0.1*g_lv_atr : h>=g_lv_trigger-0.1*g_lv_atr) &&
              g_lv_dir*(c-g_lv_trigger)>0)
      {
         double risk=g_lv_dir*(c-stop),reward=g_lv_dir*(g_lv_target-c);
         if(risk>0 && reward/risk>=InpTopDownMinRR)
         {
            g_lv_phase=3;
            g_lv_status=(g_lv_dir>0?"BUY":"SELL")+string(" WATCH / RR ")+DoubleToString(reward/risk,2)+
               " SL "+DoubleToString(stop,_Digits)+" POC "+DoubleToString(g_lv_target,_Digits);
         }
         else LV_ClearSetup("REJECT / INSUFFICIENT ROOM TO POC");
      }
   }
   else if(g_lv_profile)
   {
      bool buy=false,sell=false;
      // Reuse authoritative sweep events, restricted to known equal-pivot pools.
      for(int i=ArraySize(g_liquidity)-1;i>=0;i--)
      {
         if(g_liquidity[i].availability_bar!=closed ||
            g_liquidity[i].parent_pool_availability_bar<0 ||
            g_liquidity[i].parent_pool_availability_bar>=closed ||
            g_liquidity[i].parent_pool_id=="") continue;
         bool eq=false;
         for(int p=ArraySize(g_liquidity)-1;p>=0;p--)
            if(g_liquidity[p].id==g_liquidity[i].parent_pool_id &&
               g_liquidity[p].availability_bar>=0 && g_liquidity[p].availability_bar<closed &&
               ((g_liquidity[p].type=="EQH" && g_liquidity[i].type=="BSL TAKEN") ||
                (g_liquidity[p].type=="EQL" && g_liquidity[i].type=="SSL TAKEN"))) { eq=true; break; }
         if(!eq) continue;
         double level=g_liquidity[i].parent_level;
         if(!LV_PriceOK(level)) continue;
         if(g_liquidity[i].type=="SSL TAKEN" && l<level && c>level &&
            l<g_lv_val && c>g_lv_val && MathAbs(level-g_lv_val)<=0.3*atr) buy=true;
         if(g_liquidity[i].type=="BSL TAKEN" && h>level && c<level &&
            h>g_lv_vah && c<g_lv_vah && MathAbs(level-g_lv_vah)<=0.3*atr) sell=true;
      }
      if(buy && sell) LV_ClearSetup("CONFLICT / TWO-SIDED SWEEP");
      else if(buy || sell)
      {
         g_lv_dir=(buy?1:-1); g_lv_phase=1; g_lv_age=0;
         g_lv_edge=(buy?g_lv_val:g_lv_vah); g_lv_target=g_lv_poc;
         g_lv_extreme=(buy?l:h); g_lv_trigger=(buy?h:l); g_lv_atr=atr;
         g_lv_status=(buy?"BUY":"SELL")+string(" RECLAIM / WAIT CONFIRMATION");
      }
      else g_lv_status="WAIT / SWEEP AT VALUE EDGE";
   }
   // Freeze only AFTER assessing this candle, for the next candle's decision.
   g_lv_profile=false;
   if(feed)
   {
      int a=g_mvp_active;
      g_lv_val=g_mvp[a].val; g_lv_vah=g_mvp[a].vah; g_lv_poc=g_mvp[a].poc;
      g_lv_profile=LV_ProfileOK(a);
      if(!g_lv_profile) LV_ClearSetup("DATA UNAVAILABLE / INVALID VALUE AREA");
   }
   LV_Publish();
}
#endif
