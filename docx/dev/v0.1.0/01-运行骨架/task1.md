# Task 1: 入口与参数解析

> 模块: `01-运行骨架`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: 无
> 模块依赖: 无
> 状态: ✅ 已完成

## 目标

实现 agentmain 入口：解析运行模式参数、初始化日志与工作目录、按模式分发。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **参数解析**
   - 文件: `agentmain.py`
   - 详情: argparse 支持 --task/--func/--reflect/--rpc/--nobg/--nolog/--no-user-tools，互斥校验
2. **模式分发**
   - 文件: `agentmain.py`
   - 详情: 按参数选择 interactive / task / func / reflect / rpc 分支
3. **启动校验**
   - 文件: `agentmain.py`
   - 详情: 检查 mykey 与工作目录；--rpc 时重定向 stdout

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `agentmain.py` | 修改 | 入口与模式分发 |

## 验收标准

- [x] `python agentmain.py --help` 正常
- [x] 无参数进入交互模式
- [x] 非法组合有明确报错
