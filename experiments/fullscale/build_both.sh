#!/bin/bash
[ -f ~/.cargo/env ] && source ~/.cargo/env
for d in rr_orig rr_harr; do
  echo "=== BUILD $d start $(date)"
  mkdir -p ~/$d/build && cd ~/$d/build || exit 1
  cmake .. -DCMAKE_BUILD_TYPE=Release -DFAIL_ON_WARNINGS=OFF -DWITH_TESTS=OFF \
    "-DCMAKE_CXX_FLAGS=-Wno-error -Wno-deprecated-declarations" > ~/newexp/cmake_$d.log 2>&1 || { echo "=== BUILD $d CMAKE FAILED"; continue; }
  make -j6 > ~/newexp/make_$d.log 2>&1
  if [ -x ~/$d/bin/working_version ] && [ -x ~/$d/bin/tectonic-cli ]; then echo "=== BUILD $d DONE $(date)"; else echo "=== BUILD $d FAILED $(date)"; tail -20 ~/newexp/make_$d.log; fi
done
echo "=== ALL BUILDS FINISHED $(date)"
