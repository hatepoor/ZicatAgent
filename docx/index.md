# zicatAgent 开发文档

> 最后更新: 2026-10-23
> 当前开发版本: v0.1.0
> 当前架构版本: v1

---

## 一、项目概述

### 1.1 项目名称

**zicatAgent** — 一个本地优先、可自演进的个人 Agent 执行内核。

### 1.2 核心目的

zicatAgent 不是一个"平台"，而是一个能自己长本事的执行内核：一个 LangGraph 循环 + 一套工具 + 一套 SQLite 长期记忆 + 一套把经验沉淀成 SOP/脚本的机制。它解决的是"通用 Agent 每次都要重新教"的问题——把任务经验外置成记忆库，靠极简索引在后续任务中召回，让能力随使用生长。

本版把引擎统一到 **LangGraph + SQLite 检查点**（会话状态可持久化、可跨进程恢复），把长期记忆统一到 **SQLite 单库**（版本与事件 append-only）。目标是得到一个干净、可测试、可继续定制的最小内核。

### 1.3 目标用户

- **本人（主要）**: 本地单人使用，按自己的习惯定制人格、工具、记忆与工作流。
- **二次开发者**: 想基于一个可运行的最小 Agent 内核做二次开发的人。
- **自动化使用者**: 用 `--task` / `--func` / `--reflect` / `--rpc` 把 Agent 嵌入脚本或定时任务的人。

---

## 二、版本路线图

| 版本 | 目标 | 状态 | 对应架构版本 | 开发文档 |
|------|------|------|--------------|----------|
| v0.1.0 | 内核基线：LangGraph 单引擎、SQLite 记忆、16 工具、双 CLI、文档体系 | 🔧 | v1 | [dev/v0.1.0](./dev/v0.1.0/todolist.md) |
| v0.2.0 | 自有 Agent 层：人格/策略/知识域定制，工具扩展框架，评估基线 | ⬜ | v1 | 待建 |
| v0.3.0 | 多 Agent 与长任务：子图/任务编排、Team 工程化、沙箱 | ⬜ | v2（待评估） | 待建 |

> v0.1.0 的代码已基本落地，剩余两项工程化任务（打包声明、真实烘跑）见 [dev/v0.1.0/todolist.md](./dev/v0.1.0/todolist.md)。

---

## 三、全局开发规范

### 3.1 技术栈

| 类别 | 技术选型 | 版本 | 备注 |
|------|----------|------|------|
| 语言 | Python | 3.10–3.13（开发用 3.12） | 主实现 |
| 引擎 | LangGraph + LangChain Core | `langgraph>=0.6`、`langchain-core>=0.3` | 单引擎，legacy 已删除 |
| 模型接入 | `langchain-openai` | `>=0.3` | 仅 OpenAI 兼容接口 |
| 会话状态 | SQLite + `langgraph-checkpoint-sqlite` | `>=2.0` | `session/graph.db` |
| 长期记忆 | SQLite（自研 `memstore`） | 标准库 `sqlite3` | `memory/memory.db` |
| 前端 | Web UI（React + Vite + Tailwind） | Node 23+ | 唯一前端；Node 桥接 JSONL RPC |
| 测试 | `unittest` | 标准库 | 单测 + 进程级集成 |
| 文档 | Markdown + 单文件 HTML | — | `docx/`（guide/dev/explain/arch） |

### 3.2 目录结构约定

```text
zicatAgent/
├── agentmain.py            # 内核入口：--rpc（Web UI）/ --task / --func / --reflect
├── agent_types.py          # StepOutcome、BaseHandler.dispatch、公共类型
├── mykey_loader.py         # mykey.py 配置加载
├── zicat.py                   # 工具实现（do_*）与工作记忆
├── simphtml.py / TMWebDriver.py  # 浏览器能力
├── engine/                 # LangGraph 控制面（state/graph/runner/hooks/...）
├── core/                   # 内核：commands、RPC、rewind、review、modes
├── memstore/               # SQLite 记忆库（schema/repository/tools/sync/...）
├── reflect/                # 无人值守：scheduler / goal / team worker
├── assets/                 # 提示词、工具 schema、浏览器扩展
├── memory/                 # 运行时记忆：kb/（SOP）、*.txt、sqlite、导出/备份
├── docx/                   # 开发文档四层（本目录：guide / dev / explain / arch）
├── tests/                  # 单测与集成测试
└── temp/                   # 运行时工作区（gitignore）
```

### 3.3 命名约定

- **Python 文件/模块**: `snake_case`
- **Python 类**: `PascalCase`
- **Python 函数/变量**: `snake_case`
- **常量**: `UPPER_SNAKE_CASE`
- **TypeScript**: 函数/变量 `camelCase`，类型 `PascalCase`，文件 `kebab-case` 或 `zicat.ts`
- **记忆条目名**: 去掉 `.md` 的 SOP 文件名，如 `memory/kb/goal_mode_sop.md` → `goal_mode_sop`
- **SQLite 表**: `snake_case`，复数（`memory_items`、`memory_versions`）

### 3.4 代码风格

- 注释与文档用中文；代码标识符用英文。
- 会话消息**只追加**：`messages` 用 `operator.add`，禁止删除/替换/破坏前缀；需要压缩时追加新消息或摘要。
- 记忆版本只追加：`memory_versions` / `memory_events` 只 insert，`memory_items` 只更新当前指针。
- 不引入未使用依赖；删除功能时连同 schema、文档、测试一起删。
- 新增/修改行为必须有测试；不能只靠"跑一次看看"。
- 文件写入统一 LF；PowerShell 环境用 `python -X utf8` 运行。
- 禁止模型直接改 `memory/*.md`：记忆只能经 `memory_*` 工具写；`file_write`/`file_patch` 在 `memory/` 下会被拦截。

### 3.5 模块间通信约定

- `cli` → `runtime`：通过 `agent.put_task()` / RPC；不直接调用引擎内部节点。
- `runtime` → `engine`：`run_graph_task()` / `resume_pending()`；运行时对象（handler/runtime）不进 State。
- `engine` → `tools`：`ToolRuntime.run_tool()`；工具结果统一转成 `ToolMessage` 追加。
- `engine`/`tools` → `memory`：只经 `MemoryStore` 或 7 个 `memory_*` 工具；不直接写文件。
- `ops` → `runtime`：`--reflect` 脚本通过 `check()` 返回任务字符串，由入口投递。
- 禁止跨模块写对方的数据文件；状态由引擎写，记忆由记忆库写。

---

## 四、文档体系规则

### 4.1 目录职责

| 目录 | 回答的问题 | 文档性质 |
|------|------------|----------|
| `docx/guide/` | 这个项目怎么理解、为什么这样设计 | 导读层：项目介绍、原理讲解、历史迁移评估与裁剪记录 |
| `docx/dev/` | 这一版要做什么 | 目标态、版本计划 |
| `docx/explain/` | 这一版相对上一版变了什么 | 差异态、变更说明 |
| `docx/arch/` | 系统现在是什么样 | 事实态、架构快照 |

- `arch` 是事实源：模块边界、对外契约、依赖关系只在这里定义一次。
- `guide` 是导读层：只在与代码脱节时更新；新的开发事实写入 arch/dev/explain，不写 guide。
- `dev` 只引用 arch 的契约，不复制契约正文。
- `explain` 只写相对上一版的变化。
- `arch/vN/architecture.html` 是视图，冲突时以 markdown 为准。

### 4.2 版本指针规则

`docx/dev/todolist.md` 与 `docx/explain/todolist.md` 都只保留一行：

```text
当前: 正在开发 v0.1.0 版本，状态为 1（开发中）
```

- 状态：`0`（未开始）、`1`（开发中）、`-1`（已结束）。
- 版本开发完毕：**先把状态改为 -1，再清空文件内容**，顺序不能反。
- 清空后文件为空；下个版本开始时再写入新的一行。
- 出现两个及以上版本号时：立即询问用户当前在开发哪个版本，并删除另一个。
- `dev/todolist.md` 是主指针；`explain/todolist.md` 镜像同一状态。

### 4.3 dev/ 版本内结构

```text
dev/vX.Y.Z/
├── todolist.md          # 本版所有模块的进度
├── 01-{模块名}/
│   ├── develop.md       # 做什么 + 规范 + 依赖契约
│   ├── task1.md
│   ├── task2.md
│   └── todolist.md      # 本模块 task 进度
└── 02-{模块名}/
    └── ...
```

- 模块编号即开发顺序与依赖链：`02` 依赖 `01`。
- `develop.md` 头部写 `对应架构版本: vN`。
- `develop.md` 只写"做什么"和"规范"，"怎么做"归 `task.md`。

### 4.4 explain/ 版本内结构

```text
explain/vX.Y.Z/
├── update/              # up_{主题}.md
├── modify/              # md_{主题}.md
├── del/                 # del_{主题}.md
└── optimize/            # opt_{主题}.md
```

- 内容对比上一个版本；第一个版本不做对比，只写"本版建立了什么"。
- 一个变化一个文件。

### 4.5 arch/ 架构版本规则

```text
arch/
├── index.md             # 版本索引 + 当前指针 + 升级规则
├── changelog.md         # 全局架构变更日志
├── decisions.md         # 全局 ADR
├── v1/
│   ├── index.md
│   ├── modules.md
│   ├── data.md
│   └── architecture.html
└── vN/
    └── ...
```

- 架构版本用整数 `v1`、`v2`，不与开发版本号对齐。
- 状态：`草案`（正在实现）、`生效`（代码已符合）、`已归档`（被取代，永久只读）。
- 同一时间最多一个 `生效`、一个 `草案`。
- 升级条件：模块拓扑变化、契约破坏性变更、技术选型替换、数据模型结构性重构、非功能基线变化。
- 不算升级：新增字段、不破坏旧契约的新接口、内部重构、性能优化、bug 修复、单个功能新增。
- 升级时整代复制，旧版冻结；版本内小变化原地更新 + changelog 记一条。

### 4.6 版本收尾顺序

1. 校验所有模块 `✅`
2. 更新 arch（升级或原地修订）
3. 写 `explain/vX.Y.Z/` 四类变更文档
4. 更新 `arch/index.md` 与本文档的版本路线图
5. `dev/todolist.md` 置 `-1` 后清空；`explain/todolist.md` 同步
6. 同步 `architecture.html`

顺序不能调换。

### 4.7 阅读路径

- 了解项目全貌：`docx/index.md`
- 理解项目与原理（第一次接触）：`guide/README.md` → `guide/00-总览/` → 各模块 `00-*` 总览
- 了解当前架构：`arch/index.md` → `arch/v1/index.md` → `modules.md` → `data.md` → `architecture.html`
- 了解当前开发内容：`dev/todolist.md` → `dev/v0.1.0/todolist.md` → 模块 `develop.md` → `taskN.md`
- 了解某版变化：`explain/v0.1.0/` 四个分类目录

---

## 五、设计原则

| 决策项 | 选项 | 最终选择 | 原因 |
|--------|------|----------|------|
| 引擎架构 | 自研循环 / LangGraph | **LangGraph 单引擎** | 检查点、interrupt/resume、状态投影由框架提供，legacy 已删除 |
| 会话状态 | 文件 / SQLite | **SQLite `session/graph.db`** | 高频写、可跨进程恢复、WAL |
| 长期记忆 | 文件 / SQLite | **SQLite `memory/memory.db`** | 版本/事件可审计、FTS 检索、append-only 触发器 |
| 消息策略 | 原地压缩 / 只追加 | **只追加 + 视图折叠** | 硬性要求：不破坏前缀；存储永不删改 |
| 模型接入 | 多厂商 / 仅 OpenAI | **仅 OpenAI 兼容接口** | 简化依赖与配置，本地可替换 base_url |
| 前端 | GUI / Web / CLI | **Web UI** | 唯一前端；React 原子组件 + Node 桥接 JSONL RPC |
| 多 Agent | 暂不做 / 内置 | **暂不做**（v0.3.0 再评估） | 先保证单 Agent 可验证，避免过早引入复杂度 |
| 部署 | 容器 / 本地 | **本地单用户** | 个人使用、文件与浏览器工具依赖本机环境 |
