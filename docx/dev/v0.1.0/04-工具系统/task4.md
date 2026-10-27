# Task 4: 记忆工具桥与工具测试

> 模块: `04-工具系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task2
> 模块依赖: 03
> 状态: ✅ 已完成

## 目标

把 7 个 memory_* 工具接到 MemoryTools，并补工具层测试。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **桥接**
   - 文件: `zicat.py`
   - 详情: do_memory_* 调 _memory_call → MemoryTools.dispatch
2. **测试**
   - 文件: `tests/test_engine.py`
   - 详情: 工具分发、写拦截、记忆工具冒烟
3. **文档**
   - 文件: `docs/20 / docx`
   - 详情: 16 工具清单与边界

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `zicat.py` | 修改 | do_memory_* |
| `tests/test_engine.py` | 修改 | 工具测试 |

## 验收标准

- [x] 7 个记忆工具可用
- [x] 未知工具/坏参数不崩溃
- [x] 工具测试通过
