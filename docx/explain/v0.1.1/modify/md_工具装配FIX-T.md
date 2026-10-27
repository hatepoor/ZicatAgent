# md · 工具装配重构（FIX-T）

> 版本: v0.1.1 · 类型: modify · 日期: 2026-10-25

## 变了什么

- **tools/ 新包**：17 个工具实现自 zicat.py（704 行）迁出，按类别六子包（code/files/browser/memory/session_ctl + sandbox header）；zicat.py 瘦身为兼容壳（168 行：handler 状态所有权 + dispatch 委托 + 公共 API re-export）
- **ToolContext 显式注入**：工具函数签名统一 (ctx, args, response)，替代 self.* 隐式状态访问；ctx 为 handler 的动态视图（print/cwd 等构造后可变，走 property）
- **@register 装配**：schema 是模型侧接口、registry 是实现侧装配；新增工具 = schema 加一条 + 一个 @register 函数。装配完整性测试保证 schema 与 registry 键集一致（防 /cost 式宣传未实现）
- **流式协议不变**：registry.dispatch 为生成器函数，yield from 兼容链与原 BaseHandler.dispatch 逐字节同构

## 验证

装配 18 项（17 schema 工具 + no_tool）；每类 dispatch smoke；未知工具兜底；全量 68 tests OK
