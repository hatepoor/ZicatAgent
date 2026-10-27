# FIX-M1 · memory/ 架构重构方案（目录 + 命名）

> 状态: ✅ 已执行并验证 · 来源: 架构评审（用户发起）· 实际 0.5 天
> 原则: 结构自解释（每个目录一种身份）、单一 git 源（同内容不进两个目录）、改路径不改语义（L0–L4 分层与库条目名零变化）

## 一、目录 Before → After

```text
memory/（现状 11 条目）                 memory/（重构后 9 条目）
├── kb/                          →     ├── kb/              L3 知识手册（唯一 git 代表，不动）
├── autonomous_operation_sop/    →删   ├── scripts/         ★ L3 工具脚本（.py，机器 import）
│    └── helper.py               →移       ├── checklist_helper.py   ← 原 memory/ 顶层
├── checklist_helper.py          →移       ├── keychain.py           ← 原 memory/ 顶层
├── keychain.py                  →移       └── autonomous_helper.py  ← 原 autonomous_operation_sop/（目录删）
├── review_sop/                  →删   ├── facts.txt        ← 原 facts.txt（L2 事实源）
│    └── review_inline_prompt*   →移   ├── l1_fallback.txt  ← 原 l1_fallback.txt（L1 兜底）
├── facts.txt               →改   ├── export/          只剩 L1/ 与 L2/（L3/ 24 个镜像删除）
├── l1_fallback.txt       →改   ├── L4_raw_sessions/ 纯归档数据（compress_session.py 移出）
├── export/L1|L2|L3              →缩   ├── backup/          不变（gitignore 灾备）
├── L4_raw_sessions/ +压缩脚本   →拆   └── memory.db         不变（库本体）
├── backup/                      不变  └── README.md        ★ 新增门牌
└── memory.db                    不变
```

assets 侧（L1 家族改名对仗）：
```text
assets/l1_template.txt(_en)  →  assets/l1_template.txt(_en)
assets/l1_structure.txt(_en)      →  assets/l1_structure.txt(_en)
memory/assets/review_inline_prompt(.en).txt →  assets/review_inline_prompt(.en).txt
```

## 二、迁移清单（12 项）

| # | 从 | 到 | 类型 | 库条目影响 |
|---|---|---|---|---|
| 1 | export/L3/（24 文件） | 删除 | 消冗余 | 无（L3 git 代表=kb） |
| 2 | memory/scripts/checklist_helper.py | memory/scripts/ | git mv | 无（stem 不变） |
| 3 | memory/scripts/keychain.py | memory/scripts/ | git mv | 无 |
| 4 | scripts/autonomous_helper.py | memory/scripts/autonomous_helper.py | git mv+改名 | **rename 条目** helper→autonomous_helper（走已验证 rename 流程+审计留痕） |
| 5 | assets/（review prompt）* | assets/ | git mv | 无（非库条目） |
| 6 | memstore/l4_compress.py | memstore/l4_compress.py | git mv+改名 | 无（非条目） |
| 7 | facts.txt | memory/facts.txt | git mv+改名 | **rename 条目** global_mem→facts |
| 8 | l1_fallback.txt | memory/l1_fallback.txt | git mv+改名 | 同步 l1_rules 提取源路径（#RULES） |
| 9 | assets 两个模板 ×2 语言 | l1_template/l1_structure | git mv | 无（非条目） |

## 三、代码改动点（精确）

| 文件 | 改动 |
|---|---|
| `memstore/migrate.py` | classify()：脚本路径三处特判 → `scripts/` 前缀一条规则；`facts.txt` 特判 → `facts.txt`；l1_rules 提取源 → `l1_fallback.txt` |
| `memstore/export.py` | 跳过 L3 导出（只导 L1/L2） |
| `zicat.py` | `load_L1` 兜底路径 → `l1_fallback.txt` |
| `agentmain.py` + `engine/runner.py` | 模板/结构文件加载路径 → `l1_template` / `l1_structure` |
| `core/review.py` | prompt 路径 → `assets/review_inline_prompt*` |
| `reflect/scheduler.py` | compress_session import → `memstore.l4_compress` |
| `memory/backup/import_manifest.json` | 两个改名条目的 name/source/hash 同步（hive 批流程） |
| kb 内互引 | `checklist_sop`/`autonomous_operation_sop` 等提及 helper/keychain 路径处（3–4 处） |
| docx | guide/arch 中 `global_mem`、`review_sop/`、脚本路径提及批量替换 |
| `memory/README.md` | 新增：每子目录一行「身份（源/镜像/运行时）+ 层号映射 + 谁写谁读」+ 指向 assets/diagrams/memory_arch_v2.drawio |

## 四、验收

- [x] 全量单测 56 tests OK（export 契约用例按 L1/L2 更新）
- [x] `memstore.sync`（missing=0）→ `verify` 138 项 0 失败 → `export` 只出 L1/L2（2 条）
- [x] `render_l1` 正常、`load_L1` 兜底路径生效（断库冒烟 + L1 含新名 facts/autonomous_helper、无旧名残留）
- [x] `/review` prompt 从 assets 加载 OK（4825 字符）
- [x] 两个 rename 条目审计留痕；manifest 同步；scripts 包可导入验证
- [x] docx 18 文件术语替换；memory/README.md 门牌；kb/index 更新

## 五、执行顺序（一批一验）

1. git mv 全部文件（保留历史）→ 2. 代码路径 8 处 → 3. 库 rename×2 + manifest → 4. sync/verify/export 链路 → 5. README 门牌 → 6. docx + 全量测试 → 7. 提交（单笔 refactor commit）
