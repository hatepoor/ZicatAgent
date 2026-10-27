# up · 文档体系合并：docs/ 并入 docx/guide/

> 版本: v0.1.1（相对 v0.1.0）
> 类型: update
> 日期: 2026-10-24

## 变了什么

- `docs/`（25 个文件，约 4200 行：项目介绍、原理讲解、引擎迁移评估、裁剪记录、附录）整体 `git mv` 并入 **`docx/guide/`**（导读层），仓库从「docs + docx 两套文档」合并为 **docx 单一文档体系**（四层：guide / arch / dev / explain）。
- 新增第四层职责定义（`docx/index.md` §4.1）：guide 回答"这个项目怎么理解、为什么这样设计"；只在与代码脱节时更新，新的开发事实不写入 guide。
- 链接修正：guide 内 24 个文件的头部索引行、指向仓库根/docx 的相对链接随目录层级调整；`docx/guide/README.md` 头部重写为新定位。
- 同步引用：`docx/index.md`（目录职责表、目录结构、技术栈表、阅读路径）、`AGENT.md`（§4 事实源表、§5 目录地图、§7）、`README.md`（目录、文档链接）、`docx/arch/decisions.md`、`docx/arch/v1/modules.md`。

## 没变什么

- guide 内文档内容与模块化目录结构（00-总览 … 90-附录）原样保留，模块间相对链接因整体搬迁依然有效。
- v0.1.0 的 dev/explain 历史文档中提及 docs/ 的表述保留原样（历史记录不改写）。
- git 历史：使用 `git mv`，文件历史可追溯。
