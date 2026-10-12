#!/bin/bash -p
# Fetch the raw benchmark run artifacts that 2.0.1 moved out of this tree.
#
# Why this exists: the per-run artifacts under benchmarks/ (hundreds of files per
# run) made the checkout about 173 MB while the four skills are about 2 MB. The
# protocols, freeze records, results, and adjudications stay in the tree; the raw
# artifacts live in a pinned revision of a Hugging Face dataset and are listed in
# benchmarks/external-evidence.json. Nothing in CI needs them. Fetch them only to
# audit a number or rerun a comparison.
#
# Usage: scripts/dev/fetch-benchmark-evidence.sh [--dry-run] [--force]
#   --dry-run  print what would be downloaded and exit without touching anything
#   --force    replace a directory that already exists locally
# Needs: python3 and the `hf` CLI (pip install -U huggingface_hub). A private
# dataset also needs `hf auth login`.

set -euo pipefail
set -f

DRY_RUN=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    -h | --help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "$0")/../.." && pwd -P)"
manifest="$repo_root/benchmarks/external-evidence.json"
[ -f "$manifest" ] || { echo "missing $manifest" >&2; exit 1; }

# One line per field, so the shell never parses JSON itself.
# shellcheck disable=SC2312
read_manifest() {
  python3 -I - "$manifest" "$1" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
key = sys.argv[2]
if key == "directories":
    print("\n".join(m["directories"]))
else:
    print(m[key])
PY
}

dataset="$(read_manifest dataset)"
revision="$(read_manifest revision)"
prefix="$(read_manifest path_prefix_in_dataset)"
expected_files="$(read_manifest file_count)"

case "$revision" in
  *[!0-9a-f]* | "") echo "manifest revision is not a hex commit id: $revision" >&2; exit 1 ;;
esac
[ "${#revision}" -eq 40 ] || { echo "manifest revision must be 40 hex characters" >&2; exit 1; }

dirs=()
while IFS= read -r line; do
  case "$line" in
    "" | /* | *..*) echo "refusing unsafe manifest path: '$line'" >&2; exit 1 ;;
  esac
  dirs+=("$line")
done < <(read_manifest directories)

echo "dataset:  $dataset @ $revision"
echo "fetching: ${#dirs[@]} directories, $expected_files files into $repo_root/benchmarks/"
for d in "${dirs[@]}"; do
  if [ -e "$repo_root/benchmarks/$d" ] && [ "$FORCE" -ne 1 ]; then
    echo "  skip (exists, use --force): $d"
  else
    echo "  $d"
  fi
done
[ "$DRY_RUN" -eq 1 ] && exit 0

command -v hf >/dev/null 2>&1 || {
  echo "the hf CLI is required: pip install -U huggingface_hub" >&2
  exit 1
}

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

fetched=0
for d in "${dirs[@]}"; do
  target="$repo_root/benchmarks/$d"
  if [ -e "$target" ] && [ "$FORCE" -ne 1 ]; then
    continue
  fi
  # The Hub occasionally answers "taking longer than expected"; retry a few times.
  attempt=1
  until hf download "$dataset" --repo-type dataset --revision "$revision" \
    --include "${prefix}${d}/*" --local-dir "$stage" >/dev/null; do
    if [ "$attempt" -ge 3 ]; then
      echo "download failed after $attempt attempts: $d" >&2
      exit 1
    fi
    attempt=$((attempt + 1))
    echo "  retrying ($attempt/3): $d" >&2
    sleep $((attempt * 5))
  done
  [ -d "$stage/${prefix}${d}" ] || { echo "dataset has no ${prefix}${d} at $revision" >&2; exit 1; }
  rm -rf "$target"
  mkdir -p "$(dirname "$target")"
  mv "$stage/${prefix}${d}" "$target"
  fetched=$((fetched + 1))
done

echo "fetched $fetched directories. They are gitignored; do not commit them."
