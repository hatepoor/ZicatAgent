# Task 2: 图拓扑与节点

> 模块: `02-图引擎`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

实现 prepare/agent/tools/human/check/finalize 节点与条件路由。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **节点实现**
   - 文件: `engine/graph.py`
   - 详情: 各节点职责与写入字段；预算检查在工具前
2. **路由**
   - 文件: `engine/graph.py`
   - 详情: 有工具→tools；ask_user→human；无工具→check；超预算/退出→finalize
3. **工具适配**
   - 文件: `engine/tools.py`
   - 详情: ToolRuntime.run_tool 统一 dispatch、memory 写拦截、退出标记

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `engine/graph.py` | 新增 | 图节点与路由 |
| `engine/tools.py` | 新增 | 工具运行时 |
| `engine/runner.py` | 新增 | 事件流 |

## 验收标准

- [x] 多工具任务正确串行
- [x] ask_user 进入 human 节点
- [x] 预算耗尽进入 finalize
