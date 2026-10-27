# v1 数据模型与数据流

> 对应架构版本: v1
> 最后更新: 2026-10-23

## 实体关系

| 实体 | 说明 | 关键字段 | 关系 |
|------|------|----------|------|
| Thread | 一次会话线程（graph thread_id） | `thread_id`、`checkpoint_id` | 1:N Checkpoint |
| Checkpoint | 某轮状态快照（`ZicatState`） | `messages`、`summaries`、`working`、`turn` | N:1 Thread |
| MemoryItem | 记忆条目当前指针 | `id`、`layer`、`kind`、`name`、`body`、`status`、`priority` | 1:N Version/Event |
| MemoryVersion | 条目历史版本（只追加） | `version_id`、`item_id`、`body`、`reason`、`actor` | N:1 Item |
| MemoryEvent | 记忆操作审计（只追加） | `event_id`、`item_id`、`event`、`detail` | N:1 Item |
| MemoryLink | 条目关系 | `from_id`、`to_id`、`rel` | N:N Item |
| SessionState | 旧 session 工作记忆兼容表 | `session_id`、`working` | 1:1 Thread（可选） |

```mermaid
erDiagram
  MEMORY_ITEMS ||--o{ MEMORY_VERSIONS : has
  MEMORY_ITEMS ||--o{ MEMORY_EVENTS : logs
  MEMORY_ITEMS ||--o{ MEMORY_LINKS : from
  MEMORY_ITEMS ||--o{ MEMORY_LINKS : to
```

## 存储选型

| 数据 | 存储 | 选型理由 | 一致性要求 |
|------|------|----------|------------|
| 会话状态 | SQLite `temp/graph.db`（WAL） | 高频写、按 thread 恢复、本地零依赖 | 每轮提交；同 thread 串行 |
| 长期记忆 | SQLite `memory/memory.db`（WAL + FTS5） | 版本/事件可审计、关键词检索、append-only | 写事务内更新指针 + 插版本 + 插事件 + FTS |
| L0 META-SOP | 文件 `memory/kb/memory_management_sop.md` | 代码直接读取，人类可编辑 | 文件为准，同步入库为副本 |
| L1 兜底 | 文件 `memory/l1_fallback.txt` | 库不可用时降级 | 最终以库动态渲染为准 |
| SOP 源文件 | 文件 `memory/kb/*.md` | 可 git diff、可审阅 | 改后 `memstore.sync` 回灌 |
| 原始会话日志 | 文件 `temp/model_responses/*.txt` | L4 归档原料、人工排查 | 追加写；按任务轮次 |
| 导出快照 | 文件 `memory/export/` | 可进 git 的可读备份 | 由 `memstore.export` 生成 |
| 二进制备份 | 文件 `memory/backup/` | 灾难恢复 | 定时/手动快照 |

## 关键数据流

### 1. 任务执行

1. `ui` 把输入交给 `runtime.put_task()`，生成 thread_id 与初始 `HumanMessage`。
2. `engine` 的 `prepare` 拼 system prompt（`sys_prompt` + 日期 + 动态 L1）并初始化 `working`。
3. `agent` 节点把 `ZicatState` 投影成模型视图（system + 工作记忆 + 最近消息/摘要），调用模型。
4. 有工具调用 → `tools` 节点 `ToolRuntime.run_tool()` → 结果以 `ToolMessage` 追加；无工具调用 → `check` 节点做 `no_tool` 二次确认。
5. 循环直到 `finalize`；展示事件由 `runtime` 队列消费并输出。

**一致性策略**: 每轮状态由一个检查点提交；消息只追加；工具副作用直接落盘（文件/记忆/浏览器），不回滚。

### 2. 记忆写入

1. 模型调用 `memory_write` / `memory_patch` / `memory_archive`。
2. `zicat.do_memory_*` → `MemoryTools.dispatch()` → `MemoryStore`。
3. 同一事务内：更新 `memory_items` 当前指针 → 插入 `memory_versions` → 插入 `memory_events` → FTS 触发器同步索引。
4. `memory_read/search/index` 走 `memory_items` + `memory_fts`；L1 由 `render_l1()` 动态生成。

**一致性策略**: 单写者 + `tx()` 串行化；版本/事件触发器拒绝改删；文件副本靠 `memstore.sync` 最终一致。

### 3. 中断与恢复

1. 模型调用 `ask_user` → `human` 节点 `interrupt(values)`，检查点保存挂起状态。
2. CLI 进程退出后，新进程用 `/resume <thread_id>` 或 RPC `answer` 恢复。
3. `resume_pending()` 读取检查点，用 `Command(resume=answer)` 继续图执行。

**一致性策略**: interrupt 前检查点已落库；回答与后续消息追加到同一 thread；不允许并发 resume 同一 thread。

### 4. 模型调用与日志

1. `engine` 通过 `langchain-openai` 调用模型（绑定工具，支持流式）。
2. `UsageTracker` 收集 token；`LoggingCallback` 把 Prompt/Response 追加到 `temp/model_responses/`。
3. L4 归档脚本 `compress_session.py` 读取日志，压缩后写入 `memory/L4_raw_sessions/`。

**一致性策略**: 日志追加写；归档是离线批处理，不阻塞主流程。

## 数据迁移

- **legacy 会话**：不迁移；旧 `session_restore` 文本日志已停止支持。
- **legacy 记忆文件**：通过 `memstore.migrate` 导入 SQLite，manifest 记录 `source`/`source_sha256`；`verify` 校验正文 sha256。
- **当前文件布局**：SOP 已统一到 `memory/kb/`；`memstore.sync` 按文件扫描（`kb/index.md` 排除），按条目名更新。
- **架构升级迁移**：v1 为初版，暂无跨代迁移。
