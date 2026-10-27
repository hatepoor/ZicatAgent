# 质量与工程

> 编号: `06`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 英文标识: `ops`
> 状态: 🔧 进行中
> 最后更新: 2026-10-23

## 前置依赖

| 依赖 05 的前端（验收入口）与 01-05 全部模块 | `arch/v1/modules.md` | 本模块复用前置模块的运行入口/引擎/工具能力 |


## 概述

补齐测试、自动化脚本、文档体系与工程化收尾：打包声明、真实烘跑与版本验收。

## 功能清单

- **单测 + 进程级集成测试**: 单测 + 进程级集成测试
- **reflect 自动化（scheduler/goal/autonomous/team）**: reflect 自动化（scheduler/goal/autonomous/team）
- **docs 历史文档 + docx 三层文档**: docs 历史文档 + docx 三层文档
- **打包/依赖声明与真实任务烘跑**: 打包/依赖声明与真实任务烘跑

## 对外暴露接口

| 接口/导出 | 类型 | 说明 | 是否已写入 arch |
|-----------|------|------|-----------------|
| `测试命令` | `CLI` | unittest tests.test_engine tests.test_integration | 是 |
| `reflect 脚本契约` | `模块` | INTERVAL/ONCE/init/check | 是 |
| `pyproject.toml` | `TOML` | 可安装包与依赖 | 待修复 |

## 模块开发规范

### 模块目录结构

```text
tests/ / reflect/ / docs/ / docx/ / pyproject.toml
```

### 本模块关键约束

- 测试不依赖真实模型
- 文档三层边界不混写
- 打包声明必须与实际模块一致

## Task 清单

| Task | 名称 | 状态 | 前置 |
|------|------|------|------|
| [task1](./task1.md) | 测试体系 | ✅ | 无 |
| [task2](./task2.md) | reflect 自动化 | ✅ | task1 |
| [task3](./task3.md) | 文档体系 | ✅ | task1 |
| [task4](./task4.md) | 打包与依赖声明 | ⬜ | task1, task3 |
| [task5](./task5.md) | 真实烘跑与版本验收 | ⬜ | task1-4 |
