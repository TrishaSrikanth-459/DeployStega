#!/usr/bin/env bash
set -euo pipefail

cd ~/DeployStega1
TRACE_ROOT="experiments/covert_traces_full"
SENDER_DIR="$TRACE_ROOT/sender"
RECEIVER_DIR="$TRACE_ROOT/receiver"
EVAL_DIR="experiments/bert_semantic_evaluation"
WAIT_LOG="$TRACE_ROOT/bert_eval_watcher.log"
EVAL_LOG="$EVAL_DIR/bert_evaluation.log"
MIN_TRACES=3500

mkdir -p "$TRACE_ROOT" "$EVAL_DIR"
{
  echo "[$(date -Is)] BERT evaluation watcher armed."
  echo "Trace root: $TRACE_ROOT"
  echo "Minimum sender/receiver trace pairs required: $MIN_TRACES"
} | tee -a "$WAIT_LOG"

# Wait for active trace generation to finish. We deliberately do not kill or
# attach to the generator; this watcher is read-only until generation exits.
while pgrep -f "python .*scripts/generate_covert_traces.py|python scripts/generate_covert_traces.py" >/dev/null; do
  sender_count=$(find "$SENDER_DIR" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
  receiver_count=$(find "$RECEIVER_DIR" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
  echo "[$(date -Is)] generation still running; sender=$sender_count receiver=$receiver_count" | tee -a "$WAIT_LOG"
  sleep 300
done

echo "[$(date -Is)] generation process is no longer running." | tee -a "$WAIT_LOG"

# Wait briefly for the generator tmux pipeline to flush summary files.
for _ in $(seq 1 60); do
  if [ -s "$TRACE_ROOT/generation_summary.json" ]; then
    break
  fi
  echo "[$(date -Is)] waiting for generation_summary.json..." | tee -a "$WAIT_LOG"
  sleep 60
done

# Always run the narrow backtick cleaner as a fail-safe before evaluation.
echo "[$(date -Is)] running semantic backtick cleanup fail-safe." | tee -a "$WAIT_LOG"
python3 scripts/remove_semantic_backticks.py "$TRACE_ROOT" --summary-path "$TRACE_ROOT/backtick_cleanup_summary.json" \
  2>&1 | tee "$TRACE_ROOT/backtick_cleanup.log"

sender_count=$(find "$SENDER_DIR" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
receiver_count=$(find "$RECEIVER_DIR" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
echo "[$(date -Is)] final trace counts: sender=$sender_count receiver=$receiver_count" | tee -a "$WAIT_LOG"

if [ "$sender_count" -lt "$MIN_TRACES" ] || [ "$receiver_count" -lt "$MIN_TRACES" ]; then
  msg="Not starting BERT evaluation: need >=$MIN_TRACES sender and receiver traces, got sender=$sender_count receiver=$receiver_count"
  echo "[$(date -Is)] $msg" | tee -a "$WAIT_LOG"
  echo "$msg" > "$EVAL_DIR/NOT_STARTED_INSUFFICIENT_TRACES.txt"
  exit 2
fi

# Use original benign traces and generated covert sender traces. BERT is run on
# semantic text only (no --bert-context) to avoid adding metadata/context leakage.
source ~/myenv/bin/activate
export PYTHONUNBUFFERED=1

echo "[$(date -Is)] starting BERT semantic evaluation." | tee -a "$WAIT_LOG"
python scripts/adversarial_evaluation.py \
  --features semantic \
  --classifier bert \
  --benign-dir benign_traces \
  --covert-dir "$SENDER_DIR" \
  --target-fpr 0.05 \
  --test-size 0.3 \
  --validation-size 0.2 \
  --seed 42 \
  --output-dir "$EVAL_DIR" \
  --manifest-path experiments/experiment_manifest.json \
  --group-key experiment_id \
  --user-key role_epoch \
  --max-samples 10000 \
  --bert-epochs 3 \
  --bert-batch-size 16 \
  --bert-max-length 128 \
  2>&1 | tee "$EVAL_LOG"

echo "[$(date -Is)] BERT semantic evaluation finished. Results: $EVAL_DIR" | tee -a "$WAIT_LOG"
