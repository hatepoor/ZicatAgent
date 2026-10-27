# 架构决策记录（ADR）

> 追加式：只增不改。要推翻已接受的决策，新写一条并标注"取代 ADR-xxxx"。
> 最新决策在上，编号递增。

## 决策索引

| 编号 | 标题 | 状态 | 生效架构版本 | 是否触发升级 | 日期 |
|------|------|------|--------------|--------------|------|
| ADR-0003 | CLI 与内核通过 JSONL RPC 解耦 | 接受 | v1 | 否 | 2026-10-23 |
| ADR-0002 | 长期记忆迁移到 SQLite 单库，版本与事件 append-only | 接受 | v1 | 否 | 2026-10-23 |
| ADR-0001 | 用 LangGraph 单引擎替换自研文本循环 | 接受 | v1 | 是（初版） | 2026-10-23 |

---

## ADR-0003: CLI 与内核通过 JSONL RPC 解耦

> 日期: 2026-10-23
> 状态: 接受
> 生效架构版本: v1
> 是否触发架构升级: 否
> 关联 explain: [explain/v0.1.0/update/up_cli_rpc.md](../explain/v0.1.0/update/up_cli_rpc.md)

### 背景

迁移后只剩 Python 内核，但用户希望 CLI 显示更精致（流式、工具卡片、spinner），同时不想引入 Node 依赖或复制一套业务逻辑。

### 决策

内核新增 `--rpc` 模式：stdin 接收 `task/answer/abort/exit` JSON，stdout 输出 `ready/delta/tool/tool_result/usage/interrupt/done/exit` 事件。TypeScript CLI（零依赖，Node 23 直接执行 `.ts`）只做展示与输入，业务全部留在 Python。

### 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| Python 内嵌富 CLI | 单进程、简单 | 需要 rich 等依赖，样式受限 | 放弃 |
| TypeScript 重写内核 | 前端体验统一 | 重写引擎与工具，风险大 | 放弃 |
| JSONL RPC 分离 | 零依赖、前端可替换、协议可测 | 多一层进程与协议 | 采用 |

### 后果

- **正面**: Python 内核保持单一事实源；TS CLI 可独立替换；RPC 事件可被脚本消费。
- **负面**: 多进程带来退出/中断时序问题（已修复 `exit` 等待任务收尾）；协议变更需两端同步。
- **需要同步更新**: `core/rpc.py`、`cli/zicat.ts`、docx/guide/85-引擎迁移、docx 架构模块契约。

### 关联

- 前序决策: 无
- 取代决策: 无
- 相关模块: `ui`、`runtime`

---

## ADR-0002: 长期记忆迁移到 SQLite 单库，版本与事件 append-only

> 日期: 2026-10-23
> 状态: 接受
> 生效架构版本: v1
> 是否触发架构升级: 否
> 关联 explain: [explain/v0.1.0/update/up_memory_sqlite.md](../explain/v0.1.0/update/up_memory_sqlite.md)

### 背景

原记忆是 `memory/` 下的文件集合，没有版本、没有检索、没有写审计；模型可能直接改文件，容易产生幽灵条目和重复。

### 决策

长期记忆统一进 `memory/memory.db`：`memory_items` 存当前指针，`memory_versions`/`memory_events` 只追加，FTS5 提供检索；7 个 `memory_*` 工具是唯一写入通道，SQLite 触发器拒绝 UPDATE/DELETE 版本与事件。文件只保留 L0 META-SOP、L1 兜底、导出与备份。

### 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| 继续用文件 | 简单、可 git diff | 无版本/无审计/检索弱 | 放弃 |
| 向量数据库 | 语义检索 | 重依赖、不可解释、迁移成本高 | 放弃 |
| SQLite + FTS | 零依赖、可审计、本地快 | 语义检索弱（关键词为主） | 采用 |

### 后果

- **正面**: 版本/事件可追溯，写入有审计，L1 可动态渲染，备份/导出/迁移可脚本化。
- **负面**: 记忆正文与文件可能短暂不一致，需要 `memstore.sync`；文件编辑后必须同步。
- **需要同步更新**: `memstore/*`、`zicat.py` 的 `do_memory_*`、`memory/kb/index.md`、docx/guide/30-记忆系统、docx 架构模块契约。

### 关联

- 前序决策: 无
- 取代决策: 无
- 相关模块: `memory`、`engine`、`tools`

---

## ADR-0001: 用 LangGraph 单引擎替换自研文本循环

> 日期: 2026-10-23
> 状态: 接受
> 生效架构版本: v1
> 是否触发架构升级: 是（初版）
> 关联 explain: [explain/v0.1.0/update/up_kernel_baseline.md](../explain/v0.1.0/update/up_kernel_baseline.md)

### 背景

原引擎是自研 `while` 循环 + 文本工具协议 + 内存会话，无法可靠恢复中断、无法回退、上下文裁剪与工具调度耦合在 `llmcore`/`agent_loop` 里。目标是把控制面换成可持久化、可观测的图。

### 决策

用 LangGraph `StateGraph` 作为唯一引擎：`prepare → agent ⇄ tools → human → check → finalize`；状态用 `SqliteSaver` 持久化；消息与摘要用 `operator.add` 只追加；`ask_user` 用 `interrupt()`；模型只接 OpenAI 兼容接口。legacy 引擎与插件体系整体删除。

### 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| 保留自研循环 | 无迁移成本 | 持久化/中断/回退都要自造 | 放弃 |
| 换 LangGraph | 检查点、interrupt、状态图成熟 | 引入框架依赖、需要适配工具层 | 采用 |
| 换其他编排框架 | 可能有更多能力 | 生态/文档/本地可控性不确定 | 放弃 |

### 后果

- **正面**: 跨进程 resume、对话/文件回退、统一回调、流式中断、可测试节点。
- **负面**: 依赖 `langgraph`/`langchain-*`；图状态与工具 handler 的边界需要持续维护。
- **需要同步更新**: `engine/*`、`agentmain.py`、`core/commands.py`、测试与文档。

### 关联

- 前序决策: 无
- 取代决策: 无
- 相关模块: `engine`、`runtime`、`tools`
