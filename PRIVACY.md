# Privacy Policy

Last updated: August 16, 2026

`e2e-skills` is an open-source collection of local agent skills, plugin
metadata, and command-line helpers. The project does not operate a hosted
service and the distributed software contains no first-party telemetry or
project-operated analytics.

## Data processing boundaries

- Installing or reading the skills does not send data to this project.
- Files, reports, screenshots, traces, and generated tests remain in the
  environment where the user or agent runs them unless that user explicitly
  sends them elsewhere.
- Agent hosts, model providers, GitHub, npm, browsers, target applications, and
  other tools invoked by the user may process data under their own terms and
  privacy policies. `e2e-skills` does not control those services.
- Some explicitly enabled workflows can access the network, download pinned
  tools, inspect a user-approved target, or call a configured model provider.
  The skills document those boundaries and require the applicable trust or
  approval gates before execution.

Do not place credentials, session tokens, personal data, customer data, or
other sensitive information in public issues, shared test fixtures, prompts,
or reports. Sanitize artifacts before sharing them.

## Retention and deletion

Because this project runs locally and has no project-operated data service, it
does not retain user content on a first-party server. Users control the local
files and artifacts created by their agent host and tools and can remove them
through those products or their filesystem.

## Questions

For a non-sensitive privacy question, open a GitHub issue. For a report that
contains sensitive details or describes a security vulnerability, follow the
private-reporting guidance in [SECURITY.md](SECURITY.md).
