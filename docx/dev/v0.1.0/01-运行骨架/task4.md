# Task 4: 任务循环与文件协议

> 模块: `01-运行骨架`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task3
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

实现任务队列消费、展示输出，以及 --task 的文件协议（output/reply/_stop/_keyinfo/_intervene）。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **队列消费**
   - 文件: `agentmain.py`
   - 详情: 从展示队列读取 next/done，输出到终端或 output.txt
2. **协作协议**
   - 文件: `agentmain.py`
   - 详情: --task 等待 reply.txt；10 分钟无回复退出
3. **控制文件**
   - 文件: `agentmain.py / engine/runner.py`
   - 详情: 任务间与运行中消费 _stop/_keyinfo/_intervene

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `agentmain.py` | 修改 | 队列与文件协议 |
| `engine/runner.py` | 修改 | 运行中 _stop 检查 |

## 验收标准

- [x] 交互输出与 --task 输出一致
- [x] _stop 能中断运行中任务
- [x] reply 续跑不丢上下文
