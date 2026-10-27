"""LangGraph 控制面：图、状态、工具适配、运行入口。

注意：这里不 eager import 子模块，避免 `core/commands.py` 仅想读配置时
被迫加载 langchain（legacy-only 安装也能用 /threads）。
"""
