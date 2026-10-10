import sys
p=sys.argv[1]+"/skills/playwright-debugger/SKILL.md"
s=open(p).read()
a="Keep the axes independent."
b="Keep each field to one line. When the diagnosis axis is `unknown`, write `unknown` for Product impact and `N/A` for Test-quality severity instead of prose, and put the missing evidence in Root Cause. Keep the axes independent."
assert a in s
open(p,"w").write(s.replace(a,b,1))
