#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run one PawBench task locally via ``qwenpaw task`` (no Docker).

Use when Docker is not installed. Scores automated checks only; hybrid tasks
skip LLM-judge portion unless you wire JUDGE_* env vars separately.

Example:
  python eval/pawbench/local_smoke.py --task T053
  python eval/pawbench/local_smoke.py --task T053 --pawbench-root D:/proj/PawBench
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PAWBENCH = _REPO_ROOT.parent / "PawBench"


def _parse_task_markdown(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    prompt_match = re.search(
        r"## Prompt\s*\n+(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL,
    )
    auto_match = re.search(
        r"## Automated Checks\s*\n+```python\n(.*?)```",
        text,
        re.DOTALL,
    )
    meta: dict = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
    if not prompt_match:
        raise ValueError(f"No ## Prompt section in {path}")
    return {
        "prompt": prompt_match.group(1).strip(),
        "grade_code": auto_match.group(1).strip() if auto_match else "",
        "grading_type": meta.get("grading_type", "automated"),
        "timeout_seconds": int(meta.get("timeout_seconds", "600")),
    }


def _find_task_file(pawbench_root: Path, task_id: str) -> Path:
    tasks_dir = pawbench_root / "data" / "pawbench-v1.0" / "tasks"
    if not tasks_dir.is_dir():
        raise FileNotFoundError(
            f"PawBench tasks not found at {tasks_dir}. "
            f"Clone: git clone https://github.com/agentscope-ai/PawBench.git {_DEFAULT_PAWBENCH}",
        )
    matches = sorted(tasks_dir.glob(f"{task_id}_*.md"))
    if not matches:
        matches = sorted(tasks_dir.glob(f"*{task_id}*.md"))
    if not matches:
        raise FileNotFoundError(f"No task file for id {task_id!r} under {tasks_dir}")
    return matches[0]


def _run_grade(grade_code: str, workspace: Path) -> dict:
    namespace: dict = {}
    exec(grade_code, namespace)  # noqa: S102 — trusted PawBench grader
    grade_fn = namespace.get("grade")
    if not callable(grade_fn):
        raise RuntimeError("Automated Checks block has no grade() function")
    return grade_fn(transcript=[], workspace_path=str(workspace))


def _mean_score(scores: dict) -> float:
    if not scores:
        return 0.0
    return sum(float(v) for v in scores.values()) / len(scores)


async def _run_qwenpaw_task(
    instruction: str,
    *,
    agent_id: str,
    workspace_dir: Path,
    model: str | None,
    timeout: int,
    max_iters: int,
    output_dir: Path,
) -> dict:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
    from qwenpaw.cli.task_cmd import _run_task
    from qwenpaw.config.config import ModelSlotConfig, load_agent_config
    from qwenpaw.providers.provider_manager import ProviderManager
    from qwenpaw.utils.logging import setup_logger

    setup_logger("info")

    agent_config = load_agent_config(agent_id)
    agent_config.workspace_dir = str(workspace_dir)

    if model:
        parts = model.split("/", 1)
        if len(parts) == 2:
            agent_config.active_model = ModelSlotConfig(
                provider_id=parts[0],
                model=parts[1],
            )
        else:
            agent_config.active_model = ModelSlotConfig(model=model)
    elif not (
        agent_config.active_model
        and agent_config.active_model.provider_id
        and agent_config.active_model.model
    ):
        active = ProviderManager.get_instance().get_active_model()
        if active and active.provider_id and active.model:
            agent_config.active_model = active

    request_context = {
        "session_id": "pawbench-local-smoke",
        "user_id": "pawbench",
        "channel": "console",
        "agent_id": agent_id,
    }
    return await _run_task(
        instruction=instruction,
        agent_config=agent_config,
        request_context=request_context,
        max_iters=max_iters,
        timeout=timeout,
        output_dir=str(output_dir),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="PawBench local smoke (no Docker)")
    parser.add_argument("--task", default="T053", help="PawBench task id, e.g. T053")
    parser.add_argument(
        "--pawbench-root",
        type=Path,
        default=_DEFAULT_PAWBENCH,
        help="Path to cloned PawBench repo",
    )
    parser.add_argument("--agent-id", default="default")
    parser.add_argument(
        "-m",
        "--model",
        default=None,
        help="Model override, e.g. deepseek/deepseek-chat",
    )
    parser.add_argument("--max-iters", type=int, default=25)
    args = parser.parse_args()

    task_path = _find_task_file(args.pawbench_root, args.task)
    spec = _parse_task_markdown(task_path)
    if not spec["grade_code"]:
        print(f"Task {args.task} has no automated grader; use full PawBench + Docker.")
        return 1

    with tempfile.TemporaryDirectory(prefix="pawbench-smoke-") as tmp:
        workspace = Path(tmp)
        save_path = workspace / "blog_post.md"
        instruction = (
            f"{spec['prompt']}\n\n"
            f"Save the result exactly to this absolute path: {save_path}"
        )

        run_dir = _REPO_ROOT / "eval" / "pawbench" / "results" / "local-smoke"
        run_dir.mkdir(parents=True, exist_ok=True)

        print(f"Task file : {task_path.name}")
        print(f"Agent     : {args.agent_id}")
        print(f"Timeout   : {spec['timeout_seconds']}s")
        print(f"Workspace : {workspace}")
        print("Running qwenpaw task...\n")

        result = asyncio.run(
            _run_qwenpaw_task(
                instruction,
                agent_id=args.agent_id,
                workspace_dir=workspace,
                model=args.model,
                timeout=spec["timeout_seconds"],
                max_iters=args.max_iters,
                output_dir=run_dir,
            ),
        )

        print(json.dumps(result, indent=2, ensure_ascii=False)[:4000])

        if result.get("status") != "success":
            print(f"\nAgent run failed: {result.get('status')}")
            return 1

        if not save_path.is_file():
            # Agent may have written under configured workspace; copy hint.
            print(f"\nExpected output missing: {save_path}")
            print("Tip: agent workspace may differ from temp dir; check D:/agentdesk/workspaces/default/")
            return 1

        scores = _run_grade(spec["grade_code"], workspace)
        auto_score = _mean_score(scores)

        report = {
            "task_id": args.task,
            "task_file": str(task_path),
            "agent_status": result.get("status"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "automated_scores": scores,
            "automated_mean": round(auto_score, 4),
            "grading_type": spec["grading_type"],
            "note": (
                "LLM judge skipped in local_smoke; "
                "hybrid tasks need full PawBench for final score."
                if spec["grading_type"] == "hybrid"
                else "automated-only task"
            ),
        }
        report_path = run_dir / f"{args.task}_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"\nAutomated scores: {scores}")
        print(f"Automated mean  : {auto_score:.1%}")
        if spec["grading_type"] == "hybrid":
            print("(Hybrid task: automated is 60% of final PawBench score)")
        print(f"Report written  : {report_path}")
        return 0 if auto_score >= 0.5 else 2


if __name__ == "__main__":
    raise SystemExit(main())
