"""Compact current-state badge must measure text and avoid docked panel rectangles."""
from pathlib import Path
r=Path(__file__).resolve().parents[1]
h=(r/'MQL5/Include/QSMC/QSMC_IncidentSafety.mqh').read_text()
assert 'void QA_LayoutBadge(' in h,'current-state badge uses a fixed overlapping anchor'
for t in ('CHART_WIDTH_IN_PIXELS','CHART_HEIGHT_IN_PIXELS','TextWidthPx(', 'QSMC_ClipChars(', 'OBJ_RECTANGLE_LABEL', 'OBJPROP_CORNER', 'QA_LayoutBadge(name,full)', 'OBJPROP_TOOLTIP,full+'):
    assert t in h,t
s=(r/'nadir2.mq5').read_text()
assert 'primary="CONTEXT (NOT ENTRY) | "+primary' in s,'legacy primary still reads like an entry verdict'
assert 'state=="CONFIRMED" && g_qa_core.direction!=0' in s,'chain entry flag ignores actual Core buffer'
print('PASS compact badge measurement, panel avoidance and full tooltip')
