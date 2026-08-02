#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for transactional four-skill reinstall behavior."""

from __future__ import annotations

import json
import base64
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "dev" / "reinstall-skills.sh"
BOOTSTRAP_PACKAGE = (
    ROOT / "scripts" / "dev" / "skills-cli-bootstrap-package.json"
)
BOOTSTRAP_LOCK = (
    ROOT / "scripts" / "dev" / "skills-cli-bootstrap-package-lock.json"
)
INSTALLED_TREE_MANIFEST = (
    ROOT / "scripts" / "dev" / "skills-cli-installed-tree-sha256.json"
)
SKILLS = [
    "cypress-debugger",
    "e2e-reviewer",
    "playwright-debugger",
    "playwright-test-generator",
]


def trusted_node_executable() -> Path:
    for candidate in (
        Path("/opt/homebrew/bin/node"),
        Path("/usr/local/bin/node"),
        Path("/usr/bin/node"),
        Path("/bin/node"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise AssertionError("trusted deterministic Node executable unavailable")


class Harness:
    def __init__(self, temp: Path) -> None:
        self.temp = temp.resolve()
        self.repo = self.temp / "repo"
        self.script = self.repo / "scripts" / "dev" / "reinstall-skills.sh"
        self.script.parent.mkdir(parents=True)
        shutil.copy2(
            BOOTSTRAP_PACKAGE,
            self.script.parent / BOOTSTRAP_PACKAGE.name,
        )
        shutil.copy2(
            BOOTSTRAP_LOCK,
            self.script.parent / BOOTSTRAP_LOCK.name,
        )
        for skill in SKILLS:
            source = self.repo / "skills" / skill
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(f"new:{skill}\n", encoding="utf-8")

        self.home = self.temp / "home"
        self.store = self.home / ".agents" / "skills"
        self.store.mkdir(parents=True)
        self.claude_store = self.home / ".claude" / "skills"
        for skill in SKILLS:
            installed = self.store / skill
            installed.mkdir()
            (installed / "SKILL.md").write_text(f"old:{skill}\n", encoding="utf-8")
        unrelated = self.store / "unrelated-skill"
        unrelated.mkdir()
        (unrelated / "SKILL.md").write_text("untouched\n", encoding="utf-8")

        self.agent_log = self.temp / "codex-agent-install.log"
        installer = self.script.parent / "install-codex-agents.sh"
        installer.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' CALL >> {str(self.agent_log)!r}\n"
            "exit \"${FAKE_AGENT_INSTALL_STATUS:-0}\"\n",
            encoding="utf-8",
        )
        installer.chmod(0o755)

        self.fake_bin = self.temp / "trusted-node-bin"
        self.fake_bin.mkdir()
        real_node = trusted_node_executable()
        (self.fake_bin / "node").symlink_to(real_node)

        fake_package = self.temp / "package-fixture" / "package"
        fake_package.joinpath("bin").mkdir(parents=True)
        fake_package.joinpath("package.json").write_text(
            json.dumps(
                {
                    "name": "skills",
                    "version": "1.5.21",
                    "repository": {
                        "type": "git",
                        "url": "git+https://github.com/vercel-labs/skills.git",
                    },
                    "bin": {"skills": "./bin/cli.mjs"},
                }
            ),
            encoding="utf-8",
        )
        self.log = self.temp / "skills-argv.log"
        self.exec_log = self.temp / "skills-executables.log"
        self.count = self.temp / "skills-count"
        fake_skills = fake_package / "bin" / "cli.mjs"
        fake_skills.write_text(
            "#!/usr/bin/env node\n"
            "import fs from 'node:fs';\n"
            "import path from 'node:path';\n"
            "const args = process.argv.slice(2);\n"
            "if (args[0] === '--version') {\n"
            "  console.log(process.env.FAKE_CLI_VERSION || '1.5.21');\n"
            "  process.exit(0);\n"
            "}\n"
            f"const log = {json.dumps(str(self.log))};\n"
            f"const execLog = {json.dumps(str(self.exec_log))};\n"
            f"const countFile = {json.dumps(str(self.count))};\n"
            "fs.appendFileSync(execLog, `${process.argv[1]}\\n`);\n"
            "let count = fs.existsSync(countFile) ? Number(fs.readFileSync(countFile, 'utf8')) : 0;\n"
            "count += 1;\n"
            "fs.writeFileSync(countFile, `${count}\\n`);\n"
            "fs.appendFileSync(log, `CALL\\n${args.join('\\n')}\\n`);\n"
            "const failures = (process.env.FAKE_FAIL_CALLS || process.env.FAKE_FAIL_CALL || '0').split(',');\n"
            "if (failures.includes(String(count))) process.exit(91);\n"
            f"const store = {json.dumps(str(self.store))};\n"
            f"const claudeStore = {json.dumps(str(self.claude_store))};\n"
            f"const skills = {json.dumps(SKILLS)};\n"
            "const wantsClaude = args.includes('claude-code');\n"
            "if (args[0] === 'remove') {\n"
            "  for (const [index, skill] of skills.entries()) {\n"
            "    fs.rmSync(path.join(store, skill), {recursive: true, force: true});\n"
            "    fs.rmSync(path.join(claudeStore, skill), {recursive: true, force: true});\n"
            "    if (index === 0 && process.env.FAKE_DELETE_BEFORE_FAIL_CALL === String(count)) process.exit(92);\n"
            "  }\n"
            "} else if (args[0] === 'add') {\n"
            "  const sourceRoot = args[1];\n"
            "  if (process.env.FAKE_NOOP_CALL === String(count)) process.exit(0);\n"
            "  for (const [index, skill] of skills.entries()) {\n"
            "    const source = path.join(sourceRoot, 'skills', skill);\n"
            "    if (fs.existsSync(source)) {\n"
            "      const destination = path.join(store, skill);\n"
            "      fs.rmSync(destination, {recursive: true, force: true});\n"
            "      fs.cpSync(source, destination, {recursive: true});\n"
            "      if (wantsClaude) {\n"
            "        fs.mkdirSync(claudeStore, {recursive: true});\n"
            "        const projection = path.join(claudeStore, skill);\n"
            "        fs.rmSync(projection, {recursive: true, force: true});\n"
            "        fs.symlinkSync(path.relative(claudeStore, destination), projection, 'dir');\n"
            "      }\n"
            "    }\n"
            "    if (index === 0 && process.env.FAKE_WRITE_BEFORE_FAIL_CALL === String(count)) process.exit(93);\n"
            "    if (index === 0 && process.env.FAKE_SIGNAL_AFTER_WRITE_CALL === String(count)) {\n"
            "      process.kill(process.ppid, process.env.FAKE_SIGNAL || 'SIGTERM');\n"
            "      process.exit(94);\n"
            "    }\n"
            "    if (index === 0 && process.env.FAKE_PARTIAL_SUCCESS_CALL === String(count)) process.exit(0);\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        fake_skills.chmod(0o755)
        self.package_tarball = self.temp / "skills-1.5.21.tgz"
        with tarfile.open(self.package_tarball, "w:gz") as archive:
            archive.add(fake_package, arcname="package")
        digest = hashlib.sha512(self.package_tarball.read_bytes()).digest()
        self.package_integrity = "sha512-" + base64.b64encode(digest).decode()

        self.npm_log = self.temp / "npm-argv.log"
        fake_npm = self.fake_bin / "npm"
        fake_npm.write_text(
            "#!/usr/bin/env node\n"
            "const fs = require('fs');\n"
            "const path = require('path');\n"
            "const args = process.argv.slice(2);\n"
            f"const log = {json.dumps(str(self.npm_log))};\n"
            "fs.appendFileSync(log, `CALL\\n${args.join('\\n')}\\n`);\n"
            "if (args[0] === 'view') {\n"
            "  const field = args[2];\n"
            "  const values = {\n"
            "    name: process.env.FAKE_REGISTRY_NAME || 'skills',\n"
            "    version: process.env.FAKE_REGISTRY_VERSION || '1.5.21',\n"
            "    'repository.url': process.env.FAKE_REGISTRY_REPOSITORY || 'git+https://github.com/vercel-labs/skills.git',\n"
            f"    'dist.integrity': process.env.FAKE_REGISTRY_INTEGRITY || {json.dumps(self.package_integrity)},\n"
            "  };\n"
            "  if (!(field in values)) process.exit(88);\n"
            "  console.log(values[field]);\n"
            "} else if (args[0] === 'pack') {\n"
            "  const destination = args[args.indexOf('--pack-destination') + 1];\n"
            f"  const source = {json.dumps(str(self.package_tarball))};\n"
            "  const target = path.join(destination, 'skills-1.5.21.tgz');\n"
            "  fs.copyFileSync(source, target);\n"
            "  if (process.env.FAKE_PACK_CORRUPT === '1') fs.appendFileSync(target, 'corrupt');\n"
            "  console.log(JSON.stringify([{filename: 'skills-1.5.21.tgz'}]));\n"
            "} else if (args[0] === 'ci') {\n"
            "  const prefix = process.cwd();\n"
            f"  const source = {json.dumps(str(fake_package))};\n"
            "  const lock = JSON.parse(fs.readFileSync(path.join(prefix, 'package-lock.json'), 'utf8'));\n"
            "  for (const [relative, contract] of Object.entries(lock.packages)) {\n"
            "    if (!relative) continue;\n"
            "    const target = path.join(prefix, relative);\n"
            "    fs.mkdirSync(path.dirname(target), {recursive: true});\n"
            "    if (relative === 'node_modules/skills') fs.cpSync(source, target, {recursive: true});\n"
            "    else {\n"
            "      fs.mkdirSync(target, {recursive: true});\n"
            "      const name = relative.split('/node_modules/').pop().replace(/^node_modules\\//, '');\n"
            "      fs.writeFileSync(path.join(target, 'package.json'), JSON.stringify({name, version: contract.version}));\n"
            "    }\n"
            "  }\n"
            "  const binRoot = path.join(prefix, 'node_modules', '.bin');\n"
            "  fs.mkdirSync(binRoot, {recursive: true});\n"
            "  for (const [relative, contract] of Object.entries(lock.packages)) {\n"
            "    if (!relative || !contract.bin) continue;\n"
            "    const bins = typeof contract.bin === 'string' ? {[relative.split('/').pop()]: contract.bin} : contract.bin;\n"
            "    for (const [name, executable] of Object.entries(bins)) {\n"
            "      const target = path.join(prefix, relative, executable);\n"
            "      fs.mkdirSync(path.dirname(target), {recursive: true});\n"
            "      if (!fs.existsSync(target)) fs.writeFileSync(target, '#!/usr/bin/env node\\n');\n"
            "      fs.symlinkSync(path.relative(binRoot, target), path.join(binRoot, name));\n"
            "    }\n"
            "  }\n"
            "  const target = path.join(prefix, 'node_modules', 'skills');\n"
            "  if (process.env.FAKE_INSTALL_TAMPER === '1') "
            "fs.appendFileSync(path.join(target, 'bin', 'cli.mjs'), "
            "'\\n// tampered\\n');\n"
            "  if (process.env.FAKE_DEPENDENCY_TAMPER === '1') "
            "fs.writeFileSync(path.join(prefix, 'node_modules', 'yaml', 'package.json'), "
            "JSON.stringify({name: 'yaml', version: '0.0.0'}));\n"
            "  if (process.env.FAKE_DEPENDENCY_FILE_TAMPER === '1') "
            "fs.writeFileSync(path.join(prefix, 'node_modules', 'yaml', 'tampered.js'), "
            "'process.env.FAKE_DEPENDENCY_SENTINEL = \"ran\";\\n');\n"
            "} else process.exit(88);\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)

        self.npx_log = self.temp / "npx-argv.log"
        fake_npx = self.fake_bin / "npx"
        fake_npx.write_text(
            "#!/bin/bash\n"
            "set -eu\n"
            f"log={str(self.npx_log)!r}\n"
            "{ printf '%s\\n' CALL; for arg in \"$@\"; do printf '%s\\n' \"$arg\"; done; } >> \"$log\"\n"
            "status=${FAKE_NPX_STATUS:-0}\n"
            "[ \"$status\" -eq 0 ] || exit \"$status\"\n"
            "printf '%s\\n' unexpected-npx-execution\n",
            encoding="utf-8",
        )
        fake_npx.chmod(0o755)
        fake_rm = self.fake_bin / "rm"
        fake_rm.write_text(
            "#!/bin/bash\n"
            "set -u\n"
            'for arg in "$@"; do\n'
            '  case "$arg" in\n'
            "    *e2e-skills-reinstall.*)\n"
            '      /bin/rm "$@"\n'
            '      status=${FAKE_CLEANUP_STATUS:-0}\n'
            '      [ "$status" -eq 0 ] || exit "$status"\n'
            "      exit 0\n"
            "      ;;\n"
            "  esac\n"
            "done\n"
            'exec /bin/rm "$@"\n',
            encoding="utf-8",
        )
        fake_rm.chmod(0o755)

        fake_install = self.temp / "expected-installed-tree"
        lock_contract = json.loads(
            (
                self.script.parent
                / BOOTSTRAP_LOCK.name
            ).read_text(encoding="utf-8")
        )
        for relative, contract in lock_contract["packages"].items():
            if not relative:
                continue
            package_root = fake_install / relative
            if relative == "node_modules/skills":
                shutil.copytree(fake_package, package_root)
            else:
                package_root.mkdir(parents=True)
                package_name = relative.split("/node_modules/")[-1]
                if package_name.startswith("node_modules/"):
                    package_name = package_name[len("node_modules/"):]
                (package_root / "package.json").write_text(
                    json.dumps(
                        {
                            "name": package_name,
                            "version": contract["version"],
                        },
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )
            bins = contract.get("bin", {})
            if isinstance(bins, str):
                bins = {package_root.name: bins}
            for executable in bins.values():
                target = package_root / executable
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text(
                        "#!/usr/bin/env node\n",
                        encoding="utf-8",
                    )

        def strict_tree_digest(root: Path) -> str:
            digest = hashlib.sha256()

            def visit(relative: Path) -> None:
                absolute = root / relative
                metadata = absolute.lstat()
                assert not absolute.is_symlink()
                mode = format(metadata.st_mode & 0o777, "o")
                relative_text = "" if str(relative) == "." else str(relative)
                if absolute.is_dir():
                    digest.update(
                        f"D\0{relative_text}\0{mode}\0".encode()
                    )
                    for child in sorted(absolute.iterdir(), key=lambda p: p.name):
                        visit(relative / child.name)
                elif absolute.is_file():
                    digest.update(
                        (
                            f"F\0{relative_text}\0{mode}\0"
                            f"{metadata.st_size}\0"
                        ).encode()
                    )
                    digest.update(absolute.read_bytes())
                else:
                    raise AssertionError(f"unsupported fake package: {absolute}")

            visit(Path(""))
            return digest.hexdigest()

        fake_tree_manifest = {
            relative: strict_tree_digest(fake_install / relative)
            for relative in sorted(lock_contract["packages"])
            if relative
        }
        fake_tree_manifest_path = (
            self.script.parent / INSTALLED_TREE_MANIFEST.name
        )
        fake_tree_manifest_path.write_text(
            json.dumps(fake_tree_manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        fake_tree_manifest_sha256 = hashlib.sha256(
            fake_tree_manifest_path.read_bytes()
        ).hexdigest()

        script_text = SOURCE.read_text(encoding="utf-8")
        script_text = script_text.replace(
            'SKILLS_CLI_INTEGRITY="sha512-CJ4wx692UkQAW+DLpjJg/ww6dJBojq5E8sQBOqP639GutO72v4EFiV/fq1etW2r9NhM/mwaIq8YoqKFJ9XV7ng=="',
            f"SKILLS_CLI_INTEGRITY={json.dumps(self.package_integrity)}",
        )
        script_text = script_text.replace(
            'SKILLS_CLI_INSTALLED_TREE_MANIFEST_SHA256="63c78c35f08046546f7e89f461ae234ae9800bed2e770a7c43c71e0ccb222fa6"',
            "SKILLS_CLI_INSTALLED_TREE_MANIFEST_SHA256="
            f"{json.dumps(fake_tree_manifest_sha256)}",
        )
        production_trios = """TRUSTED_NODE_TRIOS=(
  "/opt/homebrew/bin/node|/opt/homebrew/bin/npm|/opt/homebrew/bin/npx"
  "/usr/local/bin/node|/usr/local/bin/npm|/usr/local/bin/npx"
  "/usr/bin/node|/usr/bin/npm|/usr/bin/npx"
  "/bin/node|/bin/npm|/bin/npx"
)"""
        script_text = script_text.replace(
            production_trios,
            "TRUSTED_NODE_TRIOS=(\n"
            f'  "{self.fake_bin}/node|{fake_npm}|{fake_npx}"\n'
            ")",
        )
        trusted_case = (
            f"    {self.fake_bin}/node\\|{real_node}\\|"
            f"{fake_npm.resolve()}\\|{fake_npx.resolve()}) return 0 ;;\n"
        )
        script_text = script_text.replace(
            "    # TEST_TRUSTED_NODE_TRIO\n",
            trusted_case + "    # TEST_TRUSTED_NODE_TRIO\n",
        )
        script_text = script_text.replace("RM=/bin/rm", f"RM={fake_rm}")
        self.script.write_text(script_text, encoding="utf-8")
        self.script.chmod(0o755)

    def environment(self, **overrides: str) -> dict[str, str]:
        return {
            "PATH": f"{self.fake_bin}:/bin:/usr/bin",
            "HOME": str(self.home),
            "TMPDIR": str(self.temp),
            "LC_ALL": "C",
            "LC_CTYPE": "C",
            "LANG": "C",
            **overrides,
        }

    def run(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", "-p", str(self.script)],
            env=self.environment(**overrides),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            check=False,
        )

    def calls(self) -> list[list[str]]:
        return self._calls_from(self.log)

    @staticmethod
    def _calls_from(path: Path) -> list[list[str]]:
        if not path.exists():
            return []
        calls: list[list[str]] = []
        for block in path.read_text(encoding="utf-8").split("CALL\n"):
            args = block.strip().splitlines()
            if args:
                calls.append(args)
        return calls

    def npm_calls(self) -> list[list[str]]:
        return self._calls_from(self.npm_log)

    def npx_calls(self) -> list[list[str]]:
        return self._calls_from(self.npx_log)

    def assert_versions(self, prefix: str) -> None:
        for skill in SKILLS:
            assert (self.store / skill / "SKILL.md").read_text(
                encoding="utf-8"
            ) == f"{prefix}:{skill}\n"
        assert (self.store / "unrelated-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        ) == "untouched\n"

    def assert_no_staging(self) -> None:
        assert not list(self.temp.glob("e2e-skills-reinstall.*"))

    def assert_one_cli_artifact(self) -> None:
        executables = self.exec_log.read_text(encoding="utf-8").splitlines()
        assert executables
        assert len(set(executables)) == 1, executables
        assert executables[0].endswith(
            "/cli-install/node_modules/skills/bin/cli.mjs"
        ), executables

    def remove_installed_skills(self) -> None:
        for skill in SKILLS:
            shutil.rmtree(self.store / skill)

    def assert_skills_absent(self) -> None:
        for skill in SKILLS:
            assert not (self.store / skill).exists()
        assert (self.store / "unrelated-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        ) == "untouched\n"

    def assert_presence(self, present: set[str]) -> None:
        for skill in SKILLS:
            installed = self.store / skill
            if skill in present:
                assert installed.joinpath("SKILL.md").read_text(
                    encoding="utf-8"
                ) == f"old:{skill}\n"
            else:
                assert not installed.exists()
        assert (self.store / "unrelated-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        ) == "untouched\n"


def expected(source: Path, skills: list[str] = SKILLS) -> list[list[str]]:
    common = ["-g", "-a", "claude-code", "-a", "codex"]
    return [
        [
            "add",
            str(source),
            "--skill",
            *skills,
            *common,
            "--copy",
            "-y",
        ],
    ]


def expected_remove() -> list[str]:
    return [
        "remove",
        *SKILLS,
        "-g",
        "-a",
        "claude-code",
        "-a",
        "codex",
        "-y",
    ]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run()
        assert result.returncode == 0, result.stdout
        assert harness.calls() == expected(harness.repo), harness.calls()
        npm_calls = harness.npm_calls()
        assert npm_calls[:4] == [
            ["view", "skills@1.5.21", "name"],
            ["view", "skills@1.5.21", "version"],
            ["view", "skills@1.5.21", "repository.url"],
            ["view", "skills@1.5.21", "dist.integrity"],
        ]
        assert len(npm_calls) == 6, npm_calls
        assert npm_calls[4][0:3] == [
            "pack",
            "skills@1.5.21",
            "--ignore-scripts",
        ]
        assert npm_calls[4][3] == "--pack-destination"
        assert npm_calls[4][5] == "--json"
        assert npm_calls[5] == [
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ]
        assert harness.npx_calls() == []
        harness.assert_versions("new")
        for skill in SKILLS:
            projection = harness.claude_store / skill
            assert projection.is_symlink()
            assert projection.resolve() == (harness.store / skill).resolve()
        harness.assert_one_cli_artifact()
        assert not harness.agent_log.exists()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        hostile = harness.temp / "hostile-path"
        hostile.mkdir()
        sentinels = []
        for executable in ("node", "npm", "npx"):
            sentinel = harness.temp / f"hostile-{executable}-ran"
            sentinels.append(sentinel)
            shadow = hostile / executable
            shadow.write_text(
                f"#!/bin/sh\nprintf ran > {str(sentinel)!r}\nexit 99\n",
                encoding="utf-8",
            )
            shadow.chmod(0o755)
        result = harness.run(PATH=f"{hostile}:{harness.fake_bin}:/bin:/usr/bin")
        assert result.returncode == 0, result.stdout
        assert not any(path.exists() for path in sentinels), (
            "PATH-shadowed Node/npm/npx must never run"
        )
        assert harness.npx_calls() == []
        harness.assert_versions("new")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        original_npm = harness.fake_bin / "npm"
        unexpected_target = harness.temp / "user-writable-npm"
        original_npm.rename(unexpected_target)
        original_npm.symlink_to(unexpected_target)
        result = harness.run()
        assert result.returncode == 2, result.stdout
        assert "no trusted system/package-manager Node/npm/npx trio" in result.stdout
        assert harness.npm_calls() == []
        assert harness.calls() == []
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(E2E_SKILLS_NPX="/tmp/hostile-npx")
        assert result.returncode == 2, result.stdout
        assert "E2E_SKILLS_NPX is not supported" in result.stdout
        assert harness.npm_calls() == []
        assert harness.npx_calls() == []
        assert harness.calls() == []
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        redirected_home = harness.temp / "redirected-home"
        redirected_home.symlink_to(harness.home, target_is_directory=True)
        result = harness.run(HOME=str(redirected_home))
        assert result.returncode == 2, result.stdout
        assert "refusing redirected global skills destination" in result.stdout
        assert harness.calls() == []
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_REGISTRY_VERSION="1.5.22")
        assert result.returncode == 2, result.stdout
        assert "registry identity/version/integrity mismatch" in result.stdout
        assert harness.npx_calls() == []
        assert harness.calls() == [], "registry drift must fail before mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_REGISTRY_INTEGRITY="sha512-drift")
        assert result.returncode == 2, result.stdout
        assert "registry identity/version/integrity mismatch" in result.stdout
        assert harness.calls() == [], "integrity drift must fail before mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_PACK_CORRUPT="1")
        assert result.returncode == 2, result.stdout
        assert "packed skills CLI integrity mismatch" in result.stdout
        assert harness.calls() == [], "tarball drift must fail before mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_CLI_VERSION="1.5.20")
        assert result.returncode == 2, result.stdout
        assert "packed skills CLI reported version mismatch" in result.stdout
        assert harness.calls() == [], "CLI mismatch must fail before mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_INSTALL_TAMPER="1")
        assert result.returncode == 2, result.stdout
        assert (
            "dependency closure drifted" in result.stdout
            or "differs from verified artifact" in result.stdout
        )
        assert harness.calls() == [], "staged install drift must fail before mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_DEPENDENCY_TAMPER="1")
        assert result.returncode == 2, result.stdout
        assert "dependency closure drifted" in result.stdout
        assert harness.calls() == [], "dependency drift must fail before mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_DEPENDENCY_FILE_TAMPER="1")
        assert result.returncode == 2, result.stdout
        assert "dependency closure drifted" in result.stdout
        assert harness.calls() == [], (
            "dependency file tampering must fail before executing the CLI"
        )
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        lock = (
            harness.repo
            / "scripts"
            / "dev"
            / "skills-cli-bootstrap-package-lock.json"
        )
        lock.write_text(lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        result = harness.run()
        assert result.returncode == 2, result.stdout
        assert "bootstrap manifest drifted" in result.stdout
        assert harness.npm_calls() == []
        assert harness.calls() == []
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(E2E_SKILLS_INSTALL_CODEX_AGENTS="invalid")
        assert result.returncode == 2, result.stdout
        assert harness.calls() == [], "environment validation must precede mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(E2E_SKILLS_AGENTS="-a codex unexpected")
        assert result.returncode == 2, result.stdout
        assert harness.calls() == [], "agent argv validation must precede mutation"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(E2E_SKILLS_AGENTS="-a opencode")
        assert result.returncode == 2, result.stdout
        assert "unsupported receiving-surface agent: opencode" in result.stdout
        assert harness.calls() == []
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_FAIL_CALL="1")
        assert result.returncode == 91, result.stdout
        calls = harness.calls()
        assert len(calls) == 3, calls
        assert calls[0] == expected(harness.repo)[0]
        assert calls[1] == expected_remove()
        rollback = calls[2]
        assert rollback[0] == "add"
        assert "e2e-skills-reinstall." in rollback[1]
        assert rollback[2:] == expected(Path(rollback[1]))[0][2:]
        harness.assert_versions("old")
        harness.assert_one_cli_artifact()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_WRITE_BEFORE_FAIL_CALL="1")
        assert result.returncode == 93, result.stdout
        calls = harness.calls()
        assert len(calls) == 3, calls
        assert calls[0] == expected(harness.repo)[0]
        assert calls[1] == expected_remove()
        rollback = calls[2]
        assert rollback[0] == "add"
        assert "e2e-skills-reinstall." in rollback[1]
        assert rollback[2:] == expected(Path(rollback[1]))[0][2:]
        harness.assert_versions("old")
        harness.assert_one_cli_artifact()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(
            FAKE_SIGNAL_AFTER_WRITE_CALL="1",
            FAKE_SIGNAL="SIGTERM",
        )
        assert result.returncode == -15, result.stdout
        assert "signal TERM failed; previous four-skill state restored" in (
            result.stdout
        )
        calls = harness.calls()
        assert len(calls) == 3, calls
        assert calls[0] == expected(harness.repo)[0]
        assert calls[1] == expected_remove()
        harness.assert_versions("old")
        harness.assert_one_cli_artifact()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_NOOP_CALL="1")
        assert result.returncode == 1, result.stdout
        assert "installed receiving surface digest mismatch" in result.stdout
        assert "post-install verification failed; previous four-skill state restored" in (
            result.stdout
        )
        assert len(harness.calls()) == 3, harness.calls()
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_PARTIAL_SUCCESS_CALL="1")
        assert result.returncode == 1, result.stdout
        assert "installed receiving surface digest mismatch" in result.stdout
        assert len(harness.calls()) == 3, harness.calls()
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        codex_shadow = harness.home / ".codex" / "skills" / SKILLS[0]
        codex_shadow.mkdir(parents=True)
        (codex_shadow / "SKILL.md").write_text(
            "stale-codex-shadow\n",
            encoding="utf-8",
        )
        result = harness.run()
        assert result.returncode == 1, result.stdout
        assert "Codex shadow receiving surface is stale" in result.stdout
        assert "previous four-skill state restored" in result.stdout
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        harness.remove_installed_skills()
        result = harness.run(FAKE_WRITE_BEFORE_FAIL_CALL="1")
        assert result.returncode == 93, result.stdout
        assert harness.calls() == [
            expected(harness.repo)[0],
            expected_remove(),
        ]
        harness.assert_skills_absent()
        harness.assert_one_cli_artifact()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        prior = {SKILLS[0], SKILLS[2]}
        for skill in set(SKILLS) - prior:
            shutil.rmtree(harness.store / skill)
        result = harness.run(FAKE_WRITE_BEFORE_FAIL_CALL="1")
        assert result.returncode == 93, result.stdout
        calls = harness.calls()
        assert len(calls) == 3, calls
        rollback = calls[2]
        assert rollback[3 : 3 + len(prior)] == [
            skill for skill in SKILLS if skill in prior
        ]
        harness.assert_presence(prior)
        harness.assert_one_cli_artifact()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        linked_source = harness.temp / "legacy-symlink-install"
        shutil.copytree(harness.store / SKILLS[0], linked_source)
        shutil.rmtree(harness.store / SKILLS[0])
        (harness.store / SKILLS[0]).symlink_to(linked_source, target_is_directory=True)
        result = harness.run(FAKE_WRITE_BEFORE_FAIL_CALL="1")
        assert result.returncode == 93, result.stdout
        harness.assert_versions("old")
        assert not (harness.store / SKILLS[0]).is_symlink()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        (harness.store / SKILLS[0] / "escape").symlink_to("/etc")
        result = harness.run()
        assert result.returncode == 2, result.stdout
        assert "nested symlinks" in result.stdout
        assert harness.calls() == [], "unsafe staging must fail before replacement"
        harness.assert_versions("old")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_FAIL_CALLS="1,2")
        assert result.returncode == 1, result.stdout
        assert "original status 91" in result.stdout
        assert "rollback remove status 91" in result.stdout
        assert len(harness.calls()) == 3, harness.calls()
        harness.assert_one_cli_artifact()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(
            E2E_SKILLS_INSTALL_CODEX_AGENTS="1",
            FAKE_AGENT_INSTALL_STATUS="73",
        )
        assert result.returncode == 73, result.stdout
        assert "optional Codex agent install failed" in result.stdout
        assert len(harness.calls()) == 3, harness.calls()
        harness.assert_versions("old")
        harness.assert_one_cli_artifact()
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(E2E_SKILLS_INSTALL_CODEX_AGENTS="1")
        assert result.returncode == 0, result.stdout
        assert harness.agent_log.read_text(encoding="utf-8") == "CALL\n"

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_CLEANUP_STATUS="77")
        assert result.returncode == 77, result.stdout
        assert "staging cleanup failed with status 77" in result.stdout
        harness.assert_versions("new")
        harness.assert_no_staging()

    with tempfile.TemporaryDirectory(prefix="reinstall-skills-contract-") as raw:
        harness = Harness(Path(raw))
        result = harness.run(FAKE_FAIL_CALL="1", FAKE_CLEANUP_STATUS="77")
        assert result.returncode == 91, result.stdout
        assert "add failed; previous four-skill state restored" in result.stdout
        assert (
            "staging cleanup also failed with status 77 "
            "while exiting after status 91"
        ) in result.stdout
        harness.assert_versions("old")
        harness.assert_no_staging()

    print(
        "reinstall skills contract: pass "
        "(trusted tools; verified package; rollback; signal safety; "
        "cleanup propagation)"
    )


if __name__ == "__main__":
    main()
