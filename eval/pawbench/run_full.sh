#!/usr/bin/env bash
# Full PawBench run (requires Docker). Run from repo root or this directory.
set -euo pipefail

# Git Bash on Windows often lacks Docker Desktop's bin dir on PATH.
if ! command -v docker >/dev/null 2>&1; then
  for _docker_bin in \
    "/c/Program Files/Docker/Docker/resources/bin" \
    "/mnt/c/Program Files/Docker/Docker/resources/bin"; do
    if [[ -x "${_docker_bin}/docker.exe" || -x "${_docker_bin}/docker" ]]; then
      export PATH="${_docker_bin}:${PATH}"
      break
    fi
  done
  unset _docker_bin
fi

PAWBENCH_ROOT="${PAWBENCH_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)/PawBench}"
if [[ ! -d "$PAWBENCH_ROOT" ]]; then
  PAWBENCH_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)/../PawBench"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found. Install Docker Desktop, then re-run."
  echo "  Windows: https://docs.docker.com/desktop/setup/install/windows-install/"
  echo "  Smoke without Docker: python eval/pawbench/local_smoke.py --task T053"
  exit 1
fi

if [[ ! -f "$PAWBENCH_ROOT/run_bench.py" ]]; then
  echo "Cloning PawBench to $PAWBENCH_ROOT ..."
  git clone --depth 1 https://github.com/agentscope-ai/PawBench.git "$PAWBENCH_ROOT"
fi

cd "$PAWBENCH_ROOT"
pip install -r requirements.txt python-dotenv -q

if [[ ! -f .env ]]; then
  echo "Create $PAWBENCH_ROOT/.env from eval/pawbench/.env.example first."
  exit 1
fi

echo "Building QwenPaw harness image (uses upstream qwenpaw; override with Dockerfile.workbuddy)..."
docker build -f docker/Dockerfile.pawbench-qwenpaw -t qwenclawbench-qwenpaw:latest .

TASKS="${TASKS:-T053}"
MODEL="${MODEL:-openai/deepseek-chat}"

python run_bench.py \
  --agents qwenpaw \
  --tasks $TASKS \
  --model "$MODEL" \
  --results-dir "$(dirname "$0")/results/full"

echo "Done. Results under eval/pawbench/results/full/"
