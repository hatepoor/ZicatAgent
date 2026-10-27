# md · memory/ 架构重构（FIX-M1）

> 版本: v0.1.1 · 类型: modify · 日期: 2026-10-24

## 变了什么（目录 11→9 条目，全部自解释）

- **消冗余**：export/L3 的 24 个镜像删除，export 只导 L1/L2（L3 的 git 代表=kb+scripts，verify 查漂移）
- **脚本归位**：checklist_helper/keychain（原顶层）与 autonomous_helper（原 autonomous_operation_sop/，目录删除）→ `memory/scripts/`；migrate 的 SCRIPT_FILES 三处特判收敛为 `scripts/` 前缀规则
- **资产分离**：review_sop/ 的 prompt → `assets/review_inline_prompt(.en).txt`（目录删除）；L4 压缩脚本 → `memstore/l4_compress.py`（L4 目录纯数据）
- **命名直白化**：global_mem.txt→facts.txt、global_mem_insight.txt→l1_fallback.txt、assets 两模板→l1_template/l1_structure（L1 家族对仗）
- **门牌**：新增 memory/README.md（目录身份×层号映射×谁写谁读 + 三条铁律）
- **库 rename×2**（facts、autonomous_helper，审计留痕）；L0–L4 分层字段与其余条目名零变化

## 验证

sync missing=0 / verify 138 项 0 失败 / export 仅 L1/L2 / 断库兜底冒烟 / review prompt 冒烟 / scripts 可导入 / 56 tests OK
