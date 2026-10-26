"""Workload specs for the skewed settings, in the authors' own generator format (same sizes as runexp.sh).
hotcold:  range-query start drawn from Normal(0.5, 0.015) - queries concentrate on one hot region.
shifting: same, but the hot region is centred at 0.25, then 0.5, then 0.75 (three equal phases).
Usage: python3 mkspec.py <hotcold|shifting> <inserts> <updates> <range_queries> <out.json>"""
import json, sys
kind, I, U, S, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
E, L = 128, 0.125
key, val = E * L, E * (1 - L)
ins = {"inserts": {"op_count": I, "key": {"uniform": {"len": key}}, "val": {"uniform": {"len": val}}}}


def phase(u, s, mean):
    return {"updates": {"op_count": u, "val": {"uniform": {"len": val}}, "selection": {"uniform": {"min": 0, "max": 1}}},
            "range_queries": {"op_count": s, "selectivity": 0.1, "range_format": "StartEnd",
                              "selection": {"normal": {"mean": mean, "std_dev": 0.015}}}}


def cold(u, s):
    return {"updates": {"op_count": u, "val": {"uniform": {"len": val}}, "selection": {"uniform": {"min": 0, "max": 1}}},
            "range_queries": {"op_count": s, "selectivity": 0.1, "range_format": "StartEnd",
                              "selection": {"uniform": {"min": 0, "max": 1}}}}


if kind == "hotcold8020":
    # 80% of range queries in the hot region, 20% anywhere: the generator has no mixture distribution,
    # so the run is built from short alternating blocks (24 hot queries, then 6 uniform ones).
    blocks = S // 30
    groups, used = [ins], 0
    for b in range(blocks):
        ub = U // blocks if b < blocks - 1 else U - used
        uh = ub * 4 // 5
        groups += [phase(uh, 24, 0.5), cold(ub - uh, 6)]
        used += ub
    sections = [{"groups": groups}]
elif kind == "hotcold":
    sections = [{"groups": [ins, phase(U, S, 0.5)]}]
else:
    sections = [{"groups": [ins] + [phase(U // 3, S // 3, m) for m in (0.25, 0.5, 0.75)]}]
json.dump({"sections": sections}, open(out, "w"), indent=2)
print("wrote", out)
