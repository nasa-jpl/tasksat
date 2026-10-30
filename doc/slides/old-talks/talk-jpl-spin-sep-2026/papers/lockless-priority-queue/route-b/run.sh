#!/usr/bin/env bash
# Route B: build & run the standalone underflow harness. See README.md.
set -e
cd "$(dirname "$0")"

CXX=${CXX:-clang++}
FLAGS="-std=c++14 -pthread"

echo "== building (optimized) =="
$CXX $FLAGS -O2 -o harness harness.cpp

echo
echo "== 1) PR AS WRITTEN: expect underflow to 4294967295 =="
./harness --delay-us 50 || true          # exits 2 on underflow

echo
echo "== 2) FIXED: expect exactly-once (missing=0 dup=0) and max available <= depth =="
./harness --fixed --total 300000

echo
echo "== 3) ThreadSanitizer: expect underflow BUT no data-race warning (report.md section 8) =="
$CXX $FLAGS -O1 -g -fsanitize=thread -o harness_tsan harness.cpp
if ./harness_tsan --delay-us 50 2>&1 | tee /tmp/tsan.out | grep -q "ThreadSanitizer: data race"; then
    echo "!! unexpected: TSan reported a data race"
else
    echo "(confirmed: no ThreadSanitizer data-race warning)"
fi

echo
echo "== cleanup binaries =="
rm -f harness harness_tsan
