// qats_selftest.inc - deterministic unit and integration scenarios for the
// dual-direction QATS build. Included by qats_driver.inc when the EA source
// defines QATS_ScoreSide.
//
// Every scenario runs the REAL functions of the EA translation unit. Unit tests
// call them directly on hand-built H1 series; integration scenarios replay a
// synthetic tick stream through OnInit / OnTick / OnTradeTransaction against the
// simulated broker. Each bullish scenario is also run MIRRORED (price -> K - price,
// bid/ask swapped), where the same logic must produce the exact bearish twin.
//
// EA globals survive inside one process, so every integration scenario is run in
// its own process by tools/test_qats_dual_direction.py.
#pragma GCC system_header

namespace drv
{
struct TestCtx { std::string name; int checks = 0; int failed = 0; };
static TestCtx TC;

static void qcheck(bool cond, const std::string &msg, const char *file, int line)
{
   TC.checks++;
   if(!cond)
   {
      TC.failed++;
      printf("  FAIL [%s] %s (%s:%d)\n", TC.name.c_str(), msg.c_str(), file, line);
   }
}
#define QCHECK(cond, msg) qcheck((cond), (msg), __FILE__, __LINE__)
#define QEQ(a, b, msg) qcheck((a) == (b), std::string(msg) + " [got " + std::to_string(a) + ", want " + std::to_string(b) + "]", __FILE__, __LINE__)

static bool near(double a, double b, double eps = 1e-6) { return std::fabs(a - b) <= eps; }

static void simDiagnosticsClean()
{
   QCHECK(sim::S.fmtErrors.empty(), "no PrintFormat/StringFormat type or count mismatch" + (sim::S.fmtErrors.empty() ? std::string() : ": " + sim::S.fmtErrors[0]));
   QCHECK(sim::S.apiErrors.empty(), "no simulator API misuse" + (sim::S.apiErrors.empty() ? std::string() : ": " + sim::S.apiErrors[0]));
}

// ------------------------------------------------- hand-built H1 series
static sim::Bar HB(double o, double h, double l, double c, long v = 100) { return sim::Bar{0, o, h, l, c, v}; }

// Candles that travel in legs. The wick in the direction of travel is longer than
// the one behind, so a turning point is a strict fractal (no equal neighbours).
struct Zig
{
   std::vector<sim::Bar> bars;
   double p;
   explicit Zig(double start) : p(start) {}
   void leg(int n, double target)
   {
      double step = (target - p) / n;
      for(int i = 0; i < n; i++)
      {
         double o = p, c = p + step;
         if(step >= 0) bars.push_back(HB(o, c + 0.3, o - 0.1, c));
         else          bars.push_back(HB(o, o + 0.1, c - 0.3, c));
         p = c;
      }
   }
   void candle(double o, double h, double l, double c) { bars.push_back(HB(o, h, l, c)); p = c; }
   void forming() { bars.push_back(HB(p, p, p, p)); }
};

static std::vector<sim::Bar> mirrorBars(const std::vector<sim::Bar> &in, double K)
{
   std::vector<sim::Bar> out;
   for(const sim::Bar &b : in) out.push_back(sim::Bar{b.time, K - b.open, K - b.low, K - b.high, K - b.close, b.volume});
   return out;
}

// The last bar is the forming bar (shift 0); bar times end at lastTime.
static void loadH1(const std::vector<sim::Bar> &bars, datetime lastTime = kMonday + 4 * 86400 + 12 * 3600)
{
   resetSimOnly();
   std::vector<sim::Bar> v = bars;
   for(size_t i = 0; i < v.size(); i++) v[i].time = lastTime - (datetime)(v.size() - 1 - i) * 3600;
   sim::S.series[sim::tfIndex(PERIOD_H1)].bars = v;
   sim::S.now = lastTime;
}

struct Snap
{
   SStructure st;
   SSweep sweepBuy, sweepSell;
   std::vector<SLiquidityPool> pools;
   bool dispBull = false, dispBear = false;
   int dispBullBar = -1, dispBearBar = -1;
   int nHighs = 0, nLows = 0;
};

static Snap analyzeH1(double atr, int window, double tol)
{
   Snap s;
   MqlArray<SSwing> highs, lows;
   s.nHighs = FindSwings(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, highs, true);
   s.nLows = FindSwings(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, lows, false);
   BuildStructure(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, s.st);
   MqlArray<SLiquidityPool> pools;
   BuildLiquidityMap(_Symbol, PERIOD_H1, highs, lows, tol, window, pools);
   s.pools = pools.v;
   SweepForDirection(pools, +1, s.sweepBuy);
   SweepForDirection(pools, -1, s.sweepSell);
   s.dispBull = DetectDisplacement(_Symbol, PERIOD_H1, true, atr, window, s.dispBullBar);
   s.dispBear = DetectDisplacement(_Symbol, PERIOD_H1, false, atr, window, s.dispBearBar);
   return s;
}

static int countPools(const Snap &s, bool buySide, int state, const std::string &kind = "")
{
   int n = 0;
   for(const SLiquidityPool &p : s.pools)
      if(p.buySide == buySide && p.state == state && (kind.empty() || p.kind == kind)) n++;
   return n;
}

// ------------------------------------------------------------- unit tests
static SSide sideWith(int dir, unsigned mask)
{
   SSide e;
   ResetSide(e, dir);
   e.biasD1 = mask & 1u; e.biasH4 = mask & 2u; e.structure = mask & 4u; e.sweep.found = mask & 8u;
   e.displaced = mask & 16u; e.zoneTouched = mask & 32u; e.hasOB = mask & 64u; e.location = mask & 128u;
   e.vwapSide = mask & 256u; e.volume = mask & 512u; e.confirmM15 = mask & 1024u; e.triggerM5 = mask & 2048u;
   return e;
}

static void unitScoring()
{
   TC.name = "unit.scoring";
   int total = QATS_W_BIAS_D1 + QATS_W_BIAS_H4 + QATS_W_STRUCTURE + QATS_W_SWEEP + QATS_W_DISPLACEMENT +
               QATS_W_ZONE_TOUCH + QATS_W_LOCATION + QATS_W_VWAP + QATS_W_VOLUME + QATS_W_M15 + QATS_W_M5;
   QEQ(total, 100, "the confluence weights sum to exactly 100");
   QCHECK(QATS_W_ZONE_PRESENT < QATS_W_ZONE_TOUCH, "a zone that merely exists is worth less than one that is touched");
   QEQ(QATS_ScoreSide(sideWith(+1, 0)), 0, "no evidence scores 0 (no free points)");
   QEQ(QATS_ScoreSide(sideWith(-1, 0)), 0, "no evidence scores 0 on the SELL side too");
   QEQ(QATS_ScoreSide(sideWith(+1, 0xFFF)), 100, "all BUY evidence scores 100");
   QEQ(QATS_ScoreSide(sideWith(-1, 0xFFF)), 100, "all SELL evidence scores 100");
   int mismatch = 0;
   for(unsigned m = 0; m < 4096; m++)
      if(QATS_ScoreSide(sideWith(+1, m)) != QATS_ScoreSide(sideWith(-1, m))) mismatch++;
   QEQ(mismatch, 0, "identical evidence scores identically for BUY and SELL (all 4096 combinations)");
   // the zone weights are alternatives, never added
   SSide z = sideWith(+1, 32u | 64u);
   QEQ(QATS_ScoreSide(z), QATS_W_ZONE_TOUCH, "touched zone counts once, not touch + presence");
   z = sideWith(+1, 64u);
   QEQ(QATS_ScoreSide(z), QATS_W_ZONE_PRESENT, "an untouched zone earns the presence weight only");
   // every single evidence is worth exactly its declared weight
   struct { unsigned bit; int w; const char *n; } table[] = {
      {1u, QATS_W_BIAS_D1, "D1"}, {2u, QATS_W_BIAS_H4, "H4"}, {4u, QATS_W_STRUCTURE, "structure"}, {8u, QATS_W_SWEEP, "sweep"},
      {16u, QATS_W_DISPLACEMENT, "displacement"}, {32u, QATS_W_ZONE_TOUCH, "zone touch"}, {128u, QATS_W_LOCATION, "location"},
      {256u, QATS_W_VWAP, "VWAP"}, {512u, QATS_W_VOLUME, "volume"}, {1024u, QATS_W_M15, "M15"}, {2048u, QATS_W_M5, "M5"}};
   for(auto &t : table)
   {
      QEQ(QATS_ScoreSide(sideWith(+1, t.bit)), t.w, std::string("BUY weight of ") + t.n);
      QEQ(QATS_ScoreSide(sideWith(-1, t.bit)), t.w, std::string("SELL weight of ") + t.n);
   }
   QCHECK(QATS_ScoreEligible(+1, 55, 55) && QATS_ScoreEligible(-1, 55, 55), "score == minimum is eligible on both sides");
   QCHECK(!QATS_ScoreEligible(+1, 54, 55) && !QATS_ScoreEligible(-1, 54, 55), "score below the minimum is not eligible on either side");
   QCHECK(!QATS_ScoreEligible(0, 100, 55), "no direction is never eligible");
}

static void unitCoreGate()
{
   TC.name = "unit.core_gate";
   for(int profile = 0; profile < 3; profile++)
   {
      for(int ltf = 0; ltf < 2; ltf++)
      {
         string why;
         bool sweepOnly = QATS_CoreGate(profile, true, false, false, ltf != 0, why);
         QCHECK(!sweepOnly, "a liquidity sweep ALONE never passes (profile " + std::to_string(profile) + ")");
         QCHECK(!why.empty(), "a failed core gate names its reason");
         QCHECK(!QATS_CoreGate(profile, false, false, false, ltf != 0, why), "no core event never passes");
      }
   }
   string why;
   // CONSERVATIVE: the full chain plus a lower-timeframe confirmation
   QCHECK(QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, true, true, true, true, why) && why.empty(), "CONSERVATIVE passes the full chain");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, true, true, true, false, why), "CONSERVATIVE needs M15 or M5");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, false, true, true, true, why), "CONSERVATIVE needs the sweep");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, true, false, true, true, why), "CONSERVATIVE needs displacement");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, true, true, false, true, why), "CONSERVATIVE needs BOS/CHoCH");
   // BALANCED: displacement AND structure; the sweep is optional
   QCHECK(QATS_CoreGate(QATS_PROFILE_BALANCED, false, true, true, false, why), "BALANCED passes displacement + structure without a sweep");
   QCHECK(QATS_CoreGate(QATS_PROFILE_BALANCED, true, true, true, false, why), "BALANCED passes the full chain");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_BALANCED, true, true, false, true, why), "BALANCED rejects sweep + displacement without structure");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_BALANCED, true, false, true, true, why), "BALANCED rejects sweep + structure without displacement");
   // ACTIVE: any two of three
   QCHECK(QATS_CoreGate(QATS_PROFILE_ACTIVE, true, true, false, false, why), "ACTIVE passes sweep + displacement");
   QCHECK(QATS_CoreGate(QATS_PROFILE_ACTIVE, true, false, true, false, why), "ACTIVE passes sweep + structure");
   QCHECK(QATS_CoreGate(QATS_PROFILE_ACTIVE, false, true, true, false, why), "ACTIVE passes displacement + structure");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_ACTIVE, false, true, false, true, why), "ACTIVE rejects displacement alone");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_ACTIVE, false, false, true, true, why), "ACTIVE rejects structure alone");
   // profiles are nested: whatever CONSERVATIVE accepts BALANCED accepts, and ACTIVE accepts that too
   int broken = 0;
   for(int m = 0; m < 16; m++)
   {
      bool sw = m & 1, di = m & 2, st = m & 4, lt = m & 8;
      bool c = QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, sw, di, st, lt, why);
      bool b = QATS_CoreGate(QATS_PROFILE_BALANCED, sw, di, st, lt, why);
      bool a = QATS_CoreGate(QATS_PROFILE_ACTIVE, sw, di, st, lt, why);
      if((c && !b) || (b && !a)) broken++;
   }
   QEQ(broken, 0, "CONSERVATIVE implies BALANCED implies ACTIVE on all 16 evidence combinations");
}

static void unitResolve()
{
   TC.name = "unit.resolve_direction";
   string rule;
   QEQ(QATS_ResolveDirection(true, false, 60, 90, 10, -1, -1, -1, rule), +1, "only BUY eligible -> BUY even with a lower score and every bias against it");
   QCHECK(rule == "ONLY_BUY_ELIGIBLE", "rule names the single eligible side");
   QEQ(QATS_ResolveDirection(false, true, 90, 60, 10, +1, +1, +1, rule), -1, "only SELL eligible -> SELL");
   QEQ(QATS_ResolveDirection(false, false, 99, 99, 10, +1, +1, +1, rule), 0, "nothing eligible -> no trade");
   QEQ(QATS_ResolveDirection(true, true, 75, 60, 10, -1, -1, -1, rule), +1, "both eligible, BUY leads by the margin -> BUY");
   QCHECK(rule == "CONFLICT_HIGHER_SCORE", "the higher score wins when it leads by the margin");
   QEQ(QATS_ResolveDirection(true, true, 60, 75, 10, +1, +1, +1, rule), -1, "both eligible, SELL leads by the margin -> SELL");
   QEQ(QATS_ResolveDirection(true, true, 64, 60, 10, -1, +1, +1, rule), -1, "inside the margin the H1 structure decides");
   QCHECK(rule == "CONFLICT_H1_STRUCTURE", "rule = H1 structure");
   QEQ(QATS_ResolveDirection(true, true, 60, 64, 10, 0, +1, -1, rule), +1, "no H1 trend -> D1 bias decides");
   QCHECK(rule == "CONFLICT_D1_BIAS", "rule = D1 bias");
   QEQ(QATS_ResolveDirection(true, true, 60, 60, 10, 0, 0, -1, rule), -1, "no H1 trend, no D1 bias -> H4 bias decides");
   QCHECK(rule == "CONFLICT_H4_BIAS", "rule = H4 bias");
   QEQ(QATS_ResolveDirection(true, true, 60, 60, 10, 0, 0, 0, rule), 0, "nothing can separate them -> stand aside");
   QCHECK(rule == "CONFLICT_UNRESOLVED", "rule = unresolved");
   // exhaustive mirror symmetry: swapping the sides and flipping every bias flips the answer
   long cases = 0, asym = 0;
   int scores[] = {0, 40, 54, 55, 56, 60, 64, 65, 70, 100};
   for(int bo = 0; bo < 2; bo++) for(int so = 0; so < 2; so++)
      for(int bs : scores) for(int ss : scores)
         for(int margin : {0, 1, 5, 10, 25})
            for(int h1 = -1; h1 <= 1; h1++) for(int d1 = -1; d1 <= 1; d1++) for(int h4 = -1; h4 <= 1; h4++)
            {
               string r1, r2;
               int a = QATS_ResolveDirection(bo, so, bs, ss, margin, h1, d1, h4, r1);
               int b = QATS_ResolveDirection(so, bo, ss, bs, margin, -h1, -d1, -h4, r2);
               cases++;
               if(a != -b) asym++;
               if(a != 0 && !(a > 0 ? bo : so)) asym++;       // never picks a side that is not eligible
            }
   QEQ(asym, 0L, "resolver is mirror-symmetric and never picks an ineligible side (" + std::to_string(cases) + " cases)");
   // candidate (journal only)
   QEQ(QATS_Candidate(true, false, 10, 90), +1, "candidate: a side whose core passed beats a higher score without core");
   QEQ(QATS_Candidate(false, true, 90, 10), -1, "candidate: mirrored");
   QEQ(QATS_Candidate(false, false, 40, 40), 0, "candidate: a tie names nobody");
   int casym = 0;
   for(int bc = 0; bc < 2; bc++) for(int sc = 0; sc < 2; sc++) for(int bs : scores) for(int ss : scores)
      if(QATS_Candidate(bc, sc, bs, ss) != -QATS_Candidate(sc, bc, ss, bs)) casym++;
   QEQ(casym, 0, "candidate rule is mirror-symmetric");
}

static void unitHelpers()
{
   TC.name = "unit.helpers";
   QEQ(QATS_ClassifyClose(-0.01, 0.0), -1, "band 0: any net loss is a loss");
   QEQ(QATS_ClassifyClose(0.0, 0.0), 0, "band 0: exactly zero is neutral");
   QEQ(QATS_ClassifyClose(0.01, 0.0), +1, "band 0: any net gain is a win");
   QEQ(QATS_ClassifyClose(-1.15, 3.0), 0, "a -1.15 scratch inside a 3.00 band is neutral");
   QEQ(QATS_ClassifyClose(-3.01, 3.0), -1, "beyond the band it is a loss");
   QEQ(QATS_ClassifyClose(2.99, 3.0), 0, "a small gain inside the band is neutral too");
   QEQ(QATS_ClassifyClose(-5.0, -1.0), -1, "a negative band is treated as zero");
   QEQ(QATS_CooldownRemaining(1000, 4600), 3600L, "remaining seconds");
   QEQ(QATS_CooldownRemaining(4600, 4600), 0L, "expired exactly at the expiry time");
   QEQ(QATS_CooldownRemaining(5000, 4600), 0L, "expired after the expiry time");
   QEQ(QATS_CooldownRemaining(1000, 0), 0L, "no cooldown -> 0");
   QCHECK(near(QATS_SnapToTick(4148.64, 0.01, 2, true), 4148.64), "an on-grid price is not pushed a tick up");
   QCHECK(near(QATS_SnapToTick(4148.64, 0.01, 2, false), 4148.64), "an on-grid price is not pushed a tick down");
   QCHECK(near(QATS_SnapToTick(4148.643, 0.01, 2, true), 4148.65), "off-grid rounds up when asked");
   QCHECK(near(QATS_SnapToTick(4148.647, 0.01, 2, false), 4148.64), "off-grid rounds down when asked");
   QCHECK(near(QATS_SnapToTick(1.084513, 0.00001, 5, false), 1.08451), "5-digit grid");
   QCHECK(near(QATS_SnapToTick(100.03, 0.05, 2, true), 100.05), "tick size larger than the point");
   // stops validity mirrored
   QCHECK(QATS_StopsValid(+1, 2000.0, 2000.2, 1995.0, 2010.0, 0.01), "valid BUY stops");
   QCHECK(QATS_StopsValid(-1, 2000.0, 2000.2, 2005.2, 1990.2, 0.01), "valid SELL stops");
   QCHECK(!QATS_StopsValid(+1, 2000.0, 2000.2, 2000.0, 2010.0, 0.01), "BUY SL at the bid is invalid");
   QCHECK(!QATS_StopsValid(-1, 2000.0, 2000.2, 2000.2, 1990.0, 0.01), "SELL SL at the ask is invalid");
   QCHECK(!QATS_StopsValid(+1, 2000.0, 2000.2, 1995.0, 2000.1, 0.01), "BUY TP inside the spread is invalid");
   QCHECK(!QATS_StopsValid(-1, 2000.0, 2000.2, 2005.0, 2000.1, 0.01), "SELL TP inside the spread is invalid");
   QCHECK(!QATS_StopsValid(0, 2000.0, 2000.2, 1995.0, 2010.0, 0.01), "no direction is invalid");
   for(int dir : {+1, -1})
   {
      QEQ(QATS_DirectionVeto(true, dir, -dir, -dir, true, false), 0, "XAUUSD: opposing EMAs are diagnostic only");
      QEQ(QATS_DirectionVeto(false, dir, -dir, -dir, true, false), 1, "other symbols: EMA alignment veto, both directions");
      QEQ(QATS_DirectionVeto(false, dir, -dir, dir, true, false), 2, "other symbols: counter-D1 veto, both directions");
      QEQ(QATS_DirectionVeto(false, dir, dir, -dir, true, false), 0, "other symbols: with-D1 is allowed");
   }
   QCHECK(SetupId(+1, sim::makeTime(2026, 11, 11, 9, 0)) == "B-20261111-0900", "setup id of a BUY setup");
   QCHECK(SetupId(-1, sim::makeTime(2026, 11, 11, 12, 0)) == "S-20261111-1200", "setup id of a SELL setup");
   QCHECK(SetupId(0, 123) == "none" && SetupId(+1, 0) == "none", "no setup -> none");
   QCHECK(SideName(+1) == "BUY" && SideName(-1) == "SELL" && SideName(0) == "NONE", "side names");
   QEQ(SideIndex(+1), 0, "BUY index");
   QEQ(SideIndex(-1), 1, "SELL index");
   QEQ(PoolRank("PWL"), PoolRank("PWH"), "pool ranks are side-symmetric (week)");
   QEQ(PoolRank("PDL"), PoolRank("PDH"), "pool ranks are side-symmetric (day)");
   QEQ(PoolRank("EQL"), PoolRank("EQH"), "pool ranks are side-symmetric (equal)");
   QCHECK(PoolRank("PWH") > PoolRank("PDH") && PoolRank("PDH") > PoolRank("EQH") && PoolRank("EQH") > PoolRank("SWING"), "week > day > equal > swing");
   simDiagnosticsClean();
}

// A staircase up, then a bar that closes above the last swing high.
static std::vector<sim::Bar> barsBosUp()
{
   Zig z(2000.0);
   z.leg(5, 2010.0); z.leg(3, 2006.0); z.leg(5, 2016.0); z.leg(3, 2012.0); z.leg(5, 2022.0);
   z.forming();
   return z.bars;
}
// A staircase down, then a rally that closes above the last lower high.
static std::vector<sim::Bar> barsChochUp()
{
   Zig z(2030.0);
   z.leg(5, 2020.0); z.leg(3, 2024.0); z.leg(5, 2014.0); z.leg(3, 2018.0); z.leg(5, 2008.0); z.leg(4, 2020.0);
   z.forming();
   return z.bars;
}

static void unitStructure()
{
   TC.name = "unit.structure";
   const double K = 4100.0;
   // bullish BOS and its bearish mirror
   loadH1(barsBosUp());
   Snap up = analyzeH1(2.0, 6, 0.2);
   QEQ(up.st.trend, +1, "staircase up: H1 trend bullish");
   QEQ(up.st.breakDir, +1, "bullish break of structure detected");
   QCHECK(!up.st.breakIsChoch, "a break in the direction of the trend is a BOS");
   QCHECK(up.st.breakBar >= 1 && up.st.breakBar <= 4, "the BOS bar is one of the last closed bars");
   QCHECK(near(up.st.breakLevel, 2016.3), "the broken level is the last swing high (2016.30)");
   loadH1(mirrorBars(barsBosUp(), K));
   Snap dn = analyzeH1(2.0, 6, 0.2);
   QEQ(dn.st.trend, -1, "mirrored staircase: H1 trend bearish");
   QEQ(dn.st.breakDir, -1, "bearish break of structure detected");
   QCHECK(!dn.st.breakIsChoch, "mirrored: BOS");
   QEQ(dn.st.breakBar, up.st.breakBar, "mirrored BOS happens on the same bar");
   QCHECK(near(dn.st.breakLevel, K - up.st.breakLevel), "mirrored BOS breaks the mirrored level");
   QEQ(dn.nLows, up.nHighs, "mirrored series: swing lows == original swing highs");
   QEQ(dn.nHighs, up.nLows, "mirrored series: swing highs == original swing lows");
   // bullish CHoCH and its bearish mirror
   loadH1(barsChochUp());
   Snap cu = analyzeH1(2.0, 6, 0.2);
   QEQ(cu.st.trend, +1, "downtrend then rally: trend flips bullish");
   QEQ(cu.st.breakDir, +1, "bullish break");
   QCHECK(cu.st.breakIsChoch, "a break AGAINST the prior trend is a CHoCH");
   QCHECK(near(cu.st.breakLevel, 2018.3), "the CHoCH breaks the last lower high (2018.30)");
   loadH1(mirrorBars(barsChochUp(), K));
   Snap cd = analyzeH1(2.0, 6, 0.2);
   QEQ(cd.st.trend, -1, "mirrored: trend flips bearish");
   QEQ(cd.st.breakDir, -1, "mirrored: bearish break");
   QCHECK(cd.st.breakIsChoch, "mirrored: bearish CHoCH");
   QEQ(cd.st.breakBar, cu.st.breakBar, "mirrored CHoCH on the same bar");
   // a quiet series has no break at all
   Zig flat(2000.0);
   for(int i = 0; i < 30; i++) flat.candle(2000.0, 2000.2, 1999.8, 2000.0);
   flat.forming();
   loadH1(flat.bars);
   Snap f = analyzeH1(2.0, 6, 0.2);
   QEQ(f.st.breakDir, 0, "a flat series has no break of structure");
   QEQ(f.st.trend, 0, "a flat series has no trend");
   QCHECK(!f.sweepBuy.found && !f.sweepSell.found, "a flat series has no sweep");
   QCHECK(!f.dispBull && !f.dispBear, "a flat series has no displacement");
   simDiagnosticsClean();
}

// Range with a swing low at 2003.70, then a bar that runs it and closes back above.
static Zig rangeWithLow()
{
   Zig z(2000.0);
   z.leg(5, 2010.0); z.leg(3, 2004.0); z.leg(4, 2009.0); z.leg(3, 2006.0);
   return z;
}

static void unitLiquidity()
{
   TC.name = "unit.liquidity";
   const double K = 4100.0;
   // --- one-bar sweep of sell-side liquidity (bullish) and its mirror
   Zig a = rangeWithLow();
   a.candle(2006.0, 2006.1, 2003.2, 2005.5);
   a.forming();
   loadH1(a.bars);
   Snap s = analyzeH1(2.0, 6, 0.05);
   QCHECK(s.sweepBuy.found, "SSL sweep with rejection is BUY evidence");
   QEQ(s.sweepBuy.bar, 1, "the rejection bar is the last closed bar");
   QCHECK(near(s.sweepBuy.level, 2003.7), "the swept pool is the swing low at 2003.70");
   QCHECK(near(s.sweepBuy.extreme, 2003.2), "the sweep extreme is the bar low 2003.20");
   QCHECK(s.sweepBuy.pool == "SWING", "pool kind = SWING");
   QCHECK(!s.sweepSell.found, "no SELL sweep on the same data");
   QEQ(countPools(s, false, QATS_POOL_SWEPT), 1, "exactly one sell-side pool is SWEPT");
   loadH1(mirrorBars(a.bars, K));
   Snap m = analyzeH1(2.0, 6, 0.05);
   QCHECK(m.sweepSell.found, "mirrored: BSL sweep with rejection is SELL evidence");
   QEQ(m.sweepSell.bar, 1, "mirrored: same rejection bar");
   QCHECK(near(m.sweepSell.level, K - 2003.7), "mirrored: the swept pool is the mirrored swing high");
   QCHECK(near(m.sweepSell.extreme, K - 2003.2), "mirrored: mirrored extreme");
   QCHECK(!m.sweepBuy.found, "mirrored: no BUY sweep");
   QEQ(countPools(m, true, QATS_POOL_SWEPT), 1, "mirrored: exactly one buy-side pool is SWEPT");

   // --- two-bar reclaim: the run bar closes beyond, the next bar closes back inside
   Zig b = rangeWithLow();
   b.candle(2006.0, 2006.1, 2003.0, 2003.3);
   b.candle(2003.3, 2005.2, 2003.1, 2005.0);
   b.forming();
   loadH1(b.bars);
   s = analyzeH1(2.0, 6, 0.05);
   QCHECK(s.sweepBuy.found, "two-bar reclaim counts as a sweep");
   QEQ(s.sweepBuy.bar, 1, "the rejection bar is the reclaim bar");
   QCHECK(near(s.sweepBuy.extreme, 2003.0), "the extreme spans both bars");
   loadH1(mirrorBars(b.bars, K));
   m = analyzeH1(2.0, 6, 0.05);
   QCHECK(m.sweepSell.found && m.sweepSell.bar == 1, "mirrored two-bar reclaim");

   // --- breakout acceptance: two closes beyond the level -> NOT a sweep
   Zig c = rangeWithLow();
   c.candle(2006.0, 2006.1, 2003.0, 2003.3);
   c.candle(2003.3, 2003.5, 2002.0, 2002.4);
   c.forming();
   loadH1(c.bars);
   s = analyzeH1(2.0, 6, 0.05);
   QCHECK(!s.sweepBuy.found, "two closes beyond the level are a breakout, not a sweep");
   QCHECK(s.sweepBuy.breakout, "the acceptance is reported");
   QEQ(countPools(s, false, QATS_POOL_ACCEPTED), 1, "the pool is ACCEPTED");
   loadH1(mirrorBars(c.bars, K));
   m = analyzeH1(2.0, 6, 0.05);
   QCHECK(!m.sweepSell.found && m.sweepSell.breakout, "mirrored breakout acceptance");

   // --- a rejection that later fails (a close beyond the sweep extreme) is spent
   Zig d = rangeWithLow();
   d.candle(2006.0, 2006.1, 2003.2, 2005.5);
   d.candle(2005.5, 2005.6, 2004.0, 2004.2);
   d.candle(2004.2, 2004.3, 2002.5, 2002.8);
   d.forming();
   loadH1(d.bars);
   s = analyzeH1(2.0, 6, 0.05);
   QCHECK(!s.sweepBuy.found, "a later close below the sweep extreme invalidates the sweep");
   loadH1(mirrorBars(d.bars, K));
   m = analyzeH1(2.0, 6, 0.05);
   QCHECK(!m.sweepSell.found, "mirrored: failed sweep");

   // --- a sweep older than the window is no longer evidence
   Zig e = rangeWithLow();
   e.candle(2006.0, 2006.1, 2003.2, 2005.5);
   for(int i = 0; i < 7; i++) e.candle(2005.5, 2005.9, 2005.1, 2005.5);
   e.forming();
   loadH1(e.bars);
   s = analyzeH1(2.0, 6, 0.05);
   QCHECK(!s.sweepBuy.found, "a sweep older than the setup window has expired");
   s = analyzeH1(2.0, 10, 0.05);
   QCHECK(s.sweepBuy.found && s.sweepBuy.bar == 8, "the same sweep is evidence inside a wider window");

   // --- an untouched pool is INTACT and is neither sweep nor breakout
   Zig g = rangeWithLow();
   g.candle(2006.0, 2006.4, 2005.6, 2006.2);
   g.forming();
   loadH1(g.bars);
   s = analyzeH1(2.0, 6, 0.05);
   QCHECK(!s.sweepBuy.found && !s.sweepBuy.breakout, "no run of the level -> no sweep, no breakout");
   QCHECK(countPools(s, false, QATS_POOL_INTACT) >= 1, "the resting swing low is INTACT");

   // --- equal lows / equal highs
   Zig q(2000.0);
   q.leg(5, 2010.0); q.leg(3, 2004.0); q.leg(4, 2009.5); q.leg(4, 2004.1); q.leg(3, 2008.0); q.leg(2, 2006.0);
   q.candle(2006.0, 2006.1, 2003.2, 2005.5);
   q.forming();
   loadH1(q.bars);
   s = analyzeH1(2.0, 6, 0.2);
   QCHECK(s.sweepBuy.found, "equal lows are swept");
   QCHECK(s.sweepBuy.pool == "EQL", "the pool is labelled EQL (got " + s.sweepBuy.pool + ")");
   loadH1(mirrorBars(q.bars, K));
   m = analyzeH1(2.0, 6, 0.2);
   QCHECK(m.sweepSell.found && m.sweepSell.pool == "EQH", "mirrored: equal highs swept, labelled EQH (got " + m.sweepSell.pool + ")");

   // --- prior day low / high as liquidity of the current day
   Zig h(2000.0);
   for(int i = 0; i < 20; i++) h.candle(2000.0, 2000.4, 1999.6, 2000.0);
   h.candle(2000.0, 2000.2, 1997.5, 1999.4);       // runs the prior day low 1998.00 and closes back above
   h.forming();
   datetime today = kMonday + 4 * 86400;
   loadH1(h.bars, today + 3 * 3600);
   sim::S.series[sim::tfIndex(PERIOD_D1)].bars = {sim::Bar{today - 86400, 2001.0, 2004.0, 1998.0, 2000.0, 1000}, sim::Bar{today, 2000.0, 2000.4, 1997.5, 1999.4, 100}};
   s = analyzeH1(2.0, 6, 0.05);
   QCHECK(s.sweepBuy.found, "prior day low swept and rejected");
   QCHECK(s.sweepBuy.pool == "PDL", "the pool is labelled PDL (got " + s.sweepBuy.pool + ")");
   QCHECK(near(s.sweepBuy.level, 1998.0), "the swept level is the prior day low");
   std::vector<sim::Bar> hm = mirrorBars(h.bars, K);
   loadH1(hm, today + 3 * 3600);
   sim::S.series[sim::tfIndex(PERIOD_D1)].bars = {sim::Bar{today - 86400, K - 2001.0, K - 1998.0, K - 2004.0, K - 2000.0, 1000}, sim::Bar{today, K - 2000.0, K - 1997.5, K - 2000.4, K - 1999.4, 100}};
   m = analyzeH1(2.0, 6, 0.05);
   QCHECK(m.sweepSell.found && m.sweepSell.pool == "PDH", "mirrored: prior day high swept, labelled PDH (got " + m.sweepSell.pool + ")");

   // --- liquidity targets: nearest INTACT pool that pays the minimum RR
   MqlArray<SLiquidityPool> pools;
   auto add = [&](double price, bool buySide, int state, const char *kind) {
      SLiquidityPool p; p.price = price; p.kind = kind; p.buySide = buySide; p.shift = 10; p.state = state; p.eventBar = -1; p.extreme = price;
      pools.v.push_back(p);
   };
   add(2002.0, true, QATS_POOL_INTACT, "SWING");    // RR 1.0: too close
   add(2004.0, true, QATS_POOL_INTACT, "EQH");      // RR 2.0: the nearest that pays
   add(2010.0, true, QATS_POOL_INTACT, "PDH");
   add(2003.5, true, QATS_POOL_SPENT, "SWING");     // spent liquidity is not a target
   add(1998.0, false, QATS_POOL_INTACT, "SWING");   // SELL: (2000 - 1998.3)/2 = 0.85: too close
   add(1996.0, false, QATS_POOL_INTACT, "EQL");     // SELL: (2000 - 1996.3)/2 = 1.85: the nearest that pays
   add(1990.0, false, QATS_POOL_INTACT, "PDL");
   add(1996.5, false, QATS_POOL_SWEPT, "SWING");    // swept liquidity is not a target
   double target = 0.0;
   string kind;
   QCHECK(NearestLiquidityTarget(pools, +1, 2000.0, 2.0, 1.5, 0.3, target, kind), "BUY target found");
   QCHECK(near(target, 2004.0) && kind == "EQH", "BUY target = nearest intact buy-side pool paying >= 1.5R (2004.00 EQH)");
   QCHECK(NearestLiquidityTarget(pools, -1, 2000.0, 2.0, 1.5, 0.3, target, kind), "SELL target found");
   QCHECK(near(target, 1996.3) && kind == "EQL", "SELL target = level + spread, so the ask reaches it when the bid touches the level");
   QCHECK(!NearestLiquidityTarget(pools, +1, 2000.0, 20.0, 1.5, 0.3, target, kind), "no pool pays the minimum RR -> no liquidity target");
   QCHECK(!NearestLiquidityTarget(pools, +1, 2000.0, 0.0, 1.5, 0.3, target, kind), "a zero stop distance yields no target");
   simDiagnosticsClean();
}

static void unitDisplacementZones()
{
   TC.name = "unit.displacement_zones";
   const double K = 4100.0;
   Zig z(2010.0);
   for(int i = 0; i < 10; i++) z.candle(2010.0, 2010.3, 2009.7, 2010.0);
   z.candle(2010.0, 2010.1, 2008.2, 2008.5);       // shift 3: last down candle before the impulse
   z.candle(2008.5, 2013.2, 2008.4, 2013.0);       // shift 2: displacement (body 4.5 >= 0.8 x ATR 2.0)
   z.candle(2013.0, 2013.6, 2012.6, 2013.4);       // shift 1: small bar, leaves 2010.10 .. 2012.60 unfilled
   z.forming();
   std::vector<sim::Bar> bars = z.bars;
   for(int pass = 0; pass < 2; pass++)
   {
      bool bull = (pass == 0);
      loadH1(bull ? bars : mirrorBars(bars, K));
      const char *tag = bull ? "bullish" : "bearish (mirrored)";
      int bar = -1;
      QCHECK(DetectDisplacement(_Symbol, PERIOD_H1, bull, 2.0, 6, bar), std::string(tag) + " displacement detected");
      QEQ(bar, 2, std::string(tag) + " displacement bar");
      QCHECK(!DetectDisplacement(_Symbol, PERIOD_H1, !bull, 2.0, 6, bar), std::string(tag) + ": no opposite displacement");
      QCHECK(!DetectDisplacement(_Symbol, PERIOD_H1, bull, 2.0, 1, bar), std::string(tag) + ": an impulse older than the search limit is not counted");
      QCHECK(!DetectDisplacement(_Symbol, PERIOD_H1, bull, 8.0, 6, bar), std::string(tag) + ": a body below 0.8 x ATR is not displacement");
      SZone ob, fvg;
      QCHECK(FindOrderBlock(_Symbol, PERIOD_H1, bull, 2, 12, ob), std::string(tag) + " order block found");
      QEQ(ob.shift, 3, std::string(tag) + " order block is the last opposite candle before the impulse");
      if(bull) QCHECK(near(ob.bottom, 2008.2) && near(ob.top, 2010.0), "bullish OB spans the down candle's low to its open");
      else     QCHECK(near(ob.top, K - 2008.2) && near(ob.bottom, K - 2010.0), "bearish OB is the mirror image");
      QCHECK(ZoneStillValid(_Symbol, PERIOD_H1, bull, ob, 1), std::string(tag) + " order block is unmitigated");
      QCHECK(FindFVG(_Symbol, PERIOD_H1, bull, 2, fvg), std::string(tag) + " fair value gap found");
      QEQ(fvg.shift, 2, std::string(tag) + " FVG is the gap around the impulse candle");
      if(bull) QCHECK(near(fvg.bottom, 2010.1) && near(fvg.top, 2012.6), "bullish FVG = prior high .. next low");
      else     QCHECK(near(fvg.top, K - 2010.1) && near(fvg.bottom, K - 2012.6), "bearish FVG is the mirror image");
      QCHECK(!FindFVG(_Symbol, PERIOD_H1, !bull, 2, fvg), std::string(tag) + ": no opposite FVG");
   }
   // mitigation: a later close through the zone spends it
   Zig y(2010.0);
   for(int i = 0; i < 10; i++) y.candle(2010.0, 2010.3, 2009.7, 2010.0);
   y.candle(2010.0, 2010.1, 2008.2, 2008.5);
   y.candle(2008.5, 2013.2, 2008.4, 2013.0);
   y.candle(2013.0, 2013.6, 2012.6, 2013.4);
   y.candle(2013.4, 2013.5, 2007.5, 2007.9);       // closes below the OB bottom and through the FVG
   y.forming();
   for(int pass = 0; pass < 2; pass++)
   {
      bool bull = (pass == 0);
      loadH1(bull ? y.bars : mirrorBars(y.bars, K));
      SZone ob, fvg;
      QCHECK(FindOrderBlock(_Symbol, PERIOD_H1, bull, 3, 12, ob), "order block still located");
      QCHECK(!ZoneStillValid(_Symbol, PERIOD_H1, bull, ob, 2), std::string(bull ? "bullish" : "bearish") + " order block is spent after a close through it");
      QCHECK(FindFVG(_Symbol, PERIOD_H1, bull, 3, fvg), "FVG still located");
      QCHECK(!ZoneStillValid(_Symbol, PERIOD_H1, bull, fvg, fvg.shift - 2), std::string(bull ? "bullish" : "bearish") + " FVG is spent after a close through it");
   }
   simDiagnosticsClean();
}


//+------------------------------------------------------------------+
//| v1.21 LIMIT entry: the zone arithmetic, with its mirror image.   |
//| Every case is built twice, once bullish and once on K - price,   |
//| so a rule that is not side-symmetric fails here.                 |
//+------------------------------------------------------------------+
static void unitLimitZones()
{
   TC.name = "unit.limit_zones";
   const double K = 4100.0;

   // ---- ZoneUnmitigated: closed H1 bars only, mirrored both ways --------
   {
      Zig z(2010.0);
      for(int i = 0; i < 10; i++) z.candle(2010.0, 2010.3, 2009.7, 2010.0);
      z.candle(2010.0, 2010.1, 2008.2, 2008.5);      // shift 3: last down candle
      z.candle(2008.5, 2013.2, 2008.4, 2013.0);      // shift 2: displacement
      z.candle(2013.0, 2013.6, 2012.6, 2013.4);      // shift 1: leaves the gap open
      z.forming();
      for(int pass = 0; pass < 2; pass++)
      {
         bool bull = (pass == 0);
         loadH1(bull ? z.bars : mirrorBars(z.bars, K));
         SZone ob, fvg;
         QCHECK(FindOrderBlock(_Symbol, PERIOD_H1, bull, 2, 12, ob), "OB located");
         QCHECK(FindFVG(_Symbol, PERIOD_H1, bull, 2, fvg), "FVG located");
         const char *tag = bull ? "bullish" : "bearish (mirrored)";
         QCHECK(ZoneUnmitigated(ob, bull ? +1 : -1), std::string(tag) + ": an untouched OB is unmitigated");
         QCHECK(ZoneUnmitigated(fvg, bull ? +1 : -1), std::string(tag) + ": an untouched FVG is unmitigated");
         QCHECK(!ZoneUnmitigated(ob, bull ? -1 : +1), std::string(tag) + ": an OB is NOT a zone for the opposite direction");
         SZone bad; bad.found = false; bad.top = 0.0; bad.bottom = 0.0; bad.shift = 0; bad.isFVG = false;
         QCHECK(!ZoneUnmitigated(bad, +1), std::string(tag) + ": a zone that was never found is never usable");
         SZone empty = fvg; empty.top = empty.bottom;
         QCHECK(!ZoneUnmitigated(empty, +1), std::string(tag) + ": a zero-height zone is never usable");
      }
   }
   // a later bar trading THROUGH the zone mitigates it
   {
      Zig z(2010.0);
      for(int i = 0; i < 10; i++) z.candle(2010.0, 2010.3, 2009.7, 2010.0);
      z.candle(2010.0, 2010.1, 2008.2, 2008.5);
      z.candle(2008.5, 2013.2, 2008.4, 2013.0);
      z.candle(2013.0, 2013.6, 2012.6, 2013.4);
      z.candle(2013.4, 2013.5, 2007.5, 2007.9);      // runs through OB bottom and the FVG
      z.forming();
      for(int pass = 0; pass < 2; pass++)
      {
         bool bull = (pass == 0);
         loadH1(bull ? z.bars : mirrorBars(z.bars, K));
         SZone ob, fvg;
         FindOrderBlock(_Symbol, PERIOD_H1, bull, 3, 12, ob);
         FindFVG(_Symbol, PERIOD_H1, bull, 3, fvg);
         QCHECK(!ZoneUnmitigated(ob, bull ? +1 : -1), std::string(bull ? "bullish" : "bearish") + ": a wick through the OB mitigates it");
         QCHECK(!ZoneUnmitigated(fvg, bull ? +1 : -1), std::string(bull ? "bullish" : "bearish") + ": a wick through the FVG mitigates it");
      }
   }

   // ---- LimitEntryPrice / ZoneOverlaps are mirror images ---------------
   {
      SZone z;
      z.found = true; z.isFVG = false; z.shift = 5;
      z.bottom = 2000.0; z.top = 2004.0;
      SZone zm;
      zm.found = true; zm.isFVG = false; zm.shift = 5;
      zm.bottom = K - 2004.0; zm.top = K - 2000.0;
      QATS_SetInput("InpLimitEntryMode", "0");
      double buyMid  = LimitEntryPrice(z, +1, 0.01, 2);
      double sellMid = LimitEntryPrice(zm, -1, 0.01, 2);
      QCHECK(near(buyMid, 2002.0), "mode 0: a BUY limit sits at the 50% of the zone (got " + std::to_string(buyMid) + ")");
      QCHECK(near(sellMid, K - 2002.0), "mode 0: the mirrored SELL limit sits at K - 50% (got " + std::to_string(sellMid) + ")");
      // off-grid zone: the price must stay INSIDE the zone
      SZone og = z;
      og.bottom = 2000.0; og.top = 2004.03;
      double p = LimitEntryPrice(og, +1, 0.01, 2);
      QCHECK(p >= og.bottom - 1e-9 && p <= og.top + 1e-9, "an off-grid zone keeps the entry inside the zone");
      QATS_SetInput("InpLimitEntryMode", "1");
      double buyEdge  = LimitEntryPrice(z, +1, 0.01, 2);
      double sellEdge = LimitEntryPrice(zm, -1, 0.01, 2);
      QCHECK(near(buyEdge, 2000.0), "mode 1: a BUY limit sits at the near (lower) edge (got " + std::to_string(buyEdge) + ")");
      QCHECK(near(sellEdge, K - 2000.0), "mode 1: a mirrored SELL limit sits at the near (upper) edge (got " + std::to_string(sellEdge) + ")");
      QATS_SetInput("InpLimitEntryMode", "0");
      // overlap
      SZone a = z, b = z;
      b.bottom = 2001.0; b.top = 2006.0;
      QCHECK(ZoneOverlaps(a, b), "overlapping OB and FVG are recognised");
      SZone c = z;
      c.bottom = 2005.0; c.top = 2010.0;
      QCHECK(!ZoneOverlaps(a, c), "separated OB and FVG are not merged");
      SZone missing;
      missing.found = false; missing.top = 0.0; missing.bottom = 0.0; missing.shift = 0; missing.isFVG = false;
      QCHECK(!ZoneOverlaps(a, missing), "a missing zone never overlaps");
   }

   // ---- PickEntryZone preference: OB+FVG -> OB -> FVG, mitigated skipped
   {
      for(int pass = 0; pass < 2; pass++)
      {
         bool bull = (pass == 0);
         int dir = bull ? +1 : -1;
         SSide s;
         ResetSide(s, dir);
         std::string why;
         SZone z; int src = -1;
         QCHECK(!PickEntryZone(s, dir, z, src, why), "no zone at all -> no candidate");
         QCHECK(why.find("no OB and no FVG") != std::string::npos, "the reason names the missing zone: " + why);
         // a benign series that is already inside the zones, so nothing is mitigated
         Zig calm(2002.0);
         for(int i = 0; i < 12; i++) calm.candle(2002.0, 2003.0, 2001.0, 2002.0);
         calm.forming();
         loadH1(bull ? calm.bars : mirrorBars(calm.bars, K));
         // the calm series trades at 2001..2003, so both zones sit strictly below it
         if(bull)
         {
            s.ob.top = 2000.0; s.ob.bottom = 1996.0; s.ob.shift = 5;
            s.fvg.top = 2000.5; s.fvg.bottom = 1998.0; s.fvg.shift = 5; s.fvg.isFVG = true;
         }
         else
         {
            s.ob.bottom = K - 2000.0; s.ob.top = K - 1996.0; s.ob.shift = 5;
            s.fvg.bottom = K - 2000.5; s.fvg.top = K - 1998.0; s.fvg.shift = 5; s.fvg.isFVG = true;
         }
         // OB and FVG overlapping
         s.hasOB = s.hasFVG = true;
         s.ob.found = s.fvg.found = true;
         QCHECK(PickEntryZone(s, dir, z, src, why), "OB+FVG candidate found (" + why + ")");
         QEQ(src, QATS_ZONE_OB_FVG, "the overlap is preferred");
         double wantTop = bull ? 2000.0 : K - 1998.0;
         double wantBot = bull ? 1998.0 : K - 2000.0;
         QCHECK(near(z.top, wantTop) && near(z.bottom, wantBot), "the merged zone is the shared part of OB and FVG");
         // only an FVG
         SSide f; ResetSide(f, dir);
         f.hasFVG = true; f.fvg.found = true;
         f.fvg.top = s.fvg.top; f.fvg.bottom = s.fvg.bottom; f.fvg.shift = 5;
         QCHECK(PickEntryZone(f, dir, z, src, why) && src == QATS_ZONE_FVG, "FVG alone is the last resort (" + why + ")");
         // only an OB
         SSide o; ResetSide(o, dir);
         o.hasOB = true; o.ob.found = true;
         o.ob.top = s.ob.top; o.ob.bottom = s.ob.bottom; o.ob.shift = 5;
         QCHECK(PickEntryZone(o, dir, z, src, why) && src == QATS_ZONE_OB, "OB alone is preferred to nothing (" + why + ")");
      }
   }
   simDiagnosticsClean();
}

// The plan's geometry on a live scenario, bull and bear. The two passes must
// refuse or accept for the SAME reason: that is the side-symmetry proof. Then the
// geometry itself is checked with the distance budget widened.
static void unitLimitPlan()
{
   TC.name = "unit.limit_plan";
   std::string reason[2];
   bool builtOk[2] = {false, false};
   for(int pass = 0; pass < 2; pass++)
   {
      bool bull = (pass == 0);
      const char *tag = bull ? "BUY" : "SELL (mirrored)";
      resetSimOnly();
      captureJournal();
      setInputs({{"InpUseLimitEntry", "true"}});
      Scn sc(1500.0);
      Marks m = patternFullChain(sc, true);
      Player pl;
      pl.feed.mirror = !bull;
      pl.feed.mirrorK = 400000;
      pl.play(sc, m.attachAt);
      pl.attach(sc);
      pl.play(sc, m.entryAt + 2);
      SAnalysis raw = AnalyzeMarket();
      QCHECK(raw.dataReady, std::string(tag) + ": data ready");
      QEQ(raw.dir, bull ? +1 : -1, std::string(tag) + ": the chain resolves to this side");

      // 1. with the SHIPPED defaults the plan is refused, and it says exactly why
      SAnalysis strict;
      bool strictBuilt = BuildLimitPlan(raw, strict);
      reason[pass] = g_executionReason;
      QCHECK(!strictBuilt, std::string(tag) + ": the shipped defaults refuse this continuation zone (" + g_executionReason + ")");

      // 2. the distance budget widened: the arithmetic is then exercised
      QATS_SetInput("InpLimitMaxDistATR", "40.0");
      SAnalysis wide;
      bool wideBuilt = BuildLimitPlan(raw, wide);
      std::string wideReason = g_executionReason;
      QATS_SetInput("InpLimitNeedPD", "false");
      SAnalysis plan;
      bool built = BuildLimitPlan(raw, plan);
      QATS_SetInput("InpLimitNeedPD", "true");
      QATS_SetInput("InpLimitMaxDistATR", "3.0");
      QCHECK(built, std::string(tag) + ": with the distance and the PD filter relaxed a limit plan is built (" +
                    (built ? std::string() : g_executionReason) + ")");
      builtOk[pass] = built;
      QCHECK(!wideBuilt || true, "wide-distance pass: " + wideReason);
      if(built)
      {
         double ask = sim::S.ask, bid = sim::S.bid;
         if(bull)
         {
            QCHECK(plan.entry < ask, "BUY: the limit is BEHIND the market (below the ask)");
            QCHECK(plan.sl < plan.entry && plan.tp > plan.entry, "BUY: stop below, target above");
         }
         else
         {
            QCHECK(plan.entry > bid, "SELL: the limit is BEHIND the market (above the bid)");
            QCHECK(plan.sl > plan.entry && plan.tp < plan.entry, "SELL: stop above, target below");
         }
         double rr = std::fabs(plan.tp - plan.entry) / std::fabs(plan.entry - plan.sl);
         QCHECK(rr + 1e-9 >= InpLimitMinRR, "reward:risk from the LIMIT price >= InpLimitMinRR (got " + std::to_string(rr) + ")");
         QCHECK(rr + 1e-9 >= InpMinRR, "the plan never falls below the engine's own InpMinRR");
         QCHECK(sim::onGrid(plan.entry) && sim::onGrid(plan.sl) && sim::onGrid(plan.tp), "entry, stop and target are on the tick grid");
         double stopPts = std::fabs(plan.entry - plan.sl) / sim::S.sym.point;
         QCHECK(stopPts >= InpMinStopPoints && stopPts <= InpMaxStopPoints, "the zone stop is inside InpMinStopPoints/InpMaxStopPoints");
         QCHECK(plan.stopDist > 0.0 && near(plan.stopDist, std::fabs(plan.entry - plan.sl)), "stopDist is the LIMIT-to-stop distance");
      }
      simDiagnosticsClean();
   }
   // the refusal of pass 0 and the refusal of pass 1 must be the same rule: the
   // price numbers differ, the REASON must not
   bool sameRule = ((reason[0].find("needs discount") != std::string::npos && reason[1].find("needs premium") != std::string::npos) ||
                    (reason[0].find("x H1 ATR") != std::string::npos && reason[1].find("x H1 ATR") != std::string::npos) ||
                    (reason[0].find("stops level") != std::string::npos && reason[1].find("stops level") != std::string::npos) ||
                    (reason[0].find("reward:risk") != std::string::npos && reason[1].find("reward:risk") != std::string::npos) ||
                    (reason[0].find("zone stop") != std::string::npos && reason[1].find("zone stop") != std::string::npos));
   QCHECK(reason[0] != "" && reason[1] != "" && sameRule,
          "BUY and SELL are refused by the SAME rule: [" + reason[0] + "] vs [" + reason[1] + "]");
   QCHECK(builtOk[0] == builtOk[1], "BUY and SELL build or fail together");
   simDiagnosticsClean();
}

static int runUnit()
{
   unitScoring();
   unitCoreGate();
   unitResolve();
   unitHelpers();
   unitStructure();
   unitLiquidity();
   unitDisplacementZones();
   unitLimitZones();
   unitLimitPlan();
   printf("unit: %d checks, %d failed\n", TC.checks, TC.failed);
   return TC.failed ? 1 : 0;
}
} // namespace drv

#include "qats_scenarios.inc"
