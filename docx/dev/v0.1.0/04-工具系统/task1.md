# Task 1: 单一 schema 与 reflection dispatch

> 模块: `04-工具系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: 无
> 模块依赖: 03
> 状态: ✅ 已完成

## 目标

把工具 schema 收敛到 assets/tools_schema.json，并用 dispatch 反射调用 do_*。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **schema**
   - 文件: `assets/tools_schema.json`
   - 详情: 16 个工具定义；英文版同步
2. **dispatch**
   - 文件: `agent_types.py`
   - 详情: BaseHandler.dispatch 处理生成器/StepOutcome/exhaust
3. **加载**
   - 文件: `engine/tools.py`
   - 详情: load_tools_schema，支持 --no-user-tools

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `assets/tools_schema.json` | 修改 | 合并记忆工具 |
| `agent_types.py` | 新增 | dispatch/StepOutcome |
| `engine/tools.py` | 新增 | schema 加载 |

## 验收标准

- [x] schema 数量 16
- [x] 未知工具返回明确错误
- [x] 工具异常不炸整轮
