/**
 * AgentDesk API client — prefers same-origin (no CORS).
 */
(function () {
  const FALLBACK_BASES = ["http://127.0.0.1:8088", "http://localhost:8088"];
  const API_BASE_STORAGE_KEY = "agentdesk-api-base";
  const LEGACY_API_BASE_STORAGE_KEY = "demo-api-base";
  const AUTH_TOKEN_KEY = "qwenpaw_auth_token";

  function buildAuthHeaders() {
    const headers = {};
    try {
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch (_) {
      /* ignore */
    }
    return headers;
  }

  function getCandidates() {
    const list = [];
    if (window.location.protocol.startsWith("http")) {
      list.push(window.location.origin);
    }
    if (window.AGENTDESK_API_BASE) list.push(window.AGENTDESK_API_BASE);
    if (window.DEMO_API_BASE) list.push(window.DEMO_API_BASE);
    const saved =
      localStorage.getItem(API_BASE_STORAGE_KEY) ||
      localStorage.getItem(LEGACY_API_BASE_STORAGE_KEY);
    if (saved) list.push(saved);
    return [...new Set(list)];
  }

  let resolvedBase = getCandidates()[0];

  function updateStatusBar(result) {
    const bar = document.getElementById("apiStatusBar");
    if (!bar) return;
    window.__agentdeskApiOnline = result.ok;
    if (result.ok) {
      bar.className =
        "mx-2 mb-2 cursor-pointer rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700 hover:bg-emerald-100";
      bar.textContent = `后端已连接（同源）`;
      bar.title = result.base;
    } else {
      bar.className =
        "mx-2 mb-2 cursor-pointer rounded-md bg-red-50 px-2 py-1 text-[11px] text-red-700 hover:bg-red-100";
      const hint = (result.errors && result.errors[0]) || "";
      bar.textContent = "后端未连接 — 请运行 start.bat 后点击此处重试";
      bar.title = hint || "点击重试";
    }
  }

  async function request(path, options = {}) {
    const url = `${resolvedBase}${path}`;
    const headers = { ...buildAuthHeaders(), ...(options.headers || {}) };
    const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
    if (!isFormData && !Object.prototype.hasOwnProperty.call(headers, "Content-Type")) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(url, {
      ...options,
      headers,
    });
    if (!res.ok) {
      const text = await res.text();
      let detail = text;
      try {
        const json = JSON.parse(text);
        if (Array.isArray(json.detail)) {
          detail = json.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
        } else {
          detail = json.detail || text;
        }
      } catch (_) {
        /* ignore */
      }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (res.status === 204) return null;
    return res.json();
  }

  const AgentDeskAPI = {
    get base() {
      return resolvedBase;
    },
    setBase(url) {
      resolvedBase = url;
      localStorage.setItem(API_BASE_STORAGE_KEY, url);
    },
    async probe() {
      const errors = [];
      for (const base of getCandidates()) {
        try {
          const res = await fetch(`${base}/health`, {
            method: "GET",
            cache: "no-store",
          });
          if (!res.ok) {
            errors.push(`${base}: HTTP ${res.status}`);
            continue;
          }
          const toolsRes = await fetch(`${base}/api/tools`, {
            method: "GET",
            cache: "no-store",
            headers: buildAuthHeaders(),
          });
          if (!toolsRes.ok) {
            errors.push(`${base}: /api/tools HTTP ${toolsRes.status}`);
            continue;
          }
          resolvedBase = base;
          localStorage.setItem(API_BASE_STORAGE_KEY, base);
          const result = { ok: true, base };
          updateStatusBar(result);
          return result;
        } catch (err) {
          errors.push(`${base}: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
      for (const base of FALLBACK_BASES) {
        if (getCandidates().includes(base)) continue;
        try {
          const res = await fetch(`${base}/health`, { method: "GET", cache: "no-store" });
          if (!res.ok) continue;
          const toolsRes = await fetch(`${base}/api/tools`, {
            method: "GET",
            cache: "no-store",
            headers: buildAuthHeaders(),
          });
          if (!toolsRes.ok) continue;
          resolvedBase = base;
          localStorage.setItem(API_BASE_STORAGE_KEY, base);
          const result = { ok: true, base };
          updateStatusBar(result);
          return result;
        } catch (err) {
          errors.push(`${base}: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
      const result = { ok: false, base: resolvedBase, errors };
      updateStatusBar(result);
      console.error("[AgentDesk] probe failed:", errors);
      return result;
    },
    health: () => request("/health"),
    getEmployees: () => request("/api/employees"),
    createEmployee: (body) =>
      request("/api/employees", { method: "POST", body: JSON.stringify(body) }),
    updateEmployee: (name, body) =>
      request(`/api/employees/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    deleteEmployee: (name) =>
      request(`/api/employees/${encodeURIComponent(name)}`, { method: "DELETE" }),
    getPlaza: () => request("/api/plaza"),
    createPlazaCard: (body) =>
      request("/api/plaza", { method: "POST", body: JSON.stringify(body) }),
    joinPlaza: (name) =>
      request(`/api/plaza/${encodeURIComponent(name)}/join`, { method: "POST" }),
    updatePlaza: (name, body) =>
      request(`/api/plaza/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    getTeams: () => request("/api/teams"),
    createTeam: (body) =>
      request("/api/teams", { method: "POST", body: JSON.stringify(body) }),
    updateTeam: (id, body) =>
      request(`/api/teams/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    deleteTeam: (id) =>
      request(`/api/teams/${encodeURIComponent(id)}`, { method: "DELETE" }),
    getTools: () => request("/api/tools"),
    getSkills: () => request("/api/skills"),
    createSkill: (body) =>
      request("/api/skills", { method: "POST", body: JSON.stringify(body) }),
    uploadSkill: (fileOrFiles, autoInstallSafe = false) => {
      const form = new FormData();
      if (Array.isArray(fileOrFiles)) {
        const relativePaths = [];
        for (const entry of fileOrFiles) {
          form.append("files", entry);
          relativePaths.push(entry.webkitRelativePath || entry.name || "SKILL.md");
        }
        form.append("relative_paths", JSON.stringify(relativePaths));
      } else {
        form.append("file", fileOrFiles);
      }
      form.append("auto_install_safe", String(autoInstallSafe));
      return request("/api/skills/upload", { method: "POST", body: form });
    },
    mountSkill: (skillName, body = {}) =>
      request(`/api/skills/${encodeURIComponent(skillName)}/mount`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    deleteSkill: (skillName) =>
      request(`/api/skills/${encodeURIComponent(skillName)}`, { method: "DELETE" }),
    getMcpServers: () => request("/api/mcp"),
    upsertMcpServer: (body) =>
      request("/api/mcp", { method: "POST", body: JSON.stringify(body) }),
    deleteMcpServer: (name) =>
      request(`/api/mcp/${encodeURIComponent(name)}`, { method: "DELETE" }),
    getKnowledge: () => request("/api/knowledge"),
    createKnowledge: (body) =>
      request("/api/knowledge", { method: "POST", body: JSON.stringify(body) }),
    updateKnowledge: (id, body) =>
      request(`/api/knowledge/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    deleteKnowledge: (id) =>
      request(`/api/knowledge/${encodeURIComponent(id)}`, { method: "DELETE" }),
    getCases: () => request("/api/cases"),
    createCase: (body) =>
      request("/api/cases", { method: "POST", body: JSON.stringify(body) }),
    updateCase: (id, body) =>
      request(`/api/cases/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    deleteCase: (id) =>
      request(`/api/cases/${encodeURIComponent(id)}`, { method: "DELETE" }),
    getTasks: () => request("/api/tasks"),
    getTask: (id) => request(`/api/tasks/${encodeURIComponent(id)}`),
    getTaskEvents: (id) => request(`/api/tasks/${encodeURIComponent(id)}/events`),
    getWorkspaceTree: (taskId) =>
      request(`/api/tasks/${encodeURIComponent(taskId)}/workspace/tree`),
    getWorkspaceFile: (taskId, path) =>
      request(
        `/api/tasks/${encodeURIComponent(taskId)}/workspace/file?path=${encodeURIComponent(path)}`,
      ),
    revealWorkspacePath: (taskId, path) =>
      request(`/api/tasks/${encodeURIComponent(taskId)}/workspace/reveal`, {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    getTaskStats: (id) => request(`/api/tasks/${encodeURIComponent(id)}/stats`),
    previewTaskContextBudget: (taskId, body) =>
      request(`/api/tasks/${encodeURIComponent(taskId)}/context/budget`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    createTask: (body) =>
      request("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
    deleteTask: (id) =>
      request(`/api/tasks/${encodeURIComponent(id)}`, { method: "DELETE" }),
    getTaskQueue: (taskId) =>
      request(`/api/tasks/${encodeURIComponent(taskId)}/queue`),
    updateQueueItem: (taskId, itemId, message) =>
      request(
        `/api/tasks/${encodeURIComponent(taskId)}/queue/${encodeURIComponent(itemId)}`,
        { method: "PUT", body: JSON.stringify({ message }) },
      ),
    deleteQueueItem: (taskId, itemId) =>
      request(
        `/api/tasks/${encodeURIComponent(taskId)}/queue/${encodeURIComponent(itemId)}`,
        { method: "DELETE" },
      ),
    reorderQueue: (taskId, ids) =>
      request(`/api/tasks/${encodeURIComponent(taskId)}/queue/reorder`, {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    stopTask: (taskId) =>
      request(`/api/tasks/${encodeURIComponent(taskId)}/stop`, { method: "POST" }),
    getAutomationJobs: () => request("/api/automation/jobs"),
    createAutomationJob: (body) =>
      request("/api/automation/jobs", { method: "POST", body: JSON.stringify(body) }),
    updateAutomationJob: (id, body) =>
      request(`/api/automation/jobs/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    getAutomationHistory: () => request("/api/automation/history"),
    runAutomationJob: (id) =>
      request(`/api/automation/jobs/${encodeURIComponent(id)}/run`, { method: "POST" }),
    pauseAutomationJob: (id) =>
      request(`/api/automation/jobs/${encodeURIComponent(id)}/pause`, { method: "POST" }),
    resumeAutomationJob: (id) =>
      request(`/api/automation/jobs/${encodeURIComponent(id)}/resume`, { method: "POST" }),
    deleteAutomationJob: (id) =>
      request(`/api/automation/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
    chat: (body) =>
      request("/api/chat", { method: "POST", body: JSON.stringify(body) }),
    chatStream: async (body, onEvent, options = {}) => {
      const url = `${resolvedBase}/api/chat/stream`;
      const timeoutMs = options.timeoutMs ?? 180000;
      const idleTimeoutMs =
        options.idleTimeoutMs ?? (body?.mode === "team" ? 180000 : 180000);
      const controller = options.signal ? null : new AbortController();
      const signal = options.signal || controller.signal;
      if (options.onController && controller) {
        options.onController(controller);
      }
      const timer = setTimeout(() => {
        if (controller) controller.abort();
      }, timeoutMs);
      let idleTimer = null;
      const bumpIdleTimer = () => {
        if (idleTimer) clearTimeout(idleTimer);
        idleTimer = setTimeout(() => {
          if (controller) controller.abort();
        }, idleTimeoutMs);
      };
      let res;
      try {
        res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal,
        });
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error("请求超时，请稍后重试。");
        }
        throw err;
      } finally {
        clearTimeout(timer);
      }
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      bumpIdleTimer();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          bumpIdleTimer();
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";
          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith("data:")) continue;
            const jsonStr = line.slice(5).trim();
            if (!jsonStr) continue;
            try {
              const evt = JSON.parse(jsonStr);
              if (evt.type === "heartbeat") {
                bumpIdleTimer();
                onEvent(evt);
                continue;
              }
              onEvent(evt);
            } catch (e) {
              console.warn("[AgentDeskAPI] SSE parse error", e);
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error("连接长时间无响应，已自动停止。可点击停止后重试。");
        }
        throw err;
      } finally {
        if (idleTimer) clearTimeout(idleTimer);
      }
    },
    chatStreamReconnect: (taskId, onEvent, options = {}) =>
      AgentDeskAPI.chatStream(
        { task_id: taskId, message: "", reconnect: true },
        onEvent,
        options,
      ),
    getTaskPlan: (taskId) => request(`/api/tasks/${encodeURIComponent(taskId)}/plan`),
    confirmTaskPlan: (taskId, action) =>
      request(`/api/tasks/${encodeURIComponent(taskId)}/plan/confirm`, {
        method: "POST",
        body: JSON.stringify({ action }),
      }),
    approveChat: (taskId, approved = true) =>
      request("/api/chat/approve", {
        method: "POST",
        body: JSON.stringify({ task_id: taskId, approved }),
      }),
    getConfig: () => request("/api/config"),
    updateProviderConfig: (providerId, body) =>
      request(`/api/config/providers/${encodeURIComponent(providerId)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    setActiveModel: (providerId, model) =>
      request("/api/config/active-model", {
        method: "PUT",
        body: JSON.stringify({ provider_id: providerId, model }),
      }),
  };

  AgentDeskAPI.version = "7-config";
  window.AgentDeskAPI = AgentDeskAPI;
  window.DemoAPI = AgentDeskAPI;

  function startProbeLoop() {
    AgentDeskAPI.probe();
    let tries = 0;
    const timer = setInterval(() => {
      if (window.__agentdeskApiOnline || tries >= 12) {
        clearInterval(timer);
        return;
      }
      tries += 1;
      AgentDeskAPI.probe();
    }, 5000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.getElementById("apiStatusBar");
    if (bar) bar.addEventListener("click", () => AgentDeskAPI.probe());
    startProbeLoop();
  });
})();
