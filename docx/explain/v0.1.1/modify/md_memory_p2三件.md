# md · memory P2 三件套（export 定期化 / patch 冲突提醒 / L4 蒸馏任务化）

> 版本: v0.1.1 · 类型: modify · 日期: 2026-10-24

## 变了什么

1. **export 定期化**（`reflect/scheduler.py`）：backup 周期（24h）内同步刷新 `memstore.export`（backup 是灾备二进制快照，export 是可进 git 的 markdown 快照，用途互补；此前 export 靠手动）。
2. **memory_patch 冲突提醒**（`memstore/tools.py`）：patch 前用新正文前 8 字做 FTS 短探针找相似条目（排除自身），命中时返回附 `related` + `hint`——防同一知识两份 SOP 并行演化越走越远。提醒不阻断（冲突判断留给看得见双方内容的模型）。设计迭代：探针初版 24 字被测试抓住——FTS 逐字切分下长短语要求整段相邻，太特异；8 字平衡特异与容忍。
3. **L4 蒸馏任务化**（`reflect/scheduler.py`）：每 7 天 `check()` 派发蒸馏任务（归档是压缩存储、蒸馏是知识提取，后者需模型判断，走任务字符串协议而非静默 subprocess）；任务文本强制按 salient_mining_sop 流程、summary 必填、无料如实报告不硬凑。

## 验证

- 新增 patch 提醒单测（相似命中/不相似不打扰/自身不误报）；scheduler 侧 compileall + 逻辑审查（check() 有端口锁与真实副作用，不做直接单测）
- 全量 56 tests OK；verify 140 项 0 失败
