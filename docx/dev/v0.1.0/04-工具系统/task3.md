# Task 3: 浏览器与网页工具

> 模块: `04-工具系统`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 03
> 状态: ✅ 已完成

## 目标

实现 web_scan/web_execute_js 与 TMWebDriver 桥，覆盖本地 Chrome 操作。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **驱动**
   - 文件: `TMWebDriver.py / simphtml.py`
   - 详情: CDP/WS 桥、页面扫描、结果序列化
2. **工具**
   - 文件: `zicat.py`
   - 详情: do_web_scan/do_web_execute_js
3. **降级**
   - 文件: `zicat.py`
   - 详情: 浏览器不可用时返回可操作错误

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `TMWebDriver.py` | 修改 | 浏览器桥 |
| `simphtml.py` | 修改 | 页面处理 |
| `zicat.py` | 修改 | web 工具 |

## 验收标准

- [x] 能打开本地页面并取文本
- [x] 扩展未装时错误清晰
- [x] JS 返回结果可序列化
