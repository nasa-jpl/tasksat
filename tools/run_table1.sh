#!/usr/bin/env bash
# Regenerate the timings of Table 1 in the paper.
#
# Runs every benchmark in tests/tasknet_files/benchmark in satisfy mode, in the two
# configurations a user can choose:
#   race   - default: plain and labelled solvers racing on two cores
#   plain  - --no-unsat-core: plain solver only
# and prints one line per benchmark and configuration, plus the machine details.
#
# Usage (from the tasksat directory):
#   tools/run_table1.sh                 all 16 benchmarks
#   tools/run_table1.sh seq_5 par_5_2   only the named ones
# Results are also written to results/table1_<date>.txt.

set -u
cd "$(dirname "$0")/.."

TIMEOUT=300
BENCH=tests/tasknet_files/benchmark
ALL="seq_5 seq_10 seq_15 seq_20 seqforce_5 seqforce_10 seqforce_15 seqforce_20 par_5_2 par_10_3 par_20_5 par_30_10 prop_5_10 prop_10_20 prop_10_50 prop_15_100"
NAMES=${*:-$ALL}
OUT=results/table1_$(date +%Y-%m-%d_%H-%M).txt
mkdir -p results

field() {  # field <output> <label>: the number after the first "<label>"
    echo "$1" | grep -m1 "$2" | awk '{print $3}'
}

{
    echo "# Machine"
    echo "cpu:    $(sysctl -n machdep.cpu.brand_string 2>/dev/null), $(sysctl -n hw.ncpu 2>/dev/null) cores"
    echo "memory: $(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB"
    echo "os:     $(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null)"
    echo "python: $(python3 --version 2>&1)"
    echo "z3:     $(python3 -c 'import z3; print(z3.get_version_string())')"
    echo "tool:   $(git rev-parse --short HEAD)$(git diff --quiet || echo ' (uncommitted changes)')"
    echo "timeout: ${TIMEOUT}s, mode: satisfy"
    echo
    printf "%-14s %-6s %10s %10s %10s  %s\n" benchmark config validity safety total result
} | tee "$OUT"

for name in $NAMES; do
    for config in race plain; do
        extra=""
        [ "$config" = plain ] && extra="--no-unsat-core"
        out=$(python3 src/smt/tasknet_verifier.py "$BENCH/$name.tn" --mode satisfy \
                  --timeout "$TIMEOUT" $extra 2>&1)
        if echo "$out" | grep -q "TIMEOUT"; then
            validity=">${TIMEOUT}s"; safety="-"; total="-"; result="TIMEOUT"
        else
            validity="$(field "$out" "Validity checking:")s"
            safety="$(field "$out" "Property verification:")"
            safety=${safety:+${safety}s}
            total="$(field "$out" "Total time:")s"
            if echo "$out" | grep -q "UNSAT"; then
                result="UNSAT"
            else
                result="SAT $(echo "$out" | grep -m1 "^Summary:" | sed 's/^Summary: //')"
            fi
        fi
        printf "%-14s %-6s %10s %10s %10s  %s\n" "$name" "$config" "$validity" \
            "${safety:--}" "$total" "$result" | tee -a "$OUT"
    done
done

echo
echo "Written to $OUT"
