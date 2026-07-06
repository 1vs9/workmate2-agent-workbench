/**
 * Markdown rendering for AgentDesk HTML chat (aligned with QwenPaw / XMarkdown output).
 * Uses marked (GFM) + DOMPurify; falls back to escaped plain text if CDN libs missing.
 */
(function (global) {
  const escapeHtml = (raw) =>
    String(raw || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const stripFrontmatter = (s) =>
    String(s || "").replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, "");

  let markedReady = false;

  function ensureMarked() {
    if (markedReady || !global.marked) return markedReady;
    try {
      if (typeof global.marked.use === "function") {
        global.marked.use({
          gfm: true,
          breaks: true,
        });
      } else if (typeof global.marked.setOptions === "function") {
        global.marked.setOptions({
          gfm: true,
          breaks: true,
        });
      }
      markedReady = true;
    } catch (_) {
      markedReady = false;
    }
    return markedReady;
  }

  function renderMarkdown(content) {
    const raw = stripFrontmatter(String(content || ""));
    if (!raw.trim()) return "";

    if (!ensureMarked() || !global.DOMPurify) {
      return escapeHtml(raw);
    }

    let html = "";
    try {
      html =
        typeof global.marked.parse === "function"
          ? global.marked.parse(raw)
          : global.marked(raw);
    } catch (_) {
      return escapeHtml(raw);
    }

    return global.DOMPurify.sanitize(html, {
      ADD_ATTR: ["target", "rel", "class"],
    });
  }

  function shouldRenderMarkdown(message) {
    if (!message || typeof message !== "object") return false;
    if (message.role === "user" || message.role === "system") return false;
    return true;
  }

  function renderMessageBubbleHtml(message) {
    const text = message?.content ?? "";
    if (!shouldRenderMarkdown(message)) {
      return escapeHtml(text);
    }
    return renderMarkdown(text);
  }

  function bubbleClassForMessage(message) {
    return shouldRenderMarkdown(message) ? "wm-markdown" : "whitespace-pre-wrap";
  }

  global.AgentDeskMarkdown = {
    stripFrontmatter,
    renderMarkdown,
    renderMessageBubbleHtml,
    bubbleClassForMessage,
    escapeHtml,
  };
})(window);
