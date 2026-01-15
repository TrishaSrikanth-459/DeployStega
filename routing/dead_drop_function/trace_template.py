"""
trace_template.py

Template schema for benign interaction traces and derived probabilities.

You DON'T have traces yet, so this provides:
- a JSON template writer
- a loader
- a minimal structure that FeasibilityRegion implementations can consume

Design goal:
- Keep this strictly "data plumbing" (no learning/training code)
- Allow you to plug in empirical probabilities later
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class BenignTraceModelData:
    """
    Per-epoch (or per-epoch-mod-k) probabilities for benign interaction classes + URL surfaces.
    """
    # Example:
    # class_probs["Issues_Benign"] = 0.12
    class_probs: Dict[str, float]

    # Example:
    # url_probs["Issues_Benign"]["https://github.com/o/r/issues"] = 1.0
    url_probs: Dict[str, Dict[str, float]]

    # Optional: role-conditioning (if you model sender/receiver differently)
    # role_class_probs["sender"]["Issues_Benign"] = ...
    role_class_probs: Optional[Dict[str, Dict[str, float]]] = None
    role_url_probs: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None


def write_blank_template(path: str, *, owner: str, repo: str, benign_urls: Dict[str, List[str]]) -> None:
    """
    Writes a *blank but structurally correct* template.

    - class_probs are uniform over classes
    - url_probs uniform over URLs inside each class
    """
    classes = sorted(benign_urls.keys())
    if not classes:
        raise ValueError("benign_urls is empty")

    class_p = 1.0 / len(classes)
    class_probs = {c: class_p for c in classes}

    url_probs: Dict[str, Dict[str, float]] = {}
    for c in classes:
        urls = benign_urls[c]
        if not urls:
            continue
        p = 1.0 / len(urls)
        url_probs[c] = {u: p for u in urls}

    data = {
        "version": 1,
        "owner": owner,
        "repo": repo,
        "class_probs": class_probs,
        "url_probs": url_probs,
        "notes": {
            "how_to_use": [
                "Replace class_probs with empirical probabilities learned from benign trace logs.",
                "Replace url_probs[class] with empirical URL-surface probabilities for that class.",
                "If you later condition on role, add role_class_probs and role_url_probs."
            ]
        }
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_trace_model(path: str) -> BenignTraceModelData:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    class_probs = raw.get("class_probs", {})
    url_probs = raw.get("url_probs", {})
    role_class_probs = raw.get("role_class_probs")
    role_url_probs = raw.get("role_url_probs")

    if not isinstance(class_probs, dict) or not isinstance(url_probs, dict):
        raise ValueError("Invalid trace model file: class_probs/url_probs missing or wrong type")

    # minimal validation
    for k, v in class_probs.items():
        if not isinstance(k, str) or not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f"Invalid class_probs entry: {k}={v}")

    for cls, probs in url_probs.items():
        if not isinstance(cls, str) or not isinstance(probs, dict):
            raise ValueError(f"Invalid url_probs[{cls}]")
        for url, p in probs.items():
            if not isinstance(url, str) or not isinstance(p, (int, float)) or p < 0:
                raise ValueError(f"Invalid url_probs[{cls}][{url}]={p}")

    return BenignTraceModelData(
        class_probs={k: float(v) for k, v in class_probs.items()},
        url_probs={cls: {u: float(p) for u, p in probs.items()} for cls, probs in url_probs.items()},
        role_class_probs=role_class_probs,
        role_url_probs=role_url_probs,
    )
