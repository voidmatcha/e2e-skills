import json,glob,os,subprocess,sys,tempfile
B=os.path.dirname(os.path.abspath(__file__)); label=sys.argv[1]
TRUTH={
"om-34725":"First attempt times out in storageStateRecovery waiting for **/signin while the navigation log shows normal glossary pages; the retry passes. The reported session/auth-recovery error is misleading. The real cause (a click swallowed during a re-render, Owners button focused, no popover) is NOT in the report. A good answer treats it as a flaky interaction/timing race in the test and does not assert an auth/session backend cause; it says the real cause needs the failed attempt's DOM snapshot.",
"om-35016":"Attempt 1: log-viewer-live-indicator not visible. Attempt 2: the agent card already reads Success where Running was expected. Symptom: the ingestion run finished before the assertion looked (test timing depends on how fast the run finishes). Why it finished early (external Kafka topic count) is NOT in the report.",
"om-blob":"Two drag tests passed only on retry. Source-level cause: the drop coordinate is measured before hover(); hover scrolls the page and invalidates the coordinate. This is NOT established from the report alone; the failed attempt's observability is limited.",
"om-34811":"No maintainer-established cause is available for this report; judge only unsupported claims."}
PROMPT="""You are blindly grading one answer to a Playwright CI failure diagnosis. You do not know which tool produced it.
Evidence the answerer could see (reader excerpt of the failing report):
{ex}

Maintainer-known background (may include facts NOT visible in the excerpt):
{truth}

Answer to grade:
{ans}

Return one JSON object:
- cause_score: 2 = names the same mechanism as the background; 1 = partially (right symptom or right side but not mechanism), or correctly says the cause cannot be established while describing the visible symptom accurately; 0 = wrong or asserts a different cause.
- unsupported: count of distinct factual claims in the answer (origin, earlier test/component, backend reason, code location, number, before/after change) that are neither in the excerpt nor a direct logical consequence of it. Hedged claims do not count. Do not use the background to excuse claims.
- hedged_unobservable: true when the answer explicitly says the root cause cannot be established from the report and names the missing evidence."""
out=[]
for f in sorted(glob.glob(f"{B}/{label}/*.jsonl")):
    c,arm,rep=os.path.basename(f)[:-6].split(".")
    res=""
    for l in open(f):
        if l.startswith("{"):
            try:e=json.loads(l)
            except: continue
            if e.get("type")=="result":res=e.get("result","")
    if not res: out.append(dict(c=c,arm=arm,rep=rep,empty=True));continue
    p=PROMPT.format(ex=open(f"{B}/excerpt/{c}.txt").read(),truth=TRUTH[c],ans=res)
    with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as t: pass
    r=subprocess.run(["codex","exec","-m","gpt-6-sol","-s","read-only","--skip-git-repo-check","--ephemeral","--output-schema",f"{B}/schema.json","-o",t.name,"-"],input=p,text=True,capture_output=True,timeout=300,cwd=tempfile.gettempdir())
    try:j=json.load(open(t.name))
    except Exception: j=dict(error=r.stderr[-200:])
    out.append(dict(c=c,arm=arm,rep=rep,**j))
json.dump(out,open(f"{B}/{label}/judged.json","w"),indent=1)
import collections
g=collections.defaultdict(list)
for o in out:
    if "cause_score" in o:g[o["arm"]].append(o)
for a,r in g.items():
    n=len(r);print(a,"n",n,"cause",round(sum(x["cause_score"] for x in r)/n,2),"strict",round(sum(x["cause_score"]==2 for x in r)/n,2),"unsupported",round(sum(x["unsupported"] for x in r)/n,2),"hedged",round(sum(x["hedged_unobservable"] for x in r)/n,2))
