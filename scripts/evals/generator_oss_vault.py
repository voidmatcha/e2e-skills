"""External final-evaluation access and once-only ledger. Apache-2.0.

This is an accidental-reuse guard, not protection from the owning UID or a human
who removes the ledger. No function in this module reads evaluation task bytes.
"""
import hashlib
import json
import os
from pathlib import Path
import stat


def owner_only(path, tree=False):
    """Require owner-controlled, nonlinked directories and private contents."""
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError("private root must be an unlinked directory")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private root must be owned by the runner UID with mode 0700")
    if tree:
        for item in path.rglob("*"):
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("vault contains symlink")
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("vault contents must be owner-only")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError("vault contains a nonregular entry")
    return path


def disjoint(*roots):
    paths = [Path(root).resolve() for root in roots]
    for index, a in enumerate(paths):
        for b in paths[index + 1:]:
            if a == b or a.is_relative_to(b) or b.is_relative_to(a):
                raise ValueError("vault, results, ledger and DEV campaign roots must be separate")


def prepare_results(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return owner_only(path)


def spend(ledger_root, commitment, skill_digests, freeze_sha256):
    """Atomically spend a vault before its contents open, across campaign roots.

    A commitment filename is unique even across different skill versions. The
    composite key records which skill bytes consumed it; changing skills cannot
    buy a second look at an already opened vault.
    """
    root = Path(ledger_root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    owner_only(root)
    if len(commitment) != 64 or any(c not in "0123456789abcdef" for c in commitment):
        raise ValueError("vault commitment must be a sha256")
    if not skill_digests:
        raise ValueError("spent ledger requires frozen skill digests")
    identity = {"vault_commitment": commitment, "skill_digests": skill_digests}
    record = dict(identity, key=hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
                  freeze_sha256=freeze_sha256, status="SPENT_BEFORE_OPEN")
    try:
        fd = os.open(root / (commitment + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("vault commitment already spent in external ledger") from exc
    with os.fdopen(fd, "w") as handle:
        json.dump(record, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record
