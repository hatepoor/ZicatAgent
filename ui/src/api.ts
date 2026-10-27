// ─── 与 zicatAgent 内核的通信适配器：SSE 下行（内核事件）+ POST 上行（用户指令）──
//
// 事件由 Node 桥（ui/server.mjs）从 `python agentmain.py --rpc` 的 stdout 转发而来，
// 协议见 core/rpc.py 模块 docstring。类型定义在 core/types.ts，组件不依赖传输细节。

import type { RpcEvent, SendMsg } from "./core/types";

export type {
  Entry,
  EntryStatus,
  HistoryItem,
  ModelConfig,
  PendingDelete,
  RpcCommand,
  RpcEvent,
  RpcUsage,
  SendMsg,
  SessionItem,
  ThemeState,
} from "./core/types";

/** 建立 SSE 连接，onDown 在连接断开/重连时回调；返回的 EventSource 会自动重连。 */
export function connect(onEvent: (e: RpcEvent) => void, onDown: () => void): EventSource {
  const es = new EventSource("/events");
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as RpcEvent);
    } catch {
      // 忽略无法解析的行
    }
  };
  es.onerror = onDown;
  return es;
}

/** 向内核发送一条指令；失败抛错由调用方决定如何呈现。 */
export async function send(msg: SendMsg): Promise<void> {
  const res = await fetch("/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(msg),
  });
  if (!res.ok) throw new Error(`send ${msg.type} 失败: HTTP ${res.status}`);
}
