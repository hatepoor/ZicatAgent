# Task 2: 迁移与文件扫描

> 模块: `03-记忆系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 02
> 状态: ✅ 已完成

## 目标

把 memory/ 下的 SOP/事实/脚本导入库，生成 manifest 并支持 dry-run/备份。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **扫描分类**
   - 文件: `memstore/migrate.py`
   - 详情: classify/build_plan；排除 backup/export/index；L0/L1/L2/L3/L4
2. **导入**
   - 文件: `memstore/migrate.py`
   - 详情: 写 items + version + event；manifest 记录 sha256
3. **校验**
   - 文件: `memstore/verify.py`
   - 详情: 条目/正文/版本/源文件 sha256

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `memstore/migrate.py` | 新增 | 导入 |
| `memstore/verify.py` | 新增 | 校验 |
| `memstore/common.py` | 新增 | 公共函数 |

## 验收标准

- [x] 26 条导入且 sha256 一致
- [x] 重复导入幂等
- [x] manifest 计入 git
