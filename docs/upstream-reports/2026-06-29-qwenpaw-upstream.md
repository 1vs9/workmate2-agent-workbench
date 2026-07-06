# QwenPaw Upstream Update Report - 2026-06-29

**Run time:** 2026-06-29 09:22 Asia/Shanghai  
**Project:** AgentDesk2 (`D:\proj\agentDesk2`)  
**Known AgentDesk2 base:** QwenPaw `dev/agentscope2.0` at `c74d5ea17f4c915421d28ab1331dec12b089c9d4`

## Branch Heads

| Branch | Head | Date | Subject |
|---|---:|---|---|
| `dev/agentscope2.0` | `bffedc6` | 2026-06-23 | `feat(sandbox): add bubblewrap Linux sandbox with mount namespace isolation (#5310)` |
| `main` | `90e508e` | 2026-06-26 | `perf(ChatSession): optimize session switching performance (#5559)` |
| `sen/dream` | `f34a071` | 2026-06-17 | `fix(console): keep empty dream_cron empty to disable dream job` |
| `gh-pages` | `c3caf76` | 2026-06-23 | `deploy: 09fc515c88a5e817870e6b975e66b5be81893e03` |

## Summary

This is the first recorded upstream report, so there is no previous state file to diff against. Baseline comparison:

- `dev/agentscope2.0` is **9 commits ahead** of our known base `c74d5ea`.
- `main` is **267 commits ahead** of our known base and appears to be the more active upstream integration line.
- `main` currently carries tag `v2.0.0-beta.1`.

The most relevant upstream direction is clear: QwenPaw is moving deeper into Runtime 2.0, native session/chat performance, memory lifecycle, governance/tool policy, sandboxing, provider compatibility, and desktop packaging.

## High-Signal Updates

### Runtime / Session / Streaming

- `90e508e perf(ChatSession): optimize session switching performance (#5559)`
- `8dbb9d5 fix(channel): use event content as primary text source in streaming end (#5553)`
- `c554c22 feat(runtime): align envelope event translation with v1 streaming protocol (#5495)`
- `86d4a3f feat(runtime): Runtime 2.0 modular architecture with enhanced tool-call coordination (#5078)`

**AgentDesk2 impact:** high. Our current architecture discussion is centered on `Session` as shared context and `Run` as the per-agent execution unit. Upstream session switching and streaming-end fixes should be studied before we redesign AgentDesk's single-session multi-agent behavior.

### Memory / Context

- `0dd93d5 feat(memory): refactor auto memory system with turn-based tracking (#5540)`
- `42dadbe refactor(memory): restructure auto-memory lifecycle, enhance /compact and add /system_prompt command (#5450)`
- `4995a69 Migrate context management from LightContextManager to AgentScope 2.0 native compression (#5309)`
- `5063ed7 feat(memory): migrate QwenPaw memory runtime to ReMe4 (#5349)`

**AgentDesk2 impact:** high. Shared session context across switchable agents will depend heavily on how QwenPaw now represents turns, memory, and compaction. We should avoid implementing our own long-term context projection until this is understood.

### Security / Governance / Sandbox

- `bffedc6 feat(sandbox): add bubblewrap Linux sandbox with mount namespace isolation (#5310)`
- `26042fb refactor(governance): merge ToolGuard detectors into Policy engine (#5301)`
- `54cdfb0 feat: initial governance & sandbox interface disscussion (#5088)`

**AgentDesk2 impact:** high. We already found workspace-file and API-key exposure risks. Upstream policy/sandbox changes may offer better primitives for AgentDesk's file access, tool approval, and skill execution boundaries.

### Skills / Skill Pool

- `bb1a470 fix(skill): remove enable all during init (#5477)`
- `a5908ad fix(skill): zip metadata error handling (#5481)`
- `9623f33 feat(skillpool): restore SkillPool styles (#5532)`
- `1604db2 feat(skills): split Skills page into enabled/disabled sections with dual layout (#5521)`

**AgentDesk2 impact:** medium-high. AgentDesk has its own skills market and per-agent skill mounting. The upstream "remove enable all during init" is especially relevant to avoiding surprising skill activation.

### Providers / Models

- `66092b1 feat(provider): add OpenAI Response API provider (#5519)`
- `74eabb5 fix(models): count only configured providers online (#5537)`
- `1b82596 fix: inline $ref/$defs in tool schemas for GLM model compatibility (#5496)`
- `8854eae fix(model): override format_tools for gemini (#5517)`
- `fa2b3a0 feat(dashscope provider): honour extra_body generate_kwargs and avoid sending default enable_thinking (#5491)`

**AgentDesk2 impact:** medium. Provider/model config is part of our Settings surface. These are candidates for cherry-pick or rebase study after security fixes.

### Desktop / Packaging

- `f5e1185 feat(desktop): add tauri auto updater (#4669)`
- `a4ab7c8 fix(pack): repair desktop packaging builds (#5518)`
- `da5506e feat(ci): end-to-end UI verification for desktop releases (#5428)`

**AgentDesk2 impact:** medium. Useful when AgentDesk2 becomes a desktop-oriented product. Not urgent for the session/run architecture work.

## Merge Risks

1. `main` is far ahead of our current base. A direct merge will likely touch app routing, console chat/session internals, memory, skills, providers, desktop packaging, and security policy.
2. Runtime 2.0 and memory changes may conflict conceptually with AgentDesk's current `task_store` and custom SSE reducer assumptions.
3. Sandbox/governance changes could be very useful, but should be integrated after we fix AgentDesk's current file boundary bugs so we do not mix two security migrations.

## Recommendations

1. Study `90e508e` and its related ChatSession changes before finalizing the AgentDesk `Session == shared context` design.
2. Study `0dd93d5`, `42dadbe`, `4995a69`, and `5063ed7` before building any new AgentDesk-owned context/memory projection.
3. Prioritize AgentDesk local security fixes first: API key response redaction, workspace path containment, and blocking client-controlled `workspace_dir`.
4. Treat `main` as the primary upstream watch branch going forward, while still monitoring `dev/agentscope2.0` for Runtime 2.0-specific work.
5. Do not merge upstream wholesale yet. Prefer targeted code reading and selective cherry-picks after the AgentDesk architecture ADR lands.

