# Task 5: 对话与文件回退

> 模块: `02-图引擎`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task3
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

实现 /rewind：按检查点回退对话，按 worldline 回退 file_write/file_patch 的文件。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **检查点回退**
   - 文件: `engine/rewind.py / core/rewind.py`
   - 详情: 列出 thread 检查点、按序号恢复
2. **文件回退**
   - 文件: `engine/rewind.py`
   - 详情: 记录写前快照与 worldline 节点，支持列出/恢复
3. **CLI**
   - 文件: `core/commands.py`
   - 详情: /rewind、/rewind files、/rewind file <id>

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `engine/rewind.py` | 新增 | 任务级回退 |
| `core/rewind.py` | 修改 | 存储/文件回退 |
| `core/commands.py` | 修改 | /rewind |

## 验收标准

- [x] 对话可回退到指定检查点
- [x] 文件可回退到写前版本
- [x] 回退后检查点与文件不串号
