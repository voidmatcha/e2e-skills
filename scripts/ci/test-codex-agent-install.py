#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for safe Codex-native agent installation."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts/dev/install-codex-agents.sh"
AGENT_NAMES = ("e2e-finding-verifier", "e2e-failure-classifier")


def run_installer(
    codex_home: Path,
    *,
    force: bool = False,
    env_overrides: dict[str, str] | None = None,
    installer: Path = INSTALLER,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    if force:
        env["E2E_SKILLS_FORCE_CODEX_AGENTS"] = "1"
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["/bin/bash", "-p", str(installer)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_installs_exact_files_without_temp_leftovers(base: Path) -> None:
    codex_home = base / "normal"
    result = run_installer(codex_home)
    assert result.returncode == 0, result.stderr
    for name in AGENT_NAMES:
        source = ROOT / f".codex/agents/{name}.toml"
        destination = codex_home / f"agents/{name}.toml"
        assert destination.read_bytes() == source.read_bytes()
    assert not list((codex_home / "agents").glob(".*.tmp.*"))


def test_rejects_symlinked_destination_file(base: Path) -> None:
    codex_home = base / "file-link"
    agents = codex_home / "agents"
    agents.mkdir(parents=True)
    victim = base / "victim.toml"
    victim.write_text("do not replace\n", encoding="utf-8")
    (agents / "e2e-finding-verifier.toml").symlink_to(victim)

    result = run_installer(codex_home, force=True)
    assert result.returncode != 0
    assert "refusing symlinked destination file" in result.stderr
    assert victim.read_text(encoding="utf-8") == "do not replace\n"


def test_rejects_symlinked_destination_directory(base: Path) -> None:
    codex_home = base / "dir-link"
    codex_home.mkdir()
    redirected = base / "redirected-agents"
    redirected.mkdir()
    (codex_home / "agents").symlink_to(redirected, target_is_directory=True)

    result = run_installer(codex_home, force=True)
    assert result.returncode != 0
    assert "refusing symlinked destination directory" in result.stderr
    assert not list(redirected.iterdir())


def test_rejects_symlinked_codex_home(base: Path) -> None:
    real_home = base / "real-codex-home"
    real_home.mkdir()
    linked_home = base / "linked-codex-home"
    linked_home.symlink_to(real_home, target_is_directory=True)

    result = run_installer(linked_home, force=True)
    assert result.returncode != 0
    assert "refusing redirected Codex home" in result.stderr
    assert not list(real_home.iterdir())


def test_rejects_non_regular_destination(base: Path) -> None:
    codex_home = base / "non-regular"
    destination = codex_home / "agents/e2e-finding-verifier.toml"
    destination.mkdir(parents=True)

    result = run_installer(codex_home, force=True)
    assert result.returncode != 0
    assert "refusing non-regular destination file" in result.stderr
    assert destination.is_dir()


def write_owned_prior_agents(codex_home: Path) -> dict[str, bytes]:
    agents = codex_home / "agents"
    agents.mkdir(parents=True)
    prior: dict[str, bytes] = {}
    for index, name in enumerate(AGENT_NAMES):
        content = (
            f"# e2e-skills Codex/OMX native agent: prior {name}\n"
            f'name = "{name}"\n'
        ).encode()
        destination = agents / f"{name}.toml"
        destination.write_bytes(content)
        destination.chmod(0o600 + index * 0o044)
        prior[name] = content
    return prior


def write_faulting_mv(
    base: Path, *, signal: str | None = None
) -> tuple[Path, Path]:
    fake_bin = base / ("signal-bin" if signal else "failure-bin")
    fake_bin.mkdir()
    count = base / ("signal-mv-count" if signal else "failure-mv-count")
    fake_mv = fake_bin / "mv"
    action = (
        f'kill -{signal} "$PPID"\nexit 143\n'
        if signal
        else "exit 74\n"
    )
    fake_mv.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        f"count_file={str(count)!r}\n"
        'value=0\n[ ! -f "$count_file" ] || value=$(cat "$count_file")\n'
        'value=$((value + 1))\nprintf "%s\\n" "$value" > "$count_file"\n'
        'if [ "$value" -eq 2 ]; then\n'
        f"{action}"
        "fi\n"
        'exec /bin/mv "$@"\n',
        encoding="utf-8",
    )
    fake_mv.chmod(0o755)
    return fake_bin, count


def installer_with_mv(base: Path, fake_mv: Path) -> Path:
    repo = base / "installer-fixture"
    installer = repo / "scripts/dev/install-codex-agents.sh"
    installer.parent.mkdir(parents=True)
    for name in AGENT_NAMES:
        source = ROOT / f".codex/agents/{name}.toml"
        destination = repo / f".codex/agents/{name}.toml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    text = INSTALLER.read_text(encoding="utf-8")
    text = text.replace("MV=/bin/mv", f"MV={fake_mv}")
    installer.write_text(text, encoding="utf-8")
    installer.chmod(0o755)
    return installer


def test_ignores_writable_path_tool_shadows(base: Path) -> None:
    codex_home = base / "ambient-path"
    fake_bin = base / "ambient-bin"
    fake_bin.mkdir()
    sentinel = base / "ambient-tool-ran"
    for name in (
        "node",
        "npm",
        "npx",
        "cp",
        "mv",
        "rm",
        "mkdir",
        "mktemp",
        "chmod",
        "cmp",
        "grep",
        "sed",
        "head",
        "dirname",
        "pwd",
    ):
        executable = fake_bin / name
        executable.write_text(
            f"#!/bin/sh\nprintf '%s\\n' {name!r} >> {str(sentinel)!r}\nexit 97\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
    result = run_installer(
        codex_home,
        env_overrides={"PATH": f"{fake_bin}:/bin:/usr/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert not sentinel.exists(), "ambient PATH-selected tool executed"


def test_second_commit_failure_restores_both_prior_files(base: Path) -> None:
    codex_home = base / "commit-failure"
    prior = write_owned_prior_agents(codex_home)
    fake_bin, _ = write_faulting_mv(base)
    result = run_installer(
        codex_home,
        installer=installer_with_mv(base / "failure-installer", fake_bin / "mv"),
    )
    assert result.returncode == 74, result.stderr
    assert "previous agent state restored" in result.stderr
    for name, content in prior.items():
        destination = codex_home / f"agents/{name}.toml"
        assert destination.read_bytes() == content
    assert (codex_home / f"agents/{AGENT_NAMES[0]}.toml").stat().st_mode & 0o777 == 0o600
    assert (codex_home / f"agents/{AGENT_NAMES[1]}.toml").stat().st_mode & 0o777 == 0o644
    assert not list((codex_home / "agents").glob(".e2e-skills-agents.*"))


def test_second_commit_failure_removes_new_files_when_none_existed(base: Path) -> None:
    codex_home = base / "commit-failure-absent"
    fault_base = base / "absent-fault"
    fault_base.mkdir()
    fake_bin, _ = write_faulting_mv(fault_base)
    result = run_installer(
        codex_home,
        installer=installer_with_mv(
            fault_base / "failure-installer", fake_bin / "mv"
        ),
    )
    assert result.returncode == 74, result.stderr
    for name in AGENT_NAMES:
        assert not (codex_home / f"agents/{name}.toml").exists()
    assert not list((codex_home / "agents").glob(".e2e-skills-agents.*"))


def test_commit_signals_roll_back_and_are_re_raised(base: Path) -> None:
    for signal, number in (("HUP", 1), ("INT", 2), ("TERM", 15)):
        case = base / signal.lower()
        case.mkdir()
        codex_home = case / "commit-signal"
        prior = write_owned_prior_agents(codex_home)
        fake_bin, _ = write_faulting_mv(case, signal=signal)
        result = run_installer(
            codex_home,
            installer=installer_with_mv(
                case / "signal-installer", fake_bin / "mv"
            ),
        )
        assert result.returncode == -number, result
        for name, content in prior.items():
            assert (codex_home / f"agents/{name}.toml").read_bytes() == content
        assert not list((codex_home / "agents").glob(".e2e-skills-agents.*"))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-codex-agent-install-") as raw:
        base = Path(raw)
        test_installs_exact_files_without_temp_leftovers(base)
        test_rejects_symlinked_destination_file(base)
        test_rejects_symlinked_destination_directory(base)
        test_rejects_symlinked_codex_home(base)
        test_rejects_non_regular_destination(base)
        test_ignores_writable_path_tool_shadows(base)
        test_second_commit_failure_restores_both_prior_files(base)
        test_second_commit_failure_removes_new_files_when_none_existed(base)
        test_commit_signals_roll_back_and_are_re_raised(base)
    print(
        "codex agent install: pass "
        "(trusted tools, transaction rollback, signal re-raise, symlink rejection)"
    )


if __name__ == "__main__":
    main()
