"""文件工具：file_read / file_write / file_patch。"""
from __future__ import annotations

import itertools
import json
import os
import re
from collections import deque
from difflib import SequenceMatcher
from pathlib import Path

from tools.registry import register
from tools.util import (_arg, atomic_write, detect_encoding, expand_file_refs,
                        log_memory_access, read_text_file, read_text_normalized,
                        smart_format)

_read_dirs = set()


def _scan_files(base, depth=2):
    try:
        for e in os.scandir(base):
            if e.is_file():
                yield (e.name, e.path)
            elif depth > 0 and e.is_dir(follow_symlinks=False):
                yield from _scan_files(e.path, depth - 1)
    except (PermissionError, OSError):
        pass


def _file_read(path, start=1, keyword=None, count=200, show_linenos=True):
    try:
        encoding, _bom = detect_encoding(path)
        with open(path, 'r', encoding=encoding, errors='replace', newline='') as f:
            stream = ((i, l.rstrip('\r\n')) for i, l in enumerate(f, 1))
            stream = itertools.dropwhile(lambda x: x[0] < start, stream)
            if keyword:
                before = deque(maxlen=count // 3)
                for i, l in stream:
                    if keyword.lower() in l.lower():
                        res = list(before) + [(i, l)] + list(itertools.islice(stream, count - len(before) - 1))
                        break
                    before.append((i, l))
                else:
                    return (f"Keyword '{keyword}' not found after line {start}. "
                            f"Falling back to content from line {start}:\n\n"
                            + _file_read(path, start, None, count, show_linenos))
            else:
                res = list(itertools.islice(stream, count))
            realcnt = len(res)
            L_MAX = min(max(100, 256000 // max(realcnt, 1)), 8000)
            TAG = " ... [TRUNCATED]"
            remaining = sum(1 for _ in itertools.islice(stream, 5000))
            total_lines = (res[0][0] - 1 if res else start - 1) + realcnt + remaining
            tl_str = f"{total_lines}+" if remaining >= 5000 else str(total_lines)
            partial = total_lines > realcnt
            total_tag = (f"[FILE] {tl_str} lines"
                         + (" | PARTIAL showing {0}; assess need for more".format(realcnt)
                            if partial else "") + "\n")
            res = [(i, l if len(l) <= L_MAX else l[:L_MAX] + TAG) for i, l in res]
            result = "\n".join(f"{i}|{l}" if show_linenos else l for i, l in res)
            if show_linenos:
                result = total_tag + result
            elif partial:
                result += f"\n\n[FILE PARTIAL: showing {realcnt}/{tl_str} lines; assess need for more]"
            _read_dirs.add(os.path.dirname(os.path.abspath(path)))
            return result
    except FileNotFoundError:
        msg = f"Error: File not found: {path}"
        try:
            tgt = os.path.basename(path)
            parent = os.path.dirname(os.path.abspath(path))
            scan = os.path.dirname(parent)
            roots = [parent, scan] + [d for d in _read_dirs if not d.startswith(scan)]
            cands = list(dict.fromkeys(itertools.islice(
                (c for base in roots for c in _scan_files(base)), 2000)))
            top = sorted([(SequenceMatcher(None, tgt.lower(), c[0].lower()).ratio(), c)
                          for c in cands[:2000]], key=lambda x: -x[0])[:5]
            top = [(s, c) for s, c in top if s > 0.3]
            if top:
                msg += "\n\nDid you mean:\n" + "\n".join(f"  {c[1]}  ({s:.0%})" for s, c in top)
        except Exception:
            pass
        return msg
    except Exception as e:
        return f"Error: {str(e)}"


def _file_patch(path: str, old_content: str, new_content: str):
    """在文件中寻找唯一的 old_content 块并替换为 new_content"""
    path = str(Path(path).resolve())
    try:
        if not os.path.exists(path):
            return {"status": "error", "msg": "file not found"}
        full_text, encoding, newline, bom = read_text_normalized(path)
        old_content = old_content.replace('\r\n', '\n').replace('\r', '\n')
        new_content = new_content.replace('\r\n', '\n').replace('\r', '\n')
        if not old_content:
            return {"status": "error", "msg": "old_content is blank"}
        count = full_text.count(old_content)
        if count == 0:
            return {"status": "error",
                    "msg": ("old_content is not found. Suggestion: use file_read to check current "
                            "file content, make more small patches. Don't huge overwrite (even with code)")}
        if count > 1:
            return {"status": "error",
                    "msg": (f"find {count} matches, unable to determine unique position. Provide a "
                            f"longer, more specific old_content to ensure uniqueness. Suggestion: "
                            f"include context lines to enhance features, or modify in smaller segments.")}
        updated_text = full_text.replace(old_content, new_content)
        atomic_write(path, updated_text, encoding=encoding, newline=newline, bom=bom)
        return {"status": "success", "msg": "file patched successfully"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


@register("file_read")
def do_file_read(ctx, args, response):
    """读取文件内容。从第start行开始读取。如有keyword则返回第一个keyword(忽略大小写)周边内容"""
    path = ctx.get_abs_path(args.get("path", ""))
    yield f"\n[Action] Reading file: {path}\n"
    start = _arg(args, "start", 1, int)
    count = _arg(args, "count", 200, int)
    keyword = args.get("keyword")
    show_linenos = _arg(args, "show_linenos", True, bool)
    result = _file_read(path, start=start, keyword=keyword, count=count, show_linenos=show_linenos)
    if show_linenos and not result.startswith("Error:"):
        result = '由于设置了show_linenos，以下返回信息为：(行号|)内容 。\n' + result
    if ' ... [TRUNCATED]' in result:
        result += '\n\n（某些行被截断，如需完整内容可改用 code_run 读取）'
    maxlen = ctx.get_tool_maxlen(15000, args)
    result = smart_format(result, max_str_len=maxlen, omit_str='\n\n[omitted long content]\n\n')
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    log_memory_access(path)
    if 'memory' in path or 'sop' in path:
        next_prompt += ("\n[SYSTEM TIPS] 正在读取记忆或SOP文件，若决定按sop执行请提取sop中的"
                        "关键点（特别是靠后的）update working memory.")
    from agent_types import StepOutcome
    return StepOutcome(result, next_prompt=next_prompt)


@register("file_write")
def do_file_write(ctx, args, response):
    """用于对整个文件的大量处理，精细修改要用file_patch。
    需要将要写入的内容放在<file_content>标签内，或者放在代码块中"""
    blocked = ctx.write_blocked(args.get("path", ""))
    if blocked:
        yield f"[Status] {blocked}\n"
        return __import__('agent_types').StepOutcome(
            {"status": "error", "msg": blocked},
            next_prompt=ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0))
    path = ctx.get_abs_path(args.get("path", ""))
    mode = args.get("mode", "overwrite")
    action_str = {"prepend": "Prepending to", "append": "Appending to"}.get(mode, "Overwriting")
    yield f"[Action] {action_str} file: {os.path.basename(path)}\n"

    def extract_robust_content(text):
        tags = re.findall(r"<file_content[^>]*>(.*?)</file_content>", text, re.DOTALL)
        if tags:
            return tags[-1].strip()
        blocks = re.findall(r"```[^\n]*\n([\s\S]*?)```", text)
        if blocks:
            return blocks[-1].strip()
        return None

    content = args.get('content') or extract_robust_content(response.content)
    if not content:
        yield "[Status] ❌ 失败: 未在回复中找到<file_content>代码块内容\n"
        return __import__('agent_types').StepOutcome(
            {"status": "error",
             "msg": ("No content found. Blank is not supported. Put content inside "
                     "<file_content>...</file_content> tags in your reply body before call file_write.")},
            next_prompt="\n")
    try:
        new_content = expand_file_refs(content, base_dir=ctx.cwd)
        new_content = new_content.replace('\r\n', '\n').replace('\r', '\n')
        exists = os.path.exists(path)
        if exists:
            _old, encoding, newline, bom = read_text_file(path)
        else:
            encoding, newline, bom = 'utf-8', '\n', b''
        if mode == "prepend":
            old = read_text_normalized(path)[0] if exists else ""
            atomic_write(path, new_content + old, encoding=encoding,
                         newline=newline, bom=bom)
        elif mode == "append":
            append_encoding = 'utf-8' if encoding == 'utf-8-sig' else encoding
            with open(path, 'a', encoding=append_encoding, newline=newline) as f:
                f.write(new_content)
        else:
            atomic_write(path, new_content, encoding=encoding,
                         newline=newline, bom=bom)
        yield f"[Status] ✅ {mode.capitalize()} 成功 ({len(new_content)} bytes)\n"
        next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
        if len(new_content) > 5000:
            next_prompt = "\n[SYSTEM TIPS] WRITE TOO LONG! MUST RECHECK HALLUCINATIONS! SMALL WRITES OR PATCHES NEXT TIME!"
        return __import__('agent_types').StepOutcome(
            {"status": "success", 'writed_bytes': len(new_content)}, next_prompt=next_prompt)
    except Exception as e:
        yield f"[Status] ❌ 写入异常: {str(e)}\n"
        return __import__('agent_types').StepOutcome({"status": "error", "msg": str(e)},
                                                     next_prompt="\n")


@register("file_patch")
def do_file_patch(ctx, args, response):
    blocked = ctx.write_blocked(args.get("path", ""))
    if blocked:
        yield f"[Status] {blocked}\n"
        return __import__('agent_types').StepOutcome(
            {"status": "error", "msg": blocked},
            next_prompt=ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0))
    path = ctx.get_abs_path(args.get("path", ""))
    yield f"[Action] Patching file: {path}\n"
    old_content = args.get("old_content", "")
    new_content = args.get("new_content", "")
    try:
        new_content = expand_file_refs(new_content, base_dir=ctx.cwd)
    except ValueError as e:
        yield f"[Status] ❌ 引用展开失败: {e}\n"
        return __import__('agent_types').StepOutcome({"status": "error", "msg": str(e)},
                                                     next_prompt="\n")
    result = _file_patch(path, old_content, new_content)
    yield f"\n{str(result)}\n"
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    return __import__('agent_types').StepOutcome(result, next_prompt=next_prompt)


from . import search  # noqa: E402,F401  注册 grep / glob
from . import apply_patch  # noqa: E402,F401  注册 file_apply_patch
