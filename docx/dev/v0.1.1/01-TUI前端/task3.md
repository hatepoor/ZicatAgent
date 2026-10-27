# task3 · Web TUI 前端

> 状态: ✅
> 依赖: task2

## 怎么做

`ui/` 工程（React 19 + Vite 7 + Tailwind 4，依赖清单同参考项目）：

1. 原样复用参考项目：`themes.ts`（4 主题）、`components/Rich.tsx`、`index.css`、`main.tsx`。
2. `agent.ts` 重写为纯数据模型：`Entry` 类型（user/assistant/tool/system/interrupt/error）+ 常量；**删除 mock 脚本**。
3. `api.ts` 新增：SSE 连接（`connect`）+ 指令发送（`send`）。
4. `App.tsx` 事件驱动重构：
   - 事件状态机：`delta` 追加开放 assistant 块；`tool_call` 开工具块；`tool_result` 回填行与状态/耗时；`notice` 系统块；`interrupt` 问答块；`done` 收口与 usage 累积；`exit` 断连提示。
   - 打字机渐显（纯前端表现层，`shown` 追赶 `text`）。
   - interrupt 复用主输入框回答；candidates 点击回填；Esc 中断（`abort`）。
   - 面板/状态栏：真实 usage（input+output、ctx 近似占比）、模型与工作目录来自 `ready`。
5. `components/Blocks.tsx`：Banner 显示真实 cwd/模型；ToolBlock 增加 error 态；新增 InterruptBlock。

## 验收

- [x] `npx tsc --noEmit` 通过
- [x] `vite build` 产出单文件 `dist/index.html`
- [x] 不含任何 mock Agent 逻辑（`buildAgentScript` 等已删除）
