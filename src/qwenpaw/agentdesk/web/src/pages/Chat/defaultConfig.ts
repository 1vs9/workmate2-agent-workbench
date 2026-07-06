/** Baseline AgentScopeRuntimeWebUI options (ported from QwenPaw Console). */
const defaultConfig = {
  theme: {
    colorPrimary: "#FF7F16",
    darkMode: false,
    prefix: "qwenpaw",
    leftHeader: {
      logo: "",
      title: "AgentDesk",
    },
  },
  sender: {
    attachments: false,
    maxLength: 10000,
    placeholder: "输入消息，按 Enter 发送",
    disclaimer: "为你工作，与你共同成长",
  },
  welcome: {
    greeting: "你好，我能帮你做点什么？",
    description: "我是 AgentDesk，可以协助你完成各种工作任务。",
    nick: "AgentDesk",
    prompts: [
      { value: "我们开始一段新的旅程吧！" },
      { value: "你有哪些技能可以帮我？" },
    ],
  },
  api: {
    baseURL: "",
    token: "",
  },
} as const;

export default defaultConfig;
