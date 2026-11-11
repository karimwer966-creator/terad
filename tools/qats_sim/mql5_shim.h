// mql5_shim.h - typed MQL5 API shim + single-symbol broker/market simulator.
//
// PURPOSE
//   Lets the REAL QuantumAutonomousTradingSystem.mq5 source be compiled by a host
//   C++17 compiler (after the mechanical rewrite in tools/qats_native.py) and be
//   driven tick by tick against a simulated MT5 terminal: multi-timeframe bars,
//   EMA/ATR handles, terminal global variables, a hedging account, server-side
//   SL/TP, deals, history, and OnTradeTransaction.
//
// WHAT THIS IS NOT
//   It is NOT MetaEditor and NOT the MT5 Strategy Tester. A clean host build is
//   evidence, not proof, of a clean F7. A run here is a simulation with the
//   documented fill model below, not broker execution.
//
// TYPE FIDELITY
//   Property identifiers are distinct enum types exactly as in MQL5
//   (ENUM_SYMBOL_INFO_INTEGER vs ENUM_SYMBOL_INFO_DOUBLE ...), so reading a
//   double property through the integer accessor fails to compile here just as it
//   does in MetaEditor. Return types match the MQL5 reference (iVolume -> long,
//   TerminalInfoInteger -> int, CTrade::ResultRetcode -> uint ...), so host
//   -Wconversion diagnostics map onto MetaEditor's "possible loss of data".
#pragma once
#pragma GCC system_header

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <map>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

// ---------------------------------------------------------------- MQL types
using string   = std::string;
using datetime = long;            // MQL5 datetime: 8 bytes, seconds since 1970
using ulong    = unsigned long;   // 8 bytes on LP64, same as MQL5
using uint     = unsigned int;
using ushort   = unsigned short;
using uchar    = unsigned char;
using color    = int;

#define INVALID_HANDLE (-1)
#define EMPTY_VALUE    (1.7976931348623157e308)
#define WRONG_VALUE    (-1)
#define INIT_SUCCEEDED 0
#define INIT_FAILED    1
#define INIT_PARAMETERS_INCORRECT 32767
#define TIME_DATE    1
#define TIME_MINUTES 2
#define TIME_SECONDS 4
#define CHARTS_MAX   100
#define NULL_STRING  string("")

enum ENUM_TIMEFRAMES : int
{
   PERIOD_CURRENT = 0, PERIOD_M1 = 1, PERIOD_M5 = 5, PERIOD_M15 = 15, PERIOD_M30 = 30,
   PERIOD_H1 = 16385, PERIOD_H4 = 16388, PERIOD_D1 = 16408, PERIOD_W1 = 32769, PERIOD_MN1 = 49153
};
enum ENUM_MA_METHOD : int { MODE_SMA = 0, MODE_EMA = 1, MODE_SMMA = 2, MODE_LWMA = 3 };
enum ENUM_APPLIED_PRICE : int { PRICE_CLOSE = 1, PRICE_OPEN, PRICE_HIGH, PRICE_LOW, PRICE_MEDIAN, PRICE_TYPICAL, PRICE_WEIGHTED };

enum ENUM_SYMBOL_INFO_INTEGER : int
{
   SYMBOL_DIGITS = 17, SYMBOL_SPREAD = 18, SYMBOL_TRADE_STOPS_LEVEL = 31, SYMBOL_TRADE_FREEZE_LEVEL = 32,
   SYMBOL_TRADE_MODE = 30, SYMBOL_TRADE_EXEMODE = 33, SYMBOL_FILLING_MODE = 50, SYMBOL_TIME = 5,
   SYMBOL_SELECT = 0, SYMBOL_VISIBLE = 76, SYMBOL_TRADE_CALC_MODE = 29, SYMBOL_SPREAD_FLOAT = 41,
   SYMBOL_ORDER_MODE = 71, SYMBOL_EXPIRATION_MODE = 49, SYMBOL_SWAP_MODE = 37
};
enum ENUM_SYMBOL_INFO_DOUBLE : int
{
   SYMBOL_BID = 1, SYMBOL_ASK = 4, SYMBOL_LAST = 7, SYMBOL_POINT = 16, SYMBOL_TRADE_TICK_VALUE = 26,
   SYMBOL_TRADE_TICK_SIZE = 27, SYMBOL_TRADE_CONTRACT_SIZE = 28, SYMBOL_VOLUME_MIN = 34,
   SYMBOL_VOLUME_MAX = 35, SYMBOL_VOLUME_STEP = 36, SYMBOL_VOLUME_LIMIT = 55,
   SYMBOL_SWAP_LONG = 38, SYMBOL_SWAP_SHORT = 39, SYMBOL_MARGIN_INITIAL = 42
};
enum ENUM_SYMBOL_INFO_STRING : int { SYMBOL_CURRENCY_BASE = 22, SYMBOL_CURRENCY_PROFIT = 23, SYMBOL_CURRENCY_MARGIN = 24, SYMBOL_DESCRIPTION = 20 };
enum ENUM_SYMBOL_TRADE_MODE : int { SYMBOL_TRADE_MODE_DISABLED = 0, SYMBOL_TRADE_MODE_LONGONLY = 1, SYMBOL_TRADE_MODE_SHORTONLY = 2, SYMBOL_TRADE_MODE_CLOSEONLY = 3, SYMBOL_TRADE_MODE_FULL = 4 };
enum ENUM_SYMBOL_TRADE_EXECUTION : int { SYMBOL_TRADE_EXECUTION_REQUEST = 0, SYMBOL_TRADE_EXECUTION_INSTANT = 1, SYMBOL_TRADE_EXECUTION_MARKET = 2, SYMBOL_TRADE_EXECUTION_EXCHANGE = 3 };
const long SYMBOL_EXPIRATION_GTC = 1;
const long SYMBOL_EXPIRATION_DAY = 2;
const long SYMBOL_EXPIRATION_SPECIFIED = 4;
const long SYMBOL_EXPIRATION_SPECIFIED_DAY = 8;

const int SYMBOL_FILLING_FOK = 1;
const int SYMBOL_FILLING_IOC = 2;
const int SYMBOL_FILLING_BOC = 4;

enum ENUM_ACCOUNT_INFO_INTEGER : int
{
   ACCOUNT_LOGIN = 0, ACCOUNT_TRADE_MODE = 32, ACCOUNT_LEVERAGE = 35, ACCOUNT_LIMIT_ORDERS = 47,
   ACCOUNT_MARGIN_SO_MODE = 44, ACCOUNT_TRADE_ALLOWED = 33, ACCOUNT_TRADE_EXPERT = 34,
   ACCOUNT_MARGIN_MODE = 46, ACCOUNT_CURRENCY_DIGITS = 48, ACCOUNT_FIFO_CLOSE = 49, ACCOUNT_HEDGE_ALLOWED = 50
};
enum ENUM_ACCOUNT_INFO_DOUBLE : int
{
   ACCOUNT_BALANCE = 37, ACCOUNT_CREDIT = 38, ACCOUNT_PROFIT = 39, ACCOUNT_EQUITY = 40, ACCOUNT_MARGIN = 41,
   ACCOUNT_MARGIN_FREE = 42, ACCOUNT_MARGIN_LEVEL = 43, ACCOUNT_MARGIN_SO_CALL = 45, ACCOUNT_MARGIN_SO_SO = 51
};
enum ENUM_ACCOUNT_INFO_STRING : int { ACCOUNT_NAME = 1, ACCOUNT_SERVER = 3, ACCOUNT_CURRENCY = 36, ACCOUNT_COMPANY = 2 };
enum ENUM_ACCOUNT_TRADE_MODE : int { ACCOUNT_TRADE_MODE_DEMO = 0, ACCOUNT_TRADE_MODE_CONTEST = 1, ACCOUNT_TRADE_MODE_REAL = 2 };
enum ENUM_ACCOUNT_MARGIN_MODE : int { ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0, ACCOUNT_MARGIN_MODE_EXCHANGE = 1, ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2 };

enum ENUM_TERMINAL_INFO_INTEGER : int { TERMINAL_CONNECTED = 6, TERMINAL_TRADE_ALLOWED = 8, TERMINAL_DLLS_ALLOWED = 7, TERMINAL_BUILD = 5 };
enum ENUM_MQL_INFO_INTEGER : int { MQL_TRADE_ALLOWED = 4, MQL_TESTER = 6, MQL_OPTIMIZATION = 7, MQL_VISUAL_MODE = 8, MQL_DEBUG = 5 };

// the real ENUM_ORDER_TYPE order and names (StopLimit included: Trade.mqh's
// OrderOpen documents a limit_price parameter that only a StopLimit order uses)
enum ENUM_ORDER_TYPE : int { ORDER_TYPE_BUY = 0, ORDER_TYPE_SELL = 1, ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_SELL_LIMIT,
                             ORDER_TYPE_BUY_STOP, ORDER_TYPE_SELL_STOP,
                             ORDER_TYPE_BUY_STOP_LIMIT, ORDER_TYPE_SELL_STOP_LIMIT };
enum ENUM_ORDER_TYPE_FILLING : int { ORDER_FILLING_FOK = 0, ORDER_FILLING_IOC = 1, ORDER_FILLING_RETURN = 2, ORDER_FILLING_BOC = 3 };
enum ENUM_ORDER_TYPE_TIME : int { ORDER_TIME_GTC = 0, ORDER_TIME_DAY, ORDER_TIME_SPECIFIED, ORDER_TIME_SPECIFIED_DAY };
enum ENUM_ORDER_STATE : int { ORDER_STATE_STARTED = 0, ORDER_STATE_PLACED, ORDER_STATE_CANCELED, ORDER_STATE_PARTIAL, ORDER_STATE_FILLED };
enum ENUM_ORDER_PROPERTY_INTEGER : int { ORDER_TICKET = 0, ORDER_TYPE = 1, ORDER_STATE = 2, ORDER_TIME_SETUP = 8,
                                          ORDER_TIME_EXPIRATION = 13, ORDER_TYPE_TIME = 14, ORDER_MAGIC = 9 };
enum ENUM_ORDER_PROPERTY_DOUBLE : int { ORDER_VOLUME_CURRENT = 27, ORDER_PRICE_OPEN = 3, ORDER_SL = 5, ORDER_TP = 6 };
enum ENUM_ORDER_PROPERTY_STRING : int { ORDER_SYMBOL = 0, ORDER_COMMENT = 1 };
enum ENUM_TRADE_REQUEST_ACTIONS : int { TRADE_ACTION_DEAL = 1, TRADE_ACTION_PENDING = 5, TRADE_ACTION_SLTP = 6, TRADE_ACTION_MODIFY = 7, TRADE_ACTION_REMOVE = 8, TRADE_ACTION_CLOSE_BY = 10 };
enum ENUM_POSITION_TYPE : int { POSITION_TYPE_BUY = 0, POSITION_TYPE_SELL = 1 };
enum ENUM_POSITION_PROPERTY_INTEGER : int { POSITION_TICKET = 17, POSITION_TIME = 1, POSITION_TIME_MSC = 14, POSITION_TIME_UPDATE = 15, POSITION_TYPE = 2, POSITION_MAGIC = 12, POSITION_IDENTIFIER = 13, POSITION_REASON = 18 };
enum ENUM_POSITION_PROPERTY_DOUBLE : int { POSITION_VOLUME = 3, POSITION_PRICE_OPEN = 4, POSITION_SL = 6, POSITION_TP = 7, POSITION_PRICE_CURRENT = 5, POSITION_SWAP = 9, POSITION_PROFIT = 10 };
enum ENUM_POSITION_PROPERTY_STRING : int { POSITION_SYMBOL = 0, POSITION_COMMENT = 11 };
enum ENUM_DEAL_TYPE : int { DEAL_TYPE_BUY = 0, DEAL_TYPE_SELL = 1, DEAL_TYPE_BALANCE = 2 };
enum ENUM_DEAL_ENTRY : int { DEAL_ENTRY_IN = 0, DEAL_ENTRY_OUT = 1, DEAL_ENTRY_INOUT = 2, DEAL_ENTRY_OUT_BY = 3 };
enum ENUM_DEAL_REASON : int { DEAL_REASON_CLIENT = 0, DEAL_REASON_MOBILE, DEAL_REASON_WEB, DEAL_REASON_EXPERT, DEAL_REASON_SL, DEAL_REASON_TP, DEAL_REASON_SO };
enum ENUM_DEAL_PROPERTY_INTEGER : int { DEAL_TICKET = 100, DEAL_ORDER = 1, DEAL_TIME = 2, DEAL_TIME_MSC = 14, DEAL_TYPE = 3, DEAL_ENTRY = 4, DEAL_MAGIC = 10, DEAL_REASON = 16, DEAL_POSITION_ID = 11 };
enum ENUM_DEAL_PROPERTY_DOUBLE : int { DEAL_VOLUME = 5, DEAL_PRICE = 6, DEAL_COMMISSION = 7, DEAL_SWAP = 8, DEAL_PROFIT = 9, DEAL_FEE = 17, DEAL_SL = 18, DEAL_TP = 19 };
enum ENUM_DEAL_PROPERTY_STRING : int { DEAL_SYMBOL = 12, DEAL_COMMENT = 13, DEAL_EXTERNAL_ID = 15 };
enum ENUM_TRADE_TRANSACTION_TYPE : int
{
   TRADE_TRANSACTION_ORDER_ADD = 0, TRADE_TRANSACTION_ORDER_UPDATE, TRADE_TRANSACTION_ORDER_DELETE,
   TRADE_TRANSACTION_HISTORY_ADD, TRADE_TRANSACTION_HISTORY_UPDATE, TRADE_TRANSACTION_HISTORY_DELETE,
   TRADE_TRANSACTION_DEAL_ADD, TRADE_TRANSACTION_DEAL_UPDATE, TRADE_TRANSACTION_DEAL_DELETE,
   TRADE_TRANSACTION_POSITION, TRADE_TRANSACTION_REQUEST
};

// trade server return codes (real values)
const uint TRADE_RETCODE_REQUOTE = 10004, TRADE_RETCODE_REJECT = 10006, TRADE_RETCODE_CANCEL = 10007,
           TRADE_RETCODE_PLACED = 10008, TRADE_RETCODE_DONE = 10009, TRADE_RETCODE_DONE_PARTIAL = 10010,
           TRADE_RETCODE_ERROR = 10011, TRADE_RETCODE_TIMEOUT = 10012, TRADE_RETCODE_INVALID = 10013,
           TRADE_RETCODE_INVALID_VOLUME = 10014, TRADE_RETCODE_INVALID_PRICE = 10015,
           TRADE_RETCODE_INVALID_STOPS = 10016, TRADE_RETCODE_TRADE_DISABLED = 10017,
           TRADE_RETCODE_MARKET_CLOSED = 10018, TRADE_RETCODE_NO_MONEY = 10019,
           TRADE_RETCODE_PRICE_CHANGED = 10020, TRADE_RETCODE_PRICE_OFF = 10021,
           TRADE_RETCODE_INVALID_EXPIRATION = 10022, TRADE_RETCODE_ORDER_CHANGED = 10023,
           TRADE_RETCODE_TOO_MANY_REQUESTS = 10024, TRADE_RETCODE_NO_CHANGES = 10025,
           TRADE_RETCODE_SERVER_DISABLES_AT = 10026, TRADE_RETCODE_CLIENT_DISABLES_AT = 10027,
           TRADE_RETCODE_LOCKED = 10028, TRADE_RETCODE_FROZEN = 10029, TRADE_RETCODE_INVALID_FILL = 10030,
           TRADE_RETCODE_CONNECTION = 10031, TRADE_RETCODE_ONLY_REAL = 10032,
           TRADE_RETCODE_LIMIT_ORDERS = 10033, TRADE_RETCODE_LIMIT_VOLUME = 10034,
           TRADE_RETCODE_INVALID_ORDER = 10035, TRADE_RETCODE_POSITION_CLOSED = 10036,
           TRADE_RETCODE_INVALID_CLOSE_VOLUME = 10038, TRADE_RETCODE_CLOSE_ORDER_EXIST = 10039,
           TRADE_RETCODE_LIMIT_POSITIONS = 10040, TRADE_RETCODE_REJECT_CANCEL = 10041,
           TRADE_RETCODE_LONG_ONLY = 10042, TRADE_RETCODE_SHORT_ONLY = 10043,
           TRADE_RETCODE_CLOSE_ONLY = 10044, TRADE_RETCODE_FIFO_CLOSE = 10045,
           TRADE_RETCODE_HEDGE_PROHIBITED = 10046;

struct MqlDateTime { int year, mon, day, hour, min, sec, day_of_week, day_of_year; };
struct MqlTick { datetime time; double bid, ask, last; ulong volume; long time_msc; uint flags; double volume_real; };
struct MqlRates { datetime time; double open, high, low, close; long tick_volume; int spread; long real_volume; };
struct MqlTradeRequest
{
   ENUM_TRADE_REQUEST_ACTIONS action; ulong magic; ulong order; string symbol; double volume; double price;
   double stoplimit; double sl; double tp; ulong deviation; ENUM_ORDER_TYPE type;
   ENUM_ORDER_TYPE_FILLING type_filling; ENUM_ORDER_TYPE_TIME type_time; datetime expiration;
   string comment; ulong position; ulong position_by;
};
struct MqlTradeResult
{
   uint retcode; ulong deal; ulong order; double volume; double price; double bid; double ask;
   string comment; uint request_id; int retcode_external;
};
struct MqlTradeTransaction
{
   ulong deal; ulong order; string symbol; ENUM_TRADE_TRANSACTION_TYPE type; ENUM_ORDER_TYPE order_type;
   ENUM_ORDER_STATE order_state; ENUM_DEAL_TYPE deal_type; ENUM_ORDER_TYPE_TIME time_type;
   datetime time_expiration; double price; double price_trigger; double price_sl; double price_tp;
   double volume; ulong position; ulong position_by;
};

// EA event handlers (defined by the Expert Advisor translation unit)
int  OnInit();
void OnDeinit(const int reason);
void OnTick();
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result);

// ------------------------------------------------------------ dynamic array
// "expression not boolean" (tools/qats_native.py bool_audit): the audit build wraps
// every operand MQL5 requires to be boolean in QATS_BOOL( ... ). It is the identity
// for a bool and a compile error for anything else. The normal build never uses it.
template <typename T> constexpr bool QATS_BOOL(const T &qv)
{
   static_assert(std::is_same<T, bool>::value,
                 "MQL5 'expression not boolean': a non-bool value is used as a condition");
   return qv;
}

namespace sim { [[noreturn]] void critical(const std::string &msg); }

template <class T> struct MqlArray
{
   std::vector<T> v;
   bool series = false;
   T &operator[](long i)
   {
      if(i < 0 || (size_t)i >= v.size()) sim::critical("array out of range: index " + std::to_string(i) + " size " + std::to_string(v.size()));
      return series ? v[v.size() - 1 - (size_t)i] : v[(size_t)i];
   }
   const T &operator[](long i) const
   {
      if(i < 0 || (size_t)i >= v.size()) sim::critical("array out of range: index " + std::to_string(i) + " size " + std::to_string(v.size()));
      return series ? v[v.size() - 1 - (size_t)i] : v[(size_t)i];
   }
};
template <class T> int ArraySize(const MqlArray<T> &a) { return (int)a.v.size(); }
template <class T, size_t N> int ArraySize(const T (&)[N]) { return (int)N; }
// MQL5 does NOT initialise the elements ArrayResize() adds; std::vector zeroes
// them. With -DQATS_POISON_ARRAYS every new element of a plain-data type is
// filled with 0x7F bytes (huge numbers, never zero), so code that reads an
// element before writing it behaves visibly differently from the normal build.
template <class T> int ArrayResize(MqlArray<T> &a, const int n, const int reserve = 0)
{
   (void)reserve;
   if(n < 0) return -1;
#ifdef QATS_POISON_ARRAYS
   const size_t before = a.v.size();
   a.v.resize((size_t)n);
   if constexpr (std::is_trivially_copyable<T>::value && !std::is_same<T, bool>::value)
      for(size_t i = before; i < (size_t)n; i++) std::memset((void *)&a.v[i], 0x7F, sizeof(T));
#else
   a.v.resize((size_t)n);
#endif
   return n;
}
template <class T> void ArrayFree(MqlArray<T> &a) { a.v.clear(); }
template <class T> bool ArraySetAsSeries(MqlArray<T> &a, const bool flag) { a.series = flag; return true; }
template <class T, class V> int ArrayInitialize(MqlArray<T> &a, const V value) { for(auto &x : a.v) x = (T)value; return (int)a.v.size(); }
template <class T> void ZeroMemory(T &x) { x = T{}; }

// --------------------------------------------------------------- formatting
namespace mqlfmt
{
struct Arg { char kind; long long i; unsigned long long u; double d; std::string s; };
template <class T> Arg make(const T &v)
{
   Arg a{};
   a.kind = '?'; a.i = 0; a.u = 0; a.d = 0.0;
   if constexpr(std::is_same_v<T, bool>) { a.kind = 'i'; a.i = v ? 1 : 0; }
   else if constexpr(std::is_enum_v<T>) { a.kind = 'i'; a.i = (long long)v; }
   else if constexpr(std::is_floating_point_v<T>) { a.kind = 'd'; a.d = (double)v; }
   else if constexpr(std::is_integral_v<T> && std::is_signed_v<T>) { a.kind = (sizeof(T) > 4) ? 'l' : 'i'; a.i = (long long)v; }
   else if constexpr(std::is_integral_v<T>) { a.kind = (sizeof(T) > 4) ? 'U' : 'u'; a.u = (unsigned long long)v; }
   else { a.kind = 's'; a.s = std::string(v); }
   return a;
}
std::string format(const std::string &fmt, const std::vector<Arg> &args);
} // namespace mqlfmt

// ------------------------------------------------------------- the simulator
namespace sim
{
struct Bar { datetime time; double open, high, low, close; long volume; };

struct Series
{
   ENUM_TIMEFRAMES tf;
   std::vector<Bar> bars;          // oldest first; back() is the forming bar
   int size() const { return (int)bars.size(); }
   const Bar *at(const int shift) const
   {
      int n = (int)bars.size();
      if(shift < 0 || shift >= n) return nullptr;
      return &bars[(size_t)(n - 1 - shift)];
   }
};

struct Indicator
{
   int kind;                       // 1 = EMA(close), 2 = ATR
   ENUM_TIMEFRAMES tf;
   int period;
   bool released;
   std::vector<double> val;        // one value per CLOSED bar index (aligned with Series::bars)
   std::vector<double> tr;         // ATR only
   double trSum;
};

struct Position
{
   ulong ticket; long magic; string symbol; int type; double volume; double priceOpen;
   double sl, tp; datetime time; string comment; double commission;
};

struct Deal
{
   ulong ticket; ulong order; datetime time; int type; int entry; long magic; long positionId;
   double volume, price, commission, swap, profit, fee, sl, tp; string symbol; string comment; int reason;
};

// A pending order resting at the server. MT5 keeps pending orders in a separate
// table (OrdersTotal / OrderGetTicket / OrderSelect), never in the position list.
struct PendingOrder
{
   ulong ticket; long magic; string symbol; int type; double volume; double price;
   double sl, tp; datetime timeSetup, timeExpiration; int typeTime; string comment; int state;
};

struct SymbolSpec
{
   string name = "XAUUSD";
   int digits = 2;
   double point = 0.01, tickSize = 0.01, tickValue = 1.0, contractSize = 100.0;
   double volMin = 0.01, volMax = 100.0, volStep = 0.01, volLimit = 0.0;
   int stopsLevel = 0, freezeLevel = 0;
   long tradeMode = 4;
   long fillingMode = 2;           // IOC only, as on the operator's broker
   long execMode = 2;
};

struct Account
{
   long login = 50001234;
   string server = "Sim-Demo";
   string currency = "USD";
   string name = "Simulated";
   long tradeMode = 0;             // DEMO
   long leverage = 100;
   long marginMode = 2;            // retail hedging
   bool tradeAllowed = true;
   double balance = 10000.0;
   double externalFloating = 0.0;  // P/L of positions that do NOT belong to the EA (tests)
};

struct State
{
   SymbolSpec sym;
   Account acc;
   bool terminalTradeAllowed = true;
   bool mqlTradeAllowed = true;
   bool marketOpen = true;
   datetime now = 0;
   datetime lastTickTime = 0;
   double bid = 0.0, ask = 0.0;
   bool haveQuote = false;
   // broker's ORDER_TYPE_TIME modes the symbol accepts (SYMBOL_EXPIRATION_MODE);
   // 0 = every mode is allowed, as on the operator's broker.
   long expirationMode = 0;
   Series series[6];               // M5 M15 H1 H4 D1 W1
   std::vector<Indicator> indicators;
   std::map<std::string, double> gv;
   std::vector<Position> positions;
   std::vector<PendingOrder> orders;
   std::vector<Deal> deals;
   std::vector<ulong> selected;    // deal tickets visible to HistoryDealGet*
   std::vector<ulong> selectedExtra;
   std::vector<MqlTradeTransaction> pendingTx;
   ulong nextTicket = 1000001;
   std::vector<uint> injectRetcodes;   // consumed by the next market sends
   int lastError = 0;
   double commissionPerLot = 0.0;      // per side, account currency
   double stopSlippage = 0.0;          // adverse price slippage applied to SL fills
   double entrySlippage = 0.0;         // adverse price slippage applied to market fills
   bool outDealKeepsMagic = true;      // SL/TP closing deals carry the position magic
   long sendCount = 0, sendOk = 0, modifyCount = 0;
   std::map<std::string, long> sendStats;   // "entry:10009", "modify:10016", "close:10009" ...
   // diagnostics that tests assert to be empty
   std::vector<std::string> fmtErrors;
   std::vector<std::string> apiErrors;
   std::string lastComment;
   std::function<void(const std::string &)> onPrint;
   FILE *logFile = nullptr;
   std::string logPrefix = "QuantumAutonomousTradingSystem (XAUUSD,M15)";
   bool inHandler = false;
};
inline State S;

[[noreturn]] inline void critical(const std::string &msg)
{
   throw std::runtime_error("MQL critical error: " + msg);
}

inline void apiError(const std::string &msg)
{
   if(S.apiErrors.size() < 200) S.apiErrors.push_back(msg);
}

// --- calendar helpers (proleptic Gregorian, no time zones) ---
inline long daysFromCivil(long y, unsigned m, unsigned d)
{
   y -= m <= 2;
   const long era = (y >= 0 ? y : y - 399) / 400;
   const unsigned yoe = (unsigned)(y - era * 400);
   const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
   const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
   return era * 146097 + (long)doe - 719468;
}
inline void civilFromDays(long z, int &y, int &m, int &d)
{
   z += 719468;
   const long era = (z >= 0 ? z : z - 146096) / 146097;
   const unsigned doe = (unsigned)(z - era * 146097);
   const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
   long yy = (long)yoe + era * 400;
   const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
   const unsigned mp = (5 * doy + 2) / 153;
   d = (int)(doy - (153 * mp + 2) / 5 + 1);
   m = (int)(mp < 10 ? mp + 3 : mp - 9);
   y = (int)(yy + (m <= 2));
}
inline datetime makeTime(int y, int mo, int d, int h = 0, int mi = 0, int s = 0)
{
   return daysFromCivil(y, (unsigned)mo, (unsigned)d) * 86400L + h * 3600L + mi * 60L + s;
}
inline int dayOfWeek(datetime t)      // 0 = Sunday
{
   long days = (t >= 0 ? t / 86400 : (t - 86399) / 86400);
   long w = (days + 4) % 7;
   if(w < 0) w += 7;
   return (int)w;
}
inline std::string timeString(datetime t, int mode)
{
   long days = (t >= 0 ? t / 86400 : (t - 86399) / 86400);
   long rem = t - days * 86400;
   int y, m, d;
   civilFromDays(days, y, m, d);
   char buf[48];
   std::string out;
   if(mode & TIME_DATE) { snprintf(buf, sizeof buf, "%04d.%02d.%02d", y, m, d); out += buf; }
   if(mode & (TIME_MINUTES | TIME_SECONDS))
   {
      if(!out.empty()) out += " ";
      if(mode & TIME_SECONDS) snprintf(buf, sizeof buf, "%02d:%02d:%02d", (int)(rem / 3600), (int)(rem % 3600 / 60), (int)(rem % 60));
      else snprintf(buf, sizeof buf, "%02d:%02d", (int)(rem / 3600), (int)(rem % 3600 / 60));
      out += buf;
   }
   return out;
}

inline int tfIndex(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M5: return 0;
      case PERIOD_M15: return 1;
      case PERIOD_H1: return 2;
      case PERIOD_H4: return 3;
      case PERIOD_D1: return 4;
      case PERIOD_W1: return 5;
      default: return -1;
   }
}
inline datetime barOpenTime(ENUM_TIMEFRAMES tf, datetime t)
{
   switch(tf)
   {
      case PERIOD_M5: return t - t % 300;
      case PERIOD_M15: return t - t % 900;
      case PERIOD_H1: return t - t % 3600;
      case PERIOD_H4: return t - t % 14400;
      case PERIOD_D1: return t - t % 86400;
      case PERIOD_W1: { datetime d = t - t % 86400; return d - (datetime)dayOfWeek(t) * 86400; }
      default: return t;
   }
}
inline Series *seriesFor(const string &symbol, ENUM_TIMEFRAMES tf)
{
   if(symbol != S.sym.name) { apiError("series requested for foreign symbol " + symbol); return nullptr; }
   int i = tfIndex(tf);
   if(i < 0) { apiError("series requested for unsupported timeframe " + std::to_string((int)tf)); return nullptr; }
   return &S.series[i];
}

inline void logLine(const std::string &text)
{
   if(S.onPrint) S.onPrint(text);
   if(S.logFile)
      fprintf(S.logFile, "%s.000\t%s\t%s\n", timeString(S.now, TIME_DATE | TIME_SECONDS).c_str(), S.logPrefix.c_str(), text.c_str());
}

// --- indicators: one value per closed bar, computed when the bar closes ---
inline void indicatorOnBarClosed(Indicator &ind, const Series &ser, const size_t idx)
{
   // idx = index of the bar that has just CLOSED
   if(ind.val.size() != idx) { ind.val.resize(idx, 0.0); if(ind.kind == 2) ind.tr.resize(idx, 0.0); }
   const Bar &b = ser.bars[idx];
   if(ind.kind == 1)
   {
      double k = 2.0 / ((double)ind.period + 1.0);
      double prev = (idx == 0) ? b.close : ind.val[idx - 1];
      ind.val.push_back((idx == 0) ? b.close : b.close * k + prev * (1.0 - k));
   }
   else
   {
      double tr = b.high - b.low;
      if(idx > 0)
      {
         double pc = ser.bars[idx - 1].close;
         tr = std::max(tr, std::max(std::fabs(b.high - pc), std::fabs(b.low - pc)));
      }
      ind.tr.push_back(tr);
      ind.trSum += tr;
      if(idx >= (size_t)ind.period) ind.trSum -= ind.tr[idx - (size_t)ind.period];
      ind.val.push_back(idx + 1 >= (size_t)ind.period ? ind.trSum / (double)ind.period : 0.0);
   }
}
inline void indicatorCatchUp(Indicator &ind)
{
   Series &ser = S.series[tfIndex(ind.tf)];
   size_t closed = ser.bars.empty() ? 0 : ser.bars.size() - 1;
   while(ind.val.size() < closed) indicatorOnBarClosed(ind, ser, ind.val.size());
}

// --- quotes / bars ---
inline void pushTickToSeries(datetime t, double bid, long volInc)
{
   static const ENUM_TIMEFRAMES tfs[6] = {PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1, PERIOD_W1};
   for(int i = 0; i < 6; i++)
   {
      Series &ser = S.series[i];
      ser.tf = tfs[i];
      datetime bt = barOpenTime(tfs[i], t);
      if(ser.bars.empty() || bt > ser.bars.back().time)
      {
         Bar b{bt, bid, bid, bid, bid, volInc};
         ser.bars.push_back(b);
      }
      else
      {
         Bar &b = ser.bars.back();
         if(bid > b.high) b.high = bid;
         if(bid < b.low) b.low = bid;
         b.close = bid;
         b.volume += volInc;
      }
   }
}

// --- account math ---
inline double moneyPerPriceUnit(double volume) { return volume * S.sym.tickValue / S.sym.tickSize; }
inline double floatingOf(const Position &p)
{
   if(p.type == POSITION_TYPE_BUY) return (S.bid - p.priceOpen) * moneyPerPriceUnit(p.volume);
   return (p.priceOpen - S.ask) * moneyPerPriceUnit(p.volume);
}
inline double equity()
{
   double e = S.acc.balance + S.acc.externalFloating;
   for(const Position &p : S.positions) e += floatingOf(p);
   return e;
}
inline double marginOf(double volume, double price) { return volume * S.sym.contractSize * price / (double)S.acc.leverage; }
inline double usedMargin()
{
   double m = 0.0;
   for(const Position &p : S.positions) m += marginOf(p.volume, p.priceOpen);
   return m;
}

inline const Deal *findDeal(ulong ticket)
{
   for(size_t i = S.deals.size(); i-- > 0;)
      if(S.deals[i].ticket == ticket) return &S.deals[i];
   return nullptr;
}
inline bool dealVisible(ulong ticket)
{
   for(ulong t : S.selected) if(t == ticket) return true;
   for(ulong t : S.selectedExtra) if(t == ticket) return true;
   return false;
}

inline void queueDealTx(const Deal &d)
{
   MqlTradeTransaction tx{};
   tx.type = TRADE_TRANSACTION_DEAL_ADD;
   tx.deal = d.ticket;
   tx.order = d.order;
   tx.symbol = d.symbol;
   tx.deal_type = (ENUM_DEAL_TYPE)d.type;
   tx.price = d.price;
   tx.volume = d.volume;
   tx.position = (ulong)d.positionId;
   tx.price_sl = d.sl;
   tx.price_tp = d.tp;
   S.pendingTx.push_back(tx);
}
inline void dispatchTransactions()
{
   // MT5 delivers trade transactions asynchronously, never re-entrantly.
   if(S.inHandler) return;
   while(!S.pendingTx.empty())
   {
      MqlTradeTransaction tx = S.pendingTx.front();
      S.pendingTx.erase(S.pendingTx.begin());
      MqlTradeRequest rq{};
      MqlTradeResult rs{};
      S.inHandler = true;
      OnTradeTransaction(tx, rq, rs);
      S.inHandler = false;
   }
}

inline ulong addDeal(const Position &p, int entry, double volume, double price, double profit, int reason, long magic)
{
   Deal d{};
   d.ticket = S.nextTicket++;
   d.order = S.nextTicket++;
   d.time = S.now;
   d.entry = entry;
   // an OUT deal of a BUY position is a SELL deal and vice versa
   d.type = (entry == DEAL_ENTRY_IN) ? (p.type == POSITION_TYPE_BUY ? DEAL_TYPE_BUY : DEAL_TYPE_SELL)
                                     : (p.type == POSITION_TYPE_BUY ? DEAL_TYPE_SELL : DEAL_TYPE_BUY);
   d.magic = magic;
   d.positionId = (long)p.ticket;
   d.volume = volume;
   d.price = price;
   d.commission = -S.commissionPerLot * volume;
   d.swap = 0.0;
   d.profit = profit;
   d.fee = 0.0;
   d.sl = p.sl;
   d.tp = p.tp;
   d.symbol = p.symbol;
   d.comment = p.comment;
   d.reason = reason;
   S.acc.balance += d.profit + d.commission;
   S.deals.push_back(d);
   queueDealTx(d);
   return d.ticket;
}

inline void closePositionAt(size_t idx, double volume, double price, int reason, long magic)
{
   Position &p = S.positions[idx];
   double vol = std::min(volume, p.volume);
   double diff = (p.type == POSITION_TYPE_BUY) ? (price - p.priceOpen) : (p.priceOpen - price);
   double profit = diff * moneyPerPriceUnit(vol);
   addDeal(p, DEAL_ENTRY_OUT, vol, price, profit, reason, magic);
   p.volume -= vol;
   if(p.volume < S.sym.volStep * 0.5) S.positions.erase(S.positions.begin() + (long)idx);
}

// Server-side SL/TP between the previous quote and the new one.
// Within a minute the path is continuous, so a level strictly inside the move
// fills AT the level; on a gap (first tick of a new M1 bar / session) a level
// that is already behind the market fills at the new quote.
inline void processStops(double prevBid, double prevAsk, double bid, double ask, bool gapTick)
{
   (void)prevBid; (void)prevAsk;
   for(size_t i = S.positions.size(); i-- > 0;)
   {
      Position &p = S.positions[i];
      long magic = S.outDealKeepsMagic ? p.magic : 0;
      if(p.type == POSITION_TYPE_BUY)
      {
         if(p.sl > 0.0 && bid <= p.sl)
         {
            double px = (gapTick ? std::min(p.sl, bid) : p.sl) - S.stopSlippage;
            closePositionAt(i, p.volume, px, DEAL_REASON_SL, magic);
            continue;
         }
         if(p.tp > 0.0 && bid >= p.tp)
         {
            double px = gapTick ? std::max(p.tp, bid) : p.tp;
            closePositionAt(i, p.volume, px, DEAL_REASON_TP, magic);
            continue;
         }
      }
      else
      {
         if(p.sl > 0.0 && ask >= p.sl)
         {
            double px = (gapTick ? std::max(p.sl, ask) : p.sl) + S.stopSlippage;
            closePositionAt(i, p.volume, px, DEAL_REASON_SL, magic);
            continue;
         }
         if(p.tp > 0.0 && ask <= p.tp)
         {
            double px = gapTick ? std::min(p.tp, ask) : p.tp;
            closePositionAt(i, p.volume, px, DEAL_REASON_TP, magic);
            continue;
         }
      }
   }
}

// Pending orders at the server: trigger on the quote, expire on the clock.
// A BUY LIMIT fills when the ASK reaches its price (it is bought at the ask, so a
// limit "at the level" fills as soon as the ask touches it); a SELL LIMIT fills
// when the BID reaches its price. The filled order becomes a position whose open
// price is the order price, carrying the order's own server-side SL and TP, and
// its entry deal is queued to OnTradeTransaction exactly like a market fill.
inline void processOrders()
{
   for(size_t i = S.orders.size(); i-- > 0;)
   {
      PendingOrder o = S.orders[i];
      bool expired = (o.typeTime == ORDER_TIME_SPECIFIED || o.typeTime == ORDER_TIME_SPECIFIED_DAY)
                     && o.timeExpiration > 0 && S.now >= o.timeExpiration;
      if(expired) { S.orders.erase(S.orders.begin() + (long)i); continue; }
      if(!S.marketOpen || !S.haveQuote) continue;
      bool fill = false;
      double px = o.price;
      if(o.type == ORDER_TYPE_BUY_LIMIT && S.ask <= o.price) fill = true;
      if(o.type == ORDER_TYPE_SELL_LIMIT && S.bid >= o.price) fill = true;
      if(o.type == ORDER_TYPE_BUY_STOP && S.ask >= o.price) fill = true;
      if(o.type == ORDER_TYPE_SELL_STOP && S.bid <= o.price) fill = true;
      if(!fill) continue;
      if(marginOf(o.volume, px) > equity() - usedMargin()) continue;  // not enough money: it stays pending
      Position p{};
      p.ticket = S.nextTicket++;
      p.magic = o.magic;
      p.symbol = o.symbol;
      p.type = (o.type == ORDER_TYPE_BUY_LIMIT || o.type == ORDER_TYPE_BUY_STOP) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
      p.volume = o.volume;
      p.priceOpen = px;
      p.sl = o.sl;
      p.tp = o.tp;
      p.time = S.now;
      p.comment = o.comment;
      S.positions.push_back(p);
      addDeal(p, DEAL_ENTRY_IN, p.volume, px, 0.0, DEAL_REASON_EXPERT, p.magic);
      S.orders.erase(S.orders.begin() + (long)i);
      S.sendStats["fill:" + std::to_string((long)o.ticket)]++;
   }
}

// Feed one quote. callEA=false warms the history without running the expert.
inline void feedTick(datetime t, double bid, double ask, long volInc, bool gapTick, bool callEA)
{
   double prevBid = S.bid, prevAsk = S.ask;
   S.now = t;
   S.lastTickTime = t;
   if(S.haveQuote) processStops(prevBid, prevAsk, bid, ask, gapTick);
   S.bid = bid;
   S.ask = ask;
   S.haveQuote = true;
   processOrders();
   pushTickToSeries(t, bid, volInc);
   if(callEA)
   {
      dispatchTransactions();
      S.inHandler = true;
      OnTick();
      S.inHandler = false;
      dispatchTransactions();
   }
}

inline bool onGrid(double price)
{
   double q = price / S.sym.tickSize;
   return std::fabs(q - std::round(q)) < 1e-6;
}

inline const char *retcodeText(uint rc)
{
   switch(rc)
   {
      case 10004: return "requote";
      case 10006: return "request rejected";
      case 10009: return "done";
      case 10010: return "done partially";
      case 10012: return "request timed out";
      case 10013: return "invalid request";
      case 10014: return "invalid volume";
      case 10015: return "invalid price";
      case 10016: return "invalid stops";
      case 10017: return "trade disabled";
      case 10018: return "market closed";
      case 10019: return "not enough money";
      case 10020: return "price changed";
      case 10021: return "off quotes";
      case 10024: return "too many requests";
      case 10027: return "autotrading disabled by client";
      case 10030: return "unsupported filling mode";
      case 10031: return "no connection";
      case 10036: return "position already closed";
      default: return "unknown retcode";
   }
}

inline bool stopsAcceptable(int type, double sl, double tp, uint &rc)
{
   double lvl = (double)S.sym.stopsLevel * S.sym.point;
   if((sl != 0.0 && !onGrid(sl)) || (tp != 0.0 && !onGrid(tp))) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
   if(type == POSITION_TYPE_BUY)
   {
      if(sl != 0.0 && !(sl < S.bid && S.bid - sl >= lvl - 1e-9)) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
      if(tp != 0.0 && !(tp > S.bid && tp - S.bid >= lvl - 1e-9)) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
   }
   else
   {
      if(sl != 0.0 && !(sl > S.ask && sl - S.ask >= lvl - 1e-9)) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
      if(tp != 0.0 && !(tp < S.ask && S.ask - tp >= lvl - 1e-9)) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
   }
   return true;
}

// A pending order's price must be on the correct side of the market and its
// stops must satisfy the broker's stops level, exactly as a market order's are.
inline bool pendingStopsAcceptable(const ENUM_ORDER_TYPE type, const double price, const double sl, const double tp, uint &rc)
{
   rc = 0;
   double minDist = (double)std::max(1, S.sym.stopsLevel) * S.sym.point;
   bool isBuy = (type == ORDER_TYPE_BUY_LIMIT || type == ORDER_TYPE_BUY_STOP);
   if(price <= 0.0 || sl <= 0.0 || tp <= 0.0) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
   if(type == ORDER_TYPE_BUY_LIMIT && price >= S.ask) { rc = TRADE_RETCODE_INVALID_PRICE; return false; }
   if(type == ORDER_TYPE_SELL_LIMIT && price <= S.bid) { rc = TRADE_RETCODE_INVALID_PRICE; return false; }
   if(type == ORDER_TYPE_BUY_STOP && price <= S.ask) { rc = TRADE_RETCODE_INVALID_PRICE; return false; }
   if(type == ORDER_TYPE_SELL_STOP && price >= S.bid) { rc = TRADE_RETCODE_INVALID_PRICE; return false; }
   if(isBuy)
   {
      if(sl >= price || tp <= price) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
      if(price - sl < minDist || tp - price < minDist) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
   }
   else
   {
      if(sl <= price || tp >= price) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
      if(sl - price < minDist || price - tp < minDist) { rc = TRADE_RETCODE_INVALID_STOPS; return false; }
   }
   return true;
}

inline bool serverSendImpl(const MqlTradeRequest &rq, MqlTradeResult &rs)
{
   rs = MqlTradeResult{};
   rs.bid = S.bid;
   rs.ask = S.ask;
   S.sendCount++;
   auto fail = [&](uint rc) { rs.retcode = rc; rs.comment = retcodeText(rc); return false; };
   if(!S.terminalTradeAllowed || !S.mqlTradeAllowed) return fail(TRADE_RETCODE_CLIENT_DISABLES_AT);
   if(!S.acc.tradeAllowed) return fail(TRADE_RETCODE_TRADE_DISABLED);
   if(rq.symbol != S.sym.name) return fail(TRADE_RETCODE_INVALID);
   // ---------------------------------------------------------- pending orders
   if(rq.action == TRADE_ACTION_REMOVE)
   {
      for(size_t i = 0; i < S.orders.size(); i++)
         if(S.orders[i].ticket == rq.order)
         {
            S.orders.erase(S.orders.begin() + (long)i);
            rs.retcode = TRADE_RETCODE_DONE;
            rs.comment = retcodeText(rs.retcode);
            S.sendOk++;
            return true;
         }
      return fail(TRADE_RETCODE_INVALID_ORDER);
   }
   if(rq.action == TRADE_ACTION_MODIFY)
   {
      for(PendingOrder &o : S.orders)
         if(o.ticket == rq.order)
         {
            uint rc = 0;
            if(!S.marketOpen) return fail(TRADE_RETCODE_MARKET_CLOSED);
            if(!pendingStopsAcceptable((ENUM_ORDER_TYPE)o.type, rq.price, rq.sl, rq.tp, rc)) return fail(rc);
            o.price = rq.price;
            o.sl = rq.sl;
            o.tp = rq.tp;
            if(rq.type_time != ORDER_TIME_GTC) { o.typeTime = (int)rq.type_time; o.timeExpiration = rq.expiration; }
            rs.retcode = TRADE_RETCODE_DONE;
            rs.comment = retcodeText(rs.retcode);
            S.sendOk++;
            return true;
         }
      return fail(TRADE_RETCODE_INVALID_ORDER);
   }
   if(rq.action == TRADE_ACTION_PENDING)
   {
      if(!S.marketOpen || !S.haveQuote) return fail(TRADE_RETCODE_MARKET_CLOSED);
      if(rq.type != ORDER_TYPE_BUY_LIMIT && rq.type != ORDER_TYPE_SELL_LIMIT &&
         rq.type != ORDER_TYPE_BUY_STOP && rq.type != ORDER_TYPE_SELL_STOP) return fail(TRADE_RETCODE_INVALID);
      if(S.expirationMode != 0)
      {
         long need = (rq.type_time == ORDER_TIME_SPECIFIED) ? (long)SYMBOL_EXPIRATION_SPECIFIED
                   : (rq.type_time == ORDER_TIME_GTC ? 0 : 0);
         if(need != 0 && (S.expirationMode & need) == 0) return fail(TRADE_RETCODE_INVALID_EXPIRATION);
      }
      if(rq.type_time == ORDER_TIME_SPECIFIED && (rq.expiration <= S.now || rq.expiration > S.now + 30 * 86400))
         return fail(TRADE_RETCODE_INVALID_EXPIRATION);
      long need = (rq.type_filling == ORDER_FILLING_FOK) ? SYMBOL_FILLING_FOK : (rq.type_filling == ORDER_FILLING_IOC ? SYMBOL_FILLING_IOC : 0);
      if(need != 0 && (S.sym.fillingMode & need) == 0) return fail(TRADE_RETCODE_INVALID_FILL);
      double steps = rq.volume / S.sym.volStep;
      if(rq.volume < S.sym.volMin - 1e-12 || rq.volume > S.sym.volMax + 1e-12 || std::fabs(steps - std::round(steps)) > 1e-6)
         return fail(TRADE_RETCODE_INVALID_VOLUME);
      uint rc = 0;
      if(!pendingStopsAcceptable(rq.type, rq.price, rq.sl, rq.tp, rc)) return fail(rc);
      PendingOrder o{};
      o.ticket = S.nextTicket++;
      o.magic = (long)rq.magic;
      o.symbol = rq.symbol;
      o.type = (int)rq.type;
      o.volume = rq.volume;
      o.price = rq.price;
      o.sl = rq.sl;
      o.tp = rq.tp;
      o.timeSetup = S.now;
      o.typeTime = (int)rq.type_time;
      o.timeExpiration = rq.expiration;
      o.comment = rq.comment;
      o.state = ORDER_STATE_PLACED;
      S.orders.push_back(o);
      rs.retcode = TRADE_RETCODE_PLACED;
      rs.comment = retcodeText(rs.retcode);
      rs.order = o.ticket;
      rs.volume = o.volume;
      rs.price = o.price;
      S.sendOk++;
      return true;
   }
   if(rq.action == TRADE_ACTION_SLTP)
   {
      S.modifyCount++;
      for(Position &p : S.positions)
         if(p.ticket == rq.position)
         {
            uint rc = 0;
            if(!S.marketOpen) return fail(TRADE_RETCODE_MARKET_CLOSED);
            if(!stopsAcceptable(p.type, rq.sl, rq.tp, rc)) return fail(rc);
            if(p.sl == rq.sl && p.tp == rq.tp) return fail(TRADE_RETCODE_NO_CHANGES);
            p.sl = rq.sl;
            p.tp = rq.tp;
            rs.retcode = TRADE_RETCODE_DONE;
            rs.comment = retcodeText(rs.retcode);
            return true;
         }
      return fail(TRADE_RETCODE_POSITION_CLOSED);
   }
   if(rq.action != TRADE_ACTION_DEAL) return fail(TRADE_RETCODE_INVALID);
   if(!S.injectRetcodes.empty())
   {
      uint rc = S.injectRetcodes.front();
      S.injectRetcodes.erase(S.injectRetcodes.begin());
      if(rc != TRADE_RETCODE_DONE) return fail(rc);
   }
   if(!S.marketOpen || !S.haveQuote) return fail(TRADE_RETCODE_MARKET_CLOSED);
   if(S.sym.tradeMode != SYMBOL_TRADE_MODE_FULL && rq.position == 0) return fail(TRADE_RETCODE_TRADE_DISABLED);
   {
      long need = (rq.type_filling == ORDER_FILLING_FOK) ? SYMBOL_FILLING_FOK : (rq.type_filling == ORDER_FILLING_IOC ? SYMBOL_FILLING_IOC : 0);
      if(need != 0 && (S.sym.fillingMode & need) == 0) return fail(TRADE_RETCODE_INVALID_FILL);
      if(need == 0 && S.sym.execMode == SYMBOL_TRADE_EXECUTION_MARKET && S.sym.fillingMode != 0) return fail(TRADE_RETCODE_INVALID_FILL);
   }
   double steps = rq.volume / S.sym.volStep;
   if(rq.volume < S.sym.volMin - 1e-12 || rq.volume > S.sym.volMax + 1e-12 || std::fabs(steps - std::round(steps)) > 1e-6)
      return fail(TRADE_RETCODE_INVALID_VOLUME);
   if(rq.position != 0)
   {
      for(size_t i = 0; i < S.positions.size(); i++)
         if(S.positions[i].ticket == rq.position)
         {
            Position &p = S.positions[i];
            bool opposite = (p.type == POSITION_TYPE_BUY && rq.type == ORDER_TYPE_SELL) || (p.type == POSITION_TYPE_SELL && rq.type == ORDER_TYPE_BUY);
            if(!opposite) return fail(TRADE_RETCODE_INVALID);
            if(rq.volume > p.volume + 1e-9) return fail(TRADE_RETCODE_INVALID_CLOSE_VOLUME);
            double px = (p.type == POSITION_TYPE_BUY) ? S.bid : S.ask;
            ulong before = S.nextTicket;
            closePositionAt(i, rq.volume, px, DEAL_REASON_EXPERT, (long)rq.magic);
            rs.retcode = TRADE_RETCODE_DONE;
            rs.comment = retcodeText(rs.retcode);
            rs.deal = before;
            rs.order = before + 1;
            rs.volume = rq.volume;
            rs.price = px;
            S.sendOk++;
            return true;
         }
      return fail(TRADE_RETCODE_POSITION_CLOSED);
   }
   int ptype = (rq.type == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   if(rq.type != ORDER_TYPE_BUY && rq.type != ORDER_TYPE_SELL) return fail(TRADE_RETCODE_INVALID);
   uint rc = 0;
   if(!stopsAcceptable(ptype, rq.sl, rq.tp, rc)) return fail(rc);
   double px = (ptype == POSITION_TYPE_BUY) ? S.ask + S.entrySlippage : S.bid - S.entrySlippage;
   double freeMargin = equity() - usedMargin();
   if(marginOf(rq.volume, px) > freeMargin) return fail(TRADE_RETCODE_NO_MONEY);
   Position p{};
   p.ticket = S.nextTicket++;
   p.magic = (long)rq.magic;
   p.symbol = rq.symbol;
   p.type = ptype;
   p.volume = rq.volume;
   p.priceOpen = px;
   p.sl = rq.sl;
   p.tp = rq.tp;
   p.time = S.now;
   p.comment = rq.comment;
   S.positions.push_back(p);
   ulong deal = addDeal(p, DEAL_ENTRY_IN, rq.volume, px, 0.0, DEAL_REASON_EXPERT, (long)rq.magic);
   rs.retcode = TRADE_RETCODE_DONE;
   rs.comment = retcodeText(rs.retcode);
   rs.deal = deal;
   rs.order = deal + 1;
   rs.volume = rq.volume;
   rs.price = px;
   S.sendOk++;
   return true;
}

inline bool serverSend(const MqlTradeRequest &rq, MqlTradeResult &rs)
{
   bool ok = serverSendImpl(rq, rs);
   const char *kind = (rq.action == TRADE_ACTION_SLTP) ? "modify"
                    : (rq.action == TRADE_ACTION_MODIFY) ? "order_modify"
                    : (rq.action == TRADE_ACTION_REMOVE) ? "order_remove"
                    : (rq.action == TRADE_ACTION_PENDING) ? "pending"
                    : (rq.position != 0 ? "close" : "entry");
   S.sendStats[std::string(kind) + ":" + std::to_string(rs.retcode)]++;
   return ok;
}

inline void reset()
{
   S = State{};
}
} // namespace sim

// ------------------------------------------------------- formatting engine
namespace mqlfmt
{
inline std::string format(const std::string &fmt, const std::vector<Arg> &args)
{
   std::string out;
   size_t ai = 0;
   auto err = [&](const std::string &m) {
      if(sim::S.fmtErrors.size() < 200) sim::S.fmtErrors.push_back(m + " | format: " + fmt);
      out += "<FMT-ERROR:" + m + ">";
   };
   for(size_t i = 0; i < fmt.size(); i++)
   {
      char c = fmt[i];
      if(c != '%') { out += c; continue; }
      if(i + 1 < fmt.size() && fmt[i + 1] == '%') { out += '%'; i++; continue; }
      size_t j = i + 1;
      std::string flags, width, prec;
      while(j < fmt.size() && strchr("-+ #0", fmt[j])) flags += fmt[j++];
      while(j < fmt.size() && isdigit((unsigned char)fmt[j])) width += fmt[j++];
      bool hasPrec = false;
      if(j < fmt.size() && fmt[j] == '.') { hasPrec = true; j++; while(j < fmt.size() && isdigit((unsigned char)fmt[j])) prec += fmt[j++]; }
      bool is64 = false;
      if(fmt.compare(j, 3, "I64") == 0) { is64 = true; j += 3; }
      else if(fmt.compare(j, 2, "ll") == 0) { is64 = true; j += 2; }
      else if(j < fmt.size() && (fmt[j] == 'l' || fmt[j] == 'h')) j++;
      if(j >= fmt.size()) { err("dangling %"); break; }
      char conv = fmt[j];
      i = j;
      if(ai >= args.size()) { err(std::string("missing argument for %") + conv); continue; }
      const Arg &a = args[ai++];
      std::string spec = "%" + flags + width + (hasPrec ? "." + prec : "");
      char buf[512];
      switch(conv)
      {
         case 'd': case 'i':
            if(a.kind == 'i') { snprintf(buf, sizeof buf, (spec + "lld").c_str(), a.i); out += buf; }
            else if(a.kind == 'l')
            {
               if(!is64) err("64-bit integer passed to %d (use %I64d)");
               else { snprintf(buf, sizeof buf, (spec + "lld").c_str(), a.i); out += buf; }
            }
            else err(std::string("%d given a non-signed-integer argument kind ") + a.kind);
            break;
         case 'u':
            if(a.kind == 'u') { snprintf(buf, sizeof buf, (spec + "llu").c_str(), a.u); out += buf; }
            else if(a.kind == 'U')
            {
               if(!is64) err("64-bit unsigned passed to %u (use %I64u)");
               else { snprintf(buf, sizeof buf, (spec + "llu").c_str(), a.u); out += buf; }
            }
            else err(std::string("%u given a non-unsigned argument kind ") + a.kind);
            break;
         case 'x': case 'X':
            if(a.kind == 'i' || a.kind == 'l') { snprintf(buf, sizeof buf, (spec + (conv == 'x' ? "llx" : "llX")).c_str(), a.i); out += buf; }
            else if(a.kind == 'u' || a.kind == 'U') { snprintf(buf, sizeof buf, (spec + (conv == 'x' ? "llx" : "llX")).c_str(), a.u); out += buf; }
            else err("%x given a non-integer argument");
            break;
         case 'f': case 'e': case 'E': case 'g': case 'G':
            if(a.kind == 'd') { snprintf(buf, sizeof buf, (spec + conv).c_str(), a.d); out += buf; }
            else err(std::string("%") + conv + " given a non-double argument kind " + a.kind);
            break;
         case 's':
            if(a.kind == 's') { out += a.s; }
            else err(std::string("%s given a non-string argument kind ") + a.kind);
            break;
         case 'c':
            if(a.kind == 'i') out += (char)a.i;
            else err("%c given a non-integer argument");
            break;
         default:
            err(std::string("unsupported conversion %") + conv);
      }
   }
   if(ai < args.size()) err("too many arguments (" + std::to_string(args.size()) + " given, " + std::to_string(ai) + " used)");
   return out;
}
} // namespace mqlfmt

template <class... A> string StringFormat(const string &fmt, const A &...a)
{
   std::vector<mqlfmt::Arg> args{mqlfmt::make(a)...};
   return mqlfmt::format(fmt, args);
}
template <class... A> void PrintFormat(const string &fmt, const A &...a)
{
   std::vector<mqlfmt::Arg> args{mqlfmt::make(a)...};
   sim::logLine(mqlfmt::format(fmt, args));
}
namespace mqlfmt
{
template <class T> std::string printArg(const T &v)
{
   Arg a = make(v);
   char buf[64];
   switch(a.kind)
   {
      case 's': return a.s;
      case 'd': snprintf(buf, sizeof buf, "%.15g", a.d); return buf;
      case 'u': case 'U': snprintf(buf, sizeof buf, "%llu", a.u); return buf;
      default: snprintf(buf, sizeof buf, "%lld", a.i); return buf;
   }
}
} // namespace mqlfmt
template <class... A> void Print(const A &...a)
{
   std::string s;
   ((s += mqlfmt::printArg(a)), ...);
   sim::logLine(s);
}
template <class... A> void Comment(const A &...a)
{
   std::string s;
   ((s += mqlfmt::printArg(a)), ...);
   sim::S.lastComment = s;
}

// ----------------------------------------------------------- MQL5 functions
inline string _Symbol = "XAUUSD";
inline double _Point = 0.01;
inline int    _Digits = 2;
inline int    _LastError = 0;
inline ENUM_TIMEFRAMES _Period = PERIOD_M15;

inline int  GetLastError() { return sim::S.lastError; }
inline void ResetLastError() { sim::S.lastError = 0; }
inline uint GetTickCount() { return (uint)((unsigned long)sim::S.now * 1000UL); }
inline bool IsStopped() { return false; }

template <class T> T MathAbs(const T v) { return v < 0 ? (T)(-v) : v; }
template <class A, class B> typename std::common_type<A, B>::type MathMax(const A a, const B b)
{
   typedef typename std::common_type<A, B>::type R;
   return ((R)a > (R)b) ? (R)a : (R)b;
}
template <class A, class B> typename std::common_type<A, B>::type MathMin(const A a, const B b)
{
   typedef typename std::common_type<A, B>::type R;
   return ((R)a < (R)b) ? (R)a : (R)b;
}
inline double MathFloor(const double v) { return std::floor(v); }
inline double MathCeil(const double v) { return std::ceil(v); }
inline double MathRound(const double v) { return std::round(v); }
inline double MathSqrt(const double v) { return std::sqrt(v); }
inline double MathPow(const double b, const double e) { return std::pow(b, e); }
inline double MathLog(const double v) { return std::log(v); }
inline double MathExp(const double v) { return std::exp(v); }
inline double MathMod(const double a, const double b) { return std::fmod(a, b); }
inline bool   MathIsValidNumber(const double v) { return std::isfinite(v); }
inline double NormalizeDouble(const double v, const int digits)
{
   double p = std::pow(10.0, digits);
   return std::round(v * p) / p;
}

inline string IntegerToString(const long v, const int width = 0, const ushort fill = ' ')
{
   std::string s = std::to_string(v);
   while((int)s.size() < width) s.insert(s.begin(), (char)fill);
   return s;
}
inline string DoubleToString(const double v, const int digits = 8)
{
   char buf[64];
   snprintf(buf, sizeof buf, "%.*f", digits, v);
   return buf;
}
inline int StringLen(const string &s) { return (int)s.size(); }
inline int StringFind(const string &s, const string &what, const int start = 0)
{
   size_t p = s.find(what, (size_t)std::max(0, start));
   return p == std::string::npos ? -1 : (int)p;
}
inline string StringSubstr(const string &s, const int start, const int len = -1)
{
   if(start < 0 || (size_t)start >= s.size()) return "";
   return len < 0 ? s.substr((size_t)start) : s.substr((size_t)start, (size_t)len);
}
inline bool StringToUpper(string &s) { for(char &c : s) c = (char)toupper((unsigned char)c); return true; }
inline bool StringToLower(string &s) { for(char &c : s) c = (char)tolower((unsigned char)c); return true; }
inline int StringReplace(string &s, const string &find, const string &repl)
{
   if(find.empty()) return 0;
   int n = 0;
   size_t pos = 0;
   while((pos = s.find(find, pos)) != std::string::npos) { s.replace(pos, find.size(), repl); pos += repl.size(); n++; }
   return n;
}
inline long   StringToInteger(const string &s) { return atol(s.c_str()); }
inline double StringToDouble(const string &s) { return atof(s.c_str()); }

inline datetime TimeCurrent() { return sim::S.lastTickTime; }
inline datetime TimeTradeServer() { return sim::S.now; }
inline datetime TimeLocal() { return sim::S.now; }
inline bool TimeToStruct(const datetime t, MqlDateTime &dt)
{
   long days = (t >= 0 ? t / 86400 : (t - 86399) / 86400);
   long rem = t - days * 86400;
   sim::civilFromDays(days, dt.year, dt.mon, dt.day);
   dt.hour = (int)(rem / 3600);
   dt.min = (int)(rem % 3600 / 60);
   dt.sec = (int)(rem % 60);
   dt.day_of_week = sim::dayOfWeek(t);
   dt.day_of_year = (int)(days - sim::daysFromCivil(dt.year, 1, 1));
   return true;
}
inline datetime StructToTime(const MqlDateTime &dt) { return sim::makeTime(dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec); }
inline string TimeToString(const datetime t, const int mode = TIME_DATE | TIME_MINUTES) { return sim::timeString(t, mode); }

// --- series ---
inline int iBars(const string symbol, const ENUM_TIMEFRAMES tf)
{
   sim::Series *s = sim::seriesFor(symbol, tf);
   return s ? s->size() : 0;
}
inline datetime iTime(const string symbol, const ENUM_TIMEFRAMES tf, const int shift)
{
   sim::Series *s = sim::seriesFor(symbol, tf);
   const sim::Bar *b = s ? s->at(shift) : nullptr;
   return b ? b->time : 0;
}
inline double iOpen(const string symbol, const ENUM_TIMEFRAMES tf, const int shift)
{
   sim::Series *s = sim::seriesFor(symbol, tf);
   const sim::Bar *b = s ? s->at(shift) : nullptr;
   return b ? b->open : 0.0;
}
inline double iHigh(const string symbol, const ENUM_TIMEFRAMES tf, const int shift)
{
   sim::Series *s = sim::seriesFor(symbol, tf);
   const sim::Bar *b = s ? s->at(shift) : nullptr;
   return b ? b->high : 0.0;
}
inline double iLow(const string symbol, const ENUM_TIMEFRAMES tf, const int shift)
{
   sim::Series *s = sim::seriesFor(symbol, tf);
   const sim::Bar *b = s ? s->at(shift) : nullptr;
   return b ? b->low : 0.0;
}
inline double iClose(const string symbol, const ENUM_TIMEFRAMES tf, const int shift)
{
   sim::Series *s = sim::seriesFor(symbol, tf);
   const sim::Bar *b = s ? s->at(shift) : nullptr;
   return b ? b->close : 0.0;
}
inline long iVolume(const string symbol, const ENUM_TIMEFRAMES tf, const int shift)
{
   sim::Series *s = sim::seriesFor(symbol, tf);
   const sim::Bar *b = s ? s->at(shift) : nullptr;
   return b ? b->volume : 0;
}

// --- indicator handles ---
inline int iMA(const string symbol, const ENUM_TIMEFRAMES tf, const int period, const int ma_shift,
               const ENUM_MA_METHOD method, const ENUM_APPLIED_PRICE price)
{
   if(symbol != sim::S.sym.name || sim::tfIndex(tf) < 0 || method != MODE_EMA || price != PRICE_CLOSE || ma_shift != 0 || period < 1)
   { sim::apiError("iMA: unsupported parameters in the simulator"); return INVALID_HANDLE; }
   sim::Indicator ind{};
   ind.kind = 1; ind.tf = tf; ind.period = period; ind.released = false; ind.trSum = 0.0;
   sim::S.indicators.push_back(ind);
   return (int)sim::S.indicators.size() - 1;
}
inline int iATR(const string symbol, const ENUM_TIMEFRAMES tf, const int period)
{
   if(symbol != sim::S.sym.name || sim::tfIndex(tf) < 0 || period < 1)
   { sim::apiError("iATR: unsupported parameters in the simulator"); return INVALID_HANDLE; }
   sim::Indicator ind{};
   ind.kind = 2; ind.tf = tf; ind.period = period; ind.released = false; ind.trSum = 0.0;
   sim::S.indicators.push_back(ind);
   return (int)sim::S.indicators.size() - 1;
}
inline bool IndicatorRelease(const int handle)
{
   if(handle < 0 || (size_t)handle >= sim::S.indicators.size()) return false;
   sim::S.indicators[(size_t)handle].released = true;
   return true;
}
inline int CopyBuffer(const int handle, const int buffer_num, const int start_pos, const int count, MqlArray<double> &buffer)
{
   if(handle < 0 || (size_t)handle >= sim::S.indicators.size() || buffer_num != 0 || count < 1 || start_pos < 0)
   { sim::S.lastError = 4807; return -1; }
   sim::Indicator &ind = sim::S.indicators[(size_t)handle];
   if(ind.released) { sim::S.lastError = 4807; return -1; }
   sim::indicatorCatchUp(ind);
   sim::Series &ser = sim::S.series[sim::tfIndex(ind.tf)];
   int n = ser.size();
   // shift 0 is the forming bar: only closed bars carry a value here
   if(start_pos == 0) { sim::apiError("CopyBuffer at shift 0 (forming bar) is not modelled"); return -1; }
   int newest = n - 1 - start_pos;            // index of the newest requested bar
   int oldest = newest - (count - 1);
   if(oldest < 0 || newest >= (int)ind.val.size()) { sim::S.lastError = 4806; return -1; }
   // a moving average / ATR is "not calculated" until it has a full window
   if(oldest + 1 < ind.period) { sim::S.lastError = 4806; return -1; }
   buffer.v.resize((size_t)count);
   for(int k = 0; k < count; k++) buffer.v[(size_t)k] = ind.val[(size_t)(oldest + k)];
   return count;
}

// --- symbol / account / terminal ---
inline bool SymbolSelect(const string name, const bool select) { (void)select; return name == sim::S.sym.name; }
inline long SymbolInfoInteger(const string name, const ENUM_SYMBOL_INFO_INTEGER prop)
{
   if(name != sim::S.sym.name) { sim::apiError("SymbolInfoInteger foreign symbol"); return 0; }
   switch(prop)
   {
      case SYMBOL_DIGITS: return sim::S.sym.digits;
      case SYMBOL_SPREAD: return (long)std::llround((sim::S.ask - sim::S.bid) / sim::S.sym.point);
      case SYMBOL_TRADE_STOPS_LEVEL: return sim::S.sym.stopsLevel;
      case SYMBOL_TRADE_FREEZE_LEVEL: return sim::S.sym.freezeLevel;
      case SYMBOL_EXPIRATION_MODE: return sim::S.expirationMode;
      case SYMBOL_TRADE_MODE: return sim::S.sym.tradeMode;
      case SYMBOL_TRADE_EXEMODE: return sim::S.sym.execMode;
      case SYMBOL_FILLING_MODE: return sim::S.sym.fillingMode;
      case SYMBOL_TIME: return sim::S.lastTickTime;
      case SYMBOL_SELECT: return 1;
      case SYMBOL_VISIBLE: return 1;
      default: sim::apiError("SymbolInfoInteger property not modelled: " + std::to_string((int)prop)); return 0;
   }
}
inline double SymbolInfoDouble(const string name, const ENUM_SYMBOL_INFO_DOUBLE prop)
{
   if(name != sim::S.sym.name) { sim::apiError("SymbolInfoDouble foreign symbol"); return 0.0; }
   switch(prop)
   {
      case SYMBOL_BID: return sim::S.bid;
      case SYMBOL_ASK: return sim::S.ask;
      case SYMBOL_LAST: return sim::S.bid;
      case SYMBOL_POINT: return sim::S.sym.point;
      case SYMBOL_TRADE_TICK_VALUE: return sim::S.sym.tickValue;
      case SYMBOL_TRADE_TICK_SIZE: return sim::S.sym.tickSize;
      case SYMBOL_TRADE_CONTRACT_SIZE: return sim::S.sym.contractSize;
      case SYMBOL_VOLUME_MIN: return sim::S.sym.volMin;
      case SYMBOL_VOLUME_MAX: return sim::S.sym.volMax;
      case SYMBOL_VOLUME_STEP: return sim::S.sym.volStep;
      case SYMBOL_VOLUME_LIMIT: return sim::S.sym.volLimit;
      default: sim::apiError("SymbolInfoDouble property not modelled: " + std::to_string((int)prop)); return 0.0;
   }
}
inline string SymbolInfoString(const string name, const ENUM_SYMBOL_INFO_STRING prop)
{
   (void)name; (void)prop;
   return sim::S.acc.currency;
}
inline long AccountInfoInteger(const ENUM_ACCOUNT_INFO_INTEGER prop)
{
   switch(prop)
   {
      case ACCOUNT_LOGIN: return sim::S.acc.login;
      case ACCOUNT_TRADE_MODE: return sim::S.acc.tradeMode;
      case ACCOUNT_LEVERAGE: return sim::S.acc.leverage;
      case ACCOUNT_TRADE_ALLOWED: return sim::S.acc.tradeAllowed ? 1 : 0;
      case ACCOUNT_TRADE_EXPERT: return 1;
      case ACCOUNT_MARGIN_MODE: return sim::S.acc.marginMode;
      case ACCOUNT_CURRENCY_DIGITS: return 2;
      default: sim::apiError("AccountInfoInteger property not modelled: " + std::to_string((int)prop)); return 0;
   }
}
inline double AccountInfoDouble(const ENUM_ACCOUNT_INFO_DOUBLE prop)
{
   switch(prop)
   {
      case ACCOUNT_BALANCE: return sim::S.acc.balance;
      case ACCOUNT_EQUITY: return sim::equity();
      case ACCOUNT_PROFIT: return sim::equity() - sim::S.acc.balance;
      case ACCOUNT_MARGIN: return sim::usedMargin();
      case ACCOUNT_MARGIN_FREE: return sim::equity() - sim::usedMargin();
      case ACCOUNT_MARGIN_LEVEL: { double m = sim::usedMargin(); return m > 0.0 ? sim::equity() / m * 100.0 : 0.0; }
      case ACCOUNT_CREDIT: return 0.0;
      default: sim::apiError("AccountInfoDouble property not modelled: " + std::to_string((int)prop)); return 0.0;
   }
}
inline string AccountInfoString(const ENUM_ACCOUNT_INFO_STRING prop)
{
   switch(prop)
   {
      case ACCOUNT_SERVER: return sim::S.acc.server;
      case ACCOUNT_CURRENCY: return sim::S.acc.currency;
      case ACCOUNT_NAME: return sim::S.acc.name;
      default: return "";
   }
}
inline int TerminalInfoInteger(const ENUM_TERMINAL_INFO_INTEGER prop)
{
   switch(prop)
   {
      case TERMINAL_TRADE_ALLOWED: return sim::S.terminalTradeAllowed ? 1 : 0;
      case TERMINAL_CONNECTED: return 1;
      default: return 0;
   }
}
inline int MQLInfoInteger(const ENUM_MQL_INFO_INTEGER prop)
{
   switch(prop)
   {
      case MQL_TRADE_ALLOWED: return sim::S.mqlTradeAllowed ? 1 : 0;
      case MQL_TESTER: return 0;
      default: return 0;
   }
}

// --- terminal global variables ---
inline bool GlobalVariableCheck(const string name) { return sim::S.gv.count(name) != 0; }
inline double GlobalVariableGet(const string name)
{
   auto it = sim::S.gv.find(name);
   if(it == sim::S.gv.end()) { sim::S.lastError = 4501; return 0.0; }
   return it->second;
}
inline datetime GlobalVariableSet(const string name, const double value)
{
   if(name.empty() || name.size() > 63) { sim::apiError("GlobalVariableSet: name empty or longer than 63 characters: " + name); return 0; }
   sim::S.gv[name] = value;
   return sim::S.now > 0 ? sim::S.now : 1;
}
inline bool GlobalVariableDel(const string name) { return sim::S.gv.erase(name) != 0; }
inline bool GlobalVariableTemp(const string name)
{
   if(name.empty() || name.size() > 63) { sim::apiError("GlobalVariableTemp: name empty or longer than 63 characters: " + name); return false; }
   if(!sim::S.gv.count(name)) sim::S.gv[name] = 0.0;
   return true;
}
inline bool GlobalVariableSetOnCondition(const string name, const double value, const double check_value)
{
   auto it = sim::S.gv.find(name);
   if(it == sim::S.gv.end()) { sim::S.lastError = 4501; return false; }
   if(it->second != check_value) return false;
   it->second = value;
   return true;
}
inline void GlobalVariablesFlush() {}

// --- trading ---
inline bool OrderCalcProfit(const ENUM_ORDER_TYPE action, const string symbol, const double volume,
                            const double price_open, const double price_close, double &profit)
{
   if(symbol != sim::S.sym.name || volume <= 0.0) return false;
   double diff = (action == ORDER_TYPE_BUY) ? (price_close - price_open) : (price_open - price_close);
   profit = diff * sim::moneyPerPriceUnit(volume);
   return true;
}
inline bool OrderCalcMargin(const ENUM_ORDER_TYPE action, const string symbol, const double volume,
                            const double price, double &margin)
{
   (void)action;
   if(symbol != sim::S.sym.name || volume <= 0.0 || price <= 0.0) return false;
   margin = sim::marginOf(volume, price);
   return true;
}
inline bool OrderSend(const MqlTradeRequest &request, MqlTradeResult &result) { return sim::serverSend(request, result); }

namespace sim { inline long selectedPosition = -1; }
// --- pending orders (the OrdersTotal table) ---
namespace sim { inline long selectedOrder = -1; }
inline int OrdersTotal() { return (int)sim::S.orders.size(); }
inline ulong OrderGetTicket(const int index)
{
   if(index < 0 || (size_t)index >= sim::S.orders.size()) { sim::selectedOrder = -1; return 0; }
   sim::selectedOrder = index;
   return sim::S.orders[(size_t)index].ticket;
}
inline bool OrderSelect(const ulong ticket)
{
   for(size_t i = 0; i < sim::S.orders.size(); i++)
      if(sim::S.orders[i].ticket == ticket) { sim::selectedOrder = (long)i; return true; }
   sim::selectedOrder = -1;
   return false;
}
inline sim::PendingOrder *selOrder()
{
   if(sim::selectedOrder < 0 || (size_t)sim::selectedOrder >= sim::S.orders.size()) return nullptr;
   return &sim::S.orders[(size_t)sim::selectedOrder];
}
inline long OrderGetInteger(const ENUM_ORDER_PROPERTY_INTEGER prop)
{
   sim::PendingOrder *o = selOrder();
   if(!o) { sim::apiError("OrderGetInteger with no order selected"); return 0; }
   switch(prop)
   {
      case ORDER_TICKET: return (long)o->ticket;
      case ORDER_MAGIC: return o->magic;
      case ORDER_TYPE: return o->type;
      case ORDER_STATE: return o->state;
      case ORDER_TIME_SETUP: return (long)o->timeSetup;
      case ORDER_TIME_EXPIRATION: return (long)o->timeExpiration;
      case ORDER_TYPE_TIME: return o->typeTime;
      default: sim::apiError("OrderGetInteger property not modelled: " + std::to_string((int)prop)); return 0;
   }
}
inline double OrderGetDouble(const ENUM_ORDER_PROPERTY_DOUBLE prop)
{
   sim::PendingOrder *o = selOrder();
   if(!o) { sim::apiError("OrderGetDouble with no order selected"); return 0.0; }
   switch(prop)
   {
      case ORDER_VOLUME_CURRENT: return o->volume;
      case ORDER_PRICE_OPEN: return o->price;
      case ORDER_SL: return o->sl;
      case ORDER_TP: return o->tp;
      default: sim::apiError("OrderGetDouble property not modelled: " + std::to_string((int)prop)); return 0.0;
   }
}
inline string OrderGetString(const ENUM_ORDER_PROPERTY_STRING prop)
{
   sim::PendingOrder *o = selOrder();
   if(!o) { sim::apiError("OrderGetString with no order selected"); return ""; }
   switch(prop)
   {
      case ORDER_SYMBOL: return o->symbol;
      case ORDER_COMMENT: return o->comment;
      default: return "";
   }
}
inline bool OrderDelete(const ulong ticket)
{
   MqlTradeRequest rq{};
   MqlTradeResult rs{};
   rq.action = TRADE_ACTION_REMOVE;
   rq.order = ticket;
   rq.symbol = sim::S.sym.name;
   return sim::serverSend(rq, rs);
}

inline int PositionsTotal() { return (int)sim::S.positions.size(); }
inline ulong PositionGetTicket(const int index)
{
   if(index < 0 || (size_t)index >= sim::S.positions.size()) { sim::selectedPosition = -1; return 0; }
   sim::selectedPosition = index;
   return sim::S.positions[(size_t)index].ticket;
}
inline bool PositionSelectByTicket(const ulong ticket)
{
   for(size_t i = 0; i < sim::S.positions.size(); i++)
      if(sim::S.positions[i].ticket == ticket) { sim::selectedPosition = (long)i; return true; }
   sim::selectedPosition = -1;
   return false;
}
inline bool PositionSelect(const string symbol)
{
   for(size_t i = 0; i < sim::S.positions.size(); i++)
      if(sim::S.positions[i].symbol == symbol) { sim::selectedPosition = (long)i; return true; }
   sim::selectedPosition = -1;
   return false;
}
namespace sim
{
inline const Position *selPos()
{
   if(selectedPosition < 0 || (size_t)selectedPosition >= S.positions.size())
   { apiError("Position property read without a selected position"); return nullptr; }
   return &S.positions[(size_t)selectedPosition];
}
}
inline long PositionGetInteger(const ENUM_POSITION_PROPERTY_INTEGER prop)
{
   const sim::Position *p = sim::selPos();
   if(!p) return 0;
   switch(prop)
   {
      case POSITION_TICKET: return (long)p->ticket;
      case POSITION_IDENTIFIER: return (long)p->ticket;
      case POSITION_TIME: return p->time;
      case POSITION_TIME_MSC: return p->time * 1000;
      case POSITION_TYPE: return p->type;
      case POSITION_MAGIC: return p->magic;
      default: sim::apiError("PositionGetInteger property not modelled"); return 0;
   }
}
inline double PositionGetDouble(const ENUM_POSITION_PROPERTY_DOUBLE prop)
{
   const sim::Position *p = sim::selPos();
   if(!p) return 0.0;
   switch(prop)
   {
      case POSITION_VOLUME: return p->volume;
      case POSITION_PRICE_OPEN: return p->priceOpen;
      case POSITION_SL: return p->sl;
      case POSITION_TP: return p->tp;
      case POSITION_PRICE_CURRENT: return p->type == POSITION_TYPE_BUY ? sim::S.bid : sim::S.ask;
      case POSITION_PROFIT: return sim::floatingOf(*p);
      case POSITION_SWAP: return 0.0;
      default: sim::apiError("PositionGetDouble property not modelled"); return 0.0;
   }
}
inline string PositionGetString(const ENUM_POSITION_PROPERTY_STRING prop)
{
   const sim::Position *p = sim::selPos();
   if(!p) return "";
   return prop == POSITION_SYMBOL ? p->symbol : p->comment;
}

inline bool HistorySelect(const datetime from, const datetime to)
{
   sim::S.selected.clear();
   sim::S.selectedExtra.clear();
   for(const sim::Deal &d : sim::S.deals)
      if(d.time >= from && d.time <= to) sim::S.selected.push_back(d.ticket);
   return true;
}
inline bool HistorySelectByPosition(const long position_id)
{
   sim::S.selected.clear();
   sim::S.selectedExtra.clear();
   for(const sim::Deal &d : sim::S.deals)
      if(d.positionId == position_id) sim::S.selected.push_back(d.ticket);
   return true;
}
inline int HistoryDealsTotal() { return (int)sim::S.selected.size(); }
inline ulong HistoryDealGetTicket(const int index)
{
   if(index < 0 || (size_t)index >= sim::S.selected.size()) return 0;
   return sim::S.selected[(size_t)index];
}
inline bool HistoryDealSelect(const ulong ticket)
{
   if(!sim::findDeal(ticket)) return false;
   sim::S.selectedExtra.push_back(ticket);
   if(sim::S.selectedExtra.size() > 64) sim::S.selectedExtra.erase(sim::S.selectedExtra.begin());
   return true;
}
namespace sim
{
inline const Deal *visibleDeal(ulong ticket)
{
   const Deal *d = findDeal(ticket);
   if(!d) return nullptr;
   if(!dealVisible(ticket)) { apiError("HistoryDealGet* on a deal that is not in the selected history: " + std::to_string(ticket)); return nullptr; }
   return d;
}
}
inline long HistoryDealGetInteger(const ulong ticket, const ENUM_DEAL_PROPERTY_INTEGER prop)
{
   const sim::Deal *d = sim::visibleDeal(ticket);
   if(!d) return 0;
   switch(prop)
   {
      case DEAL_TICKET: return (long)d->ticket;
      case DEAL_ORDER: return (long)d->order;
      case DEAL_TIME: return d->time;
      case DEAL_TIME_MSC: return d->time * 1000;
      case DEAL_TYPE: return d->type;
      case DEAL_ENTRY: return d->entry;
      case DEAL_MAGIC: return d->magic;
      case DEAL_REASON: return d->reason;
      case DEAL_POSITION_ID: return d->positionId;
      default: sim::apiError("HistoryDealGetInteger property not modelled"); return 0;
   }
}
inline double HistoryDealGetDouble(const ulong ticket, const ENUM_DEAL_PROPERTY_DOUBLE prop)
{
   const sim::Deal *d = sim::visibleDeal(ticket);
   if(!d) return 0.0;
   switch(prop)
   {
      case DEAL_VOLUME: return d->volume;
      case DEAL_PRICE: return d->price;
      case DEAL_COMMISSION: return d->commission;
      case DEAL_SWAP: return d->swap;
      case DEAL_PROFIT: return d->profit;
      case DEAL_FEE: return d->fee;
      case DEAL_SL: return d->sl;
      case DEAL_TP: return d->tp;
      default: sim::apiError("HistoryDealGetDouble property not modelled"); return 0.0;
   }
}
inline string HistoryDealGetString(const ulong ticket, const ENUM_DEAL_PROPERTY_STRING prop)
{
   const sim::Deal *d = sim::visibleDeal(ticket);
   if(!d) return "";
   return prop == DEAL_SYMBOL ? d->symbol : d->comment;
}

// --- CTrade (the subset of <Trade/Trade.mqh> the EA uses, same signatures) ---
class CTrade
{
   ulong m_magic = 0;
   ulong m_deviation = 10;
   ENUM_ORDER_TYPE_FILLING m_filling = ORDER_FILLING_FOK;
   MqlTradeResult m_result{};

   // CTrade::FillingCheck of the standard library: on REQUEST / INSTANT execution the
   // server places the filling type; on MARKET execution the library itself switches
   // to a policy the symbol supports (FOK first, then IOC); on EXCHANGE execution the
   // configured policy must be one the symbol supports.
   bool fillingCheck()
   {
      long exec = sim::S.sym.execMode;
      if(exec == SYMBOL_TRADE_EXECUTION_REQUEST || exec == SYMBOL_TRADE_EXECUTION_INSTANT) return true;
      long filling = sim::S.sym.fillingMode;
      if(exec == SYMBOL_TRADE_EXECUTION_MARKET)
      {
         if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) { m_filling = ORDER_FILLING_FOK; return true; }
         if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) { m_filling = ORDER_FILLING_IOC; return true; }
         m_result = MqlTradeResult{};
         m_result.retcode = TRADE_RETCODE_INVALID_FILL;
         return false;
      }
      if(m_filling == ORDER_FILLING_FOK && (filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) return true;
      if(m_filling == ORDER_FILLING_IOC && (filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) return true;
      if(m_filling == ORDER_FILLING_RETURN) return true;
      m_result = MqlTradeResult{};
      m_result.retcode = TRADE_RETCODE_INVALID_FILL;
      return false;
   }

   bool open(const ENUM_ORDER_TYPE type, const double volume, const string symbol, const double sl, const double tp, const string comment)
   {
      if(!fillingCheck()) return false;
      MqlTradeRequest rq{};
      rq.action = TRADE_ACTION_DEAL;
      rq.symbol = symbol;
      rq.magic = m_magic;
      rq.volume = volume;
      rq.type = type;
      rq.price = (type == ORDER_TYPE_BUY) ? sim::S.ask : sim::S.bid;
      rq.sl = sl;
      rq.tp = tp;
      rq.deviation = m_deviation;
      rq.type_filling = m_filling;
      rq.comment = comment;
      return sim::serverSend(rq, m_result);
   }

public:
   void SetExpertMagicNumber(const ulong magic) { m_magic = magic; }
   void SetDeviationInPoints(const ulong deviation) { m_deviation = deviation; }
   void SetTypeFilling(const ENUM_ORDER_TYPE_FILLING filling) { m_filling = filling; }
   bool Buy(const double volume, const string symbol = "", double price = 0.0, const double sl = 0.0, const double tp = 0.0, const string comment = "")
   {
      (void)price;
      return open(ORDER_TYPE_BUY, volume, symbol.empty() ? sim::S.sym.name : symbol, sl, tp, comment);
   }
   bool Sell(const double volume, const string symbol = "", double price = 0.0, const double sl = 0.0, const double tp = 0.0, const string comment = "")
   {
      (void)price;
      return open(ORDER_TYPE_SELL, volume, symbol.empty() ? sim::S.sym.name : symbol, sl, tp, comment);
   }
   // CTrade::OrderOpen / OrderModify / OrderDelete, same signatures as the
   // standard library, so the EA source is the bytes MetaEditor compiles.
   //
   // OrderOpen is SYNTAX-EXACT with Trade.mqh and it matters twice over:
   //   * the SYMBOL is the first parameter - a 9-argument call silently resolves
   //     to this overload and MetaEditor then reports "cannot convert enum" on
   //     the order type (this is the v1.21 F7 error, reproduced here);
   //   * limit_price comes BEFORE price. Anything but a StopLimit order passes
   //     limit_price = 0.0 and the real execution price in `price`; swapping them
   //     builds a StopLimit request and the order never behaves as a limit.
   bool OrderOpen(const string symbol, const ENUM_ORDER_TYPE type, const double volume,
                  const double limit_price, const double price, const double sl = 0.0, const double tp = 0.0,
                  const ENUM_ORDER_TYPE_TIME type_time = ORDER_TIME_GTC,
                  const datetime expiration = 0, const string comment = "")
   {
      if(type != ORDER_TYPE_BUY_LIMIT && type != ORDER_TYPE_SELL_LIMIT &&
         type != ORDER_TYPE_BUY_STOP && type != ORDER_TYPE_SELL_STOP &&
         type != ORDER_TYPE_BUY_STOP_LIMIT && type != ORDER_TYPE_SELL_STOP_LIMIT)
         return false;                                   // Trade.mqh checks the order type
      if(!symbol.empty() && symbol != sim::S.sym.name)
         return false;                                   // the server refuses a foreign symbol
      if(limit_price != 0.0 && type != ORDER_TYPE_BUY_STOP_LIMIT && type != ORDER_TYPE_SELL_STOP_LIMIT)
         return false;                                   // a limit_price only belongs to a StopLimit
      if(type == ORDER_TYPE_BUY_STOP_LIMIT || type == ORDER_TYPE_SELL_STOP_LIMIT)
         return false;                                   // not implemented: the EA never sends one
      MqlTradeRequest rq{};
      rq.action = TRADE_ACTION_PENDING;
      rq.symbol = symbol;
      rq.magic = m_magic;
      rq.volume = volume;
      rq.type = type;
      rq.price = price;
      rq.sl = sl;
      rq.tp = tp;
      rq.type_time = type_time;
      rq.expiration = expiration;
      rq.deviation = m_deviation;
      rq.type_filling = m_filling;
      rq.comment = comment;
      return sim::serverSend(rq, m_result);
   }
   bool OrderModify(const ulong ticket, const double price, const double sl, const double tp,
                    const ENUM_ORDER_TYPE_TIME type_time = ORDER_TIME_GTC, const datetime expiration = 0,
                    const double stoplimit = 0.0)
   {
      (void)stoplimit;
      MqlTradeRequest rq{};
      rq.action = TRADE_ACTION_MODIFY;
      rq.symbol = sim::S.sym.name;
      rq.magic = m_magic;
      rq.order = ticket;
      rq.price = price;
      rq.sl = sl;
      rq.tp = tp;
      rq.type_time = type_time;
      rq.expiration = expiration;
      return sim::serverSend(rq, m_result);
   }
   bool OrderDelete(const ulong ticket)
   {
      MqlTradeRequest rq{};
      rq.action = TRADE_ACTION_REMOVE;
      rq.symbol = sim::S.sym.name;
      rq.magic = m_magic;
      rq.order = ticket;
      return sim::serverSend(rq, m_result);
   }

   bool PositionModify(const ulong ticket, const double sl, const double tp)
   {
      MqlTradeRequest rq{};
      rq.action = TRADE_ACTION_SLTP;
      rq.symbol = sim::S.sym.name;
      rq.position = ticket;
      rq.sl = sl;
      rq.tp = tp;
      rq.magic = m_magic;
      return sim::serverSend(rq, m_result);
   }
   bool PositionClose(const ulong ticket, const ulong deviation = 0xFFFFFFFFFFFFFFFFUL)
   {
      (void)deviation;
      for(const sim::Position &p : sim::S.positions)
         if(p.ticket == ticket)
         {
            if(!fillingCheck()) return false;
            MqlTradeRequest rq{};
            rq.action = TRADE_ACTION_DEAL;
            rq.symbol = p.symbol;
            rq.position = ticket;
            rq.volume = p.volume;
            rq.type = (p.type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            rq.magic = m_magic;
            rq.type_filling = m_filling;
            return sim::serverSend(rq, m_result);
         }
      m_result = MqlTradeResult{};
      m_result.retcode = TRADE_RETCODE_POSITION_CLOSED;
      return false;
   }
   uint   ResultRetcode() const { return m_result.retcode; }
   ulong  ResultDeal() const { return m_result.deal; }
   ulong  ResultOrder() const { return m_result.order; }
   double ResultVolume() const { return m_result.volume; }
   double ResultPrice() const { return m_result.price; }
   double ResultBid() const { return m_result.bid; }
   double ResultAsk() const { return m_result.ask; }
   string ResultComment() const { return m_result.comment; }
   string ResultRetcodeDescription() const { return sim::retcodeText(m_result.retcode); }
};
