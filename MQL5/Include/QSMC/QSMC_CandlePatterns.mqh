//+------------------------------------------------------------------+
//|                                                 QSMC_CandlePatterns.mqh
//|                                          QSMC v6.6.24 (2026-11-16)
//|
//| Pure two-bar reversal geometry, shared by CReactionDetector and by the
//| native harness that executes these predicates.
//|
//| WHY THIS FILE EXISTS
//| Two of the four named reversal patterns in QSMC_Reaction.mqh were
//| ALGEBRAICALLY UNSATISFIABLE in v6.6.23, so they could never contribute
//| candle evidence:
//|
//|   piercing   required  r_c > p_o  AND  r_c < (p_o+p_c)/2
//|   dark cloud required  r_c < p_o  AND  r_c > (p_o+p_c)/2
//|
//| Both are preceded by a condition that orders the midpoint against p_o the
//| other way (piercing needs a BEARISH prior bar, so its midpoint is BELOW
//| p_o; dark cloud needs a BULLISH prior bar, so its midpoint is ABOVE p_o).
//| The two inequalities therefore contradict each other for every possible
//| input: the pattern was dead code, and the detector silently offered three
//| named reversals instead of four.
//|
//| The predicates live here, side-effect free, so tools/test_candle_patterns.py
//| can compile and execute them and can also assert that the OLD expression
//| was unsatisfiable - the regression cannot come back unnoticed.
//|
//| No MQL5 runtime call appears below: the native harness needs no stub.
//+------------------------------------------------------------------+
#ifndef __QSMC_CANDLEPATTERNS_MQH__
#define __QSMC_CANDLEPATTERNS_MQH__

//--- Piercing line - a BULLISH reversal after a bearish bar.
//---   * the prior bar is bearish                    (p_c < p_o)
//---   * the bar opens below the prior close         (r_o < p_c)
//---   * it closes bullishly                          (r_c > r_o)
//---   * above the MIDPOINT of the prior real body    (r_c > (p_o+p_c)/2)
//---   * but not above the prior open                 (r_c < p_o)
//--- The last two are the definition of a partial recovery: enough to reject
//--- the prior supply, not enough to be an engulfing bar (which is its own
//--- pattern, tested separately).
bool QCP_Piercing(const double p_o,const double p_c,
                  const double r_o,const double r_c)
  {
   bool prior_bearish=(p_c<p_o);
   bool opens_below_prior_close=(r_o<p_c);
   bool closes_up=(r_c>r_o);
   double mid=(p_o+p_c)*0.5;
   bool above_mid=(r_c>mid);
   bool below_prior_open=(r_c<p_o);
   return (prior_bearish && opens_below_prior_close && closes_up &&
           above_mid && below_prior_open);
  }

//--- Dark cloud cover - a BEARISH reversal after a bullish bar.
//---   * the prior bar is bullish                     (p_c > p_o)
//---   * the bar opens above the prior close          (r_o > p_c)
//---   * it closes bearishly                          (r_c < r_o)
//---   * below the MIDPOINT of the prior real body    (r_c < (p_o+p_c)/2)
//---   * but not below the prior open                 (r_c > p_o)
bool QCP_DarkCloud(const double p_o,const double p_c,
                   const double r_o,const double r_c)
  {
   bool prior_bullish=(p_c>p_o);
   bool opens_above_prior_close=(r_o>p_c);
   bool closes_down=(r_c<r_o);
   double mid=(p_o+p_c)*0.5;
   bool below_mid=(r_c<mid);
   bool above_prior_open=(r_c>p_o);
   return (prior_bullish && opens_above_prior_close && closes_down &&
           below_mid && above_prior_open);
  }

#endif
//+------------------------------------------------------------------+
