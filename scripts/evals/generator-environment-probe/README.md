# Model-free generator environment diagnostic

This opt-in setup diagnostic does not run a model, change an installed skill, mutate a frozen protocol, or establish a skill-quality or cost-reduction result. It reads only four files from the public v3 `v2-20` fixture and sends their text over stdin into a disposable container using the locally installed, immutable v8 image. It downloads nothing, mounts no host paths, passes no credentials, and uses a private network namespace with external networking disabled. The host disk floor is 4 GiB; failure of that floor blocks the probe rather than deleting evidence.

Run the dependency-free contract tests:

```bash
python3 scripts/ci/test-generator-environment-probe.py
```

After verifying Docker is available, the pinned image is installed, and disk space meets the floor, explicitly opt in to browser execution:

```bash
python3 scripts/evals/generator-environment-probe.py --allow-browser --context colima
```

The JSON output binds the selected fixture bytes and image identity. A diagnostic `PASS` requires all of the following: an expected curl exit 7 before startup; the default Playwright CLI's missing Chrome failure; successful explicit installed Chromium launch; readiness of the probe-owned app; an `EADDRINUSE` failure from a second app owner; Playwright's refusal to reuse that external server; and three passing existing smoke tests after the probe terminates its own app. Any unexpected control or safe-setup result is `INCONCLUSIVE`, not evidence that the environment improvement works. The browser CLI session, app process, temporary files, and generated container are owned by this invocation; no shared process is killed.

This is a single-fixture diagnostic, not the successor experiment. It validates explicit Chromium through the Node API, not a repaired browser CLI configuration. A successor must pin and verify its own exploration configuration, provide both model arms with the same startup/readiness and cleanup contract, and avoid simultaneously assigning a server to exploration and `webServer`. It must preserve independent review and fault injection until a preregistered comparison supports changing them.

Relevant Playwright API contracts: [Chromium launch](https://playwright.dev/docs/api/class-browsertype#browser-type-launch), [browser selection](https://playwright.dev/docs/browsers), and [web-server ownership and readiness](https://playwright.dev/docs/test-webserver). The pinned fixture already uses `webServer.reuseExistingServer: false`; this diagnostic leaves it unchanged and stops its exploration server before test execution. The CLI's accepted options were inspected with the exact image's `playwright cli open --help`; no undocumented CLI configuration fix is claimed.

License: Apache-2.0.
