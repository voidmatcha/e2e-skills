# Node candidate inventory spike

Experimental, dependency-free Node.js inventory of scanner candidates. This is
**not a scanner, npm package, npx product, or proof of scanner parity**. It emits
no findings and makes no P0 gating decision. No project configuration is loaded.
The current scanner implementation is `packages/scanner/src/`; installed skills use its bundled runtime through the `scan.sh` launcher. The implementation now lives in
`packages/scanner/src/inventory.mjs`; this directory retains a compatibility
CLI and re-exports that module without duplicating it.

```sh
node scripts/evals/node-scanner-spike/inventory.mjs /absolute/project > /tmp/inventory.json
node scripts/evals/node-scanner-spike/inventory.mjs --revalidate /tmp/inventory.json
python3 scripts/evals/node-scanner-spike/test_inventory.py
node --test packages/scanner/test/inventory.test.mjs
```

Exit 0 means this inventory completed; exit 2 means incomplete. Never treat a
partial `candidates` array as complete. Revalidate immediately before consuming
a saved inventory and again after work that depends on it. Revalidation repeats
discovery and fingerprints, detecting additions, removals, replacements and
content/identity drift. These checks do not provide an atomic filesystem snapshot
or an OS sandbox; a hostile concurrent writer is outside the experiment.

## Implemented slice

- Eight JS/TS extensions, hidden and ignored files, scanner vendor/artifact and
  minified exclusions, `.yarn` and PnP discovery exclusions, byte-sorted paths.
- Root symlink rejection. Source symlinks, directory links, conventional dangling
  source-root links and source FIFOs fail closed. Ordinary asset symlinks and
  unrelated FIFOs retain the existing scanner's permitted boundary.
- Colon/newline filename rejection. Device, inode, mode, size, nanosecond mtime
  and ctime are decimal strings from bigint stats; contents use SHA-256.
- `O_NOFOLLOW`, descriptor stats before/after hashing, pathname and parent checks.
  A stable parent symlink in the requested path is resolved and pinned, matching
  the legacy scanner. A persistent parent swap at open is rejected before
  reading contents; retargeted parents invalidate revalidation. Directory
  identity/metadata checks before and after traversal detect persistent drift.
  Nonblocking open also prevents a raced FIFO replacement from hanging open.
- A later unreadable candidate preserves the earlier partial inventory, reports
  the actual failing path and exits 2.

`test_inventory.py` extracts the shipped shell discovery, exclusion, preflight,
filename validation and manifest functions as an oracle. Five fixture groups
compare inventories and refusal behavior, including a late fingerprint failure.
Only the oracle uses shell/rg/Python; the implementation uses Node built-ins.

## Explicitly incomplete boundaries

Project marker discovery and the two self-checkout fixture exclusions are now implemented in the package, including nested project boundaries and direct fixture overrides. This does not provide transitive imports outside the requested source inventory or executable configuration handling. Non-UTF-8 filenames and symlinked markers fail incomplete. macOS differential fixtures cover discovery; see the package README for the pinned Linux and installed-package checks.


## Legacy call compatibility study

```sh
python3 scripts/evals/node-scanner-spike/compare-legacy-checks.py --output /new/external/evidence/path
```

This opt-in study freezes the existing scanner source, Node parser dependency and
69 pairs of small authored canaries. It verifies each legacy call's exact target
warning, requires unchanged output after call tracing, then runs the bounded Node
CLI against the same files. It reports matching pattern locations, diagnostic-only
refusals, silent omissions and negative warnings separately. One shape per call
is migration evidence, not full syntax coverage or accuracy on independent projects.
It does not execute project ESLint configuration or run browser probes.
