import sys
p=sys.argv[1]+"/skills/playwright-debugger/references/artifact-extraction.md"
s=open(p).read()
a='''```bash
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh \\
  --project-root "$PROJECT_ROOT" -- report \\
  --report-root playwright-report \\
  playwright-report/results.json
```
'''
b='''Run it as one command with literal absolute paths and no shell variables, `$()`, or `cd`, so an exact-command approval can match it. Use the project's known absolute root (the working directory) for `<absolute-project-root>`:

```bash
<skill-dir>/scripts/run-artifact-reader.sh --project-root <absolute-project-root> -- report --report-root playwright-report playwright-report/results.json
```
'''
assert a in s
open(p,"w").write(s.replace(a,b,1))
