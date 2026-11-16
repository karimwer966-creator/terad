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
      // v6.6.24: EMPTY_VALUE is DBL_MAX and MathIsValidNumber(DBL_MAX) is TRUE, so a
      // sentinel bar passed this test, pushed `high` to DBL_MAX and made every
      // candidate look infinitely far from the range. Fail closed on it explicitly.
      if(!MathIsValidNumber(l[b]) || !MathIsValidNumber(h[b]) ||
         l[b]==EMPTY_VALUE || h[b]==EMPTY_VALUE || l[b]<=0 || h[b]<l[b])
      { ArrayResize(cands,0); return; }
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
      // v6.6.24: the tick clock may legitimately LEAD TimeTradeServer() by a fraction
      // of a second. A negative age was printed as "(clock unknown)", i.e. a healthy
      // feed was reported as an unknown clock once per render.
      if(age<0 && now>0) age=0;
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
// The object scan is cached by text+viewport+object count; unchanged badges do not
// rescan. v6.6.24: the chosen position is applied on EVERY call. QA_DrawCoreStatus()
// used to set CORNER/XDISTANCE/YDISTANCE itself before calling this function, so a
// cached (early-returning) call left the badge at that hard-coded anchor and undid the
// collision avoidance one call after it had been computed.
string g_qa_badge_full="",g_qa_badge_shown="";
int g_qa_badge_cw=0,g_qa_badge_ch=0,g_qa_badge_objs=-1;
int g_qa_badge_x=12,g_qa_badge_y=0;
void QA_LayoutBadge(const string name,const string full)
{
   int cw=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS);
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS);
   if(cw<=0 || ch<=0) return;
   //--- v6.6.23 T11: the cache key used to be text + viewport only, so a badge
   //--- placed while a second panel appeared stayed where it was and the two
   //--- rectangles overlapped. The object count is part of the key now: any
   //--- panel added or removed re-runs the collision pass once.
   // Main window, rectangle labels only: a subwindow object has its own pixel origin,
   // so testing one against this badge produced collisions that do not exist.
   int objs=ObjectsTotal(0,0,OBJ_RECTANGLE_LABEL);
   bool cached=(full==g_qa_badge_full && cw==g_qa_badge_cw && ch==g_qa_badge_ch &&
                objs==g_qa_badge_objs && g_qa_badge_shown!="" && ObjectFind(0,name)>=0);
   string shown=g_qa_badge_shown;
   int x=g_qa_badge_x,y=g_qa_badge_y;
   if(!cached)
   {
      int available=(int)MathMax(20,cw-24),n=StringLen(full);
      shown=full;
      while(n>4 && TextWidthPx(shown,"Consolas",9)>available)
      { n--; shown=QSMC_ClipChars(full,n); }
      int w=TextWidthPx(shown,"Consolas",9),h=18;
      x=12; y=(int)MathMax(0,ch-30-h);
      for(int pass=0;pass<8;pass++)
      {
         bool moved=false;
         for(int j=objs-1;j>=0;j--)
         {
            string obj=ObjectName(0,j,0,OBJ_RECTANGLE_LABEL);
            if(obj==name || (ENUM_OBJECT)ObjectGetInteger(0,obj,OBJPROP_TYPE)!=OBJ_RECTANGLE_LABEL) continue;
            if(ObjectGetInteger(0,obj,OBJPROP_TIMEFRAMES)==OBJ_NO_PERIODS) continue;
            int rw=(int)ObjectGetInteger(0,obj,OBJPROP_XSIZE),rh=(int)ObjectGetInteger(0,obj,OBJPROP_YSIZE);
            int rx=(int)ObjectGetInteger(0,obj,OBJPROP_XDISTANCE),ry=(int)ObjectGetInteger(0,obj,OBJPROP_YDISTANCE);
            int corner=(int)ObjectGetInteger(0,obj,OBJPROP_CORNER);
            // The distance is measured from the chosen corner to the NEAR edge of the
            // rectangle, so a right/bottom anchor needs the width/height folded back in.
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
      g_qa_badge_full=full; g_qa_badge_shown=shown;
      g_qa_badge_cw=cw; g_qa_badge_ch=ch; g_qa_badge_objs=objs;
      g_qa_badge_x=x; g_qa_badge_y=y;
   }
   // Applied on every call, cached or not, so the position decided above can never be
   // silently replaced by a caller that also sets OBJPROP_XDISTANCE.
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x); ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetString(0,name,OBJPROP_FONT,"Consolas");
   if(ObjectGetString(0,name,OBJPROP_TEXT)!=shown) ObjectSetString(0,name,OBJPROP_TEXT,shown);
}

void QA_DrawCoreStatus()
{
   if(QSMC_IsReaderSilent() || !QSMC_PaintAllowed()) return;
   string name=PFX+"CORE_CURRENT_STATE";
   if(ObjectFind(0,name)<0 && !ObjectCreate(0,name,OBJ_LABEL,0,0,0)) return;
   // v6.6.24: geometry belongs to QA_LayoutBadge() alone (see its comment). Setting a
   // fixed corner/offset here re-applied them on every redraw, including the redraws
   // where the layout function returned early on its cache.
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,name,OBJPROP_COLOR,(g_qa_core.direction==0?clrSilver:clrGold));
   string full="CORE "+QA_CoreStatus()+(g_qa_core.direction!=0?" ENTRY CONFIRMED":" - no current entry");
   QA_LayoutBadge(name,full);
   ObjectSetString(0,name,OBJPROP_TOOLTIP,full+"\n"+g_qa_core.reason+"\n"+QA_InstanceDescription()+"\n"+QA_PriceDescription());
}

bool QA_LabelAlive(const double lo,const double hi,const datetime born,const bool invalid)
{
   //--- v6.6.23 T11: hi<=lo is a zero-height band - nothing to label, and the
   //--- old '<' let a degenerate zone survive every call.
   if(invalid || born<=0 || lo<=0 || hi<=lo) return false;
   int closed=g_rates_total-2;
   if(closed<0 || closed>=ArraySize(g_buf_c) || closed>=ArraySize(g_atr_buf)) return false;
   double atr=g_atr_buf[closed],price=g_buf_c[closed];
   if(!MathIsValidNumber(atr) || atr<=0 || atr==EMPTY_VALUE || price<=0) return false;
   int lifetime=(InpAdvisoryLabelLifetimeBars>0?InpAdvisoryLabelLifetimeBars:12);
   double distance=(MathIsValidNumber(InpAdvisoryLabelMaxDistanceATR) && InpAdvisoryLabelMaxDistanceATR>0?InpAdvisoryLabelMaxDistanceATR:3.0);
   // v6.6.24: the age is found on the bar clock the rest of the host uses, walking back
   // at most `lifetime` bars. iBarShift() is a terminal query per candidate per bar and
   // returns -1 for a stamp outside the chart's series, which this function then read as
   // "older than the lifetime" - so a history gap deleted every advisory label at once.
   if(closed>=ArraySize(g_buf_t)) return false;
   int age=-1;
   for(int back=0;back<=lifetime && closed-back>=0;back++)
      if(g_buf_t[closed-back]==born) { age=back; break; }
   if(age<0) return false;
   return MathMax(0.0,MathMax(lo-price,price-hi))<=distance*atr;
}

void QA_ClearTacticalPaint()
{
   // v6.6.24: object deletion is a chart side effect. The EA's private iCustom instance
   // runs as a SILENT reader and must never delete the host chart's marks - it used to
   // wipe MTF_ENTRY on every clear, so the visible chart lost its tactical paint every
   // time the EA refreshed its hidden instance.
   if(!QSMC_IsReaderSilent())
   { ObjectDelete(0,PFX+"MTF_ENTRY"); ObjectDelete(0,PFX+"MTF_ENTRY_TX"); }
   EntryMarkClearTactical(); // only visual buffers, never Core 7..12
}

#endif
