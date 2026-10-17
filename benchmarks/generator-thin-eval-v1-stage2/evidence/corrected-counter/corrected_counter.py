#!/usr/bin/env python3
"""Corrected defining-CLI-call counter. READ-ONLY. Counts from codex rollout logs only (no runner classification).
A "CLI call" = one invocation of `playwright cli|playwright-cli` with a verb, reconstructed from exec_command inputs:
  (a) literal  : cmd:"npx ... playwright cli [-s=X|--flags] VERB ..."   (also bash -c / sh -c wrapped, same text)
  (b) JS loop  : cmd:"npx ... playwright cli -s=X "+v  or  `... -s=X ${v}`  -> verbs taken from the quoted string
                 literals of the SAME tool-call input whose first word is a known CLI verb (array elements).
Independent corroboration from outputs: a call output containing 'Page URL:' or '### Page' or '### Snapshot'.
Usage: corrected_counter.py [--json OUT]
"""
import json, glob, os, re, sys, collections
C = os.path.expanduser("~/.cache/e2e-skills-bench")
CAMPS = [("thin-eval-v1-r3", "gpt-6-sol"), ("thin-eval-v1-r3", "gpt-6-astra"), ("thin-eval-v1-s3", "gpt-6.1-sol")]
ARMS = ["official-generator", "official+thin-rules", "official+thin-rules+scanner", "cli-first+thin-rules", "cli-first+thin-rules+scanner"]
VERBS = "open goto snapshot click fill press eval requests type select hover close check uncheck dblclick reload go-back screenshot console tab-list tab-new run-code".split()
VR = "|".join(re.escape(v) for v in VERBS)
OLD = re.compile(r'playwright(?:-cli| cli)\b((?:\s+(?:-s=\S+|--config\s+\S+|--[a-z-]+(?:=\S+)?))*)\s+([a-z-]+)')
CMD = re.compile(r'cmd:\s*"((?:[^"\\]|\\.)*)"')
# any playwright cli head, any flags (incl. --config=..., -s=X, -s X, --session X), then a verb
HEAD = re.compile(r'playwright(?:-cli| cli)\b((?:\s+(?:-s[= ]\S+|--session[= ]\S+|--config[= ]\S+|--[a-z-]+(?:=\S+)?))*)\s*(?P<rest>(?:(?!playwright(?:-cli| cli)\b)[^\n])*)')
LITV = re.compile(r'^\s*(%s)\b' % VR)
DYN = re.compile(r'playwright(?:-cli| cli)\b[^"`\n]*?(?:"\s*\+|\$\{)')
QV = re.compile(r'''["'`](%s)(?=[\s"'`])''' % VR)
OUTMARK = ("Page URL:", "### Page", "### Snapshot", "### Ran Playwright code")

def calls(path):
    for line in open(path):
        try: e = json.loads(line)
        except ValueError: continue
        if e.get("type") != "response_item": continue
        pl = e.get("payload", {}); t = pl.get("type")
        if t in ("custom_tool_call", "function_call"):
            inp = pl.get("input") if t == "custom_tool_call" else pl.get("arguments", "")
            inp = inp if isinstance(inp, str) else json.dumps(inp)
            yield "call", pl, inp
        elif t in ("custom_tool_call_output", "function_call_output"):
            o = pl.get("output"); o = o if isinstance(o, str) else json.dumps(o)
            yield "out", pl, o

def count_cell(files):
    new = collections.Counter(); old = collections.Counter(); outs = 0; shapes = collections.Counter()
    for p in files:
        for kind, pl, s in calls(p):
            if kind == "out":
                if any(m in s for m in OUTMARK) and "playwright" not in s[:0]: outs += 1
                continue
            if "playwright" not in s: continue
            # old regex (as in posthoc_report.audit_model) for comparison
            cmds = CMD.findall(s)
            if not cmds and pl.get("name") in ("shell", "exec_command"): cmds = [s]
            for c in cmds:
                for m in OLD.finditer(c): old[m.group(2)] += 1
            if re.search(r'playwright(?:-cli| cli)\s+-s=\S+\s*["\x27`]\s*\+', s):
                for v in QV.findall(s): old[v] += 1
            # corrected
            text = s.replace('\\"', '"').replace("\\n", "\n")
            dyn = bool(DYN.search(text))
            lit_found = 0
            for m in HEAD.finditer(text):
                rest = m.group("rest")
                lm = LITV.match(rest)
                if lm: new[lm.group(1)] += 1; lit_found += 1
                if re.match(r'''\s*(?:\\?["'`]\s*\+|\$\{)''', rest) or rest.strip() == "": pass
            if dyn:
                vs = QV.findall(text)
                for v in vs: new[v] += 1
                shapes["dynamic_loop"] += 1
            if lit_found: shapes["literal"] += 1
            if re.search(r'(?:bash|sh|zsh)\s+-l?c\b', text) and "playwright" in text: shapes["shell_wrapped"] += 1
    return new, old, outs, shapes

def main():
    res = {}
    for camp, mid in CAMPS:
        base = f"{C}/{camp}/{mid}"
        rep = json.load(open(base + "/final.json"))
        for r in rep["runs"]:
            a = r["attempts"][-1]; uid = os.path.basename(a["transcript_path"])[:-6]
            files = glob.glob(f"{base}/codex-sessions/{uid}/**/*.jsonl", recursive=True)
            new, old, outs, shapes = count_cell(files)
            res[f"{mid}|{r['arm']}|{r['case']}|{r['repetition']}"] = dict(
                model=mid, arm=r["arm"], cell=f"{r['case']}#{r['repetition']}", uid=uid, files=len(files),
                new=dict(new), old=dict(old), out_markers=outs, shapes=dict(shapes),
                new_explore=sum(new.get(v, 0) for v in ("open", "goto", "snapshot")),
                old_ok=bool(old.get("open") and old.get("close")))
    return res

if __name__ == "__main__":
    res = main()
    if "--json" in sys.argv: json.dump(res, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    print("%-13s %-32s %5s %9s %9s %9s %6s" % ("model", "arm", "cells", "old o&c", "new>=1", "new=0", "outmk0"))
    for mid in [m for _, m in CAMPS]:
        for arm in ARMS:
            cs = [v for v in res.values() if v["model"] == mid and v["arm"] == arm]
            print("%-13s %-32s %5d %9d %9d %9d %6d" % (mid, arm, len(cs), sum(c["old_ok"] for c in cs),
                  sum(c["new_explore"] > 0 for c in cs), sum(c["new_explore"] == 0 for c in cs), sum(c["out_markers"] == 0 for c in cs)))
