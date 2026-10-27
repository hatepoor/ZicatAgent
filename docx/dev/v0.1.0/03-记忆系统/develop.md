# 记忆系统

> 编号: `03`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 英文标识: `memory`
> 状态: ✅ 已完成
> 最后更新: 2026-10-23

## 前置依赖

| 依赖 02 的引擎（记忆工具经工具层调用） | `arch/v1/modules.md` | 本模块复用前置模块的运行入口/引擎/工具能力 |


## 概述

把长期记忆迁移到 SQLite 单库：版本/事件 append-only，提供 7 个记忆工具、动态 L1、文件同步/导出/备份与 kb 文档布局。

## 功能清单

- **SQLite schema：items/versions/events/links/fts/session_state**: SQLite schema：items/versions/events/links/fts/session_state
- **迁移与 manifest：文件 → 库，sha256 校验**: 迁移与 manifest：文件 → 库，sha256 校验
- **7 个记忆工具与 L1 动态渲染**: 7 个记忆工具与 L1 动态渲染
- **同步/导出/备份/verify**: 同步/导出/备份/verify
- **SOP 统一到 memory/kb/ 并建索引**: SOP 统一到 memory/kb/ 并建索引

## 对外暴露接口

| 接口/导出 | 类型 | 说明 | 是否已写入 arch |
|-----------|------|------|-----------------|
| `MemoryStore` | `类` | 记忆库读写与查询 | 是 |
| `memory_* 工具` | `7 个` | search/read/write/patch/archive/link/index | 是 |
| `load_L1 / render_l1` | `函数` | L1 动态渲染与兜底 | 是 |
| `memstore.sync/export/backup/verify` | `CLI` | 文件同步、导出、备份、校验 | 是 |

## 模块开发规范

### 模块目录结构

```text
memstore/schema.sql / db.py / repository.py / tools.py / migrate.py / sync.py / export.py / backup.py / verify.py / materialize.py
```

### 本模块关键约束

- versions/events 由触发器禁止 UPDATE/DELETE
- 写入必须在一个事务内更新指针 + 插版本 + 插事件
- 文件与库最终一致，以库为准

## Task 清单

| Task | 名称 | 状态 | 前置 |
|------|------|------|------|
| [task1](./task1.md) | SQLite schema 与 append-only 触发器 | ✅ | 无 |
| [task2](./task2.md) | 迁移与文件扫描 | ✅ | task1 |
| [task3](./task3.md) | 记忆工具与 L1 渲染 | ✅ | task1 |
| [task4](./task4.md) | 同步、导出、备份与 kb 布局 | ✅ | task2, task3 |
