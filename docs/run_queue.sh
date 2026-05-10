#!/usr/bin/env bash
# run_queue.sh — queued test batches for lmf-ollama-obsidian harness
#
# Usage:
#   ./docs/run_queue.sh                     # run all batches defined below
#   ./docs/run_queue.sh --dry-run           # print what would run, don't execute
#
# Add or remove batches in the BATCHES array. Each entry is a label:n:model triple.
# The harness args (vault, snapshot, gpu, host, ollama-url) are shared across all batches.

set -euo pipefail

HARNESS="python3 /home/jared/lmf-ollama-obsidian/features/testing/harness.py"
VAULT="$HOME/Documents/Obsidian/Marlin"
OLLAMA_URL="http://localhost:11434"
HOST="bazza"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# --- Define batches: "label:runs:model" ---
BATCHES=(
    "7b-fixed:50:qwen2.5:7b"
    "14b:50:qwen2.5:14b"
)

# ------------------------------------------

total_batches=${#BATCHES[@]}
batch_num=0

for entry in "${BATCHES[@]}"; do
    label="${entry%%:*}"
    rest="${entry#*:}"
    runs="${rest%%:*}"
    model="${rest#*:}"
    batch_num=$((batch_num + 1))

    echo ""
    echo "========================================"
    echo "Batch $batch_num/$total_batches — $label"
    echo "  model:  $model"
    echo "  runs:   $runs"
    echo "  start:  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"

    if $DRY_RUN; then
        echo "  [dry-run] would run $runs × $model"
        continue
    fi

    for i in $(seq 1 "$runs"); do
        echo "--- [$label] run $i/$runs ---"
        $HARNESS \
            --vault "$VAULT" \
            --snapshot \
            --model "$model" \
            --gpu \
            --host "$HOST" \
            --ollama-url "$OLLAMA_URL"
    done

    echo ""
    echo "Batch $batch_num complete — $(date '+%Y-%m-%d %H:%M:%S')"
done

echo ""
echo "All batches complete."
