# -*- coding: utf-8 -*-
"""AgentDesk default agent (AgentDesk企伴) identity and persona."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.config import load_agent_config, save_agent_config
from ..constant import (
    BUILTIN_QA_AGENT_ID,
    BUILTIN_QA_AGENT_NAME,
    LEGACY_QA_AGENT_ID,
)

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ID = "default"
DEFAULT_DISPLAY_NAME = "AgentDesk企伴"
AGENTDESK_DEFAULT_DESCRIPTION = (
    "企业智能工作助手 · 日常办公、知识问答、文档处理与工具协作"
)

# Names that resolve to the built-in default agent (not plaza employees).
_DEFAULT_ASSIGNEE_ALIASES = frozenset(
    {
        DEFAULT_DISPLAY_NAME,
        "AgentDesk",
        "agentdesk",
        DEFAULT_AGENT_ID,
        "Default Agent",
    },
)

_BUILTIN_QA_ASSIGNEE_IDS = frozenset(
    {
        BUILTIN_QA_AGENT_ID,
        LEGACY_QA_AGENT_ID,
    },
)

_BUILTIN_QA_ASSIGNEE_NAMES = frozenset(
    {
        BUILTIN_QA_AGENT_NAME,
        "QA Agent",
        "qa agent",
    },
)

AGENTDESK_DEFAULT_SYSTEM_PROMPT = """\
## AgentDesk 企伴

你是 **AgentDesk 企伴**（Agent ID: `default`），AgentDesk 产品中的默认通用工作助手。

### 身份与定位
- **名字**：AgentDesk 企伴
- **角色**：企业智能伴侣与通用工作助手，不是「数字员工广场」里可招募的岗位智能体。
- **范围**：日常办公、知识问答、文档与代码处理、轻量自动化、工具与技能协作；在用户询问 AgentDesk 安装、配置、目录结构或故障排查时，可先读取本地文档与配置文件再作答。
- **风格**：专业、清晰、务实；优先给出可执行的下一步，少套话。

### 工作方式
- 先理解用户目标，再选择合适工具或技能；需要时主动澄清关键约束。
- 能读本地文件、配置或文档时，先读再总结；不确定就说不知道，并指出应查看的路径。
- 涉及文件、代码或外部操作时，说明你将做什么并等待必要确认。
- 不编造配置项、路径或行为；涉及密钥或危险命令时提醒用户并先确认。

### 语言（普通对话优先）
- **中文优先**：用户用中文提问时，全文使用中文回复。
- 不要使用英文 FAQ/Q&A、英文小节标题或英文问答结构，除非用户明确要求英文。
- 若用户使用其他语言，则用相同语言回复；结构化输出（技能、计划、清单等）与用户输入语言一致。

### 边界
- 你不是泛用闲聊机器人；可简短回应后拉回与用户任务相关的帮助。
- **不要**自称其他岗位名称（如舆情分析师等数字员工）；那些是用户另行招募的专岗智能体。

### 多智能体协作（对用户保持 AgentDesk 品牌）
- 用户问「你用的什么模型」「你是谁」等元问题时，**直接作答**；不要调用 `list_agents` 或 `chat_with_agent`。
- 说明模型时，根据当前对话配置与运行上下文回答即可；**不要**提及底层框架、内置问答智能体或供应商内部代号。
- 仅在用户明确要求另一名数字员工参与时，才查询并调用广场中的岗位智能体。
"""


def is_default_agentdesk_assignee(name: str | None) -> bool:
    """Return True when *name* refers to the built-in default AgentDesk agent."""
    if name is None:
        return True
    normalized = str(name).strip()
    if not normalized:
        return True
    return normalized in _DEFAULT_ASSIGNEE_ALIASES


def is_builtin_qa_assignee(name_or_id: str | None) -> bool:
    """Return True when *name_or_id* refers to the builtin QwenPaw QA agent."""
    if name_or_id is None:
        return False
    normalized = str(name_or_id).strip()
    if not normalized:
        return False
    return (
        normalized in _BUILTIN_QA_ASSIGNEE_IDS
        or normalized in _BUILTIN_QA_ASSIGNEE_NAMES
    )


def is_plaza_hidden_assignee(name: str | None) -> bool:
    """Assignee/plaza lists must not surface built-in or hidden team leaders."""
    if is_default_agentdesk_assignee(name) or is_builtin_qa_assignee(name):
        return True
    from .team_leader_agents import is_team_leader_hidden

    return is_team_leader_hidden(name)


def _render_agentdesk_profile() -> str:
    return f"""---
summary: "AgentDesk 企伴 — 身份与用户资料"
read_when:
  - 手动引导工作区
---

## 身份

- **名字：** {DEFAULT_DISPLAY_NAME}
- **定位：** AgentDesk 默认通用工作助手 / 企业智能伴侣
- **风格：** 专业、清晰、务实；优先可执行的下一步
- **Agent ID：** `{DEFAULT_AGENT_ID}`

## 角色说明

{AGENTDESK_DEFAULT_DESCRIPTION}

### 行为准则

- 你就是「{DEFAULT_DISPLAY_NAME}」，请以此身份与用户交流。
- **不要**自称数字员工岗位名称或其他 agent 的名字。
- 用户用中文提问时，全文使用中文回复。
- 先理解用户目标，再选择合适工具或技能；需要时主动澄清关键约束。

## 用户资料

*了解你在帮的人。边走边更新。*

- **名字：**
- **怎么叫他们：**
- **代词：** *（可选）*
- **笔记：**

### 背景

*（他们在意什么？在做啥项目？什么让他们烦？什么逗他们笑？边走边积累。）*
"""


def ensure_agentdesk_default_agent_identity() -> None:
    """Sync default agent profile name/description and workspace PROFILE.md."""
    try:
        agent_config = load_agent_config(DEFAULT_AGENT_ID)
    except Exception as exc:  # noqa: BLE001 - user-edited config
        logger.debug(
            "Skipping AgentDesk default agent identity sync: %s",
            exc,
        )
        return

    updated = False
    if (agent_config.name or "").strip() != DEFAULT_DISPLAY_NAME:
        agent_config.name = DEFAULT_DISPLAY_NAME
        updated = True
    if (agent_config.description or "").strip() != AGENTDESK_DEFAULT_DESCRIPTION:
        agent_config.description = AGENTDESK_DEFAULT_DESCRIPTION
        updated = True

    # AgentDesk's default agent is the ONLY agent with long-term memory (the
    # workspace service gating leaves emp_*/lead_* without a memory_manager).
    # As the primary assistant it should actually use that memory, so enable
    # QwenPaw's native auto-memory: periodic write-back plus auto retrieval each
    # turn. This is pure native config on the persisted agent.json -- no kernel
    # changes -- and we only flip the disabled defaults so user customizations
    # (and the nightly ``dream_cron`` consolidation job) are preserved.
    running = getattr(agent_config, "running", None)
    memory_cfg = getattr(running, "reme_light_memory_config", None) if running else None
    if memory_cfg is not None:
        search_cfg = getattr(memory_cfg, "auto_memory_search_config", None)
        if search_cfg is not None and not getattr(search_cfg, "enabled", False):
            search_cfg.enabled = True
            updated = True
        if getattr(memory_cfg, "auto_memory_interval", None) is None:
            memory_cfg.auto_memory_interval = 5
            updated = True

    if updated:
        save_agent_config(DEFAULT_AGENT_ID, agent_config)
        logger.info("Updated AgentDesk default agent identity in agent config")

    workspace_dir = Path(agent_config.workspace_dir or "").expanduser()
    if not workspace_dir:
        return

    profile_path = workspace_dir / "PROFILE.md"
    profile_content = _render_agentdesk_profile()
    try:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        if not profile_path.exists() or profile_path.read_text(encoding="utf-8") != profile_content:
            profile_path.write_text(profile_content, encoding="utf-8")
            logger.info("Updated AgentDesk default agent PROFILE.md")
    except OSError as exc:
        logger.debug("Failed to write AgentDesk PROFILE.md: %s", exc)


def apply_agentdesk_default_persona(agent: object) -> None:
    """Append AgentDesk persona block to a freshly built default agent."""
    agent_config = getattr(agent, "_agent_config", None)
    running = getattr(agent_config, "running", None) if agent_config else None
    if running is not None:
        # Multi-step skill/tool workflows often emit interim text-only assistant
        # turns ("接下来我将…") without tool calls; auto-continue nudges extra
        # ReAct iterations (capped by react_agent._AUTO_CONTINUE_MAX_EXTRA).
        running.auto_continue_on_text_only = True

    suffix = AGENTDESK_DEFAULT_SYSTEM_PROMPT.strip()
    if not suffix:
        return

    current = str(getattr(agent, "_system_prompt", "") or "")
    if suffix in current:
        return

    updated = f"{current.rstrip()}\n\n{suffix}" if current.strip() else suffix
    setattr(agent, "_system_prompt", updated)

    state = getattr(agent, "state", None)
    if state is None:
        return

    from agentscope.message import TextBlock

    for msg in getattr(state, "context", []) or []:
        if getattr(msg, "role", None) == "system":
            msg.content = [TextBlock(type="text", text=updated)]
            break
