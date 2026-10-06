"""Checks that every finished system returned the same number of entries per range query as RocksDB."""
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
    print(f"{s.name:16s} queries={len(got)} total_returned={sum(got)} identical_to_rocksdb={same}")
print("ALL IDENTICAL" if ok else "MISMATCH FOUND")
