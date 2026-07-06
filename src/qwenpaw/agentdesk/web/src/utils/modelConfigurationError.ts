/** True when a stream/chat error likely indicates missing or invalid model setup. */
export function isModelConfigurationError(message: string | undefined | null): boolean {
  const text = String(message ?? "").trim().toLowerCase();
  if (!text) return false;
  return (
    text.includes("api key") ||
    text.includes("apikey") ||
    text.includes("未配置可用模型") ||
    text.includes("模型仍未就绪") ||
    text.includes("无法激活模型") ||
    text.includes("configure api")
  );
}
