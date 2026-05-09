#!/usr/bin/env python3
"""Remove Markdown backticks from generated covert trace semantic text.

This script is intentionally narrow and idempotent. It only edits JSON objects'
`semantic_text` fields, replacing the literal character ` with an empty string.
It does not rewrite prose, alter routing metadata, change timestamps, touch
identifiers, or modify non-semantic fields.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def iter_jsonl_files(root: Path) -> Iterable[Path]:
    if root.is_file() and root.suffix == ".jsonl":
        yield root
        return

    trace_files: List[Path] = []
    for subdir_name in ("sender", "receiver"):
        subdir = root / subdir_name
        if subdir.exists():
            trace_files.extend(sorted(subdir.glob("*.jsonl")))

    if trace_files:
        yield from trace_files
        return

    # If the user points directly at a generic directory, handle JSONL files
    # immediately under it without recursing into unrelated experiment outputs.
    yield from sorted(root.glob("*.jsonl"))


def clean_record(obj: Dict[str, Any]) -> int:
    text = obj.get("semantic_text")
    if isinstance(text, str) and "`" in text:
        count = text.count("`")
        obj["semantic_text"] = text.replace("`", "")
        return count
    return 0


def clean_file(path: Path, dry_run: bool) -> Dict[str, Any]:
    changed = False
    backticks_removed = 0
    events_seen = 0
    events_changed = 0
    output_lines: List[str] = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            raw = line.rstrip("\n")
            if not raw.strip():
                output_lines.append(raw)
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc

            events_seen += 1
            removed = clean_record(obj) if isinstance(obj, dict) else 0
            if removed:
                changed = True
                events_changed += 1
                backticks_removed += removed
            output_lines.append(json.dumps(obj, ensure_ascii=False))

    if changed and not dry_run:
        path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    return {
        "path": str(path),
        "events_seen": events_seen,
        "events_changed": events_changed,
        "backticks_removed": backticks_removed,
        "changed": changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "trace_root",
        type=Path,
        help="Trace root containing sender/ and receiver/, a directory of JSONL files, or one JSONL file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing files.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Optional JSON summary output path. Defaults to <trace_root>/backtick_cleanup_summary.json when trace_root is a directory.",
    )
    args = parser.parse_args()

    files = list(dict.fromkeys(iter_jsonl_files(args.trace_root)))
    if not files:
        raise SystemExit(f"No JSONL files found under {args.trace_root}")

    file_summaries = [clean_file(path, dry_run=args.dry_run) for path in files]
    summary = {
        "trace_root": str(args.trace_root),
        "dry_run": bool(args.dry_run),
        "files_seen": len(file_summaries),
        "files_changed": sum(1 for item in file_summaries if item["changed"]),
        "events_seen": sum(item["events_seen"] for item in file_summaries),
        "events_changed": sum(item["events_changed"] for item in file_summaries),
        "backticks_removed": sum(item["backticks_removed"] for item in file_summaries),
        "changed_files": [item for item in file_summaries if item["changed"]],
    }

    print(json.dumps(summary, indent=2))

    summary_path = args.summary_path
    if summary_path is None and args.trace_root.is_dir():
        summary_path = args.trace_root / "backtick_cleanup_summary.json"
    if summary_path is not None and not args.dry_run:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
