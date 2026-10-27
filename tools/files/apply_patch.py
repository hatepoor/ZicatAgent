"""多文件 / 多 hunk 补丁工具：file_apply_patch。

格式借鉴 OpenAI Codex 的 apply_patch（Apache-2.0），实现为纯 Python：
    *** Begin Patch
    *** Add File: a.py
    +line
    *** Update File: b.py
    @@ 可选上下文
    -old
    +new
    *** Delete File: c.py
    *** Update File: old.py
    *** Move to: new.py
    @@
    -old
    +new
    *** End Patch

匹配顺序：精确 -> 行尾空白容忍 -> SequenceMatcher 相似度。出现歧义即失败，
所有文件先在内存校验，全部通过后才落盘；写入中途失败会回滚本次已写文件。
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from agent_types import StepOutcome
from tools.registry import register
from tools.util import atomic_write, read_text_file

MIN_FUZZY_RATIO = 0.90


class PatchError(Exception):
    pass


@dataclass
class Hunk:
    context: str | None
    old_lines: list[str]
    new_lines: list[str]
    added: int = 0
    removed: int = 0


@dataclass
class FilePatch:
    action: str                     # add / update / delete
    path: str
    move_to: str | None = None
    hunks: list[Hunk] = field(default_factory=list)
    content: list[str] = field(default_factory=list)


def _strip_fences(text):
    text = text.strip()
    if not text.startswith('```'):
        return text
    lines = text.splitlines()
    lines = lines[1:]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip().startswith('```'):
        lines.pop()
    return '\n'.join(lines).strip()


def parse_patch(text):
    text = _strip_fences(text or '')
    lines = text.splitlines()
    begin = next((i for i, line in enumerate(lines)
                  if line.strip() == '*** Begin Patch'), None)
    end = next((i for i in range(len(lines) - 1, -1, -1)
                if lines[i].strip() == '*** End Patch'), None)
    if begin is None:
        raise PatchError("patch must start with '*** Begin Patch'")
    if end is None or end <= begin:
        raise PatchError("patch must end with '*** End Patch'")
    lines = lines[begin:end + 1]

    patches = []
    i = 1
    while i < len(lines) - 1:
        line = lines[i]
        if line.startswith('*** Add File: '):
            path = line[len('*** Add File: '):].strip()
            if not path:
                raise PatchError(f'line {i + 1}: empty path in Add File')
            i += 1
            content = []
            while i < len(lines) - 1 and not lines[i].startswith('*** '):
                body = lines[i]
                if body.startswith('+'):
                    content.append(body[1:])
                elif body == '':
                    content.append('')
                else:
                    raise PatchError(
                        f"line {i + 1}: Add File body must start with '+': {body[:80]!r}")
                i += 1
            patches.append(FilePatch('add', path, content=content))

        elif line.startswith('*** Delete File: '):
            path = line[len('*** Delete File: '):].strip()
            if not path:
                raise PatchError(f'line {i + 1}: empty path in Delete File')
            patches.append(FilePatch('delete', path))
            i += 1

        elif line.startswith('*** Update File: '):
            path = line[len('*** Update File: '):].strip()
            if not path:
                raise PatchError(f'line {i + 1}: empty path in Update File')
            i += 1
            move_to = None
            if i < len(lines) - 1 and lines[i].startswith('*** Move to: '):
                move_to = lines[i][len('*** Move to: '):].strip()
                if not move_to:
                    raise PatchError(f'line {i + 1}: empty path in Move to')
                i += 1
            hunks = []
            while i < len(lines) - 1 and not lines[i].startswith('*** '):
                if not lines[i].startswith('@@'):
                    raise PatchError(
                        f"line {i + 1}: expected '@@' hunk marker, got {lines[i][:80]!r}")
                context = lines[i][2:].strip() or None
                i += 1
                old_lines, new_lines = [], []
                added = removed = 0
                while (i < len(lines) - 1
                       and not lines[i].startswith('@@')
                       and not lines[i].startswith('*** ')):
                    body = lines[i]
                    if body.startswith('+'):
                        new_lines.append(body[1:])
                        added += 1
                    elif body.startswith('-'):
                        old_lines.append(body[1:])
                        removed += 1
                    elif body.startswith(' '):
                        old_lines.append(body[1:])
                        new_lines.append(body[1:])
                    elif body == '':
                        old_lines.append('')
                        new_lines.append('')
                    else:
                        raise PatchError(
                            f"line {i + 1}: hunk line must start with ' ', '-' or '+': "
                            f'{body[:80]!r}')
                    i += 1
                if i < len(lines) - 1 and lines[i].startswith('*** End of File'):
                    i += 1
                if not old_lines and not new_lines:
                    raise PatchError(f'line {i + 1}: empty hunk')
                if not old_lines and not context:
                    raise PatchError(
                        f'line {i + 1}: insertion-only hunk needs @@ context')
                hunks.append(Hunk(context, old_lines, new_lines, added, removed))
            if not hunks and not move_to:
                raise PatchError(f'line {i + 1}: Update File without hunks or Move to')
            patches.append(FilePatch('update', path, move_to=move_to, hunks=hunks))

        else:
            raise PatchError(f'line {i + 1}: unknown patch marker {line[:80]!r}')
    if not patches:
        raise PatchError('patch contains no file operations')
    return patches


def _context_ok(lines, index, length, context):
    if not context:
        return True
    window = lines[index:index + max(length, 1)] if length else lines[max(0, index - 1):index + 1]
    return any(context in line for line in window)


def _narrow(candidates, lines, length, context):
    if not context or len(candidates) <= 1:
        return candidates
    narrowed = [i for i in candidates if _context_ok(lines, i, length, context)]
    return narrowed or candidates


def _find_hunk(lines, hunk, start):
    old = hunk.old_lines
    if not old:
        # 纯插入：定位 @@ context 那一行，插到它后面
        hits = [i for i in range(start, len(lines)) if hunk.context in lines[i]]
        if len(hits) == 1:
            return hits[0] + 1
        if not hits:
            raise PatchError(f'insertion context not found: {hunk.context!r}')
        raise PatchError(f'ambiguous insertion context: {hunk.context!r} '
                         f'(lines {hits[:5]})')

    span = len(old)
    if span > len(lines) - start:
        raise PatchError('hunk is longer than remaining file')

    candidates = list(range(start, len(lines) - span + 1))

    exact = [i for i in candidates if lines[i:i + span] == old]
    exact = _narrow(exact, lines, span, hunk.context)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise PatchError(f'ambiguous hunk: {len(exact)} exact matches '
                         f'(lines {[i + 1 for i in exact[:5]]})')

    old_ws = [line.rstrip() for line in old]
    ws = [i for i in candidates
          if [line.rstrip() for line in lines[i:i + span]] == old_ws]
    ws = _narrow(ws, lines, span, hunk.context)
    if len(ws) == 1:
        return ws[0]
    if len(ws) > 1:
        raise PatchError(f'ambiguous hunk after whitespace normalization: '
                         f'{len(ws)} matches (lines {[i + 1 for i in ws[:5]]})')

    scored = []
    for i in candidates:
        ratio = SequenceMatcher(None, old, lines[i:i + span]).ratio()
        if ratio >= MIN_FUZZY_RATIO:
            scored.append((ratio, i))
    if scored:
        best = max(ratio for ratio, _ in scored)
        best_idx = [i for ratio, i in scored if ratio == best]
        best_idx = _narrow(best_idx, lines, span, hunk.context)
        if len(best_idx) == 1:
            return best_idx[0]
        raise PatchError(f'ambiguous fuzzy hunk: {len(best_idx)} candidates '
                         f'(lines {[i + 1 for i in best_idx[:5]]})')

    raise PatchError('hunk context not found')


def _normalize_text(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def _apply_hunks(lines, hunks):
    out = list(lines)
    pos = 0
    for number, hunk in enumerate(hunks, 1):
        try:
            index = _find_hunk(out, hunk, pos)
        except PatchError as e:
            raise PatchError(f'hunk #{number}: {e}')
        old_len = len(hunk.old_lines)
        out[index:index + old_len] = hunk.new_lines
        pos = index + len(hunk.new_lines)
    return out


def _atomic_write_bytes(path, data):
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.zicat-restore-', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def apply_patches(patches, ctx):
    plans = []
    originals = {}
    created = []
    moved = []

    for patch in patches:
        guard = getattr(ctx, 'write_blocked', None)
        if guard:
            blocked = guard(patch.path)
            if blocked:
                raise PatchError(blocked)
        src = ctx.get_abs_path(patch.path)
        if not patch.path:
            raise PatchError('empty file path')
        if patch.action == 'add':
            if os.path.exists(src):
                raise PatchError(f'Add File target already exists: {patch.path}')
            content = '\n'.join(patch.content)
            if content and not content.endswith('\n'):
                content += '\n'
            plans.append(('add', src, content, 'utf-8', '\n', b'', patch))
        elif patch.action == 'delete':
            if not os.path.isfile(src):
                raise PatchError(f'Delete File target not found: {patch.path}')
            originals[src] = Path(src).read_bytes()
            plans.append(('delete', src, None, None, None, None, patch))
        else:
            if not os.path.isfile(src):
                raise PatchError(f'Update File target not found: {patch.path}')
            text, encoding, newline, bom = read_text_file(src)
            lines = _normalize_text(text).split('\n')
            new_lines = _apply_hunks(lines, patch.hunks)
            originals[src] = Path(src).read_bytes()
            plans.append(('update', src, '\n'.join(new_lines), encoding, newline, bom, patch))
            if patch.move_to:
                if guard:
                    blocked = guard(patch.move_to)
                    if blocked:
                        raise PatchError(blocked)
                dst = ctx.get_abs_path(patch.move_to)
                if os.path.exists(dst) and os.path.abspath(dst) != os.path.abspath(src):
                    raise PatchError(f'Move target already exists: {patch.move_to}')
                moved.append((src, dst))

    try:
        for action, src, content, encoding, newline, bom, patch in plans:
            if action == 'add':
                atomic_write(src, content, encoding, newline, bom)
                created.append(src)
            elif action == 'delete':
                os.remove(src)
            else:
                atomic_write(src, content, encoding, newline, bom)
        for src, dst in moved:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
    except Exception as e:
        for path, data in originals.items():
            try:
                _atomic_write_bytes(path, data)
            except OSError:
                pass
        for path in created:
            try:
                os.remove(path)
            except OSError:
                pass
        for src, dst in reversed(moved):
            try:
                if os.path.exists(dst) and not os.path.exists(src):
                    os.replace(dst, src)
            except OSError:
                pass
        raise PatchError(f'write failed, rolled back: {e}')

    summaries = []
    for patch in patches:
        if patch.action == 'add':
            summaries.append({'path': patch.path, 'action': 'add',
                              'lines': len(patch.content)})
        elif patch.action == 'delete':
            summaries.append({'path': patch.path, 'action': 'delete'})
        else:
            summaries.append({
                'path': patch.path,
                'action': 'update',
                'move_to': patch.move_to,
                'hunks': len(patch.hunks),
                'added': sum(h.added for h in patch.hunks),
                'removed': sum(h.removed for h in patch.hunks),
            })
    return {'status': 'success', 'files': summaries}


def _extract_patch(args, response):
    patch = args.get('patch')
    if patch:
        return patch
    text = getattr(response, 'content', '') or ''
    match = re.search(r'<patch[^>]*>(.*?)</patch>', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    blocks = re.findall(r'```[^\n]*\n([\s\S]*?)```', text)
    for block in reversed(blocks):
        if '*** Begin Patch' in block:
            return block.strip()
    if '*** Begin Patch' in text:
        return text.strip()
    return None


@register('file_apply_patch')
def do_file_apply_patch(ctx, args, response):
    """应用多文件/多 hunk 补丁；多处修改优先用它，单块精确替换用 file_patch。"""
    patch_text = _extract_patch(args, response)
    if not patch_text:
        return StepOutcome(
            {'status': 'error', 'msg': "No patch found. Put it in the 'patch' arg or "
                                       'inside <patch>...</patch>.'},
            next_prompt='\n')
    try:
        patches = parse_patch(patch_text)
        yield f"\n[Action] Applying patch: {len(patches)} file operation(s)\n"
        result = apply_patches(patches, ctx)
        yield f"[Status] ✅ patch applied ({len(patches)} file operation(s))\n"
    except PatchError as e:
        result = {'status': 'error', 'msg': str(e)}
        yield f"[Status] ❌ patch failed: {e}\n"
    except Exception as e:
        result = {'status': 'error', 'msg': str(e)}
        yield f"[Status] ❌ patch failed: {e}\n"
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    return StepOutcome(result, next_prompt=next_prompt)
