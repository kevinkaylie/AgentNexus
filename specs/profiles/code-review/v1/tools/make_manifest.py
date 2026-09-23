#!/usr/bin/env python3
"""生成/刷新 specs/profiles/code-review/v1/manifest.json。

manifest 固定每个文件的摘要、Profile 版本与来源 Git revision（§15.9）。
manifest.json 自身不登记自身摘要。运行后再执行 tools/validate.py 复核。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PROFILE_VERSION = "agentnexus.code-review/1.0-draft.2"
PACKAGE_VERSION = "1.0-draft.2+semantic.16"

INCLUDE_DIRS = ("schemas", "fixtures", "bindings", "tools")
INCLUDE_FILES = ("README.md", "compatibility.json")
EXCLUDE = {"manifest.json"}


def git_revision() -> dict:
    def run(args):
        try:
            return subprocess.run(
                args, cwd=BASE, capture_output=True, text=True, check=True
            ).stdout.strip()
        except Exception:
            return ""

    head = run(["git", "rev-parse", "HEAD"])
    dirty = run(["git", "status", "--porcelain", "--", str(BASE)])
    return {
        "git_head": head or "unavailable",
        "worktree_dirty": bool(dirty),
        "note": "文件为冻结候选；dirty=true 表示提交前的工作树状态，冻结发布必须登记已提交 revision",
    }


def main() -> int:
    files = []
    for name in INCLUDE_FILES:
        p = BASE / name
        if p.exists():
            files.append(p)
    for d in INCLUDE_DIRS:
        for p in sorted((BASE / d).rglob("*")):
            if not p.is_file() or p.name in EXCLUDE:
                continue
            if "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            files.append(p)

    entries = []
    for p in sorted(set(files)):
        raw = p.read_bytes()
        entries.append(
            {
                "path": p.relative_to(BASE).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "byte_length": len(raw),
            }
        )

    manifest = {
        "profile": PROFILE_VERSION,
        "package_version": PACKAGE_VERSION,
        "status": "frozen-semantics-pending-external-confirmation",
        "generated_at": "2026-09-20T00:00:00Z",
        "generated_at_note": "固定日期：本包为确定性冻结候选，重新生成时应同步更新并复核摘要",
        "source": git_revision(),
        "authoritative_base": "https://agentnexus.dev/spec/code-review/v1/",
        "conformance": {
            "structural": "schemas/ + fixtures/（本 manifest 覆盖）",
            "behavioral": "CP-01～26 行为测试，未包含在本包内",
            "wire": "未声明；需 L0 binding 定版（bindings/l0-agentnexus-http.md）"
        },
        "file_count": len(entries),
        "files": entries,
        "usage": "其他仓库只引用『版本 + 摘要』；禁止各自修改后仍使用同版本名（§15.9）",
    }

    out = BASE / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] 写入 {out} （{len(entries)} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
