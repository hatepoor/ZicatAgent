# Task 2: reflect 自动化

> 模块: `06-质量与工程`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

维护 scheduler/goal/autonomous/team worker 脚本与 --reflect 契约。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **scheduler**
   - 文件: `reflect/scheduler.py`
   - 详情: sche_tasks 轮询、done 标记、L4 归档
2. **goal**
   - 文件: `reflect/goal_mode.py`
   - 详情: goal_state.json 预算与续轮
3. **team**
   - 文件: `reflect/agent_team_worker.py / checklist_master.py`
   - 详情: BBS 接单/检查单

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `reflect/scheduler.py` | 修改 | 定时任务 |
| `reflect/goal_mode.py` | 修改 | Goal 模式 |
| `reflect/agent_team_worker.py` | 修改 | Team worker |

## 验收标准

- [x] --reflect 能触发并退出
- [x] scheduler 任务格式可解析
- [x] 脚本无状态可重启
