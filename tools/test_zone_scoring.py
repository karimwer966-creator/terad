#!/usr/bin/env python3
"""Independent reference checks for the documented ZoneScorer model."""

MISS_HTF, MISS_ROOM, MISS_SPREAD = 1, 2, 4


def score(*, strength, touches, distance, room, htf, spread):
    missing = 0
    htf_pts = 0
    if htf == 0:
        missing |= MISS_HTF
    else:
        htf_pts = 12 if htf > 0 else -12
    structural = 25*max(0., min(1., strength/100.))
    freshness = 15 if touches <= 1 else (11 if touches == 2 else (6 if touches <= 4 else 0))
    dist_pts = 20*max(0., min(1., 1-distance/2.5))
    room_pts = 0
    if room < 0:
        missing |= MISS_ROOM
    else:
        room_pts = 15*max(0., min(1., room/2.5))
    spread_pts = 0
    if spread < 0:
        missing |= MISS_SPREAD
    else:
        spread_pts = 13*max(0., min(1., 1-spread/.15))
    return round(max(0., min(100., htf_pts+structural+freshness+dist_pts+room_pts+spread_pts))), missing


def valid(zone_valid=True, role="support", dir=1, state="active", broken=False,
          flipped=False, retested=False, strength=80, distance=0., atr=1.):
    if not zone_valid or role not in ("support", "resistance") or state == "expired":
        return False
    if state not in ("active", "touched", "broken", "flipped"):
        return False
    if (broken or state in ("broken", "flipped")) and not (flipped and retested):
        return False
    if (dir > 0 and role != "support") or (dir < 0 and role != "resistance"):
        return False
    return atr > 0 and 0 <= distance <= 2.5 and strength >= 1


base, missing = score(strength=80, touches=2, distance=0., room=2., htf=1, spread=.02)
check = []
check.append((base == 86 and missing == 0, "aligned zone score matches factor table"))
check.append((score(strength=80, touches=2, distance=2.5, room=2., htf=1, spread=.02)[0] < base,
              "distance penalty is monotonic"))
check.append((score(strength=80, touches=2, distance=0., room=.5, htf=1, spread=.02)[0] < base,
              "limited room reduces rank"))
check.append((score(strength=80, touches=2, distance=0., room=2., htf=1, spread=.2)[0] < base,
              "wide spread reduces rank"))
check.append((score(strength=80, touches=2, distance=0., room=-1., htf=0, spread=-1.)[1] ==
                 (MISS_HTF|MISS_ROOM|MISS_SPREAD), "missing inputs are explicit"))
check.append((valid() and not valid(role="support", dir=-1), "role mismatch is hard rejection"))
check.append((not valid(broken=True) and not valid(state="broken") and
               valid(broken=True, state="flipped", flipped=True, retested=True),
              "closed invalidation requires a confirmed flip/retest"))
check.append((not valid(distance=2.6), "out-of-reach zone fails hard gate"))

for passed, name in check:
    print(("PASS" if passed else "FAIL")+"  "+name)
if not all(passed for passed, _ in check):
    raise SystemExit("zone scoring contract failure")
print("Zone-scoring checks passed; rank is not probability.")
