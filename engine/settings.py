"""配置读取：mykey.py 中的 OpenAI 兼容配置 + graph 运行参数。"""
from __future__ import annotations

from memstore.common import DEFAULT_DB as _MEMORY_DB, GRAPH_DB as _GRAPH_DB, ROOT  # noqa: F401

SESSION_DIR = ROOT / "session"
DEFAULTS = {
    "max_turns": 180,
    "context_char_cap": 114000,
    "checkpointer": str(SESSION_DIR / "graph.db"),
    "workspace": str(ROOT / "temp"),   # 会话产物目录的根（FIX-S，可 --workspace / graph_config 覆盖）
    "memory_db": str(_MEMORY_DB),
    "ckpt_retention":20, # FIX-4: 每会话保留最近 N 份 checkpoint
    "ckpt_vacuum_mb":64 # FIX-4: 库超过该 MB 数时在收尾触发 VACUUM
}


def _mykeys() -> dict:
    from mykey_loader import mykeys_store
    keys, _ = mykeys_store.snapshot()
    return keys


def oai_configs() -> list[dict]:
    """返回所有 OpenAI 兼容模型配置（按 mykey 里的出现顺序）。"""
    out: list[dict] = []
    for key, cfg in _mykeys().items():
        if not isinstance(cfg, dict):
            continue
        if "oai_config" not in key:
            continue
        if not (cfg.get("apibase") or cfg.get("base_url")):
            continue
        out.append({"key": key, **cfg})
    return out


def graph_config() -> dict:
    """合并 mykey.py 里的 graph_config（可选）与默认值。"""
    cfg = dict(DEFAULTS)
    for key, value in _mykeys().items():
        if key == "graph_config" and isinstance(value, dict):
            cfg.update(value)
    return cfg


def effective_context_char_cap(llm_no: int = 0, cfg: dict | None = None) -> int:
    """把当前模型的 context_window（tokens）换算成引擎字符预算。

    未配置 context_window 时沿用 graph_config.context_char_cap。按 3 字符/token
    保守换算，上限 4M 字符，避免误填超大值拖垮视图。
    """
    result = dict(cfg or graph_config())
    try:
        models = oai_configs()
        idx = max(0, min(int(llm_no or 0), len(models) - 1))
        raw = str(models[idx].get("context_window") or "0").replace(",", "").strip()
        tokens = int(float(raw))
    except (TypeError, ValueError, IndexError):
        tokens = 0
    if tokens > 0:
        result["context_char_cap"] = min(max(tokens * 3, 10000), 4_000_000)
    try:
        return int(result.get("context_char_cap") or DEFAULTS["context_char_cap"])
    except (TypeError, ValueError):
        return int(DEFAULTS["context_char_cap"])
