// UI 配置与静态文案。组件不写死数值/命令列表，统一从这里取。

export const UI_CONFIG = {
  fallbackContextWindow: 200_000,
  maxTextareaHeight: 160,
  maxRecentTools: 6,
  suggestMaxHeight: 300,
  suggestWidth: 360,
  appTitle: "zicatAgent",
} as const;

export const COMPOSER_COPY = {
  pending: "输入回答，回车发送…",
  busy: "智能体工作中… 顶栏可中断",
  idle: "输入任务或 / 命令…（Enter 发送，Shift+Enter 换行）",
  send: "发送 ↵",
};

/** 前端本地命令（纯显示层，不进内核） */
export const LOCAL_COMMANDS = [
  { cmd: "/clear", desc: "清空会话显示（本地）" },
  { cmd: "/theme", desc: "切换配色主题（本地）" },
];

/** Web 端拦截的内核命令（防误触） */
export const BLOCKED_COMMANDS = ["/exit", "/quit"];

export const ABOUT_TEXT = [
  "zicatAgent Web TUI v0.1.1 — 个人 Agent 执行内核的 Web 终端界面",
  "后端：LangGraph 单引擎 + SQLite 记忆（python agentmain.py --rpc）",
  "前端：React · Tailwind · SSE，经 Node 桥与内核 JSONL 通信",
  "斜杠命令与内核一致；/clear /theme /model /mode /workspace 为前端设置层命令，/new 走新会话 RPC。",
].join("\n");

export const QUICK_COMMANDS = [
  "/help",
  "/cost",
  "/threads",
  "/plan",
  "/memory index",
  "/review",
];

export const KEYBOARD_SHORTCUTS: Array<[string, string]> = [
  ["Enter", "发送 / 补全命令"],
  ["Shift+Enter", "换行"],
  ["Tab", "补全"],
  ["↑ ↓", "选择命令（输入 / 后）"],
  ["Esc", "中断"],
];

export const SLASH_HINT = "↑↓ 选择 · Tab 补全 · Enter 填充/发送";
