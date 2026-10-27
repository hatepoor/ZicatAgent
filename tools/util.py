"""工具域共享的路径与小工具（原 zicat.py 顶层函数；zicat.py re-export 保持外部引用）。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = str(ROOT)
MEMORY_ROOT = os.path.join(SCRIPT_DIR, 'memory')


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        pass


def format_error(e):
    exc_type, exc_value, exc_traceback = sys.exc_info()
    tb = traceback.extract_tb(exc_traceback)
    if tb:
        f = tb[-1]
        fname = os.path.basename(f.filename)
        return f"{exc_type.__name__}: {str(e)} @ {fname}:{f.lineno}, {f.name} -> `{f.line}`"
    return f"{exc_type.__name__}: {str(e)}"


def smart_format(data, max_str_len=100, omit_str=' ... '):
    if not isinstance(data, str):
        data = str(data)
    if len(data) < max_str_len + len(omit_str) * 2:
        return data
    return f"{data[:max_str_len // 2]}{omit_str}{data[-max_str_len // 2:]}"


def consume_file(dr, file):
    if dr and os.path.exists(os.path.join(dr, file)):
        with open(os.path.join(dr, file), encoding='utf-8', errors='replace') as f:
            content = f.read()
        os.remove(os.path.join(dr, file))
        return content


def _arg(args, name, default, type=None):
    v = args.get(name, default)
    if type is int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    if type is bool:
        if isinstance(v, str):
            return v.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
        return default if v is None else bool(v)
    return v


def expand_file_refs(text, base_dir=None):
    """展开文本中的 {{file:路径:起始行:结束行}} 引用为实际文件内容。展开失败抛 ValueError。"""
    pattern = r'\{\{file:(.+?):(\d+):(\d+)\}\}'

    def replacer(match):
        path, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        path = os.path.abspath(os.path.join(base_dir or '.', path))
        if not os.path.isfile(path):
            raise ValueError(f"引用文件不存在: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if start < 1 or end > len(lines) or start > end:
            raise ValueError(f"行号越界: {path} 共{len(lines)}行, 请求{start}-{end}")
        return ''.join(lines[start - 1:end])

    return re.sub(pattern, replacer, text)


def _file_newline(path):
    endings = set(re.findall(rb'\r\n|[\r\n]', Path(path).read_bytes())) if os.path.exists(path) else set()
    return next(iter(endings)).decode() if len(endings) == 1 else None


def log_memory_access(path):
    if 'memory' not in path:
        return
    stats_file = os.path.join(MEMORY_ROOT, 'file_access_stats.json')
    try:
        with open(stats_file, 'r', encoding='utf-8') as f:
            stats = json.load(f)
    except Exception:
        stats = {}
    fname = os.path.basename(path)
    stats[fname] = {'count': stats.get(fname, {}).get('count', 0) + 1,
                    'last': datetime.now().strftime('%Y-%m-%d')}
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


# ---------- ripgrep ----------

def find_rg():
    """定位 ripgrep：显式禁用/覆盖优先，其次 PATH。找不到返回 None。"""
    if os.environ.get('ZICAT_NO_RG'):
        return None
    override = os.environ.get('ZICAT_RG_PATH')
    if override and os.path.isfile(override):
        return override
    return shutil.which('rg')


def run_rg(args, cwd, timeout=15, json_mode=True):
    """执行 rg，返回 (returncode, stdout, stderr)；找不到 rg 返回 None。"""
    exe = find_rg()
    if not exe:
        return None
    cmd = [exe, '--no-config']
    if json_mode:
        cmd += ['--json', '--max-filesize', '2M', '--max-columns', '300']
    cmd += list(args)
    kwargs = dict(cwd=str(cwd), capture_output=True, shell=False, timeout=timeout)
    if sys.platform == 'win32':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
    try:
        proc = subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired:
        return 124, '', f'rg timed out after {timeout}s'
    except OSError as e:
        return 127, '', str(e)
    return (proc.returncode,
            proc.stdout.decode('utf-8', errors='replace'),
            proc.stderr.decode('utf-8', errors='replace'))


# ---------- 文本编码 / 原子写 ----------

_BOMS = (
    (b'\xef\xbb\xbf', 'utf-8-sig'),
    (b'\xff\xfe', 'utf-16-le'),
    (b'\xfe\xff', 'utf-16-be'),
)


def detect_encoding(path):
    """返回 (encoding, bom)。优先 BOM，其次 UTF-8，再退 GBK。"""
    raw = Path(path).read_bytes()[:65536]
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            return enc, bom
    try:
        raw.decode('utf-8')
        return 'utf-8', b''
    except UnicodeDecodeError:
        pass
    try:
        raw.decode('gbk')
        return 'gbk', b''
    except UnicodeDecodeError:
        return 'utf-8', b''


def detect_newline(text):
    crlf = text.count('\r\n')
    lf = text.count('\n') - crlf
    return '\r\n' if crlf > lf else '\n'


def read_text_file(path):
    """读取文本并保留原始换行，返回 (text, encoding, newline, bom)。"""
    encoding, bom = detect_encoding(path)
    with open(path, 'r', encoding=encoding, newline='') as f:
        text = f.read()
    if bom and text.startswith('\ufeff'):
        text = text[1:]
    return text, encoding, detect_newline(text), bom


def read_text_normalized(path):
    """读取文本并把换行统一成 \\n，便于补丁/替换匹配。"""
    text, encoding, newline, bom = read_text_file(path)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text, encoding, newline, bom


def atomic_write(path, text, encoding='utf-8', newline=None, bom=b''):
    """同目录临时文件 + os.replace，避免写入中途截断原文件。"""
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    if newline:
        text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', newline)
    fd, tmp = tempfile.mkstemp(prefix='.zicat-', suffix='.tmp', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            if bom and not encoding.endswith('-sig'):
                f.write(bom)
            f.write(text.encode(encoding))
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
