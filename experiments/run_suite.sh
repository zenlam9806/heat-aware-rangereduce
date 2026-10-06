#!/bin/bash
# Usage: [GEN_ARGS="..."] run_suite.sh <name> <pattern> <inserts> <updates> <range_queries> <selectivity> <systems...>
# systems: rocksdb | rangereduce | heat:<abs|rel>:<threshold>
set -u
EXP=$(cd "$(dirname "$0")" && pwd)          # this folder, wherever the repository was cloned
RR=${RR:-$HOME/RangeReduce}                  # patched RangeReduce checkout (override with RR=/path)
RESULTS=${RESULTS:-$(cd "$EXP/.." && pwd)/results}
NAME=$1; PATTERN=$2; I=$3; U=$4; S=$5; Y=$6; shift 6
SYSTEMS=("$@")
T=6
LB=$(python3 -c "print(1/$T)")
WDIR=$RESULTS/$NAME
mkdir -p "$WDIR"
cd "$WDIR"

if [ ! -s workload.txt ]; then
  python3 $EXP/gen_workload.py --pattern "$PATTERN" -I "$I" -U "$U" -S "$S" -Y "$Y" ${GEN_ARGS:-} -o workload.txt | tee gen.log
fi

COMMON="-I $I -U $U -S $S -Y $Y -E 128 -B 32 -P 1024 -T $T --cc 0 --progress 0 -V 0 --tmv 1"
for SYS in "${SYSTEMS[@]}"; do
  OUT="$WDIR/${SYS//:/_}"
  if [ -f "$OUT/done" ]; then echo "skip $SYS (done)"; continue; fi
  rm -rf "$OUT"; mkdir -p "$OUT"; cd "$OUT"
  ln -sf ../workload.txt workload.txt
  unset RR_HEAT RR_HEAT_MODE RR_HEAT_THRESHOLD RR_HEAT_LOG
  case $SYS in
    rocksdb)     ARGS="--rq 0" ;;
    rangereduce) ARGS="--rq 1 --lb $LB --re 1" ;;
    heat:*)      ARGS="--rq 1 --lb $LB --re 1"
                 IFS=: read -r _ MODE TH <<< "$SYS"
                 export RR_HEAT=1 RR_HEAT_MODE=$MODE RR_HEAT_THRESHOLD=$TH RR_HEAT_LOG="$OUT/heat.csv" ;;
    *) echo "unknown system $SYS"; exit 1 ;;
  esac
  echo "[$(date +%H:%M:%S)] running $SYS on $NAME"
  START=$(date +%s)
  /usr/bin/time -v $RR/bin/working_version $COMMON $ARGS > stdout.log 2> time.log
  RC=$?
  END=$(date +%s)
  echo "$SYS rc=$RC wall=$((END-START))s" | tee summary.txt
  rm -rf db
  [ $RC -eq 0 ] && touch done
  cd "$WDIR"
done
