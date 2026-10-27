# memory/ 门牌

> 一页读懂每个子目录的身份。分层图：`assets/diagrams/memory_arch_v2.drawio`。
> L0–L4 是**库里的字段**（`memory_items.layer`），不是目录名；下表是"目录 ↔ 层"映射。

| 目录/文件 | 身份 | 层 | 谁写 | 谁读 |
|---|---|---|---|---|
| `kb/` | **源**：知识手册（.md） | L3 | 人（改后 `python -m memstore.sync` 入库） | 模型 memory_read；L1 索引动态渲染 |
| `scripts/` | **源**：工具脚本（.py，模型 import 执行） | L3 | 人（改后 sync 入库） | 模型 code_run；L1 可召回 |
| `facts.txt` | **源**：长期事实 | L2 | 人（sync 入库） | L1 索引 |
| `l1_fallback.txt` | **兜底**：L1 文本 | L1 | 人（[RULES] 段经 sync 生成 l1_rules 条目） | 库不可用时 load_L1 降级读取 |
| `memory.db` | **库本体（唯一生效源）** | — | memstore 工具链 | 引擎每轮 |
| `export/L1、L2` | **镜像**：库态 markdown 快照（可进 git、可 diff） | L1/L2 | 机器（每 24h 自动 + 手动 `memstore.export`） | 人看库演变 |
| `L4_raw_sessions/` | **运行时**：原始会话归档数据 | L4 | scheduler 每 12h | 每 7 天蒸馏任务 |
| `backup/` | **运行时**：灾备快照（gitignore） | — | scheduler 每 24h | 恢复 |

**三条铁律**：
1. 同一内容只有一个 git 源：L3 看 `kb/`+`scripts/`，L2 看 `facts.txt`——`export/` 是机器镜像**勿手改**。
2. 改任何源文件后必须 `python -m memstore.sync`（库才是生效方），定期 `memstore.verify` 查漂移。
3. 写入运行时记忆只能经 7 个 `memory_*` 工具或 memstore 工具链；版本/事件 append-only。

L3 的"手册 vs 脚本"之分：kb 是**知识**（告诉模型怎么做），scripts 是**手**（模型直接 import 执行）；两者都经 sync 进库为 L3 条目。与 `assets/` 的区别：assets 下的（sys_prompt、l1_template、review_inline_prompt）是代码资产，**不进记忆库**。
