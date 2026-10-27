# task2 · /model 热切换（方案定稿）

> 状态: ⬜ 待执行 · 工作量 ~半天

## 设计（2026-10-24 会话定稿）

**既有底子**（不造新机制，补通路）：模型每任务重建（`_build()`→`build_chat_model()`）、配置热重载（mykey_loader mtime 检测）、多配置选择器已有雏形（`--llm_no N`）。

**补三块**：

| 块 | 内容 |
|---|---|
| 通路 | RPC 新指令 `{"type":"set_model","index":N}`；CLI/TUI `/model N` 或 `/model <名称前缀>` |
| 状态 | 激活索引 `agent.llm_no`（内存）+ 落 `temp/llm_state.json`（重启保留）；`ready` 事件下发完整模型列表（现在只发当前名） |
| 反馈 | 切换后下个任务 ready/状态栏显示新模型；越界索引报错不炸 |

**生效语义**：任务间切换（当前任务跑完才换）。中途换模型对 LangGraph 无意义且行为不一致；引擎重建窗口本就只在任务开始。**与 fallback 不冲突**：切换改"谁是主"，`with_fallbacks` 其余配置继续当备胎。

## 改动清单

- [ ] `agentmain.py`：llm_no 状态（读 `build_chat_model` 尊重索引）+ llm_state 持久化
- [ ] `engine/llm.py`：`build_chat_model(index=None)` 支持
- [ ] `core/commands.py`：`/model` 命令（无参=列表，带参=切换）
- [ ] `core/rpc.py`：set_model 指令 + ready 附 model_list
- [ ] TUI：`/model` 经 slash 透传自动可用；状态栏模型名随 ready 更新
- [ ] 单测：索引切换/越界/列表；全量回归

## 验收

- [ ] 双模型 .env 下 `/model 2` 后下一任务模型切换（usage/日志可证）
- [ ] 与 task5（故障转移实测）联测：手动切换与自动 fallback 并存不冲突
