# Task 2: 配置加载

> 模块: `01-运行骨架`
> 所属版本: `v0.1.0`
> 对应架构版本: `v1`
> 前置 task: task1
> 模块依赖: 01
> 状态: ✅ 已完成

## 目标

从 mykey.py / 环境变量加载 API base、key、model，并暴露统一的配置读取接口。

## 前置准备

- [x] 前置模块/相关契约已确认
- [x] 前置 task 已完成或可并行
- [x] 开发环境可运行 `python -X utf8 -m unittest tests.test_engine`

## 实现步骤

1. **加载 mykey**
   - 文件: `mykey_loader.py`
   - 详情: 支持 mykey.py、MYKEY 环境变量；缺失时给可操作提示
2. **引擎配置**
   - 文件: `engine/settings.py`
   - 详情: oai_configs()/graph_config()/ROOT 统一出口
3. **模型构造**
   - 文件: `engine/llm.py`
   - 详情: 按配置构造 ChatOpenAI（OpenAI 兼容 base_url）

## 涉及文件

| 文件路径 | 操作类型 | 说明 |
|----------|----------|------|
| `mykey_loader.py` | 修改 | 配置加载 |
| `engine/settings.py` | 修改 | 配置出口 |
| `engine/llm.py` | 修改 | 模型构造 |

## 验收标准

- [x] 缺 mykey 时报错清晰
- [x] base_url/key/model 可覆盖
- [x] 不把密钥写入日志或仓库
