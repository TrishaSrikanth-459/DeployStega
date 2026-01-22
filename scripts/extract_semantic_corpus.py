from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from typing import Any, Dict


def _stable_id(obj: Dict[str, Any]) -> str:
    # If semantic_ref exists, use it (preferred)
    ref = obj.get("semantic_ref")
    if isinstance(ref, str) and ref.strip():
        return ref.strip()

    # Otherwise derive a stable id from epoch/role/class/url
    material = f"{obj.get('epoch')}|{obj.get('role')}|{obj.get('artifact_class', obj.get('artifactClass'))}|{obj.get('url')}"
    return "sem_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract semantic corpus from routing_trace.jsonl")
    ap.add_argument("--routing-trace", required=True)
    ap.add_argument("--out", required=True, help="Output semantic_corpus.jsonl")
    args = ap.parse_args()

    in_path = Path(args.routing_trace)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with in_path.open("r", encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)

            text = obj.get("semantic_text")
            if not isinstance(text, str):
                continue
            text = text.replace("\x00", "").strip()
            if not text:
                continue

            cls = obj.get("artifact_class", obj.get("artifactClass"))
            if not isinstance(cls, str) or not cls.strip():
                cls = "Unknown"

            fout.write(
                json.dumps(
                    {
                        "id": _stable_id(obj),
                        "type": cls,
                        "text": text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1

    print(f"[OK] Wrote {written} semantic rows to {out_path}")


if __name__ == "__main__":
    main()
