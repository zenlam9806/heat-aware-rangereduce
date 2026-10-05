"""Writes tables/paired.tex: each system on the same range queries, split by HA-RR's admit/skip decision."""
import csv
import pathlib
import statistics
import sys

RESULTS = pathlib.Path(sys.argv[1]).expanduser()
HEAT = sys.argv[2] if len(sys.argv) > 2 else "heat_rel_1.0"
OUT = pathlib.Path(__file__).resolve().parent.parent / "tables" / "paired.tex"
NAMES = {"rocksdb": "RocksDB", "rangereduce": "RangeReduce", HEAT: "HA-RR (ours)"}
WORKLOADS = [("main_hotcold", "Hot/cold"), ("main_uniform", "Uniform"), ("main_shifting", "Shifting")]


def queries(run):
    rows = list(csv.reader(open(run / "range_queries.csv")))[1:]
    return [(int(r[1]) / 1e6, int(r[2]), int(r[3])) for r in rows if len(r) > 3]


def subset_stats(data, flags, want):
    sel = [d for d, a in zip(data, flags) if a == want]
    if not sel:
        return "--", "--"
    lat = statistics.fmean(x[0] for x in sel)
    ra = sum(x[1] for x in sel) / sum(x[2] for x in sel)
    return f"{lat:.0f}", f"{ra:.3f}"


lines = [r"\begin{tabular}{@{}llrrrr@{}}", r"\toprule",
         r" & & \multicolumn{2}{c}{Admitted} & \multicolumn{2}{c}{Skipped} \\",
         r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}",
         r"Workload & System & ms & RA & ms & RA \\", r"\midrule"]
blocks = []
for wname, label in WORKLOADS:
    wdir = RESULTS / wname
    if not (wdir / HEAT / "heat.csv").exists():
        continue
    flags = [int(r["admitted"]) for r in csv.DictReader(open(wdir / HEAT / "heat.csv"))]
    rows = []
    for i, system in enumerate(["rocksdb", "rangereduce", HEAT]):
        data = queries(wdir / system)
        a_lat, a_ra = subset_stats(data, flags, 1)
        s_lat, s_ra = subset_stats(data, flags, 0)
        head = f"{label} ({sum(flags)}/{len(flags) - sum(flags)})" if i == 0 else ""
        rows.append(f"{head} & {NAMES[system]} & {a_lat} & {a_ra} & {s_lat} & {s_ra} \\\\")
    blocks.append(rows)
for i, rows in enumerate(blocks):
    lines += rows
    lines.append(r"\bottomrule" if i == len(blocks) - 1 else r"\midrule")
lines.append(r"\end{tabular}")
OUT.parent.mkdir(exist_ok=True)
OUT.write_text("\n".join(lines) + "\n")
print(OUT.read_text())
