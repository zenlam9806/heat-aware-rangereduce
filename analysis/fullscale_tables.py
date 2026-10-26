"""LaTeX tables for the full-size experiments, computed from the raw logs (standard-library Python only).

Usage:  python3 analysis/fullscale_tables.py [results/fullscale] [output_dir]
Writes  fullscale_main.tex    every metric for every run
        fullscale_paired.tex  the same queries on all systems, split by HA-RR's admit/skip decision
and prints the numbers used in the text.
"""
import csv
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fullscale as fs  # noqa: E402

ROOT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "results" / "fullscale"
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT
OUT.mkdir(parents=True, exist_ok=True)
SHOW = {"RocksDB": "RocksDB", "RangeReduce": "RangeReduce", "HA-RR": "HA-RR", "HA-RR_theta2": "HA-RR, $\\theta$=2"}


def done(run):
    log = run / "workload.log"
    return (run / "range_queries.csv").exists() and log.exists() and "END HERE" in log.read_text(errors="ignore")


runs = {}
for s in fs.SETTINGS:
    for n in fs.SYSTEMS:
        if done(ROOT / s / n):
            runs[(s, n)] = fs.summarise(ROOT / s / n)
    if (s, "RocksDB") in runs:
        base = runs[(s, "RocksDB")][1]
        for n in fs.SYSTEMS:
            if n != "RocksDB" and (s, n) in runs:
                row, q = runs[(s, n)]
                saved = sum(b["read"] - r["read"] for b, r in zip(base, q)) * fs.ENTRY
                row["eta"] = saved / (row["writeback_GB"] * fs.GB) if row["writeback_GB"] else None

# Table 1: all metrics
lines = [r"\begin{tabular}{llrrrrrrrrrrrr}", r"\toprule",
         r"Workload & System & Mean & P50 & P95 & P99 & RA & Write- & Write-back & Total & $\eta$ & SA & Debt & Admitted \\",
         r" & & (s) & (s) & (s) & (s) & & backs & (GB) & writes (GB) & & & (GB) & \\", r"\midrule"]
for s in fs.SETTINGS:
    first = True
    for n in fs.SYSTEMS:
        if (s, n) not in runs:
            continue
        r = runs[(s, n)][0]
        eta = f"{r['eta']:.2f}" if r.get("eta") else "--"
        adm = f"{r['admitted']:,}" if "admitted" in r else "--"
        lines.append(f"{fs.NAMES[s] if first else ''} & {SHOW[n]} & {r['mean_s']:.2f} & {r['p50_s']:.2f} & {r['p95_s']:.2f} & "
                     f"{r['p99_s']:.2f} & {r['read_amp']:.3f} & {r['writebacks']:,} & {r['writeback_GB']:.1f} & "
                     f"{r['total_write_GB']:.1f} & {eta} & {r['space_amp']:.2f} & {r['debt_GB']:.1f} & {adm} \\\\")
        first = False
    lines.append(r"\midrule" if s != fs.SETTINGS[-1] else r"\bottomrule")
lines.append(r"\end{tabular}")
(OUT / "fullscale_main.tex").write_text("\n".join(lines) + "\n")

# Table 2: identical queries split by HA-RR's decision
lines = [r"\begin{tabular}{lrrrrrrrr}", r"\toprule",
         r"Workload, decision & Queries & Mean, RocksDB (s) & Mean, RR (s) & Mean, HA-RR (s) & RA, RR & RA, HA-RR & "
         r"Write-backs, RR & Write-backs, HA-RR \\", r"\midrule"]
print("paired split (queries, mean latency RocksDB/RR/HA-RR, RA RR/HA-RR, write-backs RR/HA-RR)")
for s in fs.SETTINGS:
    if not all((s, n) in runs for n in ("RocksDB", "RangeReduce", "HA-RR")):
        continue
    adm = [int(r["admitted"]) for r in csv.DictReader(open(ROOT / s / "HA-RR" / "heat.csv"))]
    q = {n: runs[(s, n)][1] for n in ("RocksDB", "RangeReduce", "HA-RR")}
    for label, want in (("admitted", 1), ("skipped", 0)):
        idx = [i for i, a in enumerate(adm) if a == want]
        if not idx:
            continue
        lat = {n: statistics.fmean(q[n][i]["ns"] for i in idx) / 1e9 for n in q}
        ra = {n: sum(q[n][i]["read"] for i in idx) / sum(q[n][i]["ret"] for i in idx) for n in q}
        wb = {n: sum(q[n][i]["wb"] for i in idx) for n in q}
        print(f"  {fs.NAMES[s]:9} {label:8} {len(idx):5}  {lat['RocksDB']:.2f} {lat['RangeReduce']:.2f} {lat['HA-RR']:.2f}"
              f"  {ra['RangeReduce']:.3f} {ra['HA-RR']:.3f}  {wb['RangeReduce']} {wb['HA-RR']}")
        lines.append(f"{fs.NAMES[s]}, {label} & {len(idx):,} & {lat['RocksDB']:.2f} & {lat['RangeReduce']:.2f} & "
                     f"{lat['HA-RR']:.2f} & {ra['RangeReduce']:.3f} & {ra['HA-RR']:.3f} & {wb['RangeReduce']:,} & {wb['HA-RR']:,} \\\\")
lines += [r"\bottomrule", r"\end{tabular}"]
(OUT / "fullscale_paired.tex").write_text("\n".join(lines) + "\n")

# Numbers quoted in the text
print("relative to RocksDB / RangeReduce")
for s in fs.SETTINGS:
    if (s, "RocksDB") not in runs:
        continue
    b = runs[(s, "RocksDB")][0]
    rr = runs.get((s, "RangeReduce"), [None])[0]
    for n in fs.SYSTEMS[1:]:
        if (s, n) not in runs:
            continue
        r = runs[(s, n)][0]
        ch = lambda k, ref: 100 * (r[k] / ref[k] - 1) if ref and ref[k] else float("nan")  # noqa: E731
        print(f"  {fs.NAMES[s]:9} {n:13} vs RocksDB: mean {ch('mean_s', b):+.1f}% p95 {ch('p95_s', b):+.1f}% "
              f"RA {ch('read_amp', b):+.1f}% SA {ch('space_amp', b):+.1f}% debt {ch('debt_GB', b):+.1f}% "
              f"writes {ch('total_write_GB', b):+.1f}% movement {ch('data_movement_GB', b):+.1f}%")
        if n != "RangeReduce" and rr:
            print(f"  {'':9} {'':13} vs RangeReduce: mean {ch('mean_s', rr):+.1f}% p50 {ch('p50_s', rr):+.1f}% "
                  f"p95 {ch('p95_s', rr):+.1f}% p99 {ch('p99_s', rr):+.1f}% wb {ch('writebacks', rr):+.1f}% "
                  f"wbGB {ch('writeback_GB', rr):+.1f}% writes {ch('total_write_GB', rr):+.1f}% "
                  f"SA {ch('space_amp', rr):+.1f}% debt {ch('debt_GB', rr):+.1f}% hours {ch('run_hours', rr):+.1f}%")
print("wrote", OUT / "fullscale_main.tex", OUT / "fullscale_paired.tex")
