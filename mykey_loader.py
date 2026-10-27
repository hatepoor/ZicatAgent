"""mykey.py / .env 配置加载器（独立模块，供 agentmain / engine.settings 使用）。

优先级：.env（dotenv）> mykey.py > mykey.json。
.env 的 `ZICAT_OAI_<n>__<FIELD>` 组装为 `oai_config_<n>`（字段名转小写，
数值尽力 int/float 转换）；其存在时覆盖 mykey.py 的 oai_config*，
mykey.py 其余变量（mixin_config / 聊天平台 token / graph_config）继续生效。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import threading
import time

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # 仅在存在 .env 时才强制要求
    load_dotenv = None

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")

_OAI_KEY_RE = re.compile(r"^ZICAT_OAI_(\d+)__([A-Za-z_][A-Za-z0-9_]*)$")


def _coerce(value: str):
    text = value.strip()
    for cast in (int, float):
        try:
            return cast(text)
        except (TypeError, ValueError):
            pass
    return text


def _dotenv_data() -> dict | None:
    """解析 .env 的 ZICAT_OAI_<n>__<FIELD> 为 {oai_config_<n>: {...}}；无 .env/无模型组返回 None。"""
    if not os.path.isfile(ENV_PATH):
        return None
    if load_dotenv is None:
        raise RuntimeError("检测到 .env 但缺少 python-dotenv：请先 pip install python-dotenv")
    load_dotenv(ENV_PATH, override=True)
    groups: dict[int, dict] = {}
    for key, value in os.environ.items():
        match = _OAI_KEY_RE.match(key)
        if not match:
            continue
        index, field = int(match.group(1)), match.group(2).lower()
        groups.setdefault(index, {})[field] = _coerce(value)
    if not groups:
        return None
    return {f"oai_config_{index}": cfg for index, cfg in sorted(groups.items())}


class MyKeys:
    def __init__(self):
        self.path = self.mtime = self.updated_at = None
        self.data = {}
        self.lock = threading.Lock()

    def _load_module_data(self):
        """原 mykey.py / mykey.json 加载路径（向后兼容）。"""
        sys.modules.pop('mykey', None)
        spec = importlib.util.find_spec('mykey')
        if spec is not None:
            path = spec.origin
            mt = os.stat(path).st_mtime_ns
            module = importlib.util.module_from_spec(spec)
            sys.modules['mykey'] = module
            # 直接编译源码：pyc 的时间戳只有秒级精度。
            try:
                exec(compile(spec.loader.get_source('mykey'), path, 'exec'), module.__dict__)
            except BaseException:
                sys.modules.pop('mykey', None)
                raise
            data = {k: v for k, v in vars(module).items() if not k.startswith('_')}
        else:
            path = os.path.join(ROOT, 'mykey.json')
            mt = os.stat(path).st_mtime_ns
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'remote_url' in data:
                data = requests.get(data['remote_url'], timeout=10).json()
        if not isinstance(data, dict):
            raise ValueError('mykey configuration must be a dict')
        if os.stat(path).st_mtime_ns != mt:
            raise RuntimeError('mykey changed while loading')
        return data, path, mt

    def _load(self):
        env_data = _dotenv_data()
        if env_data is not None:
            mt = os.stat(ENV_PATH).st_mtime_ns
            if os.stat(ENV_PATH).st_mtime_ns != mt:
                raise RuntimeError('.env changed while loading')
            data = dict(env_data)
            try:
                py_data, _path, _mt = self._load_module_data()
                for key, value in py_data.items():
                    if 'oai_config' not in key:  # .env 的模型组优先
                        data.setdefault(key, value)
            except (OSError, ValueError, RuntimeError):
                pass  # 无 mykey.py / json 时纯 .env 运行
            return data, ENV_PATH, mt
        return self._load_module_data()

    def reload(self, force=False):
        with self.lock:
            try:
                mt = os.stat(self.path).st_mtime_ns if self.path else None
                if not force and self.updated_at is not None and mt == self.mtime:
                    return self.data, self.updated_at, False
                data, path, mt = self._load()
                self.data, self.path, self.mtime = data, path, mt
                self.updated_at = max(time.monotonic_ns(), (self.updated_at or 0) + 1)
                print(f'[Info] Load mykeys from {self.path}')
                return self.data, self.updated_at, True
            except Exception:
                return self.data, self.updated_at, False

    def snapshot(self):
        data, updated_at, _ = self.reload()
        return data, updated_at


mykeys_store = MyKeys()


def reload_mykeys():
    data, _, changed = mykeys_store.reload()
    return data, changed


def _load_mykeys():
    with mykeys_store.lock:
        return mykeys_store._load()[0]
