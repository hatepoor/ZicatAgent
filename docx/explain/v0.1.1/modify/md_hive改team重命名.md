# md · Goal Hive 全局更名为 Goal Team

> 版本: v0.1.1 · 类型: modify · 日期: 2026-10-24

## 变了什么

用户决策：`hive` 术语易混淆，全局更名为 `team`（"租了个 team"语义）。

| 旧 | 新 |
|---|---|
| `/hive` 命令 | `/team`（`core/modes.py`、`core/commands.py`、`cli/zicat.ts`、help 文本） |
| `goal_hive_sop.md` / `goal_hive_master_duty.md` | `goal_team_sop.md` / `goal_team_master_duty.md`（git mv） |
| 记忆库条目名 + title | 同步改名（`memory_events` 留 rename 审计事件，版本链按 item_id 不受影响） |
| `build_hive_prompt` | `build_team_prompt` |
| `hive_<短名>` 工作目录 / `hive-worker-N` | `team_<短名>` / `team-worker-N`（SOP 文本） |
| L1 模板 / kb/index / morphling_sop 交叉引用 | 全部替换 |
| docx 全层（arch/dev/explain/guide）+ README + AGENT | 全部替换（历史文档同步，避免与代码术语脱节） |

## 技术要点

- **"hive" 是 "archive" 的子串**：替换必须用词边界/精确模式序列（`goal_hive_*` → `Goal Hive` → `/hive` → `\bhive\b`），裸替换会破坏 `memory_archive`。终检确认 `memory_archive` 完好。
- 记忆库 rename 走 `UPDATE memory_items.name/title`（元数据级）+ `memory_events` 留痕；`memstore.sync/export/verify` 全链路通过（140 项 0 失败）；manifest 的 name/source/三个 hash 同步重算。
- BBS 概念与 `agent_team_worker.py`（本就叫 team）不变。

## 兼容性

旧命令 `/hive` 移除（不留别名）。旧 SOP 条目名经 memory_search 检索 "team" 可命中新条目。
