# Task 1: SQLite schema 与 append-only 触发器

> 模块: `03-记忆系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: 无
> 模块依赖: 02
> 状态: ✅ 已完成

## 目标

建立记忆库 schema、索引、FTS 与禁止改删版本/事件的触发器。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **建表**
   - 文件: `memstore/schema.sql`
   - 详情: memory_items/versions/events/links/session_state/fts
2. **触发器**
   - 文件: `memstore/schema.sql`
   - 详情: versions/events 的 UPDATE/DELETE RAISE ABORT；FTS 同步触发器
3. **连接**
   - 文件: `memstore/db.py`
   - 详情: WAL、foreign_keys、busy_timeout、tx() 串行化

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `memstore/schema.sql` | 新增 | schema 与触发器 |
| `memstore/db.py` | 新增 | 连接与事务 |

## 验收标准

- [x] UPDATE/DELETE 版本被拒绝
- [x] FTS 行数与 items 一致
- [x] WAL 模式生效
