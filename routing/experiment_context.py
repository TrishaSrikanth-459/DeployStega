import json
from pathlib import Path


class ExperimentContext:
    """
    Immutable experiment configuration shared by sender and receiver.
    """

    def __init__(self, manifest_path: str):
        path = Path(manifest_path)

        if not path.exists():
            raise FileNotFoundError(manifest_path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.experiment_id = data["experiment_id"]
        self.snapshot_path = data["snapshot"]
        self.sender_id = data["participants"]["sender"]["id"]
        self.receiver_id = data["participants"]["receiver"]["id"]

        self._validate_ids()

    def _validate_ids(self):
        for label, sid in [
            ("sender_id", self.sender_id),
            ("receiver_id", self.receiver_id),
        ]:
            if not isinstance(sid, str) or len(sid) < 16:
                raise ValueError(f"{label} is invalid or too short")
