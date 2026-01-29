from __future__ import annotations

import base64
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple, Dict, Any, List

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.routing_trace import RoutingTraceLogger
from routing.semantic.token_binning import (
    encode_secret_message,
    decode_benign_message,
)
from routing.action_spec import ACTION_SPECS
from scripts.experiment_context import load_experiment_context

Role = Literal["sender", "receiver"]

TRACE_PATH = Path("experiments/routing_trace.jsonl")
PENDING_STATE_PATH = Path("experiments/pending_secret_state.json")

# Explicit, non-covert marker used for controlled testing only.
# This script handles chunking/reassembly of this marker across epochs.
PAYLOAD_CHUNK_MARKER_PREFIX = "[EXPERIMENT_PAYLOAD_B64_CHUNK:"
PAYLOAD_CHUNK_MARKER_SUFFIX = "]"

# Optional: where you can store grounding separately if you want
# (e.g., produced by build_snapshot.py that captures repo file excerpts)
GROUNDING_PATH = Path("experiments/grounding_index.json")


# ============================================================
# Feasibility (allow all)
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
    def is_url_allowed(self, *, epoch, artifact_class, role, url) -> bool:
        return True


# ============================================================
# Time helpers
# ============================================================

def wait_until_epoch_start(epoch_origin_unix: int) -> None:
    while True:
        remaining = epoch_origin_unix - int(time.time())
        if remaining <= 0:
            print("\n=== Epoch 0 has started ===\n")
            return
        print(f"Experiment begins in {remaining} seconds")
        time.sleep(1)


def seconds_until_next_epoch(ctx) -> int:
    elapsed = int(time.time()) - ctx.epoch_origin_unix
    return ctx.epoch_duration_seconds - (elapsed % ctx.epoch_duration_seconds)


def current_epoch(ctx) -> int:
    return max(
        0,
        (int(time.time()) - ctx.epoch_origin_unix) // ctx.epoch_duration_seconds,
    )


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
    sys.exit("Too many invalid attempts.")


# ============================================================
# Resolver construction
# ============================================================

def build_resolver(ctx) -> DeadDropResolver:
    snapshot = read_snapshot(ctx.snapshot_path)

    for cls in snapshot.artifact_classes():
        arts = snapshot.artifacts_of(cls)
        if arts:
            owner, repo = arts[0].identifier[:2]
            break
    else:
        raise RuntimeError("Cannot infer repository identity")

    return DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=AllowAllFeasibility(),
        owner=owner,
        repo=repo,
    )


# ============================================================
# Artifact resolution + normalization
# ============================================================

def resolve_artifact_object(snapshot, artifact_class_name: str, identifier: Tuple):
    for cls in snapshot.artifact_classes():
        if cls.name != artifact_class_name:
            continue
        for art in snapshot.artifacts_of(cls):
            if art.identifier == identifier:
                return art
    raise RuntimeError(f"Artifact not found: class={artifact_class_name}, identifier={identifier}")


def extract_artifact_text(artifact_obj) -> str:
    """
    Safely extract textual content from ANY SnapshotArtifact.
    Never raises. Never assumes schema.
    """
    for attr in ("body", "message", "description", "text", "title"):
        val = getattr(artifact_obj, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


# ============================================================
# Grounding loader (NO snapshot.content_index)
# ============================================================

def _load_json_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_repo_grounding(*, snapshot_path: str, owner: str, repo: str) -> Dict[str, str]:
    """
    Returns {path -> excerpt} if grounding is available, else {}.

    Priority:
      1) Separate grounding_index.json (recommended stable interface)
      2) Fat snapshot JSON that includes content_index (if you used build_snapshot.py)
      3) Otherwise empty dict

    IMPORTANT:
    - Routing snapshots produced by repository_snapshot/serializer.py do NOT carry content_index.
    - So we never touch snapshot.content_index here.
    """
    # (1) Separate grounding file
    g = _load_json_if_exists(GROUNDING_PATH)
    if g:
        key = f"Repository:{owner}/{repo}"
        content = g.get(key)
        if isinstance(content, dict):
            files = content.get("files", {})
            if isinstance(files, dict):
                return {str(k): str(v) for k, v in files.items() if isinstance(k, str) and isinstance(v, str)}

    # (2) Fat snapshot (raw JSON)
    raw = _load_json_if_exists(Path(snapshot_path))
    if raw:
        ci = raw.get("content_index")
        if isinstance(ci, dict):
            key = f"Repository:{owner}/{repo}"
            content = ci.get(key, {})
            if isinstance(content, dict):
                files = content.get("files", {})
                if isinstance(files, dict):
                    return {str(k): str(v) for k, v in files.items() if isinstance(k, str) and isinstance(v, str)}

    return {}


# ============================================================
# Action semantics (keyword-based publishability)
# ============================================================

def sender_can_publish_stegotext(artifact_class: str) -> bool:
    sender_steps = ACTION_SPECS.get(artifact_class, {}).get("sender", [])
    if not sender_steps:
        return False

    MUTATION_KEYWORDS = (
        "create",
        "edit",
        "modify",
        "add",
        "submit",
        "save",
        "update",
        "rewrite",
        "comment",
        "reply",
        "post",
        "write",
        "upload",
    )

    PROHIBITIONS = (
        "do not",
        "don't",
        "without creating",
        "without modifying",
        "do not attempt",
        "do not change",
        "do not create",
        "do not edit",
        "do not submit",
        "do not save",
        "do not mark",
        "do not apply",
        "treat this as a benign baseline",
        "observe",
        "review",
        "read-only",
        "read only",
    )

    for step in sender_steps:
        for action in step:
            action_l = action.lower()
            if any(p in action_l for p in PROHIBITIONS):
                continue
            if any(k in action_l for k in MUTATION_KEYWORDS):
                return True

    return False


# ============================================================
# Action printing
# ============================================================

def print_required_actions(artifact: str, role: Role) -> None:
    actions = ACTION_SPECS.get(artifact, {}).get(role, [])
    if not actions:
        print("\n(No required actions)")
        return
    print("\n--- REQUIRED ACTIONS ---")
    for step in actions:
        for action in step:
            print(f"• {action}")


# ============================================================
# Sender flow helpers
# ============================================================

def normalize_plans(raw, default_artifact_class: str) -> List[Dict[str, str]]:
    """
    token_binning may return:
      - str (single text)
      - list[dict] (multiple plans/chunks)
    Normalize to list[dict] with keys: artifact_class, stego_text
    """
    if isinstance(raw, str):
        return [{"artifact_class": default_artifact_class, "stego_text": raw}]
    if isinstance(raw, list):
        out: List[Dict[str, str]] = []
        for p in raw:
            if not isinstance(p, dict):
                raise TypeError(f"encode_secret_message plan must be dict, got {type(p)}")
            ac = p.get("artifact_class", default_artifact_class)
            st = p.get("stego_text", "")
            if not isinstance(ac, str) or not isinstance(st, str):
                raise TypeError("plan dict must have string keys/values for artifact_class/stego_text")
            out.append({"artifact_class": ac, "stego_text": st})
        return out
    raise TypeError(f"encode_secret_message returned unsupported type: {type(raw)}")


# ============================================================
# Persistent session state for multi-epoch transmission
# (explicit, non-covert test payload chunking)
# ============================================================

@dataclass
class PendingSecretState:
    payload_b64: str
    chunk_size: int
    next_chunk_index: int  # 0-based

    def total_chunks(self) -> int:
        if self.chunk_size <= 0:
            return 1
        return (len(self.payload_b64) + self.chunk_size - 1) // self.chunk_size

    def has_remaining(self) -> bool:
        return self.next_chunk_index < self.total_chunks()

    def current_chunk(self) -> str:
        start = self.next_chunk_index * self.chunk_size
        end = min(len(self.payload_b64), start + self.chunk_size)
        return self.payload_b64[start:end]

    def advance(self) -> None:
        self.next_chunk_index += 1


def load_pending_state() -> Optional[PendingSecretState]:
    if not PENDING_STATE_PATH.exists():
        return None
    try:
        data = json.loads(PENDING_STATE_PATH.read_text(encoding="utf-8"))
        payload_b64 = data["payload_b64"]
        chunk_size = int(data["chunk_size"])
        next_chunk_index = int(data["next_chunk_index"])
        if not isinstance(payload_b64, str) or not payload_b64:
            return None
        st = PendingSecretState(payload_b64=payload_b64, chunk_size=chunk_size, next_chunk_index=next_chunk_index)
        return st if st.has_remaining() else None
    except Exception:
        return None


def save_pending_state(state: PendingSecretState) -> None:
    PENDING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_STATE_PATH.write_text(
        json.dumps(
            {
                "payload_b64": state.payload_b64,
                "chunk_size": state.chunk_size,
                "next_chunk_index": state.next_chunk_index,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_pending_state() -> None:
    try:
        if PENDING_STATE_PATH.exists():
            PENDING_STATE_PATH.unlink()
    except Exception:
        pass


def make_chunk_marker(chunk_b64: str, chunk_index: int, total_chunks: int) -> str:
    # Example:
    # [EXPERIMENT_PAYLOAD_B64_CHUNK:2/5:SGVsbG8=]
    return f"{PAYLOAD_CHUNK_MARKER_PREFIX}{chunk_index + 1}/{total_chunks}:{chunk_b64}{PAYLOAD_CHUNK_MARKER_SUFFIX}"


def parse_chunk_marker(text: str) -> Optional[Tuple[int, int, str]]:
    """
    Return (chunk_index_0_based, total_chunks, chunk_b64) if marker found else None.
    """
    if PAYLOAD_CHUNK_MARKER_PREFIX not in text:
        return None
    try:
        start = text.index(PAYLOAD_CHUNK_MARKER_PREFIX) + len(PAYLOAD_CHUNK_MARKER_PREFIX)
        end = text.index(PAYLOAD_CHUNK_MARKER_SUFFIX, start)
        inner = text[start:end].strip()  # e.g. "2/5:SGVsbG8="
        frac, chunk_b64 = inner.split(":", 1)
        a, b = frac.split("/", 1)
        chunk_num = int(a)
        total = int(b)
        if chunk_num < 1 or total < 1 or chunk_num > total:
            return None
        return (chunk_num - 1, total, chunk_b64.strip())
    except Exception:
        return None


# ============================================================
# Sender orchestration
# ============================================================

def sender_observe_only(
    *,
    trace_logger: RoutingTraceLogger,
    ctx,
    epoch_now: int,
    role: Role,
    artifact_class: str,
    identifier: Tuple,
    url: str,
) -> None:
    print("\n(No writable surface for sender this epoch; do NOT publish.)")
    print_required_actions(artifact_class, role)

    trace_logger.append(
        experiment_id=ctx.experiment_id,
        role=role,
        epoch=epoch_now,
        artifact_class=artifact_class,
        identifier=identifier,
        url=url,
        semantic_text="",
        semantic_label="deferred_no_writable_surface",
        semantic_content_type="TokenBinning_ExplicitTesting",
    )


def sender_publish_one_epoch(
    *,
    trace_logger: RoutingTraceLogger,
    ctx,
    epoch_now: int,
    role: Role,
    artifact_class: str,
    identifier: Tuple,
    url: str,
    artifact_context: dict,
) -> None:
    """
    If there is a pending secret, emit the NEXT chunk without prompting.
    If there is no pending secret, prompt ONCE, create pending state, emit first chunk.
    """
    CHUNK_SIZE_B64_CHARS = 32  # explicit marker chunking

    pending = load_pending_state()

    if pending is None:
        secret = input("Enter SECRET message:\n> ").strip()
        if not secret:
            print("\n[WARN] Empty secret; nothing to encode/publish this epoch.")
            print_required_actions(artifact_class, role)

            trace_logger.append(
                experiment_id=ctx.experiment_id,
                role=role,
                epoch=epoch_now,
                artifact_class=artifact_class,
                identifier=identifier,
                url=url,
                semantic_text="",
                semantic_label="skipped_empty_secret",
                semantic_content_type="TokenBinning_ExplicitTesting",
            )
            return

        payload_b64 = base64.urlsafe_b64encode(secret.encode("utf-8")).decode("ascii")
        pending = PendingSecretState(payload_b64=payload_b64, chunk_size=CHUNK_SIZE_B64_CHARS, next_chunk_index=0)
        save_pending_state(pending)

    total = pending.total_chunks()
    chunk_b64 = pending.current_chunk()
    marker = make_chunk_marker(chunk_b64, pending.next_chunk_index, total)

    # Generate artifact-aware benign text (no covert embedding); append explicit chunk marker.
    raw = encode_secret_message(
        secret_message="",  # explicit payload is separate for testing
        epoch=epoch_now,
        artifact_class=artifact_class,
        artifact_context=artifact_context,
    )
    plans = normalize_plans(raw, artifact_class)

    plan0 = plans[0]
    stego_text = (plan0.get("stego_text") or "").rstrip()
    if stego_text:
        stego_text = stego_text + "\n\n" + marker
    else:
        stego_text = marker

    print(f"\n--- Stegotext (epoch payload {pending.next_chunk_index + 1}/{total}) ---")
    print(stego_text)

    trace_logger.append(
        experiment_id=ctx.experiment_id,
        role=role,
        epoch=epoch_now,
        artifact_class=plan0.get("artifact_class", artifact_class),
        identifier=identifier,
        url=url,
        semantic_text=stego_text,
        semantic_label="explicit_testing_payload",
        semantic_content_type="TokenBinning_ExplicitTesting",
    )

    pending.advance()
    if pending.has_remaining():
        save_pending_state(pending)
        print(f"\n[INFO] Payload incomplete: sent {pending.next_chunk_index}/{total} chunks so far.")
    else:
        clear_pending_state()
        print("\n[INFO] Payload complete: all chunks emitted. Next writable epoch will prompt for a new secret.")

    print_required_actions(artifact_class, role)


# ============================================================
# Receiver orchestration: reassemble explicit chunks across epochs
# ============================================================

RECEIVER_BUFFER_PATH = Path("experiments/receiver_payload_buffer.json")


def load_receiver_buffer() -> Dict[str, Any]:
    if not RECEIVER_BUFFER_PATH.exists():
        return {"total": None, "chunks": {}}
    try:
        data = json.loads(RECEIVER_BUFFER_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"total": None, "chunks": {}}
    except Exception:
        return {"total": None, "chunks": {}}


def save_receiver_buffer(buf: Dict[str, Any]) -> None:
    RECEIVER_BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIVER_BUFFER_PATH.write_text(json.dumps(buf, indent=2), encoding="utf-8")


def try_finalize_receiver_buffer(buf: Dict[str, Any]) -> Optional[str]:
    total = buf.get("total")
    chunks: Dict[str, str] = buf.get("chunks", {})
    if not isinstance(total, int) or total < 1:
        return None
    if not isinstance(chunks, dict):
        return None
    if len(chunks) < total:
        return None

    assembled = ""
    for i in range(total):
        key = str(i)
        if key not in chunks:
            return None
        assembled += chunks[key]

    try:
        raw = base64.urlsafe_b64decode(assembled.encode("ascii"))
        msg = raw.decode("utf-8", errors="strict")
        try:
            RECEIVER_BUFFER_PATH.unlink(missing_ok=True)  # py3.11 ok; harmless if not
        except Exception:
            pass
        return msg
    except Exception:
        return None


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("\n=== DeployStega Dead Drop Console ===\n")

    ctx = load_experiment_context()
    snapshot = read_snapshot(ctx.snapshot_path)

    if time.time() < ctx.epoch_origin_unix:
        wait_until_epoch_start(ctx.epoch_origin_unix)

    while True:
        r = input("Select role [sender|receiver]: ").strip().lower()
        if r in ("sender", "receiver"):
            role: Role = r  # type: ignore
            break

    verify_identity_with_backoff(ctx, role)

    resolver = build_resolver(ctx)
    trace_logger = RoutingTraceLogger(TRACE_PATH)

    last_epoch: Optional[int] = None

    while True:
        if ctx.epoch_end_unix and time.time() >= ctx.epoch_end_unix:
            print("\n=== Experiment ended ===")
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

            artifact_class = result["artifactClass"]
            identifier = tuple(result["identifier"])
            url = result["url"]

            artifact_obj = resolve_artifact_object(snapshot, artifact_class, identifier)

            # Grounding is repo-wide; infer from identifier
            owner, repo = identifier[:2]
            repo_files = load_repo_grounding(snapshot_path=ctx.snapshot_path, owner=owner, repo=repo)

            artifact_context = {
                "kind": artifact_obj.artifact_class.name,
                "artifact_class": artifact_obj.artifact_class.name,
                "text": extract_artifact_text(artifact_obj),
                "files": repo_files,  # may be {}, but always present
            }

            print("\n=== DEAD DROP ===")
            print(f"Epoch   : {epoch_now}")
            print(f"Carrier : {artifact_class}")
            print(f"URL     : {url}\n")

            if role == "sender":
                if not sender_can_publish_stegotext(artifact_class):
                    sender_observe_only(
                        trace_logger=trace_logger,
                        ctx=ctx,
                        epoch_now=epoch_now,
                        role=role,
                        artifact_class=artifact_class,
                        identifier=identifier,
                        url=url,
                    )
                else:
                    sender_publish_one_epoch(
                        trace_logger=trace_logger,
                        ctx=ctx,
                        epoch_now=epoch_now,
                        role=role,
                        artifact_class=artifact_class,
                        identifier=identifier,
                        url=url,
                        artifact_context=artifact_context,
                    )

            else:
                benign = input("Paste RECEIVED benign text:\n> ").strip()

                chunk = parse_chunk_marker(benign)
                if chunk is not None:
                    idx0, total, chunk_b64 = chunk
                    buf = load_receiver_buffer()
                    buf["total"] = total
                    chunks = buf.get("chunks", {})
                    if not isinstance(chunks, dict):
                        chunks = {}
                    chunks[str(idx0)] = chunk_b64
                    buf["chunks"] = chunks
                    save_receiver_buffer(buf)

                    print(f"\n[INFO] Received payload chunk {idx0 + 1}/{total}.")
                    msg = try_finalize_receiver_buffer(buf)
                    if msg is None:
                        print("[INFO] Payload incomplete; wait for more epochs.")
                    else:
                        print("\n--- DECODED (EXPLICIT TEST PAYLOAD) ---")
                        print(msg)
                else:
                    secret = decode_benign_message(
                        benign_text=benign,
                        epoch=epoch_now,
                        artifact_class=artifact_class,
                        artifact_context=artifact_context,
                    )
                    print("\n--- DECODED SECRET ---")
                    print(secret)

                trace_logger.append(
                    experiment_id=ctx.experiment_id,
                    role=role,
                    epoch=epoch_now,
                    artifact_class=artifact_class,
                    identifier=identifier,
                    url=url,
                    semantic_text=benign,
                    semantic_label="received",
                    semantic_content_type="TokenBinning_ExplicitTesting",
                )

        time.sleep(seconds_until_next_epoch(ctx))


if __name__ == "__main__":
    main()


