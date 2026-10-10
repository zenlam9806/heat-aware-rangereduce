"""Recomputes the numbers in the report directly from the raw run logs in results/ and checks each one
against the value printed in the report. Prints PASS/FAIL per check and exits with status 1 if any fails.

Usage:  python3 analysis/report_numbers.py [results_dir]      (standard-library Python only)

Raw inputs used (per run folder): range_queries.csv (per-query latency, entries read/returned, write-back
flag), heat.csv (filter decisions), workload.log (RocksDB statistics and final tree state), plus gen.log,
queries.csv and restart_check/results.txt. results/summary.csv is NOT read: every metric is rebuilt from the
logs with experiments/analyze.py.
NOT covered (need the RangeReduce build): the filter-overhead benchmark (Section VI-K "Overhead");
see the README for how to reproduce it.
"""
import csv
import math
import pathlib
import re
import statistics as st
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))
import analyze  # noqa: E402  (raw-log parser used to produce the report)

RES = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "results"
MB = 2 ** 20
T975_DF4 = 2.776
FAILS = []
S = {f"{r['workload']}/{r['system']}": r for r in analyze.collect(RES)}
SYS = ["rocksdb", "rangereduce", "heat_rel_1.0"]
REPS = [f"rep5_r{i}" for i in range(1, 6)]


def check(label, got, want, tol):
    ok = abs(got - want) <= tol
    if not ok:
        FAILS.append(label)
    print(f"{'PASS' if ok else 'FAIL'}  {label:62} computed {got:10.3f}   report {want}")


def v(w, s, k):
    return float(S[f"{w}/{s}"][k])


def pct(a, b):
    return 100 * (a / b - 1)


def eff(w, s):
    return (v(w, "rocksdb", "rq_entries_read") - v(w, s, "rq_entries_read")) * 128 / v(w, s, "rr_write_bytes")


def queries(run):
    rows = list(csv.DictReader(open(RES / run / "range_queries.csv"), skipinitialspace=True))
    return [{k.strip(): x for k, x in r.items()} for r in rows]


def admitted(run):
    return [int(r["admitted"]) for r in csv.DictReader(open(RES / run / "heat.csv"))]


print("== Table III (single runs)")
T3 = {"main_hotcold": {"rocksdb": (187, 502, 1.250, 0, 1171, 1.293, 312), "rangereduce": (237, 1097, 1.179, 317, 1169, 1.164, 227),
                       "heat_rel_1.0": (212, 860, 1.189, 85, 1139, 1.289, 329)},
      "main_uniform": {"rocksdb": (231, 576, 1.236, 0, 1169, 1.267, 310), "rangereduce": (288, 1208, 1.176, 360, 1164, 1.151, 198),
                       "heat_rel_1.0": (309, 1153, 1.184, 294, 1179, 1.238, 306)},
      "main_shifting": {"rocksdb": (185, 545, 1.296, 0, 1178, 1.291, 310), "rangereduce": (208, 1138, 1.160, 341, 1172, 1.223, 269),
                        "heat_rel_1.0": (183, 766, 1.146, 167, 1150, 1.267, 326)}}
for w, systems in T3.items():
    for s, (mean, p95, ra, wb, tot, sa, debt) in systems.items():
        check(f"{w} {s} mean ms", v(w, s, "rq_mean_ms"), mean, 0.5)
        check(f"{w} {s} P95 ms", v(w, s, "rq_p95_ms"), p95, 0.5)
        check(f"{w} {s} read amp", v(w, s, "rq_read_amp"), ra, 0.0005)
        check(f"{w} {s} write-back MB", v(w, s, "rr_write_bytes") / MB, wb, 0.5)
        check(f"{w} {s} total writes MB", v(w, s, "total_write_bytes") / MB, tot, 0.5)
        check(f"{w} {s} space amp", v(w, s, "space_amp"), sa, 0.0005)
        check(f"{w} {s} debt MB", v(w, s, "compaction_debt_bytes") / MB, debt, 0.5)
for w, s, e in [("main_uniform", "rangereduce", 0.51), ("main_uniform", "heat_rel_1.0", 0.54), ("main_hotcold", "rangereduce", 0.69),
                ("main_hotcold", "heat_rel_1.0", 2.16), ("main_shifting", "rangereduce", 1.21), ("main_shifting", "heat_rel_1.0", 2.73)]:
    check(f"{w} {s} efficiency", eff(w, s), e, 0.005)

print("\n== Tables I and V (five repeated hot/cold runs, mean and SD)")
for s, label, key, div, mean, sd, tol in [
        ("rangereduce", "write-back MB", "rr_write_bytes", MB, 330, 3, 0.5), ("heat_rel_1.0", "write-back MB", "rr_write_bytes", MB, 79, 2, 0.5),
        ("rocksdb", "P95 ms", "rq_p95_ms", 1, 678, 74, 0.5), ("rangereduce", "P95 ms", "rq_p95_ms", 1, 1303, 95, 0.5),
        ("heat_rel_1.0", "P95 ms", "rq_p95_ms", 1, 893, 95, 0.5), ("rocksdb", "mean ms", "rq_mean_ms", 1, 233, 30, 0.5),
        ("rangereduce", "mean ms", "rq_mean_ms", 1, 261, 19, 0.5), ("heat_rel_1.0", "mean ms", "rq_mean_ms", 1, 237, 24, 0.5),
        ("rocksdb", "median ms", "rq_p50_ms", 1, 167, 23, 0.5), ("rangereduce", "median ms", "rq_p50_ms", 1, 143, 9, 0.5),
        ("heat_rel_1.0", "median ms", "rq_p50_ms", 1, 156, 17, 0.5), ("rocksdb", "debt MB", "compaction_debt_bytes", MB, 335, 19, 0.5),
        ("rangereduce", "debt MB", "compaction_debt_bytes", MB, 251, 11, 0.5), ("heat_rel_1.0", "debt MB", "compaction_debt_bytes", MB, 336, 5, 0.5)]:
    xs = [v(w, s, key) / div for w in REPS]
    check(f"rep5 {s} {label} mean", st.mean(xs), mean, tol)
    check(f"rep5 {s} {label} SD", st.stdev(xs), sd, 0.5)
for s, ra, sa in [("rocksdb", 1.243, 1.32), ("rangereduce", 1.182, 1.20), ("heat_rel_1.0", 1.177, 1.31)]:
    check(f"rep5 {s} read amp mean", st.mean(v(w, s, "rq_read_amp") for w in REPS), ra, 0.0005)
    check(f"rep5 {s} space amp mean", st.mean(v(w, s, "space_amp") for w in REPS), sa, 0.005)
for s, m, sd in [("rangereduce", 0.57, 0.04), ("heat_rel_1.0", 2.56, 0.33)]:
    xs = [eff(w, s) for w in REPS]
    check(f"rep5 {s} reads saved per byte mean", st.mean(xs), m, 0.005)
    check(f"rep5 {s} reads saved per byte SD", st.stdev(xs), sd, 0.005)

print("\n== Repeatability: paired change HA-RR vs RangeReduce over five runs, mean and 95% CI")
for label, key, mean, lo, hi in [("write-back", "rr_write_bytes", -76.1, -76.9, -75.2), ("P95", "rq_p95_ms", -31.0, -44.4, -17.6),
                                 ("mean", "rq_mean_ms", -8.5, -25.9, 8.8), ("median", "rq_p50_ms", 9.6, -7.0, 26.2)]:
    d = [pct(v(w, "heat_rel_1.0", key), v(w, "rangereduce", key)) for w in REPS]
    m, h = st.mean(d), T975_DF4 * st.stdev(d) / math.sqrt(5)
    check(f"{label} change mean %", m, mean, 0.05)
    check(f"{label} CI low %", m - h, lo, 0.05)
    check(f"{label} CI high %", m + h, hi, 0.05)
d = [pct(v(w, "heat_rel_1.0", "rr_write_bytes"), v(w, "rangereduce", "rr_write_bytes")) for w in REPS]
check("write-back change, best run %", min(d), -77, 0.5)
check("write-back change, worst run %", max(d), -75, 0.5)

print("\n== Table VII, our two rows (change vs RocksDB, means of the five runs)")
for label, key, rr, ha, tol in [("compaction debt", "compaction_debt_bytes", -25, 0.1, 0.5), ("space amp", "space_amp", -9.3, -0.4, 0.05),
                                ("read amp", "rq_read_amp", -4.9, -5.3, 0.05), ("mean latency", "rq_mean_ms", 12, 2, 0.5),
                                ("P95 latency", "rq_p95_ms", 92, 32, 0.5), ("total writes", "total_write_bytes", 1.9, -2.6, 0.05),
                                ("data movement", "data_movement_bytes", -8.4, -5.8, 0.05)]:
    base = st.mean(v(w, "rocksdb", key) for w in REPS)
    check(f"{label} RangeReduce %", pct(st.mean(v(w, "rangereduce", key) for w in REPS), base), rr, tol)
    check(f"{label} HA-RR %", pct(st.mean(v(w, "heat_rel_1.0", key) for w in REPS), base), ha, tol)

print("\n== Table IV (same queries split by HA-RR's decision; mean ms of queries and read amplification)")
T5 = {"main_hotcold": (426, {"rocksdb": (174, 1.247, 261, 1.270), "rangereduce": (185, 1.175, 534, 1.202), "heat_rel_1.0": (200, 1.175, 280, 1.273)}),
      "main_uniform": (330, {"rocksdb": (227, 1.231, 237, 1.246), "rangereduce": (263, 1.173, 336, 1.182), "heat_rel_1.0": (323, 1.163, 283, 1.225)}),
      "main_shifting": (391, {"rocksdb": (175, 1.293, 220, 1.305), "rangereduce": (166, 1.153, 359, 1.185), "heat_rel_1.0": (175, 1.127, 213, 1.214)})}
for w, (n_adm, systems) in T5.items():
    flags = admitted(f"{w}/heat_rel_1.0")
    check(f"{w} admitted queries", sum(flags), n_adm, 0)
    for s, (a_ms, a_ra, s_ms, s_ra) in systems.items():
        q = queries(f"{w}/{s}")
        for want, name, exp_ms, exp_ra in [(1, "admitted", a_ms, a_ra), (0, "skipped", s_ms, s_ra)]:
            sel = [r for r, f in zip(q, flags) if f == want]
            check(f"{w} {s} {name} mean ms", st.mean(float(r["RQ Total Time"]) / 1e6 for r in sel), exp_ms, 0.5)
            ra = sum(int(r["Total Entries Read"]) for r in sel) / sum(int(r["Total Entries Returned"]) for r in sel)
            check(f"{w} {s} {name} read amp", ra, exp_ra, 0.0005)

print("\n== Write-backs and read savings (hot/cold main run)")
for s, n in [("rangereduce", 24), ("heat_rel_1.0", 7)]:
    check(f"write-backs triggered by {s}", sum(r["Did Run RR"].strip() == "1" for r in queries(f"main_hotcold/{s}")), n, 0)
saved = {s: v("main_hotcold", "rocksdb", "rq_entries_read") - v("main_hotcold", s, "rq_entries_read") for s in ["rangereduce", "heat_rel_1.0"]}
check("HA-RR read savings as % of RangeReduce's", 100 * saved["heat_rel_1.0"] / saved["rangereduce"], 85, 0.5)
check("HA-RR write-back as % of RangeReduce's", 100 * v("main_hotcold", "heat_rel_1.0", "rr_write_bytes") / v("main_hotcold", "rangereduce", "rr_write_bytes"), 27, 0.5)
ratio = [float(r["heat"]) / float(r["bar"]) for r in csv.DictReader(open(RES / "main_hotcold/heat_rel_1.0/heat.csv"))]
check("queries with heat >= 4x mean %", 100 * sum(x >= 4 for x in ratio) / len(ratio), 76, 0.5)
check("queries with heat < 0.5x mean %", 100 * sum(x < 0.5 for x in ratio) / len(ratio), 14, 0.5)

print("\n== Shifting workload: adaptation and Table VI (decay)")
ALPH = sorted("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")  # byte order of the key alphabet


def key_pos(k):  # approximate position of a key in [0,1): keys are uniform random strings over ALPH
    return sum(ALPH.index(c) / 62 ** (i + 1) for i, c in enumerate(k[:6]))


bounds = [(r["start_key"], r["end_key"]) for r in csv.DictReader(open(RES / "main_shifting/queries.csv"))]
mid = [(key_pos(a) + key_pos(b)) / 2 for a, b in bounds]
wb = [i + 1 for i, r in enumerate(queries("main_shifting/heat_rel_1.0")) if r["Did Run RR"].strip() == "1"]
for move, centre, gap in [(167, 0.50, 19), (333, 0.75, 38)]:
    first = next(q for q in wb if q > move and abs(mid[q - 1] - centre) <= 0.025)
    check(f"first HA-RR write-back in new hot window after move {move} (queries later)", first - move, gap, 0)
for run, want in [("main_shifting", ((6, 40), (1, 54), 167)), ("decay250_shifting", ((6, 40), (6, 42), 149)), ("decay100_shifting", ((4, 42), (8, 39), 120))]:
    a = admitted(f"{run}/heat_rel_1.0")
    for (low, rec), move in zip(want[:2], (167, 333)):
        check(f"{run} lowest admitted/25 after move {move}", min(sum(a[q - 25:q]) for q in range(move, move + 80)), low, 0)
        check(f"{run} queries to recover after move {move}", next(q - move for q in range(move + 25, 501) if sum(a[q - 25:q]) >= 20), rec, 0)
    check(f"{run} write-back MB", v(run, "heat_rel_1.0", "rr_write_bytes") / MB, want[2], 0.5)


def rolling_median(xs, n=40, min_n=10):
    return [st.median(xs[max(0, i - n + 1):i + 1]) if i + 1 >= min_n else None for i in range(len(xs))]


lat = {s: rolling_median([float(r["RQ Total Time"]) / 1e6 for r in queries(f"main_shifting/{s}")]) for s in SYS}
for move, end in [(167, 333), (333, 500)]:
    below = [q for q in range(move + 1, end + 1) if all(lat[s][q - 1] < lat["rocksdb"][q - 1] for s in ["rangereduce", "heat_rel_1.0"])]
    check(f"Fig. 5: first query after move {move} with both medians below RocksDB (within 30)", min(below) - move, min(min(below) - move, 30), 0)
    check(f"Fig. 5: share of the phase with both medians below RocksDB > 50%", 100 * len(below) / (end - move) > 50, 1, 0)

print("\n== Threshold sweep, absolute threshold and second seed")
rr = "rangereduce"
for s, n_adm in [("heat_rel_0.5", 430), ("heat_rel_2.0", 406), ("heat_abs_2", 488)]:
    check(f"main_hotcold {s} admitted", sum(admitted(f"main_hotcold/{s}")), n_adm, 0)
wbs = [100 * v("main_hotcold", s, "rr_write_bytes") / v("main_hotcold", rr, "rr_write_bytes") for s in ["heat_rel_0.5", "heat_rel_1.0", "heat_rel_1.5", "heat_rel_2.0"]]
check("sweep: lowest write-back % of RangeReduce", min(wbs), 23, 0.5)
check("sweep: highest write-back % of RangeReduce", max(wbs), 27, 0.5)
for w, s, want in [("rep_hotcold_s7", "rr_write_bytes", -74), ("rep_hotcold_s7", "rq_mean_ms", -10.8), ("rep_uniform_s7", "rr_write_bytes", -10), ("rep_uniform_s7", "rq_mean_ms", 3.5)]:
    check(f"{w} HA-RR vs RangeReduce {s} %", pct(v(w, "heat_rel_1.0", s), v(w, rr, s)), want, 0.5 if abs(want) >= 10 else 0.05)

print("\n== Dataset size and restart check")
ins = int(re.search(r"wrote (\d+) inserts", (RES / "main_hotcold/gen.log").read_text())[1])
check("unique key-value data, MB (128-byte entries)", ins * 128 / MB, 61, 0.1)
txt = (RES / "restart_check/results.txt").read_text()
for name, want in [("count", [200000, 200000, 200000, 393759, 464063, 500000]), ("found by Get", [200000, 200000, 200000, 449196, 476484, 500000])]:
    got = [int(x) for x in re.findall(r"count (\d+)" if name == "count" else r"found by Get (\d+)", txt)]
    check(f"restart check: {name} values match the report", got == want, 1, 0)

print("\n== Result counts: every system returned the same number of entries for every query")
for run in sorted(p.name for p in RES.iterdir() if (p / "rocksdb" / "range_queries.csv").exists()):
    ref = [r["Total Entries Returned"] for r in queries(f"{run}/rocksdb")]
    same = all([r["Total Entries Returned"] for r in queries(f"{run}/{d.name}")] == ref
               for d in (RES / run).iterdir() if (d / "range_queries.csv").exists())
    check(f"{run} identical result counts", same, 1, 0)

print("\n== Cost model (Sections III and VI-E): read savings, write-back and break-even re-reads")
ENTRY, RESULT_MB = 128, 50000 * 128 / MB


def saved_mb(w, s):
    return (v(w, "rocksdb", "rq_entries_read") - v(w, s, "rq_entries_read")) * ENTRY / MB


def max_saved_mb(w):
    return (v(w, "rocksdb", "rq_entries_read") - v(w, "rocksdb", "rq_entries_returned")) * ENTRY / MB


hc = "main_hotcold"
check("result size of one range query, MB", RESULT_MB, 6.1, 0.05)
check("hot/cold: largest possible read savings (Delta_max), MB", max_saved_mb(hc), 763, 0.5)
check("hot/cold: RangeReduce read savings, MB", saved_mb(hc, rr), 217, 0.5)
check("hot/cold: RangeReduce savings, % of Delta_max", 100 * saved_mb(hc, rr) / max_saved_mb(hc), 28, 0.5)
check("hot/cold: HA-RR read savings, MB", saved_mb(hc, "heat_rel_1.0"), 185, 0.5)
check("hot/cold: HA-RR savings, % of Delta_max", 100 * saved_mb(hc, "heat_rel_1.0") / max_saved_mb(hc), 24, 0.5)
check("hot/cold: HA-RR savings, % of RangeReduce savings", 100 * saved_mb(hc, "heat_rel_1.0") / saved_mb(hc, rr), 85, 0.5)
check("hot/cold: HA-RR write-back, % of RangeReduce", 100 * v(hc, "heat_rel_1.0", "rr_write_bytes") / v(hc, rr, "rr_write_bytes"), 27, 0.5)
check("hot/cold: efficiency, HA-RR / RangeReduce", eff(hc, "heat_rel_1.0") / eff(hc, rr), 3.2, 0.05)
check("hot/cold: RangeReduce write-backs", v(hc, rr, "rr_triggered"), 24, 0)
check("hot/cold: HA-RR write-backs", v(hc, "heat_rel_1.0", "rr_triggered"), 7, 0)
per_wb, breakeven = [], []
for w in ["main_hotcold", "main_uniform", "main_shifting"]:
    for s in [rr, "heat_rel_1.0"]:
        mb_each = v(w, s, "rr_write_bytes") / MB / v(w, s, "rr_triggered")
        per_wb.append(mb_each)
        ra0 = v(w, "rocksdb", "rq_entries_read") / v(w, "rocksdb", "rq_entries_returned")
        breakeven.append(mb_each / ((ra0 - 1) * RESULT_MB))  # m* in Eq. (4)
    check(f"{w}: first range query is admitted (cold start)", admitted(f"{w}/heat_rel_1.0")[0], 1, 0)
check("smallest mean MB per write-back over the six runs", min(per_wb), 12, 0.5)
check("largest mean MB per write-back over the six runs", max(per_wb), 14, 0.5)
check("smallest break-even number of re-reads m*", min(breakeven), 8, 0.5)
check("largest break-even number of re-reads m*", max(breakeven), 10, 0.5)
check("RangeReduce efficiency below 1 on this many of 3 workloads",
      sum(eff(w, rr) < 1 for w in ["main_hotcold", "main_uniform", "main_shifting"]), 2, 0)

print(f"\n{'ALL CHECKS PASSED' if not FAILS else f'{len(FAILS)} CHECK(S) FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
