# md · /morphling 更名 /distill

> 版本: v0.1.1 · 类型: modify · 日期: 2026-10-26

## 变了什么

用户决策：morphling（神话变形者）命名抽象。全局更名 distill（蒸馏，语义直给）：

- 命令 `/morphling` → `/distill`（modes/cli/zicat.ts/HELP）
- SOP `morphling_sop.md` → `distill_sop.md`（git mv）；记忆库条目 rename + 审计留痕
- L1 模板/结构、kb/index、memory_cleanup_sop、memory_management_sop、facts/l1_fallback 交叉引用同步
- docx/guide/USER_GUIDE 同步（/distill 详解 + 使用示例）

## 验证

sync/verify 134 项 0 失败；/distill 出现在权威命令表；全量 69 tests OK
