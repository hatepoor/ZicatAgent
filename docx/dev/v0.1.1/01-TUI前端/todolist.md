# 01-TUI前端 开发进度

> 编号: `01`
> 所属版本: `v0.1.1`
> 对应架构版本: `v1`
> 依赖模块: v0.1.0 / 05-交互前端
> 最后更新: 2026-10-24

## Task 进度总览

| Task | 名称 | 状态 | 依赖 |
|------|------|------|------|
| [task1](./task1.md) | RPC 事件协议结构化 | ✅ | 无 |
| [task2](./task2.md) | Node 桥服务 | ✅ | task1 |
| [task3](./task3.md) | Web TUI 前端 | ✅ | task2 |
| [task4](./task4.md) | 端到端联调与验收 | ✅ | task3 |

## 进度日志

### 2026-10-24

- ✅ task1: RPC 事件协议结构化 — 已完成（engine/runner.py + core/rpc.py + 单测）
- ✅ task2: Node 桥服务 — 已完成（ui/server.mjs，SSE 缓存重放 ready）
- ✅ task3: Web TUI 前端 — 已完成（ui/ 工程，tsc/vite 构建通过）
- ✅ task3 返工（用户验收反馈）：布局改全宽网页式（顶栏操作区 + 会话流 + 侧栏），新增鼠标操作（主题下拉/中断/面板/侧栏命令点击/工具块折叠/发送按钮）；slash 命令废弃前端编造的表，全部透传内核，补全表改由 ready.commands 下发（解析自 core/commands.py::HELP）；输入改 textarea + 原生光标（修中文 IME 错位），Enter 发送/Shift+Enter 换行；过滤内核 `<summary>` 内部标签泄漏
- ✅ task4: 端到端联调与验收 — 冒烟 + 真实任务验收通过（工具链路/interrupt/abort/usage；含 FIX-3 修复），见根 todolist 真实测试记录
- 🐛 task1 修复（真实任务首跑暴露）：`_emit` 位置参数 `text` 与 extra 关键字 `text` 撞名，带工具调用的任务一进 `_consume` 即 TypeError。位置参数改名 `next_text`；新增 `ConsumeEmitTests`（FakeGraph 驱动 `_consume` 全链路 emit，修复前可复现）。教训：改 emit 链路必须有驱动 `_consume` 的单测，slash 命令冒烟覆盖不到工具分支。
- 🔍 TUI 全链路全量检查（2026-10-24，用户 /goal 发起）：
  - 已核实无需修：`--rpc` 杂散 print 早已重定向 stderr（agentmain.py:165）；`tools_node` 串行执行 tool_calls，前端顺序映射 tool_result 安全。
  - 修复 5 处：① 前端 interrupt 块回答后不过期，吞掉后续输入（加 `answered` 标记，回答即标记、done 收口全标记）；② 内核退出后 EventSource 自动重连 + 桥重放 ready 造成假连接（exit 时关连接；桥死亡状态不重放 ready、改发 exit 帧；`/send` 返回 503）；③ 工具耗时误从任务起点计（改按 tool_call 各自 t0）；④ delta 未过滤 `<summary>` 内部标签（delta 为完整消息文本，逐条过滤安全）；⑤ exit 事件 rpc 与桥各发一次致重复提示（前端幂等）。
  - 加固 3 处：桥 stdin EPIPE 防护、SSE 断连写异常防护、`RpcBridge.emit` 加线程锁；`_classify_next` usage 正则加 `\b` 锚定（about=2 不再误配 out=2）。
  - 新增测试：RpcBridgeTests（pump 映射 + done.usage、ask/answer 线程回路、_slash_commands 解析、正则锚定）、ConsumeEmitTests 错误工具结果（status=error → ok=False）。全量 42 tests OK。
  - 桥死亡场景冒烟通过：内核 exit 后 `/send`→503、新 SSE 连接收 exit 帧而非过期 ready、桥进程存活不崩。
  - 环境教训：Windows 下杀后台 bash 不一定杀掉 detach 的 node 子进程（残留进程占 8765 端口导致一次假阴/假阳冒烟），验证端口服务前先 `netstat` 确认无残留监听。
