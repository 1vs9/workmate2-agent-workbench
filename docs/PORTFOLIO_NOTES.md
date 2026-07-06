# Portfolio Notes

This document summarizes AgentDesk2 for people evaluating my AI coding and agent
engineering ability.

## One-Line Summary

AgentDesk2 is a local-first AI agent workbench that adds task-centric UX,
multi-agent team orchestration, skill mounting, streaming recovery, and artifact
management on top of QwenPaw.

## What I Want This Project To Show

- I can work above the level of a single API call or prompt wrapper.
- I understand that agent products need session boundaries, stream recovery,
  tool traces, artifacts, and state machines.
- I can keep a runtime adapter thin instead of forking core runtime behavior
  unnecessarily.
- I can design frontend state around streaming events without letting UI state
  become the backend source of truth.
- I can debug and stabilize long-running async workflows.

## Strongest Technical Signals

| Signal | Where To Look |
| --- | --- |
| Runtime/product boundary | `docs/ARCHITECTURE.md` |
| Agent task/session model | `docs/AGENT_DESIGN.md` |
| Team orchestration | `src/qwenpaw/agentdesk/team_chat.py` |
| Streaming reducer | `src/qwenpaw/agentdesk/web/src/utils/chatStreamReducer.ts` |
| Reliability case study | `docs/CASE_STUDY_STALE_TEAM_RUNS.md` |
| Persistence and compaction | `src/qwenpaw/agentdesk/store.py`, `task_store.py` |
| Skill mounting | `src/qwenpaw/agentdesk/skill_mount.py` |

## Freelance-Relevant Pitch

I can help teams build agent-facing products that need more than a prompt box:

- AI coding assistants and task workbenches;
- multi-agent workflow prototypes;
- local-first assistant tooling;
- tool-calling UX and trace panels;
- streaming/reconnect reliability;
- skill/plugin systems;
- artifact-producing agent workflows.

## Suggested Review Path

1. Read the root README.
2. Read `docs/ARCHITECTURE.md`.
3. Read `docs/AGENT_DESIGN.md`.
4. Skim `team_chat.py`, `chat.py`, and `chatStreamReducer.ts`.
5. Read the stale team run case study.

That review path is designed to show both product thinking and engineering
tradeoffs.

