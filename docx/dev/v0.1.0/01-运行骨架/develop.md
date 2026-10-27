# 运行骨架

> 编号: `01`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 英文标识: `runtime`
> 状态: ✅ 已完成
> 最后更新: 2026-10-23

## 前置依赖

无


## 概述

建立进程入口、配置加载、运行模式路由与任务循环，让内核可以被 CLI、脚本和定时任务统一驱动。

## 功能清单

- **命令行参数与模式选择（交互 / --task / --func / --reflect / --rpc）**: 命令行参数与模式选择（交互 / --task / --func / --reflect / --rpc）
- **mykey 配置加载与 OpenAI 兼容接口配置**: mykey 配置加载与 OpenAI 兼容接口配置
- **任务投递、展示队列与结果输出**: 任务投递、展示队列与结果输出
- **文件协议：_stop / _keyinfo / _intervene / reply.txt**: 文件协议：_stop / _keyinfo / _intervene / reply.txt

## 对外暴露接口

| 接口/导出 | 类型 | 说明 | 是否已写入 arch |
|-----------|------|------|-----------------|
| `ZicatAgent.put_task` | `方法` | 统一任务入口，返回展示队列 | 是 |
| `ZicatAgent.run` | `方法` | 进程主循环，返回退出码 | 是 |
| `agentmain.main` | `函数` | 参数解析与模式分发 | 是 |

## 模块开发规范

### 模块目录结构

```text
agentmain.py / mykey_loader.py / engine/settings.py / core/modes.py
```

### 本模块关键约束

- 单线程任务循环，同一时间只跑一个任务
- --rpc 模式下 stdout 只能输出 JSONL，日志走 stderr
- --task 的 _stop 在任务运行中也要被轮询

## Task 清单

| Task | 名称 | 状态 | 前置 |
|------|------|------|------|
| [task1](./task1.md) | 入口与参数解析 | ✅ | 无 |
| [task2](./task2.md) | 配置加载 | ✅ | task1 |
| [task3](./task3.md) | 运行模式路由 | ✅ | task1, task2 |
| [task4](./task4.md) | 任务循环与文件协议 | ✅ | task3 |
