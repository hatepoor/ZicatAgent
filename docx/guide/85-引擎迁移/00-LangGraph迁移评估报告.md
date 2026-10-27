# LangGraph / LangChain 迁移评估报告

> 文档索引：[docs/README.md](../README.md)
>
> 前提（已定）：**统一使用 OpenAI 兼容接口**（`ChatOpenAI`），不引入 `langchain-anthropic`；
> 采用"重写控制面、保留资产层、退役旧管线"的策略，而非在旧 loop 外再包一层。

## 0. 四个问题的直接回答

| 问题 | 结论 |
|---|---|
| **1. 哪些能用 LangGraph/LangChain 替代** | 控制面全换：循环、模型客户端、工具调度、历史裁剪、中断、多模型回退、会话恢复、成本统计。**资产层不动**：`zicat.py` 工具实现、`simphtml`、`TMWebDriver`、`memory/`、`assets/`。 |
| **2. Checkpointer 存哪** | 本机默认 **单个 SQLite 文件** `temp/langgraph.db`（WAL 模式）；多进程/多机切 **Postgres**；禁止用 `MemorySaver` 上生产。 |
| **3. 图怎么流转** | `StateGraph(ZicatState)`：`prepare → agent ⇄ tools → finalize`，条件边由 `tool_calls` 与 `turn` 预算决定；重锚/裁剪/节拍放在 `pre_model_hook`，摘要与纪律放在 `post_model_hook`。 |
| **4. 多 agent 怎么写** | 子图 + 独立 `thread_id` + 显式状态投影；并行用 `Send`，任务板用 `Store`；长跑/需崩溃隔离的仍保留子进程（`--task`）。 |

---

## 1. 优化与替代方案

### 1.1 组件级替换表

| 现有组件 | 行数 | LangGraph / LangChain 替代 | 动作 |
|---|---|---|---|
| `agent_loop.py`（while + `StepOutcome`） | 132 | `StateGraph` + `ToolNode` + 条件边 | **替换** |
| `llmcore.py` 的 OpenAI 客户端 / SSE / 重试 | ~600 | `ChatOpenAI`（底层 httpx） | **替换** |
| `llmcore.py` 的 Claude 客户端 | ~400 | — | **退役**（统一 OpenAI） |
| `llmcore.py` 的 `ToolClient` 文本协议 | ~150 | — | **退役**（图引擎只走原生 tool calling） |
| `llmcore.trim_messages_history`（字符预算） | ~25 | `pre_model_hook` 内等价实现 | **重写，保留参数** |
| `MixinSession` 多模型故障转移 | ~90 | `Runnable.with_fallbacks([...])` | **替换** |
| `zicat.py` 的 `do_*` 工具实现 | 592 | 不替换；包成 `StructuredTool` | **适配** |
| `assets/tools_schema.json` | 6KB | 继续做唯一真相，生成 pydantic `args_schema` | **保留** |
| `StepOutcome.next_prompt` 每步重锚 | — | `pre_model_hook` 临时注入（不进 State） | **保留语义** |
| `turn_end_callback` 的 15/17/41/175 节拍 | ~25 | `pre_model_hook` 按 `turn` 计算 | **保留语义** |
| `history_info` / `key_info` | — | `ZicatState.history` / `ZicatState.working` | **迁移** |
| `ask_user`（`should_exit`） | 6 | `interrupt()` + checkpointer | **升级** |
| `cost_tracker`（patch `_record_usage`） | 425 | `BaseCallbackHandler.on_llm_end` + `usage_metadata` | **替换** |
| `core/session_restore`（解析文本日志） | 1294 | checkpointer 的 thread 列表 + `get_state` | **替换** |
| `core/rewind`（文件回退） | 1125 | 图状态用 `get_state_history`；文件回退保留原实现 | **混合** |
| `core/plan_state` | 372 | `ZicatState` 字段 + 条件边 | **简化** |
| `plugins/hooks.py` 事件总线 | 67 | LangChain callbacks / `astream_events` | **替换或保留** |
| `reflect/` 自动化 | 329 | 不改（调 `engine.runner`） | **保留** |
| `memory/` L0-L4 + 自进化 | 21 文件 | 不改；可选增量接 `Store` | **保留** |
| 多 agent（`--func`/`--task`/BBS） | — | 子图 / `Send` / `Store` | **重写**（见 §4） |
| `core/cli` 斜杠命令 | ~200 | 保留，输出层适配流式事件 | **保留** |

### 1.2 收益

1. **人机中断真实化**：`interrupt()` 能把任务挂起并持久化，`ask_user` 不再是"结束本轮"的假中断。
2. **状态可回放**：每个 super-step 落检查点，天然支持"回到第 N 步"、断点续跑。
3. **并行编排**：`Send` 做 fan-out / map-reduce，替换手工 `--func` 批量。
4. **可观测性**：`astream_events` 统一事件流，接 LangSmith/Langfuse 成本低。
5. **代码量下降**：控制面约 1,300 行替代旧管线约 1,500 行 + 可退役 `core/` 约 3,000 行。
6. **工具参数校验**：JSON Schema → pydantic，模型传错参在调用前就被拦。

### 1.3 代价

1. **依赖变重**：`langgraph` + `langchain-core` + `langchain-openai` + `langgraph-checkpoint-sqlite` + pydantic v2 + httpx，约 30–50 MB（现在是 5 个小依赖）。
2. **版本漂移快**：LangChain 生态 API 迭代频繁，必须锁版本。
3. **双真源风险**：checkpointer 与 `llmcore.history` 若同时存在，token 统计与裁剪会错乱——必须只留一个。
4. **zicatAgent 特色要移植**：重锚、节拍、字符预算裁剪、`_fix_messages` 的 pairing 修补，都要在新 hook 里复刻。
5. **中断语义变化**：`ask_user` 从"结束"变成"挂起+恢复"，CLI 要改交互。

### 1.4 明确不迁移（资产层）

| 资产 | 理由 |
|---|---|
| `TMWebDriver.py` + `assets/tmwd_cdp_bridge/` | 真实浏览器会话与反检测，框架不提供，重写成本最高 |
| `simphtml.py` | 几何密度简化算法，1,100 行调出来的经验 |
| `zicat.py` 工具实现与坑（超时、编码、路径） | 同上 |
| `memory/` 21 个 SOP + L1 索引 | 自进化语料，是这套系统真正的差异点 |
| `assets/sys_prompt.txt`、`l1_structure.txt` | 行为约束与记忆契约 |

---

## 2. Checkpointer 存储

### 2.1 后端选型

| 实现 | 存储位置 | 依赖 | 适用 |
|---|---|---|---|
| `MemorySaver` | 进程内存字典 | 内置 | 单元测试 / 一次跑完的脚本 |
| **`SqliteSaver`** | **单文件** `temp/langgraph.db` | `langgraph-checkpoint-sqlite` | **本机单进程 CLI（推荐）** |
| `AsyncSqliteSaver` | 同上 | + `aiosqlite` | 异步 CLI/服务 |
| `PostgresSaver` | Postgres 表 | `langgraph-checkpoint-postgres` + `psycopg` | 多进程/多机、Team 并发 |
| 自定义 | 任意 | 实现 `BaseCheckpointSaver` | 已有 Redis/对象存储时 |

**决策**：本机默认 SQLite 单文件；`--task` 多进程并发时先各自用独立 db（`temp/langgraph_{task}.db`），真上多机再换 Postgres。

### 2.2 SQLite 初始化

```python
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

conn = sqlite3.connect("temp/langgraph.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")   # 并发读写必须
saver = SqliteSaver(conn)
saver.setup()                              # 建表，幂等
graph = builder.compile(checkpointer=saver)
```

表结构（实测版本为两张表）：

| 表 | 内容 |
|---|---|
| `checkpoints` | `thread_id`、`checkpoint_ns`、`checkpoint_id`、`parent_checkpoint_id`、`metadata`、序列化状态 |
| `writes` | 每个节点产生的中间写入，用于恢复未完成的 super-step |

> 不同版本可能额外建 `checkpoint_blobs`；本机实测只有 `checkpoints` 与 `writes`。

序列化用 `JsonPlusSerializer`（msgpack 系），存的是 blob，**不要直接读表**，用 `graph.get_state(config)`。

### 2.3 键结构（决定"一条状态存在哪"）

```python
config = {"configurable": {"thread_id": "cli:2026-10-22-a1b2", "checkpoint_ns": ""}}
```

| 维度 | 含义 | 本项目的取值规范 |
|---|---|---|
| `thread_id` | 一条独立会话 | `cli:{session}` / `task:{name}` / `sub:{parent}:{uuid}` / `team:{run}:w{n}` |
| `checkpoint_ns` | 子图命名空间 | 根图为空；子图自动为 `节点名:uuid` |
| `checkpoint_id` | 单步快照 | 由框架生成，可 `get_state(config, checkpoint_id=...)` 取任意步 |

### 2.4 容量与清理

- 粗估：20 轮、每轮约 3k token 的会话，落盘约 **2–5 MB**（blob 去重后）。
- 每个 super-step 一条检查点；180 轮 ≈ 三百多条记录。
- 清理策略：
  1. `get_state_history` + 自定义保留策略，或按 `thread_id` 删除（`delete_thread` / SQL）；
  2. 保留 30 天，挂到 `reflect/scheduler.py` 的 12h 任务里；
  3. **大产物不入消息**：`code_run` / `web_scan` 结果先截断，完整内容写文件，消息里只留路径（沿用 zicatAgent 现有策略）。

### 2.5 与现有存储的关系（避免双真源）

| 存储 | 角色 | 迁移后 |
|---|---|---|
| checkpointer（SQLite） | **对话状态真源** | 新建 |
| `temp/model_responses/*.txt` | 人类可读审计日志 | 保留，不再作为恢复来源 |
| `memory/` | 长期记忆与技能 | 保留，不受 checkpointer 影响 |
| `temp/langgraph.db` | 状态库 | `.gitignore` 忽略 |

> `/continue` 必须改数据源：从"解析文本日志"改为"列 checkpointer 的 thread"。
> 这是 P2 的明确改动项，否则恢复出来的状态与图状态对不上。

### 2.6 何时换 Postgres

满足任一条件就切换：① 同时写 checkpoint 的进程 > 3；② 需要多机共享会话；③ Team 多 worker 共用任务板；④ 单库超过约 2 GB。
迁移成本低：`PostgresSaver.from_conn_string(...)` + `.setup()`，其余代码不变。

---

## 3. 图的流转与编排

### 3.1 总体拓扑

```
START
  │
  ▼
prepare ──► agent ◄──────────┐
              │               │
              ├─ tool_calls ──► tools
              ├─ 需人工确认 ──► human (interrupt)
              └─ 结束 ────────► finalize ──► END
```

- `prepare`：拼 system prompt（`sys_prompt` + 日期 + L1 索引），初始化 `working`，写 `meta`。
- `agent`：调用模型（绑定工具），`turn += 1`。
- `tools`：`ToolNode` 执行工具，结果以 `ToolMessage` 回灌。
- `human`：`interrupt()` 挂起，恢复后继续。
- `finalize`：正常结束；若是预算耗尽，注入"交接总结"提示后结束。

### 3.2 State 定义

```python
class ZicatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]   # 对话（去重/替换）
    working:  dict                                        # 覆盖式：key_info、in_plan_mode
    history:  Annotated[list[str], operator.add]          # 追加式：轮级摘要
    turn:     int
    exit_reason: str | None
    meta:     dict
```

**绝不进 State 的东西**（不可序列化）：`ZicatAgentHandler`、cwd、socket、`stop_signal`、模型客户端。
它们放 `config["configurable"]`（运行时上下文）或闭包。

### 3.3 两个 hook 承担 zicatAgent 的"特色"

**`pre_model_hook(state) -> list[BaseMessage]`**（每次模型调用前，返回**临时**消息列表，不写回 State）

1. **重锚**：把 `working["key_info"]` 渲染成 `### [WORKING MEMORY]` 块，作为临时 `HumanMessage` 附在末尾；
2. **历史骨架**：`history` 折叠成 `<history>` 块（奇数轮注入，对应 zicatAgent 的 `%2` 逻辑）；
3. **L1 刷新**：每 15 轮把 system message 替换成最新 L1（对应 zicatAgent 的 `turn % 15`）；
4. **节拍纪律**：按 `turn` 计算 17/41/175 三条 DANGER 提示，拼进临时消息；
5. **裁剪**：对发给模型的消息做字符预算裁剪（复用 zicatAgent 的 `context_win*3` 阈值与折叠规则）。

**`post_model(state) -> dict`**（每次模型返回后）

1. 抽取 `<summary>`（80 字符），`history` 追加一条 `[Agent] ...`；
2. 缺失 `<summary>` 时，在下轮临时消息里加"必须包含 summary"提示（记到 `working`）；
3. 不在这里做纪律注入（放 pre 里按 turn 计算，避免状态污染）。

> 关键点：**hook 返回的临时消息不落 State**，否则每轮重锚会撑爆 checkpoint。

### 3.4 边与预算

```python
builder.add_edge(START, "prepare")
builder.add_edge("prepare", "agent")
builder.add_conditional_edges("agent", route_after_agent,
    {"tools": "tools", "human": "human", "finalize": "finalize"})
builder.add_edge("tools", "agent")
builder.add_edge("human", "agent")
builder.add_edge("finalize", END)
```

`route_after_agent` 的判定顺序：

1. 有 `tool_calls` → `tools`；
2. 调用了需要确认的工具（`ask_user` / 高风险 `code_run`）→ `human`；
3. `turn >= max_turns` → `finalize`（带预算耗尽提示）；
4. 否则 → `finalize`（自然结束）。

**预算注意**：`recursion_limit` 数的是 **super-step**，不是轮次。一轮 ≈ 2 步（agent + tools），所以
`recursion_limit = max_turns * 2 + 10`（180 轮 → 约 370），同时用 State 里的 `turn` 做业务预算。

### 3.5 流式与 CLI 接线

```python
for mode, chunk in graph.stream(inputs, config, stream_mode=["messages", "updates"]):
    if mode == "messages":  emit(chunk[0].content)      # 逐 token 输出
    elif mode == "updates": emit(f"[{list(chunk)[0]}]") # 节点切换提示
```

`engine/runner.run_task(agent, query, emit)` 负责：
1. 生成/复用 `thread_id`；
2. 把流事件翻译成 CLI 的 `next` / `done` 协议；
3. 处理 `__interrupt__`：把问题抛给 CLI，等 `Command(resume=...)`；
4. 把最终摘要写回 `agent.history`（兼容现有 `/cost`、`/continue` 等命令）。

### 3.6 中断与恢复

```python
from langgraph.types import interrupt, Command

def human_node(state):
    answer = interrupt({"question": state["working"]["_pending_q"]})
    return {"messages": [HumanMessage(content=answer)]}
```

- 必须 `compile(checkpointer=...)` + `thread_id`，否则 `interrupt()` 直接报错；
- CLI 侧：`/continue` 变成"选择 thread"，输入答案后以 `Command(resume=答案)` 继续；
- 超时未恢复的 thread 由清理任务回收。

### 3.7 错误与中止

| 场景 | 处理 |
|---|---|
| 模型 HTTP 失败 | `ChatOpenAI` 自带重试 + `with_fallbacks` 切备用模型 |
| 工具抛异常 | ToolNode 捕获，转成 `ToolMessage(status="error", content=...)`，模型自行决策 |
| 用户 Ctrl-C | 设 `configurable["stop"]=True`；流消费循环检查后抛 `GraphInterrupt`/取消 |
| 彻底中止 | 保留 zicatAgent 现有的"关 socket"补丁，用于挂死的连接 |

---

## 4. 多 agent（派发子 agent）的实现

### 4.1 现状回顾

| 模式 | 现有实现 | 特点 |
|---|---|---|
| `--func` | 起子进程，prompt 文件进、`*.out.txt` 出 | 一次任务，可并行 map |
| `--task` | 子进程常驻，`output.txt`/`reply.txt`/`_stop`/`_keyinfo` 文件协议 | 多轮接力，可中途干预 |
| Team | `assets/agent_bbs.py` 公告板 + 多 worker 抢单 | 真并发，跨进程 |

### 4.2 LangGraph 提供的对应能力

| 能力 | 用途 |
|---|---|
| **Subgraph** | 把"子 agent"做成可复用的图，父图里当节点调用 |
| **`Send` API** | 一次 fan-out 到 N 个并行子图，结果自动聚合（map-reduce） |
| **独立 `thread_id`** | 每个子 agent 独立状态与检查点，互不污染 |
| **`Store`** | 跨 thread 共享 KV（任务板、结果集） |
| **`Command(goto=...)`** | 动态路由（supervisor 模式） |
| **`interrupt()`** | 主从之间"等对方回答" |

### 4.3 推荐实现：三种派发模式

#### 模式 A：一次性子任务（替代 `--func`）

```python
def spawn_once(state: ZicatState, config):
    sub_state = {
        "messages": [HumanMessage(content=state["working"]["sub_prompt"])],
        "working": {"key_info": state["working"].get("key_info", "")},
    }
    result = sub_agent.invoke(
        sub_state,
        config={"configurable": {"thread_id": f"sub:{uuid4()}"}},  # 独立检查点
    )
    return {"messages": [AIMessage(content=result["messages"][-1].content)]}
```

要点：**显式投影**只传必要字段；独立 thread；结果只回灌一条消息。

#### 模式 B：并行 fan-out（替代 `--func` 批量 / map）

```python
from langgraph.types import Send

def fanout(state: ZicatState):
    return [Send("sub_agent", {"task": t}) for t in state["working"]["tasks"]]
```

结果通过 reducer 聚合（`Annotated[list, operator.add]`）。并发上限由 `config["max_concurrency"]` 控制。

#### 模式 C：持续协作（替代 `--task`）

两种做法，按需选：

| 做法 | 优点 | 缺点 |
|---|---|---|
| **同进程子图 + `interrupt()`** | 状态统一、可观测、无需文件协议 | 崩溃会带走主进程；长跑占资源 |
| **保留子进程 + 文件协议** | 故障隔离、可跨机器 | 状态不统一、编排靠文件轮询 |

**建议**：默认用子图 + interrupt；只有"长跑 / 需要崩溃隔离 / 跨机器"的场景仍走子进程（保留现有 `--task`）。

#### Team（多 worker 抢单）

- 任务板：`Store`（`("team", run_id)` 命名空间，key = `task/{i}`）；
- 调度：supervisor 图用 `Send` 分发给 worker 子图；
- **阶段一建议保留 BBS**：它已能跨进程工作，图化收益没有 A/B 大，先不动。

### 4.4 状态隔离与共享规则

| 维度 | 规则 |
|---|---|
| State | 子图**只接收投影**（任务描述 + 必要 working），不回传完整 messages |
| thread_id | 每个子 agent 独立；禁止与父图共用 |
| 长期事实 | 走 `Store` 或文件；不进子图 State |
| 工具集 | 子 agent 可裁剪工具（只读工具优先），降低误操作面 |
| 产物 | 写文件，消息里只留路径 |
| 成本 | 子图独立统计，汇总到父 thread 的 `meta` |

### 4.5 与现有 SOP 的关系

`memory/subagent.md` 现在教模型"用 `--func`/`--task` + 文件协议"。
图化后需要改写为：

- 派发一次性任务 → 说明"调用子图 / 由 runner 完成"，不再让模型自己起进程；
- 持续协作 → 保留子进程方案作为"重型模式"；
- 并行 → 明确"用 Send，不要自己写并发"。

> SOP 是给模型看的；改 SOP 和改代码要同步，否则模型会按旧协议乱调。

### 4.6 并发与限流

- `max_concurrency` 控制并行子图数（默认 4–8）；
- 每个子 agent 独立模型调用，注意供应商 QPS；
- 用 `with_fallbacks` 或队列降低 429 影响；
- 子图超时用 `config["configurable"]["timeout"]` + 外层看门狗。

---

## 5. 阶段与验收

| 阶段 | 内容 | 验收 |
|---|---|---|
| P0 | 依赖安装、`engine/` 骨架、hello graph | 图能编译执行 |
| P1 | `settings/llm/tools/runtime/state/graph/runner` + `--engine graph` | 3 个真实任务与 legacy 对齐（轮数/token/产物） |
| P2 | `hooks/checkpointer/callbacks` + `ask_user→interrupt` + 流式接 CLI | 中断可恢复、上下文不超限、`/cost` 正确 |
| P3 | 子图/Send 多 agent，SOP 同步 | 并行任务跑通、结果聚合正确 |
| P4 | 退役旧管线，删 `agent_loop`/`llmcore` OpenAI 部分/`core` 旧模块 | 代码量下降 2/3 |

## 6. 待决事项

1. `--task` 的"持续协作"是否必须保留进程级？（影响 P3 范围）
2. Team 是否本期图化，还是先保留 BBS？
3. 旧引擎保留多久（建议 2–3 周对照期）？
4. `llmcore` 的 Claude 代码何时删（建议 P4）？
5. 状态库单文件还是 `--task` 每任务独立 db？
