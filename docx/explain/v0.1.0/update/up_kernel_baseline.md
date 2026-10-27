# 内核基线：LangGraph 单引擎

> 版本: v0.1.0
> 类别: 新增
> 主题: kernel_baseline
> 对比版本: 无
> 日期: 2026-10-23
> 关联架构版本: v1
> 关联 ADR: ADR-0001
> 关联开发文档: [dev/v0.1.0/02-图引擎](../../../dev/v0.1.0/02-图引擎/develop.md)

## 变更前

无，本版首次建立。此前仓库存在自研文本循环（`agent_loop.py` + `llmcore.py`）与插件体系，无法可靠持久化、恢复中断或回退。

## 变更后

- 唯一引擎为 LangGraph `StateGraph`：`prepare → agent ⇄ tools → human → check → finalize`。
- 状态用 `SqliteSaver` 持久化到 `temp/graph.db`，支持跨进程 `/resume`。
- `messages`/`summaries` 用 `operator.add` 只追加；模型视图是投影，不改存储。
- `ask_user` 改用 `interrupt()`；`/rewind` 支持检查点对话回退与文件回退。
- legacy 引擎、Claude 直连、插件体系与 `--engine` 参数全部删除。

## 影响范围

- **模块**: `engine`、`runtime`、`tools`
- **契约**: 新增 `ZicatState`、`build_graph()`、`run_graph_task()`；旧的 `agent_runner_loop` 契约删除（破坏性，但本版为初版）
- **数据**: 新增 `temp/graph.db`；不迁移旧会话
- **兼容性**: 不兼容旧引擎；CLI 入口保持 `agentmain.py`

## 验证方式

- `python -X utf8 -m unittest tests.test_engine`：图/状态/恢复/回退用例通过
- 真实任务：建文件 + 多工具 + 中断恢复实测
- 30 轮追加式压测：消息数/配对/前缀 hash 校验通过

## 备注

`/rewind` 的对话回退与文件回退是两套编号（检查点 vs worldline），需分别操作。
