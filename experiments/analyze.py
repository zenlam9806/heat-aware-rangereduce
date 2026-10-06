"""Summarises experiment directories (results/<workload>/<system>/) into one CSV row per run."""
import csv
import json
import pathlib
import re
import statistics
import sys

ENTRY_SIZE = 128
SIZE_RATIO = 6


def percentile(values, q):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def parse_log(path):
    text = path.read_text()
    stats = {}
    for name in ["compact.read.bytes", "compact.write.bytes", "flush.write.bytes",
                 "rangereduce.file.count", "rangereduce.write.bytes"]:
        m = re.findall(rf"rocksdb\.{re.escape(name)}: (\d+)", text)
        stats[name] = int(m[-1]) if m else 0
    for name in ["Workload", "Inserts", "Updates", "RangeQuery"]:
        m = re.findall(rf"{name} Execution Time: (\d+)", text)
        stats[f"{name.lower()}_ns"] = int(m[-1]) if m else 0
    levels = []
    last_block = text.rsplit("Level Stats:", 1)[-1]
    for m in re.finditer(r"Level: (\d+), Files: (\d+), Size: (\d+) bytes, Entries: (\d+)", last_block):
        levels.append({"level": int(m[1]), "files": int(m[2]), "bytes": int(m[3]), "entries": int(m[4])})
    return stats, levels


def compaction_debt(levels, L):
    sizes = [lv["bytes"] for lv in levels] + [0] * max(0, L - len(levels))
    debt = 0
    last = L - 1
    for lvl in range(last):
        debt += sizes[lvl] * SIZE_RATIO * (last - lvl + 1)
    return debt + sizes[last]


def summarise(run_dir, inserts):
    stats, levels = parse_log(run_dir / "workload.log")
    rq_lat, read, returned, rr = [], [], [], 0
    refresh, reset, scan, ran = [], [], [], []
    with open(run_dir / "range_queries.csv") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) < 8:
                continue
            rq_lat.append(int(row[1]) / 1e6)
            read.append(int(row[2]))
            returned.append(int(row[3]))
            refresh.append(int(row[4]) / 1e6)
            reset.append(int(row[5]) / 1e6)
            scan.append(int(row[6]) / 1e6)
            ran.append(int(row[7].strip() or 0))
            rr += ran[-1]
    total_entries = sum(lv["entries"] for lv in levels)
    writes = stats["flush.write.bytes"] + stats["compact.write.bytes"] + stats["rangereduce.write.bytes"]
    rq_read_bytes = sum(read) * ENTRY_SIZE
    heat = {}
    hf = run_dir / "heat.csv"
    if hf.exists():
        rows = list(csv.DictReader(open(hf)))
        admitted = [int(r["admitted"]) for r in rows]
        heat = {"heat_admitted": sum(admitted), "heat_seen": len(rows)}
        if len(admitted) == len(rq_lat):
            adm = [l for l, a in zip(rq_lat, admitted) if a]
            skp = [l for l, a in zip(rq_lat, admitted) if not a]
            heat["lat_admitted_ms"] = statistics.fmean(adm) if adm else 0
            heat["lat_skipped_ms"] = statistics.fmean(skp) if skp else 0
    wb_lat = [l for l, r in zip(rq_lat, ran) if r]
    no_wb_lat = [l for l, r in zip(rq_lat, ran) if not r]
    last_nonempty = max((lv["level"] for lv in levels if lv["bytes"] > 0), default=0)
    return {
        "rq_count": len(rq_lat),
        "rq_mean_ms": statistics.fmean(rq_lat) if rq_lat else 0,
        "rq_p50_ms": percentile(rq_lat, 0.5),
        "rq_p95_ms": percentile(rq_lat, 0.95),
        "rq_p99_ms": percentile(rq_lat, 0.99),
        "rq_entries_read": sum(read),
        "rq_entries_returned": sum(returned),
        "rq_read_amp": (sum(read) / sum(returned)) if sum(returned) else 0,
        "rr_triggered": rr,
        "decision_ms": statistics.fmean(refresh) if refresh else 0,
        "scan_ms": statistics.fmean(scan) if scan else 0,
        "writeback_wait_ms": statistics.fmean(reset) if reset else 0,
        "lat_with_writeback_ms": statistics.fmean(wb_lat) if wb_lat else 0,
        "lat_without_writeback_ms": statistics.fmean(no_wb_lat) if no_wb_lat else 0,
        "flush_write_bytes": stats["flush.write.bytes"],
        "compact_write_bytes": stats["compact.write.bytes"],
        "compact_read_bytes": stats["compact.read.bytes"],
        "rr_write_bytes": stats["rangereduce.write.bytes"],
        "rr_files": stats["rangereduce.file.count"],
        "total_write_bytes": writes,
        "data_movement_bytes": writes + stats["compact.read.bytes"] + rq_read_bytes,
        "db_bytes": sum(lv["bytes"] for lv in levels),
        "db_entries": total_entries,
        "space_amp": total_entries / inserts if inserts else 0,
        "last_level": last_nonempty,
        "levels": json.dumps([lv["bytes"] for lv in levels if lv["level"] <= 6]),
        "workload_s": stats["workload_ns"] / 1e9,
        "rq_total_s": stats["rangequery_ns"] / 1e9,
        "update_total_s": stats["updates_ns"] / 1e9,
        **heat,
    }


def finished(run_dir):
    """A run is complete if run_suite.sh marked it done, or (for archived runs, whose markers were not
    kept) if its per-query log exists and the engine's log reached its final line."""
    if (run_dir / "done").exists():
        return True
    log = run_dir / "workload.log"
    return (run_dir / "range_queries.csv").exists() and log.exists() and "END HERE" in log.read_text(errors="ignore")


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results")
    out_rows = collect(root)
    write_summary(root, out_rows)


def collect(root):
    """Builds one metrics row per finished run directly from the raw run logs."""
    root = pathlib.Path(root)
    out_rows = []
    for wdir in sorted(p for p in root.iterdir() if p.is_dir()):
        gen = wdir / "gen.log"
        m = re.search(r"wrote (\d+) inserts", gen.read_text()) if gen.exists() else None
        inserts = int(m[1]) if m else 0
        runs = {}
        for sdir in sorted(p for p in wdir.iterdir() if p.is_dir()):
            if finished(sdir):
                runs[sdir.name] = summarise(sdir, inserts)
        if not runs:
            continue
        L = max(r["last_level"] for r in runs.values()) + 1
        for name, r in runs.items():
            stats, levels = parse_log(wdir / name / "workload.log")
            r["compaction_debt_bytes"] = compaction_debt(levels, L)
            out_rows.append({"workload": wdir.name, "system": name, **r})
    return out_rows


def write_summary(root, out_rows):
    root = pathlib.Path(root)
    if not out_rows:
        print("no finished runs")
        return
    cols = list(dict.fromkeys(k for r in out_rows for k in r))
    with open(root / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    show = ["workload", "system", "rq_mean_ms", "rq_p95_ms", "rq_read_amp", "rr_triggered",
            "rr_write_bytes", "total_write_bytes", "space_amp", "compaction_debt_bytes", "workload_s"]
    print(",".join(show))
    for r in out_rows:
        print(",".join(f"{r.get(k, 0):.3f}" if isinstance(r.get(k), float) else str(r.get(k, "")) for k in show))


if __name__ == "__main__":
    main()
