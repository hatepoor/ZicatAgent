# Task 3: 记忆工具与 L1 渲染

> 模块: `03-记忆系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 02
> 状态: ✅ 已完成

## 目标

实现 7 个 memory_* 工具语义与 L1 动态渲染，替换原来直接读文件的方式。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **工具层**
   - 文件: `memstore/tools.py`
   - 详情: search/read/write/patch/archive/link/index 的参数校验与返回
2. **handler 桥**
   - 文件: `zicat.py`
   - 详情: do_memory_* 转发 MemoryTools
3. **L1**
   - 文件: `memstore/materialize.py`
   - 详情: render_l1/load_L1；库不可用回退文件

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `memstore/tools.py` | 新增 | 7 工具 |
| `zicat.py` | 修改 | do_memory_* |
| `memstore/materialize.py` | 新增 | L1 渲染 |

## 验收标准

- [x] 工具调用产生版本/事件
- [x] L1 与库一致
- [x] 库损坏时可回退
