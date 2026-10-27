# CLI 与 JSONL RPC 前端

> 版本: v0.1.0
> 类别: 新增
> 主题: cli_rpc
> 对比版本: 无
> 日期: 2026-10-23
> 关联架构版本: v1
> 关联 ADR: ADR-0003
> 关联开发文档: [dev/v0.1.0/05-交互前端](../../../dev/v0.1.0/05-交互前端/develop.md)

## 变更前

无，本版首次建立。此前前端已裁剪到只剩 Python CLI，显示能力有限，也没有稳定的脚本化接口。

## 变更后

- Python CLI 提供 16 个 slash 命令与普通任务分流。
- `--rpc` 模式：stdin 命令（task/answer/abort/exit），stdout 事件（ready/delta/tool/tool_result/usage/interrupt/done/exit）。
- 零依赖 TypeScript CLI（Node 23 直接执行 `.ts`）：流式文本、工具卡片、spinner、命令补全、`ask_user` 弹层、Ctrl+C。
- 启动器 `zicat.ps1` / `zicat.cmd` / `zicat.sh`：探测 Node，失败回退 Python CLI。
- RPC `exit` 先 abort 并等待任务收尾，避免截断 `done`。

## 影响范围

- **模块**: `cli`、`runtime`
- **契约**: 新增 RPC 命令/事件协议与 `core.commands.handle()`
- **数据**: 无
- **兼容性**: Python CLI 行为保持；TS CLI 为新增入口

## 验证方式

- `node --no-warnings cli/zicat.ts` 交互实测
- 管道测试：`{"type":"task","text":"/cost"}` + `{"type":"exit"}` 先 `done` 后 `exit`
- 集成测试 `tests.test_integration` 覆盖 RPC 与 `--reflect`

## 备注

协议变更需同时改 `core/rpc.py` 与 `cli/zicat.ts`；事件字段保持向后兼容。
