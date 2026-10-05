# Heat-Aware RangeReduce

Admission control for query-driven compaction in RocksDB.

This repository contains the code, workloads and results for our SEG2102 (Database Management Systems, Sunway University) group project. We extend **RangeReduce** (Kaushik, Athanassoulis and Sarkar, *RangeReduce: Query-Driven LSM Compactions*, ICDE 2026, [code](https://github.com/SSD-Brandeis/RangeReduce)) with a lightweight **heat-aware admission filter**. The filter tracks how often each part of the key space is range-scanned, and lets RangeReduce write a range back only when that range is being revisited.

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

```bash
git clone https://github.com/SSD-Brandeis/RangeReduce.git
cd RangeReduce && git submodule update --init lib/KV-WorkloadGenerator lib/tectonic
python3 ../heat-aware-rangereduce/patch/apply_patch.py .
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DFAIL_ON_WARNINGS=OFF -DWITH_TESTS=OFF \
  "-DCMAKE_CXX_FLAGS=-Wno-error -Wno-deprecated-declarations"
make -j"$(nproc)"
```

Requirements: GCC 11 or newer, CMake 3.10+, `libgflags-dev`, and Rust nightly (for the Tectonic generator that the RangeReduce build also compiles).

## Run the experiments

```bash
cd experiments
./run_all.sh            # generates workloads and runs RocksDB, RangeReduce and HA-RR
python3 analyze.py results
```

`gen_workload.py` writes workloads in the same `I`/`U`/`S` format as Tectonic, with three range-query patterns: `uniform`, `hotcold` and `shifting`.

## Results summary

500,000 keys, 500,000 updates and 500 range queries of selectivity 0.1 per workload, on a 7200 rpm hard disk (WSL2, Ubuntu). MB = 2^20 bytes. Full per-run metrics are in `results/summary.csv`.

| Workload | System | Mean latency (ms) | Read amp. | Write-back (MB) | Total writes (MB) | Space amp. |
|----------|--------|------:|------:|------:|------:|------:|
| Hot/cold | RocksDB | 187 | 1.250 | 0 | 1171 | 1.293 |
| Hot/cold | RangeReduce | 237 | 1.179 | 317 | 1169 | 1.164 |
| Hot/cold | **HA-RR** | 212 | 1.189 | **85** | **1139** | 1.289 |
| Shifting | RocksDB | 185 | 1.296 | 0 | 1179 | 1.291 |
| Shifting | RangeReduce | 208 | 1.160 | 341 | 1172 | 1.223 |
| Shifting | **HA-RR** | **183** | **1.146** | **167** | **1150** | 1.267 |
| Uniform | RocksDB | 231 | 1.236 | 0 | 1169 | 1.267 |
| Uniform | RangeReduce | 288 | 1.176 | 360 | 1164 | 1.151 |
| Uniform | HA-RR | 309 | 1.184 | 294 | 1179 | 1.238 |

In short: on skewed workloads HA-RR keeps RangeReduce's read reduction on hot ranges, writes back 51–73% less, and is 10–12% faster than RangeReduce; it gives up RangeReduce's space-amplification gains and does not help on uniform workloads. All systems return identical results for every query (`experiments/verify_results.py`).

## Credit

RangeReduce, its RocksDB fork and the Tectonic workload generator are the work of the SSD lab at Brandeis University and the DiSC lab at Boston University. This repository only adds the admission filter, the workload generator and the experiment scripts.
