# md · RPC 事件协议结构化与 Web TUI 前端

> 版本: v0.1.1（相对 v0.1.0）
> 类型: modify
> 日期: 2026-10-24

## 变了什么

### RPC 事件协议（增强，向后兼容）

v0.1.0 的事件只能靠文本前缀猜测类型（`core/rpc.py::_classify_next` 认 `🛠️`/`📥`/`[usage]`），工具参数、多行结果等信息在翻译层丢失。v0.1.1 在 `engine/runner.py::_emit` 的 display 载荷上增加结构化字段，`core/rpc.py::_event_from_item` 按字段映射：

| 事件 | v0.1.0 | v0.1.1 |
|------|--------|--------|
| `delta` | 文本（分类自前缀） | `kind="assistant"` 直通 |
| `tool` | 仅工具名 | 新增 `tool_call`：`name` + `args`（显示摘要） |
| `tool_result` | 160 字符单行预览 | 保留兜底；新增多行 `text`（1200 字符）+ `ok` |
| `usage` | 仅 `text` 字符串 | 新增 `requests/input/output` 数字字段 |
| `notice` | （无） | 新增：挂起提示等系统消息 |
| `ready` | engine/model/cwd | 新增 `commands`：内核斜杠命令表（`core/rpc.py` 解析自 `core/commands.py::HELP`） |

兼容性：`next` 纯文本字段保留，Python CLI 与 `--task` 消费端不感知 `kind`；无 `kind` 的旧载荷仍走文本分类兜底。

### 前端 slash 命令对齐内核（v0.1.1 返工）

初版前端自拟了一套 `/help /model /about` 命令，与内核 `core/commands.py` 的真实命令表（`/help /review /plan /cost /threads /memory …`）不符。返工后约定：

- 内核命令一律透传内核处理，前端不编造、不拦截；
- 前端仅保留纯显示层命令 `/clear`（清显示）、`/theme`（切主题）；
- `/exit` `/quit` 在 Web 端拦截提示（防误触杀后端），退出走顶栏按钮；
- 命令补全与侧栏命令列表来自 `ready.commands`，改 `HELP` 自动跟随，无需改前端。

### 新增 Web TUI 前端（`ui/`）

- 新增 `ui/server.mjs` 桥：spawn `--rpc` 内核，SSE 下行（缓存重放 `ready`）+ `POST /send` 上行 + 静态托管，仅 Node 内置模块。
- 新增 `ui/` 前端：复用 `terminal-zizicat-tui/` 的主题与组件，事件驱动接真实数据源；`terminal-zizicat-tui/` 降级为纯历史参考。

## 没变什么

- RPC 指令集（`task/answer/abort/exit`）不变。
- 引擎状态图、检查点、记忆库、工具层均未动；消息只追加与记忆版本只追加约定不受影响（display 事件只是显示视图）。
