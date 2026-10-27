# 长期记忆迁移到 SQLite

> 版本: v0.1.0
> 类别: 新增
> 主题: memory_sqlite
> 对比版本: 无
> 日期: 2026-10-23
> 关联架构版本: v1
> 关联 ADR: ADR-0002
> 关联开发文档: [dev/v0.1.0/03-记忆系统](../../../dev/v0.1.0/03-记忆系统/develop.md)

## 变更前

无，本版首次建立。此前记忆是 `memory/` 下的文件集合（SOP/事实/L1），没有版本、没有检索、没有写审计，模型可能直接改文件。

## 变更后

- 长期记忆统一进 `memory/memory.db`：`memory_items` 当前指针 + `memory_versions`/`memory_events` 只追加 + FTS5 检索。
- 7 个 `memory_*` 工具是唯一写入通道；SQLite 触发器拒绝改删版本/事件。
- L1 由库动态渲染，失败回退 `memory/l1_fallback.txt`。
- SOP 文件统一到 `memory/kb/`，`memstore.sync` 把文件改动回灌入库。
- `memstore.migrate/verify/export/backup` 覆盖迁移、校验、导出、备份。

## 影响范围

- **模块**: `memory`、`tools`、`engine`
- **契约**: 新增 `MemoryStore`、`memory_*` 工具、`load_L1()`；文件读取不再是主路径
- **数据**: 新增 `memory/memory.db`；文件保留 L0/导出/备份
- **兼容性**: 旧文件仍可作为同步源；旧的直接文件写被拦截

## 验证方式

- `python -X utf8 -m memstore.verify`：140 项校验 0 失败
- `memstore.sync` 幂等，改动只追加版本
- L1 渲染与库内容一致；库损坏时可回退文件

## 备注

文件与库可能短暂不一致，以库为准；改完 `memory/kb/*.md` 后必须跑 `memstore.sync`。
