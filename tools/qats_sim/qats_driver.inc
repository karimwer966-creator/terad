// qats_driver.inc - command-line driver for the natively built QATS EA.
//
// Included AFTER mql5_shim.h and the transpiled EA text (see tools/qats_native.py).
// Everything here is harness code: it feeds quotes, runs the EA's own event
// handlers, and measures what the EA did from the simulator's deal history (the
// ground truth) and from the EA's own journal lines. It contains no trading logic.
//
// Modes:
//   backtest   replay M1 bid/ask CSV history (Dukascopy layout) tick by tick
//   selftest   deterministic unit + integration scenarios (dual-direction build only)
//   repro      version-independent reproductions (the same market through v1.11 and v1.20)
//   inputs     list the EA inputs the build exposes
#pragma GCC system_header

#include <fstream>
#include <iostream>
#include <set>
#include <sstream>

namespace drv
{
// ------------------------------------------------------------------ helpers
struct Tick { datetime t; long bidPts; long askPts; long vol; bool gap; };

// Price grid. grid=100 -> 2-digit quotes (point 0.01), the operator's broker.
// intGrid=true keeps prices as whole numbers of points (digits 0, point 1.0): every
// price difference is then exact in a double, which is what makes the mirrored
// replay an exact symmetry proof instead of a floating-point lottery.
struct FeedCfg
{
   int    grid = 100;
   bool   intGrid = false;
   bool   mirror = false;
   long   mirrorK = 1000000;        // in points
   int    spreadMode = 1;           // 0 real, 1 scaled, 2 fixed
   double spreadScale = 0.5;
   long   spreadFixedPts = 30;
   long   minSpreadPts = 1;
};

static bool usDst(datetime utc)
{
   // US daylight time: second Sunday of March 07:00 UTC -> first Sunday of November 06:00 UTC
   int y, m, d;
   long days = utc / 86400;
   sim::civilFromDays(days, y, m, d);
   datetime mar1 = sim::makeTime(y, 3, 1);
   int dow = sim::dayOfWeek(mar1);
   datetime start = mar1 + (datetime)(((7 - dow) % 7) + 7) * 86400 + 7 * 3600;
   datetime nov1 = sim::makeTime(y, 11, 1);
   dow = sim::dayOfWeek(nov1);
   datetime end = nov1 + (datetime)((7 - dow) % 7) * 86400 + 6 * 3600;
   return utc >= start && utc < end;
}
// "New York close" broker clock (UTC+2 in winter, UTC+3 during US daylight time):
// five D1 candles a week, the daily break at 00:00, the operator's broker convention.
static datetime toServer(datetime utc) { return utc + (usDst(utc) ? 3 : 2) * 3600; }

static datetime parseDate(const std::string &s)
{
   int y = 0, m = 1, d = 1, h = 0, mi = 0;
   if(sscanf(s.c_str(), "%d-%d-%d %d:%d", &y, &m, &d, &h, &mi) < 3) sscanf(s.c_str(), "%d.%d.%d %d:%d", &y, &m, &d, &h, &mi);
   return sim::makeTime(y, m, d, h, mi, 0);
}

static inline double fastAtof(const char *&p)
{
   double v = 0.0;
   bool neg = false;
   if(*p == '-') { neg = true; p++; }
   while(*p >= '0' && *p <= '9') { v = v * 10.0 + (*p - '0'); p++; }
   if(*p == '.')
   {
      p++;
      double f = 0.1;
      while(*p >= '0' && *p <= '9') { v += (*p - '0') * f; f *= 0.1; p++; }
   }
   if(*p == 'e' || *p == 'E') { v = atof(p - 1); while(*p && *p != ',' && *p != '\n') p++; }
   return neg ? -v : v;
}

struct M1 { datetime utc; double ob, hb, lb, cb, oa, ha, la, ca; double vol; };

static bool parseM1(const char *line, M1 &r)
{
   int y, mo, d, h, mi, s;
   if(sscanf(line, "%d-%d-%d %d:%d:%d", &y, &mo, &d, &h, &mi, &s) != 6) return false;
   const char *p = strchr(line, ',');
   if(!p) return false;
   p++;
   double v[10];
   for(int i = 0; i < 10; i++)
   {
      v[i] = fastAtof(p);
      if(*p == ',') p++;
   }
   r.utc = sim::makeTime(y, mo, d, h, mi, s);
   r.ob = v[0]; r.hb = v[1]; r.lb = v[2]; r.cb = v[3];
   r.oa = v[4]; r.ha = v[5]; r.la = v[6]; r.ca = v[7];
   r.vol = v[8] + v[9];
   return true;
}

// One M1 bar -> up to four quotes: open, then the extreme the bar most plausibly
// visited first, the other extreme, then the close (the "1 minute OHLC" model).
static int ticksFromM1(const M1 &r, const FeedCfg &cfg, datetime serverTime, Tick out[4])
{
   double g = (double)cfg.grid;
   long b[4], sp[4];
   bool up = r.cb >= r.ob;
   double bid[4] = {r.ob, up ? r.lb : r.hb, up ? r.hb : r.lb, r.cb};
   double ask[4] = {r.oa, up ? r.la : r.ha, up ? r.ha : r.la, r.ca};
   for(int i = 0; i < 4; i++)
   {
      b[i] = std::llround(bid[i] * g);
      long realSp = std::llround((ask[i] - bid[i]) * g);
      if(cfg.spreadMode == 0) sp[i] = realSp;
      else if(cfg.spreadMode == 1) sp[i] = std::llround((double)realSp * cfg.spreadScale);
      else sp[i] = cfg.spreadFixedPts;
      if(sp[i] < cfg.minSpreadPts) sp[i] = cfg.minSpreadPts;
   }
   long v = std::max(1L, (long)std::llround(r.vol * 1000.0));
   int n = (b[0] == b[1] && b[1] == b[2] && b[2] == b[3]) ? 1 : 4;
   for(int i = 0; i < n; i++)
   {
      long bp = b[i], ap = b[i] + sp[i];
      if(cfg.mirror) { long nb = cfg.mirrorK - ap; long na = cfg.mirrorK - bp; bp = nb; ap = na; }
      out[i].t = serverTime + i * 15;
      out[i].bidPts = bp;
      out[i].askPts = ap;
      out[i].vol = (n == 1) ? v : (i == 0 ? v - 3 * (v / 4) : v / 4);
      out[i].gap = (i == 0);
   }
   return n;
}

static void applySymbolGrid(const FeedCfg &cfg)
{
   if(cfg.intGrid)
   {
      // 1 point = 1.0 price unit; money per point per lot unchanged (1.00 USD on XAUUSD 2-digit)
      sim::S.sym.digits = 0;
      sim::S.sym.point = 1.0;
      sim::S.sym.tickSize = 1.0;
      sim::S.sym.tickValue = 1.0;
      sim::S.sym.contractSize = 1.0;
   }
   _Symbol = sim::S.sym.name;
   _Point = sim::S.sym.point;
   _Digits = sim::S.sym.digits;
}
static inline double ptsToPrice(long pts, const FeedCfg &cfg)
{
   return cfg.intGrid ? (double)pts : (double)pts / (double)cfg.grid;
}

// ------------------------------------------------------- journal accounting
struct Journal
{
   std::map<std::string, long> c;
   long lines = 0;
   std::vector<std::string> keep;          // optional capture for tests
   std::vector<std::string> executed;      // the scored record of every bar that ended in a fill
   bool capture = false;
   size_t captureMax = 200000;

   static std::string field(const std::string &s, const std::string &key)
   {
      size_t p = s.find(key);
      if(p == std::string::npos) return "";
      p += key.size();
      size_t e = p;
      while(e < s.size() && s[e] != ' ' && s[e] != '|') e++;
      return s.substr(p, e - p);
   }
   static std::string reasonHead(const std::string &s)
   {
      // "reason=<text> | trace" -> a stable bucket name
      size_t p = s.find("reason=");
      if(p == std::string::npos) return "";
      p += 7;
      size_t e = s.find(" | ", p);
      std::string r = s.substr(p, e == std::string::npos ? std::string::npos : e - p);
      // collapse numbers so "score 35 below minimum 55" and "score 40 ..." share a bucket
      std::string o;
      bool lastHash = false;
      for(char ch : r)
      {
         if((ch >= '0' && ch <= '9') || ch == '.') { if(!lastHash) o += '#'; lastHash = true; }
         else { o += ch; lastHash = false; }
      }
      if(o.size() > 90) o = o.substr(0, 90);
      return o;
   }
   void on(const std::string &s)
   {
      lines++;
      if(capture && keep.size() < captureMax) keep.push_back(s);
      if(s.compare(0, 6, "[QATS]") != 0) { c["other"]++; return; }
      if(s.compare(0, 22, "[QATS][SIGNAL][SCORED]") == 0)
      {
         c["bars"]++;
         std::string cand = field(s, "candidate=");
         std::string outcome = field(s, "outcome=");
         std::string elig = field(s, "eligible=");
         c["cand." + cand]++;
         if(elig == "yes") c["eligible." + cand]++;
         c["outcome." + cand + "." + outcome]++;
         if(outcome == "EXECUTED") executed.push_back(s);
         if(outcome == "BLOCKED" || outcome == "REJECTED" || outcome == "VETOED" || outcome == "CONFLICT")
            c["why." + cand + "." + outcome + "." + field(s, "reason=")]++;
         // both sides are scored on every bar: count how often each side clears the bar
         int bs = atoi(field(s, "BUY=").c_str());
         int ss = atoi(field(s, "SELL=").c_str());
         int mn = atoi(field(s, "minimum=").c_str());
         c["scored.BUY.sum"] += bs;
         c["scored.SELL.sum"] += ss;
         if(bs >= mn) c["scored.BUY.ge_min"]++;
         if(ss >= mn) c["scored.SELL.ge_min"]++;
         if(s.find("BUY core=PASS") != std::string::npos) c["core.BUY.pass"]++;
         if(s.find("SELL core=PASS") != std::string::npos) c["core.SELL.pass"]++;
         return;
      }
      if(s.compare(0, 14, "[QATS][SIGNAL]") == 0)
      {
         // v1.11 single-direction record
         c["bars"]++;
         std::string dir = field(s, "direction=");
         std::string res = field(s, "result=");
         std::string elig = field(s, "eligible=");
         c["cand." + dir]++;
         if(elig == "yes") c["eligible." + dir]++;
         c["outcome." + dir + "." + res]++;
         if(elig == "yes" && res != "ACCEPTED") c["why." + dir + "." + res + "." + reasonHead(s)]++;
         c["xtab.cand=" + dir + ".D1=" + field(s, " D1=") + ".sweep=" + field(s, "sweep=")]++;
         return;
      }
      static const char *tags[] = {"[QATS][BUY][DETECTED]", "[QATS][SELL][DETECTED]", "[QATS][EXECUTION][APPROVED]",
                                   "[QATS][EXECUTION][REJECTED]", "[QATS][EXECUTION][FILLED]", "[QATS][BLOCK][REASON]",
                                   "[QATS][SIGNAL][CONFLICT]", "[QATS][COOLDOWN]", "[QATS][GUARD]", "[QATS][EXEC][FAIL]",
                                   "[QATS][VERIFY][CRITICAL]", "[QATS][PROTECT]", "[QATS][MANAGE]", "[QATS][RETRY]"};
      for(const char *t : tags)
      {
         size_t n = strlen(t);
         if(s.compare(0, n, t) == 0)
         {
            c[std::string("tag.") + t]++;
            std::string dir = field(s, "direction=");
            if(!dir.empty()) c[std::string("tag.") + t + "." + dir]++;
            if(strcmp(t, "[QATS][BLOCK][REASON]") == 0)
            {
               std::string rs = field(s, "reasons=");
               size_t a = 0;
               while(a <= rs.size() && !rs.empty())
               {
                  size_t b = rs.find(',', a);
                  std::string one = rs.substr(a, b == std::string::npos ? std::string::npos : b - a);
                  if(!one.empty()) c["block." + dir + "." + one]++;
                  if(b == std::string::npos) break;
                  a = b + 1;
               }
            }
            if(strcmp(t, "[QATS][EXECUTION][REJECTED]") == 0)
               c["reject." + dir + "." + field(s, "stage=")]++;
            return;
         }
      }
   }
};

// ------------------------------------------------------------ trade ledger
struct Trade
{
   long id; int dir; datetime openTime, closeTime; double openPrice, closePrice, volume;
   double sl, tp; double net; double risk; int exitReason; bool closed; double plannedRR;
};

struct DirStats
{
   long trades = 0, wins = 0, losses = 0, flat = 0;
   double grossProfit = 0.0, grossLoss = 0.0, net = 0.0, sumR = 0.0, sumPlannedRR = 0.0;
   long exitSL = 0, exitTP = 0, exitOther = 0;
   double sumWinR = 0.0, sumLossR = 0.0;
   void add(const Trade &t)
   {
      trades++;
      net += t.net;
      double r = t.risk > 0.0 ? t.net / t.risk : 0.0;
      sumR += r;
      sumPlannedRR += t.plannedRR;
      if(t.net > 1e-9) { wins++; grossProfit += t.net; sumWinR += r; }
      else if(t.net < -1e-9) { losses++; grossLoss += -t.net; sumLossR += r; }
      else flat++;
      if(t.exitReason == DEAL_REASON_SL) exitSL++;
      else if(t.exitReason == DEAL_REASON_TP) exitTP++;
      else exitOther++;
   }
   std::string json() const
   {
      char buf[1024];
      double pf = grossLoss > 0.0 ? grossProfit / grossLoss : (grossProfit > 0.0 ? 9999.0 : 0.0);
      snprintf(buf, sizeof buf,
               "{\"trades\":%ld,\"wins\":%ld,\"losses\":%ld,\"flat\":%ld,\"win_rate\":%.4f,\"gross_profit\":%.2f,"
               "\"gross_loss\":%.2f,\"profit_factor\":%.4f,\"net\":%.2f,\"expectancy_money\":%.4f,\"expectancy_R\":%.4f,"
               "\"avg_planned_rr\":%.4f,\"avg_win_R\":%.4f,\"avg_loss_R\":%.4f,\"exit_sl\":%ld,\"exit_tp\":%ld,\"exit_other\":%ld}",
               trades, wins, losses, flat, trades ? (double)wins / (double)trades : 0.0, grossProfit, grossLoss, pf, net,
               trades ? net / (double)trades : 0.0, trades ? sumR / (double)trades : 0.0,
               trades ? sumPlannedRR / (double)trades : 0.0, wins ? sumWinR / (double)wins : 0.0,
               losses ? sumLossR / (double)losses : 0.0, exitSL, exitTP, exitOther);
      return buf;
   }
};

static std::vector<Trade> buildTrades()
{
   std::vector<Trade> trades;
   std::map<long, size_t> idx;
   for(const sim::Deal &d : sim::S.deals)
   {
      if(d.entry == DEAL_ENTRY_IN)
      {
         Trade t{};
         t.id = d.positionId;
         t.dir = (d.type == DEAL_TYPE_BUY) ? +1 : -1;
         t.openTime = d.time;
         t.openPrice = d.price;
         t.volume = d.volume;
         t.sl = d.sl;
         t.tp = d.tp;
         t.net = d.commission;
         t.risk = (d.sl > 0.0) ? std::fabs(d.price - d.sl) * sim::moneyPerPriceUnit(d.volume) : 0.0;
         t.plannedRR = (d.sl > 0.0 && d.tp > 0.0 && std::fabs(d.price - d.sl) > 0.0) ? std::fabs(d.tp - d.price) / std::fabs(d.price - d.sl) : 0.0;
         t.closed = false;
         idx[d.positionId] = trades.size();
         trades.push_back(t);
      }
      else
      {
         auto it = idx.find(d.positionId);
         if(it == idx.end()) continue;
         Trade &t = trades[it->second];
         t.net += d.profit + d.commission + d.swap;
         t.closeTime = d.time;
         t.closePrice = d.price;
         t.exitReason = d.reason;
         bool open = false;
         for(const sim::Position &p : sim::S.positions) if((long)p.ticket == d.positionId) open = true;
         t.closed = !open;
      }
   }
   return trades;
}

// ---------------------------------------------------------------- backtest
struct RunCfg
{
   std::string dataDir;
   std::vector<std::string> files;
   datetime from = 0, to = 0;
   int warmupDays = 150;
   FeedCfg feed;
   double balance = 10000.0;
   double commission = 0.0;
   double stopSlipPts = 5.0;
   std::vector<std::pair<std::string, std::string>> sets;
   std::string jsonPath, logPath, tradesPath, barsPath;
   datetime logFrom = 0, logTo = 0;
   bool quiet = false;
   std::string label;
};

struct RunResult
{
   Journal journal;
   std::vector<Trade> trades;
   double startBalance = 0.0, endBalance = 0.0, endEquity = 0.0;
   double maxDDMoney = 0.0, maxDDPct = 0.0, peakEquity = 0.0;
   long ticks = 0, m1bars = 0, m1repeated = 0;
   datetime firstTick = 0, lastTick = 0, attachTime = 0;
   int initCode = -1;
   long sendCount = 0, sendOk = 0;
   std::map<std::string, long> sendStats;
   std::vector<std::string> fmtErrors, apiErrors;
   std::string critical;
   std::map<int, double> yearNet;
   std::map<int, long> yearTrades;
};

static std::vector<std::string> listCsv(const std::string &dir)
{
   std::vector<std::string> files;
   std::string cmd = "ls -1 \"" + dir + "\"/*.csv 2>/dev/null";
   FILE *p = popen(cmd.c_str(), "r");
   if(!p) return files;
   char buf[4096];
   while(fgets(buf, sizeof buf, p))
   {
      std::string s(buf);
      while(!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
      if(!s.empty()) files.push_back(s);
   }
   pclose(p);
   std::sort(files.begin(), files.end());
   return files;
}

static void configureSim(const RunCfg &cfg)
{
   sim::reset();
   sim::selectedPosition = -1;
   sim::S.acc.balance = cfg.balance;
   sim::S.commissionPerLot = cfg.commission;
   applySymbolGrid(cfg.feed);
   sim::S.stopSlippage = cfg.stopSlipPts * sim::S.sym.point;
}

static RunResult runBacktest(const RunCfg &cfg)
{
   RunResult res;
   configureSim(cfg);
   for(const auto &kv : cfg.sets)
      if(!QATS_SetInput(kv.first, kv.second))
      {
         fprintf(stderr, "unknown input: %s\n", kv.first.c_str());
         exit(2);
      }
   res.startBalance = cfg.balance;
   res.peakEquity = cfg.balance;
   FILE *logf = nullptr;
   if(!cfg.logPath.empty()) logf = fopen(cfg.logPath.c_str(), "w");
   sim::S.onPrint = [&](const std::string &s) { res.journal.on(s); };

   bool attached = false;
   datetime attachAt = cfg.from;
   datetime warmFrom = cfg.from - (datetime)cfg.warmupDays * 86400;
   std::vector<std::string> files = cfg.files.empty() ? listCsv(cfg.dataDir) : cfg.files;
   if(files.empty()) { fprintf(stderr, "no CSV files found in %s\n", cfg.dataDir.c_str()); exit(2); }
   Tick tk[4];
   M1 r{};
   bool stop = false;
   datetime lastSt = 0;
   try
   {
      for(const std::string &fn : files)
      {
         if(stop) break;
         std::ifstream in(fn);
         if(!in) { fprintf(stderr, "cannot open %s\n", fn.c_str()); exit(2); }
         std::string line;
         std::getline(in, line);            // header
         while(std::getline(in, line))
         {
            if(!parseM1(line.c_str(), r)) continue;
            datetime st = toServer(r.utc);
            // The yearly files of the public dataset OVERLAP at their seams (up to
            // 23 hours of the same minutes appear in two files). A row that does
            // not move time forward is a repeat and is skipped: fed again it would
            // send the simulated clock backwards and replay a day of quotes.
            if(st <= lastSt) { res.m1repeated++; continue; }
            lastSt = st;
            if(st < warmFrom) continue;
            if(cfg.to > 0 && st >= cfg.to) { stop = true; break; }
            res.m1bars++;
            if(!attached && st >= attachAt)
            {
               // the expert is attached to a chart that already has history
               sim::S.now = st;
               sim::S.lastTickTime = st;
               res.attachTime = st;
               sim::S.logFile = (logf && (cfg.logFrom == 0 || st >= cfg.logFrom)) ? logf : nullptr;
               res.initCode = OnInit();
               attached = true;
               if(res.initCode != INIT_SUCCEEDED) { stop = true; break; }
            }
            int n = ticksFromM1(r, cfg.feed, st, tk);
            for(int i = 0; i < n; i++)
            {
               bool logOn = logf && (cfg.logFrom == 0 || tk[i].t >= cfg.logFrom) && (cfg.logTo == 0 || tk[i].t < cfg.logTo);
               sim::S.logFile = (attached && logOn) ? logf : nullptr;
               sim::feedTick(tk[i].t, ptsToPrice(tk[i].bidPts, cfg.feed), ptsToPrice(tk[i].askPts, cfg.feed), tk[i].vol, tk[i].gap, attached);
               if(attached)
               {
                  res.ticks++;
                  if(res.firstTick == 0) res.firstTick = tk[i].t;
                  res.lastTick = tk[i].t;
                  double eq = sim::equity();
                  if(eq > res.peakEquity) res.peakEquity = eq;
                  double dd = res.peakEquity - eq;
                  if(dd > res.maxDDMoney) res.maxDDMoney = dd;
                  double ddp = res.peakEquity > 0.0 ? dd / res.peakEquity * 100.0 : 0.0;
                  if(ddp > res.maxDDPct) res.maxDDPct = ddp;
               }
            }
         }
      }
      if(attached && res.initCode == INIT_SUCCEEDED)
      {
         sim::S.logFile = logf;
         OnDeinit(1);
      }
   }
   catch(const std::exception &e)
   {
      res.critical = e.what();
   }
   sim::S.logFile = nullptr;
   if(logf) fclose(logf);
   res.trades = buildTrades();
   res.endBalance = sim::S.acc.balance;
   res.endEquity = sim::equity();
   res.sendCount = sim::S.sendCount;
   res.sendOk = sim::S.sendOk;
   res.sendStats = sim::S.sendStats;
   res.fmtErrors = sim::S.fmtErrors;
   res.apiErrors = sim::S.apiErrors;
   for(const Trade &t : res.trades)
   {
      if(!t.closed) continue;
      int y, m, d;
      sim::civilFromDays(t.closeTime / 86400, y, m, d);
      res.yearNet[y] += t.net;
      res.yearTrades[y]++;
   }
   sim::S.onPrint = nullptr;
   return res;
}

static std::string jsonEscape(const std::string &s)
{
   std::string o;
   for(char ch : s)
   {
      if(ch == '"' || ch == '\\') { o += '\\'; o += ch; }
      else if(ch == '\n') o += "\\n";
      else if((unsigned char)ch < 0x20) o += ' ';
      else o += ch;
   }
   return o;
}

static std::string resultJson(const RunCfg &cfg, const RunResult &res)
{
   DirStats all, buy, sell;
   long openTrades = 0;
   for(const Trade &t : res.trades)
   {
      if(!t.closed) { openTrades++; continue; }
      all.add(t);
      (t.dir > 0 ? buy : sell).add(t);
   }
   std::ostringstream o;
   o.setf(std::ios::fixed);
   o.precision(2);
   o << "{\n";
   o << "  \"label\": \"" << jsonEscape(cfg.label) << "\",\n";
   o << "  \"ea_version\": \"" << QATS_VERSION << "\",\n";
   o << "  \"period_server_time\": {\"attach\": \"" << sim::timeString(res.attachTime, TIME_DATE | TIME_MINUTES)
     << "\", \"first_tick\": \"" << sim::timeString(res.firstTick, TIME_DATE | TIME_MINUTES)
     << "\", \"last_tick\": \"" << sim::timeString(res.lastTick, TIME_DATE | TIME_MINUTES) << "\"},\n";
   o << "  \"init_code\": " << res.initCode << ",\n";
   o << "  \"m1_bars\": " << res.m1bars << ", \"m1_rows_skipped_repeated_at_a_file_seam\": " << res.m1repeated << ", \"ticks\": " << res.ticks << ",\n";
   o << "  \"feed\": {\"spread_mode\": " << cfg.feed.spreadMode << ", \"spread_scale\": " << cfg.feed.spreadScale
     << ", \"spread_fixed_pts\": " << cfg.feed.spreadFixedPts << ", \"int_grid\": " << (cfg.feed.intGrid ? "true" : "false")
     << ", \"mirror\": " << (cfg.feed.mirror ? "true" : "false") << ", \"stop_slippage_pts\": " << cfg.stopSlipPts
     << ", \"commission_per_lot_side\": " << cfg.commission << "},\n";
   o << "  \"inputs_overridden\": {";
   for(size_t i = 0; i < cfg.sets.size(); i++)
      o << (i ? ", " : "") << "\"" << jsonEscape(cfg.sets[i].first) << "\": \"" << jsonEscape(cfg.sets[i].second) << "\"";
   o << "},\n";
   o << "  \"balance_start\": " << res.startBalance << ", \"balance_end\": " << res.endBalance
     << ", \"equity_end\": " << res.endEquity << ",\n";
   o << "  \"max_drawdown_money\": " << res.maxDDMoney << ", \"max_drawdown_pct\": " << res.maxDDPct << ",\n";
   {
      // entries only: a market order that the (simulated) server did not accept
      long entrySent = 0, entryOk = 0, otherFail = 0;
      for(const auto &kv : res.sendStats)
      {
         bool ok = kv.first.find(":10009") != std::string::npos || kv.first.find(":10010") != std::string::npos;
         if(kv.first.compare(0, 6, "entry:") == 0) { entrySent += kv.second; if(ok) entryOk += kv.second; }
         else if(!ok) otherFail += kv.second;
      }
      o << "  \"entry_orders_sent\": " << entrySent << ", \"entry_orders_accepted\": " << entryOk
        << ", \"execution_failures\": " << (entrySent - entryOk) << ", \"modify_or_close_failures\": " << otherFail << ",\n";
   }
   o << "  \"send_stats\": {";
   {
      bool f2 = true;
      for(const auto &kv : res.sendStats) { o << (f2 ? "" : ", ") << "\"" << kv.first << "\": " << kv.second; f2 = false; }
   }
   o << "},\n";
   o << "  \"open_trades_at_end\": " << openTrades << ",\n";
   o << "  \"all\": " << all.json() << ",\n";
   o << "  \"buy\": " << buy.json() << ",\n";
   o << "  \"sell\": " << sell.json() << ",\n";
   o << "  \"by_year\": {";
   bool first = true;
   for(const auto &kv : res.yearNet)
   {
      o << (first ? "" : ", ") << "\"" << kv.first << "\": {\"net\": " << kv.second << ", \"trades\": " << res.yearTrades.at(kv.first) << "}";
      first = false;
   }
   o << "},\n";
   o << "  \"journal\": {";
   first = true;
   for(const auto &kv : res.journal.c)
   {
      o << (first ? "\n    " : ",\n    ") << "\"" << jsonEscape(kv.first) << "\": " << kv.second;
      first = false;
   }
   o << "\n  },\n";
   o << "  \"journal_lines\": " << res.journal.lines << ",\n";
   o << "  \"format_errors\": " << res.fmtErrors.size() << ", \"api_errors\": " << res.apiErrors.size() << ",\n";
   o << "  \"first_format_error\": \"" << jsonEscape(res.fmtErrors.empty() ? "" : res.fmtErrors[0]) << "\",\n";
   o << "  \"first_api_error\": \"" << jsonEscape(res.apiErrors.empty() ? "" : res.apiErrors[0]) << "\",\n";
   o << "  \"critical\": \"" << jsonEscape(res.critical) << "\"\n";
   o << "}\n";
   return o.str();
}

static void writeTrades(const std::string &path, const RunResult &res)
{
   FILE *f = fopen(path.c_str(), "w");
   if(!f) return;
   fprintf(f, "position,direction,open_time,open_price,volume,sl,tp,planned_rr,close_time,close_price,exit,net,risk,R,evidence\n");
   size_t k = 0;
   for(const Trade &t : res.trades)
   {
      const char *ex = t.exitReason == DEAL_REASON_SL ? "SL" : (t.exitReason == DEAL_REASON_TP ? "TP" : "EXPERT");
      // the k-th fill belongs to the k-th scored record that ended in EXECUTED (dual-direction builds)
      std::string ev = (k < res.journal.executed.size()) ? res.journal.executed[k] : "";
      size_t bar = ev.find(" | ");
      if(bar != std::string::npos) ev = ev.substr(bar + 3);
      for(char &ch : ev) if(ch == ',' || ch == '"') ch = ';';
      k++;
      fprintf(f, "%ld,%s,%s,%.3f,%.2f,%.3f,%.3f,%.3f,%s,%.3f,%s,%.2f,%.2f,%.3f,%s\n", t.id, t.dir > 0 ? "BUY" : "SELL",
              sim::timeString(t.openTime, TIME_DATE | TIME_SECONDS).c_str(), t.openPrice, t.volume, t.sl, t.tp, t.plannedRR,
              t.closed ? sim::timeString(t.closeTime, TIME_DATE | TIME_SECONDS).c_str() : "", t.closePrice,
              t.closed ? ex : "OPEN", t.net, t.risk, t.risk > 0.0 ? t.net / t.risk : 0.0, ev.c_str());
   }
   fclose(f);
}

static int cmdBacktest(int argc, char **argv)
{
   RunCfg cfg;
   cfg.sets.push_back({"InpHeartbeatSeconds", "0"});
   for(int i = 2; i < argc; i++)
   {
      std::string a = argv[i];
      auto next = [&]() -> std::string { if(i + 1 >= argc) { fprintf(stderr, "missing value for %s\n", a.c_str()); exit(2); } return argv[++i]; };
      if(a == "--data") cfg.dataDir = next();
      else if(a == "--file") cfg.files.push_back(next());
      else if(a == "--from") cfg.from = parseDate(next());
      else if(a == "--to") cfg.to = parseDate(next());
      else if(a == "--warmup-days") cfg.warmupDays = atoi(next().c_str());
      else if(a == "--balance") cfg.balance = atof(next().c_str());
      else if(a == "--commission") cfg.commission = atof(next().c_str());
      else if(a == "--stop-slip") cfg.stopSlipPts = atof(next().c_str());
      else if(a == "--json") cfg.jsonPath = next();
      else if(a == "--log") cfg.logPath = next();
      else if(a == "--log-from") cfg.logFrom = parseDate(next());
      else if(a == "--log-to") cfg.logTo = parseDate(next());
      else if(a == "--trades") cfg.tradesPath = next();
      else if(a == "--label") cfg.label = next();
      else if(a == "--quiet") cfg.quiet = true;
      else if(a == "--int-grid") cfg.feed.intGrid = true;
      else if(a == "--mirror") cfg.feed.mirror = true;
      else if(a == "--spread")
      {
         std::string v = next();
         if(v == "real") cfg.feed.spreadMode = 0;
         else if(v.compare(0, 7, "scaled:") == 0) { cfg.feed.spreadMode = 1; cfg.feed.spreadScale = atof(v.c_str() + 7); }
         else if(v.compare(0, 6, "fixed:") == 0) { cfg.feed.spreadMode = 2; cfg.feed.spreadFixedPts = atol(v.c_str() + 6); }
         else { fprintf(stderr, "bad --spread %s\n", v.c_str()); return 2; }
      }
      else if(a == "--set")
      {
         std::string v = next();
         size_t eq = v.find('=');
         if(eq == std::string::npos) { fprintf(stderr, "bad --set %s\n", v.c_str()); return 2; }
         cfg.sets.push_back({v.substr(0, eq), v.substr(eq + 1)});
      }
      else { fprintf(stderr, "unknown argument %s\n", a.c_str()); return 2; }
   }
   if(cfg.from == 0) { fprintf(stderr, "--from is required\n"); return 2; }
   RunResult res = runBacktest(cfg);
   std::string js = resultJson(cfg, res);
   if(!cfg.jsonPath.empty()) { std::ofstream o(cfg.jsonPath); o << js; }
   if(!cfg.tradesPath.empty()) writeTrades(cfg.tradesPath, res);
   if(!cfg.quiet) std::cout << js;
   if(!res.critical.empty()) { fprintf(stderr, "CRITICAL: %s\n", res.critical.c_str()); return 3; }
   return 0;
}
} // namespace drv

#include "qats_market.inc"
#ifdef QATS_HAS_DUAL
#include "qats_selftest.inc"
#endif

int main(int argc, char **argv)
{
   std::string mode = argc > 1 ? argv[1] : "";
   if(mode == "backtest") return drv::cmdBacktest(argc, argv);
   if(mode == "inputs")
   {
      for(int i = 0; i < QATS_INPUT_COUNT; i++) printf("%s\n", QATS_INPUT_NAMES[i]);
      return 0;
   }
   if(mode == "repro") return drv::cmdRepro(argc, argv);
#ifdef QATS_HAS_DUAL
   if(mode == "selftest") return drv::cmdSelftest(argc, argv);
#endif
   fprintf(stderr, "usage: %s backtest|selftest|repro|inputs ...\n", argv[0]);
   return 2;
}
