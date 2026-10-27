# Task 3: JSONL RPC 协议

> 模块: `05-交互前端`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 02
> 状态: ✅ 已完成

## 目标

实现 --rpc：stdin 命令、stdout 事件、interrupt 回答、abort/exit 时序。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **协议**
   - 文件: `core/rpc.py`
   - 详情: task/answer/abort/exit 与事件分类
2. **桥接**
   - 文件: `core/rpc.py`
   - 详情: display_queue 消费、interrupt 挂起/回答
3. **退出**
   - 文件: `core/rpc.py`
   - 详情: exit 时 abort + join，避免截断 done

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `core/rpc.py` | 新增 | RPC 桥 |
| `agentmain.py` | 修改 | --rpc 入口 |

## 验收标准

- [x] 批处理先 done 后 exit
- [x] interrupt 可回答
- [x] abort 能停任务
