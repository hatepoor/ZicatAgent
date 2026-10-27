# memory/kb 索引

本目录集中存放 `memory/` 下的所有 SOP / 原则类 Markdown。
**文件只是可读副本，真正生效的是 SQLite 记忆库 `memory/memory.db`**；
修改文件后执行 `python -m memstore.sync` 把差异写回库（生成新版本），再用 `python -m memstore.verify` 校验。

命名规则：文件名去掉 `.md` 就是记忆库里的条目名（如 `goal_mode_sop.md` → `goal_mode_sop`）。
`index.md` 本身不参与记忆导入（见 `memstore/migrate.py` 的 `RUNTIME_ASSETS`）。

## 记忆治理

| 文件 | 作用 |
|---|---|
| `memory_management_sop.md` | **L0 META-SOP**：写记忆的公理、分层判定、容量/压缩/审计规则；代码在 `start_long_term_update` 时读取 |
| `memory_cleanup_sop.md` | 记忆清理：去重、归档、幽灵条目审计、L1 瘦身 |
| `salient_mining_sop.md` | 从 L4 历史会话中挖掘值得沉淀的事实/规律 |

## 规划与长任务

| 文件 | 作用 |
|---|---|
| `goal_mode_sop.md` | Goal 模式：单 agent 带预算持续自驱，状态写 `temp/goal_state.json` |
| `goal_team_sop.md` | Goal Team：BBS + Master + 多 worker 的协作协议 |
| `goal_team_master_duty.md` | Team Master 的职责边界：只调度/验收，不亲自干活 |
| `supervisor_sop.md` | 监察者模式：旁路检查任务质量与进度 |
| `subagent.md` | 子 agent 的调用约定与交接格式 |
| `ultraplan_sop.md` | UltraPlan：多阶段/多进程的 fan-out 执行器用法 |
| `task_planning.md` | 自主模式下的任务规划方法（配合 `autonomous_operation_sop.md`） |
| `scheduled_task_sop.md` | 定时任务/调度脚本的写法约定 |

## 自主与进化

| 文件 | 作用 |
|---|---|
| `autonomous_operation_sop.md` | 自主探索：读 TODO/历史，自选一条任务执行并写报告 |
| `distill_sop.md` | Distill：把外部项目/技能蒸馏进本仓库 |

## 工作区与协作

| 文件 | 作用 |
|---|---|
| `checklist_sop.md` | Checklist / 多 worker 任务清单协作 |

## 浏览器与前端

| 文件 | 作用 |
|---|---|
| `tmwebdriver_sop.md` | TMWebDriver 浏览器桥的使用与排障 |
| `web_setup_sop.md` | Web 工具链初始化（Chrome 扩展、端口、依赖） |
| `vue3_component_sop.md` | Vue 3 自定义组件的 JS 注入/操作约定 |

## 评审与交付

| 文件 | 作用 |
|---|---|
| `review_sop.md` | `/review` 的 in-session 对抗式评审流程 |
| `code_review_principles.md` | 好代码标准（评审时用 `memory_read` 读取） |
| `deliverable_audit_sop.md` | 交付前自检：两个常见失败模式与审计清单 |

## 不在本目录的运行时文件

| 位置 | 说明 |
|---|---|
| `memory/README.md` | 门牌：每个子目录的身份与层号映射 |
| `memory/facts.txt` | L2 事实文件（源，改后 sync） |
| `memory/l1_fallback.txt` | L1 兜底文本（正常从库动态渲染） |
| `memory/scripts/` | L3 工具脚本（`checklist_helper.py`、`keychain.py`、`autonomous_helper.py`） |
| `memory/memory.db` | 记忆库本体（运行时数据，gitignore） |
| `assets/review_inline_prompt(.en).txt` | `/review` 的内联 prompt（代码资产，不进库） |
| `memory/L4_raw_sessions/` | L4 原始会话归档（压缩工具在 `memstore/l4_compress.py`） |
| `memory/backup/`、`memory/export/` | 灾备快照（gitignore）与 L1/L2 导出镜像 |
