import sys
p=sys.argv[1]+"/skills/playwright-debugger/SKILL.md"
s=open(p).read()
a="Before extracting failures, read `references/artifact-extraction.md` and use its bundled-reader command and fail-closed interpretation rules."
b=a+"\n\nThe command is one line with literal absolute paths (no variables, `$()`, or `cd`): `<skill-dir>/scripts/run-artifact-reader.sh --project-root <absolute-project-root> -- report --report-root playwright-report playwright-report/results.json`. Run it first, then read the reference for the interpretation rules."
assert a in s
open(p,"w").write(s.replace(a,b,1))
