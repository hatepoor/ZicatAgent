# zicatAgent 用户使用手册

> 面向使用者：怎么启动、怎么对话、slash 命令怎么用。
> 命令表以 `core/commands.py` 的实际实现为准（本手册与之同步更新）；开发文档见 [docx/](../docx/index.md)。

## 一、安装与启动

```bash
# 1. 安装（Python 3.10–3.13，editable 模式）
pip install -e .

# 2. 配置模型：复制模板为 .env，填三项
copy .env.example .env
#    ZICAT_OAI_1__APIBASE=你的 API 地址
#    ZICAT_OAI_1__APIKEY=你的 Key
#    ZICAT_OAI_1__MODEL=模型名
#    （多模型：继续写 ZICAT_OAI_2__*，可故障转移 + /model 切换）

# 3. 构建并启动 Web UI（唯一前端）
cd ui; npm install; npm run build
cd ..; node ui/server.mjs   # 浏览器打开 http://127.0.0.1:8765
```

内核与 UI 共享同一 `.env` 配置与会话数据；`ui/server.mjs` 内部以 `agentmain.py --rpc` 启动内核。

## 二、基本使用

- **直接打字就是给 agent 派任务**，例如：`帮我看看这个仓库的结构并总结`
- agent 会自主调用工具（读写文件、执行代码、操作浏览器、查记忆库）并汇报
- **Esc** 或顶栏「中断」按钮可中断当前任务
- 每轮回复头部的 `<summary>...</summary>` 是该轮摘要（引擎用于上下文压缩，无需理会）

## 三、会话管理

| 命令 | 作用 |
|---|---|
| `/new [一句话]` | **开新会话**。新任务的对话、产物将进入独立目录（`temp/标题/`） |
| `/threads` | 列出所有会话（人话标题 + 时间） |
| `/resume <标题或前缀>` | **恢复指定会话**——下个任务接着它的上下文跑（支持前缀模糊；多命中会列出候选） |
| `/del <标题>` | 删除会话（对话+检查点；产物目录保留，手动清理） |

说明：会话内容存于 `session/graph.db`（SQLite，自动压缩+轮转）；**每个会话的产物文件在其工作目录**（默认 `temp/<标题>/`，可用 `--workspace` 指定任意路径含跨盘）。连续任务不加 `/new` 就延续同一会话上下文。

## 四、Slash 命令全表（20 个）

### 模型与用量

| 命令 | 作用 |
|---|---|
| `/model` | 查看模型配置列表与当前使用哪个 |
| `/model N` | **切换主模型**（N 为序号，1 起；下个任务生效；其余配置自动降为故障转移备胎） |
| `/effort` | 打开思考强度选择页：← → 选择，Enter 确认，Esc 取消；档位由当前接口决定 |
| `/cost` | 查看 token 用量与上下文配置（窗口/最大轮数） |

### 会话与状态

| 命令 | 作用 |
|---|---|
| `/new` / `/threads` / `/resume` / `/del` | 见上节 |
| `/rewind` | 列出对话检查点；`/rewind N` **回退**到 N 步之前（对话时光机） |
| `/memory` | 查看记忆库 L1 索引（agent 知道哪些手册/事实可用） |

### 工作流模式（高级）——附使用示例

这几个命令会让 agent **脱离一问一答、进入自主工作状态**，按"自主程度"从低到高排列：

| 命令 | 一句话 | 自主程度 |
|---|---|---|
| `/plan` | 看计划 / 绑定计划文件 | ★（只读） |
| `/review` | 对当前改动做对抗式评审 | ★（只读） |
| `/cost` | 看 token 花费与上下文配置 | ★（只读） |
| `/goal <目标>` | 单 agent 带预算持续自驱 | ★★★ |
| `/distill <来源>` | 把外部项目的能力"抄"进本仓库 | ★★★ |
| `/autorun` | agent 自己找活干 | ★★★★ |
| `/team <目标>` | 组建多 agent 团队协作 | ★★★★★ |

**`/goal` —— 给目标 + 预算，agent 自己拆解执行**

```text
/goal 调研 2027 年秋招后端岗要求，整理成对比表，预算 30 分钟
```
agent 会持续自驱：查资料 → 整理 → 写报告 → 检查残差，直到预算用尽或目标达成。适合"开放目标 + 你不想盯过程"的场景。查看进度：`temp/goal_state.json`。

**`/team` —— 组建多 agent 团队（额度消耗大，慎用）**

```text
/team 把 docs/ 下所有文档翻译成英文并保持术语一致
```
agent 会自动：起一个 BBS 消息板 → 拉起 1 个 Team Master（只调度不干活）+ 2~5 个 worker（领单干活）→ Master 持续拆任务/验收直到完成。适合"大量可并行的独立子任务"。**注意**：每个 worker 都是真实进程消耗额度，一般任务用 `/goal` 就够。

**`/distill` —— 让 agent "偷师"外部项目（原 /morphling）**

```text
/distill https://github.com/xxx/yyy       # 吞噬一个 GitHub 项目
/distill D:	ools\某工具                  # 或本地路径
```
agent 会研究目标项目：抽取它的核心能力与测试用例 → 选择"直接调用 / 重写 / 复刻"→ 最终让本仓库在同样的测试上达到同等能力，并沉淀成自己的 SOP。适合"看到一个好工具想变成自己的"。

**`/autorun` —— 无人值守自主模式**

```text
/autorun
```
agent 读 TODO/历史，**自己选一条最有价值的任务**执行并写报告到 `temp/autonomous_reports/`。适合"放着让它自己提升"。

**`/scheduler` —— 后台定时服务管理器（给 agent 配闹钟）**

```text
/scheduler                            # 看有哪些服务、哪些在跑
/scheduler start scheduler            # 启动定时任务引擎
/scheduler stop scheduler             # 停掉
```
启动后：`sche_tasks/` 下放任务 JSON（如 `{"enabled":true,"schedule":"09:00","repeat":"daily","task":"每天早报"}`），到点 agent 自动执行；同时每 12h 自动归档 L4 会话、每 24h 自动备份记忆库。**这些自动化是 memory 治理闭环的载体**。

**`/update` —— 更新仓库**

```text
/update 修一下 README 的错别字
```
从 git remote 拉取更新并报告影响面（合并前会先说明）。

### 评审

| 命令 | 作用 |
|---|---|
| `/review [范围]` | **对抗式代码评审**（默认审 git diff；报告直接输出到对话） |
| `/review 审 core 目录下所有改过的文件` | 按描述指定范围 |

### 其他

| 命令 | 作用 |
|---|---|
| `/help` | 显示命令帮助（同本表） |
| `/continue` | 列出 graph 会话（同 `/threads`） |
| `/exit` / `/quit` | 退出（Web UI 中被拦截，用顶栏退出按钮） |

## 五、记忆系统速览

- agent 的"知识"存于 `memory/`：**kb/ 下的 21 本 SOP 手册**（怎么写代码评审、怎么跑浏览器、怎么组织多 agent……）+ `scripts/` 的可执行技能
- agent **每轮都能看到手册目录**（L1 索引），任务需要时会自动按名取用——你不需要背诵这些手册
- 你也可以让它沉淀知识："把这次的经验写成 SOP 存进记忆"——它会走 `memory_write` 入库（带版本审计）
- 手册文件可直接编辑（改完 `python -m memstore.sync` 入库）

## 六、常见问题

- **Q：怎么换模型？** → `.env` 加 `ZICAT_OAI_2__*` 新配置后 `/model 2`；或直接改 `.env` 的 1 号配置（热重载）
- **Q：会话产物在哪？** → `temp/<会话标题>/`（或你 `--workspace` 指定的目录）
- **Q：想彻底重开会话？** → `/new`；想删干净用 `/del` 后手动清理产物目录
- **Q：任务跑偏了怎么救？** → Esc 中断 → 用 `/rewind N` 回退到之前的状态 → 补充说明重新派任务
- **Q：`code_run` 和沙箱的区别？** → `code_run` 直接操作你的机器（本地开发用）；`sandbox_run` 是护栏环境（写删仅限沙箱目录、默认禁网），agent 在调研计算类任务会自动选它

## 七、命令变更记录

- 2026-10-25：`/hive` 更名 `/team`；新增 `/new` `/del` `/model`；`/resume` 支持标题与前缀
