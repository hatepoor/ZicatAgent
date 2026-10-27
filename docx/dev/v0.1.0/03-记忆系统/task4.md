# Task 4: 同步、导出、备份与 kb 布局

> 模块: `03-记忆系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task2, task3
> 模块依赖: 02
> 状态: ✅ 已完成

## 目标

支持文件改动回灌、可读导出、每日备份，并把 SOP 统一到 memory/kb/。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **同步**
   - 文件: `memstore/sync.py`
   - 详情: 扫描文件、按条目名 patch、更新 manifest
2. **导出/备份**
   - 文件: `memstore/export.py / backup.py`
   - 详情: export 可进 git；backup 快照 db/graph
3. **文档布局**
   - 文件: `memory/kb/`
   - 详情: 移动 21 个 SOP + index.md；更新引用与 RUNTIME_ASSETS

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `memstore/sync.py` | 新增 | 同步 |
| `memstore/export.py` | 新增 | 导出 |
| `memstore/backup.py` | 新增 | 备份 |
| `memory/kb/index.md` | 新增 | SOP 索引 |

## 验收标准

- [x] sync 幂等且只追加版本
- [x] export 与库内容一致
- [x] verify 140 项 0 失败
