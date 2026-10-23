# Frozen shell scanner oracle

This verification-only snapshot preserves the exact working-tree bytes captured
on 2026-10-22 before the Node launcher cutover. It is not a supported product,
runtime fallback, or claim that the snapshot equals the recorded Git HEAD.

`manifest.json` records every original path, byte length, mode and SHA-256. The
deterministic gzip contains JSON/base64 file entries, including the shell
scanner, its Python/shell helpers, optional AST rules, Apache license and notice.
The original scanner regression source is retained separately under `regression/`
because differential tests extract unchanged fixture literals from its AST.
Probe/check runners are not part of this snapshot.

`oracle.mjs` pins the manifest digest, verifies the compressed archive and every
file, and restores only enumerated regular files in a private temporary directory.
Every accessor revalidates the extracted files; normal process exit removes them.
No extraction command, package installation or network request is used. Running
the historical scanner still requires its original local Bash/Python/ripgrep
prerequisites. Callers must keep optional downloads disabled.

Node differential tests use this oracle instead of the current public `scan.sh`.
Do not regenerate it when the product changes: update a separately versioned
oracle only for an explicitly justified new comparison baseline. A hash proves
identity with this repository snapshot, not an external signature or correctness.
