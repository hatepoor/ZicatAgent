# task1 · RPC 事件协议结构化

> 状态: ✅
> 依赖: 无

## 怎么做

1. `engine/runner.py`：`_emit` 支持 `**extra` 结构化字段；`_consume` 三个 emit 点带上 `kind`：
   - AI 回复 → `kind="assistant"`；
   - 工具调用 → `kind="tool_call"` + `name` + `args`（`_args_summary` 单行 JSON 截断 200 字符）；
   - 工具结果 → `kind="tool_result"` + `name` + `text`（多行预览 1200 字符）+ `ok`（ToolMessage.status）；
   - 挂起提示 → `kind="notice"`。
2. `core/rpc.py`：`_event_from_item` 按 `kind` 映射事件（`delta/tool_call/tool_result/notice`）；无 `kind` 的旧载荷走 `_classify_next` 文本分类兜底；`[usage]` 解析为结构化数字字段。
3. 测试：`tests/test_engine.py` 更新 usage 断言，新增 `test_structured_event_mapping`。

## 验收

- [x] 全量单测通过（37 tests OK）
- [x] `compileall` 通过
- [x] CLI（`core/commands.py`）与 `--task` 输出不感知新字段（只读 `next`）
