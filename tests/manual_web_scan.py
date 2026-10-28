"""web_scan 冷启动单次测试:新进程 fresh import -> _web_scan() -> 单行结果。"""
import sys, time, json
sys.path.insert(0, '.')

t0 = time.time()
from tools.browser import _web_scan
r = _web_scan()
dt = time.time() - t0

ok = r.get("status") == "success" and bool(r.get("content"))
meta = r.get("metadata") or {}
print(json.dumps({
    "ok": ok,
    "time_s": round(dt, 1),
    "msg": (r.get("msg") or "")[:80],
    "tabs": meta.get("tabs_count"),
    "content_chars": len(r.get("content") or ""),
}, ensure_ascii=False))
