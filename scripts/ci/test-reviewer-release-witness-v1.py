#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline wire and fail-closed checks for the release witness client."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[2]
WITNESS_PATH = ROOT / "scripts/evals/reviewer-release-witness-v1.py"
SPEC = importlib.util.spec_from_file_location("reviewer_release_witness_v1", WITNESS_PATH)
assert SPEC and SPEC.loader
WITNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WITNESS)


def rejects(fn) -> None:
    try:
        fn()
    except WITNESS.WitnessError:
        return
    raise AssertionError("expected a fail-closed witness error")


def serve_once(path: Path, reply: bytes | None, seen: list[bytes]) -> threading.Thread:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)

    def run() -> None:
        try:
            connection, _ = listener.accept()
            with connection:
                length = struct.unpack(">I", WITNESS.exact_read(connection, 4))[0]
                seen.append(WITNESS.exact_read(connection, length))
                if reply is not None:
                    connection.sendall(struct.pack(">I", len(reply)) + reply)
        finally:
            listener.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="rw-", dir="/tmp") as temporary:
        root = Path(temporary).resolve()
        receipts = root / "receipts"
        receipts.mkdir(mode=0o700)
        payload = json.dumps({
            "schema_version": 1, "protocol_id": "reviewer-release-v1",
            "corpus_id": "sealed-corpus", "event_index": 0,
            "previous_sha256": "0" * 64, "stage": "begin",
            "case_id": "case-001", "arm": "no-skill", "repetition": 1,
            "artifacts": {role: {"path": f"calls/001/inputs/{role}", "sha256": hashlib.sha256(role.encode()).hexdigest()}
                          for role in WITNESS.EVIDENCE.INPUT_ROLES},
        }, sort_keys=True, separators=(",", ":")).encode()
        envelope = json.dumps({
            "payload_base64": base64.b64encode(payload).decode(),
            "signature_base64": base64.b64encode(b"s" * 64).decode(),
        }).encode()
        verifier = Path("/usr/bin/true")
        assert verifier.is_file()
        verifier_hash = hashlib.sha256(verifier.read_bytes()).hexdigest()
        assert WITNESS.checked_verifier(verifier, verifier_hash) == str(verifier)
        local_verifier = root / "local-verifier"
        local_verifier.write_bytes(verifier.read_bytes())
        local_verifier.chmod(0o755)
        rejects(lambda: WITNESS.checked_verifier(local_verifier, verifier_hash))
        digest = hashlib.sha256(payload).hexdigest()
        original_run = WITNESS.subprocess.run
        invoked = []

        def fake_verifier(command, **kwargs):
            invoked.append(command)
            assert kwargs["env"] == {}
            assert Path(command[2]).read_bytes() == envelope
            return subprocess.CompletedProcess(command, 0, json.dumps({
                "verified": True, "phase": "receipt", "payload_sha256": digest,
            }).encode(), b"")

        WITNESS.subprocess.run = fake_verifier
        try:
            socket_path = root / "witness.sock"
            seen = []
            thread = serve_once(socket_path, envelope, seen)
            receipt = receipts / "begin.json"
            common = dict(socket_path=socket_path, payload=payload, receipt_path=receipt,
                          verifier_path=verifier, verifier_sha256=verifier_hash,
                          public_key_base64=base64.b64encode(b"k" * 32).decode())
            assert WITNESS.request_receipt(**common) == (digest, envelope)
            thread.join(timeout=2)
            assert not thread.is_alive() and seen == [payload]
            assert receipt.read_bytes() == envelope and len(invoked) == 1
            rejects(lambda: WITNESS.request_receipt(**common))
            assert len(invoked) == 1 and seen == [payload]

            wrong_socket = root / "wrong.sock"
            wrong = json.dumps({**json.loads(envelope), "payload_base64": base64.b64encode(b"different").decode()}).encode()
            seen = []
            thread = serve_once(wrong_socket, wrong, seen)
            wrong_path = receipts / "wrong.json"
            rejects(lambda: WITNESS.request_receipt(**{**common, "socket_path": wrong_socket, "receipt_path": wrong_path}))
            thread.join(timeout=2)
            assert seen == [payload] and wrong_path.exists() and wrong_path.stat().st_size == 0
            assert len(invoked) == 1

            disconnect_socket = root / "disconnect.sock"
            seen = []
            thread = serve_once(disconnect_socket, None, seen)
            disconnected = receipts / "disconnected.json"
            rejects(lambda: WITNESS.request_receipt(**{**common, "socket_path": disconnect_socket, "receipt_path": disconnected}))
            thread.join(timeout=2)
            assert seen == [payload] and disconnected.exists() and disconnected.stat().st_size == 0

            rejected_socket = root / "rejected.sock"
            seen = []
            thread = serve_once(rejected_socket, envelope, seen)
            rejected = receipts / "rejected.json"
            WITNESS.subprocess.run = lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, b"", b"rejected")
            rejects(lambda: WITNESS.request_receipt(**{**common, "socket_path": rejected_socket, "receipt_path": rejected}))
            thread.join(timeout=2)
            assert seen == [payload] and rejected.read_bytes() == envelope
            WITNESS.subprocess.run = fake_verifier

            mutation_socket = root / "mutation.sock"
            seen = []
            thread = serve_once(mutation_socket, envelope, seen)
            mutated = receipts / "mutated.json"

            def fake_verifier_mutates(command, **_kwargs):
                Path(command[2]).write_bytes(b"changed-after-verification")
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "verified": True, "phase": "receipt", "payload_sha256": digest,
                }).encode(), b"")

            WITNESS.subprocess.run = fake_verifier_mutates
            rejects(lambda: WITNESS.request_receipt(**{**common, "socket_path": mutation_socket, "receipt_path": mutated}))
            thread.join(timeout=2)
            assert seen == [payload] and mutated.read_bytes() == b"changed-after-verification"
            WITNESS.subprocess.run = fake_verifier

            bad_verifier = receipts / "bad-verifier.json"
            rejects(lambda: WITNESS.request_receipt(**{**common, "receipt_path": bad_verifier, "verifier_sha256": "0" * 64}))
            assert not bad_verifier.exists()

            linked = root / "linked.sock"
            linked.symlink_to(socket_path)
            rejects(lambda: WITNESS.request_receipt(**{**common, "socket_path": linked, "receipt_path": receipts / "linked.json"}))
        finally:
            WITNESS.subprocess.run = original_run
    with tempfile.TemporaryDirectory(prefix="rws-", dir="/tmp") as temporary:
        root = Path(temporary).resolve()
        bundle = root / "bundle"
        bundle.mkdir()
        cases = [f"case-{number:03d}" for number in range(120)]
        original_request = WITNESS.request_receipt
        seen_events = []

        def fake_request(**kwargs):
            event = json.loads(kwargs["payload"])
            seen_events.append(event)
            raw = json.dumps({
                "payload_base64": base64.b64encode(kwargs["payload"]).decode(),
                "signature_base64": base64.b64encode(b"s" * 64).decode(),
            }, separators=(",", ":")).encode()
            # The journal must use returned, verified bytes rather than a
            # mutable receipt path reopened after acknowledgement.
            kwargs["receipt_path"].write_bytes(b"replaced-after-ack")
            return hashlib.sha256(kwargs["payload"]).hexdigest(), raw

        WITNESS.request_receipt = fake_request
        try:
            settings = dict(bundle_root=bundle, case_ids=cases, corpus_id="sealed-corpus",
                            socket_path=root / "unused.sock", verifier_path=Path(sys.executable).resolve(),
                            verifier_sha256="0" * 64, public_key_base64="unused")
            with WITNESS.WitnessSession(**settings) as session:
                key = session.order[0]

                def artifacts(roles, stage):
                    paths = {}
                    folder = bundle / "calls" / "0000" / stage
                    folder.mkdir(parents=True)
                    for role in roles:
                        path = folder / role
                        path.write_bytes(role.encode())
                        paths[role] = path
                    return paths

                session.begin(key, artifacts(WITNESS.EVIDENCE.INPUT_ROLES, "inputs"))
                assert session.event_index == 1 and not session.complete
                session.end(key, artifacts(WITNESS.EVIDENCE.OUTPUT_ROLES, "outputs"))
                assert session.event_index == 2 and not session.complete
                assert seen_events[0]["previous_sha256"] == "0" * 64
                assert seen_events[1]["previous_sha256"] == hashlib.sha256(
                    json.dumps(seen_events[0], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                journal = (bundle / "execution_journal.jsonl").read_bytes().splitlines()
                assert len(journal) == 2
                assert all(json.loads(row)["payload_base64"] for row in journal)
                assert b"replaced-after-ack" not in b"\n".join(journal)
                rejects(lambda: session.begin(key, artifacts(WITNESS.EVIDENCE.INPUT_ROLES, "wrong-inputs")))
                assert session.failed and session.event_index == 2
                rejects(lambda: session.begin(session.order[1], artifacts(WITNESS.EVIDENCE.INPUT_ROLES, "next-inputs")))
            rejects(lambda: WITNESS.WitnessSession(**settings))
            failed_bundle = root / "failed-bundle"
            failed_bundle.mkdir()
            failing_settings = {**settings, "bundle_root": failed_bundle}

            def refuse_receipt(**_kwargs):
                raise WITNESS.WitnessError("independent witness refused begin")

            WITNESS.request_receipt = refuse_receipt
            with WITNESS.WitnessSession(**failing_settings) as refused:
                refusal_key = refused.order[0]
                folder = failed_bundle / "call" / "inputs"
                folder.mkdir(parents=True)
                input_paths = {}
                for role in WITNESS.EVIDENCE.INPUT_ROLES:
                    input_paths[role] = folder / role
                    input_paths[role].write_bytes(role.encode())
                rejects(lambda: refused.begin(refusal_key, input_paths))
                assert refused.failed and refused.event_index == 0
                rejects(lambda: refused.begin(refusal_key, input_paths))
                assert (failed_bundle / "execution_journal.jsonl").read_bytes() == b""
            rejects(lambda: WITNESS.WitnessSession(**failing_settings))
        finally:
            WITNESS.request_receipt = original_request
    print("reviewer release witness v1: PASS")


if __name__ == "__main__":
    main()
