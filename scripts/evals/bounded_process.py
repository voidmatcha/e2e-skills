#!/usr/bin/env python3
"""Bounded subprocess stdout capture for executable evaluation runners."""

from __future__ import annotations

from dataclasses import dataclass
import os
import selectors
import subprocess
import time
from typing import Callable


READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class CaptureResult:
    return_code: int
    output: str
    timed_out: bool
    overflowed: bool
    cleanup_failures: tuple[str, ...]


def _decode(output: bytearray) -> str:
    return bytes(output).decode("utf-8", errors="replace")


def _drain_available(stream: object) -> None:
    """Discard already-buffered output without waiting for a writer."""
    fileno = stream.fileno()
    try:
        os.set_blocking(fileno, False)
    except (AttributeError, OSError):
        return
    while True:
        try:
            chunk = os.read(fileno, READ_CHUNK_BYTES)
        except BlockingIOError:
            return
        except OSError:
            return
        if not chunk:
            return


def capture_process(
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
    output_limit_bytes: int,
    stop_process: Callable[[subprocess.Popen[bytes]], list[str]],
) -> CaptureResult:
    """Capture at most ``output_limit_bytes`` and fail closed on overflow."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if output_limit_bytes < 1:
        raise ValueError("output_limit_bytes must be positive")
    if process.stdout is None:
        raise ValueError("process stdout must be captured")

    output = bytearray()
    overflowed = False
    timed_out = False
    cleanup_failures: list[str] = []
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            events = selector.select(timeout=min(max(remaining, 0), 0.1))
            if not events:
                continue
            read_limit = min(
                READ_CHUNK_BYTES,
                output_limit_bytes + 1 - len(output),
            )
            chunk = os.read(process.stdout.fileno(), read_limit)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > output_limit_bytes:
                del output[output_limit_bytes:]
                overflowed = True
                break
    finally:
        selector.close()

    if timed_out or overflowed:
        cleanup_failures.extend(stop_process(process))
        _drain_available(process.stdout)
    elif process.poll() is None:
        wait_timeout = max(deadline - time.monotonic(), 0)
        try:
            process.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            cleanup_failures.extend(stop_process(process))
            _drain_available(process.stdout)
    try:
        process.stdout.close()
    except OSError:
        pass

    return CaptureResult(
        return_code=process.returncode if process.returncode is not None else 125,
        output=_decode(output),
        timed_out=timed_out,
        overflowed=overflowed,
        cleanup_failures=tuple(cleanup_failures),
    )
