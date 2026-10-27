# Loop 修复批次清单（fixes）

> 版本: v0.1.1 · 模块: 02-Loop修复
> 状态图例: ⬜ 待确认 / 🔧 修复中 / ✅ 已修复并验证 / ❌ 不修复
> 最后更新: 2026-10-24
> 本文档是修复批次的审阅入口：用户确认条目后按条目执行，执行完更新状态并补 develop/task 登记。

## 修复条目总览

| ID | 标题 | 严重度 | 状态 | 工作量 |
|----|------|--------|------|--------|
| [FIX-1](#fix-1--跨进程-resume-丢工作记忆) | 跨进程 resume 丢工作记忆（空副本覆盖 checkpoint） | P0 | ✅ 已修复并验证 | 实际 ~10 分钟 |
| [FIX-2](#fix-2--私密配置迁移-env--dotenv) | 私密配置迁移 .env + dotenv（API key/baseurl/model 移出 mykey.py） | 增强 | ✅ 已修复并验证（待用户填真实 .env 后终验） | 实际 ~30 分钟 |
| [FIX-3](#fix-3--中断后-finaltext-返回旧任务文本) | 中断后 final_text 返回历史轮次旧文本 | 低 | ✅ 已修复并验证（真实测试发现） | 实际 ~15 分钟 |

---

## FIX-1 · 跨进程 resume 丢工作记忆

### 现象（用户视角）

任务在 `ask_user` 处挂起后进程退出（或 TUI 桥重启），`/resume <thread_id>` 恢复执行后，模型"失忆"——它之前通过 `update_working_checkpoint` 记录的工作记忆（任务要点、结论、中间状态）全部消失，后续轮次的视图里不再有 `[WORKING MEMORY]` 重锚块，直到模型碰巧重新调用一次该工具。

**不受影响的部分**：对话历史 `messages` 完整无损（只有数据库一份，无覆盖机制）；同进程内继续对话的正常路径也不受影响（agentmain 有 handler 继承逻辑）。

### 根因（代码证据）

系统里有两份工作记忆：

| 副本 | 位置 | 生命周期 |
|------|------|----------|
| A | checkpoint 里的 `state.working`（`temp/graph.db`） | 持久化，跨进程存活 |
| B | `handler.working`（进程内 Python 对象属性） | 进程退出即消失 |

数据流是单向同步：**B → A**。链条：

1. `engine/runner.py:60-75`：`_build_context` 为 resume 构造**全新 handler**，`working = {}`（副本 B 为空；旧进程的 handler 对象已不存在）
2. `engine/graph.py:98,142`：human/tools 节点每轮执行完做 `update["working"] = dict(handler.working)`，把副本 B **覆盖式**回写进 state（`engine/state.py:16` 的 `working: dict` 无 reducer，整体替换语义）
3. 恢复执行的第一个节点（human_node 处理 ask_user 回答）就触发回写 → 副本 A 被**空 dict 抹掉**
4. 后续每轮 `build_model_messages` 读 `working["key_info"]` 为空 → 模型失忆

即：恢复时只做了 state→运行时的"读取"（拿 interrupts），没做 state→运行时的"回填"，空副本反向覆盖了持久化数据。

### 修法

在 `resume_pending`（`engine/runner.py`）中回填，复用已有的 `graph.get_state(config)`（原本只取 interrupts）：

```python
snapshot = graph.get_state(config)          # 已存在
pending = list(getattr(snapshot, "interrupts", ()) or ())
# ↓ 新增：从 checkpoint 回填工作记忆，避免空 handler.working 反向覆盖
saved_working = (snapshot.values or {}).get("working") or {}
if saved_working:
    handler.working = dict(saved_working)
```

**方案取舍**：备选是改 human/tools 节点为 merge 语义而非覆盖——不采纳：改动面大、影响正常路径语义，且违反"只改必要"；回填只动 resume 一条路径，一行级改动。

**不碰的东西**：`working` 覆盖语义、state 结构、消息只追加约定、正常路径（非 resume）行为。

### 验收标准

- [ ] 新增单测：构造「已挂起 + working 有内容」的检查点 → 新 runtime 执行 resume → 断言恢复执行后 `state.working` 的 key_info 仍在、`handler.working` 已回填（修复前该测试可复现丢失）
- [ ] 全量测试通过（当前基线 42 tests OK）
- [ ] docx 登记（本文件状态翻 ✅ + todolist 进度日志）

### 工作量

约 15 分钟（含回归测试）。

---

## FIX-2 · 私密配置迁移 .env + dotenv

### 动机（用户视角）

API key、baseurl、model 等私密配置目前硬编码在 `mykey.py`（Python 源文件）。迁移到标准 `.env` 文件，由 `python-dotenv` 加载、`mykey_loader.py` 统一组装——配置与代码彻底分离，且符合通用运维习惯。

### 设计

**`.env` 键约定**（双下划线分层：`ZICAT_OAI_<序号>__<字段>`，字段名 = mykey.py 模型字典的小写键）：

```env
ZICAT_OAI_1__APIBASE=https://api.deepseek.com/v1
ZICAT_OAI_1__APIKEY=sk-xxx
ZICAT_OAI_1__MODEL=deepseek-chat
# 可选：NAME / PROXY / MAX_TOKENS / TEMPERATURE / API_MODE / READ_TIMEOUT ...
# 多模型：ZICAT_OAI_2__APIKEY=... （故障转移按序号）
```

**加载逻辑**（改 `mykey_loader.py`，对外接口 `mykeys_store`/`reload_mykeys` 不变）：

1. `.env` 存在 → `load_dotenv(override=True)` → 正则抓取 `ZICAT_OAI_<n>__<FIELD>` 组装为 `oai_config_<n>` dict（字段名转小写；数值尽力 int/float 转换，失败留字符串）
2. **合并语义**：`.env` 的模型组存在时**覆盖** mykey.py 的 `oai_config*`；mykey.py 仍可提供 `mixin_config`、聊天平台 token、`graph_config` 等非模型配置（不填 mykey.py 也可纯 `.env` 运行）
3. 优先级：`.env` > mykey.py > mykey.json（原路径保留，向后兼容）
4. 热重载保留：`.env` 的 mtime 纳入 reload 检查

**引擎层零改动**：`engine/settings.oai_configs()` 按"变量名含 oai_config"匹配（settings.py:20-33），组装出的 `oai_config_<n>` 自然命中。

### 改动清单

- [ ] `mykey_loader.py`：新增 `_dotenv_data()`；`MyKeys._load` 加 .env 优先分支（含合并与 race 校验）
- [ ] `.env.example`：入库模板（不含真实值）
- [ ] `.gitignore`：加 `.env`
- [ ] `pyproject.toml`：新增依赖 `python-dotenv`（按规范同步声明）
- [ ] 单测：.env 组装正确性（分组/小写字段/int 转换/多模型）、无 .env 回退原路径
- [ ] README / AGENT.md / docx 同步

### 验收标准

- [ ] 单测通过 + 全量测试不破
- [ ] 用户动作：`copy .env.example .env` 填入真实 key（维护者自己迁移，loader 不读取 mykey.py 内容）后，`python agentmain.py --func` 冒烟可用

### 工作量

约 30–40 分钟（含测试与文档同步）。

---

## 后续条目（占位）

用户确认后可在此追加。上轮 Agent Loop 方案评审中其余候选——P0#2 流式中断半截 tool_calls、P1 `_turn_end` 吞异常 / 摘要兜底 / 软预算——**均未纳入本批次**，如需加入请说明。

---

## FIX-3 · 中断后 final_text 返回旧任务文本

### 现象（真实测试发现）

任务在 `ask_user` 挂起后发 abort：RPC `done` 事件的 `text` 是**上一个任务**的最终汇报（斐波那契结果），而非空或中断说明。`--task` 模式同样会把旧任务文本写进 `output.txt`。

### 根因

`run_graph_task` 收尾时 `_final_text` 从 checkpoint 取"最后一条无工具调用的 AIMessage"——中断的任务没有产生新终局消息，取到的是历史轮次的内容。

### 修法

`engine/runner.py`：返回前检测 `agent.stop_sig`，中断任务 `final_text = ""`（语义：未完成，无最终回复）。TUI 前端不受影响（delta 已流出内容，`assistantHadText` 为 true 时本就忽略 done.text）。

### 验证

- [x] 新增 `AbortFinalTextTests`（修复前返回旧文本，修复后为空）
- [x] 全量 46 tests OK

---

## FIX-4 · checkpoint 存储治理（retention + 压缩）

> 状态: ✅ 已修复并验证（教学模式：用户撰写源码，助手测试验证）· 严重度: medium · 实际 1 天

### 背景与量化目标

1M 级长会话实测（2026-10-24）：单会话 34 个 checkpoint 写入 38MB——每个 super-step 全量重写 state（msgpack 未压缩），总量 O(R²)。
已做：非交互路径 `durability='exit'`（每任务落 1 份）。剩余放大来源：交互路径每步落盘 × 全量 × 未压缩 × 旧快照全留。

**目标**：600k 字符会话占用 38MB → **3–5MB**（理论底价 1.2–2.4MB 的 2–3 倍），不丢 `/rewind` 粒度与挂起恢复能力。

### 第一层：快照压缩（写入时）

| 项 | 决策 |
|---|---|
| 位置 | `engine/checkpointer.py`：自定义 serde（子类化 langgraph 的序列化器，`dumps/loads` 外包一层压缩） |
| 算法 | **标准库 `lzma`**（零新依赖，符合"不轻易加依赖"原则；zstd 快 5–10× 但要加包——若实测 lzma 压缩耗时 >50ms/MB 再换） |
| 策略 | blob > 4KB 才压缩；压缩数据加 1 字节前缀标记 `0x01`，读取时检测前缀，无标记按原格式解（兼容） |
| 预期 | 5–10×（快照间 99% 内容相同，高度可压） |

### 第二层：retention 清理（收尾时）

- **时机**：`run_graph_task` / `resume_pending` 正常收尾后，对该 thread 执行
- **保留谓词**（三条都满足才可删）：非最近 `N` 份（默认 20，`graph_config.ckpt_retention` 可配）**且** 无挂起 interrupt 引用 **且** thread 已无挂起
- **删除**：`DELETE FROM checkpoints WHERE thread_id=? AND checkpoint_id NOT IN (保留集)`
- **VACUUM**：不每次做（锁库）；大小阈值触发（`graph.db` 超过 `ckpt_vacuum_mb`（默认 64MB）且处于任务收尾空闲期）
- 交互/非交互都启用；非交互因 durability=exit 本就每任务 1 份，retention 对其近似无操作

### 第三层：大消息外置 + hash 去重（本期不做）

对象表存大块消息（file_read 大结果/长文档，内容 hash 去重），state 放引用。**前置条件**：一、二层落地后实测仍超需求才启动，列 v0.3 候选。delta 增量快照明确排除（复杂度最高、压缩已拿走其大部分收益）。

### 风险与边界

- 挂起保护漏判会导致 `/resume` 失败——retention 谓词必须先查 pending interrupts，单测覆盖
- VACUUM 在线锁库——只在收尾空闲期 + 阈值触发
- 不动 `messages` 只追加语义、不动 durability 现状、不删 `/rewind` 保留窗口内的快照

### 改动清单与验收

- 改动：`engine/checkpointer.py`（压缩 serde + retention）、`engine/settings.py`（`ckpt_retention=20` / `ckpt_vacuum_mb=64` 默认值）、`engine/runner.py`（收尾挂清理）、`tests/test_engine.py`
- 落地内容：
  - `engine/checkpointer.py`：`CompressedSerde`（JsonPlus 子类，blob ≥4KB lzma 压缩、首字节 0x01 标记、旧格式直读兼容）注入 `SqliteSaver`；`prune_thread`（双表删 checkpoints+writes、保留最近 N 份、VACUUM 阈值触发）
  - `engine/settings.py`：`ckpt_retention=20` / `ckpt_vacuum_mb=64` 默认值（graph_config 可覆盖）
  - `engine/runner.py`：任务正常收尾后裁剪（`not pending` 挂起保护、失败静默不影响任务）
- 验收：
  - [x] 单测 ×5：压缩 roundtrip/阈值、旧格式兼容、prune 保留最新语义、retention 默认值、VACUUM 阈值路径
  - [x] 集成：`driver --mini` 真实 2 任务全链路（压缩写入→读回→跨轮→prune）
  - [x] 全量 52 tests OK
  - [x] 实测效果：16 份 checkpoint blob 总量 55KB（合成 60KB 负载/份 → 245 bytes）；/rewind 保留窗口语义由 prune 保序覆盖
