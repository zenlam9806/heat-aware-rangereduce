"""Recomputes every full-size number quoted in the report from the raw run logs in results/fullscale and checks
it against the value printed in the report. Prints PASS/FAIL per check; exits with status 1 if any fails.

Usage:  python3 analysis/report_numbers_fullscale.py [results/fullscale]      (standard-library Python only)
"""
import csv
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fullscale as fs  # noqa: E402

ROOT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "results" / "fullscale"
MiB = 2 ** 20
FAILS = []
NAME = {"uniform": "pilot_main", "hotcold": "s2_hotcold", "shifting": "s3_shifting", "8020": "s4_hotcold8020"}
R, Q, ADM = {}, {}, {}
for w, s in NAME.items():
    for n in fs.SYSTEMS:
        run = ROOT / s / n
        if (run / "range_queries.csv").exists():
            R[w, n], Q[w, n] = fs.summarise(run)
            if (run / "heat.csv").exists():
                ADM[w, n] = [int(r["admitted"]) for r in csv.DictReader(open(run / "heat.csv"))]


def check(label, got, want, tol):
    ok = abs(got - want) <= tol
    if not ok:
        FAILS.append(label)
    print(f"{'PASS' if ok else 'FAIL'}  {label:66} computed {got:12.3f}   report {want}")


def m(w, n, k):
    return R[w, n][k]


def pct(w, n, k, ref):
    return 100 * (m(w, n, k) / m(w, ref, k) - 1)


def eta(w, n):
    saved = sum(b["read"] - r["read"] for b, r in zip(Q[w, "RocksDB"], Q[w, n])) * fs.ENTRY
    return saved / (m(w, n, "writeback_GB") * fs.GB)


def mean_lat(w, n, idx):
    return statistics.fmean(Q[w, n][i]["ns"] for i in idx) / 1e9


def ra(w, n, idx):
    return sum(Q[w, n][i]["read"] for i in idx) / sum(Q[w, n][i]["ret"] for i in idx)


def wbs(w, n, idx):
    return sum(Q[w, n][i]["wb"] for i in idx)


RR, HA, RD, H2 = "RangeReduce", "HA-RR", "RocksDB", "HA-RR_theta2"

# Overview: every query returned the same 838,860 entries
check("queries per run (all 13 runs)", min(len(q) for q in Q.values()), 9000, 0)
check("runs with all queries returning 838,860", sum(all(r["ret"] == 838860 for r in q) for q in Q.values()), 13, 0)

# Reproducing RangeReduce (uniform)
check("uniform RR vs RocksDB debt %", pct("uniform", RR, "debt_GB", RD), -83.3, 0.05)
check("uniform RR vs RocksDB space amp %", pct("uniform", RR, "space_amp", RD), -17.5, 0.05)
check("uniform RR vs RocksDB mean latency %", pct("uniform", RR, "mean_s", RD), -28.5, 0.05)
check("uniform RR vs RocksDB data movement %", pct("uniform", RR, "data_movement_GB", RD), -9.9, 0.05)
check("uniform RocksDB RA", m("uniform", RD, "read_amp"), 1.204, 0.0005)
check("uniform RR RA", m("uniform", RR, "read_amp"), 1.067, 0.0005)
check("uniform RR vs RocksDB total writes %", pct("uniform", RR, "total_write_GB", RD), 73.7, 0.05)
check("uniform RR run hours", m("uniform", RR, "run_hours"), 6.9, 0.05)
check("uniform RocksDB run hours", m("uniform", RD, "run_hours"), 9.4, 0.05)
sk = [pct(w, RR, "mean_s", RD) for w in ("hotcold", "shifting", "8020")]
check("skewed RR vs RocksDB mean, smallest cut %", max(sk), -2.1, 0.05)
check("skewed RR vs RocksDB mean, largest cut %", min(sk), -23.6, 0.05)
check("hot/cold RR P95 above RocksDB (1=yes)", float(m("hotcold", RR, "p95_s") > m("hotcold", RD, "p95_s")), 1, 0)
check("80/20 RR P95 above RocksDB (1=yes)", float(m("8020", RR, "p95_s") > m("8020", RD, "p95_s")), 1, 0)

# When a write-back pays off
wb_mib = [m(w, n, "writeback_GB") * fs.GB / MiB / m(w, n, "writebacks") for w in NAME for n in (RR, HA, H2) if (w, n) in R]
check("mean write-back size, smallest (MiB)", min(wb_mib), 10.1, 0.05)
check("mean write-back size, largest (MiB)", max(wb_mib), 13.7, 0.05)
check("query result size (MiB)", 838860 * fs.ENTRY / MiB, 102, 0.5)
obs = {w: (m(w, RD, "read_amp") - 1) * 838860 * fs.ENTRY / MiB for w in NAME}
check("obsolete data per RocksDB query, smallest (MiB)", min(obs.values()), 16, 0.5)
check("obsolete data per RocksDB query, largest (MiB)", max(obs.values()), 21, 0.5)
mstar = [m(w, n, "writeback_GB") * fs.GB / MiB / m(w, n, "writebacks") / obs[w] for w in NAME for n in (RR, HA, H2) if (w, n) in R]
check("break-even re-reads m*, smallest", min(mstar), 0.49, 0.005)
check("break-even re-reads m*, largest", max(mstar), 0.81, 0.005)
check("RR eta, smallest", min(eta(w, RR) for w in NAME), 2.95, 0.005)
check("RR eta, largest", max(eta(w, RR) for w in NAME), 11.33, 0.005)

# 80/20: hot = first 24 of every block of 30 queries
hot = [i for i in range(9000) if i % 30 < 24]
cold = [i for i in range(9000) if i % 30 >= 24]
a = ADM["8020", HA]
check("80/20 hot queries", len(hot), 7200, 0)
check("80/20 hot queries admitted", sum(a[i] for i in hot), 7200, 0)
check("80/20 cold queries skipped", sum(1 - a[i] for i in cold), 1429, 0)
check("80/20 cold skipped %", 100 * sum(1 - a[i] for i in cold) / len(cold), 79, 0.5)
check("80/20 RR write-backs", m("8020", RR, "writebacks"), 2092, 0)
check("80/20 RR write-backs on cold queries", wbs("8020", RR, cold), 1272, 0)
check("80/20 RR cold share of write-backs %", 100 * wbs("8020", RR, cold) / m("8020", RR, "writebacks"), 61, 0.5)
check("80/20 HA-RR write-backs on cold queries", wbs("8020", HA, cold), 189, 0)
check("80/20 cold write-backs fewer %", 100 * (1 - wbs("8020", HA, cold) / wbs("8020", RR, cold)), 85, 0.5)
check("80/20 HA-RR write-back GB", m("8020", HA, "writeback_GB"), 9.7, 0.05)
check("80/20 RR write-back GB", m("8020", RR, "writeback_GB"), 27.9, 0.05)
check("80/20 write-back change %", pct("8020", HA, "writeback_GB", RR), -65, 0.5)
check("80/20 RR total writes GB", m("8020", RR, "total_write_GB"), 49.5, 0.05)
check("80/20 HA-RR total writes GB", m("8020", HA, "total_write_GB"), 41.0, 0.05)
check("80/20 total writes change %", pct("8020", HA, "total_write_GB", RR), -17, 0.5)
check("80/20 RR eta", eta("8020", RR), 3.28, 0.005)
check("80/20 HA-RR eta", eta("8020", HA), 6.57, 0.005)
check("80/20 HA-RR RA on hot queries", ra("8020", HA, hot), 1.058, 0.0005)
check("80/20 RR RA on hot queries", ra("8020", RR, hot), 1.062, 0.0005)
check("uniform write-back change %", pct("uniform", HA, "writeback_GB", RR), -10.6, 0.05)
check("uniform total writes change %", pct("uniform", HA, "total_write_GB", RR), 1.6, 0.05)
check("uniform HA-RR compaction GB", m("uniform", HA, "compaction_GB"), 21.9, 0.05)
check("uniform RR compaction GB", m("uniform", RR, "compaction_GB"), 16.5, 0.05)
check("hot/cold write-back change %", pct("hotcold", HA, "writeback_GB", RR), -1.5, 0.05)
check("shifting write-back change %", pct("shifting", HA, "writeback_GB", RR), -5.6, 0.05)

# Latency
for w, k, want in (("hotcold", "mean_s", -2.1), ("hotcold", "p95_s", -24.6), ("hotcold", "p99_s", -10.6),
                   ("8020", "mean_s", 6.1), ("8020", "p95_s", 17.1), ("uniform", "mean_s", 36.9),
                   ("shifting", "p95_s", 10.1)):
    check(f"{w} HA-RR vs RR {k} %", pct(w, HA, k, RR), want, 0.05)
check("80/20 HA-RR vs RocksDB mean %", pct("8020", HA, "mean_s", RD), 3.9, 0.05)
check("uniform HA-RR vs RocksDB mean %", pct("uniform", HA, "mean_s", RD), -2.2, 0.05)
sk_hc = [i for i, x in enumerate(ADM["hotcold", HA]) if not x]
check("hot/cold skipped queries", len(sk_hc), 114, 0)
check("hot/cold RR write-backs on skipped", wbs("hotcold", RR, sk_hc), 56, 0)
check("hot/cold skipped mean, RR (s)", mean_lat("hotcold", RR, sk_hc), 4.28, 0.005)
check("hot/cold skipped mean, RocksDB (s)", mean_lat("hotcold", RD, sk_hc), 3.88, 0.005)
check("hot/cold skipped mean, HA-RR (s)", mean_lat("hotcold", HA, sk_hc), 3.35, 0.005)
sk_80 = [i for i, x in enumerate(a) if not x]
check("80/20 skipped RA, HA-RR", ra("8020", HA, sk_80), 1.287, 0.0005)
check("80/20 skipped RA, RR", ra("8020", RR, sk_80), 1.073, 0.0005)
check("80/20 skipped mean, HA-RR (s)", mean_lat("8020", HA, sk_80), 5.25, 0.005)
check("80/20 skipped mean, RR (s)", mean_lat("8020", RR, sk_80), 4.77, 0.005)
check("80/20 skipped mean, RocksDB (s)", mean_lat("8020", RD, sk_80), 3.73, 0.005)
check("80/20 hot mean, HA-RR (s)", mean_lat("8020", HA, hot), 3.24, 0.005)
check("80/20 hot mean, RR (s)", mean_lat("8020", RR, hot), 3.11, 0.005)
au = ADM["uniform", HA]
sk_u = [i for i, x in enumerate(au) if not x]
ad_u = [i for i, x in enumerate(au) if x]
check("uniform skipped queries", len(sk_u), 1762, 0)
check("uniform skipped RA, HA-RR", ra("uniform", HA, sk_u), 1.130, 0.0005)
check("uniform skipped RA, RR", ra("uniform", RR, sk_u), 1.065, 0.0005)
check("uniform admitted mean, HA-RR (s)", mean_lat("uniform", HA, ad_u), 3.40, 0.005)
check("uniform admitted mean, RR (s)", mean_lat("uniform", RR, ad_u), 2.40, 0.005)

# Shifting hot spot
check("shifting HA-RR mean (s)", m("shifting", HA, "mean_s"), 3.20, 0.005)
check("shifting RR mean (s)", m("shifting", RR, "mean_s"), 3.17, 0.005)
check("shifting HA-RR vs RocksDB mean %", pct("shifting", HA, "mean_s", RD), -23, 0.5)
check("shifting RR vs RocksDB mean %", pct("shifting", RR, "mean_s", RD), -23, 0.65)
q_rr = Q["shifting", RR]
check("shifting RR first write-back after move 1", next(i + 1 for i in range(3000, 9000) if q_rr[i]["wb"]), 3001, 0)
check("shifting RR first write-back after move 2", next(i + 1 for i in range(6000, 9000) if q_rr[i]["wb"]), 6001, 0)
asf = ADM["shifting", HA]
check("shifting admitted in 200 queries after move 1", sum(asf[3000:3200]), 0, 0)
check("shifting admitted in 200 queries after move 2", sum(asf[6000:6200]), 0, 0)
q_ha = Q["shifting", HA]
f1 = next(i + 1 for i in range(3000, 9000) if q_ha[i]["wb"])
f2 = next(i + 1 for i in range(6000, 9000) if q_ha[i]["wb"])
check("shifting HA-RR first write-back after move 1", f1, 3284, 0)
check("shifting HA-RR first write-back after move 2", f2, 6220, 0)
check("shifting delay after move 2 (220)", f2 - 6000, 220, 0)
check("shifting delay after move 1 (284)", f1 - 3000, 284, 0)
sk_s = [i for i, x in enumerate(asf) if not x]
check("shifting skipped queries", len(sk_s), 552, 0)
check("shifting skipped mean, HA-RR (s)", mean_lat("shifting", HA, sk_s), 4.95, 0.005)
check("shifting skipped mean, RR (s)", mean_lat("shifting", RR, sk_s), 2.96, 0.005)

# Threshold 2.0
check("theta=2 admitted", m("hotcold", H2, "admitted"), 8712, 0)
check("theta=1 admitted", m("hotcold", HA, "admitted"), 8886, 0)
for k, want in (("mean_s", -9.8), ("p50_s", -5.0), ("p95_s", -27.4), ("p99_s", -17.5), ("writeback_GB", -8.6)):
    check(f"theta=2 vs RR {k} %", pct("hotcold", H2, k, RR), want, 0.05)
check("theta=2 eta", eta("hotcold", H2), 10.67, 0.005)
check("hot/cold RR eta", eta("hotcold", RR), 10.00, 0.005)
check("theta=1 mean (s)", m("hotcold", HA, "mean_s"), 3.29, 0.005)
check("theta=2 mean (s)", m("hotcold", H2, "mean_s"), 3.03, 0.005)

# Space and debt
for w, n, k, want, tol in (("8020", RR, "space_amp", 1.17, 0.005), ("8020", RR, "debt_GB", 2.5, 0.05),
                           ("8020", HA, "space_amp", 1.54, 0.005), ("8020", HA, "debt_GB", 9.6, 0.05),
                           ("8020", RD, "space_amp", 1.41, 0.005), ("8020", RD, "debt_GB", 13.6, 0.05)):
    check(f"{w} {n} {k}", m(w, n, k), want, tol)
for w in ("hotcold", "shifting"):
    for k in ("space_amp", "debt_GB"):
        vals = [m(w, n, k) for n in (RR, HA, H2) if (w, n) in R]
        check(f"{w} query-driven {k} spread % (within 2)", 100 * (max(vals) / min(vals) - 1), 1.0, 1.0)
sa = [m(w, n, "space_amp") for w in ("hotcold", "shifting") for n in (RR, HA, H2) if (w, n) in R]
check("hot/cold+shifting SA, smallest", min(sa), 1.54, 0.005)
check("hot/cold+shifting SA, largest", max(sa), 1.57, 0.005)
dc = [-pct(w, n, "debt_GB", RD) for w in ("hotcold", "shifting") for n in (RR, HA, H2) if (w, n) in R]
check("hot/cold+shifting debt cut, smallest %", min(dc), 24, 0.5)
check("hot/cold+shifting debt cut, largest %", max(dc), 34, 0.5)

# Tables VI and VII
check("RocksDB RA, smallest (full size)", min(m(w, RD, "read_amp") for w in NAME), 1.16, 0.005)
check("RocksDB RA, largest (full size)", max(m(w, RD, "read_amp") for w in NAME), 1.20, 0.005)
check("RocksDB debt, smallest (GB)", min(m(w, RD, "debt_GB") for w in NAME), 13.5, 0.05)
slowest = sum(m(w, RD, "mean_s") == max(m(w, n, "mean_s") for n in fs.SYSTEMS if (w, n) in R) for w in NAME)
check("workloads where RocksDB has the slowest mean", slowest, 3, 0)
cuts = [-pct(w, RR, "mean_s", RD) for w in NAME]
check("RR vs RocksDB mean cut, smallest %", min(cuts), 2, 0.5)
check("RR vs RocksDB mean cut, largest %", max(cuts), 29, 0.5)
wr = [pct(w, RR, "total_write_GB", RD) for w in NAME]
check("RR vs RocksDB total writes, smallest %", min(wr), 14, 0.5)
check("RR vs RocksDB total writes, largest %", max(wr), 74, 0.5)
check("uniform RR write-back GB", m("uniform", RR, "writeback_GB"), 41.7, 0.05)
ra_cut = [-pct(w, n, "read_amp", RD) for w in NAME for n in (RR, HA, H2) if (w, n) in R]
check("query-driven RA cut vs RocksDB, smallest % (6-11)", min(ra_cut), 6, 0.5)
check("query-driven RA cut vs RocksDB, largest % (6-11)", max(ra_cut), 11, 0.5)

print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
