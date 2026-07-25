#!/usr/bin/env bash
# Automated convention review for e2e-skills.

set -uo pipefail

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || {
  echo "review.sh: cannot resolve repo root" >&2
  exit 1
}
cd "$REPO_ROOT" || {
  echo "review.sh: cannot cd to $REPO_ROOT" >&2
  exit 1
}

ERRORS=0
WARNINGS=0
PASSED=0

err() { echo "  [FAIL] $*" >&2; ERRORS=$((ERRORS + 1)); }
warn() { echo "  [WARN] $*" >&2; WARNINGS=$((WARNINGS + 1)); }
ok() { [ "$QUIET" = "1" ] || echo "  [OK] $*"; PASSED=$((PASSED + 1)); }
section() { [ "$QUIET" = "1" ] || { echo ""; echo "-- $* --"; }; }
repo_files() { git ls-files -co --exclude-standard -- "$@" 2>/dev/null; }

section "Eval metadata"
eval_log=$(mktemp "${TMPDIR:-/tmp}/e2e-skills-evals.XXXXXX")
if ./scripts/validate-evals.sh >"$eval_log" 2>&1; then
  total=$(grep -oE 'total: [0-9]+ eval\(s\)' "$eval_log" | tail -1 || true)
  ok "validate-evals.sh ${total:-passed}"
else
  err "validate-evals.sh failed"
  [ "$QUIET" = "0" ] && tail -20 "$eval_log" >&2
fi
rm -f "$eval_log"

if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import json
import pathlib
import sys

errors = []
seen = set()
for path in sorted(pathlib.Path('skills').glob('*/evals/evals.json')):
    data = json.loads(path.read_text(encoding='utf-8'))
    skill = path.parts[1]
    if data.get('skill_name') != skill:
        errors.append(f"{path}: skill_name must be {skill!r}")
    ids = []
    for entry in data.get('evals', []):
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
  ok "pre-push-security.sh skipped by E2E_SKILLS_SKIP_SECURITY=1"
else
  security_log=$(mktemp "${TMPDIR:-/tmp}/e2e-skills-security.XXXXXX")
  if bash scripts/ci/pre-push-security.sh --quiet >"$security_log" 2>&1; then
    ok "pre-push-security.sh clean"
  else
    err "pre-push-security.sh blockers found"
    [ "$QUIET" = "0" ] && cat "$security_log" >&2
  fi
  rm -f "$security_log"
fi

section "Public skill surface"
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import json
import pathlib
import re
import sys

sys.path.insert(0, 'scripts/ci/lib')
from validate_codex import collect_codex_errors

errors = []
skill_dirs = sorted(path for path in pathlib.Path('skills').iterdir() if path.is_dir())
expected = {path.name for path in skill_dirs}

plugin = json.loads(pathlib.Path('.claude-plugin/plugin.json').read_text())
codex_plugin = json.loads(pathlib.Path('.codex-plugin/plugin.json').read_text())
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
    elif plugin_version and version_match.group(1).strip() != plugin_version:
        errors.append(
            f"{skill_file}: metadata.version {version_match.group(1).strip()!r} "
            f"does not match plugin version {plugin_version!r}"
        )

if frontmatter_names != expected:
    errors.append(f"skills/*/SKILL.md names mismatch: {sorted(frontmatter_names)} != {sorted(expected)}")

for skill_dir in skill_dirs:
    manifest = skill_dir / 'agents' / 'openai.yaml'
    if not manifest.exists():
        errors.append(f"{manifest}: missing")
        continue
    text = manifest.read_text(encoding='utf-8')
    if not re.search(rf"^name:\s*{re.escape(skill_dir.name)}\s*$", text, re.M):
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
  warn "python3 not available; skipped public skill surface check"
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

errors = []

skill_text = pathlib.Path('skills/e2e-reviewer/SKILL.md').read_text(encoding='utf-8')
grep_text = pathlib.Path('skills/e2e-reviewer/references/grep-patterns.md').read_text(encoding='utf-8')
patref_text = pathlib.Path('skills/e2e-reviewer/references/pattern-reference.md').read_text(encoding='utf-8')
scan_text = pathlib.Path('skills/e2e-reviewer/scripts/scan.sh').read_text(encoding='utf-8')
docs_text = pathlib.Path('docs/e2e-test-smells.md').read_text(encoding='utf-8')
readme_text = pathlib.Path('README.md').read_text(encoding='utf-8')
plugin = json.loads(pathlib.Path('.claude-plugin/plugin.json').read_text(encoding='utf-8'))
market = json.loads(pathlib.Path('.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
codex_plugin = json.loads(pathlib.Path('.codex-plugin/plugin.json').read_text(encoding='utf-8'))

qr_match = re.search(r'## Quick Reference\s*\n(?:.*\n)*?((?:\|.*\n)+)', skill_text)
if not qr_match:
    print('e2e-reviewer/SKILL.md: could not locate Quick Reference table', file=sys.stderr)
    sys.exit(1)

qr_severity = {}
for row in qr_match.group(1).splitlines():
    m = re.match(r'\|\s*(\d+[a-z]?)\s*\|\s*[^|]+\|\s*(P[012](?:/P[012])?)\s*\|', row)
    if m:
        qr_severity[m.group(1)] = m.group(2)
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

# Check 5: severity-grouped pattern phrase parity (canonical source: .claude-plugin/plugin.json
# description -> marketplace.json / .codex-plugin. The e2e-reviewer SKILL.md uses a lean trigger
# description by design, so the 24-phrase catalog lives in the manifests, not the skill frontmatter.)
phrase_source = plugin.get('description', '')
sev_groups = {}
for m in re.finditer(r"P([012])\s+[a-z\-]+\s*\(([^)]*)\)", phrase_source):
    sev_groups[m.group(1)] = m.group(2)

if set(sev_groups) != {'0', '1', '2'}:
    errors.append('.claude-plugin/plugin.json description: could not extract P0/P1/P2 pattern groups')
else:
    def normalize(s):
        s = s.lower()
        s = re.sub(r'[^a-z0-9+]+', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    ordered_phrases = []
    for sev in ('0', '1', '2'):
        clean = re.sub(r'\([^)]*\)', '', sev_groups[sev])
        for phrase in clean.split(','):
            phrase = phrase.strip()
            if phrase:
                ordered_phrases.append(normalize(phrase))

    if len(ordered_phrases) != 24:
        errors.append(
            f".claude-plugin/plugin.json description: expected 24 patterns across P0/P1/P2, got {len(ordered_phrases)}"
        )

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
unsupported=$(
  while IFS= read -r path; do
    [ -f "$path" ] || continue
    grep -En 'Puppeteer|puppeteer' "$path" 2>/dev/null | sed "s|^|$path:|" || true
  done < <(repo_files README.md skills docs .claude-plugin .codex-plugin scripts) | \
    grep -vE '^docs/framework-scope\.md:|^scripts/ci/review\.sh:' || true
)
if [ -z "$unsupported" ]; then
  ok "no accidental Puppeteer support claims outside framework-scope.md"
else
  err "unsupported Puppeteer references found outside framework-scope.md"
  printf '%s\n' "$unsupported" | sed 's/^/      /' >&2
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
    except Exception:
        return [p for p in pathlib.Path('.').rglob('*') if p.is_file()]

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
        ci_text_parts.append(path.read_text(encoding='utf-8', errors='ignore'))
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
i18n_ok=1
en_sec=$(grep -c '^## ' README.md || true)
en_fence=$(grep -c '^```' README.md || true)
for f in README.ko.md README.ja.md README.zh-cn.md; do
  if [ ! -f "$f" ]; then
    err "README i18n parity: translation missing: $f"
    i18n_ok=0
    continue
  fi
  s=$(grep -c '^## ' "$f" || true)
  c=$(grep -c '^```' "$f" || true)
  [ "$s" = "$en_sec" ] || { err "README i18n parity: $f has $s '## ' sections, README.md has $en_sec"; i18n_ok=0; }
  [ "$c" = "$en_fence" ] || { err "README i18n parity: $f has $c code fences, README.md has $en_fence"; i18n_ok=0; }
  grep -q 'docs/assets/hero.png' "$f" || { err "README i18n parity: $f missing hero image"; i18n_ok=0; }
  grep -q 'README.md">🇺🇸 English' "$f" || { err "README i18n parity: $f missing language switcher"; i18n_ok=0; }
done
[ "$i18n_ok" = "1" ] && ok "README.md / ko / ja / zh-cn structural parity (sections, fences, hero, switcher)"

section "Language"
if command -v python3 >/dev/null 2>&1; then
  hangul_hits=$(python3 - <<'PY' 2>/dev/null || true
import pathlib
import re
import subprocess

def repo_files():
    try:
        out = subprocess.check_output(
            ['git', 'ls-files', '-co', '--exclude-standard', '--'],
            text=True,
        )
        return [pathlib.Path(line) for line in out.splitlines() if line]
    except Exception:
        return [p for p in pathlib.Path('.').rglob('*') if p.is_file()]

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
    if not path.exists():
        continue
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        if hangul.search(line) and not switcher.search(line):
            hits.append(str(path))
            break
print('\n'.join(hits))
PY
)
  if [ -z "$hangul_hits" ]; then
    ok "public docs and skill docs are English-only"
  else
    err "Korean text found in public docs: $hangul_hits"
  fi
else
  warn "python3 not available; skipped language check"
fi

echo ""
echo "========================================"
echo "  Review: $PASSED passed, $WARNINGS warnings, $ERRORS errors"
echo "========================================"

[ "$ERRORS" -gt 0 ] && exit 1
exit 0
