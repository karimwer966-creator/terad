#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn a chart dump of the host simulator into a picture (SVG).

The engine driver (`smcvp_<tag> render`, `smcvp_<tag> replay --render-at ...`) and
the chart-hygiene driver (`smcvp_hyg_<before|after> picture ...`) write the chart
the MQL5 code left behind as JSON: the candles of a window and every object the
program owns, with the geometry, colour, text and tooltip it gave them. This
tool draws that JSON - no object is added or moved - so a reviewer can LOOK at
what the code drew without a terminal. The price axis is stretched to hold the
objects of the window shown (a far target must not fall off the picture); an
object that lies further back than the first candle shown, or still outside the
price range, is counted in the heading.

    python3 tools/smcvp_chart_svg.py render IN.json OUT.svg [--title TEXT]
                                     [--width 1500] [--height 820] [--right-bars 36] [--left-bars 0]

What the picture is and is not
  * It is the object list of a host-compiled run of the real MQL5 text against a
    chart-object simulator, drawn at about the usual M15 zoom (8 px per bar).
  * It is NOT a MetaTrader screenshot. Fonts, anti-aliasing, the price scale and
    the exact pixel width of a caption differ in the terminal. An arrow object is
    drawn as a plain triangle whatever its arrow code.

Pure standard library. Colours are MQL5 integers (0x00BBGGRR).
"""
from __future__ import print_function

import argparse
import bisect
import io
import json
import math
import sys
from xml.sax.saxutils import escape

OBJ_VLINE, OBJ_HLINE, OBJ_TREND, OBJ_RECTANGLE, OBJ_ARROW = 0, 1, 2, 16, 22
OBJ_TEXT, OBJ_LABEL, OBJ_RECTANGLE_LABEL = 100, 101, 110

# ENUM_ANCHOR_POINT -> (horizontal, vertical)
ANCHORS = {0: ("start", "top"), 1: ("start", "middle"), 2: ("start", "bottom"), 3: ("middle", "bottom"),
           4: ("end", "bottom"), 5: ("end", "middle"), 6: ("end", "top"), 7: ("middle", "top"), 8: ("middle", "middle")}
DASHES = {0: "", 1: "7 4", 2: "2 3", 3: "8 3 2 3", 4: "8 3 2 3 2 3"}

BG, GRID, AXIS = "#11151a", "#1d242c", "#8a949e"
CANDLE_UP, CANDLE_DOWN = "#4f6f64", "#7a4a47"


def mql_color(value, fallback="#c0c0c0"):
    """0x00BBGGRR -> #rrggbb; clrNONE (-1 / 0xFFFFFFFF) -> none."""
    value = int(value)
    if value < 0 or value == 0xFFFFFFFF:
        return "none"
    if value > 0xFFFFFF:
        return fallback
    return "#%02x%02x%02x" % (value & 255, (value >> 8) & 255, (value >> 16) & 255)


def nice_step(span, target):
    """A 1-2-5 step that gives about `target` grid lines over `span`."""
    if span <= 0:
        return 1.0
    raw = span / float(target)
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if m * mag >= raw:
            return m * mag
    return 10 * mag


def clock(t):
    """UTC 'MM-DD HH:MM' of a POSIX time, without importing time zones."""
    days, rem = divmod(int(t), 86400)
    hh, mm = divmod(rem // 60, 60)
    # civil-from-days (Howard Hinnant)
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    return "%02d-%02d %02d:%02d" % (month, day, hh, mm)


def render(doc, width=1500, height=820, right_bars=36, title=None, prefix=None, left_bars=0):
    candles = doc["candles"]
    objects = [o for o in doc["objects"] if prefix is None or o["name"].startswith(prefix)]
    if not candles:
        raise ValueError("the dump holds no candles")
    times = [c[0] for c in candles]
    n = len(times)
    lo = min(c[3] for c in candles)
    hi = max(c[2] for c in candles)
    # The price axis holds the candles AND the objects that lie inside this time window, up to
    # twice the candles' own range (one far level must not flatten the chart). An object that is
    # further back than the first candle shown, or still outside the price range, is not drawn
    # here - it is counted in the heading instead, so the object total stays explained.
    span = (hi - lo) or 1.0
    priced = [o for o in objects if o["type"] in (OBJ_TREND, OBJ_HLINE, OBJ_RECTANGLE, OBJ_ARROW, OBJ_TEXT)]

    def in_window(o):
        if o["type"] == OBJ_HLINE:
            return True
        if o["type"] in (OBJ_TREND, OBJ_RECTANGLE):
            return max(o["t1"], o["t2"]) >= times[0]
        return o["t1"] >= times[0]

    def prices_of(o):
        return (o["p1"], o["p2"]) if o["type"] in (OBJ_TREND, OBJ_RECTANGLE) else (o["p1"],)

    shown = [o for o in priced if in_window(o)]
    further_back = len(priced) - len(shown)
    floor, ceiling = lo - 0.5 * span, hi + 0.5 * span
    outside = sum(1 for o in shown if max(prices_of(o)) < floor or min(prices_of(o)) > ceiling)
    prices = [p for o in shown for p in prices_of(o)]
    if prices:
        lo = max(floor, min(lo, min(prices)))
        hi = min(ceiling, max(hi, max(prices)))
    pad = (hi - lo) * 0.07 or 1.0
    lo, hi = lo - pad, hi + pad
    left, right, top, bottom = 8.0, width - 66.0, 28.0, height - 24.0
    step = (right - left) / float(left_bars + n + right_bars)

    def bar_pos(t):
        if t >= times[-1]:
            return left_bars + n - 1 + (t - times[-1]) / 900.0
        if t <= times[0]:
            return left_bars - (times[0] - t) / 900.0
        return left_bars + bisect.bisect_right(times, t) - 1

    def x_of(t):
        return left + (bar_pos(t) + 0.5) * step

    def y_of(price):
        return top + (hi - price) / (hi - lo) * (bottom - top)

    out = []
    add = out.append
    add('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'font-family="DejaVu Sans, Verdana, Arial, sans-serif">' % (width, height, width, height))
    add('<defs><clipPath id="plot"><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f"/></clipPath></defs>'
        % (left, top, right - left, bottom - top))
    add('<rect width="%d" height="%d" fill="%s"/>' % (width, height, BG))

    # price grid
    pstep = nice_step(hi - lo, 9)
    level = (int(lo / pstep) + 1) * pstep
    while level < hi:
        y = y_of(level)
        add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>' % (left, y, right, y, GRID))
        label = "%.*f" % (max(0, int(math.ceil(-math.log10(pstep)))), level)
        add('<text x="%.1f" y="%.1f" fill="%s" font-size="10">%s</text>' % (right + 5, y + 3.5, AXIS, label))
        level += pstep
    # time grid
    every = max(1, int(round(110.0 / step)))
    for k in range(0, n, every):
        x = left + (left_bars + k + 0.5) * step
        add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>' % (x, top, x, bottom, GRID))
        add('<text x="%.1f" y="%.1f" fill="%s" font-size="10" text-anchor="middle">%s</text>'
            % (x, bottom + 14, AXIS, clock(times[k])))
    add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" stroke="%s" stroke-width="1"/>'
        % (left, top, right - left, bottom - top, GRID))

    def tip(o):
        text = o.get("tip") or o.get("text") or ""
        return "<title>%s</title>" % escape(o["name"] + (": " + text if text else ""))

    add('<g clip-path="url(#plot)">')
    # filled boxes first (the terminal draws them behind the candles)
    for o in objects:
        if o["type"] != OBJ_RECTANGLE:
            continue
        x1, x2 = sorted((x_of(o["t1"]), x_of(o["t2"])))
        y1, y2 = sorted((y_of(o["p1"]), y_of(o["p2"])))
        col = mql_color(o["color"])
        add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity="%s" stroke="%s" stroke-width="1">%s</rect>'
            % (x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1), col if o.get("fill") else "none", "0.30", col, tip(o)))
    # candles
    body = max(1.0, step * 0.62)
    for k, (t, o_, h_, l_, c_) in enumerate(candles):
        x = left + (left_bars + k + 0.5) * step
        col = CANDLE_UP if c_ >= o_ else CANDLE_DOWN
        add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>' % (x, y_of(h_), x, y_of(l_), col))
        y1, y2 = sorted((y_of(o_), y_of(c_)))
        add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (x - body / 2, y1, body, max(1.0, y2 - y1), col))
    # lines
    for o in objects:
        if o["type"] not in (OBJ_TREND, OBJ_HLINE, OBJ_VLINE):
            continue
        col = mql_color(o["color"])
        if o["type"] == OBJ_HLINE:
            x1, x2, y1, y2 = left, right, y_of(o["p1"]), y_of(o["p1"])
        elif o["type"] == OBJ_VLINE:
            x1 = x2 = x_of(o["t1"])
            y1, y2 = top, bottom
        else:
            x1, x2, y1, y2 = x_of(o["t1"]), x_of(o["t2"]), y_of(o["p1"]), y_of(o["p2"])
        dash = DASHES.get(int(o.get("style", 0)), "")
        add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%d"%s>%s</line>'
            % (x1, y1, x2, y2, col, max(1, int(o.get("width", 1))), (' stroke-dasharray="%s"' % dash) if dash else "", tip(o)))
    # arrows
    for o in objects:
        if o["type"] != OBJ_ARROW:
            continue
        x, y = x_of(o["t1"]), y_of(o["p1"])
        add('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s">%s</polygon>'
            % (x, y - 6, x - 5, y + 4, x + 5, y + 4, mql_color(o["color"]), tip(o)))
    # captions
    for o in objects:
        if o["type"] != OBJ_TEXT or not o.get("text"):
            continue
        size = max(6, int(o.get("size", 8))) * 1.3
        horiz, vert = ANCHORS.get(int(o.get("anchor", 0)), ("start", "top"))
        x, y = x_of(o["t1"]), y_of(o["p1"])
        y += {"top": size * 0.86, "middle": size * 0.34, "bottom": -size * 0.22}[vert]
        add('<text x="%.1f" y="%.1f" fill="%s" font-size="%.1f" text-anchor="%s">%s%s</text>'
            % (x, y, mql_color(o["color"]), size, horiz, escape(o["text"]), tip(o)))
    add("</g>")

    # the dashboard: pixel-anchored, upper-left corner
    for o in objects:
        if o["type"] != OBJ_RECTANGLE_LABEL:
            continue
        add('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" fill-opacity="0.92" stroke="%s" stroke-width="1"/>'
            % (o["x"], o["y"], o["w"], o["h"], mql_color(o.get("bg", 0), "#000000"), mql_color(o["color"], "#696969")))
    for o in objects:
        if o["type"] != OBJ_LABEL or not o.get("text"):
            continue
        size = max(6, int(o.get("size", 8))) * 1.3
        add('<text x="%d" y="%.1f" fill="%s" font-size="%.1f" font-family="DejaVu Sans Mono, Consolas, monospace" '
            'xml:space="preserve">%s</text>' % (o["x"], o["y"] + size * 0.86, mql_color(o["color"]), size, escape(o["text"])))

    heading = title or doc.get("title") or ""
    counted = len(objects)
    notes = ([("%d further back than this window" % further_back)] if further_back else []) + \
            ([("%d beyond the price range shown" % outside)] if outside else [])
    count_text = "%d chart objects" % counted + ((" (%s)" % ", ".join(notes)) if notes else "")
    add('<text x="%.1f" y="18" fill="#d5dbe1" font-size="13">%s</text>'
        % (left, escape((heading + "   |   " if heading else "") + count_text)))
    add('<text x="%.1f" y="18" fill="%s" font-size="10" text-anchor="end">host simulation of the MQL5 source - not a MetaTrader screenshot</text>'
        % (right, AXIS))
    add("</svg>")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("render", help="draw one chart dump")
    r.add_argument("src")
    r.add_argument("dst")
    r.add_argument("--title")
    r.add_argument("--width", type=int, default=1500)
    r.add_argument("--height", type=int, default=820)
    r.add_argument("--right-bars", type=int, default=36)
    r.add_argument("--left-bars", type=int, default=0, help="empty bars before the first candle (room for centred captions)")
    r.add_argument("--prefix", help="draw only the objects whose name starts with this")
    args = ap.parse_args(argv)
    if args.cmd != "render":
        ap.print_help()
        return 2
    with io.open(args.src, encoding="utf-8") as fh:
        doc = json.load(fh)
    svg = render(doc, args.width, args.height, args.right_bars, args.title, args.prefix, args.left_bars)
    with io.open(args.dst, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print("%s: %d candles, %d objects -> %s" % (args.src, len(doc["candles"]), len(doc["objects"]), args.dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
