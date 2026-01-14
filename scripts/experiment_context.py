"""
scripts/experiment_context.py

Thin wrapper for ExperimentContext to match the import used by interactive_dead_drop.py:
    from scripts.experiment_context import load_experiment_context
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Import the class from wherever you placed your canonical file.
# If your canonical file is at scripts/experiment_context.py already, this is self-import safe.
# If you keep ExperimentContext elsewhere, update this import path accordingly.
from scripts.experiment_context_impl import ExperimentContext  # type: ignore


DEFAULT_MANIFEST_PATH = "experiments/experiment_manifest.json"


def load_experiment_context(manifest_path: str = DEFAULT_MANIFEST_PATH) -> ExperimentContext:
    return ExperimentContext(manifest_path)
