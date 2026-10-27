"""Plan / todo 状态 —— 纯标准库，不依赖任何 UI 框架。

API：
  extract(text)                   → [(content, "open"|"done"), …]
  is_active(agent, messages=None) → 是否处于 plan 模式（stash 或按会话的消息引用）
  resolve_path(agent, messages=None) → 存活的 plan.md 路径（或 None）
  find_path_in_messages(messages) → 最近提到的 plan.md 路径
  current_step(messages)          → 最新的 `当前步骤：…` 片段（或 ""）
  summary(items)                  → (n_done, n_total)
  is_complete(items)              → 是否全部完成（或为空）

支持的任务行形态（`extract` 都能匹配）：
  - [ ] foo              ← 项目符号 + 未完成
  - [x] foo              ← 项目符号 + 已完成
  1. [✓] foo             ← 编号 + 已完成
  2. [✓ 2026-05-16] foo  ← 编号 + 带时间戳的已完成，内容在括号之后
  3. [✓ 已生成: foo]      ← 编号 + 已完成，描述在括号*内部*
  4. [D][P] foo          ← 两组标记（delegate + parallel），仍未完成
  5. [D] foo             ← 非标准标记 "D" → 未完成（不算 done）
"""
from __future__ import annotations
import os, re
from typing import Any, Optional

_DONE_CHARS = set("xX✓✔√☑")
# 在黏在 JSON 碎片里的项目符号前补一个换行（`{"content": "- [ ] …`）。
_GLUE_RE = re.compile(r"(?<!\n)((?:[-*+]|\d+\s*[.)、:）]) \[)")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+\s*[.)、:）])\s+")
_BRACKET_RE = re.compile(r"\[([^\]]*)\]")
# 当括号内容被当作标题时，剥掉 `✓ ` / `x ` / 时间戳前缀。
_INLINE_STRIP_RE = re.compile(
    r"^[" + re.escape("".join(_DONE_CHARS)) + r"]\s*(?:\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?\s*)?"
)
_DEBRIS_RE = re.compile(r'["\\<].*$')
# 剥掉 markdown 强调符，因为 planbar 渲染的是 rich.Text，而不是 Markdown。
_MD_EMPHASIS_RE = re.compile(
    r"\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|__([^_\n]+)__|_([^_\n]+)_|`([^`\n]+)`"
)
def _strip_md(s: str) -> str:
    return _MD_EMPHASIS_RE.sub(lambda m: next(g for g in m.groups() if g is not None), s)


def _has_done_glyph(marker: str) -> bool:
    return any(c in _DONE_CHARS for c in marker)


def extract(text: str) -> list[tuple[str, str]]:
    if not text: return []
    norm = text.replace("\\n", "\n") if "\\n" in text else text
    norm = _GLUE_RE.sub(r"\n\1", norm)
    found: dict[str, str] = {}
    for line in norm.splitlines():
        head = _BULLET_RE.match(line)
        if not head: continue
        rest = line[head.end():]
        groups: list[str] = []
        # 吃掉任意多个连续的 `[...]` 分组 —— 既覆盖 `[D][P]` 之类任务类型链，
        # 也覆盖朴素的 `[ ]` / `[x]` 单组形式。
        while True:
            b = _BRACKET_RE.match(rest)
            if not b: break
            groups.append(b.group(1))
            rest = rest[b.end():]
        if not groups: continue
        is_done = any(_has_done_glyph(g) for g in groups)
        inline = rest.strip()
        if inline:
            content = inline
        elif is_done:
            # `[✓ description]` 形态 —— 描述就在括号内、紧挨着字形标记。
            # 剥掉字形标记 + 可选时间戳。
            done_g = next(g for g in groups if _has_done_glyph(g))
            content = _INLINE_STRIP_RE.sub("", done_g).strip()
        else:
            continue
        k = _strip_md(_DEBRIS_RE.sub("", content).strip())
        if not k: continue
        status = "done" if is_done else "open"
        # 同一内容出现两次 —— done 优先于 open。
        if k not in found or status == "done":
            found[k] = status
    return list(found.items())


def _stashed_plan_path(agent) -> str:
    # 从 (handler, agent) 里取第一个非空的 `working['in_plan_mode']`。
    for src in (getattr(agent, "handler", None), agent):
        p = ((getattr(src, "working", None) or {}).get("in_plan_mode") or "").strip()
        if p: return p
    return ""


def _resolve_stashed(p: str) -> Optional[str]:
    if not p: return None
    rel = p.lstrip("./\\")
    cwd = os.getcwd()
    for c in (p, os.path.join(cwd, "temp", rel), os.path.join(cwd, rel)):
        if os.path.isfile(c) and os.path.getsize(c) > 0: return c
    return None


# 严格的按会话发现 —— 只扫本会话自己的消息。
_PATH_RE = re.compile(r"""((?:\.\/)?(?:temp\/)?plan_[A-Za-z0-9_\-]+\/plan\.md)""")


def _slice(messages, start_idx: int):
    if not messages: return []
    if start_idx <= 0: return list(messages)
    return list(messages)[start_idx:]


def find_path_in_messages(messages, start_idx: int = 0) -> Optional[str]:
    """`start_idx` 之后被引用、且磁盘上确实存在的最新 `plan_XXX/plan.md`。
    items 既可以是类 `ChatMessage` 对象（取 `.content`），也可以是纯字符串；
    只返回磁盘上确实存在的路径。"""
    sliced = _slice(messages, start_idx)
    if not sliced: return None
    for m in reversed(sliced):
        text = getattr(m, "content", None)
        if text is None: text = m if isinstance(m, str) else ""
        if not text or "plan.md" not in text: continue
        for hit in reversed(_PATH_RE.findall(text)):
            p = _resolve_stashed(hit.strip().strip("\"'"))
            if p: return p
    return None


# 优先用简洁的 `<summary>` 叙述，而不是冗长的 plan 条目回显；
# 把 `❌ 当前步骤:` 视作「该步骤已完成」，而不是「当前步骤」。
_SUMMARY_STEP_RE = re.compile(
    r"<summary>[^<]*?当前步骤[:：]\s*([^<\n]{1,160})</summary>", re.DOTALL)
_STEP_RE = re.compile(r"📌\s*当前步骤[:：]\s*([^\n。！!？?]{1,160})")
_DONE_STEP_RE = re.compile(r"❌\s*当前步骤[:：]")


def current_step(messages, start_idx: int = 0, max_len: int = 60) -> str:
    """最新的 `当前步骤：…` 片段；优先 `<summary>` 形式，跳过带 `❌` 前缀的。
    会裁剪到 `max_len` 个字符，好塞进 5 行的 plan 卡片。"""
    sliced = _slice(messages, start_idx)
    if not sliced: return ""

    def _clean(s: str) -> str:
        return _strip_md(re.sub(r"\s+", " ", s).strip().rstrip(" ：:—-"))

    def _cap(s: str) -> str:
        s = _clean(s)
        if len(s) <= max_len: return s
        return s[:max_len - 1].rstrip() + "…"

    for m in reversed(sliced):
        text = getattr(m, "content", None)
        if text is None: text = m if isinstance(m, str) else ""
        if not text or "当前步骤" not in text: continue
        hits = _SUMMARY_STEP_RE.findall(text)
        if hits: return _cap(hits[-1])
        for raw in reversed(_STEP_RE.findall(text)):
            if _DONE_STEP_RE.search(raw): continue
            return _cap(raw)
    return ""


def is_active(agent, messages=None, start_idx: int = 0,
              restored_path: str = "") -> bool:
    """plan 模式是否开启。首选：`working['in_plan_mode']`。其次是
    `restored_path` —— 由 /continue 从转录里结构化的 `enter_plan_mode`
    tool_use 恢复出来的路径（见 continue_cmd.find_plan_entry）；与消息扫描
    不同，它没法被聊天里随手打的路径伪造。
    遗留回退：本会话消息里引用到的 `plan_*/plan.md`（不做全局扫描）——
    只有在传入 `messages` 时才查。"""
    if _stashed_plan_path(agent): return True
    if restored_path and _resolve_stashed(restored_path): return True
    return find_path_in_messages(messages, start_idx) is not None


def resolve_path(agent, messages=None, start_idx: int = 0,
                 restored_path: str = "") -> Optional[str]:
    p = _resolve_stashed(_stashed_plan_path(agent))
    if p: return p
    if restored_path:
        p = _resolve_stashed(restored_path)
        if p: return p
    return find_path_in_messages(messages, start_idx)


def bind_plan_path(agent, path: str, root: str = "") -> str:
    """把计划文件绑定到当前 agent（写入 agent.working['in_plan_mode']）。

    绑定存在 agent 上而不是 handler 上：handler 每个任务会重建，agent 的生命周期
    与进程一致，所以跨任务仍能查到同一份计划。
    """
    stored = _store_plan_path(path, root or os.getcwd())
    if not stored:
        return ""
    working = getattr(agent, "working", None)
    if not isinstance(working, dict):
        working = {}
        try:
            setattr(agent, "working", working)
        except Exception:
            return stored
    working["in_plan_mode"] = stored
    return stored


def summary(items: list[tuple[str, str]]) -> tuple[int, int]:
    return sum(1 for _, st in items if st == "done"), len(items)


def is_complete(items: list[tuple[str, str]]) -> bool:
    return not items or all(st == "done" for _, st in items)


# --- 仅供 Desktop bridge 使用（上面的 API 保持不变）---
_ENTER_PLAN_RE = re.compile(r"""enter_plan_mode\s*\(\s*["']([^"']+)["']""", re.I)


def _msg_content(m) -> str:
    if isinstance(m, str): return m
    c = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
    return c if isinstance(c, str) else ""


def _msg_role(m) -> str:
    if isinstance(m, dict): return str(m.get("role") or "")
    return str(getattr(m, "role", "") or "")


def plan_path_mention_in_messages(messages, start_idx: int = 0) -> Optional[str]:
    """最新的、由 assistant/tool 发出的 `enter_plan_mode(...)` 路径；纯聊天文本不算信号。"""
    for m in reversed(_slice(messages, start_idx)):
        if _msg_role(m) == "user":
            continue
        text = _msg_content(m)
        if not text: continue
        if "enter_plan_mode" in text and (hit := _ENTER_PLAN_RE.search(text)):
            return hit.group(1).strip().strip("\"'")
    return None


def _resolve_stashed_at(p: str, root: str) -> Optional[str]:
    if not p or not root: return None
    rel = p.lstrip("./\\")
    cwd = root.rstrip("/\\")
    for c in (p, os.path.join(cwd, "temp", rel), os.path.join(cwd, rel)):
        if os.path.isfile(c) and os.path.getsize(c) > 0: return c
    return None


def _find_path_at(messages, start_idx: int, root: str) -> Optional[str]:
    for m in reversed(_slice(messages, start_idx)):
        if _msg_role(m) == "user":
            continue
        text = _msg_content(m)
        if not text or "plan.md" not in text: continue
        for hit in reversed(_PATH_RE.findall(text)):
            if p := _resolve_stashed_at(hit.strip().strip("\"'"), root): return p
    return None


def _store_plan_path(path: str, root: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    if os.path.isabs(p) and root:
        for base in (os.path.join(root, "temp"), root):
            try:
                rel = os.path.relpath(p, base)
            except ValueError:
                continue
            if rel and not rel.startswith(".."):
                return rel.replace("\\", "/")
    return p.replace("\\", "/").lstrip("./")


def ensure_agent_plan_mode(sess: Any, root: str) -> None:
    agent = getattr(sess, "agent", None)
    bound = (getattr(sess, "plan_path", "") or "").strip()
    if not agent or not bound or _stashed_plan_path(agent):
        return
    if not _resolve_stashed_at(bound, root):
        return
    for src in (getattr(agent, "handler", None), agent):
        if not src:
            continue
        enter = getattr(src, "enter_plan_mode", None)
        if callable(enter):
            enter(bound)
            return
    for src in (getattr(agent, "handler", None), agent):
        working = getattr(src, "working", None)
        if isinstance(working, dict):
            working["in_plan_mode"] = bound
            return


def sync_plan_path_from_text(sess: Any, text: str, root: str) -> None:
    """若 agent 输出了 enter_plan_mode(...)，就让会话绑定的路径保持同步。"""
    if not text:
        return
    m = _ENTER_PLAN_RE.search(text)
    if not m:
        return
    raw = m.group(1).strip().strip("\"'")
    if not raw:
        return
    sess.plan_path = _store_plan_path(raw, root)


def session_plan_active(sess: Any, agent, messages, start_idx: int, root: str) -> bool:
    """Desktop：本会话绑定了 plan_path 即为活跃（不看全局 plan_* 扫描）。"""
    bound = (getattr(sess, "plan_path", None) or "").strip()
    if _stashed_plan_path(agent):
        return True
    if not bound:
        return False
    if _resolve_stashed_at(bound, root):
        return True
    if getattr(sess, "status", "") == "running":
        return True
    return False


def session_plan_resolve(bound: str, root: str) -> Optional[str]:
    if not bound:
        return None
    return _resolve_stashed_at(bound.strip(), root)


def _desktop_resolve_plan_file(sess: Any, bound: str, root: str, agent, messages, base: int) -> Optional[str]:
    """Desktop 读取路径：绑定路径 → agent stash → 按会话扫消息。"""
    path = session_plan_resolve(bound, root)
    if path:
        return path
    if agent and (stash := _stashed_plan_path(agent)):
        if p := _resolve_stashed_at(stash, root):
            return p
    return _find_path_at(messages, base, root)


