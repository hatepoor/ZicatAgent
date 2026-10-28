# v0.1.1 开发进度

> 对应架构版本: v1
> 最后更新: 2026-10-28

## 本版目标

Web TUI 前端：把 `terminal-zizicat-tui/` 的视觉设计参考落成真实前端（`ui/`），复用其 React 组件与主题，接真实内核数据源；同时把 RPC 事件协议结构化（`kind` 字段），为所有前端提供结构化事件。

> v0.1.0 的 `06-质量与工程/task5 真实烘跑与版本验收` 仍 ⬜，待真实模型验收后 v0.1.0 才收尾；本版为插队的前端专项，不阻塞该任务。

## 模块进度总览

| 编号 | 模块 | 进度 | 依赖 | 备注 |
|------|------|------|------|------|
| 01 | [TUI前端](./01-TUI前端/todolist.md) | ✅ | v0.1.0（05-交互前端） | 全部 task 完成（真实任务验收通过） |
| 02 | [Loop修复](./02-Loop修复/fixes.md) | ✅ | 01 | FIX-1~4 全部完成 |
| 03 | [memory重构](./03-memory重构/refactor.md) | ✅ | 02 | FIX-M1 完成 |
| 05 | [功能补全](./05-功能补全/todolist.md) | 🔧 | 03 | A 组 5 项完成（沙箱/model/归档/英文/FIX-S）；B 组额度项与 C 组暂缓项见 todolist |
| 06 | 文件工具增强 | ✅ | 05 | grep/glob/file_apply_patch + 原子写/编码/路径边界；96 tests OK |
| 07 | 会话/模型/工作空间/渲染 | ✅ | 06 | /new 真新建、左侧历史、summary、模型/工作空间、Markdown+LaTeX、工具折叠、上下文统计、会话/工作区删除；116 tests OK |
| 08 | [运行性能与思考模式](./08-运行性能与思考模式/00-诊断与修复计划.md) | 🔧 | 07 | CPU+memory、`/effort` 选择页、DeepSeek 接口、thinking 折叠/历史回放已完成；待真实 UI 验收 |

## 进度日志

### 2026-10-28
- 📝 08/运行性能与思考模式诊断：定位 memory 写放大（FTS 触发器无 WHEN、每条命中一个写事务、L1 连接泄漏）、CPU 高（前端逐 token 重渲染 + 1Hz 整树刷新 + 后端逐 token 转发/checkpoint）、/effort 与 thinking 缺口（配置白名单缺失、langchain_openai 丢弃 reasoning_content、RPC/UI 无 thinking 协议）；已确认 /effort 档位 off/low/medium/high/max、thinking 实时+历史回放、本轮先 CPU+memory；见 `08-运行性能与思考模式/00-诊断与修复计划.md`。
- ✅ 08/CPU + memory 修复：FTS 更新触发器加 `WHEN` + schema v2（access_count 更新不再重建索引）；`touch_many` 单事务、`read_with_meta`、L1 单例、`/memory` 关闭连接；前端 delta 50ms 合批、时钟移入 StatusBar/RightPanel、Rich/EntryView memo；后端 `_DeltaBatcher` 80 字符/40ms 合批并移除 `tok_buf` 全量拼接。memory_read p50 2.35ms→0.14ms；131 tests OK；`ui` build OK。`memstore.verify` 仍有 6 项迁移前已有漂移（facts/l1_rules + 2 个 manifest 外条目），非本轮引入。
- 🔎 渠道探测：`deepseek/deepseek-v4.1-flash` 非流式/流式均返回 `reasoning_content`；合法 effort=`off/low/medium/high/xhigh/max`，`none`/`minimal` 400；`off` 直接发送即可。`/effort` + thinking UI 留待下一轮。
- ✅ 08/`/effort` 选择页 + DeepSeek 接口：`.env` 新增 `PROVIDER`/`REASONING_EFFORT`；`/mode` 可选 OpenAI Chat Completions / DeepSeek；`/effort` 页面 ←→ 选择、Enter 确认、Esc 取消、当前值高亮；`engine/deepseek.py` 用 `ChatDeepSeek` + tools 场景 reasoning 回传；138 tests OK，`ui` build OK；实测代理流式 reasoning + 两轮工具回传 200。
- ✅ 08/thinking 展示：runner 从 `additional_kwargs.reasoning_content` 发 `thinking_delta`（兼容 OpenRouter `reasoning`，`thinking_seen` 去重）；RPC 映射 `thinking`；前端 `ThinkingBlock` 默认折叠、`.tui-shimmer` 呼吸、`delta/tool_call/done` 切块；`session_history` + `history.ts` 支持 checkpoint 历史回放。144 tests OK，`ui` build OK。真实 UI 验证：DeepSeek + `code_run` 任务，thinking 块出现在工具调用前，展开可见推理文本，状态栏同步 `思考 high`。

### 2026-10-26
- 📐 架构图重绘：`assets/diagrams/agent_loop_v2.drawio`（接入/运行入口 → 会话与系统提示 → prepare→agent⇄tools/human/check→finalize → 状态/检查点 + 能力层；含 Web TUI/RPC、abort 回退、双流事件）与 `assets/diagrams/memory_arch_v2.drawio`（L0–L4、运行时读写、文件↔库运维、目录门牌）；两张 PNG 已导出到 `assets/diagrams/`；旧 v1 两图已删除；结构校验 0 错误。
- ✅ 07/会话/模型/工作空间/渲染：Web TUI 新增模型设置弹层（Base URL/API Key/模型名/上下文/最大输出/temperature，支持新增、保存到 .env、设为当前）与工作空间弹层；`/model`（含 `/mode` 前端别名）打开弹层，`/workspace <路径>` 切换并自动建目录；新增 `--workspace` 启动参数；RPC 增加 get_models/save_model/get_workspace/set_workspace 与 models/workspace 事件；修复斜杠命令多行输出只显示首行、弹层 Esc/遮罩退出、输入框焦点丢失。第二轮：`/new` 真正清空 thread/历史并由前端清屏；左侧新增按工作区分组的历史会话栏（可添加工作区/切换会话）；`<summary>` 内容改为斜体灰色半透明展示并隐藏标签。第三轮：修复 token 流与整段 AIMessage 重复导致回答复制；过滤内部 `[TIPS]` 与工具 JSON 回声；接入 react-markdown + remark-gfm/math + rehype-katex（含表格/代码/LaTeX）；工具块默认折叠并按 status/stdout/msg 结构化展示；上下文百分比改用模型 context_window，显示具体 tokens 与引擎字符预算，且模型窗口换算为引擎预算。第四轮：从 LangGraph checkpoint 回放会话历史（用户/助手/工具条目），切换会话和刷新页面都能恢复；旧检查点缺失的工具结果标注占位；工具块按 body/stdout/msg 结构化渲染（Markdown + 滚动区），并过滤模型复述的工具 JSON 与内部提示。第五轮：右侧统计面板改为宽度/透明度过渡；左侧会话与工作区增加删除入口（悬停显示"删除"），删除前弹窗确认；删除会话清理独占目录文件，共享工作区保留文件；删除工作区清理其下全部会话、检查点与目录文件，并重置当前会话；工具正文/折叠详情提升对比度。全量 116 tests OK。
- ✅ 06/文件工具增强：新增 `grep`/`glob`（ripgrep 优先 + 纯 Python 兜底）与 `file_apply_patch`（Codex 风格多文件/多 hunk/增删移，歧义整单不落盘）；`file_read`/`file_write`/`file_patch` 加编码探测、原子写、写路径与敏感文件拦截；schema 17→20，全量 96 tests OK。基准（Claude-Code 仓库 45MB / 2074 文件）：搜索 1.04s→0.22–0.24s（4.4–4.7x）、glob 1.04s→0.13s（8.3x）、输出字符缩减 24–28%；三处编辑 3 次调用→1 次（1.7x）；正确性校验 844/101/82 条全匹配。证据：`temp/bench/{baseline,post,comparison}.json/md`

### 2026-10-25
- 🔧 06/工具装配 FIX-T：tools/ 新包（registry + 六子包 + ToolContext 显式注入）；zicat.py 704→168 行；schema↔registry 装配完整性测试；全量 68 tests OK；见 06-工具装配/refactor.md

- ✅ 05/task9 FIX-S 会话分离：session/ 库 + session_meta 注册表 + 标题自动化 + 四命令升级；65 tests OK

### 2026-10-24
- 🏗️ memory/ 架构重构 FIX-M1（用户架构评审发起）：目录 11→9（scripts/ 归位、export 只留 L1/L2、资产分离、命名直白化 facts/l1_fallback/l1_template/l1_structure、README 门牌）；库 rename×2 审计留痕；sync/verify/export/兜底/review 全链路验证；56 tests OK；见 `03-memory重构/refactor.md`
- 📐 memory 分层图（初版，已由 v2 取代）：`assets/diagrams/memory_arch_v2.drawio`（四分区：L0–L4 分层 / 运行时读写 / 文件↔库运维 / memory 目录门牌；校验 0 错误）
- 🧠 memory P2 三件（助手直接编写）：export 随 backup 周期化 / memory_patch 8 字探针冲突提醒（24 字探针过特异被测试抓住后迭代）/ L4 蒸馏每 7 天任务化；全量 56 tests OK；见 `explain/v0.1.1/modify/md_memory_p2三件.md`
- 🧠 memory P1 三件（教学模式：用户撰写）：2 字中文 FTS / L1 冷条目折叠（keep=20，存在性编码保留）/ memory_write 同名拦截+summary 必填；修复 render_l1 新代码误插旧循环体的 bug；全量 55 tests OK；见 `explain/v0.1.1/modify/md_memory_p1三件.md`
- 🔤 Goal Hive 全局更名 Goal Team：/hive→/team 命令、SOP 文件与记忆库条目改名（rename 审计留痕）、L1 模板/morphling 交叉引用、docx 全层与 README/AGENT 同步；词边界替换防 archive 误伤；sync/verify/export 全链路 140 项 0 失败；见 `explain/v0.1.1/modify/md_hive改team重命名.md`
- 🗜️ FIX-4 checkpoint 存储治理落地（教学模式：用户撰写源码）：压缩 serde（lzma，≥4KB 首字节标记，旧格式兼容）+ retention（保留最近 20 份/双表清理/VACUUM 阈值）+ 收尾挂接（挂起保护）；全量 52 tests OK，MINI 真实链路验证；详见 `02-Loop修复/fixes.md`

- 🧪 **长上下文折叠压力复测（补 70% 目标）全通过**：驱动加 `LONGCTX_CAP` 参数把视图预算降至 30k（60k 文档读入后消息量达阈值的 **222%**，远超 70% 目标），5 轮真实执行零 APIError；每轮真实折叠 9 条，三项引擎修复指标 5/5 轮全绿——任务锚点保留（`view_has_task`）、最新摘要保留（`summary_keeps_latest`）、视图开头无孤立 ToolMessage（整轮成组折叠）、工作记忆块在位、视图字符收敛至预算内（16k-25k/30k）。模型行为质量：轮 2 纯凭工作记忆公式推算第 208/415 条属性，轮 4 重读原文核对**两问全对**（15 条工作记忆 12 条延续、3 条自修正）——折叠压力下跨轮召回准确性有客观对错验证。MINI 极端参数（cap=8k）另暴露"预算远小于任务需求时折叠诱发重复读循环"的系统性风险（usage 落账修复在该轮正确标记 invalid+error），属边界情形，已记录未修改。证据：`temp/longctx_evidence.json`
- 🧪 **真实测试（最小烘跑，渠道 deepseek-v4.1-flash）全通过**：① `--func` 计算任务——模型链路/prompt 生效（回复头部稳定输出 `<summary>`）；② TUI 桥真实工具任务——结构化事件全链路（3×tool_call[code_run→file_write→code_run]+tool_result+delta+usage+done），模型自发票回读校验，产物 `temp/sandbox_e2e.txt` 落盘 15 行正确；③ interrupt 真实挂起 + abort 放弃路径通过。发现并修复 FIX-3（中断后 done.text 返回旧任务文本，`engine/runner.py` 置空 + 回归单测）；确认 `[ROUND END]` 为 --task/--func 输出协议哨兵（非 bug）。全量 46 tests OK
- ✍️ 系统提示词优化（assets/ 六文件）：sys_prompt 双语加入 agent 名称 zizicat、`<summary>` 独立成条、补 `update_working_checkpoint` 工作记忆条、失败升级口径统一、"能力不推诿/不可逆先请示"消歧；l1_structure 双语 SOP 引用改 `memory_read` 按名为主；l1_template 双语 L3 名单对齐记忆库实际条目（补 salient_mining_sop/goal_team_master_duty/task_planning/keychain 等）；拼装冒烟通过（2700 字符，关键字全部命中）
- 🐛 02-Loop修复：FIX-1 跨进程 resume 丢工作记忆（`resume_pending` 从 checkpoint 回填 `handler.working`，空副本曾反向覆盖持久化数据）+ FIX-2 私密配置迁移 `.env`/dotenv（`mykey_loader` 统一加载，`.env` 模型组优先、mykey.py 非模型配置兼容保留，新依赖 python-dotenv）；全量 45 tests OK；清单见 `02-Loop修复/fixes.md`
- 📐 Agent Loop 架构图（初版，已由 v2 取代）：`assets/diagrams/agent_loop_v2.drawio`（接入/运行入口 → 会话与系统提示 → 图循环 → 状态/检查点 + 能力层；结构校验 0 错误）
- 📁 memory 文档全量核查与清理：判定结论——`memory/` 下**没有可删除的文档**（全部 21 个 kb SOP 均被 memory.db L1 索引/代码/同步链路引用，证据：render_l1 输出 + 全仓库引用扫描）；`review_inline_prompt` 中英对为功能性双语资产（`core/review.py` 按 `ZICAT_LANG` 加载），保留；唯一英文且有用的 `kb/ultraplan_sop.md`（181 行纯英文）按用户规则翻译为中文（代码块/archetype 术语/边界语句原样保留，结构逐项一致：标题层级、行数、代码块、术语计数全部对齐）；已 `memstore.sync`（更新 1 条）+ `verify`（140 项 0 失败）+ 刷新 export 快照 + 运行时 `memory_read` 冒烟确认中文生效；全量 42 tests OK
- 📁 文档体系合并：`docs/` 整体并入 `docx/guide/`（导读层），docx 成为单一文档体系（guide/arch/dev/explain 四层）；见 `explain/v0.1.1/update/up_文档导读层guide.md`
- ✅ 01-TUI前端：全部 task 完成（真实任务验收通过，含 FIX-3 修复）
