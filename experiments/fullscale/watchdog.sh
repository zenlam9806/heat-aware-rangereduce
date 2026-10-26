#!/bin/bash
# Watchdog: every 5 minutes, check each running experiment. If its CPU time has not increased for 45 minutes,
# it is frozen: save a stack trace, then kill it so the driver retries the run.
R=/home/user/newexp/runs
declare -A last_cpu last_change
while true; do
  for p in $(pgrep -f "^/home/user/rr_(orig|harr)/bin/working_version"); do
    [ -f /home/user/newexp/paused_at ] && continue                    # paused on purpose
    cpu=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null) || continue
    now=$(date +%s)
    if [ "${last_cpu[$p]}" != "$cpu" ]; then last_cpu[$p]=$cpu; last_change[$p]=$now; continue; fi
    if [ $(( now - ${last_change[$p]} )) -gt 2700 ]; then
      d=$(readlink /proc/$p/cwd)
      echo "$(date '+%F %T') WATCHDOG: pid $p in $d frozen for 45 min - saving stack trace and stopping it" >> $R/driver.log
      gdb -p $p -batch -ex "thread apply all bt 15" > $d/frozen_stacktrace.txt 2>&1
      kill -9 $p
      unset last_cpu[$p] last_change[$p]
    fi
  done
  sleep 300
done
