import sys
p=sys.argv[1]+"/skills/playwright-debugger/SKILL.md"
s=open(p).read()
a="- **Root Cause:** one-sentence explanation\n"
b="- **Root Cause:** one sentence: the observed failure, then the cause only if the artifact evidences it. State anything beyond the artifact as a hypothesis and name the missing evidence; never present a hypothesis as the cause.\n"
c="- **Fix:** before/after code showing the concrete change\n"
d="- **Fix:** before/after code only when the spec source was read in this session; otherwise describe the change in prose using only identifiers visible in the artifact. Never invent selectors, endpoints, line numbers, or helper names.\n"
assert a in s and c in s
open(p,"w").write(s.replace(a,b).replace(c,d))
