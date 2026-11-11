// qats_market.inc - a deterministic synthetic market and a tick player, shared by
// the dual-direction scenarios and by the version-independent reproductions.
// Nothing here depends on v1.20: it only uses the event handlers, the inputs and
// the simulator, so the SAME market can be replayed through v1.11 and v1.20.
#pragma GCC system_header

namespace drv
{
static const datetime kMonday = 1704067200;   // 2024-01-01 00:00, a Monday

static void resetSimOnly()
{
   sim::reset();
   sim::selectedPosition = -1;
   FeedCfg cfg;
   applySymbolGrid(cfg);
   static const ENUM_TIMEFRAMES tfs[6] = {PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1, PERIOD_W1};
   for(int i = 0; i < 6; i++) sim::S.series[i].tf = tfs[i];
   g_spec.digits = sim::S.sym.digits;
   g_spec.point = sim::S.sym.point;
   g_spec.tickSize = sim::S.sym.tickSize;
}

// --------------------------------------------------------- journal capture
static Journal JR;
static FILE *g_selftestLog = nullptr;       // optional MT5-format journal of the scenario (--log)
static void captureJournal()
{
   JR = Journal();
   JR.capture = true;
   sim::S.onPrint = [](const std::string &s) { JR.on(s); };
   sim::S.logFile = g_selftestLog;
}
static int linesWith(const std::string &a, const std::string &b = "", const std::string &c = "")
{
   int n = 0;
   for(const std::string &s : JR.keep)
      if(s.find(a) != std::string::npos && (b.empty() || s.find(b) != std::string::npos) && (c.empty() || s.find(c) != std::string::npos)) n++;
   return n;
}
static std::string firstWith(const std::string &a, const std::string &b = "", const std::string &c = "")
{
   for(const std::string &s : JR.keep)
      if(s.find(a) != std::string::npos && (b.empty() || s.find(b) != std::string::npos) && (c.empty() || s.find(c) != std::string::npos)) return s;
   return "";
}
static std::string lastWith(const std::string &a, const std::string &b = "")
{
   for(size_t i = JR.keep.size(); i-- > 0;)
      if(JR.keep[i].find(a) != std::string::npos && (b.empty() || JR.keep[i].find(b) != std::string::npos)) return JR.keep[i];
   return "";
}
static void dumpJournal(const std::string &filter = "")
{
   for(const std::string &s : JR.keep)
      if(filter.empty() || s.find(filter) != std::string::npos) printf("    | %s\n", s.c_str());
}
// ------------------------------------------------------- synthetic market
// Price at every trading-minute boundary. Five 24h days a week, no weekend ticks.
struct Scn
{
   std::vector<double> px;
   double cur;
   explicit Scn(double start) : cur(start) { px.push_back(start); }
   void to(int minutes, double target)
   {
      double s = cur;
      for(int i = 1; i <= minutes; i++) px.push_back(s + (target - s) * i / minutes);
      cur = target;
   }
   // one H1 bar that nets `step` but first leans 0.75 x |step| the other way: the
   // range is then 1.75 x the body, so an ordinary bar is never "displacement"
   void bar(double step)
   {
      double s = cur;
      to(20, s - 0.75 * step);
      to(40, s + step);
   }
   void leg(int bars, double total) { for(int i = 0; i < bars; i++) bar(total / bars); }
   size_t bars() const { return px.size() - 1; }
};

static datetime scnTime(size_t idx)
{
   return kMonday + (datetime)(idx / 7200) * 7 * 86400 + (datetime)(idx % 7200) * 60;
}

struct Player
{
   FeedCfg feed;
   size_t pos = 0;
   bool attached = false;
   long volume = 100;
   Player() { feed.spreadMode = 2; feed.spreadFixedPts = 20; }
   void play(const Scn &sc, size_t upTo)
   {
      Tick tk[4];
      for(; pos < upTo && pos < sc.bars(); pos++)
      {
         M1 r{};
         r.ob = sc.px[pos]; r.cb = sc.px[pos + 1];
         r.hb = std::max(r.ob, r.cb); r.lb = std::min(r.ob, r.cb);
         r.oa = r.ob; r.ha = r.hb; r.la = r.lb; r.ca = r.cb;
         r.vol = (double)volume / 1000.0;
         int n = ticksFromM1(r, feed, scnTime(pos), tk);
         for(int i = 0; i < n; i++)
            sim::feedTick(tk[i].t, ptsToPrice(tk[i].bidPts, feed), ptsToPrice(tk[i].askPts, feed), tk[i].vol, tk[i].gap, attached);
      }
   }
   int attach(const Scn &sc)
   {
      sim::S.now = scnTime(pos);
      sim::S.lastTickTime = sim::S.now;
      int rc = OnInit();
      attached = true;
      return rc;
   }
};

// 60 trading days of a rising market: 5 bars up (+6), 3 bars down (-4).
static void uptrend(Scn &sc, int cycles)
{
   for(int i = 0; i < cycles; i++) { sc.leg(5, 6.0); sc.leg(3, -4.0); }
   sc.leg(5, 6.0);                      // end on a peak
}

struct Marks { size_t attachAt = 0, entryAt = 0, endAt = 0; double peak = 0.0; };

// Strong reversal-continuation setup in the direction of the trend:
//   a slow 6-bar pullback (stale structure), one bar that runs the last swing low
//   and closes back above it (SSL sweep), one impulsive bar that closes above the
//   last swing high (displacement + BOS), then follow-through.
static Marks patternFullChain(Scn &sc, bool followThrough = true)
{
   Marks m;
   uptrend(sc, 180);
   m.peak = sc.cur;
   double P = sc.cur;
   sc.leg(6, -4.6);                     // H1..H6: pullback, ends at P - 4.6
   m.attachAt = sc.bars();
   sc.to(30, P - 7.6);                  // H7: runs the swing low at P - 6.9 ...
   sc.to(30, P - 5.6);                  //     ... and closes back above it
   sc.to(60, P + 2.0);                  // H8: displacement, closes above the swing high at P + 0.58
   m.entryAt = sc.bars();               // first M5 bar of H9 sees the complete chain
   if(followThrough) { sc.to(60, P + 8.0); sc.to(120, P + 14.0); }
   else              { sc.to(60, P - 6.0); sc.to(120, P - 12.0); }
   sc.to(600, sc.cur);
   m.endAt = sc.bars();
   return m;
}

// Displacement + BOS with NO liquidity sweep.
static Marks patternBosOnly(Scn &sc)
{
   Marks m;
   uptrend(sc, 180);
   double P = sc.cur;
   m.peak = P;
   sc.leg(6, -4.0);                     // ordinary pullback, well above the swing low
   m.attachAt = sc.bars();
   sc.to(60, P - 4.4);
   sc.to(60, P + 2.0);                  // displacement, closes above the swing high
   m.entryAt = sc.bars();
   sc.to(60, P + 8.0);
   sc.to(600, sc.cur);
   m.endAt = sc.bars();
   return m;
}

// A liquidity sweep and nothing else: no displacement, no fresh structure.
static Marks patternSweepOnly(Scn &sc)
{
   Marks m;
   uptrend(sc, 180);
   double P = sc.cur;
   m.peak = P;
   sc.leg(6, -4.6);
   m.attachAt = sc.bars();
   sc.to(30, P - 7.6);                  // the sweep bar
   sc.to(30, P - 5.6);
   m.entryAt = sc.bars();
   for(int i = 0; i < 6; i++) sc.bar(0.15);   // drifts sideways: no impulse, no break
   m.endAt = sc.bars();
   return m;
}

// Reversal AGAINST the higher timeframes: in a rising market, a failed breakout
// above the last swing high (BSL sweep), then an impulsive bar that closes below
// the last swing low (displacement + bearish CHoCH).
static Marks patternCounterTrend(Scn &sc)
{
   Marks m;
   uptrend(sc, 180);
   double P = sc.cur;
   m.peak = P;
   sc.leg(3, -4.0);                     // pullback to P - 4 (its low becomes the last swing low)
   sc.leg(4, 3.6);                      // retest, stops short of the high
   m.attachAt = sc.bars();
   sc.to(30, P + 2.2);                  // runs the swing high at P + 1.0 ...
   sc.to(30, P - 1.0);                  // ... and closes back below it
   sc.to(60, P - 8.0);                  // displacement, closes below the swing low at P - 4.7
   m.entryAt = sc.bars();
   sc.to(60, P - 14.0);
   sc.to(120, P - 20.0);
   sc.to(600, sc.cur);
   m.endAt = sc.bars();
   return m;
}

// Every scenario that predates v1.21 reproduces the MARKET entry path: it pins
// InpUseLimitEntry=false explicitly, so it measures exactly the code it was
// written for. The limit entry has its own scenarios (limit_*), which set it back
// to true. A scenario that names the switch itself is not overridden.
static void setInputs(const std::vector<std::pair<std::string, std::string>> &sets)
{
   QATS_SetInput("InpHeartbeatSeconds", "0");
   bool limitNamed = false;
   for(const auto &kv : sets)
      if(kv.first == "InpUseLimitEntry") limitNamed = true;
   if(!limitNamed) QATS_SetInput("InpUseLimitEntry", "false");
   for(const auto &kv : sets)
      if(!QATS_SetInput(kv.first, kv.second)) { printf("unknown input %s\n", kv.first.c_str()); exit(2); }
}

static long entryCount()
{
   long n = 0;
   for(const auto &kv : sim::S.sendStats)
      if(kv.first.compare(0, 6, "entry:") == 0) n += kv.second;
   return n;
}
static long entryOkCount()
{
   auto it = sim::S.sendStats.find("entry:10009");
   return it == sim::S.sendStats.end() ? 0 : it->second;
}
static const sim::Deal *firstEntryDeal()
{
   for(const sim::Deal &d : sim::S.deals)
      if(d.entry == DEAL_ENTRY_IN) return &d;
   return nullptr;
}


// ------------------------------------------------------------ reproductions
// Version-independent observations: no assertion, only facts printed for a human
// (and for the audit report) to compare v1.11 with v1.20 on the same market.

// A transient broker failure on a symbol that is not XAUUSD (the retry path).
static int reproRetry()
{
   resetSimOnly();
   sim::S.sym.name = "TESTIDX"; _Symbol = "TESTIDX";
   captureJournal();
   setInputs({});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.play(sc, m.attachAt);
   pl.attach(sc);
   pl.play(sc, m.entryAt);
   sim::S.injectRetcodes = {TRADE_RETCODE_REQUOTE};      // ONE requote, then the server is healthy
   pl.play(sc, m.entryAt + 120);
   printf("REPRO retry version=%s symbol=TESTIDX requotes_injected=1 entry_orders_sent=%ld entry_orders_accepted=%ld "
          "bars_blocked_by_retry_pending=%d retry_lines=%d positions_opened=%zu\n",
          std::string(QATS_VERSION).c_str(), entryCount(), entryOkCount(), linesWith("order retry pending"), linesWith("[QATS][RETRY]"),
          buildTrades().size());
   return 0;
}

// A restart with a position of this EA open, then an opposite signal.
static int reproRestart()
{
   resetSimOnly();
   captureJournal();
   setInputs({});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.play(sc, m.entryAt);
   MqlTradeRequest rq{};
   MqlTradeResult rs{};
   rq.action = TRADE_ACTION_DEAL; rq.symbol = sim::S.sym.name; rq.magic = (ulong)InpMagic; rq.volume = 0.01;
   rq.type = ORDER_TYPE_SELL; rq.type_filling = ORDER_FILLING_IOC;
   sim::serverSend(rq, rs);
   pl.attach(sc);
   pl.play(sc, m.entryAt + 5);
   long closeMagic = -1;
   for(const sim::Deal &d : sim::S.deals)
      if(d.entry == DEAL_ENTRY_OUT) { closeMagic = d.magic; break; }
   printf("REPRO restart version=%s closed_on_opposite=%d closing_deal_magic=%ld ea_magic=%ld deal_lines_for_the_close=%d\n",
          std::string(QATS_VERSION).c_str(), linesWith("closed on OPPOSITE signal"), closeMagic, (long)InpMagic,
          linesWith("[QATS][DEAL]", "entry=1"));
   return 0;
}

static int cmdRepro(int argc, char **argv)
{
   std::string which = argc > 2 ? argv[2] : "";
   int rc = -1;
   if(which == "retry") rc = reproRetry();
   if(which == "restart") rc = reproRestart();
   if(rc >= 0)
   {
      if(argc > 4 && std::string(argv[3]) == "--dump") dumpJournal(argv[4]);
      return rc;
   }
   fprintf(stderr, "usage: repro retry|restart\n");
   return 2;
}
} // namespace drv
