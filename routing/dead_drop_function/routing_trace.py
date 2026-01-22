from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Sequence, Literal, Optional, Dict

Role = Literal["sender", "receiver"]


@dataclass(frozen=True)
class RoutingTraceEvent:
    experiment_id: str
    ts_unix: int
    epoch: int
    role: Role
    artifact_class: str
    identifier: list[Any]
    url: str

    # Optional embedded semantic payload (scaffold)
    semantic_text: Optional[str] = None
    semantic_meaning: Optional[str] = None
    semantic_ref: Optional[str] = None
    semantic_label: Optional[str] = None          # "covert" | "benign"
    semantic_content_type: Optional[str] = None   # e.g. "IssueCommentBody"


class RoutingTraceLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        experiment_id: str,
        epoch: int,
        role: Role,
        artifact_class: str,
        identifier: Sequence[Any],
        url: str,

        # Optional semantic payload
        semantic_text: Optional[str] = None,
        semantic_meaning: Optional[str] = None,
        semantic_ref: Optional[str] = None,
        semantic_label: Optional[str] = None,
        semantic_content_type: Optional[str] = None,
    ) -> None:
        ev = RoutingTraceEvent(
            experiment_id=experiment_id,
            ts_unix=int(time.time()),
            epoch=int(epoch),
            role=role,
            artifact_class=str(artifact_class),
            identifier=list(identifier),
            url=str(url),

            semantic_text=semantic_text,
            semantic_meaning=semantic_meaning,
            semantic_ref=semantic_ref,
            semantic_label=semantic_label,
            semantic_content_type=semantic_content_type,
        )

        # Write in a stable schema (snake_case) for the dataset layer
        payload: Dict[str, Any] = asdict(ev)
        payload["timestamp"] = float(payload.pop("ts_unix"))  # dataset code expects timestamp float

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
