import { useCallback, useEffect, useRef, useState } from "react";

/** Auto-expand when a stream starts; auto-collapse when it ends. Manual toggle in between. */
export function useProcessPanelExpanded(isStreaming: boolean): [boolean, () => void] {
  const [expanded, setExpanded] = useState(isStreaming);
  const wasStreamingRef = useRef(isStreaming);

  useEffect(() => {
    const wasStreaming = wasStreamingRef.current;
    if (!wasStreaming && isStreaming) {
      setExpanded(true);
    } else if (wasStreaming && !isStreaming) {
      setExpanded(false);
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming]);

  const toggle = useCallback(() => setExpanded((v) => !v), []);

  return [expanded, toggle];
}
