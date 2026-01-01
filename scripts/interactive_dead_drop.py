"""
interactive_dead_drop.py

Interactive inspection console for the DeployStega dead-drop resolver.

Responsibilities:
- Explicitly warn about collaborator requirement
- Load experiment context and snapshot
- Verify participant identity
- Derive logical epoch deterministically from FIXED T₀
- Invoke deterministic resolver
- Display resolved URL and role-specific action instructions
- Emit a URL ONLY when explicitly requested by the user

Non-responsibilities:
- No routing logic
- No feasibility learning
- No snapshot generation
- No permission probing
- No delivery guarantees

CRITICAL TIMING MODEL:
- Epoch origin T₀ is fixed out of band and loaded from the experiment manifest
- Running this script does NOT start or reset epoch counting
- Each resolution computes the current epoch relative to T₀
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
    All namespace-valid URLs are treated as feasible.
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

    IMPORTANT:
    - Epoch indices are computed relative to FIXED T₀
    - Script execution time does NOT affect epoch origin
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
- All sender actions MUST be identifier-preserving

Repositories where the sender is not a collaborator are NOT supported.

This requirement is an experimental precondition.
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

    print(
        "Type ENTER to resolve the current epoch.\n"
        "Press Ctrl+C to terminate the session.\n"
    )

    # --------------------------------------------------------
    # Interactive resolution loop (user-driven)
    # --------------------------------------------------------

    try:
        while True:
            input("Resolve next dead drop? (ENTER = yes) ")

            epoch_now = current_epoch(ctx)

            if role == "sender":
                epochs = [epoch_now]
            else:
                epochs = list(
                    range(
                        max(0, epoch_now - ctx.epoch_window_size),
                        epoch_now + 1,
                    )
                )

            for t in epochs:
                result = resolver.resolve(
                    epoch=t,
                    sender_id=ctx.sender_id,
                    receiver_id=ctx.receiver_id,
                    role=role,
                )

                artifact = result["artifactClass"]
                identifier = result["identifier"]
                url = result["url"]

                print("\n=== DEAD DROP RESOLUTION ===")
                print("Epoch          :", t)
                print("Artifact Class :", artifact)
                print("Identifier     :", identifier)
                print("URL            :", url)

                print("\nACTION REQUIRED:")
                actions = ACTION_SPECS[artifact][role]
                action_idx = t % len(actions)
                selected_action = actions[action_idx]

                print(
                    f"(Selected action {action_idx + 1} of {len(actions)} "
                    f"for role '{role}')"
                )
                for i, step in enumerate(selected_action, start=1):
                    print(f"{i}. {step}")

                print("\n---")

                # Sender resolves exactly one epoch per request
                if role == "sender":
                    break

    except KeyboardInterrupt:
        print("\n\n[Session terminated by user]")
        print("No state persisted. No coordination occurred.\n")


if __name__ == "__main__":
    main()
