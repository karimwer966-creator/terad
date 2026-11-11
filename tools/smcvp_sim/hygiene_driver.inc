// hygiene_driver.inc - executes the chart-hygiene modules and the REAL
// AlertDispatcherDrawPrimary() text of nadir2.mq5 against the chart simulator.
// Included after the transpiled unit by tools/test_qsmc_chart_hygiene.py.
#include <cstdio>
#include <cstring>

static void hygieneReset()
{
   chartsim::resetAll();
   QSR_Reset();
   for(int i = 0; i < QSMC_PRIMARY_MARK_LIMIT; i++) g_primary_mark_names[i] = "";
   g_primary_mark_pos = 0;
}

static SAlertCandidate hygieneCandidate(const char kind, const int closed, const datetime bar_time)
{
   SAlertCandidate a{};
   a.valid = true; a.scenario_candidate = true; a.alert_eligible = true;
   a.closed_index = closed; a.bar_time = bar_time;
   a.distance_atr = 0.5; a.opposing_room_atr = 3.0;
   a.needs = "displacement"; a.detail = "detail"; a.event_id = "evt";
   switch(kind)
   {
      case 'A': a.source = 2; a.direction = 1;  a.level = 3; a.score = 72; a.zone_id = "Z1"; a.zone_lo = 4058.44; a.zone_hi = 4060.12; break;
      case 'a': a.source = 2; a.direction = 1;  a.level = 4; a.score = 81; a.zone_id = "Z1"; a.zone_lo = 4058.44; a.zone_hi = 4060.12; break;
      case 'B': a.source = 2; a.direction = -1; a.level = 3; a.score = 66; a.zone_id = "Z2"; a.zone_lo = 4071.10; a.zone_hi = 4072.90; break;
      case 'C': a.source = 3; a.direction = 1;  a.level = 5; a.score = 90; a.zone_id = "Z3"; a.zone_lo = 4040.00; a.zone_hi = 4041.50; break;
      case 'S': a.source = 2; a.direction = -1; a.level = 3; a.score = 60; a.zone_id = "Z1"; a.zone_lo = 4058.44; a.zone_hi = 4060.12; break;
      default:  a.valid = false; break;
   }
   a.mark_price = (a.zone_lo + a.zone_hi) * 0.5;
   a.invalidation = a.direction > 0 ? a.zone_lo - 1.0 : a.zone_hi + 1.0;
   return a;
}

static int hygieneReplay(const std::string &schedule, const bool verbose, const bool report = true)
{
   hygieneReset();
   const int n = (int)schedule.size() + 4;
   const datetime t0 = sim::makeTime(2026, 11, 11, 2, 0, 0);
   ArrayResize(g_buf_t, n); ArrayResize(g_buf_l, n); ArrayResize(g_buf_h, n); ArrayResize(g_atr_buf, n);
   for(int i = 0; i < n; i++)
   {
      g_buf_t.v[(size_t)i] = t0 + (datetime)i * 900;
      g_buf_l.v[(size_t)i] = 4050.0 + (double)(i % 7);
      g_buf_h.v[(size_t)i] = 4056.0 + (double)(i % 7);
      g_atr_buf.v[(size_t)i] = 4.0;
   }
   chartsim::addUserObject("My trend line", OBJ_TREND, t0, 4050.0);
   chartsim::addUserObject("QSMC_user_note_not_ours", OBJ_TEXT, t0, 4051.0);
   long peak = 0;
   int publications = 0;
   for(size_t k = 0; k < schedule.size(); k++)
   {
      const int closed = (int)k + 2;
      sim::S.now = g_buf_t.v[(size_t)closed] + 900;
      SAlertCandidate a = hygieneCandidate(schedule[k], closed, g_buf_t.v[(size_t)closed]);
      if(a.valid) { AlertDispatcherDrawPrimary(a); publications++; }
      long marks = chartsim::countPrefix("QSMC_PRIMARY_");
      if(marks > peak) peak = marks;
      if(verbose)
         printf("bar %2d pub=%c objects=%ld\n", closed, schedule[k], marks);
   }
   if(!report) return 0;
   long arrows = chartsim::countType("QSMC_PRIMARY_", OBJ_ARROW);
   long texts = chartsim::countType("QSMC_PRIMARY_", OBJ_TEXT);
   std::string text_of_first;
   for(const auto &kv : chartsim::C.objects)
      if(kv.first.compare(0, 13, "QSMC_PRIMARY_") == 0 && kv.second.type == OBJ_TEXT && text_of_first.empty())
      {
         auto it = kv.second.strs.find((int)OBJPROP_TEXT);
         if(it != kv.second.strs.end()) text_of_first = it->second;
      }
   printf("RESULT publications=%d arrows=%ld texts=%ld peak=%ld created=%ld deleted=%ld "
          "user_trend=%d user_note=%d registry_created=%d registry_updated=%d registry_live=%d registry_expired=%d\n",
          publications, arrows, texts, peak, chartsim::C.created, chartsim::C.deleted,
          ObjectFind(0, "My trend line") >= 0 ? 1 : 0, ObjectFind(0, "QSMC_user_note_not_ours") >= 0 ? 1 : 0,
          g_qsr_created, g_qsr_updated, QSR_CountLive(), QSR_CountState(QSR_STATE_EXPIRED));
   printf("FIRSTTEXT %s\n", text_of_first.c_str());
   for(const auto &kv : chartsim::C.objects)
      if(kv.first.compare(0, 13, "QSMC_PRIMARY_") == 0 && kv.second.type == OBJ_ARROW)
         printf("MARK %s at=%ld\n", kv.first.c_str(), (long)kv.second.t[0]);
   return 0;
}

// The chart after a replay, as JSON for tools/smcvp_chart_svg.py: the bars the
// replay ran over and every QSMC_PRIMARY_* object the real function left behind.
static std::string hygieneEscape(const std::string &text)
{
   std::string o;
   for(char ch : text) { if(ch == '"' || ch == '\\') { o += '\\'; o += ch; } else if((unsigned char)ch < 0x20) o += ' '; else o += ch; }
   return o;
}

static void hygienePicture(const std::string &title)
{
   const int n = (int)g_buf_t.v.size();
   std::string j = "{\n  \"title\": \"" + hygieneEscape(title) + "\",\n  \"bar\": " + std::to_string(n - 1) + ",\n  \"candles\": [";
   char b[640];
   for(int i = 0; i < n; i++)
   {
      const double lo = g_buf_l.v[(size_t)i], hi = g_buf_h.v[(size_t)i];
      const bool up = (i % 2 == 0);
      snprintf(b, sizeof b, "%s[%lld,%.2f,%.2f,%.2f,%.2f]", i == 0 ? "" : ",", (long long)g_buf_t.v[(size_t)i], up ? lo + 1.5 : hi - 1.5, hi, lo, up ? hi - 1.5 : lo + 1.5);
      j += b;
   }
   j += "],\n  \"objects\": [\n";
   bool first = true;
   for(const auto &kv : chartsim::C.objects)
   {
      const chartsim::Obj &o = kv.second;
      if(kv.first.compare(0, 13, "QSMC_PRIMARY_") != 0) continue;
      auto geti = [&](const int prop, const long dflt) { const auto it = o.ints.find(prop); return it == o.ints.end() ? dflt : it->second; };
      auto gets = [&](const int prop) { const auto it = o.strs.find(prop); return it == o.strs.end() ? std::string() : it->second; };
      snprintf(b, sizeof b, "    %s{\"name\":\"%s\",\"type\":%d,\"t1\":%lld,\"p1\":%.2f,\"t2\":%lld,\"p2\":%.2f,\"color\":%ld,\"style\":0,\"width\":1,\"fill\":0,"
               "\"anchor\":%ld,\"size\":%ld,\"x\":0,\"y\":0,\"w\":0,\"h\":0,\"bg\":0,", first ? "" : ",", hygieneEscape(kv.first).c_str(), (int)o.type,
               (long long)o.t[0], o.p[0], (long long)o.t[1], o.p[1], geti((int)OBJPROP_COLOR, 0xC0C0C0), geti((int)OBJPROP_ANCHOR, 0), geti((int)OBJPROP_FONTSIZE, 8));
      j += b;
      j += "\"text\":\"" + hygieneEscape(gets((int)OBJPROP_TEXT)) + "\",\"tip\":\"\"}\n";
      first = false;
   }
   j += "  ]\n}\n";
   printf("%s", j.c_str());
}

int main(int argc, char **argv)
{
   const std::string cmd = argc > 1 ? argv[1] : "selftest";
   int i = 2;
   for(; i + 1 < argc && std::strcmp(argv[i], "--set") == 0; i += 2)
   {
      std::string kv = argv[i + 1];
      size_t eq = kv.find('=');
      if(eq == std::string::npos || !QATS_SetInput(kv.substr(0, eq), kv.substr(eq + 1)))
      {
         fprintf(stderr, "unknown input: %s\n", kv.c_str());
         return 2;
      }
   }
   if(cmd == "selftest")
   {
      string where;
      bool a = QSR_SelfTest(where);
      printf("%s QSR_SelfTest %s\n", a ? "PASS" : "FAIL", where.c_str());
      string where2;
      bool b = QCL_SelfTest(where2);
      printf("%s QCL_SelfTest %s\n", b ? "PASS" : "FAIL", where2.c_str());
      printf("fmt_errors=%zu api_errors=%zu\n", sim::S.fmtErrors.size(), sim::S.apiErrors.size());
      return (a && b && sim::S.fmtErrors.empty() && sim::S.apiErrors.empty()) ? 0 : 1;
   }
   if(cmd == "layers")
   {
      for(; i < argc; i++)
         printf("%s=%s\n", argv[i], QCL_LayerName(QCL_LayerOfTail(argv[i])).c_str());
      return 0;
   }
   if(cmd == "allows")
   {
      for(; i < argc; i++)
         printf("%s=%d\n", argv[i], (!QCL_ProfileActive() || QCL_AllowsName(argv[i], PFX)) ? 1 : 0);
      return 0;
   }
   if(cmd == "keep")
   {
      printf("keep=%d idle=%d\n", QCL_PrimaryMarkKeep(QSMC_PRIMARY_MARK_LIMIT), QCL_EpisodeIdleSeconds(PeriodSeconds()));
      return 0;
   }
   if(cmd == "replay")
   {
      bool verbose = false;
      std::string schedule;
      for(; i < argc; i++)
      {
         if(std::strcmp(argv[i], "--verbose") == 0) verbose = true;
         else schedule = argv[i];
      }
      int rc = hygieneReplay(schedule, verbose);
      printf("fmt_errors=%zu api_errors=%zu\n", sim::S.fmtErrors.size(), sim::S.apiErrors.size());
      return (rc == 0 && sim::S.fmtErrors.empty() && sim::S.apiErrors.empty()) ? 0 : 1;
   }
   if(cmd == "picture")
   {
      // picture <schedule> <title>: run the schedule silently, print the chart as JSON
      if(i + 1 >= argc) { fprintf(stderr, "picture needs <schedule> <title>\n"); return 2; }
      const std::string schedule = argv[i], title = argv[i + 1];
      const int rc = hygieneReplay(schedule, false, false);
      hygienePicture(title);
      return (rc == 0 && sim::S.fmtErrors.empty() && sim::S.apiErrors.empty()) ? 0 : 1;
   }
   fprintf(stderr, "usage: selftest | layers <tail>... | allows <name>... | keep | replay [--verbose] <schedule> | picture <schedule> <title>\n");
   return 2;
}
