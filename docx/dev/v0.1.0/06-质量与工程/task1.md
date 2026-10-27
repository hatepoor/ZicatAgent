# Task 1: 测试体系

> 模块: `06-质量与工程`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: 无
> 模块依赖: 01-05
> 状态: ✅ 已完成

## 目标

建立单测与进程级集成测试，覆盖引擎、记忆、工具、RPC、reflect。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **单测**
   - 文件: `tests/test_engine.py`
   - 详情: 图/记忆/工具/RPC/回调等 34 个用例
2. **集成**
   - 文件: `tests/test_integration.py`
   - 详情: RPC 批处理、--reflect 进程级 2 个用例
3. **运行约定**
   - 文件: `README / docs`
   - 详情: python -X utf8 -m unittest ...

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `tests/test_engine.py` | 新增 | 单测 |
| `tests/test_integration.py` | 新增 | 集成测试 |

## 验收标准

- [x] 36 个测试全绿
- [x] 测试不需要 API key
- [x] 失败信息可定位
