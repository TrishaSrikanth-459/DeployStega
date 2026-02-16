from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal, Optional, Tuple, Dict, Any, List

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.routing_trace import RoutingTraceLogger
from routing.semantic.stego_encoder import ByteLevelStegoEncoder
from routing.semantic.stego_decoder import ByteLevelStegoDecoder
from routing.action_spec import ACTION_SPECS
from scripts.experiment_context import load_experiment_context

Role = Literal["sender", "receiver"]

TRACE_PATH = Path("experiments/routing_trace.jsonl")
PENDING_STATE_PATH = Path("experiments/pending_secret_state.json")
PENDING_CHUNKS_PATH = Path("experiments/pending_chunks.json")
RECEIVER_BUFFER_PATH = Path("experiments/receiver_payload_buffer.json")

PAYLOAD_CHUNK_MARKER_PREFIX = "[EXPERIMENT_PAYLOAD_B64_CHUNK:"
PAYLOAD_CHUNK_MARKER_SUFFIX = "]"

GROUNDING_PATH = Path("experiments/grounding_index.json")

# ============================================================
# WRAPPERS FOR STEGO ENCODER/DECODER
# ============================================================

_encoder_instance = None
_decoder_instance = None


def get_encoder():
    """Get or create the encoder instance with quiet mode enabled."""
    global _encoder_instance
    if _encoder_instance is None:
        _encoder_instance = ByteLevelStegoEncoder(quiet=True)
    return _encoder_instance


def get_decoder():
    """Get or create the decoder instance."""
    global _decoder_instance
    if _decoder_instance is None:
        _decoder_instance = ByteLevelStegoDecoder()
    return _decoder_instance


def encode_secret_message(
        secret_message: str,
        epoch: int,
        artifact_class: str,
        artifact_context: Dict[str, Any]
) -> List[Dict[str, str]]:
    """
    Wrapper function for the routing system.
    Expected signature and return format.
    """
    # Build context for encoder
    context = {
        "repo_context": artifact_context.get("text", "authentication system")[:100],
        "file_context": f"{artifact_class}/epoch_{epoch}"
    }

    # Get encoder and encode the message
    encoder = get_encoder()
    chunks = encoder.encode(secret_message, context, positions_filename=None)

    # Format as expected by routing.normalize_plans()
    plans = []
    for i, chunk in enumerate(chunks):
        plans.append({
            "artifact_class": artifact_class,
            "stego_text": chunk
        })

    return plans


def decode_benign_message(
        benign_text: str,
        epoch: int,
        artifact_class: str,
        artifact_context: Dict[str, Any]
) -> str:
    """
    Wrapper function for the routing system.
    Expected signature and return format.
    """
    decoder = get_decoder()
    positions_file = "byte_level_test.json"

    try:
        decoded = decoder.decode_with_positions([benign_text], positions_file)
        return decoded
    except Exception as e:
        print(f"[WARN] Decoding failed with positions file, trying without: {e}")
        decoded = decoder.decode_without_positions(benign_text)
        return decoded


# ============================================================
# FIX: force epoch timing to come from experiment_manifest
# ============================================================

EXPERIMENT_MANIFEST_PATH = Path("experiments/experiment_manifest.json")


def _load_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _get_int(d: Dict[str, Any], key: str) -> Optional[int]:
    try:
        v = d.get(key)
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def apply_manifest_to_ctx(ctx) -> None:
    manifest_path = None
    try:
        mp = getattr(ctx, "experiment_manifest_path", None)
        if isinstance(mp, (str, Path)):
            manifest_path = Path(mp)
    except Exception:
        manifest_path = None

    if manifest_path is None:
        manifest_path = EXPERIMENT_MANIFEST_PATH

    m = _load_json_dict(manifest_path)
    if not m:
        return

    epoch = m.get("epoch")
    if not isinstance(epoch, dict):
        return

    origin_unix = _get_int(epoch, "origin_unix")
    duration_seconds = _get_int(epoch, "duration_seconds")
    end_unix = epoch.get("end_unix", None)

    current_time = int(time.time())

    if isinstance(origin_unix, int) and origin_unix > 0:
        try:
            if origin_unix < current_time:
                print(f"[INFO] Manifest epoch origin ({origin_unix}) is in the past. "
                      f"Starting at epoch {max(0, (current_time - origin_unix) // duration_seconds)}")
            ctx.epoch_origin_unix = origin_unix
        except Exception:
            pass

    if isinstance(duration_seconds, int) and duration_seconds > 0:
        try:
            ctx.epoch_duration_seconds = duration_seconds
        except Exception:
            pass

    try:
        if end_unix is None:
            ctx.epoch_end_unix = None
        else:
            ctx.epoch_end_unix = int(end_unix)
    except Exception:
        pass

    participants = m.get("participants")
    if isinstance(participants, dict):
        s = participants.get("sender")
        r = participants.get("receiver")
        if isinstance(s, dict):
            sid = s.get("id")
            if isinstance(sid, str) and sid.strip():
                try:
                    ctx.sender_id = sid.strip()
                except Exception:
                    pass
        if isinstance(r, dict):
            rid = r.get("id")
            if isinstance(rid, str) and rid.strip():
                try:
                    ctx.receiver_id = rid.strip()
                except Exception:
                    pass

    mid = m.get("experiment_id")
    if isinstance(mid, str) and mid.strip():
        try:
            if not getattr(ctx, "experiment_id", None):
                ctx.experiment_id = mid.strip()
        except Exception:
            pass


# ============================================================
# FIX: experiment-scoped state file paths
# ============================================================

def _pending_state_path_for_ctx(ctx) -> Path:
    try:
        exp = getattr(ctx, "experiment_id", None)
    except Exception:
        exp = None
    if isinstance(exp, str) and exp.strip():
        return Path("experiments") / f"pending_secret_state.{exp}.json"
    return PENDING_STATE_PATH


def _receiver_buffer_path_for_ctx(ctx) -> Path:
    try:
        exp = getattr(ctx, "experiment_id", None)
    except Exception:
        exp = None
    if isinstance(exp, str) and exp.strip():
        return Path("experiments") / f"receiver_payload_buffer.{exp}.json"
    return RECEIVER_BUFFER_PATH


def _snapshot_fp_path_for_ctx(ctx) -> Path:
    try:
        exp = getattr(ctx, "experiment_id", None)
    except Exception:
        exp = None
    if isinstance(exp, str) and exp.strip():
        return Path("experiments") / f"snapshot_fp.{exp}.txt"
    return Path("experiments") / "snapshot_fp.txt"


def snapshot_fingerprint(snapshot_path: str) -> str:
    p = Path(snapshot_path)
    st = p.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def ensure_snapshot_unchanged_or_reset(ctx) -> None:
    fp_path = _snapshot_fp_path_for_ctx(ctx)
    fp_path.parent.mkdir(parents=True, exist_ok=True)

    current_fp = snapshot_fingerprint(ctx.snapshot_path)

    if fp_path.exists():
        expected_fp = fp_path.read_text(encoding="utf-8").strip()
        if expected_fp != current_fp:
            hard_reset_due_to_snapshot_change(ctx)
    else:
        fp_path.write_text(current_fp, encoding="utf-8")


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
    current_time = int(time.time())
    if epoch_origin_unix > current_time:
        while True:
            remaining = epoch_origin_unix - int(time.time())
            if remaining <= 0:
                print("\n=== Epoch 0 has started ===\n")
                return
            print(f"Experiment begins in {remaining} seconds")
            time.sleep(1)
    else:
        print(
            f"\n=== Experiment started in the past. Current epoch: {max(0, (current_time - epoch_origin_unix) // 30)} ===\n")


def seconds_until_next_epoch(ctx) -> int:
    elapsed = int(time.time()) - ctx.epoch_origin_unix
    n = ctx.epoch_duration_seconds - (elapsed % ctx.epoch_duration_seconds)
    return max(1, int(n))


def current_epoch(ctx) -> int:
    return max(
        0,
        (int(time.time()) - ctx.epoch_origin_unix) // ctx.epoch_duration_seconds,
    )


# ============================================================
# Receiver epoch policy
# ============================================================

def receiver_decode_target_epoch(epoch_now: int) -> Optional[int]:
    if epoch_now <= 0:
        return None
    return epoch_now - 1


def print_receiver_epoch_policy(epoch_now: int) -> None:
    tgt = receiver_decode_target_epoch(epoch_now)
    if tgt is None:
        print("[INFO] Receiver policy: no decoding at epoch 0 (no prior sender epoch exists).")
    else:
        print(
            f"[INFO] Receiver policy: decode targets content generated during epoch {tgt} (exactly one epoch before).")


# ============================================================
# Final-epoch send suppression
# ============================================================

def is_final_epoch(ctx, epoch_now: int) -> bool:
    if ctx.epoch_end_unix is None:
        return False

    total_epochs = (ctx.epoch_end_unix - ctx.epoch_origin_unix) // ctx.epoch_duration_seconds
    final_epoch_index = max(0, total_epochs - 1)
    return epoch_now >= final_epoch_index


# ============================================================
# Trace-backed receiver routing
# ============================================================

def _safe_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


def _iter_trace_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = (line or "").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except Exception:
        return []
    return out


def get_sender_epoch_target_from_trace(
        *,
        trace_path: Path,
        experiment_id: str,
        target_epoch: int,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    last_sender_entry: Optional[Dict[str, Any]] = None
    did_publish = False

    for obj in _iter_trace_jsonl(trace_path):
        if obj.get("experiment_id") != experiment_id:
            continue
        if obj.get("role") != "sender":
            continue
        e = _safe_int(obj.get("epoch"))
        if e is None or e != target_epoch:
            continue

        if obj.get("semantic_label") == "explicit_testing_payload":
            did_publish = True

        last_sender_entry = obj

    return last_sender_entry, did_publish


def _coerce_identifier(x: Any) -> Optional[Tuple]:
    if isinstance(x, (list, tuple)):
        try:
            return tuple(x)
        except Exception:
            return None
    return None


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
    for attr in ("body", "message", "description", "text", "title"):
        val = getattr(artifact_obj, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


# ============================================================
# Grounding loader
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
    g = _load_json_if_exists(GROUNDING_PATH)
    if g:
        key = f"Repository:{owner}/{repo}"
        content = g.get(key)
        if isinstance(content, dict):
            files = content.get("files", {})
            if isinstance(files, dict):
                return {str(k): str(v) for k, v in files.items() if isinstance(k, str) and isinstance(v, str)}

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
# Action semantics
# ============================================================

def sender_can_publish_stegotext(artifact_class: str) -> bool:
    sender_steps = ACTION_SPECS.get(artifact_class, {}).get("sender", [])
    if not sender_steps:
        return False

    MUTATION_KEYWORDS = (
        "create", "edit", "modify", "add", "submit", "save", "update", "rewrite",
        "comment", "reply", "post", "write", "upload",
    )
    PROHIBITIONS = (
        "do not", "don't", "without creating", "without modifying", "do not attempt",
        "do not change", "do not create", "do not edit", "do not submit", "do not save",
        "do not mark", "do not apply", "treat this as a benign baseline", "observe",
        "review", "read-only", "read only",
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
# Persistent state for pending steganographic chunks
# ============================================================

@dataclass
class PendingChunks:
    chunks: List[str]
    next_index: int = 0
    original_secret: str = ""

    def remaining(self) -> int:
        return len(self.chunks) - self.next_index

    def current_chunk(self) -> Optional[str]:
        if self.next_index < len(self.chunks):
            return self.chunks[self.next_index]
        return None

    def advance(self) -> None:
        self.next_index += 1

    def is_complete(self) -> bool:
        return self.next_index >= len(self.chunks)


def _pending_chunks_path_for_ctx(ctx) -> Path:
    try:
        exp = getattr(ctx, "experiment_id", None)
    except Exception:
        exp = None
    if isinstance(exp, str) and exp.strip():
        return Path("experiments") / f"pending_chunks.{exp}.json"
    return PENDING_CHUNKS_PATH


def load_pending_chunks(ctx) -> Optional[PendingChunks]:
    path = _pending_chunks_path_for_ctx(ctx)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PendingChunks(**data)
    except Exception:
        return None


def save_pending_chunks(state: PendingChunks, ctx) -> None:
    path = _pending_chunks_path_for_ctx(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def clear_pending_chunks(ctx) -> None:
    path = _pending_chunks_path_for_ctx(ctx)
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


# ============================================================
# Legacy persistent state (unused but kept for compatibility)
# ============================================================

@dataclass
class PendingSecretState:
    payload_b64: str
    chunk_size: int
    next_chunk_index: int

    def total_chunks(self) -> int:
        if self.chunk_size <= 0:
            return 1
        return (len(self.payload_b64) + self.chunk_size - 1) // self.chunk_size

    def has_remaining(self) -> int:
        return self.next_chunk_index < self.total_chunks()

    def current_chunk(self) -> str:
        start = self.next_chunk_index * self.chunk_size
        end = min(len(self.payload_b64), start + self.chunk_size)
        return self.payload_b64[start:end]

    def advance(self) -> None:
        self.next_chunk_index += 1


def load_pending_state(ctx=None) -> Optional[PendingSecretState]:
    path = _pending_state_path_for_ctx(ctx) if ctx is not None else PENDING_STATE_PATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        payload_b64 = data["payload_b64"]
        chunk_size = int(data["chunk_size"])
        next_chunk_index = int(data["next_chunk_index"])
        if not isinstance(payload_b64, str) or not payload_b64:
            return None
        st = PendingSecretState(payload_b64=payload_b64, chunk_size=chunk_size, next_chunk_index=next_chunk_index)
        return st if st.has_remaining() else None
    except Exception:
        return None


def save_pending_state(state: PendingSecretState, ctx=None) -> None:
    path = _pending_state_path_for_ctx(ctx) if ctx is not None else PENDING_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
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


def clear_pending_state(ctx=None) -> None:
    path = _pending_state_path_for_ctx(ctx) if ctx is not None else PENDING_STATE_PATH
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def make_chunk_marker(chunk_b64: str, chunk_index: int, total_chunks: int) -> str:
    return f"{PAYLOAD_CHUNK_MARKER_PREFIX}{chunk_index + 1}/{total_chunks}:{chunk_b64}{PAYLOAD_CHUNK_MARKER_SUFFIX}"


def parse_chunk_marker(text: str) -> Optional[Tuple[int, int, str]]:
    if PAYLOAD_CHUNK_MARKER_PREFIX not in text:
        return None
    try:
        start = text.index(PAYLOAD_CHUNK_MARKER_PREFIX) + len(PAYLOAD_CHUNK_MARKER_PREFIX)
        end = text.index(PAYLOAD_CHUNK_MARKER_SUFFIX, start)
        inner = text[start:end].strip()
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
# Sender orchestration (modified)
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
    # Check if there are pending chunks from a previous secret
    pending = load_pending_chunks(ctx)

    if pending is None or pending.is_complete():
        # No pending chunks: ask for a new secret
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

        # Encode the secret into multiple chunks
        raw = encode_secret_message(
            secret_message=secret,
            epoch=epoch_now,
            artifact_class=artifact_class,
            artifact_context=artifact_context,
        )
        plans = normalize_plans(raw, artifact_class)
        chunks = [plan["stego_text"] for plan in plans]

        # Save pending state
        pending = PendingChunks(chunks=chunks, original_secret=secret)
        save_pending_chunks(pending, ctx)
        print(f"\n[INFO] Secret split into {len(chunks)} chunks. Will publish one per epoch.\n")

    # Publish the next chunk (if any)
    if pending and not pending.is_complete():
        chunk = pending.current_chunk()
        pending.advance()
        save_pending_chunks(pending, ctx)

        print("\n--- Stegotext ---")
        print(chunk)

        trace_logger.append(
            experiment_id=ctx.experiment_id,
            role=role,
            epoch=epoch_now,
            artifact_class=artifact_class,
            identifier=identifier,
            url=url,
            semantic_text=chunk,
            semantic_label="explicit_testing_payload",
            semantic_content_type="TokenBinning_ExplicitTesting",
        )

        print_required_actions(artifact_class, role)

        if pending.is_complete():
            print("\n[INFO] All chunks of the current secret have been sent.\n")
            clear_pending_chunks(ctx)
    else:
        # Should not happen, but handle gracefully
        print("\n[WARN] No pending chunks to publish.\n")


# ============================================================
# Receiver orchestration (unchanged)
# ============================================================

def load_receiver_buffer(ctx=None) -> Dict[str, Any]:
    path = _receiver_buffer_path_for_ctx(ctx) if ctx is not None else RECEIVER_BUFFER_PATH
    if not path.exists():
        return {"total": None, "chunks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"total": None, "chunks": {}}
    except Exception:
        return {"total": None, "chunks": {}}


def save_receiver_buffer(buf: Dict[str, Any], ctx=None) -> None:
    path = _receiver_buffer_path_for_ctx(ctx) if ctx is not None else RECEIVER_BUFFER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(buf, indent=2), encoding="utf-8")


def try_finalize_receiver_buffer(buf: Dict[str, Any], ctx=None) -> Optional[str]:
    return None


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("\n=== DeployStega Dead Drop Console ===\n")

    ctx = load_experiment_context()
    apply_manifest_to_ctx(ctx)
    ensure_snapshot_unchanged_or_reset(ctx)

    snapshot = read_snapshot(ctx.snapshot_path)

    current_time = int(time.time())
    if ctx.epoch_origin_unix > current_time:
        wait_until_epoch_start(ctx.epoch_origin_unix)
    else:
        print(f"[INFO] Experiment started in the past. Current epoch: {current_epoch(ctx)}")

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

            if role == "receiver":
                decode_epoch = receiver_decode_target_epoch(epoch_now)

                if decode_epoch is None:
                    print("\n=== DEAD DROP ===")
                    print(f"Epoch   : {epoch_now}")
                    print(f"Carrier : {artifact_class}")
                    print(f"URL     : {url}\n")
                    print_receiver_epoch_policy(epoch_now)
                    print("[INFO] Receiver session begins decoding at epoch 1; wait for the next epoch.")
                    continue

                sender_entry, did_publish = get_sender_epoch_target_from_trace(
                    trace_path=TRACE_PATH,
                    experiment_id=ctx.experiment_id,
                    target_epoch=decode_epoch,
                )

                if sender_entry is None:
                    print("\n=== DEAD DROP ===")
                    print(f"Epoch   : {epoch_now}")
                    print(f"Carrier : {artifact_class}")
                    print(f"URL     : {url}\n")
                    print_receiver_epoch_policy(epoch_now)
                    print(f"[INFO] No sender routing record found for epoch {decode_epoch}; receiver will wait.")
                    continue

                sender_artifact_class = sender_entry.get("artifact_class")
                sender_identifier = _coerce_identifier(sender_entry.get("identifier"))
                sender_url = sender_entry.get("url")

                if not isinstance(sender_artifact_class, str) or sender_identifier is None or not isinstance(sender_url,
                                                                                                             str):
                    print("\n=== DEAD DROP ===")
                    print(f"Epoch   : {epoch_now}")
                    print(f"Carrier : {artifact_class}")
                    print(f"URL     : {url}\n")
                    print_receiver_epoch_policy(epoch_now)
                    print(f"[WARN] Sender trace entry for epoch {decode_epoch} is malformed; receiver will wait.")
                    continue

                artifact_class = sender_artifact_class
                identifier = sender_identifier
                url = sender_url

                if not did_publish:
                    print("\n=== DEAD DROP ===")
                    print(f"Epoch   : {epoch_now}")
                    print(f"Carrier : {artifact_class}")
                    print(f"URL     : {url}\n")
                    print_receiver_epoch_policy(epoch_now)
                    print(
                        f"[INFO] Sender published no stegotext in epoch {decode_epoch}. Receiver will not prompt for input this epoch.")
                    continue

            artifact_obj = resolve_artifact_object(snapshot, artifact_class, identifier)

            owner, repo = identifier[:2]
            repo_files = load_repo_grounding(snapshot_path=ctx.snapshot_path, owner=owner, repo=repo)

            artifact_context = {
                "kind": artifact_obj.artifact_class.name,
                "artifact_class": artifact_obj.artifact_class.name,
                "text": extract_artifact_text(artifact_obj),
                "files": repo_files,
            }

            print("\n=== DEAD DROP ===")
            print(f"Epoch   : {epoch_now}")
            print(f"Carrier : {artifact_class}")
            print(f"URL     : {url}\n")

            if role == "sender":
                if is_final_epoch(ctx, epoch_now):
                    print(
                        "\n[INFO] Final epoch reached: sender is in observe-only mode (no stegotext may be published).")
                    sender_observe_only(
                        trace_logger=trace_logger,
                        ctx=ctx,
                        epoch_now=epoch_now,
                        role=role,
                        artifact_class=artifact_class,
                        identifier=identifier,
                        url=url,
                    )
                elif not sender_can_publish_stegotext(artifact_class):
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
                print_receiver_epoch_policy(epoch_now)
                decode_epoch = receiver_decode_target_epoch(epoch_now)

                while True:
                    if current_epoch(ctx) != epoch_now:
                        print("\n[INFO] Epoch advanced; waiting for next dead drop.")
                        break

                    try:
                        benign = input("Paste RECEIVED stegotext (empty to wait):\n> ").strip()
                    except EOFError:
                        print("\n[INFO] Receiver input ended.")
                        return

                    if not benign:
                        print("[INFO] Waiting for next epoch.")
                        break

                    if decode_epoch is None:
                        print(
                            "\n[INFO] No decode attempted at epoch 0. Wait for the next epoch and paste text created during epoch 0.")
                        trace_logger.append(
                            experiment_id=ctx.experiment_id,
                            role=role,
                            epoch=epoch_now,
                            artifact_class=artifact_class,
                            identifier=identifier,
                            url=url,
                            semantic_text=benign,
                            semantic_label="received_epoch0_no_decode",
                            semantic_content_type="TokenBinning_ExplicitTesting",
                        )
                        continue

                    decoded_secret = ""
                    try:
                        decoded_secret = decode_benign_message(
                            benign_text=benign,
                            epoch=decode_epoch,
                            artifact_class=artifact_class,
                            artifact_context=artifact_context,
                        )
                    except Exception as e:
                        print(f"[WARN] Decoding error: {e}")
                        decoded_secret = ""

                    print("\n--- DECODED SECRET ---")
                    if decoded_secret.strip():
                        print(decoded_secret)
                    else:
                        print("Decoding failed: text does not appear steganographic for the expected prior epoch.")

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


def hard_reset_due_to_snapshot_change(ctx) -> None:
    print("\n[FATAL] Repository snapshot has changed.")
    print("        This invalidates all sender/receiver state.")
    print("        Both sender and receiver MUST restart from epoch 0.\n")

    clear_pending_state(ctx)
    try:
        _receiver_buffer_path_for_ctx(ctx).unlink()
    except Exception:
        pass

    try:
        _snapshot_fp_path_for_ctx(ctx).unlink()
    except Exception:
        pass

    sys.exit(1)


if __name__ == "__main__":
    main()
