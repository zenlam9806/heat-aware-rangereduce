// Admits RangeReduce compactions only for key ranges that recent range queries keep revisiting.
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "rocksdb/rocksdb_namespace.h"

namespace ROCKSDB_NAMESPACE {

class RangeHeatTracker {
 public:
  struct Config {
    bool enabled = false;
    // relative: threshold is a multiple of the mean heat of active buckets.
    bool relative = false;
    uint32_t buckets = 65536;
    double threshold = 2.0;
    uint64_t decay_period = 1000;
    std::string log_path;
  };

  static const Config& GetConfig() {
    static const Config cfg = LoadConfig();
    return cfg;
  }

  static bool Enabled() { return GetConfig().enabled; }

  static RangeHeatTracker& ForDB(const void* db) {
    static std::mutex registry_mu;
    static std::unordered_map<const void*, RangeHeatTracker*> registry;
    std::lock_guard<std::mutex> lock(registry_mu);
    RangeHeatTracker*& tracker = registry[db];
    if (tracker == nullptr) {
      tracker = new RangeHeatTracker(GetConfig());
    }
    return *tracker;
  }

  // Heat counts the current query, so a never-seen range has heat 1.
  bool RecordAndAdmit(const std::string& start, const std::string& end) {
    std::lock_guard<std::mutex> lock(mu_);
    uint32_t lo = Bucket(start);
    uint32_t hi = Bucket(end);
    if (hi < lo) {
      std::swap(lo, hi);
    }
    uint64_t sum = 0;
    for (uint32_t b = lo; b <= hi; b++) {
      if (counts_[b] == 0) {
        active_buckets_++;
      }
      if (counts_[b] < UINT32_MAX) {
        counts_[b]++;
        total_count_++;
      }
      sum += counts_[b];
    }
    const double heat = static_cast<double>(sum) / (hi - lo + 1);
    const double mean = active_buckets_ == 0
                            ? 0.0
                            : static_cast<double>(total_count_) / active_buckets_;
    const double bar = cfg_.relative ? cfg_.threshold * mean : cfg_.threshold;
    const bool admitted = heat >= bar;
    queries_++;
    admitted ? admitted_++ : skipped_++;
    if (log_ != nullptr) {
      fprintf(log_, "%llu,%.4f,%.4f,%d\n",
              static_cast<unsigned long long>(queries_), heat, bar,
              admitted ? 1 : 0);
    }
    if (cfg_.decay_period > 0 && queries_ % cfg_.decay_period == 0) {
      Decay();
    }
    return admitted;
  }

  uint64_t admitted() const { return admitted_; }
  uint64_t skipped() const { return skipped_; }

 private:
  explicit RangeHeatTracker(const Config& cfg)
      : cfg_(cfg), counts_(cfg.buckets, 0) {
    if (!cfg_.log_path.empty()) {
      log_ = fopen(cfg_.log_path.c_str(), "w");
      if (log_ != nullptr) {
        setvbuf(log_, nullptr, _IOLBF, 0);
        fprintf(log_, "rq,heat,bar,admitted\n");
      }
    }
  }

  static Config LoadConfig() {
    Config cfg;
    if (const char* v = getenv("RR_HEAT")) {
      cfg.enabled = atoi(v) != 0;
    }
    if (const char* v = getenv("RR_HEAT_MODE")) {
      cfg.relative = std::string(v) == "rel";
    }
    if (const char* v = getenv("RR_HEAT_BUCKETS")) {
      long b = atol(v);
      if (b > 0) {
        cfg.buckets = static_cast<uint32_t>(b);
      }
    }
    if (const char* v = getenv("RR_HEAT_THRESHOLD")) {
      cfg.threshold = atof(v);
    }
    if (const char* v = getenv("RR_HEAT_DECAY")) {
      cfg.decay_period = static_cast<uint64_t>(atoll(v));
    }
    if (const char* v = getenv("RR_HEAT_LOG")) {
      cfg.log_path = v;
    }
    return cfg;
  }

  void Decay() {
    total_count_ = 0;
    active_buckets_ = 0;
    for (uint32_t& c : counts_) {
      c >>= 1;
      total_count_ += c;
      active_buckets_ += c > 0 ? 1 : 0;
    }
  }

  uint32_t Bucket(const std::string& key) const {
    uint64_t prefix = 0;
    for (size_t i = 0; i < 8; i++) {
      prefix <<= 8;
      if (i < key.size()) {
        prefix |= static_cast<uint8_t>(key[i]);
      }
    }
    unsigned __int128 scaled =
        static_cast<unsigned __int128>(prefix) * cfg_.buckets;
    return static_cast<uint32_t>(scaled >> 64);
  }

  const Config cfg_;
  std::mutex mu_;
  std::vector<uint32_t> counts_;
  uint64_t total_count_ = 0;
  uint64_t active_buckets_ = 0;
  uint64_t queries_ = 0;
  uint64_t admitted_ = 0;
  uint64_t skipped_ = 0;
  FILE* log_ = nullptr;
};

}  // namespace ROCKSDB_NAMESPACE
