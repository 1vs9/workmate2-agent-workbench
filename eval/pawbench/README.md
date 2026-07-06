# PawBench evaluation for AgentDesk / QwenPaw

AgentDesk runs on the **QwenPaw** runtime. [PawBench](https://github.com/agentscope-ai/PawBench) is the official harness to compare **QwenPaw vs OpenClaw** on the same 150 tasks.

## Prerequisites

| Mode | Needs |
|------|--------|
| **Local smoke** (1 task, no Docker) | `pip install -e .` + cloned PawBench + configured model in AgentDesk |
| **Full PawBench** | Docker Desktop + `.env` API keys + ~10GB disk |

PawBench repo (cloned once):

```bash
git clone https://github.com/agentscope-ai/PawBench.git D:/proj/PawBench
```

## 1. Local smoke (no Docker)

Uses your existing AgentDesk model config (`D:\agentdesk` + `D:\agentdesk.secret`).

```bash
cd D:/proj/workbuddy
pip install -r D:/proj/PawBench/requirements.txt python-dotenv

python eval/pawbench/local_smoke.py --task T053
```

- **T053**: write `blog_post.md` (closed env, good first task)
- Output: `eval/pawbench/results/local-smoke/T053_report.json`
- Hybrid tasks: automated portion only; full score needs Docker + judge

## 2. Full PawBench (Docker)

1. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) and enable WSL2 backend.
2. Copy `eval/pawbench/.env.example` → `D:/proj/PawBench/.env` and fill API keys.
3. Run:

```bash
bash eval/pawbench/run_full.sh
```

Compare with OpenClaw on the same tasks:

```bash
bash eval/pawbench/compare_openclaw.sh
# or manually:
cd D:/proj/PawBench
python run_bench.py --agents qwenpaw openclaw --tasks T053 --model openai/deepseek-chat
```

## 3. WorkBuddy fork in Docker (optional)

To benchmark **this repo** instead of PyPI `qwenpaw==1.1.3`, build from PawBench root:

```bash
cd D:/proj/PawBench
cp -r D:/proj/workbuddy ./workbuddy-src
docker build -f D:/proj/workbuddy/eval/pawbench/Dockerfile.workbuddy -t qwenclawbench-workbuddy:latest .
python run_bench.py --docker-image qwenclawbench-workbuddy:latest --agents qwenpaw --tasks T053 --model openai/deepseek-chat
```

## Recommended task progression

| Stage | Tasks | Why |
|-------|-------|-----|
| Smoke | `T053` | Text-only, no workspace assets |
| Office | `T002` `T006` | Productivity slice |
| vs OpenClaw | same ids + `--agents qwenpaw openclaw` | Harness comparison |
| Full | omit `--tasks` | 150 tasks, high API cost |

## Results

- Local: `eval/pawbench/results/local-smoke/`
- Full: `eval/pawbench/results/full/` or PawBench `./results/`

Leaderboard reference: https://agentscope-ai.github.io/PawBench/
