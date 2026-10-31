"""Source-contract checks only; not a substitute for MetaEditor/replay."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'MQL5/Include/QSMC/QSMC_LiquidityValue.mqh').read_text()
MAIN = (ROOT / 'nadir2.mq5').read_text()

class LiquidityValueContract(unittest.TestCase):
    def test_opt_in_and_integration(self):
        self.assertIn('InpEnableLiquidityValue = false', SRC)
        self.assertIn('LV_Update(closed,prev_calculated==0)', MAIN)
        self.assertLess(MAIN.index('   MVP_Update(rates_total,'), MAIN.index('LV_Update(closed,'))
        self.assertIn('LV_Hide();', MAIN)

    def test_snapshot_after_decision(self):
        self.assertLess(SRC.index('else if(g_lv_profile)'), SRC.index('g_lv_val=g_mvp[a].val'))
        self.assertIn('g_lv_last!=g_buf_t[closed-1]', SRC)
        self.assertIn('if(now==g_lv_last) return', SRC)
        self.assertIn('g_mvp_built_time==now', SRC)

    def test_authoritative_equal_pool(self):
        for text in ('parent_pool_availability_bar>=closed', 'availability_bar!=closed',
                     'type=="EQH"', 'type=="EQL"', 'if(!eq) continue',
                     'CONFLICT / TWO-SIDED SWEEP'):
            self.assertIn(text, SRC)

    def test_separate_confirmation_retest_and_risk(self):
        self.assertIn('else if(g_lv_phase==1', SRC)
        self.assertIn('else if(g_lv_phase==2', SRC)
        self.assertIn('reward/risk>=InpTopDownMinRR', SRC)
        self.assertIn('g_lv_age>12', SRC)
        self.assertIn('INVALIDATED / VALUE LOST', SRC)
        self.assertIn('INVALIDATED / STOP', SRC)

    def test_no_execution_authority(self):
        for forbidden in ('OrderSend(', 'CTrade', 'Alert(', 'SendNotification(',
                          'BufBuy[', 'BufSell[', 'g_cf_dir=', 'g_trade_setup.'):
            self.assertNotIn(forbidden, SRC)

if __name__ == '__main__':
    unittest.main()
