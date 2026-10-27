# zicatAgent UltraPlan SOP
## 1. 协议：启动与续跑
### 这是什么
UltraPlan 是用 Python 脚本编排的多 agent 协作模式。主 agent 负责设计阶段、prompt、fan-out/fan-in 与停止/继续决策；子 agent 负责面向任务的实际工作。
### 仅显式启用
只有用户明确说出 `ultraplan`、`UltraPlan` 或 `ultraplan 模式` 时才启动。未启用就不启动，至多提一句它存在。
### 第一步动作
一旦启用，下一个实质动作就是编写并运行第一个脚本。
在第一次 `plan(...)` 之前，不得为任务本身去查看源码、测试、日志、import、文件列表、页面或 API。
启动前允许做的：记录目标/约束、确认 cwd 是 zicatAgent 的 `temp/`、写最小脚本。
### 文件与 cwd 契约
脚本是 zicatAgent `temp/` 下的普通 Python 文件；运行时 cwd = `temp/`。
从 `temp/` 引用仓库文件，如 `../assets/...`；绝不把 UltraPlan 脚本放进仓库代码树。
每个脚本以真实 API 契约和共享产物目录开头：
```python
import os, sys
sys.path.append("..")
from assets.zicat_ultraplan import plan, phase, parallel, mapchain
RUN_DIR = os.path.abspath("ultraplan_<stable_slug>")
plan(RUN_DIR)
ARTIFACT_DIR = RUN_DIR
```
`plan(...)` 必须是第一条 UltraPlan 语句；允许在它之前定义 `RUN_DIR`。若 import/plan 失败，只排查 cwd/路径/import/守护进程启动，不去排查用户任务。
### 同计划续跑
对同一个用户目标，后续每个脚本都复用完全相同的 `RUN_DIR` 与 `plan(RUN_DIR)`。
第 2/3/…轮是同一 plan/工作目录下的新脚本，不是新 plan。续跑只改变阶段/prompt/原型（archetype）。
脚本跑完不等于任务完成：读 reducer/报告路径，然后回答、询问、应用已完成的结果，或启动下一个同计划脚本。
### 委派边界
不要在 UltraPlan 之外解题。不要在主对话里做任务发现、实现、评审或验证。
主 agent 只能为了监督和决策下一个脚本而读输出。
一个目标只有一个 agent 是 UltraPlan 编排者。编排者可以读本 SOP；不得让普通 worker 去读 UltraPlan SOP、启动 UltraPlan、设计阶段或再委派。
如果编排者本身是子 agent，只给它目标、约束、输出预算和使用 UltraPlan 的许可；不要粘贴 SOP、指定阶段、告诉它读哪些 SOP 文件。由它自己选择读什么上下文。
Worker prompt 是工单，不是迷你 SOP：角色、精确范围、输入、允许/禁止的动作、证据、简短输出形态、停止条件。
每个 worker prompt 在相关时必须带上边界语句：`Do not start UltraPlan. Do not delegate. If decomposition is needed, report blocker only.`

## 2. 核心心智模型
### 为什么要编排
假设一个强单执行者能处理长文档、复杂代码和连贯的多文件修改。不要因为工作"看起来大"就编排。
编排主要是为了控制遗漏：漏掉的条目、角度、假设、证据、检查或剩余改进。Hunt 是特殊的硬搜索场景：一次直接尝试可能走进许多死胡同，才出现可行的证明/根因/方案。
### 三个决策
1. 问题类别：Explore、Sweep、Hunt 还是 Improve。
2. 遗漏风险：未知清单发现，还是已知清单认领。
3. 拓扑：单执行者、并行宽度、阶段/循环深度、流水线、屏障、reducer。
### 并行只用于控制遗漏
仅两种情况使用并行：
- 未知清单发现：条目清单未知；按有意义的搜索透镜、路径、证据源、表示方式、失败模式或反例切分。证据源可包括本地代码、日志/测试、实际复现、用户产物，以及当外部生态知识可能揭示已知问题、API 限制、历史事故或平台约束时的 web/Google 调研。
- 已知清单认领：条目清单已知、相互独立且规模适合 AI；分配归属，保证没有条目被漏掉。
不要并行化连贯执行。任务清晰、有界、连贯、在单个强 agent 舒适区内时，用一个执行者。
### 宽度 vs 深度
并行宽度：独立角度/条目可能暴露不同的遗漏。
阶段/循环深度：后续搜索依赖前面的发现、归约、验证或死胡同。用阶段/循环做 发现 -> 去重/排序 -> 验证/反驳 -> 搜索残余，直到枯竭。
### 按主要风险选择
Explore：空间未知；风险是漏角度/漏条目。
Sweep：已知独立清单；风险是漏条目/漏状态。
Hunt：根因/方案/证明未知或困难；风险是走错路/死胡同。
Improve：已有产物；风险是执行后的残余缺陷/机会。
Design/Integrator 是辅助动作：design 契约防止并行产出发散；integrator 在并行工作后恢复全局一致性。

## 3. 工具语义与输出纪律
`phase(name, desc="")` 是可见结构。给当前原型和 reducer 边界命名。
`parallel(tasks, max_workers=None, **data)` 运行相互独立的任务，按输入顺序返回结果路径。默认并发由引擎决定；没有真实理由时在示例中省略 `max_workers`。
任务形态：元组/列表 `(desc, prompt)`，或含 `desc`、`prompt`、`data`、`llm_no`、`timeout` 的字典。
子 agent 调用返回 `.out.txt` 路径。后续 prompt 应引用路径，让 worker 只读自己需要的内容/尾部。
`mapchain(items, step1, step2, ...)` 对每个条目顺序执行各步、条目间并发。`{item}` 是原始条目；`{previous}` 是上一步结果路径。
阶段之间的 `parallel(...)` 是屏障。只有下一阶段需要跨结果去重、排序、共享上下文或提前退出时才用它。若每个条目能独立推进，用 `mapchain`。
Worker 默认返回纯文本而非 JSON，但必须可被 reducer 读取：稳定 ID、证据路径/引用、结论/状态、风险、下一步动作。
简洁规则：在实用的前提下尽量短。主对话只报告状态、阻塞、下一步。Worker/reducer/verifier 包含必要证据，不加填充。
禁止凑字：不写背景长文、不复制 prompt、不复述 SOP、不写思维链散文、不写无依据的印象、不写含糊的 `done`。
Reducer 做比较而非拼接：接受、拒绝、去重、排序、暴露矛盾、说明覆盖边界、建议 停止/继续/下一个原型。

## 4. Prompt 契约
Worker prompt 必须无需追问即可执行。
写明：角色、精确范围、输入路径/条目、产物目录、允许的来源/工具、证据标准、简短输出形态、停止条件与排除项。允许 web/Google 搜索时要显式说明；要求给出 URL/来源名，区分"有来源的事实 / 本地证据 / 假设"，并把每个外部发现映射到某个任务假设、判别器、缓解措施或验证步骤。
重叠有害时，告诉 worker 不要做什么。告诉 verifier 是要确认、反驳、复现、比对还是检查本地格式。
优先给文件路径，不粘贴长上下文。只给该 worker 需要的状态。
若 worker 会创建/编辑文件，要求保存在 `ARTIFACT_DIR` 下并返回路径。
有风险或不可逆的操作，除非用户已批准，prompt 必须要求先停下请示。

## 5. 原型（Archetype）
### Explore
空间未知、过早选一条路会给任务带来偏差时，用 Explore。
按透镜扇出，不按伪依赖切分：架构、失败模式、数据/证据源、约束、用户意图、外部 web/官方/论坛证据、复现路径、反例路径、测试面、风格风险。仅当外部知识可能改变地图时才用 web 搜索；禁止泛泛的背景调研。
每个 explorer 返回：透镜、覆盖范围、发现/前沿、证据、未知项、死胡同。
Reducer 构建地图：已接受的事实、已拒绝的断言、有前景的前沿、缺失的透镜、矛盾、下一个原型。
当 reducer 能点名一个有界的 Execute/Hunt/Improve/Sweep 时，Explore 停止。
调研/报告类任务通常从素材收集 + 多研究路径 Explore 开始；把收集的素材存成文件，再综合成报告并对报告做 Improve。工程/调试任务里，web 调研只是一个喂给 reducer 的收集透镜，除非用户要的就是调研报告，否则它不是最终产物。
### Hunt
根因不确定、高风险断言要验证、或方案/证明难找时，用 Hunt。
典型流程：收集证据面 -> 综合事实/时间线/矛盾 -> 生成多元假设/路径 -> 按证据/价值/成本/可验证性排序 -> 验证选中的候选。
按不重叠的刀刃或证据源扇出：本地代码/静态路径、日志/报错/测试、复现行为、近期改动、依赖边、外部 web/官方/论坛证据、约束、怪角度、换个表示方式、反例。当本地证据可能缺失已知生态/平台故障时用 web 调研；必须返回带引用的机制与判别器，不是背景长文。
每个 hunter 返回：候选/路径 ID、证据、置信度、为何独特、为何可信、如何验证、死胡同。
只有在已有已知独立假设清单之后，验证才变成 Sweep。
全部尝试失败时：记录被否决的路径、排除重复、换刀刃/换表示、再 Hunt。死胡同也是进展。
### Improve
已有产物要修复、简化、优化、重写、润色或在多方案中抉择时，用 Improve。
Improve 是外层循环，不是一次编辑：找机会/残余风险 -> 归约/排优先级 -> 执行选中改动 -> 验证/测试 -> 搜索残余 -> 重复。
不要用机械的固定透镜开局。先问"对这个产物，什么遗漏是重要的"，再只在"每个透镜都能独特地发现某类问题"时选择搜索透镜。
小/强耦合/连贯的工作默认单 AI 执行者。已知独立条目清单才 Sweep；原因/选项未知则 Hunt。
例：单文件/连贯重写，用一个执行者，然后跑真实测试（见"验证形态"：发现既有测试/演示/CLI 用法，或构建最小但真实的测试，不是只 import 的冒烟），再可选地用未知清单发现找剩余回归、风格问题或漏掉的简化。
执行后必须验证。覆盖不确定时用阶段/循环深度：找可信的未测失败 -> 去重/排序 -> 验证/反驳 -> 搜索残余直到枯竭。并行宽度只用于彼此不同的发现透镜。
重要改动用对抗式验证：让 worker 反驳结果，而不是仅仅同意。
直到没有实质改进、或剩余条目极小/不安全，才停。
### Sweep
条目清单已知、条目真正独立、覆盖/状态重要时，用 Sweep。
经典案例：下载游戏 A/B/C/D。每个条目有自己的搜索/下载/验证路径；并行认领防止漏掉 D、隔离阻塞。
每个条目能独立推进时用 `mapchain` 做 检查 -> 行动 -> 验证。
每个条目报告：条目 ID、动作/结果、证据、状态、未解决风险、跳过条件、阻塞。
Reducer 报告：总数、已覆盖、已省略、失败、接受的发现、拒绝的发现、覆盖边界。
不要把任何大数据集都叫 Sweep。12,000 行相关数据要分析，通常是一个数据分析执行者/脚本，不是 12,000 个 AI worker。Sweep 用于 AI 规模的独立条目，通常几个到几十个；海量独立批次，先抽样/试点，再用脚本/分片并写明边界。
多个条目以相似方式失败时，归约失败、转 Hunt 找共同原因；单个条目难，就把该条目变成一个 Hunt。

## 6. 组合规则与边界情况
### 并行构建前先设计
独立产物需要共享风格/术语/格式时：先 Explore/Design 一个紧凑契约，再 Sweep 构建，最后一个 integrator 统一。
例：给 12 个独立文档页加 Troubleshooting 节。先契约；各页 worker 按契约写；integrator 统一风格并抓幻觉。
但每单元改动小、整体高连贯的产物通常仍走单执行者。例：给 40 页 PPT 每个非标题页加一句结论；叙事连续性是全局的，由一个执行者写。Sweep 只适合局部检查，如漏句、溢出、排版错误。
### 验证形态
验证不总是 Sweep。单一连贯产物的验证常用未知清单发现：找可能的问题、归约、验证/反驳、再搜残余，直到没有实质问题。
只有当不同透镜能发现不同遗漏时才并行验证。否则用一个 verifier 加真实测试。
验证透镜按证据源解耦，不按同一方法的子清单切分。把一次静态阅读拆成"查 API、查一致性、查副作用"是伪并行：同方法、同文件、输出重叠。真正独立的来源通常是：静态分析（读代码，不运行）、真实执行（跑真实测试）、质量对意图（是否达成任务目标，如更简/更干净）。只有当某个透镜的证据源确实不同时才开并行透镜。
真实执行必须是真的，不是只 import 的冒烟。以发现真实破坏为目标，不以便宜完事为目标。执行者先发现既有入口（测试套件、示例/演示脚本、README/CLI 用法、可调用的公共 API）并运行相关的；若都不覆盖改动，就构建最小但真实、能触发改动行为的测试。记录确切命令与 stdout/stderr/堆栈。绝不为没实际运行过的行为报告 pass；标注 blocked 并给出具体原因（如需要活动窗口/GPU/网络）与解锁条件。
Sweep 验证适合已知的局部独立检查：每个文件有要求的日志格式、每页幻灯不溢出、每个下载的游戏能打开。
高风险断言用 Hunt 式验证：收集证据、生成替代解释、验证/反驳，覆盖不足就阻止自信的回答。
### 调研/报告形态
调研通常不是原生原型。用收集/探索拿素材、并行路径跑不同搜索策略、一个 reducer/合成者写报告，再 Improve 消除合成伤疤、空缺、弱证据与风格问题。
最终对话总结产出了什么、文件/素材在哪，不粘贴大段收集内容。
### 多轮续跑
下一阶段依赖归约结果时，不要写一个巨型脚本。
每个脚本之后，只读决策所需的 reducer/报告输出：回答、询问、应用已完成结果，或启动下一个同计划脚本。
下一个脚本的原型由 reducer 决定：地图仍未知选 Explore、有候选选 Hunt、产物已选定选 Improve、条目已知选 Sweep、高风险断言选 Verify。
绝不因为第一个脚本跑完就在 UltraPlan 之外重启或重命名 plan；只有换了用户目标才重命名。

## 7. 规模、失败与边界
按请求定规模。快速检查用小扇出；全面审计用更宽的刀刃、更强的验证与显式覆盖边界。
优先用引擎默认并发。prompt 重叠时加更多 agent 只会更糟；先改分解，再调执行参数。
有风险或缓慢的探测用 `timeout`，并要求 worker 报告部分进展。
若有抽样、top-N、限时、跳过重试、排除某子系统或工具失败，必须在 reducer 输出与最终回答里写明边界。
Worker 失败时：读它的 `.out.txt` 或错误路径，然后用更窄范围、更长超时、换工具或换原型重试。不要原样重发失败的 prompt。
Reducer 暴露矛盾时，发起针对性验证，用证据解决冲突。
覆盖太弱时不要自信作答；再跑一个同计划脚本，或让用户在成本/覆盖之间选择。

## 8. 经典模式
把它们当识别锚点，不当死模板：
1. 改进既有产物/代码：Improve 循环。执行连贯时一个执行者改；随后跑真实测试（发现既有测试/演示/CLI 用法或构建最小真实测试，不是只 import 的冒烟）；只在找剩余回归、漏掉的简化、风格问题或弱测试时用未知清单发现；重复直到枯竭。
2. 根因/不安全结论：Hunt。先收集证据（面窄用单收集者；只有证据源彼此不同才并行收集）-> 综合 -> 找假设/反例 -> 验证/反驳 -> 记录死胡同，未决则继续。
3. 大量已知独立交付物：Sweep。例：下载 A/B/C/D 游戏。每个条目有人认领，因为顺序执行常漏条目；各条目方法可不同。Reducer 跟踪状态/阻塞。
4. 大规模相关数据：不按行 Sweep。12,000 行要分析是一次连贯的数据分析执行；只对独立的 AI 规模子集或残余问题用 Sweep。
5. 调研/报告：只因素材可能漏才对不同搜索路径/来源并行；一个写作者/integrator 合成；然后 Improve 搜证据空缺、合成伤疤、风格问题与缺失视角。
6. 跨少量文件的简单连贯代码改动：一个执行者可完成；只对已知局部检查（如每文件日志格式）加 Sweep，可选再做风格/测试残余发现。
7. 单文件或高连贯产物的验证：不 Sweep。用测试 + 未知清单问题发现；只有不同透镜能发现不同遗漏时才并行。
8. 先设计后 Sweep 构建：条目独立但风格必须一致时，先 Explore/Design 契约，再 Sweep 各条目，最后一个 integrator 统一。
9. PPT/叙事性结论编辑：连贯性优先，通常一个执行者写；Sweep 只做局部排版/格式检查，跨页叙事重要时不逐页派写。

## 9. 最小形态
```python
BOUNDARY = "Do not start UltraPlan. Do not delegate. If decomposition is needed, report blocker only."
ART = f"Save any artifacts under {ARTIFACT_DIR}; return paths."

with phase("Improve coherent artifact", "single executor -> real tests -> residual search"):
    result = parallel([("Executor", f"Apply the focused change. Keep coherence. Run real tests: find existing tests/demos/CLI usage and run them, or build minimal real ones; record commands and output; do not claim pass for unrun behavior. {ART} Return evidence/blockers. Be concise. {BOUNDARY}")])[0]

with phase("Find residuals", "only if coverage is uncertain"):
    # Fill only meaningful lenses; leave empty for one verifier.
    residual_lenses = []
    residuals = parallel(residual_lenses) if residual_lenses else parallel([
        ("Verifier", f"Inspect {result}. Find blockers/residuals only. {ART} Return evidence and stop/continue. Be concise. {BOUNDARY}")])

with phase("Reduce/decide", "dedupe, verify/refute, continue/stop"):
    next_move = parallel([("Reducer", f"Use {result} and {residuals}. Return accepted/rejected, artifact paths, evidence, next action. Be concise. {BOUNDARY}")])[0]

with phase("Hunt", "evidence -> hypotheses -> verification plan"):
    evidence = parallel(evidence_collectors)  # each collector prompt includes ART and BOUNDARY
    hypotheses = parallel(hypothesis_blades) # each hunter prompt includes ART and BOUNDARY
    ranked = parallel([("Reducer", f"Use {evidence} and {hypotheses}. Rank candidates and verification steps. Return artifact paths. Be concise. {BOUNDARY}")])[0]

with phase("Sweep known independent items", "per-item ownership and status"):
    reports = mapchain(items,
        ("Inspect {item}", "Inspect only {item}. Save artifacts under {artifact_dir}; return paths, ID, evidence, action, risk. Be concise. " + BOUNDARY),
        ("Act/verify {previous}", "Use {previous}. Save artifacts under {artifact_dir}; return paths, ID, status, evidence, blocker. Be concise. " + BOUNDARY),
        artifact_dir=ARTIFACT_DIR)
```
