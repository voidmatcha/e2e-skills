import sys
p=sys.argv[1]+"/skills/playwright-debugger/SKILL.md"
s=open(p).read()
a="## Phase 2: Classify Root Cause\n"
b=a+"\nRead the spec source only when the path the report names resolves in the working tree; do not search the filesystem for it. If it does not resolve, classify from the report and say the source was not available.\n"
assert a in s
open(p,"w").write(s.replace(a,b,1))
