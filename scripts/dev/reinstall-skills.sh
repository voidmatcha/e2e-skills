#!/bin/bash -p
# Reinstall the 4 e2e-skills from this repo via the official `skills` CLI.
# Removes any prior install (including older symlink installs) of these
# specific skills, then re-adds them as real copies (--copy). Copy mode
# snapshots the current working tree at invocation time, including uncommitted
# edits. Later source edits do not leak into that installed copy. The pre-push
# hook calls this script on every push, so first push acts as initial install.
#
# Overrides:
#   E2E_SKILLS_AGENTS  default: "-a claude-code -a codex"
#                      trusted receiving-surface verification currently
#                      supports claude-code and codex only
#   E2E_SKILLS_INSTALL_CODEX_AGENTS  default: "0"
#                      (set to "1" to install the optional named Codex agents globally)

set -euo pipefail
set -f

# Bind the utility surface before resolving repository or package-manager paths.
# Package-manager executables are selected separately from an explicit allowlist.
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
export PATH
unset BASH_ENV ENV CDPATH NODE_OPTIONS NODE_PATH

DIRNAME=/usr/bin/dirname
READLINK=/usr/bin/readlink
PWD_CMD=/bin/pwd
ENV_CMD=/usr/bin/env
FIND=/usr/bin/find
GREP=/usr/bin/grep
CP=/bin/cp
RM=/bin/rm
MKDIR=/bin/mkdir
MKTEMP=/usr/bin/mktemp
TAR=/usr/bin/tar
BASH_CMD=/bin/bash
KILL=/bin/kill

REPO_ROOT="$(cd "$("$DIRNAME" "$0")/../.." && "$PWD_CMD" -P)"
SKILLS=(cypress-debugger e2e-reviewer playwright-debugger playwright-test-generator)
SKILLS_CLI_PACKAGE="skills"
SKILLS_CLI_VERSION="1.5.21"
SKILLS_CLI_SPEC="$SKILLS_CLI_PACKAGE@$SKILLS_CLI_VERSION"
SKILLS_CLI_REPOSITORY="git+https://github.com/vercel-labs/skills.git"
SKILLS_CLI_INTEGRITY="sha512-CJ4wx692UkQAW+DLpjJg/ww6dJBojq5E8sQBOqP639GutO72v4EFiV/fq1etW2r9NhM/mwaIq8YoqKFJ9XV7ng=="
SKILLS_CLI_BOOTSTRAP_PACKAGE="$REPO_ROOT/scripts/dev/skills-cli-bootstrap-package.json"
SKILLS_CLI_BOOTSTRAP_LOCK="$REPO_ROOT/scripts/dev/skills-cli-bootstrap-package-lock.json"
SKILLS_CLI_INSTALLED_TREE_MANIFEST="$REPO_ROOT/scripts/dev/skills-cli-installed-tree-sha256.json"
SKILLS_CLI_BOOTSTRAP_PACKAGE_SHA256="77c3c1007e50b981ffdc3c4d1b5a2a0b925c5e80869356cd20794083e70221ba"
SKILLS_CLI_BOOTSTRAP_LOCK_SHA256="f5ca6fde39796c63ddfbf75b92b5b710728a77b62c5a8d01a0e05e628313b4a9"
SKILLS_CLI_INSTALLED_TREE_MANIFEST_SHA256="63c78c35f08046546f7e89f461ae234ae9800bed2e770a7c43c71e0ccb222fa6"

# Do not accept executable/package overrides for this global-write path. Bind
# npm/npx beside the selected Node launcher, clear ambient Node/npm injection,
# and verify the exact official package before touching an installation.
for override in \
  E2E_SKILLS_NODE \
  E2E_SKILLS_NPM \
  E2E_SKILLS_NPX \
  E2E_SKILLS_CLI_PACKAGE \
  E2E_SKILLS_CLI_VERSION \
  E2E_SKILLS_CLI_INTEGRITY
do
  if [ -n "${!override:-}" ]; then
    echo "reinstall-skills: $override is not supported for this trusted install path" >&2
    exit 2
  fi
done

resolve_physical_file() {
  local path=$1
  local link
  local directory
  local leaf
  local hops=0

  case "$path" in
    /*) ;;
    *) return 1 ;;
  esac
  while [ -L "$path" ]; do
    hops=$((hops + 1))
    [ "$hops" -le 16 ] || return 1
    link="$("$READLINK" "$path")" || return 1
    case "$link" in
      /*) path=$link ;;
      *) path="${path%/*}/$link" ;;
    esac
  done
  [ -f "$path" ] || return 1
  directory="${path%/*}"
  leaf="${path##*/}"
  directory="$(cd -P "$directory" 2>/dev/null && "$PWD_CMD" -P)" || return 1
  printf '%s/%s\n' "$directory" "$leaf"
}

trusted_trio_targets() {
  local node_launcher=$1
  local node_real=$2
  local npm_real=$3
  local npx_real=$4

  case "$node_launcher|$node_real|$npm_real|$npx_real" in
    /opt/homebrew/bin/node\|/opt/homebrew/Cellar/node/*/bin/node\|/opt/homebrew/lib/node_modules/npm/bin/npm-cli.js\|/opt/homebrew/lib/node_modules/npm/bin/npx-cli.js) return 0 ;;
    /usr/local/bin/node\|/usr/local/Cellar/node/*/bin/node\|/usr/local/lib/node_modules/npm/bin/npm-cli.js\|/usr/local/lib/node_modules/npm/bin/npx-cli.js) return 0 ;;
    /usr/bin/node\|/usr/bin/node\|/usr/share/nodejs/npm/bin/npm-cli.js\|/usr/share/nodejs/npm/bin/npx-cli.js) return 0 ;;
    /usr/bin/node\|/usr/bin/node\|/usr/lib/node_modules/npm/bin/npm-cli.js\|/usr/lib/node_modules/npm/bin/npx-cli.js) return 0 ;;
    /bin/node\|/usr/bin/node\|/usr/share/nodejs/npm/bin/npm-cli.js\|/usr/share/nodejs/npm/bin/npx-cli.js) return 0 ;;
    # TEST_TRUSTED_NODE_TRIO
    *) return 1 ;;
  esac
}

TRUSTED_NODE_TRIOS=(
  "/opt/homebrew/bin/node|/opt/homebrew/bin/npm|/opt/homebrew/bin/npx"
  "/usr/local/bin/node|/usr/local/bin/npm|/usr/local/bin/npx"
  "/usr/bin/node|/usr/bin/npm|/usr/bin/npx"
  "/bin/node|/bin/npm|/bin/npx"
)
NODE_EXECUTABLE=
NPM_CLI=
for trusted_trio in "${TRUSTED_NODE_TRIOS[@]}"; do
  IFS='|' read -r node_candidate npm_candidate npx_candidate <<<"$trusted_trio"
  [ -x "$node_candidate" ] && [ -e "$npm_candidate" ] && [ -e "$npx_candidate" ] ||
    continue
  node_real="$(resolve_physical_file "$node_candidate")" || continue
  npm_real="$(resolve_physical_file "$npm_candidate")" || continue
  npx_real="$(resolve_physical_file "$npx_candidate")" || continue
  trusted_trio_targets "$node_candidate" "$node_real" "$npm_real" "$npx_real" ||
    continue
  NODE_EXECUTABLE=$node_real
  NPM_CLI=$npm_real
  break
done
if [ -z "$NODE_EXECUTABLE" ]; then
  echo "reinstall-skills: no trusted system/package-manager Node/npm/npx trio found" >&2
  exit 2
fi

file_sha256() {
  "$NODE_EXECUTABLE" -e '
    const crypto = require("crypto");
    const fs = require("fs");
    const path = process.argv[1];
    const stat = fs.lstatSync(path);
    if (!stat.isFile() || stat.isSymbolicLink()) process.exit(2);
    process.stdout.write(
      crypto.createHash("sha256").update(fs.readFileSync(path)).digest("hex")
    );
  ' "$1"
}

strict_tree_digest() {
  "$NODE_EXECUTABLE" -e '
    const crypto = require("crypto");
    const fs = require("fs");
    const path = require("path");
    const root = process.argv[1];
    const hash = crypto.createHash("sha256");
    function visit(relative) {
      const absolute = path.join(root, relative);
      const stat = fs.lstatSync(absolute);
      if (stat.isSymbolicLink()) throw new Error("symlink:" + relative);
      const mode = (stat.mode & 0o777).toString(8);
      if (stat.isDirectory()) {
        hash.update("D\0" + relative + "\0" + mode + "\0");
        for (const name of fs.readdirSync(absolute).sort()) {
          visit(path.join(relative, name));
        }
      } else if (stat.isFile()) {
        hash.update(
          "F\0" + relative + "\0" + mode + "\0" + stat.size + "\0"
        );
        hash.update(fs.readFileSync(absolute));
      } else {
        throw new Error("unsupported:" + relative);
      }
    }
    visit("");
    process.stdout.write(hash.digest("hex"));
  ' "$1"
}

tree_digest() {
  "$NODE_EXECUTABLE" -e '
    const crypto = require("crypto");
    const fs = require("fs");
    const path = require("path");
    const root = process.argv[1];
    const hash = crypto.createHash("sha256");
    function visit(relative) {
      const name = path.basename(relative);
      if (name === "__pycache__" || name === ".DS_Store" ||
          name.endsWith(".pyc")) return;
      const absolute = path.join(root, relative);
      const stat = fs.lstatSync(absolute);
      if (stat.isSymbolicLink()) throw new Error("symlink:" + relative);
      if (stat.isDirectory()) {
        hash.update("D\0" + relative + "\0");
        for (const name of fs.readdirSync(absolute).sort()) {
          visit(path.join(relative, name));
        }
      } else if (stat.isFile()) {
        hash.update("F\0" + relative + "\0" + stat.size + "\0");
        hash.update(fs.readFileSync(absolute));
      } else {
        throw new Error("unsupported:" + relative);
      }
    }
    visit("");
    process.stdout.write(hash.digest("hex"));
  ' "$1"
}

verify_locked_closure() {
  "$NODE_EXECUTABLE" -e '
    const crypto = require("crypto");
    const fs = require("fs");
    const path = require("path");
    const installRoot = process.argv[1];
    const lockPath = process.argv[2];
    const digestManifestPath = process.argv[3];
    const lock = JSON.parse(fs.readFileSync(lockPath, "utf8"));
    const expectedDigests = JSON.parse(
      fs.readFileSync(digestManifestPath, "utf8")
    );
    if (lock.lockfileVersion !== 3 || lock.requires !== true ||
        !lock.packages || typeof lock.packages !== "object") {
      throw new Error("invalid-lock-contract");
    }
    const expected = new Map(
      Object.entries(lock.packages).filter(([relative]) => relative !== "")
    );
    if (Object.keys(expectedDigests).length !== expected.size ||
        [...expected.keys()].some(
          (name) => !/^[0-9a-f]{64}$/.test(expectedDigests[name] || "")
        )) {
      throw new Error("installed-tree-manifest-drift");
    }
    const actual = new Set();
    function strictDigest(root) {
      const hash = crypto.createHash("sha256");
      function visit(relative) {
        const absolute = path.join(root, relative);
        const stat = fs.lstatSync(absolute);
        if (stat.isSymbolicLink()) throw new Error("symlink:" + relative);
        const mode = (stat.mode & 0o777).toString(8);
        if (stat.isDirectory()) {
          hash.update("D\0" + relative + "\0" + mode + "\0");
          for (const name of fs.readdirSync(absolute).sort()) {
            visit(path.join(relative, name));
          }
        } else if (stat.isFile()) {
          hash.update(
            "F\0" + relative + "\0" + mode + "\0" + stat.size + "\0"
          );
          hash.update(fs.readFileSync(absolute));
        } else {
          throw new Error("unsupported:" + relative);
        }
      }
      visit("");
      return hash.digest("hex");
    }
    const expectedBins = new Map();
    for (const [relative, contract] of expected) {
      if (!contract.bin) continue;
      const bins = typeof contract.bin === "string"
        ? {[relative.split("/").pop()]: contract.bin}
        : contract.bin;
      for (const [name, target] of Object.entries(bins)) {
        if (typeof target !== "string" || target.startsWith("/") ||
            target.split("/").includes("..") || expectedBins.has(name)) {
          throw new Error("invalid-bin-contract:" + name);
        }
        expectedBins.set(name, path.join(relative, target));
      }
    }
    function inspectBins(binRoot) {
      const stat = fs.lstatSync(binRoot);
      if (!stat.isDirectory() || stat.isSymbolicLink()) {
        throw new Error("unsafe-bin-directory");
      }
      const actualBins = new Set();
      for (const name of fs.readdirSync(binRoot).sort()) {
        const absolute = path.join(binRoot, name);
        const linkStat = fs.lstatSync(absolute);
        if (!linkStat.isSymbolicLink() || !expectedBins.has(name)) {
          throw new Error("unexpected-bin:" + name);
        }
        const expectedTarget = fs.realpathSync(
          path.resolve(installRoot, expectedBins.get(name))
        );
        const actualTarget = fs.realpathSync(absolute);
        if (actualTarget !== expectedTarget ||
            !fs.lstatSync(actualTarget).isFile()) {
          throw new Error("bin-target-drift:" + name);
        }
        actualBins.add(name);
      }
      if (actualBins.size !== expectedBins.size ||
          [...expectedBins.keys()].some((name) => !actualBins.has(name))) {
        throw new Error("bin-closure-drift");
      }
    }
    function packageDirectories(nodeModules, relativePrefix) {
      const stat = fs.lstatSync(nodeModules);
      if (!stat.isDirectory() || stat.isSymbolicLink()) {
        throw new Error("unsafe-node-modules:" + relativePrefix);
      }
      for (const entry of fs.readdirSync(nodeModules).sort()) {
        if (entry === ".package-lock.json") continue;
        if (entry === ".bin") {
          if (relativePrefix !== "") {
            throw new Error("unexpected-nested-bin:" + relativePrefix);
          }
          inspectBins(path.join(nodeModules, entry));
          continue;
        }
        const absolute = path.join(nodeModules, entry);
        const entryStat = fs.lstatSync(absolute);
        if (entryStat.isSymbolicLink()) throw new Error("symlink:" + absolute);
        if (entry.startsWith("@")) {
          if (!entryStat.isDirectory()) throw new Error("invalid-scope:" + entry);
          for (const scopedName of fs.readdirSync(absolute).sort()) {
            const scopedAbsolute = path.join(absolute, scopedName);
            const relative = path.join(
              relativePrefix, "node_modules", entry, scopedName
            );
            inspectPackage(scopedAbsolute, relative);
          }
        } else {
          const relative = path.join(relativePrefix, "node_modules", entry);
          inspectPackage(absolute, relative);
        }
      }
    }
    function inspectPackage(absolute, relative) {
      const stat = fs.lstatSync(absolute);
      if (!stat.isDirectory() || stat.isSymbolicLink()) {
        throw new Error("unsafe-package:" + relative);
      }
      const normalized = relative.split(path.sep).join("/");
      actual.add(normalized);
      const contract = expected.get(normalized);
      if (!contract || typeof contract.version !== "string" ||
          typeof contract.integrity !== "string" ||
          !contract.integrity.startsWith("sha512-")) {
        throw new Error("unexpected-package:" + normalized);
      }
      const packageJson = path.join(absolute, "package.json");
      const packageStat = fs.lstatSync(packageJson);
      if (!packageStat.isFile() || packageStat.isSymbolicLink()) {
        throw new Error("unsafe-package-json:" + normalized);
      }
      const metadata = JSON.parse(fs.readFileSync(packageJson, "utf8"));
      if (metadata.version !== contract.version) {
        throw new Error("version-drift:" + normalized);
      }
      if (strictDigest(absolute) !== expectedDigests[normalized]) {
        throw new Error("installed-tree-drift:" + normalized);
      }
      const nested = path.join(absolute, "node_modules");
      if (fs.existsSync(nested)) packageDirectories(nested, normalized);
    }
    packageDirectories(path.join(installRoot, "node_modules"), "");
    if (actual.size !== expected.size ||
        [...expected.keys()].some((name) => !actual.has(name))) {
      throw new Error("dependency-closure-drift");
    }
  ' "$1" "$2" "$3"
}

bootstrap_package_sha256="$(file_sha256 "$SKILLS_CLI_BOOTSTRAP_PACKAGE")"
bootstrap_lock_sha256="$(file_sha256 "$SKILLS_CLI_BOOTSTRAP_LOCK")"
installed_tree_manifest_sha256="$(
  file_sha256 "$SKILLS_CLI_INSTALLED_TREE_MANIFEST"
)"
if [ "$bootstrap_package_sha256" != "$SKILLS_CLI_BOOTSTRAP_PACKAGE_SHA256" ] ||
   [ "$bootstrap_lock_sha256" != "$SKILLS_CLI_BOOTSTRAP_LOCK_SHA256" ] ||
   [ "$installed_tree_manifest_sha256" != "$SKILLS_CLI_INSTALLED_TREE_MANIFEST_SHA256" ]; then
  echo "reinstall-skills: pinned skills CLI bootstrap manifest drifted" >&2
  exit 2
fi

STAGING_ROOT="$("$MKTEMP" -d "${TMPDIR:-/tmp}/e2e-skills-reinstall.XXXXXX")"
cleanup() {
  "$RM" -rf -- "$STAGING_ROOT"
}
handle_exit() {
  local original_status=$?
  local cleanup_status=0

  trap - EXIT
  cleanup || cleanup_status=$?
  if [ "$cleanup_status" -ne 0 ]; then
    if [ "$original_status" -eq 0 ]; then
      echo "reinstall-skills: staging cleanup failed with status $cleanup_status" >&2
      exit "$cleanup_status"
    fi
    echo "reinstall-skills: staging cleanup also failed with status $cleanup_status while exiting after status $original_status" >&2
  fi
  exit "$original_status"
}
trap handle_exit EXIT

while IFS='=' read -r variable _; do
  case "$variable" in
    npm_config_*|NPM_CONFIG_*) unset "$variable" ;;
  esac
done < <("$ENV_CMD")
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"
export npm_config_registry="https://registry.npmjs.org/"
export npm_config_userconfig="$STAGING_ROOT/npm-userconfig"
export npm_config_globalconfig="$STAGING_ROOT/npm-globalconfig"
export npm_config_cache="$STAGING_ROOT/npm-cache"
export npm_config_prefix="$STAGING_ROOT/npm-prefix"
export npm_config_ignore_scripts="true"
: >"$npm_config_userconfig"
: >"$npm_config_globalconfig"

run_npm() {
  "$NODE_EXECUTABLE" "$NPM_CLI" "$@"
}

registry_name="$(run_npm view "$SKILLS_CLI_SPEC" name)"
registry_version="$(run_npm view "$SKILLS_CLI_SPEC" version)"
registry_repository="$(run_npm view "$SKILLS_CLI_SPEC" repository.url)"
registry_integrity="$(run_npm view "$SKILLS_CLI_SPEC" dist.integrity)"
if [ "$registry_name" != "$SKILLS_CLI_PACKAGE" ] ||
   [ "$registry_version" != "$SKILLS_CLI_VERSION" ] ||
   [ "$registry_repository" != "$SKILLS_CLI_REPOSITORY" ] ||
   [ "$registry_integrity" != "$SKILLS_CLI_INTEGRITY" ]; then
  echo "reinstall-skills: official skills CLI registry identity/version/integrity mismatch" >&2
  exit 2
fi

PACK_OUTPUT="$STAGING_ROOT/npm-pack.json"
run_npm pack "$SKILLS_CLI_SPEC" --ignore-scripts \
  --pack-destination "$STAGING_ROOT" --json >"$PACK_OUTPUT"
pack_filename="$(
  "$NODE_EXECUTABLE" -e '
    const fs = require("fs");
    const rows = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
    if (!Array.isArray(rows) || rows.length !== 1 ||
        rows[0].filename !== "skills-1.5.21.tgz") process.exit(2);
    process.stdout.write(rows[0].filename);
  ' "$PACK_OUTPUT"
)" || {
  echo "reinstall-skills: npm pack returned an unexpected artifact" >&2
  exit 2
}
SKILLS_TARBALL="$STAGING_ROOT/$pack_filename"
if [ ! -f "$SKILLS_TARBALL" ] || [ -L "$SKILLS_TARBALL" ]; then
  echo "reinstall-skills: packed skills CLI artifact is invalid" >&2
  exit 2
fi
packed_integrity="$(
  "$NODE_EXECUTABLE" -e '
    const crypto = require("crypto");
    const fs = require("fs");
    const digest = crypto.createHash("sha512")
      .update(fs.readFileSync(process.argv[1])).digest("base64");
    process.stdout.write("sha512-" + digest);
  ' "$SKILLS_TARBALL"
)"
if [ "$packed_integrity" != "$SKILLS_CLI_INTEGRITY" ]; then
  echo "reinstall-skills: packed skills CLI integrity mismatch" >&2
  exit 2
fi

PACKAGE_STAGE="$STAGING_ROOT/verified-package"
"$MKDIR" -p "$PACKAGE_STAGE"
"$TAR" -xzf "$SKILLS_TARBALL" -C "$PACKAGE_STAGE"
SKILLS_CLI_PACKAGE_ROOT="$PACKAGE_STAGE/package"
SKILLS_CLI_PACKAGE_JSON="$SKILLS_CLI_PACKAGE_ROOT/package.json"
if [ ! -f "$SKILLS_CLI_PACKAGE_JSON" ] ||
   [ -n "$("$FIND" "$SKILLS_CLI_PACKAGE_ROOT" -type l -print -quit)" ]; then
  echo "reinstall-skills: packed skills CLI contents are invalid" >&2
  exit 2
fi
resolved_contract="$(
  "$NODE_EXECUTABLE" -e '
    const p = require(process.argv[1]);
    const repository = typeof p.repository === "string"
      ? p.repository : p.repository && p.repository.url;
    process.stdout.write(JSON.stringify({
      name: p.name,
      version: p.version,
      repository,
      cli: p.bin && p.bin.skills
    }));
  ' "$SKILLS_CLI_PACKAGE_JSON"
)"
expected_contract='{"name":"skills","version":"1.5.21","repository":"git+https://github.com/vercel-labs/skills.git","cli":"./bin/cli.mjs"}'
if [ "$resolved_contract" != "$expected_contract" ]; then
  echo "reinstall-skills: packed skills CLI identity contract mismatch" >&2
  exit 2
fi
PACKED_CLI_EXECUTABLE="$SKILLS_CLI_PACKAGE_ROOT/bin/cli.mjs"
if [ ! -f "$PACKED_CLI_EXECUTABLE" ] || [ -L "$PACKED_CLI_EXECUTABLE" ]; then
  echo "reinstall-skills: packed skills CLI entrypoint is invalid" >&2
  exit 2
fi

CLI_INSTALL_ROOT="$STAGING_ROOT/cli-install"
"$MKDIR" -p "$CLI_INSTALL_ROOT"
"$CP" "$SKILLS_CLI_BOOTSTRAP_PACKAGE" "$CLI_INSTALL_ROOT/package.json"
"$CP" "$SKILLS_CLI_BOOTSTRAP_LOCK" "$CLI_INSTALL_ROOT/package-lock.json"
(
  cd -P "$CLI_INSTALL_ROOT"
  run_npm ci --ignore-scripts --no-audit --no-fund
)
if ! verify_locked_closure \
  "$CLI_INSTALL_ROOT" \
  "$CLI_INSTALL_ROOT/package-lock.json" \
  "$SKILLS_CLI_INSTALLED_TREE_MANIFEST"; then
  echo "reinstall-skills: installed skills CLI dependency closure drifted" >&2
  exit 2
fi
INSTALLED_PACKAGE_ROOT="$CLI_INSTALL_ROOT/node_modules/$SKILLS_CLI_PACKAGE"
installed_contract="$(
  "$NODE_EXECUTABLE" -e '
    const p = require(process.argv[1]);
    const repository = typeof p.repository === "string"
      ? p.repository : p.repository && p.repository.url;
    process.stdout.write(JSON.stringify({
      name: p.name,
      version: p.version,
      repository,
      cli: p.bin && p.bin.skills
    }));
  ' "$INSTALLED_PACKAGE_ROOT/package.json"
)"
if [ "$installed_contract" != "$expected_contract" ]; then
  echo "reinstall-skills: locally installed skills CLI identity contract mismatch" >&2
  exit 2
fi
SKILLS_CLI_EXECUTABLE="$INSTALLED_PACKAGE_ROOT/bin/cli.mjs"
if [ ! -f "$SKILLS_CLI_EXECUTABLE" ] || [ -L "$SKILLS_CLI_EXECUTABLE" ]; then
  echo "reinstall-skills: locally installed skills CLI entrypoint is invalid" >&2
  exit 2
fi
packed_tree_digest="$(strict_tree_digest "$SKILLS_CLI_PACKAGE_ROOT")"
installed_tree_digest="$(strict_tree_digest "$INSTALLED_PACKAGE_ROOT")"
if [ "$packed_tree_digest" != "$installed_tree_digest" ]; then
  echo "reinstall-skills: locally installed skills CLI differs from verified artifact" >&2
  exit 2
fi
reported_version="$("$NODE_EXECUTABLE" "$SKILLS_CLI_EXECUTABLE" --version)"
if [ "$reported_version" != "$SKILLS_CLI_VERSION" ]; then
  echo "reinstall-skills: packed skills CLI reported version mismatch" >&2
  exit 2
fi

run_skills_cli() {
  "$NODE_EXECUTABLE" "$SKILLS_CLI_EXECUTABLE" "$@"
}

verify_receiving_surface() {
  local skill
  local source_digest
  local installed_digest
  local installed
  local installed_real
  local projection
  local projection_real
  local projection_digest

  for skill in "${SKILLS[@]}"; do
    installed="$HOME/.agents/skills/$skill"
    if [ ! -d "$installed" ] || [ -L "$installed" ]; then
      echo "reinstall-skills: installed receiving surface is invalid: $installed" >&2
      return 1
    fi
    source_digest="$(tree_digest "$REPO_ROOT/skills/$skill")" || return 1
    installed_digest="$(tree_digest "$installed")" || return 1
    if [ "$source_digest" != "$installed_digest" ]; then
      echo "reinstall-skills: installed receiving surface digest mismatch: $skill" >&2
      return 1
    fi
  done

  if agent_requested claude-code; then
    for skill in "${SKILLS[@]}"; do
      installed="$HOME/.agents/skills/$skill"
      projection="$HOME/.claude/skills/$skill"
      if [ ! -d "$projection" ]; then
        echo "reinstall-skills: Claude Code receiving surface is missing: $projection" >&2
        return 1
      fi
      installed_real="$(cd -P "$installed" && "$PWD_CMD" -P)" || return 1
      projection_real="$(cd -P "$projection" && "$PWD_CMD" -P)" || return 1
      projection_digest="$(tree_digest "$projection_real")" || return 1
      installed_digest="$(tree_digest "$installed_real")" || return 1
      if [ "$projection_real" != "$installed_real" ] &&
         [ "$projection_digest" != "$installed_digest" ]; then
        echo "reinstall-skills: Claude Code receiving surface is stale: $projection" >&2
        return 1
      fi
    done
  fi

  # Codex discovers the canonical ~/.agents/skills store directly. Reject a
  # stale legacy ~/.codex/skills copy when present because it can shadow the
  # canonical skill even though the new install itself is correct.
  if agent_requested codex; then
    for skill in "${SKILLS[@]}"; do
      projection="$HOME/.codex/skills/$skill"
      [ -e "$projection" ] || [ -L "$projection" ] || continue
      if [ ! -d "$projection" ]; then
        echo "reinstall-skills: Codex shadow receiving surface is invalid: $projection" >&2
        return 1
      fi
      installed="$HOME/.agents/skills/$skill"
      installed_real="$(cd -P "$installed" && "$PWD_CMD" -P)" || return 1
      projection_real="$(cd -P "$projection" && "$PWD_CMD" -P)" || return 1
      projection_digest="$(tree_digest "$projection_real")" || return 1
      installed_digest="$(tree_digest "$installed_real")" || return 1
      if [ "$projection_real" != "$installed_real" ] &&
         [ "$projection_digest" != "$installed_digest" ]; then
        echo "reinstall-skills: Codex shadow receiving surface is stale: $projection" >&2
        return 1
      fi
    done
  fi
}

# Validate every environment-controlled input before touching an installation.
case "${E2E_SKILLS_INSTALL_CODEX_AGENTS:-0}" in
  0|1) ;;
  *)
    echo "reinstall-skills: E2E_SKILLS_INSTALL_CODEX_AGENTS must be 0 or 1" >&2
    exit 2
    ;;
esac

if [ -n "${E2E_SKILLS_AGENTS:-}" ]; then
  # shellcheck disable=SC2206
  AGENTS_FLAGS=($E2E_SKILLS_AGENTS)
else
  AGENTS_FLAGS=(-a claude-code -a codex)
fi

if [ "${#AGENTS_FLAGS[@]}" -eq 0 ] ||
   [ $(( ${#AGENTS_FLAGS[@]} % 2 )) -ne 0 ]; then
  echo "reinstall-skills: E2E_SKILLS_AGENTS must contain '-a <agent>' pairs" >&2
  exit 2
fi
for ((index = 0; index < ${#AGENTS_FLAGS[@]}; index += 2)); do
  if [ "${AGENTS_FLAGS[index]}" != "-a" ] ||
     [ -z "${AGENTS_FLAGS[index + 1]}" ] ||
     [[ "${AGENTS_FLAGS[index + 1]}" == -* ]]; then
    echo "reinstall-skills: E2E_SKILLS_AGENTS must contain only '-a <agent>' pairs" >&2
    exit 2
  fi
  case "${AGENTS_FLAGS[index + 1]}" in
    claude-code|codex) ;;
    *)
      echo "reinstall-skills: unsupported receiving-surface agent: ${AGENTS_FLAGS[index + 1]}" >&2
      exit 2
      ;;
  esac
done
agent_requested() {
  local requested=$1
  local index
  for ((index = 1; index < ${#AGENTS_FLAGS[@]}; index += 2)); do
    [ "${AGENTS_FLAGS[index]}" = "$requested" ] && return 0
  done
  return 1
}
for skill in "${SKILLS[@]}"; do
  if [ ! -f "$REPO_ROOT/skills/$skill/SKILL.md" ]; then
    echo "reinstall-skills: source skill is incomplete: $skill" >&2
    exit 2
  fi
done

# The global target root must not be redirected through a relative or symlinked
# home/canonical-store path.
case "$HOME" in
  /*) ;;
  *)
    echo "reinstall-skills: HOME must be an absolute directory" >&2
    exit 2
    ;;
esac
if [ ! -d "$HOME" ] || [ -L "$HOME" ] ||
   { [ -e "$HOME/.agents" ] && [ -L "$HOME/.agents" ]; } ||
   { [ -e "$HOME/.agents/skills" ] && [ -L "$HOME/.agents/skills" ]; } ||
   { agent_requested claude-code &&
     { [ -L "$HOME/.claude" ] || [ -L "$HOME/.claude/skills" ]; }; }; then
  echo "reinstall-skills: refusing redirected global skills destination" >&2
  exit 2
fi

# The skills CLI's global canonical store is ~/.agents/skills; host-specific
# locations are links managed by the CLI. Snapshot existing copies before
# remove so an add failure can restore the same four-skill contents and links.
ROLLBACK_ROOT="$STAGING_ROOT/rollback"
ROLLBACK_SKILLS=()
"$MKDIR" -p "$ROLLBACK_ROOT/skills"
for skill in "${SKILLS[@]}"; do
  installed="$HOME/.agents/skills/$skill"
  if [ -e "$installed" ] || [ -L "$installed" ]; then
    if ! installed_real="$(cd -P "$installed" 2>/dev/null && pwd)"; then
      echo "reinstall-skills: invalid installed skill target: $installed" >&2
      exit 2
    fi
    if [ ! -f "$installed_real/SKILL.md" ]; then
      echo "reinstall-skills: installed skill is incomplete: $installed" >&2
      exit 2
    fi
    if ! nested_symlink="$("$FIND" "$installed_real" -type l -print -quit)"; then
      echo "reinstall-skills: could not validate installed skill: $installed" >&2
      exit 2
    fi
    if [ -n "$nested_symlink" ]; then
      echo "reinstall-skills: refusing installed skill with nested symlinks: $installed" >&2
      exit 2
    fi
    "$CP" -R "$installed_real" "$ROLLBACK_ROOT/skills/$skill"
    ROLLBACK_SKILLS+=("$skill")
  fi
done

restore_previous_state() {
  local failed_operation=$1
  local original_status=$2
  local rollback_remove_status
  local rollback_add_status=0

  echo "reinstall-skills: $failed_operation failed with original status $original_status; restoring previous four-skill state" >&2

  # First remove every managed target that the failed operation may have
  # created, then restore only the skills that existed in the snapshot.
  set +e
  run_skills_cli remove "${SKILLS[@]}" -g "${AGENTS_FLAGS[@]}" -y
  rollback_remove_status=$?
  if [ "${#ROLLBACK_SKILLS[@]}" -gt 0 ]; then
    run_skills_cli add "$ROLLBACK_ROOT" --skill "${ROLLBACK_SKILLS[@]}" -g "${AGENTS_FLAGS[@]}" --copy -y
    rollback_add_status=$?
  fi
  set -e

  if [ "$rollback_remove_status" -ne 0 ] ||
     [ "$rollback_add_status" -ne 0 ]; then
    echo "reinstall-skills: recovery blocker after $failed_operation failure: original status $original_status; rollback remove status $rollback_remove_status; rollback add status $rollback_add_status; manual recovery required" >&2
    return 1
  fi

  echo "reinstall-skills: $failed_operation failed; previous four-skill state restored" >&2
}

MUTATION_STARTED=0
handle_signal() {
  local signal_name=$1
  local signal_status
  local cleanup_status=0

  case "$signal_name" in
    HUP) signal_status=129 ;;
    INT) signal_status=130 ;;
    TERM) signal_status=143 ;;
    *) signal_status=1 ;;
  esac

  # Ignore further termination signals while the verified rollback artifact is
  # restoring the prior state. A second interrupt must not strand a partial
  # global install.
  trap '' HUP INT TERM
  if [ "$MUTATION_STARTED" -eq 1 ]; then
    if ! restore_previous_state "signal $signal_name" "$signal_status"; then
      echo "reinstall-skills: recovery blocker after signal $signal_name; manual recovery required" >&2
      exit 1
    fi
  fi

  cleanup || cleanup_status=$?
  trap - EXIT
  if [ "$cleanup_status" -ne 0 ]; then
    echo "reinstall-skills: staging cleanup failed with status $cleanup_status while handling signal $signal_name" >&2
  fi
  trap - HUP INT TERM
  "$KILL" -s "$signal_name" "$$"
  exit "$signal_status"
}
trap 'handle_signal HUP' HUP
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

# `skills add --copy` owns overwrite handling and replaces each selected target.
# Avoid a separate remove-first window; the staged snapshot below restores the
# complete previous set if the add performs a partial replacement and fails.
echo "reinstall-skills: replacing install from $REPO_ROOT as real copies (--copy)"
MUTATION_STARTED=1
if run_skills_cli add "$REPO_ROOT" --skill "${SKILLS[@]}" -g "${AGENTS_FLAGS[@]}" --copy -y; then
  if ! verify_receiving_surface; then
    if ! restore_previous_state "post-install verification" 1; then
      exit 1
    fi
    exit 1
  fi
else
  add_status=$?
  if ! restore_previous_state "add" "$add_status"; then
    exit 1
  fi
  exit "$add_status"
fi

# The skills CLI installs SKILL.md bundles, not Codex-native agent TOMLs.
# Installing the optional named agents is a separate global write and requires
# an explicit opt-in.
case "${E2E_SKILLS_INSTALL_CODEX_AGENTS:-0}" in
  0) ;;
  1)
    if printf '%s\n' "${AGENTS_FLAGS[@]}" | "$GREP" -q '^codex$'; then
      if "$BASH_CMD" -p "$REPO_ROOT/scripts/dev/install-codex-agents.sh"; then
        :
      else
        agent_status=$?
        if ! restore_previous_state "optional Codex agent install" "$agent_status"; then
          exit 1
        fi
        exit "$agent_status"
      fi
    fi
    ;;
esac

MUTATION_STARTED=0
trap - HUP INT TERM
