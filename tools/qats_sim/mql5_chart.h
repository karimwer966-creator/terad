// mql5_chart.h - chart-object, series-copy and indicator plumbing add-on for the
// typed MQL5 shim (mql5_shim.h). Used by the QSMC SMC + Volume Profile hosts.
//
// NOT MetaTrader. It mirrors the MQL5 signatures closely enough that the host
// compiler type-checks every call the way MetaEditor would (an OBJPROP_PRICE fed
// to ObjectSetInteger does not compile), and it records what the code under test
// did to "the chart" so a test can assert it: how many objects exist, how many
// were created / deleted / rewritten, and that nothing outside the program's own
// prefix was touched.
#ifndef QATS_MQL5_CHART_H
#define QATS_MQL5_CHART_H

#include <cfloat>
#include <climits>

// ------------------------------------------------------------------ colours
#define clrNONE            (-1)
#define clrBlack           0x000000
#define clrWhite           0xFFFFFF
#define clrRed             0x0000FF
#define clrLime            0x00FF00
#define clrBlue            0xFF0000
#define clrYellow          0x00FFFF
#define clrAqua            0xFFFF00
#define clrMagenta         0xFF00FF
#define clrGold            0x00D7FF
#define clrOrange          0x00A5FF
#define clrOrangeRed       0x0045FF
#define clrTomato          0x4763FF
#define clrCrimson         0x3C14DC
#define clrFireBrick       0x2222B2
#define clrLightCoral      0x8080F0
#define clrSilver          0xC0C0C0
#define clrGray            0x808080
#define clrDimGray         0x696969
#define clrDarkGray        0xA9A9A9
#define clrSlateGray       0x908070
#define clrDarkSlateGray   0x4F4F2F
#define clrLimeGreen       0x32CD32
#define clrForestGreen     0x228B22
#define clrSeaGreen        0x578B2E
#define clrMediumSeaGreen  0x71B33C
#define clrDarkSeaGreen    0x8BBC8F
#define clrDodgerBlue      0xFF901E
#define clrDeepSkyBlue     0xFFBF00
#define clrRoyalBlue       0xE16941
#define clrSteelBlue       0xB48246
#define clrMidnightBlue    0x701919
#define clrKhaki           0x8CE6F0
#define clrViolet          0xEE82EE
#define clrMediumPurple    0xDB7093
#define clrGoldenrod       0x20A5DA

// ------------------------------------------------------------------ enums
enum ENUM_OBJECT : int
{
   OBJ_VLINE = 0, OBJ_HLINE = 1, OBJ_TREND = 2, OBJ_RECTANGLE = 16, OBJ_ARROW = 22,
   OBJ_TEXT = 100, OBJ_LABEL = 101, OBJ_RECTANGLE_LABEL = 110, OBJ_ARROWED_LINE = 108
};
enum ENUM_OBJECT_PROPERTY_INTEGER : int
{
   OBJPROP_COLOR = 6, OBJPROP_STYLE = 7, OBJPROP_WIDTH = 8, OBJPROP_BACK = 9, OBJPROP_ZORDER = 207,
   OBJPROP_FILL = 1031, OBJPROP_HIDDEN = 208, OBJPROP_SELECTED = 17, OBJPROP_TYPE = 18,
   OBJPROP_TIME = 19, OBJPROP_SELECTABLE = 1000, OBJPROP_CREATETIME = 998, OBJPROP_FONTSIZE = 100,
   OBJPROP_RAY_LEFT = 1003, OBJPROP_RAY_RIGHT = 1004, OBJPROP_ARROWCODE = 14, OBJPROP_TIMEFRAMES = 15,
   OBJPROP_ANCHOR = 1011, OBJPROP_XDISTANCE = 102, OBJPROP_YDISTANCE = 103, OBJPROP_XSIZE = 1019,
   OBJPROP_YSIZE = 1020, OBJPROP_CORNER = 101, OBJPROP_BGCOLOR = 1025, OBJPROP_BORDER_TYPE = 1029,
   OBJPROP_BORDER_COLOR = 1035, OBJPROP_ALIGN = 1036
};
enum ENUM_OBJECT_PROPERTY_DOUBLE : int { OBJPROP_PRICE = 20, OBJPROP_ANGLE = 13, OBJPROP_SCALE = 12 };
enum ENUM_OBJECT_PROPERTY_STRING : int { OBJPROP_NAME = 1002, OBJPROP_TEXT = 999, OBJPROP_TOOLTIP = 206, OBJPROP_FONT = 1001 };
enum ENUM_BASE_CORNER : int { CORNER_LEFT_UPPER = 0, CORNER_LEFT_LOWER = 1, CORNER_RIGHT_LOWER = 2, CORNER_RIGHT_UPPER = 3 };
enum ENUM_ANCHOR_POINT : int
{
   ANCHOR_LEFT_UPPER = 0, ANCHOR_LEFT = 1, ANCHOR_LEFT_LOWER = 2, ANCHOR_LOWER = 3, ANCHOR_RIGHT_LOWER = 4,
   ANCHOR_RIGHT = 5, ANCHOR_RIGHT_UPPER = 6, ANCHOR_UPPER = 7, ANCHOR_CENTER = 8
};
enum ENUM_ARROW_ANCHOR : int { ANCHOR_TOP = 0, ANCHOR_BOTTOM = 1 };
enum ENUM_LINE_STYLE : int { STYLE_SOLID = 0, STYLE_DASH = 1, STYLE_DOT = 2, STYLE_DASHDOT = 3, STYLE_DASHDOTDOT = 4 };
enum ENUM_BORDER_TYPE : int { BORDER_FLAT = 0, BORDER_RAISED = 1, BORDER_SUNKEN = 2 };
enum ENUM_ALIGN_MODE : int { ALIGN_LEFT = 1, ALIGN_CENTER = 2, ALIGN_RIGHT = 0 };
#define OBJ_ALL_PERIODS 0x001fffff
#define OBJ_NO_PERIODS  0

enum ENUM_CHART_PROPERTY_INTEGER : int
{
   CHART_FIRST_VISIBLE_BAR = 104, CHART_VISIBLE_BARS = 100, CHART_WIDTH_IN_BARS = 105,
   CHART_WIDTH_IN_PIXELS = 106, CHART_HEIGHT_IN_PIXELS = 107, CHART_COLOR_BACKGROUND = 21,
   CHART_FOREGROUND = 1, CHART_SHIFT = 2, CHART_AUTOSCROLL = 4
};
enum ENUM_INDEXBUFFER_TYPE : int { INDICATOR_DATA = 0, INDICATOR_COLOR_INDEX = 1, INDICATOR_CALCULATIONS = 2 };
enum ENUM_PLOT_PROPERTY_INTEGER : int { PLOT_ARROW = 0, PLOT_DRAW_BEGIN = 2, PLOT_DRAW_TYPE = 3, PLOT_SHOW_DATA = 4, PLOT_LINE_COLOR = 9 };
enum ENUM_PLOT_PROPERTY_DOUBLE : int { PLOT_EMPTY_VALUE = 0 };
enum ENUM_PLOT_PROPERTY_STRING : int { PLOT_LABEL = 0 };
enum ENUM_DRAW_TYPE : int { DRAW_NONE = 0, DRAW_LINE = 1, DRAW_ARROW = 3 };
enum ENUM_CUSTOMIND_PROPERTY_INTEGER : int { INDICATOR_DIGITS = 0, INDICATOR_HEIGHT = 1, INDICATOR_LEVELS = 2 };
enum ENUM_CUSTOMIND_PROPERTY_STRING : int { INDICATOR_SHORTNAME = 0, INDICATOR_LEVELTEXT = 1 };
enum ENUM_CHART_EVENT : int { CHARTEVENT_KEYDOWN = 0, CHARTEVENT_OBJECT_CLICK = 1, CHARTEVENT_CHART_CHANGE = 9 };

#define REASON_PROGRAM     0
#define REASON_REMOVE      1
#define REASON_RECOMPILE   2
#define REASON_CHARTCHANGE 3
#define REASON_CHARTCLOSE  4
#define REASON_PARAMETERS  5

// ------------------------------------------------------------------ the chart
namespace chartsim
{
struct Obj
{
   ENUM_OBJECT type = OBJ_HLINE;
   datetime t[3] = {0, 0, 0};
   double p[3] = {0.0, 0.0, 0.0};
   std::map<int, long> ints;
   std::map<int, double> dbls;
   std::map<int, std::string> strs;
   long serial = 0;                 // creation order
};

struct Chart
{
   std::map<std::string, Obj> objects;
   std::vector<std::string> order;  // creation order (ObjectName enumerates it)
   long created = 0, deleted = 0, moved = 0, propWrites = 0, redraws = 0, createFailed = 0;
   long nextSerial = 1;
   int firstVisibleBar = 200, visibleBars = 200, widthPx = 1600, heightPx = 900;
   bool shift = true;                // CHART_SHIFT: the margin right of the newest bar (the terminal's default is on)
   int shiftSets = 0;                // ChartSetInteger(CHART_SHIFT) calls
   std::vector<std::string> alerts;
   std::vector<std::string> deletedNames;
};
inline Chart C;

inline void resetCounters() { C.created = C.deleted = C.moved = C.propWrites = C.redraws = C.createFailed = 0; C.deletedNames.clear(); }
inline void resetAll() { C = Chart(); }
inline long countPrefix(const std::string &prefix)
{
   long n = 0;
   for(const auto &kv : C.objects) if(kv.first.compare(0, prefix.size(), prefix) == 0) n++;
   return n;
}
inline long countType(const std::string &prefix, ENUM_OBJECT type)
{
   long n = 0;
   for(const auto &kv : C.objects) if(kv.first.compare(0, prefix.size(), prefix) == 0 && kv.second.type == type) n++;
   return n;
}
inline Obj *find(const std::string &name)
{
   auto it = C.objects.find(name);
   return it == C.objects.end() ? nullptr : &it->second;
}
inline void erase(const std::string &name)
{
   C.objects.erase(name);
   C.order.erase(std::remove(C.order.begin(), C.order.end(), name), C.order.end());
   C.deleted++;
   C.deletedNames.push_back(name);
}
// A "user" object: created behind the program's back, never counted as its work.
inline void addUserObject(const std::string &name, ENUM_OBJECT type, datetime t, double p)
{
   Obj o; o.type = type; o.t[0] = t; o.p[0] = p; o.serial = C.nextSerial++;
   C.objects[name] = o; C.order.push_back(name);
}
}  // namespace chartsim

// MQL5 StringCompare: -1, 0 or 1, by character codes.
inline int StringCompare(const string &a, const string &b, const bool case_sensitive = true)
{
   std::string x(a), y(b);
   if(!case_sensitive)
   {
      for(char &c : x) c = (char)std::tolower((unsigned char)c);
      for(char &c : y) c = (char)std::tolower((unsigned char)c);
   }
   const int r = x.compare(y);
   return r < 0 ? -1 : (r > 0 ? 1 : 0);
}

inline long ChartID() { return 0; }
inline bool ChartRedraw(const long chart_id = 0) { (void)chart_id; chartsim::C.redraws++; return true; }
inline long ChartGetInteger(const long chart_id, const ENUM_CHART_PROPERTY_INTEGER prop, const int sub_window = 0)
{
   (void)chart_id; (void)sub_window;
   switch(prop)
   {
      case CHART_FIRST_VISIBLE_BAR: return chartsim::C.firstVisibleBar;
      case CHART_VISIBLE_BARS: case CHART_WIDTH_IN_BARS: return chartsim::C.visibleBars;
      case CHART_WIDTH_IN_PIXELS: return chartsim::C.widthPx;
      case CHART_HEIGHT_IN_PIXELS: return chartsim::C.heightPx;
      case CHART_SHIFT: return chartsim::C.shift ? 1 : 0;
      default: return 0;
   }
}
inline bool ChartSetInteger(const long chart_id, const ENUM_CHART_PROPERTY_INTEGER prop, const long value)
{
   (void)chart_id;
   if(prop == CHART_SHIFT) { chartsim::C.shift = (value != 0); chartsim::C.shiftSets++; }
   return true;
}

inline bool ObjectCreate(const long chart_id, const string name, const ENUM_OBJECT type, const int sub_window,
                         const datetime t1, const double p1, const datetime t2 = 0, const double p2 = 0.0,
                         const datetime t3 = 0, const double p3 = 0.0)
{
   (void)chart_id; (void)sub_window;
   if(name.empty() || chartsim::C.objects.count(name)) { chartsim::C.createFailed++; return false; }
   chartsim::Obj o; o.type = type; o.t[0] = t1; o.p[0] = p1; o.t[1] = t2; o.p[1] = p2; o.t[2] = t3; o.p[2] = p3;
   o.serial = chartsim::C.nextSerial++;
   o.ints[OBJPROP_CREATETIME] = (long)sim::S.now;
   chartsim::C.objects[name] = o;
   chartsim::C.order.push_back(name);
   chartsim::C.created++;
   return true;
}
inline int ObjectFind(const long chart_id, const string name) { (void)chart_id; return chartsim::C.objects.count(name) ? 0 : -1; }
inline bool ObjectDelete(const long chart_id, const string name)
{
   (void)chart_id;
   if(!chartsim::C.objects.count(name)) return false;
   chartsim::erase(name);
   return true;
}
inline int ObjectsDeleteAll(const long chart_id, const string prefix, const int sub_window = -1, const int object_type = -1)
{
   (void)chart_id; (void)sub_window;
   std::vector<std::string> victims;
   for(const auto &kv : chartsim::C.objects)
      if(kv.first.compare(0, prefix.size(), prefix) == 0 && (object_type < 0 || (int)kv.second.type == object_type))
         victims.push_back(kv.first);
   for(const auto &n : victims) chartsim::erase(n);
   return (int)victims.size();
}
inline int ObjectsTotal(const long chart_id, const int sub_window = -1, const int type = -1)
{
   (void)chart_id; (void)sub_window;
   if(type < 0) return (int)chartsim::C.order.size();
   int n = 0;
   for(const auto &kv : chartsim::C.objects) if((int)kv.second.type == type) n++;
   return n;
}
inline string ObjectName(const long chart_id, const int pos, const int sub_window = -1, const int type = -1)
{
   (void)chart_id; (void)sub_window; (void)type;
   if(pos < 0 || pos >= (int)chartsim::C.order.size()) return "";
   return chartsim::C.order[(size_t)pos];
}
inline bool ObjectMove(const long chart_id, const string name, const int point_index, const datetime time, const double price)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o || point_index < 0 || point_index > 2) return false;
   o->t[point_index] = time; o->p[point_index] = price;
   chartsim::C.moved++;
   return true;
}
inline bool ObjectSetInteger(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_INTEGER prop, const long value)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return false;
   if(prop == OBJPROP_TIME) o->t[0] = (datetime)value; else o->ints[(int)prop] = value;
   chartsim::C.propWrites++;
   return true;
}
inline bool ObjectSetInteger(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_INTEGER prop, const int modifier, const long value)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return false;
   if(prop == OBJPROP_TIME && modifier >= 0 && modifier <= 2) o->t[modifier] = (datetime)value; else o->ints[(int)prop * 8 + modifier] = value;
   chartsim::C.propWrites++;
   return true;
}
inline bool ObjectSetDouble(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_DOUBLE prop, const double value)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return false;
   if(prop == OBJPROP_PRICE) o->p[0] = value; else o->dbls[(int)prop] = value;
   chartsim::C.propWrites++;
   return true;
}
inline bool ObjectSetDouble(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_DOUBLE prop, const int modifier, const double value)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return false;
   if(prop == OBJPROP_PRICE && modifier >= 0 && modifier <= 2) o->p[modifier] = value; else o->dbls[(int)prop * 8 + modifier] = value;
   chartsim::C.propWrites++;
   return true;
}
inline bool ObjectSetString(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_STRING prop, const string value)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return false;
   o->strs[(int)prop] = value;
   chartsim::C.propWrites++;
   return true;
}
inline long ObjectGetInteger(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_INTEGER prop, const int modifier = 0)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return 0;
   if(prop == OBJPROP_TYPE) return (long)o->type;
   if(prop == OBJPROP_TIME) return (modifier >= 0 && modifier <= 2) ? (long)o->t[modifier] : 0;
   auto it = o->ints.find((int)prop);
   return it == o->ints.end() ? 0 : it->second;
}
inline double ObjectGetDouble(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_DOUBLE prop, const int modifier = 0)
{
   (void)chart_id;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return 0.0;
   if(prop == OBJPROP_PRICE) return (modifier >= 0 && modifier <= 2) ? o->p[modifier] : 0.0;
   auto it = o->dbls.find((int)prop);
   return it == o->dbls.end() ? 0.0 : it->second;
}
inline string ObjectGetString(const long chart_id, const string name, const ENUM_OBJECT_PROPERTY_STRING prop, const int modifier = 0)
{
   (void)chart_id; (void)modifier;
   chartsim::Obj *o = chartsim::find(name);
   if(!o) return "";
   if(prop == OBJPROP_NAME) return name;
   auto it = o->strs.find((int)prop);
   return it == o->strs.end() ? "" : it->second;
}

// ------------------------------------------------------------------ series
inline int PeriodSeconds(const ENUM_TIMEFRAMES tf = PERIOD_CURRENT)
{
   ENUM_TIMEFRAMES p = (tf == PERIOD_CURRENT ? _Period : tf);
   switch(p)
   {
      case PERIOD_M1: return 60;
      case PERIOD_M5: return 300;
      case PERIOD_M15: return 900;
      case PERIOD_M30: return 1800;
      case PERIOD_H1: return 3600;
      case PERIOD_H4: return 14400;
      case PERIOD_D1: return 86400;
      case PERIOD_W1: return 604800;
      default: return 0;
   }
}
inline int Bars(const string symbol, const ENUM_TIMEFRAMES tf)
{
   sim::Series *s = sim::seriesFor(symbol, tf == PERIOD_CURRENT ? _Period : tf);
   return s ? s->size() : 0;
}
// start_pos counts back from the forming bar (0), like MQL5; the copy is oldest-first.
inline int CopyRates(const string symbol, const ENUM_TIMEFRAMES tf, const int start_pos, const int count, MqlArray<MqlRates> &rates)
{
   sim::Series *s = sim::seriesFor(symbol, tf == PERIOD_CURRENT ? _Period : tf);
   if(!s || start_pos < 0 || count <= 0) return -1;
   int n = s->size();
   int last = n - 1 - start_pos;              // index of the newest bar copied
   if(last < 0) return -1;
   int first = last - count + 1;
   if(first < 0) first = 0;
   int got = last - first + 1;
   rates.v.resize((size_t)got);
   for(int i = 0; i < got; i++)
   {
      const sim::Bar &b = s->bars[(size_t)(first + i)];
      MqlRates r{};
      r.time = b.time; r.open = b.open; r.high = b.high; r.low = b.low; r.close = b.close;
      r.tick_volume = b.volume; r.spread = 0; r.real_volume = 0;
      rates.v[(size_t)i] = r;
   }
   return got;
}

// ------------------------------------------------------------------ indicator plumbing
namespace chartsim
{
inline int buffersBound = 0;
inline std::string shortName;
inline std::vector<MqlArray<double> *> bound;      // the terminal sizes these to rates_total
// What the terminal does before every OnCalculate: the bound buffers follow the chart.
inline void sizeBuffers(const size_t rates_total)
{
   for(MqlArray<double> *b : bound) b->v.resize(rates_total, EMPTY_VALUE);
}
}
inline bool SetIndexBuffer(const int index, MqlArray<double> &buffer, const ENUM_INDEXBUFFER_TYPE type = INDICATOR_DATA)
{
   (void)index; (void)type;
   chartsim::buffersBound++;
   if(std::find(chartsim::bound.begin(), chartsim::bound.end(), &buffer) == chartsim::bound.end())
      chartsim::bound.push_back(&buffer);
   return true;
}
inline bool PlotIndexSetInteger(const int plot, const ENUM_PLOT_PROPERTY_INTEGER prop, const long value) { (void)plot; (void)prop; (void)value; return true; }
inline bool PlotIndexSetDouble(const int plot, const ENUM_PLOT_PROPERTY_DOUBLE prop, const double value) { (void)plot; (void)prop; (void)value; return true; }
inline bool PlotIndexSetString(const int plot, const ENUM_PLOT_PROPERTY_STRING prop, const string value) { (void)plot; (void)prop; (void)value; return true; }
inline bool IndicatorSetString(const ENUM_CUSTOMIND_PROPERTY_STRING prop, const string value) { if(prop == INDICATOR_SHORTNAME) chartsim::shortName = value; return true; }
inline bool IndicatorSetInteger(const ENUM_CUSTOMIND_PROPERTY_INTEGER prop, const long value) { (void)prop; (void)value; return true; }
// timers: recorded, fired by the driver
namespace chartsim
{
inline int timerSeconds = 0;       // 0 = no timer armed
inline int timerSets = 0, timerKills = 0;
}
inline bool EventSetTimer(const int seconds) { chartsim::timerSeconds = seconds; chartsim::timerSets++; return seconds > 0; }
inline void EventKillTimer() { chartsim::timerSeconds = 0; chartsim::timerKills++; }
template <class... A> void Alert(const A &...a)
{
   std::string text;
   (void)std::initializer_list<int>{(text += mqlfmt::printArg(a), 0)...};
   chartsim::C.alerts.push_back(text);
}

#endif
