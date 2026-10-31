"""Integration contracts for the unified migration path; not a terminal test."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'nadir2.mq5').read_text()
HEADER=(ROOT/'MQL5/Include/QSMC/QSMC_UnifiedDecision.mqh').read_text()

def body(name):
    start=MAIN.index(name)
    opening=MAIN.index('{',start)
    depth=1
    for i in range(opening+1,len(MAIN)):
        depth+=(MAIN[i]=='{')-(MAIN[i]=='}')
        if depth==0:return MAIN[opening:i+1]
    raise AssertionError('unclosed function')

class UnifiedContract(unittest.TestCase):
    def test_optin_and_closed_core_only(self):
        self.assertIn('InpUnifiedDecision = false',HEADER)
        self.assertIn('e.availability_time!=boundary',HEADER)
        self.assertIn('e.confirmation_bar!=closed',HEADER)
        self.assertIn('e.confirmation_bar<=e.created_bar',HEADER)
        self.assertIn('if(authority!=1 && authority!=-1) return',HEADER)
        self.assertIn('if(InpUnifiedDecision) return UD_Verdict(closed,why)',MAIN)

    def test_same_snapshot_before_dispatch_and_render(self):
        dispatcher=body('void AlertDispatcherFinalize(const int rates_total)\n')
        self.assertLess(dispatcher.index('UD_Update(closed)'),dispatcher.index('UD_AlertAllows'))
        self.assertEqual(dispatcher.count('UD_AlertAllows(c.source,c.direction)'),3)
        self.assertIn('return source==3 && direction==g_ud.direction',HEADER)
        self.assertIn('arb.FinalizeBar(authoritative_pending || InpUnifiedDecision)',MAIN)
        self.assertIn('if(InpUseFinalResolver || InpUnifiedDecision)',MAIN)
        self.assertIn('(InpUnifiedDecision?g_ud.score:g_alert_primary.score)',MAIN)
        self.assertIn('if(InpUnifiedDecision) head="CONTEXT / "+head',MAIN)

    def test_merges_and_render_budget(self):
        self.assertIn('UD_MergeZones(out,dropped,tail,ctx,h,l)',MAIN)
        self.assertIn('UD_PathDuplicate(i,idx,cnt)',MAIN)
        self.assertIn('if(cnt>=ZRE_MAX_PATHS) continue',MAIN)
        self.assertIn('all[i].touches=ZRE_CountTouchEpisodes',HEADER)
        self.assertIn('if(ZRE_ZoneBefore(all[j],all[i],ctx.close_px)) all[i]=all[j]',HEADER)
        self.assertIn('return aside==bside',HEADER)

    def test_log_and_no_execution_side_effects(self):
        for key in ['Lifecycle|','SignalDebug|','PMI|']:
            self.assertIn('UD_LogAllows("'+key,MAIN)
        self.assertIn('iBarShift(_Symbol,(ENUM_TIMEFRAMES)_Period',HEADER)
        self.assertIn('if(free_slot<0) return false',HEADER)
        for forbidden in ['OrderSend(', 'CTrade', 'Alert(', 'SendNotification(',
                          'BufBuy[', 'BufSell[', 'GlobalVariableSet(']:
            self.assertNotIn(forbidden,HEADER)

if __name__=='__main__':unittest.main()
