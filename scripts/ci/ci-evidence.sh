#!/bin/bash -p
# Replay the pinned source and evidence archives independently of local Git history.

builtin set -uo pipefail

# Establish the command trust boundary before resolving the repository or
# running any external command. Non-interactive Bash imports exported
# functions before this file starts, so remove them before command dispatch.
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
builtin export PATH
builtin unset CDPATH ENV BASH_ENV GLOBIGNORE
while IFS= builtin read -r imported_function; do
  builtin unset -f "$imported_function"
done < <(builtin compgen -A function)
builtin shopt -u expand_aliases
builtin unalias -a 2>/dev/null || true

# Historical verification is an explicit replay at the snapshot source commit,
# not a validation of today's product. A verified HF restore is mandatory.
[ "$#" -eq 1 ] && [[ "$1" = /* ]] || {
  echo "usage: /bin/bash -p scripts/ci/ci-evidence.sh /absolute/verified-restore-root" >&2
  exit 2
}
EVIDENCE_ROOT="$1"
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
REPO_ROOT="$(builtin cd -- "$SCRIPT_DIR/../.." && builtin pwd -P)" || exit 2
source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh" || exit 2
run_python "$REPO_ROOT/scripts/dev/fetch-benchmark-evidence.py" --verify-only --output "$EVIDENCE_ROOT" || exit 1
run_python - "$REPO_ROOT" "$EVIDENCE_ROOT" <<'PYTHON'
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo, evidence = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("evidence_restore", repo / "scripts/dev/fetch-benchmark-evidence.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)
manifest = fetch.load_manifest(repo / "benchmarks/external-evidence.json")
commit = manifest["source_commit"]
git_env = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00"}
git = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
       "-c", "user.name=Evidence replay", "-c", "user.email=evidence-replay@example.invalid"]
# The frozen runner refuses report destinations under swept OS temp roots.
# Keep each disposable source workspace in the durable user cache so its
# unchanged ROOT/results contracts have the same semantics as a real checkout.
cache = Path.home() / ".cache/e2e-skills/historical-ci"
cache.mkdir(mode=0o700, parents=True, exist_ok=True)
cache = cache.resolve(strict=True)
with tempfile.TemporaryDirectory(prefix="e2e-evidence-replay-", dir=cache) as raw:
    replay = Path(raw).resolve() / "source"
    # Restore authenticated bytes, not a commit that a shallow or squashed
    # product clone may never have. The helper authenticates and safely extracts
    # the separately pinned source archive before any frozen code is executed.
    fetch.restore_source(manifest, replay)
    shutil.copytree(evidence / "benchmarks", replay / "benchmarks")
    # Frozen CI needs a tracked source view. This deterministic local repository
    # supplies that context; its synthetic HEAD is not the original source SHA.
    for arguments in (("init", "--quiet"), ("add", "--force", "--all", "--", "."),
                      ("commit", "--quiet", "--no-gpg-sign", "-m", "Authenticated evidence replay source")):
        subprocess.run([*git, "-C", str(replay), *arguments], env=git_env, check=True)
    replay_head = subprocess.check_output([*git, "-C", str(replay), "rev-parse", "HEAD"],
                                          env=git_env, text=True).strip()
    print(f"ci-evidence: replaying authenticated source {commit}; synthetic context HEAD {replay_head}", flush=True)
    print("ci-evidence: current product and original Git commit identity are not evaluated", flush=True)
    result = subprocess.run(["/bin/bash", "-p", "scripts/ci/ci-local.sh"], cwd=replay)
    raise SystemExit(result.returncode)
PYTHON
