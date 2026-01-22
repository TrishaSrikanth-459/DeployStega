from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Literal

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.routing_trace import RoutingTraceLogger
from routing.semantic.token_binning_placeholder import (
    encode_secret_message,
    decode_benign_message,
)
from routing.action_spec import ACTION_SPECS
from scripts.experiment_context import load_experiment_context

Role = Literal["sender", "receiver"]

TRACE_PATH = Path("experiments/routing_trace.jsonl")


# ============================================================
# Feasibility (allow-all placeholder)
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
    def is_url_allowed(self, *, epoch, artifact_class, role, url) -> bool:
        return True


# ============================================================
# Identity verification
# ============================================================

def verify_identity_with_backoff(ctx, role: Role) -> None:
    for attempt in range(1, 6):
        user_id = input(f"Enter your {role}_id ({attempt}/5): ").strip()
        if ctx.verify_identity(role, user_id):
            print("[OK] Identity verified.\n")
            return
        print("Invalid identity.\n")

    print("Too many invalid attempts. Exiting.")
    sys.exit(1)


# ============================================================
# Resolver construction
# ============================================================

def build_resolver(ctx) -> DeadDropResolver:
    snapshot = read_snapshot(ctx.snapshot_path)

    owner = repo = None
    for cls in snapshot.artifact_classes():
        arts = snapshot.artifacts_of(cls)
        if arts:
            owner, repo = arts[0].identifier[:2]
            break

    if owner is None:
        raise RuntimeError("Cannot infer repository identity")

    return DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=AllowAllFeasibility(),
        owner=owner,
        repo=repo,
    )


# ============================================================
# Epoch helpers
# ============================================================

def current_epoch(ctx) -> int:
    now = int(time.time())
    return max(0, (now - ctx.epoch_origin_unix) // ctx.epoch_duration_seconds)


# ============================================================
# Pretty-print required actions (FLAT, NO STEPS)
# ============================================================

def print_required_actions(artifact: str, role: Role) -> None:
    actions = ACTION_SPECS[artifact][role]

    print("\n--- REQUIRED ACTIONS ---")
    for action_group in actions:
        for action in action_group:
            print(f"• {action}")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("\n=== DeployStega Dead Drop Console ===\n")

    ctx = load_experiment_context()

    now = int(time.time())
    print("=== Experiment Schedule ===")
    print(f"Current UNIX time : {now}")
    print(f"Epoch origin time : {ctx.epoch_origin_unix}")

    if now < ctx.epoch_origin_unix:
        wait = ctx.epoch_origin_unix - now
        print(f"\nExperiment starts in {wait} seconds. Waiting...\n")
        time.sleep(wait)

    epoch_now = current_epoch(ctx)
    print(f"\n=== Epoch {epoch_now} has started ===\n")

    # ----------------------------------
    # Role selection
    # ----------------------------------
    while True:
        role_input = input("Select role [sender|receiver]: ").strip().lower()
        if role_input in ("sender", "receiver"):
            role: Role = role_input  # type: ignore
            break
        print("Invalid role.\n")

    verify_identity_with_backoff(ctx, role)

    print("\n=== Session Instructions ===")
    if role == "sender":
        print(
            "You will:\n"
            "  • Enter a SECRET message\n"
            "  • Receive BENIGN text to publish\n"
            "  • Follow the required action steps\n"
        )
    else:
        print(
            "You will:\n"
            "  • Receive BENIGN text externally\n"
            "  • Paste it here\n"
            "  • Decode the SECRET message\n"
        )

    resolver = build_resolver(ctx)
    trace_logger = RoutingTraceLogger(TRACE_PATH)

    result = resolver.resolve(
        epoch=epoch_now,
        sender_id=ctx.sender_id,
        receiver_id=ctx.receiver_id,
        role=role,
    )

    artifact = result["artifactClass"]
    identifier = tuple(result["identifier"])
    url = result["url"]

    print("\n=== DEAD DROP ===")
    print(f"Epoch   : {epoch_now}")
    print(f"Artifact: {artifact}")
    print(f"URL     : {url}\n")

    if role == "sender":
        secret = input("Enter SECRET message to send:\n> ").strip()

        benign = encode_secret_message(
            secret_message=secret,
            epoch=epoch_now,
            artifact_class=artifact,
        )

        print("\n--- BENIGN TEXT TO PUBLISH ---")
        print(benign)

        print_required_actions(artifact, role)

        trace_logger.append(
            experiment_id=ctx.experiment_id,
            role=role,
            epoch=epoch_now,
            artifact_class=artifact,
            identifier=identifier,
            url=url,
            semantic_text=benign,
            semantic_label="covert",
            semantic_content_type="TokenBinningPlaceholder",
        )

    else:
        benign = input("Paste RECEIVED benign text:\n> ").strip()

        secret = decode_benign_message(
            benign_text=benign,
            epoch=epoch_now,
            artifact_class=artifact,
        )

        print("\n--- DECODED SECRET MESSAGE ---")
        print(secret)

        trace_logger.append(
            experiment_id=ctx.experiment_id,
            role=role,
            epoch=epoch_now,
            artifact_class=artifact,
            identifier=identifier,
            url=url,
            semantic_text=benign,
            semantic_label="covert",
            semantic_content_type="TokenBinningPlaceholder",
        )


if __name__ == "__main__":
    main()
