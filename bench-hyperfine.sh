#!/bin/bash
set -euo pipefail

mkdir -p bench

for test in \
  contraintes_sans_action_possible \
  temps_calcul_pne \
  variantes_regroupees_complexe
do
  hyperfine --warmup 1 --runs 5 \
    --export-markdown "bench/${test}.md" \
    --export-json "bench/${test}.json" \
    -n build \
      "ctest --test-dir metrix-simulator/build --no-tests=error --output-on-failure -R '^${test}$'" \
    -n gcc16 \
      "ctest --test-dir metrix-simulator/build-gcc16 --no-tests=error --output-on-failure -R '^${test}$'" \
    -n clang \
      "ctest --test-dir metrix-simulator/build-clang --no-tests=error --output-on-failure -R '^${test}$'"
done