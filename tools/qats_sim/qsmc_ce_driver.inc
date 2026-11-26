// qsmc_ce_driver.inc - native unit/replay driver for QSMC_ConfirmationEngine.mq5.
// Included after qsmc_ce_shim.h and the transpiled EA. Everything here is test
// harness: it never places an order by default and never changes the EA source.
#pragma GCC system_header

#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <iomanip>
#include <cmath>

namespace ce_drv
{
int checks = 0;
int failures = 0;
std::vector<std::string> captured_logs;

#define CE_CHECK(cond) do { ++ce_drv::checks; if(!(cond)) { ++ce_drv::failures; \
   std::cerr << "FAIL line " << __LINE__ << ": " << #cond << "\n"; } } while(false)
#define CE_CHECK_STR(a,b) do { ++ce_drv::checks; if(std::string(a)!=std::string(b)) { ++ce_drv::failures; \
   std::cerr << "FAIL line " << __LINE__ << ": " << #a << "='" << (a) << "' != " << #b << "='" << (b) << "'\n"; } } while(false)
#define CE_CHECK_NEAR(a,b,eps) do { ++ce_drv::checks; if(std::fabs((double)(a)-(double)(b))>(double)(eps)) { ++ce_drv::failures; \
   std::cerr << "FAIL line " << __LINE__ << ": " << #a << "='" << (a) << "' not near " << #b << "='" << (b) << "'\n"; } } while(false)
#define CE_CHECK_HAS(s,needle) do { ++ce_drv::checks; if(std::string(s).find(std::string(needle))==std::string::npos) { ++ce_drv::failures; \
   std::cerr << "FAIL line " << __LINE__ << ": '" << (s) << "' lacks '" << (needle) << "'\n"; } } while(false)

static int countChar(const std::string &s, char c)
{
   int n = 0;
   for(size_t i = 0; i < s.size(); i++)
   {
      if(s[i] == c)
      {
         n++;
      }
   }
   return n;
}

static datetime utcOf(const int y, const int m, const int d, const int hh, const int mm)
{
   return (datetime)(CE_DaysFromCivil(y, m, d) * 86400 + (long)hh * 3600 + (long)mm * 60);
}

static int minutesOfTf(const ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_M1)  { return 1; }
   if(tf == PERIOD_M5)  { return 5; }
   if(tf == PERIOD_M15) { return 15; }
   if(tf == PERIOD_H1)  { return 60; }
   if(tf == PERIOD_H4)  { return 240; }
   return 1;
}

static void seedSeries(const ENUM_TIMEFRAMES tf, const datetime server, const int count)
{
   sim::Series &ser = sim::S.series[sim::tfIndex(tf)];
   ser.tf = tf;
   ser.bars.clear();
   int mins = minutesOfTf(tf);
   datetime start = server - (long)(count - 1) * (long)mins * 60;
   for(int i = 0; i < count; i++)
   {
      double mid = 3550.0 + 0.10 * (double)((i % 11) - 5);
      sim::Bar b{};
      b.time = start + (long)i * (long)mins * 60;
      b.open = mid - 0.25;
      b.high = mid + 1.20;
      b.low = mid - 1.20;
      b.close = mid + 0.25;
      b.volume = 1000 + (long)i;
      ser.bars.push_back(b);
   }
}

static void setupMarket(const datetime server)
{
   sim::reset();
   qsmc_ce::reset_files();
   chartsim::resetAll();
   sim::S.now = server;
   sim::S.lastTickTime = server;
   sim::S.bid = 3550.00;
   sim::S.ask = 3550.20;
   sim::S.haveQuote = true;
   sim::S.marketOpen = true;
   sim::S.terminalTradeAllowed = true;
   sim::S.mqlTradeAllowed = true;
   sim::S.acc.tradeAllowed = true;
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_DEMO;
   sim::S.acc.balance = 10000.0;
   sim::S.sym.name = "XAUUSD";
   sim::S.sym.digits = 2;
   sim::S.sym.point = 0.01;
   sim::S.sym.tickSize = 0.01;
   sim::S.sym.tickValue = 1.0;
   sim::S.sym.contractSize = 100.0;
   sim::S.sym.volMin = 0.01;
   sim::S.sym.volMax = 100.0;
   sim::S.sym.volStep = 0.01;
   sim::S.sym.stopsLevel = 0;
   sim::S.sym.freezeLevel = 0;
   sim::S.sym.tradeMode = 4;
   sim::S.sym.fillingMode = 2;
   sim::S.sym.execMode = 2;
   seedSeries(PERIOD_M1, server, 130);
   seedSeries(PERIOD_M5, server, 130);
   seedSeries(PERIOD_M15, server, 130);
   seedSeries(PERIOD_H1, server, 130);
   seedSeries(PERIOD_H4, server, 130);
   CE_CHECK(OnInit() == INIT_SUCCEEDED);
}

static string zoneId(const int dir, const datetime epoch)
{
   return "Z|" + CE_DirectionText(dir) + "|" + IntegerToString((long)epoch);
}

static string aiJson(const int dir, const double conf, const datetime as_of)
{
   std::ostringstream os;
   os << "{\"direction\":" << dir << ",\"confidence\":" << conf
      << ",\"reasons\":\"sweep; choch; h4 aligned\",\"invalidation\":\"close above 3570\",\"as_of\":"
      << (long)as_of << "}";
   return os.str();
}

static void makeGoodFacts(SZoneFacts &f, const datetime utc)
{
   CE_InitFacts(f);
   f.direction = 1;
   f.kind = CE_KIND_OB_FVG;
   f.state = CE_STATE_TESTED_MITIGATED;
   f.lo = 3547.0;
   f.hi = 3569.0;
   f.born_utc = utc - 3600;
   f.now_utc = utc;
   f.age_hours = 1.0;
   f.touches = 0;
   f.zone_atr_ratio = 1.0;
   f.atr_m1 = 2.0;
   f.atr_percentile = 50.0;
   f.spread_points = 20.0;
   f.spread_price = 0.20;
   f.spread_atr_pct = 10.0;
   f.room_to_liquidity = 60.0;
   f.rr_at_fill = 2.0;
   f.nearest_liquidity = 3600.0;
   f.invalidation = 3545.0;
   f.bid = 3550.00;
   f.ask = 3550.20;
   f.current_price = 3550.20;
   f.point = 0.01;
   f.tick_value = 1.0;
   f.equity = 10000.0;
   f.stops_level = 0;
   f.freeze_level = 0;
   f.min_stop_points = 20;
   f.session = CE_SESSION_LONDON;
   f.session_entry_allowed = true;
   f.h1_bias = 1;
   f.h4_bias = 1;
   f.htf_alignment = 1.0;
   f.asia_sweep = true;
   f.london_sweep = true;
   f.bsl_ssl = true;
   f.eqh_eql = true;
   f.sweep_before_reaction = true;
   f.m1_choch = true;
   f.m5_bos = true;
   f.confirmation_close = true;
   f.second_reaction = true;
   f.sweep = true;
   f.closed_beyond_zone = true;
   f.micro_bos = true;
   f.first_pullback = true;
   f.poc_reaction = true;
   f.vah_val_reaction = true;
   f.volume_expansion = true;
   f.mode = CE_MODE_RETEST;
   f.retest_percent = 0.5;
   f.max_chase_atr = 1.5;
   f.momentum_close = 3570.0;
   f.pullback_price = 3560.0;
   f.second_reaction_price = 3555.0;
   f.chase_distance = 1.0;
   f.ai_used = false;
   f.ai_direction = 0;
   f.ai_confidence = 0.0;
   f.ai_why = "AI_DISABLED";
}

static void makeGoodAccount(SAccountState &a, const datetime utc)
{
   CE_InitAccount(a);
   a.master_enable = true;
   a.dry_run = true;
   a.allow_live = false;
   a.allow_real = false;
   a.kill_switch = false;
   a.daily_lock = false;
   a.real_account = false;
   a.positions = 0;
   a.trades_today = 0;
   a.max_concurrent = 1;
   a.max_trades = 3;
   a.equity = 10000.0;
   a.day_start_equity = 10000.0;
   a.max_daily_loss_pct = 0.50;
   a.now_utc = utc;
   a.last_entry_utc = 0;
   a.cooldown_minutes = 60;
}

static void testDefaultContract()
{
   CE_CHECK(InpMasterEnable == true);
   CE_CHECK(InpDryRun == true);
   CE_CHECK(InpAllowLiveOrders == false);
   CE_CHECK(InpAllowRealTrading == false);
   CE_CHECK(InpKillSwitch == false);
   CE_CHECK(InpUseAIAgent == false);
   CE_CHECK(InpRequireSessionPermission == true);
   CE_CHECK(InpAllowAsiaEntries == false);
   CE_CHECK(InpAllowOffPeakEntries == false);
   CE_CHECK(InpTierA == 75);
   CE_CHECK(InpTierB == 55);
   CE_CHECK(InpMinHtfPoints == 3);
   CE_CHECK(InpMaxSpreadPoints > 0.0);
   CE_CHECK(InpMinRRAtFill > 0.0);
   CE_CHECK(InpMaxDailyLossPercent <= 2.00);
}

static void testSmallHelpers()
{
   CE_CHECK_STR(CE_BoolText(true), "true");
   CE_CHECK_STR(CE_BoolText(false), "false");
   CE_CHECK_STR(CE_StateText(CE_STATE_TESTED_MITIGATED), "TESTED_MITIGATED");
   CE_CHECK_STR(CE_KindText(CE_KIND_OB_FVG), "OB+FVG");
   CE_CHECK_STR(CE_DirectionText(-1), "SELL");
   CE_CHECK_STR(CE_TierText(2), "A");
   CE_CHECK_STR(CE_SessionName(CE_SESSION_NEWYORK), "NEWYORK");
   CE_CHECK_STR(CE_EntryModeName(CE_MODE_REVERSAL), "REVERSAL_AFTER_MITIGATION");
   CE_CHECK(CE_HashId("Z|BUY|1") == CE_HashId("Z|BUY|1"));
   CE_CHECK(CE_HashId("Z|BUY|1") != CE_HashId("Z|SELL|1"));
   CE_CHECK_STR(CE_LogToken("a|b,c\td\ne\rf"), "a;b;c;d;e;f");
   CE_CHECK_STR(CE_CsvToken("a,b\tc\nd\re"), "a;b;c;d;e");
   CE_CHECK_STR(CE_TrimJson("  \" abc \" \t"), " abc ");
   CE_CHECK_STR(CE_TrimJson("  123 "), "123");
   CE_CHECK_STR(CE_LogToken("none"), "none");
}

static void testCivilAndDst(const datetime utc)
{
   int y = 0;
   int m = 0;
   int d = 0;
   CE_CivilFromDays(CE_DaysFromCivil(2026, 11, 25), y, m, d);
   CE_CHECK(y == 2026);
   CE_CHECK(m == 11);
   CE_CHECK(d == 25);
   CE_CivilFromDays(CE_LastSundayOfMonthDays(2026, 3), y, m, d);
   CE_CHECK(y == 2026 && m == 3 && d == 29);
   CE_CivilFromDays(CE_LastSundayOfMonthDays(2026, 10), y, m, d);
   CE_CHECK(y == 2026 && m == 10 && d == 25);
   CE_CivilFromDays(CE_NthSundayOfMonthDays(2026, 3, 2), y, m, d);
   CE_CHECK(y == 2026 && m == 3 && d == 8);
   CE_CivilFromDays(CE_FirstSundayOfMonthDays(2026, 11), y, m, d);
   CE_CHECK(y == 2026 && m == 11 && d == 1);

   datetime eu_start = utcOf(2026, 3, 29, 0, 59);
   CE_CHECK(CE_IsEuDst(eu_start) == false);
   CE_CHECK(CE_IsEuDst(eu_start + 60) == true);
   datetime eu_end = utcOf(2026, 10, 25, 0, 59);
   CE_CHECK(CE_IsEuDst(eu_end) == true);
   CE_CHECK(CE_IsEuDst(eu_end + 60) == false);

   datetime us_start = utcOf(2026, 3, 8, 6, 59);
   CE_CHECK(CE_IsUsDst(us_start) == false);
   CE_CHECK(CE_IsUsDst(us_start + 60) == true);
   datetime us_end = utcOf(2026, 11, 1, 5, 59);
   CE_CHECK(CE_IsUsDst(us_end) == true);
   CE_CHECK(CE_IsUsDst(us_end + 60) == false);

   CE_CHECK(CE_BrokerOffsetMinutes(utcOf(2026, 1, 15, 8, 0), 120, 180, true) == 120);
   CE_CHECK(CE_BrokerOffsetMinutes(utcOf(2026, 7, 15, 8, 0), 120, 180, true) == 180);
   CE_CHECK(CE_ServerToUtc(utcOf(2026, 1, 15, 10, 0), 120, 180, true) == utcOf(2026, 1, 15, 8, 0));
   CE_CHECK(CE_ServerToUtc(utcOf(2026, 7, 15, 11, 0), 120, 180, true) == utcOf(2026, 7, 15, 8, 0));
   CE_CHECK(CE_ServerToUtc(utcOf(2026, 3, 29, 3, 30), 120, 180, true) == utcOf(2026, 3, 29, 0, 30));
   CE_CHECK(CE_ServerToUtc(utcOf(2026, 10, 25, 3, 30), 120, 180, true) == utcOf(2026, 10, 25, 1, 30));
   CE_CHECK(CE_UtcToBrokerServer(utcOf(2026, 7, 15, 8, 0), 120, 180, true) == utcOf(2026, 7, 15, 11, 0));
   CE_CHECK(CE_ServerToUtc(utc, 120, 180, false) == utc - 7200);

   CE_CHECK(CE_UtcToAlgeriaHour(utcOf(2026, 11, 25, 8, 0)) == 9);
   CE_CHECK(CE_UtcToAlgeriaHour(utcOf(2026, 11, 25, 23, 0)) == 0);
   CE_CHECK(CE_SessionOfUtc(utcOf(2026, 11, 25, 8, 0)) == CE_SESSION_LONDON);
   CE_CHECK(CE_SessionOfUtc(utcOf(2026, 11, 25, 14, 30)) == CE_SESSION_NEWYORK);
   CE_CHECK(CE_SessionOfUtc(utcOf(2026, 11, 25, 23, 0)) == CE_SESSION_ASIA);
   CE_CHECK(CE_SessionOfUtc(utcOf(2026, 11, 25, 12, 0)) == CE_SESSION_OFFPEAK);
   CE_CHECK(CE_SessionScore(CE_SESSION_LONDON) == 10.0);
   CE_CHECK(CE_SessionScore(CE_SESSION_NEWYORK) == 8.0);
   CE_CHECK(CE_SessionScore(CE_SESSION_ASIA) == 2.0);
   CE_CHECK(CE_SessionEntryAllowed(CE_SESSION_LONDON, false, false) == true);
   CE_CHECK(CE_SessionEntryAllowed(CE_SESSION_ASIA, false, false) == false);
   CE_CHECK(CE_SessionEntryAllowed(CE_SESSION_ASIA, true, false) == true);
}

static void testParser()
{
   datetime epoch = utcOf(2026, 11, 25, 8, 0);
   string sell_id = zoneId(-1, epoch);
   string tip = "Bearish OB+FVG 3547.00–3569.00 MITIGATED | " + sell_id;
   SZoneRecord z;
   CE_InitZone(z);
   CE_CHECK(CE_ParseZoneObject("QSVP_ZN_S0", tip, 3569.0, 3547.0, epoch, z) == true);
   CE_CHECK_STR(z.id, sell_id);
   CE_CHECK(z.direction == -1);
   CE_CHECK(z.kind == CE_KIND_OB_FVG);
   CE_CHECK(z.state == CE_STATE_TESTED_MITIGATED);
   CE_CHECK_NEAR(z.lo, 3547.0, 0.001);
   CE_CHECK_NEAR(z.hi, 3569.0, 0.001);

   SZoneRecord legacy;
   CE_InitZone(legacy);
   CE_CHECK(CE_ParseId(zoneId(1, epoch + 60), legacy) == true);
   CE_CHECK(legacy.direction == 1);
   CE_CHECK(legacy.born_utc == epoch + 60);

   int dir = 0;
   int idx = -1;
   CE_CHECK(CE_ExtractObjectDirection("QSVP_ZN_B7", dir, idx) == true);
   CE_CHECK(dir == 1);
   CE_CHECK(idx == 7);

   SZoneRecord fallback;
   CE_InitZone(fallback);
   CE_CHECK(CE_ParseZoneObject("QSVP_ZN_B1", "Bullish OB 3500.00-3510.00 VALIDATED",
                               3500.0, 3510.0, epoch + 120, fallback) == true);
   CE_CHECK_STR(fallback.id, zoneId(1, epoch + 120));
   CE_CHECK(fallback.state == CE_STATE_VALIDATED);
   CE_CHECK(fallback.kind == CE_KIND_OB);

   SZoneRecord legacy_name;
   CE_InitZone(legacy_name);
   string legacy_id = zoneId(1, epoch + 180);
   CE_CHECK(CE_ParseZoneObject(legacy_id, "Bullish FVG 3500.00-3510.00 DETECTED",
                               3500.0, 3510.0, epoch + 180, legacy_name) == true);
   CE_CHECK_STR(legacy_name.id, legacy_id);
   CE_CHECK(legacy_name.kind == CE_KIND_FVG);
   CE_CHECK(legacy_name.state == CE_STATE_DETECTED);

   double lo = 0.0;
   double hi = 0.0;
   CE_CHECK(CE_ExtractTwoPrices("3547.00 - 3569.00", lo, hi) == true);
   CE_CHECK_NEAR(lo, 3547.0, 0.001);
   CE_CHECK_NEAR(hi, 3569.0, 0.001);
   double number = 0.0;
   int end = 0;
   CE_CHECK(CE_ReadNumberAt("-12.5x", 0, number, end) == true);
   CE_CHECK_NEAR(number, -12.5, 0.001);
   CE_CHECK(end == 5);

   string json = aiJson(-1, 0.72, epoch);
   string field = "";
   CE_CHECK(CE_JsonField(json, "direction", field) == true);
   CE_CHECK_STR(field, "-1");
   CE_CHECK(CE_JsonField(json, "confidence", field) == true);
   CE_CHECK_STR(field, "0.72");
   CE_CHECK(CE_JsonField(json, "reasons", field) == true);
   CE_CHECK_HAS(field, "choch");
   CE_CHECK(CE_JsonField(json, "as_of", field) == true);
   CE_CHECK_STR(field, IntegerToString((long)epoch));
}

static void testRegistryAndTransitions(const datetime utc)
{
   CE_CHECK(CE_CanTransition(CE_STATE_DETECTED, CE_STATE_VALIDATED) == true);
   CE_CHECK(CE_CanTransition(CE_STATE_DETECTED, CE_STATE_TESTED_MITIGATED) == true);
   CE_CHECK(CE_CanTransition(CE_STATE_DETECTED, CE_STATE_TRIGGERED) == true);
   CE_CHECK(CE_CanTransition(CE_STATE_VALIDATED, CE_STATE_TESTED_MITIGATED) == true);
   CE_CHECK(CE_CanTransition(CE_STATE_TESTED_MITIGATED, CE_STATE_TRIGGERED) == true);
   CE_CHECK(CE_CanTransition(CE_STATE_TRIGGERED, CE_STATE_EXPIRED) == true);
   CE_CHECK(CE_CanTransition(CE_STATE_EXPIRED, CE_STATE_VALIDATED) == false);
   CE_CHECK(CE_CanTransition(CE_STATE_INVALIDATED, CE_STATE_TRIGGERED) == false);

   CZoneRegistry reg;
   reg.ZR_Init();
   SZoneRecord a;
   CE_InitZone(a);
   a.id = zoneId(1, utc);
   a.direction = 1;
   a.kind = CE_KIND_OB_FVG;
   a.lo = 3547.0;
   a.hi = 3569.0;
   a.born_utc = utc;
   a.last_score = 88.0;
   a.last_tier = 2;
   a.last_decision = "ENTER_DRY_RUN";
   a.last_reject = "NONE";
   CE_CHECK(reg.ZR_Upsert(a) == true);
   CE_CHECK(reg.ZR_Upsert(a) == true);
   CE_CHECK(reg.ZR_Count() == 1);
   CE_CHECK(reg.ZR_Find(a.id) >= 0);
   CE_CHECK(reg.ZR_Transition(a.id, CE_STATE_TESTED_MITIGATED, utc + 60, "RETEST") == true);
   SZoneRecord got;
   CE_InitZone(got);
   CE_CHECK(reg.ZR_Get(0, got) == true);
   CE_CHECK(got.state == CE_STATE_TESTED_MITIGATED);
   CE_CHECK(reg.ZR_Transition(a.id, CE_STATE_DETECTED, utc + 120, "BAD") == false);
   reg.ZR_MarkEvaluated(a.id, 91.0, 2, "ENTER_DRY_RUN", "NONE", utc + 120);
   CE_CHECK(reg.ZR_Get(0, got) == true);
   CE_CHECK_NEAR(got.last_score, 91.0, 0.001);

   string line = "";
   CE_SerializeZone(got, line);
   SZoneRecord roundtrip;
   CE_InitZone(roundtrip);
   CE_CHECK(CE_DeserializeZone(line, roundtrip) == true);
   CE_CHECK_STR(roundtrip.id, got.id);
   CE_CHECK(roundtrip.direction == got.direction);
   CE_CHECK(roundtrip.state == got.state);
   CE_CHECK_NEAR(roundtrip.lo, got.lo, 0.00001);
   CE_CHECK_NEAR(roundtrip.hi, got.hi, 0.00001);
   CE_CHECK_STR(roundtrip.last_decision, got.last_decision);

   string snapshot = "";
   CE_SaveRegistrySnapshot(reg, snapshot);
   CE_CHECK_HAS(snapshot, got.id);
   CZoneRegistry restored;
   restored.ZR_Init();
   CE_CHECK(CE_LoadRegistrySnapshot(restored, snapshot) == 1);
   CE_CHECK(restored.ZR_Find(got.id) >= 0);

   CZoneRegistry expiring;
   expiring.ZR_Init();
   SZoneRecord old_zone;
   CE_InitZone(old_zone);
   old_zone.id = zoneId(-1, utc - 100 * 3600);
   old_zone.direction = -1;
   old_zone.lo = 3547.0;
   old_zone.hi = 3569.0;
   old_zone.born_utc = utc - 100 * 3600;
   CE_CHECK(expiring.ZR_Upsert(old_zone) == true);
   expiring.ZR_Expire(utc, 48 * 3600);
   CE_CHECK(expiring.ZR_Get(0, got) == true);
   CE_CHECK(got.state == CE_STATE_EXPIRED);
   CE_CHECK_STR(got.last_reject, "AGE_TTL");
}

static void testAIParserAndFiles(const datetime utc)
{
   setupMarket(utc + 7200);
   string good = aiJson(-1, 0.72, utc);
   SAIOpinion ai;
   CE_InitAIOpinion(ai);
   CE_CHECK(CE_ParseAIOpinion(good, utc + 10, 60, ai) == true);
   CE_CHECK_STR(ai.why, "AI_OK");
   CE_CHECK(ai.direction == -1);
   CE_CHECK_NEAR(ai.confidence, 0.72, 0.0001);
   CE_CHECK_HAS(ai.reasons, "sweep");
   CE_CHECK_HAS(ai.invalidation, "3570");

   CE_InitAIOpinion(ai);
   CE_CHECK(CE_ParseAIOpinion("{\"direction\":0,\"confidence\":0.5,\"reasons\":\"x\",\"invalidation\":\"y\",\"as_of\":" +
                             IntegerToString((long)utc) + "}", utc + 10, 60, ai) == false);
   CE_CHECK_STR(ai.why, "AI_DIRECTION_INVALID");
   CE_InitAIOpinion(ai);
   CE_CHECK(CE_ParseAIOpinion(aiJson(-1, 1.20, utc), utc + 10, 60, ai) == false);
   CE_CHECK_STR(ai.why, "AI_CONFIDENCE_INVALID");
   CE_InitAIOpinion(ai);
   CE_CHECK(CE_ParseAIOpinion(aiJson(-1, 0.72, utc - 120), utc, 60, ai) == false);
   CE_CHECK_STR(ai.why, "AI_STALE_OR_FUTURE");
   CE_InitAIOpinion(ai);
   CE_CHECK(CE_ParseAIOpinion("", utc, 60, ai) == false);
   CE_CHECK_STR(ai.why, "AI_MISSING_OR_EMPTY");

   qsmc_ce::set_file("one.txt", "abc\n");
   string out = "";
   CE_CHECK(CE_ReadWholeFile("one.txt", out) == true);
   CE_CHECK_STR(out, "abc\n");
   CE_CHECK(CE_ReadWholeFile("missing.txt", out) == false);
   CE_WriteWholeFile("two.txt", "one\ntwo\n");
   CE_CHECK(CE_ReadWholeFile("two.txt", out) == true);
   CE_CHECK_STR(out, "one\ntwo\n");

   qsmc_ce::set_file(InpAIFile, good);
   string read_why = "";
   string payload = "";
   CE_CHECK(CE_ReadWholeFileWithTimeout(InpAIFile, 250, payload, read_why) == true);
   CE_CHECK_STR(read_why, "AI_FILE_READ_OK");
   CE_CHECK_HAS(payload, "direction");
   CE_CHECK(CE_ReadWholeFileWithTimeout("missing_ai.json", 250, payload, read_why) == false);
   CE_CHECK_STR(read_why, "AI_FILE_MISSING");

   qsmc_ce::set_read_delay_ms(1000);
   CE_CHECK(CE_ReadWholeFileWithTimeout(InpAIFile, 250, payload, read_why) == false);
   CE_CHECK_STR(read_why, "AI_TIMEOUT");
   qsmc_ce::set_read_delay_ms(0);

   SZoneFacts f;
   CE_InitFacts(f);
   CE_LoadAIOpinion(utc + 10, f);
   CE_CHECK(f.ai_used == false);
   CE_CHECK_STR(f.ai_why, "AI_DISABLED");

   CE_CHECK(QATS_SetInput("InpUseAIAgent", "true") == true);
   qsmc_ce::reset_files();
   qsmc_ce::set_file(InpAIFile, good);
   CE_InitFacts(f);
   CE_LoadAIOpinion(utc + 10, f);
   CE_CHECK(f.ai_used == true);
   CE_CHECK_STR(f.ai_why, "AI_OK");
   CE_CHECK(f.ai_direction == -1);
   CE_CHECK_NEAR(f.ai_confidence, 0.72, 0.0001);

   qsmc_ce::reset_files();
   qsmc_ce::set_file(InpAIFile, good);
   qsmc_ce::set_read_delay_ms(1000);
   CE_InitFacts(f);
   CE_LoadAIOpinion(utc + 10, f);
   CE_CHECK(f.ai_used == false);
   CE_CHECK_STR(f.ai_why, "AI_TIMEOUT");
   CE_CHECK(QATS_SetInput("InpUseAIAgent", "false") == true);
   qsmc_ce::reset_files();
}

static void testScoreAndDecision(const datetime utc)
{
   setupMarket(utc + 7200);
   SZoneFacts f;
   makeGoodFacts(f, utc);
   SScoreResult r;
   CE_InitScore(r);
   CE_ScoreComponents(f, r);
   CE_CHECK_NEAR(r.available_max, 95.0, 0.0001);
   CE_CHECK_NEAR(r.q_pts, 20.0, 0.0001);
   CE_CHECK_NEAR(r.liq_pts, 15.0, 0.0001);
   CE_CHECK_NEAR(r.struct_pts, 20.0, 0.0001);
   CE_CHECK_NEAR(r.htf_pts, 15.0, 0.0001);
   CE_CHECK_NEAR(r.vol_pts, 10.0, 0.0001);
   CE_CHECK_NEAR(r.session_pts, 10.0, 0.0001);
   CE_CHECK_NEAR(r.exec_pts, 10.0, 0.0001);
   CE_CHECK_NEAR(r.ai_pts, 0.0, 0.0001);
   CE_CHECK(r.total == 100);
   CE_CHECK(r.tier == 2);
   CE_CHECK_STR(r.tier_text, "A");
   CE_CHECK_STR(r.ai_why, "AI_DISABLED");

   SScoreResult with_ai;
   CE_InitScore(with_ai);
   f.ai_used = true;
   f.ai_direction = 1;
   f.ai_confidence = 0.80;
   f.ai_why = "AI_OK";
   f.ai_reasons = "sweep; choch";
   f.ai_invalidation = "close above 3570";
   CE_ScoreComponents(f, with_ai);
   CE_CHECK_NEAR(with_ai.available_max, 100.0, 0.0001);
   CE_CHECK_NEAR(with_ai.ai_pts, 4.0, 0.0001);
   CE_CHECK(with_ai.total == 100);
   CE_CHECK_STR(with_ai.ai_why, "AI_OK");
   f.ai_used = false;

   SAccountState a;
   makeGoodAccount(a, utc);
   CE_InitScore(r);
   CE_EvaluateZone(f, a, r);
   CE_CHECK_STR(r.decision, "ENTER_DRY_RUN");
   CE_CHECK_STR(r.reject_code, "NONE");
   CE_CHECK(r.plan_ready == true);
   CE_CHECK(r.lots > 0.0);
   CE_CHECK(r.entry_price > f.lo && r.entry_price < f.hi);
   CE_CHECK(r.sl < r.entry_price);
   CE_CHECK(r.tp > r.entry_price);
   CE_CHECK(r.partial_tp <= r.tp && r.partial_tp > r.entry_price);
   CE_CHECK(r.trail_sl < r.entry_price);
   CE_CHECK_NEAR(r.risk_scale, 1.0, 0.0001);
   CE_CHECK_STR(r.entry_mode, "RETEST");
   CE_CHECK_HAS(r.reject_values, "total=100");
   CE_PlaceOrder(f, a, r, utc);
   CE_CHECK_STR(r.order_action, "DRY_RUN");
   CE_CHECK(sim::S.sendCount == 0);

   SScoreResult bad_session;
   CE_InitScore(bad_session);
   f.session = CE_SESSION_ASIA;
   CE_ScoreComponents(f, bad_session);
   CE_ApplyDecision(f, a, bad_session);
   CE_CHECK_STR(bad_session.reject_code, "SESSION_PERMISSION");
   CE_CHECK(bad_session.session_permission == false);
   f.session = CE_SESSION_LONDON;

   SScoreResult bad_htf;
   CE_InitScore(bad_htf);
   f.h4_bias = -1;
   f.h1_bias = -1;
   f.htf_alignment = 0.0;
   CE_ScoreComponents(f, bad_htf);
   CE_ApplyDecision(f, a, bad_htf);
   CE_CHECK_STR(bad_htf.reject_code, "HTF_BELOW_MIN");
   CE_CHECK(bad_htf.risk_scale < 1.0);
   f.h4_bias = 1;
   f.h1_bias = 1;
   f.htf_alignment = 1.0;

   SScoreResult low;
   CE_InitScore(low);
   f.kind = CE_KIND_OB;
   f.state = CE_STATE_DETECTED;
   f.touches = 2;
   f.age_hours = 20.0;
   f.asia_sweep = false;
   f.london_sweep = false;
   f.bsl_ssl = false;
   f.eqh_eql = false;
   f.sweep_before_reaction = false;
   f.m1_choch = false;
   f.m5_bos = false;
   f.confirmation_close = false;
   f.second_reaction = false;
   f.poc_reaction = false;
   f.vah_val_reaction = false;
   f.volume_expansion = false;
   f.spread_points = 100.0;
   f.rr_at_fill = 0.0;
   f.session = CE_SESSION_OFFPEAK;
   CE_ScoreComponents(f, low);
   CE_ApplyDecision(f, a, low);
   CE_CHECK(low.tier == 0);
   CE_CHECK_STR(low.reject_code, "SCORE_BELOW_B");

   makeGoodFacts(f, utc);
   SAccountState real_account;
   makeGoodAccount(real_account, utc);
   real_account.real_account = true;
   SScoreResult real_result;
   CE_InitScore(real_result);
   CE_ApplyDecision(f, real_account, real_result);
   CE_CHECK_STR(real_result.reject_code, "REAL_REFUSED");
   CE_CHECK(real_result.account_ok == false);

   string why = "";
   SAccountState account_bad;
   makeGoodAccount(account_bad, utc);
   account_bad.kill_switch = true;
   CE_CHECK(CE_AccountAllowsEntry(account_bad, why) == false);
   CE_CHECK_STR(why, "KILL_SWITCH");
   account_bad.kill_switch = false;
   account_bad.real_account = true;
   CE_CHECK(CE_AccountAllowsEntry(account_bad, why) == false);
   CE_CHECK_STR(why, "REAL_REFUSED");
   account_bad.real_account = false;
   account_bad.daily_lock = true;
   CE_CHECK(CE_AccountAllowsEntry(account_bad, why) == false);
   CE_CHECK_STR(why, "DAILY_LOSS_LOCK");
   account_bad.daily_lock = false;
   CE_CHECK(CE_AccountAllowsEntry(account_bad, why) == true);
   CE_CHECK_STR(why, "ACCOUNT_OK");
}

static void testModesAndPlans(const datetime utc)
{
   setupMarket(utc + 7200);
   SZoneFacts f;
   makeGoodFacts(f, utc);
   double entry = 0.0;
   string why = "";
   CE_CHECK(CE_ModeEvaluate(CE_MODE_RETEST, f, entry, why) == true);
   CE_CHECK_STR(why, "RETEST_READY");
   CE_CHECK_NEAR(entry, 3558.0, 0.0001);
   f.confirmation_close = false;
   CE_CHECK(CE_ModeEvaluate(CE_MODE_RETEST, f, entry, why) == false);
   CE_CHECK_STR(why, "RETEST_NO_CONFIRMED_CLOSE");
   f.confirmation_close = true;

   CE_CHECK(CE_ModeEvaluate(CE_MODE_MOMENTUM, f, entry, why) == true);
   CE_CHECK_STR(why, "MOMENTUM_READY");
   f.chase_distance = 10.0;
   CE_CHECK(CE_ModeEvaluate(CE_MODE_MOMENTUM, f, entry, why) == false);
   CE_CHECK_STR(why, "MOMENTUM_CHASE_TOO_FAR");
   f.chase_distance = 1.0;

   CE_CHECK(CE_ModeEvaluate(CE_MODE_REVERSAL, f, entry, why) == true);
   CE_CHECK_STR(why, "REVERSAL_READY");
   CE_CHECK_NEAR(entry, 3555.0, 0.0001);
   f.sweep = false;
   CE_CHECK(CE_ModeEvaluate(CE_MODE_REVERSAL, f, entry, why) == false);
   CE_CHECK_STR(why, "REVERSAL_NEEDS_SWEEP_CHOCH_SECOND_REACTION");

   makeGoodFacts(f, utc);
   SScoreResult r;
   CE_InitScore(r);
   CE_ScoreComponents(f, r);
   r.risk_scale = 1.0;
   CE_BuildPlan(f, r);
   CE_CHECK(r.plan_ready == true);
   CE_CHECK(r.lots > 0.0);
   CE_CHECK(r.partial_tp <= r.tp);
   CE_CHECK_STR(r.plan_why, "RETEST_READY");
   CE_CHECK_NEAR(CE_CalcLots(f, 1.0, r.entry_price, r.sl), r.lots, 0.0001);
   CE_CHECK_NEAR(CE_BreakEvenSl(r.entry_price, 1, 0.20), r.entry_price - 0.20, 0.0001);
   CE_CHECK_NEAR(CE_BreakEvenSl(r.entry_price, -1, 0.20), r.entry_price + 0.20, 0.0001);

   makeGoodFacts(f, utc);
   f.confirmation_close = false;
   CE_InitScore(r);
   CE_ScoreComponents(f, r);
   CE_BuildPlan(f, r);
   CE_CHECK(r.plan_ready == false);
   CE_CHECK_STR(r.reject_code, "ENTRY_MODE_NOT_READY");
   CE_CHECK_STR(r.decision, "NEAR_MISS");
}

static void testAccountPermissionsAndState(const datetime utc)
{
   setupMarket(utc + 7200);
   string why = "";
   CE_CHECK(CE_AccountPermissionsOk(why) == false);
   CE_CHECK_STR(why, "LIVE_ORDERS_DISABLED");
   CE_CHECK(QATS_SetInput("InpAllowLiveOrders", "true") == true);
   CE_CHECK(CE_AccountPermissionsOk(why) == true);
   CE_CHECK_STR(why, "PERMISSIONS_OK");
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_REAL;
   CE_CHECK(CE_AccountPermissionsOk(why) == false);
   CE_CHECK_STR(why, "REAL_REFUSED");
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_CONTEST;
   CE_CHECK(CE_AccountPermissionsOk(why) == false);
   CE_CHECK_STR(why, "CONTEST_REFUSED");
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_DEMO;
   CE_CHECK(QATS_SetInput("InpAllowLiveOrders", "false") == true);

   CE_CHECK(CE_IsSuccessRetcode(TRADE_RETCODE_DONE) == true);
   CE_CHECK(CE_IsSuccessRetcode(TRADE_RETCODE_PLACED) == true);
   CE_CHECK(CE_IsSuccessRetcode(TRADE_RETCODE_INVALID) == false);
   CE_CHECK(CE_IsTransientRetcode(TRADE_RETCODE_REQUOTE) == true);
   CE_CHECK(CE_IsTransientRetcode(TRADE_RETCODE_INVALID_FILL) == true);
   CE_CHECK(CE_IsTransientRetcode(TRADE_RETCODE_INVALID) == false);

   CE_RefreshDailyState(utc, 10000.0);
   CE_CHECK(g_daily_lock == false);
   CE_RefreshDailyState(utc, 9900.0);
   CE_CHECK(g_daily_lock == true);
   CE_CHECK(GlobalVariableGet("CE_DailyLock") > 0.5);
   CE_LoadPersistentState();
   CE_CHECK(g_daily_lock == true);

   sim::reset();
   CE_CHECK(QATS_SetInput("InpUseAIAgent", "false") == true);
   g_daily_lock = false;
   g_trades_today = 0;
   g_last_entry_utc = 0;
   CE_RecordEntry(utc);
   CE_CHECK(g_trades_today == 1);
   CE_CHECK(g_last_entry_utc == utc);
   CE_LoadPersistentState();
   CE_CHECK(g_trades_today == 1);
   CE_CHECK(g_last_entry_utc == utc);
   ulong ticket = 1000001;
   CE_RecordPositionPlan(ticket, 3600.0, 3560.0);
   string key_final = "CE_FinalTP_" + IntegerToString((long)ticket);
   string key_partial = "CE_PartialTP_" + IntegerToString((long)ticket);
   CE_CHECK_NEAR(GlobalVariableGet(key_final), 3600.0, 0.0001);
   CE_CHECK_NEAR(GlobalVariableGet(key_partial), 3560.0, 0.0001);
}

static void testLogsPanelAndFormats(const datetime utc)
{
   setupMarket(utc + 7200);
   SZoneRecord z;
   CE_InitZone(z);
   z.id = zoneId(-1, utc);
   z.direction = -1;
   z.kind = CE_KIND_OB_FVG;
   z.state = CE_STATE_TESTED_MITIGATED;
   z.lo = 3547.0;
   z.hi = 3569.0;
   SScoreResult r;
   CE_InitScore(r);
   r.total = 88;
   r.tier = 2;
   r.tier_text = "A";
   r.decision = "ENTER_DRY_RUN";
   r.reject_code = "NONE";
   r.reject_values = CE_BuildRejectValues(SZoneFacts(), r);
   string line = CE_FormatLogLine(z, r, utc);
   CE_CHECK_HAS(line, "CE|utc=");
   CE_CHECK_HAS(line, "zone=Z;SELL;");
   CE_CHECK_HAS(line, "state=TESTED_MITIGATED");
   CE_CHECK_HAS(line, "q=0.00/20");
   CE_CHECK_HAS(line, "total=88");
   CE_CHECK_HAS(line, "decision=ENTER_DRY_RUN");
   CE_CHECK_HAS(line, "ai_why=AI_DISABLED");
   CE_CHECK_HAS(line, "plan=false");
   CE_CHECK_HAS(line, "account_ok=false");
   string header = CE_CsvHeader();
   string row = CE_FormatCsvRow(z, r, utc);
   CE_CHECK(countChar(row, ',') == countChar(header, ','));
   CE_CHECK_HAS(row, "ENTER_DRY_RUN");
   CE_CHECK_HAS(header, "ai_invalidation");
   CE_CHECK_HAS(CE_PanelBreakdown(r), "q=0.0");

   CE_InitPanel();
   SScoreResult s1;
   CE_InitScore(s1);
   s1.total = 10;
   s1.decision = "NEAR_MISS";
   s1.reject_code = "C";
   CE_UpdatePanel(z, s1);
   s1.total = 80;
   CE_UpdatePanel(z, s1);
   s1.total = 60;
   CE_UpdatePanel(z, s1);
   s1.total = 90;
   CE_UpdatePanel(z, s1);
   CE_CHECK(g_top_score[0] == 90);
   CE_CHECK(g_top_score[1] == 80);
   CE_CHECK(g_top_score[2] == 60);
   CE_CHECK_STR(g_last_decision, "NEAR_MISS");
   CE_RenderPanel(utc);
   CE_CHECK_HAS(sim::S.lastComment, "CONFIRMATION SCORE ENGINE");
   CE_CHECK_HAS(sim::S.lastComment, "TOP1=");
   CE_CHECK(chartsim::C.redraws > 0);
}

static void testCollectAndOnTick(const datetime utc)
{
   datetime server = utc + 7200;
   setupMarket(server);
   captured_logs.clear();
   sim::S.onPrint = [](const std::string &s) { ce_drv::captured_logs.push_back(s); };

   string sell_id = zoneId(-1, utc);
   string sell_tip = "Bearish OB+FVG 3547.00–3569.00 MITIGATED | " + sell_id;
   CE_CHECK(ObjectCreate(0, "QSVP_ZN_S0", OBJ_RECTANGLE, 0, server, 3569.0,
                         server + 3600, 3547.0) == true);
   CE_CHECK(ObjectSetString(0, "QSVP_ZN_S0", OBJPROP_TOOLTIP, sell_tip) == true);

   string buy_id = zoneId(1, utc + 60);
   string buy_tip = "Bullish OB 3500.00-3510.00 VALIDATED | " + buy_id;
   CE_CHECK(ObjectCreate(0, buy_id, OBJ_RECTANGLE, 0, server, 3510.0,
                         server + 3600, 3500.0) == true);
   CE_CHECK(ObjectSetString(0, buy_id, OBJPROP_TOOLTIP, buy_tip) == true);

   OnTick();
   CE_CHECK(g_reg.ZR_Count() == 2);
   CE_CHECK(g_reg.ZR_Find(sell_id) >= 0);
   CE_CHECK(g_reg.ZR_Find(buy_id) >= 0);
   CE_CHECK(captured_logs.size() >= 2);
   CE_CHECK_HAS(captured_logs[0], "CE|utc=");
   string csv = qsmc_ce::get_file(InpCsvFile);
   CE_CHECK_HAS(csv, CE_CsvHeader());
   CE_CHECK_HAS(csv, sell_id);
   CE_CHECK_HAS(csv, buy_id);
   CE_CHECK(countChar(csv, '\n') >= 3);
   string registry = qsmc_ce::get_file(InpRegistryFile);
   CE_CHECK_HAS(registry, sell_id);
   CE_CHECK_HAS(registry, buy_id);
   CE_CHECK_HAS(sim::S.lastComment, "CONFIRMATION SCORE ENGINE");
   CE_CHECK_HAS(sim::S.lastComment, "dry_run=true");
   CE_CHECK(sim::S.sendCount == 0);
   CE_CHECK(sim::S.apiErrors.empty());
   CE_CHECK(sim::S.fmtErrors.empty());

   SZoneRecord got;
   CE_InitZone(got);
   CE_CHECK(g_reg.ZR_Get(g_reg.ZR_Find(sell_id), got) == true);
   CE_CHECK(got.state == CE_STATE_TESTED_MITIGATED);
   CE_CHECK_NEAR(got.lo, 3547.0, 0.001);
   CE_CHECK_NEAR(got.hi, 3569.0, 0.001);
}

static void testInitRefusal(const datetime utc)
{
   setupMarket(utc + 7200);
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_REAL;
   CE_CHECK(OnInit() == INIT_FAILED);
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_CONTEST;
   CE_CHECK(OnInit() == INIT_FAILED);
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_DEMO;
   CE_CHECK(OnInit() == INIT_SUCCEEDED);
}

static void testPartialClose(const datetime utc)
{
   setupMarket(utc + 7200);
   ulong ticket = 1000001;
   sim::S.positions.clear();
   sim::Position p{};
   p.ticket = ticket;
   p.magic = (long)InpMagic;
   p.symbol = "XAUUSD";
   p.type = POSITION_TYPE_BUY;
   p.volume = 0.10;
   p.priceOpen = 3550.0;
   p.sl = 3540.0;
   p.tp = 3600.0;
   p.time = utc;
   p.comment = "CE";
   p.commission = 0.0;
   sim::S.positions.push_back(p);
   sim::S.nextTicket = ticket + 1;
   sim::S.bid = 3560.0;
   sim::S.ask = 3560.20;
   sim::S.haveQuote = true;
   sim::S.marketOpen = true;
   sim::S.terminalTradeAllowed = true;
   sim::S.mqlTradeAllowed = true;
   sim::S.acc.tradeAllowed = true;
   CE_RecordPositionPlan(ticket, 3600.0, 3560.0);

   // Default dry-run must not modify even a same-magic position.
   CE_CHECK(InpDryRun == true);
   CE_CHECK(InpAllowLiveOrders == false);
   CE_ManagePositions(utc);
   CE_CHECK(sim::S.sendCount == 0);
   CE_CHECK_NEAR(sim::S.positions[0].volume, 0.10, 0.0001);
   CE_CHECK(GlobalVariableGet("CE_PartialDone_" + IntegerToString((long)ticket)) == 0.0);

   // Explicit DEMO arming exercises the same plan-management path.
   InpDryRun = false;
   InpAllowLiveOrders = true;
   CE_ManagePositions(utc);
   InpDryRun = true;
   InpAllowLiveOrders = false;
   CE_CHECK(sim::S.positions.size() == 1);
   CE_CHECK_NEAR(sim::S.positions[0].volume, 0.05, 0.0001);
   string done_key = "CE_PartialDone_" + IntegerToString((long)ticket);
   CE_CHECK(GlobalVariableGet(done_key) > 0.5);
   CE_CHECK(sim::S.sendCount > 0);
   CE_CHECK(sim::S.apiErrors.empty());
}

// Replay/backtest modes live in a separate host-only include. It is included
// inside namespace ce_drv so it can reuse the unit helpers above and call the
// real compiled CE_* functions. No MQL5 source is generated from this file.
#include "qsmc_ce_replay.inc"

static int runAll()
{
   datetime utc = utcOf(2026, 11, 25, 8, 0);
   testDefaultContract();
   testInitRefusal(utc);
   testSmallHelpers();
   testCivilAndDst(utc);
   testParser();
   testRegistryAndTransitions(utc);
   testAIParserAndFiles(utc);
   testScoreAndDecision(utc);
   testModesAndPlans(utc);
   testAccountPermissionsAndState(utc);
   testLogsPanelAndFormats(utc);
   testCollectAndOnTick(utc);
   testPartialClose(utc);
   std::cout << "{\"status\":\"" << (failures == 0 ? "PASS" : "FAIL")
             << "\",\"checks\":" << checks << ",\"failed\":" << failures << "}\n";
   return failures == 0 ? 0 : 1;
}
} // namespace ce_drv

int main(int argc, char **argv)
{
   std::string mode = argc > 1 ? argv[1] : "selftest";
   if(mode == "inputs")
   {
      for(int i = 0; i < QATS_INPUT_COUNT; i++)
      {
         std::cout << QATS_INPUT_NAMES[i] << "\n";
      }
      return 0;
   }
   if(mode == "selftest")
   {
      return ce_drv::runAll();
   }
   if(mode == "replay")
   {
      return ce_drv::runReplay();
   }
   if(mode == "backtest")
   {
      return ce_drv::runBacktest();
   }
   std::cerr << "usage: " << argv[0] << " selftest|inputs|replay|backtest\n";
   return 2;
}
