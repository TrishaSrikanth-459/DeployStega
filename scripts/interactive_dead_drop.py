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
from routing.semantic.placeholder_generator import generate_placeholder_stegotext
from routing.action_spec import ACTION_SPECS
from scripts.experiment_context import load_experiment_context

Role = Literal["sender", "receiver"]

LOCKOUT_STATE_PATH = Path.home() / ".deploystega_lockout.json"
TRACE_PATH = Path("experiments/routing_trace.jsonl")

LOCKOUT_SCHEDULE_MINUTES = [1, 5, 10, 20, 40]
MAX_FAILURE_ROUND = len(LOCKOUT_SCHEDULE_MINUTES) - 1


# ============================================================
# Feasibility (temporary allow-all)
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
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
    printed_minutes: set[int] = set()
    announced_30 = False
    announced_15 = False

    while True:
        now = int(time.time())
        remaining = ctx.epoch_origin_unix - now

        if remaining <= 0:
            print("\n=== Epoch started ===\n")
            return

        if remaining > 30:
            minutes = remaining // 60
            if minutes >= 1 and minutes not in printed_minutes:
                printed_minutes.add(minutes)
                print(
                    f"Experiment has not started yet. Begins in "
                    f"{minutes} minute{'s' if minutes != 1 else ''}"
                )
            time.sleep(min(remaining - minutes * 60, 30))
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
            print("\n=== Epoch started ===\n")
            return

        time.sleep(1)


def enforce_epoch_end(ctx) -> None:
    if ctx.epoch_end_unix is not None and int(time.time()) >= ctx.epoch_end_unix:
        print("\n=== Experiment session has ended ===")
        sys.exit(0)


# ============================================================
# Identity verification (unchanged)
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


def verify_identity_with_backoff(ctx, role: Role) -> None:
    state = load_lockout_state()

    while True:
        now = int(time.time())

        if state["locked_until_unix"] > now:
            remaining = state["locked_until_unix"] - now
            mins = remaining // 60
            secs = remaining % 60
            print(f"\nLocked for {mins}m {secs}s.\n")
            time.sleep(min(remaining, 60))
            continue

        for attempt in range(1, 6):
            my_id = input(f"Enter your {role}_id ({attempt}/5): ").strip()
            if ctx.verify_identity(role, my_id):
                save_lockout_state({"failure_round": 0, "locked_until_unix": 0})
                return
            print("Invalid identity.")

        next_round = min(state["failure_round"] + 1, MAX_FAILURE_ROUND)
        wait_minutes = LOCKOUT_SCHEDULE_MINUTES[next_round]
        state["failure_round"] = next_round
        state["locked_until_unix"] = int(time.time()) + wait_minutes * 60
        save_lockout_state(state)
        print(f"\nLocked for {wait_minutes} minutes.\n")


# ============================================================
# Main loop
# ============================================================

def main():
    print("\n=== DeployStega Dead Drop Console (Automatic Mode) ===\n")

    ctx = load_experiment_context()
    wait_until_epoch_start(ctx)

    role: Role
    while True:
        r = input("Select role [sender|receiver]: ").strip().lower()
        if r in ("sender", "receiver"):
            role = r  # type: ignore
            break

    verify_identity_with_backoff(ctx, role)

    resolver = build_resolver(ctx)
    trace_logger = RoutingTraceLogger(TRACE_PATH)

    last_epoch = None

    try:
        while True:
            enforce_epoch_end(ctx)
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

                # --------------------------------------------------
                # PLACEHOLDER SEMANTIC GENERATION (FIXED)
                # --------------------------------------------------
                stegotext, meaning = generate_placeholder_stegotext(
                    epoch=epoch_now,
                    artifact_class=artifact,
                )

                trace_logger.append(
                    experiment_id=ctx.experiment_id,
                    epoch=epoch_now,
                    role=role,
                    artifact_class=artifact,
                    identifier=identifier,
                    url=url,
                    semantic_text=stegotext,
                    semantic_meaning=meaning,
                    semantic_label="covert",  # explicit placeholder
                    semantic_content_type=f"{artifact}Placeholder",
                )

                print("\n=== DEAD DROP ===")
                print("Epoch:", epoch_now)
                print("Artifact:", artifact)
                print("URL:", url)
                print("Stegotext (placeholder):")
                print(stegotext)
                print("Meaning:")
                print(meaning)

            time.sleep(seconds_until_next_epoch(ctx))

    except KeyboardInterrupt:
        print("\n[Session terminated]")


if __name__ == "__main__":
    main()
