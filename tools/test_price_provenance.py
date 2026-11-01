"""Price labels must distinguish quote and chronological closed-bar prices."""
from pathlib import Path
r=Path(__file__).resolve().parents[1]
h=(r/'MQL5/Include/QSMC/QSMC_IncidentSafety.mqh').read_text()
assert 'string QA_PriceDescription()' in h,'price source and timestamp absent'
for token in ('SymbolInfoTick(_Symbol,tick)','tick.time_msc','BID=','ASK=','CLOSED[1]=','g_buf_c[closed]','g_buf_t[closed]','quote_age_s=', 'STALE', 'QA_PriceDescription()'):
    assert token in h,token
assert 'QA_InstanceDescription()+"\\n"+QA_PriceDescription()' in h,'not exposed on current verdict'
print('PASS explicit quote and closed-price provenance')
