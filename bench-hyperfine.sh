#!/bin/bash
set -euo pipefail

mkdir -p bench

for test in \
  contraintes_sans_action_possible
do
  hyperfine --warmup 1 --runs 5 \
    --export-markdown "bench/${test}.md" \
    --export-json "bench/${test}.json" \
    -n gcc16 \
      "ctest --test-dir metrix-simulator/build-gcc16 --no-tests=error --output-on-failure -R '^${test}$'" \
    -n gcc16-native \
      "ctest --test-dir metrix-simulator/build-gcc16-native --no-tests=error --output-on-failure -R '^${test}$'"
done
