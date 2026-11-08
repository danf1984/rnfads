import json,re,glob,os
D=os.path.dirname(os.path.abspath(__file__))
keys3=json.load(open(f'{D}/keys3.json')); orig=json.load(open(f'{D}/keys.json'))
def clean(k):
    k2=re.sub(r'^\{\d+\}(?=\S)','',k); k2=re.sub(r'(?<=\S)\{\d+\}$','',k2).strip()
    m={}; return re.sub(r'\{\d+\}', lambda x:'{%d}'%m.setdefault(x.group(0),len(m)), k2)
suffix=set()
for o in orig:
    if re.search(r'[a-zà-ù]\{\d+\}$', o, re.I): suffix.add(clean(o))
rows=[]
for f in sorted(glob.glob(f'{D}/tr/0*.tsv')):
    for line in open(f,encoding='utf-8'):
        p=line.rstrip('\n').split('\t')
        if len(p)==4: rows.append((keys3[int(p[0])],p[1],p[2],p[3]))
for f in sorted(glob.glob(f'{D}/tr/extra*.tsv')):
    for line in open(f,encoding='utf-8'):
        p=line.rstrip('\n').split('\t')
        if len(p)==4: rows.append(tuple(p))
out=os.path.join(D,'..','..','live','includes','usr','lib','nido','panel','ui','lang')
os.makedirs(out,exist_ok=True)
for li,lang in enumerate(['en','es','de']):
    exact={}; pats={}
    for r in rows:
        it,t=r[0],r[1+li]
        if t=='=' or t==it: continue
        if re.search(r'\{\d+\}',it): pats[it]=[it,t,1] if it in suffix else [it,t]
        else: exact[it]=t
    json.dump({"lang":lang,"exact":exact,"pats":list(pats.values())},open(f'{out}/{lang}.json','w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
    print(lang,len(exact),len(pats),sum(1 for v in pats.values() if len(v)==3))
