"""把 memory/ 下改过的文件同步进记忆库（追加新版本），并刷新 manifest。

用于 SOP 修改后保持"文件 = 库"一致；不会删除库里的条目。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .common import DEFAULT_DB, MEMORY_DIR, sha256_bytes
from .db import Database
from .migrate import _script_summary, _headline, build_plan
from .repository import MemoryStore


def sync(db_path: str | Path, memory_dir: str | Path, manifest_path: Path | None = None) -> dict:
    memory_dir = Path(memory_dir).resolve()
    manifest_path = Path(manifest_path) if manifest_path else memory_dir / "backup" / "import_manifest.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {e["name"]: e for e in manifest.get("entries", [])}

    db = Database(Path(db_path), init=False)
    store = MemoryStore(db)
    updated = skipped = missing = 0
    for entry in build_plan(memory_dir):
        raw = entry["body"].encode("utf-8")
        item = store.get(entry["name"])
        if item is None:
            missing += 1
            continue
        if item.body == entry["body"]:
            skipped += 1
            continue
        summary = _script_summary(entry["body"], item.name) if item.kind == "script" else _headline(entry["body"])
        store.patch(item.id, body=entry["body"], summary=summary,
                    reason="file-sync", actor="system")
        updated += 1
        if item.name in entries:
            entries[item.name]["body_sha256"] = sha256_bytes(raw)
            src_bytes = entry["path"].read_bytes()
            entries[item.name]["source_sha256"] = sha256_bytes(src_bytes)
            entries[item.name]["bytes"] = len(raw)
        print(f"[sync] {item.name}")

    manifest["entries"] = list(entries.values())
    manifest["synced_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    db.close()
    return {"updated": updated, "skipped": skipped, "missing": missing}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="同步 memory/ 文件到记忆库")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--memory-dir", default=str(MEMORY_DIR))
    parser.add_argument("--manifest", default="")
    args = parser.parse_args(argv)
    result = sync(args.db, args.memory_dir, args.manifest or None)
    print(f"完成: 更新 {result['updated']} / 未变 {result['skipped']} / 库中缺失 {result['missing']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
