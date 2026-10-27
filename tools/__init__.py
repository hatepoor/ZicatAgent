"""tools/：zicatAgent 工具域统一包（FIX-T）。

子包按类别：code / files / browser / memory / session_ctl / sandbox。
装配：各子包 __init__ 触发 @register；zicat.ZicatAgentHandler.dispatch 委托
tools.registry.dispatch（yield 流式协议不变）。
"""
