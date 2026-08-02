#!/usr/bin/env python3
"""Create the local, exact-prompt token attestation required by v8."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-independent-review-v8.py"
EXPECTED_TIKTOKEN_VERSION = "0.11.0"
EXPECTED_ENCODING = "o200k_base"
EXPECTED_ENCODING_CONTRACT_SHA256 = "170a798bd4d0917feae9c78c8deb17f88e0b8d32676d7fc6f9116d8122928eb9"
EXPECTED_BPE_SOURCE_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
TOKENIZER_LOCK_PATH = ROOT / "scripts/evals/requirements-independent-review-v8-tokenizer.txt"
TOKENIZER_LOCK_SHA256 = "6fbd61316c7988c72ec6023ffa1a0ac38b36ebc0bb9bfd35b89cec3f20f1a536"
TOKENIZER_CACHE_PATH = ROOT / "scripts/evals/tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790"

sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from strict_json import StrictJsonError, loads_strict, require_exact_keys


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location("independent_review_v8_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import v8 runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_encoding():
    if sha256(TOKENIZER_LOCK_PATH.read_bytes()) != TOKENIZER_LOCK_SHA256:
        raise ValueError("pinned tokenizer dependency lock changed")
    if sha256(TOKENIZER_CACHE_PATH.read_bytes()) != EXPECTED_BPE_SOURCE_SHA256:
        raise ValueError("checked-in o200k_base source changed")
    os.environ["TIKTOKEN_CACHE_DIR"] = str(TOKENIZER_CACHE_PATH.parent)
    try:
        import tiktoken
    except ImportError as exc:
        raise ValueError("release token counting requires tiktoken exactly 0.11.0") from exc
    if getattr(tiktoken, "__version__", None) != EXPECTED_TIKTOKEN_VERSION:
        raise ValueError("release token counting requires tiktoken exactly 0.11.0")
    encoding = tiktoken.get_encoding(EXPECTED_ENCODING)
    if encoding.name != EXPECTED_ENCODING or encoding.n_vocab != 200019:
        raise ValueError("o200k_base encoding identity changed")
    ranks = sorted(encoding._mergeable_ranks.items(), key=lambda item: item[1])
    bpe_source = b"".join(
        base64.b64encode(token) + b" " + str(rank).encode("ascii") + b"\n"
        for token, rank in ranks
    )
    if sha256(bpe_source) != EXPECTED_BPE_SOURCE_SHA256:
        raise ValueError("o200k_base mergeable-rank contract changed")
    # The preregistered fingerprint names the verified package/version/encoding
    # contract above; it is recorded verbatim so validators need not import BPE code.
    return encoding


def create_only(path: Path, payload: bytes) -> None:
    parent = path.parent.expanduser().absolute()
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    destination_directory = os.open(parent.anchor, directory_flags)
    try:
        for component in parent.parts[1:]:
            next_directory = os.open(component, directory_flags, dir_fd=destination_directory)
            os.close(destination_directory); destination_directory = next_directory
    except Exception:
        os.close(destination_directory); raise
    # Cleanup scans the shared staging directory, so every writer using that
    # directory must hold the same lock even when destination filenames differ.
    lock_name = ".independent-review-v8-token-staging.state.lock"
    lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    lock_descriptor = os.open(lock_name, lock_flags, 0o600, dir_fd=destination_directory)
    opened_lock = os.fstat(lock_descriptor)
    named_lock = os.stat(lock_name, dir_fd=destination_directory, follow_symlinks=False)
    if not stat.S_ISREG(opened_lock.st_mode) or (opened_lock.st_dev, opened_lock.st_ino) != (named_lock.st_dev, named_lock.st_ino):
        os.close(lock_descriptor); os.close(destination_directory); raise ValueError("token output state lock identity changed")
    fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
    staging_name_root = ".independent-review-v8-token-staging"
    try: os.mkdir(staging_name_root, 0o700, dir_fd=destination_directory)
    except FileExistsError: pass
    try:
        stage_directory = os.open(staging_name_root, directory_flags, dir_fd=destination_directory)
        for child_name in os.listdir(stage_directory):
            metadata = os.stat(child_name, dir_fd=stage_directory, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode) or not re.fullmatch(r"token-attestation\.[0-9a-f]{32}\.staging", child_name):
                raise ValueError("unsafe token staging inventory")
            os.unlink(child_name, dir_fd=stage_directory)
    except Exception:
        try: os.close(stage_directory)
        except UnboundLocalError: pass
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN); os.close(lock_descriptor); os.close(destination_directory); raise
    staging_name = f"token-attestation.{uuid.uuid4().hex}.staging"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(staging_name, flags, 0o600, dir_fd=stage_directory)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0: raise OSError("token attestation write made no progress")
                view = view[written:]
            os.fsync(descriptor)
            created = os.fstat(descriptor)
            if not stat.S_ISREG(created.st_mode) or created.st_size != len(payload): raise OSError("token attestation staged identity changed")
        finally: os.close(descriptor)
        os.link(staging_name, path.name, src_dir_fd=stage_directory, dst_dir_fd=destination_directory, follow_symlinks=False)
        os.fsync(destination_directory)
    finally:
        try: os.unlink(staging_name, dir_fd=stage_directory)
        except FileNotFoundError: pass
        os.fsync(stage_directory); os.close(stage_directory)
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN); os.close(lock_descriptor); os.close(destination_directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = load_runner()
    protocol = runner.load_protocol(runner.PROTOCOL_PATH)
    packet, _ = runner.build_packet(ROOT, protocol)
    prompt = runner.build_rendered_prompt(packet, protocol)
    catalog, catalog_bytes = runner.load_pinned_model_catalog()
    matches = [entry for entry in catalog["models"] if entry["slug"] == args.model]
    if len(matches) != 1:
        parser.error("model catalog must contain the requested model exactly once")
    model = matches[0]
    encoding = load_encoding()
    token_ids = encoding.encode(prompt, disallowed_special=())
    effective = model["context_window_tokens"] * model["effective_context_window_percent"] // 100
    attestation = {
        "schema_version": 1,
        "attestation_id": "independent-product-review-v8-token-count-v1",
        "protocol_sha256": runner.V8_PROTOCOL_HASH,
        "prompt_sha256": sha256(prompt.encode("utf-8")),
        "prompt_utf8_bytes": len(prompt.encode("utf-8")),
        "prompt_input_tokens": len(token_ids),
        "token_ids_sha256": sha256(json.dumps(token_ids, separators=(",", ":")).encode("utf-8")),
        "tokenizer": {
            "package": "tiktoken",
            "version": EXPECTED_TIKTOKEN_VERSION,
            "encoding": EXPECTED_ENCODING,
            "name": encoding.name,
            "n_vocab": encoding.n_vocab,
            "encoding_contract_sha256": EXPECTED_ENCODING_CONTRACT_SHA256,
            "bpe_source_sha256": EXPECTED_BPE_SOURCE_SHA256,
        },
        "counter_sha256": sha256(Path(__file__).resolve().read_bytes()),
        "model_slug": args.model,
        "model_catalog_sha256": sha256(catalog_bytes),
        "context_window_tokens": model["context_window_tokens"],
        "max_context_window_tokens": model["max_context_window_tokens"],
        "effective_context_window_percent": model["effective_context_window_percent"],
        "effective_context_tokens": effective,
        "reserved_tokens": effective - len(token_ids),
        "provenance": {
            "kind": "local-token-count",
            "remote_model_attestation": False,
            "statement": "Local tokenizer and caller-provided catalog evidence only; not remote model attestation.",
        },
    }
    caps = protocol["packet"]
    if (attestation["prompt_utf8_bytes"] > caps["rendered_prompt_utf8_bytes_max"]
            or attestation["prompt_input_tokens"] > caps["prompt_input_tokens_max"]
            or attestation["context_window_tokens"] < caps["context_window_tokens_min"]
            or attestation["effective_context_window_percent"] < caps["effective_context_window_percent_min"]
            or effective < caps["effective_context_tokens_min"]
            or attestation["reserved_tokens"] < caps["reserved_tokens_min"]):
        parser.error("exact prompt/model catalog fails a preregistered v8 cap")
    payload = json.dumps(attestation, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        create_only(args.output.expanduser().absolute(), payload)
    except FileExistsError:
        parser.error("token attestation output already exists")
    print(json.dumps(attestation, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, UnicodeError) as exc:
        raise SystemExit(f"error: {exc}")
