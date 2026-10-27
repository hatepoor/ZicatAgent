# v1 模块说明

> 对应架构版本: v1
> 每个模块一节；模块 id 必须与 `index.md` 的模块清单、`architecture.html` 的 `ARCH.modules[].id` 一致。
> 每个模块前保留 `<a id="{模块 id}"></a>` 锚点，供 HTML 和 develop.md 直接跳转。

<a id="ui"></a>

## ui: Web 前端

> 所属层: 接入层
> 对应 dev 模块: [05-交互前端](../../dev/v0.1.0/05-交互前端/develop.md)
> 最后更新: 2026-10-23

### 职责

- **做什么**: Web UI 解析用户输入与 slash 命令；调用 `runtime` 投递任务；展示流式文本、工具调用、用量与中断；提供 JSONL RPC 协议（`ui/server.mjs`，SSE + POST）。
- **不做什么**: 不实现 Agent 循环、不直接读写记忆库、不直接操作工具；不持有会话状态（状态在 graph 检查点）。

### 对外契约

| 契约 | 类型 | 输入 | 输出/错误 | 说明 |
|------|------|------|-----------|------|
| `core.commands.handle(agent, raw_query, emit) -> bool` | 函数 | 原始输入、输出回调 | 是否已消费 | 命令/普通任务分流 |
| RPC 命令 | JSONL | `{"type":"task/answer/abort/exit", ...}` | — | stdin |
| RPC 事件 | JSONL | — | `ready(含 commands)/delta/tool_call/tool_result/notice/tool/usage/interrupt/done/exit` | stdout；`kind` 结构化事件为主，`tool`/旧 `tool_result` 为无 kind 文本的兜底；`commands` 解析自 `core/commands.py::HELP` |
| display 事件载荷 | 队列 dict | `{"next": str, "source": str, "kind"?: assistant/tool_call/tool_result/notice, "name"?/args?/text?/ok?}` | — | `engine.runner._emit` 产出；`next` 纯文本供 --task/旧消费端，结构化字段供 RPC |
| Web UI 桥 | HTTP | `GET /events`、`POST /send` | 静态托管 `ui/dist` | `ui/server.mjs`，仅 Node 内置模块 |

### 依赖

| 被依赖模块 | 依赖内容 | 契约 |
|------------|----------|------|
| runtime | 任务投递、进程主循环 | `put_task()`、`run()` |

### 关键约束

- CLI 不缓存会话；`/threads`、`/resume` 都通过 graph 检查点查询。
- RPC `exit` 必须先等待当前任务收尾，避免截断 `done`。
- 结构化事件只增不改：`next` 纯文本必须保留，CLI 与 `--task` 消费端不感知 `kind` 字段。
- Web UI 桥只做转发与静态托管，不实现任何 Agent 逻辑；前端状态仅限显示层。

### 扩展点

- 新前端只需实现 JSONL 协议即可接入；新命令在 `core/commands.py` 增加分支并更新 `/help`。
- 新显示事件在 `engine.runner._emit` 加 `kind`，`core.rpc._event_from_item` 映射，前端在 `ui/src/App.tsx` 事件处理器消费。

---

<a id="runtime"></a>

## runtime: 运行入口

> 所属层: 应用层
> 对应 dev 模块: [01-运行骨架](../../dev/v0.1.0/01-运行骨架/develop.md)
> 最后更新: 2026-10-23

### 职责

- **做什么**: 解析命令行参数；加载 `mykey.py` 与引擎配置；构造 `ZicatAgent`；按模式运行（交互/`--task`/`--func`/`--reflect`/`--rpc`）；消费任务队列并把结果写到 stdout/文件；处理 `_stop`/`_keyinfo`/`_intervene` 文件协议。
- **不做什么**: 不实现图节点；不直接调工具；不写记忆库。

### 对外契约

| 契约 | 类型 | 输入 | 输出/错误 | 说明 |
|------|------|------|-----------|------|
| `ZicatAgent.put_task(query, source="user") -> queue.Queue` | 方法 | 任务文本 | 展示队列 | 所有前端/模式的统一入口 |
| `ZicatAgent.run() -> int` | 方法 | — | 退出码 | 交互/任务循环 |
| `--task IODIR` | CLI | 目录（`input.txt`/`reply.txt`） | `output.txt` 等 | 持续协作模式 |
| `--func PROMPT_FILE` | CLI | prompt 文件 | `*.out.txt` + 退出 | 纯函数模式 |
| `--reflect SCRIPT` | CLI | reflect 脚本 | 进程 | 无人值守 |
| `--rpc` | CLI | stdin JSONL | stdout JSONL | 前端协议 |
| `engine.settings.oai_configs()` / `graph_config()` | 函数 | — | dict | 模型与引擎配置 |

### 依赖

| 被依赖模块 | 依赖内容 | 契约 |
|------------|----------|------|
| engine | 任务执行、恢复 | `run_graph_task()`、`resume_pending()` |
| ops | reflect 脚本加载与调度 | `check()` 契约 |

### 关键约束

- 进程为单线程任务循环；任务队列一次一个。
- `--rpc` 时 stdout 只能输出 JSONL，日志重定向到 stderr。
- `--task` 的 `_stop` 文件在任务运行中也要被轮询（节点边界）。

### 扩展点

- 新模式在 `agentmain.py` 增加分支；配置项统一从 `engine/settings.py` 读取。

---

<a id="ops"></a>

## ops: 自动化与工程

> 所属层: 应用层
> 对应 dev 模块: [06-质量与工程](../../dev/v0.1.0/06-质量与工程/develop.md)
> 最后更新: 2026-10-23

### 职责

- **做什么**: 提供 `reflect/*` 无人值守脚本（scheduler、goal、autonomous、team worker）；维护测试与验收脚本；维护文档体系（docx 四层）；提供打包与依赖声明。
- **不做什么**: 不参与单次任务的图执行；不定义业务契约。

### 对外契约

| 契约 | 类型 | 输入 | 输出/错误 | 说明 |
|------|------|------|-----------|------|
| reflect 脚本 | Python 模块 | `INTERVAL`、`ONCE`、可选 `init(agent)`、`check() -> str/None` | 任务字符串/None | 由 `--reflect` 加载 |
| 定时任务 | JSON | `sche_tasks/*.json` | 触发 prompt | scheduler 轮询 |
| 测试命令 | CLI | `python -m unittest tests.test_engine tests.test_integration` | 通过/失败 | 验收基线 |
| 打包声明 | TOML | `pyproject.toml` | 可安装包 | 需与实际模块一致 |

### 依赖

| 被依赖模块 | 依赖内容 | 契约 |
|------------|----------|------|
| 无 | — | 脚本由 `runtime` 加载，不反向依赖运行时 |

### 关键约束

- reflect 脚本必须可独立运行、无状态（状态写文件/环境变量）。
- 测试不依赖真实模型；真实任务验收单独执行。
- 文档三层边界（arch/dev/explain）不能混写。

### 扩展点

- 新自动化脚本放到 `reflect/`，即可被 `/scheduler` 发现；新测试文件加入 `tests/`。

---

<a id="engine"></a>

## engine: 图引擎

> 所属层: 控制层
> 对应 dev 模块: [02-图引擎](../../dev/v0.1.0/02-图引擎/develop.md)
> 最后更新: 2026-10-23

### 职责

- **做什么**: 定义并运行 LangGraph 状态图；维护只追加的 `ZicatState`；构建模型视图（system + 工作记忆 + 折叠历史）；执行工具节点与 `ask_user` 中断；持久化检查点；支持 `/resume` 跨进程恢复、`/rewind` 回退、流式中断；收集用量与模型日志。
- **不做什么**: 不实现具体工具；不实现记忆存储；不处理 CLI 展示。

### 对外契约

| 契约 | 类型 | 输入 | 输出/错误 | 说明 |
|------|------|------|-----------|------|
| `ZicatState` | TypedDict | — | `messages/summaries/working/turn/exit_reason/meta` | `messages`/`summaries` 用 `operator.add` |
| `build_graph(runtime, checkpointer, max_turns, context_cap, model, callbacks)` | 函数 | 运行时对象 | 编译后的图 | 节点：prepare/agent/tools/human/check/finalize |
| `run_graph_task(agent, query, source, interrupt_handler) -> Queue` | 函数 | 任务文本 | 展示队列 | 新任务或续跑 |
| `resume_pending(agent, thread_id, answer) -> Queue` | 函数 | thread id、回答 | 展示队列 | 跨进程恢复 interrupt |
| `build_model_messages(state, base_prompt, context_cap)` | 函数 | 状态 | `list[BaseMessage]` | 视图折叠，不写存储 |
| `run_tool(name, args, ai_message)` | `ToolRuntime` 方法 | 工具名/参数 | 文本结果 | 统一 dispatch 与退出标记 |

### 依赖

| 被依赖模块 | 依赖内容 | 契约 |
|------------|----------|------|
| tools | 工具执行 | `ToolRuntime.run_tool()` |
| memory | L1 渲染、记忆工具 | `load_L1()`、`memory_*` 工具 |

### 关键约束

- 存储层消息永不删改；折叠只影响模型视图。
- 同一 thread 串行执行；interrupt 挂起期间不写新消息。
- 模型调用流式；每个 chunk 检查 `stop_sig`。
- 检查点写入 `temp/graph.db`；thread_id 由 CLI 生成并持久化在 meta。

### 扩展点

- 新图节点在 `engine/graph.py` 增加并接线；新回调实现 `BaseCallbackHandler` 后传入 `build_graph`。
- 需要新状态字段时在 `engine/state.py` 增加，并明确 reducer 语义。

---

<a id="tools"></a>

## tools: 工具系统

> 所属层: 能力层
> 对应 dev 模块: [04-工具系统](../../dev/v0.1.0/04-工具系统/develop.md)
> 最后更新: 2026-10-23

### 职责

- **做什么**: 提供 20 个工具（13 原子 + 7 记忆）；从 `assets/tools_schema.json` 读取唯一 schema；把工具调用 dispatch 到 `tools.registry` 注册的实现；实现文件/搜索/代码/浏览器/网页/记忆能力；维护工作记忆与文件回退跟踪。
- **不做什么**: 不实现 Agent 循环；不直接写记忆版本（记忆工具转发 `MemoryStore`）；不持有会话状态。

### 对外契约

| 契约 | 类型 | 输入 | 输出/错误 | 说明 |
|------|------|------|-----------|------|
| `tools_schema.json` | JSON | — | OpenAI function schema | 唯一 schema 来源 |
| `BaseHandler.dispatch(name, args, response, **kwargs)` | 方法 | 工具名/参数 | 生成器/`StepOutcome` | `do_<name>` 反射分发 |
| `StepOutcome(data, next_prompt, should_exit)` | dataclass | — | — | 工具结果与退出语义 |
| `ToolRuntime.run_tool()` | 方法 | 工具名/参数 | 字符串结果 | 拦截 `memory/` 写入、记录 `_stop` |
| `memory_*` 工具 | 工具 | 记忆参数 | JSON | 转发 `MemoryTools` |

### 依赖

| 被依赖模块 | 依赖内容 | 契约 |
|------------|----------|------|
| memory | 记忆工具实现 | `MemoryTools.dispatch()` |

### 关键约束

- schema 只改 `assets/tools_schema.json`；不在代码里另写一份。
- `file_write`/`file_patch`/`file_apply_patch` 禁止写 `memory/`；写操作限制在工作区与仓库根（`ZICAT_FILE_ROOTS` 可扩展），`.env`/`mykey.py`/`.git/` 拒绝写入；`code_run` 旁路属于已知限制。
- `grep`/`glob` 以 ripgrep 为后端，`ZICAT_NO_RG=1` 或未安装时走纯 Python 兜底；`file_apply_patch` 采用 Codex 风格补丁格式，任一 hunk 失败整单不落盘。
- 工具结果统一序列化，非 JSON 类型用 `json_default`。
- 浏览器工具依赖本地 Chrome 扩展与 `TMWebDriver`。

### 扩展点

- 新工具：schema 加条目 + `zicat.py` 加 `do_<name>` + handler 测试。
- 新能力脚本可放 `memory/*.py`，由 `code_run` import，不必进 schema。

---

<a id="memory"></a>

## memory: 记忆系统

> 所属层: 能力层
> 对应 dev 模块: [03-记忆系统](../../dev/v0.1.0/03-记忆系统/develop.md)
> 最后更新: 2026-10-23

### 职责

- **做什么**: 管理 SQLite 记忆库（`memory_items`/`memory_versions`/`memory_events`/`memory_links`/`memory_fts`/`session_state`）；提供 7 个记忆工具的语义实现；动态渲染 L1；从文件迁移/同步/导出/备份；维护 `memory/kb/` SOP 文档布局。
- **不做什么**: 不实现图循环；不决定何时写记忆（模型经工具触发）；不直接改会话状态。

### 对外契约

| 契约 | 类型 | 输入 | 输出/错误 | 说明 |
|------|------|------|-----------|------|
| `MemoryStore` | 类 | db | 查询/写入 | `get/search/patch/archive/versions/events/links/index` |
| `memory_*` 工具 | 7 个 | 名称/正文/关键词 | JSON | `memory_search/read/write/patch/archive/link/index` |
| `load_L1()` / `render_l1()` | 函数 | — | 文本 | L1 动态渲染，失败回退文件 |
| `memstore.sync/export/backup/verify` | CLI 模块 | db/manifest | 退出码/统计 | 文件↔库同步与校验 |
| `memory/kb/*.md` | 文件 | — | — | SOP 源文件，sync 后入库 |

### 依赖

| 被依赖模块 | 依赖内容 | 契约 |
|------------|----------|------|
| 无 | — | — |

### 关键约束

- 版本/事件只 insert；触发器拒绝 UPDATE/DELETE。
- 写入必须经 `MemoryStore`（事务内更新指针 + 插版本 + 插事件 + FTS）。
- 文件与库可能短暂不一致；以库为准，`sync` 负责回灌。
- L0 META-SOP 由代码读取 `memory/kb/memory_management_sop.md`。

### 扩展点

- 新记忆分类/标签在 `migrate.py` 的 `TAGS` 增加；新工具在 `memstore/tools.py` 与 schema 同步。
