#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply the v6.6.0 signal-arbitration surgical patch to nadir2.mq5.

The file uses CRLF line endings; every insertion below is written with
\r\n so a diff stays clean. The script is idempotent: it refuses to run
twice (it looks for the QSMC_ARB_PATCH_MARKER).

Usage:  python3 tools/apply_qsmc_arb_patch.py
        python3 tools/apply_qsmc_arb_patch.py --check   (verify only)
"""
import sys, io, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, "nadir2.mq5")
MARK = "// v6.6.0 QSMC_ARB_PATCH_MARKER"

def rd(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()

def wr(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)

def rep(text, old, new, label, count=1):
    """Replace exactly `count` occurrences of old (CRLF-normalised)."""
    o = old.replace("\n", "\r\n")
    n = new.replace("\n", "\r\n")
    c = text.count(o)
    if c != count:
        raise SystemExit("PATCH FAILED [%s]: expected %d occurrence(s), found %d"
                         % (label, count, c))
    return text.replace(o, n)

def main():
    check = "--check" in sys.argv
    t = rd(SRC)
    if MARK in t:
        print("already patched (marker present) - nothing to do")
        return 0
    if check:
        print("not patched yet")
        return 1

    orig = t

    # ------------------------------------------------------------------
    # EDIT 1 - include the subsystem right after the #property block.
    # ------------------------------------------------------------------
    t = rep(t,
"""#property indicator_plots   7
""",
"""#property indicator_plots   7
//+------------------------------------------------------------------+
//| v6.6.0 SIGNAL ARBITRATION LAYER                                  |
//| A strict-OOP arbitration subsystem is pulled in here. It adds    |
//| ONE root object (CQuantumRoot) and routes every signal path      |
//| (CORE / ZRE / RXN / MTF-tactical) through the same gate chain.    |
//| Install the companion folder before compiling:                    |
//|   <data folder>/MQL5/Include/QSMC/*.mqh                           |
//| If the include cannot be resolved, set InpArbEnabled=false and    |
//| the indicator behaves exactly like v6.5.5.                        |
//+------------------------------------------------------------------+
#include <QSMC/QSMC_Root.mqh>
""" + MARK + "\n",
        "EDIT 1 include")

    # ------------------------------------------------------------------
    # EDIT 2 - create the root in OnInit.
    # ------------------------------------------------------------------
    t = rep(t,
"""int OnInit()
{
   AlertDispatcherClear();
""",
"""// v6.6.0: publishes the ZRE zone list into the arbitration layer and
// lets it decide. It is called from AlertDispatcherFinalize(), i.e.
// AFTER ZRE_Update() and RXN_Update(), so the tactical path reads the
// same closed-bar zone state those layers just published - the v6.5.5
// tactical path read nothing at all and could therefore emit a SELL
// inside a support zone (symptom 2 of the review).
void QSMC_ArbiterFeedAndFinalize(const int rates_total,const int closed,
                                 const bool authoritative_pending)
{
CQuantumRoot *arb=QSMC_Root();
if(arb==NULL) return;
if(!InpArbEnabled) return;
if(closed<0 || closed>=ArraySize(g_buf_t)) return;

double atr=(closed<ArraySize(g_atr_buf) && g_atr_buf[closed]>0.0 ? g_atr_buf[closed] : g_atr);
long   spr=(closed<ArraySize(g_buf_spread) ? (long)MathMax(0,g_buf_spread[closed]) : 0);

// 1) refresh the subsystem's own series + build the decision context
arb.Refresh(atr,(double)spr);

// 2) publish the ONE bias the indicator already computed (v6.5.3 D7).
//    H1 is not tracked separately by the host, so it is declared
//    UNKNOWN and removed from the weight sum - an unknown timeframe
//    can never be counted as agreement.
int d1_bias=0;
if(StringFind(g_d1_structure_state,"BULL")>=0)      d1_bias=+1;
else if(StringFind(g_d1_structure_state,"BEAR")>=0) d1_bias=-1;
arb.SetExternalBias(d1_bias,g_htf_bias,0,false);

// 3) publish the ZRE zone list (causal role, strength, flips)
int nz=ArraySize(g_zre_zones);
SQZone zs[];
int cap=(nz>0?nz:1);
if(cap>QSMC_ZONE_MAX) cap=QSMC_ZONE_MAX;
ArrayResize(zs,cap);
int written=0;
for(int i=0;i<nz && written<cap;i++)
  {
   SZREZone z=g_zre_zones[i];
   if(!(z.hi>=z.lo) || !(z.hi>0.0)) continue;
   SQZone s;
   s.valid=true;
   s.lo=z.lo;
   s.hi=z.hi;
   s.birth_role=(z.side==ZRE_SUPPORT ? ZR_SUPPORT : (z.side==ZRE_RESISTANCE ? ZR_RESISTANCE : ZR_NEUTRAL));
   s.role=s.birth_role;
   s.strength=z.strength;
   s.touches=z.touches;
   s.birth_bar=(z.age_bars>=0 && closed>=z.age_bars ? closed-z.age_bars : -1);
   s.birth_time=(s.birth_bar>=0 ? g_buf_t[s.birth_bar] : 0);
   s.flipped=false;
   s.broken_closed=false;
   s.broken_time=0;
   s.retested=false;
   s.sources=z.sources;
   s.state=ZST_ACTIVE;
   if(i<ArraySize(g_zre_status))
     {
      // ZRE already resolves the causal flip from closed bars only.
      s.flipped=g_zre_status[i].flipped;
      ENUM_ZRE_STATE bs=g_zre_status[i].base_state;
      if(bs==ZRE_ST_BROKEN)
        {
         s.broken_closed=true;
         s.broken_time=g_buf_t[closed];
        }
      if(bs==ZRE_ST_FLIPPED) s.flipped=true;
      s.state=(bs==ZRE_ST_BROKEN ? ZST_BROKEN : (bs==ZRE_ST_EXPIRED ? ZST_EXPIRED : ZST_ACTIVE));
     }
   // A deterministic id built on the BIRTH role, so a zone keeps its
   // identity when it flips (a flipped support is still the same level).
   s.id=CZoneRegistry::MakeId(s.birth_role,s.lo,s.hi);
   zs[written]=s;
   written++;
  }
arb.SetZones(zs,written);

// 4) gates + at most ONE alert for this bar. authoritative_pending is
//    true when ZRE/RXN/Core already submitted a candidate, in which
//    case the tactical path is suppressed outright and can never steal
//    the one-alert-per-bar slot.
arb.FinalizeBar(authoritative_pending);
}

int OnInit()
{
AlertDispatcherClear();
// v6.6.0: create the one arbitration root. It is destroyed in OnDeinit.
QSMC_RootCreate(SelectExecutionTF(),300,InpATRPeriod);
""",
        "EDIT 2 OnInit + QSMC_ArbiterFeedAndFinalize")

    # ------------------------------------------------------------------
    # EDIT 3 - destroy the root in OnDeinit.
    # ------------------------------------------------------------------
    t = rep(t,
"""void OnDeinit(const int reason)
{
   IndicatorRelease(h_ema_fast); IndicatorRelease(h_ema_slow);
""",
"""void OnDeinit(const int reason)
{
QSMC_RootDestroy();   // v6.6.0: the arbitration root (RAII + leak report)
IndicatorRelease(h_ema_fast); IndicatorRelease(h_ema_slow);
""",
        "EDIT 3 OnDeinit")

    # ------------------------------------------------------------------
    # EDIT 4 - record the tactical fact instead of alerting on it.
    # ------------------------------------------------------------------
    t = rep(t,
"""   if(g_mtf_sig_time<=0 || g_mtf_sig_time>et) g_mtf_sig_time=et;
""",
"""   if(g_mtf_sig_time<=0 || g_mtf_sig_time>et) g_mtf_sig_time=et;
   // v6.6.0 SYMPTOM 1-4 FIX. The fact is RECORDED here and DECIDED by
   // the arbitration layer at the end of the bar (QSMC_ArbiterFeedAnd
   // Finalize -> CQuantumRoot::FinalizeBar). The v6.5.5 code called
   // FireQuantAlert() at the bottom of this function, which:
   //   - read no zone, no reaction, no room, no cooldown (symptoms 1,2);
   //   - ran before ZRE_Update/RXN_Update, so it could not see the zone
   //     list at all (symptoms 2,3);
   //   - built its dedupe key from g_mtf_sig_time, a value that is
   //     re-anchored to 0 on every PREVIEW bar, so the same signal
   //     alternated between two keys and re-fired (symptom 1);
   //   - printed the word CONFIRMED for a non-authoritative path (R7).
   if(InpArbEnabled && InpArbGateTactical && InpAlertOnMTFExecutionEntry &&
      QSMC_Root()!=NULL)
   {
      STacticalFact _tf;
      _tf.valid=true;
      _tf.bull=bull;
      _tf.closed_confirm=closed_confirm;
      _tf.entry_price=ep;
      _tf.exec_bar_time=et;
      _tf.exec_tf=etf;
      _tf.trigger=trigger;
      _tf.trigger_time=trigger_time;
      _tf.core_owned=core_owned;
      _tf.chase_atr=dist_close_atr;
      QSMC_Root().TacticalObserve(_tf);
   }
""",
        "EDIT 4 tactical observe")

    # ------------------------------------------------------------------
    # EDIT 5 - honest label wording (terminology rule R7).
    # ------------------------------------------------------------------
    t = rep(t,
"""      string chase=(g_mtf_entry_late ? StringFormat(" | LATE (%.1f ATR from close) - wait for retest",dist_close_atr) : "");
""",
"""      string chase=(g_mtf_entry_late ? StringFormat(" | LATE (%.1f ATR from close) - wait for retest",dist_close_atr) : "");
      // v6.6.0 (R7): "CONFIRMED" is reserved for a signal that passed
      // every gate. The closed execution bar is an execution fact, not
      // a trade signal, so the label says TACTICAL-INFO.
      if(InpArbEnabled && InpArbGateTactical) chase+=" | gated by ARB";
""",
        "EDIT 5 label suffix")

    t = rep(t,
"""                    (closed_confirm?"TACTICAL / CONFIRMED":"TACTICAL / PREVIEW"),
""",
"""                    (closed_confirm?"TACTICAL-INFO (exec bar closed)":"TACTICAL / PREVIEW"),
""",
        "EDIT 5b label text")

    # ------------------------------------------------------------------
    # EDIT 6 - delete the direct alert block.
    # ------------------------------------------------------------------
    old_block = """   if(InpAlertOnMTFExecutionEntry)
   {
      string key=id+"|"+state+((g_mtf_sig_time>0 && g_mtf_sig_time!=et) ? "|"+IntegerToString((long)g_mtf_sig_time) : "");
      // one ALERT per (trigger, direction, state) - the old key carried the
      // execution-bar time, so a stable entry re-alerted on every new M5 bar.
      if(key!=g_last_mtf_entry_id)
      {
         // The forming execution-bar PREVIEW is chart-only. Only its closed-bar
         // CONFIRMED state may enter the shared directional-alert claim.
         bool fire=(state=="CONFIRMED");
         g_last_mtf_entry_id=key;
         if(fire)
         {
            g_last_mtf_entry_key=key;
            FireQuantAlert(key,StringFormat("%s %s | TACTICAL / NON-AUTHORITATIVE | MTF %s ENTRY %s @ %.2f | execution %s | institutional confirmation separate",_Symbol,TFName((ENUM_TIMEFRAMES)_Period),bull?"BUY":"SELL",state,ep,TFName(etf)));
         }
      }
   }
"""
    new_block = """   // v6.6.0: this block USED to call FireQuantAlert() directly. That was
   // the source of the reported alert storm: no zone, no reaction, no
   // room, no session and no data-quality check, plus a dedupe key that
   // alternated between two spellings whenever the signal re-armed.
   // The fact is now recorded above (TacticalObserve) and published once
   // per closed bar by the arbitration layer, which applies every gate.
   // The old globals are still maintained so the display is unchanged.
"""
    t = rep(t, old_block, new_block, "EDIT 6 remove direct alert")

    # ------------------------------------------------------------------
    # EDIT 7 - feed + finalize inside AlertDispatcherFinalize.
    # ------------------------------------------------------------------
    t = rep(t,
"""   if(bar_time<=0 || g_alert_finalized_bar_time==bar_time) return;
   g_alert_finalized_bar_time=bar_time;
""",
"""   if(bar_time<=0 || g_alert_finalized_bar_time==bar_time) return;
   g_alert_finalized_bar_time=bar_time;
   // v6.6.0: the arbitration layer runs HERE, after ZRE_Update() and
   // RXN_Update() have refreshed g_zre_zones / g_zre_status, and BEFORE
   // the ZRE/RXN selection below, so an authoritative candidate always
   // keeps the bar to itself. Placed after the once-per-bar guard above,
   // so it is also evaluated exactly once per closed bar.
   // g_alert_candidate_count>0 means ZRE/RXN/Core already submitted a
   // candidate for this exact bar -> the tactical path stands down.
   QSMC_ArbiterFeedAndFinalize(rates_total,closed,g_alert_candidate_count>0);
""",
        "EDIT 7 finalize hook")

    wr(SRC, t)
    print("patched OK: %d -> %d bytes (%+d)" % (len(orig), len(t), len(t)-len(orig)))
    return 0

if __name__ == "__main__":
    sys.exit(main())
