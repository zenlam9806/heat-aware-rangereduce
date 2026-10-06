#!/bin/bash
# Usage: ./verify_all.sh main_hotcold main_uniform ...   (folders inside the results directory)
cd "$(dirname "$0")"
RESULTS=${RESULTS:-$(cd .. && pwd)/results}
for w in "$@"; do echo "== $w"; python3 verify_results.py "$RESULTS/$w"; done
