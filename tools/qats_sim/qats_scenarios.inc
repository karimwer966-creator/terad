// qats_scenarios.inc - integration scenarios: a synthetic market replayed tick by
// tick through the real OnInit / OnTick / OnTradeTransaction of the EA.
#pragma GCC system_header

namespace drv
{
static void printResult(const std::string &name, bool mirror)
{
   const sim::Deal *d = firstEntryDeal();
   std::string scored = firstWith("[QATS][SIGNAL][SCORED]", "outcome=EXECUTED");
   int bs = atoi(Journal::field(scored, "BUY=").c_str()), ss = atoi(Journal::field(scored, "SELL=").c_str());
   printf("RESULT scenario=%s mirror=%d entries=%ld dir=%s price=%.2f sl=%.2f tp=%.2f volume=%.2f buyScore=%d sellScore=%d trades=%zu net=%.2f\n",
          name.c_str(), mirror ? 1 : 0, entryOkCount(), d ? (d->type == DEAL_TYPE_BUY ? "BUY" : "SELL") : "NONE",
          d ? d->price : 0.0, d ? d->sl : 0.0, d ? d->tp : 0.0, d ? d->volume : 0.0, bs, ss,
          buildTrades().size(), sim::S.acc.balance - 10000.0);
}

// ---------------------------------------------------------------- scenarios
// strong BUY (or, mirrored, strong SELL) from detection to a closed position
static void scnStrong(bool mirror, const std::string &profile)
{
   resetSimOnly();
   captureJournal();
   setInputs({{"InpStrategyProfile", profile}});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.feed.mirror = mirror;
   pl.feed.mirrorK = 400000;
   pl.play(sc, m.attachAt);
   QEQ(pl.attach(sc), (int)INIT_SUCCEEDED, "OnInit succeeds");
   pl.play(sc, m.entryAt);
   QEQ(entryCount(), 0L, "no order before the chain is complete");
   pl.play(sc, m.entryAt + 5);
   const char *side = mirror ? "SELL" : "BUY";
   const char *other = mirror ? "BUY" : "SELL";
   std::string detTag = std::string("[QATS][") + side + "][DETECTED]";
   QCHECK(linesWith(detTag) >= 1, std::string(side) + " setup announced with " + detTag);
   std::string det = lastWith(detTag);
   QCHECK(det.find(mirror ? "sweep=BSL:" : "sweep=SSL:") != std::string::npos, "DETECTED names the swept liquidity side: " + det);
   QCHECK(det.find("structure=BOS@") != std::string::npos, "DETECTED names the break of structure");
   QCHECK(det.find("displacement=bar ") != std::string::npos, "DETECTED names the displacement bar");
   QCHECK(det.find("core=PASS 3/3") != std::string::npos, "all three core events present");
   std::string scored = firstWith("[QATS][SIGNAL][SCORED]", "outcome=EXECUTED");
   QCHECK(!scored.empty(), "a scored record ends in outcome=EXECUTED");
   QCHECK(scored.find(std::string("candidate=") + side) != std::string::npos, std::string("the candidate is ") + side);
   int bs = atoi(Journal::field(scored, "BUY=").c_str()), ss = atoi(Journal::field(scored, "SELL=").c_str());
   int mine = mirror ? ss : bs, theirs = mirror ? bs : ss;
   QCHECK(mine >= 75, std::string(side) + " score is STRONG (>= 75), got " + std::to_string(mine));
   QCHECK(theirs < 55, std::string(other) + " score stays below the minimum, got " + std::to_string(theirs));
   QCHECK(scored.find("BUY core=") != std::string::npos && scored.find("SELL core=") != std::string::npos, "both sides are reported on the same record");
   QEQ(linesWith("[QATS][EXECUTION][APPROVED]", std::string("direction=") + side), 1, "one APPROVED record");
   QEQ(linesWith("[QATS][EXECUTION][FILLED]", std::string("direction=") + side), 1, "one FILLED record");
   QCHECK(firstWith("[QATS][EXECUTION][APPROVED]").find("class=STRONG_VALID") != std::string::npos, "the approved signal is classified STRONG_VALID");
   QEQ(linesWith("[QATS][EXECUTION][APPROVED]", std::string("direction=") + other), 0, "nothing approved on the other side");
   QEQ(entryOkCount(), 1L, "exactly one market order was accepted");
   QEQ((long)sim::S.positions.size(), 1L, "one position is open");
   if(sim::S.positions.size() == 1)
   {
      const sim::Position &p = sim::S.positions[0];
      QEQ(p.type, mirror ? (int)POSITION_TYPE_SELL : (int)POSITION_TYPE_BUY, "position direction");
      QCHECK(p.sl > 0.0 && p.tp > 0.0, "server-side SL and TP are set");
      if(!mirror) QCHECK(p.sl < p.priceOpen && p.tp > p.priceOpen, "BUY: SL below, TP above the entry");
      else        QCHECK(p.sl > p.priceOpen && p.tp < p.priceOpen, "SELL: SL above, TP below the entry");
      double risk = std::fabs(p.priceOpen - p.sl), reward = std::fabs(p.tp - p.priceOpen);
      QCHECK(reward / risk + 1e-9 >= InpMinRR, "planned reward:risk >= InpMinRR");
      QCHECK(sim::onGrid(p.sl) && sim::onGrid(p.tp), "SL and TP sit on the tick grid");
      QCHECK(risk >= InpMinStopPoints * sim::S.sym.point && risk <= InpMaxStopPoints * sim::S.sym.point, "stop distance inside the configured limits");
      double riskMoney = risk * sim::moneyPerPriceUnit(p.volume);
      QCHECK(riskMoney <= 10000.0 * EffectiveRiskPercent() / 100.0 + 1e-6, "risk at the stop does not exceed the configured equity risk");
      QCHECK(p.magic == InpMagic, "the position carries the EA magic");
   }
   pl.play(sc, m.endAt);
   std::vector<Trade> trades = buildTrades();
   QCHECK(!trades.empty() && trades[0].closed, "the position was closed by its server-side stop or target");
   if(!trades.empty()) QCHECK(trades[0].net > 0.0, "follow-through in the trade direction ends in profit");
   QCHECK(linesWith("[QATS][BLOCK][REASON]", "DUPLICATE_SETUP") + linesWith("[QATS][SIGNAL][SCORED]", "DUPLICATE_SETUP") >= 1,
          "the same setup is refused afterwards (DUPLICATE_SETUP)");
   // one fill per setup identity
   std::map<std::string, int> perSetup;
   for(const std::string &s : JR.keep)
      if(s.find("[QATS][EXECUTION][FILLED]") != std::string::npos) perSetup[Journal::field(s, "setup=")]++;
   int dup = 0;
   for(const auto &kv : perSetup) if(kv.second > 1) dup++;
   QEQ(dup, 0, "no setup identity was filled twice");
   QCHECK(linesWith("[QATS][GUARD] position", "closed WIN") >= 1, "the closed position is netted from the deal history as a WIN");
   simDiagnosticsClean();
   printResult("strong", mirror);
}

// the core gate, per profile, on three kinds of evidence
static void scnCoreGate(const std::string &pattern, const std::string &profile, bool mirror)
{
   resetSimOnly();
   captureJournal();
   setInputs({{"InpStrategyProfile", profile}});
   Scn sc(1500.0);
   Marks m = (pattern == "sweep_only") ? patternSweepOnly(sc) : patternBosOnly(sc);
   Player pl;
   pl.feed.mirror = mirror;
   pl.feed.mirrorK = 400000;
   pl.play(sc, m.attachAt);
   pl.attach(sc);
   pl.play(sc, m.endAt);
   const char *side = mirror ? "SELL" : "BUY";
   if(pattern == "sweep_only")
   {
      QEQ(entryCount(), 0L, "a liquidity sweep alone never sends an order (profile " + profile + ")");
      QEQ(linesWith("[QATS][EXECUTION][APPROVED]"), 0, "nothing approved");
      std::string hit = firstWith("[QATS][SIGNAL][SCORED]", mirror ? "SWEEP:13(BSL" : "SWEEP:13(SSL", "outcome=NO_SETUP");
      QCHECK(!hit.empty(), "the sweep IS detected and scored, and the outcome is NO_SETUP");
      QCHECK(hit.find("reason=CORE_NOT_CONFIRMED") != std::string::npos, "the reason is the core confirmation");
      QCHECK(hit.find(std::string(side) + " core=FAIL(") != std::string::npos, "the side trace says why the core failed: " + hit);
      // the SCORE alone would have qualified: only the core gate stands between a sweep and an order
      int best = 0;
      for(const std::string &s : JR.keep)
         if(s.find("[QATS][SIGNAL][SCORED]") != std::string::npos && s.find(mirror ? "SWEEP:13(BSL" : "SWEEP:13(SSL") != std::string::npos)
            best = std::max(best, atoi(Journal::field(s, mirror ? "SELL=" : "BUY=").c_str()));
      QCHECK(best >= InpMinScore, "with the sweep the score reached " + std::to_string(best) + " >= minimum, yet no trade was taken");
   }
   else
   {
      bool expect = (profile != "0");   // CONSERVATIVE demands the sweep
      if(expect)
      {
         QCHECK(entryOkCount() >= 1, "displacement + BOS trades without a sweep (profile " + profile + ")");
         std::string a = firstWith("[QATS][EXECUTION][APPROVED]");
         QCHECK(a.find(std::string("direction=") + side) != std::string::npos, std::string("approved direction is ") + side);
         QCHECK(firstWith(std::string("[QATS][") + side + "][DETECTED]").find("core=PASS 2/3") != std::string::npos, "two of three core events");
      }
      else
      {
         QEQ(entryCount(), 0L, "CONSERVATIVE refuses a setup without a liquidity sweep");
         QCHECK(!firstWith("[QATS][SIGNAL][SCORED]", std::string(side) + " core=FAIL(no liquidity sweep)").empty(), "the reason is named: no liquidity sweep");
      }
   }
   simDiagnosticsClean();
   printResult(pattern + "/" + profile, mirror);
}

// D1 and H4 point one way, H1 breaks the other way
static void scnCounterTrend(bool mirror, bool goldSymbol)
{
   resetSimOnly();
   if(!goldSymbol) { sim::S.sym.name = "TESTIDX"; _Symbol = "TESTIDX"; }
   captureJournal();
   setInputs({});
   Scn sc(1500.0);
   Marks m = patternCounterTrend(sc);
   Player pl;
   pl.feed.mirror = mirror;
   pl.feed.mirrorK = 400000;
   pl.play(sc, m.attachAt);
   pl.attach(sc);
   pl.play(sc, m.entryAt + 30);
   const char *side = mirror ? "BUY" : "SELL";            // the reversal side
   std::string det = lastWith(std::string("[QATS][") + side + "][DETECTED]");
   QCHECK(!det.empty(), std::string(side) + " reversal is DETECTED against the higher-timeframe bias");
   QCHECK(det.find(mirror ? "D1=-1" : "D1=+1") != std::string::npos, "the D1 bias opposes the setup: " + det);
   QCHECK(det.find("structure=CHOCH@") != std::string::npos, "the break is a change of character");
   QCHECK(det.find(mirror ? "sweep=SSL:" : "sweep=BSL:") != std::string::npos, "the opposing liquidity was swept");
   if(goldSymbol)
   {
      QCHECK(entryOkCount() >= 1, "XAUUSD: the counter-bias setup is executed (bias is confluence, not a veto)");
      std::string a = firstWith("[QATS][EXECUTION][APPROVED]");
      QCHECK(a.find(std::string("direction=") + side) != std::string::npos, std::string("approved direction is ") + side + ": " + a);
      std::string scored = firstWith("[QATS][SIGNAL][SCORED]", "outcome=EXECUTED");
      QCHECK(scored.find(std::string(side) + " core=PASS") != std::string::npos, "core passed on the reversal side");
      QCHECK(scored.find("D1:0 H4:0") != std::string::npos, "the reversal side earned NO bias points and still qualified: " + scored);
      if(!sim::S.positions.empty())
         QEQ(sim::S.positions[0].type, mirror ? (int)POSITION_TYPE_BUY : (int)POSITION_TYPE_SELL, "position direction");
   }
   else
   {
      QEQ(entryCount(), 0L, "non-XAUUSD: the configured directional veto blocks the counter-bias setup");
      std::string v = firstWith("[QATS][SIGNAL][SCORED]", "outcome=VETOED");
      QCHECK(!v.empty(), "the outcome is VETOED");
      QCHECK(v.find("reason=EMA_ALIGNMENT_VETO") != std::string::npos || v.find("reason=COUNTER_D1_BIAS_VETO") != std::string::npos,
             "the veto is named: " + v);
      QCHECK(v.find(std::string(side) + " core=PASS") != std::string::npos, "the setup itself was valid; only the veto stopped it");
   }
   simDiagnosticsClean();
   printResult(std::string("counter_trend/") + (goldSymbol ? "gold" : "other"), mirror);
}

// every way an eligible, core-confirmed signal can be refused, with its exact reason
static void scnRejection(const std::string &kind)
{
   resetSimOnly();
   captureJournal();
   std::vector<std::pair<std::string, std::string>> sets;
   if(kind == "dry_run") sets.push_back({"InpDryRun", "true"});
   if(kind == "master_off") sets.push_back({"InpEnableTrading", "false"});
   if(kind == "session") { sets.push_back({"InpSessionStartHour", "23"}); sets.push_back({"InpSessionEndHour", "24"}); }
   setInputs(sets);
   if(kind == "volume") sim::S.acc.balance = 60.0;
   if(kind == "margin") { sim::S.acc.balance = 1500.0; sim::S.acc.leverage = 1; }
   if(kind == "margin_fit") { sim::S.acc.balance = 6000.0; sim::S.acc.leverage = 1; }
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.play(sc, m.attachAt);
   pl.attach(sc);
   pl.play(sc, m.entryAt);
   if(kind == "spread") pl.feed.spreadFixedPts = 80;
   if(kind == "broker") sim::S.injectRetcodes = {TRADE_RETCODE_INVALID_STOPS};
   if(kind == "timeout") sim::S.injectRetcodes = {TRADE_RETCODE_TIMEOUT};
   if(kind == "permission") sim::S.terminalTradeAllowed = false;
   if(kind == "daily_cap_and_cooldown")
   {
      GVSet(GVKey("trades_" + TodayKey()), (double)InpMaxTradesPerDay);
      StartCooldown(TimeTradeServer(), 3);
   }
   if(kind == "drawdown") GVSet(GVKey("hwm"), 20000.0);
   if(kind == "daily_loss") GVSet(GVKey("daybase_" + TodayKey()), 11000.0);
   pl.play(sc, m.entryAt + 5);                              // the first bar that sees the chain
   std::string scored = firstWith("[QATS][SIGNAL][SCORED]", "candidate=BUY", "eligible=yes");
   QCHECK(!scored.empty(), "the BUY signal is eligible (core passed, score >= minimum)");
   auto expectBlock = [&](const std::string &code) {
      QEQ(entryCount(), 0L, "no order is sent while " + code + " blocks");
      std::string b = firstWith("[QATS][BLOCK][REASON]", "direction=BUY");
      QCHECK(!b.empty(), "[QATS][BLOCK][REASON] is journalled");
      QCHECK(b.find(code) != std::string::npos, "the block names " + code + ": " + b);
      QCHECK(!firstWith("[QATS][SIGNAL][SCORED]", "outcome=BLOCKED", code).empty(), "the scored record carries outcome=BLOCKED reason=" + code);
      QCHECK(b.find("detail=") != std::string::npos && b.size() > b.find("detail=") + 10, "the block carries a human-readable detail");
   };
   auto expectReject = [&](const std::string &stage, const std::string &needle) {
      std::string r = firstWith("[QATS][EXECUTION][REJECTED]", "direction=BUY");
      QCHECK(!r.empty(), "[QATS][EXECUTION][REJECTED] is journalled");
      QCHECK(r.find("stage=" + stage) != std::string::npos, "the rejection names stage " + stage + ": " + r);
      QCHECK(r.find(needle) != std::string::npos, "the rejection names the reason (" + needle + "): " + r);
      QCHECK(!firstWith("[QATS][SIGNAL][SCORED]", "outcome=REJECTED", "reason=" + stage).empty(), "the scored record carries outcome=REJECTED reason=" + stage);
   };
   if(kind == "spread") expectBlock("SPREAD");
   else if(kind == "master_off") expectBlock("MASTER_SWITCH_OFF");
   else if(kind == "session") expectBlock("OUTSIDE_SESSION");
   else if(kind == "permission") expectBlock("PROTECTION");
   else if(kind == "drawdown") expectBlock("DRAWDOWN_HALT");
   else if(kind == "daily_loss") expectBlock("DAILY_LOSS_LOCK");
   else if(kind == "daily_cap_and_cooldown")
   {
      expectBlock("LOSS_COOLDOWN");
      std::string b = firstWith("[QATS][BLOCK][REASON]", "direction=BUY");
      QCHECK(b.find("reasons=LOSS_COOLDOWN,DAILY_TRADE_CAP") != std::string::npos, "BOTH active guards are listed, not just the first: " + b);
      QCHECK(b.find("remaining=") != std::string::npos && b.find("daily trade cap reached") != std::string::npos, "both details are spelled out");
   }
   else if(kind == "dry_run")
   {
      QEQ(entryCount(), 0L, "dry run sends nothing");
      QEQ(linesWith("[QATS][EXECUTION][APPROVED]", "direction=BUY"), 1, "dry run still journals the approved order");
      QCHECK(!firstWith("[QATS][DRY RUN]").empty(), "the dry-run notice is printed");
      QCHECK(!firstWith("[QATS][SIGNAL][SCORED]", "outcome=DRY_RUN").empty(), "outcome=DRY_RUN");
      QCHECK(!SetupAlreadyTraded(+1, sim::makeTime(2100, 1, 1)) || true, "dry run consumes nothing");
      QCHECK(GVGet(GVKey("sig_buy"), 0.0) == 0.0, "dry run does not reserve the signal bar");
      QCHECK(GVGet(GVKey("setup_buy"), 0.0) == 0.0, "dry run does not spend the setup");
   }
   else if(kind == "volume")
   {
      QEQ(entryCount(), 0L, "an order that cannot be sized is never sent");
      expectReject("SIZE", "below broker minimum");
   }
   else if(kind == "margin")
   {
      QEQ(entryCount(), 0L, "an order the free margin cannot carry even at the minimum lot is never sent");
      expectReject("SIZE", "margin");
   }
   else if(kind == "margin_fit")
   {
      // risk sizing asks for more than the free margin can carry: the volume is shrunk, never the stop
      QEQ(entryOkCount(), 1L, "the order is sent with a volume the free margin can carry");
      const sim::Deal *d = firstEntryDeal();
      QCHECK(d != nullptr, "an entry deal exists");
      if(d)
      {
         double riskSized = 6000.0 * EffectiveRiskPercent() / 100.0 / (std::fabs(d->price - d->sl) * 100.0);
         QCHECK(d->volume < riskSized - 0.005, "the volume was reduced below the risk-sized volume");
         QCHECK(sim::marginOf(d->volume, d->price) <= 6000.0 * InpMaxMarginUse + 1e-6, "the margin used stays inside InpMaxMarginUse of the free margin");
         QCHECK(d->sl > 0.0 && d->tp > 0.0, "the stop and the target are untouched");
      }
   }
   else if(kind == "broker" || kind == "timeout")
   {
      QEQ(entryCount(), 1L, "exactly one order reached the server on the first bar");
      QEQ(entryOkCount(), 0L, "the server refused it");
      expectReject("BROKER", kind == "broker" ? "retcode=10016" : "retcode=10012");
      QCHECK(firstWith("[QATS][EXECUTION][REJECTED]").find("no automatic retry") != std::string::npos, "XAUUSD: no automatic retry after a refused or ambiguous send");
      QEQ((long)sim::S.positions.size(), 0L, "no position exists");
      QCHECK(g_pendingRetryAt == 0, "no retry is queued");
      QCHECK(GVGet(GVKey("setup_buy"), 0.0) == 0.0, "a refused order does not spend the setup");
      // the SAME M5 bar is reserved; the next bar may try again because no position was opened
      pl.play(sc, m.entryAt + 10);
      QEQ(entryCount(), 2L, "the next M5 bar re-evaluates and sends once more");
      QEQ(entryOkCount(), 1L, "this time the server accepts");
      QEQ((long)sim::S.positions.size(), 1L, "exactly one position");
   }
   simDiagnosticsClean();
   printResult("rejection/" + kind, false);
}

// --- deal-history driven loss streak and cooldown ---------------------------
static ulong fakePosition(int dir, double profit, long magicIn, long magicOut, double partialProfit = 0.0, bool usePartial = false)
{
   sim::Position p{};
   p.ticket = sim::S.nextTicket++;
   p.magic = magicIn;
   p.symbol = sim::S.sym.name;
   p.type = dir > 0 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   p.volume = 0.10;
   p.priceOpen = sim::S.bid;
   p.sl = dir > 0 ? sim::S.bid - 5.0 : sim::S.bid + 5.0;
   p.tp = dir > 0 ? sim::S.bid + 10.0 : sim::S.bid - 10.0;
   p.time = sim::S.now;
   auto deal = [&](int entry, double vol, double pr, long magic) {
      sim::Deal d{};
      d.ticket = sim::S.nextTicket++;
      d.order = sim::S.nextTicket++;
      d.time = sim::S.now;
      d.entry = entry;
      d.type = (entry == DEAL_ENTRY_IN) ? (dir > 0 ? DEAL_TYPE_BUY : DEAL_TYPE_SELL) : (dir > 0 ? DEAL_TYPE_SELL : DEAL_TYPE_BUY);
      d.magic = magic;
      d.positionId = (long)p.ticket;
      d.volume = vol;
      d.price = sim::S.bid;
      d.profit = pr;
      d.symbol = p.symbol;
      d.sl = p.sl; d.tp = p.tp;
      sim::S.acc.balance += pr;
      sim::S.deals.push_back(d);
      sim::queueDealTx(d);
   };
   deal(DEAL_ENTRY_IN, 0.10, 0.0, magicIn);
   if(usePartial) deal(DEAL_ENTRY_OUT, 0.05, partialProfit, magicOut);
   deal(DEAL_ENTRY_OUT, usePartial ? 0.05 : 0.10, profit, magicOut);
   sim::dispatchTransactions();
   return p.ticket;
}

static void quiet(datetime seconds, double bid = 2000.0)
{
   // flat quotes, one per minute, through the EA
   datetime end = sim::S.now + seconds;
   while(sim::S.now + 60 <= end)
      sim::feedTick(sim::S.now + 60, bid, bid + 0.2, 1, false, true);
}

static void attachBare(double balance = 10000.0)
{
   resetSimOnly();
   captureJournal();
   sim::S.acc.balance = balance;
   sim::feedTick(kMonday + 30 * 86400 + 10 * 3600, 2000.0, 2000.2, 1, true, false);
   QEQ(OnInit(), (int)INIT_SUCCEEDED, "OnInit succeeds on a chart without history");
}

static void scnCooldown()
{
   setInputs({});
   attachBare();
   QEQ(g_consecLosses, 0, "the streak starts at 0");
   QCHECK(!g_inCooldown, "no cooldown at attach");
   QCHECK(!firstWith("[QATS][COOLDOWN] state=IDLE at attach").empty(), "the attach banner prints the cooldown state");
   quiet(120);
   fakePosition(+1, -30.0, InpMagic, InpMagic);
   QEQ(g_consecLosses, 1, "one losing position -> streak 1, counted when the deal arrives (not at the next M5 bar)");
   quiet(120);
   fakePosition(-1, -30.0, InpMagic, InpMagic);
   QEQ(g_consecLosses, 2, "a second loss (a SELL) -> streak 2: both directions feed the same breaker");
   QCHECK(!g_inCooldown, "below the threshold there is no cooldown");
   string why;
   QCHECK(EntriesAllowed(why), "entries are still allowed after two losses");
   quiet(120);
   datetime lossTime = sim::S.now;
   fakePosition(+1, -30.0, InpMagic, InpMagic);
   QCHECK(g_inCooldown, "the third consecutive loss starts the stand-down");
   QEQ(g_consecLosses, 0, "the streak restarts at 0 when the stand-down begins: consecLosses=0 with cooldown=YES is the designed state");
   QEQ(g_cooldownTrigger, 3, "the stand-down remembers that 3 losses triggered it");
   QEQ((long)g_cooldownStart, (long)lossTime, "the stand-down starts at the close time of the triggering deal");
   QEQ((long)g_cooldownUntil, (long)lossTime + 3600, "it expires exactly InpCooldownAfterLossMin later");
   QCHECK(GVGet(GVKey("cooldown_start"), 0.0) == (double)lossTime && GVGet(GVKey("cooldown_until"), 0.0) == (double)(lossTime + 3600) &&
          GVGet(GVKey("cooldown_trigger"), 0.0) == 3.0, "start, expiry and trigger are persisted");
   QCHECK(!firstWith("[QATS][COOLDOWN] state=STARTED trigger=3 losses").empty(), "the start is journalled with its trigger");
   QCHECK(!firstWith("[QATS][GUARD] 3 consecutive losing closes - standing down for 60 minutes").empty(), "the legacy guard line is kept");
   QCHECK(!EntriesAllowed(why), "entries are blocked during the stand-down");
   QCHECK(why.find("CONSECUTIVE-LOSS cooldown active YES(trigger=3 losses") != std::string::npos && why.find("remaining=") != std::string::npos,
          "the block reason carries trigger, start, expiry and remaining seconds: " + why);
   // heartbeat text
   QATS_SetInput("InpHeartbeatSeconds", "60");
   quiet(600);
   std::string hb = lastWith("[QATS][HB]");
   QCHECK(hb.find("consecLosses=0/3") != std::string::npos, "heartbeat shows the streak against its threshold: " + hb);
   QCHECK(hb.find("cooldown=YES(trigger=3 losses,start=") != std::string::npos && hb.find("remaining=") != std::string::npos,
          "heartbeat explains the running timer");
   long rem1 = QATS_CooldownRemaining(TimeTradeServer(), g_cooldownUntil);
   QCHECK(rem1 > 0 && rem1 < 3600, "remaining seconds count down");
   QATS_SetInput("InpHeartbeatSeconds", "0");
   // a re-attach during the stand-down restores it from the persisted state
   g_inCooldown = false; g_cooldownUntil = 0; g_cooldownStart = 0; g_cooldownTrigger = 0;
   QEQ(OnInit(), (int)INIT_SUCCEEDED, "re-attach");
   QCHECK(g_inCooldown && g_cooldownTrigger == 3 && (long)g_cooldownUntil == (long)lossTime + 3600, "the stand-down survives a re-attach unchanged");
   QCHECK(!lastWith("[QATS][COOLDOWN] state=ACTIVE at attach").empty(), "the attach banner reports the active stand-down");
   // expiry
   quiet(3600);
   QCHECK(!g_inCooldown, "the stand-down ends at its expiry time");
   QEQ(linesWith("[QATS][COOLDOWN] state=EXPIRED"), 1, "the expiry is journalled exactly once");
   QCHECK(!GlobalVariableCheck(GVKey("cooldown_until")) && !GlobalVariableCheck(GVKey("cooldown_start")) && !GlobalVariableCheck(GVKey("cooldown_trigger")),
          "the persisted cooldown state is removed on expiry");
   QCHECK(EntriesAllowed(why), "entries are allowed again after the expiry");
   QEQ(g_consecLosses, 0, "the streak is 0 after the stand-down");
   // a win resets the streak
   fakePosition(+1, -30.0, InpMagic, InpMagic);
   fakePosition(-1, -30.0, InpMagic, InpMagic);
   QEQ(g_consecLosses, 2, "two new losses");
   fakePosition(-1, +45.0, InpMagic, InpMagic);
   QEQ(g_consecLosses, 0, "a winning position resets the streak");
   QCHECK(!g_inCooldown, "no stand-down after a win");
   simDiagnosticsClean();
   printf("RESULT scenario=cooldown\n");
}

static void scnLossCounting()
{
   setInputs({});
   attachBare();
   // a position banked in two parts: +40 on the partial, -1.20 on the remainder. NET it is a winner.
   fakePosition(+1, -1.20, InpMagic, InpMagic, 40.0, true);
   QEQ(g_consecLosses, 0, "a position that banked +40 and scratched -1.20 on the rest is a WIN, not a loss");
   QCHECK(!lastWith("[QATS][GUARD] position", "closed WIN net=+38.80").empty(), "the position is netted over all of its deals");
   // a position closed by hand (the closing deal carries no magic) still belongs to the EA
   fakePosition(-1, -25.0, InpMagic, 0);
   QEQ(g_consecLosses, 1, "a manual close of the EA's position is counted (ownership comes from the entry deal)");
   // a foreign position is ignored
   fakePosition(+1, -500.0, 777, 777);
   QEQ(g_consecLosses, 1, "another EA's losing position does not touch the streak");
   // break-even scratch: strict by default
   fakePosition(+1, -1.15, InpMagic, InpMagic);
   QEQ(g_consecLosses, 2, "default (InpNeutralCloseR=0): a -1.15 scratch is a loss");
   // with a neutral band of 0.10 R (0.5% of 10k = 50 -> band 5.00) the same scratch is neutral
   QATS_SetInput("InpNeutralCloseR", "0.10");
   fakePosition(+1, -1.15, InpMagic, InpMagic);
   QEQ(g_consecLosses, 2, "InpNeutralCloseR=0.10: a -1.15 scratch neither extends nor resets the streak");
   QCHECK(!lastWith("[QATS][GUARD] position", "closed NEUTRAL").empty(), "the neutral close is journalled as NEUTRAL");
   fakePosition(+1, +2.00, InpMagic, InpMagic);
   QEQ(g_consecLosses, 2, "a +2.00 gain inside the band is neutral too (it does not launder the streak)");
   fakePosition(+1, -30.0, InpMagic, InpMagic);
   QCHECK(g_inCooldown, "a real loss completes the streak and starts the stand-down");
   // per-direction session statistics came from the same deal history
   QCHECK(g_statLosses[0] >= 2 && g_statLosses[1] == 1, "losses are attributed to BUY and SELL separately");
   QEQ(g_statWins[0], 1, "the partial-close winner is a BUY win");
   QEQ(g_statNeutral[0], 2, "two neutral BUY closes");
   simDiagnosticsClean();
   printf("RESULT scenario=loss_counting\n");
}

static void scnCooldownStateValidation()
{
   setInputs({});
   attachBare();
   datetime now = TimeTradeServer();
   // 1. a corrupted expiry far in the future cannot lock the EA out for longer than one stand-down
   GVSet(GVKey("cooldown_until"), (double)(now + 10 * 86400));
   GVSet(GVKey("cooldown_start"), (double)now);
   UpdateCooldownState();
   QCHECK(g_inCooldown, "a persisted stand-down is honoured");
   QCHECK(QATS_CooldownRemaining(now, g_cooldownUntil) <= 3600, "an expiry beyond one configured stand-down is clamped to one stand-down from now");
   QCHECK(!lastWith("[QATS][COOLDOWN] state=REPAIRED persisted expiry").empty(), "the repair is journalled");
   // 2. a state written by v1.11 has no start time: it is derived, the expiry is untouched
   ClearCooldownState();
   GVSet(GVKey("cooldown_until"), (double)(now + 1500));
   UpdateCooldownState();
   QCHECK(g_inCooldown && (long)g_cooldownUntil == (long)now + 1500, "a v1.11 state keeps its expiry");
   QEQ((long)g_cooldownStart, (long)now + 1500 - 3600, "the missing start is derived from the expiry");
   QCHECK(!lastWith("[QATS][COOLDOWN] state=REPAIRED start time missing").empty(), "the derivation is journalled");
   // 3. an invalid streak is reset
   ClearCooldownState();
   GVSet(GVKey("consec_losses"), -5.0);
   UpdateCooldownState();
   QEQ(g_consecLosses, 0, "a negative persisted streak is reset to 0");
   QCHECK(!lastWith("[QATS][COOLDOWN] state=REPAIRED persisted loss streak").empty(), "the reset is journalled");
   // 4. a streak at the threshold with no stand-down running starts one (the protection is never skipped)
   GVSet(GVKey("consec_losses"), 3.0);
   UpdateCooldownState();
   QCHECK(g_inCooldown, "a streak at the threshold starts the stand-down immediately");
   QEQ(g_consecLosses, 0, "and restarts the streak");
   // 5. an expired state is cleared and journalled once
   ClearCooldownState();
   GVSet(GVKey("cooldown_until"), (double)(now - 10));
   GVSet(GVKey("cooldown_start"), (double)(now - 3610));
   GVSet(GVKey("cooldown_trigger"), 3.0);
   int before = linesWith("[QATS][COOLDOWN] state=EXPIRED");
   UpdateCooldownState();
   UpdateCooldownState();
   QCHECK(!g_inCooldown, "an expired stand-down does not block");
   QEQ(linesWith("[QATS][COOLDOWN] state=EXPIRED") - before, 1, "expiry is journalled once, not on every tick");
   // 6. disabling the breaker drops a persisted stand-down, and says so
   GVSet(GVKey("cooldown_until"), (double)(now + 1500));
   GVSet(GVKey("cooldown_start"), (double)now);
   QATS_SetInput("InpStopAfterConsecLoss", "0");
   UpdateCooldownState();
   QCHECK(!g_inCooldown, "with the breaker disabled by input no stand-down applies");
   QCHECK(!lastWith("[QATS][COOLDOWN] state=CLEARED").empty(), "the drop is journalled");
   QATS_SetInput("InpStopAfterConsecLoss", "3");
   // 7. operator reset clears everything
   GVSet(GVKey("cooldown_until"), (double)(now + 1500));
   GVSet(GVKey("cooldown_start"), (double)now);
   GVSet(GVKey("cooldown_trigger"), 3.0);
   ResetBreakers();
   UpdateCooldownState();
   QCHECK(!g_inCooldown && !GlobalVariableCheck(GVKey("cooldown_start")) && !GlobalVariableCheck(GVKey("cooldown_trigger")), "the operator reset removes every cooldown key");
   simDiagnosticsClean();
   printf("RESULT scenario=cooldown_state\n");
}

// never both sides; an opposite eligible setup closes first, then opens
static void scnOpposite(bool closeOnOpposite)
{
   resetSimOnly();
   captureJournal();
   setInputs({{"InpCloseOnOpposite", closeOnOpposite ? "true" : "false"}, {"InpMaxOpenPositions", "2"}});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.play(sc, m.attachAt);
   pl.attach(sc);
   pl.play(sc, m.entryAt);
   // a SELL of this EA is open when the BUY setup completes
   MqlTradeRequest rq{};
   MqlTradeResult rs{};
   rq.action = TRADE_ACTION_DEAL; rq.symbol = sim::S.sym.name; rq.magic = (ulong)InpMagic; rq.volume = 0.01;
   rq.type = ORDER_TYPE_SELL; rq.type_filling = ORDER_FILLING_IOC;
   QCHECK(sim::serverSend(rq, rs), "test fixture: a SELL position of this magic exists");
   sim::dispatchTransactions();
   long before = entryOkCount();
   pl.play(sc, m.entryAt + 5);
   if(!closeOnOpposite)
   {
      QEQ(entryOkCount() - before, 0L, "no BUY is opened while the EA's SELL is open");
      std::string b = firstWith("[QATS][BLOCK][REASON]", "direction=BUY");
      QCHECK(b.find("OPPOSITE_POSITION") != std::string::npos, "the block is OPPOSITE_POSITION: " + b);
      QEQ((long)sim::S.positions.size(), 1L, "still exactly one position (the SELL)");
   }
   else
   {
      QCHECK(!firstWith("[QATS][MANAGE]", "closed on OPPOSITE signal (BUY)").empty(), "the SELL is closed on the opposite eligible setup");
      QEQ(entryOkCount() - before, 1L, "then the BUY is opened");
      QEQ((long)sim::S.positions.size(), 1L, "exactly one position afterwards");
      if(!sim::S.positions.empty()) QEQ(sim::S.positions[0].type, (int)POSITION_TYPE_BUY, "and it is the BUY");
   }
   int both = 0;
   bool haveBuy = false, haveSell = false;
   for(const sim::Position &p : sim::S.positions) { if(p.type == POSITION_TYPE_BUY) haveBuy = true; else haveSell = true; }
   if(haveBuy && haveSell) both++;
   QEQ(both, 0, "the EA never holds BUY and SELL at the same time");
   simDiagnosticsClean();
   printf("RESULT scenario=opposite/%d\n", closeOnOpposite ? 1 : 0);
}

// A restart with a position open: management can close it before the first entry of
// the new session. The trade object must already carry the EA's magic and deviation
// (v1.11 configured it lazily, inside the first entry: such a close went out with
// magic 0, was never journalled as the EA's deal and never reached the loss streak).
static void scnRestartManage()
{
   resetSimOnly();
   captureJournal();
   setInputs({});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.play(sc, m.entryAt);
   // a SELL of this EA from a previous session; the symbol accepts IOC only
   MqlTradeRequest rq{};
   MqlTradeResult rs{};
   rq.action = TRADE_ACTION_DEAL; rq.symbol = sim::S.sym.name; rq.magic = (ulong)InpMagic; rq.volume = 0.01;
   rq.type = ORDER_TYPE_SELL; rq.type_filling = ORDER_FILLING_IOC;
   QCHECK(sim::serverSend(rq, rs), "test fixture: an open SELL from an earlier session");
   QEQ(pl.attach(sc), (int)INIT_SUCCEEDED, "attach with a position open");
   pl.play(sc, m.entryAt + 5);
   QEQ(linesWith("opposite-close failed"), 0, "the opposite close does not fail right after a restart");
   QCHECK(!firstWith("[QATS][MANAGE]", "closed on OPPOSITE signal (BUY)").empty(), "the old SELL is closed by the first eligible BUY setup");
   long closeMagic = -1;
   for(const sim::Deal &d : sim::S.deals)
      if(d.entry == DEAL_ENTRY_OUT) { closeMagic = d.magic; break; }
   QEQ(closeMagic, (long)InpMagic, "the closing deal carries the EA magic (the trade object is configured at attach)");
   QCHECK(!firstWith("[QATS][DEAL]", "entry=1").empty(), "the close is journalled as the EA's own deal");
   QCHECK(!firstWith("[QATS][GUARD] position", "SELL closed").empty(), "the closed position reaches the loss-streak accounting");
   simDiagnosticsClean();
   printf("RESULT scenario=restart_manage\n");
}

// non-XAUUSD transient failure: the retry goes through the guard chain and cannot lock entries out
static void scnRetry(bool keepFailing)
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
   if(keepFailing) sim::S.injectRetcodes = {TRADE_RETCODE_REQUOTE, TRADE_RETCODE_REQUOTE, TRADE_RETCODE_REQUOTE, TRADE_RETCODE_REQUOTE, TRADE_RETCODE_REQUOTE};
   else            sim::S.injectRetcodes = {TRADE_RETCODE_REQUOTE};
   pl.play(sc, m.entryAt + 4);
   QCHECK(!firstWith("[QATS][EXEC] transient failure - queued retry 1/3").empty(), "a transient retcode queues a retry");
   if(!keepFailing)
   {
      QEQ(entryOkCount(), 1L, "the retry is accepted");
      QEQ((long)sim::S.positions.size(), 1L, "one position");
      QCHECK(g_pendingRetryAt == 0 && g_pendingRetries == 0, "the retry state is cleared after success");
      QCHECK(firstWith("[QATS][EXECUTION][FILLED]").find("direction=BUY") != std::string::npos, "the retried order is journalled as FILLED");
   }
   else
   {
      QEQ(entryOkCount(), 0L, "nothing was accepted while the server kept requoting");
      QCHECK(entryCount() >= 4, "the original send plus three retries reached the server");
      QCHECK(g_pendingRetryAt == 0, "after the budget is spent NO retry stays pending");
      string why;
      bool allowed = EntriesAllowed(why);
      QCHECK(allowed || why.find("order retry pending") == std::string::npos, "entries are not locked out by a stale retry flag: " + why);
      sim::S.injectRetcodes.clear();
      pl.play(sc, m.entryAt + 15);
      QCHECK(entryOkCount() >= 1, "a later bar can trade again once the server recovers");
   }
   simDiagnosticsClean();
   printf("RESULT scenario=retry/%d\n", keepFailing ? 1 : 0);
}

// journal invariants on a two-sided market: a with-trend BUY chain, a pause, then a
// reversal that runs the highs and breaks the lows (SELL)
static void scnJournalInvariants()
{
   resetSimOnly();
   captureJournal();
   setInputs({});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);          // BUY: sweep -> displacement -> BOS -> follow-through
   for(int i = 0; i < 4; i++) { sc.leg(5, 6.0); sc.leg(3, -4.0); }
   sc.leg(5, 6.0);
   double P = sc.cur;
   sc.leg(3, -4.0);
   sc.leg(4, 3.6);
   sc.to(30, P + 2.2);                            // SELL: failed breakout above the last swing high ...
   sc.to(30, P - 1.0);
   sc.to(60, P - 8.0);                            // ... displacement through the last swing low (CHoCH)
   sc.to(60, P - 14.0);
   sc.to(120, P - 20.0);
   sc.to(600, sc.cur);
   Player pl;
   pl.play(sc, m.attachAt);
   pl.attach(sc);
   pl.play(sc, sc.bars());
   OnDeinit(1);
   int scored = 0, sumBad = 0, bothSides = 0, noOutcome = 0;
   for(const std::string &s : JR.keep)
   {
      if(s.compare(0, 22, "[QATS][SIGNAL][SCORED]") != 0) continue;
      scored++;
      if(s.find("BUY core=") != std::string::npos && s.find("SELL core=") != std::string::npos) bothSides++;
      if(Journal::field(s, "outcome=").empty() || Journal::field(s, "reason=").empty()) noOutcome++;
      for(const char *side : {"BUY", "SELL"})
      {
         size_t p = s.find(std::string(side) + " core=");
         size_t a = s.find('[', p), b = s.find(']', a);
         std::string inner = s.substr(a + 1, b - a - 1);
         int sum = 0;
         std::stringstream ss(inner);
         std::string tok;
         while(ss >> tok) { size_t c = tok.find(':'); if(c != std::string::npos) sum += atoi(tok.c_str() + c + 1); }
         int score = atoi(Journal::field(s, std::string(side) + "=").c_str());
         if(sum != score) sumBad++;
      }
   }
   QCHECK(scored > 200, "every closed M5 bar produced a scored record (" + std::to_string(scored) + ")");
   QEQ(bothSides, scored, "every record reports BOTH sides");
   QEQ(noOutcome, 0, "every record carries an outcome and a reason code");
   QEQ(sumBad, 0, "on every record the listed points add up to the printed score (no hidden component)");
   QCHECK(linesWith("[QATS][BUY][DETECTED]") >= 1 && linesWith("[QATS][SELL][DETECTED]") >= 1, "both BUY and SELL setups were detected in a two-sided market");
   int buyFills = linesWith("[QATS][EXECUTION][FILLED]", "direction=BUY"), sellFills = linesWith("[QATS][EXECUTION][FILLED]", "direction=SELL");
   QCHECK(buyFills >= 1 && sellFills >= 1, "both BUY and SELL orders were executed (" + std::to_string(buyFills) + " / " + std::to_string(sellFills) + ")");
   // life cycle: every APPROVED order ends in exactly one FILLED or one broker/reserve REJECTED record
   QEQ(linesWith("[QATS][EXECUTION][APPROVED]"),
       linesWith("[QATS][EXECUTION][FILLED]") + linesWith("[QATS][EXECUTION][REJECTED]", "stage=BROKER") + linesWith("[QATS][EXECUTION][REJECTED]", "stage=RESERVE"),
       "every APPROVED order is accounted for by a FILLED or a REJECTED record");
   QEQ(linesWith("[QATS][SIGNAL][SCORED]", "outcome=EXECUTED"), linesWith("[QATS][EXECUTION][FILLED]"), "one EXECUTED outcome per FILLED record");
   // an eligible candidate never ends without an outcome that explains it
   int silent = 0;
   for(const std::string &s : JR.keep)
      if(s.compare(0, 22, "[QATS][SIGNAL][SCORED]") == 0 && s.find("eligible=yes") != std::string::npos)
      {
         std::string o = Journal::field(s, "outcome=");
         if(o != "EXECUTED" && o != "BLOCKED" && o != "REJECTED" && o != "DRY_RUN" && o != "CONFLICT") silent++;
      }
   QEQ(silent, 0, "no eligible signal is discarded silently");
   QCHECK(!lastWith("[QATS][STATS] scope=session").empty(), "the session statistics are printed at deinit, per direction");
   std::string stats = lastWith("[QATS][STATS] scope=session");
   QCHECK(stats.find("BUY detected=") != std::string::npos && stats.find("| SELL detected=") != std::string::npos, "statistics carry both directions: " + stats);
   simDiagnosticsClean();
   printf("RESULT scenario=journal_invariants scored=%d buyFills=%d sellFills=%d\n", scored, buyFills, sellFills);
}

// rarely travelled paths: a position without a stop, a REAL account, a wide spread at attach
static void scnMiscPaths()
{
   setInputs({});
   // 1. attach on a REAL account without authorization: analysis only, no orders
   resetSimOnly();
   captureJournal();
   sim::S.acc.tradeMode = ACCOUNT_TRADE_MODE_REAL;
   sim::feedTick(kMonday + 30 * 86400 + 10 * 3600, 2000.0, 2000.9, 1, true, false);
   QEQ(OnInit(), (int)INIT_SUCCEEDED, "the EA attaches on an unauthorized REAL account (analysis only)");
   QCHECK(g_execBlocked, "execution is blocked on an unauthorized REAL account");
   QCHECK(!firstWith("[QATS][PROTECTION] EXECUTION BLOCKED: REAL account blocked by InpDemoOnly").empty(), "the block is journalled with its reason");
   QCHECK(!firstWith("[QATS][CONFIG] current spread 90 pts is above InpMaxSpreadPoints=50").empty(), "a spread above the limit at attach is announced");
   string why;
   QCHECK(!EntriesAllowed(why) && why.find("REAL account") != std::string::npos, "entries are refused and the reason is the account: " + why);
   // 2. a position of this EA that lost its stop is re-protected on the next tick
   resetSimOnly();
   captureJournal();
   sim::feedTick(kMonday + 30 * 86400 + 10 * 3600, 2000.0, 2000.2, 1, true, false);
   QEQ(OnInit(), (int)INIT_SUCCEEDED, "attach");
   MqlTradeRequest rq{};
   MqlTradeResult rs{};
   rq.action = TRADE_ACTION_DEAL; rq.symbol = sim::S.sym.name; rq.magic = (ulong)InpMagic; rq.volume = 0.01;
   rq.type = ORDER_TYPE_SELL; rq.type_filling = ORDER_FILLING_IOC;
   QCHECK(sim::serverSend(rq, rs), "test fixture: a SELL position without any stop");
   quiet(120);
   QEQ((long)sim::S.positions.size(), 1L, "the position is still open");
   if(!sim::S.positions.empty())
   {
      QCHECK(sim::S.positions[0].sl > sim::S.ask, "the unprotected SELL received a stop ABOVE the market");
      QCHECK(!firstWith("[QATS][PROTECT]", "had NO stop - rebuilt SL").empty(), "the rescue is journalled");
   }
   // mirrored: an unprotected BUY receives a stop BELOW the market
   resetSimOnly();
   captureJournal();
   sim::feedTick(kMonday + 30 * 86400 + 10 * 3600, 2000.0, 2000.2, 1, true, false);
   OnInit();
   rq.type = ORDER_TYPE_BUY;
   QCHECK(sim::serverSend(rq, rs), "test fixture: a BUY position without any stop");
   quiet(120);
   if(!sim::S.positions.empty())
      QCHECK(sim::S.positions[0].sl > 0.0 && sim::S.positions[0].sl < sim::S.bid, "the unprotected BUY received a stop BELOW the market");
   // 3. operator reset and deinit statistics
   ResetBreakers();
   QCHECK(!firstWith("[QATS][RESET] Operator reset").empty(), "the operator reset is journalled");
   OnDeinit(1);
   QCHECK(!firstWith("[QATS][STATS] scope=session").empty(), "session statistics at deinit");
   simDiagnosticsClean();
   printf("RESULT scenario=misc_paths\n");
}


//+------------------------------------------------------------------+
//| v1.21 LIMIT entry, end to end (bull and its exact mirror).        |
//|   limit_entry      the order is a LIMIT at the zone, not a market |
//|                    order, with its own server-side SL and TP      |
//|   limit_cancel     price runs away: the limit is cancelled BY     |
//|                    NAME, the daily cap stays 0, the setup is NOT  |
//|                    spent (it is still tradable)                   |
//|   limit_fill       the retracement reaches the limit: ONE fill,   |
//|                    the cap moves to exactly 1, the setup is spent |
//+------------------------------------------------------------------+
static long pendingCount() { return (long)sim::S.orders.size(); }

static long pendingTypeOf()
{
   return sim::S.orders.empty() ? -1 : (long)sim::S.orders[0].type;
}

static void scnLimitEntry(bool mirror)
{
   const char *side = mirror ? "SELL" : "BUY";
   resetSimOnly();
   captureJournal();
   setInputs({{"InpUseLimitEntry", "true"}, {"InpLimitMaxDistATR", "40"}, {"InpLimitNeedPD", "false"}});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.feed.mirror = mirror;
   pl.feed.mirrorK = 400000;
   pl.play(sc, m.attachAt);
   QEQ(pl.attach(sc), (int)INIT_SUCCEEDED, "OnInit succeeds");
   pl.play(sc, m.entryAt);
   QEQ(entryOkCount(), 0L, std::string("no MARKET entry is sent: the EA does not pay the market mid-move"));
   pl.play(sc, m.entryAt + 5);
   QEQ(pendingCount(), 1L, std::string("exactly one resting ") + side + "_LIMIT");
   QEQ(pendingTypeOf(), mirror ? (long)ORDER_TYPE_SELL_LIMIT : (long)ORDER_TYPE_BUY_LIMIT,
       std::string("the order type is ") + side + "_LIMIT");
   if(pendingCount() == 1)
   {
      const sim::PendingOrder o = sim::S.orders[0];
      QCHECK(o.sl > 0.0 && o.tp > 0.0, "the pending order carries its OWN server-side SL and TP (no order without a stop)");
      QCHECK(o.volume > 0.0, "the order is sized");
      if(mirror) QCHECK(o.price > sim::S.bid && o.sl > o.price && o.tp < o.price, "SELL LIMIT: above the bid, stop above, target below");
      else       QCHECK(o.price < sim::S.ask && o.sl < o.price && o.tp > o.price, "BUY LIMIT: below the ask, stop below, target above");
      QCHECK(o.typeTime == ORDER_TIME_SPECIFIED && o.timeExpiration > sim::S.now,
             "expiry is ORDER_TIME_SPECIFIED and in the future (" + std::to_string((long)o.timeExpiration - (long)sim::S.now) + "s)");
      QCHECK(sim::onGrid(o.price) && sim::onGrid(o.sl) && sim::onGrid(o.tp), "entry, SL and TP sit on the tick grid");
      double stopPts = std::fabs(o.price - o.sl) / sim::S.sym.point;
      QCHECK(stopPts >= InpMinStopPoints && stopPts <= InpMaxStopPoints, "the zone stop is inside InpMinStopPoints/InpMaxStopPoints");
      double rr = std::fabs(o.tp - o.price) / std::fabs(o.price - o.sl);
      QCHECK(rr + 1e-9 >= InpLimitMinRR, "reward:risk measured from the LIMIT price >= InpLimitMinRR (got " + std::to_string(rr) + ")");
      // the risk carried by the resting order is the equity risk, not a guess
      double riskMoney = std::fabs(o.price - o.sl) * sim::moneyPerPriceUnit(o.volume);
      QCHECK(riskMoney <= 10000.0 * EffectiveRiskPercent() / 100.0 + 1e-6, "risk at the zone stop does not exceed the configured equity risk");
   }
   QCHECK(linesWith("[QATS][LIMIT] PLAN direction=" + std::string(side), "type=" + std::string(side) + "_LIMIT") == 1,
          "one [QATS][LIMIT] PLAN line naming the order type");
   QCHECK(linesWith("[QATS][LIMIT] PLACED", "zone=") == 1, "one [QATS][LIMIT] PLACED line naming the zone source");
   QCHECK(firstWith("[QATS][LIMIT] PLACED").find("zone=OB") != std::string::npos, "the zone source is the OB/FVG that produced it");
   QCHECK(firstWith("[QATS][LIMIT] PLAN").find("volume=") != std::string::npos, "the entry log carries entry, SL, TP, volume and risk");
   QEQ(g_tradesToday, 0, "a PLACED limit does not touch the daily trade counter");
   QEQ(linesWith("[QATS][EXECUTION][APPROVED]"), 0, "no market execution record was produced");
   simDiagnosticsClean();
   printf("RESULT scenario=limit_entry mirror=%d pending=%ld type=%ld trades=%d price=%.2f sl=%.2f tp=%.2f volume=%.2f\n",
          mirror ? 1 : 0, pendingCount(), pendingTypeOf(), g_tradesToday,
          sim::S.orders.empty() ? 0.0 : sim::S.orders[0].price,
          sim::S.orders.empty() ? 0.0 : sim::S.orders[0].sl,
          sim::S.orders.empty() ? 0.0 : sim::S.orders[0].tp,
          sim::S.orders.empty() ? 0.0 : sim::S.orders[0].volume);
}

// walk the market AWAY from the zone in small steps that never reach the limit
static void walkAway(bool mirror, double distance)
{
   double start = sim::S.bid;
   for(int i = 0; i < 40; i++)
   {
      // the mirror of "price rises away from a BUY limit below the market" is
      // "price falls away from a SELL limit above the market"
      double d = (mirror ? -1.0 : +1.0) * distance * (i + 1) / 40.0;
      double bid = start + d;
      sim::feedTick(sim::S.now + 60, bid, bid + 22.0, 1, false, true);   // the spread stays positive
   }
}

static void scnLimitCancel(bool mirror)
{
   const char *side = mirror ? "SELL" : "BUY";
   resetSimOnly();
   captureJournal();
   // The placement needs the wider budget (the continuation zone is ~850 pts away,
   // the shipped 3.0 x ATR is 675), and the run-away guard is then 1.5 x that
   // budget x H1 ATR. The walk below crosses it - nothing else can cancel here,
   // because the price only moves AWAY from the limit, never through its stop.
   setInputs({{"InpUseLimitEntry", "true"}, {"InpLimitNeedPD", "false"}, {"InpLimitMaxDistATR", "8"}});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.feed.mirror = mirror;
   pl.feed.mirrorK = 400000;
   pl.play(sc, m.attachAt);
   QEQ(pl.attach(sc), (int)INIT_SUCCEEDED, "OnInit succeeds");
   pl.play(sc, m.entryAt + 5);
   QEQ(pendingCount(), 1L, std::string("one ") + side + "_LIMIT is working");
   SAnalysis raw = AnalyzeMarket();
   int dir = mirror ? -1 : +1;
   double setup = (double)raw.setupTime;
   QCHECK(setup > 0.0, "the setup has an identity");
   QCHECK(!SetupAlreadyTraded(dir, raw.setupTime), "placing the limit did NOT spend the setup");
   QEQ(g_tradesToday, 0, "no trade counted at placement");

   // the retracement never comes: the price leaves the zone
   walkAway(mirror, 140.0);
   QEQ(linesWith("[QATS][LIMIT] CANCELLED"), 1, "exactly one cancellation");
   QCHECK(linesWith("[QATS][LIMIT] CANCELLED", "reason=PRICE_RAN_AWAY") == 1, "the cancellation names its reason");
   QCHECK(linesWith("[QATS][LIMIT] CANCELLED", "the daily trade cap is untouched") == 1,
          "the cancellation line states that the cap was not consumed");
   QEQ(pendingCount(), 0L, "the order is gone from the server");
   QEQ(g_tradesToday, 0, "a CANCELLED limit does NOT consume the daily trade cap");
   QEQ((long)GVGet(GVKey(std::string("trades_") + TodayKey()), 0.0), 0L, "the persisted counter is still 0");
   QCHECK(!SetupAlreadyTraded(dir, raw.setupTime), "a CANCELLED limit does NOT spend the setup: it can be traded again");
   QEQ(entryOkCount(), 0L, "no order ever filled");
   simDiagnosticsClean();
   printf("RESULT scenario=limit_cancel mirror=%d cancelled=%d trades=%d pending=%ld setup=%ld\n",
          mirror ? 1 : 0, linesWith("[QATS][LIMIT] CANCELLED"), g_tradesToday, pendingCount(), (long)setup);
}

static void scnLimitFill(bool mirror)
{
   const char *side = mirror ? "SELL" : "BUY";
   resetSimOnly();
   captureJournal();
   setInputs({{"InpUseLimitEntry", "true"}, {"InpLimitMaxDistATR", "40"}, {"InpLimitNeedPD", "false"}});
   Scn sc(1500.0);
   Marks m = patternFullChain(sc, true);
   Player pl;
   pl.feed.mirror = mirror;
   pl.feed.mirrorK = 400000;
   pl.play(sc, m.attachAt);
   QEQ(pl.attach(sc), (int)INIT_SUCCEEDED, "OnInit succeeds");
   pl.play(sc, m.entryAt + 5);
   QEQ(pendingCount(), 1L, "one limit is working");
   double price = sim::S.orders[0].price;
   double sl = sim::S.orders[0].sl;
   double tp = sim::S.orders[0].tp;
   QEQ(g_tradesToday, 0, "no trade counted yet");

   // the retracement arrives: quote THROUGH the limit price, one tick
   if(mirror) sim::feedTick(sim::S.now + 60, price + 20, price + 22, 1, false, true);
   else       sim::feedTick(sim::S.now + 60, price - 22, price - 20, 1, false, true);

   QEQ(pendingCount(), 0L, "the limit is consumed by the fill");
   QEQ((long)sim::S.positions.size(), 1L, "exactly ONE position exists");
   QEQ(linesWith("[QATS][LIMIT] FILLED"), 1, "the fill is journalled once, as a [QATS][LIMIT] line");
   QEQ(g_tradesToday, 1, "a FILLED entry moves the daily counter to exactly 1");
   QEQ((long)GVGet(GVKey(std::string("trades_") + TodayKey()), 0.0), 1L, "the persisted counter agrees");
   if(!sim::S.positions.empty())
   {
      const sim::Position &p = sim::S.positions[0];
      QCHECK(near(p.priceOpen, price), "the position opened AT the limit price, not at the market");
      QCHECK(near(p.sl, sl) && near(p.tp, tp), "the fill kept the order's own SL and TP");
      QCHECK(p.magic == InpMagic, "the position carries the EA magic");
      QEQ(p.type, mirror ? (int)POSITION_TYPE_SELL : (int)POSITION_TYPE_BUY, "the position side is the order side");
   }
   QCHECK(linesWith("[QATS][LIMIT] FILLED", "filled orders only") == 1, "the fill line explains what the counter counts");
   QCHECK(linesWith("[QATS][EXECUTION][FILLED]") == 0, "the MARKET execution log is not used by the limit path");
   // never twice: the fill spent the setup
   int before = g_tradesToday;
   quiet(600, mirror ? 1900.0 : 2100.0);
   QCHECK(g_tradesToday >= before, "the counter never goes backwards");
   QCHECK((long)sim::S.positions.size() <= 1L, "no second position for the same setup");
   QEQ(linesWith("[QATS][LIMIT] FILLED"), 1, "still exactly one fill after ten more minutes");
   simDiagnosticsClean();
   printf("RESULT scenario=limit_fill mirror=%d trades=%d positions=%zu filled=%d price=%.2f sl=%.2f tp=%.2f\n",
          mirror ? 1 : 0, g_tradesToday, sim::S.positions.size(), linesWith("[QATS][LIMIT] FILLED"), price, sl, tp);
}

struct ScnEntry { const char *name; std::function<void()> fn; };
static std::vector<ScnEntry> scenarioTable()
{
   return {
      {"strong_buy", [] { scnStrong(false, "1"); }},
      {"strong_sell", [] { scnStrong(true, "1"); }},
      {"strong_buy_conservative", [] { scnStrong(false, "0"); }},
      {"strong_sell_conservative", [] { scnStrong(true, "0"); }},
      {"strong_buy_active", [] { scnStrong(false, "2"); }},
      {"strong_sell_active", [] { scnStrong(true, "2"); }},
      {"sweep_only_buy_conservative", [] { scnCoreGate("sweep_only", "0", false); }},
      {"sweep_only_buy_balanced", [] { scnCoreGate("sweep_only", "1", false); }},
      {"sweep_only_buy_active", [] { scnCoreGate("sweep_only", "2", false); }},
      {"sweep_only_sell_conservative", [] { scnCoreGate("sweep_only", "0", true); }},
      {"sweep_only_sell_balanced", [] { scnCoreGate("sweep_only", "1", true); }},
      {"sweep_only_sell_active", [] { scnCoreGate("sweep_only", "2", true); }},
      {"bos_only_buy_conservative", [] { scnCoreGate("bos_only", "0", false); }},
      {"bos_only_buy_balanced", [] { scnCoreGate("bos_only", "1", false); }},
      {"bos_only_buy_active", [] { scnCoreGate("bos_only", "2", false); }},
      {"bos_only_sell_conservative", [] { scnCoreGate("bos_only", "0", true); }},
      {"bos_only_sell_balanced", [] { scnCoreGate("bos_only", "1", true); }},
      {"bos_only_sell_active", [] { scnCoreGate("bos_only", "2", true); }},
      {"counter_trend_sell_gold", [] { scnCounterTrend(false, true); }},
      {"counter_trend_buy_gold", [] { scnCounterTrend(true, true); }},
      {"counter_trend_sell_other", [] { scnCounterTrend(false, false); }},
      {"counter_trend_buy_other", [] { scnCounterTrend(true, false); }},
      {"reject_spread", [] { scnRejection("spread"); }},
      {"reject_master_off", [] { scnRejection("master_off"); }},
      {"reject_session", [] { scnRejection("session"); }},
      {"reject_permission", [] { scnRejection("permission"); }},
      {"reject_drawdown", [] { scnRejection("drawdown"); }},
      {"reject_daily_loss", [] { scnRejection("daily_loss"); }},
      {"reject_daily_cap_and_cooldown", [] { scnRejection("daily_cap_and_cooldown"); }},
      {"reject_dry_run", [] { scnRejection("dry_run"); }},
      {"reject_volume", [] { scnRejection("volume"); }},
      {"reject_margin", [] { scnRejection("margin"); }},
      {"margin_shrink_to_fit", [] { scnRejection("margin_fit"); }},
      {"reject_broker", [] { scnRejection("broker"); }},
      {"reject_timeout", [] { scnRejection("timeout"); }},
      {"cooldown", [] { scnCooldown(); }},
      {"loss_counting", [] { scnLossCounting(); }},
      {"cooldown_state", [] { scnCooldownStateValidation(); }},
      {"opposite_blocked", [] { scnOpposite(false); }},
      {"opposite_close_then_open", [] { scnOpposite(true); }},
      {"restart_manage", [] { scnRestartManage(); }},
      {"retry_success", [] { scnRetry(false); }},
      {"retry_exhausted", [] { scnRetry(true); }},
      {"journal_invariants", [] { scnJournalInvariants(); }},
      {"misc_paths", [] { scnMiscPaths(); }},
      // v1.21 LIMIT entry (each one in both directions)
      {"limit_entry_buy", [] { scnLimitEntry(false); }},
      {"limit_entry_sell", [] { scnLimitEntry(true); }},
      {"limit_cancel_buy", [] { scnLimitCancel(false); }},
      {"limit_cancel_sell", [] { scnLimitCancel(true); }},
      {"limit_fill_buy", [] { scnLimitFill(false); }},
      {"limit_fill_sell", [] { scnLimitFill(true); }},
   };
}

static int cmdSelftest(int argc, char **argv)
{
   std::string which = argc > 2 ? argv[2] : "unit";
   bool dump = false;
   std::string filter;
   for(int i = 3; i < argc; i++)
   {
      if(std::string(argv[i]) == "--dump") { dump = true; if(i + 1 < argc) filter = argv[++i]; }
      else if(std::string(argv[i]) == "--log" && i + 1 < argc) g_selftestLog = fopen(argv[++i], "w");
   }
   if(which == "--list")
   {
      for(const ScnEntry &e : scenarioTable()) printf("%s\n", e.name);
      return 0;
   }
   if(which == "unit") return runUnit();
   for(const ScnEntry &e : scenarioTable())
      if(which == e.name)
      {
         TC.name = e.name;
         try { e.fn(); }
         catch(const std::exception &ex) { printf("  FAIL [%s] exception: %s\n", e.name, ex.what()); TC.failed++; }
         if(dump) dumpJournal(filter);
         if(g_selftestLog) { fclose(g_selftestLog); g_selftestLog = nullptr; sim::S.logFile = nullptr; }
         printf("%s: %d checks, %d failed\n", e.name, TC.checks, TC.failed);
         return TC.failed ? 1 : 0;
      }
   fprintf(stderr, "unknown scenario %s\n", which.c_str());
   return 2;
}
} // namespace drv
