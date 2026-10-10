#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One-shot client for an independently operated reviewer-release-v1 witness.

The signer must run outside the model runner with its private key inaccessible
to this process. The client cannot establish that independence or online timing
by itself; the operator must attest and audit both before any release claim.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
from typing import Any


HERE = Path(__file__).resolve().parent
MAX_RECEIPT = 16 << 10
MAX_VERIFIER = 64 << 20
TIMEOUT = 10
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def load_evidence() -> Any:
    spec = importlib.util.spec_from_file_location("release_witness_call_evidence", HERE / "verify-reviewer-release-calls-v1.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release call evidence contract")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVIDENCE = load_evidence()


def load_assembler() -> Any:
    spec = importlib.util.spec_from_file_location("release_witness_assembler", HERE / "assemble-reviewer-release-call-v1.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load release execution event builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASSEMBLE = load_assembler()


class WitnessError(ValueError):
    pass


def exact_read(stream: socket.socket, length: int) -> bytes:
    result = bytearray()
    while len(result) < length:
        chunk = stream.recv(length - len(result))
        if not chunk:
            raise WitnessError("witness disconnected before a complete receipt")
        result.extend(chunk)
    return bytes(result)


def checked_verifier(path: Path, expected_sha256: str) -> str:
    if not path.is_absolute() or path.is_symlink() or not isinstance(expected_sha256, str) or SHA256.fullmatch(expected_sha256) is None:
        raise WitnessError("verifier path or pinned digest is invalid")
    # The verifier is executed by pathname after hashing. Its inode and every
    # ancestor therefore have to be outside the runner user's write control.
    # A same-owner read-only mode is insufficient: the owner could chmod it.
    current = Path(path.anchor)
    runner_uid = os.geteuid()
    try:
        for component in path.parts[1:]:
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid == runner_uid or info.st_mode & 0o022:
                raise WitnessError("verifier has a runner-writable or unsafe ancestor")
            current /= component
        path_info = path.lstat()
        if not stat.S_ISREG(path_info.st_mode) or path_info.st_uid == runner_uid or path_info.st_mode & 0o022:
            raise WitnessError("verifier must be an operator-owned non-writable real file")
    except OSError as exc:
        raise WitnessError("verifier path is unavailable") from exc
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise WitnessError("pinned verifier is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if ((info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
                or not stat.S_ISREG(info.st_mode) or info.st_size > MAX_VERIFIER
                or not os.access(path, os.X_OK)):
            raise WitnessError("verifier is not a bounded executable file")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1 << 20):
            digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise WitnessError("verifier differs from the independently pinned binary")
    finally:
        os.close(descriptor)
    return str(path)


def request_receipt(
    *, socket_path: Path, payload: bytes, receipt_path: Path,
    verifier_path: Path, verifier_sha256: str, public_key_base64: str,
) -> tuple[str, bytes]:
    """Reserve a receipt, request it once, then verify its exact signed payload.

    A failure leaves the reserved receipt path in place. The operator must mark
    the release run inconclusive rather than retrying the same event.
    """
    if not payload or len(payload) > MAX_RECEIPT:
        raise WitnessError("execution event payload is empty or oversized")
    try:
        event = EVIDENCE.strict_json(payload, "witness event")
    except EVIDENCE.CallEvidenceError as exc:
        raise WitnessError("execution event payload is invalid") from exc
    if not isinstance(event, dict) or event.get("protocol_id") != "reviewer-release-v1" or event.get("stage") not in {"begin", "end"}:
        raise WitnessError("execution event identity is invalid")
    if not isinstance(public_key_base64, str) or not public_key_base64:
        raise WitnessError("independently pinned public key is required")
    verifier = checked_verifier(verifier_path, verifier_sha256)
    if not socket_path.is_absolute() or socket_path.is_symlink():
        raise WitnessError("witness socket must be an absolute non-symlink path")
    try:
        socket_info = socket_path.lstat()
    except OSError as exc:
        raise WitnessError("witness socket is unavailable") from exc
    if not stat.S_ISSOCK(socket_info.st_mode):
        raise WitnessError("witness endpoint is not a Unix socket")
    if not receipt_path.is_absolute() or receipt_path.is_symlink():
        raise WitnessError("receipt path must be absolute and new")
    parent = receipt_path.parent
    if parent.is_symlink() or not parent.is_dir() or parent.resolve(strict=True) != parent or parent.stat().st_mode & 0o077:
        raise WitnessError("receipt parent must be a private real directory")
    try:
        descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as exc:
        raise WitnessError("receipt path is already reserved or unavailable") from exc
    try:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(TIMEOUT)
                connection.connect(str(socket_path))
                connection.sendall(struct.pack(">I", len(payload)) + payload)
                response_length = struct.unpack(">I", exact_read(connection, 4))[0]
                if response_length == 0 or response_length > MAX_RECEIPT:
                    raise WitnessError("witness receipt size is invalid")
                receipt = exact_read(connection, response_length)
        except OSError as exc:
            raise WitnessError("witness transport failed without a retry") from exc
        try:
            envelope = EVIDENCE.exact(EVIDENCE.strict_json(receipt, "witness receipt"), {"payload_base64", "signature_base64"}, "witness receipt")
            signed_payload = base64.b64decode(envelope["payload_base64"], validate=True)
        except (EVIDENCE.CallEvidenceError, ValueError, TypeError) as exc:
            raise WitnessError("witness receipt envelope is invalid") from exc
        if signed_payload != payload:
            raise WitnessError("witness signed different event bytes")
        if b"\n" in receipt or b"\r" in receipt:
            raise WitnessError("witness receipt is not one JSONL row")
        pending = memoryview(receipt)
        while pending:
            written = os.write(descriptor, pending)
            if written <= 0:
                raise WitnessError("receipt file accepted no bytes")
            pending = pending[written:]
        os.fsync(descriptor)
        written_identity = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    expected = hashlib.sha256(payload).hexdigest()
    try:
        completed = subprocess.run(
            [verifier, "--receipt", str(receipt_path), "--expected-receipt-payload-sha256", expected, "--public-key", public_key_base64],
            cwd=parent, env={}, capture_output=True, timeout=TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WitnessError("trusted receipt verifier did not complete") from exc
    if completed.returncode != 0:
        raise WitnessError("trusted verifier rejected the witness receipt")
    try:
        result = EVIDENCE.exact(EVIDENCE.strict_json(completed.stdout, "receipt verification"), {"verified", "phase", "payload_sha256"}, "receipt verification")
    except EVIDENCE.CallEvidenceError as exc:
        raise WitnessError("trusted verifier returned an invalid receipt result") from exc
    if result != {"verified": True, "phase": "receipt", "payload_sha256": expected}:
        raise WitnessError("trusted verifier did not confirm the exact event")
    try:
        after = receipt_path.lstat()
        if not stat.S_ISREG(after.st_mode) or (after.st_dev, after.st_ino, after.st_size) != (written_identity.st_dev, written_identity.st_ino, len(receipt)):
            raise WitnessError("verified receipt path changed")
        opened = os.open(receipt_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if os.fstat(opened).st_ino != written_identity.st_ino or os.read(opened, MAX_RECEIPT + 1) != receipt:
                raise WitnessError("verified receipt bytes changed")
        finally:
            os.close(opened)
    except OSError as exc:
        raise WitnessError("verified receipt became unavailable") from exc
    # Journal the exact response bytes checked above, not a later path read.
    # A receipt-file replacement after verification must not change the journal.
    return expected, receipt


def bound_artifact_refs(bundle_root: Path, paths: dict[str, Path], roles: set[str]) -> dict[str, dict[str, str]]:
    if set(paths) != roles:
        raise WitnessError("event artifact roles differ from the frozen boundary")
    references = {}
    for role in sorted(roles):
        path = paths[role]
        try:
            relative = path.relative_to(bundle_root).as_posix()
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except (OSError, ValueError) as exc:
            raise WitnessError("event artifact is outside the evidence bundle or unavailable") from exc
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > EVIDENCE.LIMITS[role]:
                raise WitnessError("event artifact is not a bounded regular file")
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1 << 20):
                digest.update(chunk)
        finally:
            os.close(descriptor)
        reference = {"path": relative, "sha256": digest.hexdigest()}
        try:
            EVIDENCE.read_bound(bundle_root, reference, role)
        except EVIDENCE.CallEvidenceError as exc:
            raise WitnessError("event artifact changed or has an unsafe path") from exc
        references[role] = reference
    return references


class WitnessSession:
    """One-process journal coordinator; independent service enforces durable no-retry."""

    def __init__(
        self, *, bundle_root: Path, case_ids: list[str], corpus_id: str,
        socket_path: Path, verifier_path: Path, verifier_sha256: str,
        public_key_base64: str,
    ) -> None:
        if not bundle_root.is_absolute() or bundle_root.is_symlink() or not bundle_root.is_dir() or bundle_root.resolve(strict=True) != bundle_root:
            raise WitnessError("evidence bundle must be an absolute real directory")
        if not isinstance(corpus_id, str) or not corpus_id:
            raise WitnessError("signed corpus identity is required")
        try:
            order = EVIDENCE.PLAN.ordered_call_keys(case_ids)
        except EVIDENCE.PLAN.ReleasePlanError as exc:
            raise WitnessError("signed corpus does not define the frozen call order") from exc
        self.bundle_root = bundle_root
        self.order = order
        self.corpus_id = corpus_id
        self.socket_path = socket_path
        self.verifier_path = verifier_path
        self.verifier_sha256 = verifier_sha256
        self.public_key_base64 = public_key_base64
        self.event_index = 0
        self.previous_sha256 = "0" * 64
        self.failed = False
        self.receipt_dir = bundle_root / "execution-receipts"
        try:
            self.receipt_dir.mkdir(mode=0o700)
        except OSError as exc:
            raise WitnessError("execution receipt directory already exists or is unavailable") from exc
        self.journal_path = bundle_root / "execution_journal.jsonl"
        try:
            self.journal_fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as exc:
            raise WitnessError("execution journal already exists or is unavailable") from exc

    def close(self) -> None:
        if self.journal_fd >= 0:
            os.close(self.journal_fd)
            self.journal_fd = -1

    def __enter__(self) -> "WitnessSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def complete(self) -> bool:
        return not self.failed and self.event_index == 2160

    def begin(self, key: tuple[str, str, int], paths: dict[str, Path]) -> None:
        self._emit("begin", key, paths, EVIDENCE.INPUT_ROLES)

    def end(self, key: tuple[str, str, int], paths: dict[str, Path]) -> None:
        self._emit("end", key, paths, EVIDENCE.OUTPUT_ROLES)

    def _emit(self, stage: str, key: tuple[str, str, int], paths: dict[str, Path], roles: set[str]) -> None:
        if self.failed or self.journal_fd < 0 or self.event_index >= 2160:
            raise WitnessError("witness session is closed, failed, or complete")
        expected_stage = "begin" if self.event_index % 2 == 0 else "end"
        if stage != expected_stage or key != self.order[self.event_index // 2]:
            self.failed = True
            raise WitnessError("witness event differs from the frozen schedule")
        try:
            refs = bound_artifact_refs(self.bundle_root, paths, roles)
            payload = ASSEMBLE.execution_event_payload(
                corpus_id=self.corpus_id, event_index=self.event_index,
                previous_sha256=self.previous_sha256, stage=stage,
                case_id=key[0], arm=key[1], repetition=key[2], artifacts=refs,
            )
            receipt_path = self.receipt_dir / f"event-{self.event_index:04d}.json"
            digest, receipt = request_receipt(
                socket_path=self.socket_path, payload=payload, receipt_path=receipt_path,
                verifier_path=self.verifier_path, verifier_sha256=self.verifier_sha256,
                public_key_base64=self.public_key_base64,
            )
            row = receipt + b"\n"
            while row:
                written = os.write(self.journal_fd, row)
                if written <= 0:
                    raise WitnessError("execution journal accepted no bytes")
                row = row[written:]
            os.fsync(self.journal_fd)
            self.previous_sha256 = digest
            self.event_index += 1
        except Exception:
            self.failed = True
            raise
