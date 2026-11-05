#ifndef QSMC_INCIDENT_SAFETY_MQH
#define QSMC_INCIDENT_SAFETY_MQH
// Appended after existing Inputs: no positional iCustom argument is shifted.
input double InpZoneMaxDistanceATR = 12.0;
input int InpZoneLifetimeBars = 120;

void QA_FilterCandidates(SZRECand &cands[],const SZREContext &ctx,const double &h[],const double &l[],const datetime &t[])
{
   double low=DBL_MAX,high=0;
   // Guard against callers that pass unallocated/undersized arrays (e.g. self-tests
   // that invoke ZRE_BuildZones with synthetic h[]/l[] of size ctx.hist). In that
   // case we SKIP the filter instead of wiping the candidate list (the caller's
   // own h/l arrays are the history window they want evaluated).
   bool have_h=(ArraySize(h)>ctx.closed);
   bool have_l=(ArraySize(l)>ctx.closed);
   if(!have_h || !have_l) return;            // caller history is authoritative; do not evict
   for(int b=0;b<=ctx.closed;b++)
   {
      if(!MathIsValidNumber(l[b]) || !MathIsValidNumber(h[b]) || l[b]<=0 || h[b]<l[b]) { ArrayResize(cands,0); return; }
      low=MathMin(low,l[b]); high=MathMax(high,h[b]);
   }
   // v6.6.14 (H5): prefer ctx-preset values (set by ZRE_FillContext) when they
   // are configured, fall back to the raw input defaults otherwise. This keeps
   // the safety filter consistent with the preset (SCALPER/INTRADAY/SWING)
   // instead of always applying M30-suitable 120/12 defaults.
   double distance=((MathIsValidNumber(ctx.reject_max_distance_atr) && ctx.reject_max_distance_atr>=1.0)
                    ? ctx.reject_max_distance_atr
                    : (MathIsValidNumber(InpZoneMaxDistanceATR) && InpZoneMaxDistanceATR>=1.0?InpZoneMaxDistanceATR:12.0));
   int lifetime=(ctx.reject_lifetime_bars>0
                 ? ctx.reject_lifetime_bars
                 : (InpZoneLifetimeBars>0?InpZoneLifetimeBars:120));
   int keep=0;
   for(int i=0;i<ArraySize(cands);i++)
   {
      int born=cands[i].born_bar;
      int age=(born>=0 && born<=ctx.closed?ctx.closed-born:-1);
      string why=QSMC_ZoneRangeReason(cands[i].lo,cands[i].hi,ctx.close_px,low,high,ctx.atr,age,lifetime,distance);
      if(why!="")
      {
         if(!QSMC_IsReaderSilent() &&
            UD_LogAllows("ZONE_REJECT|"+cands[i].tokens+"|"+why))
            Print("[QSMC_ZONE_REJECT] role=",EnumToString(g_instance_role)," symbol=", _Symbol," tf=",EnumToString((ENUM_TIMEFRAMES)_Period),
                  " source=",cands[i].tokens," created=",
                  (born>=0 && born<=ctx.closed && ArraySize(t)>born && t[born]>0
                     ? TimeToString(t[born])
                     : "unknown"),
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
   if(QA_InstanceMismatch()) { g_qa_core.reason="INSTANCE MISMATCH: "+QA_InstanceDescription(); return; }
   double d=BufSigCoreDir[closed];
   if(d!=1.0 && d!=-1.0) return;
   g_qa_core.direction=(int)d;
   g_qa_core.reason="published Core buffer 7; closed bar "+TimeToString(g_qa_core.bar);
}

string QA_CoreStatus()
{
   if(StringFind(g_qa_core.reason,"INSTANCE MISMATCH")==0) return "INSTANCE MISMATCH - WAIT";
   return (g_qa_core.direction==1?"BUY":(g_qa_core.direction==-1?"SELL":"WAIT"));
}

// Snapshot metadata only: quote is never substituted for the closed decision price.
string QA_PriceDescription()
{
   string text="symbol="+_Symbol+" tf="+EnumToString((ENUM_TIMEFRAMES)_Period)+
               " rendered_server="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS);
   MqlTick tick;
   if(SymbolInfoTick(_Symbol,tick) && tick.time_msc>0)
   {
      datetime now=TimeTradeServer();
      long age=(now>0?(long)now-(long)(tick.time_msc/1000):-1);
      text+="\nQUOTE BID="+DoubleToString(tick.bid,_Digits)+" ASK="+DoubleToString(tick.ask,_Digits)+
            " tick_ms="+IntegerToString(tick.time_msc)+" quote_age_s="+IntegerToString(age)+
            (age<0?" (clock unknown)":(age>300?" STALE":" (at render)"));
   }
   else text+="\nQUOTE unavailable / STALE";
   int closed=g_rates_total-2;
   if(closed>=0 && closed<ArraySize(g_buf_c) && closed<ArraySize(g_buf_t))
      text+="\nCLOSED[1]="+DoubleToString(g_buf_c[closed],_Digits)+" bar_open="+
            TimeToString(g_buf_t[closed],TIME_DATE|TIME_SECONDS)+" (decision source, NOT live bid/ask)";
   return text;
}

// Display-only: fit badge to the viewport, then avoid existing docked rectangles.
// The object scan is cached by text+viewport; unchanged badges do not rescan.
string g_qa_badge_full="",g_qa_badge_shown="";
int g_qa_badge_cw=0,g_qa_badge_ch=0;
void QA_LayoutBadge(const string name,const string full)
{
   int cw=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS);
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS);
   if(cw<=0 || ch<=0) return;
   if(full==g_qa_badge_full && cw==g_qa_badge_cw && ch==g_qa_badge_ch &&
      ObjectFind(0,name)>=0 && ObjectGetString(0,name,OBJPROP_TEXT)==g_qa_badge_shown)
      return;
   int available=(int)MathMax(20,cw-24),n=StringLen(full);
   string shown=full;
   while(n>4 && TextWidthPx(shown,"Consolas",9)>available)
   { n--; shown=QSMC_ClipChars(full,n); }
   int w=TextWidthPx(shown,"Consolas",9),h=18,x=12,y=(int)MathMax(0,ch-30-h);
   for(int pass=0;pass<8;pass++)
   {
      bool moved=false;
      for(int j=ObjectsTotal(0,-1,-1)-1;j>=0;j--)
      {
         string obj=ObjectName(0,j,-1,-1);
         if(obj==name || (ENUM_OBJECT)ObjectGetInteger(0,obj,OBJPROP_TYPE)!=OBJ_RECTANGLE_LABEL) continue;
         if(ObjectGetInteger(0,obj,OBJPROP_TIMEFRAMES)==OBJ_NO_PERIODS) continue;
         int rw=(int)ObjectGetInteger(0,obj,OBJPROP_XSIZE),rh=(int)ObjectGetInteger(0,obj,OBJPROP_YSIZE);
         int rx=(int)ObjectGetInteger(0,obj,OBJPROP_XDISTANCE),ry=(int)ObjectGetInteger(0,obj,OBJPROP_YDISTANCE);
         int corner=(int)ObjectGetInteger(0,obj,OBJPROP_CORNER);
         if(corner==CORNER_RIGHT_UPPER || corner==CORNER_RIGHT_LOWER) rx=cw-rx-rw;
         if(corner==CORNER_LEFT_LOWER || corner==CORNER_RIGHT_LOWER) ry=ch-ry-rh;
         if(x<rx+rw+4 && x+w+4>rx && y<ry+rh+4 && y+h+4>ry)
         {
            int above=ry-h-6;
            if(above>=0) y=above;
            else { x=(int)MathMax(0,cw-w-12); y=(int)MathMax(0,ch-h-12); }
            moved=true; break;
         }
      }
      if(!moved) break;
   }
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x); ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetString(0,name,OBJPROP_FONT,"Consolas");
   ObjectSetString(0,name,OBJPROP_TEXT,shown);
   g_qa_badge_full=full; g_qa_badge_shown=shown;
   g_qa_badge_cw=cw; g_qa_badge_ch=ch;
}

void QA_DrawCoreStatus()
{
   if(QSMC_IsReaderSilent() || !QSMC_PaintAllowed()) return;
   string name=PFX+"CORE_CURRENT_STATE";
   if(ObjectFind(0,name)<0 && !ObjectCreate(0,name,OBJ_LABEL,0,0,0)) return;
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_LOWER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,12); ObjectSetInteger(0,name,OBJPROP_YDISTANCE,30);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,name,OBJPROP_COLOR,(g_qa_core.direction==0?clrSilver:clrGold));
   string full="CORE "+QA_CoreStatus()+(g_qa_core.direction!=0?" ENTRY CONFIRMED":" - no current entry");
   QA_LayoutBadge(name,full);
   ObjectSetString(0,name,OBJPROP_TOOLTIP,full+"\n"+g_qa_core.reason+"\n"+QA_InstanceDescription()+"\n"+QA_PriceDescription());
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
