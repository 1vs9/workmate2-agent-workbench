# -*- coding: utf-8 -*-
"""AgentDesk one-sentence skill creation via make-skill agent orchestration."""

from __future__ import annotations

import re
import uuid
from typing import Any

import frontmatter as fm
from fastapi import HTTPException, Request

from qwenpaw.exceptions import SkillsError

from ..agents.skill_system import SkillPoolService
from ..agents.skill_system.store import get_workspace_skills_dir, read_skill_from_dir
from ..app.utils import schedule_agent_reload
from .agent_workspace import (
    agent_workspace_dir,
    resolve_agentdesk_agent_id,
)
from .locale import detect_user_language, is_chinese_language
from .skill_mount import ensure_skill_mounted
from .store import store as agentdesk_store

SKILL_CREATOR_SKILL = "make-skill"
EMPLOYEE_CREATOR_SKILL = "employee-creator"
SKILL_WIZARD_SENDER = "skill-creator"

_STUB_BODY_MARKERS = (
    "Break the work into concrete steps.",
    "Clarify the user's goal related to:",
    "Use this skill when the user asks for this capability.",
)

_MATERIALIZE_SUCCESS_RE = re.compile(
    r"\*\*Skill created and enabled\*\*:\s*`([^`]+)`",
    re.IGNORECASE,
)

_SKILL_FIND_PREFIX_RE = re.compile(r"请帮我查找", re.IGNORECASE)
_SKILL_FIND_RE = re.compile(
    r"(查找|搜索|寻找|找).{0,80}(安装|下载).{0,40}(skill|技能)",
    re.IGNORECASE,
)


def is_skill_find_message(message: str) -> bool:
    """True when the user wants to find/install an existing skill, not create one."""
    text = (message or "").strip()
    if not text:
        return False
    if _SKILL_FIND_PREFIX_RE.search(text):
        return True
    return bool(_SKILL_FIND_RE.search(text))


_SKILL_CREATE_META_HEAD_RE = re.compile(
    r"^(?:把|将)?(?:上述|以上|这些|上面|这个)",
    re.IGNORECASE,
)
_SKILL_CREATE_META_VERB_RE = re.compile(
    r"总结|概括|汇总|整理|归纳|描述|说明",
    re.IGNORECASE,
)
_SKILL_CREATE_META_INLINE_RE = re.compile(
    r"总结|概括|汇总|整理|归纳|描述成|说明成|改成|修改|优化|润色",
    re.IGNORECASE,
)
_SKILL_CREATE_DRAFT_RE = re.compile(
    r"请帮我创建一个可以实现「",
    re.IGNORECASE,
)
_SKILL_CREATE_REQUEST_RE = re.compile(
    r"请(?:帮我|为我)?(?:创建|新建|写一个|做一个|生成).{0,60}(?:skill|技能)",
    re.IGNORECASE,
)
_SKILL_CREATE_EN_RE = re.compile(r"^create\s+(?:a\s+)?skill\b", re.IGNORECASE)


def _is_skill_create_meta_message(text: str) -> bool:
    first_line = (text.splitlines()[0] if text.splitlines() else text).strip()
    if _SKILL_CREATE_META_HEAD_RE.search(first_line) and _SKILL_CREATE_META_VERB_RE.search(
        first_line,
    ):
        return True
    if re.match(r"^(?:总结|概括|汇总|整理|归纳|描述|说明)", first_line, re.IGNORECASE):
        return True
    return bool(_SKILL_CREATE_META_INLINE_RE.search(text[:60]))


def is_skill_create_message(message: str) -> bool:
    """True when the user explicitly asks to create a new skill."""
    text = (message or "").strip()
    if not text or is_skill_find_message(text) or _is_skill_create_meta_message(text):
        return False

    if _SKILL_CREATE_DRAFT_RE.search(text) and re.search(
        r"」的\s*skill",
        text,
        re.IGNORECASE,
    ):
        return True

    probe = text if len(text) <= 120 else (text.splitlines()[0] if text.splitlines() else text).strip()
    if _SKILL_CREATE_REQUEST_RE.search(probe):
        return True
    if re.search(r"/make-skill\b", probe, re.IGNORECASE):
        return True
    return bool(_SKILL_CREATE_EN_RE.search(probe))


def build_skill_find_agent_message(user_text: str) -> str:
    """Prompt the default agent to search pool + cloud market, not create skills."""
    capability = extract_skill_purpose(user_text)
    language = detect_user_language(user_text)
    if is_chinese_language(language):
        return (
            "AgentDesk 技能查找：帮用户在本地技能池与云端技能市场中找到并安装匹配的技能。\n\n"
            "规则：\n"
            "- 不要调用 `materialize_skill`，不要新建 SKILL.md 或使用 skill-creator 流程。\n"
            "- 先在本地 skill pool / 已安装技能中搜索（如 `/api/skills/pool`、"
            "工作区技能列表、技能池目录）。\n"
            "- 若无合适结果，再搜索云端市场（如 `POST /api/market/search`、"
            "`GET /api/skills/hub/search`，覆盖 ClawHub / ModelScope / SkillsMP 等源）。\n"
            "- 找到匹配项后通过 hub install 或 pool 安装 API 安装，并告知技能名与用法。\n"
            "- 若本地与云端均无匹配，说明情况；可建议用户改用「创建技能」或手动上传。\n\n"
            f"用户请求：{user_text.strip()}\n"
            f"能力关键词：{capability}\n"
        )
    return (
        "AgentDesk skill lookup: find and install an existing skill from the local pool "
        "and cloud market — do not create a new skill.\n\n"
        "Rules:\n"
        "- Do NOT call `materialize_skill` or write a new SKILL.md.\n"
        "- Search the local skill pool / installed skills first.\n"
        "- If nothing fits, search the cloud market (`POST /api/market/search`, "
        "`GET /api/skills/hub/search`).\n"
        "- Install the best match via hub/pool install APIs and tell the user how to use it.\n"
        "- If no match exists, say so and suggest create/upload instead.\n\n"
        f"User request: {user_text.strip()}\n"
        f"Capability keywords: {capability}\n"
    )


def extract_skill_purpose(message: str) -> str:
    """Pull the skill goal from a natural-language create request."""
    text = (message or "").strip()
    if not text:
        return ""

    quoted = re.search(r"[「『]([^」』]+)[」』]", text)
    if quoted:
        return quoted.group(1).strip()

    match = re.search(
        r"(?:创建|新建|写一个|做一个|生成)\s*(?:一个)?(?:可以实现)?(.{2,120}?)(?:的)?(?:skill|技能)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip("「」『』 \t，,。.!！?？")

    return text[:120].strip()


def propose_skill_name(purpose: str, *, existing: set[str] | None = None) -> str:
    """Derive a pool-safe skill directory name from the purpose text."""
    existing = existing or set()
    slug = re.sub(r"[^\w\s-]", "", purpose, flags=re.UNICODE)
    slug = re.sub(r"[\s_]+", "-", slug.strip()).strip("-").lower()
    if len(slug) >= 3 and re.fullmatch(r"[\w-]+", slug):
        base = slug[:48]
    else:
        base = f"agentdesk-skill-{uuid.uuid4().hex[:8]}"

    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def build_employee_create_agent_message(user_text: str) -> str:
    """Prompt the default agent to create an employee in one deterministic pass."""
    language = detect_user_language(user_text)
    if is_chinese_language(language):
        return (
            "AgentDesk 快速创建员工：在本轮内一次性完成数字员工创建，不做环境探测。\n\n"
            "规则：\n"
            "- 跳过 `create_plan`、首次引导问卷（BOOTSTRAP）和多步追问。\n"
            "- 若用户消息已包含名称、专长、背景且无占位符（如 XXX、[请补充…]），"
            "直接调用 API 创建，无需二次确认。\n"
            "- **必须自动绑定技能**：根据专长推荐 2–4 个技能（文档→docx、表格→xlsx、"
            "规划→make_plan、阅读→file_reader）；用户消息已列出技能名时优先采用。\n"
            "- 避免全量扫描技能池；只有在技能名不确定时才调用一次 `GET /api/skills`，"
            "且仅做精确名称匹配。\n"
            "- API 基址优先使用已知配置/环境给定值；本地默认 `http://127.0.0.1:8088/api`。\n"
            "- **优先调用 `create_agentdesk_employee` 工具**完成创建；"
            "不要用 `execute_shell_command` + curl/Invoke-WebRequest。\n"
            "- 严格使用 AgentDesk API 路径（`/api/plaza`、`/api/plaza/<name>/join`、"
            "`/api/skills/...`），不要访问前端 HTML 路由。\n"
            "- `POST /api/plaza` 的 JSON body **必须包含** `skills: [\"...\"]` 数组。\n"
            "- 再调用 `POST /api/plaza/<url-encoded-name>/join`；若返回 `joined: true` "
            "且含 skills/mounted_skills，视为技能已生效并结束流程。\n"
            "- **不要**在 join 成功后逐个 mount；仅当 join 返回明确失败技能（如 "
            "`failed_skills`）时，才对失败项执行 `POST /api/skills/<skill>/mount`。\n"
            "- `mount` 路径参数使用技能标识（后端会解析别名），不要猜测技能 ID/名称映射。\n"
            "- 创建完成后只做一次最终确认（读取 join 返回或单次 `GET /api/employees`）。\n"
            "- API 成功前不要声称已创建成功；失败时返回具体错误。\n\n"
            "推荐流程（最少调用）：\n"
            "1) `create_agentdesk_employee`（一次完成 plaza + join）\n"
            "2) 仅在 join 报告 failed_skills 时，对失败项补 `mount`\n"
            "3) 返回创建结果与已绑定技能\n\n"
            f"用户请求：{user_text.strip()}\n"
        )
    return (
        "AgentDesk quick-create employee: finish creation in one deterministic pass.\n\n"
        "Rules:\n"
        "- Skip `create_plan`, BOOTSTRAP onboarding, and multi-step questionnaires.\n"
        "- When name, specialty, and background are present with no placeholders "
        "(e.g. XXX, [please add…]), call the APIs directly without asking again.\n"
        "- **Auto-bind skills**: recommend 2-4 skills (docs->docx, spreadsheets->xlsx, "
        "planning->make_plan, reading->file_reader); honor explicit names from the user.\n"
        "- Avoid full skill dumps. Call `GET /api/skills` once only when a name needs "
        "exact matching.\n"
        "- Base URL should come from known config/environment; default to "
        "`http://127.0.0.1:8088/api` for local runs.\n"
        "- **Prefer `create_agentdesk_employee`**; do not use "
        "`execute_shell_command` with curl or Invoke-WebRequest.\n"
        "- Use only AgentDesk API routes (`/api/plaza`, `/api/plaza/<name>/join`, "
        "`/api/skills/...`), never frontend HTML pages.\n"
        "- `POST /api/plaza` body **must include** `skills: [\"...\"]`.\n"
        "- Then call `POST /api/plaza/<url-encoded-name>/join`; when join returns "
        "`joined: true` with skills/mounted_skills, trust it and stop.\n"
        "- Do **not** loop over per-skill mount after successful join. Mount only "
        "for explicit `failed_skills` returned by join.\n"
        "- Mount path parameter uses a skill identifier; backend resolves name aliases.\n"
        "- Perform only one final verification (join payload or one `GET /api/employees`).\n"
        "- Do not claim success until APIs succeed; report errors clearly.\n\n"
        "Recommended minimal call sequence:\n"
        "1) `create_agentdesk_employee` (plaza + join in one tool call)\n"
        "2) fallback `mount` only for `failed_skills`\n"
        "3) return result and bound skills\n\n"
        f"User request: {user_text.strip()}\n"
    )


def build_skill_create_agent_message(user_text: str) -> str:
    """Prompt the make-skill agent to create a skill in one turn (no plan gate)."""
    purpose = extract_skill_purpose(user_text)
    suggested_name = propose_skill_name(purpose)
    language = detect_user_language(user_text)
    if is_chinese_language(language):
        return (
            "AgentDesk 快速创建：根据用户的一句话需求，在本轮直接生成新的 workspace 技能。\n\n"
            "规则：\n"
            "- 跳过 `create_plan`、用户审批和多步问卷。\n"
            "- 撰写完整、面向领域的 SKILL.md 正文（不要通用英文模板）。\n"
            "- `description`、正文、步骤说明、FAQ/问答等结构化内容一律使用中文，"
            "与用户请求语言一致。\n"
            "- 调用 `materialize_skill`，传入 `name`、`description`、`body`。\n"
            "- 不要用 `write_file` / `edit_file` 写 SKILL.md。\n"
            "- `materialize_skill` 成功前不要声称已创建成功。\n\n"
            f"建议技能名：`{suggested_name}`\n"
            f"用户请求：{user_text.strip()}\n"
            f"重点：{purpose}\n"
        )
    return (
        "AgentDesk quick-create: turn the user's one-line request into a new workspace "
        "skill in this turn.\n\n"
        "Rules:\n"
        "- Skip `create_plan`, user approval, and multi-step questionnaires.\n"
        "- Write a complete, domain-specific SKILL.md body (not a generic template).\n"
        "- Keep `description`, body, steps, and any FAQ/Q&A sections in the same "
        "language as the user request.\n"
        "- Call `materialize_skill` with `name`, `description`, and `body`.\n"
        "- Do not use `write_file` / `edit_file` for SKILL.md.\n"
        "- Do not claim success until `materialize_skill` returns success.\n\n"
        f"Suggested skill name: `{suggested_name}`\n"
        f"User request: {user_text.strip()}\n"
        f"Focus: {purpose}\n"
    )


def parse_materialize_skill_success(detail: str) -> str | None:
    """Return created skill name when materialize_skill output indicates success."""
    text = (detail or "").strip()
    if not text:
        return None
    match = _MATERIALIZE_SUCCESS_RE.search(text)
    if match:
        return match.group(1).strip()
    if "skill created and enabled" in text.lower():
        backtick = re.search(r"`([^`]+)`", text)
        if backtick:
            return backtick.group(1).strip()
    return None


def _skill_body_without_frontmatter(content: str) -> str:
    raw = (content or "").strip()
    if raw.startswith("---"):
        post = fm.loads(raw)
        return (post.content or "").strip()
    return raw


def is_substantive_skill_content(content: str, *, min_body_chars: int = 120) -> bool:
    """Reject template-only or empty SKILL.md bodies."""
    body = _skill_body_without_frontmatter(content)
    if len(body) < min_body_chars:
        return False
    stub_hits = sum(1 for marker in _STUB_BODY_MARKERS if marker in body)
    return stub_hits < 2


def ensure_packaged_builtin_in_pool(
    skill_name: str,
    *,
    user_text: str | None = None,
) -> None:
    """Import a packaged builtin into the skill pool when it is missing."""
    from ..agents.skill_system.registry import (
        ensure_skill_pool_initialized,
        get_packaged_builtin_versions,
        import_builtin_skills,
    )

    normalized = str(skill_name or "").strip()
    if not normalized or normalized not in get_packaged_builtin_versions():
        return
    ensure_skill_pool_initialized()
    language = detect_user_language(user_text or "")
    import_builtin_skills(
        [{"skill_name": normalized, "language": language}],
    )


def ensure_agentdesk_builtin_mounted(
    *,
    skill_name: str,
    agent_id: str,
    request: Request | None,
    user_text: str | None = None,
    overwrite: bool = False,
) -> None:
    """Ensure a packaged builtin is in the pool and mounted on the agent."""
    ensure_packaged_builtin_in_pool(skill_name, user_text=user_text)
    ensure_skill_mounted(
        skill_name=skill_name,
        agent_id=agent_id,
        overwrite=overwrite,
    )
    schedule_agent_reload(request, agent_id)


def ensure_skill_creator_mounted(
    *,
    agent_id: str,
    request: Request | None,
    user_text: str | None = None,
) -> list[str]:
    """Ensure make-skill exists in the pool and is mounted on the agent."""
    ensure_agentdesk_builtin_mounted(
        skill_name=SKILL_CREATOR_SKILL,
        agent_id=agent_id,
        request=request,
        user_text=user_text,
        overwrite=True,
    )
    return [SKILL_CREATOR_SKILL]


def ensure_employee_creator_mounted(
    *,
    agent_id: str,
    request: Request | None,
    user_text: str | None = None,
) -> list[str]:
    """Ensure employee-creator exists in the pool and is mounted on the agent."""
    ensure_agentdesk_builtin_mounted(
        skill_name=EMPLOYEE_CREATOR_SKILL,
        agent_id=agent_id,
        request=request,
        user_text=user_text,
        overwrite=False,
    )
    return [EMPLOYEE_CREATOR_SKILL]


def _agent_workspace_dir(agent_id: str) -> Path:
    try:
        return agent_workspace_dir(agent_id)
    except HTTPException as exc:
        raise SkillsError(message=str(exc.detail)) from exc


def load_created_skill(agent_id: str, skill_name: str) -> dict[str, str] | None:
    """Load a workspace skill created by materialize_skill if it is substantive."""
    workspace_dir = _agent_workspace_dir(agent_id)
    skill_root = get_workspace_skills_dir(workspace_dir)
    skill = read_skill_from_dir(skill_root / skill_name, "agent")
    if skill is None:
        return None
    if not is_substantive_skill_content(skill.content):
        return None
    return {
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "purpose": skill.description,
    }


def sync_created_skill_to_pool_and_store(
    created: dict[str, str],
    *,
    agent_id: str,
) -> dict[str, str]:
    """Mirror a workspace skill into the shared pool and AgentDesk store."""
    pool = SkillPoolService()
    pool_names = {skill.name for skill in pool.list_all_skills()}
    name = created["name"]
    if name not in pool_names:
        created_name = pool.create_skill(
            name=name,
            content=created["content"],
            installed_from="agentdesk-skill-wizard",
        )
        if created_name is None:
            workspace_dir = _agent_workspace_dir(agent_id)
            upload_result = pool.upload_from_workspace(workspace_dir, name)
            if not upload_result.get("success"):
                raise SkillsError(message="技能已写入工作区，但同步到技能池失败。")
            name = str(upload_result.get("name") or name)
        else:
            name = created_name

    agentdesk_store.upsert_by_key(
        "skills",
        "name",
        name,
        {
            "name": name,
            "description": created["description"],
            "body": created["content"],
            "source": "agentdesk",
        },
    )
    return {**created, "name": name}


def persist_task_wizard(task_id: str, wizard: dict[str, Any]) -> None:
    """Persist wizard state on the task for GET /api/tasks/{id}/plan."""
    task = agentdesk_store.get_by_key("tasks", "id", task_id) or agentdesk_store.ensure_task(
        task_id,
    )
    status = str(wizard.get("status") or "idle")
    task["wizard"] = wizard
    task["plan_status"] = status
    agentdesk_store.upsert_by_key("tasks", "id", task_id, task)


def build_skill_done_wizard(created: dict[str, str]) -> dict[str, Any]:
    """Wizard payload returned to the frontend on successful create."""
    name = created["name"]
    return {
        "kind": "skill_create",
        "status": "skill_done",
        "mode": "create",
        "questions": [],
        "answers": {},
        "created_skill": {
            "name": name,
            "description": created["description"],
            "body": created["content"],
            "dir": name,
        },
    }


def build_skill_failed_wizard(*, reason: str) -> dict[str, Any]:
    """Wizard payload when orchestration did not produce a real skill."""
    return {
        "kind": "skill_create",
        "status": "skill_failed",
        "mode": "create",
        "questions": [],
        "answers": {},
        "error": reason,
    }


def resolve_skill_wizard_agent_id(employee_name: str | None) -> str:
    """Agent profile used for skill-create orchestration."""
    return resolve_agentdesk_agent_id(employee_name)
