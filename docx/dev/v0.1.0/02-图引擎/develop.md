# 图引擎

> 编号: `02`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 英文标识: `engine`
> 状态: ✅ 已完成
> 最后更新: 2026-10-23

## 前置依赖

| 依赖 01 的运行入口 | `arch/v1/modules.md` | 本模块复用前置模块的运行入口/引擎/工具能力 |


## 概述

用 LangGraph 状态图实现 Agent 控制面：状态只追加、模型视图可折叠、检查点可恢复、工具与人工中断可编排。

## 功能清单

- **ZicatState：messages/summaries 只追加，working/turn/exit_reason 覆盖**: ZicatState：messages/summaries 只追加，working/turn/exit_reason 覆盖
- **图拓扑：prepare → agent ⇄ tools → human → check → finalize**: 图拓扑：prepare → agent ⇄ tools → human → check → finalize
- **SQLite 检查点与跨进程 resume**: SQLite 检查点与跨进程 resume
- **模型视图：工作记忆重锚、摘要折叠、轮末钩子、no_tool 守夜**: 模型视图：工作记忆重锚、摘要折叠、轮末钩子、no_tool 守夜
- **流式调用与 Ctrl+C 中断；对话/文件回退**: 流式调用与 Ctrl+C 中断；对话/文件回退

## 对外暴露接口

| 接口/导出 | 类型 | 说明 | 是否已写入 arch |
|-----------|------|------|-----------------|
| `ZicatState` | `TypedDict` | 图状态 schema | 是 |
| `build_graph` | `函数` | 编译图并提供节点路由 | 是 |
| `run_graph_task / resume_pending` | `函数` | 执行新任务 / 恢复挂起任务 | 是 |
| `build_model_messages` | `函数` | 状态 → 模型视图 | 是 |
| `ToolRuntime.run_tool` | `方法` | 工具执行适配 | 是 |

## 模块开发规范

### 模块目录结构

```text
engine/state.py / graph.py / runner.py / hooks.py / checkpointer.py / rewind.py / callbacks.py
```

### 本模块关键约束

- 存储层 messages 永不删改；折叠只影响模型视图
- 同一 thread 串行执行，不允许并发 resume
- 模型调用必须流式并在 chunk 间检查 stop_sig

## Task 清单

| Task | 名称 | 状态 | 前置 |
|------|------|------|------|
| [task1](./task1.md) | State schema 与只追加不变式 | ✅ | 无 |
| [task2](./task2.md) | 图拓扑与节点 | ✅ | task1 |
| [task3](./task3.md) | 检查点与跨进程恢复 | ✅ | task2 |
| [task4](./task4.md) | 模型视图、轮末钩子与流式中断 | ✅ | task3 |
| [task5](./task5.md) | 对话与文件回退 | ✅ | task3 |
