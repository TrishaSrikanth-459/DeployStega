"""
interactive_dead_drop.py

Interactive inspection console for the DeployStega dead-drop resolver.

Responsibilities:
- Explicitly warn about collaborator requirement
- Load experiment context and snapshot
- Verify participant identity
- Derive logical epoch deterministically
- Invoke deterministic resolver
- Display resolved URL and role-specific action instructions

Non-responsibilities:
- No routing logic
- No feasibility learning
- No snapshot generation
- No permission probing
- No delivery guarantees
"""

from __future__ import annotations

import sys
import time
from typing import Literal

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.action_spec import ACTION_SPECS
from scripts.experiment_context import load_experiment_context


Role = Literal["sender", "receiver"]


# ============================================================
# Feasibility (inspection-only, allow-all)
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
    """
    Inspection-only feasibility region.

    This console does not model behavioral constraints.
    """
    def is_url_allowed(self, *, epoch, artifact_class, role, url) -> bool:
        return True


# ============================================================
# Resolver construction
# ============================================================

def build_resolver(ctx) -> DeadDropResolver:
    snapshot = read_snapshot(ctx.snapshot_path)

    owner = repo = None
    for artifact_class in snapshot.artifact_classes():
        artifacts = snapshot.artifacts_of(artifact_class)
        if artifacts:
            owner, repo = artifacts[0].identifier[:2]
            break

    if owner is None or repo is None:
        raise RuntimeError(
            "Snapshot contains no artifacts in any class; cannot infer owner/repo."
        )

    return DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=AllowAllFeasibility(),
        owner=owner,
        repo=repo,
    )


# ============================================================
# Epoch derivation
# ============================================================

def current_epoch(ctx) -> int:
    """
    Deterministically derive the current logical epoch.

    Epochs are analytical indices derived from shared constants,
    NOT synchronized clocks or coordination events.
    """
    now = int(time.time())
    return (now - ctx.epoch_origin_unix) // ctx.epoch_duration_seconds


# ============================================================
# Interactive console
# ============================================================

def main():
    print("\n=== DeployStega Dead Drop Interactive Console ===\n")

    # --------------------------------------------------------
    # HARD EXPERIMENT PRECONDITION
    # --------------------------------------------------------

    print(
        """
IMPORTANT EXPERIMENT REQUIREMENT

The GitHub repository used for this experiment MUST satisfy the following:

- The sender MUST be a collaborator on the repository
- The provided GitHub token MUST have write access
- The sender must be able to:
  • Create issues
  • Edit or create files (commit)
  • Comment on issues, pull requests, and commits

Repositories where the sender is not a collaborator are NOT supported.

This requirement is an experimental precondition.
Routing behavior assumes identifier-preserving write access.
"""
    )

    input("Press Enter to continue only if this requirement is satisfied...")

    # --------------------------------------------------------
    # Load experiment context
    # --------------------------------------------------------

    ctx = load_experiment_context()

    print("\nExperiment ID :", ctx.experiment_id)
    print()

    # --------------------------------------------------------
    # Role selection
    # --------------------------------------------------------

    while True:
        role_input = input("Select role [sender|receiver]: ").strip().lower()
        if role_input in ("sender", "receiver"):
            role: Role = role_input  # type: ignore
            break
        print("Invalid role. Please enter 'sender' or 'receiver'.")

    # --------------------------------------------------------
    # Identity verification
    # --------------------------------------------------------

    my_id = input(f"Enter your {role}_id: ").strip()

    if not ctx.verify_identity(role, my_id):
        print("\n[ERROR] Invalid identity for this experiment.")
        sys.exit(1)

    print("\n[OK] Identity verified.\n")

    # --------------------------------------------------------
    # Resolver setup
    # --------------------------------------------------------

    resolver = build_resolver(ctx)

    # --------------------------------------------------------
    # Epoch handling
    # --------------------------------------------------------

    now_epoch = current_epoch(ctx)

    print(f"Current logical epoch : {now_epoch}")
    print(f"Receiver window size  : {ctx.epoch_window_size} epochs\n")

    if role == "sender":
        epochs_to_inspect = [now_epoch]
    else:
        # Receiver inspects a bounded window of past epochs
        epochs_to_inspect = list(
            range(
                max(0, now_epoch - ctx.epoch_window_size),
                now_epoch + 1,
            )
        )

    # --------------------------------------------------------
    # Resolve + display
    # --------------------------------------------------------

    for epoch in epochs_to_inspect:
        result = resolver.resolve(
            epoch=epoch,
            sender_id=ctx.sender_id,
            receiver_id=ctx.receiver_id,
            role=role,
        )

        artifact = result["artifactClass"]
        identifier = result["identifier"]
        url = result["url"]

        print("\n=== DEAD DROP RESOLUTION ===")
        print("Epoch          :", epoch)
        print("Artifact Class :", artifact)
        print("Identifier     :", identifier)
        print("URL            :", url)

        print("\nACTION REQUIRED:")
        actions = ACTION_SPECS[artifact][role]

        # Deterministically select exactly one action
        action_idx = epoch % len(actions)
        selected_action = actions[action_idx]

        print(
            f"(Selected action {action_idx + 1} of {len(actions)} "
            f"for role '{role}')"
        )
        for i, step in enumerate(selected_action, start=1):
            print(f"{i}. {step}")

        print("\n---")

        if role == "sender":
            break  # sender resolves exactly one epoch

    print("\n(Resolver logic complete. No further interaction assumed.)\n")


if __name__ == "__main__":
    main()
