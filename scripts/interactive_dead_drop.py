"""
interactive_dead_drop.py

Interactive CLI for observing DeadDropResolver behavior.
"""

import sys
from pathlib import Path

# ============================================================
# Ensure project root is on PYTHONPATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot


# ============================================================
# Feasibility region: allow everything
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
    def is_url_allowed(self, *, epoch, artifact_class, role, url):
        return True


# ============================================================
# Setup resolver once
# ============================================================

SNAPSHOT_PATH = PROJECT_ROOT / "tests" / "snapshots" / "minimal.json"


def build_resolver() -> DeadDropResolver:
    snapshot = read_snapshot(str(SNAPSHOT_PATH))

    first_class = next(iter(snapshot.artifacts))
    first_artifact = snapshot.artifacts[first_class][0]
    owner, repo = first_artifact.identifier[:2]

    return DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=AllowAllFeasibility(),
        owner=owner,
        repo=repo,
    )


# ============================================================
# Interactive loop
# ============================================================

def main():
    resolver = build_resolver()

    print("\n=== Dead Drop Resolver Interactive Console ===")
    print("Type Ctrl+C or Ctrl+D to exit.\n")

    while True:
        try:
            epoch = int(input("epoch (int): ").strip())
            sender = input("sender_id: ").strip()
            receiver = input("receiver_id: ").strip()
            role = input("role [sender|receiver]: ").strip()

            if role not in ("sender", "receiver"):
                print("❌ role must be 'sender' or 'receiver'\n")
                continue

            result = resolver.resolve(
                epoch=epoch,
                sender_id=sender,
                receiver_id=receiver,
                role=role,
            )

            print("\n--- RESOLUTION ---")
            print(f"Artifact Class : {result['artifactClass']}")
            print(f"Identifier     : {result['identifier']}")
            print(f"URL            : {result['url']}")
            print("------------------\n")

        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except EOFError:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()
