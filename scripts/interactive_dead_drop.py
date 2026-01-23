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
# Feasibility (placeholder: allow all)
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
    def is_url_allowed(self, *, epoch, artifact_class, role, url) -> bool:
        return True


# ============================================================
# Countdown utilities
# ============================================================

def wait_until_epoch_start(epoch_origin_unix: int) -> None:
    printed_minutes: set[int] = set()
    announced_30 = False
    announced_15 = False

    while True:
        now = int(time.time())
        remaining = epoch_origin_unix - now

        if remaining <= 0:
            print("\n=== Epoch 0 has started ===\n")
            return

        if remaining > 30:
            minutes = remaining // 60
            if minutes >= 1 and minutes not in printed_minutes:
                printed_minutes.add(minutes)
                print(
                    f"Experiment has not started yet. Begins in "
                    f"{minutes} minute{'s' if minutes != 1 else ''}"
                )
            time.sleep(1)
            continue

        if remaining <= 30 and not announced_30:
            print("Experiment has not started yet. Begins in 30 seconds")
            announced_30 = True

        if remaining <= 15 and not announced_15:
            print("Experiment has not started yet. Begins in 15 seconds")
            announced_15 = True

        if remaining <= 5:
            for i in range(remaining, 0, -1):
                print(f"Experiment has not started yet. Begins in {i}")
                time.sleep(1)
            print("\n=== Epoch 0 has started ===\n")
            return

        time.sleep(1)


def seconds_until_next_epoch(ctx) -> int:
    now = int(time.time())
    elapsed = now - ctx.epoch_origin_unix
    remainder = elapsed % ctx.epoch_duration_seconds
    return ctx.epoch_duration_seconds - remainder


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
# Action printing
# ============================================================

def print_required_actions(artifact: str, role: Role) -> None:
    actions = ACTION_SPECS[artifact][role]
    print("\n--- REQUIRED ACTIONS ---")
    for step in actions:
        for action in step:
            print(f"• {action}")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("\n=== DeployStega Dead Drop Console ===\n")

    ctx = load_experiment_context()

    print("=== Experiment Schedule ===")
    print(f"Current UNIX time : {int(time.time())}")
    print(f"Epoch origin time : {ctx.epoch_origin_unix}\n")

    if time.time() < ctx.epoch_origin_unix:
        wait_until_epoch_start(ctx.epoch_origin_unix)
    else:
        print("\n=== Epoch 0 has started ===\n")

    # -------- Role selection --------
    while True:
        role_input = input("Select role [sender|receiver]: ").strip().lower()
        if not role_input:
            continue
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
            "  • Paste RECEIVED benign text\n"
            "  • Decode the SECRET message\n"
        )

    resolver = build_resolver(ctx)
    trace_logger = RoutingTraceLogger(TRACE_PATH)

    last_epoch: int | None = None

    # ========================================================
    # MAIN EPOCH LOOP (FIX)
    # ========================================================

    while True:
        now = time.time()

        if ctx.epoch_end_unix is not None and now >= ctx.epoch_end_unix:
            print("\n=== Experiment session has ended ===")
            return

        epoch_now = current_epoch(ctx)

        if epoch_now != last_epoch:
            last_epoch = epoch_now

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

        time.sleep(seconds_until_next_epoch(ctx))


if __name__ == "__main__":
    main()

