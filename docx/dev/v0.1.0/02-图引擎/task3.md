# Task 3: 检查点与跨进程恢复

> 模块: `02-图引擎`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task2
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

用 SqliteSaver 持久化状态，支持 /resume 在新进程回答挂起的 interrupt。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **检查点**
   - 文件: `engine/checkpointer.py`
   - 详情: temp/graph.db，WAL/busy_timeout，setup()
2. **thread 管理**
   - 文件: `engine/runner.py`
   - 详情: thread_id 生成、meta 记录、get_state 查询
3. **恢复**
   - 文件: `engine/runner.py`
   - 详情: resume_pending 用 Command(resume=answer) 继续

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `engine/checkpointer.py` | 新增 | SqliteSaver 单例 |
| `engine/runner.py` | 修改 | resume 入口 |
| `core/commands.py` | 修改 | /resume |

## 验收标准

- [x] 进程退出后 /resume 能继续
- [x] 挂起期间无新消息写入
- [x] 非法 thread 报错清晰
