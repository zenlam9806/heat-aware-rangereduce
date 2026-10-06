"""Checks that every system in a workload folder returned the same NUMBER of entries for every range
query as RocksDB. It compares result counts only; the run logs do not record the returned keys/values.
Exits with status 1 if any count differs, so it can be used in scripts.
Usage: python3 verify_results.py <results/workload_folder>
"""
import csv
import pathlib
import sys

w = pathlib.Path(sys.argv[1]).expanduser()


def returned(run):
    rows = list(csv.reader(open(run / "range_queries.csv")))[1:]
    return [int(r[3]) for r in rows if len(r) > 3]


ref = returned(w / "rocksdb")
ok = True
for s in sorted(p for p in w.iterdir() if (p / "range_queries.csv").exists()):
    got = returned(s)
    same = got == ref
    ok &= same
    print(f"{s.name:16s} queries={len(got)} total_returned={sum(got)} same_counts_as_rocksdb={same}")
print("ALL RESULT COUNTS IDENTICAL" if ok else "COUNT MISMATCH FOUND")
sys.exit(0 if ok else 1)
