"""Recomputes every derived number quoted in the report from the raw results in this repository.

Usage:  python3 analysis/report_numbers.py [results_dir]      (default: results/ next to this folder)
Only the Python standard library is needed. Each block names the table or section of the report it checks.
MB = 2^20 bytes, as in the report.
"""
import csv
import math
import pathlib
import statistics as st
import sys

RES = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "results"
MB = 2 ** 20
T975_DF4 = 2.776  # Student's t, 95% two-sided, 4 degrees of freedom
S = {r["workload"] + "/" + r["system"]: r for r in csv.DictReader(open(RES / "summary.csv"))}
SYS = ["rocksdb", "rangereduce", "heat_rel_1.0"]
NAME = {"rocksdb": "RocksDB", "rangereduce": "RangeReduce", "heat_rel_1.0": "HA-RR"}


def v(w, s, k):
    return float(S[f"{w}/{s}"][k])


def pct(a, b):
    return 100 * (a / b - 1)


def efficiency(w, s):
    """Bytes of range-query reads saved relative to RocksDB per byte written back (128-byte entries)."""
    wb = v(w, s, "rr_write_bytes")
    return (v(w, "rocksdb", "rq_entries_read") - v(w, s, "rq_entries_read")) * 128 / wb if wb else None


def column(rows, i):
    return [r[i] for r in rows]


print("== Table III: main results (one run per workload)")
for w in ["main_uniform", "main_hotcold", "main_shifting"]:
    for s in SYS:
        print(f"{w:14} {NAME[s]:12} mean {v(w, s, 'rq_mean_ms'):5.0f} ms  P95 {v(w, s, 'rq_p95_ms'):5.0f} ms  "
              f"RA {v(w, s, 'rq_read_amp'):.3f}  write-back {v(w, s, 'rr_write_bytes') / MB:4.0f} MB  "
              f"total writes {v(w, s, 'total_write_bytes') / MB:5.0f} MB  SA {v(w, s, 'space_amp'):.3f}  "
              f"debt {v(w, s, 'compaction_debt_bytes') / MB:4.0f} MB  efficiency "
              f"{'-' if efficiency(w, s) is None else format(efficiency(w, s), '.2f')}")

print("\n== Tables I and VI: hot/cold repeated five times (mean +- SD)")
reps = [f"rep5_r{i}" for i in range(1, 6)]
metrics = [("write-back MB", "rr_write_bytes", MB), ("P95 ms", "rq_p95_ms", 1), ("mean ms", "rq_mean_ms", 1),
           ("median ms", "rq_p50_ms", 1), ("read amp", "rq_read_amp", 1), ("space amp", "space_amp", 1),
           ("debt MB", "compaction_debt_bytes", MB), ("total writes MB", "total_write_bytes", MB),
           ("data movement MB", "data_movement_bytes", MB)]
for label, key, div in metrics:
    line = []
    for s in SYS:
        xs = [v(w, s, key) / div for w in reps]
        line.append(f"{NAME[s]} {st.mean(xs):8.3f} +- {st.stdev(xs):6.3f}")
    print(f"{label:17} " + " | ".join(line))
for s in ["rangereduce", "heat_rel_1.0"]:
    xs = [efficiency(w, s) for w in reps]
    print(f"{'reads saved/byte':17} {NAME[s]} {st.mean(xs):.2f} +- {st.stdev(xs):.2f}")

print("\n== Section IV 'Repeatability': per-run change of HA-RR vs RangeReduce and paired 95% CIs")
for label, key in [("write-back", "rr_write_bytes"), ("P95", "rq_p95_ms"), ("mean", "rq_mean_ms"), ("median", "rq_p50_ms")]:
    d = [pct(v(w, "heat_rel_1.0", key), v(w, "rangereduce", key)) for w in reps]
    m, sd = st.mean(d), st.stdev(d)
    h = T975_DF4 * sd / math.sqrt(5)
    print(f"{label:10} per run {[round(x, 1) for x in d]}  mean {m:+.1f}%  95% CI [{m - h:+.1f}%, {m + h:+.1f}%]")

print("\n== Table IV: change relative to RocksDB (means of the five hot/cold runs)")
for label, key in [("compaction debt", "compaction_debt_bytes"), ("space amp", "space_amp"), ("read amp", "rq_read_amp"),
                   ("mean latency", "rq_mean_ms"), ("P95 latency", "rq_p95_ms"), ("total writes", "total_write_bytes"),
                   ("data movement", "data_movement_bytes")]:
    base = st.mean(v(w, "rocksdb", key) for w in reps)
    print(f"{label:16} " + "  ".join(f"{NAME[s]} {pct(st.mean(v(w, s, key) for w in reps), base):+.1f}%"
                                      for s in ["rangereduce", "heat_rel_1.0"]))

print("\n== Hot/cold main run: write-backs and read savings (Section IV 'Write-back and total writes')")
w = "main_hotcold"
print(f"write-backs triggered: RangeReduce {v(w, 'rangereduce', 'rr_triggered'):.0f}, HA-RR {v(w, 'heat_rel_1.0', 'rr_triggered'):.0f}")
saved = {s: v(w, "rocksdb", "rq_entries_read") - v(w, s, "rq_entries_read") for s in ["rangereduce", "heat_rel_1.0"]}
print(f"HA-RR read savings / RangeReduce read savings = {100 * saved['heat_rel_1.0'] / saved['rangereduce']:.1f}%; "
      f"write-back ratio = {100 * v(w, 'heat_rel_1.0', 'rr_write_bytes') / v(w, 'rangereduce', 'rr_write_bytes'):.1f}%")


def admitted(run):
    return [int(r["admitted"]) for r in csv.DictReader(open(RES / run / "heat_rel_1.0" / "heat.csv"))]


a = admitted("main_hotcold")
print(f"admitted {sum(a)} of {len(a)} hot/cold queries")
rows = list(csv.DictReader(open(RES / "main_hotcold" / "heat_rel_1.0" / "heat.csv")))
ratio = [float(r["heat"]) / float(r["bar"]) for r in rows]
print(f"heat/mean >= 4: {100 * sum(x >= 4 for x in ratio) / len(ratio):.1f}%, < 0.5: "
      f"{100 * sum(x < 0.5 for x in ratio) / len(ratio):.1f}%, in between: "
      f"{100 * sum(0.5 <= x < 4 for x in ratio) / len(ratio):.1f}%  (Section IV 'Sensitivity')")

print("\n== Shifting workload and Table VII (decay): admission recovery after the moves at queries 167 and 333")
for run in ["main_shifting", "decay250_shifting", "decay100_shifting"]:
    if not (RES / run / "heat_rel_1.0" / "heat.csv").exists():
        print(f"{run}: not present")
        continue
    a = admitted(run)
    out = []
    for move in (167, 333):
        rec = next((q - move for q in range(move + 25, len(a) + 1) if sum(a[q - 25:q]) >= 20), None)
        low = min(sum(a[q - 25:q]) for q in range(move, move + 80))
        out.append(f"move {move}: lowest {low}/25, recovered after {rec} queries")
    wbmb = v(run, "heat_rel_1.0", "rr_write_bytes") / MB
    print(f"{run:18} per-25 windows {[sum(a[i:i + 25]) for i in range(0, 500, 25)]}")
    print(f"{'':18} {'; '.join(out)}; write-back {wbmb:.0f} MB "
          f"({pct(v(run, 'heat_rel_1.0', 'rr_write_bytes'), v('main_shifting', 'rangereduce', 'rr_write_bytes')):+.0f}% vs RangeReduce), "
          f"RA {v(run, 'heat_rel_1.0', 'rq_read_amp'):.3f}")

print("\n== Threshold sweep (Fig. 12) and absolute threshold")
rr = "main_hotcold/rangereduce"
for s in ["heat_rel_0.5", "heat_rel_1.0", "heat_rel_1.5", "heat_rel_2.0", "heat_abs_2"]:
    a = admitted_n = sum(int(r["admitted"]) for r in csv.DictReader(open(RES / "main_hotcold" / s / "heat.csv")))
    sv = (v("main_hotcold", "rocksdb", "rq_entries_read") - v("main_hotcold", s, "rq_entries_read")) / saved["rangereduce"]
    print(f"{s:13} admitted {admitted_n:3d}  write-back {100 * v('main_hotcold', s, 'rr_write_bytes') / float(S[rr]['rr_write_bytes']):5.1f}% of RR  "
          f"mean {pct(v('main_hotcold', s, 'rq_mean_ms'), float(S[rr]['rq_mean_ms'])):+.1f}% vs RR  read savings {100 * sv:.0f}% of RR")

print("\n== Different random seed (Section IV 'Robustness')")
for w in ["rep_hotcold_s7", "rep_uniform_s7"]:
    print(f"{w:15} write-back {pct(v(w, 'heat_rel_1.0', 'rr_write_bytes'), v(w, 'rangereduce', 'rr_write_bytes')):+.1f}%  "
          f"mean {pct(v(w, 'heat_rel_1.0', 'rq_mean_ms'), v(w, 'rangereduce', 'rq_mean_ms')):+.1f}% vs RangeReduce")

print("\n== Result counts: every system must return the same number of entries for every query")
for run in sorted(p.name for p in RES.iterdir() if (p / "rocksdb" / "range_queries.csv").exists()):
    ref = column(list(csv.reader(open(RES / run / "rocksdb" / "range_queries.csv")))[1:], 3)
    ok = all(column(list(csv.reader(open(f)))[1:], 3) == ref for f in (RES / run).glob("*/range_queries.csv"))
    print(f"{run:16} {'identical counts' if ok else 'MISMATCH'} ({len(ref)} queries)")
