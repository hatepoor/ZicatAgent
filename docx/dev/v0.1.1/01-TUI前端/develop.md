# 01-TUI前端 · develop

> 所属版本: v0.1.1
> 对应架构版本: v1
> 对应架构模块: [cli 交互前端](../../../arch/v1/modules.md)
> 最后更新: 2026-10-24

## 做什么

把 `terminal-zizicat-tui/`（React 19 + Vite + Tailwind 4 视觉设计参考）落成真实前端 `ui/`：

1. **RPC 事件协议结构化**（后端）：`engine/runner.py` 的 display 载荷增加结构化字段 `kind/name/args/text/ok`，`core/rpc.py` 按字段映射新事件 `tool_call/notice` 并结构化 `usage`；`next` 纯文本保留，CLI 与 `--task` 消费端零感知。
2. **Node 桥**（`ui/server.mjs`）：spawn `python agentmain.py --rpc`，`GET /events` 以 SSE 推送内核 JSONL 事件（缓存重放 `ready`），`POST /send` 把浏览器指令写入内核 stdin；托管 `ui/dist` 构建产物；仅用 Node 内置模块。
3. **Web TUI 前端**（`ui/src/`）：复用参考项目的主题/消息块/富文本组件，事件驱动重构 `App.tsx`（删除 mock 的 `buildAgentScript`），新增 interrupt 问答、Esc 中断（abort）、打字机渐显、真实 usage 统计。

## 规范

- 前端不实现任何 Agent 逻辑；mock 的 `agent.ts` 模拟脚本不得接入内核（AGENT.md §9）。
- **slash 命令必须与内核一致**：内核命令（`core/commands.py::HELP` 定义的那套）一律透传内核处理，前端不得编造、不得拦截改名；前端仅保留纯显示层命令 `/clear`（清显示）与 `/theme`（切主题）；`/exit` `/quit` 在 Web 端拦截提示（防误触杀后端，退出走顶栏按钮）。命令补全表来自 `ready.commands`（`core/rpc.py` 解析自 `HELP`，单一事实源，改 HELP 自动跟随）。
- Web 布局按网页标准做：全宽利用、鼠标可操作（顶栏按钮：主题下拉/面板开关/中断/关于；侧栏命令点击即发送；工具块点击折叠展开；欢迎页快捷按钮），键盘只是补充。
- 输入用原生光标（textarea + `caretColor`），不自绘光标（自绘在中文/IME 下宽度错位）；Enter 发送、Shift+Enter 换行，IME 组合中不误发。
- 协议变化只增不改：`next` 纯文本必须保留；`tool`/旧 `tool_result` 兜底事件保留。
- 桥服务零 npm 依赖；前端 npm 依赖仅限参考项目已有清单（react/vite/tailwind 等）。
- 前端为纯显示层：不缓存会话状态（会话在 graph 检查点），刷新即重置显示。

## 依赖契约

- 上游：v0.1.0 `05-交互前端` 的 JSONL RPC（`core/rpc.py`）；本版对其**只增不改**。
- 下游：无。

## 验收

- 单测：`tests.test_engine`（RpcTests 含结构化事件映射用例）。
- 冒烟：`node ui/server.mjs` 后 `GET /` 返回页面、`GET /events` 收到 `ready` 重放、`POST /send` 发 slash 命令收到 `done`。
- 真实任务验收（待做）：真实模型跑一个含工具调用的任务，验证 assistant 流式块、工具块、interrupt 问答与 usage 统计。
