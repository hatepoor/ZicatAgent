# 05-功能补全 开发进度

> 编号: `05` · 所属版本: `v0.1.1` · 对应架构版本: `v1` · 最后更新: 2026-10-24
> 来源: 2026-10-24 功能盘点（会话结论落盘）。

## Task 进度总览

| Task | 名称 | 分组 | 状态 | 工作量 | 依赖 |
|------|------|------|------|--------|------|
| [task1](./task1_sandbox.md) | 本地沙箱 sandbox_run | A（纯开发） | ✅ | 实际 0.5 天 | 无 |
| [task2](./task2_model_switch.md) | /model 热切换 | A | ✅ | 实际 0.5 天 | 无 |
| [task3](#task3) | project_mode_sop 归档 | A | ✅ | 实际 10 分钟 | 无 |
| [task4](#task4) | 英文模式端到端冒烟 | A | ✅ | 实际 20 分钟 | 发现并补齐 tools_schema_en.json 缺失 |
| task5 | 多模型故障转移实测 | B | ❌ 砍除（2026-10-25 用户决策：不实测；故障转移代码保留，未来需要再验） | — | — |
| task6 | v0.1.0 task5 完整验收 | B | ❌ 砍除（2026-10-25 用户决策：最小烘跑已通过即视为验收；v0.1.0 收尾按此执行） | — | — |
| [task7](#task7) | token 级真流式 | C | ✅ | 实际 0.5 天 | stream_mode 双流 + 去重 |
| task8 | api_mode='responses' 验证 | C | ✅ 结论：砍除 | 实际 10 分钟 | 实测 404；且发现 api_mode 从未在 llm.py 实现（纯虚假文档配置）——已从模板与 guide 移除 |
| [task9](./task9_session_split.md) | 会话/工作区分离 FIX-S | A | ✅ | 实际 1 天 | 含跨盘工作区支持；temp 分家并入此项 |

## task3 · project_mode_sop 归档

半退役条目（插件已移除）：`memory_archive("project_mode_sop")` + kb 文件标注归档状态 + sync；L1 让位一个索引行。验收：L1 不再渲染该条目、verify 通过。

## task4 · 英文模式端到端冒烟

`ZICAT_LANG=en` 真实跑 `--func` 小任务 + `/review`，验证 sys_prompt_en / l1_structure_en / l1_template_en / tools_schema_en / review_inline_prompt.en 五件套链路。**产出二选一**：链路通过（保留双语维护）或发现漂移严重（评估砍英文模式）。已知风险点：tools_schema 双语漂移（中文加新工具英文未同步）。

## task5 · 多模型故障转移实测

`.env` 配 `ZICAT_OAI_2__*`（deepseek/deepseek-v4-pro，渠道 models 列表现成）→ 人为将主模型名改错 → 真实任务验证 `with_fallbacks` 自动切换 + usage 归属 + TUI 显示。验收：主模型失败后任务不中断、最终 done 正常。

## task6 · v0.1.0 task5 完整验收

真实模型组合场景：① 多轮工具长任务（≥10 轮）② memory_write 落库审计 ③ `/rewind` 实测回退后继续 ④ `/threads`+`/resume` 跨进程恢复。完成后 v0.1.0 可走版本收尾。这是 B 组最大额度消耗项。

## task7 · token 级真流式（暂缓，独立立项）

runner 扩 `stream_mode="messages"` + TUI 适配，打字机从前端伪造变真流式。工程量大不混入本批。

## task8 · responses 协议验证（条件项）

**结论（2026-10-25）**：当前渠道 Responses 端点 404 不支持；且审查发现 `api_mode` 从未在 `engine/llm.py` 实现（纯文档虚假配置）。已执行：mykey_template.py 与 guide 的 api_mode 说明移除。若未来接入支持 Responses 的渠道，需在 llm.py 先实现路由再恢复文档。

## 进度日志

### 2026-10-25（B/C 组执行）

- ✅ task5/6：用户决策砍除（不实测；故障转移代码保留，v0.1.0 收尾按最小烘跑执行）
- ✅ task8：api_mode 探针 404 + 审查发现**从未在 llm.py 实现**（虚假文档配置）——模板与 guide 移除
- ✅ task7：真流式落地——`_consume` 升级双流（stream_mode=["messages","updates"]）：messages 出 token 级增量（kind=delta_token→RPC delta）、updates 出结构化事件；按轮 tok_buf 去重防整段重复；新增 DualStreamTests；桥端冒烟 13 条小增量、done 与拼接一致；TUI/CLI 零改动受益
- 全量 69 tests OK

- ✅ task3：project_mode_sop 归档（L1 让位，verify 137 项 0 失败）
- ✅ task4：英文模式端到端冒烟——**发现 tools_schema_en.json 从不存在**（文档宣称"及 _en"为假），补齐 17 工具英文版后 EN-OK 冒烟精确命中
- ✅ task1：沙箱 sandbox_run 落地（assets/sandbox_header.py 审计钩子 + zicat.do_sandbox_run 双阶段确认 + schema 双语 + prompt 路由句）；单测 ×5 全绿
- ✅ task2：/model 热切换落地（llm index / set_llm_no 持久化 / cli+rpc）；**顺带修复 /cost 历史遗留 bug**（handle 无分支致命令透传模型）
- scheduler 蒸馏派发加 --nobg 跳过（此前首次 check 恒触发烧模型；注意不能 return None 否则吞 TASKS 探针）
- 全量 61 tests OK

### 2026-10-25（task9 FIX-S 会话分离）

- ✅ 会话/工作区分离落地：`session/graph.db`（checkpoint 库迁出 temp）+ `session_meta` 注册表 + `core/sessions.py`（register/set_title/find/list/delete）；agent 新会话链自动注册（标题=用户第一句话前 10 字查重加序号）+ handler cwd 绑定；/threads 人话列表、/resume 标题前缀翻译回 thread_id（checkpoint 读写零改动）、/new /del；CLI 四命令 + HELP 同步
- 修复过程：workspace_of 位置参数误传 title 位、delete 需容错未建表、find 语义确认（精确命中优先返回合理，测试改用前缀断言）
- 端到端冒烟 4 步全过：注册/标题目录 → resume 翻译 → 清 temp 不丢会话 → /del 清理
- 全量 65 tests OK

### 2026-10-24

- 📋 功能盘点落盘：8 项残疾清单 + 沙箱//model 两份方案定稿归档（此前仅在会话中）

### 2026-10-24

- 📋 功能盘点落盘：8 项残疾清单 + 沙箱//model 两份方案定稿归档（此前仅在会话中）
