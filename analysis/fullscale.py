"""Full-size experiments (the RangeReduce authors' main configuration): one metrics row per run.

Usage:  python3 analysis/fullscale.py [results/fullscale]        (standard-library Python only)

Each run folder <setting>/<system>/ holds the raw logs written by the engine: range_queries.csv (one line per
range query), workload.log (RocksDB statistics and final tree shape) and, for HA-RR, heat.csv (one admission
decision per range query).  Writes <root>/summary.csv and prints a table.
"""
import csv
import pathlib
import re
import statistics
import sys

ENTRY = 128            # bytes per entry
UNIQUE = 8388608       # unique keys inserted
T = 6                  # size ratio
GB = 2 ** 30
SETTINGS = ["pilot_main", "s2_hotcold", "s3_shifting", "s4_hotcold8020"]
NAMES = {"pilot_main": "uniform", "s2_hotcold": "hot/cold", "s3_shifting": "shifting", "s4_hotcold8020": "80/20"}
SYSTEMS = ["RocksDB", "RangeReduce", "HA-RR", "HA-RR_theta2"]


def pct(values, q):
    s = sorted(values)
    k = (len(s) - 1) * q
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def queries(run):
    rows = []
    with open(run / "range_queries.csv") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if len(row) >= 8 and row[1].strip():
                rows.append({"ns": int(row[1]), "read": int(row[2]), "ret": int(row[3]), "wb": int(row[7])})
    return rows


def log_stats(run):
    text = (run / "workload.log").read_text(errors="ignore")
    stats = {}
    for name in ["compact.read.bytes", "compact.write.bytes", "flush.write.bytes",
                 "rangereduce.file.count", "rangereduce.write.bytes"]:
        m = re.findall(rf"rocksdb\.{re.escape(name)}: (\d+)", text)
        stats[name] = int(m[-1]) if m else 0
    m = re.findall(r"Workload Execution Time: (\d+)", text)
    stats["workload_s"] = int(m[-1]) / 1e9 if m else 0
    last = text.rsplit("Level Stats:", 1)[-1]
    levels = [int(b) for _, b in sorted((int(l), b) for l, b in re.findall(r"Level: (\d+), Files: \d+, Size: (\d+) bytes", last))]
    return stats, levels


def debt(levels):
    """Compaction debt as in the RangeReduce paper: bytes that later compactions still have to rewrite."""
    nonzero = [i for i, b in enumerate(levels) if b > 0]
    last = nonzero[-1] if nonzero else 0
    return sum(levels[i] * T * (last - i + 1) for i in range(last)) + levels[last]


def summarise(run):
    q = queries(run)
    lat = [r["ns"] / 1e9 for r in q]
    stats, levels = log_stats(run)
    read = sum(r["read"] for r in q)
    ret = sum(r["ret"] for r in q)
    writes = stats["compact.write.bytes"] + stats["flush.write.bytes"] + stats["rangereduce.write.bytes"]
    row = {
        "queries": len(q),
        "mean_s": statistics.fmean(lat), "p50_s": pct(lat, 0.5), "p95_s": pct(lat, 0.95), "p99_s": pct(lat, 0.99),
        "read_amp": read / ret,
        "writebacks": sum(r["wb"] for r in q),
        "writeback_GB": stats["rangereduce.write.bytes"] / GB,
        "compaction_GB": stats["compact.write.bytes"] / GB,
        "flush_GB": stats["flush.write.bytes"] / GB,
        "total_write_GB": writes / GB,
        "data_movement_GB": (writes + stats["compact.read.bytes"] + read * ENTRY) / GB,
        "space_amp": sum(levels) / (UNIQUE * ENTRY),
        "debt_GB": debt(levels) / GB,
        "run_hours": stats["workload_s"] / 3600,
        "reads_saved_GB": None,
    }
    heat = run / "heat.csv"
    if heat.exists():
        adm = [int(r["admitted"]) for r in csv.DictReader(open(heat))]
        row["admitted"] = sum(adm)
    return row, q


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "results" / "fullscale")
    out = []
    for s in SETTINGS:
        base = None
        for sysname in SYSTEMS:
            run = root / s / sysname
            log = run / "workload.log"
            if not (run / "range_queries.csv").exists() or not log.exists() or "END HERE" not in log.read_text(errors="ignore"):
                continue   # missing or unfinished run
            row, q = summarise(run)
            if sysname == "RocksDB":
                base = q
            if base is not None and sysname != "RocksDB":   # reads saved per byte written back (eta)
                saved = sum(b["read"] - r["read"] for b, r in zip(base, q)) * ENTRY
                row["reads_saved_GB"] = saved / GB
                row["eta"] = saved / (row["writeback_GB"] * GB) if row["writeback_GB"] else None
            out.append({"setting": NAMES[s], "system": sysname, **row})
    cols = list(dict.fromkeys(k for r in out for k in r))
    with open(root / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(f"{r['setting']:9} {r['system']:13} mean {r['mean_s']:.2f}s p95 {r['p95_s']:.2f}s p99 {r['p99_s']:.2f}s "
              f"RA {r['read_amp']:.4f} wb {r['writebacks']:5d} {r['writeback_GB']:5.1f}GB total {r['total_write_GB']:5.1f}GB "
              f"SA {r['space_amp']:.3f} debt {r['debt_GB']:5.2f}GB  {r['run_hours']:.1f}h"
              + (f"  eta {r['eta']:.2f}" if r.get('eta') else "") + (f"  admitted {r['admitted']}" if 'admitted' in r else ""))


if __name__ == "__main__":
    main()
