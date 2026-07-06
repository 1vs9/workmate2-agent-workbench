import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildTaskTitle, tasksApi } from "../../api/tasks";
import AgentDeskIcon from "../../components/branding/AgentDeskIcon";
import ComposerToolbar from "../../components/composer/ComposerToolbar";
import { HOME_QUICK_PROMPTS } from "../../constants/homePrompts";
import { useAppStore } from "../../store/appStore";
import { useComposerStore } from "../../store/composerStore";

export default function HomePage() {
  const navigate = useNavigate();
  const prependTask = useAppStore((s) => s.prependTask);
  const setActiveTaskId = useAppStore((s) => s.setActiveTaskId);
  const resetForNewChat = useComposerStore((s) => s.resetForNewChat);

  useEffect(() => {
    resetForNewChat();
  }, [resetForNewChat]);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = async (text?: string) => {
    const value = (text ?? input).trim();
    if (!value || submitting) return;
    setSubmitting(true);
    try {
      const created = await tasksApi.create({ title: buildTaskTitle(value) });
      prependTask(created);
      setActiveTaskId(created.id);
      navigate(`/task/${created.id}`, { state: { initialMessage: value } });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "创建任务失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#f8faf9]">
      <div className="wm-home-bg pointer-events-none absolute inset-0" aria-hidden="true" />

      <div className="relative flex h-full min-h-0 flex-col items-center px-4 pb-5 pt-6 sm:px-8 sm:pb-6 sm:pt-8">
        <div className="flex min-h-0 w-full max-w-[720px] flex-1 flex-col items-center justify-end px-2 pb-16 pt-[3vh] text-center sm:pb-24 sm:pt-[5vh]">
          <div className="relative mb-5">
            <AgentDeskIcon
              size={72}
              ring
              className="shadow-[0_10px_40px_rgba(15,23,42,0.08)]"
            />
          </div>
          <h1 className="text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
            Claw Your Ideas Into{" "}
            <span className="bg-gradient-to-r from-emerald-600 to-teal-500 bg-clip-text text-transparent">
              Reality
            </span>
          </h1>
          <p className="mt-2 text-[15px] font-medium text-gray-500">
            Triggered Anywhere, Completed Locally
          </p>
          <p className="mt-1 text-[13px] text-gray-400">随时随地触发，本地完成执行</p>
        </div>

        <div className="wm-home-dock flex w-full flex-col items-stretch">
          <div className="wm-home-chips-row mb-2.5 sm:mb-3" role="group" aria-label="快速场景">
            {HOME_QUICK_PROMPTS.map(({ label, prompt }) => (
              <button
                key={label}
                type="button"
                onClick={() => {
                  setInput(prompt);
                  inputRef.current?.focus();
                }}
                className="wm-home-chip inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-gray-200/90 bg-white/90 px-3 py-1.5 text-[12px] text-gray-600 shadow-sm backdrop-blur-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500 sm:px-3.5 sm:text-[13px]"
              >
                {label}
              </button>
            ))}
          </div>

          <div className="wm-composer wm-home-composer w-full p-4">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submit();
                }
              }}
              placeholder="输入消息，或从上方选择场景快速开始…"
              aria-label="新任务输入"
              className="min-h-[88px] w-full resize-none border-none bg-transparent text-[15px] leading-relaxed text-gray-800 placeholder:text-gray-400 outline-none sm:min-h-[96px]"
            />
            <ComposerToolbar
              onSend={() => void submit()}
              sending={submitting}
              disabled={!input.trim()}
            />
          </div>

          <p className="mt-3 pb-1 text-center text-[11px] text-gray-400">
            内容由 AI 生成，请核实重要信息。
          </p>
        </div>
      </div>
    </div>
  );
}
