#!/bin/bash
# Main experiment matrix. Runs sequentially so that no two runs share the disk.
cd ~/experiments
I=500000; U=500000; S=500; Y=0.1
SYSTEMS="rocksdb rangereduce heat:rel:1.0 heat:abs:2"
./run_suite.sh main_hotcold  hotcold  $I $U $S $Y $SYSTEMS
./run_suite.sh main_uniform  uniform  $I $U $S $Y $SYSTEMS
./run_suite.sh main_shifting shifting $I $U $S $Y $SYSTEMS
./run_suite.sh main_hotcold  hotcold  $I $U $S $Y heat:rel:0.5 heat:rel:1.5 heat:rel:2.0
python3 analyze.py results
echo ALL_DONE
