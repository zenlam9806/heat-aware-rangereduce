#!/bin/bash
cd ~/experiments
for w in "$@"; do echo "== $w"; python3 verify_results.py "results/$w"; done
