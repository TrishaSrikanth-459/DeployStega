from __future__ import annotations

import sys
import time
import json
from pathlib import Path
from typing import Literal

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.routing_trace import RoutingTraceLogger
from routing.action_spec import ACTION_SPECS
from scripts.experiment_context import load_experiment_context

Role = Literal["sender", "receiver"]

LOCKOUT_STATE_PATH = Path.home() / ".deploystega_lockout.json"
TRACE_PATH = Path("experiments/routing_trace.jsonl")

# iPhone-style escalating lockout (minutes)
LOCKOUT_SCHEDULE_MINUTES = [1, 5, 10, 20, 40]
MAX_FAILURE_ROUND = len(LOCKOUT_SCHEDULE_MINUTES) - 1


# ============================================================
# Feasibility (temporary allow-all)
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
        raise RuntimeError("Cannot infer owner/repo from snapshot")

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
    return (now - ctx.epoch_origin_unix) // ctx.epoch_duration_seconds


def seconds_until_next_epoch(ctx) -> int:
    now = int(time.time())
    elapsed = now - ctx.epoch_origin_unix
    remainder = elapsed % ctx.epoch_duration_seconds
    return ctx.epoch_duration_seconds - remainder


def wait_until_epoch_start(ctx) -> None:
    """
    Human-friendly countdown policy:
    - Print only when minute value changes
    - Announce once at 30s and 15s
    - Final 5–4–3–2–1 countdown
    """
    printed_minutes = set()
    announced_30 = False
    announced_15 = False

    while True:
        now = int(time.time())
        remaining = ctx.epoch_origin_unix - now

        if remaining <= 0:
            print("\n=== Epoch started ===\n")
            return

        # -------------------------------
        # Phase 1: minute-level updates
        # -------------------------------
        if remaining > 30:
            minutes = remaining // 60

            if minutes > 0 and minutes not in printed_minutes:
                printed_minutes.add(minutes)
                print(
                    f"Experiment has not started yet. Begins in "
                    f"{minutes} minute{'s' if minutes != 1 else ''}"
                )

            # Sleep conservatively toward next boundary
            time.sleep(1)
            continue

        # -------------------------------
        # Phase 2: threshold announcements
        # -------------------------------
        if remaining <= 30 and not announced_30:
            print("Experiment has not started yet. Begins in 30 seconds")
            announced_30 = True

        if remaining <= 15 and not announced_15:
            print("Experiment has not started yet. Begins in 15 seconds")
            announced_15 = True

        # -------------------------------
        # Phase 3: final countdown
        # -------------------------------
        if remaining <= 5:
            for i in range(remaining, 0, -1):
                print(f"Experiment has not started yet. Begins in {i}")
                time.sleep(1)
            print("\n=== Epoch started ===\n")
            return

        time.sleep(1)


def enforce_epoch_end(ctx) -> None:
    if ctx.epoch_end_unix is None:
        return

    if int(time.time()) >= ctx.epoch_end_unix:
        print("\n=== Experiment session has ended ===")
        sys.exit(0)


# ============================================================
# Lockout persistence helpers
# ============================================================

def load_lockout_state() -> dict:
    if not LOCKOUT_STATE_PATH.exists():
        return {"failure_round": 0, "locked_until_unix": 0}
    try:
        return json.loads(LOCKOUT_STATE_PATH.read_text())
    except Exception:
        return {"failure_round": 0, "locked_until_unix": 0}


def save_lockout_state(state: dict) -> None:
    LOCKOUT_STATE_PATH.write_text(json.dumps(state, indent=2))


# ============================================================
# Identity verification with backoff
# ============================================================

def verify_identity_with_backoff(ctx, role: Role) -> None:
    state = load_lockout_state()

    while True:
        now = int(time.time())

        if state["locked_until_unix"] > now:
            remaining = state["locked_until_unix"] - now
            mins = remaining // 60
            secs = remaining % 60
            print(
                f"\nToo many invalid attempts.\n"
                f"Locked for {mins}m {secs}s.\n"
            )
            time.sleep(min(remaining, 60))
            continue

        for attempt in range(1, 6):
            my_id = input(f"Enter your {role}_id ({attempt}/5): ").strip()
            if ctx.verify_identity(role, my_id):
                print("[OK] Identity verified.\n")
                save_lockout_state({"failure_round": 0, "locked_until_unix": 0})
                return
            print("Invalid identity.")

        next_round = min(state["failure_round"] + 1, MAX_FAILURE_ROUND)
        wait_minutes = LOCKOUT_SCHEDULE_MINUTES[next_round]

        state["failure_round"] = next_round
        state["locked_until_unix"] = int(time.time()) + wait_minutes * 60
        save_lockout_state(state)

        print(
            f"\nToo many invalid attempts.\n"
            f"Locked for {wait_minutes} minutes.\n"
        )


# ============================================================
# Main loop (automatic, mandatory participation)
# ============================================================

def main():
    print("\n=== DeployStega Dead Drop Console (Automatic Mode) ===\n")

    ctx = load_experiment_context()

    wait_until_epoch_start(ctx)

    while True:
        role_input = input("Select role [sender|receiver]: ").strip().lower()

        if not role_input:
            continue

        if role_input in ("sender", "receiver"):
            role: Role = role_input  # type: ignore
            break

        print("Invalid role. Please enter 'sender' or 'receiver'.")

    verify_identity_with_backoff(ctx, role)

    resolver = build_resolver(ctx)
    trace_logger = RoutingTraceLogger(TRACE_PATH)

    print("Automatic epoch resolution started.")
    print("Participation is mandatory. Press Ctrl+C to terminate.\n")

    last_epoch = None

    try:
        while True:
            enforce_epoch_end(ctx)

            epoch_now = current_epoch(ctx)

            if epoch_now != last_epoch:
                last_epoch = epoch_now

                epochs = (
                    [epoch_now]
                    if role == "sender"
                    else range(
                        max(0, epoch_now - ctx.epoch_window_size),
                        epoch_now + 1,
                    )
                )

                for t in epochs:
                    enforce_epoch_end(ctx)

                    result = resolver.resolve(
                        epoch=t,
                        sender_id=ctx.sender_id,
                        receiver_id=ctx.receiver_id,
                        role=role,
                    )

                    artifact = result["artifactClass"]
                    identifier = result["identifier"]
                    url = result["url"]

                    trace_logger.append(
                        experiment_id=ctx.experiment_id,
                        epoch=t,
                        role=role,
                        artifact_class=artifact,
                        identifier=identifier,
                        url=url,
                    )

                    print("\n=== DEAD DROP ===")
                    print("Epoch:", t)
                    print("Artifact Class:", artifact)
                    print("Identifier:", identifier)
                    print("URL:", url)

                    actions = ACTION_SPECS[artifact][role]
                    selected = actions[t % len(actions)]

                    print("\nACTION REQUIRED:")
                    for i, step in enumerate(selected, start=1):
                        print(f"{i}. {step}")

                    if role == "sender":
                        break

            sleep_time = seconds_until_next_epoch(ctx)

            if ctx.epoch_end_unix is not None:
                remaining = ctx.epoch_end_unix - int(time.time())
                sleep_time = max(0, min(sleep_time, remaining))

            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\n[Session terminated by user]")


if __name__ == "__main__":
    main()

