# Task 1: State schema 与只追加不变式

> 模块: `02-图引擎`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: 无
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

定义 ZicatState，确保 messages/summaries 只追加，working 等覆盖式字段语义明确。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **定义 State**
   - 文件: `engine/state.py`
   - 详情: TypedDict：messages/summaries 用 operator.add；working/turn/exit_reason 覆盖
2. **追加断言**
   - 文件: `engine/state.py`
   - 详情: 禁止 add_messages；注释说明为何不按 id 替换
3. **测试**
   - 文件: `tests/test_engine.py`
   - 详情: 单轮/多轮后消息数只增不减，前缀 hash 不变

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `engine/state.py` | 新增 | ZicatState |
| `tests/test_engine.py` | 新增 | 追加式断言 |

## 验收标准

- [x] messages 前缀在工具轮后不变
- [x] summaries 只增
- [x] working 更新不产生新消息
