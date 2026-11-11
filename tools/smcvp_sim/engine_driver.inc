// engine_driver.inc - executes the QSMC SMC + Volume Profile engine
// (MQL5/Indicators/QSMC_SmcVpEngine.mq5 and the QSMC_Svp* modules, transpiled
// from the real text) against synthetic candles, a chart-object simulator and
// real M1 history. Included after the unit by tools/test_qsmc_smcvp.py.
//
//   unit [group]                         engine unit checks
//   story [--mirror] [--branch win|loss] decision timeline of the synthetic story
//   host <scenario>                      the real OnInit / OnCalculate / OnDeinit
//   replay --data DIR --from D --to D    the host on real history
//
// NOT MetaTrader. Evidence about logic, never about a MetaEditor build.
#include <cstdio>
#include <cstring>
#include <cmath>
#include <fstream>
#include <sstream>
#include <array>
#include <deque>
#include <chrono>

namespace drv
{
static int g_pass = 0, g_fail = 0;
static std::string g_group;

static void check(const bool ok, const std::string &label, const std::string &detail = "")
{
   if(ok) g_pass++; else g_fail++;
   printf("%s  %s %s%s\n", ok ? "PASS" : "FAIL", g_group.c_str(), label.c_str(),
          (ok || detail.empty()) ? "" : ("  [" + detail + "]").c_str());
}
static std::string num(const double v, const int digits = 2)
{
   char b[64]; snprintf(b, sizeof b, "%.*f", digits, v); return b;
}
static bool near(const double a, const double b, const double eps = 1e-6) { return std::fabs(a - b) <= eps; }

// ------------------------------------------------------------------ candles
static const datetime T0 = 1767571200;      // 2026-01-05 00:00:00, a Monday

struct Gen
{
   std::vector<MqlRates> b;
   datetime t;
   double px;
   long vol = 1000;
   Gen(const datetime start, const double price) : t(start), px(price) {}
   void bar(const double o, const double h, const double l, const double c, const long v = -1)
   {
      MqlRates r{};
      r.time = t; r.open = o; r.high = h; r.low = l; r.close = c;
      r.tick_volume = (v < 0 ? vol : v); r.spread = 0; r.real_volume = 0;
      b.push_back(r);
      t += 900; px = c;
   }
   // one candle that travels d from the previous close, wicks of w on both ends
   void step(const double d, const double w = 0.2, const long v = -1)
   {
      const double o = px, c = px + d;
      bar(o, std::max(o, c) + w, std::min(o, c) - w, c, v);
   }
   void run(const int n, const double d, const double w = 0.2, const long v = -1) { for(int i = 0; i < n; i++) step(d, w, v); }
   // `cycles` x (a candles of da, then k candles of dk)
   void zig(const int cycles, const int a, const double da, const int k, const double dk, const double w = 0.2)
   {
      for(int c = 0; c < cycles; c++) { run(a, da, w); run(k, dk, w); }
   }
   int size() const { return (int)b.size(); }
};

static void toArray(const std::vector<MqlRates> &src, MqlArray<MqlRates> &out) { out.v = src; out.series = false; }

static void aggregate(const std::vector<MqlRates> &src, const long seconds, MqlArray<MqlRates> &out)
{
   out.v.clear(); out.series = false;
   for(const MqlRates &r : src)
   {
      const datetime bt = r.time - r.time % seconds;
      if(out.v.empty() || out.v.back().time != bt)
      {
         MqlRates a = r; a.time = bt; out.v.push_back(a);
      }
      else
      {
         MqlRates &a = out.v.back();
         a.high = std::max(a.high, r.high); a.low = std::min(a.low, r.low); a.close = r.close;
         a.tick_volume += r.tick_volume; a.real_volume += r.real_volume;
      }
   }
}

struct Tf
{
   MqlArray<MqlRates> m15, h1, h4;
   void build(const std::vector<MqlRates> &b) { toArray(b, m15); aggregate(b, 3600, h1); aggregate(b, 14400, h4); }
   int n15() const { return (int)m15.v.size(); }
};

// price mirror around c: a rally becomes a sell-off of the same shape
static std::vector<MqlRates> mirrored(const std::vector<MqlRates> &src, const double c)
{
   std::vector<MqlRates> out = src;
   for(MqlRates &r : out)
   {
      const double o = c - r.open, h = c - r.low, l = c - r.high, cl = c - r.close;
      r.open = o; r.high = h; r.low = l; r.close = cl;
   }
   return out;
}

// the same candles on another price scale / precision (e.g. a 5-digit FX symbol)
static std::vector<MqlRates> scaled(const std::vector<MqlRates> &src, const double k, const int digits)
{
   const double q = std::pow(10.0, digits);
   std::vector<MqlRates> out = src;
   for(MqlRates &r : out)
   {
      r.open = std::round(r.open * k * q) / q; r.high = std::round(r.high * k * q) / q;
      r.low = std::round(r.low * k * q) / q;   r.close = std::round(r.close * k * q) / q;
   }
   return out;
}

static bool analyze(const Tf &tf, const int n15, const SSvpParams &p)
{
   return SVP_Analyze(tf.h4, (int)tf.h4.v.size(), tf.h1, (int)tf.h1.v.size(), tf.m15, n15, p);
}

// ------------------------------------------------------------------ the story
// Four and a half bullish cycles (H4 and H1 make higher highs and higher lows),
// a pullback, then on M15: equal lows -> a sweep of them -> displacement and a
// bullish CHoCH -> an order block + fair value gap -> a retest that closes back
// out. `branch` continues with the target being reached (1) or the stop (2).
struct Story
{
   std::vector<MqlRates> bars;
   int i_low1 = -1, i_low2 = -1, i_sweep = -1, i_disp = -1, i_fvg = -1, i_touch = -1, i_confirm = -1, i_end = -1;
   double L0 = 0.0;          // close of the first equal low
};

static Story makeStory(const int branch)
{
   Story s;
   Gen g(T0, 2000.0);
   for(int c = 0; c < 4; c++)
   {
      g.zig(20, 5, 0.9, 3, -0.5);          // up leg: 160 candles, +60
      g.zig(12, 5, -0.9, 3, 0.5);          // pullback: 96 candles, -36
   }
   g.zig(20, 5, 0.9, 3, -0.5);
   g.zig(11, 5, -0.9, 3, 0.5);
   g.run(5, -0.9);                         // the last leg down of the pullback
   s.i_low1 = g.size() - 1;
   s.L0 = g.px;
   const double L0 = s.L0;
   g.vol = 3000;                           // the base where the day's volume builds
   g.run(3, 0.5);
   g.step(-0.5); g.step(-0.5); g.step(-0.45);          // second low: 0.05 above the first
   s.i_low2 = g.size() - 1;
   g.run(4, 0.5);
   g.step(-0.5); g.step(-0.45);
   // the sweep: through both lows by 1.2, closes back above them
   g.bar(g.px, L0 + 1.2, L0 - 1.4, L0 + 0.6);
   s.i_sweep = g.size() - 1;
   // displacement: body 3.0, closes above the last M15 swing high
   g.bar(L0 + 0.6, L0 + 3.7, L0 + 0.5, L0 + 3.6);
   s.i_disp = g.size() - 1;
   // third candle of the gap: its low stays above the sweep candle's high
   g.bar(L0 + 3.6, L0 + 4.5, L0 + 3.3, L0 + 4.3);
   s.i_fvg = g.size() - 1;
   g.vol = 1000;
   // retest: into the zone, first close is bearish, the next closes back out bullish
   g.bar(L0 + 4.3, L0 + 4.4, L0 + 3.0, L0 + 3.5);
   s.i_touch = g.size() - 1;
   g.bar(L0 + 3.5, L0 + 4.3, L0 + 3.1, L0 + 4.1);
   s.i_confirm = g.size() - 1;
   if(branch == 1) g.zig(8, 5, 0.9, 3, -0.5);                       // rally through the target
   if(branch == 2) { g.run(2, 0.3); g.run(8, -1.0); }               // fails: trades through the stop
   s.i_end = g.size() - 1;
   s.bars = g.b;
   return s;
}

static std::string decisionLine(const int k, const MqlRates &bar, const int digits)
{
   std::string s = std::to_string(k) + " " + sim::timeString(bar.time, TIME_DATE | TIME_MINUTES) + " " + std::string(g_svp.headline);
   s += " | buy " + std::to_string(g_svp_buy.progress) + "/10 sell " + std::to_string(g_svp_sell.progress) + "/10";
   if(g_svp.plan_valid)
      s += " | E " + num(g_svp.entry, digits) + " SL " + num(g_svp.stop, digits) + " TP " + num(g_svp.target, digits) + " RR " + num(g_svp.rr, 2);
   s += " | " + std::string(g_svp.reason);
   return s;
}

static void dumpSide(const SSvpSide &s)
{
   for(int i = 0; i < SVP_MAX_STEPS; i++)
      printf("      %-16s %-8s %s\n", std::string(SVP_StepName(i)).c_str(), std::string(SVP_StatusText(s.status[i])).c_str(),
             std::string(s.text[i]).c_str());
}

static int cmdStory(const bool mirror, const int branch, const int from_back, const bool steps)
{
   Story st = makeStory(branch);
   std::vector<MqlRates> bars = mirror ? mirrored(st.bars, 4300.0) : st.bars;
   Tf tf; tf.build(bars);
   SSvpParams p; SVP_DefaultParams(p);
   QSR_Reset(); SVP_VpCacheReset();
   printf("story: %d candles | low1 %d low2 %d sweep %d disp %d fvg %d touch %d confirm %d end %d | L0 %.2f\n",
          st.i_end + 1, st.i_low1, st.i_low2, st.i_sweep, st.i_disp, st.i_fvg, st.i_touch, st.i_confirm, st.i_end, st.L0);
   for(int k = std::max(SVP_MIN_M15_BARS, st.i_low1 - from_back); k <= st.i_end; k++)
   {
      analyze(tf, k + 1, p);
      printf("%s\n", decisionLine(k, bars[(size_t)k], p.digits).c_str());
      if(steps && (k >= st.i_sweep && k <= st.i_confirm + 1))
      {
         printf("    H4 %s | H1 %s | M15 %s\n", std::string(g_svp.h4_text).c_str(), std::string(g_svp.h1_text).c_str(),
                std::string(SVP_StructureText(g_svp_m15, p.digits)).c_str());
         printf("    liq %s | sweep %s | zone %s | vp %s POC %.2f VAH %.2f VAL %.2f\n", std::string(g_svp.liq_text).c_str(),
                std::string(g_svp.sweep_text).c_str(), std::string(g_svp.zone_text).c_str(), std::string(g_svp.vp_text).c_str(),
                g_svp.poc, g_svp.vah, g_svp.val);
         dumpSide(mirror ? g_svp_sell : g_svp_buy);
      }
   }
   return 0;
}

// ================================================================== unit: structure
static const double BOS_SERIES[24][4] = {
   {100.0, 100.5, 99.5, 100.0}, {100.0, 101.0, 99.8, 100.8}, {100.8, 102.0, 100.5, 101.5}, {101.5, 101.6, 100.2, 100.4},
   {100.4, 100.8, 99.0, 99.4},  {99.4, 100.6, 99.3, 100.5},  {100.5, 101.9, 100.3, 101.7}, {101.7, 102.6, 101.5, 101.9},
   {101.9, 103.2, 101.8, 103.0}, {103.0, 104.0, 102.8, 103.8}, {103.8, 104.5, 103.5, 104.2}, {104.2, 104.3, 103.0, 103.2},
   {103.2, 103.4, 102.2, 102.5}, {102.5, 103.6, 102.4, 103.4}, {103.4, 104.4, 103.2, 104.0}, {104.0, 104.2, 102.6, 102.8},
   {102.8, 103.0, 101.6, 101.8}, {101.8, 102.4, 101.0, 101.3}, {101.3, 101.5, 100.2, 100.5}, {100.5, 101.6, 100.4, 101.4},
   {101.4, 102.0, 101.2, 101.8}, {101.8, 102.2, 101.0, 101.2}, {101.2, 101.4, 100.3, 100.6}, {100.6, 100.8, 99.4, 99.6}};

static std::vector<MqlRates> bosSeries()
{
   Gen g(T0, 100.0);
   for(int i = 0; i < 24; i++) g.bar(BOS_SERIES[i][0], BOS_SERIES[i][1], BOS_SERIES[i][2], BOS_SERIES[i][3]);
   return g.b;
}

static std::string eventsText(const MqlArray<SSvpStructEvent> &ev)
{
   std::string s;
   for(const SSvpStructEvent &e : ev.v)
      s += std::string(e.kind == SVP_EV_BOS ? "BOS" : "CHoCH") + (e.direction > 0 ? "+" : "-") + "@" + num(e.level, 1) + "#" + std::to_string(e.break_index) + " ";
   return s;
}

static void unitStructure()
{
   g_group = "structure";
   MqlArray<SSvpSwing> sw; MqlArray<SSvpStructEvent> ev; SSvpStructure st;
   // --- H4 bias from swings and breaks only
   Story story = makeStory(0);
   Tf tf; tf.build(story.bars);
   SVP_TrackStructure(tf.h4, (int)tf.h4.v.size(), 3, 3, sw, ev, st);
   bool all_up = !ev.v.empty();
   for(const SSvpStructEvent &e : ev.v) if(e.direction != 1 || e.kind != SVP_EV_BOS) all_up = false;
   check(st.valid && st.trend == 1 && st.bias == 1 && all_up && st.high_label == SVP_SW_HH && st.low_label == SVP_SW_HL,
         "S01 H4 of a rising zigzag: every break is a bullish BOS, swings HH/HL, bias BULLISH",
         "trend " + std::to_string(st.trend) + " bias " + std::to_string(st.bias) + " " + eventsText(ev));
   const int up_events = (int)ev.v.size();
   Tf tm; tm.build(mirrored(story.bars, 4300.0));
   SVP_TrackStructure(tm.h4, (int)tm.h4.v.size(), 3, 3, sw, ev, st);
   bool all_dn = !ev.v.empty();
   for(const SSvpStructEvent &e : ev.v) if(e.direction != -1 || e.kind != SVP_EV_BOS) all_dn = false;
   check(st.trend == -1 && st.bias == -1 && all_dn && (int)ev.v.size() == up_events && st.high_label == SVP_SW_LH && st.low_label == SVP_SW_LL,
         "S02 the price-mirrored series: the same number of bearish BOS, swings LH/LL, bias BEARISH", eventsText(ev));
   {
      Gen g(T0, 2000.0);
      for(int c = 0; c < 8; c++) { g.run(80, 0.25); g.run(80, -0.25); }
      Tf tr; tr.build(g.b);
      SVP_TrackStructure(tr.h4, (int)tr.h4.v.size(), 3, 3, sw, ev, st);
      check(st.valid && st.swing_count >= 8 && ev.v.empty() && st.trend == 0 && st.bias == 0,
            "S03 a range (equal highs and lows, no close beyond a swing): no break, bias NEUTRAL",
            "swings " + std::to_string(st.swing_count) + " events " + eventsText(ev));
   }
   {
      // uptrend, then a fall through the last H4 swing low, a lower high, and a second leg down
      Gen g(T0, 2000.0);
      for(int c = 0; c < 2; c++) { g.zig(20, 5, 0.9, 3, -0.5); g.zig(12, 5, -0.9, 3, 0.5); }
      g.zig(20, 5, 0.9, 3, -0.5);
      g.run(160, -0.6); g.run(96, 0.3); g.run(160, -0.6);
      Tf tc; tc.build(g.b);
      const int n4 = (int)tc.h4.v.size();
      SVP_TrackStructure(tc.h4, n4, 3, 3, sw, ev, st);
      int choch = -1, bos_after = -1;
      for(size_t i = 0; i < ev.v.size(); i++)
      {
         if(choch < 0 && ev.v[i].kind == SVP_EV_CHOCH && ev.v[i].direction == -1) choch = (int)i;
         else if(choch >= 0 && bos_after < 0 && ev.v[i].kind == SVP_EV_BOS && ev.v[i].direction == -1) bos_after = (int)i;
      }
      check(choch >= 0 && bos_after > choch && st.trend == -1 && st.bias == -1,
            "S04 uptrend -> bearish CHoCH -> lower high -> bearish BOS: bias ends BEARISH", eventsText(ev));
      if(choch >= 0)
      {
         MqlArray<SSvpSwing> sw2; MqlArray<SSvpStructEvent> ev2; SSvpStructure s2;
         SVP_TrackStructure(tc.h4, ev.v[(size_t)choch].break_index + 1, 3, 3, sw2, ev2, s2);
         check(s2.trend == -1 && s2.last_kind == SVP_EV_CHOCH && s2.bias == 0,
               "S05 on the bar of the CHoCH itself the trend has flipped but the bias is still NEUTRAL (a warning, not a bias)",
               "bias " + std::to_string(s2.bias));
      }
   }
   // --- BOS / CHoCH on a hand-checked series, pivots of 2 bars each side
   std::vector<MqlRates> bs = bosSeries();
   MqlArray<MqlRates> a; toArray(bs, a);
   SVP_TrackStructure(a, 24, 2, 2, sw, ev, st);
   check(eventsText(ev) == "BOS+@102.0#8 CHoCH-@102.2#16 BOS-@100.2#23 ",
         "S06 hand-checked series: bullish BOS of 102.0 on bar 8, bearish CHoCH of 102.2 on bar 16, bearish BOS of 100.2 on bar 23",
         eventsText(ev));
   check(a.v[7].high > 102.0 && a.v[7].close < 102.0 && ev.v.size() == 3 && ev.v[0].break_index == 8,
         "S07 bar 7 wicks through 102.0 and closes below it: no break (liquidity taken, structure intact)");
   check(st.trend == -1 && st.bias == -1 && st.high_label == SVP_SW_LH && st.low_label == SVP_SW_LL && near(st.last_level, 100.2),
         "S08 final state: bearish, swings LH/LL, last broken level 100.2");
   // --- nothing is known before it could be known
   bool causal = true; std::string why;
   for(int n = 6; n <= 24 && causal; n++)
   {
      MqlArray<SSvpSwing> sp; MqlArray<SSvpStructEvent> ep; SSvpStructure xp;
      SVP_TrackStructure(a, n, 2, 2, sp, ep, xp);
      for(const SSvpSwing &x : sp.v) if(x.confirm > n - 1 || x.confirm != x.index + 2) { causal = false; why = "swing known before its confirmation bar at n=" + std::to_string(n); }
      size_t expect = 0;
      for(const SSvpStructEvent &e : ev.v) if(e.break_index < n) expect++;
      if(ep.v.size() != expect) { causal = false; why = "event list of prefix " + std::to_string(n) + " differs"; }
      for(size_t i = 0; i < ep.v.size() && causal; i++)
         if(ep.v[i].break_index != ev.v[i].break_index || ep.v[i].kind != ev.v[i].kind || !near(ep.v[i].level, ev.v[i].level)) { causal = false; why = "event changed with later data"; }
   }
   check(causal, "S09 every prefix of the series gives the same swings and events as the full series up to that bar (no repaint)", why);
   // --- internal vs external structure (H1), and the invalidation level
   {
      // a major up-leg, a shallow dip (an INTERNAL pivot low only), a new high,
      // then a pullback that closes under the internal low but not the external one
      Gen g(T0, 100.0);
      g.run(12, 1.0); g.run(8, -0.7); g.run(12, 1.0);
      g.run(3, -0.6); g.run(6, 1.0);
      g.run(7, -1.1);
      MqlArray<MqlRates> h; toArray(g.b, h);
      MqlArray<SSvpSwing> s_ext, s_int; MqlArray<SSvpStructEvent> e_ext, e_int; SSvpStructure x_ext, x_int;
      SVP_TrackStructure(h, g.size(), 5, 5, s_ext, e_ext, x_ext);
      SVP_TrackStructure(h, g.size(), 2, 2, s_int, e_int, x_int);
      check(x_ext.trend == 1 && x_int.trend == -1 && x_int.last_kind == SVP_EV_CHOCH && x_ext.invalidation < x_int.last_level,
            "S10 a close under an INTERNAL swing low flips the internal structure (CHoCH) while the EXTERNAL structure stays bullish: "
            "a pullback, not a reversal",
            "ext " + std::to_string(x_ext.trend) + " " + eventsText(e_ext) + "| int " + std::to_string(x_int.trend) + " " + eventsText(e_int));
   }
   SSvpParams p; SVP_DefaultParams(p);
   analyze(tf, story.i_low1 + 1, p);
   check(g_svp_h1.invalidation > 0.0 && near(g_svp_h1.invalidation, g_svp_h1.low_price) && g_svp_h1.low_standing &&
         g_svp_h1.invalidation < tf.m15.v[(size_t)story.i_low1].low,
         "S11 the structural invalidation of a bullish H1 is its last standing swing low, below the pullback",
         num(g_svp_h1.invalidation));
   // --- displacement is measured against the volatility that existed BEFORE the candle
   MqlArray<double> atr;
   SVP_ATR(tf.m15, tf.n15(), 14, atr);
   check(SVP_IsDisplacement(tf.m15, atr, story.i_disp, 1, 1.0, 0.6) && !SVP_IsDisplacement(tf.m15, atr, story.i_disp, -1, 1.0, 0.6) &&
         !SVP_IsDisplacement(tf.m15, atr, story.i_sweep, 1, 1.0, 0.6) && !SVP_IsDisplacement(tf.m15, atr, story.i_disp, 1, 3.0, 0.6),
         "S12 displacement: the 3.0-point bullish body qualifies, the sweep candle does not, and neither does a 3x ATR demand");
   bool atr_causal = true;
   for(int n = 20; n < 400 && atr_causal; n += 37)
   {
      MqlArray<double> ap; SVP_ATR(tf.m15, n, 14, ap);
      for(int i = 0; i < n; i++) if(!near(ap.v[(size_t)i], atr.v[(size_t)i], 1e-12)) atr_causal = false;
   }
   check(atr_causal, "S13 ATR of bar i is the same whether or not later bars exist");
}

// ================================================================== unit: liquidity
// one synthetic day of 96 candles that trades hi and lo exactly once each
static void dayRange(Gen &g, const double lo, const double hi)
{
   const double mid = 0.5 * (lo + hi), w = 0.2;
   g.px = mid;
   g.run(24, ((hi - w) - mid) / 24.0, w);
   g.run(48, ((lo + w) - (hi - w)) / 48.0, w);
   g.run(24, (mid - (lo + w)) / 24.0, w);
}

// two weeks and a day of ranges, then the current day with two highs at x1 and x2
static Gen liquiditySeries(const int days, const double x1, const double x2, const bool take_pdh)
{
   Gen g(T0, 2000.0);
   for(int d = 0; d < days; d++)
   {
      if(d < 7) dayRange(g, 1980.0 + d, 2020.0 + d);                       // week 1: PWH 2026, PWL 1980
      else if(d < 14) dayRange(g, 1992.0 - (d - 7), 2028.0 + (d - 7));     // week 2: PWH 2034, PWL 1986
      else dayRange(g, 2000.0, 2024.0);                                    // the previous day: PDH 2024, PDL 2000
   }
   g.px = 2012.0;
   g.run(4, (x1 - 1.0 - 2012.0) / 4.0);
   g.bar(g.px, x1, g.px - 0.2, x1 - 0.4);                                   // first high
   g.run(3, -0.8); g.run(2, 0.8);
   g.bar(g.px, x2, g.px - 0.2, x2 - 0.5);                                   // second high
   g.run(4, -0.7);
   if(take_pdh) { g.bar(g.px, 2024.5, g.px - 0.2, g.px + 0.3); g.run(3, -0.5); }
   return g;
}

static int findZone(const MqlArray<SSvpLiqZone> &z, const int side, const int kind_mask, const double level)
{
   for(size_t i = 0; i < z.v.size(); i++)
      if(z.v[i].side == side && (z.v[i].kinds & kind_mask) == kind_mask && near(z.v[i].level, level, 1e-6)) return (int)i;
   return -1;
}

static int buildLiquidity(const Gen &g, const SSvpParams &p, MqlArray<SSvpLiqZone> &zones, MqlArray<double> &atr,
                          MqlArray<MqlRates> &a)
{
   toArray(g.b, a);
   MqlArray<SSvpSwing> sw; MqlArray<SSvpStructEvent> ev; SSvpStructure st;
   SVP_ATR(a, g.size(), p.atr_period, atr);
   SVP_TrackStructure(a, g.size(), p.m15_swing, p.m15_swing, sw, ev, st);
   return SVP_BuildLiquidity(a, g.size(), atr, sw, p, zones);
}

static void unitLiquidity()
{
   g_group = "liquidity";
   SSvpParams p; SVP_DefaultParams(p);
   MqlArray<SSvpLiqZone> z; MqlArray<double> atr; MqlArray<MqlRates> a;
   Gen g = liquiditySeries(15, 2018.00, 2018.04, false);
   buildLiquidity(g, p, z, atr, a);
   const double atr_now = atr.v.back();
   int eq = findZone(z, 1, SVP_LIQ_EQ, 2018.04);
   check(eq >= 0 && near(z.v[(size_t)eq].lo, 2018.00) && near(z.v[(size_t)eq].hi, 2018.04) && z.v[(size_t)eq].taken_index < 0 &&
         z.v[(size_t)eq].strength == 3 && std::string(z.v[(size_t)eq].label) == "EQH",
         "L01 two pivot highs 0.04 apart (tolerance " + num(SVP_Tolerance(atr_now, p.liq_eq_tol_atr, p.liq_tol_ticks, p.tick_size)) +
         ") are ONE equal-highs zone 2018.00-2018.04, level 2018.04, intact", eq < 0 ? "no EQH zone" : std::string(z.v[(size_t)eq].label));
   int pdh = findZone(z, 1, SVP_LIQ_PD, 2024.0), pdl = findZone(z, -1, SVP_LIQ_PD, 2000.0);
   int pwh = findZone(z, 1, SVP_LIQ_PW, 2034.0), pwl = findZone(z, -1, SVP_LIQ_PW, 1986.0);
   check(pdh >= 0 && pdl >= 0 && z.v[(size_t)pdh].taken_index < 0 && z.v[(size_t)pdl].taken_index < 0,
         "L02 PDH 2024.00 and PDL 2000.00 are the previous COMPLETE day's extremes, both intact");
   check(pwh >= 0 && pwl >= 0, "L03 PWH 2034.00 and PWL 1986.00 are the previous COMPLETE week's extremes (weeks start on Monday)");
   check(pdh >= 0 && std::string(z.v[(size_t)pdh].label) == "PDH" && z.v[(size_t)pdh].members == 2 && z.v[(size_t)pdh].strength == 4,
         "L04 the pivot high that MADE the previous day's high is merged into the PDH zone: one object, not two lines",
         pdh < 0 ? "" : std::string(z.v[(size_t)pdh].label) + " members " + std::to_string(z.v[(size_t)pdh].members));
   int dup = 0;
   for(size_t i = 0; i < z.v.size(); i++)
      for(size_t j = i + 1; j < z.v.size(); j++)
         if(z.v[i].side == z.v[j].side && z.v[i].taken_index == z.v[j].taken_index &&
            std::max(z.v[i].lo, z.v[j].lo) - std::min(z.v[i].hi, z.v[j].hi) <=
            SVP_Tolerance(atr_now, p.liq_merge_atr, p.liq_tol_ticks, p.tick_size) && z.v[i].taken_index < 0) dup++;
   check(dup == 0, "L05 no two intact zones of one side sit inside the merge tolerance of each other", std::to_string(dup) + " overlapping pairs");
   // near the previous day's high the equal highs join it
   Gen g2 = liquiditySeries(15, 2023.80, 2023.84, false);
   buildLiquidity(g2, p, z, atr, a);
   int both = findZone(z, 1, SVP_LIQ_PD | SVP_LIQ_EQ, 2024.0);
   check(both >= 0 && std::string(z.v[(size_t)both].label) == "PDH+EQH" && near(z.v[(size_t)both].lo, 2023.80) && near(z.v[(size_t)both].hi, 2024.0),
         "L06 equal highs 0.16 under the PDH merge with it: zone PDH+EQH 2023.80-2024.00, level 2024.00",
         both < 0 ? "not merged" : std::string(z.v[(size_t)both].label));
   // half a point apart is not "equal" at this volatility
   Gen g3 = liquiditySeries(15, 2018.00, 2018.50, false);
   buildLiquidity(g3, p, z, atr, a);
   bool any_eq = false;
   for(const SSvpLiqZone &x : z.v) if(x.side == 1 && (x.kinds & SVP_LIQ_EQ) != 0 && x.level < 2020.0) any_eq = true;
   check(!any_eq && findZone(z, 1, SVP_LIQ_SWING, 2018.50) >= 0,
         "L07 highs 0.50 apart are NOT equal highs: the tolerance follows ATR and the tick size, not a fixed number");
   check(near(SVP_Tolerance(3.0, 0.10, 5, 0.01), 0.30) && near(SVP_Tolerance(0.1, 0.10, 5, 0.01), 0.05) &&
         near(SVP_Tolerance(0.0003, 0.10, 5, 0.00001), 0.00005),
         "L08 tolerance = max(ATR multiple, ticks): 0.30 at ATR 3.0, 5 ticks when volatility is tiny, on any precision");
   // the previous day's high is traded through
   Gen g4 = liquiditySeries(15, 2018.00, 2018.04, true);
   buildLiquidity(g4, p, z, atr, a);
   int taken = findZone(z, 1, SVP_LIQ_PD, 2024.0);
   check(taken >= 0 && z.v[(size_t)taken].taken_index == g4.size() - 4,
         "L09 a bar that trades through the PDH marks the zone as taken on that bar", taken < 0 ? "zone missing" : std::to_string(z.v[(size_t)taken].taken_index));
   // missing history: a level that cannot be proven complete is absent, not guessed
   Gen g5 = liquiditySeries(1, 2018.00, 2018.04, false);
   buildLiquidity(g5, p, z, atr, a);
   bool pd = false, pw = false;
   for(const SSvpLiqZone &x : z.v) { if((x.kinds & SVP_LIQ_PD) != 0) pd = true; if((x.kinds & SVP_LIQ_PW) != 0) pw = true; }
   check(!pd && !pw, "L10 with one earlier day in the history there is no PDH/PDL and no PWH/PWL (completeness cannot be proven)");
   Gen g6 = liquiditySeries(4, 2018.00, 2018.04, false);
   buildLiquidity(g6, p, z, atr, a);
   pd = false; pw = false;
   for(const SSvpLiqZone &x : z.v) { if((x.kinds & SVP_LIQ_PD) != 0) pd = true; if((x.kinds & SVP_LIQ_PW) != 0) pw = true; }
   check(pd && !pw, "L11 with four earlier days: PDH/PDL exist, PWH/PWL still do not");
   // the story: equal LOWS, sell-side
   Story st = makeStory(0); Tf tf; tf.build(st.bars);
   analyze(tf, st.i_sweep, p);                    // as of the bar BEFORE the sweep
   int eql = -1;
   for(size_t i = 0; i < g_svp_liq.v.size(); i++)
      if(g_svp_liq.v[i].side == -1 && (g_svp_liq.v[i].kinds & SVP_LIQ_EQ) != 0 && g_svp_liq.v[i].taken_index < 0) eql = (int)i;
   check(eql >= 0 && near(g_svp_liq.v[(size_t)eql].level, st.L0 - 0.2) && near(g_svp_liq.v[(size_t)eql].hi, st.L0 - 0.15),
         "L12 the story's two lows 0.05 apart are an intact EQL zone, level = the lower one",
         eql < 0 ? "no EQL" : num(g_svp_liq.v[(size_t)eql].level));
   bool ids_unique = true;
   for(size_t i = 0; i < g_svp_liq.v.size(); i++)
      for(size_t j = i + 1; j < g_svp_liq.v.size(); j++)
         if(std::string(g_svp_liq.v[i].id) == std::string(g_svp_liq.v[j].id)) ids_unique = false;
   check(ids_unique && g_svp_liq.v.size() >= 4, "L13 every zone has its own stable id (side | earliest member | level)");
}

// ================================================================== unit: sweep engine
struct SweepCase
{
   std::vector<MqlRates> bars;
   MqlArray<SSvpStructEvent> events;
   SSvpLiqZone zone;
};

// 30 calm candles around 100 (ATR 1.0), then `extra` candles {o,h,l,c}; a
// sell-side zone at 99.00 that candle 30 trades through
static SweepCase sweepCase(const std::vector<std::array<double, 4>> &extra, const int event_at, const bool mirror)
{
   SweepCase c;
   Gen g(T0, 100.0);
   for(int i = 0; i < 30; i++) g.step((i % 2 == 0) ? 0.6 : -0.6);
   for(const auto &e : extra) g.bar(e[0], e[1], e[2], e[3]);
   c.bars = mirror ? mirrored(g.b, 200.0) : g.b;
   c.zone.side = mirror ? 1 : -1;
   c.zone.lo = c.zone.hi = c.zone.level = mirror ? 101.0 : 99.0;
   c.zone.kinds = SVP_LIQ_EQ; c.zone.strength = 3; c.zone.members = 1; c.zone.label = mirror ? "EQH" : "EQL";
   c.zone.formed_index = 20; c.zone.formed_time = c.bars[20].time;
   c.zone.taken_index = 30; c.zone.taken_time = c.bars[30].time;
   c.zone.id = "test";
   if(event_at >= 0)
   {
      SSvpStructEvent e{};
      e.kind = SVP_EV_CHOCH; e.direction = mirror ? -1 : 1; e.break_index = event_at; e.break_time = c.bars[(size_t)event_at].time;
      e.level = mirror ? 99.4 : 100.6; e.swing_index = 25; e.swing_time = c.bars[25].time;
      c.events.v.push_back(e);
   }
   return c;
}

static SSvpSweep classify(const SweepCase &c, const int n, const SSvpParams &p)
{
   MqlArray<MqlRates> a; toArray(c.bars, a);
   MqlArray<double> atr; SVP_ATR(a, n, p.atr_period, atr);
   MqlArray<SSvpStructEvent> ev;
   for(const SSvpStructEvent &e : c.events.v) if(e.break_index < n) ev.v.push_back(e);
   SSvpSweep sw; SVP_ClassifySweep(a, n, atr, ev, c.zone, p, sw);
   return sw;
}

static void unitSweep()
{
   g_group = "sweep";
   SSvpParams p; SVP_DefaultParams(p);
   typedef std::array<double, 4> B;
   const B take = {100.0, 100.1, 98.5, 99.4};                 // 0.5 through 99.00, closes back at 99.40
   const B disp = {99.4, 100.9, 99.3, 100.8};                 // bullish body 1.4
   const B quiet_a = {99.4, 99.7, 99.2, 99.5}, quiet_b = {99.5, 99.7, 99.2, 99.4};
   for(int m = 0; m < 2; m++)
   {
      const bool mir = (m == 1);
      const std::string tag = mir ? " [mirrored: buy-side]" : " [sell-side]";
      const int rev = mir ? -1 : 1;
      // a) the genuine sweep
      SweepCase a = sweepCase({take, disp}, 31, mir);
      SSvpSweep s0 = classify(a, 31, p), s1 = classify(a, 32, p);
      check(s0.state == SVP_SWEEP_DETECTED && s0.closed_back && near(s0.penetration, 0.5) && s0.reject_ratio > 0.55 && !SVP_SweepActionable(s0),
            "W01 a wick 0.5 through the level that closes back inside is SWEEP_DETECTED - and nothing more yet" + tag,
            std::string(SVP_SweepStateText(s0.state)));
      check(s1.state == SVP_SWEEP_CONFIRMED && s1.displacement && s1.structure && s1.disp_index == 31 && s1.state_index == 31 &&
            s1.direction == rev && SVP_SweepActionable(s1) && SVP_SweepReadyIndex(s1) == 31,
            "W02 displacement away + a structure shift on the next bar make it SWEEP_CONFIRMED" + tag, std::string(SVP_SweepStateText(s1.state)));
      // b) displacement but no structure shift, then the window lapses
      SweepCase b = sweepCase({take, disp, quiet_a, quiet_b, quiet_a, quiet_b, quiet_a, quiet_b, quiet_a, quiet_b}, -1, mir);
      SSvpSweep b1 = classify(b, 34, p), b2 = classify(b, 39, p);
      check(b1.state == SVP_SWEEP_DETECTED && b1.displacement && !b1.structure,
            "W03 displacement WITHOUT a structure shift stays SWEEP_DETECTED" + tag, std::string(SVP_SweepStateText(b1.state)));
      check(b2.state == SVP_SWEEP_UNCONFIRMED && b2.state_index == 38 && !SVP_SweepActionable(b2),
            "W04 ... and becomes UNCONFIRMED once the 8-bar window has passed" + tag,
            std::string(SVP_SweepStateText(b2.state)) + " at " + std::to_string(b2.state_index));
      // c) the genuine breakout
      SweepCase c = sweepCase({B{100.0, 100.1, 98.3, 98.5}, B{98.5, 98.7, 98.0, 98.2}, B{98.2, 98.4, 97.8, 98.0}}, -1, mir);
      SSvpSweep c0 = classify(c, 31, p), c2 = classify(c, 33, p);
      check(c0.state == SVP_SWEEP_UNCONFIRMED && !c0.closed_back,
            "W05 a close beyond the level is UNCONFIRMED: not a sweep, not yet a breakout" + tag, std::string(SVP_SweepStateText(c0.state)));
      check(c2.state == SVP_SWEEP_BREAKOUT_CONFIRMED && c2.state_index == 32 && !SVP_SweepActionable(c2),
            "W06 three consecutive closes beyond the level are BREAKOUT_CONFIRMED" + tag, std::string(SVP_SweepStateText(c2.state)));
      // d) the failed breakout
      SweepCase d = sweepCase({B{100.0, 100.1, 98.3, 98.5}, B{98.5, 98.8, 98.3, 98.6}, B{98.6, 99.7, 98.5, 99.5}, B{99.5, 101.1, 99.4, 101.0}}, 33, mir);
      SSvpSweep d2 = classify(d, 33, p), d3 = classify(d, 34, p);
      check(d2.state == SVP_SWEEP_FALSE_BREAKOUT && d2.state_index == 32 && !SVP_SweepActionable(d2),
            "W07 closed beyond twice, then closed back inside: FALSE_BREAKOUT, not yet a trigger" + tag, std::string(SVP_SweepStateText(d2.state)));
      check(d3.state == SVP_SWEEP_FALSE_BREAKOUT && d3.displacement && d3.structure && SVP_SweepActionable(d3) && SVP_SweepReadyIndex(d3) == 33,
            "W08 a FALSE_BREAKOUT becomes a reversal trigger only with displacement AND a structure shift" + tag);
      // f) too deep, g) weak rejection
      SSvpSweep f = classify(sweepCase({B{100.0, 100.1, 97.0, 99.6}, disp}, 31, mir), 32, p);
      check(f.state == SVP_SWEEP_UNCONFIRMED && f.closed_back && f.penetration > 1.5,
            "W09 a 2.0 penetration (more than 1.5 ATR) is not a sweep even with a perfect rejection" + tag, std::string(SVP_SweepStateText(f.state)));
      SSvpSweep w = classify(sweepCase({B{100.0, 100.3, 98.5, 99.05}, disp}, 31, mir), 32, p);
      check(w.state == SVP_SWEEP_UNCONFIRMED && w.closed_back && w.reject_ratio < 0.5,
            "W10 a close back inside with a rejection of only " + num(w.reject_ratio) + " of the bar is not a sweep" + tag,
            std::string(SVP_SweepStateText(w.state)));
      // h) the rejection fails
      SweepCase h = sweepCase({take, B{99.4, 99.5, 98.4, 98.6}, B{98.6, 98.7, 98.2, 98.4}, B{98.4, 98.5, 98.0, 98.2}}, -1, mir);
      SSvpSweep h1 = classify(h, 32, p), h3 = classify(h, 34, p);
      check(h1.state == SVP_SWEEP_UNCONFIRMED && h3.state == SVP_SWEEP_BREAKOUT_CONFIRMED && h3.state_index == 33,
            "W11 a detected sweep whose level is then closed through reverts to UNCONFIRMED and ends as a breakout" + tag,
            std::string(SVP_SweepStateText(h1.state)) + " -> " + std::string(SVP_SweepStateText(h3.state)));
      // i) confirmation that arrives after the window does not count
      SweepCase late = sweepCase({take, quiet_a, quiet_b, quiet_a, quiet_b, quiet_a, quiet_b, quiet_a, quiet_b, disp}, 39, mir);
      SSvpSweep l = classify(late, 40, p);
      check(l.state == SVP_SWEEP_UNCONFIRMED && !SVP_SweepActionable(l),
            "W12 displacement + structure shift nine bars later is too late: still UNCONFIRMED" + tag, std::string(SVP_SweepStateText(l.state)));
      // the classification of an event never changes once it is final, whatever follows
      bool stable = true;
      for(int n = 33; n <= 34; n++) if(classify(d, n, p).state_index != 32 && n == 33) stable = false;
      SweepCase a_long = sweepCase({take, disp, quiet_a, quiet_b, B{99.4, 99.5, 97.0, 97.2}, B{97.2, 97.4, 96.0, 96.2}}, 31, mir);
      for(int n = 32; n <= 36; n++) if(classify(a_long, n, p).state != SVP_SWEEP_CONFIRMED) stable = false;
      check(stable, "W13 a confirmed sweep stays confirmed whatever the later bars do (an event is a fact, not a forecast)" + tag);
   }
   // the minimum penetration: touching a level is not taking it
   {
      Gen g(T0, 100.0);
      for(int i = 0; i < 30; i++) g.step((i % 2 == 0) ? 0.6 : -0.6);
      g.bar(100.0, 100.1, 98.99, 99.5);
      g.bar(99.5, 99.6, 98.97, 99.4);
      MqlArray<MqlRates> a; toArray(g.b, a);
      MqlArray<double> atr; SVP_ATR(a, g.size(), 14, atr);
      check(SVP_TakenIndex(a, 31, atr, 25, -1, 99.0, p) == -1 && SVP_TakenIndex(a, 32, atr, 25, -1, 99.0, p) == 31,
            "W14 a low 0.01 under the level does not take it (minimum 0.02 = 2 ticks / 0.02 ATR); 0.03 under does");
   }
   // the story, end to end through the engine
   Story st = makeStory(0); Tf tf; tf.build(st.bars);
   analyze(tf, st.i_sweep + 1, p);
   int si = SVP_PickSweep(-1, st.i_sweep, p);
   check(si >= 0 && g_svp_sweeps.v[(size_t)si].state == SVP_SWEEP_DETECTED && g_svp_sweeps.v[(size_t)si].take_index == st.i_sweep &&
         g_svp_buy.status[SVP_STEP_SWEEP] == SVP_STEP_PENDING && g_svp.state == SVP_DECISION_WAIT,
         "W15 story, sweep bar: SWEEP_DETECTED, the sweep step is PENDING and the decision is WAIT (no entry on a wick)");
   const std::string id0 = si >= 0 ? std::string(g_svp_sweeps.v[(size_t)si].id) : "";
   analyze(tf, st.i_disp + 1, p);
   si = SVP_PickSweep(-1, st.i_disp, p);
   check(si >= 0 && g_svp_sweeps.v[(size_t)si].state == SVP_SWEEP_CONFIRMED && std::string(g_svp_sweeps.v[(size_t)si].id) == id0 &&
         near(g_svp_sweeps.v[(size_t)si].extreme, st.L0 - 1.4),
         "W16 story, next bar: the SAME event (same id) is now SWEEP_CONFIRMED; its extreme is the swept low");
   int breakouts = 0;
   analyze(tf, st.i_low1 + 1, p);
   for(const SSvpSweep &x : g_svp_sweeps.v) if(x.side == -1 && x.state == SVP_SWEEP_BREAKOUT_CONFIRMED) breakouts++;
   check(breakouts >= 1 && g_svp_buy.status[SVP_STEP_SWEEP] == SVP_STEP_FAIL,
         "W17 story, during the pullback: lows that are closed through are BREAKOUT_CONFIRMED and fail the long sweep step",
         std::to_string(breakouts) + " breakouts");
}

// ================================================================== unit: OB / FVG zones
// 30 calm candles (ATR 1.0), a down candle, a displacement up, the third candle of a gap
static Gen zoneSeries()
{
   Gen g(T0, 100.0);
   for(int i = 0; i < 30; i++) g.step((i % 2 == 0) ? 0.6 : -0.6);
   g.bar(100.0, 100.2, 99.2, 99.4);       // 30: the last down candle  -> order block 99.20-100.20
   g.bar(99.4, 101.9, 99.3, 101.8);       // 31: displacement, body 2.4
   g.bar(101.8, 102.6, 101.5, 102.4);     // 32: low 101.50 above the high of 30 -> gap 100.20-101.50
   return g;
}

static int zonesOf(const std::vector<MqlRates> &bars, const int n, const SSvpParams &p, MqlArray<SSvpZone> &z,
                   const MqlArray<SSvpStructEvent> *events = nullptr)
{
   MqlArray<MqlRates> a; toArray(bars, a);
   MqlArray<double> atr; SVP_ATR(a, n, p.atr_period, atr);
   MqlArray<SSvpStructEvent> none;
   return SVP_BuildZones(a, n, atr, events ? *events : none, p, z);
}

static int firstZone(const MqlArray<SSvpZone> &z, const int direction)
{
   for(size_t i = 0; i < z.v.size(); i++) if(z.v[i].direction == direction) return (int)i;
   return -1;
}

static int countZones(const MqlArray<SSvpZone> &z, const int direction)
{
   int n = 0;
   for(const SSvpZone &x : z.v) if(x.direction == direction) n++;
   return n;
}

static void unitZones()
{
   g_group = "zones";
   SSvpParams p; SVP_DefaultParams(p);
   MqlArray<SSvpZone> z;
   Gen g = zoneSeries();
   zonesOf(g.b, 31, p, z);
   check(z.v.empty(), "Z01 before the displacement candle closes there is no zone (a down candle alone is not an order block)");
   zonesOf(g.b, 32, p, z);
   int i = firstZone(z, 1);
   const std::string id0 = i >= 0 ? std::string(z.v[(size_t)i].id) : "";
   check(i >= 0 && countZones(z, 1) == 1 && z.v[(size_t)i].kind == SVP_ZONE_OB && near(z.v[(size_t)i].lo, 99.2) && near(z.v[(size_t)i].hi, 100.2) &&
         z.v[(size_t)i].origin_index == 30 && z.v[(size_t)i].avail_index == 31 && z.v[(size_t)i].state == SVP_ZS_DETECTED,
         "Z02 the displacement closes: bullish OB 99.20-100.20 = the last down candle, known from bar 31, state DETECTED (not backed yet)");
   {
      MqlArray<SSvpStructEvent> ev; SSvpStructEvent e{};
      e.kind = SVP_EV_BOS; e.direction = 1; e.break_index = 31; e.break_time = g.b[31].time; e.level = 100.8;
      ev.v.push_back(e);
      zonesOf(g.b, 32, p, z, &ev);
      i = firstZone(z, 1);
      check(i >= 0 && z.v[(size_t)i].state == SVP_ZS_VALIDATED && z.v[(size_t)i].backed,
            "Z03 the same block with a structure break behind it is VALIDATED");
   }
   zonesOf(g.b, 33, p, z);
   i = firstZone(z, 1);
   check(i >= 0 && countZones(z, 1) == 1 && z.v[(size_t)i].kind == SVP_ZONE_BOTH && near(z.v[(size_t)i].lo, 99.2) && near(z.v[(size_t)i].hi, 101.5) &&
         std::string(z.v[(size_t)i].id) == id0 && z.v[(size_t)i].origin_index == 30 && z.v[(size_t)i].avail_index == 32 &&
         z.v[(size_t)i].state == SVP_ZS_VALIDATED && z.v[(size_t)i].touches == 0,
         "Z04 the gap 100.20-101.50 of the same leg MERGES with the block: ONE zone OB+FVG 99.20-101.50, same id, VALIDATED, fresh",
         i < 0 ? "" : std::string(SVP_ZoneText(z.v[(size_t)i], 2)));
   // lifecycle
   Gen l = zoneSeries();
   l.bar(102.4, 102.5, 101.0, 101.6);     // 33: first retest, 0.5 into a 2.3-high zone
   l.bar(101.6, 102.2, 101.1, 102.0);     // 34: still inside: the same retest
   l.bar(102.0, 102.8, 101.9, 102.6);     // 35: left the zone
   l.bar(102.6, 102.7, 99.1, 100.4);      // 36: second retest, through the whole zone, closes inside
   l.bar(100.4, 100.5, 98.6, 98.8);       // 37: closes below the zone
   zonesOf(l.b, 34, p, z); i = firstZone(z, 1);
   check(i >= 0 && z.v[(size_t)i].state == SVP_ZS_PARTIAL && z.v[(size_t)i].touches == 1 && z.v[(size_t)i].first_touch == 33 &&
         near(z.v[(size_t)i].fill, 0.5 / 2.3, 1e-9) && SVP_ZoneAlive(z.v[(size_t)i]),
         "Z05 first retest 0.50 deep: PARTIALLY MITIGATED, fill 22%, still alive", i < 0 ? "" : num(z.v[(size_t)i].fill, 4));
   zonesOf(l.b, 36, p, z); i = firstZone(z, 1);
   check(i >= 0 && z.v[(size_t)i].touches == 1 && z.v[(size_t)i].state == SVP_ZS_PARTIAL,
         "Z06 two consecutive bars inside the zone are ONE retest, not two");
   zonesOf(l.b, 37, p, z); i = firstZone(z, 1);
   check(i >= 0 && z.v[(size_t)i].state == SVP_ZS_MITIGATED && z.v[(size_t)i].touches == 2 && near(z.v[(size_t)i].fill, 1.0) && SVP_ZoneAlive(z.v[(size_t)i]),
         "Z07 traded through but closed inside: MITIGATED (fill 100%), second retest counted, still alive");
   zonesOf(l.b, 38, p, z); i = firstZone(z, 1);
   check(i >= 0 && z.v[(size_t)i].state == SVP_ZS_INVALIDATED && z.v[(size_t)i].state_index == 37 && !SVP_ZoneAlive(z.v[(size_t)i]),
         "Z08 a CLOSE below the zone: INVALIDATED on that bar, no longer alive");
   // expiry
   Gen e = zoneSeries();
   e.run(100, 0.05);
   auto byId = [&z](const std::string &id) { for(size_t q = 0; q < z.v.size(); q++) if(std::string(z.v[q].id) == id) return (int)q; return -1; };
   zonesOf(e.b, 129, p, z); i = byId(id0);
   const bool alive_before = (i >= 0 && z.v[(size_t)i].state == SVP_ZS_VALIDATED && SVP_ZoneAlive(z.v[(size_t)i]));
   zonesOf(e.b, 130, p, z); i = byId(id0);
   check(alive_before && i >= 0 && z.v[(size_t)i].state == SVP_ZS_EXPIRED && !SVP_ZoneAlive(z.v[(size_t)i]),
         "Z09 never retested: alive through its 96th bar, EXPIRED on the 97th");
   // the mirror
   std::vector<MqlRates> m = mirrored(l.b, 200.0);
   zonesOf(m, 33, p, z); i = firstZone(z, -1);
   bool mir = (i >= 0 && z.v[(size_t)i].kind == SVP_ZONE_BOTH && near(z.v[(size_t)i].lo, 98.5) && near(z.v[(size_t)i].hi, 100.8) && countZones(z, -1) == 1);
   zonesOf(m, 34, p, z); i = firstZone(z, -1);
   mir = mir && i >= 0 && z.v[(size_t)i].state == SVP_ZS_PARTIAL && near(z.v[(size_t)i].fill, 0.5 / 2.3, 1e-9);
   zonesOf(m, 38, p, z); i = firstZone(z, -1);
   mir = mir && i >= 0 && z.v[(size_t)i].state == SVP_ZS_INVALIDATED && z.v[(size_t)i].state_index == 37;
   check(mir, "Z10 the price-mirrored series gives the mirrored bearish zone 98.50-100.80 with the same lifecycle");
   // the minimum gap
   for(int k = 0; k < 2; k++)
   {
      Gen f(T0, 100.0);
      for(int q = 0; q < 30; q++) f.step((q % 2 == 0) ? 0.6 : -0.6);
      f.bar(100.0, 101.2, 99.9, 101.1);                                   // displacement; the bar before it has high 100.80
      const double low3 = (k == 0 ? 100.85 : 100.95);
      f.bar(101.1, 101.6, low3, 101.5);
      zonesOf(f.b, 32, p, z); i = firstZone(z, 1);
      if(k == 0)
         check(i >= 0 && z.v[(size_t)i].kind == SVP_ZONE_OB && near(z.v[(size_t)i].hi, 100.8),
               "Z11 a 0.05 gap at ATR 1.0 (minimum 0.10) is not a fair value gap");
      else
         check(i >= 0 && z.v[(size_t)i].kind == SVP_ZONE_BOTH && near(z.v[(size_t)i].hi, 100.95),
               "Z12 a 0.15 gap is, and it joins the block of its leg");
   }
   // the story: the merge rule left nothing mergeable, ids are unique, nothing is known early
   Story st = makeStory(1); Tf tf; tf.build(st.bars);
   analyze(tf, tf.n15(), p);
   int mergeable = 0, dup_ids = 0, early = 0;
   const int nz = (int)g_svp_zones.v.size();
   for(int a = 0; a < nz; a++)
   {
      const SSvpZone &x = g_svp_zones.v[(size_t)a];
      if(x.avail_index < x.origin_index || x.avail_index > tf.n15() - 1) early++;
      for(int b = a + 1; b < nz; b++)
      {
         const SSvpZone &y = g_svp_zones.v[(size_t)b];
         if(std::string(x.id) == std::string(y.id)) dup_ids++;
         if(x.direction != y.direction || std::abs(x.origin_index - y.origin_index) > 3) continue;
         const int early_i = std::min(x.avail_index, y.avail_index);
         if(std::max(x.lo, y.lo) - std::min(x.hi, y.hi) <= p.zone_merge_atr * g_svp_atr_m15.v[(size_t)early_i]) mergeable++;
      }
   }
   check(nz >= 4 && mergeable == 0 && dup_ids == 0 && early == 0,
         "Z13 story (" + std::to_string(nz) + " zones): no two zones of one leg are left unmerged, every id is unique",
         "mergeable " + std::to_string(mergeable) + " dup " + std::to_string(dup_ids) + " early " + std::to_string(early));
   bool causal = true;
   for(int n = st.i_sweep; n <= st.i_confirm + 1 && causal; n++)
   {
      MqlArray<SSvpZone> a_z, b_z;
      zonesOf(st.bars, n, p, a_z);
      std::vector<MqlRates> cut(st.bars.begin(), st.bars.begin() + n);
      zonesOf(cut, n, p, b_z);
      if(a_z.v.size() != b_z.v.size()) causal = false;
      for(size_t q = 0; q < a_z.v.size() && causal; q++)
         if(std::string(a_z.v[q].id) != std::string(b_z.v[q].id) || a_z.v[q].state != b_z.v[q].state || !near(a_z.v[q].lo, b_z.v[q].lo) ||
            !near(a_z.v[q].hi, b_z.v[q].hi)) causal = false;
   }
   check(causal, "Z14 zones computed with later bars present in the array equal zones computed without them (bars >= n are never read)");
}

// ================================================================== unit: volume profile
static MqlRates vbar(const datetime t, const double lo, const double hi, const long tick, const long real = 0)
{
   MqlRates r{};
   r.time = t; r.open = lo; r.close = hi; r.low = lo; r.high = hi; r.tick_volume = tick; r.real_volume = real; r.spread = 0;
   return r;
}

static std::string vpText(const SSvpProfile &p)
{
   return "POC " + num(p.poc, 3) + " VAL " + num(p.val, 3) + " VAH " + num(p.vah, 3) + " share " + num(p.va_fraction, 4) +
          " bins " + std::to_string(p.bin_count) + " row " + num(p.bin_size, 3) + " | " + std::string(p.reason);
}

// deterministic pseudo-random candles (LCG), prices on a 0.01 grid
static std::vector<MqlRates> randomBars(const int n, unsigned seed, const double start, const double vol)
{
   std::vector<MqlRates> out;
   double px = start;
   datetime t = T0;
   auto next = [&seed]() { seed = seed * 1664525u + 1013904223u; return (double)(seed >> 8) / 16777216.0; };
   for(int i = 0; i < n; i++)
   {
      const double o = px;
      const double c = std::round((o + (next() - 0.5) * 2.0 * vol) * 100.0) / 100.0;
      const double h = std::round((std::max(o, c) + next() * vol * 0.6) * 100.0) / 100.0;
      const double l = std::round((std::min(o, c) - next() * vol * 0.6) * 100.0) / 100.0;
      MqlRates r{};
      r.time = t; r.open = o; r.high = h; r.low = l; r.close = c;
      r.tick_volume = 200 + (long)(next() * 3000.0); r.real_volume = 0; r.spread = 0;
      out.push_back(r);
      px = c; t += 900;
   }
   return out;
}

static void unitVolume()
{
   g_group = "volume";
   SSvpParams p; SVP_DefaultParams(p);
   string where;
   check(SVP_VpSelfTest(where), "V01 the module's own numeric self-test (six one-row bars: POC 102.5, value area 101.0-104.0)", std::string(where));
   // --- a hand-computed profile with bars that span several rows
   //   A 100.00-102.99 x300 -> rows 0,1,2 get 100 each     B 101.00-101.99 x200 -> row 1
   //   C 102.00-104.99 x300 -> rows 2,3,4 get 100 each     D 104.00-104.99 x50  -> row 4
   //   rows: 100 | 300 | 200 | 100 | 150   total 850
   MqlArray<MqlRates> r;
   r.v = {vbar(T0, 100.0, 102.99, 300), vbar(T0 + 900, 101.0, 101.99, 200), vbar(T0 + 1800, 102.0, 104.99, 300), vbar(T0 + 2700, 104.0, 104.99, 50)};
   SSvpProfile vp;
   const bool built = SVP_VpBuild(r, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, p, vp);
   check(built && vp.bin_count == 5 && near(vp.bins[0], 100) && near(vp.bins[1], 300) && near(vp.bins[2], 200) && near(vp.bins[3], 100) &&
         near(vp.bins[4], 150) && near(vp.total_volume, 850),
         "V02 a bar's volume is spread evenly over the rows its range touches: rows 100 | 300 | 200 | 100 | 150, total 850", vpText(vp));
   check(built && near(vp.poc, 101.5) && near(vp.poc_volume, 300),
         "V03 POC = centre of the heaviest row = 101.50");
   check(built && near(vp.val, 100.0) && near(vp.vah, 104.0) && near(vp.va_fraction, 700.0 / 850.0, 1e-12),
         "V04 value area 70%: 300 -> +200 above (58.8%) -> the next rows TIE at 100 / 100 and are taken together, so the area has no preferred "
         "side -> 700/850 = 82.4%: VAL 100.00, VAH 104.00", vpText(vp));
   string why;
   check(built && SVP_VpValidate(vp, why), "V05 the profile satisfies every invariant (rows sum to the total, POC heaviest, VAL <= POC <= VAH)", std::string(why));
   {
      SSvpParams q = p; q.vp_value_fraction = 0.95;
      SSvpProfile wide; SVP_VpBuild(r, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, q, wide);
      SSvpParams q2 = p; q2.vp_value_fraction = 0.50;
      SSvpProfile narrow; SVP_VpBuild(r, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, q2, narrow);
      check(near(wide.val, 100.0) && near(wide.vah, 105.0) && near(narrow.val, 101.0) && near(narrow.vah, 103.0),
            "V06 the value-area share is configurable: 95% -> 100.00-105.00, 50% -> 101.00-103.00",
            vpText(wide) + " / " + vpText(narrow));
   }
   // --- rows follow the tick size
   check(near(SVP_VpBinSize(0.01, 3.0, 0.10, 0), 0.30) && near(SVP_VpBinSize(0.25, 0.3, 0.10, 0), 0.25) &&
         near(SVP_VpBinSize(0.01, 3.0, 0.10, 7), 0.07) && near(SVP_VpBinSize(0.00001, 0.0012, 0.10, 0), 0.00012, 1e-12) &&
         near(SVP_VpBinSize(0.01, 0.0, 0.10, 0), 0.01) && near(SVP_VpBinSize(0.05, 0.37, 0.10, 0), 0.05),
         "V07 row height = a whole number of ticks: 0.30 (XAU, ATR 3), 0.25 when one tick is larger, 7 ticks when fixed, 0.00012 on 5 digits, never below one tick");
   {
      std::vector<MqlRates> rb = randomBars(96, 7u, 2011.37, 1.2);
      MqlArray<MqlRates> a; toArray(rb, a);
      SSvpProfile x; SVP_VpBuild(a, 96, T0, T0 + 86400, 0.07, SVP_VP_DAILY, p, x);
      bool grid = x.valid;
      for(int b = 0; b <= x.bin_count && grid; b++)
      {
         const double edge = x.origin + b * x.bin_size;
         if(std::fabs(edge / 0.01 - std::round(edge / 0.01)) > 1e-6) grid = false;
      }
      check(grid && near(x.bin_size, 0.07) && std::fabs(x.origin / 0.07 - std::round(x.origin / 0.07)) < 1e-6,
            "V08 every row boundary of a 7-tick profile is on the tick grid and on the fixed 0.07 lattice", vpText(x));
      // the histogram is capped: rows double until the range fits
      SSvpProfile big; SVP_VpBuild(a, 96, T0, T0 + 86400, 0.01, SVP_VP_DAILY, p, big);
      why = "";
      check(big.valid && big.bin_count <= SVP_VP_MAX_BINS && big.bin_size > 0.01 &&
            std::fabs(std::log2(big.bin_size / 0.01) - std::round(std::log2(big.bin_size / 0.01))) < 1e-9 && SVP_VpValidate(big, why),
            "V09 one-tick rows over a range that needs more than 600 of them: the row doubles (still a tick multiple), the profile stays valid",
            vpText(big));
   }
#ifdef SMCVP_WITH_LEGACY_VP
   // --- parity with the profile the existing indicator displays
   {
      int compared = 0, rows_differ = 0, rule_differs = 0, tie_free = 0, tie_free_differ = 0, with_tie = 0, unexplained = 0;
      double worst_rows = 0.0;
      std::string first_bad;
      for(unsigned seed = 1; seed <= 40; seed++)
      {
         const int n = 20 + (int)(seed * 7 % 180);
         std::vector<MqlRates> rb = randomBars(n, seed, 1900.0 + seed * 13.7, 0.4 + 0.1 * (seed % 9));
         if(seed % 5 == 0) rb[(size_t)(n / 2)].tick_volume = 0;             // a bar without volume is skipped by both
         MqlArray<MqlRates> a; toArray(rb, a);
         const double bins[3] = {0.05, 0.30, 1.00};
         const double fracs[3] = {0.70, 0.68, 0.80};
         for(int k = 0; k < 3; k++)
         {
            SSvpParams q = p; q.vp_value_fraction = fracs[k];
            SSvpProfile mine; const bool ok_mine = SVP_VpBuild(a, n, rb[0].time, rb[(size_t)(n - 1)].time + 900, bins[k], SVP_VP_RANGE, q, mine);
            CVolumeProfile legacy; const bool ok_leg = legacy.Build(a, 0, n, bins[k], fracs[k], false);
            SVolumeProfileResult lr = legacy.Result();
            // ours doubles the row when the range needs more than 600 of them; the
            // legacy class keeps the row (up to 2048) or refuses: a different resolution
            // by design, so those are not comparable and are not counted
            if(mine.valid && mine.bin_size > bins[k] + 1e-12) continue;
            compared++;
            if(ok_mine != ok_leg || !ok_mine) { rows_differ++; continue; }
            // 1. the histogram itself
            bool rows = near(mine.total_volume, lr.total_tick_volume, 1e-9) && mine.bin_count == lr.bin_count;
            for(int b = 0; b < mine.bin_count && rows; b++) if(!near(mine.bins[b], legacy.BinVolume(b), 1e-9)) rows = false;
            if(!rows) { rows_differ++; continue; }
            // 2. the legacy RULE applied to OUR rows: the lowest of the heaviest rows, and on equal neighbours the lower side first
            int poc = 0;
            for(int b = 1; b < mine.bin_count; b++) if(mine.bins[b] > mine.bins[poc]) poc = b;
            bool tie = false;
            for(int b = 0; b < mine.bin_count; b++) if(b != poc && mine.bins[b] == mine.bins[poc]) tie = true;
            int left = poc, right = poc; double included = mine.bins[poc];
            while(included / mine.total_volume + 1.0e-12 < fracs[k] && (left > 0 || right < mine.bin_count - 1))
            {
               const double lv = (left > 0 ? mine.bins[left - 1] : -1.0), rv = (right < mine.bin_count - 1 ? mine.bins[right + 1] : -1.0);
               if(lv == rv) tie = true;
               if(lv >= rv) { if(left > 0) { left--; included += mine.bins[left]; } else { right++; included += mine.bins[right]; } }
               else { right++; included += mine.bins[right]; }
            }
            const double rule_poc = mine.origin + (poc + 0.5) * mine.bin_size, rule_val = mine.origin + left * mine.bin_size, rule_vah = mine.origin + (right + 1) * mine.bin_size;
            if(!near(rule_poc, lr.poc, 1e-9) || !near(rule_val, lr.val, 1e-9) || !near(rule_vah, lr.vah, 1e-9)) rule_differs++;
            // 3. our levels: identical when nothing ties; where rows tie, the POC is the centre of the tied run instead of its lowest row
            const bool same_levels = near(mine.poc, lr.poc, 1e-9) && near(mine.vah, lr.vah, 1e-9) && near(mine.val, lr.val, 1e-9);
            if(!tie) { tie_free++; if(!same_levels) { tie_free_differ++; if(first_bad.empty()) first_bad = "seed " + std::to_string(seed) + " row " + num(bins[k]) + ": " + vpText(mine) + " vs POC " + num(lr.poc, 3) + " VAL " + num(lr.val, 3) + " VAH " + num(lr.vah, 3); } }
            else
            {
               with_tie++;
               worst_rows = std::max(worst_rows, std::fabs(mine.poc - lr.poc) / mine.bin_size);
               // the engine's POC must still be a heaviest row (or the centre of a run of them), never below the legacy one
               if(mine.poc + 1e-9 < lr.poc || mine.poc_volume != mine.bins[poc]) unexplained++;
            }
         }
      }
      check(compared >= 100 && rows_differ == 0 && rule_differs == 0 && tie_free >= 80 && tie_free_differ == 0 && unexplained == 0,
            "V10 PARITY with CVolumeProfile (QSMC_Stats.mqh, the profile nadir2 displays) on 100+ random profiles (rows 0.05 / 0.30 / 1.00, value area "
            "70 / 68 / 80%): EVERY row and the total identical on all of them; POC / VAH / VAL identical on every profile without an exact tie; where rows "
            "tie, the legacy levels are exactly its rule (lowest tied row, lower side first) applied to our rows",
            std::to_string(compared) + " compared, rows differ " + std::to_string(rows_differ) + ", legacy rule differs " + std::to_string(rule_differs) +
            ", tie-free " + std::to_string(tie_free) + " (differ " + std::to_string(tie_free_differ) + "), with a tie " + std::to_string(with_tie) + ": " + first_bad);
      printf("INFO  volume parity: %d profiles compared with CVolumeProfile; rows identical on all; %d without a tie (levels identical), %d with an exact tie "
             "(POC up to %.1f rows above the legacy one, never below)\n", compared, tie_free, with_tie, worst_rows);
   }
#else
   check(false, "V10 PARITY with CVolumeProfile: the legacy class was not built into this unit");
#endif
   // --- what the volume IS
   {
      MqlArray<MqlRates> v; v.v = r.v;
      SSvpProfile t; SVP_VpBuild(v, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, p, t);
      const std::string basis = std::string(t.basis);
      check(!t.real_volume && basis.find("BROKER TICK VOLUME") != std::string::npos && basis.find("not centralized exchange volume") != std::string::npos &&
            basis.find("not bid/ask order flow") != std::string::npos,
            "V11 the profile names its source: BROKER TICK VOLUME, not centralized exchange volume, not bid/ask order flow");
      SSvpParams q = p; q.vp_use_real_volume = true;
      v.v[0].real_volume = 5; v.v[1].real_volume = 5; v.v[2].real_volume = 900;        // one bar has none
      SVP_VpBuild(v, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, q, t);
      const bool fallback = (!t.real_volume && near(t.poc, 101.5) && std::string(t.reason).find("tick volume used") != std::string::npos);
      v.v[3].real_volume = 50;
      SVP_VpBuild(v, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, q, t);
      // real volumes 5 | 5 | 900 | 50 -> rows 1.67 | 6.67 | 301.67 | 300 | 350: the POC moves to 104.5
      check(fallback && t.real_volume && std::string(t.basis).find("REAL volume") != std::string::npos && near(t.poc, 104.5) && near(t.total_volume, 960),
            "V12 real volume is used only when requested AND present on EVERY bar; one bar without it -> tick volume, and it says so",
            vpText(t));
   }
   // --- windows
   {
      const datetime wed = T0 + 2 * 86400 + 10 * 3600 + 1800;            // Wed 2026-01-07 10:30
      datetime f = 0, t = 0;
      SVP_SessionWindow(wed, p, f, t);
      const bool london = (f == T0 + 2 * 86400 + 7 * 3600 && t == T0 + 2 * 86400 + 13 * 3600);
      SVP_SessionWindow(T0 + 2 * 86400 + 3 * 3600, p, f, t);
      const bool asia = (f == T0 + 2 * 86400 && t == T0 + 2 * 86400 + 7 * 3600);
      SVP_SessionWindow(T0 + 2 * 86400 + 15 * 3600, p, f, t);
      const bool ny = (f == T0 + 2 * 86400 + 13 * 3600 && t == T0 + 2 * 86400 + 22 * 3600);
      SVP_SessionWindow(T0 + 2 * 86400 + 23 * 3600, p, f, t);
      const bool late = (f == T0 + 2 * 86400 + 22 * 3600 && t == T0 + 3 * 86400);
      check(london && asia && ny && late && SVP_DayStart(wed) == T0 + 2 * 86400 && SVP_WeekStart(wed) == T0 &&
            SVP_WeekStart(T0 + 6 * 86400 + 86399) == T0 && SVP_WeekStart(T0 + 7 * 86400) == T0 + 7 * 86400,
            "V13 windows: day = 00:00-24:00, week starts Monday, sessions 00-07 / 07-13 / 13-22 / 22-24 server time");
      bool every_hour = true;
      for(int a0 = 0; a0 < 24 && every_hour; a0 += 5)
         for(int h = 0; h < 24 && every_hour; h++)
         {
            SSvpParams q = p; q.sess_asia_start = a0; q.sess_london_start = a0 + 3; q.sess_ny_start = a0 + 9; q.sess_ny_end = a0 + 20;
            SVP_SanitizeParams(q);
            const datetime x = T0 + 2 * 86400 + h * 3600 + 900;
            SVP_SessionWindow(x, q, f, t);
            if(!(f <= x && x < t && t - f <= 86400 && t > f)) every_hour = false;
         }
      check(every_hour, "V14 whatever session hours are typed in, every moment falls inside exactly one positive window of at most a day");
      // the previous period is found in the DATA: a weekend is skipped
      Gen g(T0 + 3 * 86400, 2000.0);                                      // Thursday
      g.run(96, 0.1); g.run(96, -0.1);                                    // Thursday, Friday
      g.t = T0 + 7 * 86400;                                               // Monday: Saturday and Sunday have no bars
      g.run(40, 0.1);
      MqlArray<MqlRates> a; toArray(g.b, a);
      datetime pf = 0, pt = 0;
      const bool ok = SVP_VpWindow(a, g.size(), SVP_VP_DAILY, 1, p, pf, pt);
      datetime wf = 0, wt = 0;
      const bool okw = SVP_VpWindow(a, g.size(), SVP_VP_WEEKLY, 1, p, wf, wt);
      datetime nf = 0, nt = 0;
      const bool none = SVP_VpWindow(a, g.size(), SVP_VP_WEEKLY, 2, p, nf, nt);
      check(ok && pf == T0 + 4 * 86400 && pt == T0 + 5 * 86400 && okw && wf == T0 && wt == T0 + 7 * 86400 && !none,
            "V15 on Monday the previous daily profile is FRIDAY's (the weekend has no bars), the previous week is found, a week that is not in the data is not invented");
   }
   // --- reference profile, cache
   {
      Gen g(T0, 2000.0);
      g.run(96, 0.1); g.run(10, -0.1);                                    // a full Monday, then 10 bars of Tuesday
      MqlArray<MqlRates> a; toArray(g.b, a);
      MqlArray<double> atr; SVP_ATR(a, g.size(), 14, atr);
      SVP_VpCacheReset();
      SSvpProfile ref; bool prev = false;
      const bool got = SVP_VpReference(a, g.size(), atr, p, ref, prev);
      check(got && prev && ref.from_time == T0 && ref.bars == 96 && g_svp_vp_builds == 2,
            "V16 a developing day with 10 bars (minimum 16) defers to the PREVIOUS complete day, and says so");
      const int builds0 = g_svp_vp_builds;
      SVP_VpReference(a, g.size(), atr, p, ref, prev);
      check(g_svp_vp_builds == builds0 && g_svp_vp_hits >= 2, "V17 the same request again is answered from the cache: nothing is rebuilt",
            "builds " + std::to_string(g_svp_vp_builds) + " hits " + std::to_string(g_svp_vp_hits));
      // new bars: the finished day stays cached, only the developing one is rebuilt, once per bar
      for(int k = 0; k < 20; k++) g.step(0.1);
      toArray(g.b, a); SVP_ATR(a, g.size(), 14, atr);
      SVP_VpCacheReset();
      int rebuilt_prev = 0;
      for(int n = 107; n <= g.size(); n++)
      {
         const int before = g_svp_vp_builds;
         SVP_VpReference(a, n, atr, p, ref, prev);
         SVP_VpReference(a, n, atr, p, ref, prev);
         const int built_now = g_svp_vp_builds - before;
         if(n == 107) { if(built_now != 2) rebuilt_prev += 100; }
         else if(prev && built_now != 1) rebuilt_prev++;                   // developing rebuilt, previous from cache
         else if(!prev && built_now != 1) rebuilt_prev++;
      }
      check(rebuilt_prev == 0 && !prev && ref.from_time == T0 + 86400 && ref.bars == 30,
            "V18 over 20 new bars the finished profile is built ONCE and the developing one once per closed bar; at 16 bars the developing day takes over",
            "anomalies " + std::to_string(rebuilt_prev) + " bars " + std::to_string(ref.bars));
      // the row height of a profile is fixed for its whole life
      double row0 = 0.0; bool fixed_row = true;
      for(int n = 120; n <= g.size(); n++)
      {
         SSvpProfile d; datetime f = 0, t = 0;
         SVP_VpWindow(a, n, SVP_VP_DAILY, 0, p, f, t);
         SVP_VpGet(a, n, atr, f, t, SVP_VP_DAILY, p, d);
         if(row0 == 0.0) row0 = d.bin_size; else if(!near(d.bin_size, row0, 1e-12)) fixed_row = false;
      }
      check(fixed_row && row0 > 0.0, "V19 a developing profile keeps one row height (set from the ATR when its window opened): rows do not wobble");
      // nothing after bar n-1 is read, even inside the window
      SSvpProfile part, cut;
      SVP_VpBuild(a, 110, T0 + 86400, T0 + 2 * 86400, 0.05, SVP_VP_DAILY, p, part);
      MqlArray<MqlRates> b; b.v.assign(a.v.begin(), a.v.begin() + 110);
      SVP_VpBuild(b, 110, T0 + 86400, T0 + 2 * 86400, 0.05, SVP_VP_DAILY, p, cut);
      bool same = part.valid && cut.valid && part.bars == 14 && near(part.poc, cut.poc) && near(part.total_volume, cut.total_volume);
      check(same, "V20 a profile built as of bar n ignores later bars of the same window (no look-ahead)");
      // explicit range
      SSvpParams q = p; q.vp_kind = SVP_VP_RANGE;
      SSvpProfile rg; bool pv = true;
      const bool no_range = SVP_VpReference(a, g.size(), atr, q, rg, pv);
      q.vp_range_from = T0 + 20 * 900; q.vp_range_to = T0 + 60 * 900;
      const bool with_range = SVP_VpReference(a, g.size(), atr, q, rg, pv);
      check(!no_range && with_range && rg.kind == SVP_VP_RANGE && rg.bars == 40 && !pv && rg.first_bar == T0 + 20 * 900,
            "V21 visible / selected range: exactly the bars of the window; with no window selected the profile is N/A, not guessed");
   }
   // --- no data: N/A, never a number
   {
      MqlArray<MqlRates> a; a.v = {vbar(T0, 100.0, 101.0, 0), vbar(T0 + 900, 100.5, 101.5, 0)};
      SSvpProfile x; const bool zero = SVP_VpBuild(a, 2, T0, T0 + 3600, 0.1, SVP_VP_RANGE, p, x);
      SSvpProfile y; const bool empty = SVP_VpBuild(a, 2, T0 + 86400, T0 + 2 * 86400, 0.1, SVP_VP_RANGE, p, y);
      SSvpProfile w; const bool badrow = SVP_VpBuild(a, 2, T0, T0 + 3600, 0.0, SVP_VP_RANGE, p, w);
      string t1, t2;
      SSvpVpContext c; SVP_VpContext(x, a, 2, 1.0, p, c);
      check(!zero && !empty && !badrow && !x.valid && x.poc == 0.0 && std::string(x.basis) == "N/A" && !SVP_VpValidate(x, t1) && !c.valid &&
            std::string(c.text) == "N/A" && SVP_VpVerdict(x, c, 100.0, 101.0, 1, 0.1, 2, t2) == 0 && std::string(t2) == "N/A (no volume profile)",
            "V22 zero volume / no bars / a zero row height: the profile is INVALID, POC / VAH / VAL stay empty, the context is N/A");
   }
   // --- validation catches a damaged profile
   {
      SSvpProfile bad = vp; bad.bins[3] = 999.0;
      string w1; const bool a1 = SVP_VpValidate(bad, w1);
      bad = vp; bad.val = 102.0;
      string w2; const bool a2 = SVP_VpValidate(bad, w2);
      bad = vp; bad.bins[0] = -1.0;
      string w3; const bool a3 = SVP_VpValidate(bad, w3);
      check(!a1 && !a2 && !a3, "V23 SVP_VpValidate rejects a profile whose rows do not sum, whose VAL is above the POC, or with a negative row",
            std::string(w1) + " / " + std::string(w2) + " / " + std::string(w3));
   }
   // --- HVN / LVN on a two-cluster profile
   {
      // rows of 1.0 from 100: volumes 20 60 100 60 20 5 5 30 90 40 10
      // 3-row smoothing: 40 60 73.3 60 28.3 10 13.3 41.7 53.3 46.7 25 -> peaks at rows 2 and 8, trough at row 5
      const long vols[11] = {20, 60, 100, 60, 20, 5, 5, 30, 90, 40, 10};
      MqlArray<MqlRates> a;
      for(int k = 0; k < 11; k++) a.v.push_back(vbar(T0 + k * 900, 100.25 + k, 100.75 + k, vols[k]));
      SSvpProfile x; SVP_VpBuild(a, 11, T0, T0 + 11 * 900, 1.0, SVP_VP_RANGE, p, x);
      const bool hv = (x.hvn_count == 1 && near(x.hvn[0], 108.5));
      const bool lv = (x.lvn_count == 1 && near(x.lvn[0], 105.5));
      why = "";
      check(x.valid && near(x.poc, 102.5) && hv && lv && SVP_VpValidate(x, why),
            "V24 two volume clusters: POC 102.5 in the heavier one, ONE HVN at 108.5 (the POC itself is not repeated as a node), ONE LVN in the thin area between",
            "hvn " + std::to_string(x.hvn_count) + (x.hvn_count ? " @" + num(x.hvn[0]) : "") + " lvn " + std::to_string(x.lvn_count) + (x.lvn_count ? " @" + num(x.lvn[0]) : ""));
      // --- context
      // value area of this profile: POC 100 -> 60(101) -> 60(103) -> 30? ... computed by the engine; use it as given
      const double vah = x.vah, val = x.val, poc = x.poc;
      auto ctx = [&](const std::vector<std::array<double, 4>> &tail, const double atr_now) {
         MqlArray<MqlRates> s;
         datetime t = T0 + 86400;
         for(const auto &q : tail)
         {
            MqlRates b{}; b.time = t; b.open = q[0]; b.high = q[1]; b.low = q[2]; b.close = q[3]; b.tick_volume = 100; s.v.push_back(b); t += 900;
         }
         SSvpVpContext c; SVP_VpContext(x, s, (int)s.v.size(), atr_now, p, c);
         return c;
      };
      typedef std::array<double, 4> B;
      // came from inside value, traded the VAH, closed back inside -> rejection, supports shorts
      SSvpVpContext c1 = ctx({B{vah - 1.6, vah - 1.2, vah - 1.8, vah - 1.5}, B{vah - 1.5, vah - 1.0, vah - 1.7, vah - 1.2}, B{vah - 1.2, vah + 0.3, vah - 1.3, vah - 0.4},
                              B{vah - 0.4, vah + 0.2, vah - 1.2, vah - 1.0}, B{vah - 1.0, vah - 0.8, vah - 1.6, vah - 1.4}}, 1.0);
      SSvpVpContext c2 = ctx({B{val + 1.6, val + 1.8, val + 1.2, val + 1.5}, B{val + 1.5, val + 1.7, val + 1.0, val + 1.2}, B{val + 1.2, val + 1.3, val - 0.3, val + 0.4},
                              B{val + 0.4, val + 1.2, val - 0.2, val + 1.0}, B{val + 1.0, val + 1.6, val + 0.8, val + 1.4}}, 1.0);
      check(c1.valid && c1.state == SVP_VPC_VAH_REJECTION && c1.support == -1 && near(c1.level, vah) &&
            c2.valid && c2.state == SVP_VPC_VAL_REJECTION && c2.support == 1 && near(c2.level, val),
            "V25 context: price from inside value trades the VAH and closes back inside = VAH rejection (supports shorts); the mirror at the VAL supports longs",
            std::string(c1.text) + " / " + std::string(c2.text));
      SSvpVpContext c3 = ctx({B{vah + 0.5, vah + 0.9, vah + 0.4, vah + 0.8}, B{vah + 0.8, vah + 1.3, vah + 0.7, vah + 1.2}, B{vah + 1.2, vah + 1.6, vah + 1.1, vah + 1.5},
                              B{vah + 1.5, vah + 1.9, vah + 1.4, vah + 1.8}, B{vah + 1.8, vah + 2.3, vah + 1.7, vah + 2.2}}, 1.0);
      SSvpVpContext c4 = ctx({B{val - 0.5, val - 0.4, val - 0.9, val - 0.8}, B{val - 0.8, val - 0.7, val - 1.3, val - 1.2}, B{val - 1.2, val - 1.1, val - 1.6, val - 1.5},
                              B{val - 1.5, val - 1.4, val - 1.9, val - 1.8}, B{val - 1.8, val - 1.7, val - 2.3, val - 2.2}}, 1.0);
      check(c3.state == SVP_VPC_VAH_ACCEPTANCE && c3.support == 1 && c3.location == 1 && c4.state == SVP_VPC_VAL_ACCEPTANCE && c4.support == -1 && c4.location == -1,
            "V26 context: three closes above the VAH = acceptance above value (supports longs); below the VAL supports shorts",
            std::string(c3.text) + " / " + std::string(c4.text));
      SSvpVpContext c5 = ctx({B{poc, poc + 0.1, poc - 0.1, poc + 0.05}, B{poc + 0.05, poc + 0.1, poc - 0.1, poc}, B{poc, poc + 0.1, poc - 0.1, poc - 0.05},
                              B{poc - 0.05, poc + 0.1, poc - 0.1, poc + 0.02}, B{poc + 0.02, poc + 0.1, poc - 0.1, poc}}, 1.0);
      check(c5.state == SVP_VPC_POC_ACCEPTANCE && c5.support == 0,
            "V27 context: closes sitting on the POC = balance; it supports NEITHER side", std::string(c5.text));
      // --- the verdict
      string t;
      const int opposing = SVP_VpVerdict(x, c1, poc - 0.5, poc + 0.5, 1, 0.3, 2, t);
      const std::string opp_text = std::string(t);
      const int supportive = SVP_VpVerdict(x, c5, poc - 0.5, poc + 0.5, 1, 0.3, 2, t);
      const std::string sup_text = std::string(t);
      SSvpVpContext none; none.valid = true; none.state = SVP_VPC_NONE; none.support = 0; none.location = 0; none.level = 0; none.text = "no volume-profile reaction";
      const int neutral = SVP_VpVerdict(x, none, 105.2, 105.8, 1, 0.1, 2, t);
      const std::string neu_text = std::string(t);
      check(opposing == -1 && opp_text.find("OPPOSING") == 0 && supportive == 1 && sup_text.find("POC") != std::string::npos &&
            neutral == 0 && neu_text.find("NEUTRAL") == 0,
            "V28 verdict: a zone sitting on the POC is supportive; an opposing reaction WINS over that confluence; a zone in thin volume with no reaction is neutral",
            opp_text + " / " + sup_text + " / " + neu_text);
   }
   // --- rows that tie: no preferred side
   {
      // A 100.00-101.99 x300 -> rows 0,1 get 150 each     B 102.00-102.99 x10 -> row 2     C 103.00-103.99 x40 -> row 3
      // rows: 150 | 150 | 10 | 40   total 350.  The two heaviest rows are equal.
      MqlArray<MqlRates> a;
      a.v = {vbar(T0, 100.0, 101.99, 300), vbar(T0 + 900, 102.0, 102.99, 10), vbar(T0 + 1800, 103.0, 103.99, 40)};
      SSvpProfile x; SVP_VpBuild(a, 3, T0, T0 + 3600, 1.0, SVP_VP_RANGE, p, x);
      why = "";
      const bool one = (x.valid && near(x.poc, 101.0) && x.poc_lo_bin == 0 && x.poc_hi_bin == 1 && near(x.val, 100.0) && near(x.vah, 102.0) &&
                        near(x.va_fraction, 300.0 / 350.0, 1e-12) && SVP_VpValidate(x, why));
      // two separate heaviest rows: 100 | 20 | 100 | 60 -> the one nearer the centre of the volume (row 2: the 60 sits above it) is the POC
      MqlArray<MqlRates> b2;
      b2.v = {vbar(T0, 100.0, 100.99, 100), vbar(T0 + 900, 101.0, 101.99, 20), vbar(T0 + 1800, 102.0, 102.99, 100), vbar(T0 + 2700, 103.0, 103.99, 60)};
      SSvpProfile y; SVP_VpBuild(b2, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, p, y);
      // ...and with the 60 below instead: 60 | 100 | 20 | 100 -> row 1
      MqlArray<MqlRates> b3;
      b3.v = {vbar(T0, 100.0, 100.99, 60), vbar(T0 + 900, 101.0, 101.99, 100), vbar(T0 + 1800, 102.0, 102.99, 20), vbar(T0 + 2700, 103.0, 103.99, 100)};
      SSvpProfile z; SVP_VpBuild(b3, 4, T0, T0 + 3600, 1.0, SVP_VP_RANGE, p, z);
      check(one && y.valid && near(y.poc, 102.5) && z.valid && near(z.poc, 101.5),
            "V29 rows that tie for the maximum: two ADJACENT equal rows are one point of control at the centre of the run (101.00, not the lower row's "
            "100.50), and the value area starts from the whole run; two SEPARATE equal rows: the one nearer the centre of the volume wins, whichever "
            "side that is", vpText(x) + " / " + vpText(y) + " / " + vpText(z));
   }
   // --- a reflected series on the reflected row lattice gives the reflected profile, for any mirror line and any row height
   {
      int compared = 0, bad = 0, plateaus = 0, nodes = 0;
      std::string first_bad;
      for(unsigned seed = 1; seed <= 40; seed++)
      {
         const int n = 20 + (int)(seed * 11 % 150);
         std::vector<MqlRates> rb = randomBars(n, seed + 100u, 1900.0 + seed * 7.3, 0.4 + 0.1 * (seed % 9));
         const double c = 4000.37 + 0.01 * (double)(seed * 37 % 500);             // an arbitrary mirror line on the tick grid
         std::vector<MqlRates> rm = mirrored(rb, c);
         MqlArray<MqlRates> a, m; toArray(rb, a); toArray(rm, m);
         const double rows[4] = {0.05, 0.07, 0.30, 1.00};
         for(int k = 0; k < 4; k++)
         {
            SSvpParams q = p; q.vp_grid_phase = 0.005;                             // half a tick: no traded price can sit on a row boundary
            SSvpParams qm = p; qm.vp_grid_phase = c - 0.005;                       // the same lattice, reflected
            SSvpProfile x, y;
            const bool ok1 = SVP_VpBuild(a, n, rb[0].time, rb[(size_t)(n - 1)].time + 900, rows[k], SVP_VP_RANGE, q, x);
            const bool ok2 = SVP_VpBuild(m, n, rb[0].time, rb[(size_t)(n - 1)].time + 900, rows[k], SVP_VP_RANGE, qm, y);
            compared++;
            bool same = (ok1 && ok2 && x.bin_count == y.bin_count && near(x.bin_size, y.bin_size, 1e-12) && near(x.total_volume, y.total_volume, 1e-9) &&
                         near(y.poc, c - x.poc, 1e-7) && near(y.val, c - x.vah, 1e-7) && near(y.vah, c - x.val, 1e-7) && near(x.va_fraction, y.va_fraction, 1e-12) &&
                         x.hvn_count == y.hvn_count && x.lvn_count == y.lvn_count);
            for(int b = 0; b < x.bin_count && same; b++) if(x.bins[b] != y.bins[x.bin_count - 1 - b]) same = false;      // bit for bit
            for(int i = 0; i < x.hvn_count && same; i++) if(!near(y.hvn[i], c - x.hvn[i], 1e-7)) same = false;
            for(int i = 0; i < x.lvn_count && same; i++) if(!near(y.lvn[i], c - x.lvn[i], 1e-7)) same = false;
            if(ok1 && x.poc_hi_bin > x.poc_lo_bin) plateaus++;
            if(ok1) nodes += x.hvn_count + x.lvn_count;
            if(!same) { bad++; if(first_bad.empty()) first_bad = "seed " + std::to_string(seed) + " row " + num(rows[k]) + ": " + vpText(x) + " vs mirrored " + vpText(y); }
         }
      }
      check(compared == 160 && bad == 0 && plateaus >= 5 && nodes >= 50,
            "V30 mirror symmetry of the profile itself: 160 random profiles reflected about an arbitrary line - every row bit-identical in reverse order, "
            "POC' = c - POC, VAL' = c - VAH, VAH' = c - VAL, every HVN / LVN reflected in the same order (" + std::to_string(plateaus) +
            " of them have a tied point of control, " + std::to_string(nodes) + " nodes)", std::to_string(bad) + " differ: " + first_bad);
   }
   // --- both edges of a narrow value area inside the look-back
   {
      SSvpProfile x; SVP_VpReset(x);
      x.valid = true; x.bin_size = 0.1; x.origin = 90.0; x.bin_count = 200; x.poc = 100.0; x.val = 99.0; x.vah = 101.0; x.total_volume = 1.0;
      typedef std::array<double, 4> B;
      auto ctx = [&](const std::vector<B> &tail) {
         MqlArray<MqlRates> sq;
         datetime t = T0 + 86400;
         for(const auto &q : tail) { MqlRates b{}; b.time = t; b.open = q[0]; b.high = q[1]; b.low = q[2]; b.close = q[3]; b.tick_volume = 100; sq.v.push_back(b); t += 900; }
         SSvpVpContext c; SVP_VpContext(x, sq, (int)sq.v.size(), 1.0, p, c);
         return c;
      };
      auto flip = [&](const std::vector<B> &tail) {                       // the same bars reflected about the POC
         std::vector<B> out;
         for(const auto &q : tail) out.push_back(B{200.0 - q[0], 200.0 - q[2], 200.0 - q[1], 200.0 - q[3]});
         return out;
      };
      // inside value throughout; the VAL is traded first, the VAH last; the close is back inside
      const std::vector<B> val_then_vah = {B{100.2, 100.4, 100.0, 100.3}, B{100.3, 100.5, 100.1, 100.2}, B{100.2, 100.3, 98.9, 99.6}, B{99.6, 100.6, 99.5, 100.5}, B{100.5, 101.1, 100.2, 100.4}};
      const std::vector<B> vah_then_val = flip(val_then_vah);
      // ONE bar trades both edges
      const std::vector<B> same_bar = {B{100.2, 100.4, 100.0, 100.3}, B{100.3, 100.5, 100.1, 100.2}, B{100.2, 100.4, 100.0, 100.3}, B{100.3, 100.5, 100.1, 100.2}, B{100.2, 101.1, 98.9, 100.3}};
      const SSvpVpContext c1 = ctx(val_then_vah), c2 = ctx(vah_then_val), c3 = ctx(same_bar), c4 = ctx(flip(same_bar));
      check(c1.state == SVP_VPC_VAH_REJECTION && c1.support == -1 && c2.state == SVP_VPC_VAL_REJECTION && c2.support == 1 &&
            c3.support == -c4.support && c3.state != SVP_VPC_VAH_REJECTION && c3.state != SVP_VPC_VAL_REJECTION && c3.state == c4.state,
            "V31 a narrow value area with BOTH edges traded inside the look-back: the edge traded LAST decides (VAL then VAH = VAH rejection, the "
            "reflected bars = VAL rejection); when one bar traded both, neither edge is claimed - there is no built-in preference for the short side",
            std::string(c1.text) + " / " + std::string(c2.text) + " / " + std::string(c3.text) + " / " + std::string(c4.text));
   }
   // --- a flat top is ONE node at its centre
   {
      // rows of 1.0 from 100: volumes 90 90 20 4 4 4 20 70 70 70 70 20 8
      // smoothed: 90 66.7 38 9.3 4 9.3 31.3 53.3 70 70 53.3 32.7 14 -> a flat top on rows 8-9 (70 >= 70% of 90), a single trough on row 4
      const long vols[13] = {90, 90, 20, 4, 4, 4, 20, 70, 70, 70, 70, 20, 8};
      MqlArray<MqlRates> a;
      for(int k = 0; k < 13; k++) a.v.push_back(vbar(T0 + k * 900, 100.25 + k, 100.75 + k, vols[k]));
      SSvpProfile x; SVP_VpBuild(a, 13, T0, T0 + 13 * 900, 1.0, SVP_VP_RANGE, p, x);
      why = "";
      check(x.valid && near(x.poc, 101.0) && x.hvn_count == 1 && near(x.hvn[0], 109.0) && x.lvn_count == 1 && near(x.lvn[0], 104.5) && SVP_VpValidate(x, why),
            "V32 a flat top of the smoothed histogram is ONE high-volume node at the centre of the flat run (109.00, between its two rows), not a node "
            "leaning to its lower end; the POC of two equal rows is 101.00; the trough between is one LVN",
            vpText(x) + " hvn " + std::to_string(x.hvn_count) + (x.hvn_count ? " @" + num(x.hvn[0]) : "") + " lvn " + std::to_string(x.lvn_count) + (x.lvn_count ? " @" + num(x.lvn[0]) : "") + " " + std::string(why));
   }
}

// ================================================================== unit: the decision
struct Snap
{
   int state = 0; bool ready = false, plan = false, tracked = false;
   double entry = 0, stop = 0, target = 0, rr = 0;
   int buy = 0, sell = 0, blocking = -1;
   std::string reason, anchor, type;
   std::string steps;
};

static Snap snap()
{
   Snap x;
   x.state = (int)g_svp.state; x.ready = g_svp.ready; x.plan = g_svp.plan_valid; x.tracked = g_svp.tracked;
   x.entry = g_svp.entry; x.stop = g_svp.stop; x.target = g_svp.target; x.rr = g_svp.rr;
   x.buy = g_svp_buy.progress; x.sell = g_svp_sell.progress;
   x.blocking = (g_svp.focus > 0 ? g_svp_buy.blocking : (g_svp.focus < 0 ? g_svp_sell.blocking : -1));
   x.reason = std::string(g_svp.reason); x.anchor = std::string(g_svp.anchor_id); x.type = std::string(g_svp.setup_type);
   for(int i = 0; i < SVP_MAX_STEPS; i++) x.steps += std::string(SVP_StatusText(g_svp.status[i])).substr(0, 2) + " ";
   return x;
}

static bool sameSnap(const Snap &a, const Snap &b, const double eps = 1e-9)
{
   return a.state == b.state && a.ready == b.ready && a.plan == b.plan && a.tracked == b.tracked && near(a.entry, b.entry, eps) &&
          near(a.stop, b.stop, eps) && near(a.target, b.target, eps) && a.buy == b.buy && a.sell == b.sell && a.steps == b.steps &&
          a.anchor == b.anchor && a.type == b.type;
}

// the invariants every decision must satisfy, whatever the data
static std::string decisionDefect(const SSvpParams &p)
{
   const std::string h = std::string(g_svp.headline);
   if(g_svp.state == SVP_DECISION_BUY && h != "BUY SETUP") return "headline/state mismatch";
   if(g_svp.state == SVP_DECISION_SELL && h != "SELL SETUP") return "headline/state mismatch";
   if(g_svp.state == SVP_DECISION_WAIT && h != "WAIT") return "headline/state mismatch";
   if(g_svp.state == SVP_DECISION_WAIT)
   {
      if(g_svp.plan_valid) return "WAIT with a valid-looking plan";
      return "";
   }
   const int d = (int)g_svp.state;
   if(!g_svp.ready || !g_svp.plan_valid || !g_svp.tracked || g_svp.focus != d || g_svp.direction != d) return "setup without ready/plan/tracked";
   for(int i = 0; i < SVP_MAX_STEPS; i++) if(g_svp.status[i] != SVP_STEP_PASS) return "setup with step " + std::string(SVP_StepName(i)) + " not PASS";
   if(!(g_svp.entry > 0.0) || !(g_svp.stop > 0.0) || !(g_svp.target > 0.0)) return "setup with an empty price";
   if(!(d * (g_svp.entry - g_svp.stop) > 0.0)) return "stop on the wrong side";
   if(!(d * (g_svp.target - g_svp.entry) > 0.0)) return "target on the wrong side";
   if(!near(g_svp.risk, d * (g_svp.entry - g_svp.stop), 1e-9) || !near(g_svp.reward, d * (g_svp.target - g_svp.entry), 1e-9)) return "risk/reward fields inconsistent";
   if(!near(g_svp.rr, g_svp.reward / g_svp.risk, 1e-9)) return "RR is not reward/risk";
   if(g_svp.rr + 1e-9 < p.min_rr) return "RR below the minimum";
   if(p.min_stop_distance > 0.0 && g_svp.risk + 1e-9 < p.min_stop_distance) return "stop inside the broker minimum";
   if(std::fabs(g_svp.stop / p.tick_size - std::round(g_svp.stop / p.tick_size)) > 1e-6) return "stop off the tick grid";
   if(std::string(g_svp.anchor_id).empty() || g_svp.origin_time <= 0 || std::string(g_svp.setup_type).empty()) return "setup without an identity";
   return "";
}

static void unitDecision()
{
   g_group = "decision";
   SSvpParams p; SVP_DefaultParams(p);
   const char *order[SVP_MAX_STEPS] = {"H4 BIAS", "H1 STRUCTURE", "M15 LIQUIDITY", "LIQUIDITY SWEEP", "DISPLACEMENT", "BOS/CHoCH", "OB/FVG",
                                       "VOLUME PROFILE", "ENTRY", "RISK/REWARD"};
   bool ordered = (SVP_MAX_STEPS == 10);
   for(int i = 0; i < SVP_MAX_STEPS; i++) if(std::string(SVP_StepName(i)) != order[i]) ordered = false;
   check(ordered, "D01 the pipeline has ten steps in the specified order: H4 bias -> H1 structure -> M15 liquidity -> sweep -> displacement -> "
                  "BOS/CHoCH -> OB/FVG -> volume profile -> entry -> risk/reward");
   check(SVP_Resolve(true, false) == SVP_DECISION_BUY && SVP_Resolve(false, true) == SVP_DECISION_SELL &&
         SVP_Resolve(false, false) == SVP_DECISION_WAIT && SVP_Resolve(true, true) == SVP_DECISION_WAIT,
         "D02 exactly one outcome: BUY only when the long side alone qualifies, SELL only when the short side alone does, WAIT otherwise - "
         "including when BOTH qualify (conflicting evidence)");
   Story st = makeStory(0); Tf tf; tf.build(st.bars);
   // --- the timeline
   std::string defect; int setups = 0, first_setup = -1;
   std::vector<Snap> line((size_t)tf.n15());
   for(int k = SVP_MIN_M15_BARS; k < tf.n15(); k++)
   {
      analyze(tf, k + 1, p);
      line[(size_t)k] = snap();
      const std::string dft = decisionDefect(p);
      if(!dft.empty() && defect.empty()) defect = "bar " + std::to_string(k) + ": " + dft;
      if(g_svp.state != SVP_DECISION_WAIT) { setups++; if(first_setup < 0) first_setup = k; }
   }
   check(defect.empty(), "D03 on every bar of the story (1094 decisions) the result is one of BUY SETUP / SELL SETUP / WAIT, a setup has all ten steps "
                         "PASS and a complete plan, and WAIT never carries a plan", defect);
   check(setups == 1 && first_setup == st.i_confirm,
         "D04 the story produces exactly ONE setup, on the bar that confirms the retest - not on the sweep, not on the displacement, not on the touch",
         std::to_string(setups) + " setups, first at " + std::to_string(first_setup));
   const Snap &sw = line[(size_t)st.i_sweep], &di = line[(size_t)st.i_disp], &to = line[(size_t)st.i_touch], &cf = line[(size_t)st.i_confirm];
   check(sw.state == 0 && sw.buy == 3 && sw.blocking == SVP_STEP_SWEEP && sw.reason.find("PENDING at LIQUIDITY SWEEP") != std::string::npos,
         "D05 sweep bar: WAIT - the wick through the lows is only SWEEP_DETECTED; step 4 is PENDING", sw.reason);
   check(di.state == 0 && di.buy == 8 && di.blocking == SVP_STEP_ENTRY && di.tracked && di.reason.find("awaiting a retest") != std::string::npos,
         "D06 displacement bar: WAIT - eight steps hold, the zone exists, but there is no entry until price returns to it", di.reason);
   check(to.state == 0 && !to.plan && to.tracked,
         "D07 touch bar: WAIT - price is inside the zone but has not closed back out (no entry on a wick touch)", to.reason);
   analyze(tf, st.i_confirm + 1, p);
   const double atr_c = g_svp_atr_m15.v[(size_t)st.i_confirm];
   const double exp_entry = st.bars[(size_t)st.i_confirm].close;
   const double exp_stop = std::floor(((st.L0 - 1.4) - 0.20 * atr_c) / 0.01 + 1e-9) * 0.01;
   check(cf.state == 1 && near(cf.entry, exp_entry) && near(cf.entry, st.L0 + 4.1),
         "D08 confirm bar: BUY SETUP, entry = the close of the confirming candle (" + num(exp_entry) + ")");
   check(near(cf.stop, exp_stop, 1e-6) && cf.stop < st.L0 - 1.4 && std::string(g_svp.stop_source).find("0.20 ATR") != std::string::npos,
         "D09 stop = the swept low " + num(st.L0 - 1.4) + " minus 0.20 ATR (" + num(0.20 * atr_c, 3) + "), rounded away from price to the tick: " + num(exp_stop),
         num(cf.stop) + " / " + std::string(g_svp.stop_source));
   {
      // the target must be a real level: one of the intact buy-side zones, the H1 swing high, the POC or the VAH
      bool real = false; std::string src = std::string(g_svp.target_source);
      for(const SSvpLiqZone &z : g_svp_liq.v) if(z.side == 1 && near(z.level, cf.target)) real = true;
      if(near(g_svp_h1.high_price, cf.target) || near(g_svp_profile.poc, cf.target) || near(g_svp_profile.vah, cf.target)) real = true;
      // and the nearest one that pays the minimum
      bool nearer = false;
      const double risk = cf.entry - cf.stop;
      for(const SSvpLiqZone &z : g_svp_liq.v)
         if(z.side == 1 && z.taken_index < 0 && z.level > cf.entry && (z.level - cf.entry) / risk >= p.min_rr && z.level < cf.target - 1e-9) nearer = true;
      check(real && !nearer && near(cf.rr, (cf.target - cf.entry) / (cf.entry - cf.stop), 1e-9) && cf.rr >= 2.0 && !src.empty(),
            "D10 target " + num(cf.target) + " is a REAL level (" + src + "), the nearest one paying at least 1:2; RR = reward / risk = 1:" + num(cf.rr));
   }
   // --- the mirror
   {
      Tf tm; tm.build(mirrored(st.bars, 4300.0));
      analyze(tm, st.i_confirm + 1, p);
      const bool at_confirm = (g_svp.state == SVP_DECISION_SELL && near(g_svp.entry, 4300.0 - cf.entry, 1e-6) && near(g_svp.stop, 4300.0 - cf.stop, 1e-6) &&
                               near(g_svp.target, 4300.0 - cf.target, 1e-6) && near(g_svp.rr, cf.rr, 1e-6));
      int diff = 0;
      for(int k = SVP_MIN_M15_BARS; k < tf.n15(); k++)
      {
         analyze(tm, k + 1, p);
         const Snap m = snap();
         const Snap &o = line[(size_t)k];
         if(m.state != -o.state || m.buy != o.sell || m.sell != o.buy || m.plan != o.plan || m.steps != o.steps) diff++;
      }
      check(at_confirm && diff == 0,
            "D11 the price-mirrored story gives SELL SETUP with mirrored entry / stop / target and the same RR, and on all 1094 bars the "
            "mirrored decision and step statuses (BUY and SELL treated by the same code)", std::to_string(diff) + " bars differ");
   }
   // --- timeframes that disagree
   {
      Tf tm; tm.build(mirrored(st.bars, 4300.0));
      SVP_Analyze(tm.h4, (int)tm.h4.v.size(), tm.h1, (int)tm.h1.v.size(), tf.m15, st.i_confirm + 1, p);
      check(g_svp.state == SVP_DECISION_WAIT && g_svp_h4.bias == -1 && g_svp_buy.status[SVP_STEP_H4] == SVP_STEP_FAIL && g_svp_buy.blocking == SVP_STEP_H4 &&
            g_svp_buy.progress == 0 && !g_svp.plan_valid,
            "D12 the same M15 sequence under a BEARISH H4 / H1: WAIT - the long is blocked at step 1 and nothing later can buy it back",
            std::string(g_svp.reason));
   }
   // --- risk / reward
   {
      SSvpParams q = p; q.min_rr = 20.0;
      analyze(tf, st.i_confirm + 1, q);
      const std::string rr_text = std::string(g_svp_buy.text[SVP_STEP_RR]);
      check(g_svp.state == SVP_DECISION_WAIT && !g_svp.plan_valid && g_svp_buy.status[SVP_STEP_RR] == SVP_STEP_FAIL && g_svp_buy.progress == 9 &&
            rr_text.find("best available R:R is 1:") != std::string::npos && rr_text.find("minimum 1:20.00") != std::string::npos,
            "D13 minimum RR 20: nine steps hold but no real level pays 1:20 -> WAIT, and the plan is withheld (never a far-away invented target)", rr_text);
      MqlArray<string> rows;
      const int nrows = SVV_DashboardRows(g_svp, "XAUUSD", q, "(DAILY, tick volume)", rows);
      bool na = (nrows == SVV_ROWS);
      for(int i = 0; i < nrows; i++)
      {
         const std::string row = std::string(rows[i]);
         if(row.find("STOP LOSS:") == 0 && row != "STOP LOSS: N/A") na = false;
         if(row.find("TAKE PROFIT:") == 0 && row != "TAKE PROFIT: N/A") na = false;
         if(row.find("RISK/REWARD:") == 0 && row != "RISK/REWARD: N/A") na = false;
         if(row.find("ENTRY:") == 0 && row.find("ENTRY: N/A") != 0) na = false;
         if(row.find("FINAL DECISION:") == 0 && row != "FINAL DECISION: WAIT") na = false;
      }
      check(na, "D14 ... and the dashboard shows ENTRY / STOP LOSS / TAKE PROFIT / RISK-REWARD as N/A with FINAL DECISION: WAIT");
      q.min_rr = 1.0;
      analyze(tf, st.i_confirm + 1, q);
      check(g_svp.state == SVP_DECISION_BUY && g_svp.target < cf.target - 1e-9 && g_svp.rr >= 1.0 && g_svp.rr < cf.rr && near(g_svp.stop, cf.stop),
            "D15 minimum RR 1: the target becomes the NEAREST real level that pays it (" + num(g_svp.target) + ", 1:" + num(g_svp.rr) + "); the stop does not move");
   }
   // --- the stop
   {
      SSvpParams q = p; q.min_stop_distance = 8.0;
      analyze(tf, st.i_confirm + 1, q);
      const bool widened = (std::string(g_svp_buy.stop_source).find("broker minimum") != std::string::npos && near(g_svp_buy.stop, cf.entry - 8.0, 1e-6) &&
                            near(g_svp_buy.risk, 8.0, 1e-6));
      const std::string dft = decisionDefect(q);
      check(widened && dft.empty() && (g_svp.state == SVP_DECISION_WAIT || g_svp.rr >= 2.0),
            "D16 a broker minimum stop distance of 8.00 (structural risk " + num(cf.entry - cf.stop) + "): the stop is WIDENED to it and the RR is recomputed on "
            "the wider risk -> " + std::string(g_svp.headline) + (g_svp.plan_valid ? " 1:" + num(g_svp.rr) : " (" + std::string(g_svp_buy.text[SVP_STEP_RR]) + ")"), dft);
      q = p; q.spread = 0.30;
      analyze(tf, st.i_confirm + 1, q);
      check(near(g_svp_buy.stop, cf.stop - 0.30, 1e-6), "D17 the spread is added to the stop buffer: 0.30 of spread moves the stop 0.30 further away");
      // rounding to the tick is always AWAY from price, and a value already on the grid does not move
      check(near(SVP_RoundTick(100.30, 0.25, -1), 100.25) && near(SVP_RoundTick(100.30, 0.25, 1), 100.50) &&
            near(SVP_RoundTick(100.50, 0.25, -1), 100.50) && near(SVP_RoundTick(100.50, 0.25, 1), 100.50) &&
            near(SVP_RoundTick(2116.84, 0.01, -1), 2116.84) && near(SVP_RoundTick(2116.84, 0.01, 1), 2116.84) &&
            near(SVP_RoundTick(1.058423, 0.00001, -1), 1.05842) && near(SVP_RoundTick(1.058423, 0.00001, 1), 1.05843),
            "D18 tick rounding: down for a long's stop, up for a short's, never moving a price that is already on the grid (0.25, 0.01 and 0.00001 ticks)");
      // the same candles x25 on a 0.25 tick (an index near 53,000): every 0.01 becomes exactly one tick
      {
         Tf tx; tx.build(scaled(st.bars, 25.0, 2));
         SSvpParams x = p; x.tick_size = 0.25; x.point = 0.25;
         analyze(tx, st.i_confirm + 1, x);
         const double st_long = g_svp.stop;
         const bool long_ok = (g_svp.state == SVP_DECISION_BUY && std::fabs(st_long / 0.25 - std::round(st_long / 0.25)) < 1e-9 &&
                               near(st_long, cf.stop * 25.0, 0.25 + 1e-9) && near(g_svp.entry, cf.entry * 25.0, 1e-6) && decisionDefect(x).empty());
         // a histogram has rows: a mirror image is only exact when the mirror line sits on a row boundary
         const double row = g_svp_profile.bin_size;
         const double centre = std::round(120000.0 / row) * row;
         Tf ty; ty.build(mirrored(scaled(st.bars, 25.0, 2), centre));
         analyze(ty, st.i_confirm + 1, x);
         const double st_short = g_svp.stop;
         check(long_ok && row > 0.0 && g_svp.state == SVP_DECISION_SELL && std::fabs(st_short / 0.25 - std::round(st_short / 0.25)) < 1e-9 &&
               near(st_short, centre - st_long, 1e-6) && decisionDefect(x).empty(),
               "D18b the story x25 on a 0.25 tick: BUY SETUP with the stop on the 0.25 grid (" + num(st_long) + "); its mirror: SELL SETUP, stop " + num(st_short),
               std::string(g_svp.headline) + " " + std::string(g_svp.reason));
      }
      q = p; q.sl_buffer_atr = 0.0;
      analyze(tf, st.i_confirm + 1, q);
      check(near(g_svp_buy.stop, st.L0 - 1.4, 1e-6), "D19 with no buffer the stop is exactly the structural level: the swept low " + num(st.L0 - 1.4));
   }
   // --- entry window, chase, a plan that has already resolved
   {
      Story win = makeStory(1); Tf tw; tw.build(win.bars);
      analyze(tw, win.i_confirm + 2, p);
      const std::string t1 = std::string(g_svp_buy.text[SVP_STEP_ENTRY]);
      check(g_svp.state == SVP_DECISION_WAIT && g_svp_buy.status[SVP_STEP_ENTRY] == SVP_STEP_FAIL && t1.find("ATR beyond the zone") != std::string::npos,
            "D20 one bar later price has run more than 1 ATR beyond the zone: WAIT - the setup is not chased", t1);
      Story loss = makeStory(2); Tf tl; tl.build(loss.bars);
      analyze(tl, loss.i_confirm + 2, p);
      const bool still = (g_svp.state == SVP_DECISION_BUY && near(g_svp.entry, cf.entry) && near(g_svp.stop, cf.stop) && near(g_svp.target, cf.target));
      analyze(tl, loss.i_confirm + 4, p);
      const std::string t3 = std::string(g_svp_buy.text[SVP_STEP_ENTRY]);
      check(still && g_svp.state == SVP_DECISION_WAIT && t3.find("entry window passed") != std::string::npos,
            "D21 while price stays near the zone the setup remains actionable with the SAME entry / stop / target; after 2 bars the entry window is over", t3);
      // a wick through the stop on the bar after the confirmation, closing back near the entry
      std::vector<MqlRates> wick(st.bars);
      MqlRates w = wick.back(); w.time += 900; w.open = cf.entry; w.high = cf.entry + 0.4; w.low = cf.stop - 0.3; w.close = cf.entry + 0.1;
      wick.push_back(w);
      Tf tk; tk.build(wick);
      analyze(tk, tk.n15(), p);
      const std::string t4 = std::string(g_svp_buy.text[SVP_STEP_RR]);
      check(g_svp.state == SVP_DECISION_WAIT && !g_svp.plan_valid && t4.find("has traded since the retest was confirmed") != std::string::npos,
            "D22 the stop level trades on the next bar (a wick, closing back at the entry): WAIT - a setup whose stop was already hit is never shown as valid", t4);
   }
   // --- volume profile is context: required, never sufficient
   {
      SSvpParams q = p; q.vp_required = false;
      analyze(tf, st.i_touch + 1, q);
      const bool opposing_blocks = (g_svp_buy.status[SVP_STEP_VOLUME] == SVP_STEP_FAIL && std::string(g_svp_buy.text[SVP_STEP_VOLUME]).find("OPPOSING") == 0);
      analyze(tf, st.i_touch + 1, p);
      check(opposing_blocks && g_svp_buy.status[SVP_STEP_VOLUME] == SVP_STEP_FAIL,
            "D23 an OPPOSING volume context (rejection at the VAH on the touch bar) blocks the long whether or not volume confirmation is required");
      std::vector<MqlRates> novol(st.bars);
      for(MqlRates &b : novol) b.tick_volume = 0;
      Tf tn; tn.build(novol);
      analyze(tn, st.i_confirm + 1, p);
      const std::string v1 = std::string(g_svp_buy.text[SVP_STEP_VOLUME]);
      const bool blocked = (g_svp.state == SVP_DECISION_WAIT && !g_svp.vp_valid && g_svp_buy.status[SVP_STEP_VOLUME] == SVP_STEP_FAIL && v1.find("N/A") == 0);
      MqlArray<string> rows;
      SVV_DashboardRows(g_svp, "XAUUSD", p, "N/A", rows);
      const bool na_rows = (std::string(rows[7]) == "POC: N/A" && std::string(rows[8]) == "VAH / VAL: N/A");
      analyze(tn, st.i_confirm + 1, q);
      check(blocked && na_rows && g_svp.state == SVP_DECISION_BUY && std::string(g_svp_buy.text[SVP_STEP_VOLUME]).find("N/A (not required") == 0,
            "D24 no volume on any bar: POC / VAH / VAL are N/A; with volume confirmation required the answer is WAIT, with it switched off the "
            "other nine steps decide and the row still says N/A", v1);
      // supportive volume alone is nothing: every bar where the profile supports longs but the sequence is incomplete is WAIT
      int supportive_only = 0, became_setup = 0;
      for(int k = SVP_MIN_M15_BARS; k < st.i_sweep; k++)
      {
         analyze(tf, k + 1, p);
         if(g_svp_vpc.valid && g_svp_vpc.support == 1) { supportive_only++; if(g_svp.state != SVP_DECISION_WAIT) became_setup++; }
      }
      check(supportive_only > 20 && became_setup == 0,
            "D25 on " + std::to_string(supportive_only) + " bars before the sweep the volume context supported longs - and the decision was WAIT every time "
            "(the profile is context, never a signal)");
   }
   // --- history that is missing or damaged: N/A, not a guess
   {
      MqlArray<MqlRates> few4; few4.v.assign(tf.h4.v.end() - 30, tf.h4.v.end());
      const bool ok = SVP_Analyze(few4, 30, tf.h1, (int)tf.h1.v.size(), tf.m15, st.i_confirm + 1, p);
      MqlArray<string> rows;
      const int nrows = SVV_DashboardRows(g_svp, "XAUUSD", p, "N/A", rows);
      int na = 0;
      for(int i = 2; i < nrows - 1; i++) if(std::string(rows[i]).find("N/A") != std::string::npos) na++;
      check(!ok && !g_svp.ready && g_svp.state == SVP_DECISION_WAIT && std::string(g_svp.reason).find("history not ready") != std::string::npos &&
            std::string(g_svp.reason).find("H4 ") != std::string::npos && na == 12 && std::string(rows[9]) == "FINAL DECISION: WAIT",
            "D26 too little H4 history: not ready - WAIT, the reason names the missing timeframe, and the 12 analysis rows of the dashboard read N/A",
            std::string(g_svp.reason) + " | N/A rows " + std::to_string(na));
      std::vector<MqlRates> bad(st.bars);
      bad[500].high = bad[500].low - 1.0;
      Tf tb; tb.build(bad);
      const bool ok2 = analyze(tb, st.i_confirm + 1, p);
      std::vector<MqlRates> dup(st.bars);
      dup[700].time = dup[699].time;
      MqlArray<MqlRates> d15; toArray(dup, d15);
      const bool ok3 = SVP_Analyze(tf.h4, (int)tf.h4.v.size(), tf.h1, (int)tf.h1.v.size(), d15, st.i_confirm + 1, p);
      std::vector<MqlRates> nan(st.bars);
      nan[900].close = std::nan("");
      MqlArray<MqlRates> n15; toArray(nan, n15);
      const bool ok4 = SVP_Analyze(tf.h4, (int)tf.h4.v.size(), tf.h1, (int)tf.h1.v.size(), n15, st.i_confirm + 1, p);
      check(!ok2 && !ok3 && !ok4 && !g_svp.ready && g_svp.state == SVP_DECISION_WAIT,
            "D27 a bar with high < low, a duplicated timestamp or a NaN price makes the series unusable: WAIT / N/A instead of an analysis built on garbage");
   }
   // --- no look-ahead
   {
      int diff = 0, checked = 0;
      for(int k = st.i_low1 - 40; k <= st.i_confirm; k++)
      {
         // (a) only the bars that had closed
         MqlArray<MqlRates> c15; c15.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + k + 1);
         MqlArray<MqlRates> c1, c4;
         const datetime closed_at = tf.m15.v[(size_t)k].time + 900;
         for(const MqlRates &b : tf.h1.v) if(b.time + 3600 <= closed_at) c1.v.push_back(b);
         for(const MqlRates &b : tf.h4.v) if(b.time + 14400 <= closed_at) c4.v.push_back(b);
         SVP_VpCacheReset();
         SVP_Analyze(c4, (int)c4.v.size(), c1, (int)c1.v.size(), c15, k + 1, p);
         const Snap a = snap();
         // (b) the whole future present in the arrays, and poisoned
         Tf poison = tf;
         for(size_t i = (size_t)k + 1; i < poison.m15.v.size(); i++)
         { MqlRates &b = poison.m15.v[i]; b.open *= 3.0; b.high *= 5.0; b.low *= 0.2; b.close *= 3.0; b.tick_volume = 99999999; }
         for(MqlRates &b : poison.h1.v) if(b.time + 3600 > closed_at) { b.open *= 3.0; b.high *= 5.0; b.low *= 0.2; b.close *= 3.0; }
         for(MqlRates &b : poison.h4.v) if(b.time + 14400 > closed_at) { b.open *= 3.0; b.high *= 5.0; b.low *= 0.2; b.close *= 3.0; }
         SVP_VpCacheReset();
         analyze(poison, k + 1, p);
         const Snap b = snap();
         checked++;
         if(!sameSnap(a, b) || a.reason != b.reason) diff++;
      }
      check(checked > 50 && diff == 0,
            "D28 NO LOOK-AHEAD: on " + std::to_string(checked) + " bars the decision from arrays that hold ONLY closed bars equals the decision from arrays that also "
            "hold the (poisoned) future M15 bars and the still-forming H1 / H4 bars", std::to_string(diff) + " differ");
   }
   // --- stateless and repeatable
   {
      SVP_VpCacheReset();
      int diff = 0;
      for(int k = tf.n15() - 1; k >= st.i_low1 - 10; k--)            // backwards, cache warm from "later" bars
      {
         analyze(tf, k + 1, p);
         if(!sameSnap(snap(), line[(size_t)k]) || snap().reason != line[(size_t)k].reason) diff++;
      }
      check(diff == 0, "D29 the decision of a bar is a pure function of the closed bars: evaluated in reverse order with a warm profile cache it is identical "
                       "to the forward pass", std::to_string(diff) + " differ");
      // the start of the look-back window does not matter
      int wdiff = 0;
      for(int k = st.i_low1; k <= st.i_confirm; k++)
      {
         const int cut = 320;                                     // drop the first 320 M15 bars (80 H1, 20 H4)
         Tf part;
         std::vector<MqlRates> sub(st.bars.begin() + cut, st.bars.begin() + k + 1);
         part.build(sub);
         SVP_VpCacheReset();
         analyze(part, part.n15(), p);
         const Snap a = snap();
         const Snap &b = line[(size_t)k];
         if(a.state != b.state || a.buy != b.buy || a.sell != b.sell || !near(a.entry, b.entry) || !near(a.stop, b.stop) || !near(a.target, b.target)) wdiff++;
      }
      check(wdiff == 0, "D30 dropping the oldest 320 bars of history changes no decision and no price of the plan (a sliding window is safe)",
            std::to_string(wdiff) + " differ");
   }
   // --- another instrument scale
   {
      const double k = 0.001;                                     // 2120.00 -> 2.12000: every 0.01 becomes exactly one 0.00001 tick
      Tf ts; ts.build(scaled(st.bars, k, 5));
      SSvpParams q = p; q.tick_size = 0.00001; q.point = 0.00001; q.digits = 5;
      int diff = 0;
      for(int b = st.i_low1; b <= st.i_confirm; b++)
      {
         analyze(ts, b + 1, q);
         if((int)g_svp.state != line[(size_t)b].state || g_svp_buy.progress != line[(size_t)b].buy) diff++;
      }
      analyze(ts, st.i_confirm + 1, q);
      const std::string dft = decisionDefect(q);
      check(diff == 0 && g_svp.state == SVP_DECISION_BUY && dft.empty() && near(g_svp.entry, cf.entry * k, 2e-5) && near(g_svp.stop, cf.stop * k, 2e-5) &&
            near(g_svp.target, cf.target * k, 2e-5),
            "D31 the same candles on a 5-digit scale (2.12000, tick 0.00001): the same decisions, the plan scales with the prices - nothing is "
            "hard-wired to gold", dft + " diff " + std::to_string(diff) + " E " + num(g_svp.entry, 5) + " SL " + num(g_svp.stop, 5) + " TP " + num(g_svp.target, 5));
   }
   // --- targets
   {
      double pick = 0.0, best = 0.0;
      const double levels[5] = {2135.0, 2128.0, 2150.0, 2131.9, 2140.0};       // entry 2120, risk 6 -> 2R is 2132
      for(double l : levels) SVP_ConsiderTarget(1, 2120.0, 6.0, 2.0, l, pick, best);
      double pick2 = 0.0, best2 = 0.0;
      for(int i = 4; i >= 0; i--) SVP_ConsiderTarget(1, 2120.0, 6.0, 2.0, levels[i], pick2, best2);
      double pick3 = 0.0, best3 = 0.0;
      SVP_ConsiderTarget(1, 2120.0, 6.0, 2.0, 2110.0, pick3, best3);            // on the wrong side
      SVP_ConsiderTarget(1, 2120.0, 6.0, 2.0, 2125.0, pick3, best3);            // too near
      double pick4 = 0.0, best4 = 0.0;
      SVP_ConsiderTarget(-1, 2120.0, 6.0, 2.0, 2105.0, pick4, best4);
      SVP_ConsiderTarget(-1, 2120.0, 6.0, 2.0, 2108.0, pick4, best4);
      SVP_ConsiderTarget(-1, 2120.0, 6.0, 2.0, 2130.0, pick4, best4);
      check(near(pick, 2135.0) && near(pick2, 2135.0) && near(best, 5.0) && pick3 == 0.0 && near(best3, 5.0 / 6.0) && near(pick4, 2108.0),
            "D32 target choice: the nearest level paying at least the minimum (2135 of 2128 / 2131.9 / 2135 / 2140 / 2150), in any order; a level on the "
            "wrong side or too near is never taken; the same rule for a short");
   }
}

// ================================================================== unit: signal lifecycle
static SSvvStyle styleDefault() { SSvvStyle st; SVV_DefaultStyle(st); return st; }

static void sessionReset()
{
   SVV_ResetSignals(); SVP_VpCacheReset(); SVP_DecisionReset(g_svp);
   chartsim::resetAll(); g_svv_alerts = 0;
}

// one closed bar, exactly as the host does it
static bool barPass(const Tf &tf, const int n, const SSvpParams &p, const SSvvStyle &style, const bool announce)
{
   const bool ready = analyze(tf, n, p);
   if(ready)
   {
      SVV_UpdateSignals(tf.m15, n, "XAUUSD", (int)PERIOD_M15, style, announce);
      SVV_AlignDecision("XAUUSD", (int)PERIOD_M15, p);
      string message;
      while(SVV_NextAnnouncement(message)) Alert(message);      // the host delivers what the module queued
   }
   return ready;
}

static int confirmedRecords()
{
   int n = 0;
   for(int i = 0; i < QSR_CAPACITY; i++) if(g_qsr[i].used && g_qsr[i].entry > 0.0) n++;
   return n;
}

static int recordWithPlan()
{
   for(int i = 0; i < QSR_CAPACITY; i++) if(g_qsr[i].used && g_qsr[i].entry > 0.0) return i;
   return -1;
}

static int recordByOrigin(const datetime origin, const int direction)
{
   for(int i = 0; i < QSR_CAPACITY; i++) if(g_qsr[i].used && g_qsr[i].origin_time == origin && g_qsr[i].direction == direction) return i;
   return -1;
}

// the story, then a second, later setup of the same kind (a new sweep of new lows)
static Story makeDoubleStory(int &second_sweep, int &second_confirm)
{
   Story st = makeStory(1);
   Gen g(st.bars.back().time + 900, st.bars.back().close);
   g.zig(4, 5, -0.9, 3, 0.5);
   g.run(5, -0.9);
   const double L0 = g.px;
   g.vol = 3000;
   g.run(3, 0.5);
   g.step(-0.5); g.step(-0.5); g.step(-0.45);
   g.run(4, 0.5);
   g.step(-0.5); g.step(-0.45);
   g.bar(g.px, L0 + 1.2, L0 - 1.4, L0 + 0.6);
   second_sweep = (int)st.bars.size() + g.size() - 1;
   g.bar(L0 + 0.6, L0 + 3.7, L0 + 0.5, L0 + 3.6);
   g.bar(L0 + 3.6, L0 + 4.5, L0 + 3.3, L0 + 4.3);
   g.vol = 1000;
   g.bar(L0 + 4.3, L0 + 4.4, L0 + 3.0, L0 + 3.5);
   g.bar(L0 + 3.5, L0 + 4.3, L0 + 3.1, L0 + 4.1);
   second_confirm = (int)st.bars.size() + g.size() - 1;
   g.zig(8, 5, 0.9, 3, -0.5);
   st.bars.insert(st.bars.end(), g.b.begin(), g.b.end());
   st.i_end = (int)st.bars.size() - 1;
   return st;
}

static int boxOverlaps(const std::string &prefix);
static std::string objectDigest(const std::string &prefix);
static int captionCollisions(const std::vector<datetime> &times, const int n);
static int captionStrikes(const std::vector<datetime> &times, const int n, const bool column);
static int exactDuplicates(const std::string &prefix);
static std::vector<MqlRates> syntheticBars(unsigned seed, const int bars);
static std::string renderJson(const std::vector<MqlRates> &bars, const int first, const int last, const std::string &title);

static void unitSignal()
{
   g_group = "signal";
   SSvpParams p; SVP_DefaultParams(p);
   SSvvStyle style = styleDefault();
   // --- identity
   {
      const std::string a = std::string(SVV_SignalId(1, "SWEEP_MSS_RETEST", 1767571200)), b = std::string(SVV_SignalId(-1, "FAILED_BREAKOUT_RETEST", 1767571200));
      const std::string fam = std::string(QSR_Family("XAUUSD", 15, 1, "SWEEP_MSS_RETEST", "SSL@1"));
      const std::string key = std::string(QSR_Key(fam, 1767571200));
      check(a == "SBM1767571200" && b == "SSF1767571200" && fam.find("XAUUSD") != std::string::npos && fam.find("SWEEP_MSS_RETEST") != std::string::npos &&
            fam.find("SSL@1") != std::string::npos && key.find("1767571200") != std::string::npos &&
            key != std::string(QSR_Key(std::string(QSR_Family("XAUUSD", 15, -1, "SWEEP_MSS_RETEST", "SSL@1")), 1767571200)) &&
            key != std::string(QSR_Key(std::string(QSR_Family("EURUSD", 15, 1, "SWEEP_MSS_RETEST", "SSL@1")), 1767571200)) &&
            key != std::string(QSR_Key(std::string(QSR_Family("XAUUSD", 60, 1, "SWEEP_MSS_RETEST", "SSL@1")), 1767571200)) &&
            key != std::string(QSR_Key(fam, 1767572100)),
            "G01 a signal's identity = symbol | timeframe | direction | setup type | liquidity event | originating bar; the chart id (SBM<origin>) "
            "contains no drawing bar and no counter", a + " " + b + " " + key);
   }
   // --- the life of one setup: target reached
   {
      Story st = makeStory(1); Tf tf; tf.build(st.bars);
      sessionReset();
      std::string states; int rec = -1; int created_total = 0;
      int at_disp = -1, at_confirm = -1, at_next = -1, hit_bar = -1; std::string final_state, final_note;
      const datetime origin = st.bars[(size_t)st.i_sweep].time;
      for(int k = st.i_low1 - 40; k <= st.i_end; k++)
      {
         barPass(tf, k + 1, p, style, true);
         rec = recordByOrigin(origin, 1);
         const int stt = rec >= 0 ? (int)g_qsr[rec].state : 0;
         if(k == st.i_disp) at_disp = stt;
         if(k == st.i_confirm) at_confirm = stt;
         if(k == st.i_confirm + 1) at_next = stt;
         if(hit_bar < 0 && rec >= 0 && QSR_IsTerminal(g_qsr[rec].state)) { hit_bar = k; final_state = std::string(QSR_StateName(g_qsr[rec].state)); final_note = std::string(g_qsr[rec].note); }
      }
      created_total = g_qsr_created;
      int first_touch = -1;
      for(int k = st.i_confirm + 1; k <= st.i_end && first_touch < 0; k++) if(st.bars[(size_t)k].high >= 2135.20 - 1e-9) first_touch = k;
      check(at_disp == QSR_STATE_DETECTED && at_confirm == QSR_STATE_CONFIRMED && at_next == QSR_STATE_ACTIVE && final_state == "MITIGATED" &&
            hit_bar == first_touch && first_touch > 0 && final_note == "target traded",
            "G02 lifecycle (target reached): DETECTED on the displacement bar -> CONFIRMED on the retest confirmation -> ACTIVE the next bar -> "
            "MITIGATED on the first bar whose high trades the target", "states " + std::to_string(at_disp) + "/" + std::to_string(at_confirm) + "/" +
            std::to_string(at_next) + " final " + final_state + " at " + std::to_string(hit_bar) + " expected " + std::to_string(first_touch));
      check(confirmedRecords() == 1 && chartsim::C.alerts.size() == 1 && g_svv_alerts == 1 &&
            chartsim::C.alerts[0].find("BUY SETUP") != std::string::npos && chartsim::C.alerts[0].find("2122.60") != std::string::npos &&
            chartsim::C.alerts[0].find("2116.84") != std::string::npos && chartsim::C.alerts[0].find("2135.20") != std::string::npos,
            "G03 over " + std::to_string(st.i_end - st.i_low1 + 41) + " bars: ONE confirmed signal and ONE alert, carrying entry / SL / TP (" +
            std::to_string(created_total) + " registry records in all, the rest never confirmed)",
            std::to_string(confirmedRecords()) + " confirmed, " + std::to_string(chartsim::C.alerts.size()) + " alerts");
      // the plan in the registry is the one of the confirming bar
      rec = recordWithPlan();
      check(rec >= 0 && near(g_qsr[rec].entry, 2122.60) && near(g_qsr[rec].stop, 2116.84) && near(g_qsr[rec].target, 2135.20) &&
            g_svv_confirmed[rec] == st.bars[(size_t)st.i_confirm].time && g_qsr[rec].origin_time == origin,
            "G04 the record keeps the plan frozen at confirmation (2122.60 / 2116.84 / 2135.20), its confirmation bar and its originating bar (the sweep)");
   }
   // --- stop reached
   {
      Story st = makeStory(2); Tf tf; tf.build(st.bars);
      sessionReset();
      const datetime origin = st.bars[(size_t)st.i_sweep].time;
      int hit_bar = -1; std::string final_state, note; int setups_after = 0;
      for(int k = st.i_low1 - 40; k <= st.i_end; k++)
      {
         barPass(tf, k + 1, p, style, false);
         const int rec = recordByOrigin(origin, 1);
         if(hit_bar < 0 && rec >= 0 && QSR_IsTerminal(g_qsr[rec].state)) { hit_bar = k; final_state = std::string(QSR_StateName(g_qsr[rec].state)); note = std::string(g_qsr[rec].note); }
         if(hit_bar >= 0 && g_svp.state != SVP_DECISION_WAIT) setups_after++;
      }
      int first_touch = -1;
      for(int k = st.i_confirm + 1; k <= st.i_end && first_touch < 0; k++) if(st.bars[(size_t)k].low <= 2116.84 + 1e-9) first_touch = k;
      check(final_state == "INVALIDATED" && hit_bar == first_touch && note == "stop level traded" && setups_after == 0 && chartsim::C.alerts.empty(),
            "G05 lifecycle (stop reached): INVALIDATED on the first bar whose low trades the stop; no setup is shown afterwards; nothing is "
            "announced when alerts are off", final_state + " at " + std::to_string(hit_bar) + " expected " + std::to_string(first_touch));
   }
   // --- the same bar again and again
   {
      Story st = makeStory(0); Tf tf; tf.build(st.bars);
      sessionReset();
      for(int k = st.i_low1 - 10; k < st.i_confirm; k++) barPass(tf, k + 1, p, style, true);
      barPass(tf, st.i_confirm + 1, p, style, true);
      const int created0 = g_qsr_created, trans0 = g_qsr_transitions; const size_t alerts0 = chartsim::C.alerts.size();
      const int rec = recordWithPlan();
      const int state0 = rec >= 0 ? (int)g_qsr[rec].state : -1;
      for(int r = 0; r < 25; r++) barPass(tf, st.i_confirm + 1, p, style, true);
      check(rec >= 0 && g_qsr_created == created0 && g_qsr_transitions == trans0 && chartsim::C.alerts.size() == alerts0 && alerts0 == 1 &&
            (int)g_qsr[rec].state == state0 && state0 == QSR_STATE_CONFIRMED && g_svp.state == SVP_DECISION_BUY,
            "G06 the confirming bar evaluated 25 more times (re-init, refresh, timeframe change): no new record, no state change, no second alert");
   }
   // --- one plan while the setup stays actionable
   {
      Story st = makeStory(2); Tf tf; tf.build(st.bars);
      sessionReset();
      for(int k = st.i_low1 - 10; k <= st.i_confirm; k++) barPass(tf, k + 1, p, style, false);
      SSvpParams wide = p; wide.spread = 0.50;                      // the spread widened on the next bar
      analyze(tf, st.i_confirm + 2, wide);
      const double engine_stop = g_svp.stop; const bool engine_setup = (g_svp.state == SVP_DECISION_BUY);
      SVV_UpdateSignals(tf.m15, st.i_confirm + 2, "XAUUSD", (int)PERIOD_M15, style, false);
      SVV_AlignDecision("XAUUSD", (int)PERIOD_M15, wide);
      check(engine_setup && near(engine_stop, 2116.34) && g_svp.state == SVP_DECISION_BUY && near(g_svp.stop, 2116.84) && near(g_svp.entry, 2122.60) &&
            near(g_svp.target, 2135.20) && near(g_svp.rr, (2135.20 - 2122.60) / (2122.60 - 2116.84), 1e-9) && confirmedRecords() == 1,
            "G07 a bar later the spread is wider and the stateless engine would print another stop (2116.34): the operator still sees the plan "
            "frozen at confirmation (stop 2116.84) - one setup, one plan", "engine " + num(engine_stop) + " shown " + num(g_svp.stop));
      // the record is over but the engine still describes the setup: the decision shown is WAIT
      const int rec = recordWithPlan();
      QSR_SetState(rec, QSR_STATE_INVALIDATED, st.bars[(size_t)st.i_confirm + 1].time, "stop level traded");
      analyze(tf, st.i_confirm + 2, p);
      const bool engine_still = (g_svp.state == SVP_DECISION_BUY);
      SVV_AlignDecision("XAUUSD", (int)PERIOD_M15, p);
      MqlArray<string> rows; SVV_DashboardRows(g_svp, "XAUUSD", p, "x", rows);
      check(engine_still && g_svp.state == SVP_DECISION_WAIT && !g_svp.plan_valid && std::string(g_svp.reason).find("is over (INVALIDATED: stop level traded)") != std::string::npos &&
            std::string(rows[9]) == "FINAL DECISION: WAIT" && std::string(rows[11]) == "STOP LOSS: N/A",
            "G08 a setup whose record is INVALIDATED is never shown as a setup again: WAIT, plan N/A, and the reason says why", std::string(g_svp.reason));
   }
   // --- a candidate that never gets its retest
   {
      Story st = makeStory(0);
      std::vector<MqlRates> bars(st.bars.begin(), st.bars.begin() + st.i_fvg + 1);
      Gen g(bars.back().time + 900, bars.back().close);
      g.run(45, 0.8);                                                // price runs away and never comes back
      bars.insert(bars.end(), g.b.begin(), g.b.end());
      Tf tf; tf.build(bars);
      sessionReset();
      const datetime origin = st.bars[(size_t)st.i_sweep].time;
      bool was_detected = false; std::string end_state, note;
      for(int k = st.i_low1 - 10; k < tf.n15(); k++)
      {
         barPass(tf, k + 1, p, style, true);
         const int rec = recordByOrigin(origin, 1);
         if(rec >= 0 && g_qsr[rec].state == QSR_STATE_DETECTED) was_detected = true;
         if(rec >= 0) { end_state = std::string(QSR_StateName(g_qsr[rec].state)); note = std::string(g_qsr[rec].note); }
      }
      check(was_detected && end_state == "EXPIRED" && confirmedRecords() == 0 && chartsim::C.alerts.empty(),
            "G09 a candidate whose retest never comes (price runs away for 45 bars): DETECTED while the sweep is fresh, then EXPIRED once the engine "
            "stops reporting it - never confirmed, never announced",
            end_state + " (" + note + ")");
   }
   // --- stop and target inside one bar; an active signal that goes nowhere
   {
      Story st = makeStory(0);
      std::vector<MqlRates> bars(st.bars);
      MqlRates w = bars.back(); w.time += 900; w.open = 2122.6; w.high = 2136.0; w.low = 2116.0; w.close = 2125.0;
      bars.push_back(w);
      Tf tf; tf.build(bars);
      sessionReset();
      for(int k = st.i_low1 - 10; k < tf.n15(); k++) barPass(tf, k + 1, p, style, false);
      int rec = recordWithPlan();
      const bool both = (rec >= 0 && g_qsr[rec].state == QSR_STATE_INVALIDATED);
      std::vector<MqlRates> flat(st.bars);
      Gen g(flat.back().time + 900, flat.back().close);
      for(int i = 0; i < 30; i++) g.step((i % 2 == 0) ? 0.3 : -0.3, 0.1);
      flat.insert(flat.end(), g.b.begin(), g.b.end());
      Tf tq; tq.build(flat);
      SSvvStyle quick = style; quick.max_active_bars = 20;
      sessionReset();
      for(int k = st.i_low1 - 10; k < tq.n15(); k++) barPass(tq, k + 1, p, quick, false);
      rec = recordWithPlan();
      check(both && rec >= 0 && g_qsr[rec].state == QSR_STATE_EXPIRED && std::string(g_qsr[rec].note) == "older than 20 bars",
            "G10 a bar that trades BOTH the stop and the target cannot be ordered from OHLC: it counts as the stop (INVALIDATED); an active signal "
            "that reaches neither within the configured life EXPIRES", rec >= 0 ? std::string(QSR_StateName(g_qsr[rec].state)) + " " + std::string(g_qsr[rec].note) : "none");
   }
   // --- a later, separate setup is a new signal
   {
      int sweep2 = -1, confirm2 = -1;
      Story st = makeDoubleStory(sweep2, confirm2); Tf tf; tf.build(st.bars);
      sessionReset();
      std::vector<int> setup_bars;
      for(int k = st.i_low1 - 40; k <= st.i_end; k++)
      {
         barPass(tf, k + 1, p, style, true);
         if(g_svp.state != SVP_DECISION_WAIT) setup_bars.push_back(k);
      }
      const int a = recordByOrigin(st.bars[(size_t)st.i_sweep].time, 1), b = recordByOrigin(st.bars[(size_t)sweep2].time, 1);
      std::string where;
      for(int k : setup_bars) where += std::to_string(k) + " ";
      check(a >= 0 && b >= 0 && a != b && g_qsr[a].entry > 0.0 && g_qsr[b].entry > 0.0 && confirmedRecords() == 2 && chartsim::C.alerts.size() == 2 &&
            std::string(g_qsr[a].key) != std::string(g_qsr[b].key) &&
            std::string(SVV_SignalId(1, g_qsr[a].setup_type, g_qsr[a].origin_time)) != std::string(SVV_SignalId(1, g_qsr[b].setup_type, g_qsr[b].origin_time)),
            "G11 a NEW sweep of NEW lows after the first setup finished is a new signal: two identities, two alerts - and still one per setup",
            "setup bars: " + where + "| confirmed " + std::to_string(confirmedRecords()) + " alerts " + std::to_string(chartsim::C.alerts.size()) +
            " second sweep " + std::to_string(sweep2) + " confirm " + std::to_string(confirm2));
   }
   // --- two live signals of one side: one box per price area, the setup in play first
   {
      SSvpParams pp; SVP_DefaultParams(pp);
      SSvvStyle look = styleDefault();
      Story st = makeStory(1); Tf tf; tf.build(st.bars);
      sessionReset();
      SVC_Init("QSVP_", 0);
      SVC_SetLayer(SVC_LAYER_PRIMARY, true, 48); SVC_SetLayer(SVC_LAYER_SECONDARY, true, 40); SVC_SetLayer(SVC_LAYER_VOLUME, true, 24);
      SVC_SetLayer(SVC_LAYER_DETAIL, false, 48); SVC_SetLayer(SVC_LAYER_OPTIONAL, false, 48);
      const int n = 1200;
      MqlArray<MqlRates> view; view.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + n);
      const datetime now = view.v.back().time;
      auto draw = [&]() { SVC_Begin(); SVV_DrawSignals(view, n, pp, look); SVC_End(); };
      auto boxes = [&]() { return (int)chartsim::countType("QSVP_S", OBJ_RECTANGLE); };
      auto has = [&](const std::string &name) { return chartsim::find(name) != nullptr; };
      bool created = false;
      // A: a SELL setup in play since 20 bars, entry zone 2100-2102
      const datetime originA = now - 30 * 900, originB = now - 6 * 900;
      const int a = QSR_Upsert("XAUUSD", 15, -1, "SWEEP_MSS_RETEST", "BSL|1|2103.00", originA, now - 28 * 900, QSR_STATE_DETECTED, created);
      QSR_SetState(a, QSR_STATE_CONFIRMED, now - 20 * 900, "c"); QSR_SetState(a, QSR_STATE_ACTIVE, now - 19 * 900, "in play");
      QSR_SetPlan(a, 0, 0, 2099.50, 2103.40, 2090.00);
      g_svv_zone_lo[a] = 2100.00; g_svv_zone_hi[a] = 2102.00; g_svv_confirmed[a] = now - 20 * 900;
      // B: a NEWER SELL candidate whose zone 2099-2103 covers the same prices
      const int b = QSR_Upsert("XAUUSD", 15, -1, "FAILED_BREAKOUT_RETEST", "BSL|2|2103.50", originB, now - 4 * 900, QSR_STATE_DETECTED, created);
      g_svv_zone_lo[b] = 2099.00; g_svv_zone_hi[b] = 2103.00;
      const std::string idA = std::string(SVV_SignalId(-1, "SWEEP_MSS_RETEST", originA)), idB = std::string(SVV_SignalId(-1, "FAILED_BREAKOUT_RETEST", originB));
      draw();
      const bool step1 = (boxes() == 1 && has("QSVP_" + idA + "_ZONE") && has("QSVP_" + idA + "_E") && has("QSVP_" + idA + "_SL") && has("QSVP_" + idA + "_TP") &&
                          !has("QSVP_" + idB + "_ZONE") && !has("QSVP_" + idB + "_TAG") && g_svv_signals_hidden == 1 && boxOverlaps("QSVP_") == 0);
      const std::string seen1 = std::to_string(boxes()) + " box(es), hidden " + std::to_string(g_svv_signals_hidden);
      // the candidate confirms: both carry a plan, the newer one is shown, the older one waits off the chart
      QSR_SetState(b, QSR_STATE_CONFIRMED, now, "c"); QSR_SetPlan(b, 0, 0, 2098.60, 2104.10, 2086.00); g_svv_confirmed[b] = now;
      draw();
      const bool step2 = (boxes() == 1 && has("QSVP_" + idB + "_ZONE") && has("QSVP_" + idB + "_E") && !has("QSVP_" + idA + "_ZONE") && !has("QSVP_" + idA + "_E") &&
                          g_svv_signals_hidden == 1 && boxOverlaps("QSVP_") == 0 && chartsim::countType("QSVP_S", OBJ_TREND) == 3);
      // the newer one ends: the older setup, still in play, is back - nothing was lost
      QSR_SetState(b, QSR_STATE_ACTIVE, now, "in play"); QSR_SetState(b, QSR_STATE_INVALIDATED, now, "stop level traded");
      draw();
      const bool step3 = (boxes() == 1 && has("QSVP_" + idA + "_ZONE") && has("QSVP_" + idA + "_TP") && !has("QSVP_" + idB + "_ZONE") && g_svv_signals_hidden == 0);
      // a third candidate somewhere else (2110-2112) and a BUY candidate over the same prices as A: both are drawn
      const int c = QSR_Upsert("XAUUSD", 15, -1, "SWEEP_MSS_RETEST", "BSL|3|2113.00", now - 3 * 900, now - 2 * 900, QSR_STATE_DETECTED, created);
      g_svv_zone_lo[c] = 2110.00; g_svv_zone_hi[c] = 2112.00;
      const int d = QSR_Upsert("XAUUSD", 15, 1, "SWEEP_MSS_RETEST", "SSL|4|2099.00", now - 5 * 900, now - 2 * 900, QSR_STATE_DETECTED, created);
      g_svv_zone_lo[d] = 2100.50; g_svv_zone_hi[d] = 2101.50;
      look.live_signals = 4;
      draw();
      const bool step4 = (boxes() == 3 && boxOverlaps("QSVP_") == 0 && g_svv_signals_hidden == 0);
      // the order of the table must not matter: rebuild the same records in the opposite order
      const std::string picture = objectDigest("QSVP_");
      sessionReset(); SVC_Init("QSVP_", 0);
      SVC_SetLayer(SVC_LAYER_PRIMARY, true, 48); SVC_SetLayer(SVC_LAYER_SECONDARY, true, 40); SVC_SetLayer(SVC_LAYER_VOLUME, true, 24);
      SVC_SetLayer(SVC_LAYER_DETAIL, false, 48); SVC_SetLayer(SVC_LAYER_OPTIONAL, false, 48);
      const int d2 = QSR_Upsert("XAUUSD", 15, 1, "SWEEP_MSS_RETEST", "SSL|4|2099.00", now - 5 * 900, now - 2 * 900, QSR_STATE_DETECTED, created);
      g_svv_zone_lo[d2] = 2100.50; g_svv_zone_hi[d2] = 2101.50;
      const int c2 = QSR_Upsert("XAUUSD", 15, -1, "SWEEP_MSS_RETEST", "BSL|3|2113.00", now - 3 * 900, now - 2 * 900, QSR_STATE_DETECTED, created);
      g_svv_zone_lo[c2] = 2110.00; g_svv_zone_hi[c2] = 2112.00;
      const int b2 = QSR_Upsert("XAUUSD", 15, -1, "FAILED_BREAKOUT_RETEST", "BSL|2|2103.50", originB, now - 4 * 900, QSR_STATE_DETECTED, created);
      g_svv_zone_lo[b2] = 2099.00; g_svv_zone_hi[b2] = 2103.00;
      QSR_SetState(b2, QSR_STATE_CONFIRMED, now, "c"); QSR_SetPlan(b2, 0, 0, 2098.60, 2104.10, 2086.00); g_svv_confirmed[b2] = now;
      QSR_SetState(b2, QSR_STATE_ACTIVE, now, "in play"); QSR_SetState(b2, QSR_STATE_INVALIDATED, now, "stop level traded");
      const int a2 = QSR_Upsert("XAUUSD", 15, -1, "SWEEP_MSS_RETEST", "BSL|1|2103.00", originA, now - 28 * 900, QSR_STATE_DETECTED, created);
      QSR_SetState(a2, QSR_STATE_CONFIRMED, now - 20 * 900, "c"); QSR_SetState(a2, QSR_STATE_ACTIVE, now - 19 * 900, "in play");
      QSR_SetPlan(a2, 0, 0, 2099.50, 2103.40, 2090.00);
      g_svv_zone_lo[a2] = 2100.00; g_svv_zone_hi[a2] = 2102.00; g_svv_confirmed[a2] = now - 20 * 900;
      draw();
      const bool step5 = (objectDigest("QSVP_") == picture);
      check(step1 && step2 && step3 && step4 && step5,
            "G13 two live SELL signals over the same prices: ONE entry-zone box - the setup in play (with its entry / SL / TP) is drawn, the newer candidate "
            "stays off the chart; when the candidate confirms it takes the place; when it ends the older setup is back; a zone elsewhere and a BUY zone over "
            "the same prices are drawn; the picture does not depend on the order of the records in the table",
            seen1 + " | steps " + std::to_string(step1) + std::to_string(step2) + std::to_string(step3) + std::to_string(step4) + std::to_string(step5));
      sessionReset();
   }
   // --- an age is counted in bars: a weekend does not expire a setup
   {
      SSvpParams pp; SVP_DefaultParams(pp);
      SSvvStyle look = styleDefault();
      Story st = makeStory(0);
      std::vector<MqlRates> bars(st.bars.begin(), st.bars.begin() + st.i_confirm + 1);
      // after the confirmation: quiet candles between the stop (2116.84) and the target (2135.20);
      // the market closes for two days after the third of them
      const MqlRates shape = bars.back();
      for(int k = 1; k <= 120; k++)
      {
         MqlRates r = shape;
         r.time = shape.time + (datetime)k * 900 + (k > 3 ? 2 * 86400 : 0);
         r.open = 2123.00; r.close = (k % 2 == 0 ? 2123.40 : 2122.80); r.high = 2124.00; r.low = 2122.20;
         bars.push_back(r);
      }
      Tf tf; tf.build(bars);
      sessionReset();
      const datetime origin = st.bars[(size_t)st.i_sweep].time;
      int first_seen_bar = -1, expired_bar = -1; int state_monday = -1, state_before_expiry = -1; std::string note;
      for(int k = st.i_low1 - 40; k < (int)bars.size(); k++)
      {
         barPass(tf, k + 1, pp, look, false);
         const int rec = recordByOrigin(origin, 1);
         if(rec < 0) continue;
         if(first_seen_bar < 0) first_seen_bar = k;
         if(k == st.i_confirm + 4) state_monday = (int)g_qsr[rec].state;                // the first bar after the weekend
         if(expired_bar < 0 && QSR_IsTerminal(g_qsr[rec].state)) { expired_bar = k; note = std::string(g_qsr[rec].note); }
         if(expired_bar < 0) state_before_expiry = (int)g_qsr[rec].state;
      }
      check(first_seen_bar > 0 && state_monday == QSR_STATE_ACTIVE && state_before_expiry == QSR_STATE_ACTIVE &&
            expired_bar == first_seen_bar + look.max_active_bars + 1 && note == "older than 96 bars",
            "G14 a setup's age is counted in BARS: confirmed three bars before a two-day market close it is still ACTIVE on the first bar after "
            "it (26 bars are not 56 hours), and it expires on its 97th bar, not earlier",
            "state after the gap " + std::to_string(state_monday) + ", ended on bar " + std::to_string(expired_bar) + " (first seen " +
            std::to_string(first_seen_bar) + ") note [" + note + "]");
      sessionReset();
   }
   // --- the registry itself
   {
      string where;
      const bool ok = QSR_SelfTest(where);
      QSR_Reset();
      bool created = false;
      const int a = QSR_Upsert("XAUUSD", 15, 1, "T", "A", 1000, 1000, QSR_STATE_DETECTED, created);
      const bool c1 = created;
      const int b = QSR_Upsert("XAUUSD", 15, 1, "T", "A", 1000, 1900, QSR_STATE_DETECTED, created);
      const bool c2 = created;
      const bool back1 = QSR_SetState(a, QSR_STATE_CONFIRMED, 2800, "c");
      const bool back2 = QSR_SetState(a, QSR_STATE_DETECTED, 3700, "back");          // never backwards
      QSR_SetState(a, QSR_STATE_INVALIDATED, 4600, "x");
      const bool back3 = QSR_SetState(a, QSR_STATE_ACTIVE, 5500, "resurrect");       // a finished signal stays finished
      int over = 0;
      for(int k = 0; k < QSR_CAPACITY + 10; k++) { QSR_Upsert("XAUUSD", 15, 1, "T", "B" + std::to_string(k), 9000 + k, 9000 + k, QSR_STATE_DETECTED, created); if(QSR_Count() > QSR_CAPACITY) over++; }
      check(ok && a >= 0 && a == b && c1 && !c2 && back1 && !back2 && !back3 && over == 0 && QSR_Count() == QSR_CAPACITY,
            "G12 registry: its own self-test passes; the same identity is updated in place; a state never moves backwards and a finished signal is "
            "never revived; the table is bounded (64 records, oldest finished evicted first)", std::string(where));
      QSR_Reset();
   }
}

// ================================================================== unit: Chart Object Manager
static long chartOps() { return chartsim::C.created + chartsim::C.deleted + chartsim::C.moved + chartsim::C.propWrites; }

// two objects that would print on top of each other: same type, same anchors, same text
// Two boxes of the same side (same colour) that share a price: the same area
// drawn twice.
static int boxOverlaps(const std::string &prefix)
{
   std::vector<const chartsim::Obj *> boxes;
   for(const auto &kv : chartsim::C.objects)
      if(kv.second.type == OBJ_RECTANGLE && kv.first.compare(0, prefix.size(), prefix) == 0) boxes.push_back(&kv.second);
   int n = 0;
   for(size_t a = 0; a < boxes.size(); a++)
      for(size_t b = a + 1; b < boxes.size(); b++)
      {
         const double alo = std::min(boxes[a]->p[0], boxes[a]->p[1]), ahi = std::max(boxes[a]->p[0], boxes[a]->p[1]);
         const double blo = std::min(boxes[b]->p[0], boxes[b]->p[1]), bhi = std::max(boxes[b]->p[0], boxes[b]->p[1]);
         const bool same_side = (boxes[a]->ints.at((int)OBJPROP_COLOR) == boxes[b]->ints.at((int)OBJPROP_COLOR));
         if(same_side && alo <= bhi && blo <= ahi) n++;
      }
   return n;
}

// Captions of levels that share a column (liquidity on the left of the right
// edge, volume profile on the right) and sit closer than the declutter gap.
// ---- the chart measured from outside --------------------------------------
// Every text object under QSVP_ as a rectangle (bar position x price) by the
// declared layout model: one character = one M15 bar (a caption that names a
// direction has the room of its longer spelling), one line = the declutter gap
// of price, the anchor decides which way the text reaches. Written here
// independently of the view code. `times` = the M15 bars known to the pass.
struct CapBox { double x1, x2, lo, hi; bool in_chart; std::string name; };

static double barPosOf(const std::vector<datetime> &times, const int n, const datetime t)
{
   if(t >= times[(size_t)n - 1]) return (double)(n - 1) + (double)(t - times[(size_t)n - 1]) / 900.0;
   if(t <= times[0]) return -(double)(times[0] - t) / 900.0;
   return (double)(std::upper_bound(times.begin(), times.begin() + n, t) - times.begin() - 1);
}

static std::vector<CapBox> captionBoxes(const std::vector<datetime> &times, const int n)
{
   std::vector<CapBox> caps;
   if(n <= 0 || n > (int)times.size()) return caps;
   for(const auto &kv : chartsim::C.objects)
   {
      const chartsim::Obj &o = kv.second;
      if(o.type != OBJ_TEXT || kv.first.compare(0, 5, "QSVP_") != 0) continue;
      const auto txt = o.strs.find((int)OBJPROP_TEXT);
      const auto anc = o.ints.find((int)OBJPROP_ANCHOR);
      double w = 0.0;
      if(txt != o.strs.end())
      {
         const std::string &c = txt->second;
         w = (double)c.size() + (c.compare(0, 3, "BUY") == 0 ? 1.0 : 0.0) + (c.find(" up") != std::string::npos ? 2.0 : 0.0) + (c.find(" low") != std::string::npos ? 1.0 : 0.0);
      }
      const int a = anc == o.ints.end() ? (int)ANCHOR_LEFT_UPPER : (int)anc->second;
      const double x = barPosOf(times, n, o.t[0]), gap = g_svv_label_gap;
      CapBox c{x - 0.5 * w, x + 0.5 * w, o.p[0] - 0.5 * gap, o.p[0] + 0.5 * gap, false, kv.first};
      if(a == ANCHOR_LEFT_UPPER || a == ANCHOR_LEFT || a == ANCHOR_LEFT_LOWER) { c.x1 = x; c.x2 = x + w; }
      if(a == ANCHOR_RIGHT_UPPER || a == ANCHOR_RIGHT || a == ANCHOR_RIGHT_LOWER) { c.x1 = x - w; c.x2 = x; }
      if(a == ANCHOR_LEFT_UPPER || a == ANCHOR_UPPER || a == ANCHOR_RIGHT_UPPER) { c.lo = o.p[0] - gap; c.hi = o.p[0]; }
      if(a == ANCHOR_LEFT_LOWER || a == ANCHOR_LOWER || a == ANCHOR_RIGHT_LOWER) { c.lo = o.p[0]; c.hi = o.p[0] + gap; }
      // captions of structure breaks, finished signals and old sweeps sit on a bar inside the chart; the others in the right-hand column
      c.in_chart = (kv.first.compare(0, 9, "QSVP_STR_") == 0 || kv.first.compare(0, 9, "QSVP_SWP_") == 0 ||
                    (kv.first.size() > 2 && kv.first.compare(kv.first.size() - 2, 2, "_H") == 0));
      caps.push_back(c);
   }
   return caps;
}

// captions printed on top of each other
static int captionCollisions(const std::vector<datetime> &times, const int n)
{
   const std::vector<CapBox> caps = captionBoxes(times, n);
   int hits = 0;
   for(size_t i = 0; i < caps.size(); i++)
      for(size_t j = i + 1; j < caps.size(); j++)
         if(caps[i].x1 < caps[j].x2 && caps[j].x1 < caps[i].x2 && caps[i].lo < caps[j].hi && caps[j].lo < caps[i].hi) hits++;
   return hits;
}

// Captions struck through: a horizontal line, or the top / bottom edge of a box,
// running through the inside of a caption. `column` = count the captions of the
// right-hand column (levels), otherwise the captions that sit inside the chart.
static int captionStrikes(const std::vector<datetime> &times, const int n, const bool column)
{
   const std::vector<CapBox> caps = captionBoxes(times, n);
   int hits = 0;
   for(const CapBox &c : caps)
   {
      if(c.in_chart == column) continue;
      for(const auto &kv : chartsim::C.objects)
      {
         const chartsim::Obj &o = kv.second;
         if(kv.first.compare(0, 5, "QSVP_") != 0 || (o.type != OBJ_TREND && o.type != OBJ_RECTANGLE)) continue;
         const double xa = barPosOf(times, n, std::min(o.t[0], o.t[1])), xb = barPosOf(times, n, std::max(o.t[0], o.t[1]));
         if(!(xa < c.x2 - 1e-9 && c.x1 + 1e-9 < xb)) continue;                 // no stretch of the line lies under the text
         const double edges[2] = {o.p[0], o.p[1]};
         const int edge_count = (o.type == OBJ_RECTANGLE || o.p[0] != o.p[1]) ? 2 : 1;
         for(int e = 0; e < edge_count; e++)
            if(edges[e] > c.lo + 1e-9 && edges[e] < c.hi - 1e-9) { hits++; break; }
      }
   }
   return hits;
}
static std::vector<datetime> barTimes(const MqlArray<MqlRates> &m15, const int n)
{
   std::vector<datetime> t((size_t)n);
   for(int i = 0; i < n; i++) t[(size_t)i] = m15.v[(size_t)i].time;
   return t;
}

// The panel as drawn: how many text rows, the longest, how many were cut.
static void dashboardStats(int &labels, int &longest, int &clipped)
{
   labels = 0; longest = 0; clipped = 0;
   for(const auto &kv : chartsim::C.objects)
   {
      if(kv.second.type != OBJ_LABEL || kv.first.find("QSVP_DASH_R") != 0) continue;
      labels++;
      const std::string t = kv.second.strs.count((int)OBJPROP_TEXT) ? kv.second.strs.at((int)OBJPROP_TEXT) : std::string();
      longest = std::max(longest, (int)t.size());
      if(t.size() >= 3 && t.compare(t.size() - 3, 3, "...") == 0) clipped++;
   }
}

static int exactDuplicates(const std::string &prefix)
{
   std::map<std::string, int> seen; int dup = 0;
   for(const auto &kv : chartsim::C.objects)
   {
      if(kv.first.compare(0, prefix.size(), prefix) != 0) continue;
      const chartsim::Obj &o = kv.second;
      if(o.type == OBJ_LABEL || o.type == OBJ_RECTANGLE_LABEL) continue;         // pixel-anchored, compared separately
      char b[256];
      const auto t = o.strs.find((int)OBJPROP_TEXT);
      snprintf(b, sizeof b, "%d|%lld|%.6f|%lld|%.6f|%s", (int)o.type, (long long)o.t[0], o.p[0], (long long)o.t[1], o.p[1], t == o.strs.end() ? "" : t->second.c_str());
      if(++seen[b] > 1) dup++;
   }
   return dup;
}

static void unitChart()
{
   g_group = "chart";
   const datetime t1 = T0, t2 = T0 + 9000;
   chartsim::resetAll();
   chartsim::addUserObject("MyTrendline", OBJ_TREND, T0, 2000.0);
   chartsim::addUserObject("QSMC_PRIMARY_1", OBJ_ARROW, T0, 2001.0);              // belongs to nadir2
   chartsim::addUserObject("QSVP_left_over", OBJ_TEXT, T0, 2002.0);               // ours, from a previous session
   SVC_Init("QSVP_", 0);
   check(chartsim::find("MyTrendline") && chartsim::find("QSMC_PRIMARY_1") && !chartsim::find("QSVP_left_over") && chartsim::C.deleted == 1 && SVC_Count() == 0,
         "C01 start-up removes what a previous session left under OUR prefix and nothing else (the operator's line and nadir2's object stay)");
   chartsim::resetCounters();
   for(int pass = 0; pass < 200; pass++)
   {
      SVC_Begin();
      SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC");
      SVC_Box("ZONE", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t1, 2110.0, t2, 2105.0, clrLime, false, "zone");
      SVC_Text("TXT", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t2, 2110.0, "BSL", clrOrange, 8, ANCHOR_RIGHT_LOWER, "tip");
      SVC_Label("ROW", SVC_LAYER_PRIMARY, 0, 10, 20, "FINAL DECISION: WAIT", clrWhite, 9, ANCHOR_LEFT_UPPER);
      SVC_Panel("BG", SVC_LAYER_PRIMARY, 0, 10, 20, 300, 200, clrBlack, clrDimGray);
      SVC_End();
   }
   check(chartsim::C.created == 5 && chartsim::C.deleted == 0 && chartsim::countPrefix("QSVP_") == 5 && SVC_Count() == 5 && g_svc_created == 5 &&
         g_svc_updated == 5 * 199,
         "C02 the same five objects drawn in 200 refresh passes: 5 created, 0 deleted, 5 on the chart - a refresh UPDATES, it never adds",
         std::to_string(chartsim::C.created) + " created " + std::to_string(chartsim::C.deleted) + " deleted");
   {
      const long ops0 = chartOps();
      SVC_Begin();
      SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC");
      SVC_Box("ZONE", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t1, 2110.0, t2, 2105.0, clrLime, false, "zone");
      SVC_Text("TXT", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t2, 2110.0, "BSL", clrOrange, 8, ANCHOR_RIGHT_LOWER, "tip");
      SVC_Label("ROW", SVC_LAYER_PRIMARY, 0, 10, 20, "FINAL DECISION: WAIT", clrWhite, 9, ANCHOR_LEFT_UPPER);
      SVC_Panel("BG", SVC_LAYER_PRIMARY, 0, 10, 20, 300, 200, clrBlack, clrDimGray);
      SVC_End();
      const long same = chartOps() - ops0;
      const long ops1 = chartOps();
      SVC_Begin();
      SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2 + 900, 2100.0, clrGold, STYLE_SOLID, 2, "POC");   // one anchor moved
      SVC_Box("ZONE", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t1, 2110.0, t2, 2105.0, clrLime, false, "zone");
      SVC_Text("TXT", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t2, 2110.0, "BSL", clrOrange, 8, ANCHOR_RIGHT_LOWER, "tip");
      SVC_Label("ROW", SVC_LAYER_PRIMARY, 0, 10, 20, "FINAL DECISION: BUY SETUP", clrLime, 9, ANCHOR_LEFT_UPPER);                           // text and colour changed
      SVC_Panel("BG", SVC_LAYER_PRIMARY, 0, 10, 20, 300, 200, clrBlack, clrDimGray);
      SVC_End();
      const long changed = chartOps() - ops1;
      check(same == 0 && changed == 3,
            "C03 an identical pass performs ZERO chart operations; a pass where one anchor, one text and one colour changed performs exactly three",
            std::to_string(same) + " / " + std::to_string(changed));
   }
   {
      chartsim::resetCounters();
      SVC_Begin();
      SVC_Label("ROW", SVC_LAYER_PRIMARY, 0, 10, 20, "FINAL DECISION: BUY SETUP", clrLime, 9, ANCHOR_LEFT_UPPER);
      SVC_Panel("BG", SVC_LAYER_PRIMARY, 0, 10, 20, 300, 200, clrBlack, clrDimGray);
      const int removed = SVC_End();
      check(removed == 3 && chartsim::C.deleted == 3 && !chartsim::find("QSVP_ZONE") && !chartsim::find("QSVP_TXT") && !chartsim::find("QSVP_LVL") &&
            chartsim::find("QSVP_ROW") && SVC_Count() == 2,
            "C04 what a pass does not draw (zone invalidated, level gone) is deleted at the end of that pass - and only that");
   }
   {
      SVC_SetLayer(SVC_LAYER_SECONDARY, false, 40);
      const int refused0 = g_svc_refused;
      SVC_Begin();
      SVC_Box("ZONE", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t1, 2110.0, t2, 2105.0, clrLime, false, "zone");
      SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC");
      SVC_End();
      const bool off = (!chartsim::find("QSVP_ZONE") && chartsim::find("QSVP_LVL") && g_svc_refused == refused0 + 1 && SVC_CountLayer(SVC_LAYER_SECONDARY) == 0);
      SVC_SetLayer(SVC_LAYER_SECONDARY, true, 40);
      SVC_Begin();
      SVC_Box("ZONE", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t1, 2110.0, t2, 2105.0, clrLime, false, "zone");
      SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC");
      SVC_End();
      SVC_SetLayer(SVC_LAYER_VOLUME, false, 24);
      SVC_Begin();
      SVC_Box("ZONE", SVC_LAYER_SECONDARY, "Z1", "VALIDATED", t1, 2110.0, t2, 2105.0, clrLime, false, "zone");
      SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC");
      SVC_End();
      check(off && chartsim::find("QSVP_ZONE") && !chartsim::find("QSVP_LVL"),
            "C05 a layer that is switched off draws nothing; switching a layer off removes its objects on the next pass, switching it on brings them back");
      SVC_SetLayer(SVC_LAYER_VOLUME, true, 24);
   }
   {
      SVC_SetLayer(SVC_LAYER_OPTIONAL, true, 6);
      SVC_Begin();
      for(int i = 0; i < 40; i++) SVC_Text("OLD" + std::to_string(i), SVC_LAYER_OPTIONAL, "S", "EXPIRED", t1 + i * 900, 2100.0 + i, "old", clrSilver, 8, ANCHOR_LEFT, "t");
      SVC_End();
      const bool capped = (SVC_CountLayer(SVC_LAYER_OPTIONAL) == 6 && chartsim::countPrefix("QSVP_OLD") == 6);
      // the registry itself is bounded
      for(int k = 0; k < SVC_LAYERS; k++) SVC_SetLayer((ENUM_SVC_LAYER)k, true, 100000);
      long peak = 0;
      for(int pass = 0; pass < 2; pass++)
      {
         SVC_Begin();
         for(int i = 0; i < SVC_MAX_OBJECTS + 50; i++)
         {
            SVC_Text("N" + std::to_string(i), SVC_LAYER_OPTIONAL, "S", "x", t1, 2100.0, "n", clrSilver, 8, ANCHOR_LEFT, "t");
            peak = std::max(peak, chartsim::countPrefix("QSVP_"));
         }
         SVC_End();
      }
      check(capped && peak == SVC_MAX_OBJECTS && SVC_Count() == SVC_MAX_OBJECTS && chartsim::countPrefix("QSVP_") == SVC_MAX_OBJECTS,
            "C06 every layer has a hard cap (40 requests into a cap of 6 leave 6 objects) and the whole program can never own more than " +
            std::to_string(SVC_MAX_OBJECTS) + " objects", std::to_string(SVC_Count()) + " registered, " + std::to_string(chartsim::countPrefix("QSVP_")) + " on chart");
   }
   {
      SVC_Init("QSVP_", 0);
      for(int k = 0; k < SVC_LAYERS; k++) SVC_SetLayer((ENUM_SVC_LAYER)k, true, 64);
      SVC_Begin(); SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC"); SVC_End();
      ObjectDelete(0, "QSVP_LVL");                                   // the operator deleted our line by hand
      SVC_Begin(); SVC_Segment("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC"); SVC_End();
      chartsim::Obj *o = chartsim::find("QSVP_LVL");
      const bool back = (o && near(o->p[0], 2100.0) && o->t[1] == t2 && o->ints[(int)OBJPROP_COLOR] == clrGold && SVC_Count() == 1);
      // the same id asked for as another kind of object
      SVC_Begin(); SVC_Text("LVL", SVC_LAYER_VOLUME, "PROFILE", "DAILY", t1, 2100.0, "POC", clrGold, 8, ANCHOR_LEFT, "t"); SVC_End();
      o = chartsim::find("QSVP_LVL");
      check(back && o && o->type == OBJ_TEXT && chartsim::countPrefix("QSVP_") == 1 && SVC_Count() == 1,
            "C07 an object deleted behind the program's back is re-created on the next pass (once); an id re-used for another object type "
            "replaces the old object instead of leaving two");
   }
   {
      chartsim::resetCounters();
      SVC_Begin();
      SVC_Segment("A", SVC_LAYER_VOLUME, "P", "x", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC");
      SVC_Segment("A", SVC_LAYER_VOLUME, "P", "x", t1, t2, 2100.0, clrGold, STYLE_SOLID, 2, "POC");     // the same id twice in one pass
      SVC_Text("", SVC_LAYER_VOLUME, "P", "x", t1, 2100.0, "anonymous", clrGold, 8, ANCHOR_LEFT, "t");   // no id
      SVC_End();
      check(chartsim::C.created == 1 && chartsim::countPrefix("QSVP_A") == 1 && SVC_Count() == 1,
            "C08 the same id claimed twice in one pass is one object; an object without an id is never created");
   }
   {
      const std::string before_user = std::to_string(chartsim::find("MyTrendline")->p[0]) + "|" + std::to_string(chartsim::find("QSMC_PRIMARY_1")->p[0]);
      SVC_Shutdown();
      bool only_ours = true;
      for(const std::string &n : chartsim::C.deletedNames) if(n.compare(0, 5, "QSVP_") != 0) only_ours = false;
      const std::string after_user = std::to_string(chartsim::find("MyTrendline") ? chartsim::find("MyTrendline")->p[0] : -1.0) + "|" +
                                     std::to_string(chartsim::find("QSMC_PRIMARY_1") ? chartsim::find("QSMC_PRIMARY_1")->p[0] : -1.0);
      check(chartsim::countPrefix("QSVP_") == 0 && SVC_Count() == 0 && only_ours && before_user == after_user && (int)chartsim::C.objects.size() == 2,
            "C09 shutdown removes every object of the program and touches nothing else: the two foreign objects are still there, unchanged");
   }
   // --- the view on the story: caps, no duplicates, no double zone, captions that do not collide
   {
      SSvpParams p; SVP_DefaultParams(p);
      SSvvStyle style = styleDefault();
      Story st = makeStory(1); Tf tf; tf.build(st.bars);
      sessionReset();
      SVC_Init("QSVP_", 0);
      SVC_SetLayer(SVC_LAYER_PRIMARY, true, 48); SVC_SetLayer(SVC_LAYER_SECONDARY, true, 40); SVC_SetLayer(SVC_LAYER_VOLUME, true, 24);
      SVC_SetLayer(SVC_LAYER_DETAIL, false, 48); SVC_SetLayer(SVC_LAYER_OPTIONAL, false, 48);
      int max_objects = 0, dup = 0, zone_twice = 0, close_captions = 0, max_secondary = 0, max_primary = 0, max_volume = 0, hidden = 0, passes = 0, struck = 0;
      int at_confirm = 0; std::string names_confirm;
      const std::vector<datetime> all_times = barTimes(tf.m15, (int)tf.m15.v.size());
      for(int k = st.i_low1 - 60; k <= st.i_end; k++)
      {
         MqlArray<MqlRates> view; view.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + k + 1);
         barPass(tf, k + 1, p, style, false);
         SVV_Render(view, k + 1, "XAUUSD", p, style);
         passes++;
         const int n = (int)chartsim::countPrefix("QSVP_");
         max_objects = std::max(max_objects, n);
         max_primary = std::max(max_primary, SVC_CountLayer(SVC_LAYER_PRIMARY));
         max_secondary = std::max(max_secondary, SVC_CountLayer(SVC_LAYER_SECONDARY));
         max_volume = std::max(max_volume, SVC_CountLayer(SVC_LAYER_VOLUME));
         dup += exactDuplicates("QSVP_");
         hidden += g_svv_labels_hidden;
         // an entry zone must not also be drawn as a generic zone box
         zone_twice += boxOverlaps("QSVP_");
         // captions printed on top of each other
         close_captions += captionCollisions(all_times, k + 1);
         struck += captionStrikes(all_times, k + 1, true) + captionStrikes(all_times, k + 1, false);
         if(k == st.i_confirm) { at_confirm = n; for(const auto &kv : chartsim::C.objects) if(kv.first.compare(0, 5, "QSVP_") == 0) names_confirm += kv.first.substr(5) + " "; }
      }
      check(max_objects <= 60 && max_primary <= 48 && max_secondary <= 40 && max_volume <= 24 && dup == 0,
            "C10 the whole view over " + std::to_string(passes) + " bars of the story: never more than " + std::to_string(max_objects) + " objects (primary " +
            std::to_string(max_primary) + ", secondary " + std::to_string(max_secondary) + ", volume " + std::to_string(max_volume) + "), and never two objects "
            "with the same type, anchors and text", std::to_string(dup) + " duplicates");
      check(zone_twice == 0, "C11 one box per price area: no two boxes of the same side overlap on any bar (an entry zone is not drawn again as an OB/FVG box)",
            std::to_string(zone_twice) + " overlapping pairs");
      check(close_captions == 0 && struck == 0, "C12 on no bar is a caption printed on top of another or struck through by a line (" + std::to_string(hidden) +
            " captions were withheld over the walk; their lines stayed)", std::to_string(close_captions) + " colliding pairs, " + std::to_string(struck) + " struck through");
      printf("INFO  chart objects on the confirming bar (%d): %s\n", at_confirm, names_confirm.c_str());
      printf("INFO  chart census at the end of the walk: %s\n", std::string(SVC_Census()).c_str());
      // churn: how many objects were created over the walk per bar
      const double per_bar = (double)g_svc_created / passes;
      check(per_bar < 1.5 && g_svc_created - g_svc_deleted == SVC_Count(),
            "C13 churn: " + num(per_bar, 2) + " objects created per closed bar on average (" + std::to_string(g_svc_created) + " over " + std::to_string(passes) +
            " bars), every one of them accounted for (created - deleted = on the chart)");
      // optional and detail layers on: still bounded
      SVC_SetLayer(SVC_LAYER_DETAIL, true, 48); SVC_SetLayer(SVC_LAYER_OPTIONAL, true, 48);
      int max_all = 0, dup_all = 0;
      for(int k = st.i_confirm - 5; k <= st.i_end; k++)
      {
         MqlArray<MqlRates> view; view.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + k + 1);
         barPass(tf, k + 1, p, style, false);
         SVV_Render(view, k + 1, "XAUUSD", p, style);
         max_all = std::max(max_all, (int)chartsim::countPrefix("QSVP_"));
         dup_all += exactDuplicates("QSVP_");
      }
      check(max_all <= 48 + 40 + 24 + 48 + 48 && max_all > max_objects && dup_all == 0 && SVC_CountLayer(SVC_LAYER_DETAIL) <= 40,
            "C14 with the histogram and the optional layer switched on the chart holds at most " + std::to_string(max_all) + " objects: still capped, still no duplicates");
      SVC_Shutdown();
   }
   // --- the caption layout model
   {
      Story st = makeStory(0); Tf tf; tf.build(st.bars);
      const int n = 600;
      MqlArray<MqlRates> view; view.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + n);
      const datetime t100 = view.v[100].time, t109 = view.v[109].time, t110 = view.v[110].time;
      g_svv_label_gap = 2.0;
      auto fresh = [&]() { g_svv_caps = 0; g_svv_labels_hidden = 0; };
      // the same place twice
      fresh();
      const bool a1 = SVV_CaptionRoom(view, n, t100, 2100.0, "ABCDEFGHIJ", ANCHOR_LEFT);
      const bool a2 = SVV_CaptionRoom(view, n, t100, 2100.0, "ABCDEFGHIJ", ANCHOR_LEFT);
      const bool same_place = (a1 && !a2 && g_svv_labels_hidden == 1 && g_svv_caps == 1);
      // ten characters starting on bar 100 reach bar 110: a caption starting there fits, one starting on bar 109 does not
      fresh();
      SVV_CaptionRoom(view, n, t100, 2100.0, "ABCDEFGHIJ", ANCHOR_LEFT);
      const bool b1 = SVV_CaptionRoom(view, n, t110, 2100.0, "ABCDEFGHIJ", ANCHOR_LEFT);
      const bool b2 = SVV_CaptionRoom(view, n, t109, 2100.0, "ABC", ANCHOR_LEFT);
      // a right-anchored caption ends on its bar: ending on bar 100 it fits, ending on bar 101 it does not
      const bool b3 = SVV_CaptionRoom(view, n, t100, 2100.0, "ABC", ANCHOR_RIGHT);
      const bool b4 = SVV_CaptionRoom(view, n, view.v[101].time, 2100.0, "ABC", ANCHOR_RIGHT);
      const bool sideways = (b1 && !b2 && b3 && !b4);
      // text above a level and text below the same level do not collide; one line is `gap` high
      fresh();
      const bool c1 = SVV_CaptionRoom(view, n, t100, 2100.0, "ABCDE", ANCHOR_RIGHT_LOWER);     // stands on the level: 2100..2102
      const bool c2 = SVV_CaptionRoom(view, n, t100, 2100.0, "ABCDE", ANCHOR_RIGHT_UPPER);     // hangs below it:    2098..2100
      const bool c3 = SVV_CaptionRoom(view, n, t100, 2101.9, "ABCDE", ANCHOR_RIGHT_LOWER);     // 2101.9..2103.9 overlaps the first
      const bool c4 = SVV_CaptionRoom(view, n, t100, 2102.0, "ABCDE", ANCHOR_RIGHT_LOWER);     // 2102..2104 touches it: fits
      const bool c5 = SVV_CaptionRoom(view, n, t100, 2099.5, "ABCDE", ANCHOR_RIGHT);           // centred 2098.5..2100.5: overlaps both
      const bool vertical = (c1 && c2 && !c3 && c4 && !c5);
      // bars are counted, not minutes: across a weekend two captions three bars apart still collide
      std::vector<MqlRates> gap_bars(st.bars.begin(), st.bars.begin() + 300);
      for(size_t k = 200; k < gap_bars.size(); k++) gap_bars[k].time += 2 * 86400;
      MqlArray<MqlRates> gview; toArray(gap_bars, gview);
      fresh();
      SVV_CaptionRoom(gview, 300, gap_bars[198].time, 2100.0, "ABCDEFGHIJ", ANCHOR_LEFT);
      const bool d1 = SVV_CaptionRoom(gview, 300, gap_bars[201].time, 2100.0, "ABC", ANCHOR_LEFT);
      const bool d2 = SVV_CaptionRoom(gview, 300, gap_bars[208].time, 2100.0, "ABC", ANCHOR_LEFT);
      // to the right of the newest bar the count continues at one bar per 15 minutes
      const double x_future = SVV_BarPos(gview, 300, gap_bars[299].time + 8 * 900), x_gap = SVV_BarPos(gview, 300, gap_bars[199].time + 86400);
      const bool weekend = (!d1 && d2 && near(x_future, 307.0) && near(x_gap, 199.0));
      // a caption that names a direction takes the room of its longer spelling
      const bool neutral = (SVV_CaptionChars("H1 BOS up") == SVV_CaptionChars("H1 BOS down") && SVV_CaptionChars("H4+H1 CHoCH up") == SVV_CaptionChars("H4+H1 CHoCH down") &&
                            SVV_CaptionChars("BUY SETUP ACTIVE") == SVV_CaptionChars("SELL SETUP ACTIVE") &&
                            SVV_CaptionChars("BUY candidate: awaiting retest") == SVV_CaptionChars("SELL candidate: awaiting retest") &&
                            SVV_CaptionChars("BSL swing high") == SVV_CaptionChars("SSL swing low") && SVV_CaptionChars("BSL PDH+EQH") == SVV_CaptionChars("SSL PDL+EQL") &&
                            SVV_CaptionChars("POC") == 3 && SVV_CaptionChars("SELL SETUP ACTIVE") == 17);
      // a full table refuses instead of risking an overlap
      fresh();
      int placed = 0;
      for(int k = 0; k < SVV_CAPTION_MAX + 5; k++) if(SVV_CaptionRoom(view, n, t100, 2000.0 + 10.0 * k, "ABC", ANCHOR_LEFT)) placed++;
      const bool bounded = (placed == SVV_CAPTION_MAX && g_svv_labels_hidden == 5);
      check(same_place && sideways && vertical && weekend && neutral && bounded,
            "C15 caption layout model: a second caption in the same place is withheld; a character is one bar wide and the anchor decides which way the text "
            "reaches; text above a level and text below it do not collide; bars are counted, not minutes (a weekend does not separate two captions); BUY/SELL, "
            "up/down, high/low captions take the same room; the table is bounded",
            std::string("steps ") + (same_place ? "1" : "0") + (sideways ? "1" : "0") + (vertical ? "1" : "0") + (weekend ? "1" : "0") + (neutral ? "1" : "0") + (bounded ? "1" : "0"));
      fresh();
   }
   // --- market structure: one mark per broken level
   {
      Story st = makeStory(0); Tf tf; tf.build(st.bars);
      const int n = 600;
      MqlArray<MqlRates> view; view.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + n);
      SSvpParams pp; SVP_DefaultParams(pp); pp.tick_size = 0.01; pp.point = 0.01; pp.digits = 2;
      SSvvStyle look = styleDefault();
      chartsim::resetAll();
      SVC_Init("QSVP_", 0);
      SVC_SetLayer(SVC_LAYER_PRIMARY, true, 48); SVC_SetLayer(SVC_LAYER_SECONDARY, true, 40); SVC_SetLayer(SVC_LAYER_VOLUME, true, 24);
      SVC_SetLayer(SVC_LAYER_DETAIL, false, 48); SVC_SetLayer(SVC_LAYER_OPTIONAL, false, 48);
      auto event = [&](const ENUM_SVP_EVENT kind, const int dir, const int swing_bar, const int break_bar, const double level) {
         SSvpStructEvent e; e.kind = kind; e.direction = dir; e.swing_index = swing_bar; e.swing_time = view.v[(size_t)swing_bar].time;
         e.break_index = break_bar; e.break_time = view.v[(size_t)break_bar].time; e.level = level; return e;
      };
      auto draw = [&]() { g_svv_caps = 0; g_svv_labels_hidden = 0; g_svv_deferred = 0; g_svv_label_gap = 2.0; SVC_Begin(); SVV_DrawStructureSet(pp, look); SVV_PlaceDeferred(view, n); SVC_End(); };
      auto lines = [&]() { return (int)chartsim::countType("QSVP_STR_", OBJ_TREND); };
      auto texts = [&]() { return (int)chartsim::countType("QSVP_STR_", OBJ_TEXT); };
      auto textOf = [&](const std::string &name) { const chartsim::Obj *o = chartsim::find(name); return o && o->strs.count((int)OBJPROP_TEXT) ? o->strs.at((int)OBJPROP_TEXT) : std::string(); };
      auto tipOf = [&](const std::string &name) { const chartsim::Obj *o = chartsim::find(name); return o && o->strs.count((int)OBJPROP_TOOLTIP) ? o->strs.at((int)OBJPROP_TOOLTIP) : std::string(); };
      // H4 and H1 broke the same swing high (an H4 swing is an H1 swing too); M15 broke a low far away
      ArrayResize(g_svp_ev_h4, 1); ArrayResize(g_svp_ev_h1, 1); ArrayResize(g_svp_ev_m15, 1); ArrayResize(g_svp_ev_h1_int, 0);
      g_svp_ev_h4[0] = event(SVP_EV_BOS, 1, 400, 480, 2100.00);
      g_svp_ev_h1[0] = event(SVP_EV_BOS, 1, 420, 470, 2100.00);
      g_svp_ev_m15[0] = event(SVP_EV_CHOCH, -1, 540, 560, 2080.00);
      draw();
      const std::string id4 = "QSVP_STR_H4_" + std::to_string((long long)view.v[480].time);
      const chartsim::Obj *line = chartsim::find(id4 + "_L");
      const bool merged = (lines() == 2 && texts() == 2 && textOf(id4 + "_T") == "H4+H1 BOS up" && line && line->t[0] == view.v[400].time && line->t[1] == view.v[480].time &&
                           tipOf(id4 + "_L").find("H4 BOS up @ 2100.00") != std::string::npos && tipOf(id4 + "_L").find("H1 BOS up @ 2100.00") != std::string::npos &&
                           exactDuplicates("QSVP_") == 0);
      const std::string seen = std::to_string(lines()) + " lines, " + std::to_string(texts()) + " captions, [" + textOf(id4 + "_T") + "]";
      // a BOS on one timeframe and a CHoCH on the other: both are named
      g_svp_ev_h1[0] = event(SVP_EV_CHOCH, 1, 420, 470, 2100.00);
      draw();
      const bool mixed = (lines() == 2 && textOf(id4 + "_T") == "H4 BOS + H1 CHoCH up");
      // another level 0.50 away: its own mark. The H1 line runs where the H4 caption would stand, so that caption
      // hangs UNDER its own line instead; nothing overprints, nothing is struck through
      g_svp_ev_h1[0] = event(SVP_EV_BOS, 1, 420, 478, 2100.50);
      draw();
      const std::string id1 = "QSVP_STR_H1_" + std::to_string((long long)view.v[478].time);
      const std::vector<datetime> times16 = barTimes(view, n);
      auto anchorOf = [&](const std::string &name) { const chartsim::Obj *o = chartsim::find(name); return o && o->ints.count((int)OBJPROP_ANCHOR) ? (int)o->ints.at((int)OBJPROP_ANCHOR) : -1; };
      const bool apart = (lines() == 3 && texts() == 3 && textOf(id4 + "_T") == "H4 BOS up" && anchorOf(id4 + "_T") == (int)ANCHOR_RIGHT_UPPER &&
                          textOf(id1 + "_T") == "H1 BOS up" && anchorOf(id1 + "_T") == (int)ANCHOR_RIGHT_LOWER && g_svv_labels_hidden == 0 &&
                          captionCollisions(times16, n) == 0 && captionStrikes(times16, n, false) == 0);
      // a third line under the H4 level as well: no clear side is left for the H4 caption -> it is withheld, its line stays
      g_svp_ev_m15[0] = event(SVP_EV_CHOCH, -1, 440, 476, 2099.50);
      draw();
      const bool boxed_in = (lines() == 3 && texts() == 2 && chartsim::find(id4 + "_L") != nullptr && chartsim::find(id4 + "_T") == nullptr &&
                             g_svv_labels_hidden == 1 && captionCollisions(times16, n) == 0 && captionStrikes(times16, n, false) == 0);
      g_svp_ev_m15[0] = event(SVP_EV_CHOCH, -1, 540, 560, 2080.00);
      // the same price broken in opposite directions is two events: two marks, text above and text below
      g_svp_ev_h1[0] = event(SVP_EV_CHOCH, -1, 420, 478, 2100.00);
      draw();
      const bool opposite = (lines() == 3 && texts() == 3 && textOf(id1 + "_T") == "H1 CHoCH down" && g_svv_labels_hidden == 0);
      // an older H1 break of the same level (optional layer) is not folded into "H1+H1"
      SVC_SetLayer(SVC_LAYER_OPTIONAL, true, 48);
      ArrayResize(g_svp_ev_h1, 2);
      g_svp_ev_h1[0] = event(SVP_EV_BOS, 1, 300, 330, 2100.00);          // older
      g_svp_ev_h1[1] = event(SVP_EV_BOS, 1, 420, 470, 2100.00);          // newest
      draw();
      const bool older = (lines() == 3 && textOf(id4 + "_T") == "H4+H1 BOS up" &&
                          textOf("QSVP_STR_H1_" + std::to_string((long long)view.v[330].time) + "_T") == "H1 BOS up");
      check(merged && mixed && apart && boxed_in && opposite && older,
            "C16 market structure: H4 and H1 breaking the SAME level are one line and one caption (\"H4+H1 BOS up\"), with both events in the tooltip; "
            "a level 0.50 away keeps its own mark and the caption a line would strike through moves to the other side of its line; with a line on "
            "both sides it is withheld (the line stays); opposite directions stay two marks; an older break of the same timeframe is not merged into itself",
            seen + " | steps " + (merged ? "1" : "0") + (mixed ? "1" : "0") + (apart ? "1" : "0") + (boxed_in ? "1" : "0") + (opposite ? "1" : "0") + (older ? "1" : "0"));
      ArrayResize(g_svp_ev_h4, 0); ArrayResize(g_svp_ev_h1, 0); ArrayResize(g_svp_ev_m15, 0);
      SVC_Shutdown();
   }
   // --- volume profile: a node on a profile level is one line
   {
      Story st = makeStory(0); Tf tf; tf.build(st.bars);
      const int n = 600;
      MqlArray<MqlRates> view; view.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + n);
      SSvpParams pp; SVP_DefaultParams(pp); pp.tick_size = 0.01; pp.point = 0.01; pp.digits = 2;
      SSvvStyle look = styleDefault();
      chartsim::resetAll();
      SVC_Init("QSVP_", 0);
      SVC_SetLayer(SVC_LAYER_PRIMARY, true, 48); SVC_SetLayer(SVC_LAYER_SECONDARY, true, 40); SVC_SetLayer(SVC_LAYER_VOLUME, true, 24);
      SVC_SetLayer(SVC_LAYER_DETAIL, false, 48); SVC_SetLayer(SVC_LAYER_OPTIONAL, false, 48);
      const SSvpProfile keep = g_svp_profile;
      g_svp_profile.valid = true; g_svp_profile.kind = SVP_VP_DAILY; g_svp_profile.first_bar = view.v[500].time; g_svp_profile.last_bar = view.v[599].time;
      g_svp_profile.bin_size = 0.50; g_svp_profile.bin_count = 0; g_svp_profile.real_volume = false; g_svp_profile.basis = "BROKER TICK VOLUME";
      g_svp_profile.poc = 2100.00; g_svp_profile.vah = 2105.00; g_svp_profile.val = 2095.00;
      g_svp_profile.hvn_count = 3; g_svp_profile.hvn[0] = 2095.00; g_svp_profile.hvn[1] = 2102.00; g_svp_profile.hvn[2] = 2100.10;   // on VAL, free, on the POC
      g_svp_profile.lvn_count = 2; g_svp_profile.lvn[0] = 2105.20; g_svp_profile.lvn[1] = 2097.75;                                  // on VAH, free
      look.nodes = 3;
      g_svv_caps = 0; g_svv_labels_hidden = 0; g_svv_label_gap = 2.0;
      SVC_Begin(); SVV_DrawProfile(view, n, pp, look); SVC_End();
      auto tipOf = [&](const std::string &name) { const chartsim::Obj *o = chartsim::find(name); return o && o->strs.count((int)OBJPROP_TOOLTIP) ? o->strs.at((int)OBJPROP_TOOLTIP) : std::string(); };
      const int segs = (int)chartsim::countType("QSVP_VP_", OBJ_TREND);
      check(segs == 5 && chartsim::find("QSVP_VP_HVN1") && chartsim::find("QSVP_VP_LVN1") && !chartsim::find("QSVP_VP_HVN0") && !chartsim::find("QSVP_VP_HVN2") &&
            !chartsim::find("QSVP_VP_LVN0") && tipOf("QSVP_VP_VAL").find("(also HVN)") != std::string::npos && tipOf("QSVP_VP_VAH").find("(also LVN)") != std::string::npos &&
            tipOf("QSVP_VP_POC").find("(also") == std::string::npos && exactDuplicates("QSVP_") == 0,
            "C17 a volume node that sits on the POC or on a value-area edge is not drawn a second time: POC, VAH, VAL and the two free nodes are five lines, "
            "and the VAL / VAH tooltips say what else they are", std::to_string(segs) + " lines | VAL tip: " + tipOf("QSVP_VP_VAL"));
      g_svp_profile = keep;
      SVC_Shutdown();
   }
   // --- the whole view on candles nobody arranged
   {
      const std::vector<MqlRates> bars = syntheticBars(11, 3400);
      Tf tf; tf.build(bars);
      SSvpParams pp; SVP_DefaultParams(pp); pp.tick_size = 1.0; pp.point = 1.0; pp.digits = 0; pp.spread = 20.0;
      SSvvStyle look = styleDefault();
      sessionReset();
      SVC_Init("QSVP_", 0);
      SVC_SetLayer(SVC_LAYER_PRIMARY, true, 48); SVC_SetLayer(SVC_LAYER_SECONDARY, true, 40); SVC_SetLayer(SVC_LAYER_VOLUME, true, 24);
      SVC_SetLayer(SVC_LAYER_DETAIL, false, 48); SVC_SetLayer(SVC_LAYER_OPTIONAL, false, 48);
      const std::vector<datetime> all_times = barTimes(tf.m15, (int)tf.m15.v.size());
      int passes = 0, dup = 0, boxes_twice = 0, collisions = 0, hidden = 0, max_objects = 0, merged_marks = 0, setups = 0, last_state = 0, struck = 0, drawn = 0;
      for(int k = 2200; k < (int)bars.size(); k++)
      {
         MqlArray<MqlRates> view; view.v.assign(tf.m15.v.begin(), tf.m15.v.begin() + k + 1);
         if(!barPass(tf, k + 1, pp, look, false)) continue;
         SVV_Render(view, k + 1, "SYNTH", pp, look);
         passes++;
         dup += exactDuplicates("QSVP_"); boxes_twice += boxOverlaps("QSVP_"); collisions += captionCollisions(all_times, k + 1);
         struck += captionStrikes(all_times, k + 1, true) + captionStrikes(all_times, k + 1, false);
         for(const auto &kv : chartsim::C.objects) if(kv.second.type == OBJ_TEXT && kv.first.compare(0, 5, "QSVP_") == 0) drawn++;
         hidden += g_svv_labels_hidden;
         max_objects = std::max(max_objects, (int)chartsim::countPrefix("QSVP_"));
         for(const auto &kv : chartsim::C.objects)
            if(kv.second.type == OBJ_TEXT && kv.first.compare(0, 9, "QSVP_STR_") == 0 && kv.second.strs.count((int)OBJPROP_TEXT) &&
               kv.second.strs.at((int)OBJPROP_TEXT).find('+') != std::string::npos) { merged_marks++; break; }
         if(g_svp.state != SVP_DECISION_WAIT && (int)g_svp.state != last_state) setups++;
         last_state = (int)g_svp.state;
      }
      check(passes >= 1100 && dup == 0 && boxes_twice == 0 && collisions == 0 && struck == 0 && max_objects <= 60 && merged_marks > 0 && hidden > 0 && drawn > 4 * passes,
            "C18 " + std::to_string(passes) + " bars of a synthetic series (random walk with stop runs - nobody arranged these candles): no two objects on the same "
            "spot, no two same-side boxes over one price area, no caption on top of another, no caption struck through by a line (" + std::to_string(drawn) +
            " captions drawn, " + std::to_string(hidden) + " withheld, " + std::to_string(merged_marks) + " bars showed a merged H4+H1 mark), at most " +
            std::to_string(max_objects) + " objects",
            std::to_string(dup) + " duplicates, " + std::to_string(boxes_twice) + " box overlaps, " + std::to_string(collisions) + " caption collisions, " +
            std::to_string(struck) + " struck, max " + std::to_string(max_objects) + ", merged " + std::to_string(merged_marks) + ", drawn " + std::to_string(drawn) +
            ", setups " + std::to_string(setups));
      SVC_Shutdown();
      sessionReset();
   }
}

// ================================================================== unit: dashboard
static void unitDashboard()
{
   g_group = "dashboard";
   SSvpParams p; SVP_DefaultParams(p);
   SSvvStyle style = styleDefault();
   Story st = makeStory(0); Tf tf; tf.build(st.bars);
   const char *labels[SVV_ROWS] = {"MARKET: ", "TIMEFRAME: ", "H4 BIAS: ", "H1 STRUCTURE: ", "LIQUIDITY: ", "SWEEP: ", "OB/FVG: ", "POC: ", "VAH / VAL: ",
                                   "FINAL DECISION: ", "ENTRY: ", "STOP LOSS: ", "TAKE PROFIT: ", "RISK/REWARD: ", "VOLUME PROFILE: ", "WHY: "};
   sessionReset();
   barPass(tf, st.i_confirm + 1, p, style, false);
   MqlArray<string> rows;
   int n = SVV_DashboardRows(g_svp, "XAUUSD", p, "(DAILY, tick volume)", rows);
   bool order = (n == SVV_ROWS);
   for(int i = 0; i < n && order; i++) if(std::string(rows[i]).find(labels[i]) != 0) order = false;
   check(order, "B01 sixteen rows in a fixed order: MARKET, TIMEFRAME, H4 BIAS, H1 STRUCTURE, LIQUIDITY, SWEEP, OB/FVG, POC, VAH / VAL, FINAL DECISION, "
                "ENTRY, STOP LOSS, TAKE PROFIT, RISK/REWARD, VOLUME PROFILE, WHY");
   check(std::string(rows[0]) == "MARKET: XAUUSD" && std::string(rows[2]) == "H4 BIAS: BULLISH" && std::string(rows[9]) == "FINAL DECISION: BUY SETUP" &&
         std::string(rows[10]) == "ENTRY: 2122.60" && std::string(rows[11]) == "STOP LOSS: 2116.84" &&
         std::string(rows[12]).find("TAKE PROFIT: 2135.20 (") == 0 && std::string(rows[13]) == "RISK/REWARD: 1:2.19" &&
         std::string(rows[7]).find("POC: ") == 0 && std::string(rows[7]).find("(DAILY, tick volume)") != std::string::npos &&
         std::string(rows[15]) == "WHY: BUY SETUP - all 10 confirmations hold",
         "B02 on the confirming bar: FINAL DECISION: BUY SETUP, ENTRY 2122.60, STOP LOSS 2116.84, TAKE PROFIT 2135.20 (its source), RISK/REWARD 1:2.19, "
         "the POC row names the profile and its volume source", std::string(rows[12]) + " | " + std::string(rows[7]));
   for(int i = 0; i < n; i++) printf("INFO  dashboard  %s\n", std::string(rows[i]).c_str());
   barPass(tf, st.i_disp + 1, p, style, false);
   SVV_DashboardRows(g_svp, "XAUUSD", p, "(DAILY, tick volume)", rows);
   check(std::string(rows[9]) == "FINAL DECISION: WAIT" && std::string(rows[10]).find("ENTRY: N/A (awaiting retest of ") == 0 &&
         std::string(rows[11]) == "STOP LOSS: N/A" && std::string(rows[12]) == "TAKE PROFIT: N/A" && std::string(rows[13]) == "RISK/REWARD: N/A" &&
         std::string(rows[15]).find("WHY: WAIT - BUY candidate 8/10") == 0,
         "B03 while the retest is pending: WAIT, ENTRY reads N/A (awaiting retest of the zone), SL / TP / RR read N/A, and WHY names the step that is missing",
         std::string(rows[10]) + " | " + std::string(rows[15]));
   // never a price without a valid plan, on any bar
   int leaks = 0, checked = 0;
   for(int k = SVP_MIN_M15_BARS; k < tf.n15(); k += 3)
   {
      analyze(tf, k + 1, p);
      SVV_DashboardRows(g_svp, "XAUUSD", p, "x", rows);
      checked++;
      const bool setup = (g_svp.state != SVP_DECISION_WAIT);
      const bool has_sl = (std::string(rows[11]) != "STOP LOSS: N/A"), has_tp = (std::string(rows[12]) != "TAKE PROFIT: N/A"), has_rr = (std::string(rows[13]) != "RISK/REWARD: N/A");
      if(setup != has_sl || setup != has_tp || setup != has_rr) leaks++;
      if(!setup && std::string(rows[10]).find("ENTRY: N/A") != 0) leaks++;
   }
   check(leaks == 0 && checked > 300, "B04 over " + std::to_string(checked) + " bars: ENTRY / STOP LOSS / TAKE PROFIT / RISK-REWARD carry numbers if and only if "
                                      "the decision is a setup", std::to_string(leaks) + " leaks");
   // the panel on the chart
   chartsim::resetAll();
   SVC_Init("QSVP_", 0);
   for(int k = 0; k < SVC_LAYERS; k++) SVC_SetLayer((ENUM_SVC_LAYER)k, k == 0, 48);
   barPass(tf, st.i_confirm + 1, p, style, false);
   MqlArray<MqlRates> none;
   SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, style);
   int labels_n = (int)chartsim::countType("QSVP_DASH_R", OBJ_LABEL), panels = (int)chartsim::countType("QSVP_DASH_BG", OBJ_RECTANGLE_LABEL);
   bool texts = true; size_t longest = 0;
   SVV_DashboardRows(g_svp, "XAUUSD", p, "(DAILY, tick volume)", rows);
   for(int i = 0; i < SVV_ROWS; i++)
   {
      chartsim::Obj *o = chartsim::find("QSVP_DASH_R" + std::to_string(i));
      if(!o) { texts = false; continue; }
      const std::string shown = o->strs[(int)OBJPROP_TEXT];
      longest = std::max(longest, shown.size());
      const std::string want = std::string(rows[i]);
      if(shown != want && !(want.size() > SVV_ROW_CHARS && shown == want.substr(0, SVV_ROW_CHARS - 3) + "...")) texts = false;
      if(o->ints[(int)OBJPROP_YDISTANCE] != style.y + 6 + i * (style.font_size + 7)) texts = false;
   }
   chartsim::Obj *bg = chartsim::find("QSVP_DASH_BG");
   check(labels_n == 16 && panels == 1 && texts && longest <= SVV_ROW_CHARS && bg && bg->ints[(int)OBJPROP_YSIZE] == 16 * (style.font_size + 7) + 12 &&
         chartsim::find("QSVP_DASH_R9")->ints[(int)OBJPROP_COLOR] == style.bull,
         "B05 on the chart: ONE panel and 16 labels, one row each, evenly spaced (no row can overlap another), no row longer than 78 characters, the "
         "decision row in the bullish colour", std::to_string(labels_n) + " labels, " + std::to_string(panels) + " panel, longest " + std::to_string(longest));
   const long ops0 = chartOps();
   for(int r = 0; r < 20; r++) SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, style);
   const long idle_ops = chartOps() - ops0;
   SSvvStyle quiet = style; quiet.show_reason = false;
   SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, quiet);
   check(idle_ops == 0 && chartsim::countType("QSVP_DASH_R", OBJ_LABEL) == 15 && !chartsim::find("QSVP_DASH_R15"),
         "B06 re-rendering an unchanged decision 20 times touches nothing; with the WHY row switched off there are 15 labels",
         std::to_string(idle_ops) + " operations");
   // a long reason wraps at word boundaries onto at most two extra lines
   {
      barPass(tf, st.i_confirm + 1, p, style, false);
      auto rowText = [&](int i) -> std::string {
         chartsim::Obj *o = chartsim::find("QSVP_DASH_R" + std::to_string(i));
         return o ? o->strs[(int)OBJPROP_TEXT] : std::string();
      };
      // the WHY text as the trader reads it: the wrapped lines joined back together
      auto whyJoined = [&](int shown) -> std::string {
         std::string out = rowText(15);
         for(int i = 16; i < shown; i++) { const std::string t = rowText(i); out += " " + (t.size() > 5 ? t.substr(5) : std::string()); }
         return out;
      };
      auto whyFits = [&](int shown) -> bool {
         for(int i = 0; i < shown; i++) if(rowText(i).size() > (size_t)SVV_ROW_CHARS) return false;
         for(int i = 16; i < shown; i++) if(rowText(i).compare(0, 5, "     ") != 0) return false;
         return true;
      };
      const std::string why2 = "WAIT - BUY candidate 3/10, FAIL at LIQUIDITY SWEEP: BREAKOUT_CONFIRMED - taken 2026.01.18 06:45, 3 closes beyond the level";
      const std::string why3 = why2 + ": genuine breakout, the sweep is cancelled";
      g_svp.reason = why2;
      SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, style);
      const int n2 = (int)chartsim::countType("QSVP_DASH_R", OBJ_LABEL);
      const bool ok2 = (n2 == 17 && whyFits(n2) && whyJoined(n2) == "WHY: " + why2 &&
                        chartsim::find("QSVP_DASH_BG")->ints[(int)OBJPROP_YSIZE] == 17 * (style.font_size + 7) + 12);
      const std::string shown2 = rowText(15) + " / " + rowText(16);
      const long width2 = chartsim::find("QSVP_DASH_BG")->ints[(int)OBJPROP_XSIZE];
      g_svp.reason = why3;
      SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, style);
      const int n3 = (int)chartsim::countType("QSVP_DASH_R", OBJ_LABEL);
      const bool ok3 = (n3 == 18 && whyFits(n3) && whyJoined(n3) == "WHY: " + why3 &&
                        chartsim::find("QSVP_DASH_BG")->ints[(int)OBJPROP_YSIZE] == 18 * (style.font_size + 7) + 12 &&
                        chartsim::find("QSVP_DASH_BG")->ints[(int)OBJPROP_XSIZE] == width2);
      check(ok2 && ok3,
            "B06b a long reason wraps at word boundaries: " + std::to_string(why2.size()) + " characters take one extra line (17 labels), " +
            std::to_string(why3.size()) + " take two (18 labels); joined back the text is complete, no line exceeds 78 characters, the panel grows "
            "down by one row per line and does not get wider", shown2);
      // far too long: three lines at most, the last one ends in "...", and going back to a short reason removes the extra rows
      std::string huge = "WAIT -";
      for(int k = 0; k < 60; k++) huge += " word" + std::to_string(k);
      g_svp.reason = huge;
      SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, style);
      const int many = (int)chartsim::countType("QSVP_DASH_R", OBJ_LABEL);
      const std::string last = rowText(17);
      const bool fit = whyFits(many);
      g_svp.reason = "WAIT - short";
      SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, style);
      check(many == 18 && fit && last.size() >= 3 && last.substr(last.size() - 3) == "..." && chartsim::countType("QSVP_DASH_R", OBJ_LABEL) == 16 &&
            chartsim::find("QSVP_DASH_BG")->ints[(int)OBJPROP_YSIZE] == 16 * (style.font_size + 7) + 12,
            "B06d a reason of 500 characters: three lines at most (18 labels), the last ends in \"...\"; back to a short reason the two extra rows are "
            "deleted and the panel shrinks - no stale text is left behind", std::to_string(many) + " labels; last: " + last);
      // the other three corners: the panel stays on screen and the rows stay inside it
      bool corners = true; std::string bad;
      for(int corner = 1; corner <= 3; corner++)
      {
         SSvvStyle cs = style; cs.corner = corner; cs.x = 10; cs.y = 20;
         g_svp.reason = "WAIT - test";
         SVV_Render(tf.m15, st.i_confirm + 1, "XAUUSD", p, cs);
         chartsim::Obj *panel = chartsim::find("QSVP_DASH_BG");
         const long w = panel->ints[(int)OBJPROP_XSIZE], hh = panel->ints[(int)OBJPROP_YSIZE];
         const long px = panel->ints[(int)OBJPROP_XDISTANCE], py = panel->ints[(int)OBJPROP_YDISTANCE];
         const bool right = (corner == 2 || corner == 3), lower = (corner == 1 || corner == 2);
         // the panel's upper-left point, measured from the corner, must leave the whole panel on screen
         if(px != (right ? 10 + w : 10) || py != (lower ? 20 + hh : 20)) { corners = false; bad += " panel@" + std::to_string(corner); }
         long prev_y = -1;
         for(int i = 0; i < 16; i++)
         {
            chartsim::Obj *row = chartsim::find("QSVP_DASH_R" + std::to_string(i));
            const long ry = row->ints[(int)OBJPROP_YDISTANCE];
            const long depth = lower ? py - ry : ry - py;              // how far below the panel's top edge the row starts
            if(depth != 6 + i * (style.font_size + 7) || depth + style.font_size > hh) { corners = false; bad += " row" + std::to_string(i) + "@" + std::to_string(corner); }
            if(row->ints[(int)OBJPROP_ANCHOR] != (right ? ANCHOR_RIGHT_UPPER : ANCHOR_LEFT_UPPER) || row->ints[(int)OBJPROP_CORNER] != corner) { corners = false; bad += " anchor@" + std::to_string(corner); }
            if(prev_y >= 0 && std::labs(ry - prev_y) != style.font_size + 7) { corners = false; bad += " spacing@" + std::to_string(corner); }
            prev_y = ry;
         }
      }
      check(corners, "B06c in each of the other three corners the panel lies fully on screen, the rows stay inside it in reading order, and text in a "
                     "right-hand corner is right-anchored (it grows into the chart, not off the edge)", bad);
      g_svp.reason = "x";
   }
   // not ready
   SVP_DecisionReset(g_svp);
   g_svp.reason = "WAIT - history is loading (M15 0, H1 0, H4 0 bars)";
   SVV_Render(none, 0, "XAUUSD", p, style);
   int na = 0;
   for(int i = 2; i <= 14; i++) if(i != 9 && chartsim::find("QSVP_DASH_R" + std::to_string(i))->strs[(int)OBJPROP_TEXT].find("N/A") != std::string::npos) na++;
   check(na == 12 && chartsim::find("QSVP_DASH_R9")->strs[(int)OBJPROP_TEXT] == "FINAL DECISION: WAIT" && chartsim::countPrefix("QSVP_") == 17 &&
         chartsim::find("QSVP_DASH_R15")->strs[(int)OBJPROP_TEXT] == "WHY: WAIT - history is loading (M15 0, H1 0, H4 0 bars)",
         "B07 with no history the panel still shows: twelve N/A rows, FINAL DECISION: WAIT, and WHY says the history is loading - nothing else is drawn",
         std::to_string(na) + " N/A rows, " + std::to_string(chartsim::countPrefix("QSVP_")) + " objects");
   SVC_Shutdown();
}

// ================================================================== the terminal
// Drives the REAL OnInit / OnCalculate / OnTimer / OnChartEvent / OnDeinit of
// QSMC_SmcVpEngine.mq5. M15 candles are the feed; H1, H4 and (for an M5 chart)
// M5 series are derived from them the way a terminal would show them: the last
// bar of every series is the one that is still forming.
struct Term
{
   std::vector<MqlRates> all;        // M15 candles with their final values
   int forming = -1;                 // index in `all` of the bar that is forming (== all.size(): one synthetic bar past the end)
   int prev = 0;                     // what OnCalculate returned last
   long calls = 0;
   int m5sub = 0;
   MqlArray<datetime> time; MqlArray<double> o, h, l, c; MqlArray<long> tv, rv; MqlArray<int> sp;
   std::vector<std::string> journal;

   static sim::Bar toBar(const MqlRates &r) { return sim::Bar{r.time, r.open, r.high, r.low, r.close, (long)r.tick_volume}; }
   static sim::Bar openOnly(const MqlRates &r) { return sim::Bar{r.time, r.open, r.open, r.open, r.open, 1}; }
   static void merge(sim::Series &s, const long seconds, const sim::Bar &b, const bool final_values)
   {
      const datetime bt = b.time - b.time % seconds;
      if(s.bars.empty() || s.bars.back().time != bt) s.bars.push_back(sim::Bar{bt, b.open, b.high, b.low, b.close, final_values ? b.volume : 0});
      else
      {
         sim::Bar &a = s.bars.back();
         a.high = std::max(a.high, b.high); a.low = std::min(a.low, b.low); a.close = b.close;
         if(final_values) a.volume += b.volume;
      }
   }
   MqlRates barAt(const int i) const
   {
      if(i < (int)all.size()) return all[(size_t)i];
      MqlRates r{};                                   // one bar past the data: only its opening tick exists
      r.time = all.back().time + 900; r.open = r.high = r.low = r.close = all.back().close; r.tick_volume = 1;
      return r;
   }
   void openBar(const int i)
   {
      const MqlRates b = barAt(i);
      sim::S.series[sim::tfIndex(PERIOD_M15)].bars.push_back(openOnly(b));
      merge(sim::S.series[sim::tfIndex(PERIOD_H1)], 3600, openOnly(b), false);
      merge(sim::S.series[sim::tfIndex(PERIOD_H4)], 14400, openOnly(b), false);
      sim::S.series[sim::tfIndex(PERIOD_M5)].bars.push_back(sim::Bar{b.time, b.open, b.open, b.open, b.open, 1});
      m5sub = 0;
      forming = i;
      sim::S.now = sim::S.lastTickTime = b.time;
      sim::S.bid = sim::S.ask = b.open; sim::S.haveQuote = true;
   }
   // the forming bar closes and the next one opens with its first tick
   void step()
   {
      const MqlRates b = barAt(forming);
      sim::S.series[sim::tfIndex(PERIOD_M15)].bars.back() = toBar(b);
      merge(sim::S.series[sim::tfIndex(PERIOD_H1)], 3600, toBar(b), true);
      merge(sim::S.series[sim::tfIndex(PERIOD_H4)], 14400, toBar(b), true);
      sim::Series &m5 = sim::S.series[sim::tfIndex(PERIOD_M5)];
      for(int k = m5sub + 1; k <= 2; k++) m5.bars.push_back(sim::Bar{b.time + k * 300, b.close, b.close, b.close, b.close, 1});
      openBar(forming + 1);
   }
   // a tick inside the forming bar, `seconds` after its open
   void tickAt(const int seconds)
   {
      const MqlRates b = barAt(forming);
      sim::S.now = sim::S.lastTickTime = b.time + seconds;
      sim::Series &m5 = sim::S.series[sim::tfIndex(PERIOD_M5)];
      while(m5sub < 2 && seconds >= (m5sub + 1) * 300) { m5sub++; m5.bars.push_back(sim::Bar{b.time + m5sub * 300, b.open, b.open, b.open, b.open, 1}); }
   }
   // history: bars [0, closed) are closed, bar `closed` is forming
   void boot(const std::vector<MqlRates> &bars, const int closed, const ENUM_TIMEFRAMES chart_tf = PERIOD_M15)
   {
      sim::reset();
      chartsim::resetAll(); chartsim::bound.clear(); chartsim::buffersBound = 0; chartsim::timerSeconds = 0; chartsim::timerSets = 0; chartsim::timerKills = 0;
      const ENUM_TIMEFRAMES tfs[6] = {PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1, PERIOD_W1};
      for(int i = 0; i < 6; i++) { sim::S.series[i].tf = tfs[i]; sim::S.series[i].bars.clear(); }
      all = bars; forming = -1; prev = 0; calls = 0; journal.clear();
      time.v.clear(); o.v.clear(); h.v.clear(); l.v.clear(); c.v.clear(); tv.v.clear(); rv.v.clear(); sp.v.clear();
      _Period = chart_tf; _Symbol = "XAUUSD"; _Point = 0.01; _Digits = 2;
      openBar(0);
      for(int i = 0; i < closed; i++) step();
      sim::S.onPrint = [this](const std::string &line) { journal.push_back(line); };
   }
   void chartTf(const ENUM_TIMEFRAMES tf)
   {
      _Period = tf; prev = 0;
      time.v.clear(); o.v.clear(); h.v.clear(); l.v.clear(); c.v.clear(); tv.v.clear(); rv.v.clear(); sp.v.clear();
   }
   int ratesTotal() const { return sim::S.series[sim::tfIndex(_Period)].size(); }
   int calc()
   {
      const sim::Series &s = sim::S.series[sim::tfIndex(_Period)];
      const size_t n = (size_t)s.size(), old = time.v.size();
      time.v.resize(n); o.v.resize(n); h.v.resize(n); l.v.resize(n); c.v.resize(n); tv.v.resize(n); rv.v.resize(n); sp.v.resize(n);
      for(size_t i = (old > 2 ? old - 2 : 0); i < n; i++)
      {
         const sim::Bar &b = s.bars[i];
         time.v[i] = b.time; o.v[i] = b.open; h.v[i] = b.high; l.v[i] = b.low; c.v[i] = b.close; tv.v[i] = b.volume; rv.v[i] = 0; sp.v[i] = 0;
      }
      chartsim::sizeBuffers(n);
      prev = OnCalculate((int)n, prev, time, o, h, l, c, tv, rv, sp);
      calls++;
      return prev;
   }
   // value of buffer `b` on the newest closed chart bar
   static double closedCell(const MqlArray<double> &buf) { return buf.v.size() >= 2 ? buf.v[buf.v.size() - 2] : EMPTY_VALUE; }
   int journalCount(const std::string &needle) const
   {
      int n = 0;
      for(const std::string &line : journal) if(line.find(needle) != std::string::npos) n++;
      return n;
   }
};

// inputs a scenario may change; every scenario starts from the shipped defaults
static void defaultInputs()
{
   InpSveAlerts = false; InpSveLog = true; InpSveRunSelfTest = true;
   InpSveShowPrimary = true; InpSveShowSecondary = true; InpSveShowVolume = true; InpSveShowHistogram = false; InpSveShowOptional = false;
   InpSveProfileKind = SVP_VP_DAILY; InpSveBackfillBars = 96; InpSveM15Bars = 1500; InpSveH1Bars = 600; InpSveH4Bars = 300;
   InpSveMinRR = 2.00; InpSveVpRequired = true; InpSveLiveSignals = 2; InpSveHistorySignals = 8; InpSveRowTicks = 0; InpSveUseRealVolume = false;
   InpSveShowReason = true; InpSveCorner = 0; InpSveFontSize = 9; InpSveChartShift = true;
}

static std::string objectDigest(const std::string &prefix)
{
   std::string d;
   for(const auto &kv : chartsim::C.objects)
   {
      if(kv.first.compare(0, prefix.size(), prefix) != 0) continue;
      const chartsim::Obj &ob = kv.second;
      char b[200];
      const auto t = ob.strs.find((int)OBJPROP_TEXT);
      snprintf(b, sizeof b, "%s|%d|%lld|%.4f|%lld|%.4f|", kv.first.c_str(), (int)ob.type, (long long)ob.t[0], ob.p[0], (long long)ob.t[1], ob.p[1]);
      d += b; d += (t == ob.strs.end() ? "" : t->second); d += "\n";
   }
   return d;
}

static std::string dashRow(const int i)
{
   chartsim::Obj *ob = chartsim::find("QSVP_DASH_R" + std::to_string(i));
   return ob ? ob->strs[(int)OBJPROP_TEXT] : "<missing>";
}

static void unitHost()
{
   g_group = "host";
   Story st = makeStory(1);
   const int boot_at = st.i_low1 - 20;                    // the indicator is attached 20 bars before the first equal low
   Term T;
   defaultInputs();
   check(!InpSveShowHistogram && !InpSveShowOptional && !InpSveAlerts && InpSveProfileKind == SVP_VP_DAILY && InpSveVpRequired && InpSveMinRR == 2.0,
         "H01 shipped defaults: primary + secondary + volume layers on, histogram and optional layer OFF, alerts off, daily profile, volume context required, minimum RR 2");
   // --- attach
   T.boot(st.bars, boot_at);
   chartsim::addUserObject("MyTrendline", OBJ_TREND, T0, 2000.0);
   chartsim::addUserObject("QSMC_PRIMARY_1", OBJ_ARROW, T0, 2001.0);
   chartsim::addUserObject("QSVP_stale_from_last_session", OBJ_TEXT, T0, 2002.0);
   const int init = OnInit();
   check(init == INIT_SUCCEEDED && chartsim::buffersBound == 5 && chartsim::shortName.find("QSMC SMC+VP Engine") == 0 && chartsim::timerSeconds == 2 &&
         T.journalCount("self-tests PASS") == 1 && T.journalCount("display only, no orders") == 1 && T.journalCount("broker tick volume") == 1 &&
         !chartsim::find("QSVP_stale_from_last_session") && chartsim::find("MyTrendline") && chartsim::find("QSMC_PRIMARY_1") && sim::S.sendCount == 0,
         "H02 OnInit: succeeds, binds 5 buffers, runs both self-tests, states 'display only, no orders' and the volume source, arms a 2 s start-up "
         "timer, removes only its own left-overs");
   const long created0 = chartsim::C.created;
   T.calc();
   const int objects_first = (int)chartsim::countPrefix("QSVP_");
   check(g_sve_started && g_sve_runs == 1 && g_svp.ready && objects_first >= 17 && objects_first <= 60 && chartsim::C.created - created0 == objects_first &&
         dashRow(0) == "MARKET: XAUUSD" && dashRow(9) == "FINAL DECISION: WAIT" && T.closedCell(g_sve_decision) == 0.0 && T.closedCell(g_sve_entry) == EMPTY_VALUE,
         "H03 first OnCalculate: 96 closed bars replayed silently, ONE render - " + std::to_string(objects_first) + " objects created once, dashboard up, "
         "decision buffer 0 (WAIT), plan buffers empty", std::to_string(g_sve_runs) + " runs, " + std::to_string(objects_first) + " objects");
   // --- between two M15 closes: nothing
   {
      const int runs0 = g_sve_runs; const long ops0 = chartOps(); const long redraw0 = chartsim::C.redraws; const int builds0 = g_svp_vp_builds;
      const int idle0 = g_sve_idle;
      for(int i = 1; i <= 500; i++) { T.tickAt(1 + (i * 898) / 500); T.calc(); }
      check(g_sve_runs == runs0 && chartOps() == ops0 && chartsim::C.redraws == redraw0 && g_svp_vp_builds == builds0 && g_sve_idle == idle0 + 500,
            "H04 500 ticks inside one M15 bar: 0 engine passes, 0 chart operations, 0 profile rebuilds - all work happens once per closed bar",
            std::to_string(g_sve_runs - runs0) + " runs, " + std::to_string(chartOps() - ops0) + " chart ops");
   }
   // --- a bar closes: exactly one pass
   {
      const int runs0 = g_sve_runs;
      T.step(); T.calc(); T.calc(); T.calc();
      check(g_sve_runs == runs0 + 1, "H05 a new M15 bar: exactly ONE pass, however many ticks follow");
   }
   // --- walk to the end of the story
   int max_objects = 0, dup = 0; long created_walk = chartsim::C.created;
   double dec_confirm = 99, e_confirm = 0, sl_confirm = 0, tp_confirm = 0, rr_confirm = 0, dec_before = 99, e_before = 0;
   std::string rows_confirm, digest_confirm; int objects_confirm = 0; bool buf_matches = true; int decisions_buy = 0;
   const int runs_before_walk = g_sve_runs; int bars_walked = 0;
   Term mid;                                               // snapshot source for the re-init scenarios below
   while(T.forming <= st.i_end)
   {
      T.step(); T.calc(); T.tickAt(300); T.calc();
      bars_walked++;
      const int closed = T.forming - 1;
      max_objects = std::max(max_objects, (int)chartsim::countPrefix("QSVP_"));
      dup += exactDuplicates("QSVP_");
      const double cell = T.closedCell(g_sve_decision);
      if(cell != (double)((int)g_svp.state)) buf_matches = false;
      if((cell != 0.0) != (T.closedCell(g_sve_entry) != EMPTY_VALUE)) buf_matches = false;
      if(cell == 1.0) decisions_buy++;
      if(closed == st.i_confirm - 1) { dec_before = cell; e_before = T.closedCell(g_sve_entry); }
      if(closed == st.i_confirm)
      {
         dec_confirm = cell; e_confirm = T.closedCell(g_sve_entry); sl_confirm = T.closedCell(g_sve_stop); tp_confirm = T.closedCell(g_sve_target);
         rr_confirm = T.closedCell(g_sve_rr);
         for(int i = 9; i <= 13; i++) rows_confirm += dashRow(i) + " | ";
         digest_confirm = objectDigest("QSVP_"); objects_confirm = (int)chartsim::countPrefix("QSVP_");
      }
   }
   created_walk = chartsim::C.created - created_walk;
   check(dec_before == 0.0 && e_before == EMPTY_VALUE && dec_confirm == 1.0 && near(e_confirm, 2122.60) && near(sl_confirm, 2116.84) && near(tp_confirm, 2135.20) &&
         near(rr_confirm, 2.1875, 1e-3) && rows_confirm.find("FINAL DECISION: BUY SETUP | ENTRY: 2122.60 | STOP LOSS: 2116.84 | TAKE PROFIT: 2135.20") == 0,
         "H06 the bar before the confirmation: buffers 0 / empty; the confirming bar: decision +1, entry 2122.60, stop 2116.84, target 2135.20, RR 2.19 "
         "in the buffers AND on the dashboard", rows_confirm);
   check(buf_matches && decisions_buy == 1 && g_sve_runs - runs_before_walk == bars_walked,
         "H07 over " + std::to_string(bars_walked) + " closed bars: one pass per bar, the buffers always equal the decision shown, plan cells are filled "
         "only on a setup bar, and the setup occupies exactly ONE bar", std::to_string(decisions_buy) + " BUY cells, " + std::to_string(g_sve_runs - runs_before_walk) + " runs");
   check(max_objects <= 60 && dup == 0 && created_walk < 2 * bars_walked,
         "H08 the chart never held more than " + std::to_string(max_objects) + " objects, never two identical ones; " + std::to_string(created_walk) +
         " objects were created over the whole walk", std::to_string(dup) + " duplicates");
   check(T.journalCount("BUY SETUP - all 10 confirmations hold") == 1 && chartsim::C.alerts.empty() && sim::S.sendCount == 0 && sim::S.apiErrors.empty() && sim::S.fmtErrors.empty(),
         "H09 the journal carries the setup once (one line per decision CHANGE), no alert with alerts off, no trade request ever, no API misuse",
         std::to_string(T.journalCount("BUY SETUP - all 10 confirmations hold")) + " journal lines, " + std::to_string(sim::S.apiErrors.size()) + " api errors" +
         (sim::S.apiErrors.empty() ? "" : ": " + sim::S.apiErrors[0]));
   // --- remove: everything of ours goes, nothing else
   {
      OnDeinit(REASON_REMOVE);
      bool only_ours = true;
      for(const std::string &n : chartsim::C.deletedNames) if(n.compare(0, 5, "QSVP_") != 0) only_ours = false;
      check(chartsim::countPrefix("QSVP_") == 0 && only_ours && chartsim::find("MyTrendline") && chartsim::find("QSMC_PRIMARY_1") && chartsim::timerSeconds == 0 &&
            near(chartsim::find("MyTrendline")->p[0], 2000.0) && near(chartsim::find("QSMC_PRIMARY_1")->p[0], 2001.0),
            "H10 OnDeinit removes every QSVP_ object, kills the timer and leaves the operator's line and nadir2's object untouched");
   }
   // --- re-init on the confirming bar: the same picture, no duplicates, no second alert
   {
      defaultInputs(); InpSveAlerts = true;
      T.boot(st.bars, st.i_confirm + 1);
      OnInit(); T.calc();
      const std::string fresh = objectDigest("QSVP_");
      const int n0 = (int)chartsim::countPrefix("QSVP_");
      const size_t alerts0 = chartsim::C.alerts.size();
      const bool same_as_walk = (fresh == digest_confirm);
      for(int r = 0; r < 5; r++) { OnDeinit(REASON_PARAMETERS); OnInit(); T.prev = 0; T.calc(); }
      check(same_as_walk && n0 == objects_confirm && objectDigest("QSVP_") == fresh && (int)chartsim::countPrefix("QSVP_") == n0 && alerts0 == 0 && chartsim::C.alerts.empty() &&
            T.closedCell(g_sve_decision) == 1.0 && near(T.closedCell(g_sve_stop), 2116.84),
            "H11 attached fresh on the confirming bar the chart is IDENTICAL to the one that was open all along (" + std::to_string(n0) + " objects, same "
            "anchors and texts); five re-initialisations leave the same objects, no duplicate, and a setup rebuilt from history is not announced",
            std::string(same_as_walk ? "" : "differs from the continuous run; ") + std::to_string(n0) + " vs " + std::to_string(objects_confirm) + " objects, alerts " +
            std::to_string(chartsim::C.alerts.size()));
      // live: the next setup IS announced once
      int sweep2 = -1, confirm2 = -1;
      Story two = makeDoubleStory(sweep2, confirm2);
      T.boot(two.bars, st.i_confirm - 5);
      OnInit(); T.calc();
      while(T.forming <= two.i_end) { T.step(); T.calc(); T.tickAt(60); T.calc(); }
      check(chartsim::C.alerts.size() == 2 && chartsim::C.alerts[0].find("BUY SETUP") != std::string::npos && chartsim::C.alerts[1].find("BUY SETUP") != std::string::npos &&
            chartsim::C.alerts[0] != chartsim::C.alerts[1] && T.journalCount("BUY SETUP - all 10 confirmations hold") == 2,
            "H12 with alerts on, two separate setups that confirm while the indicator runs give exactly two alerts (one each)",
            std::to_string(chartsim::C.alerts.size()) + " alerts");
      OnDeinit(REASON_REMOVE);
   }
   // --- chart timeframe: the decision does not depend on it
   {
      defaultInputs();
      std::string rows15, rows5, rows60, dig15, dig5, dig60;
      const ENUM_TIMEFRAMES tfs[3] = {PERIOD_M15, PERIOD_M5, PERIOD_H1};
      std::string *rows[3] = {&rows15, &rows5, &rows60}; std::string *digs[3] = {&dig15, &dig5, &dig60};
      double cells[3] = {0, 0, 0};
      for(int k = 0; k < 3; k++)
      {
         T.boot(st.bars, st.i_confirm + 1, tfs[k]);
         OnInit(); T.calc();
         for(int i = 0; i < SVV_ROWS; i++) *rows[k] += dashRow(i) + "\n";
         *digs[k] = objectDigest("QSVP_");
         cells[k] = T.closedCell(g_sve_decision);
         OnDeinit(REASON_CHARTCHANGE);
      }
      check(rows15 == rows5 && rows15 == rows60 && dig15 == dig5 && dig15 == dig60 && cells[0] == 1.0 && cells[1] == 1.0 && cells[2] == 1.0 &&
            rows15.find("FINAL DECISION: BUY SETUP") != std::string::npos,
            "H13 the same moment on an M5, an M15 and an H1 chart: identical dashboard, identical objects, the same decision in the buffer - the "
            "analysis is always M15 + H1 + H4 whatever the chart shows");
      // on a lower timeframe the decision in force is carried on every closed chart bar
      T.boot(st.bars, st.i_confirm + 1, PERIOD_M5);
      OnInit(); T.calc();
      const int runs0 = g_sve_runs;
      T.tickAt(300); T.calc();
      const double c1 = T.closedCell(g_sve_decision);
      T.tickAt(600); T.calc();
      const double c2 = T.closedCell(g_sve_decision);
      check(c1 == 1.0 && c2 == 1.0 && g_sve_runs == runs0 && near(T.closedCell(g_sve_stop), 2116.84),
            "H14 M5 chart: two more M5 bars close inside the same M15 bar - no new pass, and each closed M5 bar carries the decision in force");
      OnDeinit(REASON_REMOVE);
   }
   // --- history that is not there yet
   {
      defaultInputs();
      std::vector<MqlRates> few(st.bars.begin(), st.bars.begin() + 300);            // 75 H1 bars, 19 H4 bars: not enough
      T.boot(few, 299);
      OnInit(); T.calc();
      int na = 0;
      for(int i = 2; i <= 14; i++) if(i != 9 && dashRow(i).find("N/A") != std::string::npos) na++;
      const bool waiting = (!g_sve_started && na == 12 && dashRow(9) == "FINAL DECISION: WAIT" && dashRow(15).find("history not ready") != std::string::npos &&
                            T.closedCell(g_sve_decision) == EMPTY_VALUE && (int)chartsim::countPrefix("QSVP_") == 17);
      const int runs0 = g_sve_runs;
      for(int i = 1; i <= 50; i++) { T.tickAt(1); T.calc(); }                       // 50 ticks within the same second: one attempt, not 50
      const bool throttled = (g_sve_runs == runs0);
      T.tickAt(8); T.calc();                                                        // 5 s later the same bar is tried again
      check(waiting && throttled && g_sve_runs == runs0 + 1 && !g_sve_started,
            "H15 too little H4 history: every analysis row is N/A, FINAL DECISION: WAIT, WHY names what is missing, the buffers stay EMPTY (not 0), "
            "and the retry is throttled to one attempt per 5 s", dashRow(15) + " | N/A rows " + std::to_string(na) + " runs " + std::to_string(g_sve_runs - runs0));
      OnDeinit(REASON_REMOVE);
      // no bars at all
      Term E; std::vector<MqlRates> one(st.bars.begin(), st.bars.begin() + 1);
      E.boot(one, 0);
      const int rc = OnInit();
      E.calc();
      check(rc == INIT_SUCCEEDED && !g_sve_started && dashRow(15).find("WHY: WAIT - M15 history is loading") == 0 && (int)chartsim::countPrefix("QSVP_") == 17,
            "H16 a chart with no closed M15 bar at all: no crash, the panel says the history is loading", dashRow(15));
      OnDeinit(REASON_REMOVE);
   }
   // --- a closed market: no tick ever arrives
   {
      defaultInputs();
      T.boot(st.bars, st.i_confirm + 1);
      OnInit();
      const bool armed = (chartsim::timerSeconds == 2 && (int)chartsim::countPrefix("QSVP_") == 0);
      OnTimer();
      const bool drawn = (g_sve_started && dashRow(9) == "FINAL DECISION: BUY SETUP" && (int)chartsim::countPrefix("QSVP_") == objects_confirm);
      const bool killed = (chartsim::timerSeconds == 0 && chartsim::timerKills == 1);
      T.calc();                                                                      // the first tick on Monday: nothing new to analyse, the buffers catch up
      check(armed && drawn && killed && g_sve_runs == 1 && T.closedCell(g_sve_decision) == 1.0,
            "H17 attached while the market is closed (no tick): the 2 s timer runs the first pass, then is killed; the first tick later only publishes the buffers");
      OnDeinit(REASON_REMOVE);
   }
   // --- layers
   {
      defaultInputs(); InpSveShowSecondary = false; InpSveShowVolume = false;
      T.boot(st.bars, st.i_confirm + 1);
      OnInit(); T.calc();
      const int primary_only = (int)chartsim::countPrefix("QSVP_");
      // 17 dashboard objects + the entry zone, three lines and their three captions
      const bool only_primary = (SVC_CountLayer(SVC_LAYER_SECONDARY) == 0 && SVC_CountLayer(SVC_LAYER_VOLUME) == 0 && primary_only == 17 + 7 &&
                                 chartsim::countPrefix("QSVP_DASH_") == 17 && dashRow(9) == "FINAL DECISION: BUY SETUP");
      OnDeinit(REASON_PARAMETERS);
      defaultInputs(); InpSveShowHistogram = true; InpSveShowOptional = true;
      OnInit(); T.prev = 0; T.calc();
      const int everything = (int)chartsim::countPrefix("QSVP_");
      const bool all_on = (SVC_CountLayer(SVC_LAYER_DETAIL) > 0 && SVC_CountLayer(SVC_LAYER_DETAIL) <= 40 && everything > objects_confirm && everything <= 208 &&
                           exactDuplicates("QSVP_") == 0);
      OnDeinit(REASON_PARAMETERS);
      defaultInputs(); InpSveShowPrimary = false;
      OnInit(); T.prev = 0; T.calc();
      check(only_primary && all_on && chartsim::countPrefix("QSVP_DASH_") == 0 && T.closedCell(g_sve_decision) == 1.0,
            "H18 layers: primary only = " + std::to_string(primary_only) + " objects (dashboard + the setup); default = " + std::to_string(objects_confirm) +
            "; histogram + optional on = " + std::to_string(everything) + "; primary off = no panel, the buffers still carry the decision",
            std::to_string(primary_only) + " / " + std::to_string(everything));
      OnDeinit(REASON_REMOVE);
   }
   // --- visible-range profile
   {
      defaultInputs(); InpSveProfileKind = SVP_VP_RANGE;
      T.boot(st.bars, st.i_confirm + 1);
      chartsim::C.firstVisibleBar = 120; chartsim::C.visibleBars = 100;
      OnInit(); T.calc();
      const bool range_profile = (g_svp_profile.valid && g_svp_profile.kind == SVP_VP_RANGE && dashRow(7).find("(VISIBLE RANGE") != std::string::npos);
      const double poc0 = g_svp_profile.poc; const int bars0 = g_svp_profile.bars;
      const int runs0 = g_sve_runs;
      long lp = 0; double dp = 0.0; string sp = "";
      OnChartEvent(CHARTEVENT_CHART_CHANGE, lp, dp, sp);                              // a redraw that moved nothing
      OnTimer();
      const bool no_news = (g_sve_runs == runs0);
      chartsim::C.firstVisibleBar = 60; chartsim::C.visibleBars = 50;                // the operator scrolled and zoomed
      OnChartEvent(CHARTEVENT_CHART_CHANGE, lp, dp, sp);
      OnTimer();
      const bool moved = (g_sve_runs == runs0 + 1 && g_svp_profile.valid && g_svp_profile.bars < bars0);
      check(range_profile && bars0 == 100 && no_news && moved && g_svp_profile.bars == 50 && chartsim::timerSeconds == 2,
            "H19 visible-range profile: built from the bars on screen (" + std::to_string(bars0) + " closed M15 bars, POC " + num(poc0) + "); a chart event "
            "that moved nothing costs nothing, scrolling rebuilds it once; the timer stays on only in this mode",
            dashRow(7) + " bars " + std::to_string(bars0) + " -> " + std::to_string(g_svp_profile.bars));
      OnDeinit(REASON_REMOVE);
   }
   // --- the terminal reloads the history (prev_calculated = 0 again)
   {
      defaultInputs();
      T.boot(st.bars, st.i_confirm + 1);
      OnInit(); T.calc();
      const std::string before = objectDigest("QSVP_"); const int runs0 = g_sve_runs; const long created0b = chartsim::C.created;
      T.prev = 0; T.calc();
      check(objectDigest("QSVP_") == before && g_sve_runs == runs0 && chartsim::C.created == created0b && T.closedCell(g_sve_decision) == 1.0 &&
            near(T.closedCell(g_sve_target), 2135.20),
            "H20 the terminal recalculates from scratch (prev_calculated = 0): the buffers are refilled, no object is created, no pass is repeated");
      OnDeinit(REASON_REMOVE);
   }
   // --- hostile inputs
   {
      defaultInputs();
      InpSveM15Bars = -5; InpSveH1Bars = 0; InpSveH4Bars = 999999; InpSveBackfillBars = -3; InpSveLiveSignals = 0; InpSveFontSize = 500; InpSveCorner = 9;
      InpSveMinRR = -1.0; InpSveRowTicks = -7;
      T.boot(st.bars, st.i_confirm + 1);
      const int rc = OnInit(); T.calc();
      check(rc == INIT_SUCCEEDED && g_sve_started && g_sve_m15_bars >= SVP_MIN_M15_BARS && g_sve_h1_bars >= SVP_MIN_H1_BARS && g_sve_h4_bars <= 2000 &&
            g_sve_backfill == 0 && g_sve_style.live_signals == 1 && g_sve_style.font_size == 20 && g_sve_style.corner == 0 && g_sve_params.min_rr > 0.0 &&
            g_sve_params.vp_row_ticks >= 0 && (int)chartsim::countPrefix("QSVP_") <= 60,
            "H21 nonsense inputs (negative history sizes, RR -1, font 500, corner 9): clamped to safe values, the indicator still starts and analyses",
            "m15 " + std::to_string(g_sve_m15_bars) + " h1 " + std::to_string(g_sve_h1_bars) + " h4 " + std::to_string(g_sve_h4_bars) + " rr " + num(g_sve_params.min_rr));
      OnDeinit(REASON_REMOVE);
      defaultInputs();
   }
   // --- the right margin the captions live in
   {
      defaultInputs();
      T.boot(st.bars, st.i_confirm + 1);
      OnInit(); T.calc();
      // every level caption starts where the level lines end, to the right of the newest bar
      const datetime edge = st.bars[(size_t)st.i_confirm].time;
      int column = 0, inside = 0, lines_past_column = 0; datetime column_at = 0;
      for(const auto &kv : chartsim::C.objects)
      {
         const chartsim::Obj &ob = kv.second;
         if(kv.first.compare(0, 5, "QSVP_") != 0) continue;
         if(ob.type == OBJ_TEXT && kv.first.compare(0, 9, "QSVP_STR_") != 0) { if(ob.t[0] > edge) { column++; column_at = ob.t[0]; } else inside++; }
      }
      for(const auto &kv : chartsim::C.objects)
         if(kv.first.compare(0, 5, "QSVP_") == 0 && (kv.second.type == OBJ_TREND || kv.second.type == OBJ_RECTANGLE) && std::max(kv.second.t[0], kv.second.t[1]) > column_at) lines_past_column++;
      const bool untouched = (chartsim::C.shiftSets == 0 && chartsim::C.shift && T.journalCount("Chart Shift") == 0);
      OnDeinit(REASON_REMOVE);
      // Chart Shift off: the host turns it on (once) and says so
      T.boot(st.bars, st.i_confirm + 1);
      chartsim::C.shift = false;
      OnInit(); T.calc();
      const bool turned_on = (chartsim::C.shift && chartsim::C.shiftSets == 1 && T.journalCount("Chart Shift was off: turned ON") == 1);
      OnDeinit(REASON_REMOVE);
      // ... unless the operator said no: the setting is left alone, the journal explains what is missing
      defaultInputs(); InpSveChartShift = false;
      T.boot(st.bars, st.i_confirm + 1);
      chartsim::C.shift = false;
      OnInit(); T.calc();
      const bool left_alone = (!chartsim::C.shift && chartsim::C.shiftSets == 0 && T.journalCount("Chart Shift is off") == 1 &&
                               dashRow(9) == "FINAL DECISION: BUY SETUP");
      check(column >= 6 && inside == 0 && lines_past_column == 0 && untouched && turned_on && left_alone,
            "H22 the level captions (" + std::to_string(column) + " on the confirming bar) all start right of the newest bar, where no line or box reaches; that "
            "margin is the terminal's Chart Shift: when it is off the host turns it on once and says so in the journal, or - with InpSveChartShift=false - "
            "leaves the chart alone and explains what is not visible",
            std::to_string(column) + " in the column, " + std::to_string(inside) + " inside, " + std::to_string(lines_past_column) + " lines past it | " +
            (untouched ? "1" : "0") + (turned_on ? "1" : "0") + (left_alone ? "1" : "0"));
      OnDeinit(REASON_REMOVE);
      defaultInputs();
   }
}

// ================================================================== commands
static int runUnits(const std::string &only)
{
   struct G { const char *name; void (*fn)(); };
   const G groups[] = {{"structure", unitStructure}, {"liquidity", unitLiquidity}, {"sweep", unitSweep}, {"zones", unitZones}, {"volume", unitVolume},
                       {"decision", unitDecision}, {"signal", unitSignal}, {"chart", unitChart}, {"dashboard", unitDashboard}, {"host", unitHost}};
   bool any = false;
   for(const G &g : groups)
   {
      if(!only.empty() && only != g.name) continue;
      any = true;
      const int p0 = g_pass, f0 = g_fail;
      try { g.fn(); }
      catch(const std::exception &e) { g_fail++; printf("FAIL  %s aborted: %s\n", g.name, e.what()); }
      printf("GROUP %s: %d passed, %d failed\n", g.name, g_pass - p0, g_fail - f0);
   }
   if(!any) { fprintf(stderr, "unknown group: %s\n", only.c_str()); return 2; }
   printf("smcvp-engine: %d passed, %d failed\n", g_pass, g_fail);
   return g_fail ? 1 : 0;
}

// ------------------------------------------------------------------ real history
// The same M1 bid/ask CSV layout tools/qats_backtest.py fetches (Dukascopy):
// timestamp,open_bid,high_bid,low_bid,close_bid,open_ask,...,volume_bid,volume_ask
static bool usDst(const datetime utc)
{
   // US daylight time: second Sunday of March 07:00 UTC -> first Sunday of November 06:00 UTC
   int y, m, d;
   sim::civilFromDays(utc / 86400, y, m, d);
   const datetime mar1 = sim::makeTime(y, 3, 1);
   const datetime start = mar1 + (datetime)(((7 - sim::dayOfWeek(mar1)) % 7) + 7) * 86400 + 7 * 3600;
   const datetime nov1 = sim::makeTime(y, 11, 1);
   const datetime end = nov1 + (datetime)((7 - sim::dayOfWeek(nov1)) % 7) * 86400 + 6 * 3600;
   return utc >= start && utc < end;
}
// "New York close" broker clock (UTC+2 in winter, UTC+3 during US daylight time):
// five daily candles a week, the daily break at 00:00 - the operator's broker convention.
static datetime toServer(const datetime utc) { return utc + (usDst(utc) ? 3 : 2) * 3600; }

static datetime parseDate(const std::string &text)
{
   int y = 0, m = 1, d = 1, h = 0, mi = 0;
   if(sscanf(text.c_str(), "%d-%d-%d %d:%d", &y, &m, &d, &h, &mi) < 3) sscanf(text.c_str(), "%d.%d.%d %d:%d", &y, &m, &d, &h, &mi);
   return sim::makeTime(y, m, d, h, mi, 0);
}

static std::vector<std::string> listCsv(const std::string &dir)
{
   std::vector<std::string> files;
   const std::string cmd = "ls -1 \"" + dir + "\"/*.csv 2>/dev/null";
   FILE *pp = popen(cmd.c_str(), "r");
   if(!pp) return files;
   char buf[4096];
   while(fgets(buf, sizeof buf, pp))
   {
      std::string f(buf);
      while(!f.empty() && (f.back() == '\n' || f.back() == '\r')) f.pop_back();
      if(!f.empty()) files.push_back(f);
   }
   pclose(pp);
   std::sort(files.begin(), files.end());
   return files;
}

struct FeedStats { long m1 = 0, m15 = 0, bad = 0, overlap = 0; datetime first = 0, last = 0; };

// M1 bid candles -> M15 candles on the server clock, prices on a `grid` (0.01 for
// the operator's 2-digit gold; 1.0 = whole points, which makes a mirrored replay exact).
// tick_volume: the feed's bid + ask volume x 10^4, at least 1 - a PROXY for the
// broker's tick count, good for the shape of a profile, not for its absolute size.
static std::vector<MqlRates> loadM15(const std::string &dir, const datetime from, const datetime to, const double grid, const double scale, FeedStats &fs)
{
   std::vector<MqlRates> out;
   double vol_acc = 0.0;
   datetime last_st = 0;
   auto flush = [&]() { if(!out.empty()) out.back().tick_volume = std::max<long>(1, std::llround(vol_acc * 10000.0)); vol_acc = 0.0; };
   auto q = [&](const double v) { return std::round(v * scale / grid) * grid; };
   for(const std::string &file : listCsv(dir))
   {
      std::ifstream in(file);
      if(!in) continue;
      std::string line;
      std::getline(in, line);
      while(std::getline(in, line))
      {
         int y, mo, d, h, mi, sec;
         if(sscanf(line.c_str(), "%d-%d-%d %d:%d:%d", &y, &mo, &d, &h, &mi, &sec) != 6) { fs.bad++; continue; }
         const datetime st = toServer(sim::makeTime(y, mo, d, h, mi, sec));
         // The yearly files of the dataset OVERLAP at their seams (up to 23 hours of
         // the same minutes in two files). A row that does not move time forward
         // is a repeat: fed again it would send the clock backwards and leave
         // duplicate / out-of-order bars in the series.
         if(st <= last_st) { fs.overlap++; continue; }
         last_st = st;
         if(st < from) continue;
         if(to > 0 && st >= to) break;
         const char *c = strchr(line.c_str(), ',');
         if(!c) { fs.bad++; continue; }
         double v[10]; int got = 0;
         while(c && got < 10) { v[got++] = atof(c + 1); c = strchr(c + 1, ','); }
         if(got < 10 || !(v[2] > 0.0) || v[1] < v[2]) { fs.bad++; continue; }
         fs.m1++;
         const datetime bt = st - st % 900;
         if(out.empty() || out.back().time != bt)
         {
            flush();
            MqlRates r{};
            r.time = bt; r.open = q(v[0]); r.high = q(v[1]); r.low = q(v[2]); r.close = q(v[3]); r.tick_volume = 1; r.real_volume = 0; r.spread = 0;
            out.push_back(r);
         }
         else
         {
            MqlRates &r = out.back();
            r.high = std::max(r.high, q(v[1])); r.low = std::min(r.low, q(v[2])); r.close = q(v[3]);
         }
         vol_acc += v[8] + v[9];
      }
   }
   flush();
   fs.m15 = (long)out.size();
   if(!out.empty()) { fs.first = out.front().time; fs.last = out.back().time; }
   return out;
}

struct SetupRow
{
   datetime confirmed = 0, origin = 0; int direction = 0; std::string type;
   double entry = 0, stop = 0, target = 0, rr = 0;
   int outcome = 0;            // +1 target first, -1 stop first, -2 both inside one bar (counted as stop), 0 neither within the horizon
   int bars_to_outcome = 0;
   std::string registry_end;   // the engine's own lifecycle verdict
};

struct RawSnap { datetime t = 0; int state = 0; double entry = 0, stop = 0, target = 0; int buy = 0, sell = 0; };

static RawSnap rawNow(const datetime t)
{
   RawSnap r; r.t = t; r.state = (int)g_svp.state; r.entry = g_svp.entry; r.stop = g_svp.stop; r.target = g_svp.target;
   r.buy = g_svp_buy.progress; r.sell = g_svp_sell.progress;
   return r;
}

static std::string jsonEscape(const std::string &text)
{
   std::string o;
   for(char ch : text) { if(ch == '"' || ch == '\\') { o += '\\'; o += ch; } else if(ch == '\n') o += "\\n"; else if((unsigned char)ch < 0x20) o += ' '; else o += ch; }
   return o;
}

// A synthetic M15 series for hosts without the market dataset: whole-point prices
// (a mirrored replay is exact), five trading days a week, volatility clusters,
// drift regimes and - so that the liquidity logic has something to do - stop
// runs: a wick through the recent extreme that closes back inside, sometimes
// followed by a displacement the other way. It is NOT market data and says
// nothing about markets; it exists to drive every branch of the engine with
// messy, non-hand-made candles.
static std::vector<MqlRates> syntheticBars(unsigned seed, const int bars)
{
   std::vector<MqlRates> out;
   out.reserve((size_t)bars);
   auto next = [&seed]() { seed = seed * 1664525u + 1013904223u; return (double)(seed >> 8) / 16777216.0; };
   auto gauss = [&]() { double a = 0.0; for(int k = 0; k < 6; k++) a += next(); return (a - 3.0) * 1.4142; };
   double px = 400000.0, vol = 180.0, drift = 0.0;
   int regime_left = 0, push = 0, push_dir = 0;
   datetime t = 1704672000;                     // Monday 2024-01-08 00:00
   for(int i = 0; i < bars; i++)
   {
      if(regime_left <= 0) { regime_left = 150 + (int)(next() * 700.0); const double u = next(); drift = (u < 0.36 ? -1.0 : (u < 0.72 ? 1.0 : 0.0)) * (10.0 + next() * 22.0); }
      regime_left--;
      const double shock = gauss();
      vol = std::max(70.0, std::min(520.0, 0.93 * vol + 0.07 * (120.0 + 240.0 * std::fabs(shock))));
      double o = px, c = px + drift + shock * vol, h = std::max(o, c) + next() * vol * 0.55, l = std::min(o, c) - next() * vol * 0.55;
      if(push > 0)
      {  // the displacement that follows a stop run
         c = o + push_dir * (2.2 + next() * 1.6) * vol; h = std::max(o, c) + next() * vol * 0.15; l = std::min(o, c) - next() * vol * 0.15;
         push--;
      }
      else if(i > 40 && next() < 0.035)
      {  // a stop run: through the extreme of the last 24 bars, close back inside
         double hi = out[(size_t)(i - 1)].high, lo = out[(size_t)(i - 1)].low;
         for(int k = 2; k <= 24; k++) { hi = std::max(hi, out[(size_t)(i - k)].high); lo = std::min(lo, out[(size_t)(i - k)].low); }
         const bool up = next() < 0.5;
         if(up) { h = hi + (0.3 + next() * 0.9) * vol; c = std::min(o, hi) - next() * vol * 0.4; l = std::min(l, c - next() * vol * 0.2); }
         else   { l = lo - (0.3 + next() * 0.9) * vol; c = std::max(o, lo) + next() * vol * 0.4; h = std::max(h, c + next() * vol * 0.2); }
         if(next() < 0.6) { push = 1 + (next() < 0.3 ? 1 : 0); push_dir = up ? -1 : 1; }
      }
      MqlRates r{};
      r.time = t;
      r.open = std::round(o); r.close = std::round(c);
      r.high = std::max(std::round(h), std::max(r.open, r.close)); r.low = std::min(std::round(l), std::min(r.open, r.close));
      if(r.low < 1000.0) { const double lift = 1000.0 - r.low; r.open += lift; r.high += lift; r.low += lift; r.close += lift; }
      r.tick_volume = 150 + (long)(900.0 * (r.high - r.low) / vol * (0.6 + 0.8 * next()));
      r.real_volume = 0; r.spread = 20;
      out.push_back(r);
      px = r.close;
      t += 900;
      if((t / 86400 + 4) % 7 == 6) t += 2 * 86400;            // Saturday 00:00 -> Monday 00:00
   }
   return out;
}
static std::vector<MqlRates> syntheticM15(unsigned seed, const int bars, FeedStats &fs)
{
   std::vector<MqlRates> out = syntheticBars(seed, bars);
   fs.m1 = 0; fs.m15 = (long)out.size(); fs.first = out.front().time; fs.last = out.back().time;
   return out;
}

static int cmdReplay(int argc, char **argv)
{
   std::string dir, out_json, out_csv, out_trace;
   datetime from = 0, to = 0; int warm_days = 150; bool mirror = false, int_grid = false; int recheck = 0, reattach = 0, horizon = 96;
   bool sym_grid = false, canonical = false; long synthetic = -1; int synthetic_bars = 12000;
   std::string render_at, render_out; int render_back = 150; bool rendered = false;
   std::vector<std::pair<std::string, std::string>> sets;
   for(int i = 2; i < argc; i++)
   {
      const std::string a = argv[i];
      auto next = [&]() { return std::string(i + 1 < argc ? argv[++i] : ""); };
      if(a == "--data") dir = next();
      else if(a == "--from") from = parseDate(next());
      else if(a == "--to") to = parseDate(next());
      else if(a == "--warmup-days") warm_days = atoi(next().c_str());
      else if(a == "--mirror") mirror = true;
      else if(a == "--int-grid") int_grid = true;
      else if(a == "--recheck") recheck = atoi(next().c_str());
      else if(a == "--reattach") reattach = atoi(next().c_str());
      else if(a == "--horizon") horizon = atoi(next().c_str());
      else if(a == "--out") out_json = next();
      else if(a == "--signals") out_csv = next();
      else if(a == "--trace") out_trace = next();
      else if(a == "--render-at") render_at = next();
      else if(a == "--render-out") render_out = next();
      else if(a == "--render-back") render_back = atoi(next().c_str());
      else if(a == "--sym-grid") sym_grid = true;
      else if(a == "--canonical") canonical = true;
      else if(a == "--synthetic") { synthetic = atol(next().c_str()); int_grid = true; }
      else if(a == "--bars") synthetic_bars = atoi(next().c_str());
      else if(a == "--set") { const std::string kv = next(); const size_t eq = kv.find('='); if(eq != std::string::npos) sets.push_back({kv.substr(0, eq), kv.substr(eq + 1)}); }
      else { fprintf(stderr, "unknown option %s\n", a.c_str()); return 2; }
   }
   if(synthetic < 0 && (dir.empty() || from <= 0)) { fprintf(stderr, "replay needs --data DIR --from YYYY-MM-DD [--to YYYY-MM-DD], or --synthetic SEED [--bars N]\n"); return 2; }
   const double grid = int_grid ? 1.0 : 0.01, scale = int_grid ? 100.0 : 1.0;
   FeedStats fs;
   std::vector<MqlRates> bars;
   if(synthetic >= 0)
   {
      if(synthetic_bars < 3000) { fprintf(stderr, "--bars must be at least 3000\n"); return 2; }
      bars = syntheticM15((unsigned)synthetic, synthetic_bars, fs);
      from = bars[1800].time;                                  // 1,800 bars of warm-up
   }
   else bars = loadM15(dir, from - (datetime)warm_days * 86400, to, grid, scale, fs);
   if(bars.size() < 2000) { fprintf(stderr, "not enough history in %s (%zu M15 bars)\n", dir.c_str(), bars.size()); return 2; }
   const double centre = int_grid ? 1000000.0 : 10000.0;
   if(mirror) bars = mirrored(bars, centre);
   // --sym-grid: the row lattice of the volume profile is moved by half a tick,
   // so no traded price can sit on a row boundary, and reflected with the data.
   // Then a mirrored run must reproduce the original bar for bar.
   const double grid_phase = sym_grid ? (mirror ? centre - 0.5 * grid : 0.5 * grid) : 0.0;
   int attach = 0;
   while(attach < (int)bars.size() && bars[(size_t)attach].time < from) attach++;
   if(attach < SVP_MIN_M15_BARS + 200 || attach >= (int)bars.size() - 10) { fprintf(stderr, "the window leaves no warm-up or no data\n"); return 2; }

   defaultInputs();
   InpSveAlerts = true; InpSveLog = false;
   for(const auto &kv : sets) if(!QATS_SetInput(kv.first, kv.second)) { fprintf(stderr, "unknown input: %s\n", kv.first.c_str()); return 2; }
   Term T;
   T.boot(bars, attach);
   if(int_grid) { _Point = 1.0; _Digits = 0; sim::S.sym.point = 1.0; sim::S.sym.tickSize = 1.0; sim::S.sym.digits = 0; }
   if(OnInit() != INIT_SUCCEEDED) { fprintf(stderr, "OnInit failed\n"); return 1; }
   g_sve_params.vp_grid_phase = grid_phase;
   std::vector<datetime> all_times(T.all.size());
   for(size_t i = 0; i < T.all.size(); i++) all_times[i] = T.all[i].time;
   // --canonical: a mirrored run writes its trace and its signals in the
   // orientation of the original data, so the two files can be compared as they are
   const bool flip = (mirror && canonical);
   std::ofstream trace;
   if(!out_trace.empty()) { trace.open(out_trace); trace << "bar,state,buy_passed,sell_passed,focus,blocking_step,objects\n"; }

   std::vector<SetupRow> setups;
   std::map<std::string, long> blocking;       // what kept the decision at WAIT, by step
   long passes = 0, buy_bars = 0, sell_bars = 0, wait_bars = 0, not_ready = 0, cells_bad = 0;
   long objects_sum = 0; int objects_max = 0, layer_max[SVC_LAYERS] = {0, 0, 0, 0, 0}; long dup_objects = 0;
   long box_overlaps = 0, caption_hits = 0, dash_clipped = 0, dash_clipped_bars = 0; int dash_labels_max = 0, dash_longest = 0;
   long level_struck = 0, inchart_crossed = 0, inchart_crossed_bars = 0, captions_drawn = 0, captions_withheld = 0;
   long vp_seen = 0, vp_poc_plateau = 0;
   long recheck_n = 0, recheck_diff = 0, reattach_n = 0, reattach_diff = 0;
   std::deque<RawSnap> ring;
   double worst_us = 0.0, total_us = 0.0;
   const long created_at_start = chartsim::C.created;
   auto pass = [&]() {
      const int runs0 = g_sve_runs;
      const auto t0 = std::chrono::steady_clock::now();
      T.calc();
      const double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count();
      if(g_sve_runs != runs0) { passes++; total_us += us; worst_us = std::max(worst_us, us); }
   };
   pass();
   const int first_bar = T.forming;
   while(T.forming < (int)bars.size())
   {
      const int closed = T.forming - 1;
      const datetime bar_time = bars[(size_t)closed].time;
      // --- what the host says for the bar that has just closed
      if(!g_svp.ready) not_ready++;
      else if(g_svp.state == SVP_DECISION_BUY) buy_bars++;
      else if(g_svp.state == SVP_DECISION_SELL) sell_bars++;
      else
      {
         wait_bars++;
         const int side_block = (g_svp.focus > 0 ? g_svp_buy.blocking : (g_svp.focus < 0 ? g_svp_sell.blocking : -1));
         blocking[side_block >= 0 && side_block < SVP_MAX_STEPS ? std::string(SVP_StepName(side_block)) : std::string("no candidate on either side")]++;
      }
      const double cell = Term::closedCell(g_sve_decision);
      if(g_svp.ready && cell != (double)((int)g_svp.state)) cells_bad++;
      // --- signals confirmed on this bar
      for(int i = 0; i < QSR_CAPACITY; i++)
      {
         if(!g_qsr[i].used || g_svv_confirmed[i] != bar_time || !(g_qsr[i].entry > 0.0)) continue;
         bool known = false;
         for(const SetupRow &r : setups) if(r.origin == g_qsr[i].origin_time && r.direction == g_qsr[i].direction && r.confirmed == bar_time) known = true;
         if(known) continue;
         SetupRow r;
         r.confirmed = bar_time; r.origin = g_qsr[i].origin_time; r.direction = g_qsr[i].direction; r.type = std::string(g_qsr[i].setup_type);
         r.entry = g_qsr[i].entry; r.stop = g_qsr[i].stop; r.target = g_qsr[i].target;
         r.rr = std::fabs(r.target - r.entry) / std::fabs(r.entry - r.stop);
         // outcome from the candles that FOLLOW, independently of the engine
         for(int k = closed + 1; k < (int)bars.size() && k <= closed + horizon; k++)
         {
            const bool hit_stop = (r.direction > 0 ? bars[(size_t)k].low <= r.stop : bars[(size_t)k].high >= r.stop);
            const bool hit_target = (r.direction > 0 ? bars[(size_t)k].high >= r.target : bars[(size_t)k].low <= r.target);
            if(hit_stop || hit_target) { r.outcome = (hit_stop && hit_target) ? -2 : (hit_stop ? -1 : 1); r.bars_to_outcome = k - closed; break; }
         }
         setups.push_back(r);
      }
      for(SetupRow &r : setups)
      {
         if(!r.registry_end.empty()) continue;
         for(int i = 0; i < QSR_CAPACITY; i++)
            if(g_qsr[i].used && g_qsr[i].origin_time == r.origin && g_qsr[i].direction == r.direction && QSR_IsTerminal(g_qsr[i].state))
               r.registry_end = std::string(QSR_StateName(g_qsr[i].state));
      }
      // --- the chart
      const int n_obj = (int)chartsim::countPrefix("QSVP_");
      objects_sum += n_obj; objects_max = std::max(objects_max, n_obj);
      if(trace.is_open())
      {
         const int state_now = g_svp.ready ? (int)g_svp.state : 9;
         const int block = (g_svp.focus > 0 ? g_svp_buy.blocking : (g_svp.focus < 0 ? g_svp_sell.blocking : -1));
         trace << sim::timeString(bar_time, TIME_DATE | TIME_MINUTES) << ',' << (flip && state_now != 9 ? -state_now : state_now) << ','
               << (flip ? g_svp_sell.progress : g_svp_buy.progress) << ',' << (flip ? g_svp_buy.progress : g_svp_sell.progress) << ','
               << (flip ? -g_svp.focus : g_svp.focus) << ',' << block << ',' << n_obj << '\n';
      }
      for(int k = 0; k < SVC_LAYERS; k++) layer_max[k] = std::max(layer_max[k], SVC_CountLayer((ENUM_SVC_LAYER)k));
      dup_objects += exactDuplicates("QSVP_");
      if(!render_at.empty() && !rendered && sim::timeString(bar_time, TIME_DATE | TIME_MINUTES) == render_at)
      {  // the picture of this bar, for tools/smcvp_chart_svg.py
         const int last = T.forming - 1;
         const std::string j = renderJson(T.all, std::max(0, last - render_back), last, std::string(_Symbol) + " M15, " + render_at);
         if(render_out.empty()) printf("%s", j.c_str());
         else { std::ofstream f(render_out); f << j; }
         rendered = true;
      }
      if(g_sve_started)
      {
         box_overlaps += boxOverlaps("QSVP_");
         caption_hits += captionCollisions(all_times, T.forming);
         level_struck += captionStrikes(all_times, T.forming, true);
         { const int crossed = captionStrikes(all_times, T.forming, false); inchart_crossed += crossed; if(crossed > 0) inchart_crossed_bars++; }
         for(const auto &kv : chartsim::C.objects) if(kv.second.type == OBJ_TEXT && kv.first.compare(0, 5, "QSVP_") == 0) captions_drawn++;
         captions_withheld += g_svv_labels_hidden;
         if(g_svp_profile.valid)
         {
            vp_seen++;
            int at_max = 0;
            for(int b = 0; b < g_svp_profile.bin_count; b++) if(g_svp_profile.bins[b] == g_svp_profile.poc_volume) at_max++;
            if(at_max > 1) vp_poc_plateau++;
         }
         int dl = 0, dw = 0, dc = 0;
         dashboardStats(dl, dw, dc);
         dash_labels_max = std::max(dash_labels_max, dl); dash_longest = std::max(dash_longest, dw); dash_clipped += dc;
         if(dc > 0) dash_clipped_bars++;
      }
      // --- would the same bar be judged the same way later, with more bars in the arrays?
      if(recheck > 0 && g_svp.ready && closed % 5 == 0)
      {
         const SSvpDecision keep = g_svp;
         const int n15 = (int)g_sve_m15.v.size(), n1 = (int)g_sve_h1.v.size(), n4 = (int)g_sve_h4.v.size();
         SVP_Analyze(g_sve_h4, n4, g_sve_h1, n1, g_sve_m15, n15, g_sve_params);
         ring.push_back(rawNow(bar_time));
         while(!ring.empty() && ring.front().t < bar_time - (datetime)recheck * 900 * 3) ring.pop_front();
         // the bar `recheck` M15 bars back, judged with today's arrays
         if(n15 > recheck + SVP_MIN_M15_BARS)
         {
            const datetime old_t = g_sve_m15.v[(size_t)(n15 - 1 - recheck)].time;
            for(const RawSnap &was : ring)
            {
               if(was.t != old_t) continue;
               SVP_Analyze(g_sve_h4, n4, g_sve_h1, n1, g_sve_m15, n15 - recheck, g_sve_params);
               const RawSnap now = rawNow(old_t);
               recheck_n++;
               if(now.state != was.state || now.buy != was.buy || now.sell != was.sell ||
                  (was.state != 0 && (!near(now.entry, was.entry, 1e-9) || !near(now.stop, was.stop, 1e-9) || !near(now.target, was.target, 1e-9)))) recheck_diff++;
               break;
            }
         }
         g_svp = keep;
      }
      // --- a fresh attach must show what the continuous run shows
      if(reattach > 0 && closed % reattach == 0 && g_sve_started)
      {
         const std::string before = objectDigest("QSVP_"); const int state_before = (int)g_svp.state;
         OnDeinit(REASON_PARAMETERS); OnInit(); g_sve_params.vp_grid_phase = grid_phase; T.prev = 0; T.calc();
         reattach_n++;
         if(objectDigest("QSVP_") != before || (int)g_svp.state != state_before) reattach_diff++;
      }
      T.step();
      pass();
   }
   const int last_bar = T.forming - 1;
   OnDeinit(REASON_REMOVE);
   const long left_over = chartsim::countPrefix("QSVP_");

   long n_buy = 0, n_sell = 0, tgt[2] = {0, 0}, stp[2] = {0, 0}, amb[2] = {0, 0}, open_[2] = {0, 0}; double rr_sum[2] = {0, 0};
   long agree = 0, compared = 0;
   for(const SetupRow &r : setups)
   {
      const int s = r.direction > 0 ? 0 : 1;
      (r.direction > 0 ? n_buy : n_sell)++;
      rr_sum[s] += r.rr;
      if(r.outcome == 1) tgt[s]++; else if(r.outcome == -1) stp[s]++; else if(r.outcome == -2) amb[s]++; else open_[s]++;
      if(!r.registry_end.empty() && r.outcome != 0)
      {
         compared++;
         if((r.outcome == 1 && r.registry_end == "MITIGATED") || (r.outcome < 0 && r.registry_end == "INVALIDATED")) agree++;
      }
   }
   const long analysed = (long)(last_bar - first_bar + 1);
   char buf[256];
   std::string j = "{\n";
   auto add = [&](const std::string &k, const std::string &v, const bool quote = false) { j += "  \"" + k + "\": " + (quote ? "\"" + jsonEscape(v) + "\"" : v) + ",\n"; };
   add("from", sim::timeString(bars[(size_t)first_bar].time, TIME_DATE | TIME_MINUTES), true);
   add("to", sim::timeString(bars[(size_t)last_bar].time, TIME_DATE | TIME_MINUTES), true);
   add("source", synthetic >= 0 ? "synthetic series, seed " + std::to_string(synthetic) + " (not market data)" : "M1 bid candles aggregated to M15", true);
   add("mirror", mirror ? "true" : "false"); add("int_grid", int_grid ? "true" : "false"); add("sym_grid", sym_grid ? "true" : "false");
   add("m1_rows", std::to_string(fs.m1)); add("m1_rows_skipped_repeated_at_a_file_seam", std::to_string(fs.overlap));
   add("m15_bars_loaded", std::to_string(fs.m15)); add("m15_bars_analysed", std::to_string(analysed));
   add("engine_passes", std::to_string(passes)); add("idle_calls", std::to_string(g_sve_idle));
   add("bars_buy_setup", std::to_string(buy_bars)); add("bars_sell_setup", std::to_string(sell_bars)); add("bars_wait", std::to_string(wait_bars));
   add("bars_not_ready", std::to_string(not_ready)); add("buffer_mismatches", std::to_string(cells_bad));
   add("setups", std::to_string(setups.size())); add("setups_buy", std::to_string(n_buy)); add("setups_sell", std::to_string(n_sell));
   add("alerts", std::to_string(chartsim::C.alerts.size()));
   add("buy_target_first", std::to_string(tgt[0])); add("buy_stop_first", std::to_string(stp[0])); add("buy_both_in_one_bar", std::to_string(amb[0])); add("buy_unresolved", std::to_string(open_[0]));
   add("sell_target_first", std::to_string(tgt[1])); add("sell_stop_first", std::to_string(stp[1])); add("sell_both_in_one_bar", std::to_string(amb[1])); add("sell_unresolved", std::to_string(open_[1]));
   snprintf(buf, sizeof buf, "%.3f", n_buy ? rr_sum[0] / (double)n_buy : 0.0); add("buy_mean_planned_rr", buf);
   snprintf(buf, sizeof buf, "%.3f", n_sell ? rr_sum[1] / (double)n_sell : 0.0); add("sell_mean_planned_rr", buf);
   add("outcome_horizon_bars", std::to_string(horizon));
   add("lifecycle_compared", std::to_string(compared)); add("lifecycle_agrees_with_candles", std::to_string(agree));
   add("objects_max", std::to_string(objects_max));
   snprintf(buf, sizeof buf, "%.2f", analysed ? (double)objects_sum / (double)analysed : 0.0); add("objects_mean", buf);
   for(int k = 0; k < SVC_LAYERS; k++) add("objects_max_" + std::string(SVC_LayerName((ENUM_SVC_LAYER)k)), std::to_string(layer_max[k]));
   add("objects_created", std::to_string(chartsim::C.created - created_at_start));
   snprintf(buf, sizeof buf, "%.3f", analysed ? (double)(chartsim::C.created - created_at_start) / (double)analysed : 0.0); add("objects_created_per_bar", buf);
   add("duplicate_objects", std::to_string(dup_objects)); add("objects_left_after_deinit", std::to_string(left_over));
   add("zone_boxes_overlapping", std::to_string(box_overlaps)); add("captions_colliding", std::to_string(caption_hits));
   add("captions_drawn", std::to_string(captions_drawn)); add("captions_withheld", std::to_string(captions_withheld));
   add("level_captions_struck_through", std::to_string(level_struck));
   add("in_chart_captions_struck_through", std::to_string(inchart_crossed)); add("bars_with_a_struck_caption", std::to_string(inchart_crossed_bars));
   add("dashboard_labels_max", std::to_string(dash_labels_max)); add("dashboard_longest_row_chars", std::to_string(dash_longest));
   add("dashboard_rows_clipped", std::to_string(dash_clipped)); add("dashboard_bars_with_a_clipped_row", std::to_string(dash_clipped_bars));
   add("recheck_lag_bars", std::to_string(recheck)); add("recheck_compared", std::to_string(recheck_n)); add("recheck_differ", std::to_string(recheck_diff));
   add("reattach_every_bars", std::to_string(reattach)); add("reattach_compared", std::to_string(reattach_n)); add("reattach_differ", std::to_string(reattach_diff));
   snprintf(buf, sizeof buf, "%.1f", passes ? total_us / (double)passes : 0.0); add("pass_mean_us", buf);
   snprintf(buf, sizeof buf, "%.1f", worst_us); add("pass_worst_us", buf);
   add("vp_builds", std::to_string(g_svp_vp_builds)); add("vp_cache_hits", std::to_string(g_svp_vp_hits));
   add("vp_bars_with_profile", std::to_string(vp_seen)); add("vp_bars_poc_shared_by_several_rows", std::to_string(vp_poc_plateau));
   add("api_errors", std::to_string(sim::S.apiErrors.size())); add("format_errors", std::to_string(sim::S.fmtErrors.size())); add("trade_requests", std::to_string(sim::S.sendCount));
   j += "  \"wait_blocked_at\": {";
   bool first_kv = true;
   for(const auto &kv : blocking) { j += std::string(first_kv ? "" : ", ") + "\"" + jsonEscape(kv.first) + "\": " + std::to_string(kv.second); first_kv = false; }
   j += "}\n}\n";
   if(!out_json.empty()) { std::ofstream f(out_json); f << j; }
   printf("%s", j.c_str());
   if(!out_csv.empty())
   {
      std::ofstream f(out_csv);
      f << "confirmed,origin,direction,type,entry,stop,target,planned_rr,outcome,bars_to_outcome,engine_lifecycle\n";
      for(const SetupRow &r : setups)
      {
         const char *oc = r.outcome == 1 ? "TARGET_FIRST" : (r.outcome == -1 ? "STOP_FIRST" : (r.outcome == -2 ? "BOTH_IN_ONE_BAR" : "UNRESOLVED"));
         const int dir_out = flip ? -r.direction : r.direction;
         snprintf(buf, sizeof buf, "%s,%s,%s,%s,%.2f,%.2f,%.2f,%.2f,%s,%d,%s\n", sim::timeString(r.confirmed, TIME_DATE | TIME_MINUTES).c_str(),
                  sim::timeString(r.origin, TIME_DATE | TIME_MINUTES).c_str(), dir_out > 0 ? "BUY" : "SELL", r.type.c_str(),
                  flip ? centre - r.entry : r.entry, flip ? centre - r.stop : r.stop, flip ? centre - r.target : r.target, r.rr, oc,
                  r.bars_to_outcome, r.registry_end.c_str());
         f << buf;
      }
   }
   return (sim::S.apiErrors.empty() && sim::S.fmtErrors.empty() && cells_bad == 0 && left_over == 0) ? 0 : 1;
}

// ------------------------------------------------------------------ render: the chart as data
// The candles and every object of the program on the confirming bar of the
// story (or `--bar N`), as JSON, for tools/test_qsmc_smcvp.py to draw.
// The chart as the program left it: the candles of a window and every object
// under QSVP_ with its geometry, colour, text and tooltip. tools/smcvp_chart_svg.py
// turns this into a picture.
static std::string renderJson(const std::vector<MqlRates> &bars, const int first, const int last, const std::string &title)
{
   std::string j = "{\n  \"title\": \"" + jsonEscape(title) + "\",\n  \"bar\": " + std::to_string(last) + ",\n  \"candles\": [";
   char b[512];
   for(int k = first; k <= last; k++)
   {
      const MqlRates &r = bars[(size_t)k];
      snprintf(b, sizeof b, "%s[%lld,%.2f,%.2f,%.2f,%.2f]", k == first ? "" : ",", (long long)r.time, r.open, r.high, r.low, r.close);
      j += b;
   }
   j += "],\n  \"objects\": [\n";
   bool first_obj = true;
   for(const std::string &name : chartsim::C.order)
   {
      const chartsim::Obj *ob = chartsim::find(name);
      if(!ob || name.compare(0, 5, "QSVP_") != 0) continue;
      auto geti = [&](const int prop, const long dflt) { const auto it = ob->ints.find(prop); return it == ob->ints.end() ? dflt : it->second; };
      auto gets = [&](const int prop) { const auto it = ob->strs.find(prop); return it == ob->strs.end() ? std::string() : it->second; };
      snprintf(b, sizeof b, "    %s{\"name\":\"%s\",\"type\":%d,\"t1\":%lld,\"p1\":%.2f,\"t2\":%lld,\"p2\":%.2f,\"color\":%ld,\"style\":%ld,\"width\":%ld,\"fill\":%ld,"
               "\"anchor\":%ld,\"size\":%ld,\"x\":%ld,\"y\":%ld,\"w\":%ld,\"h\":%ld,\"bg\":%ld,",
               first_obj ? "" : ",", jsonEscape(name).c_str(), (int)ob->type, (long long)ob->t[0], ob->p[0], (long long)ob->t[1], ob->p[1],
               geti((int)OBJPROP_COLOR, 0), geti((int)OBJPROP_STYLE, 0), geti((int)OBJPROP_WIDTH, 1), geti((int)OBJPROP_FILL, 0), geti((int)OBJPROP_ANCHOR, 0),
               geti((int)OBJPROP_FONTSIZE, 8), geti((int)OBJPROP_XDISTANCE, 0), geti((int)OBJPROP_YDISTANCE, 0), geti((int)OBJPROP_XSIZE, 0),
               geti((int)OBJPROP_YSIZE, 0), geti((int)OBJPROP_BGCOLOR, 0));
      j += b;
      j += "\"text\":\"" + jsonEscape(gets((int)OBJPROP_TEXT)) + "\",\"tip\":\"" + jsonEscape(gets((int)OBJPROP_TOOLTIP)) + "\"}\n";
      first_obj = false;
   }
   j += "  ],\n  \"caption_line_price\": " + std::to_string(g_svv_label_gap) + ",\n  \"captions_withheld\": " + std::to_string(g_svv_labels_hidden) +
        ",\n  \"census\": \"" + jsonEscape(std::string(SVC_Census())) + "\"\n}\n";
   return j;
}

static int cmdRender(int argc, char **argv)
{
   int bar = -1, back = 110; bool optional = false, histogram = false; std::string out;
   for(int i = 2; i < argc; i++)
   {
      const std::string a = argv[i];
      if(a == "--bar" && i + 1 < argc) bar = atoi(argv[++i]);
      else if(a == "--back" && i + 1 < argc) back = atoi(argv[++i]);
      else if(a == "--optional") optional = true;
      else if(a == "--histogram") histogram = true;
      else if(a == "--out" && i + 1 < argc) out = argv[++i];
   }
   Story st = makeStory(1);
   if(bar < 0) bar = st.i_confirm;
   defaultInputs(); InpSveShowOptional = optional; InpSveShowHistogram = histogram; InpSveLog = false;
   Term T;
   T.boot(st.bars, bar + 1);
   if(OnInit() != INIT_SUCCEEDED) return 1;
   T.calc();
   const std::string j = renderJson(st.bars, std::max(0, bar - back), bar, "synthetic story, the confirming bar");
   if(out.empty()) printf("%s", j.c_str());
   else { std::ofstream f(out); f << j; }
   OnDeinit(REASON_REMOVE);
   return 0;
}
}  // namespace drv

int main(int argc, char **argv)
{
   const std::string cmd = argc > 1 ? argv[1] : "";
   try
   {
      if(cmd == "unit") return drv::runUnits(argc > 2 ? argv[2] : "");
      if(cmd == "story")
      {
         bool mirror = false, steps = false; int branch = 0, back = 6;
         for(int i = 2; i < argc; i++)
         {
            const std::string a = argv[i];
            if(a == "--mirror") mirror = true;
            else if(a == "--steps") steps = true;
            else if(a == "--branch" && i + 1 < argc) { const std::string v = argv[++i]; branch = (v == "win" ? 1 : (v == "loss" ? 2 : 0)); }
            else if(a == "--back" && i + 1 < argc) back = atoi(argv[++i]);
         }
         return drv::cmdStory(mirror, branch, back, steps);
      }
      if(cmd == "replay") return drv::cmdReplay(argc, argv);
      if(cmd == "render") return drv::cmdRender(argc, argv);
      if(cmd == "probe")
      {
         // what this binary is: lets a test prove that the "poisoned" build
         // really leaves new array elements non-zero, as the terminal may
         MqlArray<double> fresh;
         ArrayResize(fresh, 4);
         printf("poison=%d\n", fresh[0] != 0.0 ? 1 : 0);
#ifdef SMCVP_WITH_LEGACY_VP
         printf("legacy_vp=1\n");
#else
         printf("legacy_vp=0\n");
#endif
         return 0;
      }
   }
   catch(const std::exception &e)
   {
      fprintf(stderr, "FATAL %s\n", e.what());
      return 3;
   }
   fprintf(stderr, "usage: unit [group] | story [--mirror] [--steps] [--branch win|loss] [--back N] | replay --data DIR --from D [--to D] ... | render [--bar N] | probe\n");
   return 2;
}
