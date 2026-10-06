#include <cstdio>
#include <string>
#include "rocksdb/db.h"
int main(int c, char** v){ rocksdb::Options o; rocksdb::DB* db=nullptr;
 auto s = rocksdb::DB::Open(o, v[1], &db); if(!s.ok()){fprintf(stderr,"%s\n",s.ToString().c_str());return 1;}
 auto it=db->NewIterator(rocksdb::ReadOptions()); long n=0; std::string last;
 for(it->SeekToFirst();it->Valid();it->Next()){ n++; last=it->key().ToString(); }
 fprintf(stderr,"count %ld last=%s status=%s\n",n,last.c_str(),it->status().ToString().c_str());
 // count by sampling Gets of keys from the workload
 FILE* f=fopen(v[2],"r"); char op; char k[64], val[256]; long found=0, total=0; std::string got;
 while(fscanf(f," %c %63s %255s",&op,k,val)==3){ if(op!='I') continue; total++; if(db->Get(rocksdb::ReadOptions(),k,&got).ok()) found++; }
 fprintf(stderr,"inserted keys %ld, found by Get %ld\n", total, found);
 delete it; delete db; }
