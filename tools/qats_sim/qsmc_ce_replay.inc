// qsmc_ce_replay.inc - deterministic replay/backtest drivers for the CE host harness.
// Included INSIDE namespace ce_drv, after the unit helpers in qsmc_ce_driver.inc.
// It calls the real compiled CE_* functions. It is NOT MetaEditor, NOT Strategy
// Tester, NOT broker ticks, NOT a live/demo trading result.

static std::string jstr(const std::string &s)
{
   std::ostringstream os;
   os << "\"";
   for(size_t i = 0; i < s.size(); i++)
   {
      unsigned char c = (unsigned char)s[i];
      if(c == '"' || c == '\\') { os << '\\' << (char)c; }
      else if(c == '\n')        { os << "\\n"; }
      else if(c == '\r')        { os << "\\r"; }
      else if(c == '\t')        { os << "\\t"; }
      else if(c < 0x20)
      {
         std::ostringstream hex;
         hex << "\\u" << std::hex << std::setw(4) << std::setfill('0') << (int)c;
         os << hex.str();
      }
      else                      { os << (char)c; }
   }
   os << "\"";
   return os.str();
}

static void jf(std::ostringstream &os, bool &first, const std::string &key, const std::string &raw)
{
   if(!first) { os << ","; }
   first = false;
   os << jstr(key) << ":" << raw;
}
static void jfs(std::ostringstream &os, bool &first, const std::string &key, const std::string &v)
{
   jf(os, first, key, jstr(v));
}
static void jfi(std::ostringstream &os, bool &first, const std::string &key, const long long v)
{
   jf(os, first, key, std::to_string(v));
}
static void jfb(std::ostringstream &os, bool &first, const std::string &key, const bool v)
{
   jf(os, first, key, v ? "true" : "false");
}
static void jfd(std::ostringstream &os, bool &first, const std::string &key, const double v)
{
   std::ostringstream tmp;
   tmp << std::fixed << std::setprecision(4) << v;
   jf(os, first, key, tmp.str());
}
static std::string jarr(const std::vector<std::string> &items)
{
   std::ostringstream os;
   os << "[";
   for(size_t i = 0; i < items.size(); i++)
   {
      if(i) { os << ","; }
      os << items[i];
   }
   os << "]";
   return os.str();
}
static std::string isoUtc(const datetime t)
{
   long days = (long)(t / 86400);
   long sec = (long)(t % 86400);
   if(sec < 0) { sec += 86400; days--; }
   int y = 1970, m = 1, d = 1;
   CE_CivilFromDays(days, y, m, d);
   std::ostringstream os;
   os << std::setw(4) << std::setfill('0') << y << "-"
      << std::setw(2) << m << "-" << std::setw(2) << d << " "
      << std::setw(2) << (sec / 3600) << ":"
      << std::setw(2) << ((sec % 3600) / 60) << ":"
      << std::setw(2) << (sec % 60) << "Z";
   return os.str();
}

struct RParser
{
   std::string label;
   std::string name;
   std::string format;
   bool ok;
   SZoneRecord zone;
};
struct RTransition
{
   std::string from;
   std::string to;
   bool expected;
   bool actual;
};
struct RTime
{
   std::string label;
   datetime utc;
   bool expected_eu;
   bool expected_us;
   bool actual_eu;
   bool actual_us;
   datetime server;
   datetime roundtrip;
};
struct RAi
{
   std::string label;
   bool used;
   std::string load_why;
   std::string score_why;
   double confidence;
   double ai_pts;
   double available_max;
};
struct REval
{
   std::string label;
   std::string setup;
   std::string object_format;
   datetime utc;
   int dza_hour;
   std::string session;
   std::string zone;
   std::string state;
   std::string dir;
   std::string kind;
   int score;
   std::string tier;
   std::string decision;
   std::string reject;
   std::string mode;
   bool plan_ready;
   double risk_scale;
   double htf_penalty;
   double lots;
   std::string log;
   std::string csv;
};

static std::string parserObj(const RParser &p)
{
   std::ostringstream os; bool first = true;
   jfs(os, first, "label", p.label);
   jfs(os, first, "name", p.name);
   jfs(os, first, "format", p.format);
   jfb(os, first, "parse_ok", p.ok);
   jfs(os, first, "id", p.zone.id);
   jfs(os, first, "direction", CE_DirectionText(p.zone.direction));
   jfs(os, first, "state", CE_StateText(p.zone.state));
   jfs(os, first, "kind", CE_KindText(p.zone.kind));
   jfd(os, first, "lo", p.zone.lo);
   jfd(os, first, "hi", p.zone.hi);
   jfi(os, first, "born_utc", (long long)p.zone.born_utc);
   return "{" + os.str() + "}";
}
static std::string transitionObj(const RTransition &t)
{
   std::ostringstream os; bool first = true;
   jfs(os, first, "from", t.from);
   jfs(os, first, "to", t.to);
   jfb(os, first, "expected", t.expected);
   jfb(os, first, "actual", t.actual);
   jfb(os, first, "pass", t.expected == t.actual);
   return "{" + os.str() + "}";
}
static std::string timeObj(const RTime &t)
{
   std::ostringstream os; bool first = true;
   jfs(os, first, "label", t.label);
   jfs(os, first, "utc_iso", isoUtc(t.utc));
   jfi(os, first, "utc", (long long)t.utc);
   jfb(os, first, "expected_eu_dst", t.expected_eu);
   jfb(os, first, "actual_eu_dst", t.actual_eu);
   jfb(os, first, "expected_us_dst", t.expected_us);
   jfb(os, first, "actual_us_dst", t.actual_us);
   jfi(os, first, "server", (long long)t.server);
   jfi(os, first, "roundtrip_utc", (long long)t.roundtrip);
   jfb(os, first, "roundtrip_exact", t.utc == t.roundtrip);
   jfb(os, first, "pass", t.expected_eu == t.actual_eu && t.expected_us == t.actual_us);
   return "{" + os.str() + "}";
}
static std::string aiObj(const RAi &a)
{
   std::ostringstream os; bool first = true;
   jfs(os, first, "case", a.label);
   jfb(os, first, "ai_used", a.used);
   jfs(os, first, "load_why", a.load_why);
   jfs(os, first, "score_why", a.score_why);
   jfd(os, first, "confidence", a.confidence);
   jfd(os, first, "ai_points", a.ai_pts);
   jfd(os, first, "available_max", a.available_max);
   return "{" + os.str() + "}";
}
static std::string evalObj(const REval &e)
{
   std::ostringstream os; bool first = true;
   jfs(os, first, "label", e.label);
   jfs(os, first, "setup", e.setup);
   jfs(os, first, "object_format", e.object_format);
   jfs(os, first, "utc_iso", isoUtc(e.utc));
   jfi(os, first, "utc", (long long)e.utc);
   jfi(os, first, "dza_hour", (long long)e.dza_hour);
   jfs(os, first, "session", e.session);
   jfs(os, first, "zone", e.zone);
   jfs(os, first, "state", e.state);
   jfs(os, first, "dir", e.dir);
   jfs(os, first, "kind", e.kind);
   jfi(os, first, "score", (long long)e.score);
   jfs(os, first, "tier", e.tier);
   jfs(os, first, "decision", e.decision);
   jfs(os, first, "reject", e.reject);
   jfs(os, first, "mode", e.mode);
   jfb(os, first, "plan_ready", e.plan_ready);
   jfd(os, first, "risk_scale", e.risk_scale);
   jfd(os, first, "htf_penalty", e.htf_penalty);
   jfd(os, first, "lots", e.lots);
   jfs(os, first, "log", e.log);
   jfs(os, first, "csv", e.csv);
   return "{" + os.str() + "}";
}

static void setReplayDefaults()
{
   InpMasterEnable = true;
   InpDryRun = true;
   InpAllowLiveOrders = false;
   InpAllowRealTrading = false;
   InpKillSwitch = false;
   InpRequireSessionPermission = true;
   InpAllowAsiaEntries = false;
   InpAllowOffPeakEntries = false;
   InpTierA = 75;
   InpTierB = 55;
   InpMinHtfPoints = 3;
   InpTierBRiskScale = 0.50;
   InpHtfCounterRiskScale = 0.60;
   InpRiskPercent = 0.25;
   InpMaxSpreadPoints = 60.0;
   InpMinRRAtFill = 1.20;
   InpEntryMode = CE_MODE_RETEST;
   InpBrokerUtcOffsetWinterMinutes = 120;
   InpBrokerUtcOffsetSummerMinutes = 180;
   InpBrokerUsesEuDst = true;
   InpUseAIAgent = false;
   InpAITimeoutMs = 250;
   InpAIMaxAgeSec = 60;
}

static void replayFacts(SZoneFacts &f, const SZoneRecord &z, const datetime utc, const int scenario, const int mode)
{
   CE_InitFacts(f);
   f.direction = z.direction;
   f.kind = z.kind;
   f.state = z.state;
   f.lo = z.lo;
   f.hi = z.hi;
   f.born_utc = z.born_utc;
   f.now_utc = utc;
   f.age_hours = (double)(utc - z.born_utc) / 3600.0;
   f.touches = z.touches;
   double mid = (z.lo + z.hi) / 2.0;
   f.atr_m1 = (scenario == 1 ? 10.0 : 8.0);
   f.zone_atr_ratio = (f.hi - f.lo) / f.atr_m1;
   f.atr_percentile = 50.0;
   f.spread_points = 20.0;
   f.spread_price = 0.20;
   f.spread_atr_pct = f.spread_price / f.atr_m1 * 100.0;
   f.bid = mid - 0.10;
   f.ask = mid + 0.10;
   f.current_price = (f.direction > 0 ? f.ask : f.bid);
   f.point = 0.01;
   f.tick_value = 1.0;
   f.equity = 10000.0;
   f.stops_level = 0;
   f.freeze_level = 0;
   f.min_stop_points = 20;
   f.session = CE_SessionOfUtc(utc);
   f.session_entry_allowed = CE_SessionEntryAllowed(f.session, InpAllowAsiaEntries, InpAllowOffPeakEntries);
   f.h4_bias = -1;
   f.h1_bias = (scenario == 1 ? -1 : 1);
   f.htf_alignment = CE_HtfAlignment(f.h1_bias, f.h4_bias, f.direction);
   f.asia_sweep = true;
   f.london_sweep = true;
   f.bsl_ssl = (scenario == 1);
   f.eqh_eql = (scenario == 1);
   f.sweep_before_reaction = (scenario == 1);
   f.m1_choch = true;
   f.m5_bos = (scenario == 1);
   f.confirmation_close = (mode != CE_MODE_RETEST || scenario == 1);
   f.second_reaction = (scenario == 1 || mode == CE_MODE_REVERSAL);
   f.sweep = (scenario == 1 || mode != CE_MODE_RETEST);
   f.closed_beyond_zone = (mode == CE_MODE_MOMENTUM);
   f.micro_bos = (mode == CE_MODE_MOMENTUM);
   f.first_pullback = (mode == CE_MODE_MOMENTUM);
   f.poc_reaction = true;
   f.vah_val_reaction = true;
   f.volume_expansion = true;
   f.mode = mode;
   f.retest_percent = 0.50;
   f.max_chase_atr = 1.50;
   f.momentum_close = mid + (f.direction > 0 ? f.atr_m1 : -f.atr_m1);
   f.pullback_price = mid;
   f.second_reaction_price = mid;
   f.chase_distance = 1.0;
   f.rr_at_fill = 2.0;
   f.room_to_liquidity = 60.0;
   f.nearest_liquidity = (f.direction > 0 ? mid + 60.0 : mid - 60.0);
   f.invalidation = (f.direction > 0 ? f.lo - f.atr_m1 : f.hi + f.atr_m1);
   f.ai_used = false;
   f.ai_direction = 0;
   f.ai_confidence = 0.0;
   f.ai_why = "AI_DISABLED";
   f.ai_as_of = 0;
}

static RParser parseCase(const std::string &label, const std::string &name,
                         const std::string &format, const std::string &tooltip,
                         const double lo, const double hi, const datetime anchor)
{
   RParser p;
   p.label = label;
   p.name = name;
   p.format = format;
   CE_InitZone(p.zone);
   p.ok = CE_ParseZoneObject(name, tooltip, lo, hi, anchor, p.zone);
   return p;
}

static int runReplay()
{
   setReplayDefaults();
   datetime winter_day = utcOf(2026, 11, 25, 8, 0);
   setupMarket(winter_day + 7200);
   CE_InitPanel();
   g_reg.ZR_Init();

   datetime s1_server = utcOf(2026, 11, 25, 1, 15);
   datetime s2_server = utcOf(2026, 11, 25, 18, 30);
   datetime s1_birth = CE_ServerToUtc(s1_server, 120, 180, true);
   datetime s2_birth = CE_ServerToUtc(s2_server, 120, 180, true);
   std::string s1_id = zoneId(-1, s1_birth);
   std::string s2_id = zoneId(1, s2_birth);
   std::string s1_tip = "Bearish OB+FVG 3547.06–3568.91 MITIGATED | " + s1_id;
   std::string s2_tip = "Bullish OB 3447.85-3464.37 VALIDATED | " + s2_id;
   std::string s1_plain = "Bearish OB+FVG 3547.06-3568.91 MITIGATED";
   std::string s2_plain = "Bullish OB 3447.85-3464.37 VALIDATED";

   std::vector<RParser> parser_cases;
   parser_cases.push_back(parseCase("S1 current object + tooltip id", "QSVP_ZN_S0",
      "QSVP_ZN_S0 / OBJPROP_TOOLTIP", s1_tip, 3547.06, 3568.91, s1_birth));
   parser_cases.push_back(parseCase("S1 legacy name", s1_id,
      "Z|SELL|<epoch> object name", s1_plain, 3547.06, 3568.91, s1_birth));
   parser_cases.push_back(parseCase("S2 current object + tooltip id", "QSVP_ZN_B0",
      "QSVP_ZN_B0 / OBJPROP_TOOLTIP", s2_tip, 3447.85, 3464.37, s2_birth));
   parser_cases.push_back(parseCase("S2 legacy name", s2_id,
      "Z|BUY|<epoch> object name", s2_plain, 3447.85, 3464.37, s2_birth));
   datetime generated_anchor = utcOf(2026, 11, 25, 9, 0);
   parser_cases.push_back(parseCase("current object without tooltip", "QSVP_ZN_B7",
      "QSVP_ZN_B7 generated stable id", "", 3500.0, 3510.0, generated_anchor));

   SZoneRecord z1, z2;
   CE_InitZone(z1); CE_InitZone(z2);
   bool p1 = CE_ParseZoneObject("QSVP_ZN_S0", s1_tip, 3547.06, 3568.91, s1_birth, z1);
   bool p2 = CE_ParseZoneObject("QSVP_ZN_B0", s2_tip, 3447.85, 3464.37, s2_birth, z2);

   // Registry starts at DETECTED, then transitions to the visible state. A
   // refused evaluation never deletes or burns the zone.
   SZoneRecord seed1 = z1, seed2 = z2;
   seed1.state = CE_STATE_DETECTED; seed1.touches = 0;
   seed2.state = CE_STATE_DETECTED;
   g_reg.ZR_Upsert(seed1);
   g_reg.ZR_Upsert(seed2);
   bool tr1 = g_reg.ZR_Transition(z1.id, CE_STATE_TESTED_MITIGATED, s1_birth, "SECOND_REACTION");
   bool tr2 = g_reg.ZR_Transition(z2.id, CE_STATE_VALIDATED, s2_birth, "ZONE_VALIDATED");
   g_reg.ZR_Get(g_reg.ZR_Find(z1.id), z1);
   g_reg.ZR_Get(g_reg.ZR_Find(z2.id), z2);

   std::vector<RTransition> transitions;
   RTransition t;
   t.from = CE_StateText(CE_STATE_DETECTED); t.to = CE_StateText(CE_STATE_VALIDATED);
   t.expected = true; t.actual = CE_CanTransition(CE_STATE_DETECTED, CE_STATE_VALIDATED); transitions.push_back(t);
   t.from = CE_StateText(CE_STATE_VALIDATED); t.to = CE_StateText(CE_STATE_TESTED_MITIGATED);
   t.expected = true; t.actual = CE_CanTransition(CE_STATE_VALIDATED, CE_STATE_TESTED_MITIGATED); transitions.push_back(t);
   t.from = CE_StateText(CE_STATE_TESTED_MITIGATED); t.to = CE_StateText(CE_STATE_TESTED_MITIGATED);
   t.expected = true; t.actual = CE_CanTransition(CE_STATE_TESTED_MITIGATED, CE_STATE_TESTED_MITIGATED); transitions.push_back(t);
   t.from = CE_StateText(CE_STATE_TESTED_MITIGATED); t.to = CE_StateText(CE_STATE_TRIGGERED);
   t.expected = true; t.actual = CE_CanTransition(CE_STATE_TESTED_MITIGATED, CE_STATE_TRIGGERED); transitions.push_back(t);
   t.from = CE_StateText(CE_STATE_TRIGGERED); t.to = CE_StateText(CE_STATE_TESTED_MITIGATED);
   t.expected = false; t.actual = CE_CanTransition(CE_STATE_TRIGGERED, CE_STATE_TESTED_MITIGATED); transitions.push_back(t);

   std::vector<RTime> time_checks;
   const datetime dst_points[9] = {
      utcOf(2026, 3, 29, 0, 30), utcOf(2026, 3, 29, 1, 30),
      utcOf(2026, 10, 25, 0, 30), utcOf(2026, 10, 25, 1, 30),
      utcOf(2026, 3, 8, 6, 30), utcOf(2026, 3, 8, 7, 30),
      utcOf(2026, 11, 1, 5, 30), utcOf(2026, 11, 1, 6, 30),
      utcOf(2026, 11, 25, 8, 30)
   };
   const std::string dst_labels[9] = {
      "EU spring 00:30Z before 01:00Z", "EU spring 01:30Z after 01:00Z",
      "EU fall 00:30Z before 01:00Z", "EU fall 01:30Z after 01:00Z",
      "US spring 06:30Z before 07:00Z", "US spring 07:30Z after 07:00Z",
      "US fall 05:30Z before 06:00Z", "US fall 06:30Z after 06:00Z",
      "2026-11-25 setup day"
   };
   const bool dst_eu[9] = {false, true, true, false, false, false, false, false, false};
   // US DST starts two Sundays before the EU spring edge and ends one week
   // after the EU autumn edge. These are the exact expected values at each
   // probe, not a copy of the EU array.
   const bool dst_us[9] = {true, true, true, true, false, true, true, false, false};
   for(int i = 0; i < 9; i++)
   {
      RTime x;
      x.label = dst_labels[i];
      x.utc = dst_points[i];
      x.expected_eu = dst_eu[i];
      x.expected_us = dst_us[i];
      x.actual_eu = CE_IsEuDst(x.utc);
      x.actual_us = CE_IsUsDst(x.utc);
      x.server = CE_UtcToBrokerServer(x.utc, 120, 180, true);
      x.roundtrip = CE_ServerToUtc(x.server, 120, 180, true);
      time_checks.push_back(x);
   }

   // Optional AI: disabled / missing / timeout / malformed / stale / valid /
   // direction mismatch. The score layer and a kill switch prove it cannot
   // dominate the decision or loosen an account gate.
   std::vector<RAi> ai_cases;
   InpUseAIAgent = true;
   InpAIFile = "QSMC\\ce_replay_ai.json";
   datetime ai_now = utcOf(2026, 11, 25, 8, 30);
   auto addAi = [&](const std::string &label, const std::string &content,
                    const bool missing, const uint delay, const int direction)
   {
      qsmc_ce::set_read_delay_ms(delay);
      if(missing) { qsmc_ce::files().erase(InpAIFile); }
      else        { qsmc_ce::set_file(InpAIFile, content); }
      SZoneFacts f; CE_InitFacts(f);
      f.direction = 1;
      f.session = CE_SESSION_LONDON;
      f.spread_points = 20.0;
      f.rr_at_fill = 2.0;
      f.atr_percentile = 50.0;
      f.kind = CE_KIND_OB_FVG;
      f.state = CE_STATE_VALIDATED;
      f.age_hours = 1.0;
      f.zone_atr_ratio = 1.0;
      f.h1_bias = 1; f.h4_bias = 1; f.htf_alignment = 1.0;
      f.confirmation_close = true;
      f.mode = CE_MODE_RETEST;
      f.retest_percent = 0.5;
      CE_LoadAIOpinion(ai_now, f);
      SScoreResult r; CE_InitScore(r);
      CE_ScoreComponents(f, r);
      RAi a;
      a.label = label;
      a.used = f.ai_used;
      a.load_why = f.ai_why;
      a.score_why = r.ai_why;
      a.confidence = f.ai_confidence;
      a.ai_pts = r.ai_pts;
      a.available_max = r.available_max;
      ai_cases.push_back(a);
      return r;
   };
   InpUseAIAgent = false;
   RAi disabled;
   {
      SZoneFacts f; CE_InitFacts(f); f.direction = 1; f.session = CE_SESSION_LONDON;
      f.spread_points = 20.0; f.rr_at_fill = 2.0; f.atr_percentile = 50.0;
      CE_LoadAIOpinion(ai_now, f);
      SScoreResult r; CE_InitScore(r); CE_ScoreComponents(f, r);
      disabled.label = "disabled"; disabled.used = f.ai_used; disabled.load_why = f.ai_why;
      disabled.score_why = r.ai_why; disabled.confidence = f.ai_confidence;
      disabled.ai_pts = r.ai_pts; disabled.available_max = r.available_max;
      ai_cases.push_back(disabled);
   }
   InpUseAIAgent = true;
   SScoreResult valid_score = addAi("valid", aiJson(1, 0.72, ai_now), false, 0, 1);
   addAi("missing", "", true, 0, 1);
   addAi("timeout", aiJson(1, 0.72, ai_now), false, 400, 1);
   addAi("malformed", "not-json", false, 0, 1);
   addAi("stale", aiJson(1, 0.72, ai_now - 3600), false, 0, 1);
   addAi("direction_mismatch", aiJson(-1, 0.90, ai_now), false, 0, -1);
   qsmc_ce::set_read_delay_ms(0);
   qsmc_ce::files().erase(InpAIFile);
   InpUseAIAgent = false;

   SAccountState kill; CE_InitAccount(kill);
   kill.master_enable = true; kill.dry_run = true; kill.allow_live = false;
   kill.allow_real = false; kill.kill_switch = true; kill.real_account = false;
   kill.equity = 10000.0; kill.day_start_equity = 10000.0;
   kill.now_utc = ai_now; kill.max_concurrent = 1; kill.max_trades = 3;
   SZoneFacts kill_f; CE_InitFacts(kill_f);
   kill_f.direction = 1; kill_f.session = CE_SESSION_LONDON; kill_f.spread_points = 20.0;
   kill_f.rr_at_fill = 2.0; kill_f.atr_percentile = 50.0;
   kill_f.ai_used = true; kill_f.ai_direction = 1; kill_f.ai_confidence = 1.0;
   kill_f.ai_why = "AI_OK";
   SScoreResult kill_r; CE_InitScore(kill_r);
   CE_ScoreComponents(kill_f, kill_r);
   CE_ApplyDecision(kill_f, kill, kill_r);
   bool ai_gate_ok = (kill_r.decision == "NEAR_MISS" && kill_r.reject_code == "KILL_SWITCH");

   std::vector<REval> evals;
   SAccountState acc; makeGoodAccount(acc, winter_day);
   auto addEval = [&](const std::string &label, const std::string &setup,
                      const std::string &format, SZoneRecord &z,
                      const datetime utc, const int scenario, const int mode)
   {
      z.last_seen_utc = utc;
      SZoneFacts f; replayFacts(f, z, utc, scenario, mode);
      acc.now_utc = utc;
      acc.last_entry_utc = 0;
      acc.cooldown_minutes = 0;
      acc.positions = 0;
      acc.trades_today = 0;
      SScoreResult r; CE_InitScore(r);
      CE_EvaluateZone(f, acc, r);
      g_reg.ZR_MarkEvaluated(z.id, (double)r.total, r.tier, r.decision, r.reject_code, utc);
      CE_UpdatePanel(z, r);
      REval e;
      e.label = label; e.setup = setup; e.object_format = format; e.utc = utc;
      e.dza_hour = CE_UtcToAlgeriaHour(utc);
      e.session = CE_SessionName(r.session);
      e.zone = z.id; e.state = CE_StateText(z.state);
      e.dir = CE_DirectionText(z.direction); e.kind = CE_KindText(z.kind);
      e.score = r.total; e.tier = r.tier_text; e.decision = r.decision;
      e.reject = r.reject_code; e.mode = r.entry_mode; e.plan_ready = r.plan_ready;
      e.risk_scale = r.risk_scale; e.htf_penalty = r.htf_penalty; e.lots = r.lots;
      e.log = CE_FormatLogLine(z, r, utc);
      e.csv = CE_FormatCsvRow(z, r, utc);
      evals.push_back(e);
   };

   addEval("S1 Asia birth", "S1", "QSVP_ZN_S0", z1, s1_birth, 1, CE_MODE_REVERSAL);
   addEval("S1 UTC day boundary", "S1", "QSVP_ZN_S0", z1, utcOf(2026, 11, 25, 0, 0), 1, CE_MODE_REVERSAL);
   addEval("S1 London second reaction", "S1", "QSVP_ZN_S0", z1, utcOf(2026, 11, 25, 8, 30), 1, CE_MODE_REVERSAL);
   addEval("S1 off-peak refusal", "S1", "QSVP_ZN_S0", z1, utcOf(2026, 11, 25, 12, 30), 1, CE_MODE_REVERSAL);
   addEval("S1 New York retest", "S1", "QSVP_ZN_S0", z1, utcOf(2026, 11, 25, 15, 30), 1, CE_MODE_REVERSAL);
   addEval("S2 NY birth no retest", "S2", "QSVP_ZN_B0", z2, s2_birth, 2, CE_MODE_RETEST);
   addEval("S2 next-day Asia boundary", "S2", "Z|BUY|<epoch>", z2, utcOf(2026, 11, 26, 0, 0), 2, CE_MODE_MOMENTUM);
   addEval("S2 next-day London no retest", "S2", "QSVP_ZN_B0", z2, utcOf(2026, 11, 26, 8, 30), 2, CE_MODE_RETEST);
   addEval("S2 next-day New York no retest", "S2", "QSVP_ZN_B0", z2, utcOf(2026, 11, 26, 15, 30), 2, CE_MODE_RETEST);

   CE_RenderPanel(evals.back().utc);
   string snap = "";
   CE_SaveRegistrySnapshot(g_reg, snap);
   CZoneRegistry reload; reload.ZR_Init();
   int loaded = CE_LoadRegistrySnapshot(reload, snap);

   bool parser_ok = p1 && p2 && parser_cases.size() == 5;
   for(size_t i = 0; i < parser_cases.size(); i++) { parser_ok = parser_ok && parser_cases[i].ok; }
   bool time_ok = true;
   for(size_t i = 0; i < time_checks.size(); i++)
   {
      time_ok = time_ok && time_checks[i].expected_eu == time_checks[i].actual_eu
                        && time_checks[i].expected_us == time_checks[i].actual_us;
   }
   bool transition_ok = true;
   for(size_t i = 0; i < transitions.size(); i++) { transition_ok = transition_ok && transitions[i].expected == transitions[i].actual; }
   bool z1_alive = (g_reg.ZR_Find(z1.id) >= 0);
   bool z2_alive = (g_reg.ZR_Find(z2.id) >= 0);
   bool mitigated_ok = (z1.state == CE_STATE_TESTED_MITIGATED);
   bool orders_disarmed = (sim::S.sendCount == 0 && InpDryRun && !InpAllowLiveOrders && !InpAllowRealTrading);
   bool status = parser_ok && time_ok && transition_ok && tr1 && tr2 && mitigated_ok
                 && z1_alive && z2_alive && g_reg.ZR_Count() == 2 && loaded == 2
                 && ai_gate_ok && orders_disarmed && failures == 0;

   std::vector<std::string> parser_json, transition_json, time_json, ai_json, eval_json;
   for(size_t i = 0; i < parser_cases.size(); i++)    { parser_json.push_back(parserObj(parser_cases[i])); }
   for(size_t i = 0; i < transitions.size(); i++)     { transition_json.push_back(transitionObj(transitions[i])); }
   for(size_t i = 0; i < time_checks.size(); i++)     { time_json.push_back(timeObj(time_checks[i])); }
   for(size_t i = 0; i < ai_cases.size(); i++)        { ai_json.push_back(aiObj(ai_cases[i])); }
   for(size_t i = 0; i < evals.size(); i++)           { eval_json.push_back(evalObj(evals[i])); }

   std::ostringstream os; bool first = true;
   jfs(os, first, "status", status ? "PASS" : "FAIL");
   jfs(os, first, "engine", "MQL5/Experts/QSMC_ConfirmationEngine.mq5");
   jfs(os, first, "scope", "deterministic source-derived replay of two 2026-11-25 setups");
   jfs(os, first, "not", "MetaEditor F7, Strategy Tester, broker ticks, live MT5 demo");
   jfi(os, first, "evaluations", (long long)evals.size());
   jfi(os, first, "parser_cases", (long long)parser_cases.size());
   jfi(os, first, "time_checks", (long long)time_checks.size());
   jfi(os, first, "ai_cases", (long long)ai_cases.size());
   jfi(os, first, "registry_count", (long long)g_reg.ZR_Count());
   jfi(os, first, "registry_reloaded", (long long)loaded);
   jfi(os, first, "orders_sent", (long long)sim::S.sendCount);
   jfb(os, first, "dry_run", InpDryRun);
   jfb(os, first, "live_orders", InpAllowLiveOrders);
   jfb(os, first, "real_allowed", InpAllowRealTrading);
   jfb(os, first, "mitigated_is_second_reaction_state", mitigated_ok);
   jfb(os, first, "ai_kill_switch_still_blocks", ai_gate_ok);
   jfs(os, first, "ai_valid_score_why", valid_score.ai_why);
   jfd(os, first, "ai_valid_points", valid_score.ai_pts);
   jfd(os, first, "ai_max_points", valid_score.ai_max);
   jfd(os, first, "ai_available_max", valid_score.available_max);
   jfs(os, first, "s1_server_birth_iso", isoUtc(s1_server));
   jfs(os, first, "s1_utc_birth_iso", isoUtc(s1_birth));
   jfs(os, first, "s2_server_birth_iso", isoUtc(s2_server));
   jfs(os, first, "s2_utc_birth_iso", isoUtc(s2_birth));
   jfs(os, first, "csv_header", CE_CsvHeader());
   jfs(os, first, "panel", sim::S.lastComment);
   jfs(os, first, "registry_snapshot", snap);
   jf(os, first, "parser", jarr(parser_json));
   jf(os, first, "state_transitions", jarr(transition_json));
   jf(os, first, "time", jarr(time_json));
   jf(os, first, "ai", jarr(ai_json));
   jf(os, first, "rows", jarr(eval_json));
   std::cout << "{" << os.str() << "}\n";
   return status ? 0 : 1;
}

// --------------------------------------------------------------------------
// Three-month deterministic synthetic surrogate. No broker ticks, no calendar,
// no spread/latency model, no Strategy Tester and no live order is involved.
// The score/decision/plan/risk/time functions are the real compiled CE layer.
// --------------------------------------------------------------------------
struct LCG
{
   unsigned long long state;
   LCG(const unsigned long long seed) : state(seed) {}
   unsigned long long next()
   {
      state = state * 6364136223846793005ULL + 1442695040888963407ULL;
      return state;
   }
   double unit()
   {
      return (double)(next() >> 11) / 9007199254740992.0;
   }
};

struct BSetup
{
   int day;
   int index;
   datetime utc;
   int dir;
   double lo;
   double hi;
   double atr;
   double spread;
   double mid;
   bool aligned;
   bool liquidity;
   bool structure;
   bool volume;
   int kind;
   int state;
   int touches;
   int session;
};
struct BParams
{
   std::string label;
   int tier_a;
   int tier_b;
   int min_htf;
   double b_scale;
   double counter_scale;
   double risk;
   double max_spread;
   int mode;
};
struct BMetrics
{
   int evaluations;
   int enter_dry_run;
   int near_miss;
   int shadow_fills;
   int wins;
   int losses;
   int scratch;
   double sum_r;
   double max_dd_r;
   double score_sum;
   double risk_scale_sum;
   double lots_sum;
   std::map<std::string, int> rejects;
};

static std::string paramsObj(const BParams &p)
{
   std::ostringstream os; bool first = true;
   jfs(os, first, "label", p.label);
   jfi(os, first, "tier_a", (long long)p.tier_a);
   jfi(os, first, "tier_b", (long long)p.tier_b);
   jfi(os, first, "min_htf", (long long)p.min_htf);
   jfd(os, first, "b_risk_scale", p.b_scale);
   jfd(os, first, "counter_risk_scale", p.counter_scale);
   jfd(os, first, "risk_percent", p.risk);
   jfd(os, first, "max_spread_points", p.max_spread);
   jfs(os, first, "entry_mode", CE_EntryModeName(p.mode));
   return "{" + os.str() + "}";
}
static std::string metricsObj(const BMetrics &m)
{
   std::ostringstream os; bool first = true;
   jfi(os, first, "evaluations", (long long)m.evaluations);
   jfi(os, first, "enter_dry_run", (long long)m.enter_dry_run);
   jfi(os, first, "near_miss", (long long)m.near_miss);
   jfi(os, first, "shadow_fills", (long long)m.shadow_fills);
   jfi(os, first, "wins", (long long)m.wins);
   jfi(os, first, "losses", (long long)m.losses);
   jfi(os, first, "scratch", (long long)m.scratch);
   jfd(os, first, "sum_r", m.sum_r);
   jfd(os, first, "max_drawdown_r", m.max_dd_r);
   jfd(os, first, "avg_score", m.evaluations ? m.score_sum / m.evaluations : 0.0);
   jfd(os, first, "avg_risk_scale", m.evaluations ? m.risk_scale_sum / m.evaluations : 0.0);
   jfd(os, first, "avg_lots", m.evaluations ? m.lots_sum / m.evaluations : 0.0);
   std::ostringstream rej; bool rf = true;
   for(std::map<std::string, int>::const_iterator it = m.rejects.begin(); it != m.rejects.end(); ++it)
   {
      jfi(rej, rf, it->first, (long long)it->second);
   }
   jf(os, first, "rejects", "{" + rej.str() + "}");
   return "{" + os.str() + "}";
}

static void backtestFacts(SZoneFacts &f, const BSetup &s, const BParams &p)
{
   CE_InitFacts(f);
   f.direction = s.dir;
   f.kind = s.kind;
   f.state = s.state;
   f.touches = s.touches;
   f.lo = s.lo;
   f.hi = s.hi;
   f.born_utc = s.utc - 3600;
   f.now_utc = s.utc;
   f.age_hours = 1.0;
   f.atr_m1 = s.atr;
   f.zone_atr_ratio = (s.hi - s.lo) / s.atr;
   f.atr_percentile = 50.0;
   f.spread_price = s.spread;
   f.spread_points = s.spread / 0.01;
   f.spread_atr_pct = s.spread / s.atr * 100.0;
   f.bid = s.mid - s.spread / 2.0;
   f.ask = s.mid + s.spread / 2.0;
   f.current_price = (s.dir > 0 ? f.ask : f.bid);
   f.point = 0.01;
   f.tick_value = 1.0;
   f.equity = 10000.0;
   f.stops_level = 0;
   f.freeze_level = 0;
   f.min_stop_points = 20;
   f.session = s.session;
   f.session_entry_allowed = CE_SessionEntryAllowed(s.session, InpAllowAsiaEntries, InpAllowOffPeakEntries);
   f.h4_bias = (s.aligned ? s.dir : -s.dir);
   f.h1_bias = s.dir;
   f.htf_alignment = CE_HtfAlignment(f.h1_bias, f.h4_bias, f.direction);
   f.asia_sweep = s.liquidity;
   f.london_sweep = s.liquidity;
   f.bsl_ssl = s.liquidity;
   f.eqh_eql = false;
   f.sweep_before_reaction = s.liquidity;
   f.m1_choch = true;
   f.m5_bos = s.structure;
   f.confirmation_close = true;
   f.second_reaction = true;
   f.sweep = true;
   f.closed_beyond_zone = true;
   f.micro_bos = true;
   f.first_pullback = true;
   f.poc_reaction = s.volume;
   f.vah_val_reaction = s.volume;
   f.volume_expansion = s.volume;
   f.mode = p.mode;
   f.retest_percent = 0.50;
   f.max_chase_atr = 1.50;
   f.momentum_close = s.mid + (s.dir > 0 ? s.atr : -s.atr);
   f.pullback_price = s.mid;
   f.second_reaction_price = s.mid;
   f.chase_distance = 0.50;
   f.rr_at_fill = 2.0;
   f.room_to_liquidity = s.atr * 20.0;
   f.nearest_liquidity = (s.dir > 0 ? s.mid + s.atr * 20.0 : s.mid - s.atr * 20.0);
   f.invalidation = (s.dir > 0 ? s.lo - s.atr : s.hi + s.atr);
   f.ai_used = false;
   f.ai_why = "AI_DISABLED";
}

static bool shadowOutcome(const std::vector<double> &mid, const BSetup &s,
                          const SScoreResult &r, double &pnl)
{
   pnl = 0.0;
   if(!r.plan_ready || r.risk <= 0.0) { return false; }
   int fill = -1;
   int fill_end = s.index + 60;
   if(fill_end >= (int)mid.size()) { fill_end = (int)mid.size() - 1; }
   for(int k = s.index + 1; k <= fill_end; k++)
   {
      double p = mid[k];
      bool stopped = (s.dir > 0 ? p <= r.sl : p >= r.sl);
      bool touched = (s.dir > 0 ? p <= r.entry_price + s.spread / 2.0 && p >= r.sl
                                : p >= r.entry_price - s.spread / 2.0 && p <= r.sl);
      if(stopped) { return false; }
      if(touched) { fill = k; break; }
   }
   if(fill < 0) { return false; }
   int hold_end = fill + 240;
   if(hold_end >= (int)mid.size()) { hold_end = (int)mid.size() - 1; }
   for(int k = fill + 1; k <= hold_end; k++)
   {
      double p = mid[k];
      if(s.dir > 0 && p <= r.sl) { pnl = -1.0; return true; }
      if(s.dir < 0 && p >= r.sl) { pnl = -1.0; return true; }
      if(s.dir > 0 && p >= r.tp) { pnl = (r.tp - r.entry_price) / r.risk; return true; }
      if(s.dir < 0 && p <= r.tp) { pnl = (r.entry_price - r.tp) / r.risk; return true; }
   }
   double last = mid[hold_end];
   pnl = (s.dir > 0 ? last - r.entry_price : r.entry_price - last) / r.risk;
   if(pnl > 2.0) { pnl = 2.0; }
   if(pnl < -1.0) { pnl = -1.0; }
   return true;
}

static BMetrics evaluateSetups(const std::vector<double> &mid, const std::vector<BSetup> &setups,
                               const BParams &p, const int day_from, const int day_to)
{
   int old_a = InpTierA, old_b = InpTierB, old_min_htf = InpMinHtfPoints;
   double old_b_scale = InpTierBRiskScale, old_counter = InpHtfCounterRiskScale;
   double old_risk = InpRiskPercent, old_spread = InpMaxSpreadPoints;
   InpTierA = p.tier_a; InpTierB = p.tier_b; InpMinHtfPoints = p.min_htf;
   InpTierBRiskScale = p.b_scale; InpHtfCounterRiskScale = p.counter_scale;
   InpRiskPercent = p.risk; InpMaxSpreadPoints = p.max_spread;

   BMetrics m{};
   double equity_r = 0.0, peak_r = 0.0;
   for(size_t i = 0; i < setups.size(); i++)
   {
      const BSetup &s = setups[i];
      if(s.day < day_from || s.day >= day_to) { continue; }
      SZoneFacts f; backtestFacts(f, s, p);
      SAccountState a; CE_InitAccount(a);
      a.master_enable = true; a.dry_run = true; a.allow_live = false; a.allow_real = false;
      a.kill_switch = false; a.daily_lock = false; a.real_account = false;
      a.positions = 0; a.trades_today = 0; a.max_concurrent = 99; a.max_trades = 999;
      a.equity = 10000.0; a.day_start_equity = 10000.0; a.max_daily_loss_pct = 2.0;
      a.now_utc = s.utc; a.last_entry_utc = 0; a.cooldown_minutes = 0;
      SScoreResult r; CE_InitScore(r);
      CE_EvaluateZone(f, a, r);
      m.evaluations++;
      m.score_sum += (double)r.total;
      m.risk_scale_sum += r.risk_scale;
      m.lots_sum += r.lots;
      if(r.decision == "ENTER_DRY_RUN") { m.enter_dry_run++; }
      if(r.decision == "NEAR_MISS")    { m.near_miss++; }
      m.rejects[r.reject_code]++;
      double pnl = 0.0;
      if(r.decision == "ENTER_DRY_RUN" && shadowOutcome(mid, s, r, pnl))
      {
         m.shadow_fills++;
         if(pnl > 0.0001) { m.wins++; }
         else if(pnl < -0.0001) { m.losses++; }
         else { m.scratch++; }
         m.sum_r += pnl;
         equity_r += pnl;
         if(equity_r > peak_r) { peak_r = equity_r; }
         double dd = peak_r - equity_r;
         if(dd > m.max_dd_r) { m.max_dd_r = dd; }
      }
   }
   InpTierA = old_a; InpTierB = old_b; InpMinHtfPoints = old_min_htf;
   InpTierBRiskScale = old_b_scale; InpHtfCounterRiskScale = old_counter;
   InpRiskPercent = old_risk; InpMaxSpreadPoints = old_spread;
   return m;
}

static int runBacktest()
{
   setReplayDefaults();
   datetime start = utcOf(2026, 8, 25, 0, 0);
   datetime split = utcOf(2026, 10, 25, 0, 0);
   datetime end = utcOf(2026, 11, 25, 0, 0);
   int days = (int)((end - start) / 86400);
   int in_window_bars = days * 1440;
   int total_bars = in_window_bars + 300;
   setupMarket(start + 7200);

   LCG rng(20261125ULL);
   std::vector<double> mid;
   mid.reserve((size_t)total_bars);
   double price = 3550.0;
   for(int i = 0; i < total_bars; i++)
   {
      double wave = 0.03 * std::sin((double)i / 720.0);
      price += (rng.unit() - 0.5) * 0.90 + wave;
      if(price < 3350.0) { price = 3350.0; }
      if(price > 3700.0) { price = 3700.0; }
      mid.push_back(price);
   }

   std::vector<BSetup> setups;
   int roundtrip_checks = 0, roundtrip_mismatches = 0;
   for(int day = 0; day < days; day++)
   {
      for(int slot = 0; slot < 2; slot++)
      {
         int minute = (slot == 0 ? 8 * 60 + 30 : 15 * 60 + 30);
         int index = day * 1440 + minute;
         datetime utc = start + (long)index * 60;
         datetime server = CE_UtcToBrokerServer(utc, 120, 180, true);
         datetime back = CE_ServerToUtc(server, 120, 180, true);
         roundtrip_checks++;
         if(back != utc) { roundtrip_mismatches++; }
         BSetup s{};
         s.day = day; s.index = index; s.utc = utc; s.mid = mid[(size_t)index];
         s.dir = (rng.unit() < 0.5 ? 1 : -1);
         s.atr = 1.60 + rng.unit() * 0.80;
         double half = s.atr * (0.80 + rng.unit() * 0.40);
         s.lo = s.mid - half; s.hi = s.mid + half;
         s.spread = 0.18 + rng.unit() * 0.24;
         s.aligned = rng.unit() < 0.68;
         s.liquidity = rng.unit() < 0.55;
         s.structure = rng.unit() < 0.65;
         s.volume = rng.unit() < 0.60;
         s.kind = (rng.unit() < 0.45 ? CE_KIND_OB_FVG : CE_KIND_OB);
         s.state = (rng.unit() < 0.35 ? CE_STATE_TESTED_MITIGATED : CE_STATE_VALIDATED);
         s.touches = (s.state == CE_STATE_TESTED_MITIGATED ? 1 : 0);
         s.session = CE_SessionOfUtc(utc);
         setups.push_back(s);
      }
   }

   std::vector<BParams> params;
   BParams p;
   p.label = "baseline"; p.tier_a = 75; p.tier_b = 55; p.min_htf = 3;
   p.b_scale = 0.50; p.counter_scale = 0.60; p.risk = 0.25; p.max_spread = 60.0; p.mode = CE_MODE_RETEST;
   params.push_back(p);
   p.label = "strict-A"; p.tier_a = 82; p.tier_b = 65; p.min_htf = 5; params.push_back(p);
   p.label = "loose-A"; p.tier_a = 68; p.tier_b = 50; p.min_htf = 2; params.push_back(p);
   p.label = "tight-spread"; p.tier_a = 75; p.tier_b = 55; p.min_htf = 3; p.max_spread = 20.0; params.push_back(p);
   p.label = "momentum-mode"; p.max_spread = 60.0; p.mode = CE_MODE_MOMENTUM; params.push_back(p);
   p.label = "reversal-mode"; p.mode = CE_MODE_REVERSAL; params.push_back(p);

   BMetrics baseline = evaluateSetups(mid, setups, params[0], 0, days);
   BMetrics in_sample = evaluateSetups(mid, setups, params[0], 0, 61);
   BMetrics holdout = evaluateSetups(mid, setups, params[0], 61, days);
   std::vector<std::string> sensitivity_json;
   std::vector<std::string> param_json;
   std::vector<std::string> metric_json;
   for(size_t i = 0; i < params.size(); i++)
   {
      BMetrics m = (i == 0 ? baseline : evaluateSetups(mid, setups, params[i], 0, days));
      std::ostringstream row; bool first = true;
      jfs(row, first, "label", params[i].label);
      jf(row, first, "params", paramsObj(params[i]));
      jf(row, first, "metrics", metricsObj(m));
      sensitivity_json.push_back("{" + row.str() + "}");
      param_json.push_back(paramsObj(params[i]));
   }
   bool disarmed = (sim::S.sendCount == 0 && InpDryRun && !InpAllowLiveOrders && !InpAllowRealTrading);
   bool status = disarmed && days == 92 && in_window_bars == 132480
                 && setups.size() == 184 && baseline.evaluations == 184
                 && in_sample.evaluations == 122 && holdout.evaluations == 62
                 && failures == 0;

   std::ostringstream os; bool first = true;
   jfs(os, first, "status", status ? "PASS" : "FAIL");
   jfs(os, first, "engine", "MQL5/Experts/QSMC_ConfirmationEngine.mq5");
   jfs(os, first, "scope", "deterministic 3-month synthetic M1 surrogate");
   jfs(os, first, "not", "MetaEditor F7, Strategy Tester, broker ticks, live MT5 demo, evidence of edge");
   jfs(os, first, "start_utc_iso", isoUtc(start));
   jfs(os, first, "split_utc_iso", isoUtc(split));
   jfs(os, first, "end_utc_iso", isoUtc(end));
   jfi(os, first, "start_utc", (long long)start);
   jfi(os, first, "split_utc", (long long)split);
   jfi(os, first, "end_utc", (long long)end);
   jfi(os, first, "days", (long long)days);
   jfi(os, first, "m1_bars_in_window", (long long)in_window_bars);
   jfi(os, first, "m1_bars_with_synthetic_tail", (long long)total_bars);
   jfi(os, first, "setups", (long long)setups.size());
   jfi(os, first, "server_roundtrip_checks", (long long)roundtrip_checks);
   jfi(os, first, "server_roundtrip_mismatches", (long long)roundtrip_mismatches);
   jfi(os, first, "in_sample_days", (long long)61);
   jfi(os, first, "holdout_days", (long long)31);
   jfi(os, first, "orders_sent", (long long)sim::S.sendCount);
   jfb(os, first, "dry_run", InpDryRun);
   jfb(os, first, "live_orders", InpAllowLiveOrders);
   jfb(os, first, "real_allowed", InpAllowRealTrading);
   jf(os, first, "baseline", metricsObj(baseline));
   jf(os, first, "walk_forward", "{\"in_sample\":" + metricsObj(in_sample)
      + ",\"holdout\":" + metricsObj(holdout) + "}");
   jf(os, first, "parameter_sets", jarr(param_json));
   jf(os, first, "sensitivity", jarr(sensitivity_json));
   jf(os, first, "warnings", jarr(std::vector<std::string>{
      jstr("NOT MetaEditor F7"),
      jstr("NOT Strategy Tester"),
      jstr("NOT broker tick data"),
      jstr("NOT a live MT5 demo run"),
      jstr("synthetic R results are a deterministic shadow simulation, not evidence of profitability")
   }));
   std::cout << "{" << os.str() << "}\n";
   return status ? 0 : 1;
}
