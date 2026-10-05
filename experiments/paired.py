"""Compares every system on the same range queries, split by HA-RR's admit/skip decision."""
import csv
import pathlib
import statistics
import sys

wdir = pathlib.Path(sys.argv[1]).expanduser()
heat_name = sys.argv[2] if len(sys.argv) > 2 else "heat_rel_1.0"
flags = [int(r["admitted"]) for r in csv.DictReader(open(wdir / heat_name / "heat.csv"))]


def series(system):
    f = wdir / system / "range_queries.csv"
    rows = list(csv.reader(open(f)))[1:]
    return [(int(r[1]) / 1e6, int(r[2]), int(r[3])) for r in rows if len(r) > 3]


print(f"{wdir.name}: {sum(flags)} admitted, {len(flags) - sum(flags)} skipped by {heat_name}")
print(f"{'system':16s} {'admitted: ms':>13s} {'RA':>6s} {'skipped: ms':>12s} {'RA':>6s}")
for system in ["rocksdb", "rangereduce", heat_name]:
    data = series(system)
    out = []
    for want in (1, 0):
        sel = [d for d, a in zip(data, flags) if a == want]
        lat = statistics.fmean(x[0] for x in sel) if sel else 0
        ra = sum(x[1] for x in sel) / max(1, sum(x[2] for x in sel))
        out += [lat, ra]
    print(f"{system:16s} {out[0]:13.1f} {out[1]:6.3f} {out[2]:12.1f} {out[3]:6.3f}")
