//+------------------------------------------------------------------+
//|                                                  QSMC_ExecutionRules.mqh
//|                                          QSMC v6.6.24 (2026-11-16)
//|
//| PURE EXECUTION RULES.
//|
//| This file holds the numeric decisions that used to live inline inside
//| QSMC_AutoTrader.mq5:
//|   * the daily-loss floor and the account drawdown floor,
//|   * the consecutive-loss and post-loss-cooldown triggers,
//|   * the session-window arithmetic,
//|   * the twelve RunEntryReview conditions,
//|   * the per-signal retry budget lookup.
//|
//| Every function here is side-effect free: it reads no account, no clock,
//| no terminal global, no file and no log. It takes the numbers and returns
//| the decision. That is the ONLY reason this file exists - it lets
//| tools/test_execution_rules.py compile and execute the exact same code the
//| EA runs, natively, without a terminal. The EA keeps calling these
//| functions, so the tested text IS the shipped text.
//|
//| The functions were extracted from the EA by moving each existing
//| expression verbatim (same comparison, same operand order, same sign
//| convention). Anything the EA still decides from terminal state stays in
//| the EA; only the arithmetic moved.
//|
//| No MQL5 runtime call appears below, so the native harness needs no stub
//| beyond the scalar types (datetime, ulong, string).
//+------------------------------------------------------------------+
#ifndef __QSMC_EXECUTIONRULES_MQH__
#define __QSMC_EXECUTIONRULES_MQH__

//--- RunEntryReview condition indices. These are the same 0..11 the EA's
//--- ReviewName() prints, and they never change (a log line is a contract).
#define QER_R1_CLASS          0
#define QER_R2_ACCOUNT        1
#define QER_R3_TICK_AGE       2
#define QER_R4_SPREAD         3
#define QER_R5_SESSION        4
#define QER_R6_TRADES_TODAY   5
#define QER_R7_OPEN_POSITIONS 6
#define QER_R8_GEOMETRY       7
#define QER_R9_RR_AT_FILL     8
#define QER_R10_STOPS_LEVEL   9
#define QER_R11_RISK_SIZE    10
#define QER_R12_NO_OPPOSITE  11
#define QER_REVIEW_COUNT     12

//--- Size of the per-signal retry table. Eight distinct identities in flight
//--- is far more than InpMaxSignalAgeBars (1) can present at once; the bound
//--- exists so the table can never grow with uptime.
#define QER_RETRY_SLOTS       8

//====================================================================
// 1. DAY / DRAWDOWN BREAKERS
//====================================================================

//--- Server-day index. Both the daily guard and the day-rollover reset key on
//--- this, so it is the one definition of "a new day".
int QER_DayIndex(const datetime t)
  {
   long v=(long)t;
   if(v<0) v=0;
   return (int)(v/86400);
  }

//--- The money stop, bounded by the HARD percentage ceiling.
//---   inp_money <= 0  -> 0.0 (the money stop is off)
//---   base     <= 0  -> the input is returned unchanged (nothing to cap it to)
//--- The money stop WINS over the percentage stop: a fat-fingered input can
//--- make it smaller, never looser than the HARD ceiling.
double QER_DayStopMoney(const double inp_money,const double base,const double hard_pct)
  {
   if(inp_money<=0.0) return 0.0;
   double hard=0.0;
   if(base>0.0) hard=base*hard_pct/100.0;
   if(hard>0.0) return (inp_money<hard ? inp_money : hard);
   return inp_money;
  }

//--- Equity at which the daily guard trips, or 0.0 when nothing can trip it.
//--- A disabled percentage stop stays disabled: it is NEVER mapped to a
//--- ceiling, because "off" must not print as "the loosest allowed value".
double QER_DayFloorEquity(const double base,const double stop_money,const double eff_pct)
  {
   if(base<=0.0) return 0.0;
   if(stop_money>0.0) return base-stop_money;
   if(eff_pct<=0.0) return 0.0;
   return base*(1.0-eff_pct/100.0);
  }

//--- The daily trigger. A floor of 0.0 means "no floor": it cannot trip.
bool QER_DailyTripped(const double floor_eq,const double eq)
  {
   return (floor_eq>0.0 && eq<=floor_eq);
  }

//--- Equity floor for the account drawdown breaker (0.0 = no floor).
double QER_DrawdownFloor(const double ref,const double pct)
  {
   if(ref<=0.0 || pct<=0.0) return 0.0;
   return ref*(1.0-pct/100.0);
  }

bool QER_DrawdownTripped(const double ref,const double pct,const double eq)
  {
   double floor_eq=QER_DrawdownFloor(ref,pct);
   return (floor_eq>0.0 && eq<=floor_eq);
  }

//--- Consecutive losing closes. limit<=0 disables the breaker.
bool QER_LossStreakTripped(const int streak,const int limit)
  {
   if(limit<=0) return false;
   return (streak>=limit);
  }

//--- Post-loss cooldown. The EA finds the most recent close of its own magic
//--- and passes the age of it; this decides. A negative age (clock skew back)
//--- is treated as "just now", which fails SAFE (keeps the cooldown on)
//--- rather than releasing it.
bool QER_CooldownTripped(const bool cooldown_on,const long seconds_since_loss,const int minutes)
  {
   if(!cooldown_on || minutes<=0) return false;
   long window=(long)minutes*60;
   if(seconds_since_loss<0) return true;
   //--- inclusive at the edge: the EA selects the window with
   //--- HistorySelect(now-window, now), which includes a deal stamped exactly
   //--- at `now-window`. The predicate must agree with the query, not tighten it.
   return (seconds_since_loss<=window);
  }

//====================================================================
// 2. SESSION WINDOW
//====================================================================
//--- Server-hour window. start==end means "no window" (the filter is off).
//--- A window may wrap midnight (22 -> 6), which is how an Asia-only or
//--- NY-only mandate is expressed.
bool QER_SessionInside(const int hour,const int start,const int end)
  {
   if(start==end) return true;
   if(start<end)  return (hour>=start && hour<end);
   return (hour>=start || hour<end);
  }

//====================================================================
// 3. THE TWELVE ENTRY-REVIEW CONDITIONS
//====================================================================
//--- R1 CLASS: a class this EA does not allow is REFUSED. It is never
//--- downgraded to a smaller volume and never promoted to a larger one.
bool QER_ClassOk(const bool class_allowed)
  {
   return class_allowed;
  }

//--- R2 ACCOUNT: the account gate returns an empty string when trading is
//--- allowed. Any text at all is a refusal, and the text is the reason.
bool QER_AccountOk(const string env_block)
  {
   return (env_block=="");
  }

//--- R3 TICK AGE: cap<=0 disables the check (documented input).
//--- A negative age (symbol tick ahead of the terminal clock) is not stale.
bool QER_TickAgeOk(const long age_seconds,const int cap_seconds)
  {
   if(cap_seconds<=0) return true;
   return (age_seconds<=cap_seconds);
  }

//--- R4 SPREAD: an absolute cap AND a share-of-stop cap. `share` is written
//--- with the measured fraction for the log line whether or not it is capped.
bool QER_SpreadOk(const double spread_points,const int cap_points,
                  const double stop_points,const double max_frac,double &share)
  {
   share=0.0;
   //--- v6.6.25 (AUD-03 / P1): the spread is a real number of points, so it is
   //--- compared as one. `(int)spread_points<=cap_points` truncated first: a
   //--- 20.9-point spread became 20 and passed a 20-point cap. A quote that is
   //--- not a finite number (no tick yet, or a NaN out of a broken feed) now
   //--- fails closed instead of casting to garbage, and cap_points<=0 disables
   //--- the absolute cap exactly as SpreadOK() in the EA does - a tuning input
   //--- set to 0 must not silently veto every order.
   if(!MathIsValidNumber(spread_points) || spread_points<0.0) return false;
   bool abs_ok=(cap_points<=0 || spread_points<=(double)cap_points);
   bool share_ok=true;
   if(max_frac>0.0 && stop_points>0.0)
     {
      share=spread_points/stop_points;
      share_ok=(share<=max_frac);
     }
   return (abs_ok && share_ok);
  }

//--- R5 SESSION: the review re-uses the same resolver the entry path uses.
bool QER_SessionOk(const bool inside)
  {
   return inside;
  }

//--- R6 TRADES TODAY: max_day<=0 means "unlimited" (documented input).
bool QER_TradesTodayOk(const int today,const int max_day)
  {
   if(max_day<=0) return true;
   return (today<max_day);
  }

//--- R7 OPEN POSITIONS: `max_pos` is already floored at 1 by the EA, so this
//--- is a strict "fewer than the cap" test.
bool QER_OpenPositionsOk(const int open_now,const int max_pos)
  {
   if(max_pos<=0) return false;   // a zero/unknown cap is a refusal, not a pass
   return (open_now<max_pos);
  }

//--- R8 GEOMETRY at the CURRENT price: both levels present and on their side.
bool QER_GeometryOk(const double sl,const double tp,const double price,const bool buy)
  {
   bool shape=(buy ? (sl<price && tp>price) : (sl>price && tp<price));
   return (shape && sl>0.0 && tp>0.0);
  }

//--- R9 RR AT FILL: floor<=0 disables the check. The 1e-9 tolerance absorbs
//--- the double rounding of a reward:risk that lands exactly on the floor.
bool QER_RROk(const double rr,const double floor_rr)
  {
   if(floor_rr<=0.0) return true;
   return (rr+1e-9>=floor_rr);
  }

//--- R10 STOPS LEVEL: delegated to the broker-distance resolver in the EA
//--- (it needs SymbolInfo*), so the review passes that resolver's verdict in.
bool QER_StopsOk(const bool stops_ok)
  {
   return stops_ok;
  }

//--- R11 RISK SIZE: a volume of zero is a refusal. Sizing already refused any
//--- volume below the broker minimum, so no second threshold belongs here.
bool QER_SizeOk(const double lots)
  {
   return (lots>0.0);
  }

//--- R12 NO OPPOSITE: an opposite position of this magic is allowed only when
//--- the operator asked for it to be closed first (InpCloseOnOpposite).
bool QER_OppositeOk(const ulong opposite_ticket,const bool close_on_opposite)
  {
   return (opposite_ticket==0 || close_on_opposite);
  }

//====================================================================
// 4. PER-SIGNAL RETRY BUDGET
//====================================================================
//--- Identity lookup. -1 means "this identity has no budget consumed yet".
//--- The identity string is the same SignalKey() the journal prints, so a
//--- retry row and a fill row can be joined by hand.
int QER_RetryFind(string &keys[],const int n,const string key)
  {
   for(int i=0;i<n;i++)
      if(keys[i]==key) return i;
   return -1;
  }

//--- Is there budget left for one more attempt? max_attempts<1 is treated as
//--- 1: a zero input can never mean "unlimited".
bool QER_RetryAllows(const int used,const int max_attempts)
  {
   int cap=(max_attempts<1 ? 1 : max_attempts);
   return (used<cap);
  }

//--- Slot for a NEW identity: rotate through the table so an old identity is
//--- evicted instead of the table growing without bound.
int QER_RetryNextSlot(const int n,const int cursor)
  {
   if(n<=0) return 0;
   int c=(cursor<0 ? 0 : cursor);
   return (c%n);
  }

#endif
//+------------------------------------------------------------------+
