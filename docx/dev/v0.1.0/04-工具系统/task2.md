# Task 2: 文件/代码工具与写拦截

> 模块: `04-工具系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 03
> 状态: ✅ 已完成

## 目标

实现 file_read/file_write/file_patch/code_run，并在两层拦截 memory/ 写入。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **文件工具**
   - 文件: `zicat.py`
   - 详情: 读写补丁、长度控制、行号显示
2. **code_run**
   - 文件: `zicat.py`
   - 详情: 子进程执行、超时、输出截断、环境变量
3. **写拦截**
   - 文件: `zicat.py / engine/tools.py`
   - 详情: memory/ 路径拒绝；rewind 记录写前快照

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `zicat.py` | 修改 | do_file_*/do_code_run |
| `engine/tools.py` | 修改 | 路径拦截 |

## 验收标准

- [x] memory/ 写入被拒绝
- [x] 大文件/长输出有截断提示
- [x] code_run 超时可停止
