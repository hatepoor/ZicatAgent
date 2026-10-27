"""把 memory/ 下的文件导入 SQLite（P1 迁移脚本）。

用法：
    python -m memstore.migrate --dry-run
    python -m memstore.migrate --backup

规则：
- 只读源文件，不改不删；
- 每个文件写入一条 memory_items + 一条 memory_versions(reason='import')；
- 生成 manifest（sha256），供 verify 比对；
- 运行时读取/导入的文件不导入（见 RUNTIME_ASSETS）；
- 被代码 import 的模块一律不导入。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .common import DEFAULT_DB, MEMORY_DIR, sha256_bytes
from .db import Database
from .repository import DuplicateItem, MemoryStore

DEFAULT_MEMORY = MEMORY_DIR

# 代码运行时读取的文件：保留在磁盘，不当作记忆内容导入
RUNTIME_ASSETS = {
    "l1_fallback.txt",                             # L1 兜底文本（库可用时动态渲染）
    "README.md",                                   # memory 门牌，不是记忆条目
    "kb/index.md",                                 # kb 目录说明，不是记忆条目
}

# L1 分类导航的标签（用于后续动态渲染分组）
TAGS = {
    "tmwebdriver_sop": ["browser"], "web_setup_sop": ["browser"],
    "vue3_component_sop": ["browser", "frontend"],
    "scheduled_task_sop": ["scheduler"], "autonomous_operation_sop": ["scheduler"],
    "ultraplan_sop": ["plan"], "goal_mode_sop": ["plan", "goal"],
    "goal_team_sop": ["multiagent"], "goal_team_master_duty": ["multiagent"],
    "subagent": ["multiagent"], "supervisor_sop": ["multiagent"],
    "checklist_sop": ["multiagent"], "checklist_helper": ["multiagent", "script"],
    "review_sop": ["review"], "code_review_principles": ["review"],
    "deliverable_audit_sop": ["review"],
    "project_mode_sop": ["workspace"], "distill_sop": ["evolution"],
    "memory_management_sop": ["memory"], "memory_cleanup_sop": ["memory"],
    "keychain": ["security", "script"],
    "salient_mining_sop": ["memory"], "task_planning": ["plan"],
    "autonomous_helper": ["scheduler", "script"],
}


def _headline(text: str, limit: int = 80) -> str:
    for line in text.splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:limit]
    return ""


def _script_summary(body: str, name: str, limit: int = 80) -> str:
    """脚本摘要：优先模块 docstring，其次文件头注释，最后退化。"""
    text = body.lstrip()
    if text.startswith(('"""', "'''")):
        quote = text[:3]
        inner = text[3:].split(quote, 1)[0]
        for line in inner.splitlines():
            clean = line.strip()
            if clean:
                return clean[:limit]
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith(("#!", "# -*-", "# coding")):
            continue
        if clean.startswith("#"):
            return clean.lstrip("#").strip()[:limit]
        break
    return f"技能脚本: {name}"


# 扫描时跳过的目录（备份快照、导出目录不参与导入）
SKIP_DIRS = {"backup", "export", "__pycache__"}


def classify(path: Path, memory_dir: Path) -> tuple[str, str] | None:
    rel = path.relative_to(memory_dir).as_posix()
    if any(part in SKIP_DIRS for part in Path(rel).parts[:-1]):
        return None
    if path.suffix == ".pyc":
        return None
    if rel in RUNTIME_ASSETS:
        return None
    if path.suffix == ".md":
        return ("L3", "sop")
    if path.suffix == ".py":
        return ("L3", "script") if rel.startswith("scripts/") else None
    if rel == "facts.txt":
        return ("L2", "fact")
    if rel.startswith("L4_raw_sessions/") and path.suffix == ".txt":
        return ("L4", "archive")
    return None


def l1_rules_block(memory_dir: Path) -> str:
    path = memory_dir / "l1_fallback.txt"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "[RULES]"
    idx = text.find(marker)
    return text[idx:].strip() if idx >= 0 else ""


def build_plan(memory_dir: Path) -> list[dict]:
    plan: list[dict] = []
    for path in sorted(memory_dir.rglob("*")):
        if not path.is_file():
            continue
        klass = classify(path, memory_dir)
        if not klass:
            continue
        layer, kind = klass
        rel = path.relative_to(memory_dir).as_posix()
        if kind == "archive":
            plan.append({
                "path": path, "rel": rel, "layer": layer, "kind": kind,
                "name": path.stem, "body": "", "summary": f"历史会话归档: {path.name}",
                "tags": ["archive"], "priority": 500, "verified": 0,
            })
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"[skip] 非 UTF-8，跳过: {rel}")
            continue
        if rel == "facts.txt" and not body.strip():
            print(f"[skip] 空文件，跳过: {rel}")
            continue
        plan.append({
            "path": path, "rel": rel, "layer": layer, "kind": kind,
            "name": path.stem,
            "body": body,
            "summary": _script_summary(body, path.stem) if kind == "script" else _headline(body),
            "tags": TAGS.get(path.stem, []),
            "priority": 10 if layer == "L2" else 100,
            "verified": 1 if kind == "script" else 0,
        })
    rules = l1_rules_block(memory_dir)
    if rules:
        plan.append({
            "path": memory_dir / "l1_fallback.txt", "rel": "l1_fallback.txt#RULES",
            "layer": "L1", "kind": "index", "name": "l1_rules",
            "body": rules, "summary": "L1 固定规则（来自 legacy L1）",
            "tags": ["rules", "l1"], "priority": 0, "verified": 1,
        })
    return plan


def backup(memory_dir: Path, plan: list[dict]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = memory_dir / "backup" / f"import_{stamp}"
    dst.mkdir(parents=True, exist_ok=True)
    for entry in plan:
        src = entry["path"]
        if not src.is_file():
            continue
        rel = src.relative_to(memory_dir)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
    return dst


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="memory/ 文件导入 SQLite")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY))
    parser.add_argument("--manifest", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", action="store_true", help="导入前把源文件快照到 memory/backup/")
    args = parser.parse_args(argv)

    memory_dir = Path(args.memory_dir).resolve()
    db_path = Path(args.db).resolve()
    manifest_path = Path(args.manifest) if args.manifest else memory_dir / "backup" / "import_manifest.json"

    plan = build_plan(memory_dir)
    print(f"待导入 {len(plan)} 条（db={db_path}）")
    if args.dry_run:
        for entry in plan:
            print(f"  {entry['layer']}/{entry['kind']:7} {entry['name']:28} <- {entry['rel']}")
        return 0

    if args.backup:
        snapshot = backup(memory_dir, plan)
        print(f"源文件已快照: {snapshot}")

    db = Database(db_path)
    store = MemoryStore(db)
    entries: list[dict] = []
    created = skipped = failed = 0
    for entry in plan:
        raw = entry["body"].encode("utf-8")
        source_bytes = entry["path"].read_bytes() if entry["path"].is_file() else b""
        meta = {
            "source": entry["rel"],
            "sha256": sha256_bytes(source_bytes) if source_bytes else sha256_bytes(raw),
            "bytes": len(source_bytes) or len(raw),
            "imported_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            item = store.create(
                name=entry["name"], layer=entry["layer"], kind=entry["kind"],
                title=entry["name"], summary=entry["summary"], body=entry["body"],
                tags=entry["tags"], meta=meta, status="active",
                priority=entry["priority"], verified=entry["verified"],
                actor="system", reason="import",
            )
            created += 1
            item_id = item.id
        except DuplicateItem:
            existing = store.get(entry["name"])
            if not existing:
                print(f"[fail] 重名但取不到: {entry['rel']}")
                failed += 1
                continue
            skipped += 1
            item_id = existing.id
            print(f"[skip] 已存在: {existing.layer}/{existing.name}")
        except Exception as exc:  # noqa: BLE001 - 迁移脚本需要逐条报告
            failed += 1
            print(f"[fail] {entry['rel']}: {exc}")
            continue
        entries.append({
            "source": entry["rel"],
            "source_sha256": meta["sha256"],
            "body_sha256": sha256_bytes(raw),
            "layer": entry["layer"],
            "kind": entry["kind"],
            "name": entry["name"],
            "item_id": item_id,
            "bytes": len(raw),
        })

    stats = store.stats()
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db": str(db_path),
        "memory_dir": str(memory_dir),
        "entries": entries,
        "stats": stats,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    db.close()

    print(f"\n完成: 新建 {created} / 跳过 {skipped} / 失败 {failed}")
    print(f"manifest: {manifest_path}")
    print(f"统计: {json.dumps(stats, ensure_ascii=False)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
