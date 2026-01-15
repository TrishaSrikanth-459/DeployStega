from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Sequence, Literal

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
    ) -> None:
        ev = RoutingTraceEvent(
            experiment_id=experiment_id,
            ts_unix=int(time.time()),
            epoch=epoch,
            role=role,
            artifact_class=artifact_class,
            identifier=list(identifier),
            url=url,
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ev)) + "\n")
