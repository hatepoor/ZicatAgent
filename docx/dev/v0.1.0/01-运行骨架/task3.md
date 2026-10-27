# Task 3: 运行模式路由

> 模块: `01-运行骨架`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1, task2
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

实现交互、--task、--func、--reflect、--rpc 五种运行模式的路由与生命周期。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **交互模式**
   - 文件: `agentmain.py`
   - 详情: 读取 stdin，交给 core.commands.handle，循环直到 /exit
2. **一次性模式**
   - 文件: `agentmain.py`
   - 详情: --func 读 prompt 文件、执行、写 *.out.txt；--task 进入文件循环
3. **无人值守**
   - 文件: `agentmain.py`
   - 详情: --reflect 加载脚本，按 INTERVAL 调 check() 投递任务
4. **RPC**
   - 文件: `agentmain.py / core/rpc.py`
   - 详情: --rpc 走 JSONL 协议

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `agentmain.py` | 修改 | 模式路由 |
| `core/modes.py` | 修改 | 模式提示词 |
| `core/rpc.py` | 修改 | RPC 入口 |

## 验收标准

- [x] 五种模式都能启动
- [x] --func 结果写入 .out.txt
- [x] --reflect 能按脚本触发并退出
