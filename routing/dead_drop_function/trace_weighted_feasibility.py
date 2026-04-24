"""
trace_weighted_feasibility.py – Concrete feasibility region using your generated traces.
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import List, Optional
from routing.dead_drop_function.feasibility_region import FeasibilityRegion, Role


class TraceBasedFeasibilityRegion(FeasibilityRegion):
    """Feasibility region learned from actual trace files."""

    def __init__(self, trace_dir: str):
        self.trace_dir = Path(trace_dir)
        # Structure: [epoch][artifact_class][role] -> set of URLs
        self.url_observations = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        self._load_traces()

    def _load_traces(self):
        """Load all trace files and record observed URLs."""
        trace_files = sorted(self.trace_dir.glob("user_*.jsonl"))
        print(f"Loading {len(trace_files)} trace files for feasibility...")

        for fpath in trace_files:
            with open(fpath, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        epoch = event.get('epoch', 0)
                        artifact_class = event.get('artifact_class', '')
                        url = event.get('url', '')
                        role = event.get('role', 'user')  # 'user' in traces

                        # Map 'user' to both sender and receiver for feasibility
                        if role == 'user':
                            if artifact_class and url:
                                self.url_observations[epoch][artifact_class]['sender'].add(url)
                                self.url_observations[epoch][artifact_class]['receiver'].add(url)
                        else:
                            if artifact_class and url:
                                self.url_observations[epoch][artifact_class][role].add(url)
                    except Exception as e:
                        print(f"Warning: could not parse line in {fpath}: {e}")
                        continue

        print(f"Loaded feasibility data for {len(self.url_observations)} epochs")

    def is_url_allowed(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> bool:
        """A URL is allowed if it appeared in benign traces for this context."""
        return url in self.url_observations[epoch][artifact_class].get(role, set())

    def url_weight(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> Optional[float]:
        """
        Return weight proportional to frequency (uniform if observed).
        Since we don't track frequencies, return 1.0 if allowed, None otherwise.
        """
        if self.is_url_allowed(epoch=epoch, artifact_class=artifact_class, role=role, url=url):
            return 1.0
        return None

    def get_allowed_urls(self, *, epoch: int, artifact_class: str, role: Role) -> List[str]:
        """Get all URLs observed for this context."""
        return list(self.url_observations[epoch][artifact_class].get(role, set()))


class AllowAllFeasibilityRegion(FeasibilityRegion):
    """Fallback that allows all URLs."""

    def is_url_allowed(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> bool:
        return True

    def url_weight(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> Optional[float]:
        return 1.0