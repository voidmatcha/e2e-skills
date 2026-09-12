# Subagent routing v1 protocol revision 1

Revision 1 is superseded and unscored. Its first scheduled measured cell,
`FC-03-claude.named-r2`, stopped twice: the original attempt and one explicitly
authorized diagnostic rerun. Both model responses also failed the strict evidence
schema, which remains an unexplained measured observation rather than part of the
attestation repair.

The diagnostic proved the route failure itself was a harness defect. Claude emitted
one `Agent` tool invocation and a `tool_progress` heartbeat whose
`parent_tool_use_id` pointed to that same invocation. The revision-1 runner counted
both dictionaries because it matched `name` and `tool_name` without first restricting
the event type. `attestation-debug.json` preserves the pre-truncation event paths and
scalar fields that established the duplicate count.

This directory preserves the revision-1 freeze, authorization, successful smoke,
measured report, and every raw artifact. None may be used as revision-2 measured data.
