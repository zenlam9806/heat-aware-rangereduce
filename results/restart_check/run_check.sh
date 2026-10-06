#!/bin/bash
# Restart (close + reopen) integrity check: loads a hot/cold workload into each system, then reopens the
# database with the standard RocksDB API and counts the keys by full scan and by Get of every inserted key.
#   N=200000 Q=60  bash run_check.sh    -> all three systems keep every key (results.txt, first block)
#   N=500000 Q=100 bash run_check.sh    -> RangeReduce and HA-RR lose keys (results.txt, second block)
# Each size takes roughly 15-30 minutes per system on a hard disk.
set -euo pipefail

RR=${RR:-$HOME/RangeReduce}
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
EXP="$HERE/../../experiments"
N=${N:-200000}
Q=${Q:-60}
W=${W:-$HOME/integrity_$N}
case "$W" in
  "$HOME"/integrity_*) ;;
  *) echo "Refusing to clear unexpected W=$W" >&2; exit 2 ;;
esac
rm -rf -- "$W"
mkdir -p -- "$W"
cd -- "$W"
python3 "$EXP/gen_workload.py" --pattern hotcold -I "$N" -U "$N" -S "$Q" -Y 0.1 -o workload.txt
g++ -std=c++20 -O2 -I "$RR/lib/rocksdb/include" "$HERE/check.cc" -L "$RR/build/lib/rocksdb" -lrocksdb \
  -Wl,-rpath,"$RR/build/lib/rocksdb" -o "$W/check"
for SYS in rocksdb rangereduce heat; do
  mkdir -p "$W/$SYS"
  cd "$W/$SYS"
  ln -sf ../workload.txt workload.txt
  unset RR_HEAT RR_HEAT_MODE RR_HEAT_THRESHOLD RR_HEAT_LOG
  case $SYS in
    rocksdb)     A=(--rq 0) ;;
    rangereduce) A=(--rq 1 --lb 0.1667 --re 1) ;;
    heat)        A=(--rq 1 --lb 0.1667 --re 1); export RR_HEAT=1 RR_HEAT_MODE=rel RR_HEAT_THRESHOLD=1.0 ;;
  esac
  "$RR/bin/working_version" -I "$N" -U "$N" -S "$Q" -Y 0.1 -E 128 -B 32 -P 1024 -T 6 \
    --cc 0 --progress 0 -V 0 --tmv 1 "${A[@]}" > run.log 2>&1
  echo "== $SYS rc=$?"
  cp -r db dbcopy
  "$W/check" dbcopy ../workload.txt   # reopen a copy and count keys
  cd "$W"
done
