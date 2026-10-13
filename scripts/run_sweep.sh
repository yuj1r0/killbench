#!/usr/bin/env bash
# killbench frontier sweep driver.
#
# Runs the 24-case v0.0.1 suite across the four big US labs' current frontier
# models, at two reasoning-effort levels, repeated N times.
#
# Concurrency design:
#   - Four PROVIDER LANES run in parallel, sequential within a lane, so no
#     provider ever contends with itself and per-turn latency stays meaningful.
#   - Repeat 1 runs at --workers 1, which is the only setting where the recorded
#     latency is a true time-to-answer. Later repeats run concurrently: score and
#     cost are concurrency-invariant, latency is not (compare_models.py drops
#     latency from any batch with workers > 1).
#
# Usage:
#   scripts/run_sweep.sh [-n] [-r REPEATS] [-o OUTPUT_DIR] [-c CASE_GLOB]
#     -n  dry run: print the commands without spending anything

set -uo pipefail
cd "$(dirname "$0")/.."

DRY=0; REPEATS=3; OUT="outputs"; CASES="cases_v0.0.1"
PAR_WORKERS=6          # workers for repeats 2..N
DOCTOR_MAX_TOKENS=4000 # thinking is drawn from this budget; 1000 starves max effort

while getopts "nr:o:c:j:" opt; do
  case $opt in
    n) DRY=1 ;;
    r) REPEATS=$OPTARG ;;
    o) OUT=$OPTARG ;;
    c) CASES=$OPTARG ;;
    j) PAR_WORKERS=$OPTARG ;;
    *) echo "usage: $0 [-n] [-r REPEATS] [-o OUT] [-c CASES] [-j WORKERS]" >&2; exit 2 ;;
  esac
done

mkdir -p "$OUT" logs

# "model:efforts" -- Haiku 4.5 is default-only: it rejects the effort parameter
# outright (verified 2026-09-02), so a max arm would just be a duplicate.
# Fable 5.1 is deliberately excluded: at $10/$50 it is 2x Opus 5's price and
# alone accounted for ~$54 of the projected spend. Revisit once the rest land.
ANTHROPIC_LANE=( "claude-opus-5:default,max" "claude-haiku-4-5-20251001:default" )
OPENAI_LANE=(    "gpt-5.6-sol:default,max" "gpt-5.6-terra:default,max" "gpt-5.6-luna:default,max" )
GOOGLE_LANE=(    "gemini-3.8-flash:default,max" )
XAI_LANE=(       "grok-4.6:default,max" )

run_batch() {  # model effort repeat workers
  local model=$1 effort=$2 rep=$3 workers=$4
  local log="logs/$(echo "${model}" | tr './' '__')_${effort}_r${rep}.log"
  local cmd=(python3 src/run_benchmark.py --cases "$CASES" --doctor "$model"
             --effort "$effort" --doctor-max-tokens "$DOCTOR_MAX_TOKENS"
             --repeat "$rep" --workers "$workers" --output-dir "$OUT")
  if [[ $DRY -eq 1 ]]; then
    echo "  ${cmd[*]}  > $log"
    return 0
  fi
  echo "[$(date +%H:%M:%S)] START $model effort=$effort r$rep (workers=$workers)"
  if ! "${cmd[@]}" > "$log" 2>&1; then
    # One model failing must not take down its lane or the sweep.
    echo "[$(date +%H:%M:%S)] FAIL  $model effort=$effort r$rep -- see $log" >&2
    return 1
  fi
  echo "[$(date +%H:%M:%S)] DONE  $model effort=$effort r$rep"
}

run_lane() {  # lane_name entries...
  local lane=$1; shift
  for entry in "$@"; do
    local model="${entry%%:*}" efforts="${entry##*:}"
    IFS=',' read -ra EFFS <<< "$efforts"
    for rep in $(seq 1 "$REPEATS"); do
      # Repeat 1 is the clean-latency pass; later repeats trade latency fidelity
      # for wall-clock, since they only contribute score/cost variance.
      local workers=1
      [[ $rep -gt 1 ]] && workers=$PAR_WORKERS
      for eff in "${EFFS[@]}"; do
        run_batch "$model" "$eff" "$rep" "$workers"
      done
    done
  done
  echo "[$(date +%H:%M:%S)] LANE COMPLETE: $lane"
}

echo "=== killbench sweep: repeats=$REPEATS cases=$CASES out=$OUT ==="
[[ $DRY -eq 1 ]] && echo "(dry run)"

run_lane anthropic "${ANTHROPIC_LANE[@]}" &  A=$!
run_lane openai    "${OPENAI_LANE[@]}"    &  O=$!
run_lane google    "${GOOGLE_LANE[@]}"    &  G=$!
run_lane xai       "${XAI_LANE[@]}"       &  X=$!
wait $A $O $G $X

echo "=== sweep complete ==="
[[ $DRY -eq 0 ]] && python3 src/compare_models.py --dir "$OUT" \
  --csv "$OUT/comparison.csv" --md "$OUT/comparison.md"
