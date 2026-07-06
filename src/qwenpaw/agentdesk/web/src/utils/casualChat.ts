/** Short greetings / acknowledgements — skip composer skills for these turns. */
import { isSkillCreateMessage } from "./skillCreate";

export function isCasualChatMessage(text: string): boolean {
  const t = String(text || "").trim();
  if (!t || t.length > 80 || isSkillCreateMessage(t)) return false;
  return /^(你好|您好|hi|hello|hey|在吗|在不在|谢谢|感谢|好的|嗯|哦|啊|哈哈|呵呵|你是谁|你能做什么)[\s!！?？。．.…,，~～]*$/i.test(
    t,
  );
}
