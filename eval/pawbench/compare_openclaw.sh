#!/usr/bin/env bash
# QwenPaw vs OpenClaw on the same PawBench tasks (requires Docker + two images).
set -euo pipefail

PAWBENCH_ROOT="${PAWBENCH_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)/../PawBench}"
TASKS="${TASKS:-T053}"
MODEL="${MODEL:-openai/deepseek-chat}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker required. See eval/pawbench/run_full.sh"
  exit 1
fi

cd "$PAWBENCH_ROOT"

docker build -f docker/Dockerfile.pawbench-qwenpaw -t qwenclawbench-qwenpaw:latest .

python run_bench.py \
  --agents qwenpaw openclaw \
  --tasks $TASKS \
  --model "$MODEL" \
  --results-dir "$(dirname "$0")/results/compare"
