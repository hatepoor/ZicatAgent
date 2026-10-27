# md · 会话/工作区分离（FIX-S）

> 版本: v0.1.1 · 类型: modify · 日期: 2026-10-25

## 变了什么

- **会话库迁址**：`temp/graph.db` → `session/graph.db`（temp 恢复"可随时清理"语义；清 temp 不丢会话）
- **注册表**：`session_meta` 表（thread_id 主键 / title 唯一 / workspace_dir / status）+ 新模块 `core/sessions.py`
- **标题自动化**：新会话链首任务标题 = 用户第一句话前 10 字（smart_format，查重加 _2/_3）
- **目录绑定**：每个会话独立产物目录（`temp/<标题>/`）；handler cwd 与 tools 的相对路径全部跟随注册表
- **命令升级**：/threads 人话标题列表；/resume 按标题/前缀（翻译回 thread_id，多命中列候选不猜）；/new 显式开新会话；/del 删对话与检查点（产物目录保留单独确认）
- **跨盘支持**：--workspace / graph_config.workspace 可指定任意路径（含 D 盘），sys_prompt 相对路径提示随 workspace 注入

## 验证

单测 ×4（标题查重/兜底/删除/库分离）；端到端冒烟 4 步；全量 65 tests OK；verify 138 项 0 失败
