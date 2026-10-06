#!/bin/bash
# Small live demo (about 1 minute): generate a dataset, load it into RocksDB with the
# heat-aware filter switched on, then open the database and show what is stored.
# Usage: bash demo.sh            (small, about 1 minute)
#        N=500000 Q=100 bash demo.sh   (same size as the paper, several minutes)
set -e
N=${N:-20000}   # number of inserts (and updates)
Q=${Q:-40}      # number of range queries
RR=~/RangeReduce
EXP=~/experiments
HERE=$(cd "$(dirname "$0")" && pwd)
DEMO=~/demo_run
rm -rf "$DEMO"; mkdir -p "$DEMO"; cd "$DEMO"

echo "### Step 1: generate the dataset ($N inserts, $N updates, $Q range queries)"
python3 $EXP/gen_workload.py --pattern hotcold -I $N -U $N -S $Q -Y 0.1 -o workload.txt
echo "First 3 lines of workload.txt (I = insert, U = update, S = range scan):"
head -3 workload.txt | cut -c1-60
grep -m2 "^S" workload.txt

echo
echo "### Step 2: run RocksDB + RangeReduce + our heat-aware filter on the dataset"
export RR_HEAT=1 RR_HEAT_MODE=rel RR_HEAT_THRESHOLD=1.0 RR_HEAT_LOG="$DEMO/heat.csv"
$RR/bin/working_version -I $N -U $N -S $Q -Y 0.1 -E 128 -B 32 -P 1024 -T 6 \
  --cc 0 --progress 0 -V 0 --tmv 1 --rq 1 --lb 0.1667 --re 1 > run.log 2>&1
echo "Range queries admitted by the heat filter: $(grep -c ',1$' heat.csv 2>/dev/null || echo '?') of $Q"

echo
echo "### Step 3: the RocksDB database on disk"
ls -lh db | awk '{print $5, $9}'

echo
echo "### Step 4: open the database and read from it"
[ -x "$HERE/inspect_db" ] || g++ -std=c++20 -O2 -I $RR/lib/rocksdb/include "$HERE/inspect_db.cc" \
  -L $RR/build/lib/rocksdb -lrocksdb -Wl,-rpath,$RR/build/lib/rocksdb -o "$HERE/inspect_db"
"$HERE/inspect_db" db
