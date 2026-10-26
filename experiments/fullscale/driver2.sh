#!/bin/bash
# One driver for all full-size runs, with automatic checking and retry.
#  - every run is validated after it ends (all 9000 range queries logged, RocksDB summary written);
#  - a failed or frozen run is moved to failed_attempts/ (with its logs) and retried, up to 2 retries;
#  - the watchdog (watchdog.sh) kills a run whose CPU time has not moved for 45 minutes, which ends here as a failure.
ulimit -n $(ulimit -Hn)
source ~/.cargo/env 2>/dev/null
R=~/newexp/runs
LB=$(echo "scale=9; 1/6" | bc)
BASE="-I 8388608 -U 8388608 -S 9000 -Y 0.1 -E 128 -B 32 -P 1024 -T 6 --progress 1 -V 0 --sanity 0 --usedb 0 --snap 0"
log() { echo "$(date '+%F %T') $*" >> $R/driver.log; }

valid() {  # dir
  [ "$(wc -l < $1/range_queries.csv 2>/dev/null)" = "9001" ] && grep -q "END HERE" $1/workload.log 2>/dev/null
}

one() {   # setting name binary flags env...
  local set=$1 S=$R/$1 name=$2 bin=$3 flags=$4; shift 4
  local D=$S/$name
  [ -f $D/done ] && return 0
  for attempt in 1 2 3; do
    # adopt a run that is already in progress in this folder (started by an earlier driver)
    local pid=""
    for p in $(pgrep -f "bin/working_version"); do [ "$(readlink /proc/$p/cwd)" = "$D" ] && pid=$p; done
    if [ -n "$pid" ]; then
      log "$set/$name: waiting for running pid $pid"
      echo "$set: $name" > $R/current
      while kill -0 $pid 2>/dev/null; do sleep 30; done
    else
      rm -rf $D; mkdir -p $D; cd $D || return 1
      ln -sf ../workload.txt workload.txt
      echo "$set: $name (attempt $attempt)" > $R/current
      echo "env $* $bin $BASE $flags" > command.txt
      log "$set/$name: start attempt $attempt"
      local t=$(date +%s)
      env "$@" /usr/bin/time -v $bin $BASE $flags > progress.log 2> stderr.log
      echo "${name}_seconds $(( $(date +%s) - t ))  (attempt $attempt)" >> $S/timing.txt
    fi
    if valid $D; then
      rm -rf $D/db; touch $D/done; log "$set/$name: OK"; return 0
    fi
    local F=$S/failed_attempts/${name}_$(date +%Y%m%d_%H%M); mkdir -p $S/failed_attempts
    [ -f $D/db/LOG ] && grep -E "ERROR|WARN" $D/db/LOG | tail -50 > $D/log_errors.txt
    rm -rf $D/db; mv $D $F
    log "$set/$name: FAILED attempt $attempt, kept in $F"
  done
  log "$set/$name: GAVE UP after 3 attempts"; return 1
}

setting() {   # name kind
  local S=$R/$1; mkdir -p $S; cd $S || return
  if [ ! -f workload.txt ]; then
    echo "$1: generating workload" > $R/current
    python3 ~/newexp/mkspec.py $2 8388608 8388608 9000 workload.specs.json
    ~/rr_orig/bin/tectonic-cli generate -w workload.specs.json > gen.log 2>&1
    sha256sum workload.txt > workload.sha256
  fi
  one $1 RocksDB ~/rr_orig/bin/working_version "--rq 0 --tmv 1" RR_HEAT=0
  one $1 RangeReduce ~/rr_orig/bin/working_version "--rq 1 --lb $LB --re 1" RR_HEAT=0
  one $1 HA-RR ~/rr_harr/bin/working_version "--rq 1 --lb $LB --re 1" RR_HEAT=1 RR_HEAT_MODE=rel RR_HEAT_THRESHOLD=1.0 RR_HEAT_DECAY=1000 RR_HEAT_LOG=$S/HA-RR/heat.csv
  log "$1: setting finished"
}

echo 13 > $R/planned
log "driver started"


setting s4_hotcold8020 hotcold8020
echo "" > $R/current
log "driver finished"
