# 工具系统

> 编号: `04`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 英文标识: `tools`
> 状态: ✅ 已完成
> 最后更新: 2026-10-23

## 前置依赖

| 依赖 03 的记忆工具（memory_* 桥接） | `arch/v1/modules.md` | 本模块复用前置模块的运行入口/引擎/工具能力 |


## 概述

维护 16 个工具的单一 schema、反射 dispatch 与具体能力：文件/代码/浏览器/网页/记忆。

## 功能清单

- **assets/tools_schema.json 唯一 schema（9 原子 + 7 记忆）**: assets/tools_schema.json 唯一 schema（9 原子 + 7 记忆）
- **BaseHandler.dispatch 反射调度 do_***: BaseHandler.dispatch 反射调度 do_*
- **文件/代码工具与 memory/ 写拦截**: 文件/代码工具与 memory/ 写拦截
- **浏览器工具（web_scan/web_execute_js）**: 浏览器工具（web_scan/web_execute_js）
- **记忆工具桥与工具层测试**: 记忆工具桥与工具层测试

## 对外暴露接口

| 接口/导出 | 类型 | 说明 | 是否已写入 arch |
|-----------|------|------|-----------------|
| `tools_schema.json` | `JSON` | OpenAI function schema | 是 |
| `BaseHandler.dispatch` | `方法` | 工具名 → do_* | 是 |
| `StepOutcome` | `dataclass` | data/next_prompt/should_exit | 是 |
| `ToolRuntime.run_tool` | `方法` | 引擎侧工具适配 | 是 |

## 模块开发规范

### 模块目录结构

```text
zicat.py / agent_types.py / assets/tools_schema.json / TMWebDriver.py / simphtml.py
```

### 本模块关键约束

- schema 只改 assets/tools_schema.json
- file_write/file_patch 禁止写 memory/；code_run 旁路为已知限制
- 工具结果统一 JSON 序列化

## Task 清单

| Task | 名称 | 状态 | 前置 |
|------|------|------|------|
| [task1](./task1.md) | 单一 schema 与 reflection dispatch | ✅ | 无 |
| [task2](./task2.md) | 文件/代码工具与写拦截 | ✅ | task1 |
| [task3](./task3.md) | 浏览器与网页工具 | ✅ | task1 |
| [task4](./task4.md) | 记忆工具桥与工具测试 | ✅ | task2 |
