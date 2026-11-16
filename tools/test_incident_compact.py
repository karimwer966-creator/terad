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

# --- v6.6.24: who owns the badge geometry, where the collision scan looks, and what a
# --- silent reader may touch. Text contracts: the header executed as C++ covers the rest.
def body(sig):
    i=h.index(sig); j=h.index('\n}',i)
    return h[i:j]
core=body('void QA_DrawCoreStatus()')
assert 'OBJPROP_XDISTANCE' not in core and 'OBJPROP_CORNER' not in core,\
    'QA_DrawCoreStatus still sets geometry, which undoes the layout on a cached call'
assert 'QA_LayoutBadge(name,full)' in core
layout=body('void QA_LayoutBadge(const string name,const string full)')
assert 'g_qa_badge_x=x; g_qa_badge_y=y;' in layout,'the chosen position is not cached'
assert layout.rindex('OBJPROP_XDISTANCE,x')>layout.index('g_qa_badge_x=x; g_qa_badge_y=y;'),\
    'the position is applied only on a cache miss, so a later caller can move the badge'
assert 'ObjectsTotal(0,0,OBJ_RECTANGLE_LABEL)' in layout,'collision scan is not main-window only'
assert 'iBarShift(_Symbol' not in h,'a display header still queries the terminal for a bar index'
assert 'l[b]==EMPTY_VALUE' in h and 'h[b]==EMPTY_VALUE' in h,'EMPTY_VALUE passes MathIsValidNumber'
clear=body('void QA_ClearTacticalPaint()')
assert clear.index('QSMC_IsReaderSilent()')<clear.index('ObjectDelete'),\
    'a silent reader can still delete the host chart objects'
print('PASS compact badge measurement, panel avoidance, badge ownership and reader safety')
