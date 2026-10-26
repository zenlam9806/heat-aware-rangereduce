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

The committed evidence supports independent checks of the report's experimental tables, graphs, result counts, adaptation timings and restart observations. The filter-only overhead benchmark requires the RangeReduce build rather than the committed run logs; the raw benchmark output, with the exact command and compiler, is in `results/overhead/bench_output.txt`. Checks 1 to 3 need only Python and this repository; the later checks explain the additional requirements.

1. **Numbers and tables** (about a minute, standard-library Python only). This rebuilds the metrics of every run from the raw logs (it does not read `summary.csv`) and performs 243 checks against the values and claims printed in the paper: Tables III to VI, the two rows of Table VII measured in this study, the confidence intervals, the cost-model quantities (largest possible read savings, share recovered, megabytes per write-back, break-even number of re-reads), the write-back counts and positions, the adaptation and decay results, the Fig. 6 statement, the threshold sweep, the second seed, the dataset size, the restart results and the per-query result counts. It prints PASS/FAIL for each and exits with an error if any fails. Not covered, because it needs the RangeReduce build: the filter-overhead benchmark. The other rows of Table VII and Tables I and VIII quote numbers published by other authors; check those against the cited papers.
   ```bash
   python3 analysis/report_numbers.py
   ```
   The result-count checks compare how many entries each query returned; the logs do not record the returned keys and values themselves.
2. **Graphs (Figs. 4 to 7) and Tables III and IV.** These scripts produced the paper's result figures; they write `figures/` and `tables/`, which can be compared with the paper (they also draw a space-amplification and compaction-debt chart that the paper no longer prints; its numbers are in Table III):
   ```bash
   python3 -m pip install -r requirements.txt
   python3 analysis/plot_results.py results
   python3 analysis/paired_table.py results
   ```
3. **Raw logs.** Each run folder (for example `results/main_hotcold/heat_rel_1.0/`) holds the per-query log `range_queries.csv` (latency and entries read and returned for each of the 500 queries), the filter's per-query decisions `heat.csv`, and RocksDB's own statistics in `workload.log`. `results/summary.csv` has one row per completed run and can be opened in Excel; the checker above derives its values from the run logs instead of trusting this summary file.
4. **The code behind the equations.** The paper describes the filter with equations (5) to (8) and does not print code. The code is `patch/range_heat_tracker.h`: `Bucket` (lines 136 to 147) is equation (5), `RecordAndAdmit` (lines 47 to 83) is equations (6) and (7), and `Decay` (lines 126 to 134) is equation (8). After applying the patch to RangeReduce commit `4e19184`, our hook is lines 416 to 423 of `lib/rocksdb/db/arena_wrapped_db_iter.cc`. (`analysis/make_code_figs.py` can still render these lines as images.)
5. **Workloads.** The 132 MB workload files are not stored here, but every experiment folder has a `workload_manifest.txt` (SHA-256 of the exact file used, generator command, Python version) and `queries.csv` (all 500 query ranges). The five-run workload regenerates byte-identically; the earlier workloads were made before the generator fix that fixed the key insertion order, but their keys and all 500 query ranges regenerate exactly.
6. **Seeing the dataset and the database.** Run `N=200000 Q=60 bash demo/demo.sh`; our output is saved in `results/demo_figures/demo_output.txt`. Running the demo again produces a byte-identical dataset and the same key-value pairs and counts; only the sizes of the newest files and RocksDB's estimated key count vary slightly with background-compaction timing (compare `demo_output_second_run.txt`).
7. **Re-running the experiments.** `experiments/run_all.sh`, `run_repeat5.sh` and `run_decay.sh` repeat everything. The generated data and the result counts are reproducible; write volumes stay close; absolute latencies depend on the machine and vary from run to run on a hard disk, so compare relative results (see the report's repeatability section).

## Important durability limitation

At 500,000 keys, the evaluated RangeReduce artifact and HA-RR (which builds on it) can lose access to keys after the database is closed and reopened: plain RocksDB returned all 500,000 keys, RangeReduce 449,196 by point lookup (393,759 by full scan) and HA-RR 476,484 (464,063). At 200,000 keys all three returned every key. Live-run result counts are equal across systems, but that does not establish restart durability. Do not use RangeReduce or HA-RR for real data until this is fixed. Details and the test script: `results/restart_check/` (reproduce the failure with `N=500000 Q=100 bash results/restart_check/run_check.sh`; the passing case is `N=200000 Q=60`).

## Full-size results (the RangeReduce authors' setup)

Every system was re-run with the RangeReduce authors' own code (commit `4e19184`), their Tectonic workload generator and their main configuration: 8,388,608 inserts, 8,388,608 updates and 9,000 range queries of selectivity 0.1 (`-I 8388608 -U 8388608 -S 9000 -Y 0.1 -E 128 -B 32 -P 1024 -T 6`), on the same 7200 rpm hard disk. One run took 7 to 11 hours; each configuration was run once. Raw logs (without the large workload and database files): `results/fullscale/`. Scripts: `experiments/fullscale/` (`driver.sh` runs everything, `mkspec.py` writes the workload specifications, `watchdog.sh` stops a frozen run). GB = 2^30 bytes.

| Workload | System | Mean (s) | P95 (s) | Read amp. | Write-backs | Write-back (GB) | Total writes (GB) | Space amp. | Debt (GB) |
|----------|--------|------:|------:|------:|------:|------:|------:|------:|------:|
| Uniform | RocksDB | 3.47 | 4.68 | 1.204 | 0 | 0.0 | 34.7 | 1.42 | 13.6 |
| Uniform | RangeReduce | 2.48 | 4.41 | 1.067 | 4,158 | 41.7 | 60.3 | 1.17 | 2.3 |
| Uniform | HA-RR | 3.39 | 5.89 | 1.079 | 3,408 | 37.3 | 61.3 | 1.23 | 3.8 |
| Hot/cold | RocksDB | 3.93 | 5.56 | 1.158 | 0 | 0.0 | 34.8 | 1.41 | 13.5 |
| Hot/cold | RangeReduce | 3.36 | 6.35 | 1.066 | 837 | 8.3 | 40.1 | 1.57 | 10.2 |
| Hot/cold | HA-RR | 3.29 | 4.79 | 1.067 | 827 | 8.1 | 40.0 | 1.57 | 10.3 |
| Hot/cold | HA-RR, θ = 2 | 3.03 | 4.61 | 1.068 | 764 | 7.5 | 39.6 | 1.57 | 10.3 |
| Shifting | RocksDB | 4.15 | 6.31 | 1.168 | 0 | 0.0 | 34.9 | 1.42 | 13.5 |
| Shifting | RangeReduce | 3.17 | 4.84 | 1.058 | 802 | 8.7 | 39.7 | 1.54 | 8.9 |
| Shifting | HA-RR | 3.20 | 5.33 | 1.071 | 758 | 8.2 | 39.5 | 1.54 | 9.0 |
| 80/20 | RocksDB | 3.48 | 4.69 | 1.166 | 0 | 0.0 | 34.7 | 1.41 | 13.6 |
| 80/20 | RangeReduce | 3.40 | 5.41 | 1.064 | 2,092 | 27.9 | 49.5 | 1.17 | 2.5 |
| 80/20 | HA-RR | 3.61 | 6.33 | 1.095 | 848 | 9.7 | 41.0 | 1.54 | 9.6 |

In short: RangeReduce's published gains reproduced. On 80/20, HA-RR skipped 79% of cold queries and wrote back 65% less (17% fewer total writes) than RangeReduce, but was 6% slower on average; on hot/cold its 95th-percentile latency was 25% lower; on uniform it was 37% slower. At this scale a write-back pays for itself after less than one later scan, so skipping it saves writes but not time.

Recompute everything from the raw logs:

```bash
python3 analysis/fullscale.py              # one metrics row per run -> results/fullscale/summary.csv
python3 analysis/fullscale_tables.py       # the two LaTeX tables of the report
python3 analysis/report_numbers_fullscale.py   # checks every full-size number in the report (126 checks)
python3 analysis/plot_fullscale.py         # the full-size figures (needs matplotlib)
```

## Small-scale results

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
