#!/bin/bash
# Tuning test (option B): hot/cold workload, HA-RR with a stricter relative threshold theta = 2.0.
ulimit -n $(ulimit -Hn)
R=~/newexp/runs; S=$R/s2_hotcold; D=$S/HA-RR_theta2
log() { echo "$(date '+%F %T') $*" >> $R/driver.log; }
[ -f $D/done ] && exit 0
rm -rf $D; mkdir -p $D; cd $D || exit 1
ln -sf ../workload.txt workload.txt
LB=$(echo "scale=9; 1/6" | bc)
BASE="-I 8388608 -U 8388608 -S 9000 -Y 0.1 -E 128 -B 32 -P 1024 -T 6 --progress 1 -V 0 --sanity 0 --usedb 0 --snap 0"
ENV="RR_HEAT=1 RR_HEAT_MODE=rel RR_HEAT_THRESHOLD=2.0 RR_HEAT_DECAY=1000 RR_HEAT_LOG=$D/heat.csv"
echo "env $ENV ~/rr_harr/bin/working_version $BASE --rq 1 --lb $LB --re 1" > command.txt
echo "s2_hotcold: HA-RR theta=2.0 (tuning test)" > $R/current
log "s2_hotcold/HA-RR_theta2: start"
t=$(date +%s)
env $ENV /usr/bin/time -v ~/rr_harr/bin/working_version $BASE --rq 1 --lb $LB --re 1 > progress.log 2> stderr.log
echo "HA-RR_theta2_seconds $(( $(date +%s) - t ))" >> $S/timing.txt
if [ "$(wc -l < range_queries.csv)" = "9001" ] && grep -q "END HERE" workload.log; then
  rm -rf db; touch done; log "s2_hotcold/HA-RR_theta2: OK"
else
  log "s2_hotcold/HA-RR_theta2: FAILED"
fi
echo "" > $R/current
