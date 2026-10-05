// Measures the per-query cost of RangeHeatTracker on the range queries of a workload file.
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "db/range_heat_tracker.h"

static uint32_t BucketOf(const std::string& key, uint32_t buckets) {
  uint64_t prefix = 0;
  for (size_t i = 0; i < 8; i++) {
    prefix <<= 8;
    if (i < key.size()) prefix |= static_cast<uint8_t>(key[i]);
  }
  return static_cast<uint32_t>((static_cast<unsigned __int128>(prefix) * buckets) >> 64);
}

int main(int argc, char** argv) {
  std::ifstream in(argv[1]);
  std::vector<std::pair<std::string, std::string>> queries;
  std::string line;
  while (std::getline(in, line)) {
    if (line.size() > 2 && line[0] == 'S') {
      std::istringstream ss(line.substr(2));
      std::string a, b;
      ss >> a >> b;
      queries.emplace_back(a, b);
    }
  }
  auto& tracker = ROCKSDB_NAMESPACE::RangeHeatTracker::ForDB(&queries);
  const uint32_t buckets = ROCKSDB_NAMESPACE::RangeHeatTracker::GetConfig().buckets;
  uint64_t covered = 0;
  for (auto& q : queries) {
    covered += BucketOf(q.second, buckets) - BucketOf(q.first, buckets) + 1;
  }
  const int rounds = 200;
  auto t0 = std::chrono::steady_clock::now();
  uint64_t admitted = 0;
  for (int r = 0; r < rounds; r++) {
    for (auto& q : queries) admitted += tracker.RecordAndAdmit(q.first, q.second);
  }
  auto t1 = std::chrono::steady_clock::now();
  double ns = std::chrono::duration<double, std::nano>(t1 - t0).count() / (rounds * queries.size());
  printf("queries=%zu mean_buckets_per_query=%.0f ns_per_query=%.0f admitted=%llu\n", queries.size(),
         static_cast<double>(covered) / queries.size(), ns, static_cast<unsigned long long>(admitted));
  return 0;
}
