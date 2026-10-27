# task4 · 端到端联调与验收

> 状态: ✅
> 依赖: task3

## 怎么做

1. 冒烟（已完成）：`node ui/server.mjs` → `GET /` 页面、SSE `ready` 重放、`POST /send` slash 命令 `done`。
2. 全链路 bug 排查（已完成，2026-10-24 /goal）：engine emit → core/rpc → 桥 → 前端逐层核对；修复 interrupt 过期、假重连、工具耗时、summary 泄漏、exit 幂等 5 处，桥与 rpc 加固 3 处；补 RpcBridgeTests 等单测（全量 42 OK）；桥死亡场景冒烟（503/exit 帧/进程存活）通过。明细见 todolist 进度日志。
3. 真实任务验收（待做）：真实模型跑含工具调用的任务，验证 assistant 流式块、工具块（args/结果/耗时/错误态）、`ask_user` interrupt 问答、Esc 中断、usage 统计与面板数字。
4. 验收通过后走 v0.1.1 收尾（arch → explain → 根指针），并回到 v0.1.0 task5 烘跑。

## 验收清单

- [x] 冒烟通路（无真实 API 消耗）
- [x] 全链路静态排查 + 单测覆盖 emit/桥/命令表/错误分支
- [x] 桥死亡场景（/send 503、新连接 exit 帧、进程存活）
- [x] 真实任务：工具调用链路显示正确（3×tool_call/result、delta、usage、done，产物落盘校验）
- [x] 真实任务：interrupt 真实挂起 + abort 放弃路径通过（回答回路有单测与 ask/answer 集成覆盖），回答后输入不再被吞
- [x] 面板 usage 与 `done.usage` 一致（真实数据 input=15215/output=949/requests=4）
