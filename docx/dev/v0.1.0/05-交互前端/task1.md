# Task 1: Python CLI 命令分发

> 模块: `05-交互前端`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: 无
> 模块依赖: 04
> 状态: ✅ 已完成

## 目标

实现 core.commands.handle：内置命令、模式命令、普通任务投递与 /help。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **命令表**
   - 文件: `core/commands.py`
   - 详情: 16 个命令分支与别名 /? /h /quit
2. **模式命令**
   - 文件: `core/modes.py`
   - 详情: /goal /team /autorun /morphling /update 提示词
3. **错误处理**
   - 文件: `core/commands.py`
   - 详情: 未知命令提示、参数缺失提示

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `core/commands.py` | 新增 | 命令分发 |
| `core/modes.py` | 修改 | 模式提示词 |

## 验收标准

- [x] /help 列出全部命令
- [x] 普通文本进入任务
- [x] 未知命令不崩溃
