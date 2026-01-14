from __future__ import annotations

import argparse
from pathlib import Path

from routing.dead_drop_function.benign_interaction_schema import repo_scoped_urls
from routing.dead_drop_function.trace_template import write_blank_template


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default="experiments/benign_trace_model.json")
    args = ap.parse_args()

    urls = repo_scoped_urls(args.owner, args.repo)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write_blank_template(args.out, owner=args.owner, repo=args.repo, benign_urls=urls)
    print(f"✅ Wrote benign trace model template to {args.out}")


if __name__ == "__main__":
    main()
