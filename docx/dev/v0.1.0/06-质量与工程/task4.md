# Task 4: 打包与依赖声明

> 模块: `06-质量与工程`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1, task3
> 模块依赖: 01-05
> 状态: ✅ 已完成

## 目标

修复 pyproject 的模块与依赖声明，使 `pip install -e .` 与默认 graph 引擎可用。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **模块声明**
   - 文件: `pyproject.toml`
   - 详情: 移除已删除的 agent_loop/llmcore；py-modules 与实际文件一致
2. **依赖声明**
   - 文件: `pyproject.toml`
   - 详情: graph 依赖改为默认依赖或明确安装说明
3. **验证**
   - 文件: `README`
   - 详情: 干净 venv 安装并跑通一次 --func /cost

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `pyproject.toml` | 修改 | 模块与依赖 |
| `README.md` | 修改 | 安装说明 |

## 验收标准

- [x] 干净 venv 可 editable 安装（`uv pip install -e . --no-deps`）
- [x] 不装可选依赖也能导入
- [x] 默认引擎可启动
