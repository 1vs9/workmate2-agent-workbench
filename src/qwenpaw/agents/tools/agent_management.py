# -*- coding: utf-8 -*-
"""Tools and shared helpers for agent discovery and inter-agent chat."""

import asyncio
import json
import re
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

import httpx
from agentscope.message import TextBlock
from agentscope.tool import ToolChunk
from agentscope.message import ToolResultState

from ...config.utils import read_last_api
from ...runtime.worker_stream_bus import WORKER_STREAM_DONE_SENTINEL, worker_stream_bus
from ...utils.http import trust_env_for_url


DEFAULT_AGENT_API_BASE_URL = "http://127.0.0.1:8088"
DEFAULT_AGENT_API_TIMEOUT = 30.0
TASK_SUBMIT_TIMEOUT = 60


def resolve_agent_api_base_url(base_url: Optional[str] = None) -> str:
    """Resolve the agent API base URL.

    Priority:
    1. Explicit ``base_url`` argument
    2. Last recorded API host/port from config
    3. Built-in localhost fallback
    """
    if base_url:
        return base_url.rstrip("/")

    last_api = read_last_api()
    if last_api:
        host, port = last_api
        return f"http://{host}:{port}"

    return DEFAULT_AGENT_API_BASE_URL


def _normalize_api_base_url(base_url: Optional[str]) -> str:
    base = resolve_agent_api_base_url(base_url).rstrip("/")
    if not base.endswith("/api"):
        base = f"{base}/api"
    return base


def _tool_text_response(text: str) -> ToolChunk:
    return ToolChunk(
        is_last=True,
        state=ToolResultState.SUCCESS,
        content=[TextBlock(type="text", text=text)],
    )


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def normalize_id(id_to_normalize: Optional[str]) -> Optional[str]:
    """Trim surrounding whitespace and quotes from an ID."""
    if id_to_normalize is None:
        return None
    return id_to_normalize.strip().strip("\"'").strip()


def create_agent_api_client(
    base_url: Optional[str],
    default_timeout: float = DEFAULT_AGENT_API_TIMEOUT,
) -> httpx.Client:
    """Create an HTTP client targeting the local agent API."""
    normalized = _normalize_api_base_url(base_url)
    return httpx.Client(
        base_url=normalized,
        timeout=default_timeout,
        trust_env=trust_env_for_url(normalized),
    )


def generate_unique_session_id(from_agent: str, to_agent: str) -> str:
    """Generate a concurrency-safe session ID for inter-agent chat."""
    timestamp = int(time.time() * 1000)
    uuid_short = str(uuid4())[:8]
    return f"{from_agent}:to:{to_agent}:{timestamp}:{uuid_short}"


def _team_root_task_id(root_session_id: Optional[str]) -> str:
    """Derive the root team task id from a root/leader/member session id."""
    raw = str(root_session_id or "").strip()
    if not raw:
        return ""
    marker = ":team:"
    if marker in raw:
        return raw.split(marker, 1)[0].strip()
    return raw


_TEAM_LEADER_NATIVE_MARKER = ":team:leader-native"


def resolve_team_delegation_root_session(
    caller_session_id: Optional[str],
    caller_root_session: Optional[str],
) -> str:
    """Prefer the leader-native session as the team task root for worker routing.

    AgentDesk team runs key worker bus subscriptions by ``{task_id}:team:member:…``.
    If ``root_session_id`` is a stale bare team id while ``session_id`` is the
    leader-native session, member workers would publish to the wrong bus key.
    """
    sid = str(caller_session_id or "").strip()
    if _TEAM_LEADER_NATIVE_MARKER in sid:
        return sid
    root = str(caller_root_session or "").strip()
    if _TEAM_LEADER_NATIVE_MARKER in root:
        return root
    return root or sid


def _team_member_session_suffix(member_name: str) -> str:
    safe = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9:_·-]+", "_", str(member_name or "").strip())[:48]
    return f"member:{safe or 'unknown'}"


def _team_member_session_id(root_session_id: Optional[str], member_name: str) -> str:
    task_root = _team_root_task_id(root_session_id)
    if not task_root:
        return ""
    return f"{task_root}:team:{_team_member_session_suffix(member_name)}"


def _is_team_member_session_id(session_id: str) -> bool:
    sid = str(session_id or "").strip()
    return ":team:member:" in sid or ":team:member-" in sid


def worker_stream_publish_key(
    session_id: str,
    root_session_id: Optional[str],
) -> Optional[str]:
    """Key for worker SSE fan-out: member native session when in team mode."""
    sid = str(session_id or "").strip()
    if _is_team_member_session_id(sid):
        return sid
    root = str(root_session_id or "").strip()
    return root or sid or None


def _resolve_team_member_name_for_target(
    caller_agent_id: str,
    target_agent_id: str,
) -> Optional[str]:
    """Return roster member name when a team leader targets one of its workers."""
    try:
        from ...agentdesk.team_leader_agents import (
            agent_matches_team_roster,
            team_roster_for_leader_agent,
        )
    except Exception:  # noqa: BLE001
        return None

    roster = team_roster_for_leader_agent(caller_agent_id)
    if not roster:
        return None
    normalized_target = str(target_agent_id or "").strip()
    if not normalized_target:
        return None
    for member_name in roster:
        if agent_matches_team_roster(normalized_target, [str(member_name)]):
            return str(member_name).strip()
    return None


def resolve_calling_agent_id(from_agent: Optional[str] = None) -> str:
    """Resolve the calling agent ID.

    Priority:
    1. Explicit ``from_agent`` argument
    2. Current runtime agent context
    """
    if from_agent:
        return from_agent
    from ...app.agent_context import get_current_agent_id

    return get_current_agent_id()


def resolve_agent_session_id(
    from_agent: Optional[str],
    to_agent: str,
    session_id: Optional[str],
    root_session_id: Optional[str] = None,
) -> str:
    """Resolve the effective session ID based on session reuse semantics."""
    caller_agent_id = resolve_calling_agent_id(from_agent)
    if not session_id:
        member_name = _resolve_team_member_name_for_target(
            caller_agent_id,
            to_agent,
        )
        if member_name:
            member_session_id = _team_member_session_id(
                root_session_id,
                member_name,
            )
            if member_session_id:
                return member_session_id
        return generate_unique_session_id(caller_agent_id, to_agent)
    return session_id


def ensure_agent_identity_prefix(
    text: str,
    from_agent: Optional[str] = None,
) -> str:
    """Prefix inter-agent prompts so the target knows the message source."""
    caller_agent_id = resolve_calling_agent_id(from_agent)
    patterns = [
        r"^\[Agent\s+\w+",
        r"^\[来自智能体\s+\w+",
    ]
    stripped = text.strip()
    for pattern in patterns:
        if re.match(pattern, stripped):
            return text
    return f"[Agent {caller_agent_id} requesting] {text}"


def parse_agent_sse_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single SSE line emitted by /console/chat."""
    stripped = line.strip()
    if stripped.startswith("data: "):
        try:
            return json.loads(stripped[6:])
        except json.JSONDecodeError:
            return None
    return None


def is_completed_agent_sse_response(payload: Dict[str, Any]) -> bool:
    """True when *payload* is a terminal console ``response`` envelope."""
    if str(payload.get("object") or "") != "response":
        return False
    return str(payload.get("status") or "").lower() == "completed"


def merge_agent_sse_snapshot(
    current: Optional[Dict[str, Any]],
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep the best console SSE snapshot seen so far.

    Heartbeats and in-progress envelopes can arrive after tool output but
    before the model's final text. Always prefer the completed ``response``
    event so background task pollers see the full worker reply.
    """
    if not parsed:
        return dict(current or {})
    if not current:
        return parsed
    if is_completed_agent_sse_response(parsed):
        return parsed
    if is_completed_agent_sse_response(current):
        return current
    cur_out = current.get("output") or []
    new_out = parsed.get("output") or []
    if len(new_out) > len(cur_out):
        return parsed
    if len(new_out) == len(cur_out):
        return parsed
    return current


_EMPTY_AGENT_REPLY_MARKERS = frozenset(
    {"(No text content in response)", "(No response received)"},
)


def is_empty_agent_reply_text(text: str) -> bool:
    """True when agent chat formatting found no usable reply body."""
    normalized = str(text or "").strip()
    return not normalized or normalized in _EMPTY_AGENT_REPLY_MARKERS


def extract_agent_text_content(response_data: Dict[str, Any]) -> str:
    """Extract concatenated text blocks from an agent response payload."""
    try:
        output = response_data.get("output", [])
        if not output:
            return ""

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        for msg in output:
            if not isinstance(msg, dict):
                continue
            for item in msg.get("content") or []:
                if not isinstance(item, dict):
                    continue
                block_type = item.get("type")
                piece = str(item.get("text") or "")
                if not piece:
                    continue
                if block_type == "text":
                    text_parts.append(piece)
                elif block_type in ("reasoning", "thinking"):
                    reasoning_parts.append(piece)

        text = "\n".join(text_parts).strip()
        if text:
            return text
        return "\n".join(reasoning_parts).strip()
    except (KeyError, IndexError, TypeError):
        return ""


def _filter_agent_list_for_agentdesk(data: Dict[str, Any]) -> Dict[str, Any]:
    """Hide builtin/default agents from AgentDesk inter-agent collaboration."""
    try:
        from ...agentdesk.default_agent import is_plaza_hidden_assignee
        from ...agentdesk.settings import is_agentdesk_enabled
    except ImportError:
        return data

    if not is_agentdesk_enabled():
        return data

    agents = data.get("agents", [])
    if not isinstance(agents, list):
        return data

    filtered = [
        agent
        for agent in agents
        if isinstance(agent, dict)
        and not is_plaza_hidden_assignee(agent.get("id"))
        and not is_plaza_hidden_assignee(agent.get("name"))
    ]
    return {**data, "agents": filtered}


def _filter_agent_list_for_team_caller(data: Dict[str, Any]) -> Dict[str, Any]:
    """Scope ``list_agents`` for team leaders and workers in AgentDesk team mode."""
    try:
        from ...app.agent_context import get_current_agent_id
        from ...agentdesk.team_leader_agents import (
            agent_matches_team_roster,
            team_roster_for_leader_agent,
            team_roster_for_worker_agent,
        )
    except ImportError:
        return data

    caller_id = get_current_agent_id()

    if team_roster_for_worker_agent(caller_id) is not None:
        return {**data, "agents": []}

    roster = team_roster_for_leader_agent(caller_id)
    if roster is None:
        return data

    agents = data.get("agents", [])
    if not isinstance(agents, list):
        return data

    filtered = [
        agent
        for agent in agents
        if isinstance(agent, dict)
        and agent_matches_team_roster(str(agent.get("id") or ""), roster)
    ]
    return {**data, "agents": filtered}


def _team_delegation_violation(resolved_agent_id: str) -> Optional[str]:
    """Return an error when inter-agent delegation violates team role boundaries."""
    try:
        from ...app.agent_context import get_current_agent_id
        from ...agentdesk.team_leader_agents import (
            agent_matches_team_roster,
            format_team_roster_hint,
            team_roster_for_leader_agent,
            team_roster_for_worker_agent,
        )
    except ImportError:
        return None

    caller_id = get_current_agent_id()

    if team_roster_for_worker_agent(caller_id) is not None:
        return (
            "ERROR: Team workers cannot delegate to other agents. "
            "Only the team leader may assign work via chat_with_agent."
        )

    roster = team_roster_for_leader_agent(caller_id)
    if roster is None:
        return None
    if agent_matches_team_roster(resolved_agent_id, roster):
        return None
    hint = format_team_roster_hint(roster)
    return (
        f"ERROR: Agent [{resolved_agent_id}] is not a member of this team. "
        f"Delegate only to team workers: {hint}."
    )


def _agentdesk_blocks_agent_target(agent_id: Optional[str]) -> bool:
    """Return True when AgentDesk must not route chat to *agent_id*."""
    if not agent_id:
        return False
    try:
        from ...agentdesk.default_agent import is_plaza_hidden_assignee
        from ...agentdesk.settings import is_agentdesk_enabled
    except ImportError:
        return False
    return is_agentdesk_enabled() and is_plaza_hidden_assignee(agent_id)


def list_agents_data(
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch the configured agent list from the local API."""
    with create_agent_api_client(base_url) as client:
        response = client.get("/agents")
        response.raise_for_status()
        data = _filter_agent_list_for_agentdesk(response.json())
        return _filter_agent_list_for_team_caller(data)


def extract_agent_ids(agent_list_data: Dict[str, Any]) -> set[str]:
    """Extract configured agent IDs from the /agents payload."""
    agents = agent_list_data.get("agents", [])
    if not isinstance(agents, list):
        return set()

    agent_ids = set()
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("id")
        if isinstance(agent_id, str) and agent_id:
            agent_ids.add(agent_id)
    return agent_ids


def agent_exists(
    to_agent: str,
    base_url: Optional[str] = None,
) -> bool:
    """Check whether the target agent exists in the configured agent list."""
    if _agentdesk_blocks_agent_target(to_agent):
        return False
    return to_agent in extract_agent_ids(list_agents_data(base_url))


def resolve_agent_target(
    to_agent: str,
    base_url: Optional[str] = None,
) -> Optional[str]:
    """Resolve *to_agent* (an agent id or display name) to a real agent id.

    Delegating agents (e.g. team leaders) are instructed to address members by
    their display name (``@成员名``), but the underlying chat endpoint only
    accepts canonical agent ids. This resolver bridges the two by matching the
    target against the configured agent list, by id first and then by display
    name (case-insensitive). Returns ``None`` when nothing matches so callers
    can surface a clear, self-correcting error instead of silently failing.
    """
    target = normalize_id(to_agent)
    if not target or _agentdesk_blocks_agent_target(target):
        return None

    agents = list_agents_data(base_url).get("agents", [])
    if not isinstance(agents, list):
        return None

    id_map: Dict[str, str] = {}
    name_map: Dict[str, str] = {}
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        id_map[agent_id] = agent_id
        id_map[agent_id.casefold()] = agent_id
        name = agent.get("name")
        if isinstance(name, str) and name.strip():
            name_map.setdefault(name.strip().casefold(), agent_id)

    if target in id_map:
        return id_map[target]
    lowered = target.casefold()
    if lowered in id_map:
        return id_map[lowered]
    return name_map.get(lowered)


def _available_agent_targets(base_url: Optional[str] = None) -> str:
    """Return a human-readable ``name (id)`` list of delegable agents."""
    try:
        agents = list_agents_data(base_url).get("agents", [])
    except Exception:  # noqa: BLE001 - hint only, never fail the caller
        return ""
    if not isinstance(agents, list):
        return ""
    parts = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        name = agent.get("name")
        if isinstance(name, str) and name.strip():
            parts.append(f"{name.strip()} ({agent_id})")
        else:
            parts.append(agent_id)
    return ", ".join(parts)


def build_agent_chat_request(
    to_agent: str,
    text: str,
    session_id: Optional[str] = None,
    from_agent: Optional[str] = None,
    root_session_id: Optional[str] = None,
) -> tuple[str, Dict[str, Any], bool]:
    """Build the inter-agent chat payload and resolve the final session ID.

    Args:
        to_agent: Target agent ID
        text: Message text
        session_id: Optional session ID override
        from_agent: Calling agent ID (for identity prefix)
        root_session_id: Root session ID for cross-session approval routing

    Returns:
        Tuple of (final_session_id, request_payload, text_was_prefixed)
    """
    caller_agent_id = resolve_calling_agent_id(from_agent)
    final_session_id = resolve_agent_session_id(
        caller_agent_id,
        to_agent,
        session_id,
        root_session_id,
    )
    final_text = ensure_agent_identity_prefix(text, caller_agent_id)
    request_payload = {
        "session_id": final_session_id,
        "input": [
            {
                "role": "user",
                "content": [{"type": "text", "text": final_text}],
            },
        ],
        "request_context": {
            "root_agent_id": caller_agent_id,
        },
    }

    # Add root_session_id to request_context for cross-session approval routing
    if root_session_id:
        request_payload["request_context"]["root_session_id"] = root_session_id

    return final_session_id, request_payload, final_text != text


def _request_headers(
    to_agent: Optional[str],
) -> Dict[str, str]:
    """Build HTTP headers for agent chat requests.

    Args:
        to_agent: Target agent ID

    Returns:
        Dictionary of HTTP headers
    """
    headers = {}
    if to_agent:
        headers["X-Agent-Id"] = to_agent
    return headers


def stream_agent_chat(
    base_url: Optional[str],
    request_payload: Dict[str, Any],
    to_agent: str,
    timeout: int,
    line_handler: Callable[[str], None] | None = None,
) -> list[str]:
    """Stream SSE lines from inter-agent chat."""
    lines: list[str] = []
    with create_agent_api_client(base_url, default_timeout=timeout) as client:
        with client.stream(
            "POST",
            "/console/chat",
            json=request_payload,
            headers=_request_headers(to_agent),
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    lines.append(line)
                    if line_handler is not None:
                        line_handler(line)
    return lines


def collect_final_agent_chat_response(
    base_url: Optional[str],
    request_payload: Dict[str, Any],
    to_agent: str,
    timeout: int,
    publish_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Collect the last SSE payload from inter-agent chat.

    When *publish_key* is provided and the worker stream bus has subscribers for
    it, each raw SSE line is also forwarded to the bus so the caller (e.g. the
    team-mode stream) can surface the worker's intermediate progress live.
    """
    response_data: Optional[Dict[str, Any]] = None
    publish_key_str = str(publish_key or "").strip()
    published_any = False
    with create_agent_api_client(base_url, default_timeout=timeout) as client:
        with client.stream(
            "POST",
            "/console/chat",
            json=request_payload,
            headers=_request_headers(to_agent),
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                if (
                    publish_key_str
                    and worker_stream_bus.has_subscribers(publish_key_str)
                ):
                    worker_stream_bus.publish(
                        publish_key_str,
                        (to_agent, line),
                    )
                    published_any = True
                parsed = parse_agent_sse_line(line)
                if parsed:
                    response_data = merge_agent_sse_snapshot(
                        response_data,
                        parsed,
                    )
    if (
        published_any
        and publish_key_str
        and worker_stream_bus.has_subscribers(publish_key_str)
    ):
        worker_stream_bus.publish(
            publish_key_str,
            (to_agent, WORKER_STREAM_DONE_SENTINEL),
        )
    return response_data


def submit_agent_chat_task(
    base_url: Optional[str],
    request_payload: Dict[str, Any],
    to_agent: str,
    timeout: int,
    task_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Submit an inter-agent chat task for background execution."""
    payload = dict(request_payload)
    if task_timeout is not None:
        payload["timeout"] = task_timeout
    with create_agent_api_client(base_url) as client:
        response = client.post(
            "/console/chat/task",
            json=payload,
            headers=_request_headers(to_agent),
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()


def get_agent_chat_task_status(
    base_url: Optional[str],
    task_id: str,
    to_agent: Optional[str] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Get the current status for a background inter-agent chat task."""
    polling_agent = to_agent or resolve_calling_agent_id()
    with create_agent_api_client(base_url) as client:
        response = client.get(
            f"/console/chat/task/{task_id}",
            headers=_request_headers(polling_agent),
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()


def format_agent_chat_text(
    response_data: Dict[str, Any],
    session_id: Optional[str] = None,
) -> str:
    """Format agent chat output as plain text for tool consumption."""
    text = extract_agent_text_content(response_data)
    parts: list[str] = []
    if session_id:
        parts.append(f"[SESSION: {session_id}]")
        parts.append("")
    parts.append(text or "(No text content in response)")
    return "\n".join(parts)


def format_background_submission_text(
    task_result: Dict[str, Any],
    session_id: str,
) -> str:
    """Format background submission result as plain text."""
    task_id = task_result.get("task_id")
    if not task_id:
        return "ERROR: No task_id returned from server"

    return "\n".join(
        [
            f"[TASK_ID: {task_id}]",
            f"[SESSION: {session_id}]",
            "",
            "Task submitted successfully.",
            "Check status with: check_agent_task(" f"task_id='{task_id}')",
        ],
    )


def format_background_status_text(
    task_id: str,
    result: Dict[str, Any],
) -> str:
    """Format background task status as plain text."""
    status = result.get("status", "unknown")
    parts = [f"[TASK_ID: {task_id}]", f"[STATUS: {status}]", ""]

    if status == "finished":
        task_result = result.get("result", {})
        task_status = task_result.get("status")
        if task_status == "completed":
            parts.append("Task completed.")
            parts.append("")
            parts.append(
                format_agent_chat_text(
                    task_result,
                    session_id=task_result.get("session_id"),
                ),
            )
        elif task_status == "failed":
            error_info = task_result.get("error", {})
            error_msg = error_info.get("message", "Unknown error")
            parts.append("Task failed.")
            parts.append("")
            parts.append(f"Error: {error_msg}")
        else:
            parts.append(_json_text(result))
        return "\n".join(parts)

    if status == "running":
        started_at = result.get("started_at", "N/A")
        parts.append("Task is still running...")
        parts.append(f"Started at: {started_at}")
    elif status == "pending":
        parts.append("Task is pending in queue...")
    elif status == "submitted":
        parts.append("Task submitted, waiting to start...")
    else:
        parts.append(_json_text(result))
    return "\n".join(parts)


async def list_agents(
    base_url: Optional[str] = None,
) -> ToolChunk:
    """List all configured agents from the QwenPaw service.

    Returns:
        `ToolChunk`:
            A tool response containing the agent list as json text. Each agent
            has its id, name, description and workspace directory.
    """
    result = await asyncio.to_thread(list_agents_data, base_url)
    return _tool_text_response(_json_text(result))


async def chat_with_agent(
    to_agent: str,
    text: str,
    session_id: Optional[str] = None,
    timeout: int = 120,
) -> ToolChunk:
    """Send a foreground message to another configured agent.

    This tool waits for the target agent to finish and returns the final text
    response in a single tool result. It is intended for direct inter-agent
    consultation where the caller expects an immediate reply rather than a
    background task handle.

    Args:
        to_agent (`str`):
            The target agent ID to send the message to. This must be an agent
            ID returned by ``list_agents``.
        text (`str`):
            The message text to send to the target agent.
        session_id (`str`, optional):
            Existing session ID to continue a previous conversation. If not
            provided, a new session ID is generated automatically.
        timeout (`int`, optional):
            Foreground wait timeout in seconds. Callers should estimate how
            long the target agent may need to finish to reduce avoidable
            timeout failures.

    Returns:
        `ToolChunk`:
            A text response containing the final agent reply. Successful
            responses include a ``[SESSION: ...]`` header followed by the reply
            text so the caller can reuse the same session in later turns.
    """
    normalized_to_agent = normalize_id(to_agent)
    normalized_session_id = normalize_id(session_id)
    if not normalized_to_agent:
        return _tool_text_response("ERROR: 'to_agent' is required for chat")
    if not text:
        return _tool_text_response("ERROR: 'text' is required for chat")
    if _agentdesk_blocks_agent_target(normalized_to_agent):
        return _tool_text_response(
            f"Agent [{normalized_to_agent}] not exists",
        )

    resolved_to_agent = await asyncio.to_thread(
        resolve_agent_target,
        normalized_to_agent,
        None,
    )
    if not resolved_to_agent:
        available = await asyncio.to_thread(_available_agent_targets, None)
        hint = f" Available agents: {available}." if available else ""
        return _tool_text_response(
            f"Agent [{normalized_to_agent}] not exists.{hint}",
        )
    normalized_to_agent = resolved_to_agent

    roster_error = await asyncio.to_thread(
        _team_delegation_violation,
        normalized_to_agent,
    )
    if roster_error:
        return _tool_text_response(roster_error)

    # Get root_session_id from current context for cross-session approval
    from ...app.agent_context import (
        get_current_session_id,
        get_current_root_session_id,
    )

    caller_session_id = get_current_session_id() or ""
    caller_root_session = get_current_root_session_id()
    final_root_session = resolve_team_delegation_root_session(
        caller_session_id,
        caller_root_session,
    )

    final_session_id, request_payload, _ = build_agent_chat_request(
        normalized_to_agent,
        text,
        session_id=normalized_session_id,
        from_agent=None,
        root_session_id=final_root_session,
    )

    publish_key = worker_stream_publish_key(final_session_id, final_root_session)
    response_data = await asyncio.to_thread(
        collect_final_agent_chat_response,
        None,
        request_payload,
        normalized_to_agent,
        timeout,
        publish_key,
    )
    if not response_data:
        return _tool_text_response("(No response received)")

    return _tool_text_response(
        format_agent_chat_text(response_data, session_id=final_session_id),
    )


async def submit_to_agent(
    to_agent: str,
    text: str,
    session_id: Optional[str] = None,
    task_timeout: Optional[float] = None,
) -> ToolChunk:
    """Submit a background message to another configured agent.

    This tool is the background-task counterpart to ``chat_with_agent``. It
    submits the request and returns immediately with task metadata instead of
    waiting for the target agent to finish.

    Args:
        to_agent (`str`):
            The target agent ID to send the message to. This must be an agent
            ID returned by ``list_agents``.
        text (`str`):
            The message text to execute as a background task.
        session_id (`str`, optional):
            Existing session ID to continue a previous conversation in the
            background. If not provided, a new session ID is generated.
        task_timeout (`float`, optional):
            Task execution timeout in seconds. Overrides the server-side
            default stream_task_timeout for this specific task.

    Returns:
        `ToolChunk`:
            A text response containing ``[TASK_ID: ...]`` and
            ``[SESSION: ...]`` headers. The returned task ID can be passed to
            ``check_agent_task`` to inspect progress or fetch the final result.
    """
    normalized_to_agent = normalize_id(to_agent)
    normalized_session_id = normalize_id(session_id)
    if not normalized_to_agent:
        return _tool_text_response(
            "ERROR: 'to_agent' is required for submission",
        )
    if not text:
        return _tool_text_response(
            "ERROR: 'text' is required for submission",
        )
    if _agentdesk_blocks_agent_target(normalized_to_agent):
        return _tool_text_response(
            f"Agent [{normalized_to_agent}] not exists",
        )

    resolved_to_agent = await asyncio.to_thread(
        resolve_agent_target,
        normalized_to_agent,
        None,
    )
    if not resolved_to_agent:
        available = await asyncio.to_thread(_available_agent_targets, None)
        hint = f" Available agents: {available}." if available else ""
        return _tool_text_response(
            f"Agent [{normalized_to_agent}] not exists.{hint}",
        )
    normalized_to_agent = resolved_to_agent

    roster_error = await asyncio.to_thread(
        _team_delegation_violation,
        normalized_to_agent,
    )
    if roster_error:
        return _tool_text_response(roster_error)

    # Get root_session_id from current context for cross-session approval
    from ...app.agent_context import (
        get_current_session_id,
        get_current_root_session_id,
    )

    caller_session_id = get_current_session_id() or ""
    caller_root_session = get_current_root_session_id()
    final_root_session = resolve_team_delegation_root_session(
        caller_session_id,
        caller_root_session,
    )

    final_session_id, request_payload, _ = build_agent_chat_request(
        normalized_to_agent,
        text,
        session_id=normalized_session_id,
        from_agent=None,
        root_session_id=final_root_session,
    )

    result = await asyncio.to_thread(
        submit_agent_chat_task,
        None,
        request_payload,
        normalized_to_agent,
        TASK_SUBMIT_TIMEOUT,
        task_timeout,
    )
    return _tool_text_response(
        format_background_submission_text(result, final_session_id),
    )


async def check_agent_task(
    task_id: str,
) -> ToolChunk:
    """Check the status of a background inter-agent task.

    This tool queries a previously submitted background task by its task ID.
    If the task is still in progress, it returns the current lifecycle state.
    If the task has finished, it returns either the final agent response or a
    failure message.

    Args:
        task_id (`str`):
            The background task ID returned by ``submit_to_agent``.

    Returns:
        `ToolChunk`:
            A text response containing a ``[TASK_ID: ...]`` header and current
            task status. Completed tasks also include the resolved session ID
            and final agent text when available.
    """
    normalized_task_id = normalize_id(task_id)
    if not normalized_task_id:
        return _tool_text_response(
            "ERROR: 'task_id' is required to check task status",
        )

    result = await asyncio.to_thread(
        get_agent_chat_task_status,
        None,
        normalized_task_id,
        to_agent=None,
        timeout=10,
    )
    return _tool_text_response(
        format_background_status_text(normalized_task_id, result),
    )
