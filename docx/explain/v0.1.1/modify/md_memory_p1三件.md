# md · memory P1 三件套（检索/渲染/写入校验）

> 版本: v0.1.1 · 类型: modify · 日期: 2026-10-24

## 变了什么

1. **2 字中文走 FTS**（`repository.py::search`）：阈值 `len(q)>=3` → `>=2`。中文关键词大量 2 字（"部署/浏览器/评审"），此前全降级 LIKE 全表扫；`_fts_query` 短语引号在逐字切分下对 2 字中文合法。
2. **L1 冷条目折叠**（`render_l1`）：L2 全量；L3 按 priority（list_items 既有排序）保留前 20 条带摘要，其余折叠为一行名字列表（存在性编码保留——名字可见即可 memory_read 召回）。不用 access_count 动态排序（索引随热度漂移会伤跨轮连贯）。
3. **memory_write 前置校验**（`tools.py`）：同名拦截并指引 memory_patch（原为 UNIQUE 约束报笼统错误）；summary 必填（无 summary 的条目在 L1 是死名字）。META-SOP"先读再写"公理的代码化。

## 验证

- 新增 MemoryP1Tests ×3；两个旧测试按新契约补 summary 字段
- 全量 55 tests OK；verify 140 项 0 失败
- 真库冒烟：L1 1481 字符、折叠行生效、"浏览器"2 字检索命中 web 相关 SOP（此前走 LIKE）
