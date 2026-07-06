(function (root) {

  "use strict";



  const TERMINAL_TYPES = new Set(["done", "error"]);



  const createStreamTurnState = () => ({

    turns: new Map(),

  });



  const createTeamStreamState = () => ({

    phase: "",

    activeActorId: "",

    terminal: false,

    actors: new Map(),

  });



  const turnKeyFor = (evt, fallbackTaskId) => {

    const taskId = String(evt.task_id || fallbackTaskId || "");

    const roundId = String(evt.round_id || "legacy");

    return `${taskId}::${roundId}`;

  };



  const resolveActorId = (evt) =>

    String(

      evt?.actor_id || evt?.source_member || evt?.worker || evt?.sender || "",

    ).trim();



  const isTerminalEvent = (evt) => {

    if (evt.is_terminal === true) return true;

    if (TERMINAL_TYPES.has(String(evt.type || ""))) return true;

    return String(evt.type || "") === "team_phase" && String(evt.phase || "") === "done";

  };



  const LEADER_BRIDGE_SENTENCE =

    /好的[，,][^。！!?\n]{0,120}?(介绍完毕|下一位|最后一位|所有成员|邀请|请.*成员|已介绍|继续安排|派工|协作完成)[^。！!?\n]*[。！!?]/g;



  const isTeamLeaderSender = (sender) => {

    const name = String(sender || "").trim().toLowerCase();

    return name.includes("(leader)") || name.includes("（leader）");

  };



  const isLeaderBridgeLine = (line) => {

    const text = String(line || "").trim();

    if (!text) return true;

    if (/^好的[，,]/.test(text) && text.length <= 120) {

      return /(介绍完毕|下一位|最后一位|所有成员|邀请|请.*成员|继续安排)/.test(text);

    }

    return false;

  };



  const isLeaderOrchestrationOnly = (content) => {

    const text = String(content || "").trim();

    if (!text) return true;

    if (text.length > 220) return false;

    if (text.includes("|") || text.includes("##") || text.includes("**")) return false;

    const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);

    if (!lines.length) return true;

    return lines.every(isLeaderBridgeLine);

  };



  const stripPreSummaryIntro = (text) => {
    let raw = String(text || "").trim();
    if (!raw) return "";
    if (!raw.includes("##") && !raw.includes("|")) return raw;
    const hashIdx = raw.indexOf("##");
    if (hashIdx > 0) raw = raw.slice(hashIdx).trimStart();
    const lines = raw.split("\n");
    while (lines.length) {
      const line = lines[0].trim();
      if (!line) {
        lines.shift();
        continue;
      }
      if (line.startsWith("##") || line.startsWith("|")) break;
      if (line.length <= 100) {
        lines.shift();
        continue;
      }
      break;
    }
    return lines.join("\n").trim();
  };



  const leaderHasDeliverable = (content) => {
    const text = String(content || "").trim();
    return text.includes("|") || text.includes("##") || text.includes("**") || text.length > 200;
  };



  const cleanLeaderSummaryContent = (content) => {
    let text = String(content || "").replace(LEADER_BRIDGE_SENTENCE, "").trim();
    text = text.replace(/\n{3,}/g, "\n\n");
    if (!text) return "";

    if (text.includes("##")) {
      const parts = text.split(/(?=## )/).map((part) => part.trim()).filter(Boolean);
      const tableParts = parts.filter((part) => part.includes("|"));
      if (tableParts.length > 1) {
        const last = tableParts[tableParts.length - 1];
        return last.startsWith("##") ? last : `## ${last}`;
      }
      if (tableParts.length === 1) {
        text = tableParts[0];
        if (!text.startsWith("##") && String(content || "").includes("##")) {
          text = `## ${text}`;
        }
      }
    }

    return stripPreSummaryIntro(text);
  };

  const stripLeaderOrchestrationPrefix = (content) => cleanLeaderSummaryContent(content);



  const sanitizeTeamTurnMessages = (messages) => {

    const list = Array.isArray(messages) ? messages : [];

    if (!list.length) return list;

    let lastUser = -1;

    list.forEach((msg, idx) => {

      if (msg?.role === "user") lastUser = idx;

    });

    if (lastUser < 0) return list;

    const head = list.slice(0, lastUser + 1);

    const tail = list.slice(lastUser + 1);

    const cleaned = [];

    let lastLeaderIdx = -1;

    tail.forEach((msg, idx) => {

      if (msg?.role === "assistant" && isTeamLeaderSender(msg?.sender)) {

        lastLeaderIdx = idx;

      }

    });

    tail.forEach((msg, idx) => {

      if (msg?.role !== "assistant") {

        cleaned.push(msg);

        return;

      }

      if (!isTeamLeaderSender(msg?.sender)) {
        cleaned.push(msg);
        return;
      }
      if (idx !== lastLeaderIdx) return;

      const original = String(msg.content || "").trim();
      let stripped = cleanLeaderSummaryContent(original);
      if (!stripped && original && !isLeaderOrchestrationOnly(original)) {
        stripped = original;
      }
      if (stripped) cleaned.push({ ...msg, content: stripped });

    });

    return [...head, ...cleaned];

  };



  const ensureTurn = (state, key, evt, fallbackTaskId) => {

    let turn = state.turns.get(key);

    if (!turn) {

      turn = {

        key,

        taskId: String(evt.task_id || fallbackTaskId || ""),

        roundId: String(evt.round_id || "legacy"),

        lastSeq: -1,

        activeSpeaker: "",

        terminal: false,

        terminalType: "",

        planSnapshot: null,

        traces: [],

      };

      state.turns.set(key, turn);

    }

    return turn;

  };



  const ensureActor = (state, actorId, seed = {}) => {

    if (!actorId) return null;

    let actor = state.actors.get(actorId);

    if (!actor) {

      actor = {

        actorId,

        delegationId: "",

        content: "",

        streaming: false,

        traces: [],

        ...seed,

      };

      state.actors.set(actorId, actor);

    }

    return actor;

  };



  const applyStreamEvent = (state, evt, options = {}) => {

    const key = turnKeyFor(evt || {}, options.taskId);

    const turn = ensureTurn(state, key, evt || {}, options.taskId);

    const hasSeq = Number.isFinite(Number(evt?.seq));

    const seq = hasSeq ? Number(evt.seq) : turn.lastSeq + 1;

    const terminal = isTerminalEvent(evt || {});

    if (hasSeq && seq <= turn.lastSeq && !terminal) {

      return { applied: false, stale: true, turn };

    }



    turn.lastSeq = Math.max(turn.lastSeq, seq);

    const speaker = resolveActorId(evt || {});

    if (speaker) turn.activeSpeaker = speaker;

    if (evt?.type === "trace") turn.traces.push(evt);

    if (evt?.type === "plan_update" || evt?.plan) {

      turn.planSnapshot = {

        status: evt.plan_status || evt.plan?.status || turn.planSnapshot?.status || "",

        tasks: Array.isArray(evt.plan?.tasks) ? evt.plan.tasks : turn.planSnapshot?.tasks || [],

      };

    }

    if (isTerminalEvent(evt || {})) {

      turn.terminal = true;

      turn.terminalType = String(evt?.type || "");

    }

    return { applied: true, stale: false, turn };

  };



  const applyTeamStreamEvent = (state, evt, options = {}) => {

    const type = String(evt?.type || "");

    const actorId = resolveActorId(evt || {});



    if (type === "team_phase") {

      state.phase = String(evt?.team_phase || evt?.phase || "");

      if (state.phase === "done" || evt?.phase === "done") {

        state.terminal = true;

        state.activeActorId = "";

      }

    } else if (type === "worker_start") {

      state.activeActorId = actorId;

      ensureActor(state, actorId, {

        delegationId: String(evt?.delegation_id || evt?.task_id || ""),

        streaming: true,

      });

    } else if (type === "worker_done") {

      const doneActor = ensureActor(state, actorId);

      if (doneActor) doneActor.streaming = false;

      if (state.activeActorId === actorId) state.activeActorId = "";

    } else if (type === "text_delta") {

      const targetId = actorId || state.activeActorId;

      const actor = ensureActor(state, targetId, { streaming: true });

      if (actor) {

        actor.content += String(evt?.content || "");

        if (evt?.delegation_id) actor.delegationId = String(evt.delegation_id);

      }

      if (actorId && evt?.role === "worker") state.activeActorId = actorId;

    } else if (type === "message") {

      const targetId = actorId || state.activeActorId;

      const actor = ensureActor(state, targetId);

      if (actor) {

        const part = String(evt?.content || "").trim();

        if (part) {

          const cur = String(actor.content || "").trim();

          if (!cur) actor.content = part;

          else if (part.startsWith(cur)) actor.content = part;

          else if (part !== cur && !cur.endsWith(part)) actor.content = `${cur}\n\n${part}`;

        }

        actor.streaming = false;

      }

    } else if (type === "trace") {

      const targetId = state.activeActorId || actorId;

      const actor = ensureActor(state, targetId);

      if (actor) actor.traces.push(evt || {});

    }



    return {

      phase: state.phase,

      activeActorId: state.activeActorId,

      terminal: state.terminal,

      actor: actorId ? state.actors.get(actorId) || null : null,

      taskId: options.taskId || "",

    };

  };



  const api = {

    createStreamTurnState,

    createTeamStreamState,

    applyStreamEvent,

    applyTeamStreamEvent,

    turnKeyFor,

    resolveActorId,

    isTerminalEvent,

    isTeamLeaderSender,

    isLeaderOrchestrationOnly,

    stripLeaderOrchestrationPrefix,

    sanitizeTeamTurnMessages,

  };



  root.AgentDeskStreamReducer = api;

  if (typeof module !== "undefined" && module.exports) {

    module.exports = api;

  }

})(typeof window !== "undefined" ? window : globalThis);

