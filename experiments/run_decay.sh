#!/bin/bash
# Shifting workload with counter decay actually triggered (W = 250 and W = 100), replaying the
# same workload file as main_shifting. Run run_all.sh first so that main_shifting exists.
# Usage: [RR=/path/to/RangeReduce] [RESULTS=/path/to/results] ./run_decay.sh
cd "$(dirname "$0")"
export RESULTS=${RESULTS:-$(cd .. && pwd)/results}
for W in 250 100; do
  D="$RESULTS/decay${W}_shifting"; mkdir -p "$D"
  [ -e "$D/workload.txt" ] || cp "$RESULTS/main_shifting/workload.txt" "$D/"
  cp "$RESULTS/main_shifting/gen.log" "$D/"
  RR_HEAT_DECAY=$W ./run_suite.sh decay${W}_shifting shifting 500000 500000 500 0.1 heat:rel:1.0
done
python3 analyze.py "$RESULTS" > /dev/null
echo DECAY_DONE
