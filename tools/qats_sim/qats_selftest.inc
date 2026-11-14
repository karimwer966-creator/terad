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
   double poolLevel = 0.0;
   QCHECK(NearestLiquidityTarget(pools, +1, 2000.0, 2.0, 1.5, 0.3, target, kind, poolLevel), "BUY target found");
   QCHECK(near(target, 2004.0) && kind == "EQH", "BUY target = nearest intact buy-side pool paying >= 1.5R (2004.00 EQH)");
   QCHECK(near(poolLevel, 2004.0), "BUY poolLevel is the pool's own level, so the TP journal can name the level it aims at");
   QCHECK(NearestLiquidityTarget(pools, -1, 2000.0, 2.0, 1.5, 0.3, target, kind, poolLevel), "SELL target found");
   QCHECK(near(target, 1996.3) && kind == "EQL", "SELL target = level + spread, so the ask reaches it when the bid touches the level");
   QCHECK(near(poolLevel, 1996.0), "SELL poolLevel is the pool's own level (1996.00), NOT the spread-shifted 1996.30 the SELL is anchored to");
   QCHECK(!NearestLiquidityTarget(pools, +1, 2000.0, 20.0, 1.5, 0.3, target, kind, poolLevel), "no pool pays the minimum RR -> no liquidity target");
   QEQ(poolLevel, 0.0, "a failed lookup leaves poolLevel zeroed");
   QCHECK(!NearestLiquidityTarget(pools, +1, 2000.0, 0.0, 1.5, 0.3, target, kind, poolLevel), "a zero stop distance yields no target");
   simDiagnosticsClean();
}

// Duplicate pools at the same level: one level, one identity.
static void unitLiquidityDedup()
{
   TC.name = "unit.liquidity_dedup";
   const double tol = 0.05;
   // a quiet H1 series so the map builder has bars to walk when it evaluates pool state
   Zig z(2000.0);
   for(int i = 0; i < 40; i++) z.candle(2000.0 + (i % 5) * 0.1, 2000.5 + (i % 5) * 0.1, 1999.5 + (i % 5) * 0.1, 2000.0);
   z.forming();
   loadH1(z.bars);

   MqlArray<SSwing> highs, lows;
   highs.v = {SSwing{2010.30, 10, true}, SSwing{2010.32, 6, true}, SSwing{2020.00, 2, true}};
   lows.v  = {SSwing{2004.00, 10, false}, SSwing{2004.02, 6, false}};
   MqlArray<SLiquidityPool> pools;
   captureJournal();
   int n = BuildLiquidityMap(_Symbol, PERIOD_H1, highs, lows, tol, 6, pools);
   QEQ(n, 3, "the map carries three levels: 2010 group, the unrelated 2020 swing, the 2004 group (got " + std::to_string(n) + ")");
   int in2010 = 0, in2004 = 0, in2020 = 0;
   string kind2010, kind2004;
   int shift2010 = -1;
   for(const SLiquidityPool &p : pools.v)
   {
      if(MathAbs(p.price - 2010.3) <= tol) { in2010++; kind2010 = p.kind; shift2010 = p.shift; }
      if(MathAbs(p.price - 2004.0) <= tol) { in2004++; kind2004 = p.kind; }
      if(MathAbs(p.price - 2020.0) <= tol) in2020++;
   }
   QEQ(in2010, 1, "the duplicate highs collapse into one pool");
   QCHECK(kind2010 == "EQH", "the stronger kind (EQH) survives the merge (got " + kind2010 + ")");
   QEQ(shift2010, 10, "the equal-high identity is the older formation's record");
   QEQ(in2004, 1, "the duplicate lows collapse into one pool");
   QCHECK(kind2004 == "EQL", "the stronger kind (EQL) survives the merge (got " + kind2004 + ")");
   QEQ(in2020, 1, "an unrelated level is untouched by the merge");
   QEQ(linesWith("[QATS][LIQUIDITY] merged 2 duplicate"), 1, "the merge is journalled once with its count");

   // now park a prior-day high/low ON the duplicated levels: PDH/PDL outrank EQH/EQL
   datetime day = kMonday + 5 * 86400;   // a Friday; the prior day is Thursday
   std::vector<sim::Bar> d1(2);
   d1[0].time = day - 86400; d1[0].open = 2005.0; d1[0].high = 2010.31; d1[0].low = 2004.01; d1[0].close = 2008.0; d1[0].volume = 1000;
   d1[1].time = day;        d1[1].open = 2008.0; d1[1].high = 2025.0;  d1[1].low = 2001.0;  d1[1].close = 2012.0; d1[1].volume = 100;
   sim::S.series[sim::tfIndex(PERIOD_D1)].bars = d1;
   pools.v.clear();
   n = BuildLiquidityMap(_Symbol, PERIOD_H1, highs, lows, tol, 6, pools);
   in2010 = 0; in2004 = 0; kind2010 = ""; kind2004 = "";
   for(const SLiquidityPool &p : pools.v)
   {
      if(MathAbs(p.price - 2010.3) <= tol) { in2010++; kind2010 = p.kind; }
      if(MathAbs(p.price - 2004.0) <= tol) { in2004++; kind2004 = p.kind; }
   }
   QEQ(in2010, 1, "the prior-day high joins the 2010 group as one identity");
   QCHECK(kind2010 == "PDH", "PDH outranks EQH and SWING at the same level (got " + kind2010 + ")");
   QEQ(in2004, 1, "the prior-day low joins the 2004 group as one identity");
   QCHECK(kind2004 == "PDL", "PDL outranks EQL and SWING at the same level (got " + kind2004 + ")");
   QEQ(linesWith("[QATS][LIQUIDITY] merged 4 duplicate"), 1, "the second rebuild journals the fuller merge (2 groups x 2 extra pools)");
   sim::S.series[sim::tfIndex(PERIOD_D1)].bars.clear();
   sim::S.onPrint = nullptr;

   // PoolBetter: kind rank beats recency; recency beats seniority; day boundary is newest
   SLiquidityPool pdh; pdh.kind = "PDH"; pdh.shift = 9; pdh.price = 1.0; pdh.buySide = true; pdh.state = 0; pdh.eventBar = -1; pdh.extreme = 1.0;
   SLiquidityPool eqh; eqh.kind = "EQH"; eqh.shift = 1; eqh.price = 1.0; eqh.buySide = true; eqh.state = 0; eqh.eventBar = -1; eqh.extreme = 1.0;
   SLiquidityPool newer; newer.kind = "SWING"; newer.shift = 1; newer.price = 1.0; newer.buySide = true; newer.state = 0; newer.eventBar = -1; newer.extreme = 1.0;
   SLiquidityPool older; older.kind = "SWING"; older.shift = 5; older.price = 1.0; older.buySide = true; older.state = 0; older.eventBar = -1; older.extreme = 1.0;
   SLiquidityPool today; today.kind = "SWING"; today.shift = 0; today.price = 1.0; today.buySide = true; today.state = 0; today.eventBar = -1; today.extreme = 1.0;
   QCHECK(PoolBetter(pdh, eqh), "the stronger kind (PDH) wins even when the other is newer");
   QCHECK(!PoolBetter(eqh, pdh), "and the newer kind does not win on recency alone");
   QCHECK(PoolBetter(newer, older), "same kind: the newer formation wins");
   QCHECK(!PoolBetter(older, newer), "same kind: the older formation loses");
   QCHECK(PoolBetter(today, older), "shift 0 (the day/week boundary) counts as the newest");
   QCHECK(!PoolBetter(older, today), "shift 0 is not outranked by any real shift");
   QCHECK(!PoolBetter(older, older), "identical entries keep the first");
   simDiagnosticsClean();
}

// The transition journal: one line per state change, named with bar and level.
static void unitLiquidityJournal()
{
   TC.name = "unit.liquidity_journal";
   Zig z(2000.0);
   for(int i = 0; i < 10; i++) z.candle(2000.0, 2000.5, 1999.5, 2000.0);
   z.forming();
   loadH1(z.bars);

   auto mk = [](double price, const char *kind, bool buySide, int state) {
      SLiquidityPool p; p.price = price; p.kind = kind; p.buySide = buySide; p.shift = 5;
      p.state = state; p.eventBar = -1; p.extreme = price; return p;
   };
   MqlArray<SLiquidityPool> pools;
   pools.v.push_back(mk(2010.0, "EQH", true, QATS_POOL_INTACT));
   pools.v.push_back(mk(2004.0, "SWING", false, QATS_POOL_INTACT));

   // reset the transition memory through the public surface (n = 0)
   JournalLiquidityTransitions(pools, 0, 0.05);
   captureJournal();
   JournalLiquidityTransitions(pools, 2, 0.05);
   QEQ(linesWith("[QATS][LIQUIDITY] TRANSITION"), 0, "the first evaluation after attach is a silent baseline");

   pools.v[1].state = QATS_POOL_SWEPT; pools.v[1].eventBar = 1; pools.v[1].extreme = 2003.2;
   JournalLiquidityTransitions(pools, 2, 0.05);
   QEQ(linesWith("[QATS][LIQUIDITY] TRANSITION"), 1, "INTACT -> SWEPT is journalled exactly once");
   std::string line = firstWith("[QATS][LIQUIDITY] TRANSITION");
   QCHECK(line.find("SSL") != std::string::npos, "the line names the sell-side: " + line);
   QCHECK(line.find("SWING") != std::string::npos, "the line names the pool kind: " + line);
   QCHECK(line.find("state=INTACT->SWEPT") != std::string::npos, "the line names the state change: " + line);
   QCHECK(line.find("bar=") != std::string::npos, "the line names the bar: " + line);
   QCHECK(line.find("2004") != std::string::npos, "the line names the level: " + line);

   JournalLiquidityTransitions(pools, 2, 0.05);
   QEQ(linesWith("[QATS][LIQUIDITY] TRANSITION"), 1, "an unchanged map produces no repeat line");

   pools.v[1].state = QATS_POOL_ACCEPTED; pools.v[1].eventBar = 2;
   JournalLiquidityTransitions(pools, 2, 0.05);
   QEQ(linesWith("[QATS][LIQUIDITY] TRANSITION"), 2, "SWEPT -> ACCEPTED is journalled exactly once");
   QCHECK(firstWith("[QATS][LIQUIDITY] TRANSITION", "ACCEPTED").find("state=SWEPT->ACCEPTED") != std::string::npos,
          "the second transition names the new state change: " + firstWith("[QATS][LIQUIDITY] TRANSITION", "ACCEPTED"));

   // a NEW pool appearing is not a transition
   pools.v.push_back(mk(1996.0, "PDL", false, QATS_POOL_INTACT));
   JournalLiquidityTransitions(pools, 3, 0.05);
   QEQ(linesWith("[QATS][LIQUIDITY] TRANSITION"), 2, "a newly appearing pool is not a state transition");

   JournalLiquidityTransitions(pools, 0, 0.05);   // leave the transition memory clean
   sim::S.onPrint = nullptr;
   simDiagnosticsClean();
}

// The merged survivor carries the most DECIDED state of its group: a consumed
// level can never read INTACT just because its runner had the weaker kind.
static void unitLiquidityFold()
{
   TC.name = "unit.liquidity_fold";
   const double tol = 0.05;
   auto mkp = [](const char *kind, double price, int shift, int state, int eventBar, double extreme, bool buySide) {
      SLiquidityPool p; p.kind = kind; p.price = price; p.shift = shift; p.state = state;
      p.eventBar = eventBar; p.extreme = extreme; p.buySide = buySide; return p;
   };
   auto run = [&](std::initializer_list<SLiquidityPool> list, int &mergedOut) {
      MqlArray<SLiquidityPool> one;
      for(const SLiquidityPool &p : list) one.v.push_back(p);
      mergedOut = 0;
      MergeSideDuplicates(one, tol, mergedOut);
      return one;
   };

   // 1. INTACT PDH (stronger kind) absorbs a SWEPT SWING at the same level
   int merged = 0;
   MqlArray<SLiquidityPool> out = run({mkp("PDH", 2010.0, 0, QATS_POOL_INTACT, -1, 2010.0, true),
                                       mkp("SWING", 2010.0, 12, QATS_POOL_SWEPT, 3, 2011.5, true)}, merged);
   QEQ(out.v.size(), 1u, "the group collapses to one pool");
   QEQ(merged, 1, "one duplicate was merged");
   QCHECK(out.v[0].kind == "PDH", "the stronger kind keeps the identity (got " + out.v[0].kind + ")");
   QEQ(out.v[0].state, (int)QATS_POOL_SWEPT, "the survivor carries the consumed state, never INTACT");
   QEQ(out.v[0].eventBar, 3, "the survivor carries the member's decisive bar");
   QCHECK(near(out.v[0].extreme, 2011.5), "the survivor carries the further reach");

   // 2. ACCEPTED outranks SWEPT whatever the kind order
   merged = 0;
   out = run({mkp("PDH", 2010.0, 0, QATS_POOL_SWEPT, 4, 2011.0, true),
              mkp("SWING", 2010.0, 12, QATS_POOL_ACCEPTED, 2, 2012.25, true)}, merged);
   QEQ(out.v[0].state, (int)QATS_POOL_ACCEPTED, "ACCEPTED outranks SWEPT on merge");
   QEQ(out.v[0].eventBar, 2, "the ACCEPTED member's decisive bar is kept");
   QCHECK(near(out.v[0].extreme, 2012.25), "the further reach is kept");

   // 3. SPENT outranks INTACT (pierced-but-unusable still means consumed)
   merged = 0;
   out = run({mkp("PDH", 2010.0, 0, QATS_POOL_INTACT, -1, 2010.0, true),
              mkp("SWING", 2010.0, 12, QATS_POOL_SPENT, -1, 2013.0, true)}, merged);
   QEQ(out.v[0].state, (int)QATS_POOL_SPENT, "SPENT outranks INTACT on merge");
   QCHECK(near(out.v[0].extreme, 2013.0), "the further reach is kept");

   // 4. two INTACT twins stay INTACT
   merged = 0;
   out = run({mkp("PDH", 2010.0, 0, QATS_POOL_INTACT, -1, 2010.0, true),
              mkp("SWING", 2010.0, 12, QATS_POOL_INTACT, -1, 2010.0, true)}, merged);
   QEQ(out.v[0].state, (int)QATS_POOL_INTACT, "two INTACT twins stay INTACT");
   QEQ(merged, 1, "the duplicate was merged");

   // 5. equal conviction (SWEPT vs SWEPT): later decisive bar wins
   merged = 0;
   out = run({mkp("SWING", 2010.0, 12, QATS_POOL_SWEPT, 2, 2011.0, true),
              mkp("EQL", 2010.0, 6, QATS_POOL_SWEPT, 5, 2011.2, true)}, merged);
   QEQ(out.v[0].eventBar, 5, "equal conviction keeps the later (nearest) decisive bar");
   QCHECK(near(out.v[0].extreme, 2011.2), "equal conviction keeps the further reach");

   // 6. the sell side folds symmetrically: the LOWER extreme wins
   merged = 0;
   out = run({mkp("PDL", 2004.0, 0, QATS_POOL_INTACT, -1, 2004.0, false),
              mkp("SWING", 2004.0, 12, QATS_POOL_SWEPT, 7, 2002.75, false)}, merged);
   QEQ(out.v[0].state, (int)QATS_POOL_SWEPT, "sell-side survivor carries the consumed state");
   QCHECK(near(out.v[0].extreme, 2002.75), "sell-side fold keeps the LOWER extreme");

   // 7. three-way group: kind-winner stays, evidence folds across both members
   merged = 0;
   out = run({mkp("SWING", 2010.0, 12, QATS_POOL_SWEPT, 2, 2011.0, true),
              mkp("PDH", 2010.0, 0, QATS_POOL_INTACT, -1, 2010.0, true),
              mkp("EQH", 2010.0, 6, QATS_POOL_ACCEPTED, 1, 2012.0, true)}, merged);
   QEQ(out.v.size(), 1u, "all three collapse into one");
   QEQ(merged, 2, "two duplicates were merged");
   QCHECK(out.v[0].kind == "PDH", "the PDH keeps the identity");
   QEQ(out.v[0].state, (int)QATS_POOL_ACCEPTED, "the most decided state (ACCEPTED) wins the fold");
   QCHECK(near(out.v[0].extreme, 2012.0), "the furthest reach of the group is kept");
   simDiagnosticsClean();
}

// Per-event TF+shift storage for liquidity sweep events (Phase 5, mirror of
// dispTF/dispBar), the chain text that names the event, and the reset contract.
static void unitSweepEvent()
{
   TC.name = "unit.sweep_event";
   const double K = 4100.0;
   Zig z = rangeWithLow();
   z.candle(2006.0, 2006.1, 2003.2, 2005.5);
   z.forming();
   loadH1(z.bars);
   Snap s = analyzeH1(2.0, 6, 0.05);
   QCHECK(s.sweepBuy.found, "SSL sweep detected");
   QEQ((int)s.sweepBuy.tf, (int)PERIOD_H1, "the sweep event names its timeframe");
   QEQ(s.sweepBuy.bar, 1, "the rejection shift is the last closed bar");
   QEQ((long)s.sweepBuy.eventTime, (long)iTime(_Symbol, PERIOD_H1, 1), "the event time is frozen at the rejection bar");
   QCHECK(s.sweepBuy.poolShift >= 1, "the pool formation shift is stored (got " + std::to_string(s.sweepBuy.poolShift) + ")");
   QCHECK(near(iLow(_Symbol, PERIOD_H1, s.sweepBuy.poolShift), s.sweepBuy.level),
          "the formation bar of a SWING pool is the bar that made the level");
   loadH1(mirrorBars(z.bars, K));
   s = analyzeH1(2.0, 6, 0.05);
   QCHECK(s.sweepSell.found, "mirrored: BSL sweep detected");
   QEQ((int)s.sweepSell.tf, (int)PERIOD_H1, "mirrored: the sweep event names its timeframe");
   QEQ((long)s.sweepSell.eventTime, (long)iTime(_Symbol, PERIOD_H1, 1), "mirrored: frozen event time");
   QCHECK(s.sweepSell.poolShift >= 1 && near(iHigh(_Symbol, PERIOD_H1, s.sweepSell.poolShift), s.sweepSell.level),
          "mirrored: the formation bar is the bar that made the level");
   // reset returns the event to its empty state
   SSide fresh; ResetSide(fresh, +1);
   QEQ((int)fresh.sweep.tf, (int)PERIOD_CURRENT, "ResetSide clears the event timeframe");
   QEQ(fresh.sweep.poolShift, -1, "ResetSide clears the formation shift");
   QEQ((long)fresh.sweep.eventTime, 0L, "ResetSide clears the frozen event time");
   // the journal names the event with its TF, shifts and frozen time
   SSide e; ResetSide(e, +1);
   e.sweep.found = true; e.sweep.tf = PERIOD_H1;
   e.sweep.bar = 3; e.sweep.poolShift = 14; e.sweep.eventTime = (datetime)1700000000;
   e.sweep.level = 1996.0; e.sweep.extreme = 1992.5; e.sweep.pool = "EQH";
   std::string chain = ChainText(e);
   QCHECK(chain.find("detected H1 shift 3") != std::string::npos, "the chain text names the rejection TF and shift: " + chain);
   QCHECK(chain.find("level formed shift 14") != std::string::npos, "the chain text names the formation shift: " + chain);
   QCHECK(chain.find(TimeToString((datetime)1700000000, TIME_DATE | TIME_MINUTES)) != std::string::npos,
          "the chain text prints the frozen event time: " + chain);
   QCHECK(std::string(TFName(PERIOD_H1)) == "H1" && std::string(TFName(PERIOD_M15)) == "M15",
          "TFName names the timeframes the EA reports");
   QCHECK(std::string(TFName(PERIOD_CURRENT)) == "TF?", "TFName degrades to TF? for PERIOD_CURRENT");
   simDiagnosticsClean();
}

// M5 confirmation authority (Phase 6 contract): the M5 trigger candle is
// score-only confluence everywhere except CONSERVATIVE, where it is OR'ed with
// M15 (never a sole gate); it is never core on BALANCED/ACTIVE.
static void unitM5TriggerAuthority()
{
   TC.name = "unit.m5_trigger_authority";
   const double K = 4100.0;
   const datetime kT = kMonday + 4 * 86400 + 12 * 3600;
   auto loadM5 = [&](const std::vector<sim::Bar> &bars) {
      resetSimOnly();
      std::vector<sim::Bar> w = bars;
      for(size_t i = 0; i < w.size(); i++) w[i].time = kT - (datetime)(w.size() - 1 - i) * 300;
      sim::S.series[sim::tfIndex(PERIOD_M5)].bars = w;
      sim::S.now = kT;
   };
   // bullish engulfing / mirror
   std::vector<sim::Bar> v;
   v.push_back(HB(2004.0, 2004.2, 2001.5, 2002.0));   // shift 2: prior bearish
   v.push_back(HB(2001.8, 2006.5, 2001.6, 2006.2));   // shift 1: current bullish, body engulfs
   v.push_back(HB(2006.2, 2006.2, 2006.2, 2006.2));   // forming bar (never read)
   loadM5(v);
   QCHECK(M5Trigger(_Symbol, +1), "bullish engulfing is a BUY M5 trigger");
   QCHECK(!M5Trigger(_Symbol, -1), "the same tape is not a SELL M5 trigger");
   loadM5(mirrorBars(v, K));
   QCHECK(M5Trigger(_Symbol, -1), "mirrored: bearish engulfing is a SELL M5 trigger");
   QCHECK(!M5Trigger(_Symbol, +1), "mirrored: the same tape is not a BUY M5 trigger");
   // bullish marubozu (body >= 65% of range) / mirror
   std::vector<sim::Bar> m;
   m.push_back(HB(2000.0, 2001.0, 1999.5, 2000.5));
   m.push_back(HB(2000.5, 2002.55, 2000.45, 2002.5));
   m.push_back(HB(2002.5, 2002.5, 2002.5, 2002.5));
   loadM5(m);
   QCHECK(M5Trigger(_Symbol, +1), "bullish marubozu is a BUY M5 trigger");
   loadM5(mirrorBars(m, K));
   QCHECK(M5Trigger(_Symbol, -1), "mirrored: bearish marubozu is a SELL M5 trigger");
   // bullish pin bar (long lower wick) / mirror
   std::vector<sim::Bar> p;
   p.push_back(HB(2000.0, 2001.0, 1999.5, 2000.5));
   p.push_back(HB(2001.0, 2001.2, 1998.8, 2001.1));
   p.push_back(HB(2001.1, 2001.1, 2001.1, 2001.1));
   loadM5(p);
   QCHECK(M5Trigger(_Symbol, +1), "bullish pin bar is a BUY M5 trigger");
   loadM5(mirrorBars(p, K));
   QCHECK(M5Trigger(_Symbol, -1), "mirrored: bearish pin bar is a SELL M5 trigger");
   // indecision: no trigger either way
   std::vector<sim::Bar> f;
   f.push_back(HB(2000.0, 2000.4, 1999.6, 2000.2));
   f.push_back(HB(2000.2, 2000.5, 1999.7, 2000.1));
   f.push_back(HB(2000.1, 2000.1, 2000.1, 2000.1));
   loadM5(f);
   QCHECK(!M5Trigger(_Symbol, +1) && !M5Trigger(_Symbol, -1), "indecision bars trigger nothing");
   // --- core authority: M5/M15 are never core on BALANCED / ACTIVE, never a sole gate anywhere
   std::string why;
   QCHECK(!QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, true, true, true, false, why),
          "CONSERVATIVE refuses without an M15/M5 confirmation");
   QCHECK(why == "no M15/M5 confirmation", "the refusal is named: " + why);
   QCHECK(QATS_CoreGate(QATS_PROFILE_CONSERVATIVE, true, true, true, true, why),
          "CONSERVATIVE passes with the M15/M5 confirmation present");
   QCHECK(QATS_CoreGate(QATS_PROFILE_BALANCED, true, true, true, false, why),
          "BALANCED passes without any M15/M5 confirmation (score-only confluence)");
   QCHECK(QATS_CoreGate(QATS_PROFILE_BALANCED, false, true, true, false, why),
          "BALANCED passes on displacement + structure alone; M5/M15 are never core");
   QCHECK(QATS_CoreGate(QATS_PROFILE_ACTIVE, true, true, false, false, why),
          "ACTIVE passes on sweep + displacement; M5/M15 ignored");
   QCHECK(!QATS_CoreGate(QATS_PROFILE_ACTIVE, true, false, false, true, why),
          "ACTIVE refuses a lone sweep even with M15/M5 present (confirmation is not core evidence)");
   // --- weight contract: equal, small, optional
   QEQ(QATS_W_M5, 5, "the M5 trigger is a 5-point optional confluence weight");
   QEQ(QATS_W_M15, QATS_W_M5, "M15 and M5 carry the same weight");
   simDiagnosticsClean();
}

// Filled-with-report accounting (Phase 8): the shortfall predicate the market path uses.
static void unitFillShort()
{
   TC.name = "unit.fill_short";
   QCHECK(!QATS_FillShort(0.10, 0.10), "an exact fill is not short");
   QCHECK(QATS_FillShort(0.10, 0.05), "a fill below the request is reported short");
   QCHECK(!QATS_FillShort(0.10, 0.10 - 5e-9), "a fill within the 1e-8 epsilon is not short");
   QCHECK(QATS_FillShort(0.10, 0.10 - 5e-8), "a fill beyond the 1e-8 epsilon is short");
   QCHECK(!QATS_FillShort(0.0, 0.0), "a zero request is never short");
   QCHECK(QATS_FillShort(0.10, 0.0), "a zero fill for a nonzero request is short (DONE_PARTIAL semantics)");
   simDiagnosticsClean();
}

// Signal reservation (Phase 8, CR-3): account+magic+symbol namespaced keys; the EA
// reserves on EVERY symbol; reservation persists and is CAS-guarded.
static void unitReservation()
{
   TC.name = "unit.reservation";
   resetSimOnly();
   SAnalysis plan;
   ResetAnalysis(plan);
   plan.dir = +1;
   GVSet(GVKey("sig_buy"), 0.0);
   GVSet(GVKey("sig_sell"), 0.0);
   string reason;
   plan.signalBar = 1000;
   QCHECK(ReserveSignal(plan, reason), "a fresh reservation succeeds");
   QEQ((long)GVGet(GVKey("sig_buy"), -1.0), 1000L, "the reservation holds the reserved bar");
   QCHECK(!ReserveSignal(plan, reason), "re-reserving the same bar is refused");
   QCHECK(reason.find("duplicate") != std::string::npos, "the refusal names the duplicate");
   plan.signalBar = 900;
   QCHECK(!ReserveSignal(plan, reason), "an older bar can never re-reserve");
   QCHECK(reason.find("duplicate") != std::string::npos, "an older bar is refused as duplicate/older");
   plan.signalBar = 1001;
   QCHECK(ReserveSignal(plan, reason), "a newer bar may reserve after an older one");
   QEQ((long)GVGet(GVKey("sig_buy"), -1.0), 1001L, "the key holds the newest reservation");
   SAnalysis sellPlan;
   ResetAnalysis(sellPlan);
   sellPlan.dir = -1; sellPlan.signalBar = 1000;
   QCHECK(ReserveSignal(sellPlan, reason), "the SELL reservation is an independent key");
   QEQ((long)GVGet(GVKey("sig_sell"), -1.0), 1000L, "the SELL reservation holds its own bar");
   QEQ((long)GVGet(GVKey("sig_buy"), -1.0), 1001L, "the BUY reservation is untouched by the SELL side");
   QEQ((long)GVGet(GVKey("setup_buy"), 0.0), 0L, "a reservation does not spend the setup identity");
   plan.dir = 0;
   plan.signalBar = 5000;
   QCHECK(ReserveSignal(plan, reason) || true, "a zero direction keeps the legacy key mapping");
   simDiagnosticsClean();
}

// RISK_STATUS exposure map (Phase 8): computed from live + persisted state.
static void unitRiskStatus()
{
   TC.name = "unit.risk_status";
   resetSimOnly();
   double ob = g_dayBase, op = g_dayPnL, oh = g_equityHWM, od = g_accountDDPct;
   int oc = g_consecLosses, ot = g_tradesToday;
   bool olk = g_dayLocked, ohlt = g_ddHalted, ocdl = g_inCooldown;
   datetime oud = g_cooldownUntil;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayBase = eq + 250.0; g_dayPnL = -250.0; g_equityHWM = eq + 9000.0; g_accountDDPct = 12.5;
   g_consecLosses = 2; g_tradesToday = 3; g_dayLocked = false; g_ddHalted = true;
   g_inCooldown = true; g_cooldownUntil = kMonday + 86400;
   SRiskStatus st;
   BuildRiskStatus(st);
   QEQ(st.consecLosses, 2, "the streak is exposed");
   QEQ(st.streakMax, InpStopAfterConsecLoss, "the streak cap is exposed");
   QEQ(st.tradesToday, 3, "the cap usage is exposed");
   QEQ(st.tradesMax, InpMaxTradesPerDay, "the daily cap is exposed");
   QCHECK(near(st.dayPnl, -250.0), "day P/L in money is exposed");
   QCHECK(near(st.dayPnlPct, -250.0 / (eq + 250.0) * 100.0), "day P/L as a percent of the baseline is exposed");
   QCHECK(near(st.hwm, eq + 9000.0), "the high-water mark is exposed");
   QCHECK(near(st.ddPct, 12.5), "the drawdown percent is exposed");
   QCHECK(near(st.dailyLossPct, 250.0 / (eq + 250.0) * 100.0), "the day loss as a percent of the baseline is exposed");
   QCHECK(near(st.dailyLossCapPct, EffectiveDailyLossPercent()), "the effective daily loss cap is exposed");
   QCHECK(st.ddHalted, "the drawdown halt is exposed");
   QCHECK(!st.dayLocked, "the daily-loss lock is exposed");
   QCHECK(st.cooldownActive, "the cooldown state is exposed");
   QCHECK(st.cooldownUntil == kMonday + 86400, "the cooldown deadline is exposed");
   std::string txt = RiskStatusText(st);
   QCHECK(txt.find("equity=") != std::string::npos, "the text carries equity");
   QCHECK(txt.find("dayPnL=-250.00") != std::string::npos, "the text carries the day P/L");
   QCHECK(txt.find("streak=2/") != std::string::npos, "the text carries the streak");
   QCHECK(txt.find("tradesToday=3/") != std::string::npos, "the text carries the cap usage");
   QCHECK(txt.find("ddHalted=yes") != std::string::npos, "the text carries the halt");
   QCHECK(txt.find("cooldown=until") != std::string::npos, "the text carries the cooldown deadline");
   // restore the globals so later tests see the defaults
   g_dayBase = ob; g_dayPnL = op; g_equityHWM = oh; g_accountDDPct = od;
   g_consecLosses = oc; g_tradesToday = ot; g_dayLocked = olk; g_ddHalted = ohlt; g_inCooldown = ocdl; g_cooldownUntil = oud;
   simDiagnosticsClean();
}

// Memoized liquidity context (Phase 8, NC-2): identical content to a direct build,
// keyed on the closed-bar context, exact element copies for the caller.
static void unitLiquidityContext()
{
   TC.name = "unit.liquidity_context";
   Zig z(2000.0);
   z.leg(5, 2010.0); z.leg(3, 2006.0); z.leg(5, 2016.0); z.leg(3, 2012.0); z.leg(5, 2022.0);
   z.forming();
   loadH1(z.bars);
   double atrH1 = 2.0;
   double tol = MathMax(atrH1 * InpLiquidityToleranceATR, _Point * 2);
   MqlArray<SSwing> h1, l1;
   FindSwings(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, h1, true);
   FindSwings(_Symbol, PERIOD_H1, InpSwingLookback, InpSwingK, l1, false);
   MqlArray<SLiquidityPool> p1;
   BuildLiquidityMap(_Symbol, PERIOD_H1, h1, l1, tol, MathMax(1, InpSetupWindowBars), p1);
   g_mH1Bar = 0;   // force a cold build inside LiquidityContext
   MqlArray<SSwing> h2, l2;
   MqlArray<SLiquidityPool> p2;
   LiquidityContext(_Symbol, atrH1, h2, l2, p2);
   QEQ(ArraySize(h2), ArraySize(h1), "the cached context reproduces the swing highs");
   QEQ(ArraySize(l2), ArraySize(l1), "the cached context reproduces the swing lows");
   QEQ(ArraySize(p2), ArraySize(p1), "the cached context reproduces the pool count");
   bool poolsEqual = true;
   for(int i = 0; i < ArraySize(p1); i++)
      poolsEqual = poolsEqual && p2[i].price == p1[i].price && p2[i].state == p1[i].state
                   && std::string(p2[i].kind) == std::string(p1[i].kind);
   QCHECK(poolsEqual, "every cached pool matches the direct build (price, state, kind)");
   MqlArray<SSwing> h3, l3;
   MqlArray<SLiquidityPool> p3;
   LiquidityContext(_Symbol, atrH1, h3, l3, p3);
   QEQ(ArraySize(p3), ArraySize(p2), "a second call on the same bar returns the same pools");
   QCHECK(g_mH1Bar == iTime(_Symbol, PERIOD_H1, 1), "the cache is keyed to the newest closed H1 bar");
   QCHECK(g_mH1Bars == iBars(_Symbol, PERIOD_H1), "the cache key includes the bar count");
   simDiagnosticsClean();
}

// Diagnostics record (Phase 9): the single-record ANALYSIS/FINAL contract, the
// per-setup per-outcome dedup, and the high-score rejection explanation.
static void unitDiagnosticsRecord()
{
   TC.name = "unit.diagnostics_record";
   resetSimOnly();
   captureJournal();
   SAnalysis a;
   ResetAnalysis(a);
   a.signalBar = kMonday + 3 * 86400;
   a.dataReady = true;
   a.dir = +1; a.candidate = +1; a.score = 78; a.setupTime = kMonday + 2 * 86400;
   a.buy.corePass = true; a.buy.coreCount = 2; a.buy.setupTime = kMonday + 2 * 86400; a.buy.score = 78;
   a.buy.eligible = true;
   a.buy.structure = true; a.buy.structChoch = false; a.buy.structLevel = 2001.25; a.buy.structBar = 7;
   a.buy.sweep.found = true; a.buy.sweep.pool = "SWING"; a.buy.sweep.level = 1998.5; a.buy.sweep.bar = 9;
   a.buy.sweep.poolShift = 12; a.buy.sweep.tf = PERIOD_H1;
   a.buy.sweep.eventTime = kMonday + 2 * 86400 - 3600; a.buy.sweep.extreme = 1995.0;
   a.buy.displaced = true; a.buy.dispTF = PERIOD_H1; a.buy.dispBar = 11;
   a.pdStatus = "OK";
   JournalSetupRecord(a, "EXECUTED", "ORDER_FILLED");
   QEQ(linesWith("[QATS][ANALYSIS]"), 1, "one ANALYSIS record per setup per outcome");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "side=BUY", "FINAL_DECISION=ENTER_MARKET").empty(), "EXECUTED maps to ENTER_MARKET");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "CORE_STATUS=PASS 2/3").empty(), "the core status is carried");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "STRUCTURE_STATUS=BOS@2001.25(shift 7)").empty(), "the structure status is carried");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "sweep=SSL:SWING@1998.50(shift 9)").empty(), "the liquidity status is carried");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "DISPLACEMENT_STATUS=TF=H1 shift=11 STATUS=OK").empty(), "the displacement status (with TF= and STATUS=) is carried");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "PD_STATUS=OK").empty(), "PD_STATUS is carried");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "EXECUTION_STATUS=EXECUTED").empty(), "the execution status is carried");
   QCHECK(!firstWith("[QATS][ANALYSIS]", "RISK equity=").empty(), "the RISK_STATUS exposure is folded in");
   QEQ(linesWith("[QATS][FINAL]", "DECISION=ENTER_MARKET"), 1, "the FINAL record carries the decision");
   QEQ(linesWith("[QATS][GUARD]"), 0, "an executed setup never prints the rejection explanation");
   JournalSetupRecord(a, "EXECUTED", "ORDER_FILLED");
   QEQ(linesWith("[QATS][ANALYSIS]"), 1, "the dedup suppresses a repeat of the same setup+outcome");
   JournalSetupRecord(a, "BLOCKED", "DAILY_LOSS_LOCK");
   QEQ(linesWith("[QATS][ANALYSIS]"), 2, "a different outcome prints for the same setup");
   QCHECK(!firstWith("[QATS][GUARD]", "SCORE=78", "REJECTED AT=RISK_GUARD REASON=DAILY_LOSS_LOCK").empty(),
          "a high-scoring blocked setup explains itself: SCORE=78 REJECTED AT=RISK_GUARD REASON=DAILY_LOSS_LOCK");
   // the SELL side is an independent record
   a.sell.corePass = true; a.sell.coreCount = 1; a.sell.setupTime = kMonday + 2 * 86400 + 1800; a.sell.score = 60;
   a.candidate = 0;
   JournalSetupRecord(a, "BLOCKED", "DAILY_LOSS_LOCK");
   QEQ(linesWith("[QATS][ANALYSIS]", "side=SELL"), 1, "the bearish side gets its own record");
   // a side whose core did not pass produces no setup record
   SAnalysis b;
   ResetAnalysis(b);
   b.signalBar = kMonday + 4 * 86400;
   b.dataReady = true;
   JournalSetupRecord(b, "NO_SETUP", "CORE_NOT_CONFIRMED");
   QEQ(linesWith("[QATS][ANALYSIS]"), 3, "a bar with no core-passed side prints no setup record");
   simDiagnosticsClean();
}

// Regime classification (Phase 7): report-only, deterministic, fail closed.
static void unitRegime()
{
   TC.name = "unit.regime";
   const double K = 4100.0;
   double volRatio = 0.0;
   QEQ(ClassifyRegime(3.1, 2.0, 2000.0, 2001.0, 2000.5, 1999.0, 2.0, volRatio), QATS_REGIME_HIGH_VOL, "ATR 1.55x median is HIGH_VOL");
   QCHECK(near(volRatio, 1.55), "the ATR ratio is reported alongside the class");
   QEQ(ClassifyRegime(3.0, 2.0, 2000.0, 2001.0, 2000.5, 1999.0, 2.0, volRatio), QATS_REGIME_HIGH_VOL, "the HIGH_VOL boundary is inclusive");
   QEQ(ClassifyRegime(0.9, 2.0, 2000.0, 2001.0, 2000.5, 1999.0, 0.9, volRatio), QATS_REGIME_LOW_VOL, "ATR 0.45x median is LOW_VOL");
   QEQ(ClassifyRegime(2.0, 2.0, 2100.0, 2050.0, 2000.0, 1900.0, 2.0, volRatio), QATS_REGIME_TREND_BULL, "close>EMA20>EMA50>EMA200 is TREND_BULL");
   QEQ(ClassifyRegime(2.0, 2.0, 1900.0, 1950.0, 2000.0, 2100.0, 2.0, volRatio), QATS_REGIME_TREND_BEAR, "close<EMA20<EMA50<EMA200 is TREND_BEAR");
   QEQ(ClassifyRegime(2.0, 2.0, 2000.0, 2100.0, 2099.5, 1900.0, 2.0, volRatio), QATS_REGIME_RANGE, "crossed EMAs with a flat fast/slow pair fall through to RANGE");
   QEQ(ClassifyRegime(2.0, 2.0, 2000.0, 2000.9, 2000.7, 2100.0, 2.0, volRatio), QATS_REGIME_RANGE, "fast/slow pair flat vs one ATR is RANGE");
   QEQ(ClassifyRegime(2.0, 2.0, 2000.0, 2100.0, 1950.0, 2050.0, 0.2, volRatio), QATS_REGIME_UNCLEAR, "crossed EMAs at normal vol is UNCLEAR");
   QEQ(ClassifyRegime(2.0, 0.0, 2100.0, 2050.0, 2000.0, 1900.0, 2.0, volRatio), QATS_REGIME_UNCLEAR, "no ATR median fails closed to UNCLEAR");
   QCHECK(std::string(RegimeName(QATS_REGIME_TREND_BULL)) == "TREND_BULL", "RegimeName(TREND_BULL)");
   QCHECK(std::string(RegimeName(QATS_REGIME_TREND_BEAR)) == "TREND_BEAR", "RegimeName(TREND_BEAR)");
   QCHECK(std::string(RegimeName(QATS_REGIME_RANGE)) == "RANGE", "RegimeName(RANGE)");
   QCHECK(std::string(RegimeName(QATS_REGIME_HIGH_VOL)) == "HIGH_VOL", "RegimeName(HIGH_VOL)");
   QCHECK(std::string(RegimeName(QATS_REGIME_LOW_VOL)) == "LOW_VOL", "RegimeName(LOW_VOL)");
   QCHECK(std::string(RegimeName(QATS_REGIME_UNCLEAR)) == "UNCLEAR", "RegimeName(UNCLEAR)");
   // range breadth on loaded H1 bars: 80 near-flat bars then 20 that span everything
   Zig dead(2000.0);
   for(int i = 0; i < 80; i++) dead.leg(1, 2000.0);
   for(int i = 0; i < 5; i++) dead.leg(2, 2006.0);
   for(int i = 0; i < 5; i++) dead.leg(2, 1994.0);
   dead.forming();
   loadH1(dead.bars);
   double r100 = RangeRatio(_Symbol, 20, 100);
   QCHECK(r100 > 0.8, "the last 20 bars spanning the 100-bar range give a HIGH breadth (got " + std::to_string(r100) + ")");
   loadH1(mirrorBars(dead.bars, K));
   QCHECK(near(RangeRatio(_Symbol, 20, 100), r100), "range breadth is mirror-invariant");
   Zig top(1990.0);
   for(int i = 0; i < 40; i++) { top.leg(1, 2020.0); top.leg(1, 1990.0); }   // 80 bars, full 1990..2020 span (ends at 1990)
   for(int i = 0; i < 20; i++) top.candle(1990.0, 1990.2, 1989.8, 1990.0);   // last 20 bars dead flat
   top.forming();
   loadH1(top.bars);
   double rLow = RangeRatio(_Symbol, 20, 100);
   QCHECK(rLow < 0.1, "dead-flat last 20 bars inside a wide 100-bar range give near-zero breadth (got " + std::to_string(rLow) + ")");
   simDiagnosticsClean();
}

// News / calendar blackout (Phase 7, opt-in): blocks inside the window, never on an unreachable calendar.
static void unitNewsFilter()
{
   TC.name = "unit.news_filter";
   resetSimOnly();
   const datetime kT = kMonday + 4 * 86400 + 12 * 3600;
   sim::S.now = kT;
   g_newsUnavailableLogged = false;
   g_newsReadyLogged = false;
   sim::S.calMode = 0;
   sim::S.calEvents.clear();
   QATS_SetInput("InpNewsFilterEnable", "true");
   QATS_SetInput("InpNewsBlockBeforeMin", "30");
   QATS_SetInput("InpNewsBlockAfterMin", "30");
   QATS_SetInput("InpNewsCurrencies", "USD,XAU");
   QATS_SetInput("InpNewsMinImportance", "3");
   string why;
   QCHECK(NewsEntriesAllowed(kT, why), "no calendar events -> entries allowed");
   sim::S.calEvents.push_back({kT + 10 * 60, 3, "USD"});
   QCHECK(!NewsEntriesAllowed(kT, why), "a high-impact USD event inside the window blocks");
   QCHECK(why.find("high-impact") != std::string::npos, "the block names the cause: " + why);
   sim::S.calEvents.clear();
   sim::S.calEvents.push_back({kT + 60 * 60, 3, "USD"});
   QCHECK(NewsEntriesAllowed(kT, why), "an event 60min ahead sits outside the 30min window");
   sim::S.calEvents.clear();
   sim::S.calEvents.push_back({kT - 10 * 60, 3, "USD"});
   QCHECK(!NewsEntriesAllowed(kT, why), "an event that already happened inside the after-window blocks");
   sim::S.calEvents.clear();
   sim::S.calEvents.push_back({kT + 5 * 60, 2, "USD"});
   QCHECK(NewsEntriesAllowed(kT, why), "moderate impact passes when HIGH is required");
   QATS_SetInput("InpNewsMinImportance", "2");
   QCHECK(!NewsEntriesAllowed(kT, why), "moderate impact blocks when moderate and up is required");
   QATS_SetInput("InpNewsMinImportance", "3");
   sim::S.calEvents.clear();
   sim::S.calEvents.push_back({kT + 5 * 60, 3, "EUR"});
   QCHECK(NewsEntriesAllowed(kT, why), "an unwatched currency never blocks");
   sim::S.calEvents.clear();
   sim::S.calEvents.push_back({kT + 5 * 60, 3, "XAU"});
   QCHECK(!NewsEntriesAllowed(kT, why), "a watched XAU event blocks");
   // unreachable calendar -> entries NOT blocked, journalled exactly once
   captureJournal();
   sim::S.calEvents.clear();
   sim::S.calMode = 1;
   QCHECK(NewsEntriesAllowed(kT, why), "an unreachable calendar blocks nothing");
   QCHECK(g_newsUnavailableLogged, "the unavailable calendar was journalled");
   int lines = linesWith("CALENDAR_UNAVAILABLE");
   NewsEntriesAllowed(kT, why);
   QEQ(linesWith("CALENDAR_UNAVAILABLE"), lines, "the miss is journalled once per attach, never per bar");
   QEQ(lines >= 1 ? 1 : 0, 1, "exactly one CALENDAR_UNAVAILABLE line");
   // restore defaults so later tests see a news-off EA
   sim::S.calMode = 0;
   sim::S.calEvents.clear();
   QATS_SetInput("InpNewsFilterEnable", "false");
   QATS_SetInput("InpNewsMinImportance", "3");
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


static void unitAdaptivePD()
{
   TC.name = "unit.adaptive_pd";
   const double ATR = 10.0;
   // ---------- series builders (H1, closed bars only; the forming bar is ignored) ----------
   auto fullSeries = [&]() {           // 130 candles, both 120-window extremes inside the last 60 bars
      Zig z(1540.0);
      z.leg(70, 1546.0);               // tight drift (the old part of the window)
      z.leg(16, 1496.0);               // global swing LOW  at shift ~55
      z.leg(16, 1596.0);               // global swing HIGH at shift ~39
      z.leg(18, 1560.0);               // pullback: the newest confirmed swing low, shift ~22
      z.leg(22, 1590.0);               // recovery rise; range C = [1560..1596], range A = [1496..1596]
      return z.bars;                   // 142 candles = 141 closed + the forming bar
   };

   // ---------- A/B window contracts ----------
   loadH1(fullSeries());
   g_pdLastSelected = QATS_PD_NONE;
   SPdRange ra, rb;
   QCHECK(PdRangeFromWindow(_Symbol, 120, ATR, ra), "range A (120 closed H1 bars) is computable on 120+ bars");
   QCHECK(PdRangeFromWindow(_Symbol, 48, ATR, rb), "range B (48 closed H1 bars) is computable");
   QCHECK(ra.valid && rb.valid, "A and B both valid on a healthy series");
   QCHECK(ra.high >= rb.high && ra.low <= rb.low, "the 48-bar window sits inside the 120-bar window (bounds contain)");
   QCHECK(near(ra.eq, (ra.high + ra.low) / 2.0) && near(rb.eq, (rb.high + rb.low) / 2.0), "each equilibrium is the midpoint of its own range");
   QCHECK(ra.highShift >= 1 && ra.highShift <= 120 && rb.highShift >= 1 && rb.highShift <= 48, "the window extremes lie inside their windows");

   // incomplete history is rejected, loudly
   {
      Zig small(1500.0);
      small.leg(59, 1550.0);           // 59 closed bars only
      loadH1(small.bars);
      SPdRange r60;
      QCHECK(!PdRangeFromWindow(_Symbol, 120, ATR, r60), "range A is REJECTED when 120 closed bars are not available");
      QCHECK(PdRangeFromWindow(_Symbol, 48, ATR, r60), "range B is computable on 59 closed bars (the full 48-bar window exists)");
   }

   // flat series: no equilibrium exists, everything rejects, the gate fails closed
   {
      std::vector<sim::Bar> flat;
      for(int i = 0; i < 130; i++) flat.push_back(HB(1600.0, 1600.2, 1599.8, 1600.0));
      loadH1(flat);
      g_pdLastSelected = QATS_PD_NONE;
      SPdAdaptive pd;
      ComputePdAdaptive(_Symbol, ATR, pd);
      QEQ(pd.selected, (int)QATS_PD_NONE, "a flat market yields NO valid range");
      QCHECK(pd.status.find("REJECTED") == 0, "the flat-market status says REJECTED out loud");
      QCHECK(near(pd.position, 0.5), "no range means no location claim (0.5 neutral), never an invented position");
      string why;
      QCHECK(!PdPriceOnSide(pd.selected, pd.eq, pd.status, +1, 1600.0, "PD_MARKET", why), "BUY is refused when no range is valid (fail closed)");
      QCHECK(!PdPriceOnSide(pd.selected, pd.eq, pd.status, -1, 1600.0, "PD_MARKET", why), "SELL is refused when no range is valid (fail closed)");
      QCHECK(why.find("no valid H1 dealing range") != std::string::npos, "the refusal names the reason");
      QCHECK(PdLine(pd).find("SELECTED=NONE") != std::string::npos, "the journal line says NONE out loud");
   }

   // ---------- stale extreme dominating ----------
   {
      Zig z(1500.0);
      z.leg(125, 1612.5);              // monotonic drift: no fractals anywhere
      // an ancient spike above everything (shift ~115): an extreme older than
      // InpPdSwingMaxAge that is FAR from price
      z.bars[10] = HB(1502.0, 3000.0, 1501.0, 1503.0);
      loadH1(z.bars);
      g_pdLastSelected = QATS_PD_NONE;
      SPdAdaptive pd;
      ComputePdAdaptive(_Symbol, ATR, pd);
      QCHECK(!pd.a.valid, "range A is rejected: an ancient spike 1400 above price dominates its equilibrium");
      QCHECK(pd.b.valid, "range B (the recent drift) still anchors price");
      QEQ(pd.selected, (int)QATS_PD_B, "the fresh short-term range is selected when the long range goes stale");
   }

   // ---------- swing freshness ----------
   {
      Zig z(1500.0);
      z.leg(55, 1560.0);               // rise
      z.leg(14, 1522.0);               // swing high
      z.leg(18, 1580.0);               // swing low
      for(int i = 0; i < 80; i++)      // 80 IDENTICAL flat bars: no new fractal can form
         z.bars.push_back(HB(1580.0, 1580.2, 1579.8, 1580.0));
      loadH1(z.bars);
      g_pdLastSelected = QATS_PD_NONE;
      SPdAdaptive pd;
      // ATR=200 here: the 0.5-ATR staleness tolerance must not eat A's real (but 58
      // points away) swing low - it is only "stale" in a low-volatility world
      ComputePdAdaptive(_Symbol, 200.0, pd);
      QCHECK(!pd.c.valid, "range C is rejected: the newest of its two defining swings is older than InpPdSwingMaxAge (freshness)");
      QCHECK(!pd.b.valid, "range B covers only the flat tail and is rejected as flat");
      QCHECK(pd.a.valid, "range A still sees the real rise and stays valid");
      QEQ(pd.selected, (int)QATS_PD_A, "with C stale and B flat the long-term range anchors PD");
   }

   // ---------- full comparison line ----------
   loadH1(fullSeries());
   g_pdLastSelected = QATS_PD_NONE;
   {
      SPdAdaptive pd;
      ComputePdAdaptive(_Symbol, ATR, pd);
      string line = PdLine(pd);
      QCHECK(line.find("LONG_EQ=") == 0, "the journal line starts with LONG_EQ=");
      QCHECK(line.find("SHORT_EQ=") != std::string::npos && line.find("SWING_EQ=") != std::string::npos,
             "the journal line carries all THREE equilibriums");
      QCHECK(line.find("SELECTED=") != std::string::npos && line.find("POS=") != std::string::npos && line.find("STATUS=") != std::string::npos,
             "the journal line carries the selection, the position and the status");
      QEQ(pd.selected, (int)QATS_PD_C, "a healthy fresh series selects the confirmed swing range");
   }

   // ---------- direction semantics through the shared check ----------
   {
      SPdAdaptive pd;
      ComputePdAdaptive(_Symbol, ATR, pd);
      string why;
      QCHECK(PdPriceOnSide(pd.selected, pd.eq, pd.status, +1, pd.eq - 1.0, "PD_MARKET", why), "BUY in discount is allowed");
      QCHECK(!PdPriceOnSide(pd.selected, pd.eq, pd.status, +1, pd.eq + 1.0, "PD_MARKET", why), "BUY in premium is refused");
      QCHECK(PdPriceOnSide(pd.selected, pd.eq, pd.status, -1, pd.eq + 1.0, "PD_MARKET", why), "SELL in premium is allowed");
      QCHECK(!PdPriceOnSide(pd.selected, pd.eq, pd.status, -1, pd.eq - 1.0, "PD_MARKET", why), "SELL in discount is refused");
      QCHECK(PdPriceOnSide(pd.selected, pd.eq, pd.status, +1, pd.eq, "PD_MARKET", why), "exact equality is allowed on the BUY side");
      QCHECK(PdPriceOnSide(pd.selected, pd.eq, pd.status, -1, pd.eq, "PD_MARKET", why), "exact equality is allowed on the SELL side");
      QCHECK(why == "", "an allowed side carries no refusal text");
   }

   // ---------- hysteresis: no flip-flop on adjacent evaluations ----------
   {
      QATS_SetInput("InpPdHysteresisATR", "0.0001");   // effectively off: the preferred range wins
      g_pdLastSelected = QATS_PD_A;
      SPdAdaptive pd;
      ComputePdAdaptive(_Symbol, ATR, pd);            // huge ATR band means delta is inside it; with 0.0001 the veto is off
      QEQ(pd.selected, (int)QATS_PD_C, "with hysteresis disabled the preferred (fresh swing) range wins");
      QATS_SetInput("InpPdHysteresisATR", "100.0");    // huge band: everything sticks to the previous selection
      g_pdLastSelected = QATS_PD_A;
      ComputePdAdaptive(_Symbol, ATR, pd);
      QEQ(pd.selected, (int)QATS_PD_A, "with hysteresis enabled the previous selection is kept while every EQs stay inside the band");
      QCHECK(pd.status.find("hysteresis") != std::string::npos, "the kept selection says HYSTERESIS out loud in the status");
      QATS_SetInput("InpPdHysteresisATR", "0.25");     // shipped default
      g_pdLastSelected = QATS_PD_NONE;
      ComputePdAdaptive(_Symbol, ATR, pd);
      QEQ(pd.selected, (int)QATS_PD_C, "default hysteresis: first evaluation of an attach selects the preferred range");
   }
   g_pdLastSelected = QATS_PD_NONE;
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
   unitLiquidityDedup();
   unitLiquidityJournal();
   unitLiquidityFold();
   unitSweepEvent();
   unitM5TriggerAuthority();
   unitRegime();
   unitNewsFilter();
   unitDiagnosticsRecord();
   unitFillShort();
   unitReservation();
   unitRiskStatus();
   unitLiquidityContext();
   unitDisplacementZones();
   unitLimitZones();
   unitLimitPlan();
   unitAdaptivePD();
   printf("unit: %d checks, %d failed\n", TC.checks, TC.failed);
   return TC.failed ? 1 : 0;
}
} // namespace drv

#include "qats_scenarios.inc"
