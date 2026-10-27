# 交互前端

> 编号: `05`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 英文标识: `cli`
> 状态: ✅ 已完成
> 最后更新: 2026-10-23

## 前置依赖

| 依赖 04 的工具与 02 的引擎（CLI 只做展示与命令分发） | `arch/v1/modules.md` | 本模块复用前置模块的运行入口/引擎/工具能力 |


## 概述

实现 Python CLI 与零依赖 TS CLI：命令分发、graph 会话命令、JSONL RPC、启动器。

## 功能清单

- **slash 命令分发（16 个命令）与 /help**: slash 命令分发（16 个命令）与 /help
- **graph 会话命令：/threads /resume /continue /rewind /cost**: graph 会话命令：/threads /resume /continue /rewind /cost
- **JSONL RPC 协议与中断/退出时序**: JSONL RPC 协议与中断/退出时序
- **零依赖 TS CLI（流式、工具卡片、spinner）与启动器**: 零依赖 TS CLI（流式、工具卡片、spinner）与启动器

## 对外暴露接口

| 接口/导出 | 类型 | 说明 | 是否已写入 arch |
|-----------|------|------|-----------------|
| `core.commands.handle` | `函数` | 命令/普通任务分流 | 是 |
| `RPC 命令/事件` | `JSONL` | task/answer/abort/exit → ready/delta/tool/tool_result/usage/interrupt/done/exit | 是 |
| `zicat.ps1 / zicat.cmd / zicat.sh` | `脚本` | Node 探测与回退 | 是 |

## 模块开发规范

### 模块目录结构

```text
core/commands.py / core/rpc.py / cli/zicat.ts / zicat.ps1 / zicat.cmd / zicat.sh
```

### 本模块关键约束

- CLI 不缓存会话状态
- RPC exit 必须先等任务收尾
- TS CLI 零 npm 依赖，Node 23+ 直接跑 .ts

## Task 清单

| Task | 名称 | 状态 | 前置 |
|------|------|------|------|
| [task1](./task1.md) | Python CLI 命令分发 | ✅ | 无 |
| [task2](./task2.md) | graph 会话命令 | ✅ | task1 |
| [task3](./task3.md) | JSONL RPC 协议 | ✅ | task1 |
| [task4](./task4.md) | TS CLI 与启动器 | ✅ | task3 |
