"""模型配置读写：查看当前模型、把修改写回 .env。

.env 是模型组的唯一可写源（`ZICAT_OAI_<n>__<FIELD>`）；写入后立即 reload，
下一个任务就会用新配置。API Key 在传输/展示层掩码，编辑时由前端传原值。
"""
from __future__ import annotations

import os
import re
import tempfile

from mykey_loader import ENV_PATH, mykeys_store

FIELD_MAP = {
    "base_url": "APIBASE",
    "api_key": "APIKEY",
    "model": "MODEL",
    "name": "NAME",
    "context_window": "CONTEXT_WINDOW",
    "max_tokens": "MAX_TOKENS",
    "temperature": "TEMPERATURE",
    "provider": "PROVIDER",
    "reasoning_effort": "REASONING_EFFORT",
}

PROVIDERS = ("openai", "deepseek")

# 当前只做 DeepSeek；openai 走通用 Chat Completions。
REASONING_EFFORT_OPTIONS = {
    "openai": ["low", "medium", "high"],
    "deepseek": ["off", "low", "medium", "high", "xhigh", "max"],
}


def provider_of(cfg: dict) -> str:
    provider = str(cfg.get("provider") or "openai").strip().lower()
    return provider if provider in PROVIDERS else "openai"


def mask_key(value: str) -> str:
    value = str(value or "")
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def list_models(reveal: bool = False) -> list[dict]:
    """返回 .env 中的模型组，index 为 0 起的前端序号。

    默认对 API Key 掩码；只有显式 reveal=True（本地 CLI/用户点“显示”）才返回原值。
    """
    from engine.settings import oai_configs

    out = []
    for i, cfg in enumerate(oai_configs()):
        raw_key = cfg.get("apikey") or cfg.get("api_key") or ""
        provider = provider_of(cfg)
        out.append({
            "index": i,
            "env_index": i + 1,
            "name": cfg.get("name") or cfg.get("model") or f"模型 {i + 1}",
            "model": cfg.get("model", ""),
            "base_url": cfg.get("apibase") or cfg.get("base_url") or "",
            "api_key": raw_key if reveal else mask_key(raw_key),
            "context_window": cfg.get("context_window") or cfg.get("context") or "",
            "max_tokens": cfg.get("max_tokens") or cfg.get("max_output") or "",
            "temperature": cfg.get("temperature", ""),
            "provider": provider,
            "reasoning_effort": cfg.get("reasoning_effort", ""),
            "reasoning_effort_options": REASONING_EFFORT_OPTIONS.get(provider, []),
        })
    return out


def _env_quote(value) -> str:
    text = str(value if value is not None else "").strip()
    if text == "" or re.search(r'[\s#"\'\\]', text):
        return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return text


def upsert_env(text: str, key: str, value) -> str:
    """在 .env 文本中替换/追加一行，保留其它注释与顺序。"""
    pattern = re.compile(rf'^\s*(?:export\s+)?{re.escape(key)}\s*=.*$', re.MULTILINE)
    line = f"{key}={_env_quote(value)}"
    if pattern.search(text):
        return pattern.sub(lambda _m: line, text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def remove_env(text: str, key: str) -> str:
    """删除 .env 中的一行（用于切换接口后清理不兼容的思考强度）。"""
    pattern = re.compile(rf'^\s*(?:export\s+)?{re.escape(key)}\s*=.*\n?', re.MULTILINE)
    return pattern.sub("", text, count=1)


def _atomic_write(path: str, text: str) -> None:
    parent = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".env-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_model(index: int, values: dict, env_path: str | None = None) -> list[dict]:
    """保存一个模型组。index 0 起；index == len(models) 表示新增。

    values 支持 base_url/api_key/model/name/context_window/max_tokens/temperature。
    空值视为“保持原值”；API key 掩码值不会被写回。
    """
    if index < 0:
        raise ValueError("模型序号不能为负数")
    path = env_path or ENV_PATH
    existing = (list_models(reveal=True) if env_path is None
                else list_models_after_write(path, index))
    if index > len(existing):
        raise ValueError(f"模型序号超出范围（当前 {len(existing)} 个，新增请用 {len(existing)}）")
    current = existing[index] if index < len(existing) else {}
    merged = dict(current)
    for field, value in (values or {}).items():
        if field not in FIELD_MAP:
            continue
        if value is None or str(value).strip() == "":
            continue
        if field == "api_key" and ("…" in str(value) or set(str(value)) == {"*"}):
            continue
        merged[field] = str(value).strip()

    incoming_provider = str((values or {}).get("provider") or "").strip().lower()
    if incoming_provider and incoming_provider not in PROVIDERS:
        raise ValueError(
            f"未知接口类型: {incoming_provider}（可选: {', '.join(PROVIDERS)}）"
        )
    merged["provider"] = incoming_provider or provider_of(merged)

    allowed_efforts = REASONING_EFFORT_OPTIONS.get(merged["provider"], [])
    incoming_effort = str((values or {}).get("reasoning_effort") or "").strip().lower()
    if incoming_effort and incoming_effort not in allowed_efforts:
        raise ValueError(
            f"{merged['provider']} 不支持思考强度 {incoming_effort}；"
            f"可选: {', '.join(allowed_efforts)}"
        )
    current_effort = str(merged.get("reasoning_effort") or "").strip().lower()
    drop_effort = bool(current_effort and current_effort not in allowed_efforts)
    if drop_effort:
        merged.pop("reasoning_effort", None)

    if not merged.get("base_url"):
        raise ValueError("Base URL 不能为空")
    if not merged.get("model"):
        raise ValueError("模型名不能为空")

    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = "# zicatAgent model config\n"

    if index < len(existing):
        env_index = int(existing[index].get("env_index") or index + 1)
    else:
        env_index = max([int(m.get("env_index") or 0) for m in existing] + [0]) + 1
    prefix = f"ZICAT_OAI_{env_index}__"
    for field, suffix in FIELD_MAP.items():
        if field in merged and merged[field] != "":
            if field == "api_key" and merged[field] == current.get("api_key"):
                continue  # 未修改就不重写 Key
            text = upsert_env(text, prefix + suffix, merged[field])
    if drop_effort:
        text = remove_env(text, prefix + "REASONING_EFFORT")
    _atomic_write(path, text)
    if env_path is None:
        mykeys_store.reload(force=True)
        return list_models()
    return list_models_after_write(path, index)


def list_models_after_write(path: str, index: int) -> list[dict]:
    """测试/自定义 env 路径时用：解析该文件里的模型组，不触碰全局缓存。"""
    groups: dict[int, dict] = {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []
    for line in raw.splitlines():
        m = re.match(r'\s*(?:export\s+)?ZICAT_OAI_(\d+)__([A-Za-z_]+)\s*=\s*(.*)$', line)
        if not m:
            continue
        group = int(m.group(1))
        field = m.group(2).lower()
        value = m.group(3).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        groups.setdefault(group, {})[field] = value
    out = []
    for group, cfg in sorted(groups.items()):
        if not (cfg.get("apibase") or cfg.get("base_url")):
            continue
        out.append({
            "index": len(out),
            "env_index": group,
            "name": cfg.get("name") or cfg.get("model") or f"模型 {group}",
            "model": cfg.get("model", ""),
            "base_url": cfg.get("apibase") or cfg.get("base_url") or "",
            "api_key": cfg.get("apikey") or cfg.get("api_key") or "",
            "context_window": cfg.get("context_window") or cfg.get("context") or "",
            "max_tokens": cfg.get("max_tokens") or cfg.get("max_output") or "",
            "temperature": cfg.get("temperature", ""),
            "provider": provider_of(cfg),
            "reasoning_effort": cfg.get("reasoning_effort", ""),
            "reasoning_effort_options": REASONING_EFFORT_OPTIONS.get(provider_of(cfg), []),
        })
    return out
