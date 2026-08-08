# SPDX-License-Identifier: Apache-2.0
"""Run the mutating parity smoke suite only inside a disposable source copy."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


IGNORED_NAMES = frozenset(
    {
        ".DS_Store",
        ".git",
        ".omx",
        ".serena",
        "__pycache__",
        "e2e-reviewer-workspace",
        "node_modules",
        "results",
        "testbed",
    }
)
DISPOSABLE_PREFIX = "e2e-parity-disposable-"
SENTINEL = ".e2e-parity-disposable-root"


@dataclass(frozen=True)
class DisposableParityResult:
    returncode: int
    digest_before: str
    digest_after: str
    cleaned: bool


def _ignored(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in IGNORED_NAMES or name.endswith(".parity-backup")
    }


def source_digest(root: Path) -> str:
    """Hash copied-source inputs without following symlinks."""
    digest = hashlib.sha256()
    root = root.resolve()
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_NAMES)
        base = Path(directory)
        for name in sorted(filenames):
            if name in IGNORED_NAMES or name.endswith(".parity-backup"):
                continue
            path = base / name
            relative = path.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(os.readlink(path).encode("utf-8"))
            else:
                digest.update(b"file\0")
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
            digest.update(b"\0")
    return digest.hexdigest()


def _initialize_disposable_git_index(copied_root: Path) -> None:
    """Create local tracked-file metadata without copying the source .git dir."""
    trusted_path = os.pathsep.join(
        ("/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin")
    )
    git = shutil.which("git", path=trusted_path)
    if git is None:
        raise RuntimeError("trusted git executable is unavailable")
    environment = os.environ.copy()
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    commands = (
        [git, "-c", "core.hooksPath=/dev/null", "init", "--quiet"],
        [
            git,
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.autocrlf=false",
            "add",
            "--all",
        ],
    )
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=copied_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(
                f"disposable git index setup failed ({command[-1]}): {detail}"
            )


def run_disposable_copy(
    source_root: Path,
    *,
    inner_script: Path = Path("scripts/ci/test-parity.sh"),
    temp_parent: Path | None = None,
    shard: tuple[int, int] | None = None,
) -> DisposableParityResult:
    """Copy source, run the inner mutation suite, prove source unchanged, clean.

    `shard` is an (index, count) pair handed to the inner script so several copies can split the
    case list between them. Each worker gets its own copy, so mutate/restore cycles never meet.
    """
    source_root = source_root.resolve(strict=True)
    before = source_digest(source_root)
    parent = (temp_parent or Path(tempfile.gettempdir())).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    disposable_parent = Path(
        tempfile.mkdtemp(prefix=DISPOSABLE_PREFIX, dir=str(parent))
    ).resolve()
    copied_root = disposable_parent / "repo"
    cleaned = False
    inner_returncode = 1
    after = ""
    try:
        shutil.copytree(
            source_root,
            copied_root,
            symlinks=True,
            ignore=_ignored,
        )
        copied_root = copied_root.resolve(strict=True)
        (copied_root / SENTINEL).write_text(
            f"source={source_root}\n", encoding="utf-8"
        )
        _initialize_disposable_git_index(copied_root)
        command = copied_root / inner_script
        if not command.is_file():
            raise RuntimeError(f"inner parity script is missing: {inner_script}")
        environment = os.environ.copy()
        environment["E2E_PARITY_DISPOSABLE_ROOT"] = str(copied_root)
        if shard is not None:
            shard_index, shard_count = shard
            environment["E2E_PARITY_SHARD_INDEX"] = str(shard_index)
            environment["E2E_PARITY_SHARD_COUNT"] = str(shard_count)
        completed = subprocess.run(
            ["/bin/bash", str(command)],
            cwd=copied_root,
            env=environment,
            check=False,
        )
        inner_returncode = completed.returncode
        after = source_digest(source_root)
    finally:
        if (
            disposable_parent.parent != parent
            or not disposable_parent.name.startswith(DISPOSABLE_PREFIX)
        ):
            raise RuntimeError(
                f"refusing unsafe disposable cleanup target: {disposable_parent}"
            )
        shutil.rmtree(disposable_parent)
        cleaned = not disposable_parent.exists()
        if not cleaned:
            raise RuntimeError(
                f"disposable parity cleanup did not remove {disposable_parent}"
            )

    if before != after:
        return DisposableParityResult(74, before, after, cleaned)
    return DisposableParityResult(inner_returncode, before, after, cleaned)


def run_sharded(source_root: Path, workers: int) -> int:
    """Run the suite across `workers` disposable copies concurrently.

    Every case still executes exactly once: the inner script walks the whole case list and asserts
    only the indices congruent to its shard, so the union over shards is the unsharded suite. The
    source digest is proven once around the whole fan-out, so a worker that wrote outside its own
    copy still trips it.
    """
    source_root = source_root.resolve(strict=True)
    before = source_digest(source_root)
    codes: list[int] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(run_disposable_copy, source_root, shard=(index, workers))
            for index in range(workers)
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            codes.append(result.returncode)
            if not result.cleaned:
                print("disposable parity cleanup was not proven", file=sys.stderr)
                codes.append(75)
    after = source_digest(source_root)
    if before != after:
        print(
            f"disposable parity source digest changed: {before} -> {after}",
            file=sys.stderr,
        )
        return 74
    failed = [code for code in codes if code != 0]
    if failed:
        return failed[0]
    print(
        "disposable parity proof: source digest unchanged "
        f"{after}; {workers} temporary copies removed"
    )
    return 0


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(
            "usage: run_disposable_parity.py <source-root> [workers]", file=sys.stderr
        )
        return 2
    if len(sys.argv) == 3:
        try:
            workers = int(sys.argv[2])
        except ValueError:
            print("workers must be a positive integer", file=sys.stderr)
            return 2
        if workers < 1:
            print("workers must be a positive integer", file=sys.stderr)
            return 2
        if workers > 1:
            try:
                return run_sharded(Path(sys.argv[1]), workers)
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                print(f"disposable parity runner failed closed: {exc}", file=sys.stderr)
                return 75
    try:
        result = run_disposable_copy(Path(sys.argv[1]))
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"disposable parity runner failed closed: {exc}", file=sys.stderr)
        return 75
    if result.digest_before != result.digest_after:
        print(
            "disposable parity source digest changed: "
            f"{result.digest_before} -> {result.digest_after}",
            file=sys.stderr,
        )
        return 74
    if not result.cleaned:
        print("disposable parity cleanup was not proven", file=sys.stderr)
        return 75
    print(
        "disposable parity proof: source digest unchanged "
        f"{result.digest_after}; temporary copy removed"
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
