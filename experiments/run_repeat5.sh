# Five repetitions of the hot/cold experiment on one identical workload file.
cd ~/experiments
mkdir -p results/rep5_base
[ -s results/rep5_base/workload.txt ] || python3 gen_workload.py --pattern hotcold -I 500000 -U 500000 -S 500 -Y 0.1 -o results/rep5_base/workload.txt
for r in 1 2 3 4 5; do
  mkdir -p results/rep5_r$r
  [ -e results/rep5_r$r/workload.txt ] || cp results/rep5_base/workload.txt results/rep5_r$r/workload.txt
  ./run_suite.sh rep5_r$r hotcold 500000 500000 500 0.1 rocksdb rangereduce heat:rel:1.0
done
python3 analyze.py results > /dev/null
echo REPS_DONE
