"""内容搜索与文件发现：grep / glob。

优先调用 ripgrep；找不到或超时时退回纯 Python，输出格式保持一致。
只读工具，不写文件。
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path

from agent_types import StepOutcome
from tools.registry import register
from tools.util import find_rg, read_text_file, run_rg, smart_format

SKIP_DIRS = {'.git', '.venv', 'node_modules', '__pycache__', 'build', 'dist',
             '.idea', '.mypy_cache', '.pytest_cache', 'coverage'}
MAX_FILE_BYTES = 2 * 1024 * 1024


def _as_int(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _display_path(path, cwd):
    candidate = path if os.path.isabs(path) else os.path.join(cwd, path)
    try:
        rel = os.path.relpath(os.path.abspath(candidate), os.path.abspath(cwd))
    except ValueError:
        rel = os.path.abspath(candidate)
    return rel.replace('\\', '/')


def _format(groups, total, truncated, max_results, files_only, fallback, pattern, target):
    if not groups:
        msg = f"No matches for {pattern!r} in {target}"
        return msg + ('\n[fallback: ripgrep unavailable]' if fallback else '')
    lines = []
    if files_only:
        lines.extend(groups.keys())
        summary = f'[{len(groups)} file' + ('' if len(groups) == 1 else 's')
    else:
        for path, entries in groups.items():
            lines.append(path)
            for marker, lineno, text in entries:
                lines.append(f'  {lineno}: {text}' if marker == ':' else f'  {lineno}- {text}')
        summary = (f'[{total} match' + ('' if total == 1 else 'es') +
                   f' in {len(groups)} file' + ('' if len(groups) == 1 else 's'))
    if truncated:
        summary += f', truncated at {max_results}'
    lines.append(summary + ']')
    if fallback:
        lines.append('[fallback: ripgrep unavailable]')
    return '\n'.join(lines)


def _parse_rg_json(stdout, cwd, max_results, files_only, context):
    groups = {}
    total = 0
    truncated = False
    seen_files = set()
    for line in stdout.splitlines():
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        kind = obj.get('type')
        if kind not in ('match', 'context'):
            continue
        data = obj.get('data') or {}
        path = (data.get('path') or {}).get('text')
        if not path:
            continue
        path = _display_path(path, cwd)
        text = ((data.get('lines') or {}).get('text') or '').rstrip('\r\n')
        lineno = data.get('line_number') or 0
        if kind == 'match':
            if files_only:
                if path not in seen_files:
                    if len(seen_files) >= max_results:
                        truncated = True
                        break
                    seen_files.add(path)
                    groups.setdefault(path, [])
                total += 1
                continue
            if total >= max_results:
                truncated = True
                break
            total += 1
            groups.setdefault(path, []).append((':', lineno, text))
        else:
            if context <= 0 or files_only:
                continue
            groups.setdefault(path, []).append(('-', lineno, text))
    return groups, total, truncated


def _candidate_files(base):
    base = Path(base)
    if base.is_file():
        yield base
        return
    # git 仓库内优先用 ls-files：尊重 .gitignore，且包含未跟踪文件
    try:
        import subprocess
        proc = subprocess.run(
            ['git', '-C', str(base), 'ls-files', '-z', '--cached', '--others',
             '--exclude-standard'],
            capture_output=True, timeout=15,
            creationflags=0x08000000 if os.name == 'nt' else 0)
        if proc.returncode == 0:
            found = []
            for raw in proc.stdout.split(b'\0'):
                if not raw:
                    continue
                p = base / raw.decode('utf-8', errors='replace')
                if p.is_file():
                    found.append(p)
            if found:
                yield from found
                return
    except Exception:
        pass
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def _looks_binary(path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return True
        with open(path, 'rb') as f:
            return b'\0' in f.read(8192)
    except OSError:
        return True


def _glob_match(path, base, pattern):
    if not pattern:
        return True
    rel = os.path.relpath(str(path), str(base)).replace('\\', '/')
    return fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(rel, pattern)


def _grep_fallback(pattern, path, glob_pattern, case_sensitive, fixed_strings,
                   max_results, context, cwd):
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(re.escape(pattern) if fixed_strings else pattern, flags)
    except re.error as e:
        return f'Error: invalid regex: {e}'

    base = Path(path)
    groups = {}
    total = 0
    truncated = False
    for file_path in _candidate_files(base):
        if truncated:
            break
        if glob_pattern and not _glob_match(file_path, base, glob_pattern):
            continue
        if _looks_binary(file_path):
            continue
        try:
            text, _enc, _nl, _bom = read_text_file(file_path)
        except (OSError, UnicodeError):
            continue
        lines = text.splitlines()
        hits = [i for i, line in enumerate(lines) if regex.search(line)]
        if not hits:
            continue
        display = _display_path(file_path, cwd)
        for idx in hits:
            if total >= max_results:
                truncated = True
                break
            total += 1
            groups.setdefault(display, [])
            if context > 0:
                start = max(0, idx - context)
                end = min(len(lines), idx + context + 1)
                for j in range(start, end):
                    marker = ':' if j == idx else '-'
                    entry = (marker, j + 1, lines[j])
                    if entry not in groups[display]:
                        groups[display].append(entry)
            else:
                groups[display].append((':', idx + 1, lines[idx]))
    return _format(groups, total, truncated, max_results, False, True,
                   pattern, _display_path(base, cwd))


@register('grep')
def do_grep(ctx, args, response):
    """按内容搜索文件。先用它定位，再 file_read 确认。"""
    pattern = args.get('pattern') or ''
    if not pattern:
        return StepOutcome('Error: pattern is required', next_prompt='\n')
    target = args.get('path') or '.'
    path = ctx.get_abs_path(target)
    if not os.path.exists(path):
        return StepOutcome(f'Error: path not found: {target}', next_prompt='\n')

    glob_pattern = args.get('glob')
    case_sensitive = bool(args.get('case_sensitive', False))
    fixed_strings = bool(args.get('fixed_strings', False))
    files_only = bool(args.get('files_only', False))
    max_results = _as_int(args.get('max_results', 100), 100, 1, 1000)
    context = _as_int(args.get('context', 0), 0, 0, 10)

    yield f"\n[Action] grep {pattern!r} in {_display_path(path, ctx.cwd)}\n"

    rg = find_rg()
    fallback = False
    if rg:
        rg_args = []
        if not case_sensitive:
            rg_args.append('-i')
        if fixed_strings:
            rg_args.append('-F')
        if glob_pattern:
            rg_args += ['-g', glob_pattern]
        if context:
            rg_args += ['-C', str(context)]
        rg_args += [pattern, path]
        proc = run_rg(rg_args, cwd=ctx.cwd, timeout=15, json_mode=True)
        if proc is not None:
            code, stdout, stderr = proc
            if code in (0, 1):
                groups, total, truncated = _parse_rg_json(
                    stdout, ctx.cwd, max_results, files_only, context)
                result = _format(groups, total, truncated, max_results, files_only,
                                 False, pattern, _display_path(path, ctx.cwd))
            elif code == 2:
                result = f'Error: rg regex error: {stderr.strip()[:2000]}'
            else:
                fallback = True
        else:
            fallback = True
    else:
        fallback = True

    if fallback:
        result = _grep_fallback(pattern, path, glob_pattern, case_sensitive,
                                fixed_strings, max_results, context, ctx.cwd)

    maxlen = ctx.get_tool_maxlen(15000, args)
    result = smart_format(result, max_str_len=maxlen, omit_str='\n\n[omitted]\n\n')
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    return StepOutcome(result, next_prompt=next_prompt)


def _glob_fallback(base, pattern, max_results, cwd):
    base_path = Path(base)
    try:
        paths = list(base_path.rglob(pattern)) if pattern else list(base_path.rglob('*'))
    except (OSError, ValueError, NotImplementedError):
        paths = []
    out = []
    for p in sorted(paths, key=lambda x: str(x).lower()):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(_display_path(p, cwd))
        if len(out) >= max_results:
            break
    return out


@register('glob')
def do_glob(ctx, args, response):
    """按文件名/glob 查找文件，返回路径列表。"""
    pattern = args.get('pattern') or ''
    if not pattern:
        return StepOutcome('Error: pattern is required', next_prompt='\n')
    target = args.get('path') or '.'
    path = ctx.get_abs_path(target)
    if not os.path.exists(path):
        return StepOutcome(f'Error: path not found: {target}', next_prompt='\n')
    max_results = _as_int(args.get('max_results', 200), 200, 1, 2000)
    yield f"\n[Action] glob {pattern!r} in {_display_path(path, ctx.cwd)}\n"

    files = None
    fallback = False
    if find_rg():
        proc = run_rg(['--files', path, '-g', pattern], cwd=ctx.cwd,
                      timeout=15, json_mode=False)
        if proc is not None:
            code, stdout, stderr = proc
            if code in (0, 1):
                files = [line for line in stdout.splitlines() if line.strip()]
            elif code == 2:
                return StepOutcome(f'Error: rg error: {stderr.strip()[:2000]}',
                                   next_prompt='\n')
            else:
                fallback = True
        else:
            fallback = True
    else:
        fallback = True

    if fallback:
        files = _glob_fallback(path, pattern, max_results, ctx.cwd)

    if files is None:
        files = []
    truncated = len(files) > max_results
    files = files[:max_results]
    shown = [_display_path(p, ctx.cwd) if os.path.isabs(p) else p.replace('\\', '/')
             for p in files]
    if not shown:
        result = f"No files matching {pattern!r} in {_display_path(path, ctx.cwd)}"
    else:
        result = '\n'.join(shown)
        result += (f'\n[{len(shown)} file' + ('' if len(shown) == 1 else 's') +
                   (f', truncated at {max_results}' if truncated else '') + ']')
    if fallback:
        result += '\n[fallback: ripgrep unavailable]'

    maxlen = ctx.get_tool_maxlen(15000, args)
    result = smart_format(result, max_str_len=maxlen, omit_str='\n\n[omitted]\n\n')
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    return StepOutcome(result, next_prompt=next_prompt)
