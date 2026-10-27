# Agent Loop（legacy，已删除）

> 文档索引：[docs/README.md](../README.md)
>
> **注意**：本文描述的是已按 P5 删除的 legacy 手写引擎（`agent_loop.py` / `llmcore.py`），
> 仅作历史参考。当前 LangGraph 循环见 [docs/85-引擎迁移/10-引擎改造设计](../85-引擎迁移/10-引擎改造设计.md)。

主循环的四层分工、一轮的完整时序、退出语义。

---

## 四层分工

| 层 | 文件 | 职责 | 行数 |
|---|---|---|---|
| 引擎 | `agent_loop.py` | 轮次推进、工具调度、退出判定 | 132 |
| 调度器 | `agent_loop.py: BaseHandler.dispatch` | 把工具名反射成 `do_<name>` 方法 | 13 |
| 处理器 | `zicat.py: ZicatAgentHandler` | 9 个工具实现 + 每轮 prompt 组装 | ~310 |
| 会话 | `llmcore.py: *Session` | HTTP、历史、裁剪、重试 | ~1270 |

关键点：**`agent_loop.py` 完全不知道有"工具"是什么**。它只认 `do_<tool_name>` 这个方法名约定（`agent_loop.py:19`）。加工具 = 在 handler 里加一个 `do_xxx` 方法 + 在 schema json 里加一条描述，没有任何注册表。

## 一轮的完整时序

以"模型决定调用 `file_read`"为例，逐行对应：

```python
# agent_loop.py:50
while turn < handler.max_turns:            # max_turns=180（agentmain.py:201）
    turn += 1
    if turn % 10 == 0: client.last_tools = ''      # :56 逼客户端重发完整工具协议
    response = yield from client.chat(messages, tools_schema)   # :59 流式输出

    if not response.tool_calls:                    # :69 模型没调工具
        tool_calls = [{'tool_name': 'no_tool', 'args': {}}]

    for ii, tc in enumerate(tool_calls):           # :74 一轮可并行多个工具
        gen = handler.dispatch(tool_name, args, response, index=ii, tool_num=len(tool_calls))
        v = next(gen)                              # :83 第一次 yield = 给人看的进度
        outcome = (yield from gen)                 # :85 后续 yield = 流式进度
        if outcome.should_exit:  exit_reason = {'result': 'EXITED'}; break     # :89
        if not outcome.next_prompt: exit_reason = {'result': 'CURRENT_TASK_DONE'}; break  # :91
        next_prompts.add(outcome.next_prompt)      # :97
    next_prompt = handler.turn_end_callback(...)   # :101 合并 + 摘要 + 纪律注入
    messages = [{"role": "user", "content": next_prompt,
                 "tool_results": tool_results}]    # :103 ← 只递增量！
```

这 30 行里有 5 个决定成败的设计：

### ① 循环不持有历史

`agent_loop.py:103` 的注释写得很直白：`# just new message, history is kept in *Session`。

每一轮 `messages` 都被**重置为一条增量消息**。真正的对话历史在 `client.backend.history` 里（`llmcore.py:680`、`:723`、`:875`）。这么做的好处：

- 循环无状态 → 可被任意前端复用（CLI、桌面、IM 机器人共用同一套循环）；
- 上下文策略集中在一处（`llmcore.py`）→ 换模型/换压缩策略不动循环；
- 每轮只传增量 → 循环本身没有 token 开销，开销全在 session 的可控预算里。

代价：**你必须自己把"该让模型看到的东西"塞进 `next_prompt`**。这就引出第 ②。

### ② 每步重锚：`next_prompt` 是"下一轮的燃料"

工具执行完，不是简单回一句"成功了"，而是由 handler 重新拼一段结构化 prompt（`zicat.py:537-547`）：

```
### [WORKING MEMORY]
<earlier_context>...（>30 条历史且 turn%4==1 时才有）</earlier_context>
<history>...最近 30 条摘要，只有奇数轮注入...</history>
Current turn: 7
<key_info>...工作便签，每轮都有...</key_info>
```

这段东西会作为下一轮 user 消息的主体发给模型。也就是说：**模型不是"记得"上下文，而是每一轮都被重新告知一次它该记住什么**。

这是 ZicatAgent 和"纯靠长上下文硬扛"的框架最本质的区别。它的上下文是**每轮重新构造**的，而不是单调增长的。

### ③ StepOutcome 只有三件事

```python
@dataclass
class StepOutcome:              # agent_loop.py:6-10
    data: Any                   # 回灌给模型的 tool_result
    next_prompt: Optional[str]  # 下一轮的用户消息主体
    should_exit: bool           # 是否终止任务
```

三种退出/继续的语义（`agent_loop.py:89-93`）：

| 返回值 | 引擎行为 | 谁这么用 |
|---|---|---|
| `should_exit=True` | 立刻 EXITED，跳出 | `ask_user`（`zicat.py:336`） |
| `next_prompt` 为空 | CURRENT_TASK_DONE，跳出 | `no_tool`（`zicat.py:507`） |
| 两者都有 | 继续下一轮 | 其余 8 个工具 |

注意 `data` 和 `next_prompt` 是**两条独立的回灌通道**：

- `data` → 进 `tool_results`，成为工具结果（原生客户端是 `tool_result` block）；
- `next_prompt` → 成为下一轮 user 消息。

为什么需要两条？因为**同一次工具调用既要"报结果"又要"改行为"**。比如 `start_long_term_update`（`zicat.py:509-521`）：`data` 放 L0 记忆规范全文（这是"结果"），`next_prompt` 放 L1 索引 + 提纯指令（这是"下一步该干什么"）。如果只有一条通道，你就得把两件事拼成一个字符串，模型分不清哪部分是事实、哪部分是指令。

### ④ `no_tool` 是隐式的"我干完了"

模型如果这一轮不调任何工具，引擎自动合成一个 `no_tool`（`agent_loop.py:69`），它做**二次确认**（`zicat.py:468-507`）：

- 空回复 → 要求重试（最多 3 次，`zicat.py:463-466`）；
- 回复被截断（含 `[!!! 流异常中断`、`max_tokens !!!]`）→ 要求重试；
- 工具调用格式坏了（回复以错误的内置工具调用标记结尾，说明模型用错了协议）→ 要求重试；
- **大代码块但没调工具**（`zicat.py:486-505`）：若回复里恰好有一个 ≥50 字符的代码块、且代码块之后没有别的话，就判定为"模型把该执行的东西当讲解输出了"，追问一句"你是要执行还是只是展示？"。这是全仓库最精细的一条行为矫正。

重试计数到 3 次就 `should_exit=True`（`zicat.py:463-466`），防止死循环刷 token。

### ⑤ 一轮可以并行多个工具，靠"预算分摊"防爆

`agent_loop.py:74` 遍历所有 tool_calls，同一轮里多个工具的输出通过 `_tool_num` 分摊长度预算（`zicat.py:291-293`）：

```python
def _get_tool_maxlen(self, l, args, growth_rate=1.0):
    multiplier = 1 + (self.parent.get_ctx_multiplier() - 1) * growth_rate
    return int(l * multiplier / args.get('_tool_num', 1))
```

同时 `_index > 0` 的工具（同轮第二个及以后）会被 `_get_anchor_prompt(skip=True)` 跳过重锚注入（`zicat.py:538`），避免一段工作记忆被重复塞 N 次。

## 每轮收口：`turn_end_callback` 是"心跳 + 纪律 + 干预"三合一

`agent_loop.py:101` 每轮必调，实现在 `zicat.py:549-573`：

```python
def turn_end_callback(self, response, tool_calls, tool_results, turn, next_prompt, exit_reason):
    _c = 去掉代码块和 <thinking> 的正文
    rsumm = re.search(r"<summary>(.*?)</summary>", _c)
    raw = (rsumm.group(1) if rsumm else _c).strip()
    if raw:
        summary = smart_format(raw.replace('\n',''), max_str_len=80)   # 头 40 + ... + 尾 40
        self.history_info.append('[Agent] ' + summary)                # ← 跨轮记忆的原料
    if not rsumm and tool_calls and tool_calls[0]['tool_name'] != 'no_tool':
        next_prompt += "\n\n\n[TIPS] 必须在回复文本中包含<summary>！\n\n"

    if   turn % 175 == 0: 强制 ask_user 汇报进展，禁止盲重试
    elif turn % 17  == 0: 强制 update_working_checkpoint，换策略/回读 SOP
    elif turn % 41  == 0: 强制把关键结论**写成文件**
    elif turn % 15  == 0: 重新注入 <global_memory>（= L0 宪法 + L1 索引全量）

    injkeyinfo / injprompt = parent.extrakeyinfo / parent.intervene 或 task_dir 下的文件
    if injkeyinfo: 追加到 key_info
    if injprompt: 追加到 next_prompt
    跑插件 hook: turn_after
```

四个周期数是**互斥的 elif**，所以一轮只会命中一条。这组数字是全框架最"经验主义"的部分：17 轮提醒存检查点、41 轮提醒落文件、175 轮提醒汇报——本质是给长任务装"心跳"，对抗模型在长程任务中的目标漂移。

`[MASTER]` 通道（`zicat.py:567-570`）是唯一的外部干预入口：父 agent 或用户往 `temp/<task>/_keyinfo`、`_intervene` 写文件，下一轮就会被注入。这是 `--task` 子代理协作模式的底层机制。

## 退出语义全景

| 退出结果 | 触发条件 | 代码 |
|---|---|---|
| `EXITED` | 工具返回 `should_exit=True`（`ask_user`） | `agent_loop.py:89-90` |
| `CURRENT_TASK_DONE` | 工具返回空 `next_prompt`（`no_tool`） | `agent_loop.py:91-92` |
| （无 next_prompt 且有 done hooks） | 执行插件注册的收尾任务 | `agent_loop.py:98-100` |
| `MAX_TURNS_EXCEEDED` | 180 轮耗尽 | `agent_loop.py:106` |

**注意**：`MAX_TURNS_EXCEEDED` 返回时**没有任何"收口/交接"动作**，直接结束。对比之下 `reflect/goal_mode.py` 有专门的预算耗尽 prompt——这是原版一个明确的短板，自己造 Agent 时应该补上。

## "薄循环"的代价与收益

| | 收益 | 代价 |
|---|---|---|
| 循环无状态 | 前端随便接；换模型不动循环 | 必须自己写"重锚 prompt"，写错了模型就失忆 |
| 只有 9 个工具 | 工具描述短（约 5.6KB），省 token | 复杂能力全靠组合，单步效率低 |
| 纯文本协议兼容层 | 任何 OpenAI 兼容端点都能跑 | 解析失败率高，需要 `bad_json`、弱解析等多重兜底（`llmcore.py:1010-1045`） |
| 每轮重发工作记忆 | 抗上下文滑移 | 每轮固定开销（约几百 token） |

---
