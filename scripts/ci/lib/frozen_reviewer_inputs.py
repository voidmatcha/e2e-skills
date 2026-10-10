# SPDX-License-Identifier: Apache-2.0
"""Stage frozen reviewer-holdout inputs from committed snapshots.

Historical holdout protocols pin files of the checkout they ran on: v15's
enforced schema enum is the output legend of the skill it evaluated, v17 pins
the Lean severity model's digest, and v18-v21 pin skill digests. The live
checkout moves on (2.0.0 added the #8c sub-ID, which extends the legend and
regenerates the model), so the historical CI checks validate those inputs from
snapshots committed under the owning benchmark directory instead of requiring
the live files to stay byte-identical to that past release.

The snapshots are deterministic `.tar.gz` archives of the pinned git trees
(sorted members, zero mtime/uid/gid, gzip mtime 0), so they are reproducible
from the recorded revision but need no git history: a depth-1 clone can run
every check. Each staged tree or file is verified against the digest the frozen
protocol or report records, and a mismatch fails closed. Nothing here invokes
git or any other external command.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile
from typing import Callable

ROOT = Path(__file__).resolve().parents[3]
V15_FULL_REPORT = ROOT / "benchmarks/reviewer-holdout-v15/reports/full-claude.json"
V15_FROZEN_DIR = ROOT / "benchmarks/reviewer-holdout-v15/frozen"
V17_PROTOCOL = ROOT / "scripts/evals/reviewer-validation-protocol-v17.json"
V17_FULL_REPORT = ROOT / "benchmarks/reviewer-holdout-v17/reports/full.json"
V17_FROZEN_DIR = ROOT / "benchmarks/reviewer-holdout-v17/frozen"
V20_PROTOCOL = ROOT / "scripts/evals/reviewer-validation-protocol-v20.json"
V20_FROZEN_DIR = ROOT / "benchmarks/reviewer-holdout-v20/frozen"
SKILL_SUBDIR = "skills/e2e-reviewer"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_member(member: tarfile.TarInfo, destination: Path) -> None:
    """Refuse anything but plain files and directories that stay inside destination."""
    name = member.name
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError(f"frozen snapshot member has an unsafe name: {name!r}")
    parts = Path(name).parts
    if any(part in ("..", "") for part in parts):
        raise ValueError(f"frozen snapshot member escapes its root: {name!r}")
    if not (member.isfile() or member.isdir()):
        raise ValueError(f"frozen snapshot member is not a regular file or directory: {name!r}")
    if member.islnk() or member.issym() or member.isdev() or member.isfifo():
        raise ValueError(f"frozen snapshot member is a link or special file: {name!r}")
    target = (destination / name).resolve()
    if destination.resolve() not in (target, *target.parents):
        raise ValueError(f"frozen snapshot member resolves outside the destination: {name!r}")


def extract_frozen_tarball(tarball: Path, destination: Path) -> Path:
    """Extract a committed snapshot after validating every member path and type.

    Python 3.12+ also applies tarfile's `data` filter; older interpreters that
    lack extraction filters fall back to the plain extraction, which is safe
    because every member was validated first (CONTRIBUTING promises 3.10+ for
    the CI mirror and 3.9 for bundled helpers).
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, mode="r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            _validate_member(member, destination)
        try:
            tar.extractall(destination, members=members, filter="data")
        except TypeError:  # extraction filters are unavailable before 3.12 backports
            tar.extractall(destination, members=members)
    for current, _dirs, files in os.walk(destination):
        for name in files:
            mode = os.lstat(Path(current) / name).st_mode
            if not stat.S_ISREG(mode):
                raise ValueError(f"frozen snapshot produced a non-regular file: {name}")
    return destination


def _frozen_skill_tarball(frozen_dir: Path, revision: str) -> Path:
    tarball = frozen_dir / f"skill-{revision[:7]}.tar.gz"
    if not tarball.is_file():
        raise FileNotFoundError(f"missing committed skill snapshot for {revision[:7]}: {tarball}")
    return tarball


def stage_frozen_skill(
    tarball: Path, expected_digest: str, digest_fn: Callable[[Path], str], destination: Path
) -> Path:
    """Extract a skill snapshot and verify it is the tree the protocol pinned."""
    extract_frozen_tarball(tarball, destination)
    skill_dir = Path(destination) / SKILL_SUBDIR
    if not (skill_dir / "SKILL.md").is_file():
        raise ValueError(f"{tarball}: snapshot does not contain {SKILL_SUBDIR}/SKILL.md")
    digest = digest_fn(skill_dir)
    if digest != expected_digest:
        raise ValueError(
            f"{tarball}: staged skill digest {digest} is not the pinned {expected_digest}"
        )
    return skill_dir


def stage_v15_skill(destination: Path, digest_fn: Callable[[Path], str]) -> Path:
    """Stage the skill v15 evaluated: the revision and digest its frozen report records."""
    report = _read_json(V15_FULL_REPORT)
    tarball = _frozen_skill_tarball(V15_FROZEN_DIR, report["git_revision"])
    return stage_frozen_skill(tarball, report["skill_sha256"], digest_fn, destination)


def stage_v20_skill(revision: str, destination: Path, digest_fn: Callable[[Path], str]) -> Path:
    """Stage v20's pinned `before` or `after` skill (shared by v18, v19 and v21)."""
    pin = _read_json(V20_PROTOCOL)["revision_comparison"]["revisions"][revision]
    tarball = _frozen_skill_tarball(V20_FROZEN_DIR, pin["source_commit"])
    return stage_frozen_skill(tarball, pin["skill_sha256"], digest_fn, destination)


def stage_v17_formal_model(destination: Path) -> Path:
    """Write the Lean model v17 appended to its prompts, as the v17 run saw it.

    The protocol records the model's path and sha256; the frozen full report
    records the git revision of the run, which names the committed snapshot.
    The staged copy must reproduce the pinned digest, so a drifted snapshot or
    protocol still fails closed.
    """
    pin = _read_json(V17_PROTOCOL)["formal_model"]
    revision = _read_json(V17_FULL_REPORT)["git_revision"]
    tarball = V17_FROZEN_DIR / f"lean-model-{revision[:7]}.tar.gz"
    if not tarball.is_file():
        raise FileNotFoundError(f"missing committed Lean model snapshot: {tarball}")
    destination = Path(destination)
    extract_frozen_tarball(tarball, destination)
    target = destination / pin["path"]
    if not target.is_file():
        raise ValueError(f"{tarball}: snapshot does not contain {pin['path']}")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != pin["sha256"]:
        raise ValueError(
            f"{pin['path']} in {tarball.name} has sha256 {digest}, not the v17 pinned {pin['sha256']}"
        )
    return target
