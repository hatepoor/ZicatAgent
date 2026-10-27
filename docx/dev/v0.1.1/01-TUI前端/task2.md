# task2 · Node 桥服务

> 状态: ✅
> 依赖: task1

## 怎么做

`ui/server.mjs`（仅 Node 内置模块）：

1. spawn `python -X utf8 agentmain.py --rpc`（探测 `.venv`，`ZICAT_PYTHON` 可覆盖）。
2. `GET /events`：SSE；stdout 逐行 JSON 原子广播；`ready` 缓存并在新连接时重放（页面晚开不丢）；15s 注释帧保活。
3. `POST /send`：body 透传写入内核 stdin（指令协议不变）。
4. 静态托管 `ui/dist`（`vite build` 单文件产物），防目录穿越。
5. SIGINT/SIGTERM 时向内核发 `{"type":"exit"}` 再回收。

## 验收

- [x] `GET /` 返回构建页面
- [x] 晚连接的 SSE 客户端收到 `ready` 重放
- [x] `POST /send` 发 `/help` 收到 `done` 事件
