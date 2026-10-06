# Heat-Aware RangeReduce

Admission control for query-driven compaction in RocksDB.

This repository contains the code, workloads and results for our SEG2102 (Database Management Systems, Sunway University) group project. We extend **RangeReduce** (Kaushik, Athanassoulis and Sarkar, *RangeReduce: Query-Driven LSM Compactions*, ICDE 2026, [code](https://github.com/SSD-Brandeis/RangeReduce)) with a lightweight **heat-aware admission filter**. The filter tracks how often each part of the key space is range-scanned, and lets RangeReduce write a range back only when its measured heat meets a threshold relative to the average heat of active buckets.

## What we changed

| File | Change |
|------|--------|
| `patch/range_heat_tracker.h` | New: per-DB key-space heat tracker (decaying bucket counters, absolute or relative admission threshold). |
| `patch/apply_patch.py` | Copies the tracker into RangeReduce's RocksDB and adds a short hook in `ArenaWrappedDBIter::Refresh`, enables the artifact's timing/statistics output, and logs exact per-level entry counts. |

The filter is configured with environment variables, so one binary runs all three systems:

| Variable | Meaning | Default |
|----------|---------|---------|
| `RR_HEAT` | `1` enables the admission filter | `0` |
| `RR_HEAT_MODE` | `rel` (relative to mean bucket heat) or `abs` | `abs` |
| `RR_HEAT_THRESHOLD` | admission threshold θ | `2.0` |
| `RR_HEAT_BUCKETS` | number of key-space buckets | `65536` |
| `RR_HEAT_DECAY` | halve all counters every N range queries | `1000` |
| `RR_HEAT_LOG` | optional CSV log of per-query heat and decision | unset |

## Build (Linux or WSL2)

Clone this repository and RangeReduce side by side. The patch was tested against RangeReduce commit `4e19184ce3197b02cba16852803e1359d0f77eae` (30 June 2026); check out that commit, because the patch matches exact lines of the source.

```bash
git clone https://github.com/zenlam9806/heat-aware-rangereduce.git
git clone https://github.com/SSD-Brandeis/RangeReduce.git
cd RangeReduce && git checkout 4e19184ce3197b02cba16852803e1359d0f77eae
git submodule update --init lib/KV-WorkloadGenerator lib/tectonic
python3 ../heat-aware-rangereduce/patch/apply_patch.py .
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DFAIL_ON_WARNINGS=OFF -DWITH_TESTS=OFF \
  "-DCMAKE_CXX_FLAGS=-Wno-error -Wno-deprecated-declarations"
make -j"$(nproc)"
```

Requirements: GCC 11 or newer, CMake 3.10+, `libgflags-dev`, and Rust nightly (for the Tectonic generator that the RangeReduce build also compiles; run `source ~/.cargo/env` before `make`). Tested environment: Ubuntu under WSL2 on Windows 10, GCC 15, CMake 4.2, Python 3.12+. The build produces `RangeReduce/bin/working_version`.

Python packages for the analysis scripts:

```bash
python3 -m pip install -r requirements.txt
```

## Quick check (about 1 minute)

After building, run the small demo. It needs no other setup and shows that everything works end to end:

```bash
RR=/path/to/RangeReduce bash heat-aware-rangereduce/demo/demo.sh
```

Expected output: four steps, ending with `Exact number of keys (full scan): 20000` and the result of a range query. If `RR` is not set, the scripts look for RangeReduce in `~/RangeReduce`.

## Run the experiments

```bash
cd heat-aware-rangereduce/experiments
RR=/path/to/RangeReduce ./run_all.sh     # runs RocksDB, RangeReduce and HA-RR; several hours on a hard disk
RR=/path/to/RangeReduce ./run_repeat5.sh # five repetitions of the hot/cold experiment
./verify_all.sh main_hotcold main_uniform main_shifting   # checks all systems returned the same number of entries per query
```

Results are written to `heat-aware-rangereduce/results/` (override with `RESULTS=/path`), and `analyze.py` writes `results/summary.csv`. Already-finished runs are skipped, so the scripts can be re-run safely. The results of our own runs are already included in `results/`.

`gen_workload.py` writes workloads in the same `I`/`U`/`S` format as Tectonic, with three range-query patterns: `uniform`, `hotcold` and `shifting`.

## Live demo: see the database and the dataset

```bash
bash demo/demo.sh                    # small, about 1 minute
N=500000 Q=100 bash demo/demo.sh     # larger demo: 500,000 keys, 100 range queries, several minutes
```

The script generates a dataset, runs RocksDB with RangeReduce and the heat-aware filter on it, lists the RocksDB files on disk, and then uses `demo/inspect_db` to open the database through the RocksDB API and print the number of keys, the LSM-tree levels, the first key-value pairs and the result of a range query.

## How to check our results

The committed evidence supports independent checks of the report's experimental tables, graphs, result counts, adaptation timings and restart observations. The filter-only overhead benchmark and screenshots require the RangeReduce build rather than the committed run logs. Checks 1 to 3 need only Python and this repository; the later checks explain the additional requirements.

1. **Numbers and tables** (about a minute, standard-library Python only). This rebuilds the metrics of every run from the raw logs (it does not read `summary.csv`) and checks 225 numbers against the values printed in the report: Tables I and III to VII, the confidence intervals, the write-back counts and positions, the adaptation and decay results, the Fig. 11 statement, the threshold sweep, the second seed, the dataset size, the restart results and the per-query result counts. It prints PASS/FAIL for each and exits with an error if any fails. Not covered, because they need the RangeReduce build: the filter-overhead benchmark and the screenshots (points 4 and 6).
   ```bash
   python3 analysis/report_numbers.py
   ```
   The result-count checks compare how many entries each query returned; the logs do not record the returned keys and values themselves.
2. **Graphs (Figs. 8 to 12) and Tables III and V.** These scripts produced the report's figures; they write `figures/` and `tables/`, which can be compared with the report:
   ```bash
   python3 -m pip install -r requirements.txt
   python3 analysis/plot_results.py results
   python3 analysis/paired_table.py results
   ```
3. **Raw logs.** Each run folder (for example `results/main_hotcold/heat_rel_1.0/`) holds the per-query log `range_queries.csv` (latency and entries read and returned for each of the 500 queries), the filter's per-query decisions `heat.csv`, and RocksDB's own statistics in `workload.log`. `results/summary.csv` has one row per completed run and can be opened in Excel; the checker above derives its values from the run logs instead of trusting this summary file.
4. **Code screenshots (Figs. 3 to 5).** They show `patch/range_heat_tracker.h` (lines 47 to 83 and 126 to 147) and, after applying the patch to RangeReduce commit `4e19184`, lines 408 to 426 of `lib/rocksdb/db/arena_wrapped_db_iter.cc` (our hook is lines 416 to 423). To redraw them (Linux/WSL with the DejaVu fonts; needs `pip install -r requirements.txt`, which includes Pygments and Pillow): `RR=/path/to/RangeReduce python3 analysis/make_code_figs.py results/demo_figures/demo_output.txt`.
5. **Workloads.** The 132 MB workload files are not stored here, but every experiment folder has a `workload_manifest.txt` (SHA-256 of the exact file used, generator command, Python version) and `queries.csv` (all 500 query ranges). The five-run workload regenerates byte-identically; the earlier workloads were made before the generator fix that fixed the key insertion order, but their keys and all 500 query ranges regenerate exactly.
6. **Dataset and database screenshots (Figs. 1 and 2).** They come from `N=200000 Q=60 bash demo/demo.sh`; our output is saved in `results/demo_figures/demo_output.txt`. Running the demo again produces a byte-identical dataset and the same key-value pairs and counts; only the sizes of the newest files and RocksDB's estimated key count vary slightly with background-compaction timing (compare `demo_output_second_run.txt`).
7. **Re-running the experiments.** `experiments/run_all.sh`, `run_repeat5.sh` and `run_decay.sh` repeat everything. The generated data and the result counts are reproducible; write volumes stay close; absolute latencies depend on the machine and vary from run to run on a hard disk, so compare relative results (see the report's repeatability section).

## Important durability limitation

At 500,000 keys, the evaluated RangeReduce artifact and HA-RR (which builds on it) can lose access to keys after the database is closed and reopened: plain RocksDB returned all 500,000 keys, RangeReduce 449,196 by point lookup (393,759 by full scan) and HA-RR 476,484 (464,063). At 200,000 keys all three returned every key. Live-run result counts are equal across systems, but that does not establish restart durability. Do not use RangeReduce or HA-RR for real data until this is fixed. Details and the test script: `results/restart_check/` (reproduce the failure with `N=500000 Q=100 bash results/restart_check/run_check.sh`; the passing case is `N=200000 Q=60`).

## Results summary

500,000 keys, 500,000 updates and 500 range queries of selectivity 0.1 per workload, on a 7200 rpm hard disk (WSL2, Ubuntu). MB = 2^20 bytes. Full per-run metrics are in `results/summary.csv`.

| Workload | System | Mean latency (ms) | Read amp. | Write-back (MB) | Total writes (MB) | Space amp. |
|----------|--------|------:|------:|------:|------:|------:|
| Hot/cold | RocksDB | 187 | 1.250 | 0 | 1171 | 1.293 |
| Hot/cold | RangeReduce | 237 | 1.179 | 317 | 1169 | 1.164 |
| Hot/cold | **HA-RR** | 212 | 1.189 | **85** | **1139** | 1.289 |
| Shifting | RocksDB | 185 | 1.296 | 0 | 1178 | 1.291 |
| Shifting | RangeReduce | 208 | 1.160 | 341 | 1172 | 1.223 |
| Shifting | **HA-RR** | **183** | **1.146** | **167** | **1150** | 1.267 |
| Uniform | RocksDB | 231 | 1.236 | 0 | 1169 | 1.267 |
| Uniform | RangeReduce | 288 | 1.176 | 360 | 1164 | 1.151 |
| Uniform | HA-RR | 309 | 1.184 | 294 | 1179 | 1.238 |

In short: on skewed workloads HA-RR keeps RangeReduce's read reduction on hot ranges, writes back 51–77% less, and lowers 95th-percentile latency (by 31% on average over five repeated hot/cold runs, `results/rep5_r*`, lower in every run); mean latency differences against RangeReduce were within run-to-run noise on our hard disk; it gives up RangeReduce's space-amplification gains and does not help on uniform workloads. All systems return the same number of entries for every query (`experiments/verify_results.py` compares result counts, not the individual keys and values).

## Credit

RangeReduce, its RocksDB fork and the Tectonic workload generator are the work of the SSD lab at Brandeis University and the DiSC lab at Boston University. This repository only adds the admission filter, the workload generator and the experiment scripts.
