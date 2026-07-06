import { Markdown } from "@agentscope-ai/chat";

interface AssistantMarkdownProps {
  content: string;
  /** Show streaming cursor while the assistant reply is in progress. */
  streaming?: boolean;
}

export default function AssistantMarkdown({
  content,
  streaming = false,
}: AssistantMarkdownProps) {
  if (!content) return null;

  return (
    <Markdown
      content={content}
      cursor={streaming ? true : false}
      className="wm-markdown"
      baseFontSize={14}
      baseLineHeight={1.625}
    />
  );
}
