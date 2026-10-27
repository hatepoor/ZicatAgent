# Task 2: graph 会话命令

> 模块: `05-交互前端`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 02
> 状态: ✅ 已完成

## 目标

实现 /threads /resume /continue /rewind /cost 等 graph 专属命令。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **会话**
   - 文件: `core/commands.py`
   - 详情: 列出 thread/检查点数；/resume 恢复挂起
2. **回退**
   - 文件: `core/commands.py / core/rewind.py`
   - 详情: /rewind、/rewind files、/rewind file
3. **用量**
   - 文件: `core/commands.py`
   - 详情: /cost 读 last_graph_usage 与 graph_config

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `core/commands.py` | 修改 | graph 命令 |
| `core/rewind.py` | 修改 | 回退存储 |

## 验收标准

- [x] /threads 列出真实检查点
- [x] /resume 能回答挂起
- [x] /cost 显示用量与预算
