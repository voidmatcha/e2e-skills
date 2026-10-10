import json,glob,sys,collections,os
d=sys.argv[1] if len(sys.argv)>1 else "out"
rows=collections.defaultdict(list)
for f in sorted(glob.glob(d+"/*.jsonl")):
    c,arm,rep=os.path.basename(f)[:-6].split(".")
    cost=out=inp=0;skill=reader=0;reads=set();turns=0;res=""
    for l in open(f):
        try:e=json.loads(l)
        except:continue
        if e.get("type")=="result":
            cost=e.get("total_cost_usd",0);turns=e.get("num_turns",0);res=e.get("result","")
            u=e.get("usage",{});out=u.get("output_tokens",0);inp=u.get("input_tokens",0)+u.get("cache_creation_input_tokens",0)+u.get("cache_read_input_tokens",0)
        for b in (e.get("message",{}) or {}).get("content",[]) if isinstance(e.get("message"),dict) else []:
            if isinstance(b,dict) and b.get("type")=="tool_use":
                if b["name"]=="Skill":skill=1
                if b["name"]=="Bash" and "run-artifact-reader" in json.dumps(b["input"]):reader=1
                if b["name"]=="Read":reads.add(os.path.basename(b["input"].get("file_path","")))
    secs=int(open(f[:-6]+".secs").read())
    rows[arm].append(dict(c=c,rep=rep,cost=cost,secs=secs,out=out,inp=inp,turns=turns,skill=skill,reader=reader,refs=len([r for r in reads if r.endswith(".md")]),res=res))
for arm,r in rows.items():
    n=len(r);m=lambda k:sum(x[k] for x in r)/n
    print(f"{arm:7} n={n} cost=${m('cost'):.3f} secs={m('secs'):.0f} out={m('out'):.0f} in={m('inp'):.0f} turns={m('turns'):.1f} skill={m('skill'):.2f} reader={m('reader'):.2f} md_reads={m('refs'):.1f}")
json.dump(rows,open(d+"/summary.json","w"),indent=1)
