#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 experiment_a|experiment_b|experiment_c"
  exit 1
fi

EXP="$1"
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
EXP_DIR="$BASE_DIR/$EXP"

if [[ ! -d "$EXP_DIR" ]]; then
  echo "Error: experiment folder not found: $EXP_DIR"
  exit 1
fi

TRACK="${AI_OPT_TRACK:-profiler}"

case "$TRACK" in
  baseline)
    MODEL="${AI_OPT_MODEL_BASELINE:-}"
    API_BASE="${AI_OPT_API_BASE_BASELINE:-http://127.0.0.1:8000/v1}"
    export AI_OPT_RUN_BCOZ=0
    export AI_OPT_RUN_BPERF=0
    ;;
  gpt5)
    MODEL="${AI_OPT_MODEL_GPT5:-gpt-5}"
    API_BASE="${AI_OPT_API_BASE_GPT5:-https://api.openai.com/v1}"
    export AI_OPT_RUN_BCOZ=0
    export AI_OPT_RUN_BPERF=0
    ;;
  profiler)
    MODEL="${AI_OPT_MODEL_PROFILER:-}"
    API_BASE="${AI_OPT_API_BASE_PROFILER:-http://127.0.0.1:8000/v1}"
    export AI_OPT_RUN_BCOZ=${AI_OPT_RUN_BCOZ:-1}
    export AI_OPT_RUN_BPERF=${AI_OPT_RUN_BPERF:-1}
    ;;
  *)
    echo "Unknown AI_OPT_TRACK: $TRACK (expected baseline|gpt5|profiler)"
    exit 1
    ;;
esac

if [[ -z "$MODEL" ]]; then
  echo "Model not set for track '$TRACK'."
  echo "Set one of: AI_OPT_MODEL_BASELINE / AI_OPT_MODEL_GPT5 / AI_OPT_MODEL_PROFILER"
  exit 1
fi

CONFIG="$EXP_DIR/config.yaml"
INIT="$EXP_DIR/initial_program.py"
EVAL="$EXP_DIR/evaluator.py"

python -m openevolve.cli "$INIT" "$EVAL" --config "$CONFIG" --api-base "$API_BASE" --primary-model "$MODEL"
