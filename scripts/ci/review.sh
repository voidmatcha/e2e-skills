#!/bin/bash -p
# Automated convention review for e2e-skills.

builtin set -uo pipefail

# Pin command lookup and discard functions imported from the caller before
# repository resolution or any external command can be influenced by them.
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
builtin export PATH
builtin unset CDPATH ENV BASH_ENV GLOBIGNORE
while IFS= builtin read -r imported_function; do
  builtin unset -f "$imported_function"
done < <(builtin compgen -A function)
builtin shopt -u expand_aliases
builtin unalias -a 2>/dev/null || true

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
REPO_ROOT="$(builtin cd -- "$SCRIPT_DIR/../.." && builtin pwd -P)" || {
  echo "review.sh: cannot resolve repo root" >&2
  exit 1
}
builtin cd -- "$REPO_ROOT" || {
  echo "review.sh: cannot cd to $REPO_ROOT" >&2
  exit 1
}
source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh" || exit 2

ERRORS=0
WARNINGS=0
PASSED=0

err() { echo "  [FAIL] $*" >&2; ERRORS=$((ERRORS + 1)); }
warn() { echo "  [WARN] $*" >&2; WARNINGS=$((WARNINGS + 1)); }
ok() { [ "$QUIET" = "1" ] || echo "  [OK] $*"; PASSED=$((PASSED + 1)); }
section() { [ "$QUIET" = "1" ] || { echo ""; echo "-- $* --"; }; }
repo_files() { /usr/bin/git ls-files -co --exclude-standard -- "$@" 2>/dev/null; }

section "Eval metadata"
eval_log=$(mktemp "${TMPDIR:-/tmp}/e2e-skills-evals.XXXXXX")
if /bin/bash ./scripts/validate-evals.sh >"$eval_log" 2>&1; then
  total=$(grep -oE 'total: [0-9]+ eval\(s\)' "$eval_log" | tail -1 || true)
  ok "validate-evals.sh ${total:-passed}"
else
  err "validate-evals.sh failed"
  [ "$QUIET" = "0" ] && tail -20 "$eval_log" >&2
fi
rm -f "$eval_log"

if run_python scripts/ci/test-eval-schema.py >/dev/null; then
  ok "strict eval schema regression cases"
else
  err "strict eval schema regression cases failed"
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import pathlib
import sys

sys.path.insert(0, 'scripts/ci/lib')
from strict_json import load_strict, require_exact_keys

errors = []
seen = set()
allowed_entry_keys = {
    'id',
    'title',
    'prompt',
    'expected_output',
    'files',
    'assertions',
}
for path in sorted(pathlib.Path('skills').glob('*/evals/evals.json')):
    data = load_strict(path)
    require_exact_keys(
        data,
        {'skill_name', 'evals'},
        context=str(path),
    )
    skill = path.parts[1]
    if data.get('skill_name') != skill:
        errors.append(f"{path}: skill_name must be {skill!r}")
    if not isinstance(data['evals'], list):
        errors.append(f"{path}: evals must be a list")
        continue
    ids = []
    for index, entry in enumerate(data['evals']):
        if not isinstance(entry, dict):
            errors.append(f"{path}: evals[{index}] must be an object")
            continue
        unknown = sorted(set(entry) - allowed_entry_keys)
        if unknown:
            errors.append(
                f"{path}: evals[{index}] has unknown keys {unknown!r}"
            )
        missing = sorted(
            {'id', 'prompt', 'expected_output', 'assertions'} - set(entry)
        )
        if missing:
            errors.append(
                f"{path}: evals[{index}] is missing keys {missing!r}"
            )
            continue
        eval_id = entry.get('id')
        key = (skill, eval_id)
        if key in seen:
            errors.append(f"{path}: duplicate eval id {eval_id!r}")
        seen.add(key)
        ids.append(eval_id)
        if 'files' in entry and not isinstance(entry['files'], list):
            errors.append(f"{path}: eval {eval_id!r} files must be a list when present")
    if ids != sorted(ids):
        errors.append(f"{path}: eval ids should be sorted")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "eval names and ids match skill conventions"
  else
    err "eval convention check failed"
  fi
else
  warn "python3 not available; skipped eval convention check"
fi

section "Security"
if [ "${E2E_SKILLS_SKIP_SECURITY:-}" = "1" ]; then
  err "refusing E2E_SKILLS_SKIP_SECURITY=1; standalone review requires security"
else
  security_log=$(mktemp "${TMPDIR:-/tmp}/e2e-skills-security.XXXXXX")
  if /bin/bash -p scripts/ci/pre-push-security.sh --quiet >"$security_log" 2>&1; then
    ok "pre-push-security.sh clean"
  else
    err "pre-push-security.sh blockers found"
    [ "$QUIET" = "0" ] && cat "$security_log" >&2
  fi
  rm -f "$security_log"
fi

ast_grep_workflow=".github/workflows/e2e-smell-scan.yml"
if [ ! -f "$ast_grep_workflow" ]; then
  err "missing ast-grep workflow: $ast_grep_workflow"
elif grep -qF "npm i -g '@ast-grep/cli@0.39.7'" "$ast_grep_workflow" &&
     [ "$(grep -cF "@ast-grep/cli@" "$ast_grep_workflow")" -eq 1 ]; then
  ok "workflow pins @ast-grep/cli exactly to 0.39.7"
else
  err "workflow ast-grep install must use exact @ast-grep/cli@0.39.7"
fi

section "Public skill surface"
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import json
import pathlib
import re
import sys

sys.path.insert(0, 'scripts/ci/lib')
from strict_json import load_manifest_json
from validate_codex import collect_codex_errors
from version_contract import canonical_semver_error

errors = []
skill_dirs = sorted(path for path in pathlib.Path('skills').iterdir() if path.is_dir())
expected = {path.name for path in skill_dirs}

def parse_openai_manifest(path):
    """Parse the deliberately small agents/openai.yaml schema, fail closed."""
    text = path.read_text(encoding='utf-8')
    if text.startswith('\ufeff'):
        raise ValueError("UTF-8 BOM is not supported")
    if '\t' in text:
        raise ValueError("tabs are not allowed")
    top = {}
    metadata = {}
    current = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith(' '):
            match = re.fullmatch(r"  ([A-Za-z_][A-Za-z0-9_-]*):[ ]+(.+)", line)
            if current != 'metadata' or not match:
                raise ValueError(f"line {number}: unsupported indentation or nested value")
            key, value = match.groups()
            if key in metadata:
                raise ValueError(f"line {number}: duplicate metadata key {key!r}")
            metadata[key] = value
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ ]+(.*))?", line)
        if not match:
            raise ValueError(f"line {number}: unsupported YAML syntax")
        key, value = match.groups()
        if key in top:
            raise ValueError(f"line {number}: duplicate top-level key {key!r}")
        if key == 'metadata':
            if value is not None:
                raise ValueError(f"line {number}: metadata must be a mapping")
            top[key] = metadata
        else:
            if value is None or not value.strip():
                raise ValueError(f"line {number}: {key} must have a scalar value")
            if re.search(r":\s|(?:^|\s)#", value):
                raise ValueError(f"line {number}: unsupported ambiguous plain scalar")
            top[key] = value
        current = key
    expected_top = {'name', 'description', 'metadata', 'allow_implicit_invocation'}
    if set(top) != expected_top:
        raise ValueError(
            f"top-level keys must be exactly {sorted(expected_top)!r}, got {sorted(top)!r}"
        )
    if set(metadata) != {'short-description'}:
        raise ValueError("metadata must contain exactly short-description")
    if top['allow_implicit_invocation'] not in {'true', 'false'}:
        raise ValueError("allow_implicit_invocation must be true or false")
    return top

plugin = load_manifest_json(pathlib.Path('.claude-plugin/plugin.json'))
codex_plugin = load_manifest_json(pathlib.Path('.codex-plugin/plugin.json'))
expected_paths = {f'./skills/{skill}' for skill in expected}
plugin_paths = plugin.get('skills')
if (
    not isinstance(plugin_paths, list)
    or not all(isinstance(path, str) for path in plugin_paths)
    or set(plugin_paths) != expected_paths
    or len(plugin_paths) != len(expected_paths)
):
    errors.append(f"Claude plugin skills must be exactly these paths: {sorted(expected_paths)!r}")

errors.extend(collect_codex_errors(codex_plugin, expected, pathlib.Path('.')))

frontmatter_names = set()
plugin_version = plugin.get('version')
for skill_dir in skill_dirs:
    skill_file = skill_dir / 'SKILL.md'
    text = skill_file.read_text(encoding='utf-8')
    match = re.search(r"^---\n(.*?)\n---", text, re.S)
    if not match:
        errors.append(f"{skill_file}: missing YAML frontmatter")
        continue
    name = re.search(r"^name:\s*['\"]?([^'\"\n]+)['\"]?\s*$", match.group(1), re.M)
    if not name:
        errors.append(f"{skill_file}: missing frontmatter name")
        continue
    public_name = name.group(1).strip()
    frontmatter_names.add(public_name)
    if public_name != skill_dir.name:
        errors.append(f"{skill_file}: frontmatter name must match directory {skill_dir.name}")
    desc = re.search(r"^description:\s*(.+?)\s*$", match.group(1), re.M)
    if desc:
        val = desc.group(1)
        quoted = (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"'))
        desc_value = val[1:-1] if quoted else val
        if len(desc_value) > 1024:
            errors.append(
                f"{skill_file}: frontmatter description exceeds 1024 characters "
                f"({len(desc_value)})"
            )
        if not quoted and re.search(r":\s", val):
            errors.append(
                f"{skill_file}: frontmatter description contains ': ' (colon-space) in an unquoted plain scalar — "
                "wrap the description in single quotes; YAML parsers (gray-matter / js-yaml) reject this and the "
                "skills CLI will silently skip the skill (regression of bug fixed in v0.7.3)"
            )
    # SKILL.md metadata.version must match the plugin manifest version. The
    # manifest-vs-manifest version parity check above guards Claude/Codex/
    # marketplace drift; this guard catches the case where a SKILL.md file
    # gets left behind during a lock-step bump (see v1.3.1 changelog).
    version_match = re.search(r"^  version:\s*['\"]?([^'\"\n]+)['\"]?\s*$", match.group(1), re.M)
    if not version_match:
        errors.append(f"{skill_file}: missing metadata.version in frontmatter")
    else:
        skill_version = version_match.group(1).strip()
        version_error = canonical_semver_error(
            skill_version, f"{skill_file}: metadata.version"
        )
        if version_error:
            errors.append(version_error)
        elif plugin_version and skill_version != plugin_version:
            errors.append(
                f"{skill_file}: metadata.version {skill_version!r} "
                f"does not match plugin version {plugin_version!r}"
            )

if frontmatter_names != expected:
    errors.append(f"skills/*/SKILL.md names mismatch: {sorted(frontmatter_names)} != {sorted(expected)}")

for skill_dir in skill_dirs:
    manifest = skill_dir / 'agents' / 'openai.yaml'
    if not manifest.exists():
        errors.append(f"{manifest}: missing")
        continue
    try:
        parsed = parse_openai_manifest(manifest)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"{manifest}: invalid OpenAI agent YAML: {exc}")
        continue
    if parsed['name'] != skill_dir.name:
        errors.append(f"{manifest}: name must match {skill_dir.name}")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "Claude, Codex, and OpenAI skill surfaces match"
  else
    err "public skill surface parity failed"
  fi
else
  err "python3 unavailable; public skill/OpenAI YAML checks did not run"
fi

# Frontmatter `description` is the cross-host trigger surface and is pre-loaded for EVERY
# installed skill, so it is budgeted, not free:
#   - Claude Code: hard cap of 1,024 characters (validation error above it).
#   - Codex: no per-skill cap, but the whole skill list is capped at 2% of the context window
#     (8,000 chars when unknown). Over budget, Codex SHORTENS descriptions first and may drop
#     skills entirely — so a long description silently loses its tail, and with it any trigger
#     phrases parked at the end. Front-load the use case and trigger words.
# WARN threshold leaves headroom to add triggers later without hitting the hard cap by surprise.
section "Skill description budget"
if command -v python3 >/dev/null 2>&1; then
  desc_out=$(python3 - "$REPO_ROOT" <<'PY'
import pathlib, re, sys
HARD, SOFT = 1024, 900
root = pathlib.Path(sys.argv[1])
bad, warned = [], []
skills_seen = 0
for skill in sorted((root / "skills").iterdir()):
    md = skill / "SKILL.md"
    if not md.is_file():
        continue
    skills_seen += 1
    text = md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        bad.append(f"{skill.name}: missing YAML frontmatter")
        continue
    d = re.search(r"^description:[ \t]*(.*(?:\n[ \t]+.*)*)", m.group(1), re.M)
    if not d:
        bad.append(f"{skill.name}: no description field")
        continue
    val = " ".join(part.strip() for part in d.group(1).splitlines()).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
        val = val[1:-1]
    n = len(val)
    if n > HARD:
        bad.append(f"{skill.name}: description {n} chars exceeds the {HARD}-char cap")
    elif n > SOFT:
        warned.append(f"{skill.name}: description {n} chars (cap {HARD}) — little headroom; Codex truncates long descriptions first")
if not skills_seen:
    print("BAD:no SKILL.md found under skills/ — the check scanned nothing")
    raise SystemExit(0)
print("BAD:" + "|".join(bad))
print("WARN:" + "|".join(warned))
PY
  )
  # Fail closed. This block parses stdout instead of relying on the exit code alone (it needs to
  # tell FAIL from WARN), so a crashed interpreter would otherwise yield empty output and print
  # [OK] — the same false-pass shape as the earlier undefined-$ROOT bug. Require both a zero exit
  # and the expected BAD:/WARN: envelope before trusting the result.
  desc_rc=$?
  if [ "$desc_rc" -ne 0 ] || [ "${desc_out#BAD:}" = "$desc_out" ]; then
    err "skill description budget check did not run (python exit $desc_rc); output: ${desc_out:-<empty>}"
    desc_bad=""; desc_warn=""
  else
    desc_bad=${desc_out#BAD:}; desc_bad=${desc_bad%%$'\n'*}
    desc_warn=${desc_out##*WARN:}
    if [ -n "$desc_bad" ]; then
      IFS='|' read -ra _dbad <<< "$desc_bad"
      for _m in "${_dbad[@]}"; do [ -n "$_m" ] && err "$_m"; done
    elif [ -n "$desc_warn" ]; then
      IFS='|' read -ra _dwarn <<< "$desc_warn"
      for _m in "${_dwarn[@]}"; do [ -n "$_m" ] && warn "$_m"; done
    else
      ok "all skill descriptions within the 1024-char cap with headroom"
    fi
  fi
else
  warn "python3 not available; skipped skill description budget check"
fi

section "Pattern and description parity"
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import json
import pathlib
import re
import sys

sys.path.insert(0, 'scripts/ci/lib')
from strict_json import load_manifest_json
from manifest_phrase_contract import MANIFEST_PATTERN_PHRASES

errors = []

skill_text = pathlib.Path('skills/e2e-reviewer/SKILL.md').read_text(encoding='utf-8')
grep_text = pathlib.Path('skills/e2e-reviewer/references/grep-patterns.md').read_text(encoding='utf-8')
patref_text = pathlib.Path('skills/e2e-reviewer/references/pattern-reference.md').read_text(encoding='utf-8')
scan_text = pathlib.Path('skills/e2e-reviewer/scripts/scan.sh').read_text(encoding='utf-8')
docs_text = pathlib.Path('docs/e2e-test-smells.md').read_text(encoding='utf-8')
readme_text = pathlib.Path('README.md').read_text(encoding='utf-8')
plugin = load_manifest_json(pathlib.Path('.claude-plugin/plugin.json'))
market = load_manifest_json(pathlib.Path('.claude-plugin/marketplace.json'))
codex_plugin = load_manifest_json(pathlib.Path('.codex-plugin/plugin.json'))

qr_match = re.search(r'## Quick Reference\s*\n(?:.*\n)*?((?:\|.*\n)+)', skill_text)
if not qr_match:
    print('e2e-reviewer/SKILL.md: could not locate Quick Reference table', file=sys.stderr)
    sys.exit(1)

qr_severity = {}
qr_titles = {}
for row in qr_match.group(1).splitlines():
    m = re.match(
        r'\|\s*(\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|\s*(P[012](?:/P[012])?)\s*\|',
        row,
    )
    if m:
        qr_titles[m.group(1)] = m.group(2).strip()
        qr_severity[m.group(1)] = m.group(3)
qr_ids = set(qr_severity)

def base_id(s):
    s = s.split('-')[0]
    m = re.match(r'^(\d+)', s)
    return m.group(1) if m else s

def matches_qr(s):
    return s in qr_ids or base_id(s) in qr_ids

# Check 1: every pattern id in subordinate sources must map back to a QR base id
grep_ids = sorted(set(re.findall(r'\|\s*#(\d+[a-z]?(?:-\d+[a-z]?)?)', grep_text)))
scan_ids = sorted(set(re.findall(r"run_check\s+P[012]\s+'#(\d+[a-z]?(?:-\d+[a-z]?)?)", scan_text)))
docs_ids = sorted(set(re.findall(r'\|\s*#(\d+[a-z]?)\s*\|', docs_text)))
for label, ids in (
    ('skills/e2e-reviewer/references/grep-patterns.md', grep_ids),
    ('skills/e2e-reviewer/scripts/scan.sh', scan_ids),
    ('docs/e2e-test-smells.md', docs_ids),
):
    for pid in ids:
        if not matches_qr(pid):
            errors.append(f"{label}: pattern #{pid} has no matching base id in e2e-reviewer/SKILL.md Quick Reference")

# Check 1b: every QR base id must appear in docs/e2e-test-smells.md (reverse of Check 1)
docs_id_set = set(docs_ids)
missing_in_docs = sorted(pid for pid in qr_ids if pid not in docs_id_set)
if missing_in_docs:
    errors.append(
        f"docs/e2e-test-smells.md: missing rows for Quick Reference ids {missing_in_docs}"
    )

# Check 1c: docs/e2e-test-smells.md taxonomy tables must keep four complete
# columns. ID/severity parity can stay green even when a Markdown row is
# truncated and drops the user-facing rationale.
def split_markdown_table_row(line):
    """Split separators while preserving Markdown-escaped pipe characters."""
    cells = []
    current = []
    preceding_backslashes = 0
    for character in line.strip()[1:-1]:
        if character == '|' and preceding_backslashes % 2 == 0:
            cells.append(''.join(current).strip())
            current = []
            preceding_backslashes = 0
            continue
        current.append(character)
        if character == '\\':
            preceding_backslashes += 1
        else:
            preceding_backslashes = 0
    cells.append(''.join(current).strip())
    return cells

for number, line in enumerate(docs_text.splitlines(), 1):
    if not re.match(r'\|\s*#\d+[a-z]?\s*\|', line):
        continue
    stripped = line.strip()
    if not stripped.startswith('|') or not stripped.endswith('|'):
        errors.append(
            f"docs/e2e-test-smells.md:{number}: taxonomy row must start and end with |"
        )
        continue
    cells = split_markdown_table_row(stripped)
    if len(cells) != 4 or any(not cell for cell in cells):
        errors.append(
            f"docs/e2e-test-smells.md:{number}: taxonomy row must have 4 non-empty columns"
        )

# Check 1d: the changelog's scanner budget note must match the measured audit
# document. This is not a benchmark claim; it protects a small public prose
# contract from drifting by one number while both files still read plausibly.
audit_budget = re.search(
    r'preregistered 123,000 reference tokens\s+—\s+([a-z]+) tokens of headroom',
    pathlib.Path('docs/rule-self-audit.md').read_text(encoding='utf-8'),
)
changelog_budget = re.search(
    r'frozen review packet with ([a-z]+) tokens\s+of headroom',
    pathlib.Path('CHANGELOG.md').read_text(encoding='utf-8'),
)
if not audit_budget:
    errors.append("docs/rule-self-audit.md: missing scanner headroom statement")
elif not changelog_budget:
    errors.append("CHANGELOG.md: missing scanner headroom statement")
elif changelog_budget.group(1) != audit_budget.group(1):
    errors.append(
        "CHANGELOG.md: scanner headroom must match docs/rule-self-audit.md "
        f"({changelog_budget.group(1)} != {audit_budget.group(1)})"
    )

# Check 1e: roadmap campaign summaries must equal the rows in their own
# false-green tables. Reviewer-informed maintenance is a separate contribution
# class and must not inflate either campaign count.
roadmap_text = pathlib.Path('docs/roadmap.md').read_text(encoding='utf-8')
roadmap_sections = {}

def roadmap_section(title):
    if title in roadmap_sections:
        return roadmap_sections[title]
    sections = re.findall(
        rf'^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)',
        roadmap_text,
        re.M | re.S,
    )
    if len(sections) != 1:
        errors.append(
            f"docs/roadmap.md: expected exactly one {title} section, found {len(sections)}"
        )
        roadmap_sections[title] = None
        return None
    roadmap_sections[title] = sections[0]
    return sections[0]

def roadmap_section_rows(title):
    section = roadmap_section(title)
    if section is None:
        return None
    return [
        line
        for line in section.splitlines()
        if re.match(r'^\|\s*[^-|][^|]*\|', line)
        and not line.startswith('| Repository |')
    ]

roadmap_counts = {}
for title, summary_pattern in (
    ('Merged', r'^- \*\*Merged:\*\* (\d+) upstream PRs'),
    ('In review', r'^- \*\*In review:\*\* (\d+) active/open upstream PRs'),
):
    summaries = re.findall(summary_pattern, roadmap_text, re.M)
    rows = roadmap_section_rows(title)
    if len(summaries) != 1:
        errors.append(
            f"docs/roadmap.md: expected exactly one {title} summary count, "
            f"found {len(summaries)}"
        )
    else:
        summary_count = int(summaries[0])
        roadmap_counts[title] = summary_count
        if rows is not None and summary_count != len(rows):
            errors.append(
                f"docs/roadmap.md: {title} summary count {summary_count} "
                f"does not match {len(rows)} table rows"
            )

def pull_request_urls(text):
    if text is None:
        return []
    return re.findall(
        r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+',
        text,
    )

merged_section = roadmap_section('Merged')
in_review_section = roadmap_section('In review')
maintenance_section = roadmap_section('Reviewer-informed maintenance')
merged_urls = pull_request_urls(merged_section)
in_review_urls = pull_request_urls(in_review_section)
maintenance_urls = pull_request_urls(maintenance_section)

for title, urls in (
    ('Merged', merged_urls),
    ('In review', in_review_urls),
    ('Reviewer-informed maintenance', maintenance_urls),
):
    rows = roadmap_section_rows(title)
    if rows is not None and (
        len(urls) != len(rows) or len(urls) != len(set(urls))
    ):
        errors.append(
            f"docs/roadmap.md: {title} table must contain one distinct PR URL per row"
        )

for left_title, left_urls, right_title, right_urls in (
    ('Merged', merged_urls, 'In review', in_review_urls),
    ('Merged', merged_urls, 'Reviewer-informed maintenance', maintenance_urls),
    ('In review', in_review_urls, 'Reviewer-informed maintenance', maintenance_urls),
):
    overlap = sorted(set(left_urls) & set(right_urls))
    if overlap:
        errors.append(
            f"docs/roadmap.md: {left_title} and {right_title} share PR URLs {overlap}"
        )

tooljet_url = 'https://github.com/ToolJet/ToolJet/pull/17492'
if tooljet_url not in maintenance_urls:
    errors.append(
        "docs/roadmap.md: ToolJet #17492 must remain Reviewer-informed maintenance"
    )
if tooljet_url in merged_urls or tooljet_url in in_review_urls:
    errors.append(
        "docs/roadmap.md: ToolJet #17492 must not enter false-green campaign counts"
    )

readme_adoption = re.findall(
    r'^## Open-source adoption\s*$\n(.*?)(?=^## |\Z)',
    readme_text,
    re.M | re.S,
)
if len(readme_adoption) != 1:
    errors.append(
        f"README.md: expected exactly one Open-source adoption section, found {len(readme_adoption)}"
    )
else:
    readme_merged_urls = pull_request_urls(readme_adoption[0])
    if len(readme_merged_urls) != len(set(readme_merged_urls)):
        errors.append("README.md: Open-source adoption table contains duplicate PR URLs")
    if set(readme_merged_urls) != set(merged_urls):
        errors.append("README.md: merged PR URL set differs from docs/roadmap.md")

merged_count = roadmap_counts.get('Merged')
if merged_count is not None:
    count_contracts = [
        (
            'README.md merged badge',
            re.findall(r'merged_PRs-(\d+)-', readme_text),
        ),
        (
            'README.md Why try it',
            re.findall(
                r'\[(\d+) merged upstream PRs\]\(#open-source-adoption\)',
                readme_text,
            ),
        ),
        (
            'README.md Open-source adoption',
            re.findall(r'\*\*(\d+) merged upstream PRs\*\*', readme_adoption[0])
            if len(readme_adoption) == 1
            else [],
        ),
        (
            'benchmarks/STATUS.md merged count',
            re.findall(
                r'Findings have contributed to \*\*(\d+) merged upstream PRs\*\*',
                pathlib.Path('benchmarks/STATUS.md').read_text(encoding='utf-8'),
            ),
        ),
    ]
    for label, matches in count_contracts:
        if len(matches) != 1:
            errors.append(f"{label}: expected exactly one count, found {len(matches)}")
        elif int(matches[0]) != merged_count:
            errors.append(
                f"{label} {matches[0]} does not match roadmap {merged_count}"
            )

    translated_prose_patterns = {
        'README.ko.md': r'PR (?:\*\*)?(\d+)건이',
        'README.ja.md': r'(?:\[|\*\*)(\d+) 件のマージ済み upstream PR',
        'README.zh-cn.md': r'(?:\[|\*\*)(\d+) 个合入上游的 PR',
    }
    for translated_readme, prose_pattern in translated_prose_patterns.items():
        translated_text = pathlib.Path(translated_readme).read_text(encoding='utf-8')
        badge_counts = re.findall(
            r'merged_PRs-(\d+)-',
            translated_text,
        )
        if len(badge_counts) != 1:
            errors.append(
                f"{translated_readme} merged badge: expected exactly one count, "
                f"found {len(badge_counts)}"
            )
        elif int(badge_counts[0]) != merged_count:
            errors.append(
                f"{translated_readme} merged badge {badge_counts[0]} does not match "
                f"roadmap {merged_count}"
            )
        prose_counts = re.findall(prose_pattern, translated_text)
        if prose_counts != [str(merged_count), str(merged_count)]:
            errors.append(
                f"{translated_readme} merged prose counts {prose_counts} do not match "
                f"roadmap {merged_count} twice"
            )

# Check 2: docs P0/P1/P2 section placement must agree with QR severity
sections = re.split(r'^##\s+(P[012]):', docs_text, flags=re.M)
for i in range(1, len(sections), 2):
    sev = sections[i]
    body = sections[i + 1]
    for pid in re.findall(r'\|\s*#(\d+[a-z]?)\s*\|', body):
        key = pid if pid in qr_severity else base_id(pid)
        qr_sev = qr_severity.get(key)
        if qr_sev and sev not in qr_sev:
            errors.append(f"docs/e2e-test-smells.md: #{pid} under {sev} but Quick Reference says {qr_sev}")

# Check 3: README severity-section placement must agree with QR severity
readme_sev_specs = [
    ('P0', 'P0', r'#### P0 — Must Fix[^\n]*\n(.+?)(?=\n####|\n###|\Z)'),
    ('P1', 'P1', r'#### P1 — Should Fix[^\n]*\n(.+?)(?=\n####|\n###|\Z)'),
    ('P2', 'P2', r'#### P2 — Nice to Fix[^\n]*\n(.+?)(?=\n####|\n###|\Z)'),
]
for sev_name, required, pattern in readme_sev_specs:
    tm = re.search(pattern, readme_text, re.S)
    if not tm:
        errors.append(f"README: missing {sev_name} section")
        continue
    for pid in re.findall(r'\|\s*(\d+[a-z]?)\s*\|\s*\*\*', tm.group(1)):
        qr_sev = qr_severity.get(pid)
        if qr_sev and required not in qr_sev:
            errors.append(f"README {sev_name} lists #{pid} but Quick Reference severity is {qr_sev}")

# Check 3b: e2e-reviewer/SKILL.md severity-section placement must agree with QR severity
skill_sev_specs = [
    ('P0', 'P0', r'### P0 — Must Fix[^\n]*\n(.+?)(?=\n### |\Z)'),
    ('P1', 'P1', r'### P1 — Should Fix[^\n]*\n(.+?)(?=\n### |\Z)'),
    ('P2', 'P2', r'### P2 — Nice to Fix[^\n]*\n(.+?)(?=\n### |\Z)'),
]
section_ids = set()
for sev_name, required, pattern in skill_sev_specs:
    tm = re.search(pattern, patref_text, re.S)
    if not tm:
        errors.append(f"e2e-reviewer/references/pattern-reference.md: missing {sev_name} section")
        continue
    for pid in re.findall(r'^####\s+(\d+[a-z]?)\.', tm.group(1), re.M):
        section_ids.add(pid)
        qr_sev = qr_severity.get(pid)
        if qr_sev and required not in qr_sev:
            errors.append(
                f"e2e-reviewer/references/pattern-reference.md {sev_name} lists #{pid} but Quick Reference severity is {qr_sev}"
            )

# Check 3c: Quick Reference row count equals 24 and ID set equals Pattern Reference section IDs
if len(qr_severity) != 24:
    errors.append(
        f"e2e-reviewer/SKILL.md Quick Reference: expected 24 rows, got {len(qr_severity)}"
    )
qr_only = qr_ids - section_ids
section_only = section_ids - qr_ids
if qr_only:
    errors.append(
        f"e2e-reviewer/SKILL.md Quick Reference has IDs missing from references/pattern-reference.md sections: {sorted(qr_only)}"
    )
if section_only:
    errors.append(
        f"e2e-reviewer/references/pattern-reference.md sections have IDs missing from Quick Reference: {sorted(section_only)}"
    )

# Check 4: debugger evals.json may only reference F-codes from SKILL.md F-table
for skill in ('playwright-debugger', 'cypress-debugger'):
    md_path = pathlib.Path('skills') / skill / 'SKILL.md'
    evals_path = pathlib.Path('skills') / skill / 'evals' / 'evals.json'
    md_text = md_path.read_text(encoding='utf-8')
    evals = json.loads(evals_path.read_text(encoding='utf-8'))
    skill_codes = set(re.findall(r'\|\s*(F\d+)\s*\|', md_text))
    seen = set()

    def scan(obj):
        if isinstance(obj, str):
            seen.update(re.findall(r'\bF\d+\b', obj))
        elif isinstance(obj, list):
            for v in obj:
                scan(v)
        elif isinstance(obj, dict):
            for v in obj.values():
                scan(v)

    scan(evals)
    missing = seen - skill_codes
    if missing:
        errors.append(f"{evals_path}: F-codes not in SKILL.md taxonomy: {sorted(missing)}")

# Check 5: severity-grouped manifest phrase parity. The source is the checked
# ID/title contract above, never one of the three manifests being compared.
def normalize(s):
    s = s.lower()
    s = re.sub(r'[^a-z0-9+]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

contract_ids = {pid for pid, _, _, _ in MANIFEST_PATTERN_PHRASES}
if len(MANIFEST_PATTERN_PHRASES) != 24 or contract_ids != qr_ids:
    errors.append(
        "manifest phrase contract must contain exactly the 24 Quick Reference IDs"
    )

for pid, expected_title, severity, _ in MANIFEST_PATTERN_PHRASES:
    actual_title = qr_titles.get(pid)
    if actual_title != expected_title:
        errors.append(
            f"manifest phrase contract #{pid} title {expected_title!r} "
            f"does not match Quick Reference {actual_title!r}"
        )
    actual_severity = qr_severity.get(pid, "")
    if severity not in actual_severity.split("/"):
        errors.append(
            f"manifest phrase contract #{pid} severity {severity} "
            f"does not match Quick Reference {actual_severity!r}"
        )

ordered_phrases = [
    normalize(phrase) for _, _, _, phrase in MANIFEST_PATTERN_PHRASES
]
plugin_desc_norm = normalize(plugin.get('description', ''))
market_desc_norm = ''
for entry in market.get('plugins', []):
    if entry.get('name') == 'e2e-skills':
        market_desc_norm = normalize(entry.get('description', ''))
        break
codex_desc_norm = normalize(codex_plugin.get('description', ''))

for label, desc in (
    ('.claude-plugin/plugin.json', plugin_desc_norm),
    ('.claude-plugin/marketplace.json', market_desc_norm),
    ('.codex-plugin/plugin.json', codex_desc_norm),
):
    pos = 0
    for phrase in ordered_phrases:
        idx = desc.find(phrase, pos)
        if idx < 0:
            errors.append(f"{label}: missing or out-of-order pattern '{phrase}'")
            break
        pos = idx + len(phrase)

# Check 6: version parity across all three manifest files
plugin_version = plugin.get('version')
market_version = None
for entry in market.get('plugins', []):
    if entry.get('name') == 'e2e-skills':
        market_version = entry.get('version')
        break
codex_version = codex_plugin.get('version')
versions = {
    '.claude-plugin/plugin.json': plugin_version,
    '.claude-plugin/marketplace.json (plugins[e2e-skills])': market_version,
    '.codex-plugin/plugin.json': codex_version,
}
distinct = {v for v in versions.values() if v is not None}
if None in versions.values() or len(distinct) > 1:
    errors.append(f"manifest version mismatch: {versions}")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "pattern IDs, severities, F-codes, and P0/P1/P2 pattern descriptions consistent"
  else
    err "pattern/severity/description parity check failed"
  fi
else
  warn "python3 not available; skipped pattern parity check"
fi

section "Framework scope"
if command -v python3 >/dev/null 2>&1; then
  if python3 - "$REPO_ROOT" <<'PY'
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
frameworks = ("Puppeteer", "Selenium", "WebdriverIO", "TestCafe", "Nightwatch")
framework_re = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in frameworks) + r")\b",
    re.I,
)
negative_scope_re = re.compile(
    r"(?:"
    r"\bout[- ]of[- ]scope\b|"
    r"\bnot in scope\b|"
    r"\bdoes not (?:accept|produce|ship|support)\b|"
    r"\bdo not introduce\b|"
    r"\bmust not appear\b|"
    r"\bintentionally not listed as supported\b"
    r")",
    re.I,
)
evidence_document_sections = {
    pathlib.Path("docs/llm-generated-e2e-test-evidence.md"): None,
    pathlib.Path("README.md"): "Further evidence and practice",
}
evidence_attribution_re = re.compile(
    r"(?:"
    r"\b(?:study|paper|preprint|proceedings|evaluation|implementation|"
    r"evidence|reports?|evaluates?|measures?|results?)\b|"
    r"\bdoi\b|arxiv\.org|doi\.org"
    r")",
    re.I,
)
product_subject_re = (
    r"(?:\be2e[- ]skills\b|\bthis (?:bundle|product|repository|skill)\b|"
    r"\bour (?:bundle|product|repository|skill)s?\b)"
)
positive_capability_re = (
    r"(?:fully support(?:s|ed)?|support(?:s|ed)?|generat(?:e|es|ed|ing)|"
    r"produc(?:e|es|ed|ing)|review(?:s|ed|ing)?|debug(?:s|ged|ging)?)"
)
control_files = {
    pathlib.Path("scripts/ci/review.sh"),
    pathlib.Path("scripts/ci/test-parity.sh"),
}
scope_document = pathlib.Path("docs/framework-scope.md")

listed = subprocess.run(
    ["git", "ls-files", "-co", "--exclude-standard", "--"],
    cwd=str(root),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    check=False,
)
if listed.returncode != 0:
    print(
        "framework scope: git file enumeration failed: {}".format(
            listed.stderr.strip() or "unknown error"
        ),
        file=sys.stderr,
    )
    raise SystemExit(1)

paths = []
for raw in listed.stdout.splitlines():
    path = pathlib.Path(raw)
    if (
        path in {pathlib.Path("README.md"), pathlib.Path("CONTRIBUTING.md"), pathlib.Path("AGENTS.md")}
        or path.parts[:1] in {
            ("skills",),
            ("docs",),
            (".claude-plugin",),
            (".codex-plugin",),
            ("scripts",),
        }
    ):
        paths.append(path)
if not paths:
    print("framework scope: file enumeration returned zero scoped files", file=sys.stderr)
    raise SystemExit(1)

errors = []
for relative in sorted(set(paths)):
    absolute = root / relative
    if not absolute.is_file() or relative in control_files or relative == scope_document:
        continue
    text = absolute.read_text(encoding="utf-8", errors="replace")
    evidence_region = None
    evidence_heading = evidence_document_sections.get(relative)
    if relative in evidence_document_sections:
        if evidence_heading is None:
            evidence_region = (0, len(text))
        else:
            heading_re = re.compile(
                rf"^(?P<marks>#{{1,6}})[ \t]+{re.escape(evidence_heading)}[ \t]*$",
                re.M,
            )
            heading_match = heading_re.search(text)
            if heading_match:
                heading_level = len(heading_match.group("marks"))
                next_heading = re.search(
                    rf"^#{{1,{heading_level}}}[ \t]+",
                    text[heading_match.end():],
                    re.M,
                )
                region_end = (
                    heading_match.end() + next_heading.start()
                    if next_heading
                    else len(text)
                )
                evidence_region = (heading_match.start(), region_end)
    for match in framework_re.finditer(text):
        # Exempt only when the negative scope wording governs this framework in
        # the same sentence/clause. A separate negative sentence elsewhere in
        # the paragraph must not launder a positive support claim.
        sentence_start_matches = list(re.finditer(r"[.!?](?:\s|$)", text[:match.start()]))
        sentence_start = sentence_start_matches[-1].end() if sentence_start_matches else 0
        sentence_end_match = re.search(r"[.!?](?:\s|$)", text[match.end():])
        sentence_end = (
            match.end() + sentence_end_match.start()
            if sentence_end_match
            else len(text)
        )
        sentence = text[sentence_start:sentence_end]
        match_in_sentence = match.start() - sentence_start
        clause_start_matches = list(re.finditer(r"[;|]", sentence[:match_in_sentence]))
        clause_start = clause_start_matches[-1].end() if clause_start_matches else 0
        clause_end_match = re.search(r"[;|]", sentence[match_in_sentence:])
        clause_end = (
            match_in_sentence + clause_end_match.start()
            if clause_end_match
            else len(sentence)
        )
        clause = sentence[clause_start:clause_end]
        if negative_scope_re.search(clause):
            continue
        if (
            evidence_region is not None
            and evidence_region[0] <= match.start() < evidence_region[1]
        ):
            block_start = text.rfind("\n\n", 0, match.start())
            block_start = 0 if block_start < 0 else block_start + 2
            block_end = text.find("\n\n", match.end())
            block_end = len(text) if block_end < 0 else block_end
            block = text[block_start:block_end]
            framework = re.escape(match.group(1))
            product_claim_re = re.compile(
                rf"(?:"
                rf"{product_subject_re}.{{0,180}}{positive_capability_re}.{{0,80}}\b{framework}\b|"
                rf"\b{framework}\b.{{0,80}}{positive_capability_re}.{{0,180}}{product_subject_re}"
                rf")",
                re.I | re.S,
            )
            # Evidence documents are not blanket-whitelisted. Each reference
            # must remain inside an attributed research/evidence block, and a
            # positive e2e-skills capability claim invalidates that exemption.
            if evidence_attribution_re.search(block) and not product_claim_re.search(block):
                continue
        line = text.count("\n", 0, match.start()) + 1
        canonical = next(
            name for name in frameworks if name.lower() == match.group(1).lower()
        )
        errors.append(
            "{}:{}: unsupported framework reference: {}".format(
                relative,
                line,
                canonical,
            )
        )

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    raise SystemExit(1)
PY
  then
    ok "no accidental support claims for the five declared out-of-scope frameworks"
  else
    err "unsupported framework references found outside narrow negative/scope documentation"
  fi
else
  err "python3 unavailable; framework scope check did not run"
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import pathlib
import re
import sys

required = {
    'playwright-test-generator': ('Playwright',),
    'e2e-reviewer': ('Playwright', 'Cypress'),
    'playwright-debugger': ('Playwright',),
    'cypress-debugger': ('Cypress',),
}
errors = []
for skill, words in required.items():
    path = pathlib.Path('skills') / skill / 'SKILL.md'
    text = path.read_text(encoding='utf-8')
    frontmatter = re.search(r"^---\n(.*?)\n---", text, re.S)
    surface = frontmatter.group(1) if frontmatter else text[:500]
    for word in words:
        if word not in surface:
            errors.append(f"{path}: frontmatter description should mention {word}")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "skill trigger descriptions preserve Playwright/Cypress boundaries"
  else
    err "skill trigger boundary check failed"
  fi
else
  warn "python3 not available; skipped skill trigger boundary check"
fi

section "Subagent parity"
# AGENTS.md rule 5: a subagent must never be the ONLY path to a verdict — the
# inline fallback must reach an identical verdict from the same source of truth.
# These checks freeze that contract and guard the A1 fix (agents must be handed
# an absolute source-of-truth path, since their CWD is the project under review,
# not this repo). A relative `skills/...` read target silently resolves nowhere.
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import pathlib
import re
import sys

errors = []


def read(rel):
    p = pathlib.Path(rel)
    if not p.is_file():
        errors.append(f"{rel}: expected file is missing")
        return ""
    return p.read_text(encoding="utf-8")


verifier = read("agents/e2e-finding-verifier.md")
classifier = read("agents/e2e-failure-classifier.md")
reviewer = read("skills/e2e-reviewer/SKILL.md")
pw_dbg = read("skills/playwright-debugger/SKILL.md")
cy_dbg = read("skills/cypress-debugger/SKILL.md")

# SP1 — A1 regression guard: each agent must document that the caller passes an
# absolute source-of-truth path (CWD is the target project, not this repo).
for name, text in (("e2e-finding-verifier", verifier), ("e2e-failure-classifier", classifier)):
    if "absolute path" not in text or "working directory" not in text:
        errors.append(
            f"agents/{name}.md: must state the caller passes the absolute "
            "source-of-truth path (its working directory is the target project). "
            "Do not hardcode a repo-relative skills/... read target."
        )

# SP2 — delegating skills must actually hand the subagent that absolute path.
# Anchor the check to the delegation line itself (the line naming the agent),
# NOT the whole file — otherwise an unrelated 'absolute' elsewhere would keep the
# guard green after the delegation sentence drops the path contract (the A1 bug).
for rel, text, agent in (
    ("skills/e2e-reviewer/SKILL.md", reviewer, "e2e-finding-verifier"),
    ("skills/playwright-debugger/SKILL.md", pw_dbg, "e2e-failure-classifier"),
    ("skills/cypress-debugger/SKILL.md", cy_dbg, "e2e-failure-classifier"),
):
    delegation_lines = [ln for ln in text.splitlines() if agent in ln]
    if not delegation_lines:
        errors.append(f"{rel}: lost the {agent} delegation block")
    elif not any("absolute" in ln for ln in delegation_lines):
        errors.append(
            f"{rel}: the {agent} delegation line must pass the subagent an absolute "
            "source-of-truth path (the word 'absolute' is missing from the line that "
            "names the agent)."
        )

# SP3 — verdict vocabulary parity: the verifier's three verdicts must appear in
# BOTH the subagent and the e2e-reviewer inline fallback, so both paths agree.
verdicts = ("CONFIRMED", "FALSE-POSITIVE", "NEEDS-CONTEXT")
for verdict in verdicts:
    if verdict not in verifier:
        errors.append(f"agents/e2e-finding-verifier.md: missing verdict term {verdict}")
    if verdict not in reviewer:
        errors.append(
            f"skills/e2e-reviewer/SKILL.md: inline fallback missing verdict term "
            f"{verdict} (must match the subagent verdict set)"
        )

# SP3b — F1-vs-F7 is decided by the isolation probe, and a read-only classifier
# can never run it. The no-probe verdict term must therefore exist on every path
# that can return one, or the delegated path silently guesses F1 from the error
# text — which the debugger skills say is wrong about half the time.
# The bare token is not enough: both debugger skills use CANNOT_VERIFY elsewhere
# for proof labelling, so a token check stays green even if the F1/F7 rule itself
# is deleted. Require the rule, by the pair it names.
for label, text in (
    ("skills/playwright-debugger/SKILL.md", pw_dbg),
    ("skills/cypress-debugger/SKILL.md", cy_dbg),
):
    if "CANNOT_VERIFY" not in text or "between F1 and F7" not in text:
        errors.append(
            f"{label}: missing the CANNOT_VERIFY rule for F1 versus F7 when the "
            "isolation probe was not performed"
        )
# A delegated classifier needs the term twice: in the procedure, so it knows when
# the verdict applies, and in the output contract, so the verdict is legal to
# return. Either one alone lets the path fall back to guessing.
classifier_copies = [("agents/e2e-failure-classifier.md", classifier)]
codex_classifier = pathlib.Path(".codex/agents/e2e-failure-classifier.toml")
if codex_classifier.is_file():
    classifier_copies.append(
        (str(codex_classifier), codex_classifier.read_text(encoding="utf-8"))
    )
for label, text in classifier_copies:
    if text.count("CANNOT_VERIFY") < 2:
        errors.append(
            f"{label}: missing the CANNOT_VERIFY term in both the procedure and "
            "the output contract (F1/F7 has no probe on a read-only path)"
        )

# SP4 — F-code taxonomy frozen at F1–F15, shared by both debuggers and the
# classifier; nobody may invent F16+.
EXPECTED_FCODES = {f"F{i}" for i in range(1, 16)}
# A new code beyond F15 (F16–F99), by word boundary so it never matches inside a
# larger token. The freeze phrase "F16+" is stripped before probing.
NEW_FCODE = re.compile(r"\bF(?:1[6-9]|[2-9][0-9])\b")

# The two debugger SKILL.md files carry the canonical F1–F15 tables: the set of
# `| Fn |` table codes must be EXACTLY {F1..F15}. This catches BOTH a dropped code
# and an added F16+/F17 row — a bare "F16" substring check would miss both.
for rel, text in (
    ("skills/playwright-debugger/SKILL.md", pw_dbg),
    ("skills/cypress-debugger/SKILL.md", cy_dbg),
):
    table_codes = set(re.findall(r"\|\s*(F\d+)\s*\|", text))
    if table_codes != EXPECTED_FCODES:
        missing = sorted(EXPECTED_FCODES - table_codes, key=lambda c: int(c[1:]))
        extra = sorted(table_codes - EXPECTED_FCODES, key=lambda c: int(c[1:]))
        errors.append(
            f"{rel}: F-code table must be exactly F1–F15 "
            f"(missing={missing or '-'}, unexpected={extra or '-'})"
        )

# All three files (incl. the prose classifier that has no table) must reference
# the range endpoints by WORD BOUNDARY — so "F1" cannot vacuously match inside
# "F15" — and must contain no F16+ code, allowing only the freeze phrase.
for rel, text in (
    ("agents/e2e-failure-classifier.md", classifier),
    ("skills/playwright-debugger/SKILL.md", pw_dbg),
    ("skills/cypress-debugger/SKILL.md", cy_dbg),
):
    probe = text.replace("F16+", "")
    for code in ("F1", "F15"):
        if not re.search(rf"\b{code}\b", probe):
            errors.append(f"{rel}: F-code taxonomy must reference {code}")
    if NEW_FCODE.search(probe):
        errors.append(f"{rel}: F-codes are frozen at F1–F15; found a new F16+ code")

# SP5 — Codex/OMX-native TOML ports (optional third copy of each subagent
# contract). If present under .codex/agents/, they must NOT drift from the .md
# agents / inline fallback: same A1 absolute-path contract, same verdict set, same
# frozen F1–F15 taxonomy. Skipped silently when a port is absent (they are not
# required — but a shipped port that drifts is exactly what this guards).
for rel in (".codex/agents/e2e-finding-verifier.toml", ".codex/agents/e2e-failure-classifier.toml"):
    p = pathlib.Path(rel)
    if not p.is_file():
        continue
    text = p.read_text(encoding="utf-8")
    if "absolute" not in text.lower() or "working directory" not in text:
        errors.append(
            f"{rel}: must state the caller passes the absolute source-of-truth path "
            "(its working directory is the target project, not this repo)."
        )
    if rel.endswith("e2e-finding-verifier.toml"):
        for verdict in verdicts:
            if verdict not in text:
                errors.append(f"{rel}: missing verdict term {verdict} (must match the subagent verdict set)")
    if rel.endswith("e2e-failure-classifier.toml"):
        # allow both freeze phrasings ("F16+" and "F16 or higher")
        probe = text.replace("F16+", "").replace("F16 or higher", "")
        for code in ("F1", "F15"):
            if not re.search(rf"\b{code}\b", probe):
                errors.append(f"{rel}: F-code taxonomy must reference {code}")
        if NEW_FCODE.search(probe):
            errors.append(f"{rel}: F-codes are frozen at F1–F15; found a new F16+ code")

# SP6 — a skills-CLI install does not register custom TOMLs. Latest Codex can
# still preserve independent review through standard native roles, so named
# agents must be an optimization rather than the only delegation path.
if "native `verifier` role" not in reviewer or "named registration is an optimization" not in reviewer:
    errors.append(
        "skills/e2e-reviewer/SKILL.md: must fall back from the named agent to "
        "the native verifier role before the inline fallback"
    )
for rel, text in (
    ("skills/playwright-debugger/SKILL.md", pw_dbg),
    ("skills/cypress-debugger/SKILL.md", cy_dbg),
):
    if "native `debugger` role" not in text or "named registration is an optimization" not in text:
        errors.append(
            f"{rel}: must fall back from the named classifier to the native "
            "debugger role before the inline fallback"
        )

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "subagents and inline fallbacks share one verdict/taxonomy source of truth"
  else
    err "subagent parity check failed"
  fi
else
  warn "python3 not available; skipped subagent parity check"
fi

section "Markdown links"
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import pathlib
import re
import subprocess
import sys
from urllib.parse import unquote

def repo_files():
    try:
        out = subprocess.check_output(
            ['git', 'ls-files', '-co', '--exclude-standard', '--'],
            text=True,
        )
        return [pathlib.Path(line) for line in out.splitlines() if line]
    except Exception:
        return [p for p in pathlib.Path('.').rglob('*') if p.is_file()]

errors = []
link_re = re.compile(r"\[[^\]]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
for path in sorted(p for p in repo_files() if p.suffix == '.md'):
    if any(part in {'.git', '.sisyphus', 'testbed', 'node_modules'} for part in path.parts):
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    for match in link_re.finditer(text):
        raw = match.group(1)
        if raw.startswith(('#', 'http://', 'https://', 'mailto:')):
            continue
        target = raw.split('#', 1)[0]
        if not target:
            continue
        target_path = (path.parent / unquote(target)).resolve()
        try:
            target_path.relative_to(pathlib.Path('.').resolve())
        except ValueError:
            continue
        if not target_path.exists():
            errors.append(f"{path}: broken local link {raw}")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "local markdown links resolve"
  else
    err "broken local markdown links found"
  fi
else
  warn "python3 not available; skipped markdown link check"
fi

section "Docs orphan check"
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import pathlib
import re
import subprocess
import sys

def repo_files():
    try:
        out = subprocess.check_output(
            ['git', 'ls-files', '-co', '--exclude-standard', '--'],
            text=True,
        )
        return [pathlib.Path(line) for line in out.splitlines() if line]
    except Exception as exc:
        raise RuntimeError(f"git file enumeration failed: {exc}") from exc

docs_dir = pathlib.Path('docs')
if not docs_dir.is_dir():
    sys.exit(0)

# Files allowed to exist as references from CI scripts or other docs, not just README.
# Exclude test-parity.sh — it intentionally names docs files for drift smoke tests,
# which would otherwise mask real orphan detection (meta-circular).
ci_referenced_globs = ['scripts/**/*.sh', 'scripts/**/*.py']
excluded_paths = {'scripts/ci/test-parity.sh'}

all_repo_files = repo_files()
doc_files = sorted(p for p in all_repo_files if len(p.parts) > 1 and p.parts[0] == 'docs' and p.suffix == '.md')
if not doc_files:
    sys.exit(0)

readme_text = pathlib.Path('README.md').read_text(encoding='utf-8') if pathlib.Path('README.md').exists() else ''
ci_text_parts = []
for path in all_repo_files:
    if path.as_posix() in excluded_paths:
        continue
    if len(path.parts) > 1 and path.parts[0] == 'scripts' and path.suffix in {'.sh', '.py'}:
        ci_text_parts.append(path.read_text(encoding='utf-8'))
ci_text = '\n'.join(ci_text_parts)

errors = []
for doc in doc_files:
    rel = doc.as_posix()
    name = doc.name
    # A doc qualifies if README links to it OR a CI script names it
    in_readme = rel in readme_text or name in readme_text
    in_ci = rel in ci_text or name in ci_text
    if not (in_readme or in_ci):
        errors.append(f"{rel}: orphan — not linked from README.md or any scripts/")

if errors:
    for err in errors:
        print(err, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "every docs/ file is linked from README.md or referenced by CI"
  else
    err "orphan doc files found — link from README.md or remove"
  fi
else
  warn "python3 not available; skipped docs orphan check"
fi

section "README i18n parity"
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import collections
import hashlib
import pathlib
import re
import sys

canonical_path = pathlib.Path("README.md")
translations = tuple(map(pathlib.Path, ("README.ko.md", "README.ja.md", "README.zh-cn.md")))
try:
    canonical_bytes = canonical_path.read_bytes()
    canonical = canonical_bytes.decode("utf-8")
except (OSError, UnicodeError) as exc:
    print(f"README i18n parity: cannot read README.md: {exc}", file=sys.stderr)
    raise SystemExit(1)
canonical_digest = hashlib.sha256(canonical_bytes).hexdigest()
canonical_ack_re = re.compile(
    r"<!-- README-CANONICAL-REVISION: "
    r"sha256=([0-9a-f]{64}); "
    r"bytes=exact-README\.md-UTF-8; "
    r"translation-quality=not-attested -->"
)

command_re = re.compile(
    r"^(?:/plugin (?:marketplace add|install) |"
    r"codex plugin (?:marketplace add|add) |"
    r"npx --yes skills@[0-9]+\.[0-9]+\.[0-9]+ add |"
    r"git clone ).+$"
)
repo_url_re = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"(?:/[A-Za-z0-9_.#?=&/-]+)?"
)


def install_contract(text):
    commands = collections.Counter(
        line.strip()
        for line in text.splitlines()
        if command_re.fullmatch(line.strip())
    )
    repo_urls = collections.Counter(repo_url_re.findall(text))
    return commands, repo_urls


def check_manual_clone_contract(path, text, errors):
    required = (
        'git clone https://github.com/voidmatcha/e2e-skills.git '
        '"$HOME/.claude/e2e-skills"',
        'mkdir -p "$HOME/.claude/skills"',
        "for skill in playwright-test-generator e2e-reviewer "
        "playwright-debugger cypress-debugger; do",
        'ln -s "$HOME/.claude/e2e-skills/skills/$skill" '
        '"$HOME/.claude/skills/$skill"',
        "/skills",
    )
    if any(token not in text for token in required):
        errors.append(
            f"README i18n parity: {path} manual Claude Code clone must expose "
            "four direct per-skill roots and document /skills verification"
        )
    if "~/.claude/skills/e2e-skills" in text:
        errors.append(
            f"README i18n parity: {path} manual Claude Code clone uses an "
            "unsupported nested bundle path"
        )


def check_codex_install_and_delegation_contract(path, text, errors):
    codex_heading = "\n### Codex\n"
    start = text.find(codex_heading)
    if start < 0:
        errors.append(f"README i18n parity: {path} missing Codex install section")
        return
    end = text.find("\n### ", start + len(codex_heading))
    section = text[start:end if end >= 0 else len(text)]
    codex_only = (
        "npx --yes skills@1.5.21 add voidmatcha/e2e-skills "
        "--skill '*' -g -a codex"
    )
    combined = (
        "npx --yes skills@1.5.21 add voidmatcha/e2e-skills "
        "--skill '*' -g -a claude-code -a codex"
    )
    if codex_only not in section or combined in section:
        errors.append(
            f"README i18n parity: {path} Codex install must target only "
            "-a codex and disclose Claude Code separately"
        )
    delegation_tokens = (
        "`e2e-reviewer`",
        "`playwright-debugger`",
        "`cypress-debugger`",
        "`playwright-test-generator`",
        "V6",
        "`CANNOT_VERIFY`",
        "`PARTIAL/BLOCKED`",
    )
    missing = [token for token in delegation_tokens if token not in section]
    if missing:
        errors.append(
            f"README i18n parity: {path} Codex delegation limits missing "
            f"tokens {missing!r}"
        )


def taxonomy_contract(text):
    headings = list(re.finditer(r"^#### P([012])\b.*$", text, re.M))
    pattern_severity = {}
    duplicates = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end():end]
        for pattern_id in re.findall(r"^\| (3b|\d+) \|", section, re.M):
            if pattern_id in pattern_severity:
                duplicates.append(pattern_id)
            pattern_severity[pattern_id] = f"P{heading.group(1)}"
    f_codes = collections.Counter(
        int(code) for code in re.findall(r"^\| F(\d+) \|", text, re.M)
    )
    return pattern_severity, duplicates, f_codes


canonical_commands, canonical_urls = install_contract(canonical)
if not canonical_commands or not canonical_urls:
    print("README i18n parity: canonical install command/URL contract is empty", file=sys.stderr)
    raise SystemExit(1)
canonical_patterns, canonical_duplicates, canonical_f_codes = taxonomy_contract(canonical)
expected_pattern_ids = {
    "1", "2", "3", "3b", "4", "5", "6", "7", "8", "9", "10", "11",
    "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23",
}
expected_f_codes = collections.Counter({number: 1 for number in range(1, 16)})
if (
    set(canonical_patterns) != expected_pattern_ids
    or canonical_duplicates
    or canonical_f_codes != expected_f_codes
):
    print(
        "README i18n parity: canonical taxonomy contract is incomplete or duplicated",
        file=sys.stderr,
    )
    raise SystemExit(1)

errors = []
check_manual_clone_contract(canonical_path, canonical, errors)
check_codex_install_and_delegation_contract(canonical_path, canonical, errors)
contract_start = "<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->"
contract_end = "<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->"
contract_re = re.compile(
    re.escape(contract_start) + r"\n(.*?)\n" + re.escape(contract_end),
    re.S,
)
contract_hashes = {
    "README.md": "ac9a9be1d95d6519bb06901a8c29c997dfad01a03909fe890c28cc629ffd15da",
    "README.ko.md": "ab75ae3a16567155ae894b40ebcdc10fa55cfa2531238d6c1c54481b85fa0798",
    "README.ja.md": "53ba87e9d0211ebbd56d8ab6c86a587f5003be4167ca171e7fdfde9c37c4857f",
    "README.zh-cn.md": "5f1646eeff6d91174af04e396eabf2a4eb954bbe16b373f43c1fb6e70e89efb0",
}
contract_tokens = (
    "24",
    "P0/P1/P2",
    "scan.sh",
    "F1–F15",
    "--isolation-wrapper",
)
read_scope_start = "<!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->"
read_scope_end = "<!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->"
read_scope_re = re.compile(
    r"^> " + re.escape(read_scope_start) + r"\n"
    r"(.*?)"
    r"^> " + re.escape(read_scope_end),
    re.M | re.S,
)
read_scope_hashes = {
    "README.md": "9209cac05d579471fd256711cef1dbf6f76d65b8b562cf04ca187471a82d100c",
    "README.ko.md": "5afdc0fd243b7c36ff4bc4266e452918568e6c954257a910bfb73bff4db91290",
    "README.ja.md": "e3ff750d899a3d4d63f3df80c25330b1528e71c297c793ba05ecc22f0aefb55e",
    "README.zh-cn.md": "845d90bae16c9b33eba5de39b18c20a088c65fd8643cde55f1fa175b59c87c8f",
}


def check_protected_contract(path, text):
    matches = contract_re.findall(text)
    if len(matches) != 1:
        errors.append(
            f"README i18n parity: {path} missing or duplicated protected semantic contract"
        )
        return
    contract = matches[0].strip()
    missing = [token for token in contract_tokens if token not in contract]
    if missing:
        errors.append(
            f"README i18n parity: {path} protected semantic contract missing "
            f"tokens {missing!r}"
        )
        return
    digest = hashlib.sha256(contract.encode("utf-8")).hexdigest()
    if digest != contract_hashes[path.name]:
        errors.append(
            f"README i18n parity: {path} protected semantic contract changed; "
            "review the scope/safety claims and update its accepted digest"
        )


def check_scanner_read_scope_contract(path, text):
    matches = read_scope_re.findall(text)
    if len(matches) != 1:
        errors.append(
            f"README i18n parity: {path} missing or duplicated protected "
            "scanner read-scope contract"
        )
        return
    contract = "\n".join(
        re.sub(r"^> ?", "", line)
        for line in matches[0].strip().splitlines()
    ).strip()
    if "fixture/support" not in contract:
        errors.append(
            f"README i18n parity: {path} protected scanner read-scope contract "
            "missing fixture/support exception"
        )
        return
    digest = hashlib.sha256(contract.encode("utf-8")).hexdigest()
    if digest != read_scope_hashes[path.name]:
        errors.append(
            f"README i18n parity: {path} protected scanner read-scope contract "
            "changed; review the requested-path/containing-project exception "
            "and update its accepted digest"
        )


check_protected_contract(canonical_path, canonical)
check_scanner_read_scope_contract(canonical_path, canonical)
en_sections = len(re.findall(r"^## ", canonical, re.M))
en_fences = len(re.findall(r"^```", canonical, re.M))
for path in translations:
    if not path.is_file():
        errors.append(f"README i18n parity: translation missing: {path}")
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"README i18n parity: cannot read {path}: {exc}")
        continue
    check_manual_clone_contract(path, text, errors)
    check_codex_install_and_delegation_contract(path, text, errors)
    acknowledgements = canonical_ack_re.findall(text)
    if len(acknowledgements) != 1:
        errors.append(
            f"README i18n parity: {path} missing or duplicated canonical "
            "revision acknowledgement"
        )
    elif acknowledgements[0] != canonical_digest:
        errors.append(
            f"README i18n parity: {path} canonical revision acknowledgement is "
            "stale; review the translation against exact README.md bytes and "
            "update the digest (translation quality is not attested)"
        )
    sections = len(re.findall(r"^## ", text, re.M))
    fences = len(re.findall(r"^```", text, re.M))
    if sections != en_sections:
        errors.append(
            f"README i18n parity: {path} has {sections} '## ' sections, "
            f"README.md has {en_sections}"
        )
    if fences != en_fences:
        errors.append(
            f"README i18n parity: {path} has {fences} code fences, "
            f"README.md has {en_fences}"
        )
    if "docs/assets/hero.png" not in text:
        errors.append(f"README i18n parity: {path} missing hero image")
    if 'README.md">🇺🇸 English' not in text:
        errors.append(f"README i18n parity: {path} missing language switcher")
    commands, urls = install_contract(text)
    if commands != canonical_commands:
        errors.append(
            f"README i18n parity: {path} canonical install commands differ from README.md"
        )
    if urls != canonical_urls:
        errors.append(
            f"README i18n parity: {path} canonical repository URLs differ from README.md"
        )
    patterns, duplicates, f_codes = taxonomy_contract(text)
    if patterns != canonical_patterns or duplicates:
        errors.append(
            f"README i18n parity: {path} pattern ID/severity contract differs from README.md"
        )
    if f_codes != canonical_f_codes:
        errors.append(
            f"README i18n parity: {path} F1-F15 taxonomy contract differs from README.md"
        )
    check_protected_contract(path, text)
    check_scanner_read_scope_contract(path, text)

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    raise SystemExit(1)
PY
  then
    ok "README contracts and exact canonical-revision acknowledgements (translation quality not attested)"
  else
    err "README i18n parity failed"
  fi
else
  err "python3 unavailable; README i18n parity check did not run"
fi

section "Language"
if command -v python3 >/dev/null 2>&1; then
  language_hits=$(mktemp "${TMPDIR:-/tmp}/e2e-skills-language-hits.XXXXXX")
  language_errors=$(mktemp "${TMPDIR:-/tmp}/e2e-skills-language-errors.XXXXXX")
  if python3 - >"$language_hits" 2>"$language_errors" <<'PY'
import pathlib
import re
import subprocess
import sys

def repo_files():
    result = subprocess.run(
        ['git', 'ls-files', '-co', '--exclude-standard', '--'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"git file enumeration failed: {detail}")
    return [pathlib.Path(line) for line in result.stdout.splitlines() if line]

hangul = re.compile(r'[\uAC00-\uD7AF]')
# Sanctioned exception: language-switcher lines that link to README.<lang>.md
# translation files may carry Hangul. Matches both markdown links
# ([\uD55C\uAD6D\uC5B4](README.ko.md)) and centered HTML links
# (<a href="README.ko.md">\uD55C\uAD6D\uC5B4</a>).
switcher = re.compile(r'(?:\(|href=["\x27])README\.[a-z]{2}(?:-[a-z]{2,4})?\.md')
hits = []
for path in sorted(p for p in repo_files() if p.suffix == '.md'):
    if not (path.as_posix() == 'README.md' or path.parts[:1] in [('docs',), ('skills',)]):
        continue
    if '/evals/' in str(path):
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    for line in text.splitlines():
        if hangul.search(line) and not switcher.search(line):
            hits.append(str(path))
            break
print('\n'.join(hits))
PY
  then
    hangul_hits=$(cat "$language_hits")
    if [ -z "$hangul_hits" ]; then
      ok "public docs and skill docs are English-only"
    else
      err "Korean text found in public docs: $hangul_hits"
    fi
  else
    err "Language checker failed closed"
    [ "$QUIET" = "0" ] && sed 's/^/      /' "$language_errors" >&2
  fi
  rm -f "$language_hits" "$language_errors"
else
  err "python3 unavailable; language check did not run"
fi

echo ""
echo "========================================"
echo "  Review: $PASSED passed, $WARNINGS warnings, $ERRORS errors"
echo "========================================"

[ "$ERRORS" -gt 0 ] && exit 1
exit 0
