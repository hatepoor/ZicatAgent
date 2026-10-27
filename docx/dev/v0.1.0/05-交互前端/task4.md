# Task 4: TS CLI 与启动器

> 模块: `05-交互前端`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task3
> 模块依赖: 05
> 状态: ✅ 已完成

## 目标

实现零依赖 TS CLI 与跨平台启动器。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **TS CLI**
   - 文件: `cli/zicat.ts`
   - 详情: spawn Python --rpc、流式渲染、工具卡片、命令补全
2. **启动器**
   - 文件: `zicat.ps1 / zicat.cmd / zicat.sh`
   - 详情: 探测 Node 23+，否则回退 Python CLI
3. **包声明**
   - 文件: `cli/package.json`
   - 详情: 零依赖，Node 23 直接执行 .ts

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `cli/zicat.ts` | 新增 | TS CLI |
| `zicat.ps1` | 新增 | Windows 启动 |
| `zicat.cmd` | 新增 | cmd 启动 |
| `zicat.sh` | 新增 | POSIX 启动 |

## 验收标准

- [x] node cli/zicat.ts 可交互
- [x] 无 Node 时回退 Python
- [x] Ctrl+C/ask_user 正常
