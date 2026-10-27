# AGENT.md — zicatAgent 开发工作约定

> 面向所有在本仓库工作的 AI agent / 开发者。
> 最后更新: 2026-10-24

---

## 1. 项目是什么

**zicatAgent** 是一个本地优先、单用户的个人 Agent 执行内核：LangGraph 单引擎 + 工具层 + SQLite 长期记忆 + Web UI。
当前仓库是二次开发的主仓库（不是上游裁剪快照）。

核心组成：

| 层 | 路径 | 职责 |
|---|---|---|
| 入口 | `agentmain.py` | 进程生命周期、任务队列、运行模式、`--rpc` |
| 控制面 | `engine/` | LangGraph 状态图、检查点、模型视图、回退、回调 |
| 工具 | `tools/` + `zicat.py` + `engine/tools.py` + `assets/tools_schema*.json` | 20 个工具与 dispatch |
| 记忆 | `memstore/` + `memory/` | SQLite 记忆库、7 个 `memory_*` 工具、L1 渲染、同步/导出/备份 |
| 前端 | `core/commands.py` + `core/rpc.py` + `ui/` | 内核命令分发 + JSONL RPC + 唯一 Web UI |
| 自动化 | `reflect/` | scheduler / goal / autonomous / team worker |

---

## 2. 当前任务：二次开发四方向

本阶段的目标是改造内核，不改写产品定位。四个主攻方向：

### 2.1 Agent Loop

- **关键文件**：`engine/state.py`、`engine/graph.py`、`engine/runner.py`、`engine/hooks.py`、`engine/checkpointer.py`、`agentmain.py`
- **改什么**：节点与路由、预算/退出语义、工具循环、`ask_user` 中断、检查点、流式中断、回退。
- **约束**：`messages` / `summaries` 用 `operator.add` 只追加；新增状态字段必须明确 reducer 语义；不要绕过检查点直接改内存状态。
- **检查点治理（FIX-4 已落地）**：blob 经 `CompressedSerde` lzma 压缩（≥4KB、首字节 `0x01` 标记、旧格式直读兼容）；任务收尾按 `ckpt_retention`（默认 20）裁剪（`prune_thread` 双表删）；**有挂起 interrupt 的会话不裁**（恢复依赖历史检查点，改动删除逻辑必须保住这条）；`durability='exit'` 仅非交互路径生效，交互路径保持每步落盘（保 /rewind 粒度）。
- **上下文窗口**：引擎视图预算 = `context_char_cap`（默认 114k 字符，`graph_config` 可调），与模型真实窗口（渠道决定，当前实测 ≥700k 字符）是两回事；折叠只影响视图、存储永不删改；任务锚点不可折叠、摘要从新保留、整轮成组折叠是既有修复，勿回退。

### 2.2 Tools

- **关键文件**：`assets/tools_schema.json`（及 `_en`）、`zicat.py`（`do_*`）、`engine/tools.py`（`ToolRuntime`）、`agent_types.py`（`dispatch`/`StepOutcome`）
- **改什么**：新增/修改工具、参数与返回结构、工具执行边界、文件/代码/浏览器/记忆工具。
- **约束**：schema 只改 `assets/tools_schema.json`；新工具 = schema + `do_<name>` + dispatch 测试；`file_write`/`file_patch`/`file_apply_patch` 不得写 `memory/`，写操作限制在工作区与仓库根（`ZICAT_FILE_ROOTS` 可扩展），`.env`/`mykey.py`/`.git/` 拒绝写入；`grep`/`glob` 优先 rg，缺失时纯 Python 兜底；`code_run` 无沙箱，危险动作依赖 `ask_user`。

### 2.3 Memory

- **关键文件**：`memstore/schema.sql`、`memstore/repository.py`、`memstore/tools.py`、`memstore/{migrate,sync,export,backup,verify}.py`、`memory/kb/`
- **改什么**：记忆分层与条目、检索/索引、L1 渲染、版本/事件、SOP 文档、迁移与备份。
- **约束**：`memory_versions` / `memory_events` 只 insert（触发器拒绝改删）；`memory_items` 只更新当前指针；写入必须经 `MemoryStore` 或 7 个 `memory_*` 工具；不要直接改 `memory/*.md`（会被拦截），改 `memory/kb/*.md` 后必须 `memstore.sync`。

### 2.4 Context

- **关键文件**：`engine/hooks.py`（`build_model_messages`）、`engine/graph.py`（视图/轮末）、`engine/state.py`（`working`/`summaries`）、`assets/sys_prompt*.txt`、`assets/l1_structure*.txt`
- **改什么**：工作记忆重锚、字符预算折叠、摘要链、L1 刷新、周期提醒、提示词结构。
- **约束**：折叠只影响发给模型的视图，**存储层永不删改**；摘要也是追加的新消息；不要用 `add_messages` 之类会按 id 替换的 reducer。

---

## 3. 不可破坏的约定

1. **消息只追加**：新的消息内容永远追加在末尾，不允许删除、替换或破坏已有前缀。
2. **记忆版本只追加**：版本/事件是审计记录；需要修正就写新版本，不改历史。
3. **状态与记忆分库**：`temp/graph.db`（会话状态，高频写）与 `memory/memory.db`（长期记忆，低频写）物理隔离。
4. **模型不能直接写状态**：状态只由引擎写；记忆只能经记忆工具写，且必须留痕。
5. **模型接口**：仅 OpenAI 兼容；配置优先读 `.env`（`ZICAT_OAI_<n>__<FIELD>`，见 `.env.example`），无 `.env` 回退 `mykey.py`；不引入多厂商 SDK。`.env` / `mykey.py` 均不入库。
6. **本地单用户**：不做多租户、并发任务、后台服务；不要为未存在的需求加抽象。
7. **前端唯一**：只保留 `ui/` Web 前端；它通过 Node 桥 / JSONL RPC 与内核交互，不共享内存状态。

---

## 4. 文档事实源

优先读、优先改：

| 文档 | 用途 |
|---|---|
| `docx/index.md` | 项目概述、路线图、全局规范 |
| `docx/arch/v1/index.md` + `modules.md` + `data.md` | 当前架构事实源 |
| `docx/dev/v0.1.0/todolist.md` | 当前版本进度与任务 |
| `docx/explain/v0.1.0/` | 本版相对上一版的变更 |
| `memory/kb/index.md` | SOP 文档索引（记忆库同步源） |
| `docx/guide/` | 项目导读层：介绍、原理讲解、历史迁移评估（讲解看这里，事实看 arch） |

改动行为/契约时：

1. 先看 `docx/arch/v1/modules.md` 是否已有对应契约；
2. 在 `docx/dev/v0.1.0/` 对应模块的 task 里登记（状态 → 🔧/✅）；
3. 契约变化同步 `arch` + `explain`；
4. 记忆 SOP 变化同步 `memory/kb/` 并 `python -m memstore.sync`。

---

## 5. 关键目录地图

```text
agentmain.py         入口：模式路由 / 任务队列 / --rpc
agent_types.py       StepOutcome / BaseHandler.dispatch / 公共类型
zicat.py             兼容壳：handler 状态所有权 + dispatch 委托 + 公共 API（工具实现已迁 tools/）
tools/               工具域：registry 装配 + code/files/browser/memory/session_ctl 六子包
engine/              LangGraph：state/graph/runner/hooks/tools/checkpointer/rewind/callbacks
core/                内核命令、RPC、rewind 存储、review、modes
memstore/            SQLite 记忆库：schema/repository/tools/migrate/sync/export/backup/verify
ui/                  唯一前端：React/Vite/Tailwind + Node 桥（server.mjs，SSE+POST）
reflect/             scheduler / goal / autonomous / team worker
assets/              系统提示词、工具 schema、浏览器扩展、diagrams/（drawio 架构图）
memory/              运行时记忆：kb/（SOP）、global_mem*.txt、memory.db、export/、backup/
docx/                开发文档四层（guide 导读 / arch 事实 / dev 目标 / explain 差异）
tests/               单测 + 进程级集成
temp/                运行时工作区（gitignore；含长上下文测试驱动/探针脚本）
.env(.example)       模型配置（ZICAT_OAI_n__FIELD，见 §3-5）；.env 不入库
```

---

## 6. 开发流程

### 6.1 开发模式（由用户声明）

| 模式 | 含义 |
|------|------|
| **自动模式** | 所有代码由助手直接编写并验证，无需逐步过问 |
| **批阅模式** | 先给出代码供用户审阅，用户同意后再写入文件；期间用户可能对代码提问 |
| **教学模式** | 给出代码与讲解，由用户亲手编写；助手负责测试代码与验证 |

- 用户没有指明模式时，默认为**教学模式**。
- 无论当前处于何种模式，用户声明「**你来写**」时，该轮代码由助手直接编写。
- **每次更改完成后，必须提及 git 本地仓库状态**（未提交的改动等），提醒用户是否需要提交。

### 6.2 常规流程

1. 读 `docx/dev/todolist.md` 与对应模块 `develop.md` / `taskN.md`，确认当前任务。
2. 小步修改：一次只动一个方向（loop / tools / memory / context），避免跨模块大改。
3. 写/改测试，先跑窄测试再跑全量：

```powershell
python -X utf8 -m unittest tests.test_engine tests.test_integration
python -X utf8 -m memstore.verify
```

4. 需要真实模型验证时，用 `--func` 跑一个最小任务（不要在测试里依赖真实 API）。
5. 更新 `docx` 对应 task 状态与进度日志；有契约变化再更新 arch/explain。
6. 提交前检查：

```powershell
python -X utf8 -m compileall -q agentmain.py agent_types.py mykey_loader.py zicat.py core engine memstore tests reflect
git diff --check
git status --short
```

7. 提交信息用英文 `type(scope): summary`，正文可中文；不要提交 `mykey.py`、`temp/`、`memory.db`。

---

## 7. 代码风格

- 注释与文档用中文；标识符用英文。
- Python 3.10–3.13；文件 LF；入口统一 `python -X utf8`。
- 不新增依赖，除非确实需要并同步 `pyproject.toml` / README / docx。
- 错误要显式返回或抛出，不做静默兜底；工具结果统一 JSON 序列化。
- 保持模块边界：`cli` 不碰引擎内部，`tools` 不直接写记忆版本，`engine` 不直接写记忆文件。
- 删除功能时连同 schema、测试、文档、SOP 一起删，不留半死代码。

---

## 8. 当前版本状态

- **v0.1.0（v1 架构）**：01–05 模块已完成；`06-质量与工程` 仅剩 `task5 真实烘跑与版本验收`——**最小烘跑已通过**（--func / TUI 真实工具任务 / interrupt+abort，渠道 deepseek-v4.1-flash），完整验收（长任务/记忆写入/rewind/多模型故障转移）待做。
- **v0.1.1（进行中）**：① `01-TUI前端` ✅ 全部完成（真实任务验收通过）；② `02-Loop修复` FIX-1~4 全部 ✅（resume 工作记忆回填 / `.env`+dotenv 配置 / 中断 final_text 置空 / checkpoint 压缩+retention）；③ 长上下文专项：30k 窗口 222% 压力复测三项指标全绿、1M 窗口 71.3% 五轮实测（5 项 finding 已修）；④ prompt 优化（zizicat 名称/`<summary>` 独立条/工作记忆条）、agent_loop 架构图（`assets/diagrams/`）。
- **下一步**：v0.1.1 收尾（arch/explain 同步 → 版本指针）；v0.1.0 task5 完整验收后版本收尾；再进入 v0.2.0「自有 Agent 层」。
- **已知边界**：
  - `code_run` 无沙箱（本地沙箱方案已调研：skilllite 暂不可用，审计钩子护栏方案待立项）；
  - 预算远小于任务需求时折叠可能诱发重复读循环（MINI 极端参数下观察到，边界情形已记录）；
  - 交互长会话 checkpoint 写放大仍在（retention+压缩已治磁盘，写带宽按步落盘保留）；
  - 记忆库有 1 条旧品牌历史版本（append-only 审计，不能改删）；
  - Git 历史与仓库目录名仍可能保留旧名，未做历史重写。

---

## 9. TUI 设计参考

`ui/` 是**生产 Web TUI**（v0.1.1 落地）：React 19 + Vite 7 + Tailwind 4，`ui/server.mjs` 桥（仅 Node 内置模块）spawn `--rpc` 内核，SSE 下行 + `POST /send` 上行。运行：

```powershell
cd ui; npm install; npm run build
node ui/server.mjs   # → http://127.0.0.1:8765
```

历史沿革：早期视觉设计 mock `terminal-zizicat-tui/` 已毕业为 `ui/` 并删除（组件/主题复用，历史在 git ≤ 2026-10-25）；事件协议见 `core/rpc.py` docstring 与 `docx/arch/v1/modules.md`。

---

## 10. 安全与边界

- `code_run` 以当前用户权限执行任意代码；`inline_eval` 在进程内 eval。
- 不读取/移动 `mykey.py`、`.env` 等密钥文件；日志与提交里不得出现 key。
- 浏览器工具依赖本机 Chrome 扩展，不要假设 headless 环境可用。
- 任何不可逆操作（删除、覆盖、推送、安装）先向用户确认。
