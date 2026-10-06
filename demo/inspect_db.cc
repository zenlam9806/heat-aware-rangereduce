// inspect_db: opens a RocksDB database and shows what is stored in it.
// Usage: inspect_db <db_dir> [start_key]
#include <cstdio>
#include <string>

#include "rocksdb/db.h"
#include "rocksdb/options.h"

int main(int argc, char** argv) {
  if (argc < 2) {
    std::fprintf(stderr, "usage: %s <db_dir> [start_key]\n", argv[0]);
    return 1;
  }
  rocksdb::Options options;
  rocksdb::DB* db = nullptr;
  // A normal open: read-only iterators crash in the RangeReduce fork of RocksDB.
  rocksdb::Status s = rocksdb::DB::Open(options, argv[1], &db);
  if (!s.ok()) {
    std::fprintf(stderr, "open failed: %s\n", s.ToString().c_str());
    return 1;
  }

  std::string v;
  db->GetProperty("rocksdb.estimate-num-keys", &v);
  std::printf("== Database: %s\n== Estimated number of keys: %s\n", argv[1], v.c_str());
  db->GetProperty("rocksdb.levelstats", &v);
  std::printf("== LSM-tree levels (files and size per level):\n%s\n", v.c_str());

  // First five key-value pairs in key order (values shortened for display).
  std::printf("== First 5 key-value pairs (sorted by key):\n");
  rocksdb::Iterator* it = db->NewIterator(rocksdb::ReadOptions());
  int n = 0;
  for (it->SeekToFirst(); it->Valid() && n < 5; it->Next(), n++) {
    std::printf("  %s -> %.20s... (%zu B)\n", it->key().ToString().c_str(),
                it->value().ToString().c_str(), it->value().size());
  }

  // Exact number of live keys, by scanning the whole database once.
  long total = 0;
  for (it->SeekToFirst(); it->Valid(); it->Next()) total++;
  std::printf("\n== Exact number of keys (full scan): %ld\n", total);

  // A small range query: count the entries between two keys.
  std::string start = argc > 2 ? argv[2] : "M";
  std::string end = start + "~";
  int count = 0;
  for (it->Seek(start); it->Valid() && it->key().ToString() < end; it->Next()) count++;
  std::printf("\n== Range query [\"%s\", \"%s\"): %d entries\n", start.c_str(), end.c_str(), count);
  delete it;
  delete db;
  return 0;
}
