# e2e-skills 3.7.0 release notes (local candidate)

This non-breaking candidate retains `playwright-test-generator`, `e2e-reviewer`, and `e2e-debugger`. The reviewer still performs static analysis by default.

## Experimental reviewer runtime proof

An explicit request can use the portable V2 assertion-mutation or V3 behavior-fault executor on a disposable project copy. The executor requires a sourced behavior promise, structured `expected_failure` (spec, exact title, intended assertion locator or matcher, failure kind, expected and actual value shapes), a passing healthy baseline, and a separate observer for V3. It binds the preview, plan, source and executor bytes before exact-command approval and refuses unrelated or vague failures as detection. A bounded test-strengthening loop is available only when separately requested and approved after V3 survival. The original checkout stays unchanged.

The proof covers only the selected test and injected fault. Gate401 reached a runtime verdict in about 0–1 of 6 fresh React repositories and used about 2.2 times the tokens of the comparison arm; it did not establish a release-gate advantage. Treat this path as EXPERIMENTAL and opt in explicitly. No runtime probe is automatic in ordinary reviews.

## Local release checklist

Run the following commands from this worktree **only after choosing this candidate for release**. They switch to the owner's main checkout, fetch the local candidate from its scratch repository, verify the main checkout's `origin`, and then publish. They are a draft; none has been run here. Review the desired remote branch and release ordering before using them.

```sh
cd ../e2e-skills
git fetch ../e2e-skills-lanes400/relprep-work/source.git rel/370:refs/heads/rel/370
git remote get-url origin
git push origin rel/370:refs/heads/rel/370
git tag -a v3.7.0 rel/370 -m 'e2e-skills 3.7.0'
git push origin refs/tags/v3.7.0
(cd packages/scanner && npm publish --access public)
```

The npm package is `@voidmatcha/e2e-skills-scanner`; its `publishConfig` targets the public npm registry and `latest`. The repository and plugin tags require a separate release decision; this list does not imply that a remote release or npm version exists yet.
