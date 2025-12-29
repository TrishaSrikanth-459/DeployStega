import json
import secrets
from pathlib import Path

MANIFEST_PATH = Path("experiments/experiment_manifest.json")


def generate_id() -> str:
    # 128-bit opaque session ID
    return secrets.token_hex(16)


def main():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"{MANIFEST_PATH} does not exist")

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest["participants"]["sender"]["id"] = generate_id()
    manifest["participants"]["receiver"]["id"] = generate_id()

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("✅ Experiment bootstrapped")
    print("Sender ID  :", manifest["participants"]["sender"]["id"])
    print("Receiver ID:", manifest["participants"]["receiver"]["id"])


if __name__ == "__main__":
    main()
