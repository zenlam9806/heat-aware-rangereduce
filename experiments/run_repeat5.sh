#!/bin/bash
# Five repetitions of the hot/cold experiment on one identical workload file.
# Usage: [RR=/path/to/RangeReduce] [RESULTS=/path/to/results] ./run_repeat5.sh
cd "$(dirname "$0")"
export RESULTS=${RESULTS:-$(cd .. && pwd)/results}
mkdir -p "$RESULTS/rep5_base"
if [ ! -s "$RESULTS/rep5_base/workload.txt" ]; then
  python3 gen_workload.py --pattern hotcold -I 500000 -U 500000 -S 500 -Y 0.1 \
    -o "$RESULTS/rep5_base/workload.txt" | tee "$RESULTS/rep5_base/gen.log"
fi
for r in 1 2 3 4 5; do
  mkdir -p "$RESULTS/rep5_r$r"
  [ -e "$RESULTS/rep5_r$r/workload.txt" ] || cp "$RESULTS/rep5_base/workload.txt" "$RESULTS/rep5_r$r/"
  cp "$RESULTS/rep5_base/gen.log" "$RESULTS/rep5_r$r/"   # analyze.py reads the insert count from gen.log
  ./run_suite.sh rep5_r$r hotcold 500000 500000 500 0.1 rocksdb rangereduce heat:rel:1.0
done
python3 analyze.py "$RESULTS" > /dev/null
echo REPS_DONE
