# FIX-T · 工具装配重构方案（tools/ 包 + 显式注册表）

> 状态: ✅ 已执行并验证 · 实际 1 天
> 来源: 用户判定"工具装配乱着放、高耦合"。目标形态：按类别分子包、schema↔实现显式注册、新增工具只碰 1+1 个文件。

## 一、现状诊断（先承认问题在哪）

**zicat.py（704 行）一个文件装了四类东西**：

1. 17 个工具的 `do_*` 实现（code/sandbox/file/browser/session_ctl/memory 桥混排）
2. 工具的支撑函数（`code_run` 执行器、`web_scan`/`web_execute_js` 浏览器管理、`file_patch`/`file_read`、`expand_file_refs`、`_arg`、`smart_format`、`consume_file`……）
3. Handler 共享状态（`working`/`cwd`/`code_stop_signal`/`history_info`/`print`…）
4. 非工具职责（`load_L1`/`get_global_memory`/`turn_end_callback`/`_get_anchor_prompt`/`format_error`/`consume_file`——被 agentmain/engine 引用的公共 API）

**耦合方式**：所有 `do_*` 通过 `self.*` 隐式访问 8 项共享状态（cwd/working/print/parent/code_stop_signal/history_info + `_get_tool_maxlen`/`_get_abs_path`/`_memory_write_blocked`/`_extract_code_block` 等方法）——拆文件最大的风险点。

**隐性约定**：schema 的 `sandbox_run` ↔ `do_sandbox_run` 靠命名反射（`BaseHandler.dispatch`），没有注册表；漏写 dispatch 只有运行时才发现。

## 二、目标结构

```text
tools/                          ★ 新包（工具域统一收口）
├── __init__.py
├── context.py                  ToolContext：工具可见的共享状态（显式注入，替代 self.*）
│                                 · parent / cwd / working / history_info / print
│                                 · code_stop_signal / current_turn
│                                 · get_tool_maxlen() / get_abs_path() /
│                                   memory_write_blocked() / extract_code_block()
├── registry.py                 装配注册表：
│                                 · ToolDef(name, fn, generator=bool)
│                                 · dispatch(ctx, name, args, response, index, tool_num)
│                                   —— 保持 agent_types 的 yield 流式协议不变
│                                 · unknown/bad_json 兜底（原 dispatch 分支）
├── code/                       代码执行
│   ├── __init__.py             # 注册：code_run / sandbox_run
│   ├── runner.py               # code_run 生成器执行器（原 zicat 30-114 行）
│   └── sandbox.py              # sandbox_scan + do_sandbox_run（header 拼接/双阶段）
├── sandbox/
│   └── header.py               # 审计钩子策略（自 assets/sandbox_header.py 迁入，模板性质）
├── files/                      文件三件
│   ├── __init__.py             # 注册：file_read / file_write / file_patch
│   └── files.py                # 实现 + expand_file_refs/_file_newline/_scan_files
├── browser/                    浏览器
│   ├── __init__.py             # 注册：web_scan / web_execute_js
│   └── web.py                  # first_init_driver/driver 管理 + 两个工具
├── memory/                     记忆七件（用户指定位置）
│   ├── __init__.py             # 注册：memory_search/read/write/patch/archive/link/index
│   └── bridge.py               # 薄桥：调 memstore.tools.MemoryTools（实现仍在 memstore）
└── session_ctl/                会话控制
    ├── __init__.py             # 注册：update_working_checkpoint / ask_user /
    │                           #         start_long_term_update / no_tool
    └── control.py              # 实现 + _retry_or_exit
zicat.py                        瘦身后的兼容层（~200 行）：
├── ZicatAgentHandler           保留类名与构造签名（agentmain/engine 引用不变）
│   ├── self.ctx = ToolContext(...)
│   ├── dispatch()              委托 tools.registry（协议入口不动）
│   ├── turn_end_callback()     留守（非工具职责，依赖 history/_fold_earlier）
│   └── _get_anchor_prompt()    留守（同上）
├── load_L1 / get_global_memory 留守（agentmain 引用的公共 API）
├── smart_format / consume_file / format_error  留守（agentmain/外部引用）
└── （17 个 do_* 与支撑函数全部迁出）
```

**归属说明**：`memory_*` 的真正实现仍在 `memstore/`（它是独立子系统），`tools/memory/` 只放 dispatch 桥——这与"engine 不直接写记忆"的既有边界一致；`ask_user` 实现走 `runner.py` 的 interrupt 协议（graph 侧），文件里只留 legacy 侧逻辑。

## 三、装配协议（registry 核心设计）

```python
# tools/registry.py（示意）
TOOL_DEFS: dict[str, ToolDef] = {}

def register(name: str, generator: bool = True):
    def deco(fn):
        TOOL_DEFS[name] = ToolDef(name=name, fn=fn, generator=generator)
        return fn
    return deco

def dispatch(ctx, tool_name, args, response, index=0, tool_num=1):
    # 与 agent_types.BaseHandler.dispatch 的 yield 流式协议逐字节兼容：
    #   generator 工具 → yield from fn(ctx, args, response)
    #   普通工具     → 返回 StepOutcome / dict / str
    #   unknown / bad_json 兜底分支原样迁移
```

各子包 `__init__.py` 末尾 `import` 实现模块触发注册（如 `from tools.code import runner  # noqa`），`zicat.py` 只 `import tools` 一次即完成全部装配。

**与 schema 的关系**：schema 仍是模型可见的接口描述（不动）；registry 是实现侧装配。新增工具 = schema 加一条 + 子包写一个带 `@register` 的函数——2 个文件，不再碰 zicat.py。

## 四、兼容性红线（全部保持）

1. `agent_types.BaseHandler.dispatch` 的调用入口与 **yield 流式协议**不变（engine 全链路无感知）
2. `ZicatAgentHandler` 类名/构造签名不变（agentmain.py:128、runner.py `_build_context` 引用不变）
3. zicat.py 的对外公共 API 保留：`load_L1`/`get_global_memory`/`smart_format`/`consume_file`/`format_error`/`get_system_prompt`
4. 工具行为零变化：StepOutcome 结构、`_index`/`_tool_num` 注入、memory/ 写拦截、`_tool_num` 长度分摊逻辑逐字节保持
5. memstore/tools.py（memory 工具的库侧实现）不动

## 五、改动清单

| # | 动作 | 文件 |
|---|------|------|
| 1 | 新建 tools/ 包 | context.py / registry.py / code/ / files/ / browser/ / memory/ / session_ctl/ / sandbox/ |
| 2 | 迁出实现 | zicat.py 17 个 do_* + code_run/web/文件支撑函数 → 对应子包（签名改 `(ctx, args, response)`） |
| 3 | zicat.py 瘦身 | 保留兼容层（handler 类壳 + 公共 API），~700 → ~250 行 |
| 4 | sandbox header | assets/sandbox_header.py → tools/sandbox/header.py（do_sandbox_run 读取路径同步） |
| 5 | pyproject | `packages = [... "tools"]` |
| 6 | 测试 | 现有测试引用 ZicatAgentHandler 的不变；新增 registry 装配完整性测试（schema 17 个名字与 registry 键集一致、逐工具 dispatch smoke） |
| 7 | docx | arch/v1/modules.md 工具行、explain modify、README/AGENT 目录地图 |

## 六、验收

- [ ] 全量测试通过（现基线 65）
- [ ] 装配完整性：schema 名单 == registry 键集（防"宣传未实现"）
- [ ] 每工具 dispatch smoke（真实 ctx 跑一遍 happy path）
- [ ] zicat.py ≤ 300 行；新增工具模拟测试（只加 schema + 一个 @register 函数即可被调用）
- [ ] 长会话路径无回归（smart_format/consume_file 等公共 API 冒烟）

## 七、风险与对策

| 风险 | 对策 |
|---|---|
| 生成器流式协议被破坏 | registry 的 generator 分支 `yield from` 原样；dispatch smoke 逐工具验证 |
| ctx 注入遗漏（某 do_* 还在摸 self） | 迁移是一次性机械改写 + `grep "self\." tools/` 终检（只允许 ctx.handler. 前缀） |
| zicat.py 外部引用断裂 | 兼容层保留全部公共 API；compileall + 冒烟 |
| 行为差异 | diff 逐函数 review（移动为主、逻辑不改） |
