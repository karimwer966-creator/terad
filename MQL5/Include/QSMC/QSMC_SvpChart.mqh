//+------------------------------------------------------------------+
//|                                                QSMC_SvpChart.mqh |
//|  Chart Object Manager, signal lifecycle and the compact dashboard |
//|  of the SMC + Volume Profile engine.                              |
//|                                                                   |
//|  CHART OBJECT MANAGER (SVC_*)                                     |
//|  Every object this program draws is created HERE and is recorded  |
//|  in a registry: stable name, type, layer, the setup / entity it   |
//|  belongs to, lifecycle state, creation time.                      |
//|   * a name is derived from WHAT the object shows (a signal id, a  |
//|     zone id, a fixed slot), never from the bar it was drawn on,   |
//|     so a refresh UPDATES the object instead of adding one;        |
//|   * a property is written only when its value changed;            |
//|   * a refresh pass is SVC_Begin() ... draw ... SVC_End(): what    |
//|     was not drawn in the pass (invalidated, expired, layer off)   |
//|     is deleted - there is no blanket delete-and-redraw;           |
//|   * each layer has a switch and a hard cap on visible objects;    |
//|   * only names that start with the program's own prefix are ever  |
//|     created, moved or deleted. The operator's objects are never   |
//|     touched.                                                      |
//|                                                                   |
//|  SIGNAL LIFECYCLE (SVV_UpdateSignals)                             |
//|  DETECTED (trigger + entry zone, awaiting the retest) ->          |
//|  CONFIRMED (BUY/SELL SETUP on a closed bar) -> ACTIVE ->          |
//|  MITIGATED (target traded) / INVALIDATED (stop traded) / EXPIRED  |
//|  The plan of a confirmed signal is frozen at confirmation.        |
//|                                                                   |
//|  It draws and it explains. It places no order.                    |
//+------------------------------------------------------------------+
#ifndef QSMC_SVP_CHART_MQH
#define QSMC_SVP_CHART_MQH

#include <QSMC/QSMC_SvpDecision.mqh>
#include <QSMC/QSMC_SignalRegistry.mqh>

#define SVC_MAX_OBJECTS 320
#define SVC_LAYERS      5
#define SVV_ROWS        16

enum ENUM_SVC_LAYER
{
   SVC_LAYER_PRIMARY   = 0,   // dashboard, current setup, entry zone, SL / TP
   SVC_LAYER_SECONDARY = 1,   // major BOS/CHoCH, liquidity, active OB/FVG
   SVC_LAYER_VOLUME    = 2,   // POC, VAH, VAL, selected HVN / LVN
   SVC_LAYER_DETAIL    = 3,   // volume histogram
   SVC_LAYER_OPTIONAL  = 4    // previous signals, old sweeps, older structure
};

struct SSvcObject
{
   bool           used;
   string         name;       // full chart name: prefix + stable id
   ENUM_OBJECT    type;
   ENUM_SVC_LAYER layer;
   string         setup;      // the setup / entity the object belongs to
   string         state;      // lifecycle state text of that entity
   datetime       created;
   int            pass;       // refresh pass that last drew it
};

struct SSvvStyle
{
   color bull;
   color bear;
   color neutral;
   color text;
   color panel_bg;
   color panel_border;
   color poc;
   color value_area;
   color node;
   color liquidity;
   color stop;
   color target;
   int   font_size;
   int   corner;              // 0 left-upper, 1 left-lower, 2 right-lower, 3 right-upper
   int   x;
   int   y;
   int   liq_per_side;
   int   zones_per_side;
   int   nodes;
   int   live_signals;        // live setups drawn in full; older live ones become one mark
   int   history_signals;
   int   history_sweeps;
   int   histogram_rows;
   int   max_active_bars;     // an ACTIVE signal older than this expires
   bool  show_reason;
};

SSvcObject g_svc[SVC_MAX_OBJECTS];
string     g_svc_prefix="QSVP_";
long       g_svc_chart=0;
int        g_svc_pass=0;
bool       g_svc_on[SVC_LAYERS];
#define SVC_EDGE_MAX 256
int        g_svc_edges=0;               // horizontal edges drawn in this pass
bool       g_svc_edges_lost=false;      // more edges than the table holds
datetime   g_svc_edge_t1[SVC_EDGE_MAX];
datetime   g_svc_edge_t2[SVC_EDGE_MAX];
double     g_svc_edge_price[SVC_EDGE_MAX];
int        g_svc_cap[SVC_LAYERS];
int        g_svc_drawn[SVC_LAYERS];     // objects drawn per layer in the current pass
int        g_svc_created=0;             // lifetime counters, read by the tests
int        g_svc_updated=0;
int        g_svc_deleted=0;
int        g_svc_refused=0;
int        g_svc_writes=0;
double     g_svv_zone_lo[QSR_CAPACITY]; // entry zone of each registry record
double     g_svv_zone_hi[QSR_CAPACITY];
datetime   g_svv_confirmed[QSR_CAPACITY]; // bar that confirmed the record (0 = never confirmed)
int        g_svv_alerts=0;              // confirmations announced
#define SVV_OUTBOX_MAX 4
int        g_svv_outbox=0;              // announcements waiting for the host program to deliver them
string     g_svv_outbox_text[SVV_OUTBOX_MAX];
#define SVV_SHOWN_MAX 8
int        g_svv_shown=0;               // entry zones the primary layer drew in this pass
int        g_svv_shown_dir[SVV_SHOWN_MAX];
double     g_svv_shown_lo[SVV_SHOWN_MAX];
double     g_svv_shown_hi[SVV_SHOWN_MAX];
#define SVV_CAPTION_MAX 64
#define SVV_BARS_PER_CHAR 1.0           // layout model: one caption character is one M15 bar wide
double     g_svv_label_gap=0.0;         // layout model: one caption line is this much price (0.6 ATR)
int        g_svv_labels_hidden=0;       // captions withheld in the last pass (the line is still drawn)
int        g_svv_caps=0;                // captions placed in this pass: bar position x1..x2, price lo..hi
#define SVV_DEFER_MAX 24
int        g_svv_deferred=0;            // captions inside the chart, placed after every line of the pass is known
string     g_svv_def_id[SVV_DEFER_MAX];
string     g_svv_def_setup[SVV_DEFER_MAX];
string     g_svv_def_state[SVV_DEFER_MAX];
string     g_svv_def_text[SVV_DEFER_MAX];
string     g_svv_def_tip[SVV_DEFER_MAX];
int        g_svv_def_layer[SVV_DEFER_MAX];
int        g_svv_def_anchor[SVV_DEFER_MAX];
int        g_svv_def_other[SVV_DEFER_MAX];
int        g_svv_def_font[SVV_DEFER_MAX];
color      g_svv_def_color[SVV_DEFER_MAX];
datetime   g_svv_def_time[SVV_DEFER_MAX];
double     g_svv_def_price[SVV_DEFER_MAX];
double     g_svv_cap_x1[SVV_CAPTION_MAX];
double     g_svv_cap_x2[SVV_CAPTION_MAX];
double     g_svv_cap_lo[SVV_CAPTION_MAX];
double     g_svv_cap_hi[SVV_CAPTION_MAX];
int        g_svv_signals_hidden=0;      // live signals kept off the chart in the last pass (zone already shown)

void SVV_DefaultStyle(SSvvStyle &s)
{
   s.bull=clrMediumSeaGreen; s.bear=clrTomato; s.neutral=clrSilver; s.text=clrWhite;
   s.panel_bg=clrBlack; s.panel_border=clrDimGray; s.poc=clrGold; s.value_area=clrDodgerBlue;
   s.node=clrDarkGray; s.liquidity=clrOrange; s.stop=clrCrimson; s.target=clrLimeGreen;
   s.font_size=9; s.corner=0; s.x=10; s.y=20;
   s.liq_per_side=2; s.zones_per_side=2; s.nodes=2; s.live_signals=2;
   s.history_signals=8; s.history_sweeps=6; s.histogram_rows=40; s.max_active_bars=96;
   s.show_reason=true;
}

//====================================================================
// Chart Object Manager
//====================================================================
void SVC_ResetRegistry()
{
   for(int i=0;i<SVC_MAX_OBJECTS;i++)
   {
      g_svc[i].used=false; g_svc[i].name=""; g_svc[i].type=OBJ_TEXT; g_svc[i].layer=SVC_LAYER_OPTIONAL;
      g_svc[i].setup=""; g_svc[i].state=""; g_svc[i].created=0; g_svc[i].pass=0;
   }
   g_svc_pass=0;
   for(int k=0;k<SVC_LAYERS;k++) g_svc_drawn[k]=0;
}

// Take ownership of the chart namespace `prefix`. Objects a previous session
// left behind under OUR prefix are removed; nothing else is looked at.
void SVC_Init(const string prefix,const long chart_id)
{
   g_svc_prefix=(prefix==""?"QSVP_":prefix);
   g_svc_chart=chart_id;
   SVC_ResetRegistry();
   for(int k=0;k<SVC_LAYERS;k++) { g_svc_on[k]=true; g_svc_cap[k]=64; }
   g_svc_created=0; g_svc_updated=0; g_svc_deleted=0; g_svc_refused=0; g_svc_writes=0;
   ObjectsDeleteAll(g_svc_chart,g_svc_prefix);
}

void SVC_SetLayer(const ENUM_SVC_LAYER layer,const bool on,const int cap)
{
   int k=(int)layer;
   if(k<0 || k>=SVC_LAYERS) return;
   g_svc_on[k]=on;
   g_svc_cap[k]=(cap<0?0:cap);
}

string SVC_LayerName(const ENUM_SVC_LAYER layer)
{
   if(layer==SVC_LAYER_PRIMARY)   return "PRIMARY";
   if(layer==SVC_LAYER_SECONDARY) return "SECONDARY";
   if(layer==SVC_LAYER_VOLUME)    return "VOLUME";
   if(layer==SVC_LAYER_DETAIL)    return "DETAIL";
   return "OPTIONAL";
}

int SVC_Find(const string name)
{
   for(int i=0;i<SVC_MAX_OBJECTS;i++)
      if(g_svc[i].used && g_svc[i].name==name) return i;
   return -1;
}

int SVC_Count()
{
   int n=0;
   for(int i=0;i<SVC_MAX_OBJECTS;i++) if(g_svc[i].used) n++;
   return n;
}

int SVC_CountLayer(const ENUM_SVC_LAYER layer)
{
   int n=0;
   for(int i=0;i<SVC_MAX_OBJECTS;i++) if(g_svc[i].used && g_svc[i].layer==layer) n++;
   return n;
}

void SVC_Begin()
{
   g_svc_pass++;
   for(int k=0;k<SVC_LAYERS;k++) g_svc_drawn[k]=0;
   g_svc_edges=0; g_svc_edges_lost=false;
}

// Every horizontal line the pass draws (a segment, the top and the bottom of a
// box) is remembered, so a caption inside the chart can be kept clear of them.
void SVC_NoteEdge(const datetime t1,const datetime t2,const double price)
{
   if(g_svc_edges>=SVC_EDGE_MAX) { g_svc_edges_lost=true; return; }
   g_svc_edge_t1[g_svc_edges]=(t1<t2?t1:t2);
   g_svc_edge_t2[g_svc_edges]=(t1<t2?t2:t1);
   g_svc_edge_price[g_svc_edges]=price;
   g_svc_edges++;
}

// Claim (create or re-use) the object `id` for this pass. Returns the full
// chart name, or "" when the layer is off, its cap is reached or the registry
// is full - in which case nothing is drawn and nothing is left behind.
string SVC_Claim(const string id,const ENUM_OBJECT type,const ENUM_SVC_LAYER layer,
                 const string setup,const string state,const datetime t1,const double p1,
                 const datetime t2,const double p2)
{
   int k=(int)layer;
   if(id=="" || k<0 || k>=SVC_LAYERS) return "";
   if(!g_svc_on[k] || g_svc_drawn[k]>=g_svc_cap[k]) { g_svc_refused++; return ""; }
   string name=g_svc_prefix+id;
   int slot=SVC_Find(name);
   if(slot>=0 && g_svc[slot].pass==g_svc_pass) return name;      // already drawn in this pass
   bool on_chart=(ObjectFind(g_svc_chart,name)>=0);
   // the same id asked for as another kind of object: the old one goes first
   if(slot>=0 && g_svc[slot].type!=type && on_chart)
   {
      ObjectDelete(g_svc_chart,name);
      g_svc_deleted++;
      on_chart=false;
   }
   bool is_new=(slot<0);
   if(slot<0)
   {
      for(int i=0;i<SVC_MAX_OBJECTS && slot<0;i++) if(!g_svc[i].used) slot=i;
      if(slot<0) { g_svc_refused++; return ""; }
   }
   // not on the chart: never drawn yet, or removed behind our back - (re)create it
   if(!on_chart)
   {
      if(!ObjectCreate(g_svc_chart,name,type,0,t1,p1,t2,p2))
      {
         g_svc_refused++;
         if(!is_new) { g_svc[slot].used=false; g_svc[slot].name=""; }
         return "";
      }
      g_svc_created++;
      ObjectSetInteger(g_svc_chart,name,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(g_svc_chart,name,OBJPROP_HIDDEN,true);
   }
   if(is_new)
   {
      g_svc[slot].used=true; g_svc[slot].name=name;
      g_svc[slot].created=TimeCurrent();
      if(on_chart)
      {
         // an object of ours that the registry did not know (cannot happen after
         // SVC_Init, which clears the prefix): adopt it rather than duplicate it
         ObjectSetInteger(g_svc_chart,name,OBJPROP_SELECTABLE,false);
         ObjectSetInteger(g_svc_chart,name,OBJPROP_HIDDEN,true);
      }
   }
   else if(on_chart) g_svc_updated++;
   g_svc[slot].type=type;
   g_svc[slot].layer=layer; g_svc[slot].setup=setup; g_svc[slot].state=state;
   g_svc[slot].pass=g_svc_pass;
   g_svc_drawn[k]++;
   return name;
}

// Property writers: a write happens only when the value actually changes.
void SVC_Int(const string name,const ENUM_OBJECT_PROPERTY_INTEGER prop,const long value)
{
   if(ObjectGetInteger(g_svc_chart,name,prop)==value) return;
   ObjectSetInteger(g_svc_chart,name,prop,value);
   g_svc_writes++;
}

void SVC_Dbl(const string name,const ENUM_OBJECT_PROPERTY_DOUBLE prop,const double value)
{
   if(ObjectGetDouble(g_svc_chart,name,prop)==value) return;
   ObjectSetDouble(g_svc_chart,name,prop,value);
   g_svc_writes++;
}

void SVC_Str(const string name,const ENUM_OBJECT_PROPERTY_STRING prop,const string value)
{
   if(ObjectGetString(g_svc_chart,name,prop)==value) return;
   ObjectSetString(g_svc_chart,name,prop,value);
   g_svc_writes++;
}

void SVC_Point(const string name,const int point,const datetime t,const double price)
{
   if(ObjectGetInteger(g_svc_chart,name,OBJPROP_TIME,point)==(long)t &&
      ObjectGetDouble(g_svc_chart,name,OBJPROP_PRICE,point)==price) return;
   ObjectMove(g_svc_chart,name,point,t,price);
   g_svc_writes++;
}

// Close the pass: every registered object that was NOT drawn in it is stale
// (its entity ended, was invalidated, or its layer was switched off) and goes.
int SVC_End()
{
   int removed=0;
   for(int i=0;i<SVC_MAX_OBJECTS;i++)
   {
      if(!g_svc[i].used || g_svc[i].pass==g_svc_pass) continue;
      if(ObjectFind(g_svc_chart,g_svc[i].name)>=0) ObjectDelete(g_svc_chart,g_svc[i].name);
      g_svc[i].used=false; g_svc[i].name="";
      g_svc_deleted++;
      removed++;
   }
   return removed;
}

// Remove everything this program owns - by registry, then by its own prefix.
void SVC_Shutdown()
{
   for(int i=0;i<SVC_MAX_OBJECTS;i++)
   {
      if(!g_svc[i].used) continue;
      if(ObjectFind(g_svc_chart,g_svc[i].name)>=0) ObjectDelete(g_svc_chart,g_svc[i].name);
      g_svc_deleted++;
   }
   SVC_ResetRegistry();
   ObjectsDeleteAll(g_svc_chart,g_svc_prefix);
}

string SVC_Census()
{
   string s="objects "+IntegerToString(SVC_Count());
   for(int k=0;k<SVC_LAYERS;k++)
      s+=" | "+SVC_LayerName((ENUM_SVC_LAYER)k)+" "+IntegerToString(SVC_CountLayer((ENUM_SVC_LAYER)k))+
         (g_svc_on[k]?"":" (off)");
   return s+" | created "+IntegerToString(g_svc_created)+" updated "+IntegerToString(g_svc_updated)+
          " deleted "+IntegerToString(g_svc_deleted)+" refused "+IntegerToString(g_svc_refused);
}

//--- drawing helpers --------------------------------------------------------------
void SVC_Segment(const string id,const ENUM_SVC_LAYER layer,const string setup,const string state,
                 const datetime t1,const datetime t2,const double price,const color col,
                 const ENUM_LINE_STYLE style,const int width,const string tip)
{
   string name=SVC_Claim(id,OBJ_TREND,layer,setup,state,t1,price,t2,price);
   if(name=="") return;
   SVC_NoteEdge(t1,t2,price);
   SVC_Point(name,0,t1,price);
   SVC_Point(name,1,t2,price);
   SVC_Int(name,OBJPROP_COLOR,col);
   SVC_Int(name,OBJPROP_STYLE,style);
   SVC_Int(name,OBJPROP_WIDTH,width);
   SVC_Int(name,OBJPROP_RAY_RIGHT,false);
   SVC_Int(name,OBJPROP_BACK,true);
   SVC_Str(name,OBJPROP_TOOLTIP,tip);
}

// Returns true when the box is on the chart after the call.
bool SVC_Box(const string id,const ENUM_SVC_LAYER layer,const string setup,const string state,
             const datetime t1,const double p1,const datetime t2,const double p2,const color col,
             const bool fill,const string tip)
{
   string name=SVC_Claim(id,OBJ_RECTANGLE,layer,setup,state,t1,p1,t2,p2);
   if(name=="") return false;
   SVC_NoteEdge(t1,t2,p1);
   SVC_NoteEdge(t1,t2,p2);
   SVC_Point(name,0,t1,p1);
   SVC_Point(name,1,t2,p2);
   SVC_Int(name,OBJPROP_COLOR,col);
   SVC_Int(name,OBJPROP_FILL,fill);
   SVC_Int(name,OBJPROP_WIDTH,1);
   SVC_Int(name,OBJPROP_BACK,true);
   SVC_Str(name,OBJPROP_TOOLTIP,tip);
   return true;
}

void SVC_Text(const string id,const ENUM_SVC_LAYER layer,const string setup,const string state,
              const datetime t,const double price,const string text,const color col,const int size,
              const ENUM_ANCHOR_POINT anchor,const string tip)
{
   string name=SVC_Claim(id,OBJ_TEXT,layer,setup,state,t,price,0,0.0);
   if(name=="") return;
   SVC_Point(name,0,t,price);
   SVC_Str(name,OBJPROP_TEXT,text);
   SVC_Str(name,OBJPROP_FONT,"Arial");
   SVC_Int(name,OBJPROP_FONTSIZE,size);
   SVC_Int(name,OBJPROP_COLOR,col);
   SVC_Int(name,OBJPROP_ANCHOR,anchor);
   SVC_Str(name,OBJPROP_TOOLTIP,tip);
}

void SVC_Label(const string id,const ENUM_SVC_LAYER layer,const int corner,const int x,const int y,
               const string text,const color col,const int size,const ENUM_ANCHOR_POINT anchor)
{
   string name=SVC_Claim(id,OBJ_LABEL,layer,"DASHBOARD","",0,0.0,0,0.0);
   if(name=="") return;
   SVC_Int(name,OBJPROP_CORNER,corner);
   SVC_Int(name,OBJPROP_ANCHOR,anchor);
   SVC_Int(name,OBJPROP_XDISTANCE,x);
   SVC_Int(name,OBJPROP_YDISTANCE,y);
   SVC_Str(name,OBJPROP_TEXT,text);
   SVC_Str(name,OBJPROP_FONT,"Consolas");
   SVC_Int(name,OBJPROP_FONTSIZE,size);
   SVC_Int(name,OBJPROP_COLOR,col);
   SVC_Int(name,OBJPROP_BACK,false);
}

void SVC_Panel(const string id,const ENUM_SVC_LAYER layer,const int corner,const int x,const int y,
               const int w,const int h,const color bg,const color border)
{
   string name=SVC_Claim(id,OBJ_RECTANGLE_LABEL,layer,"DASHBOARD","",0,0.0,0,0.0);
   if(name=="") return;
   SVC_Int(name,OBJPROP_CORNER,corner);
   SVC_Int(name,OBJPROP_XDISTANCE,x);
   SVC_Int(name,OBJPROP_YDISTANCE,y);
   SVC_Int(name,OBJPROP_XSIZE,w);
   SVC_Int(name,OBJPROP_YSIZE,h);
   SVC_Int(name,OBJPROP_BGCOLOR,bg);
   SVC_Int(name,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   SVC_Int(name,OBJPROP_COLOR,border);
   SVC_Int(name,OBJPROP_BACK,false);
}

//====================================================================
// Signal lifecycle
//====================================================================
// Forget every signal (start of a session, or before the history is replayed).
void SVV_ResetSignals()
{
   QSR_Reset();
   for(int i=0;i<QSR_CAPACITY;i++) { g_svv_zone_lo[i]=0.0; g_svv_zone_hi[i]=0.0; g_svv_confirmed[i]=0; }
   g_svv_shown=0;
   g_svv_outbox=0;
}

// Hands the oldest waiting announcement to the caller and removes it; false
// when none is left. The caller (the host program) decides how to deliver it.
bool SVV_NextAnnouncement(string &text)
{
   if(g_svv_outbox<=0) return false;
   text=g_svv_outbox_text[0];
   for(int i=1;i<g_svv_outbox;i++) g_svv_outbox_text[i-1]=g_svv_outbox_text[i];
   g_svv_outbox--;
   return true;
}

// Chart id of a signal: direction, setup family and the bar that took the
// liquidity. It never contains the bar the object was drawn on.
string SVV_SignalId(const int direction,const string setup_type,const datetime origin)
{
   return "S"+(direction>0?"B":"S")+(StringFind(setup_type,"FAILED")==0?"F":"M")+IntegerToString((long)origin);
}

// Closed M15 bars between the bar that holds `t` and the newest bar of the
// array. An age is counted in BARS, never in hours: a setup confirmed on Friday
// afternoon is 26 bars old on Monday's first bar, not 56 hours old.
int SVV_BarsSince(const MqlRates &m15[],const int n,const datetime t)
{
   if(n<=0 || t>=m15[n-1].time) return 0;
   if(t<m15[0].time) return n;         // older than the whole array
   int lo=0,hi=n-1;                    // m15[lo].time <= t < m15[hi].time
   while(hi-lo>1)
   {
      int mid=(lo+hi)/2;
      if(m15[mid].time<=t) lo=mid; else hi=mid;
   }
   return (n-1)-lo;
}

// Register / update the tracked setup and move every live record forward.
// `announce` allows alerts (never during the initial history pass).
void SVV_UpdateSignals(const MqlRates &m15[],const int n,const string symbol,const int tf_code,
                       const SSvvStyle &style,const bool announce)
{
   if(n<=0) return;
   int last=n-1;
   datetime now=m15[last].time;
   if(g_svp.ready && g_svp.tracked)
   {
      ENUM_QSR_STATE want=(g_svp.state!=SVP_DECISION_WAIT?QSR_STATE_CONFIRMED:QSR_STATE_DETECTED);
      bool created=false;
      int idx=QSR_Upsert(symbol,tf_code,g_svp.direction,g_svp.setup_type,g_svp.anchor_id,
                         g_svp.origin_time,now,want,created);
      if(idx>=0)
      {
         if(created) g_svv_confirmed[idx]=0;
         if(created || g_qsr[idx].state==QSR_STATE_DETECTED)
         { g_svv_zone_lo[idx]=g_svp.zone_lo; g_svv_zone_hi[idx]=g_svp.zone_hi; }
         // the plan is frozen on the bar that confirmed the setup
         if(g_svp.plan_valid && g_qsr[idx].state==QSR_STATE_CONFIRMED && g_qsr[idx].state_time==now &&
            !(g_qsr[idx].entry>0.0))
         {
            QSR_SetPlan(idx,0,0,g_svp.entry,g_svp.stop,g_svp.target);
            g_svv_zone_lo[idx]=g_svp.zone_lo; g_svv_zone_hi[idx]=g_svp.zone_hi;
            g_svv_confirmed[idx]=now;
            if(announce)
            {
               // This module never talks to the operator itself: the message is
               // queued, and the host PROGRAM - the one place that owns the
               // user-facing channel - sends it (SVV_NextAnnouncement).
               g_svv_alerts++;
               if(g_svv_outbox<SVV_OUTBOX_MAX)
               {
                  g_svv_outbox_text[g_svv_outbox]=symbol+" "+g_svp.headline+" | entry "+DoubleToString(g_svp.entry,_Digits)+
                                                  " SL "+DoubleToString(g_svp.stop,_Digits)+" TP "+DoubleToString(g_svp.target,_Digits)+
                                                  " RR 1:"+DoubleToString(g_svp.rr,2);
                  g_svv_outbox++;
               }
            }
         }
      }
   }
   for(int i=0;i<QSR_CAPACITY;i++)
   {
      if(!g_qsr[i].used || !QSR_IsLive(g_qsr[i].state)) continue;
      if(g_qsr[i].state==QSR_STATE_DETECTED)
      {
         // a candidate that the engine stopped reporting is over
         if(SVV_BarsSince(m15,n,g_qsr[i].last_seen)>2) QSR_SetState(i,QSR_STATE_EXPIRED,now,"candidate no longer valid");
         continue;
      }
      if(g_qsr[i].state_time>=now && g_qsr[i].state==QSR_STATE_CONFIRMED) continue;   // confirmed on this very bar
      if(g_qsr[i].state==QSR_STATE_CONFIRMED) QSR_SetState(i,QSR_STATE_ACTIVE,now,"in play");
      if(!(g_qsr[i].entry>0.0) || !(g_qsr[i].stop>0.0) || !(g_qsr[i].target>0.0))
      {
         QSR_SetState(i,QSR_STATE_EXPIRED,now,"no plan recorded");
         continue;
      }
      bool stop_hit=(g_qsr[i].direction>0 ? m15[last].low<=g_qsr[i].stop : m15[last].high>=g_qsr[i].stop);
      bool target_hit=(g_qsr[i].direction>0 ? m15[last].high>=g_qsr[i].target : m15[last].low<=g_qsr[i].target);
      // both inside one bar cannot be ordered from OHLC: assume the stop came first
      if(stop_hit) QSR_SetState(i,QSR_STATE_INVALIDATED,now,"stop level traded");
      else if(target_hit) QSR_SetState(i,QSR_STATE_MITIGATED,now,"target traded");
      else if(SVV_BarsSince(m15,n,g_qsr[i].first_seen)>style.max_active_bars)
         QSR_SetState(i,QSR_STATE_EXPIRED,now,"older than "+IntegerToString(style.max_active_bars)+" bars");
   }
}

// One identity, one plan. The engine is stateless and may re-derive slightly
// different numbers (spread, a developing profile) while a setup stays
// actionable; what the operator sees is the plan frozen on the confirming bar.
// A setup whose stop or target has already traded is over: the decision is WAIT.
void SVV_AlignDecision(const string symbol,const int tf_code,const SSvpParams &p)
{
   if(!g_svp.ready || !g_svp.tracked || g_svp.state==SVP_DECISION_WAIT) return;
   string key=QSR_Key(QSR_Family(symbol,tf_code,g_svp.direction,g_svp.setup_type,g_svp.anchor_id),g_svp.origin_time);
   int idx=QSR_FindKey(key);
   if(idx<0 || !(g_qsr[idx].entry>0.0) || !(g_qsr[idx].stop>0.0) || !(g_qsr[idx].target>0.0)) return;
   if(g_qsr[idx].state==QSR_STATE_CONFIRMED || g_qsr[idx].state==QSR_STATE_ACTIVE)
   {
      double risk=(double)g_svp.direction*(g_qsr[idx].entry-g_qsr[idx].stop);
      double reward=(double)g_svp.direction*(g_qsr[idx].target-g_qsr[idx].entry);
      if(!(risk>0.0) || !(reward>0.0)) return;
      g_svp.entry=g_qsr[idx].entry; g_svp.stop=g_qsr[idx].stop; g_svp.target=g_qsr[idx].target;
      g_svp.risk=risk; g_svp.reward=reward; g_svp.rr=reward/risk;
      return;
   }
   string side=(g_svp.direction>0?"BUY":"SELL");
   g_svp.state=SVP_DECISION_WAIT;
   g_svp.headline=SVP_DecisionText(SVP_DECISION_WAIT);
   g_svp.plan_valid=false;
   g_svp.reason="WAIT - the "+side+" setup of "+SVP_ClockText(g_svp.origin_time)+" is over ("+
                QSR_StateName(g_qsr[idx].state)+": "+g_qsr[idx].note+")";
}

//====================================================================
// Compact dashboard
//====================================================================
string SVV_Clip(const string text,const int max_len)
{
   if(StringLen(text)<=max_len) return text;
   return StringSubstr(text,0,max_len-3)+"...";
}

// The rows, in the fixed order of the specification. Whatever is not known is
// printed as N/A - a price is never invented to fill a row.
int SVV_DashboardRows(const SSvpDecision &d,const string symbol,const SSvpParams &p,
                      const string profile_tag,string &rows[])
{
   ArrayResize(rows,SVV_ROWS);
   int k=0;
   rows[k++]="MARKET: "+symbol;
   rows[k++]="TIMEFRAME: M15 (context H1 / H4)";
   rows[k++]="H4 BIAS: "+(d.ready?SVP_DirText(d.h4_bias):"N/A");
   rows[k++]="H1 STRUCTURE: "+(d.ready?d.h1_text:"N/A");
   rows[k++]="LIQUIDITY: "+(d.ready?d.liq_text:"N/A");
   rows[k++]="SWEEP: "+(d.ready?d.sweep_text:"N/A");
   rows[k++]="OB/FVG: "+(d.ready?d.zone_text:"N/A");
   rows[k++]="POC: "+(d.vp_valid?DoubleToString(d.poc,p.digits)+" "+profile_tag:"N/A");
   rows[k++]="VAH / VAL: "+(d.vp_valid?DoubleToString(d.vah,p.digits)+" / "+DoubleToString(d.val,p.digits):"N/A");
   rows[k++]="FINAL DECISION: "+d.headline;
   bool pending_zone=(d.ready && !d.plan_valid && d.tracked && d.zone_hi>d.zone_lo);
   rows[k++]="ENTRY: "+(d.plan_valid?DoubleToString(d.entry,p.digits):
              (pending_zone?"N/A (awaiting retest of "+DoubleToString(d.zone_lo,p.digits)+"-"+DoubleToString(d.zone_hi,p.digits)+")":"N/A"));
   rows[k++]="STOP LOSS: "+(d.plan_valid?DoubleToString(d.stop,p.digits):"N/A");
   rows[k++]="TAKE PROFIT: "+(d.plan_valid?DoubleToString(d.target,p.digits)+" ("+d.target_source+")":"N/A");
   rows[k++]="RISK/REWARD: "+(d.plan_valid?"1:"+DoubleToString(d.rr,2):"N/A");
   rows[k++]="VOLUME PROFILE: "+(d.ready?d.vp_text:"N/A");
   rows[k++]="WHY: "+d.reason;
   return k;
}

#define SVV_ROW_CHARS 78

#define SVV_WHY_LINES 3

// The panel. One label per row, evenly spaced, so two rows can never overlap.
// A long WHY wraps at word boundaries onto at most two extra lines instead of
// widening the panel. The panel sits in the chosen corner: distances are
// measured from that corner, a rectangle label is always anchored by its
// upper-left point, and text in a right-hand corner is right-anchored so it
// grows INTO the chart.
void SVV_DrawDashboard(const string symbol,const SSvpParams &p,const SSvvStyle &style,const string profile_tag)
{
   string rows[];
   int n=SVV_DashboardRows(g_svp,symbol,p,profile_tag,rows);
   if(!style.show_reason) n--;
   string lines[];
   int kind[];                                   // logical row each printed line belongs to
   ArrayResize(lines,n+SVV_WHY_LINES);
   ArrayResize(kind,n+SVV_WHY_LINES);
   int m=0;
   for(int i=0;i<n;i++)
   {
      if(i!=SVV_ROWS-1)
      {
         lines[m]=SVV_Clip(rows[i],SVV_ROW_CHARS); kind[m]=i; m++;
         continue;
      }
      // the reason: wrap, never widen
      string rest=rows[i];
      string indent="";
      for(int part=0;part<SVV_WHY_LINES;part++)
      {
         int room=SVV_ROW_CHARS-StringLen(indent);
         if(StringLen(rest)<=room || part==SVV_WHY_LINES-1)
         {
            lines[m]=indent+SVV_Clip(rest,room); kind[m]=i; m++;
            break;
         }
         int cut=room;
         for(int k=room;k>room/2;k--)
            if(StringSubstr(rest,k,1)==" ") { cut=k; break; }
         lines[m]=indent+StringSubstr(rest,0,cut); kind[m]=i; m++;
         rest=StringSubstr(rest,cut+(StringSubstr(rest,cut,1)==" "?1:0));
         indent="     ";
      }
   }
   int line=style.font_size+7;
   int width=0;
   for(int i=0;i<m;i++)
      if(StringLen(lines[i])>width) width=StringLen(lines[i]);
   int w=width*(style.font_size-1)+18;
   if(w<260) w=260;
   int h=m*line+12;
   bool right=(style.corner==2 || style.corner==3);
   bool lower=(style.corner==1 || style.corner==2);
   SVC_Panel("DASH_BG",SVC_LAYER_PRIMARY,style.corner,(right?style.x+w:style.x),(lower?style.y+h:style.y),w,h,
             style.panel_bg,style.panel_border);
   for(int i=0;i<m;i++)
   {
      color col=style.text;
      if(kind[i]==9) col=(g_svp.state==SVP_DECISION_BUY?style.bull:(g_svp.state==SVP_DECISION_SELL?style.bear:style.neutral));
      if(kind[i]==2) col=(g_svp.h4_bias>0?style.bull:(g_svp.h4_bias<0?style.bear:style.neutral));
      int y=(lower?style.y+h-6-i*line:style.y+6+i*line);
      SVC_Label("DASH_R"+IntegerToString(i),SVC_LAYER_PRIMARY,style.corner,style.x+8,y,lines[i],col,style.font_size,
                (right?ANCHOR_RIGHT_UPPER:ANCHOR_LEFT_UPPER));
   }
}

//====================================================================
// View: every layer, drawn through the manager
//====================================================================
// Captions must not print on top of each other. The layout model is
// deliberately simple and does not depend on the zoom, so the same data always
// gives the same chart:
//   * one caption character is SVV_BARS_PER_CHAR M15 bars wide;
//   * one caption line is g_svv_label_gap of price high (0.6 ATR);
//   * the anchor decides which way the text reaches from its point, exactly as
//     the terminal does (an UPPER anchor is the top of the text, a LEFT anchor
//     its left end).
// A caption whose rectangle would overlap one already placed in this pass is
// withheld. Captions are placed in the order of their importance (setup, market
// structure, liquidity, profile), so the more important one keeps its text; a
// withheld caption's LINE is still drawn and still explains itself in its
// tooltip. The model fits an M15 chart at the usual zoom; zoomed far out,
// captions can still come close to each other.
//
// Captions of LEVELS (entry / stop / target, liquidity, POC / VAH / VAL) all
// sit in one column that starts where every level line ends, to the right of
// the newest bar: no line reaches into it, so no caption is ever struck
// through. That column lives in the chart's right margin (Chart Shift).

// Position of a time on the M15 bar axis. Bars are counted, not minutes, so a
// weekend gap does not push two neighbouring captions apart; times to the right
// of the newest bar continue the count at one bar per 15 minutes.
double SVV_BarPos(const MqlRates &m15[],const int n,const datetime t)
{
   if(n<=0) return 0.0;
   if(t>=m15[n-1].time) return (double)(n-1)+(double)(t-m15[n-1].time)/900.0;
   if(t<=m15[0].time) return -(double)(m15[0].time-t)/900.0;
   int lo=0,hi=n-1;                    // m15[lo].time <= t < m15[hi].time
   while(hi-lo>1)
   {
      int mid=(lo+hi)/2;
      if(m15[mid].time<=t) lo=mid; else hi=mid;
   }
   return (double)lo;
}

// Width of a caption in characters. A caption that names a direction is given
// the room of the longer of its two spellings (BUY / SELL, up / down, low /
// high): a chart and its mirror image are then laid out identically, which is
// what the mirrored replay verifies object for object.
int SVV_CaptionChars(const string text)
{
   int chars=StringLen(text);
   if(StringFind(text,"BUY")==0) chars+=1;
   if(StringFind(text," up")>=0) chars+=2;
   if(StringFind(text," low")>=0) chars+=1;
   return chars;
}

// The rectangle a caption covers on the bar axis (x1..x2) and in price (lo..hi).
void SVV_CaptionBox(const MqlRates &m15[],const int n,const datetime t,const double price,const string text,
                    const ENUM_ANCHOR_POINT anchor,double &x1,double &x2,double &lo,double &hi)
{
   double w=SVV_BARS_PER_CHAR*(double)SVV_CaptionChars(text);
   double x=SVV_BarPos(m15,n,t);
   x1=x-0.5*w; x2=x+0.5*w;
   if(anchor==ANCHOR_LEFT_UPPER || anchor==ANCHOR_LEFT || anchor==ANCHOR_LEFT_LOWER) { x1=x; x2=x+w; }
   else if(anchor==ANCHOR_RIGHT_UPPER || anchor==ANCHOR_RIGHT || anchor==ANCHOR_RIGHT_LOWER) { x1=x-w; x2=x; }
   lo=price-0.5*g_svv_label_gap; hi=price+0.5*g_svv_label_gap;
   if(anchor==ANCHOR_LEFT_UPPER || anchor==ANCHOR_UPPER || anchor==ANCHOR_RIGHT_UPPER) { lo=price-g_svv_label_gap; hi=price; }
   else if(anchor==ANCHOR_LEFT_LOWER || anchor==ANCHOR_LOWER || anchor==ANCHOR_RIGHT_LOWER) { lo=price; hi=price+g_svv_label_gap; }
}

// true when no caption placed in this pass overlaps the rectangle
bool SVV_CaptionFree(const double x1,const double x2,const double lo,const double hi)
{
   if(g_svv_caps>=SVV_CAPTION_MAX) return false;        // no room left to remember it: do not risk an overlap
   for(int i=0;i<g_svv_caps;i++)
      if(x1<g_svv_cap_x2[i] && g_svv_cap_x1[i]<x2 && lo<g_svv_cap_hi[i] && g_svv_cap_lo[i]<hi) return false;
   return true;
}

void SVV_CaptionTake(const double x1,const double x2,const double lo,const double hi)
{
   if(g_svv_caps>=SVV_CAPTION_MAX) return;
   g_svv_cap_x1[g_svv_caps]=x1; g_svv_cap_x2[g_svv_caps]=x2;
   g_svv_cap_lo[g_svv_caps]=lo; g_svv_cap_hi[g_svv_caps]=hi;
   g_svv_caps++;
}

// Room for a caption; takes the place when it is free.
bool SVV_CaptionRoom(const MqlRates &m15[],const int n,const datetime t,const double price,const string text,
                     const ENUM_ANCHOR_POINT anchor)
{
   double x1,x2,lo,hi;
   SVV_CaptionBox(m15,n,t,price,text,anchor,x1,x2,lo,hi);
   if(!SVV_CaptionFree(x1,x2,lo,hi)) { g_svv_labels_hidden++; return false; }
   SVV_CaptionTake(x1,x2,lo,hi);
   return true;
}

// true when a horizontal line drawn in this pass runs through the inside of the
// rectangle (a line along its edge - the caption's own line - does not count)
bool SVV_LineThrough(const MqlRates &m15[],const int n,const double x1,const double x2,const double lo,const double hi)
{
   if(g_svc_edges_lost) return true;                    // not every line is known: do not risk it
   for(int i=0;i<g_svc_edges;i++)
   {
      if(!(g_svc_edge_price[i]>lo && g_svc_edge_price[i]<hi)) continue;
      double from=SVV_BarPos(m15,n,g_svc_edge_t1[i]),to=SVV_BarPos(m15,n,g_svc_edge_t2[i]);
      if(from<x2 && x1<to) return true;
   }
   return false;
}

// A caption that sits on a bar INSIDE the chart (a structure break, a finished
// signal, an old sweep) is not placed at once: lines drawn later in the pass
// could run through it. It is remembered here and placed by SVV_PlaceDeferred()
// when every line of the pass is known. `other` = the anchor to try when the
// preferred side is taken or crossed (the same anchor = no second try).
void SVV_Defer(const string id,const ENUM_SVC_LAYER layer,const string setup,const string state,const datetime t,
               const double price,const string text,const color col,const int font_size,
               const ENUM_ANCHOR_POINT anchor,const ENUM_ANCHOR_POINT other,const string tip)
{
   if(!g_svc_on[(int)layer]) return;
   if(g_svv_deferred>=SVV_DEFER_MAX) { g_svv_labels_hidden++; return; }
   int k=g_svv_deferred;
   g_svv_def_id[k]=id; g_svv_def_setup[k]=setup; g_svv_def_state[k]=state; g_svv_def_text[k]=text; g_svv_def_tip[k]=tip;
   g_svv_def_layer[k]=(int)layer; g_svv_def_anchor[k]=(int)anchor; g_svv_def_other[k]=(int)other;
   g_svv_def_font[k]=font_size; g_svv_def_color[k]=col; g_svv_def_time[k]=t; g_svv_def_price[k]=price;
   g_svv_deferred++;
}

// Places the deferred captions: on the preferred side of its point when that
// spot is free of captions AND of lines, else on the other side, else not at all.
void SVV_PlaceDeferred(const MqlRates &m15[],const int n)
{
   for(int k=0;k<g_svv_deferred;k++)
   {
      bool placed=false;
      for(int attempt=0;attempt<2 && !placed;attempt++)
      {
         int a=(attempt==0?g_svv_def_anchor[k]:g_svv_def_other[k]);
         if(attempt==1 && a==g_svv_def_anchor[k]) break;
         ENUM_ANCHOR_POINT anchor=(ENUM_ANCHOR_POINT)a;
         double x1,x2,lo,hi;
         SVV_CaptionBox(m15,n,g_svv_def_time[k],g_svv_def_price[k],g_svv_def_text[k],anchor,x1,x2,lo,hi);
         if(!SVV_CaptionFree(x1,x2,lo,hi) || SVV_LineThrough(m15,n,x1,x2,lo,hi)) continue;
         SVV_CaptionTake(x1,x2,lo,hi);
         SVC_Text(g_svv_def_id[k],(ENUM_SVC_LAYER)g_svv_def_layer[k],g_svv_def_setup[k],g_svv_def_state[k],
                  g_svv_def_time[k],g_svv_def_price[k],g_svv_def_text[k],g_svv_def_color[k],g_svv_def_font[k],
                  anchor,g_svv_def_tip[k]);
         placed=true;
      }
      if(!placed) g_svv_labels_hidden++;
   }
   g_svv_deferred=0;
}

// true when the primary layer already shows this price area as an entry zone
bool SVV_ZoneShown(const int dir,const double lo,const double hi)
{
   for(int i=0;i<g_svv_shown;i++)
      if(g_svv_shown_dir[i]==dir && g_svv_shown_lo[i]<=hi && g_svv_shown_hi[i]>=lo) return true;
   return false;
}

// 0 = a setup in play (confirmed or active: it carries a plan), 1 = a
// candidate, 2 = finished.
int SVV_SignalRank(const int idx)
{
   if(g_qsr[idx].state==QSR_STATE_CONFIRMED || g_qsr[idx].state==QSR_STATE_ACTIVE) return 0;
   if(QSR_IsLive(g_qsr[idx].state)) return 1;
   return 2;
}

// Drawing order of two registry slots: a total order (rank, then the newest
// first, then the later origin, then the slot), so the picture never depends
// on where a record happens to sit in the table.
bool SVV_SignalBefore(const int a,const int b)
{
   int ra=SVV_SignalRank(a),rb=SVV_SignalRank(b);
   if(ra!=rb) return ra<rb;
   if(g_qsr[a].first_seen!=g_qsr[b].first_seen) return g_qsr[a].first_seen>g_qsr[b].first_seen;
   if(g_qsr[a].origin_time!=g_qsr[b].origin_time) return g_qsr[a].origin_time>g_qsr[b].origin_time;
   if(g_qsr[a].direction!=g_qsr[b].direction) return g_qsr[a].direction>g_qsr[b].direction;
   return StringCompare(g_qsr[a].key,g_qsr[b].key)<0;
}

void SVV_DrawSignals(const MqlRates &m15[],const int n,const SSvpParams &p,const SSvvStyle &style)
{
   datetime now=m15[n-1].time;
   datetime right=now+(datetime)(8*900);
   // What matters most first, so the caps keep it: a setup in play (it has a
   // plan), then a candidate, then finished signals; newest first inside each.
   int order[QSR_CAPACITY];
   int m=0;
   for(int i=0;i<QSR_CAPACITY;i++)
      if(g_qsr[i].used) { order[m]=i; m++; }
   for(int i=1;i<m;i++)
   {
      int key=order[i]; int j=i-1;
      while(j>=0 && SVV_SignalBefore(key,order[j])) { order[j+1]=order[j]; j--; }
      order[j+1]=key;
   }
   int shown_history=0,shown_live=0;
   g_svv_shown=0;
   g_svv_signals_hidden=0;
   for(int k=0;k<m;k++)
   {
      int pick=order[k];
      string id=SVV_SignalId(g_qsr[pick].direction,g_qsr[pick].setup_type,g_qsr[pick].origin_time);
      string state=QSR_StateName(g_qsr[pick].state);
      string side=(g_qsr[pick].direction>0?"BUY":"SELL");
      color col=(g_qsr[pick].direction>0?style.bull:style.bear);
      string tip=side+" "+g_qsr[pick].setup_type+" | "+state+" | "+g_qsr[pick].note+
                 " | origin "+SVP_ClockText(g_qsr[pick].origin_time);
      if(QSR_IsLive(g_qsr[pick].state) && shown_live<style.live_signals)
      {
         double zlo=g_svv_zone_lo[pick],zhi=g_svv_zone_hi[pick];
         // One box per price area holds for setups too: a live signal whose
         // entry zone overlaps the zone of a more important live signal of the
         // same side stays off the chart until that one is over. It keeps its
         // record and its lifecycle in the registry; g_svv_signals_hidden counts
         // how many live signals this pass did not draw for that reason.
         if(zhi>zlo && SVV_ZoneShown(g_qsr[pick].direction,zlo,zhi))
         {
            g_svv_signals_hidden++;
            continue;
         }
         shown_live++;
         if(zhi>zlo)
         {
            bool drawn=SVC_Box(id+"_ZONE",SVC_LAYER_PRIMARY,id,state,g_qsr[pick].origin_time,zhi,right,zlo,col,false,
                               side+" entry zone "+DoubleToString(zlo,p.digits)+"-"+DoubleToString(zhi,p.digits)+" | "+state);
            if(drawn && g_svv_shown<SVV_SHOWN_MAX)
            {
               g_svv_shown_dir[g_svv_shown]=g_qsr[pick].direction;
               g_svv_shown_lo[g_svv_shown]=zlo; g_svv_shown_hi[g_svv_shown]=zhi;
               g_svv_shown++;
            }
         }
         // Captions sit in the column to the RIGHT of where every level line ends,
         // so no line can strike a caption through.
         if(g_qsr[pick].entry>0.0 && g_qsr[pick].stop>0.0 && g_qsr[pick].target>0.0)
         {
            // the three lines start on the bar that confirmed the setup and stay there
            datetime from=(g_svv_confirmed[pick]>0?g_svv_confirmed[pick]:g_qsr[pick].state_time);
            SVC_Segment(id+"_E",SVC_LAYER_PRIMARY,id,state,from,right,g_qsr[pick].entry,col,
                        STYLE_SOLID,1,"ENTRY "+DoubleToString(g_qsr[pick].entry,p.digits));
            SVC_Segment(id+"_SL",SVC_LAYER_PRIMARY,id,state,from,right,g_qsr[pick].stop,style.stop,
                        STYLE_DASH,1,"STOP LOSS "+DoubleToString(g_qsr[pick].stop,p.digits));
            SVC_Segment(id+"_TP",SVC_LAYER_PRIMARY,id,state,from,right,g_qsr[pick].target,style.target,
                        STYLE_DASH,1,"TAKE PROFIT "+DoubleToString(g_qsr[pick].target,p.digits));
            // The plan can be read off the chart: the entry caption is centred on
            // its line, the stop and target captions reach AWAY from the trade
            // (a BUY stop caption hangs below its line, its target caption stands
            // above), so the three never crowd each other.
            if(g_svc_on[(int)SVC_LAYER_PRIMARY])
            {
               bool buy=(g_qsr[pick].direction>0);
               string entry_text=side+" "+DoubleToString(g_qsr[pick].entry,p.digits);
               string stop_text="SL "+DoubleToString(g_qsr[pick].stop,p.digits);
               string target_text="TP "+DoubleToString(g_qsr[pick].target,p.digits);
               ENUM_ANCHOR_POINT stop_anchor=(buy?ANCHOR_LEFT_UPPER:ANCHOR_LEFT_LOWER);
               ENUM_ANCHOR_POINT target_anchor=(buy?ANCHOR_LEFT_LOWER:ANCHOR_LEFT_UPPER);
               if(SVV_CaptionRoom(m15,n,right,g_qsr[pick].entry,entry_text,ANCHOR_LEFT))
                  SVC_Text(id+"_TAG",SVC_LAYER_PRIMARY,id,state,right,g_qsr[pick].entry,entry_text,col,style.font_size,ANCHOR_LEFT,tip);
               if(SVV_CaptionRoom(m15,n,right,g_qsr[pick].stop,stop_text,stop_anchor))
                  SVC_Text(id+"_SLT",SVC_LAYER_PRIMARY,id,state,right,g_qsr[pick].stop,stop_text,style.stop,style.font_size,stop_anchor,
                           "STOP LOSS "+DoubleToString(g_qsr[pick].stop,p.digits)+" | "+tip);
               if(SVV_CaptionRoom(m15,n,right,g_qsr[pick].target,target_text,target_anchor))
                  SVC_Text(id+"_TPT",SVC_LAYER_PRIMARY,id,state,right,g_qsr[pick].target,target_text,style.target,style.font_size,target_anchor,
                           "TAKE PROFIT "+DoubleToString(g_qsr[pick].target,p.digits)+" | "+tip);
            }
         }
         else if(g_svc_on[(int)SVC_LAYER_PRIMARY])
         {
            // a candidate has no plan yet: one tag, level with the middle of its zone
            string tag=side+" candidate";
            double tag_price=(zhi>zlo ? 0.5*(zlo+zhi) : m15[n-1].close);
            if(SVV_CaptionRoom(m15,n,right,tag_price,tag,ANCHOR_LEFT))
               SVC_Text(id+"_TAG",SVC_LAYER_PRIMARY,id,state,right,tag_price,tag,col,style.font_size,ANCHOR_LEFT,
                        tip+" | awaiting the retest of its zone");
         }
         continue;
      }
      // a finished signal (or a live one beyond the cap): one small mark in the
      // optional layer, and only if it ever confirmed
      if(shown_history>=style.history_signals || !(g_qsr[pick].entry>0.0)) continue;
      shown_history++;
      if(!g_svc_on[(int)SVC_LAYER_OPTIONAL]) continue;
      datetime mark_time=(g_svv_confirmed[pick]>0?g_svv_confirmed[pick]:g_qsr[pick].first_seen);
      SVV_Defer(id+"_H",SVC_LAYER_OPTIONAL,id,state,mark_time,g_qsr[pick].entry,side+" "+state,col,style.font_size-1,
                ANCHOR_LEFT_LOWER,ANCHOR_LEFT_UPPER,tip);
   }
}

#define SVV_STR_MAX 5

// Structure marks: the newest break of H4, H1 and M15 (two older H1 breaks in
// the optional layer). One mark per BROKEN LEVEL: an H4 swing is also an H1
// swing, so both timeframes often break the same price on the same bar - that
// is one line and one caption ("H4+H1 BOS up"), not two captions printed on top
// of each other. A caption that would still collide with another one, or that a
// line would strike through, is withheld; its line stays.
void SVV_DrawStructureSet(const SSvpParams &p,const SSvvStyle &style)
{
   string          tf[SVV_STR_MAX];
   SSvpStructEvent ev[SVV_STR_MAX];
   int             layer[SVV_STR_MAX];
   bool            merged[SVV_STR_MAX];
   int m=0;
   int n4=ArraySize(g_svp_ev_h4),n1=ArraySize(g_svp_ev_h1),n15=ArraySize(g_svp_ev_m15);
   if(n4>0)  { tf[m]="H4";  ev[m]=g_svp_ev_h4[n4-1];   layer[m]=(int)SVC_LAYER_SECONDARY; m++; }
   if(n1>0)  { tf[m]="H1";  ev[m]=g_svp_ev_h1[n1-1];   layer[m]=(int)SVC_LAYER_SECONDARY; m++; }
   if(n15>0) { tf[m]="M15"; ev[m]=g_svp_ev_m15[n15-1]; layer[m]=(int)SVC_LAYER_SECONDARY; m++; }
   for(int back=1;back<=2 && n1-1-back>=0;back++)
   { tf[m]="H1"; ev[m]=g_svp_ev_h1[n1-1-back]; layer[m]=(int)SVC_LAYER_OPTIONAL; m++; }
   for(int i=0;i<m;i++) merged[i]=false;
   double same=0.5*p.tick_size;
   for(int i=0;i<m;i++)
   {
      if(merged[i]) continue;
      if(!g_svc_on[layer[i]]) continue;
      string dir=(ev[i].direction>0?" up":" down");
      string names=tf[i];
      string mixed=tf[i]+" "+SVP_EventText(ev[i].kind);
      string tip=tf[i]+" "+SVP_EventText(ev[i].kind)+dir+" @ "+DoubleToString(ev[i].level,p.digits);
      bool one_kind=true;
      datetime from=ev[i].swing_time,to=ev[i].break_time;
      for(int j=i+1;j<m;j++)
      {
         if(merged[j] || !g_svc_on[layer[j]] || ev[j].direction!=ev[i].direction || MathAbs(ev[j].level-ev[i].level)>same) continue;
         if(StringFind(names,tf[j])>=0) continue;           // an older break of a timeframe already named keeps its own mark
         merged[j]=true;
         names+="+"+tf[j];
         mixed+=" + "+tf[j]+" "+SVP_EventText(ev[j].kind);
         tip+=" | "+tf[j]+" "+SVP_EventText(ev[j].kind)+dir+" @ "+DoubleToString(ev[j].level,p.digits);
         if(ev[j].kind!=ev[i].kind) one_kind=false;
         if(ev[j].swing_time<from) from=ev[j].swing_time;
         if(ev[j].break_time>to) to=ev[j].break_time;
      }
      string text=(one_kind ? names+" "+SVP_EventText(ev[i].kind)+dir : mixed+dir);
      string id="STR_"+tf[i]+"_"+IntegerToString((long)ev[i].break_time);
      ENUM_SVC_LAYER lay=(ENUM_SVC_LAYER)layer[i];
      color col=(ev[i].direction>0?style.bull:style.bear);
      SVC_Segment(id+"_L",lay,id,text,from,to,ev[i].level,col,STYLE_DOT,1,tip);
      // the caption stands on its line for a break up and hangs under it for a
      // break down; when that side is taken or a line runs through it, the other
      SVV_Defer(id+"_T",lay,id,text,to,ev[i].level,text,col,style.font_size-1,
                (ev[i].direction>0?ANCHOR_RIGHT_LOWER:ANCHOR_RIGHT_UPPER),
                (ev[i].direction>0?ANCHOR_RIGHT_UPPER:ANCHOR_RIGHT_LOWER),tip);
   }
}

void SVV_DrawLiquidity(const MqlRates &m15[],const int n,const SSvpParams &p,const SSvvStyle &style)
{
   double price=m15[n-1].close;
   datetime right=m15[n-1].time+(datetime)(8*900);
   int zc=ArraySize(g_svp_liq);
   for(int side=-1;side<=1;side+=2)
   {
      double floor_level=0.0;
      for(int rank=0;rank<style.liq_per_side;rank++)
      {
         // nearest intact zone beyond the ones already drawn
         int best=-1;
         for(int i=0;i<zc;i++)
         {
            if(g_svp_liq[i].side!=side || g_svp_liq[i].taken_index>=0) continue;
            double dist=(double)side*(g_svp_liq[i].level-price);
            if(dist<=0.0 || dist<=floor_level) continue;
            if(best<0 || dist<(double)side*(g_svp_liq[best].level-price)) best=i;
         }
         if(best<0) break;
         floor_level=(double)side*(g_svp_liq[best].level-price);
         string id="LIQ_"+(side>0?"B":"S")+IntegerToString(rank);
         string text=(side>0?"BSL ":"SSL ")+g_svp_liq[best].label;
         string tip=text+" "+DoubleToString(g_svp_liq[best].lo,p.digits)+"-"+DoubleToString(g_svp_liq[best].hi,p.digits)+
                    " | strength "+IntegerToString(g_svp_liq[best].strength)+" | "+g_svp_liq[best].id;
         SVC_Segment(id+"_L",SVC_LAYER_SECONDARY,g_svp_liq[best].id,"INTACT",g_svp_liq[best].formed_time,right,
                     g_svp_liq[best].level,style.liquidity,STYLE_DASHDOT,1,tip);
         // caption in the right-hand column, level with the end of its line
         if(g_svc_on[(int)SVC_LAYER_SECONDARY] && SVV_CaptionRoom(m15,n,right,g_svp_liq[best].level,text,ANCHOR_LEFT))
            SVC_Text(id+"_T",SVC_LAYER_SECONDARY,g_svp_liq[best].id,"INTACT",right,g_svp_liq[best].level,text,
                     style.liquidity,style.font_size-1,ANCHOR_LEFT,tip);
      }
   }
   // old sweeps: optional layer, newest first
   int sc=ArraySize(g_svp_sweeps);
   for(int i=0;i<sc && i<style.history_sweeps;i++)
   {
      string id="SWP_"+IntegerToString((long)g_svp_sweeps[i].take_time)+(g_svp_sweeps[i].side>0?"B":"S");
      string text=(g_svp_sweeps[i].side>0?"BSL ":"SSL ")+SVP_SweepStateText(g_svp_sweeps[i].state);
      ENUM_ANCHOR_POINT anchor=(g_svp_sweeps[i].side>0?ANCHOR_LOWER:ANCHOR_UPPER);
      SVV_Defer(id,SVC_LAYER_OPTIONAL,g_svp_sweeps[i].id,SVP_SweepStateText(g_svp_sweeps[i].state),
                g_svp_sweeps[i].take_time,g_svp_sweeps[i].extreme,text,style.neutral,style.font_size-2,
                anchor,anchor,SVP_SweepText(g_svp_sweeps[i],p.digits)+" | "+g_svp_sweeps[i].note);
   }
}


// Nearest alive zones on each side. One box per PRICE AREA: alive zones of one
// direction that overlap are drawn as their union, and an area the tracked
// setup already shows as its entry zone is not drawn a second time.
void SVV_DrawZones(const MqlRates &m15[],const int n,const SSvpParams &p,const SSvvStyle &style)
{
   double price=m15[n-1].close;
   datetime right=m15[n-1].time+(datetime)(8*900);
   int zc=ArraySize(g_svp_zones);
   if(zc>SVP_ZONE_MAX) zc=SVP_ZONE_MAX;
   bool used[SVP_ZONE_MAX];
   for(int dir=-1;dir<=1;dir+=2)
   {
      for(int i=0;i<SVP_ZONE_MAX;i++) used[i]=false;
      int drawn=0;
      while(drawn<style.zones_per_side)
      {
         // nearest ALIVE zone on its natural side of price (demand below, supply above)
         int best=-1;
         double best_dist=0.0;
         for(int i=0;i<zc;i++)
         {
            if(used[i] || g_svp_zones[i].direction!=dir || !SVP_ZoneAlive(g_svp_zones[i])) continue;
            double edge=(dir>0?g_svp_zones[i].hi:g_svp_zones[i].lo);
            double dist=(double)dir*(price-edge);
            if(dist<0.0) dist=0.0;                       // price is inside the zone
            if(best<0 || dist<best_dist) { best=i; best_dist=dist; }
         }
         if(best<0) break;
         used[best]=true;
         double lo=g_svp_zones[best].lo,hi=g_svp_zones[best].hi;
         datetime origin=g_svp_zones[best].origin_time;
         int members=1;
         bool grew=true;
         while(grew)
         {
            grew=false;
            for(int i=0;i<zc;i++)
            {
               if(used[i] || g_svp_zones[i].direction!=dir || !SVP_ZoneAlive(g_svp_zones[i])) continue;
               if(g_svp_zones[i].lo>hi || g_svp_zones[i].hi<lo) continue;
               used[i]=true; members++; grew=true;
               if(g_svp_zones[i].lo<lo) lo=g_svp_zones[i].lo;
               if(g_svp_zones[i].hi>hi) hi=g_svp_zones[i].hi;
               if(g_svp_zones[i].origin_time<origin) origin=g_svp_zones[i].origin_time;
            }
         }
         if(SVV_ZoneShown(dir,lo,hi)) continue;
         string id="ZN_"+(dir>0?"B":"S")+IntegerToString(drawn);
         string text=SVP_ZoneText(g_svp_zones[best],p.digits);
         if(members>1)
            text+=" | area "+DoubleToString(lo,p.digits)+"-"+DoubleToString(hi,p.digits)+" ("+
                  IntegerToString(members)+" overlapping zones shown as one)";
         SVC_Box(id,SVC_LAYER_SECONDARY,g_svp_zones[best].id,SVP_ZoneStateText(g_svp_zones[best].state),
                 origin,hi,right,lo,(dir>0?style.bull:style.bear),false,text+" | "+g_svp_zones[best].id);
         drawn++;
      }
   }
}

// true when a profile node lies on the POC, VAH or VAL line (closer than half a row)
bool SVV_OnProfileLevel(const double price)
{
   double half_row=0.5*g_svp_profile.bin_size;
   return (MathAbs(price-g_svp_profile.poc)<half_row || MathAbs(price-g_svp_profile.vah)<half_row ||
           MathAbs(price-g_svp_profile.val)<half_row);
}

// what else a profile line is: " (also HVN)" / " (also LVN)" for the tooltip
string SVV_ProfileNodeNote(const double price,const int nodes)
{
   double half_row=0.5*g_svp_profile.bin_size;
   for(int i=0;i<g_svp_profile.hvn_count && i<nodes;i++)
      if(MathAbs(price-g_svp_profile.hvn[i])<half_row) return " (also HVN)";
   for(int i=0;i<g_svp_profile.lvn_count && i<nodes;i++)
      if(MathAbs(price-g_svp_profile.lvn[i])<half_row) return " (also LVN)";
   return "";
}

void SVV_DrawProfile(const MqlRates &m15[],const int n,const SSvpParams &p,const SSvvStyle &style)
{
   if(!g_svp_profile.valid) return;
   datetime left=g_svp_profile.first_bar;
   datetime right=m15[n-1].time+(datetime)(8*900);
   string kind=SVP_VpKindText(g_svp_profile.kind)+(g_svp_profile_previous?" (previous)":"");
   string basis=" | "+g_svp_profile.basis;
   SVC_Segment("VP_POC",SVC_LAYER_VOLUME,"PROFILE",kind,left,right,g_svp_profile.poc,style.poc,STYLE_SOLID,2,
               kind+" POC "+DoubleToString(g_svp_profile.poc,p.digits)+basis);
   SVC_Segment("VP_VAH",SVC_LAYER_VOLUME,"PROFILE",kind,left,right,g_svp_profile.vah,style.value_area,STYLE_DASH,1,
               kind+" VAH "+DoubleToString(g_svp_profile.vah,p.digits)+SVV_ProfileNodeNote(g_svp_profile.vah,style.nodes)+basis);
   SVC_Segment("VP_VAL",SVC_LAYER_VOLUME,"PROFILE",kind,left,right,g_svp_profile.val,style.value_area,STYLE_DASH,1,
               kind+" VAL "+DoubleToString(g_svp_profile.val,p.digits)+SVV_ProfileNodeNote(g_svp_profile.val,style.nodes)+basis);
   if(g_svc_on[(int)SVC_LAYER_VOLUME] && SVV_CaptionRoom(m15,n,right,g_svp_profile.poc,"POC",ANCHOR_LEFT))
      SVC_Text("VP_POC_T",SVC_LAYER_VOLUME,"PROFILE",kind,right,g_svp_profile.poc,"POC",style.poc,style.font_size-1,ANCHOR_LEFT,kind+basis);
   if(g_svc_on[(int)SVC_LAYER_VOLUME] && SVV_CaptionRoom(m15,n,right,g_svp_profile.vah,"VAH",ANCHOR_LEFT))
      SVC_Text("VP_VAH_T",SVC_LAYER_VOLUME,"PROFILE",kind,right,g_svp_profile.vah,"VAH",style.value_area,style.font_size-1,ANCHOR_LEFT,kind+basis);
   if(g_svc_on[(int)SVC_LAYER_VOLUME] && SVV_CaptionRoom(m15,n,right,g_svp_profile.val,"VAL",ANCHOR_LEFT))
      SVC_Text("VP_VAL_T",SVC_LAYER_VOLUME,"PROFILE",kind,right,g_svp_profile.val,"VAL",style.value_area,style.font_size-1,ANCHOR_LEFT,kind+basis);
   // a node that sits on the POC or on a value-area edge is already a line
   for(int i=0;i<g_svp_profile.hvn_count && i<style.nodes;i++)
      if(!SVV_OnProfileLevel(g_svp_profile.hvn[i]))
         SVC_Segment("VP_HVN"+IntegerToString(i),SVC_LAYER_VOLUME,"PROFILE",kind,left,right,g_svp_profile.hvn[i],style.node,
                     STYLE_DOT,1,"HVN "+DoubleToString(g_svp_profile.hvn[i],p.digits)+basis);
   for(int i=0;i<g_svp_profile.lvn_count && i<style.nodes;i++)
      if(!SVV_OnProfileLevel(g_svp_profile.lvn[i]))
         SVC_Segment("VP_LVN"+IntegerToString(i),SVC_LAYER_VOLUME,"PROFILE",kind,left,right,g_svp_profile.lvn[i],style.node,
                     STYLE_DASHDOTDOT,1,"LVN "+DoubleToString(g_svp_profile.lvn[i],p.digits)+basis);
   // histogram: at most histogram_rows rows, each the sum of whole bins
   int rows=style.histogram_rows;
   if(rows<=0 || !g_svc_on[(int)SVC_LAYER_DETAIL]) return;
   int per=(g_svp_profile.bin_count+rows-1)/rows;
   if(per<1) per=1;
   double peak=0.0;
   for(int b=0;b<g_svp_profile.bin_count;b+=per)
   {
      double v=0.0;
      for(int k=b;k<b+per && k<g_svp_profile.bin_count;k++) v+=g_svp_profile.bins[k];
      if(v>peak) peak=v;
   }
   if(!(peak>0.0)) return;
   datetime span=(datetime)(24*900);
   int row=0;
   for(int b=0;b<g_svp_profile.bin_count;b+=per)
   {
      double v=0.0;
      int top=b+per;
      if(top>g_svp_profile.bin_count) top=g_svp_profile.bin_count;
      for(int k=b;k<top;k++) v+=g_svp_profile.bins[k];
      double lo=g_svp_profile.origin+(double)b*g_svp_profile.bin_size;
      double hi=g_svp_profile.origin+(double)top*g_svp_profile.bin_size;
      datetime t2=left+(datetime)MathRound((double)span*v/peak);
      bool in_value=(hi>g_svp_profile.val && lo<g_svp_profile.vah);
      if(v>0.0)
         SVC_Box("VP_H"+IntegerToString(row),SVC_LAYER_DETAIL,"PROFILE",kind,left,hi,t2,lo,
                 (in_value?style.value_area:style.node),true,
                 DoubleToString(lo,p.digits)+"-"+DoubleToString(hi,p.digits)+" volume "+DoubleToString(v,0));
      row++;
   }
}

// One refresh pass: every layer, then the stale objects go.
void SVV_Render(const MqlRates &m15[],const int n,const string symbol,const SSvpParams &p,const SSvvStyle &style)
{
   SVC_Begin();
   g_svv_caps=0; g_svv_labels_hidden=0; g_svv_deferred=0;
   g_svv_label_gap=0.0;
   if(g_svp.ready && n>0 && ArraySize(g_svp_atr_m15)>=n) g_svv_label_gap=0.60*g_svp_atr_m15[n-1];
   string tag="N/A";
   if(g_svp_profile.valid)
      tag="("+SVP_VpKindText(g_svp_profile.kind)+(g_svp_profile_previous?" previous":"")+", "+
          (g_svp_profile.real_volume?"real volume":"tick volume")+")";
   SVV_DrawDashboard(symbol,p,style,tag);
   if(g_svp.ready && n>0)
   {
      SVV_DrawSignals(m15,n,p,style);
      SVV_DrawStructureSet(p,style);
      SVV_DrawLiquidity(m15,n,p,style);
      SVV_DrawZones(m15,n,p,style);
      SVV_DrawProfile(m15,n,p,style);
      SVV_PlaceDeferred(m15,n);          // captions inside the chart, now that every line is known
   }
   SVC_End();
}

#endif
//+------------------------------------------------------------------+
