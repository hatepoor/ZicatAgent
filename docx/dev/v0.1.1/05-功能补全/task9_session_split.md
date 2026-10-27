# task9 · 会话/工作区分离 FIX-S（方案定稿）

> 状态: ✅ 已执行并验证 · 实际 1 天
> 设计定稿（已确认）: session/ 单库+注册表 · 标题=首轮 summary 前 10 字（查重加序号）· 先 ID 后改名 · `/new` 显式开新会话 · `/resume` 按标题（前缀模糊，多命中列候选）· checkpoint 读写路径零改动

## 一、目标结构

```text
zicatAgent/
├── session/                      ★ 新增（gitignore）
│   ├── graph.db                  ← 从 temp/ 迁入（checkpoints/writes + 新表 session_meta）
│   └── （会话域数据全在此）
├── temp/                         工作区（可由 --workspace / graph_config.workspace 指定，默认 temp/）
│   ├── 调研27年秋招/             ★ 会话产物目录（首轮后由 cli-xxxxx 改名而来）
│   ├── model_responses/          滚动日志（12h 归档后清走，留 temp 可接受）
│   └── （goal_state/team_*/sandbox 等现有机制不动）
```

**语义**：会话内容（checkpoint）住 `session/`，会话产物（文件/脚本/报告）住工作区的会话目录；`temp/` 恢复"可随时清理"语义（清空不丢会话，最多丢 12h 内未归档日志）。

## 二、注册表（session_meta 表，建在 graph.db）

```sql
CREATE TABLE IF NOT EXISTS session_meta (
    thread_id     TEXT PRIMARY KEY,   -- LangGraph 真主键（cli-...），加载/删除的最终依据
    title         TEXT UNIQUE,        -- 人话标题；注册时查重，重名自动 _2/_3
    workspace_dir TEXT,               -- 绝对路径；首任务期间为 ID 目录，得标题后 rename
    created_at    TEXT,
    updated_at    TEXT,
    status        TEXT DEFAULT 'open' -- open/done/archived（/del 软删）
);
```

## 三、新模块 `core/sessions.py`（会话注册/查找/删除，全部纯函数式）

| 函数 | 职责 |
|---|---|
| `ensure_table(conn)` | 建表（幂等）；graph.db 不存在时先建库 |
| `register(thread_id, workspace_root)` | 新会话登记：title=NULL，建 `workspace_root/<thread_id 短码>/` 目录 |
| `set_title(thread_id, title)` | 查重加序号 → UPDATE title → **os.rename 工作目录** → 返回最终标题 |
| `find(text)` | 精确→前缀匹配；唯一命中返回记录，多命中返回候选列表（含时间） |
| `list_sessions(limit)` | 标题/时间/目录，updated_at 倒序 |
| `delete(thread_id)` | 删 session_meta 行 + checkpoints/writes 该 thread 全部行（复用 prune 双表删法） |

## 四、改动点（按文件）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `engine/settings.py` | DEFAULTS：`checkpointer` → `ROOT/session/graph.db`；新增 `workspace`（默认 `ROOT/temp`） |
| 2 | `.gitignore` | + `session/` |
| 3 | `agentmain.py` | ① 启动时 `sessions.ensure_table`；② `run()` 任务收尾：该 thread 无 title 且 summaries 非空 → `set_title(取 summary 前 10 字)`（从 get_state 取，不加模型调用）；③ handler 构造的 cwd 改为"该 thread 的 workspace_dir（meta 查，无则建 ID 目录）" |
| 4 | `core/commands.py` + HELP | ① `/new [一句话]`：生成新 thread_id + register，下个任务即新会话（带一句话则直接作标题候选）；② `/threads`：改列 `session_meta`（标题+时间+目录；旧无 meta 的 thread 显示短码+"(未命名)"）；③ `/resume <标题\|前缀>`：find → 唯一→设 agent.graph_thread_id；多命中→列候选；④ `/del <标题>`：delete + 产物目录是否删单独确认 |
| 5 | `engine/runner.py` | resume_pending 的回填逻辑不动；`_build` 的 checkpointer 路径来自 settings（自动跟随 #1） |
| 6 | `core/rpc.py` | `ready` 事件附 `current_session`（标题）；`/threads` 等命令输出走既有 slash 透传，**TUI 零改动**（/new 按钮/会话下拉留后续迭代） |
| 7 | `reflect/scheduler.py` | 零改动（model_responses 留 temp） |
| 8 | 一次性迁移 | `mv temp/graph.db* session/`（当前库近空，直接搬）；旧 thread 不补 meta |

## 五、关键流程（改造后）

```text
/new            → 新 thread cli-xx + register + 工作区建目录 temp/cli-xx/
首任务对话      → 模型输出 <summary>调研27年秋招岗位...</summary>
任务收尾        → set_title("调研27年秋招")（查重）→ rename temp/cli-xx → temp/调研27年秋招
/threads        → 标题列表（人话）
/resume 调研27  → find 前缀唯一命中 → thread_id → 现有 attach 机制续跑（cwd 自动指回其目录）
/del 调研27     → 删 3 处行 → 问：产物目录也删？[y/N]
清空 temp/      → 会话不受影响（checkpoint 在 session/）
```

## 六、边界与取舍

- **标题来源**：首任务结束才命名（期间目录是 ID 短码）——避免为起名多一次模型调用；`/new 带一句话`时直接预置标题候选
- **`--task` 常驻子代理**：本就有 task_dir，不受影响（不注册 meta，保持原样）
- **同 thread 连续多任务**：现状特性（上下文延续）不变，产物继续落同会话目录
- **model_responses 留 temp**：它是滚动待归档队列（12h 清）非永久数据；清理 temp 最多丢 12h 日志，可接受
- **并发**：单用户单进程，meta 无锁竞争；TUI/CLI 同库读写走既有 busy_timeout

## 七、外部工作区支持（跨盘，如 D:\）

- **必修坑**：sys_prompt/L1 结构里的项目内相对路径提示（`../memory`、`./temp`）在 cwd 移出项目后失配 → `get_global_memory()` 改为运行时注入绝对路径（workspace 与 memory//assets 各自绝对路径）
- **防护**：`register()` 校验工作区存在/可写，建目录失败明确报错
- **沙箱对齐**：未来 sandbox/ 交换区挂 workspace 下（不写死 temp/）
- 已核实无碍：memory/ 写保护按绝对前缀判断；rewind/code_run 跟随 cwd 跨盘正常；session/、L4 日志留项目内

## 八、验收

- [ ] 单测：sessions 模块（注册/标题查重序号/rename 同步/前缀查找多命中候选/删除三表清理）
- [ ] 冒烟：`/new` → 首任务 → 目录自动改名为标题；`/threads` 出人话列表；`/resume 前缀` 续跑且 cwd 正确；`/del` 全清
- [ ] 迁移：graph.db 在 session/ 生效，旧路径无残留引用
- [ ] 清空 temp/ 后会话可恢复（证明分离彻底）
- [ ] 外部工作区（跨盘路径）冒烟：工具落位正确、提示词路径有效
- [ ] 全量测试 + docx 登记（AGENT/README 目录地图、explain modify）
