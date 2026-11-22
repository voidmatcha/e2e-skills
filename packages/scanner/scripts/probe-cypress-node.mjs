// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
export function cypressCommandEvidenceTask(artifactPath) {
  return sidecar => {
    // Caller creates the approved output directory. Never overwrite old evidence.
    fs.writeFileSync(artifactPath, JSON.stringify(sidecar, null, 2), { flag: 'wx', mode: 0o600 });
    return null;
  };
}
