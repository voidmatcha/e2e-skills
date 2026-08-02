#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Executable guards for debugger report extraction and summary contracts."""

from __future__ import annotations

import ast
from contextlib import contextmanager
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import unicodedata
import warnings
import zipfile
# Resolve the temp root so mkdtemp never returns a symlinked path.
# macOS /tmp is a symlink to /private/tmp and the bundled launchers reject
# symlinked roots; hardcoding /private/tmp broke every non-macOS runner.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())


ROOT = Path(__file__).resolve().parents[2]
CYPRESS_SKILL = ROOT / "skills/cypress-debugger"
PLAYWRIGHT_SKILL = ROOT / "skills/playwright-debugger/SKILL.md"


def run_extractor(
    extractor: Path,
    report_root: Path | None,
    *reports: Path,
) -> subprocess.CompletedProcess[str]:
    command = ["/usr/bin/python3", str(extractor)]
    if report_root is not None:
        command.extend(["--report-root", str(report_root)])
    command.extend(str(report) for report in reports)
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )


def run_playwright_reader(
    reader: Path,
    mode: str,
    report_root: Path | None,
    artifact: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    command = ["/usr/bin/python3", str(reader), mode]
    if report_root is not None:
        command.extend(["--report-root", str(report_root)])
    command.append(str(artifact))
    command.extend(extra)
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )


def run_cypress_reader(
    reader: Path,
    mode: str,
    artifact_root: Path | None,
    artifact: Path,
) -> subprocess.CompletedProcess[str]:
    command = ["/usr/bin/python3", str(reader), mode]
    if artifact_root is not None:
        command.extend(["--artifact-root", str(artifact_root)])
    command.append(str(artifact))
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )


def assert_no_unguarded_npx(text: str, executable: str) -> None:
    unguarded = re.findall(
        rf"\bnpx\s+(?!--no-install(?:\s|$)){re.escape(executable)}\b",
        text,
    )
    assert not unguarded, f"unguarded npx {executable} may install dependencies"


def assert_artifact_reader_launcher_boundary() -> None:
    playwright_skill = ROOT / "skills/playwright-debugger"
    cases = (
        (
            playwright_skill / "scripts/run-artifact-reader.sh",
            playwright_skill / "evals/files/results-selector-timeout.json",
            "playwright-report/results.json",
            (),
            (
                "report",
                "--report-root",
                "playwright-report",
                "playwright-report/results.json",
            ),
        ),
        (
            CYPRESS_SKILL / "scripts/run-artifact-reader.sh",
            CYPRESS_SKILL / "evals/files/mochawesome-selector-timeout.json",
            "cypress/reports/mochawesome.json",
            (),
            (
                "mochawesome",
                "--artifact-root",
                "cypress/reports",
                "cypress/reports/mochawesome.json",
            ),
        ),
        (
            CYPRESS_SKILL / "scripts/run-artifact-reader.sh",
            CYPRESS_SKILL / "evals/files/junit-mixed-suites.xml",
            "cypress/reports/results.xml",
            ("--reader", "extract-junit-failures.py"),
            (
                "--report-root",
                "cypress/reports",
                "cypress/reports/results.xml",
            ),
        ),
    )
    for launcher, fixture, artifact_relative, launcher_options, reader_args in cases:
        launcher_text = launcher.read_text(encoding="utf-8")
        assert launcher.is_file() and os.access(launcher, os.X_OK)
        assert "exec /usr/bin/env -i" in launcher_text
        assert '"$interpreter" -I -B "$reader"' in launcher_text
        assert "/usr/bin/python3" in launcher_text
        assert "is_root_owned_system_path" in launcher_text
        assert '"$project_root"/*' in launcher_text
        # PATH must play no part in choosing the interpreter. It may now appear
        # further down as an explicitly allowlisted forwarded value for the
        # publisher, so pin the ban to the selection region itself.
        selection_region = launcher_text[
            launcher_text.index("for fixed_candidate in") :
            launcher_text.index('[ -n "$interpreter" ]')
        ]
        assert "PATH" not in selection_region, launcher
        # A reader invocation forwards nothing at all.
        assert "read-playwright-artifact.py) pass_env_allowlist=''" in launcher_text or (
            "read-cypress-artifact.py|extract-junit-failures.py) pass_env_allowlist=''"
            in launcher_text
        ), launcher

        with tempfile.TemporaryDirectory(
            prefix="e2e-hostile-python-boundary-",
        ) as temp_dir:
            project = Path(temp_dir) / "project"
            hostile_bin = project / "bin"
            hostile_package = project / "python-injection"
            hostile_bin.mkdir(parents=True)
            hostile_package.mkdir()
            artifact = project / artifact_relative
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(fixture.read_bytes())
            path_marker = project / "path-python-executed"
            injection_marker = project / "python-injection-loaded"
            hostile_python = hostile_bin / "python3"
            hostile_python.write_text(
                "#!/bin/sh\n"
                f"/usr/bin/touch {path_marker}\n"
                "exit 91\n",
                encoding="utf-8",
            )
            hostile_python.chmod(0o755)
            (hostile_package / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(injection_marker)!r}).touch()\n",
                encoding="utf-8",
            )
            hostile_env = {
                "PATH": str(hostile_bin),
                "PYTHONHOME": str(project / "fake-home"),
                "PYTHONPATH": str(hostile_package),
                "PYTHONSTARTUP": str(hostile_package / "sitecustomize.py"),
                "PYTHONINSPECT": "1",
            }
            result = subprocess.run(
                [
                    str(launcher),
                    "--project-root",
                    str(project),
                    *launcher_options,
                    "--",
                    *reader_args,
                ],
                cwd=project,
                env=hostile_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip(), "bundled reader produced no output"
            assert not path_marker.exists(), "launcher used hostile PATH python"
            assert not injection_marker.exists(), "Python injection environment survived"

            project_link = Path(temp_dir) / "project-link"
            project_link.symlink_to(project, target_is_directory=True)
            rejected = subprocess.run(
                [
                    str(launcher),
                    "--project-root",
                    str(project_link),
                    *launcher_options,
                    "--",
                    *reader_args,
                ],
                cwd=project,
                env=hostile_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
            assert rejected.returncode != 0
            assert "not a symlink" in rejected.stderr

            project_skill_scripts = project / "target-controlled-skill/scripts"
            project_skill_scripts.mkdir(parents=True)
            project_launcher = project_skill_scripts / launcher.name
            project_launcher.write_bytes(launcher.read_bytes())
            project_launcher.chmod(0o755)
            if launcher_options:
                project_reader_name = launcher_options[1]
            elif "playwright" in str(launcher):
                project_reader_name = "read-playwright-artifact.py"
            else:
                project_reader_name = "read-cypress-artifact.py"
            source_reader = launcher.parent / project_reader_name
            (project_skill_scripts / project_reader_name).write_bytes(
                source_reader.read_bytes()
            )
            for untrusted_launcher in (
                project_launcher,
                Path(temp_dir) / "launcher-physical-alias",
            ):
                if untrusted_launcher != project_launcher:
                    untrusted_launcher.symlink_to(project_launcher)
                inside_project = subprocess.run(
                    [
                        str(untrusted_launcher),
                        "--project-root",
                        str(project),
                        *launcher_options,
                        "--",
                        *reader_args,
                    ],
                    cwd=project,
                    env=hostile_env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=20,
                    check=False,
                )
                assert inside_project.returncode != 0
                assert "launcher resolves inside the target project" in (
                    inside_project.stderr
                )


def adversarial_credentials(limit: int) -> tuple[str, tuple[str, ...]]:
    secrets = (
        "BOUNDARY_CREDENTIAL_LEAK",
        "BEARER_CREDENTIAL_LEAK",
        "BASIC_CREDENTIAL_LEAK",
        "COOKIE_CREDENTIAL_LEAK",
        "PASSWORD_CREDENTIAL_LEAK",
        "SECRET_CREDENTIAL_LEAK",
        "APIKEY_CREDENTIAL_LEAK",
        "URL_USER_CREDENTIAL_LEAK",
        "URL_PASSWORD_CREDENTIAL_LEAK",
        "QUERY_CREDENTIAL_LEAK",
    )
    prefix = "\n".join(
        (
            f"Authorization: Bearer {secrets[1]}",
            f"Proxy-Authorization: Basic {secrets[2]}",
            f"Cookie: session={secrets[3]}; preference=dark",
            f"password={secrets[4]}",
            f"client_secret={secrets[5]}",
            f"api key={secrets[6]}",
            (
                "https://"
                f"{secrets[7]}:{secrets[8]}@example.test/private"
                f"?token={secrets[9]}"
            ),
        )
    )
    padding = "x" * max(0, limit - len(prefix) - 60)
    # The tail marker proves the reader emits the END of a payload sized against
    # its byte limit -- that redaction never truncates. It sits on its OWN line
    # because the assignment value extent now runs to the end of the line for
    # every separator, so anything sharing a line with `token=<secret>` is
    # redacted with it. That is the documented cost of closing multi-word
    # secrets (`PASSWORD=correct horse battery staple`), not a truncation: put
    # the marker back on the credential's line and this fixture would only be
    # re-asserting the whitespace-terminated extent that leaked.
    text = (
        f"{prefix}\n{padding} token={secrets[0] * 20}\n"
        "redaction-tail-marker"
    )
    return text, secrets


def assert_credentials_redacted(
    output: str,
    secrets: tuple[str, ...],
) -> None:
    assert "[REDACTED]" in output
    assert "redaction-tail-marker" in output
    for secret in secrets:
        assert secret not in output, secret


PLAYWRIGHT_SKILL_DIR = ROOT / "skills/playwright-debugger"
CYPRESS_SKILL_DIR = ROOT / "skills/cypress-debugger"
PLAYWRIGHT_READER = PLAYWRIGHT_SKILL_DIR / "scripts/read-playwright-artifact.py"
CYPRESS_READER = CYPRESS_SKILL_DIR / "scripts/read-cypress-artifact.py"
RESIDUAL_MODULE = PLAYWRIGHT_SKILL_DIR / "scripts/residual_credentials.py"
CYPRESS_RESIDUAL_MODULE = CYPRESS_SKILL_DIR / "scripts/residual_credentials.py"
CYPRESS_REDACTOR = CYPRESS_SKILL_DIR / "scripts/redact_artifact.py"

# `scripts/ci/lib/scan-secrets.py` scans every shipped text file for exactly
# these shapes and has no per-line allowlist, so the fixtures are assembled at
# runtime. Splitting each prefix from its body keeps that gate meaningful
# instead of teaching it to ignore this file.
GITHUB_PAT = "ghp_" + "16C7e42F292c6912E7710c838347Ae178B4a"
GITHUB_OAUTH_TOKEN = "gho_" + "16C7e42F292c6912E7710c838347Ae178B4a"
AWS_ACCESS_KEY_ID = "AKIA" + "IOSFODNN7EXAMPLE"
AWS_SESSION_KEY_ID = "ASIA" + "Y34FZKBOKMUTVV7A"
SLACK_BOT_TOKEN = "xoxb-" + "2451234567-2451234599-AbCdEfGhIjKlMnOpQrStUvWx"
GOOGLE_API_KEY = "AIza" + "SyD-1234567890abcdefghijklmnopqrstuv"
PEM_BEGIN = "-----BEGIN RSA PRIVATE" + " KEY-----"
PEM_END = "-----END RSA PRIVATE" + " KEY-----"
PEM_BODY = "MIIEowIBAAKCAQEAx7Ke9dQm2vN0pLrTgYhZ8cWfJqB3sVnE5tRuIoPaKdLmXcVb"
STRIPE_LIVE_KEY = "sk_live_" + "51H8abcDEFghiJKLmnoPQRstu"
STRIPE_TEST_KEY = "sk_test_" + "51H8abcDEFghiJKLmnoPQRstuVWXyz0123"

# Live credential shapes that carry no keyword at all. Every keyword-anchored
# detector is blind to these by construction, so they are the regression corpus
# for the shape table.
KEYWORD_FREE_CREDENTIAL_SHAPES = (
    (
        "pem",
        f"Error: tls handshake failed\n{PEM_BEGIN}\n{PEM_BODY}\n{PEM_END}",
        PEM_BODY,
    ),
    (
        "aws",
        f"Error: upload failed for {AWS_ACCESS_KEY_ID} in us-east-1",
        AWS_ACCESS_KEY_ID,
    ),
    (
        "aws-session",
        f"Error: assume-role returned {AWS_SESSION_KEY_ID}",
        AWS_SESSION_KEY_ID,
    ),
    (
        "slack",
        f"Error: notify failed {SLACK_BOT_TOKEN}",
        SLACK_BOT_TOKEN,
    ),
    (
        "jwt",
        "Error: assertion failed eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
    ),
    (
        "github",
        f"Error: clone failed {GITHUB_OAUTH_TOKEN}",
        GITHUB_OAUTH_TOKEN,
    ),
    (
        "stripe",
        f"Error: charge failed {STRIPE_TEST_KEY}",
        STRIPE_TEST_KEY,
    ),
    (
        "google",
        f"Error: maps init {GOOGLE_API_KEY}",
        GOOGLE_API_KEY,
    ),
)

# Env-var-style names: `\b` never matches inside them because underscore is a
# word character, which is exactly the blind spot the readers used to share.
ENV_VAR_STYLE_CREDENTIALS = (
    (f"GITHUB_TOKEN={GITHUB_PAT}", GITHUB_PAT),
    ("AUTH_TOKEN=liveAuthTokenValue", "liveAuthTokenValue"),
    ("X_API_KEY=liveApiKeyValue", "liveApiKeyValue"),
    ("id_token=liveIdTokenValue", "liveIdTokenValue"),
    ("MY_CLIENT_SECRET=liveClientSecretValue", "liveClientSecretValue"),
    ('{"x_api_key":"liveJsonApiKeyValue"}', "liveJsonApiKeyValue"),
    ('headers: {"cookie":"sid=liveCookieValue"}', "liveCookieValue"),
)

# Realistic Playwright/Cypress artifact text that carries no credential. These
# readers exist to make failures debuggable, so a detector that trips on
# selectors, stack frames, paths, UUIDs, base64 screenshots, or documentation
# placeholders would be worse than the leak it prevents.
BENIGN_ARTIFACT_TEXT = (
    "Error: Timed out 5000ms waiting for "
    "expect(locator).toBeVisible()\n"
    "Locator: getByRole('button', { name: 'Sign in' })\n"
    "Expected: visible\nReceived: hidden",
    "    at Object.<anonymous> "
    "(/Users/example/app/tests/e2e/login.spec.ts:42:18)\n"
    "    at processTicksAndRejections "
    "(node:internal/process/task_queues:95:5)",
    "cy.get('[data-testid=\"password-input\"]').should('be.visible')",
    "await page.getByLabel('Password').fill(process.env.PASSWORD)",
    "AssertionError: expected 'token' to equal 'refresh'",
    "attachment {\"name\":\"screenshot\",\"contentType\":\"image/png\","
    "\"base64\":\"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42"
    "mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==\"}",
    "test c17d2e3f-1111-2222-3333-444455556666 retried 2 times",
    "Set the token first: export GITHUB_TOKEN=your-token-here",
    "config { apiKey: '<YOUR_API_KEY>' }",
    "Authorization header must be present on every request",
    "Cookie banner did not appear within 3000ms",
    "trace playwright-report/data/3f2a-trace.zip (1.2 MiB)",
    "webpack://app/./cypress/e2e/checkout.cy.ts:4:7",
    "npm ERR! code ELIFECYCLE\nnpm ERR! errno 1",
    "Element is not visible: <input type=\"password\" name=\"password\"/>",
    # Widening `=` to `=>` must not swallow arrow functions. This one names a
    # sensitive word on the left of the arrow, which is exactly the shape the
    # separator change could have mangled into unreadable output.
    "const submit = () => page.getByLabel('Password').fill(pw)",
    "await expect(page.getByTestId('signature-pad')).toBeVisible()",
    "TypeError: credentials is not a function\n"
    "    at login (/app/tests/e2e/support/auth.ts:12:9)",
)

# Assignment shapes that were emitted verbatim at exit 0 before the gate became
# a marker invariant. Every one was reproduced leaking against the previous
# design; the separator families and the substring-keyword families are kept
# apart so a narrowing shows up as a named failure rather than a count change.
MUST_CLOSE_ASSIGNMENT_LEAKS = (
    ("equality-triple", "password === {secret}"),
    ("equality-double", "password == {secret}"),
    ("equality-triple-client-secret", "client_secret === {secret}"),
    ("equality-triple-env-token", "TOKEN === {secret}"),
    ("equality-inside-expect", "expect(password === '{secret}').to.be.true"),
    ("substring-suffix", "passwordConfirm={secret}"),
    ("substring-infix", "api_key_v2={secret}"),
    ("substring-env-suffix", "AUTH_SECRET={secret}"),
    ("thin-arrow", "password -> {secret}"),
    ("plus-equals", "password += {secret}"),
    ("pipe-equals", "password |= {secret}"),
    ("walrus", "password := {secret}"),
    ("passphrase", "passphrase={secret}"),
    ("quoted-subscript-pass", "user['pass']={secret}"),
    # The compound-assignment family. `-=` was the one ECMAScript punctuator
    # containing `=` that the separator alphabet was missing, and it was
    # reachable because the key window could absorb its `-` head: the site
    # parsed as key `password -` + separator `=`, and the keyword test then
    # rejected `password -` because the run against the separator was `-`.
    ("minus-equals", "password -= {secret}"),
    ("minus-equals-header-key", "X-API-KEY -= {secret}"),
    ("minus-equals-subscript", "user['pass'] -= {secret}"),
    # A stray hyphen between key and separator: not the head of any token in
    # the alphabet, so it belongs to neither side.
    ("stray-hyphen-before-equals", "password - = {secret}"),
    # `=-` is `=` followed by a unary minus on the value. The whitespace-
    # terminated value extent stopped on the minus and emitted
    # `password=[REDACTED] {secret}`.
    ("equals-unary-minus", "password =- {secret}"),
    # Relational operators spelled with an explicit `=`.
    ("less-equals", "password <= {secret}"),
    ("greater-equals", "password >= {secret}"),
    # Multi-word values. The equals branch used to stop at the first space, so
    # a passphrase kept everything after its first word while the identical
    # colon spelling was fully closed.
    ("multiword-passphrase", "PASSWORD=correct horse {secret} staple"),
    ("auth-scheme-then-credential", "AUTHORIZATION=Token {secret}"),
    ("cookie-pair-value", "Cookie=sid={secret}; auth=session"),
    # Not an assignment: the HTTP auth-scheme path. `www-authenticate` is not a
    # header keyword and `WWW-Authenticate` names no assignment keyword, so
    # AUTH_SCHEME_NAMES is the only thing standing between this line and
    # stdout.
    ("auth-scheme-negotiate", "WWW-Authenticate: Negotiate {secret}"),
    # Cross-line values. The redactor used to refuse to cross a newline, so a
    # keyword ending a line got a marker minted out of an empty value, that
    # marker satisfied the gate, and the secret one line down was emitted at
    # exit 0. The nested spelling is the one that also needs the clamp: without
    # it `credentials:` swallows the whole `password:` line, that site is never
    # visited, and the secret one line further down still ships.
    ("newline-split-colon", "password:\n    {secret}"),
    ("newline-split-nested", "credentials:\n  password:\n    {secret}"),
    ("newline-split-blank-line", "password:\n\n    {secret}"),
    ("newline-split-equals", "PASSWORD =\n{secret}"),
    ("newline-split-tab-indent", "secret:\n\t{secret}"),
    ("newline-split-yaml-block", "password: |\n    {secret}"),
    ("newline-split-yaml-folded-chomped", "password: >-\n    {secret}"),
    # Unicode renderings of the separator alphabet (closure rule layer 3).
    # None of these contain an ASCII separator character at all.
    ("homoglyph-fullwidth-equals", "password\uff1d{secret}"),
    ("homoglyph-fullwidth-colon", "password\uff1a{secret}"),
    ("homoglyph-small-equals", "password\ufe66{secret}"),
    ("homoglyph-modifier-equals", "password\ua78a{secret}"),
    ("homoglyph-ratio-colon", "password\u2236{secret}"),
    ("homoglyph-colon-equals", "password\u2254{secret}"),
    ("homoglyph-double-equals", "password\u2a75{secret}"),
    ("homoglyph-identical-to", "password\u2261{secret}"),
    ("homoglyph-rightwards-arrow", "password\u2192{secret}"),
    # Per-character closure: a two-character ASCII token spelled entirely in
    # renderings, which a token-level homoglyph list would have missed.
    ("homoglyph-fullwidth-double-equals", "password\uff1d\uff1d{secret}"),
    ("homoglyph-fullwidth-arrow", "password\uff1d\uff1e{secret}"),
    # Assignment operators from the languages that are not JavaScript. The
    # first three contain no `=` at all, so "every ECMAScript punctuator that
    # contains `=`" could never have reached them.
    ("non-js-left-arrow", "password <- {secret}"),
    ("non-js-super-assign", "password <<- {secret}"),
    ("non-js-pipeline", "password |> {secret}"),
    ("non-js-make-conditional", "password ?= {secret}"),
    ("non-js-python-floordiv", "password //= {secret}"),
    ("non-js-python-matmul", "password @= {secret}"),
    ("non-js-lua-compare", "password ~= {secret}"),
    # Key tails deeper than two closing characters, and closers the class did
    # not hold at all.
    ("key-tail-three-closers", 'obj[cfg["password"]]={secret}'),
    ("key-tail-four-closers", 'obj[a[cfg["password"]]]={secret}'),
    ("key-tail-call-result", 'get("password")={secret}'),
    ("key-tail-template-subscript", "cfg[`password`]={secret}"),
    ("key-tail-brace-close", "${{password}}={secret}"),
)
MUST_CLOSE_SECRET = "hunter2LiveProdPassword"

# Artifact text that carries no credential but sits next to a sensitivity
# keyword. Under the current policy their VALUES may be redacted -- that is the
# intended trade -- but none of them may fail the read closed. Availability is
# the bar these defend: the readers must keep exiting 0 with output.
AVAILABILITY_CORPUS = (
    "TypeError: Failed to execute 'fetch' on 'Window': credentials: "
    "'include' is not a valid enum value",
    "const authorization = () => next()",
    "Cookie=abc def",
    "password: 'hunter2' was rejected by the form",
    "token: 'abc' expired at 10:00",
    "Error: expect(locator).toBeVisible() failed / "
    "Locator: getByRole('button', { name: 'Sign in' })",
    "const submit = () => page.getByLabel('Password').fill(pw)",
    "await page.locator('[data-testid=\"password-input\"]').fill(pw)",
    "webpack://app/./cypress/e2e/checkout.cy.ts:4:7",
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
    "test c17d2e3f-1111-2222-3333-444455556666 retried 2 times",
    "commit 4f9a1c2b8e7d6f5a4b3c2d1e0f9a8b7c6d5e4f3a",
    "Timed out 5000ms exceeded",
    # A bare keyword with no value at all. The redactor still has to write the
    # marker, or the gate sees a separator with nothing behind it and fails a
    # perfectly ordinary line closed.
    "Enter your password:",
    "Cookie:",
    # Measured cost of putting bare `pass` in the keyword list: runner summary
    # prose loses its counts. That is survivable; failing closed is not.
    "  Passing:      2",
    "passes=5 failures=1",
    # A hyphen with whitespace on both sides is loose text, not an operator
    # head -- but only when a separator actually follows it. These must find no
    # site at all.
    "password - see the migration guide for the new flow",
    "| password | - | required |",
    # Adjacent hyphens are an HTML comment marker, not a stray hyphen plus an
    # arrow. The gap deliberately requires whitespace after the hyphen so this
    # keeps its `-->`.
    "<!-- password --> was rendered by the template",
    # The relational separators, next to a keyword and away from one.
    "expect(retries <= 3).toBe(true)",
    "const cls = r.pass_rate >= 0.8 ? 'good' : 'bad'",
    # The documented cost of one value extent for every separator: an
    # unrelated assignment sharing the line with a credential one is redacted
    # too. Survivable; failing closed is not.
    "TOKEN=abc PATH=/usr/bin",
    # A second assignment site after a wide value. `auth` is not a sensitivity
    # keyword (`authorization` is), so this one is left alone by design.
    "Cookie=sid=abc123; auth=session",
    # An auth scheme name with no credential behind it.
    "WWW-Authenticate: Negotiate",
    # Redaction has to be a FIXED POINT, not merely safe: both readers run it
    # twice and refuse to emit anything if the second pass moves. This line is
    # the shape that breaks that -- the assignment value extent stops at the
    # comma, and QUERY_ASSIGNMENT then rewrites the `?k=v` pair with a value
    # class that swallows the comma, so a second pass would reach further than
    # the first. Failing this corpus entry means a real artifact string exits
    # non-zero with no output at all.
    "target /checkout?access_token=abc, browser_click, and browser_snapshot",
    # The cost side of the cross-line extent. Redacting the continuation line
    # is the intended trade; failing the read closed on any of these is not.
    "credentials:\n  'include' is not a valid enum value",
    "Expected password:\n    at login (/app/tests/e2e/support/auth.ts:12:9)",
    "const authorization =\n  () => next()",
    # A keyword-separator that ends the whole string, and one followed only by
    # blank lines: there is no continuation to claim and no marker to mint from
    # anything, and the read still has to come back.
    "password:",
    "token:\n",
    "secret:\n\n\n",
    "config:\n  password: |\n",
    # Unicode renderings in ordinary prose. Widening the alphabet widens what
    # gets redacted; it must never widen what fails closed.
    "expect(retries \u2264 3).toBe(true)",
    "step 1 \u2192 step 2 \u2192 done",
    "\u30d1\u30b9\u30ef\u30fc\u30c9\uff1a\u672a\u5165\u529b",
    # Closer runs with no separator behind them. Widening the key tail to
    # eight closers must not invent a site where the artifact has none.
    'await expect(page.locator(obj[cfg["password"]])).toBeVisible()',
    "cy.get('[data-testid=\"password-input\"]').should('be.visible')",
    "const [password] = useState('')",
    # Non-JavaScript operators as ordinary log text.
    "value <- readline()",
    "pipeline: token |> String.trim()",
)

# Fragments that must survive redaction, otherwise the reader has stopped being
# useful for diagnosis.
BENIGN_FRAGMENTS_THAT_MUST_SURVIVE = (
    "getByRole('button', { name: 'Sign in' })",
    "login.spec.ts:42:18",
    "iVBORw0KGgo",
    "c17d2e3f-1111-2222-3333-444455556666",
    "Timed out 5000ms",
    "webpack://app/./cypress/e2e/checkout.cy.ts:4:7",
    "ELIFECYCLE",
    "const submit = () => page.getByLabel('Password').fill(pw)",
    "getByTestId('signature-pad')",
    "auth.ts:12:9",
)


def load_contract_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def playwright_report_with_message(root: Path, message: str) -> str:
    return json.dumps(
        {
            "config": {"rootDir": str(root)},
            "stats": {
                "expected": 0,
                "skipped": 0,
                "unexpected": 1,
                "flaky": 0,
            },
            "suites": [
                {
                    "title": "login.spec.ts",
                    "file": "login.spec.ts",
                    "specs": [
                        {
                            "title": "login works",
                            "ok": False,
                            "file": "login.spec.ts",
                            "line": 3,
                            "column": 1,
                            "tests": [
                                {
                                    "projectName": "chromium",
                                    "status": "unexpected",
                                    "results": [
                                        {
                                            "status": "failed",
                                            "duration": 12,
                                            "error": {"message": message},
                                            "errors": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "suites": [],
                }
            ],
        }
    )


def mochawesome_report_with_message(message: str) -> str:
    test_uuid = "c17d2e3f-1111-2222-3333-444455556666"
    return json.dumps(
        {
            "stats": {
                "suites": 1,
                "tests": 1,
                "passes": 0,
                "pending": 0,
                "failures": 1,
                "skipped": 0,
                "start": "2026-06-26T10:00:00.000Z",
                "end": "2026-06-26T10:00:12.000Z",
                "duration": 12000,
            },
            "results": [
                {
                    "uuid": "0f4a2b1c-1111-2222-3333-444455556666",
                    "title": "",
                    "fullFile": "cypress/e2e/checkout.cy.ts",
                    "file": "cypress/e2e/checkout.cy.ts",
                    "suites": [
                        {
                            "uuid": "7a8b9c0d-1111-2222-3333-444455556666",
                            "title": "Checkout flow",
                            "fullFile": "cypress/e2e/checkout.cy.ts",
                            "tests": [
                                {
                                    "title": "submits the order",
                                    "fullTitle": "Checkout flow submits it",
                                    "duration": 4102,
                                    "state": "failed",
                                    "pass": False,
                                    "fail": True,
                                    "pending": False,
                                    "skipped": False,
                                    "uuid": test_uuid,
                                    "code": "cy.visit('/checkout');",
                                    "err": {
                                        "message": message,
                                        "estack": f"CypressError: {message}",
                                    },
                                }
                            ],
                            "suites": [],
                            "passes": [],
                            "failures": [test_uuid],
                            "pending": [],
                            "skipped": [],
                        }
                    ],
                    "tests": [],
                    "passes": [],
                    "failures": [],
                    "pending": [],
                    "skipped": [],
                }
            ],
        }
    )


def read_both_readers(temp: Path, message: str) -> tuple:
    """Run the same failure message through both bundled readers."""
    playwright_report = temp / "results.json"
    playwright_report.write_text(
        playwright_report_with_message(temp, message),
        encoding="utf-8",
    )
    cypress_report = temp / "mochawesome.json"
    cypress_report.write_text(
        mochawesome_report_with_message(message),
        encoding="utf-8",
    )
    return (
        run_playwright_reader(
            PLAYWRIGHT_READER,
            "report",
            temp,
            playwright_report,
        ),
        run_cypress_reader(
            CYPRESS_READER,
            "mochawesome",
            temp,
            cypress_report,
        ),
    )


def assert_shared_residual_module_is_single_source_of_truth() -> None:
    """Hole 5 (structure): one detector, imported by both readers."""
    playwright_copy = RESIDUAL_MODULE.read_bytes()
    cypress_copy = CYPRESS_RESIDUAL_MODULE.read_bytes()
    assert playwright_copy == cypress_copy, (
        "the two residual_credentials.py copies have drifted; each debugger "
        "skill installs on its own, so they must stay byte-identical"
    )

    playwright_source = PLAYWRIGHT_READER.read_text(encoding="utf-8")
    cypress_redactor_source = CYPRESS_REDACTOR.read_text(encoding="utf-8")
    for source in (playwright_source, cypress_redactor_source):
        assert "from residual_credentials import" in source
    # The Cypress emission path must call the gate, not merely import it.
    assert (
        "structure_has_residual_credential(sanitized)"
        in cypress_redactor_source
    )
    # Neither reader forks the auth-scheme list either: the gate's
    # RESIDUAL_AUTH_VALUE and both readers' AUTH_SCHEME are built from the same
    # AUTH_SCHEME_NAMES string, so a scheme the gate checks is always a scheme
    # some redactor rewrites.
    for source in (playwright_source, cypress_redactor_source):
        assert "AUTH_SCHEME_NAMES" in source, (
            "a reader hard-codes its own HTTP auth scheme list; the gate can "
            "then recognise a scheme no redactor rewrites and fail an "
            "ordinary line closed"
        )

    # Neither reader may re-fork the patterns the shared module owns.
    for source in (playwright_source, cypress_redactor_source):
        for forked in (
            "RESIDUAL_ASSIGNMENT_SITE = re.compile",
            "REDACTOR_ASSIGNMENT_SITE = re.compile",
            "COLON_VALUE = re.compile",
            "OTHER_VALUE = re.compile",
            "ASSIGNMENT_VALUE = re.compile",
            # A hard-coded scheme alternation is the readable form of forking
            # AUTH_SCHEME_NAMES: importing the constant and then ignoring it
            # leaves the import in place, so the import alone proves nothing.
            "bearer|basic",
            "SAFE_CREDENTIAL_VALUE = re.compile",
        ):
            assert forked not in source, forked

    residual = load_contract_module(
        "residual_credentials_contract",
        RESIDUAL_MODULE,
    )
    # The gate has to be reachable without a redactor: it is a backstop, not a
    # second opinion from the same code.
    assert residual.has_residual_credential("token=liveTokenValue")
    assert not residual.has_residual_credential("token=[REDACTED]")


# The separator floor the design fixes for the gate. This literal lives in the
# test on purpose: it is the external contract, so deleting a separator from
# the module cannot quietly delete the expectation with it.
REQUIRED_GATE_SEPARATORS = (
    ":",
    "=",
    "=>",
    "==",
    "===",
    "->",
    "+=",
    "-=",
    "|=",
    ":=",
    "<=",
    ">=",
)
# Key spellings the gate must recognise around a separator. `[` / `'` forms are
# the bracketed and quoted key tails.
REQUIRED_GATE_KEY_FORMS = (
    "password",
    "user[password]",
    "user['password']",
    'headers["password"]',
    # Hyphenated and space-separated header spellings, which is where the key
    # window has to stop absorbing an operator head without losing `api key`.
    "X-API-KEY",
    "api key",
)
# Spellings of the gap between key and separator. The bare form is how env and
# code text writes it, the spaced form is how prose and log lines do, and the
# stray-hyphen form is the one that used to be swallowed into the key window.
# Every token in the alphabet has to close under all three.
REQUIRED_GATE_SPACINGS = (
    ("bare", "{key}{token}{secret}"),
    ("spaced", "{key} {token} {secret}"),
    ("stray-hyphen", "{key} - {token} {secret}"),
)


def assert_gate_separators_contain_redactor_separators() -> None:
    """The property that replaced "the gate is an independent detector".

    The gate never was independent -- its keyword class is derived from the
    redactor's, so it structurally cannot catch a redactor keyword miss. What
    it can be is STRICTLY WIDER on separators, which makes a separator the
    redactor cannot rewrite fail closed instead of leak. Three things are
    checked, because a declared token that is never compiled in would satisfy
    a set comparison and still leak:

    1. the required floor is present in the gate alphabet,
    2. the redactor alphabet is contained in the gate alphabet,
    3. every declared token is actually wired into both regexes.
    """
    residual = load_contract_module(
        "residual_credentials_separator_contract",
        RESIDUAL_MODULE,
    )
    gate = set(residual.GATE_SEPARATOR_TOKENS)
    redactor = set(residual.REDACTOR_SEPARATOR_TOKENS)

    missing_floor = sorted(set(REQUIRED_GATE_SEPARATORS) - gate)
    assert not missing_floor, (
        "the residual gate no longer recognises required assignment "
        f"separators: {missing_floor}"
    )
    uncovered = sorted(redactor - gate)
    assert not uncovered, (
        "the redactor rewrites separators the gate cannot see, so an "
        f"unrewritten value at one of them is certified clean: {uncovered}"
    )

    secret = "hunter2LiveProdSeparatorProbe"
    redact = residual.build_assignment_redactor()
    for token in sorted(gate):
        for key in REQUIRED_GATE_KEY_FORMS:
            for spacing, shape in REQUIRED_GATE_SPACINGS:
                probe = shape.format(key=key, token=token, secret=secret)
                # Wired into the gate: an unredacted value at this separator
                # must fail closed.
                assert residual.string_has_residual_credential(probe), (
                    token,
                    key,
                    spacing,
                )
                if token not in redactor:
                    continue
                # Wired into the redactor: and the result must then satisfy the
                # marker invariant rather than merely differ from the input.
                redacted = redact(probe)
                assert secret not in redacted, (token, key, spacing, redacted)
                assert not residual.string_has_residual_credential(
                    redacted
                ), (token, key, spacing, redacted)

    # LAYER 3a OF THE CLOSURE RULE, checked mechanically instead of by
    # inspection. Sweep the entire Unicode codepoint range: any single
    # character whose NFKC normalisation IS one of the separator characters is
    # a spelling of that separator, and it has to be listed as a rendering of
    # it. This is what stops the alphabet from silently reopening on the class
    # the first closure rule missed -- `password<U+FF1D>secret` reads exactly
    # like `password=secret` and used to be no site at all.
    renderings = residual.SEPARATOR_CHARACTER_RENDERINGS
    token_characters = {
        character
        for token in gate
        for character in token
        if character.isascii()
    }
    unlisted = []
    for codepoint in range(0x110000):
        character = chr(codepoint)
        folded = unicodedata.normalize("NFKC", character)
        if folded == character or folded not in token_characters:
            continue
        if character not in renderings.get(folded, ""):
            unlisted.append((hex(codepoint), folded))
    assert not unlisted, (
        "these Unicode characters normalise onto a separator character but "
        "are not listed as renderings of it, so the alphabet has a hole: "
        f"{unlisted}"
    )
    dead = sorted(set(renderings) - token_characters)
    assert not dead, (
        f"renderings are declared for characters no token uses: {dead}"
    )

    # And the renderings are wired in, not merely declared: every ASCII token
    # spelled entirely in renderings has to behave like the token itself. The
    # closure is per CHARACTER, so this also covers the multi-character tokens
    # that a token-level homoglyph list could not have reached.
    for token in sorted(gate):
        rendered = "".join(
            renderings[character][0] if character in renderings else character
            for character in token
        )
        if rendered == token:
            continue
        for key in REQUIRED_GATE_KEY_FORMS:
            for spacing, shape in REQUIRED_GATE_SPACINGS:
                probe = shape.format(key=key, token=rendered, secret=secret)
                assert residual.string_has_residual_credential(probe), (
                    token,
                    rendered,
                    key,
                    spacing,
                )
                if token not in redactor:
                    continue
                redacted = redact(probe)
                assert secret not in redacted, (token, key, spacing, redacted)
                assert not residual.string_has_residual_credential(
                    redacted
                ), (token, key, spacing, redacted)

    # The lead-character guard is derived from the alphabet rather than
    # hand-maintained, so every token -- ASCII or rendering -- can actually be
    # reached. A token whose first character is outside the guard class is
    # dead code that a set comparison would still certify as present.
    for token in sorted(gate):
        assert re.match(residual.SEPARATOR_GUARD + r".", token), token


    # Redaction is idempotent: the emission path raises if a second pass
    # changes anything, so a separator that is rewritten into a new site is a
    # hard failure rather than a cosmetic one.
    for token in sorted(redactor):
        once = redact(f"password{token}{secret}")
        assert redact(once) == once, (token, once)


def assert_env_var_style_keyword_credentials_fail_closed() -> None:
    """Hole 1: `\\b` never matches inside GITHUB_TOKEN / X_API_KEY / id_token."""
    residual = load_contract_module(
        "residual_credentials_env_var_contract",
        RESIDUAL_MODULE,
    )
    for text, secret in ENV_VAR_STYLE_CREDENTIALS:
        assert residual.string_has_residual_credential(text), text
        assert secret in text

    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-env-var-",
    ) as temp_dir:
        temp = Path(temp_dir)
        message = (
            "Error: login step failed\n env dump: "
            f"GITHUB_TOKEN={GITHUB_PAT} "
            f"X_API_KEY={STRIPE_LIVE_KEY}\n redirect: "
            "https://idp.example.com/cb#id_token="
            "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0.SIGSIGSIG"
        )
        leaked = (
            GITHUB_PAT,
            STRIPE_LIVE_KEY,
            "eyJhbGciOiJSUzI1NiJ9",
            "SIGSIGSIG",
        )
        playwright_result, cypress_result = read_both_readers(temp, message)
        for result in (playwright_result, cypress_result):
            assert result.returncode == 0, result.stderr
            combined = result.stdout + result.stderr
            for secret in leaked:
                assert secret not in combined, secret
            assert "[REDACTED]" in result.stdout
            # The surrounding diagnosis must survive the redaction.
            assert "login step failed" in result.stdout


def assert_keyword_free_credential_shapes_fail_closed() -> None:
    """Hole 2: nothing detected keyword-free credential shapes at all."""
    residual = load_contract_module(
        "residual_credentials_shape_contract",
        RESIDUAL_MODULE,
    )
    for name, text, secret in KEYWORD_FREE_CREDENTIAL_SHAPES:
        assert residual.text_has_credential_shape(text), name
        assert residual.has_residual_credential(text), name
        assert secret not in residual.redact_credential_shapes(text), name

    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-shape-",
    ) as temp_dir:
        temp = Path(temp_dir)
        for name, text, secret in KEYWORD_FREE_CREDENTIAL_SHAPES:
            playwright_result, cypress_result = read_both_readers(temp, text)
            for result in (playwright_result, cypress_result):
                assert result.returncode == 0, (name, result.stderr)
                combined = result.stdout + result.stderr
                assert secret not in combined, (name, secret)
                assert "[REDACTED]" in result.stdout, name

    # With shape redaction disabled the gate must still refuse to emit: the
    # detector cannot be a restatement of the redactor.
    playwright_module = load_contract_module(
        "read_playwright_artifact_shape_contract",
        PLAYWRIGHT_READER,
    )
    cypress_redactor = load_contract_module(
        "redact_artifact_shape_contract",
        CYPRESS_REDACTOR,
    )
    identity = staticmethod(lambda text: text).__func__
    for module, emit in (
        (playwright_module, lambda m, v: m.encode_json({"message": v})),
        (cypress_redactor, lambda m, v: m.redact_for_output({"message": v})),
    ):
        original = module.redact_credential_shapes
        module.redact_credential_shapes = identity
        try:
            for name, text, _secret in KEYWORD_FREE_CREDENTIAL_SHAPES:
                try:
                    emit(module, text)
                except ValueError as exc:
                    assert str(exc) == (
                        "credential redaction left residual sensitive output"
                    ), name
                else:
                    raise AssertionError(
                        f"credential shape was emitted unredacted: {name}"
                    )
        finally:
            module.redact_credential_shapes = original


def assert_diagnostics_never_echo_artifact_bytes() -> None:
    """Hole 3: `parser.error` is an exit that bypasses the emission gate."""
    residual = load_contract_module(
        "residual_credentials_diagnostic_contract",
        RESIDUAL_MODULE,
    )
    withheld = residual.sanitize_diagnostic(
        f"boom {GITHUB_OAUTH_TOKEN}",
        lambda text: text,
    )
    assert withheld == residual.DIAGNOSTIC_WITHHELD
    assert GITHUB_OAUTH_TOKEN not in withheld
    assert residual.sanitize_diagnostic("invalid JSON: line 1", str) == (
        "invalid JSON: line 1"
    )

    # Both readers must route their stderr exit through redaction, and must
    # not hand it artifact bytes in the first place. The marker is deliberately
    # not credential-shaped: it proves the bytes are never interpolated, which
    # redaction alone would hide.
    for reader in (PLAYWRIGHT_READER, CYPRESS_READER):
        source = reader.read_text(encoding="utf-8")
        assert "parser.error(str(exc))" not in source, reader.name
        assert "duplicate JSON key at object entry" in source, reader.name
    assert (
        "sanitize_diagnostic(exc, redact_string)"
        in PLAYWRIGHT_READER.read_text(encoding="utf-8")
    )
    assert (
        "redact_diagnostic(exc)" in CYPRESS_READER.read_text(encoding="utf-8")
    )

    marker = "ARTIFACT_CONTROLLED_KEY_MARKER"
    secret_key = f"{marker}-Authorization: Bearer SECRET_ABC123"
    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-diagnostic-",
    ) as temp_dir:
        temp = Path(temp_dir)
        duplicate_key = temp / "duplicate-key.json"
        duplicate_key.write_text(
            '{"config":{"rootDir":"' + str(temp) + '",'
            f'"{secret_key}":1,"{secret_key}":2' + "},"
            '"stats":{"expected":0,"skipped":0,"unexpected":0,"flaky":0},'
            '"suites":[]}',
            encoding="utf-8",
        )
        rejected = run_playwright_reader(
            PLAYWRIGHT_READER,
            "report",
            temp,
            duplicate_key,
        )
        assert rejected.returncode != 0
        assert rejected.stdout == ""
        assert "SECRET_ABC123" not in rejected.stderr
        assert marker not in rejected.stderr
        assert "duplicate JSON key" in rejected.stderr

        cypress_duplicate = temp / "duplicate-key-mochawesome.json"
        cypress_duplicate.write_text(
            '{"stats":{"suites":0,"tests":0,"passes":0,"pending":0,'
            '"failures":0,"skipped":0,"duration":0,'
            f'"{secret_key}":1,"{secret_key}":2' + "},"
            '"results":[]}',
            encoding="utf-8",
        )
        cypress_rejected = run_cypress_reader(
            CYPRESS_READER,
            "mochawesome",
            temp,
            cypress_duplicate,
        )
        assert cypress_rejected.returncode != 0
        assert cypress_rejected.stdout == ""
        assert "SECRET_ABC123" not in cypress_rejected.stderr
        assert marker not in cypress_rejected.stderr

        # ZIP entry names are artifact-controlled on the same stderr path.
        credential_entry = temp / "credential-entry-name.zip"
        with zipfile.ZipFile(
            credential_entry, "w", compression=zipfile.ZIP_STORED
        ) as archive:
            archive.writestr(
                f"../{marker}-{GITHUB_PAT}/trace.trace",
                "{}\n",
            )
        zip_rejected = run_playwright_reader(
            PLAYWRIGHT_READER,
            "trace",
            temp,
            credential_entry,
            "--entry",
            "trace.trace",
        )
        assert zip_rejected.returncode != 0
        assert zip_rejected.stdout == ""
        assert GITHUB_PAT not in zip_rejected.stderr
        assert marker not in zip_rejected.stderr
        assert "unsafe zip entry name" in zip_rejected.stderr.lower()


def assert_partial_redaction_cannot_satisfy_the_gate() -> None:
    """Hole 4, restated for the marker invariant.

    UPDATED POLICY. This contract used to assert that the gate re-reads the
    value and judges it, so `password:[REDACTED] horse battery staple` had to
    read as unsafe. The gate no longer parses values -- it asks only whether
    the marker sits immediately after a separator a keyword claimed -- so that
    string now reads as safe, and the guarantee moved one step earlier: the
    redactor must never emit it in the first place. That is asserted directly
    below, which is a stronger check than the old one because it names the
    output rather than a property of a hand-written intermediate.
    """
    residual = load_contract_module(
        "residual_credentials_partial_contract",
        RESIDUAL_MODULE,
    )
    cypress_redactor = load_contract_module(
        "redact_artifact_partial_contract",
        CYPRESS_REDACTOR,
    )
    # A colon value runs to the end of the line, so no tail survives to be
    # certified: this is the shape the old assertion was defending against.
    assert cypress_redactor.redact_string(
        "password: correct horse battery staple"
    ) == "password:[REDACTED]"
    assert residual.string_has_residual_credential(
        "password: correct horse battery staple"
    )
    assert not residual.string_has_residual_credential("password:[REDACTED]")
    # The marker must be adjacent to the separator. A value that survives in
    # front of the marker is still a violation.
    assert residual.string_has_residual_credential(
        "password: correct horse [REDACTED]"
    )
    # `=` stays whitespace-terminated so unrelated env pairs survive.
    assert not residual.string_has_residual_credential(
        "TOKEN=[REDACTED] PATH=/usr/bin"
    )

    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-partial-",
    ) as temp_dir:
        temp = Path(temp_dir)
        message = "login failed, password: correct horse battery staple"
        playwright_result, cypress_result = read_both_readers(temp, message)
        for result in (playwright_result, cypress_result):
            assert result.returncode == 0, result.stderr
            combined = result.stdout + result.stderr
            for fragment in ("correct horse", "battery staple"):
                assert fragment not in combined, fragment
            assert "login failed" in result.stdout


def assert_multi_line_value_boundary_is_pinned() -> None:
    """Characterisation test for a KNOWN, DELIBERATE boundary.

    The value extent claims the separator's own line and exactly one continuation
    line. The second and later lines of a multi-line value are outside it, so a
    secret spread over several lines is still emitted and the gate does not flag
    it. That is documented in the module and in both debugger SKILL.md files.

    This test pins the boundary rather than the guarantee. If a later change
    widens the extent, this test fails and the widening becomes a deliberate
    decision with a measured availability cost, instead of a silent behaviour
    change in a security control.
    """
    residual = load_contract_module(
        "residual_credentials_multiline_boundary",
        RESIDUAL_MODULE,
    )
    cypress_redactor = load_contract_module(
        "redact_artifact_multiline_boundary",
        CYPRESS_REDACTOR,
    )
    payload = "password:\n    FIRSTLINEsecret\n    SECONDLINEsecret"
    redacted = cypress_redactor.redact_string(payload)

    # Covered: the separator's line and the first continuation line.
    assert "FIRSTLINEsecret" not in redacted, redacted
    assert redacted.startswith("password:[REDACTED]\n"), redacted

    # Outside the extent, and the gate agrees it is outside rather than
    # certifying a value it never examined.
    assert "SECONDLINEsecret" in redacted, redacted
    assert not residual.string_has_residual_credential(redacted), redacted

    # A single-line value of the same shape stays fully covered.
    assert cypress_redactor.redact_string(
        "password: FIRSTLINEsecret"
    ) == "password:[REDACTED]"


def assert_cypress_reader_enforces_the_same_residual_gate() -> None:
    """Hole 5 (behaviour): Cypress used to leak a strictly larger set."""
    parity_leaks = (
        (
            'headers: {"cookie":"sid=SUPERSECRET"} '
            f"GITHUB_TOKEN={GITHUB_PAT}",
            ("SUPERSECRET", GITHUB_PAT),
        ),
        (
            f"Error: charge failed {STRIPE_LIVE_KEY} and {AWS_ACCESS_KEY_ID}",
            (STRIPE_LIVE_KEY, AWS_ACCESS_KEY_ID),
        ),
    )
    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-parity-",
    ) as temp_dir:
        temp = Path(temp_dir)
        for message, secrets in parity_leaks:
            playwright_result, cypress_result = read_both_readers(temp, message)
            for result in (playwright_result, cypress_result):
                assert result.returncode == 0, result.stderr
                combined = result.stdout + result.stderr
                for secret in secrets:
                    assert secret not in combined, secret

    # Fail closed, not warn: with redaction neutered the Cypress path must
    # raise and emit nothing, exactly like the Playwright path.
    cypress_redactor = load_contract_module(
        "redact_artifact_parity_contract",
        CYPRESS_REDACTOR,
    )
    original = cypress_redactor.redact_sensitive
    cypress_redactor.redact_sensitive = lambda value, parent_key=None: value
    try:
        for leaked in (
            {"message": "Cookie: session=liveCookieValue"},
            {"message": "token=liveTokenValue"},
            {"headers": [{"name": "Cookie", "value": "session=live"}]},
            {"authorization": "opaqueLiveCredential"},
        ):
            try:
                cypress_redactor.redact_for_output(leaked)
            except ValueError as exc:
                assert str(exc) == (
                    "credential redaction left residual sensitive output"
                )
                assert "live" not in str(exc).lower()
            else:
                raise AssertionError(
                    f"Cypress emitted a residual credential: {leaked!r}"
                )
    finally:
        cypress_redactor.redact_sensitive = original


# Every one of these emitted the secret at exit 0 through all three readers.
# Keyed by the structural gap each one exercises, so a future narrowing shows
# up as a named failure rather than a count change.
KEYWORD_GAP_LEAKS = (
    ("arrow-assignment", "config.password => {secret}"),
    # Header keywords run through a second gate pattern. It has to consume the
    # `>` too: otherwise it reads the redactor's own `authorization=>[REDACTED]`
    # back as the unsafe value `>[REDACTED]` and fails the read closed, which
    # suppresses every diagnostic instead of leaking one.
    ("arrow-header", "Authorization => {secret}"),
    ("arrow-header-bracket", 'headers["authorization"] => {secret}'),
    ("snake-private-key", "private_key={secret}"),
    ("camel-private-key", "privateKey: {secret}"),
    ("bracket-subscript", "user[password]={secret}"),
    ("credential-plural", "credentials={secret}"),
    ("pwd-abbreviation", "pwd={secret}"),
    ("signature", "signature={secret}"),
)
KEYWORD_GAP_SECRET = "hunter2ResidualLeakProbe"


def junit_report_with_message(message: str) -> str:
    escaped = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<testsuite name="Checkout flow" tests="1" failures="1"'
        ' file="cypress/e2e/checkout.cy.ts">\n'
        '  <testcase name="submits the order" classname="Checkout flow">\n'
        f'    <failure message="{escaped}" type="CypressError">'
        f"{escaped}</failure>\n"
        "  </testcase>\n</testsuite>\n"
    )


def read_all_three_readers(temp: Path, message: str) -> tuple:
    """Both artifact readers plus the JUnit extractor, which shares the gate."""
    junit_report = temp / "junit.xml"
    junit_report.write_text(
        junit_report_with_message(message),
        encoding="utf-8",
    )
    playwright_result, cypress_result = read_both_readers(temp, message)
    return (
        playwright_result,
        cypress_result,
        run_extractor(
            CYPRESS_SKILL / "scripts/extract-junit-failures.py",
            temp,
            junit_report,
        ),
    )


def assert_keyword_gaps_do_not_leak_through_any_reader() -> None:
    """Hole 6: the gate reused the redactor's keyword class, so it could only
    ever confirm what the redactor already knew. Seven assignment shapes fell
    through both at once and were emitted verbatim at exit 0."""
    residual = load_contract_module(
        "residual_credentials_keyword_gap_contract",
        RESIDUAL_MODULE,
    )
    # The gate must not be anchored on a narrower class than the redactor;
    # deriving one from the other is what makes that unrepresentable.
    assert (
        residual.RESIDUAL_ASSIGNMENT_KEYWORDS == residual.ASSIGNMENT_KEYWORDS
    ), "the residual gate anchors on a narrower keyword class than the redactor"

    for name, template in KEYWORD_GAP_LEAKS:
        text = template.format(secret=KEYWORD_GAP_SECRET)
        assert residual.string_has_residual_credential(text), name

    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-keyword-gap-",
    ) as temp_dir:
        temp = Path(temp_dir)
        for name, template in KEYWORD_GAP_LEAKS:
            message = f"login failed, {template.format(secret=KEYWORD_GAP_SECRET)}"
            for result in read_all_three_readers(temp, message):
                # Exit 0 with the secret in the payload was the whole bug, so
                # a non-zero exit is not on its own a pass -- assert both.
                assert result.returncode == 0, (name, result.stderr)
                combined = result.stdout + result.stderr
                assert KEYWORD_GAP_SECRET not in combined, (name, combined[:400])
                assert "[REDACTED]" in result.stdout, name


def assert_arrow_assignment_redaction_matches_the_gate() -> None:
    """Hole 7: the redactor stopped at `>` and the gate read back the mask.

    `password => secret` was rewritten to `password=[REDACTED] secret`, and the
    gate's equals-branch capture then saw the literal `[REDACTED]` and called
    the line safe -- the exact partial-redaction class the previous pass
    claimed to close, reopened by a separator the two sides parsed differently.

    The whole `=`-family is checked here now, because `==` and `===` reopened
    the identical hole one design pass later.
    """
    residual = load_contract_module(
        "residual_credentials_arrow_contract",
        RESIDUAL_MODULE,
    )
    cypress_redactor = load_contract_module(
        "redact_artifact_arrow_contract",
        CYPRESS_REDACTOR,
    )

    # Redactor and gate must agree on where the value starts and ends.
    assert (
        cypress_redactor.redact_string("config.password => hunter2SECRET")
        == "config.password=>[REDACTED]"
    )
    assert residual.string_has_residual_credential(
        "config.password => hunter2SECRET"
    )
    # ...and the fully redacted form must not fail closed.
    assert not residual.string_has_residual_credential(
        "config.password=>[REDACTED]"
    )
    # UPDATED POLICY. The half-redacted form `password=[REDACTED] secret` is
    # still not recoverable at the gate -- it is structurally identical to
    # `TOKEN=[REDACTED] PATH=/usr/bin`, which must keep passing -- but the
    # reason it never appears has changed. It is no longer that both sides
    # parse the separator the same way; it is that the separator alphabet the
    # gate checks CONTAINS the one the redactor rewrites, so a separator the
    # redactor mis-split would fail the read closed instead of certifying the
    # tail. See assert_gate_separators_contain_redactor_separators.
    assert not residual.string_has_residual_credential(
        "TOKEN=[REDACTED] PATH=/usr/bin"
    )
    for separator in ("=>", "==", "===", "->", "+=", "|=", ":="):
        emitted = cypress_redactor.redact_string(
            f"config.password {separator} hunter2LiveProdPassword"
        )
        assert emitted == f"config.password{separator}[REDACTED]", emitted
    assert cypress_redactor.redact_string(
        "config.password => hunter2SECRET"
    ) == cypress_redactor.redact_string(
        cypress_redactor.redact_string("config.password => hunter2SECRET")
    )

    # `>` alone is never an assignment separator, or every password input in
    # every DOM dump would be mangled.
    assert (
        cypress_redactor.redact_string('<input type="password">')
        == '<input type="password">'
    )
    arrow_fn = "const submit = () => page.getByLabel('Password').fill(pw)"
    assert cypress_redactor.redact_string(arrow_fn) == arrow_fn
    assert not residual.string_has_residual_credential(arrow_fn)


def assert_benign_artifact_text_is_not_flagged() -> None:
    """False positives here cost more than they save: keep debugging possible."""
    residual = load_contract_module(
        "residual_credentials_benign_contract",
        RESIDUAL_MODULE,
    )
    for text in BENIGN_ARTIFACT_TEXT:
        assert not residual.text_has_credential_shape(text), text

    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-benign-",
    ) as temp_dir:
        temp = Path(temp_dir)
        for text in BENIGN_ARTIFACT_TEXT:
            playwright_result, cypress_result = read_both_readers(temp, text)
            for result in (playwright_result, cypress_result):
                assert result.returncode == 0, (text, result.stderr)
                assert result.stdout.strip(), text

        combined_text = "\n".join(BENIGN_ARTIFACT_TEXT)
        playwright_result, cypress_result = read_both_readers(
            temp,
            combined_text,
        )
        for result in (playwright_result, cypress_result):
            assert result.returncode == 0, result.stderr
            for fragment in BENIGN_FRAGMENTS_THAT_MUST_SURVIVE:
                assert fragment in result.stdout, fragment


def assert_must_close_assignment_leaks_are_closed() -> None:
    """Hole 8: separator families and substring keywords the old design missed.

    Each entry emitted its secret at exit 0 through all three readers. A
    non-zero exit is not a pass on its own -- that would trade the leak for an
    availability outage -- so exit 0, the absent secret, and the presence of
    the marker are all asserted together.
    """
    residual = load_contract_module(
        "residual_credentials_must_close_contract",
        RESIDUAL_MODULE,
    )
    cypress_redactor = load_contract_module(
        "redact_artifact_must_close_contract",
        CYPRESS_REDACTOR,
    )
    for name, template in MUST_CLOSE_ASSIGNMENT_LEAKS:
        text = template.format(secret=MUST_CLOSE_SECRET)
        assert residual.string_has_residual_credential(text), name
        redacted = cypress_redactor.redact_string(text)
        assert MUST_CLOSE_SECRET not in redacted, (name, redacted)
        assert not residual.string_has_residual_credential(redacted), (
            name,
            redacted,
        )

    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-must-close-",
    ) as temp_dir:
        temp = Path(os.path.realpath(temp_dir))
        for name, template in MUST_CLOSE_ASSIGNMENT_LEAKS:
            message = (
                "login failed, " + template.format(secret=MUST_CLOSE_SECRET)
            )
            for result in read_all_three_readers(temp, message):
                assert result.returncode == 0, (name, result.stderr)
                combined = result.stdout + result.stderr
                assert MUST_CLOSE_SECRET not in combined, (
                    name,
                    combined[:400],
                )
                assert "[REDACTED]" in result.stdout, name


def assert_availability_corpus_never_fails_closed() -> None:
    """The cost side of the policy: aggressive redaction, never an outage.

    Redacting a benign value next to a sensitivity keyword is the intended
    trade. Refusing to emit anything is not, so every entry has to reach exit 0
    with non-empty output through all three readers.
    """
    residual = load_contract_module(
        "residual_credentials_availability_contract",
        RESIDUAL_MODULE,
    )
    cypress_redactor = load_contract_module(
        "redact_artifact_availability_contract",
        CYPRESS_REDACTOR,
    )
    playwright_module = load_contract_module(
        "read_playwright_artifact_availability_contract",
        PLAYWRIGHT_READER,
    )
    for text in AVAILABILITY_CORPUS:
        for redact in (
            cypress_redactor.redact_string,
            playwright_module.redact_string,
        ):
            redacted = redact(text)
            assert not residual.string_has_residual_credential(redacted), (
                text,
                redacted,
            )
            # The emission path raises when a second pass changes anything.
            assert redact(redacted) == redacted, (text, redacted)

    with tempfile.TemporaryDirectory(
        prefix="e2e-residual-availability-",
    ) as temp_dir:
        temp = Path(os.path.realpath(temp_dir))
        for text in AVAILABILITY_CORPUS:
            for result in read_all_three_readers(temp, text):
                assert result.returncode == 0, (text, result.stderr)
                assert result.stdout.strip(), text


# Minimum Python the bundled launchers may hand a bundled script. The launcher
# candidate list is /usr/bin/python3 and /bin/python3; on macOS that is 3.9.6,
# so every bundled script must stay inside the 3.9 API surface. Raise this only
# together with the launcher candidate list.
MINIMUM_BUNDLED_PYTHON = (3, 9)

# Method keywords that pathlib gained after MINIMUM_BUNDLED_PYTHON. These pass
# a syntax check on any version and only explode at call time, so a plain
# compile() sweep cannot catch them.
POST_MINIMUM_METHOD_KEYWORDS = {
    "stat": {"follow_symlinks"},
    "chmod": {"follow_symlinks"},
    "glob": {"case_sensitive", "recurse_symlinks"},
    "rglob": {"case_sensitive", "recurse_symlinks"},
    "is_dir": {"follow_symlinks"},
    "is_file": {"follow_symlinks"},
    "relative_to": {"walk_up"},
}


def bundled_helper_scripts() -> tuple[tuple[Path, str, str], ...]:
    """(launcher, --reader name, kind) for every launcher-startable script."""
    playwright_skill = ROOT / "skills/playwright-debugger"
    playwright_launcher = playwright_skill / "scripts/run-artifact-reader.sh"
    cypress_launcher = CYPRESS_SKILL / "scripts/run-artifact-reader.sh"
    return (
        (playwright_launcher, "read-playwright-artifact.py", "reader"),
        (playwright_launcher, "publish-json-report.py", "publisher"),
        (playwright_launcher, "download-playwright-report.py", "downloader"),
        (cypress_launcher, "read-cypress-artifact.py", "reader"),
        (cypress_launcher, "extract-junit-failures.py", "reader"),
        (cypress_launcher, "publish-mochawesome-report.py", "publisher"),
        (cypress_launcher, "download-cypress-reports.py", "downloader"),
    )


def hostile_python_environment(root: Path) -> tuple[dict[str, str], Path, Path]:
    """A PATH shim plus a PYTHONPATH startup hook, with their two markers.

    The shim re-populates PYTHONPATH itself, because it runs *after* any
    ``env -i`` the caller used: clearing the environment is not enough when the
    interpreter is still resolved by bare name through a forwarded PATH.
    """
    hostile_bin = root / "hostile-bin"
    hostile_package = root / "hostile-package"
    markers = root / "markers"
    hostile_bin.mkdir(parents=True)
    hostile_package.mkdir()
    markers.mkdir()
    path_marker = markers / "path-shim-selected"
    startup_marker = markers / "startup-hook-executed"
    (hostile_package / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(startup_marker)!r}).touch()\n",
        encoding="utf-8",
    )
    shim = hostile_bin / "python3"
    shim.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {path_marker}\n"
        f"PYTHONPATH={hostile_package} exec /usr/bin/python3 \"$@\"\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    environment = {
        "PATH": f"{hostile_bin}:/usr/bin:/bin",
        "PYTHONPATH": str(hostile_package),
        "PYTHONSTARTUP": str(hostile_package / "sitecustomize.py"),
        "PYTHONHOME": str(root / "fake-python-home"),
        "PYTHONINSPECT": "1",
    }
    return environment, path_marker, startup_marker


def assert_bundled_helpers_never_resolve_python_through_path() -> None:
    """Publisher and downloader must not pick their interpreter from PATH.

    ``/usr/bin/env -i PATH="$PATH" python3 <helper>`` clears the environment
    but still resolves the bare name ``python3`` through the forwarded ambient
    PATH, so a project virtualenv or a shim on PATH chooses the interpreter
    that then execs the bundled reader in-process. Every bundled helper must go
    through the launcher instead.
    """
    playwright_skill = ROOT / "skills/playwright-debugger"

    for launcher, reader_name, _kind in bundled_helper_scripts():
        launcher_text = launcher.read_text(encoding="utf-8")
        allowlist_block = launcher_text[
            launcher_text.index('case "$reader_name" in') :
            launcher_text.index("requested_env=''")
        ]
        assert reader_name in allowlist_block, (launcher, reader_name)
        assert "pass_env_allowlist" in launcher_text, launcher
        # Interpreter selection stays bounded and absolute; PATH may only ever
        # appear as an explicitly allowlisted forwarded value.
        assert "for fixed_candidate in" in launcher_text
        assert "/usr/bin/python3" in launcher_text
        assert "is_root_owned_system_path" in launcher_text
        assert "exec /usr/bin/env -i" in launcher_text
        assert 'shutil.which' not in launcher_text
        selection_region = launcher_text[
            launcher_text.index("for fixed_candidate in") :
            launcher_text.index("[ -n \"$interpreter\" ]")
        ]
        assert "PATH" not in selection_region, (
            f"{launcher} resolves its interpreter through PATH"
        )

    # No SKILL.md may prescribe a bare python3 for a bundled helper any more.
    for skill_path, helpers in (
        (
            PLAYWRIGHT_SKILL,
            ("publish-json-report.py", "download-playwright-report.py"),
        ),
        (
            CYPRESS_SKILL / "SKILL.md",
            ("publish-mochawesome-report.py", "download-cypress-reports.py"),
        ),
    ):
        skill_text = skill_path.read_text(encoding="utf-8")
        for helper in helpers:
            assert f"python3 <skill-dir>/scripts/{helper}" not in skill_text, (
                f"{skill_path} still starts {helper} with a bare python3"
            )
            assert f'PATH="$PATH" python3 \\\n  <skill-dir>/scripts/{helper}' not in (
                skill_text
            ), f"{skill_path} still starts {helper} with a PATH-resolved python3"
            assert f"--reader {helper}" in skill_text, (
                f"{skill_path} does not route {helper} through the launcher"
            )
        assert "does **not** satisfy this rule" in skill_text, skill_path
        assert "--pass-env NAME" in skill_text, skill_path

    with tempfile.TemporaryDirectory(
        prefix="e2e-helper-interpreter-boundary-",
    ) as temp_dir:
        root = Path(temp_dir)
        # /private/tmp, not /tmp: the launcher compares physical paths, and on
        # macOS /tmp is a symlink, so a /tmp project root would compare against
        # a different string than the one `cd -P` produces.
        assert os.path.realpath(root) == str(root), root
        environment, path_marker, startup_marker = hostile_python_environment(root)
        project = root / "project"
        project.mkdir()
        assert os.path.realpath(project) == str(project), project
        # HOME must exist and stay outside the project: the downloader refuses a
        # project-controlled HOME before it ever reaches the network.
        home = root / "home"
        home.mkdir()

        emitter = project / "emit-report.sh"
        emitter.write_text(
            "#!/bin/sh\n"
            "cat <<'JSON'\n"
            + playwright_report_with_message(project, "boom")
            + "\nJSON\n",
            encoding="utf-8",
        )
        emitter.chmod(0o755)

        publisher = subprocess.run(
            [
                str(playwright_skill / "scripts/run-artifact-reader.sh"),
                "--project-root",
                str(project),
                "--reader",
                "publish-json-report.py",
                "--pass-env",
                "PATH",
                "--",
                "--pass-env",
                "PATH",
                "playwright-report/results.json",
                "--",
                "./emit-report.sh",
            ],
            cwd=project,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        assert publisher.returncode == 0, publisher.stderr
        assert (project / "playwright-report/results.json").is_file()
        assert not path_marker.exists(), "publisher used the hostile PATH python3"
        assert not startup_marker.exists(), (
            "publisher executed a checkout-supplied startup hook"
        )

        # The bundled reader must still be the in-process validator: an invalid
        # report has to be rejected by read-playwright-artifact.py's own schema
        # check, and nothing may be published.
        (project / "playwright-report/results.json").unlink()
        bad_emitter = project / "emit-garbage.sh"
        bad_emitter.write_text(
            "#!/bin/sh\nprintf '%s' '{\"not\": \"a report\"}'\n",
            encoding="utf-8",
        )
        bad_emitter.chmod(0o755)
        rejected = subprocess.run(
            [
                str(playwright_skill / "scripts/run-artifact-reader.sh"),
                "--project-root",
                str(project),
                "--reader",
                "publish-json-report.py",
                "--pass-env",
                "PATH",
                "--",
                "--pass-env",
                "PATH",
                "playwright-report/results.json",
                "--",
                "./emit-garbage.sh",
            ],
            cwd=project,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        assert rejected.returncode != 0
        assert "suites" in rejected.stderr, rejected.stderr
        assert not (project / "playwright-report/results.json").exists()
        assert not path_marker.exists()
        assert not startup_marker.exists()

        # Downloaders: no credentials and no network here, which is fine. A
        # startup hook runs before the helper's first statement, so the markers
        # answer the isolation question regardless of how the download fails.
        for launcher, reader_name, kind in bundled_helper_scripts():
            if kind != "downloader":
                continue
            downloader_environment = dict(environment)
            downloader_environment["HOME"] = str(home)
            download = subprocess.run(
                [
                    str(launcher),
                    "--project-root",
                    str(project),
                    "--reader",
                    reader_name,
                    "--pass-env",
                    "HOME",
                    "--",
                    "--repo",
                    "owner/repo",
                    "1234567890",
                ],
                cwd=project,
                env=downloader_environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
            assert not path_marker.exists(), (
                f"{reader_name} used the hostile PATH python3"
            )
            assert not startup_marker.exists(), (
                f"{reader_name} executed a checkout-supplied startup hook"
            )
            # Prove the bundled helper itself ran, so the two markers above are
            # evidence of isolation and not of an early launcher abort.
            assert reader_name.removesuffix(".py") + ":" in download.stderr, (
                download.stderr
            )

        # The pass-env allowlist is closed, per helper.
        forbidden = (
            ("read-playwright-artifact.py", "PATH"),
            ("read-playwright-artifact.py", "PYTHONPATH"),
            ("publish-json-report.py", "HOME"),
            ("publish-json-report.py", "GH_TOKEN"),
            ("publish-json-report.py", "PYTHONPATH"),
            ("download-playwright-report.py", "PATH"),
            ("download-playwright-report.py", "PYTHONPATH"),
        )
        for reader_name, variable in forbidden:
            refused = subprocess.run(
                [
                    str(playwright_skill / "scripts/run-artifact-reader.sh"),
                    "--project-root",
                    str(project),
                    "--reader",
                    reader_name,
                    "--pass-env",
                    variable,
                    "--",
                    "--repo",
                    "owner/repo",
                    "1",
                ],
                cwd=project,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            assert refused.returncode != 0, (reader_name, variable)
            assert "not allowlisted" in refused.stderr, refused.stderr
            assert not path_marker.exists()
            assert not startup_marker.exists()

        duplicated = subprocess.run(
            [
                str(playwright_skill / "scripts/run-artifact-reader.sh"),
                "--project-root",
                str(project),
                "--reader",
                "publish-json-report.py",
                "--pass-env",
                "PATH",
                "--pass-env",
                "PATH",
                "--",
                "--pass-env",
                "PATH",
                "playwright-report/results.json",
                "--",
                "./emit-report.sh",
            ],
            cwd=project,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        assert duplicated.returncode != 0
        assert "more than once" in duplicated.stderr, duplicated.stderr

    print("bundled helper interpreter boundary: pass")


def assert_bundled_scripts_match_the_launcher_minimum_python() -> None:
    """Bundled scripts must run on the oldest interpreter the launcher picks.

    The launchers select from /usr/bin/python3 and /bin/python3. macOS ships
    3.9.6 there, so a bundled script that needs 3.10+ crashes on an interpreter
    its own launcher is allowed to hand it.
    """
    scripts = sorted(
        path
        for skill in ("playwright-debugger", "cypress-debugger")
        for path in (ROOT / "skills" / skill / "scripts").glob("*.py")
    )
    assert scripts, "no bundled debugger scripts found"

    for script in scripts:
        source = script.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(script))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            gated = POST_MINIMUM_METHOD_KEYWORDS.get(node.func.attr)
            if not gated:
                continue
            # os.stat(path, follow_symlinks=...) has always accepted the
            # keyword; only the bound pathlib method form is version-gated.
            target = node.func.value
            if isinstance(target, ast.Name) and target.id == "os":
                continue
            for keyword in node.keywords:
                assert keyword.arg not in gated, (
                    f"{script}:{node.lineno} uses "
                    f"{node.func.attr}({keyword.arg}=...), which needs Python "
                    f"newer than {'.'.join(str(part) for part in MINIMUM_BUNDLED_PYTHON)}; "
                    "the launcher may select /usr/bin/python3"
                )

    # Whatever interpreter the launcher actually selects on this host must be
    # at least the declared floor, and must be able to compile every script.
    selected = subprocess.run(
        [
            "/bin/sh",
            "-c",
            'for c in /usr/bin/python3 /bin/python3; do '
            '[ -x "$c" ] && { printf "%s" "$c"; exit 0; }; done; exit 1',
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert selected.returncode == 0, "no launcher interpreter candidate exists"
    interpreter = selected.stdout.strip()
    version = subprocess.run(
        [interpreter, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=True,
    ).stdout.strip()
    major, minor = (int(part) for part in version.split("."))
    assert (major, minor) >= MINIMUM_BUNDLED_PYTHON, (
        f"{interpreter} is {version}, below the declared bundled floor"
    )

    for script in scripts:
        compiled = subprocess.run(
            [
                interpreter,
                "-c",
                "import sys; "
                "compile(open(sys.argv[1], 'rb').read(), sys.argv[1], 'exec')",
                str(script),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        assert compiled.returncode == 0, (
            f"{script} does not compile on {interpreter} ({version}): "
            f"{compiled.stderr}"
        )

    floor = ".".join(str(part) for part in MINIMUM_BUNDLED_PYTHON)
    for skill_path in (PLAYWRIGHT_SKILL, CYPRESS_SKILL / "SKILL.md"):
        skill_text = skill_path.read_text(encoding="utf-8")
        assert f"Python {floor}" in skill_text, (
            f"{skill_path} does not state the bundled Python {floor} floor"
        )

    print(f"bundled script Python floor ({floor}): pass")


def main() -> None:
    assert_artifact_reader_launcher_boundary()
    assert_bundled_helpers_never_resolve_python_through_path()
    assert_bundled_scripts_match_the_launcher_minimum_python()
    assert_shared_residual_module_is_single_source_of_truth()
    assert_gate_separators_contain_redactor_separators()
    assert_must_close_assignment_leaks_are_closed()
    assert_availability_corpus_never_fails_closed()
    assert_env_var_style_keyword_credentials_fail_closed()
    assert_keyword_free_credential_shapes_fail_closed()
    assert_diagnostics_never_echo_artifact_bytes()
    assert_partial_redaction_cannot_satisfy_the_gate()
    assert_multi_line_value_boundary_is_pinned()
    assert_cypress_reader_enforces_the_same_residual_gate()
    assert_keyword_gaps_do_not_leak_through_any_reader()
    assert_arrow_assignment_redaction_matches_the_gate()
    assert_benign_artifact_text_is_not_flagged()
    extractor = CYPRESS_SKILL / "scripts/extract-junit-failures.py"
    fixture = CYPRESS_SKILL / "evals/files/junit-mixed-suites.xml"
    missing_root = run_extractor(extractor, None, fixture)
    assert missing_root.returncode != 0
    assert "--report-root" in missing_root.stderr

    result = run_extractor(extractor, fixture.parent, fixture)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert rows == [
        {
            "classname": "Checkout flow",
            "file": "cypress/e2e/checkout.cy.ts",
            "kind": "failure",
            "message": "expected receipt to be visible",
            "name": "places the order",
            "report": str(fixture),
        },
        {
            "classname": "Profile settings",
            "file": "cypress/e2e/profile.cy.ts",
            "kind": "failure",
            "message": "expected Ada but found Grace",
            "name": "saves the display name",
            "report": str(fixture),
        },
    ], rows

    with tempfile.TemporaryDirectory(
        prefix="e2e-junit-contract-",
    ) as temp_dir:
        temp = Path(temp_dir)
        reports = temp / "reports"
        reports.mkdir()
        valid = reports / "valid.xml"
        valid.write_text(
            '<testsuite file="spec.cy.ts"><testcase name="fails">'
            '<failure message="boom"/></testcase></testsuite>',
            encoding="utf-8",
        )
        invalid_after_valid = reports / "invalid-after-valid.xml"
        invalid_after_valid.write_text("<testsuite>", encoding="utf-8")
        atomic_rejection = run_extractor(
            extractor,
            reports,
            valid,
            invalid_after_valid,
        )
        assert atomic_rejection.returncode != 0
        assert atomic_rejection.stdout == ""

        junit_secret_text, junit_secrets = adversarial_credentials(500)
        secret_junit = reports / "secret.xml"
        secret_junit.write_text(
            "<testsuite><testcase name=\"secret failure\"><failure><![CDATA["
            f"{junit_secret_text}"
            "]]></failure></testcase></testsuite>",
            encoding="utf-8",
        )
        secret_junit_result = run_extractor(
            extractor,
            reports,
            secret_junit,
        )
        assert secret_junit_result.returncode == 0, secret_junit_result.stderr
        assert_credentials_redacted(
            secret_junit_result.stdout,
            junit_secrets,
        )

        report_count_boundary = []
        for index in range(128):
            path = reports / f"count-{index}.xml"
            path.write_text("<testsuite/>", encoding="utf-8")
            report_count_boundary.append(path)
        accepted = run_extractor(
            extractor,
            reports,
            *report_count_boundary,
        )
        assert accepted.returncode == 0, accepted.stderr
        rejected = run_extractor(
            extractor,
            reports,
            *report_count_boundary,
            reports / "not-read.xml",
        )
        assert rejected.returncode != 0
        assert "128-report limit" in rejected.stderr
        assert "not-read" not in rejected.stderr
        assert rejected.stdout == ""

        def write_exact_sized_junit(path: Path, size: int) -> None:
            prefix = b"<testsuite><!--"
            suffix = b"--></testsuite>"
            assert size >= len(prefix) + len(suffix)
            path.write_bytes(
                prefix
                + b"x" * (size - len(prefix) - len(suffix))
                + suffix
            )

        aggregate_first = reports / "aggregate-first.xml"
        aggregate_second = reports / "aggregate-second.xml"
        write_exact_sized_junit(aggregate_first, 8 * 1024 * 1024)
        write_exact_sized_junit(aggregate_second, 8 * 1024 * 1024)
        accepted = run_extractor(
            extractor,
            reports,
            aggregate_first,
            aggregate_second,
        )
        assert accepted.returncode == 0, accepted.stderr
        aggregate_overflow = reports / "aggregate-overflow.xml"
        aggregate_overflow.write_bytes(b"x")
        rejected = run_extractor(
            extractor,
            reports,
            aggregate_first,
            aggregate_second,
            aggregate_overflow,
        )
        assert rejected.returncode != 0
        assert "16777216-byte aggregate input limit" in rejected.stderr
        assert rejected.stdout == ""

        def failure_suite(count: int, suite_file: str = "") -> str:
            return (
                f'<testsuite file="{suite_file}">'
                + "".join(
                    f'<testcase name="failure-{index}">'
                    '<failure message="boom"/></testcase>'
                    for index in range(count)
                )
                + "</testsuite>"
            )

        aggregate_rows_first = reports / "aggregate-rows-first.xml"
        aggregate_rows_second = reports / "aggregate-rows-second.xml"
        aggregate_rows_first.write_text(
            failure_suite(5_000),
            encoding="utf-8",
        )
        aggregate_rows_second.write_text(
            failure_suite(5_000),
            encoding="utf-8",
        )
        accepted = run_extractor(
            extractor,
            reports,
            aggregate_rows_first,
            aggregate_rows_second,
        )
        assert accepted.returncode == 0, accepted.stderr
        assert len(accepted.stdout.splitlines()) == 10_000
        one_more_row = reports / "one-more-row.xml"
        one_more_row.write_text(failure_suite(1), encoding="utf-8")
        rejected = run_extractor(
            extractor,
            reports,
            aggregate_rows_first,
            aggregate_rows_second,
            one_more_row,
        )
        assert rejected.returncode != 0
        assert "10000-failure aggregate limit" in rejected.stderr
        assert rejected.stdout == ""

        amplified_output = reports / "amplified-output.xml"
        amplified_output.write_text(
            failure_suite(8_000, "x" * 1_000),
            encoding="utf-8",
        )
        rejected = run_extractor(extractor, reports, amplified_output)
        assert rejected.returncode != 0
        assert "8388608-byte limit" in rejected.stderr
        assert rejected.stdout == ""

        long_value = "x" * 1_200
        bounded = reports / "bounded.xml"
        bounded.write_text(
            f'<testsuite file="{long_value}"><testcase '
            f'classname="{long_value}" name="{long_value}">'
            f'<failure message="{long_value}"/></testcase></testsuite>',
            encoding="utf-8",
        )
        bounded_result = run_extractor(extractor, reports, bounded)
        assert bounded_result.returncode == 0, bounded_result.stderr
        bounded_row = json.loads(bounded_result.stdout)
        assert len(bounded_row["file"]) == 1_000
        assert len(bounded_row["classname"]) == 1_000
        assert len(bounded_row["name"]) == 1_000
        assert len(bounded_row["message"]) == 500

        linked_root = temp / "linked-reports"
        linked_root.symlink_to(reports, target_is_directory=True)
        rejected = run_extractor(extractor, linked_root, linked_root / "valid.xml")
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        linked_parent = temp / "linked-parent"
        linked_parent.symlink_to(temp, target_is_directory=True)
        rejected = run_extractor(
            extractor,
            linked_parent / "reports",
            linked_parent / "reports/valid.xml",
        )
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        junit_spec = importlib.util.spec_from_file_location(
            "extract_junit_ancestor_swap_contract",
            extractor,
        )
        assert junit_spec is not None and junit_spec.loader is not None
        junit_module = importlib.util.module_from_spec(junit_spec)
        junit_spec.loader.exec_module(junit_module)
        junit_anchor = temp / "junit-anchor"
        junit_reports = junit_anchor / "reports"
        junit_reports.mkdir(parents=True)
        anchored_junit = junit_reports / "results.xml"
        anchored_junit.write_text("<testsuite/>", encoding="utf-8")
        junit_attacker = temp / "junit-attacker"
        attacker_reports = junit_attacker / "reports"
        attacker_reports.mkdir(parents=True)
        (attacker_reports / "results.xml").write_text(
            "<testsuite/>",
            encoding="utf-8",
        )
        moved_junit_anchor = temp / "junit-anchor-original"
        original_junit_root_open = junit_module.open_trusted_directory
        junit_ancestor_swapped = False

        def swap_junit_ancestor_before_root_open(
            *args: object,
            **kwargs: object,
        ) -> int:
            nonlocal junit_ancestor_swapped
            if not junit_ancestor_swapped:
                junit_anchor.rename(moved_junit_anchor)
                junit_anchor.symlink_to(
                    junit_attacker,
                    target_is_directory=True,
                )
                junit_ancestor_swapped = True
            return original_junit_root_open(*args, **kwargs)

        junit_module.open_trusted_directory = (
            swap_junit_ancestor_before_root_open
        )
        try:
            try:
                junit_module.read_bounded_report(
                    junit_reports,
                    anchored_junit,
                )
            except ValueError as exc:
                assert "symlink" in str(exc).lower()
            else:
                raise AssertionError(
                    "ancestor swap before JUnit root-open must fail closed"
                )
        finally:
            junit_module.open_trusted_directory = original_junit_root_open
            if junit_anchor.is_symlink():
                junit_anchor.unlink()
            if moved_junit_anchor.exists():
                moved_junit_anchor.rename(junit_anchor)

        stable_junit = reports / "stable-read.xml"
        stable_junit_payload = (
            b'<testsuite><testcase name="stable">'
            b'<failure message="expected"/></testcase></testsuite>'
        )
        stable_junit.write_bytes(stable_junit_payload)
        stable_path, stable_data = junit_module.read_bounded_report(
            reports,
            stable_junit,
        )
        assert stable_path == stable_junit
        assert stable_data == stable_junit_payload

        concurrent_junit = reports / "concurrent.xml"
        original_junit_payload = (
            b'<testsuite><testcase name="original">'
            b'<failure message="original"/></testcase></testsuite>'
            + b" " * 70_000
        )
        truncated_junit_payload = b"<testsuite/>"
        concurrent_junit.write_bytes(original_junit_payload)
        concurrent_junit_metadata = concurrent_junit.stat()
        original_junit_read = junit_module.os.read
        junit_truncated = False

        def truncate_same_inode_junit_during_read(
            descriptor: int,
            byte_count: int,
        ) -> bytes:
            nonlocal junit_truncated
            if not junit_truncated:
                writer = os.open(concurrent_junit, os.O_WRONLY | os.O_TRUNC)
                try:
                    os.write(writer, truncated_junit_payload)
                    os.fsync(writer)
                finally:
                    os.close(writer)
                rewritten = concurrent_junit.stat()
                assert rewritten.st_ino == concurrent_junit_metadata.st_ino
                assert rewritten.st_size < concurrent_junit_metadata.st_size
                junit_truncated = True
            return original_junit_read(descriptor, byte_count)

        junit_module.os.read = truncate_same_inode_junit_during_read
        try:
            try:
                junit_module.read_bounded_report(
                    reports,
                    concurrent_junit,
                )
            except ValueError as exc:
                assert "changed while being read" in str(exc)
            else:
                raise AssertionError(
                    "same-inode JUnit rewrite/truncation must fail closed"
                )
        finally:
            junit_module.os.read = original_junit_read

        linked_report = reports / "linked.xml"
        linked_report.symlink_to(valid)
        rejected = run_extractor(extractor, reports, linked_report)
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        nested = reports / "nested"
        nested.mkdir()
        linked_component = reports / "linked-component"
        linked_component.symlink_to(nested, target_is_directory=True)
        nested_report = nested / "nested.xml"
        nested_report.write_text("<testsuite/>", encoding="utf-8")
        rejected = run_extractor(
            extractor, reports, linked_component / "nested.xml"
        )
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        outside = temp / "outside.xml"
        outside.write_text("<testsuite/>", encoding="utf-8")
        rejected = run_extractor(extractor, reports, outside)
        assert rejected.returncode != 0
        assert "outside the report root" in rejected.stderr.lower()

        fifo = reports / "report.fifo"
        os.mkfifo(fifo)
        rejected = run_extractor(extractor, reports, fifo)
        assert rejected.returncode != 0
        assert "regular file" in rejected.stderr.lower()

        oversized = reports / "oversized.xml"
        oversized.write_bytes(b"<testsuite>" + b"x" * (8 * 1024 * 1024))
        rejected = run_extractor(extractor, reports, oversized)
        assert rejected.returncode != 0
        assert "byte limit" in rejected.stderr.lower()

        for declaration in (
            b'<!DOCTYPE testsuite [<!ENTITY boom "boom">]><testsuite/>',
            b'<!ENTITY boom "boom"><testsuite/>',
        ):
            unsafe_xml = reports / "unsafe.xml"
            unsafe_xml.write_bytes(declaration)
            rejected = run_extractor(extractor, reports, unsafe_xml)
            assert rejected.returncode != 0
            assert "doctype/entity" in rejected.stderr.lower()

        utf16_unsafe = reports / "utf16-unsafe.xml"
        utf16_unsafe.write_bytes(
            (
                '<?xml version="1.0" encoding="UTF-16"?>'
                '<!DOCTYPE testsuite [<!ENTITY boom "expanded">]>'
                '<testsuite><testcase name="fails">'
                '<failure message="&boom;"/></testcase></testsuite>'
            ).encode("utf-16")
        )
        rejected = run_extractor(extractor, reports, utf16_unsafe)
        assert rejected.returncode != 0
        assert "utf-8" in rejected.stderr.lower(), rejected.stderr

        deeply_nested = reports / "deeply-nested.xml"
        deeply_nested.write_text(
            "<testsuite>" * 101
            + '<testcase name="too deep"/>'
            + "</testsuite>" * 101,
            encoding="utf-8",
        )
        started = time.monotonic()
        rejected = run_extractor(extractor, reports, deeply_nested)
        assert time.monotonic() - started < 15
        assert rejected.returncode != 0
        assert "depth limit" in rejected.stderr.lower(), rejected.stderr

        too_many_nodes = reports / "too-many-nodes.xml"
        too_many_nodes.write_text(
            "<testsuite>"
            + "<property/>" * 100_000
            + "</testsuite>",
            encoding="utf-8",
        )
        started = time.monotonic()
        rejected = run_extractor(extractor, reports, too_many_nodes)
        assert time.monotonic() - started < 15
        assert rejected.returncode != 0
        assert "node limit" in rejected.stderr.lower(), rejected.stderr

        near_depth_limit = reports / "near-depth-limit.xml"
        near_depth_limit.write_text(
            "<testsuite>" * 99
            + '<testcase name="depth guard"/>'
            + "</testsuite>" * 99,
            encoding="utf-8",
        )
        accepted = run_extractor(extractor, reports, near_depth_limit)
        assert accepted.returncode == 0, accepted.stderr

        near_node_limit = reports / "near-node-limit.xml"
        near_node_limit.write_text(
            "<testsuite>"
            + "<property/>" * 99_998
            + "</testsuite>",
            encoding="utf-8",
        )
        started = time.monotonic()
        accepted = run_extractor(extractor, reports, near_node_limit)
        assert time.monotonic() - started < 15
        assert accepted.returncode == 0, accepted.stderr

        contradictory_junit_reports = {
            "wrong-suite-tests.xml": (
                '<testsuite tests="0" failures="1">'
                '<testcase name="fails"><failure message="boom"/></testcase>'
                "</testsuite>"
            ),
            "wrong-suite-failures.xml": (
                '<testsuite tests="1" failures="0">'
                '<testcase name="fails"><failure message="boom"/></testcase>'
                "</testsuite>"
            ),
            "wrong-root-counters.xml": (
                '<testsuites tests="1" failures="0" errors="0" skipped="0">'
                '<testsuite tests="1" failures="1" errors="0" skipped="0">'
                '<testcase name="fails"><failure message="boom"/></testcase>'
                "</testsuite></testsuites>"
            ),
            "contradictory-testcase.xml": (
                '<testsuite tests="1" failures="1" errors="0" skipped="0">'
                '<testcase name="contradictory">'
                '<failure message="boom"/><skipped/>'
                "</testcase></testsuite>"
            ),
        }
        for name, content in contradictory_junit_reports.items():
            contradictory = reports / name
            contradictory.write_text(content, encoding="utf-8")
            rejected = run_extractor(extractor, reports, contradictory)
            assert rejected.returncode != 0, name
            assert "contradict" in rejected.stderr.lower(), rejected.stderr

        invalid_junit_hierarchy = {
            "wrapped-testcase.xml": (
                "<testsuite><wrapper><testcase name=\"hidden\">"
                "<failure message=\"boom\"/></testcase></wrapper></testsuite>"
            ),
            "wrapped-failure.xml": (
                "<testsuite><testcase name=\"hidden\"><wrapper>"
                "<failure message=\"boom\"/></wrapper></testcase></testsuite>"
            ),
        }
        for name, content in invalid_junit_hierarchy.items():
            invalid_hierarchy = reports / name
            invalid_hierarchy.write_text(content, encoding="utf-8")
            rejected = run_extractor(extractor, reports, invalid_hierarchy)
            assert rejected.returncode != 0, name
            assert "direct child" in rejected.stderr.lower(), rejected.stderr

        valid_counted_junit = reports / "valid-counted.xml"
        valid_counted_junit.write_text(
            '<testsuites tests="4" failures="1" errors="1" skipped="1">'
            '<testsuite tests="2" failures="1" errors="0" skipped="0">'
            '<testcase name="passes"/><testcase name="fails">'
            '<failure message="boom"/></testcase></testsuite>'
            '<testsuite tests="2" failures="0" errors="1" skipped="1">'
            '<testcase name="errors"><error message="crash"/></testcase>'
            '<testcase name="skips"><skipped/></testcase>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        valid_counted_result = run_extractor(
            extractor, reports, valid_counted_junit
        )
        assert valid_counted_result.returncode == 0, valid_counted_result.stderr
        assert [
            row["kind"]
            for row in map(
                json.loads, valid_counted_result.stdout.splitlines()
            )
        ] == ["failure", "error"]

        nested_order = reports / "nested-order.xml"
        nested_order.write_text(
            '<testsuite tests="3" failures="3">'
            '<testcase name="outer before"><failure message="before"/></testcase>'
            '<testsuite tests="1" failures="1">'
            '<testcase name="inner"><failure message="inner"/></testcase>'
            "</testsuite>"
            '<testcase name="outer after"><failure message="after"/></testcase>'
            "</testsuite>",
            encoding="utf-8",
        )
        nested_order_result = run_extractor(extractor, reports, nested_order)
        assert nested_order_result.returncode == 0, nested_order_result.stderr
        assert [
            json.loads(line)["name"]
            for line in nested_order_result.stdout.splitlines()
        ] == ["outer before", "outer after", "inner"]

    cypress_reader = CYPRESS_SKILL / "scripts/read-cypress-artifact.py"
    cypress_fixtures = CYPRESS_SKILL / "evals/files"
    mochawesome_result = run_cypress_reader(
        cypress_reader,
        "mochawesome",
        cypress_fixtures,
        cypress_fixtures / "mochawesome-selector-timeout.json",
    )
    assert mochawesome_result.returncode == 0, mochawesome_result.stderr
    mochawesome_payload = json.loads(mochawesome_result.stdout)
    mochawesome_rows = mochawesome_payload["failures"]
    submit_row = next(
        row for row in mochawesome_rows
        if row["title"] == "submits the contact form"
    )
    assert submit_row["file"] == "cypress/e2e/form.cy.ts"
    assert submit_row["error"].startswith("Timed out retrying")

    clean_result = run_cypress_reader(
        cypress_reader,
        "mochawesome",
        cypress_fixtures,
        cypress_fixtures / "mochawesome-clean.json",
    )
    assert clean_result.returncode == 0, clean_result.stderr
    clean_payload = json.loads(clean_result.stdout)
    assert clean_payload["failures"] == []
    assert clean_payload["stats"]["failures"] == 0

    run_result = run_cypress_reader(
        cypress_reader,
        "run-results",
        cypress_fixtures,
        cypress_fixtures / "cypress-run-results-retries.json",
    )
    assert run_result.returncode == 0, run_result.stderr
    retry_records = json.loads(run_result.stdout)
    assert retry_records[0]["file"] == "cypress/e2e/dashboard.cy.ts"
    assert retry_records[0]["attempts"] == [
        {"attempt": 0, "error": None, "state": "failed"},
        {"attempt": 1, "error": None, "state": "passed"},
    ]

    with tempfile.TemporaryDirectory(
        prefix="e2e-cypress-artifact-contract-",
    ) as temp_dir:
        temp = Path(temp_dir)
        reports = temp / "reports"
        reports.mkdir()
        for name, content, expected_error in (
            ("empty.json", b"", "invalid json"),
            ("empty-object.json", b"{}", "schema"),
            (
                "malformed.json",
                b'{"results":[{"file":"x","suites":{}}]}',
                "schema",
            ),
        ):
            artifact = reports / name
            artifact.write_bytes(content)
            rejected = run_cypress_reader(
                cypress_reader, "mochawesome", reports, artifact
            )
            assert rejected.returncode != 0, name
            assert expected_error in rejected.stderr.lower(), rejected.stderr

        malformed_run_results = reports / "malformed-run-results.json"
        malformed_run_results.write_text(
            '{"runs":[{"spec":{},"tests":[]}]}',
            encoding="utf-8",
        )
        rejected = run_cypress_reader(
            cypress_reader,
            "run-results",
            reports,
            malformed_run_results,
        )
        assert rejected.returncode != 0
        assert "schema" in rejected.stderr.lower()

        run_results_template = {
            "runs": [
                {
                    "spec": {"relative": "cypress/e2e/state.cy.ts"},
                    "tests": [
                        {
                            "title": ["state contract"],
                            "state": "passed",
                            "attempts": [{"state": "passed"}],
                        }
                    ],
                }
            ]
        }
        cypress_secret_text, cypress_secrets = adversarial_credentials(4000)
        secret_mochawesome = reports / "secret-mochawesome.json"
        secret_mochawesome.write_text(
            json.dumps(
                {
                    "stats": {
                        "suites": 0,
                        "tests": 1,
                        "passes": 0,
                        "pending": 0,
                        "failures": 1,
                        "skipped": 0,
                        "duration": 1,
                    },
                    "results": [
                        {
                            "file": "secret.cy.ts",
                            "tests": [
                                {
                                    "title": "redacts credentials",
                                    "fullTitle": "redacts credentials",
                                    "state": "failed",
                                    "pass": False,
                                    "fail": True,
                                    "pending": False,
                                    "skipped": False,
                                    "duration": 1,
                                    "err": {
                                        "message": cypress_secret_text,
                                        "estack": cypress_secret_text,
                                    },
                                    "uuid": "secret-test",
                                }
                            ],
                            "passes": [],
                            "failures": ["secret-test"],
                            "pending": [],
                            "skipped": [],
                            "suites": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        secret_mochawesome_result = run_cypress_reader(
            cypress_reader,
            "mochawesome",
            reports,
            secret_mochawesome,
        )
        assert secret_mochawesome_result.returncode == 0, (
            secret_mochawesome_result.stderr
        )
        assert_credentials_redacted(
            secret_mochawesome_result.stdout,
            cypress_secrets,
        )

        secret_run_results = reports / "secret-run-results.json"
        secret_run_results.write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "spec": {"relative": "secret.cy.ts"},
                            "tests": [
                                {
                                    "title": ["redacts credentials"],
                                    "state": "failed",
                                    "attempts": [
                                        {
                                            "state": "failed",
                                            "displayError": cypress_secret_text,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        secret_run_result = run_cypress_reader(
            cypress_reader,
            "run-results",
            reports,
            secret_run_results,
        )
        assert secret_run_result.returncode == 0, secret_run_result.stderr
        assert_credentials_redacted(
            secret_run_result.stdout,
            cypress_secrets,
        )

        contradictory_run_results = {
            "unknown-test-state.json": ("mystery", [{"state": "passed"}]),
            "unknown-attempt-state.json": (
                "passed",
                [{"state": "mystery"}],
            ),
            "empty-attempts.json": ("passed", []),
            "final-attempt-mismatch.json": (
                "passed",
                [{"state": "failed"}],
            ),
        }
        for name, (test_state, attempts) in contradictory_run_results.items():
            payload = json.loads(json.dumps(run_results_template))
            test = payload["runs"][0]["tests"][0]
            test["state"] = test_state
            test["attempts"] = attempts
            contradictory = reports / name
            contradictory.write_text(json.dumps(payload), encoding="utf-8")
            rejected = run_cypress_reader(
                cypress_reader, "run-results", reports, contradictory
            )
            assert rejected.returncode != 0, name
            assert "run-results" in rejected.stderr.lower(), rejected.stderr

        valid_run_result_states = reports / "valid-run-result-states.json"
        valid_run_result_states.write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "spec": {"relative": "cypress/e2e/states.cy.ts"},
                            "tests": [
                                {
                                    "title": ["passes on retry"],
                                    "state": "passed",
                                    "attempts": [
                                        {"state": "failed"},
                                        {"state": "passed"},
                                    ],
                                },
                                {
                                    "title": ["passes threshold strategy"],
                                    "state": "passed",
                                    "attempts": [
                                        {"state": "passed"},
                                        {"state": "failed"},
                                        {"state": "passed"},
                                    ],
                                },
                                {
                                    "title": ["pending"],
                                    "state": "pending",
                                    "attempts": [{"state": "pending"}],
                                },
                                {
                                    "title": ["skipped after retry"],
                                    "state": "skipped",
                                    "attempts": [
                                        {"state": "failed"},
                                        {"state": "skipped"},
                                    ],
                                },
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        valid_states = run_cypress_reader(
            cypress_reader, "run-results", reports, valid_run_result_states
        )
        assert valid_states.returncode == 0, valid_states.stderr

        strict_json_cases = {
            "duplicate-key.json": b'{"stats":{},"results":[],"results":[]}',
            "nan.json": b'{"stats":{},"results":[],"value":NaN}',
            "infinity.json": b'{"stats":{},"results":[],"value":Infinity}',
            "negative-infinity.json": (
                b'{"stats":{},"results":[],"value":-Infinity}'
            ),
            "bom.json": b'\xef\xbb\xbf{"stats":{},"results":[]}',
            "trailing.json": b'{"stats":{},"results":[]}{}',
        }
        for name, content in strict_json_cases.items():
            ambiguous = reports / name
            ambiguous.write_bytes(content)
            rejected = run_cypress_reader(
                cypress_reader, "mochawesome", reports, ambiguous
            )
            assert rejected.returncode != 0, name
            assert "json" in rejected.stderr.lower(), rejected.stderr

        valid_merged = reports / "valid-merged.json"
        valid_merged.write_text(
            json.dumps(
                {
                    "stats": {
                        "suites": 1,
                        "tests": 2,
                        "passes": 1,
                        "pending": 0,
                        "failures": 1,
                        "skipped": 0,
                        "duration": 12,
                        "testsRegistered": 2,
                    },
                    "results": [
                        {
                            "file": "direct.cy.ts",
                            "tests": [
                                {
                                    "title": "direct pass",
                                    "fullTitle": "direct pass",
                                    "state": "passed",
                                    "pass": True,
                                    "fail": False,
                                    "pending": False,
                                    "skipped": False,
                                    "duration": 2,
                                    "err": {},
                                    "uuid": "direct-pass",
                                }
                            ],
                            "passes": ["direct-pass"],
                            "failures": [],
                            "pending": [],
                            "skipped": [],
                            "suites": [
                                {
                                    "file": "nested.cy.ts",
                                    "tests": [
                                        {
                                            "title": "nested fail",
                                            "fullTitle": "nested fail",
                                            "state": "failed",
                                            "pass": False,
                                            "fail": True,
                                            "pending": False,
                                            "skipped": False,
                                            "duration": 10,
                                            "err": {
                                                "message": "failure",
                                                "estack": "stack",
                                            },
                                            "uuid": "nested-fail",
                                        }
                                    ],
                                    "passes": [],
                                    "failures": ["nested-fail"],
                                    "pending": [],
                                    "skipped": [],
                                    "suites": [],
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        valid_merged_result = run_cypress_reader(
            cypress_reader, "mochawesome", reports, valid_merged
        )
        assert valid_merged_result.returncode == 0, valid_merged_result.stderr
        valid_merged_payload = json.loads(valid_merged_result.stdout)
        assert valid_merged_payload["stats"]["tests"] == 2
        assert valid_merged_payload["failures"][0]["file"] == "nested.cy.ts"

        hook_only = reports / "hook-only.json"
        hook_only.write_text(
            json.dumps(
                {
                    "stats": {
                        "suites": 1,
                        "tests": 0,
                        "passes": 0,
                        "pending": 0,
                        "failures": 0,
                        "skipped": 0,
                        "duration": 5,
                        "other": 1,
                        "hasOther": True,
                    },
                    "results": [
                        {
                            "file": "hooks.cy.ts",
                            "tests": [],
                            "passes": [],
                            "failures": [],
                            "pending": [],
                            "skipped": [],
                            "suites": [
                                {
                                    "file": "hooks.cy.ts",
                                    "tests": [],
                                    "passes": [],
                                    "failures": [],
                                    "pending": [],
                                    "skipped": [],
                                    "beforeHooks": [
                                        {
                                            "title": '"before all" hook',
                                            "fullTitle": 'suite "before all" hook',
                                            "state": "failed",
                                            "pass": False,
                                            "fail": True,
                                            "pending": False,
                                            "skipped": False,
                                            "isHook": True,
                                            "duration": 5,
                                            "err": {
                                                "message": "database seed failed",
                                                "estack": "seed stack",
                                            },
                                        }
                                    ],
                                    "suites": [],
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        hook_only_result = run_cypress_reader(
            cypress_reader, "mochawesome", reports, hook_only
        )
        assert hook_only_result.returncode == 0, hook_only_result.stderr
        hook_rows = json.loads(hook_only_result.stdout)["failures"]
        assert hook_rows == [
            {
                "duration": 5,
                "error": "database seed failed",
                "file": "hooks.cy.ts",
                "fullTitle": 'suite "before all" hook',
                "hook": "beforeHooks",
                "screenshots": [],
                "stack": "seed stack",
                "state": "failed",
                "title": '"before all" hook',
            }
        ]

        contradictory_mochawesome_tests = {
            "flag-state-mismatch.json": {
                "title": "state mismatch",
                "fullTitle": "state mismatch",
                "state": "passed",
                "pass": False,
                "fail": True,
                "pending": False,
                "duration": 1,
                "err": {"message": "boom"},
            },
            "failed-without-error.json": {
                "title": "missing error",
                "fullTitle": "missing error",
                "state": "failed",
                "pass": False,
                "fail": True,
                "pending": False,
                "duration": 1,
                "err": {},
            },
            "passed-with-error.json": {
                "title": "unexpected error",
                "fullTitle": "unexpected error",
                "state": "passed",
                "pass": True,
                "fail": False,
                "pending": False,
                "duration": 1,
                "err": {"message": "boom"},
            },
        }
        for name, test in contradictory_mochawesome_tests.items():
            contradictory = reports / name
            is_failed = bool(test["fail"])
            contradictory.write_text(
                json.dumps(
                    {
                        "stats": {
                            "suites": 0,
                            "tests": 1,
                            "passes": 0 if is_failed else 1,
                            "pending": 0,
                            "failures": 1 if is_failed else 0,
                            "skipped": 0,
                            "duration": 1,
                            "passPercent": 0 if is_failed else 100,
                            "pendingPercent": 0,
                        },
                        "results": [
                            {
                                "file": "contradictory.cy.ts",
                                "tests": [test],
                                "suites": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rejected = run_cypress_reader(
                cypress_reader, "mochawesome", reports, contradictory
            )
            assert rejected.returncode != 0, name
            assert "mochawesome" in rejected.stderr.lower(), rejected.stderr

        wrong_percent = reports / "wrong-percent.json"
        wrong_percent_payload = json.loads(valid_merged.read_text(encoding="utf-8"))
        wrong_percent_payload["stats"]["passPercent"] = 99
        wrong_percent_payload["stats"]["pendingPercent"] = 0
        wrong_percent.write_text(
            json.dumps(wrong_percent_payload), encoding="utf-8"
        )
        rejected = run_cypress_reader(
            cypress_reader, "mochawesome", reports, wrong_percent
        )
        assert rejected.returncode != 0
        assert "passpercent" in rejected.stderr.lower(), rejected.stderr

        wrong_suite_ids = reports / "wrong-suite-ids.json"
        wrong_suite_ids_payload = json.loads(
            valid_merged.read_text(encoding="utf-8")
        )
        wrong_suite_ids_payload["results"][0]["suites"][0]["failures"] = [
            "different-test"
        ]
        wrong_suite_ids.write_text(
            json.dumps(wrong_suite_ids_payload), encoding="utf-8"
        )
        rejected = run_cypress_reader(
            cypress_reader, "mochawesome", reports, wrong_suite_ids
        )
        assert rejected.returncode != 0
        assert "contradicts test flags" in rejected.stderr.lower()

        valid_pending_skipped = reports / "valid-pending-skipped.json"
        valid_pending_skipped.write_text(
            json.dumps(
                {
                    "stats": {
                        "suites": 0,
                        "tests": 1,
                        "passes": 0,
                        "pending": 1,
                        "failures": 0,
                        "skipped": 1,
                        "duration": 0,
                        "testsRegistered": 2,
                        "passPercent": 0,
                        "pendingPercent": 50,
                        "other": 0,
                        "hasOther": False,
                        "hasSkipped": True,
                    },
                    "results": [
                        {
                            "file": "states.cy.ts",
                            "tests": [
                                {
                                    "title": "pending",
                                    "fullTitle": "pending",
                                    "pass": False,
                                    "fail": False,
                                    "pending": True,
                                    "skipped": False,
                                    "err": {},
                                    "uuid": "pending-test",
                                },
                                {
                                    "title": "skipped",
                                    "fullTitle": "skipped",
                                    "pass": False,
                                    "fail": False,
                                    "pending": False,
                                    "skipped": True,
                                    "err": {},
                                    "uuid": "skipped-test",
                                },
                            ],
                            "suites": [],
                            "passes": [],
                            "failures": [],
                            "pending": ["pending-test"],
                            "skipped": ["skipped-test"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        valid_states_result = run_cypress_reader(
            cypress_reader, "mochawesome", reports, valid_pending_skipped
        )
        assert valid_states_result.returncode == 0, valid_states_result.stderr

        invalid_stats_cases = {
            "negative-stats.json": -1,
            "string-stats.json": "1",
            "boolean-stats.json": True,
        }
        for name, invalid_count in invalid_stats_cases.items():
            invalid_stats = reports / name
            invalid_stats.write_text(
                json.dumps(
                    {
                        "stats": {
                            "suites": 0,
                            "tests": invalid_count,
                            "passes": 0,
                            "pending": 0,
                            "failures": 0,
                            "skipped": 0,
                            "duration": 0,
                        },
                        "results": [],
                    }
                ),
                encoding="utf-8",
            )
            rejected = run_cypress_reader(
                cypress_reader, "mochawesome", reports, invalid_stats
            )
            assert rejected.returncode != 0, name
            assert "nonnegative integer" in rejected.stderr.lower()

        for name, stats in (
            (
                "contradictory-tests.json",
                {
                    "suites": 1,
                    "tests": 0,
                    "passes": 0,
                    "pending": 0,
                    "failures": 0,
                    "skipped": 0,
                    "duration": 12,
                },
            ),
            (
                "contradictory-failures.json",
                {
                    "suites": 1,
                    "tests": 2,
                    "passes": 2,
                    "pending": 0,
                    "failures": 0,
                    "skipped": 0,
                    "duration": 12,
                },
            ),
        ):
            contradictory = reports / name
            contradictory.write_text(
                json.dumps(
                    {
                        "stats": stats,
                        "results": json.loads(
                            valid_merged.read_text(encoding="utf-8")
                        )["results"],
                    }
                ),
                encoding="utf-8",
            )
            rejected = run_cypress_reader(
                cypress_reader, "mochawesome", reports, contradictory
            )
            assert rejected.returncode != 0, name
            assert "contradicts parsed" in rejected.stderr.lower()

        deep = reports / "deep.json"
        deep.write_text("[" * 110 + "0" + "]" * 110, encoding="utf-8")
        rejected = run_cypress_reader(
            cypress_reader, "mochawesome", reports, deep
        )
        assert rejected.returncode != 0
        assert "depth limit" in rejected.stderr.lower()

        valid = reports / "valid.json"
        valid.write_text(
            '{"stats":{},"results":[{"file":"spec.cy.ts","tests":[],'
            '"suites":[]}]}',
            encoding="utf-8",
        )
        linked = reports / "linked.json"
        linked.symlink_to(valid)
        rejected = run_cypress_reader(
            cypress_reader, "mochawesome", reports, linked
        )
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        fifo = reports / "report.fifo"
        os.mkfifo(fifo)
        rejected = run_cypress_reader(
            cypress_reader, "mochawesome", reports, fifo
        )
        assert rejected.returncode != 0
        assert "regular file" in rejected.stderr.lower()

        oversized = reports / "oversized.json"
        with oversized.open("wb") as oversized_file:
            oversized_file.truncate(8 * 1024 * 1024 + 1)
        rejected = run_cypress_reader(
            cypress_reader, "mochawesome", reports, oversized
        )
        assert rejected.returncode != 0
        assert "byte limit" in rejected.stderr.lower()

        screenshots = temp / "screenshots"
        screenshots.mkdir()
        screenshot = screenshots / "failure.png"
        screenshot.write_bytes(b"\x89PNG\r\n\x1a\nbounded")
        media_result = run_cypress_reader(
            cypress_reader, "media", screenshots, screenshot
        )
        assert media_result.returncode == 0, media_result.stderr
        media = json.loads(media_result.stdout)
        assert media["kind"] == "png"
        assert media["size"] == len(b"\x89PNG\r\n\x1a\nbounded")
        assert media["sha256"] == hashlib.sha256(
            b"\x89PNG\r\n\x1a\nbounded"
        ).hexdigest()
        snapshot = Path(media["path"])
        snapshot_directory = Path(media["snapshot_directory"])
        assert snapshot != screenshot
        assert snapshot.parent == snapshot_directory
        assert snapshot.read_bytes() == b"\x89PNG\r\n\x1a\nbounded"
        assert stat.S_IMODE(snapshot.stat().st_mode) == stat.S_IRUSR
        assert stat.S_IMODE(snapshot_directory.stat().st_mode) == (
            stat.S_IRWXU
        )
        assert media["lifecycle"] == (
            "temporary owner-only snapshot; delete snapshot_directory "
            "after the viewer closes"
        )

        reader_spec = importlib.util.spec_from_file_location(
            "read_cypress_artifact_media_race_contract",
            cypress_reader,
        )
        assert reader_spec is not None and reader_spec.loader is not None
        reader_module = importlib.util.module_from_spec(reader_spec)
        reader_spec.loader.exec_module(reader_module)

        cypress_anchor = temp / "cypress-anchor"
        cypress_reports = cypress_anchor / "reports"
        cypress_reports.mkdir(parents=True)
        anchored_report = cypress_reports / "results.json"
        anchored_report.write_bytes(b'{"stats":{},"results":[]}')
        cypress_attacker = temp / "cypress-attacker"
        attacker_reports = cypress_attacker / "reports"
        attacker_reports.mkdir(parents=True)
        (attacker_reports / "results.json").write_bytes(
            b'{"stats":{},"results":[]}'
        )
        moved_anchor = temp / "cypress-anchor-original"
        original_open_trusted_directory = (
            reader_module.open_trusted_directory
        )
        cypress_ancestor_swapped = False

        def swap_cypress_ancestor_before_root_open(
            *args: object,
            **kwargs: object,
        ) -> int:
            nonlocal cypress_ancestor_swapped
            if not cypress_ancestor_swapped:
                cypress_anchor.rename(moved_anchor)
                cypress_anchor.symlink_to(
                    cypress_attacker,
                    target_is_directory=True,
                )
                cypress_ancestor_swapped = True
            return original_open_trusted_directory(*args, **kwargs)

        reader_module.open_trusted_directory = (
            swap_cypress_ancestor_before_root_open
        )
        try:
            try:
                reader_module.read_artifact(
                    cypress_reports,
                    anchored_report,
                    8 * 1024 * 1024,
                )
            except ValueError as exc:
                assert "symlink" in str(exc).lower()
            else:
                raise AssertionError(
                    "ancestor swap before Cypress root-open must fail closed"
                )
        finally:
            reader_module.open_trusted_directory = (
                original_open_trusted_directory
            )
            if cypress_anchor.is_symlink():
                cypress_anchor.unlink()
            if moved_anchor.exists():
                moved_anchor.rename(cypress_anchor)

        concurrent_cypress_json = reports / "concurrent.json"
        original_cypress_json = (
            b'{"stats":{},"results":[]}' + b" " * 70_000
        )
        replacement_cypress_json = (
            b'{"stats":{},"results":[]}' + b"\n" + b" " * 69_999
        )
        assert len(original_cypress_json) == len(replacement_cypress_json)
        concurrent_cypress_json.write_bytes(original_cypress_json)
        cypress_json_metadata = concurrent_cypress_json.stat()
        original_cypress_read = reader_module.os.read
        cypress_json_mutated = False

        def rewrite_cypress_json_during_read(
            descriptor: int,
            byte_count: int,
        ) -> bytes:
            nonlocal cypress_json_mutated
            if not cypress_json_mutated:
                time.sleep(0.01)
                writer = os.open(concurrent_cypress_json, os.O_WRONLY)
                try:
                    os.pwrite(writer, replacement_cypress_json, 0)
                    os.fsync(writer)
                finally:
                    os.close(writer)
                os.utime(
                    concurrent_cypress_json,
                    ns=(
                        cypress_json_metadata.st_atime_ns,
                        cypress_json_metadata.st_mtime_ns,
                    ),
                )
                rewritten = concurrent_cypress_json.stat()
                assert rewritten.st_ino == cypress_json_metadata.st_ino
                assert rewritten.st_size == cypress_json_metadata.st_size
                assert rewritten.st_mtime_ns == cypress_json_metadata.st_mtime_ns
                cypress_json_mutated = True
            return original_cypress_read(descriptor, byte_count)

        reader_module.os.read = rewrite_cypress_json_during_read
        try:
            try:
                reader_module.read_artifact(
                    reports,
                    concurrent_cypress_json,
                    8 * 1024 * 1024,
                )
            except ValueError as exc:
                assert "changed while being read" in str(exc)
            else:
                raise AssertionError(
                    "same-inode same-size Cypress JSON rewrite with restored "
                    "mtime must fail closed"
                )
        finally:
            reader_module.os.read = original_cypress_read

        race_source = screenshots / "race.png"
        original_media = b"\x89PNG\r\n\x1a\nvalidated-original"
        attacker_media = b"\x89PNG\r\n\x1a\nattacker-replacement"
        race_source.write_bytes(original_media)
        attacker = screenshots / "attacker.png"
        attacker.write_bytes(attacker_media)
        moved_source = screenshots / "race-original.png"
        original_open = reader_module.open_artifact_descriptor

        @contextmanager
        def replace_path_after_open(*args: object, **kwargs: object):
            with original_open(*args, **kwargs) as opened:
                race_source.rename(moved_source)
                race_source.symlink_to(attacker)
                yield opened

        reader_module.open_artifact_descriptor = replace_path_after_open
        try:
            reader_module.media_metadata(
                screenshots,
                race_source,
            )
        except ValueError as exc:
            assert "changed while being read" in str(exc)
        else:
            raise AssertionError(
                "media source path replacement must fail closed"
            )
        race_source.unlink()
        moved_source.rename(race_source)

        concurrent_media = screenshots / "concurrent.png"
        original_concurrent_media = (
            b"\x89PNG\r\n\x1a\n"
            + b"a" * 70_000
        )
        replacement_concurrent_media = (
            b"\x89PNG\r\n\x1a\n"
            + b"b" * 70_000
        )
        concurrent_media.write_bytes(original_concurrent_media)
        concurrent_media_metadata = concurrent_media.stat()
        original_media_read = reader_module.os.read
        original_mkdtemp = reader_module.tempfile.mkdtemp
        media_read_count = 0
        media_snapshot_directories: list[Path] = []

        def rewrite_media_during_read(
            descriptor: int,
            byte_count: int,
        ) -> bytes:
            nonlocal media_read_count
            media_read_count += 1
            if media_read_count == 2:
                time.sleep(0.01)
                writer = os.open(concurrent_media, os.O_WRONLY)
                try:
                    os.pwrite(writer, replacement_concurrent_media, 0)
                    os.fsync(writer)
                finally:
                    os.close(writer)
                os.utime(
                    concurrent_media,
                    ns=(
                        concurrent_media_metadata.st_atime_ns,
                        concurrent_media_metadata.st_mtime_ns,
                    ),
                )
                rewritten = concurrent_media.stat()
                assert rewritten.st_ino == concurrent_media_metadata.st_ino
                assert rewritten.st_size == concurrent_media_metadata.st_size
                assert (
                    rewritten.st_mtime_ns
                    == concurrent_media_metadata.st_mtime_ns
                )
            return original_media_read(descriptor, byte_count)

        def tracked_media_mkdtemp(*args: object, **kwargs: object) -> str:
            kwargs["dir"] = temp
            directory = original_mkdtemp(*args, **kwargs)
            media_snapshot_directories.append(Path(directory))
            return directory

        reader_module.os.read = rewrite_media_during_read
        reader_module.tempfile.mkdtemp = tracked_media_mkdtemp
        try:
            try:
                reader_module.media_metadata(
                    screenshots,
                    concurrent_media,
                )
            except ValueError as exc:
                assert "changed while being read" in str(exc)
            else:
                raise AssertionError(
                    "same-inode same-size Cypress media rewrite with restored "
                    "mtime must fail closed"
                )
        finally:
            reader_module.os.read = original_media_read
            reader_module.tempfile.mkdtemp = original_mkdtemp
        assert media_snapshot_directories
        assert all(
            not directory.exists()
            for directory in media_snapshot_directories
        )

        linked_screenshot = screenshots / "linked.png"
        linked_screenshot.symlink_to(screenshot)
        rejected = run_cypress_reader(
            cypress_reader, "media", screenshots, linked_screenshot
        )
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        invalid_png = screenshots / "invalid.png"
        invalid_png.write_bytes(b"not-a-png")
        rejected = run_cypress_reader(
            cypress_reader, "media", screenshots, invalid_png
        )
        assert rejected.returncode != 0
        assert "invalid signature" in rejected.stderr.lower()

        videos = temp / "videos"
        videos.mkdir()
        video = videos / "run.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00")
        video_result = run_cypress_reader(
            cypress_reader, "media", videos, video
        )
        assert video_result.returncode == 0, video_result.stderr
        video_media = json.loads(video_result.stdout)
        assert video_media["kind"] == "mp4"
        video_snapshot = Path(video_media["path"])
        video_snapshot_directory = Path(
            video_media["snapshot_directory"]
        )
        assert video_snapshot.read_bytes() == video.read_bytes()

        downloaded_screenshots = temp / "cypress/reports/screenshots/spec"
        downloaded_screenshots.mkdir(parents=True)
        downloaded_screenshot = downloaded_screenshots / "failure.png"
        downloaded_screenshot.write_bytes(b"\x89PNG\r\n\x1a\ndownloaded")
        downloaded_png_result = run_cypress_reader(
            cypress_reader,
            "media",
            temp / "cypress/reports/screenshots",
            downloaded_screenshot,
        )
        assert downloaded_png_result.returncode == 0, downloaded_png_result.stderr
        downloaded_png = json.loads(downloaded_png_result.stdout)
        assert downloaded_png["kind"] == "png"

        downloaded_videos = temp / "cypress/reports/videos"
        downloaded_videos.mkdir()
        downloaded_video = downloaded_videos / "spec.mp4"
        downloaded_video.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00")
        downloaded_mp4_result = run_cypress_reader(
            cypress_reader,
            "media",
            downloaded_videos,
            downloaded_video,
        )
        assert downloaded_mp4_result.returncode == 0, downloaded_mp4_result.stderr
        downloaded_mp4 = json.loads(downloaded_mp4_result.stdout)
        assert downloaded_mp4["kind"] == "mp4"

        for media_path, media_directory in (
            (snapshot, snapshot_directory),
            (video_snapshot, video_snapshot_directory),
            (
                Path(downloaded_png["path"]),
                Path(downloaded_png["snapshot_directory"]),
            ),
            (
                Path(downloaded_mp4["path"]),
                Path(downloaded_mp4["snapshot_directory"]),
            ),
        ):
            media_path.unlink()
            media_directory.rmdir()

    cypress_text = (CYPRESS_SKILL / "SKILL.md").read_text(encoding="utf-8")
    cypress_flat = " ".join(cypress_text.split())
    for module_name, script_name in (
        (
            "extract_junit_failures_contract",
            "extract-junit-failures.py",
        ),
        (
            "read_cypress_artifact_contract",
            "read-cypress-artifact.py",
        ),
    ):
        script = CYPRESS_SKILL / f"scripts/{script_name}"
        module_spec = importlib.util.spec_from_file_location(
            module_name,
            script,
        )
        assert module_spec is not None and module_spec.loader is not None
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        original_no_follow = getattr(module.os, "O_NOFOLLOW", None)
        original_supports_dir_fd = module.os.supports_dir_fd
        try:
            module.os.O_NOFOLLOW = None
            module.os.supports_dir_fd = set()
            try:
                module.require_secure_descriptor_support()
            except ValueError as exc:
                assert "requires POSIX descriptor-relative no-follow" in str(exc)
                assert "WSL" in str(exc)
            else:
                raise AssertionError("unsupported platform must fail closed")
        finally:
            if original_no_follow is None:
                delattr(module.os, "O_NOFOLLOW")
            else:
                module.os.O_NOFOLLOW = original_no_follow
            module.os.supports_dir_fd = original_supports_dir_fd
    assert "npx mochawesome-merge" not in cypress_text
    assert "node_modules/.bin/mochawesome-merge" in cypress_text
    assert "publish-mochawesome-report.py" in cypress_text
    assert "> cypress/reports/merged.json" not in cypress_text
    assert "node_modules/.bin/cypress" in cypress_text
    assert_no_unguarded_npx(cypress_text, "cypress")
    assert "extract-junit-failures.py" in cypress_text
    assert "run-artifact-reader.sh" in cypress_flat
    assert "-- mochawesome" in cypress_flat
    assert "-- run-results" in cypress_flat
    assert "-- media" in cypress_flat
    assert "temporary owner-only snapshot" in cypress_text
    assert "never reopen the original media path" in cypress_text
    assert "delete the exact `snapshot_directory`" in cypress_flat
    assert "**F-code / confidence:**" in cypress_text
    assert "**Diagnosis axis:** product regression | test defect | unknown" in cypress_text
    assert "**Product impact:**" in cypress_text
    assert "**Test-reliability urgency:**" in cypress_text
    assert "**Test-quality severity:**" in cypress_text
    assert (
        '- **Error excerpt source:** `bundled reader` | '
        '`safely redacted direct input` | `unavailable placeholder`'
        in cypress_text
    )
    assert (
        '- **Error excerpt:** `"<sanitized bounded excerpt or unavailable '
        'placeholder, max 500 characters>"`'
        in cypress_text
    )
    assert "- **Error:** `Expected to find element" not in cypress_text
    assert "Every reported error excerpt must be a quoted, sanitized excerpt" in cypress_flat
    assert "at most 500 Unicode characters" in cypress_flat
    assert "only from the bundled reader output" in cypress_flat
    assert "Every finding must also label the excerpt's actual provenance" in cypress_flat
    assert "Use `bundled reader` only for text emitted by the" in cypress_flat
    assert "The label must never claim a bundled reader" in cypress_flat
    assert "with source `unavailable placeholder`" in cypress_flat
    assert "Never truncate first" in cypress_flat
    assert "Never pass raw artifact text or an unredacted directly supplied" in cypress_flat
    assert (
        '"[error excerpt unavailable: safe redaction not verified]"'
        in cypress_text
    )
    assert "Apply P0/P1/P2 only to confirmed test-quality defects" in cypress_text
    assert "never map those codes to P2 before the" in cypress_flat
    assert "P2:** Consistent failures" not in cypress_text
    assert "cat cypress/reports" not in cypress_text
    assert "| jq" not in cypress_text
    assert "require('./cypress/reports" not in cypress_text
    assert "allow_nan=False" in cypress_reader.read_text(encoding="utf-8")
    assert "must be nonnegative integers" in cypress_text
    assert "contradictory merged reports fail" in cypress_text
    assert "--report-root cypress/reports" in cypress_flat
    assert "8 MiB" in cypress_text
    assert "DOCTYPE" in cypress_text
    assert "ENTITY" in cypress_text
    assert "Never re-click a non-idempotent control" in cypress_text
    assert "submit, payment, delete, registration, or toggle" in cypress_text
    assert "**Execution safety gate (before any Cypress test command):**" in cypress_text
    assert "`local/disposable`" in cypress_text
    assert "explicitly approved non-production test environment" in cypress_text
    assert "production, shared, or unknown" in cypress_text
    assert "replay non-idempotent writes" in cypress_text
    assert "regular, non-symlink file" in cypress_text
    assert "require POSIX descriptor-relative no-follow APIs" in cypress_text
    assert "inside WSL" in cypress_text
    assert "at most 128 reports and 16 MiB total input" in cypress_text
    assert "before emitting atomic JSONL" in cypress_text
    assert "10,000 rows and" in cypress_text
    assert "8 MiB of serialized UTF-8" in cypress_text
    assert "canonical `cypress/reports/` root" in cypress_flat
    assert "Before any command creates or replaces a report artifact" in cypress_text
    assert "any existing component beneath" in cypress_text
    assert "Never publish a report with raw shell redirection" in cypress_flat
    assert "cypress/reports/screenshots/" in cypress_text
    assert "cypress/reports/videos/" in cypress_text
    assert "**Repository execution gate:**" in cypress_text
    assert "explicitly trusted this repository" in cypress_text
    assert "approved the exact command line" in cypress_flat
    assert "General approval to diagnose, reproduce" in cypress_flat
    assert "--config retries=0" in cypress_text
    assert "system-boundary effects are idempotent" in cypress_text
    for artifact in (
        "mochawesome JSON",
        "merged JSON",
        "`run-results.json`",
        "JUnit XML",
    ):
        assert artifact in cypress_text, f"missing Cypress artifact guard: {artifact}"

    playwright_text = PLAYWRIGHT_SKILL.read_text(encoding="utf-8")
    playwright_flat = " ".join(playwright_text.split())
    playwright_reader = (
        ROOT / "skills/playwright-debugger/scripts/read-playwright-artifact.py"
    )
    reader_spec = importlib.util.spec_from_file_location(
        "read_playwright_artifact_contract",
        playwright_reader,
    )
    assert reader_spec is not None and reader_spec.loader is not None
    reader_module = importlib.util.module_from_spec(reader_spec)
    reader_spec.loader.exec_module(reader_module)
    original_no_follow = getattr(reader_module.os, "O_NOFOLLOW", None)
    original_supports_dir_fd = reader_module.os.supports_dir_fd
    try:
        reader_module.os.O_NOFOLLOW = None
        reader_module.os.supports_dir_fd = set()
        try:
            reader_module.require_secure_descriptor_support()
        except ValueError as exc:
            assert "requires POSIX descriptor-relative no-follow" in str(exc)
            assert "WSL" in str(exc)
        else:
            raise AssertionError("unsupported platform must fail closed")
    finally:
        if original_no_follow is None:
            delattr(reader_module.os, "O_NOFOLLOW")
        else:
            reader_module.os.O_NOFOLLOW = original_no_follow
        reader_module.os.supports_dir_fd = original_supports_dir_fd
    assert "requires POSIX descriptor-relative no-follow APIs" in playwright_text
    assert "inside WSL" in playwright_text
    with tempfile.TemporaryDirectory(
        prefix="e2e-playwright-artifact-contract-",
    ) as temp_dir:
        temp = Path(temp_dir)
        reports = temp / "playwright-report"
        reports.mkdir()
        playwright_anchor = temp / "playwright-anchor"
        anchored_reports = playwright_anchor / "playwright-report"
        anchored_reports.mkdir(parents=True)
        anchored_report = anchored_reports / "results.json"
        anchored_report.write_bytes(b'{"suites":[]}')
        playwright_attacker = temp / "playwright-attacker"
        attacker_reports = playwright_attacker / "playwright-report"
        attacker_reports.mkdir(parents=True)
        (attacker_reports / "results.json").write_bytes(b'{"suites":[]}')
        moved_anchor = temp / "playwright-anchor-original"
        original_open_trusted_directory = (
            reader_module.open_trusted_directory
        )
        playwright_ancestor_swapped = False

        def swap_playwright_ancestor_before_root_open(
            *args: object,
            **kwargs: object,
        ) -> int:
            nonlocal playwright_ancestor_swapped
            if not playwright_ancestor_swapped:
                playwright_anchor.rename(moved_anchor)
                playwright_anchor.symlink_to(
                    playwright_attacker,
                    target_is_directory=True,
                )
                playwright_ancestor_swapped = True
            return original_open_trusted_directory(*args, **kwargs)

        reader_module.open_trusted_directory = (
            swap_playwright_ancestor_before_root_open
        )
        try:
            try:
                reader_module.read_bounded_file(
                    anchored_reports,
                    anchored_report,
                    8 * 1024 * 1024,
                )
            except ValueError as exc:
                assert "symlink" in str(exc).lower()
            else:
                raise AssertionError(
                    "ancestor swap before Playwright root-open must fail closed"
                )
        finally:
            reader_module.open_trusted_directory = (
                original_open_trusted_directory
            )
            if playwright_anchor.is_symlink():
                playwright_anchor.unlink()
            if moved_anchor.exists():
                moved_anchor.rename(playwright_anchor)

        concurrent_report = reports / "concurrent-results.json"
        original_payload = b'{"suites":[]}' + b" " * 70_000
        replacement_payload = b'{"suites":[]}' + b"\n" + b" " * 69_999
        assert len(original_payload) == len(replacement_payload)
        concurrent_report.write_bytes(original_payload)
        original_metadata = concurrent_report.stat()
        original_read = reader_module.os.read
        mutation_completed = False

        def mutate_same_inode_during_read(
            descriptor: int,
            byte_count: int,
        ) -> bytes:
            nonlocal mutation_completed
            if not mutation_completed:
                time.sleep(0.01)
                writer = os.open(concurrent_report, os.O_WRONLY)
                try:
                    os.pwrite(writer, replacement_payload, 0)
                    os.fsync(writer)
                finally:
                    os.close(writer)
                os.utime(
                    concurrent_report,
                    ns=(
                        original_metadata.st_atime_ns,
                        original_metadata.st_mtime_ns,
                    ),
                )
                rewritten = concurrent_report.stat()
                assert rewritten.st_ino == original_metadata.st_ino
                assert rewritten.st_size == original_metadata.st_size
                assert rewritten.st_mtime_ns == original_metadata.st_mtime_ns
                mutation_completed = True
            return original_read(descriptor, byte_count)

        reader_module.os.read = mutate_same_inode_during_read
        try:
            try:
                reader_module.read_bounded_file(
                    reports,
                    concurrent_report,
                    8 * 1024 * 1024,
                )
            except ValueError as exc:
                assert "changed while being read" in str(exc)
            else:
                raise AssertionError(
                    "same-inode same-size Playwright rewrite with restored "
                    "mtime must fail closed"
                )
        finally:
            reader_module.os.read = original_read

        media_payloads = {
            "failure.png": b"\x89PNG\r\n\x1a\nplaywright-png",
            "failure.jpeg": b"\xff\xd8\xff\xe0playwright-jpeg",
            "video.webm": (
                b"\x1aE\xdf\xa3\x9fB\x82\x84webm"
                b"B\x87\x81\x02B\x85\x81\x02"
            ),
        }
        media_snapshots: list[tuple[Path, Path]] = []
        for name, payload in media_payloads.items():
            artifact = reports / name
            artifact.write_bytes(payload)
            result = run_playwright_reader(
                playwright_reader,
                "media",
                reports,
                artifact,
            )
            assert result.returncode == 0, result.stderr
            media = json.loads(result.stdout)
            expected_kind = (
                "jpeg"
                if artifact.suffix == ".jpeg"
                else artifact.suffix.removeprefix(".")
            )
            assert media["kind"] == expected_kind
            assert media["size"] == len(payload)
            assert media["sha256"] == hashlib.sha256(payload).hexdigest()
            snapshot = Path(media["path"])
            snapshot_directory = Path(media["snapshot_directory"])
            assert snapshot != artifact
            assert snapshot.parent == snapshot_directory
            assert snapshot.read_bytes() == payload
            assert stat.S_IMODE(snapshot.stat().st_mode) == stat.S_IRUSR
            assert stat.S_IMODE(snapshot_directory.stat().st_mode) == (
                stat.S_IRWXU
            )
            assert media["lifecycle"] == (
                "temporary owner-only read-only snapshot; delete "
                "snapshot_directory after the viewer closes"
            )
            media_snapshots.append((snapshot, snapshot_directory))

        linked_media = reports / "linked.png"
        linked_media.symlink_to(reports / "failure.png")
        rejected = run_playwright_reader(
            playwright_reader,
            "media",
            reports,
            linked_media,
        )
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        path_swap_source = reports / "path-swap.png"
        path_swap_original = b"\x89PNG\r\n\x1a\nvalidated-original"
        path_swap_attacker = b"\x89PNG\r\n\x1a\nattacker-replacement"
        path_swap_source.write_bytes(path_swap_original)
        attacker_media = reports / "attacker.png"
        attacker_media.write_bytes(path_swap_attacker)
        moved_path_swap_source = reports / "path-swap-original.png"
        original_open_artifact = reader_module.open_artifact_descriptor

        @contextmanager
        def replace_playwright_media_path_after_open(
            *args: object,
            **kwargs: object,
        ):
            with original_open_artifact(*args, **kwargs) as opened:
                path_swap_source.rename(moved_path_swap_source)
                path_swap_source.symlink_to(attacker_media)
                yield opened

        reader_module.open_artifact_descriptor = (
            replace_playwright_media_path_after_open
        )
        try:
            try:
                reader_module.media_metadata(reports, path_swap_source)
            except ValueError as exc:
                assert "changed while being read" in str(exc)
            else:
                raise AssertionError(
                    "Playwright media source path replacement must fail closed"
                )
        finally:
            reader_module.open_artifact_descriptor = original_open_artifact
            if path_swap_source.is_symlink():
                path_swap_source.unlink()
            if moved_path_swap_source.exists():
                moved_path_swap_source.rename(path_swap_source)

        escaped_media = temp / "escaped.png"
        escaped_media.write_bytes(b"\x89PNG\r\n\x1a\nescaped")
        rejected = run_playwright_reader(
            playwright_reader,
            "media",
            reports,
            escaped_media,
        )
        assert rejected.returncode != 0
        assert "outside the report root" in rejected.stderr.lower()

        invalid_media = reports / "invalid.jpeg"
        invalid_media.write_bytes(b"not-a-jpeg")
        rejected = run_playwright_reader(
            playwright_reader,
            "media",
            reports,
            invalid_media,
        )
        assert rejected.returncode != 0
        assert "invalid signature" in rejected.stderr.lower()

        oversized_media = reports / "oversized.png"
        with oversized_media.open("wb") as oversized_file:
            oversized_file.truncate(64 * 1024 * 1024 + 1)
        rejected = run_playwright_reader(
            playwright_reader,
            "media",
            reports,
            oversized_media,
        )
        assert rejected.returncode != 0
        assert "byte limit" in rejected.stderr.lower()

        concurrent_media = reports / "concurrent.png"
        original_media = b"\x89PNG\r\n\x1a\n" + b"a" * 70_000
        replacement_media = b"\x89PNG\r\n\x1a\n" + b"b" * 70_000
        concurrent_media.write_bytes(original_media)
        media_metadata = concurrent_media.stat()
        original_media_read = reader_module.os.read
        original_media_mkdtemp = reader_module.tempfile.mkdtemp
        media_read_count = 0
        partial_snapshot_directories: list[Path] = []

        def rewrite_playwright_media_during_read(
            descriptor: int,
            byte_count: int,
        ) -> bytes:
            nonlocal media_read_count
            media_read_count += 1
            if media_read_count == 2:
                writer = os.open(concurrent_media, os.O_WRONLY)
                try:
                    os.pwrite(writer, replacement_media, 0)
                    os.fsync(writer)
                finally:
                    os.close(writer)
                os.utime(
                    concurrent_media,
                    ns=(
                        media_metadata.st_atime_ns,
                        media_metadata.st_mtime_ns,
                    ),
                )
                rewritten = concurrent_media.stat()
                assert rewritten.st_ino == media_metadata.st_ino
                assert rewritten.st_size == media_metadata.st_size
                assert rewritten.st_mtime_ns == media_metadata.st_mtime_ns
            return original_media_read(descriptor, byte_count)

        def tracked_playwright_media_mkdtemp(
            *args: object,
            **kwargs: object,
        ) -> str:
            kwargs["dir"] = temp
            directory = original_media_mkdtemp(*args, **kwargs)
            partial_snapshot_directories.append(Path(directory))
            return directory

        reader_module.os.read = rewrite_playwright_media_during_read
        reader_module.tempfile.mkdtemp = tracked_playwright_media_mkdtemp
        try:
            try:
                reader_module.media_metadata(reports, concurrent_media)
            except ValueError as exc:
                assert "changed while being read" in str(exc)
            else:
                raise AssertionError(
                    "same-inode same-size Playwright media rewrite with "
                    "restored mtime must fail closed"
                )
        finally:
            reader_module.os.read = original_media_read
            reader_module.tempfile.mkdtemp = original_media_mkdtemp
        assert partial_snapshot_directories
        assert all(
            not directory.exists()
            for directory in partial_snapshot_directories
        )

        trace_for_viewer = reports / "viewer-trace.zip"
        with zipfile.ZipFile(
            trace_for_viewer,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                "trace.trace",
                b'{"type":"before","apiName":"page.click"}\n',
            )
        trace_snapshot_result = run_playwright_reader(
            playwright_reader,
            "trace-snapshot",
            reports,
            trace_for_viewer,
        )
        assert trace_snapshot_result.returncode == 0, (
            trace_snapshot_result.stderr
        )
        trace_snapshot = json.loads(trace_snapshot_result.stdout)
        assert trace_snapshot["kind"] == "zip"
        viewer_path = Path(trace_snapshot["path"])
        viewer_directory = Path(trace_snapshot["snapshot_directory"])
        assert viewer_path != trace_for_viewer
        assert viewer_path.read_bytes() == trace_for_viewer.read_bytes()
        assert stat.S_IMODE(viewer_path.stat().st_mode) == stat.S_IRUSR
        assert stat.S_IMODE(viewer_directory.stat().st_mode) == stat.S_IRWXU

        invalid_trace_for_viewer = reports / "invalid-trace.zip"
        invalid_trace_for_viewer.write_bytes(b"not-a-zip")
        rejected = run_playwright_reader(
            playwright_reader,
            "trace-snapshot",
            reports,
            invalid_trace_for_viewer,
        )
        assert rejected.returncode != 0
        assert "invalid or unsupported zip" in rejected.stderr.lower()

        corrupt_trace_for_viewer = reports / "corrupt-member-trace.zip"
        corrupt_payload = b'{"type":"before","apiName":"page.click"}\n'
        with zipfile.ZipFile(
            corrupt_trace_for_viewer,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as archive:
            archive.writestr("trace.trace", corrupt_payload)
        with zipfile.ZipFile(corrupt_trace_for_viewer, "r") as archive:
            corrupt_info = archive.getinfo("trace.trace")
        corrupt_zip_bytes = bytearray(corrupt_trace_for_viewer.read_bytes())
        local_header = corrupt_info.header_offset
        filename_length = int.from_bytes(
            corrupt_zip_bytes[local_header + 26 : local_header + 28],
            "little",
        )
        extra_length = int.from_bytes(
            corrupt_zip_bytes[local_header + 28 : local_header + 30],
            "little",
        )
        member_offset = local_header + 30 + filename_length + extra_length
        corrupt_zip_bytes[member_offset] ^= 0x01
        corrupt_trace_for_viewer.write_bytes(corrupt_zip_bytes)
        rejected = run_playwright_reader(
            playwright_reader,
            "trace-snapshot",
            reports,
            corrupt_trace_for_viewer,
        )
        assert rejected.returncode != 0
        assert "invalid or corrupt zip entry payload" in rejected.stderr.lower()

        documented_artifacts = reports / "path/to"
        documented_artifacts.mkdir(parents=True)
        documented_trace = documented_artifacts / "trace.zip"
        documented_trace.write_bytes(trace_for_viewer.read_bytes())
        documented_trace_result = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            documented_trace,
            "--list",
        )
        assert documented_trace_result.returncode == 0, (
            documented_trace_result.stderr
        )
        assert json.loads(documented_trace_result.stdout) == ["trace.trace"]
        documented_media = documented_artifacts / "failure.png"
        documented_media.write_bytes(media_payloads["failure.png"])
        documented_media_result = run_playwright_reader(
            playwright_reader,
            "media",
            reports,
            documented_media,
        )
        assert documented_media_result.returncode == 0, (
            documented_media_result.stderr
        )
        documented_media_snapshot = json.loads(documented_media_result.stdout)
        documented_media_path = Path(documented_media_snapshot["path"])
        documented_media_directory = Path(
            documented_media_snapshot["snapshot_directory"]
        )

        for snapshot_path, snapshot_directory in (
            *media_snapshots,
            (viewer_path, viewer_directory),
            (documented_media_path, documented_media_directory),
        ):
            snapshot_path.unlink()
            snapshot_directory.rmdir()
            assert not snapshot_directory.exists()

        retry_report = reports / "results.json"
        retry_report.write_text(
            json.dumps(
                {
                    "stats": {
                        "expected": 0,
                        "skipped": 0,
                        "unexpected": 0,
                        "flaky": 1,
                    },
                    "suites": [
                        {
                            "specs": [
                                {
                                    "title": "eventually passes",
                                    "file": "retry.spec.ts",
                                    "line": 10,
                                    "ok": True,
                                    "tests": [
                                        {
                                            "projectName": "chromium",
                                            "status": "flaky",
                                            "results": [
                                                {
                                                    "status": "failed",
                                                    "duration": 30000,
                                                    "retry": 0,
                                                    "error": {
                                                        "message": "first failure",
                                                        "location": {
                                                            "file": "retry.spec.ts",
                                                            "line": 14,
                                                            "column": 9,
                                                        },
                                                    },
                                                },
                                                {
                                                    "status": "passed",
                                                    "duration": 125,
                                                    "retry": 1,
                                                    "error": None,
                                                },
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        read_result = run_playwright_reader(
            playwright_reader, "report", reports, retry_report
        )
        assert read_result.returncode == 0, read_result.stderr
        retry_rows = json.loads(read_result.stdout)
        assert len(retry_rows) == 1
        assert retry_rows[0]["outcome"] == "flaky"
        assert retry_rows[0]["retries"] == 1
        assert retry_rows[0]["attempts"] == [
            {
                "attempt": 0,
                "duration": 30000,
                "error": "first failure",
                "errorLocation": {
                    "column": 9,
                    "file": "retry.spec.ts",
                    "line": 14,
                },
                "status": "failed",
            },
            {
                "attempt": 1,
                "duration": 125,
                "error": None,
                "errorLocation": None,
                "status": "passed",
            },
        ]

        playwright_secret_text, playwright_secrets = (
            adversarial_credentials(4000)
        )
        secret_report = reports / "secret-results.json"
        secret_report.write_text(
            json.dumps(
                {
                    "stats": {
                        "expected": 0,
                        "skipped": 0,
                        "unexpected": 1,
                        "flaky": 0,
                    },
                    "suites": [
                        {
                            "specs": [
                                {
                                    "title": "redacts credentials",
                                    "file": "secret.spec.ts",
                                    "line": 1,
                                    "ok": False,
                                    "tests": [
                                        {
                                            "projectName": "chromium",
                                            "status": "unexpected",
                                            "results": [
                                                {
                                                    "status": "failed",
                                                    "duration": 1,
                                                    "retry": 0,
                                                    "error": {
                                                        "message": (
                                                            playwright_secret_text
                                                        )
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        secret_report_result = run_playwright_reader(
            playwright_reader,
            "report",
            reports,
            secret_report,
        )
        assert secret_report_result.returncode == 0, (
            secret_report_result.stderr
        )
        assert_credentials_redacted(
            secret_report_result.stdout,
            playwright_secrets,
        )

        interrupted_reports = (
            (
                "interrupted-only.json",
                "unexpected",
                False,
                {
                    "expected": 0,
                    "skipped": 0,
                    "unexpected": 1,
                    "flaky": 0,
                },
                [{"status": "interrupted", "error": {"message": "cancelled"}}],
            ),
            (
                "interrupted-then-passed.json",
                "flaky",
                True,
                {
                    "expected": 0,
                    "skipped": 0,
                    "unexpected": 0,
                    "flaky": 1,
                },
                [
                    {
                        "status": "interrupted",
                        "error": {"message": "worker interrupted"},
                    },
                    {"status": "passed"},
                ],
            ),
        )
        for name, outcome, spec_ok, stats, results in interrupted_reports:
            interrupted_report = reports / name
            interrupted_report.write_text(
                json.dumps(
                    {
                        "stats": stats,
                        "suites": [
                            {
                                "specs": [
                                    {
                                        "title": name,
                                        "file": "interrupted.spec.ts",
                                        "line": 1,
                                        "ok": spec_ok,
                                        "tests": [
                                            {
                                                "status": outcome,
                                                "results": results,
                                            }
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            interrupted_result = run_playwright_reader(
                playwright_reader,
                "report",
                reports,
                interrupted_report,
            )
            assert interrupted_result.returncode == 0, interrupted_result.stderr
            interrupted_rows = json.loads(interrupted_result.stdout)
            assert interrupted_rows[0]["outcome"] == outcome
            assert interrupted_rows[0]["attempts"][0]["status"] == "interrupted"
            assert interrupted_rows[0]["attempts"][0]["error"] in {
                "cancelled",
                "worker interrupted",
            }

        contradictory_stats_reports = {
            "negative-stats.json": {
                "expected": 0,
                "skipped": 0,
                "unexpected": -1,
                "flaky": 0,
            },
            "wrong-stats-type.json": {
                "expected": 0,
                "skipped": 0,
                "unexpected": "0",
                "flaky": 0,
            },
            "hidden-unexpected.json": {
                "expected": 0,
                "skipped": 0,
                "unexpected": 1,
                "flaky": 0,
            },
        }
        for name, stats in contradictory_stats_reports.items():
            contradictory_stats = reports / name
            contradictory_stats.write_text(
                json.dumps({"stats": stats, "suites": []}),
                encoding="utf-8",
            )
            rejected = run_playwright_reader(
                playwright_reader,
                "report",
                reports,
                contradictory_stats,
            )
            assert rejected.returncode != 0, name
            assert "stats" in rejected.stderr.lower(), rejected.stderr

        contradictory_playwright_reports = {
            "wrong-spec-ok.json": {
                "ok": True,
                "test": {
                    "expectedStatus": "passed",
                    "status": "unexpected",
                    "results": [{"status": "failed"}],
                },
            },
            "wrong-test-status.json": {
                "ok": False,
                "test": {
                    "expectedStatus": "passed",
                    "status": "unexpected",
                    "results": [{"status": "passed"}],
                },
            },
            "unknown-result-status.json": {
                "ok": False,
                "test": {
                    "expectedStatus": "passed",
                    "status": "unexpected",
                    "results": [{"status": "mystery"}],
                },
            },
        }
        for name, contradiction in contradictory_playwright_reports.items():
            contradictory = reports / name
            contradictory.write_text(
                json.dumps(
                    {
                        "suites": [
                            {
                                "specs": [
                                    {
                                        "title": name,
                                        "file": "contradictory.spec.ts",
                                        "line": 1,
                                        "ok": contradiction["ok"],
                                        "tests": [contradiction["test"]],
                                    }
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rejected = run_playwright_reader(
                playwright_reader, "report", reports, contradictory
            )
            assert rejected.returncode != 0, name
            assert "contradict" in rejected.stderr.lower(), rejected.stderr

        valid_expected_statuses = reports / "valid-expected-statuses.json"
        valid_expected_statuses.write_text(
            json.dumps(
                {
                    "stats": {
                        "expected": 1,
                        "skipped": 1,
                        "unexpected": 0,
                        "flaky": 0,
                    },
                    "suites": [
                        {
                            "specs": [
                                {
                                    "title": "expected failure and skip",
                                    "file": "expected.spec.ts",
                                    "line": 1,
                                    "ok": True,
                                    "tests": [
                                        {
                                            "expectedStatus": "failed",
                                            "status": "expected",
                                            "results": [{"status": "failed"}],
                                        },
                                        {
                                            "expectedStatus": "skipped",
                                            "status": "skipped",
                                            "results": [{"status": "skipped"}],
                                        },
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        valid_expected_result = run_playwright_reader(
            playwright_reader, "report", reports, valid_expected_statuses
        )
        assert valid_expected_result.returncode == 0, valid_expected_result.stderr
        assert json.loads(valid_expected_result.stdout) == []

        fallback_report = reports / "fallback-location.json"
        fallback_report.write_text(
            json.dumps(
                {
                    "stats": {
                        "expected": 0,
                        "skipped": 0,
                        "unexpected": 1,
                        "flaky": 0,
                    },
                    "suites": [
                        {
                            "specs": [
                                {
                                    "title": "fallback location",
                                    "file": "fallback.spec.ts",
                                    "line": 3,
                                    "ok": False,
                                    "tests": [
                                        {
                                            "projectName": "chromium",
                                            "status": "unexpected",
                                            "results": [
                                                {
                                                    "status": "failed",
                                                    "error": {"message": "boom"},
                                                    "errorLocation": {
                                                        "file": "fallback.spec.ts",
                                                        "line": 7,
                                                        "column": 2,
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        fallback_result = run_playwright_reader(
            playwright_reader, "report", reports, fallback_report
        )
        assert fallback_result.returncode == 0, fallback_result.stderr
        fallback_rows = json.loads(fallback_result.stdout)
        assert fallback_rows[0]["attempts"][0]["errorLocation"]["line"] == 7

        nested_report = reports / "nested-suites.json"
        nested_report.write_text(
            json.dumps(
                {
                    "stats": {
                        "expected": 0,
                        "skipped": 0,
                        "unexpected": 1,
                        "flaky": 0,
                    },
                    "suites": [
                        {
                            "specs": [],
                            "suites": [
                                {
                                    "specs": [
                                        {
                                            "title": "nested failure",
                                            "file": "nested.spec.ts",
                                            "line": 2,
                                            "ok": False,
                                            "tests": [
                                                {
                                                    "status": "unexpected",
                                                    "results": [
                                                        {
                                                            "status": "failed",
                                                            "error": {
                                                                "message": "nested"
                                                            },
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ]
                                }
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        nested_result = run_playwright_reader(
            playwright_reader, "report", reports, nested_report
        )
        assert nested_result.returncode == 0, nested_result.stderr
        nested_rows = json.loads(nested_result.stdout)
        assert nested_rows[0]["title"] == "nested failure"
        assert nested_rows[0]["attempts"][0]["error"] == "nested"

        global_error_report = reports / "global-error.json"
        global_error_report.write_text(
            json.dumps(
                {
                    "stats": {
                        "expected": 0,
                        "skipped": 0,
                        "unexpected": 0,
                        "flaky": 0,
                    },
                    "suites": [],
                    "errors": [
                        {
                            "message": "global setup failed",
                            "location": {
                                "file": "global-setup.ts",
                                "line": 9,
                                "column": 3,
                            },
                        }
                    ],
                    "projects": [
                        {
                            "name": "webkit",
                            "errors": [
                                {
                                    "message": "project dependency failed",
                                    "location": {
                                        "file": "playwright.config.ts",
                                        "line": 18,
                                        "column": 5,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        global_result = run_playwright_reader(
            playwright_reader, "report", reports, global_error_report
        )
        assert global_result.returncode == 0, global_result.stderr
        global_rows = json.loads(global_result.stdout)
        assert [row["attempts"][0]["error"] for row in global_rows] == [
            "global setup failed",
            "project dependency failed",
        ]
        assert global_rows[0]["projectName"] is None
        assert global_rows[1]["projectName"] == "webkit"
        assert global_rows[0]["attempts"][0]["errorLocation"]["line"] == 9

        malformed_reports = {
            "missing-suites.json": {},
            "wrong-suites.json": {"suites": {}},
            "malformed-nested.json": {
                "suites": [{"title": "suite", "specs": {}}]
            },
            "malformed-errors.json": {
                "suites": [],
                "errors": {"message": "not an array"},
            },
            "decoy.json": {
                "suites": [],
                "metadata": {
                    "ok": False,
                    "tests": [
                        {
                            "status": "unexpected",
                            "results": [{"status": "failed"}],
                        }
                    ],
                },
            },
        }
        for name, malformed_report in malformed_reports.items():
            malformed = reports / name
            malformed.write_text(json.dumps(malformed_report), encoding="utf-8")
            rejected = run_playwright_reader(
                playwright_reader, "report", reports, malformed
            )
            assert rejected.returncode != 0, name
            assert "schema" in rejected.stderr.lower(), rejected.stderr

        strict_json_cases = {
            "duplicate-key.json": b'{"suites":[],"suites":[]}',
            "nan.json": b'{"suites":[],"value":NaN}',
            "infinity.json": b'{"suites":[],"value":Infinity}',
            "negative-infinity.json": b'{"suites":[],"value":-Infinity}',
            "bom.json": b'\xef\xbb\xbf{"suites":[]}',
            "trailing.json": b'{"suites":[]}{"suites":[]}',
        }
        for name, content in strict_json_cases.items():
            ambiguous = reports / name
            ambiguous.write_bytes(content)
            rejected = run_playwright_reader(
                playwright_reader, "report", reports, ambiguous
            )
            assert rejected.returncode != 0, name
            assert "json" in rejected.stderr.lower(), rejected.stderr

        linked_report = reports / "linked-results.json"
        linked_report.symlink_to(retry_report)
        rejected = run_playwright_reader(
            playwright_reader, "report", reports, linked_report
        )
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        linked_root = temp / "linked-playwright-report"
        linked_root.symlink_to(reports, target_is_directory=True)
        rejected = run_playwright_reader(
            playwright_reader,
            "report",
            linked_root,
            linked_root / "results.json",
        )
        assert rejected.returncode != 0
        assert "symlink" in rejected.stderr.lower()

        fifo = reports / "results.fifo"
        os.mkfifo(fifo)
        rejected = run_playwright_reader(
            playwright_reader, "report", reports, fifo
        )
        assert rejected.returncode != 0
        assert "regular file" in rejected.stderr.lower()

        deep_report = reports / "deep.json"
        deep_report.write_text("[" * 110 + "0" + "]" * 110, encoding="utf-8")
        rejected = run_playwright_reader(
            playwright_reader, "report", reports, deep_report
        )
        assert rejected.returncode != 0
        assert "depth limit" in rejected.stderr.lower()

        oversized_report = reports / "oversized-report.json"
        with oversized_report.open("wb") as oversized_file:
            oversized_file.truncate(8 * 1024 * 1024 + 1)
        rejected = run_playwright_reader(
            playwright_reader,
            "report",
            reports,
            oversized_report,
        )
        assert rejected.returncode != 0
        assert "byte limit" in rejected.stderr.lower()

        trace_zip = reports / "trace.zip"
        with zipfile.ZipFile(
            trace_zip, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "trace.trace",
                '{"type":"after","apiName":"locator.click","error":'
                '{"message":"boom"}}\n'
                '{"type":"after","apiName":"expect","error":null}\n'
                '{"type":"console","messageType":"error",'
                '"text":"browser exploded"}\n'
                '{"type":"event","method":"pageError","params":'
                '{"error":{"name":"Error","message":"page exploded"}}}\n',
            )
            archive.writestr(
                "trace.network",
                '{"type":"resource-snapshot","snapshot":'
                '{"request":{"method":"GET","url":'
                '"https://example.test/api?debug=true"},'
                '"response":{"status":500,"statusText":"Server Error"}}}\n',
            )
            archive.writestr("resources/screenshot.jpeg", b"jpeg")
        list_result = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            trace_zip,
            "--list",
        )
        assert list_result.returncode == 0, list_result.stderr
        assert json.loads(list_result.stdout) == [
            "trace.network",
            "trace.trace",
        ]
        trace_result = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            trace_zip,
            "--entry",
            "trace.trace",
        )
        assert trace_result.returncode == 0, trace_result.stderr
        trace_rows = json.loads(trace_result.stdout)
        assert [row["kind"] for row in trace_rows] == [
            "failed-action",
            "console-error",
            "page-error",
        ]
        assert trace_rows[0]["apiName"] == "locator.click"
        assert trace_rows[0]["error"]["message"] == "boom"
        assert trace_rows[1]["text"] == "browser exploded"
        assert trace_rows[2]["error"]["message"] == "page exploded"
        assert "expect" not in trace_result.stdout

        network_result = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            trace_zip,
            "--entry",
            "trace.network",
        )
        assert network_result.returncode == 0, network_result.stderr
        network_rows = json.loads(network_result.stdout)
        assert network_rows == [
            {
                "failure": None,
                "kind": "network-error",
                "method": "GET",
                "status": 500,
                "statusText": "Server Error",
                "url": "https://example.test/api?debug=[REDACTED]",
            }
        ]

        sentinel = "TRACE_SENTINEL_SECRET_7d349"
        recursively_redacted = reader_module.redact_sensitive(
            {
                "outer": {
                    "credentials": {"token": sentinel},
                    "headers": [
                        {"name": "Authorization", "value": f"Bearer {sentinel}"},
                        {"name": "x-api-key", "value": sentinel},
                    ],
                    "cookies": [{"name": "session", "value": sentinel}],
                    "request": {
                        "url": f"https://example.test/x?code={sentinel}",
                        "postData": {"text": sentinel},
                    },
                }
            }
        )
        redacted_json = json.dumps(recursively_redacted, sort_keys=True)
        assert sentinel not in redacted_json
        assert "[REDACTED]" in redacted_json

        safe_credential_prose = (
            "Authorization header must be present; Bearer authentication "
            "uses the Authorization header; Cookie header guidance; "
            "token=<TOKEN>; api_key=${API_KEY}"
        )
        # UPDATED POLICY. This used to assert that the gate reads raw
        # documentation prose as clean because `<TOKEN>` and `${API_KEY}` look
        # like placeholders. The gate no longer judges values, so it now reads
        # any unredacted value after a keyword separator as a violation --
        # a placeholder included. What actually has to hold is unchanged and is
        # asserted directly instead: the prose still reaches stdout, with the
        # placeholder replaced on the way, which is the intended trade.
        redacted_prose = reader_module.redact_string(safe_credential_prose)
        assert not reader_module.has_residual_credential(redacted_prose), (
            redacted_prose
        )
        emitted_prose = reader_module.encode_json(
            {"message": safe_credential_prose}
        )
        assert b"Authorization header must be present" in emitted_prose
        assert b"Cookie header guidance" in emitted_prose

        leaked_credential_shapes = (
            "Authorization: Bearer liveBearerValue",
            "Proxy-Authorization: Basic dXNlcjpwYXNz",
            "Cookie: session=liveCookieValue",
            "Set-Cookie: session=liveSetCookieValue",
            "X-API-Key: liveApiKeyValue",
            "password=livePasswordValue",
            "secret: liveSecretValue",
            "token=liveTokenValue",
            "api_key=liveApiKeyAssignment",
            "https://liveUser:livePassword@example.test/private",
            "https://example.test/private?access_token=liveQueryValue",
        )
        for leaked_shape in leaked_credential_shapes:
            assert reader_module.has_residual_credential(leaked_shape)
        assert reader_module.has_residual_credential(
            json.dumps(
                {"headers": [{"name": "Cookie", "value": "session=live"}]}
            )
        )
        assert reader_module.has_residual_credential(
            json.dumps({"authorization": "opaqueLiveCredential"})
        )

        original_redact_sensitive = reader_module.redact_sensitive
        reader_module.redact_sensitive = lambda value, parent_key=None: value
        try:
            leaked_values = leaked_credential_shapes + (
                {"headers": [{"name": "Cookie", "value": "session=live"}]},
                {"authorization": "opaqueLiveCredential"},
            )
            for leaked_shape in leaked_values:
                try:
                    reader_module.encode_json({"message": leaked_shape})
                except ValueError as exc:
                    assert str(exc) == (
                        "credential redaction left residual sensitive output"
                    )
                    assert "live" not in str(exc).lower()
                else:
                    raise AssertionError(
                        f"residual credential shape was emitted: {leaked_shape!r}"
                    )
        finally:
            reader_module.redact_sensitive = original_redact_sensitive

        secret_trace_zip = reports / "secret-trace.zip"
        with zipfile.ZipFile(
            secret_trace_zip, "w", compression=zipfile.ZIP_STORED
        ) as archive:
            archive.writestr(
                "trace.trace",
                json.dumps(
                    {
                        "type": "after",
                        "apiName": "page.request.post",
                        "error": {
                            "message": (
                                f"Authorization: Bearer {sentinel}; "
                                f"body={sentinel}; "
                                f"https://example.test/private?token={sentinel}"
                            )
                        },
                        "params": {
                            "headers": [
                                {"name": "Cookie", "value": sentinel}
                            ],
                            "postData": sentinel,
                        },
                    }
                )
                + "\n",
            )
            archive.writestr(
                "trace.network",
                json.dumps(
                    {
                        "type": "resource-snapshot",
                        "snapshot": {
                            "request": {
                                "method": "POST",
                                "url": (
                                    "https://example.test/private"
                                    f"?access_token={sentinel}"
                                ),
                                "headers": [
                                    {
                                        "name": "Authorization",
                                        "value": f"Bearer {sentinel}",
                                    }
                                ],
                                "postData": sentinel,
                            },
                            "response": {
                                "status": 401,
                                "headers": [
                                    {"name": "Set-Cookie", "value": sentinel}
                                ],
                            },
                        },
                    }
                )
                + "\n",
            )
        for entry in ("trace.trace", "trace.network"):
            secret_result = run_playwright_reader(
                playwright_reader,
                "trace",
                reports,
                secret_trace_zip,
                "--entry",
                entry,
            )
            assert secret_result.returncode == 0, secret_result.stderr
            assert sentinel not in secret_result.stdout
            assert "[REDACTED]" in secret_result.stdout

        large_trace_zip = reports / "large-trace.zip"
        irrelevant_rows = "".join(
            json.dumps(
                {
                    "type": "frame-snapshot",
                    "snapshot": {"name": f"irrelevant-{index}"},
                }
            )
            + "\n"
            for index in range(12_500)
        )
        with zipfile.ZipFile(
            large_trace_zip, "w", compression=zipfile.ZIP_STORED
        ) as archive:
            archive.writestr(
                "trace.trace",
                irrelevant_rows
                + '{"type":"after","apiName":"locator.fill","error":'
                '{"message":"late useful failure"}}\n',
            )
        large_trace_result = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            large_trace_zip,
            "--entry",
            "trace.trace",
        )
        assert large_trace_result.returncode == 0, large_trace_result.stderr
        assert json.loads(large_trace_result.stdout) == [
            {
                "apiName": "locator.fill",
                "callId": None,
                "error": {
                    "message": "late useful failure",
                    "name": None,
                    "stack": None,
                },
                "kind": "failed-action",
            }
        ]

        strict_trace_cases = {
            "duplicate": b'{"type":"after","type":"before"}\n',
            "nan": b'{"type":"after","duration":NaN}\n',
            "bom": b'\xef\xbb\xbf{"type":"after"}\n',
            "trailing": b'{"type":"after"}{"type":"before"}\n',
        }
        for name, trace_content in strict_trace_cases.items():
            strict_trace_zip = reports / f"strict-trace-{name}.zip"
            with zipfile.ZipFile(
                strict_trace_zip, "w", compression=zipfile.ZIP_STORED
            ) as archive:
                archive.writestr("trace.trace", trace_content)
            rejected = run_playwright_reader(
                playwright_reader,
                "trace",
                reports,
                strict_trace_zip,
                "--entry",
                "trace.trace",
            )
            assert rejected.returncode != 0, name
            assert "json" in rejected.stderr.lower(), rejected.stderr

        rejected = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            trace_zip,
            "--entry",
            "resources/screenshot.jpeg",
        )
        assert rejected.returncode != 0
        assert "expected trace entry" in rejected.stderr.lower()

        bomb_zip = reports / "bomb.zip"
        with zipfile.ZipFile(
            bomb_zip, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr("trace.trace", b"A" * (2 * 1024 * 1024))
        rejected = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            bomb_zip,
            "--entry",
            "trace.trace",
        )
        assert rejected.returncode != 0
        assert "compression ratio" in rejected.stderr.lower()

        duplicate_zip = reports / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(
                duplicate_zip, "w", compression=zipfile.ZIP_STORED
            ) as archive:
                archive.writestr("trace.trace", '{"type":"after"}\n')
                archive.writestr("trace.trace", '{"type":"after"}\n')
        rejected = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            duplicate_zip,
            "--entry",
            "trace.trace",
        )
        assert rejected.returncode != 0
        assert "duplicate zip entry" in rejected.stderr.lower()

        symlink_zip = reports / "symlink-entry.zip"
        with zipfile.ZipFile(
            symlink_zip, "w", compression=zipfile.ZIP_STORED
        ) as archive:
            symlink_info = zipfile.ZipInfo("trace.trace")
            symlink_info.create_system = 3
            symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(symlink_info, "trace.network")
        rejected = run_playwright_reader(
            playwright_reader,
            "trace",
            reports,
            symlink_zip,
            "--entry",
            "trace.trace",
        )
        assert rejected.returncode != 0
        assert "symlink zip entry" in rejected.stderr.lower()

        zip_mode_cases = {}
        regular_with_slash = zipfile.ZipInfo("trace.trace/")
        regular_with_slash.create_system = 3
        regular_with_slash.external_attr = (stat.S_IFREG | 0o644) << 16
        zip_mode_cases["regular-mode-directory-name"] = regular_with_slash
        directory_without_slash = zipfile.ZipInfo("trace.trace")
        directory_without_slash.create_system = 3
        directory_without_slash.external_attr = (stat.S_IFDIR | 0o755) << 16
        zip_mode_cases["directory-mode-file-name"] = directory_without_slash
        for name, info in zip_mode_cases.items():
            mismatch_zip = reports / f"{name}.zip"
            with zipfile.ZipFile(
                mismatch_zip, "w", compression=zipfile.ZIP_STORED
            ) as archive:
                archive.writestr(info, b"")
            rejected = run_playwright_reader(
                playwright_reader,
                "trace",
                reports,
                mismatch_zip,
                "--entry",
                "trace.trace",
            )
            assert rejected.returncode != 0, name
            assert "directory mode/name disagreement" in rejected.stderr.lower()

    assert "node_modules/.bin/playwright" in playwright_text
    assert_no_unguarded_npx(playwright_text, "playwright")
    assert "> playwright-report/results.json" not in playwright_text
    assert playwright_text.count("publish-json-report.py") >= 3
    assert (
        "node_modules/.bin/playwright merge-reports --reporter=json ./blob-report"
        in playwright_flat
    )
    assert "do not replace it with `mkdir` plus shell redirection" in playwright_flat
    assert "Dedupe by `file` + `title` across projects" in playwright_text
    assert "**F-code / confidence:**" in playwright_text
    assert "**Diagnosis axis:** product regression | test defect | unknown" in playwright_text
    assert "**Product impact:**" in playwright_text
    assert "**Test-reliability urgency:**" in playwright_text
    assert "**Test-quality severity:**" in playwright_text
    assert (
        '- **Error excerpt:** `"<sanitized, bounded error excerpt from bundled '
        'artifact-reader output>"`'
        in playwright_text
    )
    assert "<raw error message>" not in playwright_text
    assert "Never copy direct or raw artifact text into the finding" in playwright_flat
    assert (
        "Preserve enough emitted context to identify the failing assertion or action"
        in playwright_flat
    )
    assert "Apply P0/P1/P2 only to confirmed test-quality defects" in playwright_text
    assert "never map those codes to P2 before the" in playwright_flat
    assert "P2:** Consistent failures" not in playwright_text
    assert "file` + `title` + `projectName" not in playwright_text
    assert "Never retry a non-idempotent action" in playwright_text
    assert "submit, payment, delete, registration, or toggle" in playwright_text
    assert "**Execution safety gate (before any Playwright test command):**" in playwright_text
    assert "`local/disposable`" in playwright_text
    assert "explicitly approved non-production test environment" in playwright_text
    assert "production, shared, or unknown" in playwright_text
    assert "replay non-idempotent writes" in playwright_text
    assert "regular, non-symlink file" in playwright_text
    assert "canonical `playwright-report/` root" in playwright_flat
    assert "Before any command creates or replaces a report artifact" in playwright_text
    assert "any existing component beneath either" in playwright_text
    assert "immediately before `mkdir`, reporter output, shell redirection" in playwright_flat
    assert "**Repository execution gate:**" in playwright_text
    assert "explicitly trusted this repository" in playwright_text
    assert "approved the exact command line" in playwright_flat
    assert "General approval to diagnose, reproduce" in playwright_flat
    assert "--grep '^exact failing test title$' --retries=0" in playwright_flat
    assert "system-boundary effects are idempotent" in playwright_text
    playwright_config_match = re.search(
        r"`playwright\.config\.\{([^}]+)\}`",
        playwright_text,
    )
    assert playwright_config_match is not None
    assert playwright_config_match.group(1).split(",") == [
        "ts",
        "js",
        "mts",
        "mjs",
        "cts",
        "cjs",
    ]
    assert "six default-discovery filenames" in playwright_text
    cypress_config_match = re.search(
        r"`cypress\.config\.\{([^}]+)\}`",
        cypress_text,
    )
    assert cypress_config_match is not None
    assert cypress_config_match.group(1).split(",") == [
        "js",
        "ts",
        "mjs",
        "cjs",
    ]
    assert "four default-discovery filenames" in cypress_text
    assert "select a `.mts` or `.cts` config explicitly with `--config-file`" in cypress_text
    assert "do not treat those extensions as additional default-discovery names" in cypress_text
    assert "`results.json`" in playwright_text
    assert "HTML report data ZIP" in playwright_text
    assert "trace ZIP" in playwright_text
    assert "run-artifact-reader.sh" in playwright_flat
    assert "-- report" in playwright_flat
    assert "-- trace" in playwright_flat
    assert "-- media" in playwright_flat
    assert "-- trace-snapshot" in playwright_flat
    assert "never reopen the original media path" in playwright_flat
    assert "never give the viewer the original trace path" in playwright_flat
    assert "page.screenshot({ path:" in playwright_text
    assert "without `path` only returns bytes" in playwright_flat
    documented_report_artifacts = re.findall(
        r"--report-root playwright-report (?:\\ )?([^\s`]+)",
        playwright_flat,
    )
    assert len(documented_report_artifacts) >= 7
    assert all(
        artifact.startswith("playwright-report/")
        for artifact in documented_report_artifacts
    ), documented_report_artifacts
    assert "attempts" in playwright_text
    assert "jq" not in playwright_text
    assert "unzip -p" not in playwright_text
    assert "allow_nan=False" in playwright_reader.read_text(encoding="utf-8")
    assert "Unix file mode and a trailing-slash directory name must agree" in playwright_flat
    assert "8 MiB per report JSON" in playwright_text
    assert "8 MiB input" in cypress_text
    assert "UTF-8 XML" in cypress_text
    redaction_contract = (
        "recursively sanitized before any per-field or output truncation"
    )
    for skill_text in (playwright_flat, cypress_flat):
        assert redaction_contract in skill_text
        assert "Bearer/Basic credentials" in skill_text
        assert "URL userinfo" in skill_text
        assert "residual credential shape fails closed" in skill_text

    print(
        "debugger contracts: pass "
        "(bounded Playwright/Cypress JSON, ZIP, media, and JUnit artifacts; "
        "redact-before-truncate credential handling; "
        "attempt-coherent retries; safe execution environments; guarded "
        "runtime resolution; safe blob merge; project trust and exact-command "
        "approval; retry-zero reproduction; project dedupe)"
    )


if __name__ == "__main__":
    main()
