"""模型：OpenAI 兼容接口 + 多模型故障转移。"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from . import settings


def _kwargs(cfg: dict) -> dict:
    kw: dict = {
        "model": cfg.get("model", ""),
        "base_url": cfg.get("apibase") or cfg.get("base_url"),
        "api_key": cfg.get("apikey") or cfg.get("api_key") or "EMPTY",
        "max_retries": int(cfg.get("max_retries", 3)),
        "timeout": float(cfg.get("read_timeout") or cfg.get("timeout") or 180),
        "streaming": True,
    }
    if "temperature" in cfg:
        kw["temperature"] = cfg["temperature"]
    if "max_tokens" in cfg:
        kw["max_tokens"] = int(cfg["max_tokens"])
    if cfg.get("reasoning_effort"):
        kw["reasoning_effort"] = cfg["reasoning_effort"]
    if cfg.get("proxy"):
        kw["openai_proxy"] = cfg["proxy"]
    return kw


def _build_openai(cfg: dict, callbacks=None):
    return ChatOpenAI(**_kwargs(cfg), callbacks=callbacks)


def _build_deepseek(cfg: dict, callbacks=None):
    from .deepseek import DeepSeekChatModel
    return DeepSeekChatModel(**_kwargs(cfg), callbacks=callbacks)


_BUILDERS = {
    "openai": _build_openai,
    "deepseek": _build_deepseek,
}


def build_chat_model(tools_schema: list[dict] | None = None, callbacks=None, index: int = 0):
    """构造模型；index 选主模型（/model 热切换），其余配置作为 fallback。"""
    configs = settings.oai_configs()
    if not configs:
        raise RuntimeError("mykey.py 中未找到 OpenAI 兼容配置（native_oai_config*）")
    index = max(0, min(int(index), len(configs) - 1))  # 越界收敛到边界而非报错
    ordered = configs[index:] + configs[:index]        # 选中者为主，其余按原序跟随当 fallback
    models = []
    for cfg in ordered:
        provider = str(cfg.get("provider") or "openai").strip().lower()
        builder = _BUILDERS.get(provider, _build_openai)
        model = builder(cfg, callbacks)
        if tools_schema:
            model = model.bind_tools(tools_schema)
        models.append(model)
    return models[0] if len(models) == 1 else models[0].with_fallbacks(models[1:])
