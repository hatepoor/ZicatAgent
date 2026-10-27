# task1 · 本地沙箱 sandbox_run（方案定稿）

> 状态: ⬜ 待执行 · 工作量 ~1 天

## 设计（2026-10-24 会话定稿）

**双模式路由**：本地开发/操作本地文件 → 现有 `code_run`（全权，不变）；其他任务的代码执行（调研计算/数据处理/运行临时代码）→ 新工具 `sandbox_run`。

**三层架构**：

| 层 | 机制 | 说明 |
|---|---|---|
| 默认层（本任务交付） | Python 审计钩子护栏：子进程 `sys.addaudithook`（CPython 3.8+ 官方机制，零依赖） | 防 agent 误操作（删文件/写系统/起进程/偷读密钥/乱联网），非对抗性安全边界 |
| 双阶段确认 | 静态扫描发现危险模式（subprocess/ctypes/socket/写白名单外路径）→ **强制 ask_user** | 防提示注入的实际缓解（借鉴 SkillLite 两阶段确认） |
| 扩展点 | `backend` 参数位（检测到 `sandbox-exec`/`bwrap` 时 OS 级隔离；skilllite/Docker 留 v0.3） | macOS/Linux 用户可自动升一档 |

**审计钩子策略**（子进程内，进程级）：
- `open`：写仅 `workspace/sandbox/` + 系统临时目录；读放行 Python 库目录（保 numpy 等 import）+ 沙箱目录；拒读仓库源码/`.env`/`mykey.py`/用户主目录
- `subprocess.Popen`/`os.system`/`os.exec`/`os.spawn`/`os.fork`：全禁（沙箱内不起进程）
- `socket.*`：默认禁；`network=true` 参数放行（模型按需传）
- `ctypes.dlopen`/`pickle.find_class`：禁/白名单（封 C 层与反序列化绕过）
- `os.remove/rename/mkdir/listdir` 等改动类：限沙箱目录内
- 执行形态：拼接 `assets/sandbox_header.py`（钩子策略）+ 用户代码 → tempfile → subprocess（cwd=workspace 下沙箱交换区、清洗环境变量、stop_signal 可中断、输出截断）——复用 code_run 成熟管道

**诚实边界**（写入工具描述与文档）：护栏≠安全边界，Python 层内有效、理论可绕过（PEP 578 定位为审计非沙箱）；主场景 Windows 无 OS 级轻量方案（Claude Code 同样），audit hook 是当下唯一零配置选项。仅支持 python 模式（bash/ps 仍走 code_run）。

## SkillLite 调研结论（2026-10-24，实测）

定位匹配（Rust 系统级沙箱+Python SDK+MIT）但暂不可用：Windows 降级"PARTIAL security"（文件/网络不隔离）、稳态延迟 ~10s/次、numpy 等依赖经 skill 目录声明流程不支持、0.1.29 行为与文档不一致。**保留观察**：出 Windows 原生方案且性能改善后作为 backend 接入。

## 改动清单

- [ ] `assets/sandbox_header.py`（钩子策略 ~100 行）
- [ ] `zicat.py::do_sandbox_run`（复用 code_run 管道 + 静态扫描双阶段）
- [ ] `assets/tools_schema.json`(+_en)：sandbox_run 定义 + 工具描述写路由规则与诚实边界
- [ ] `assets/sys_prompt.txt`(+_en)：路由一句（本地开发→code_run；计算/不可信代码→sandbox_run）
- [ ] 单测：违规必拒（各类 open/subprocess/socket/ctypes）+ 合规必过（numpy 计算、沙箱内读写、network 开关）
- [ ] docx 登记 + AGENT.md §10 边界更新

## 验收

- [ ] 危险操作全拦截且有清晰报错；numpy/pandas 计算零损耗（C 层不经钩子）
- [ ] 静态扫描触发 ask_user 的双阶段路径实测
- [ ] 与 code_run 路由不混淆（描述+prompt 双引导）；全量测试通过
