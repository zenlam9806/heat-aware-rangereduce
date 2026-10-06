#!/bin/bash
# Remaining runs: threshold sweep and seed-7 repetitions. Safe to re-run: finished runs are skipped.
cd "$(dirname "$0")"
export RESULTS=${RESULTS:-$(cd .. && pwd)/results}

{
  echo "[$(date +%H:%M:%S)] finish.sh started"
  ./run_suite.sh main_hotcold hotcold 500000 500000 500 0.1 heat:rel:1.5 heat:rel:2.0
  GEN_ARGS="--seed 7" ./run_suite.sh rep_hotcold_s7 hotcold 500000 500000 500 0.1 rocksdb rangereduce heat:rel:1.0
  GEN_ARGS="--seed 7" ./run_suite.sh rep_uniform_s7 uniform 500000 500000 500 0.1 rocksdb rangereduce heat:rel:1.0
  python3 analyze.py "$RESULTS" > /dev/null
  echo "[$(date +%H:%M:%S)] FINISH_DONE"
} >> finish.log 2>&1
