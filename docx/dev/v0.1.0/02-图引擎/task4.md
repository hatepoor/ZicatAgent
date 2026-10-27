# Task 4: 模型视图、轮末钩子与流式中断

> 模块: `02-图引擎`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task3
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

实现工作记忆重锚、字符预算折叠、轮末提醒、no_tool 二次确认和流式 Ctrl+C。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **视图构建**
   - 文件: `engine/hooks.py`
   - 详情: system + working + 折叠历史 + 摘要占位；不写存储
2. **轮末钩子**
   - 文件: `engine/graph.py`
   - 详情: 复用 zicat.turn_end_callback：15 轮 L1、周期提醒、_keyinfo/_intervene
3. **守夜**
   - 文件: `engine/graph.py`
   - 详情: check 节点复用 zicat.do_no_tool，空/截断/大代码块重试
4. **流式中断**
   - 文件: `engine/graph.py`
   - 详情: _invoke_with_stop 逐 chunk 检查 stop_sig

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `engine/hooks.py` | 新增 | 模型视图 |
| `engine/graph.py` | 修改 | 轮末与守夜 |
| `engine/callbacks.py` | 修改 | 日志/用量 |

## 验收标准

- [x] 超预算时折叠且前缀仍在存储中
- [x] no_tool 能触发重试
- [x] Ctrl+C 不必等完整模型返回
