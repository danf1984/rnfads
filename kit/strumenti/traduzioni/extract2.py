import json, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jsparse import js_strings
UI, PY = sys.argv[1], sys.argv[2]
IT = re.compile(r"[a-zàèéìòù]{2,}", re.I)
BAD = re.compile(r"=>|;\s*$|;\s*\w+\s*[=(]|\$\(|[<>]|path d=|\bconst\b|\breturn\b|\.join\(|\)\)|^/|^[a-z]+/$|\\[ux]|&amp;|\|\||&&|\.\w+\(")
def segs(t):
    """Divide un template nei pezzi di testo tra i tag; ${...} diventa {0}, {1}…"""
    out, cur, k, i, n = [], '', 0, 0, len(t)
    while i < n:
        if t.startswith('${', i):
            d = 1; i += 2
            while i < n and d:
                if t[i] == '{': d += 1
                elif t[i] == '}': d -= 1
                i += 1
            cur += '{%d}' % k; k += 1; continue
        if t[i] == '<':
            j = t.find('>', i)
            if j > 0:
                out.append(cur); cur = ''; k = 0; i = j + 1; continue
        cur += t[i]; i += 1
    out.append(cur)
    for m in re.finditer(r'(?:placeholder|title|aria-label)="([^"]+)"', t):
        out.append(m.group(1))
    return out
def norm(t):
    t = re.sub(r'\s+', ' ', t.replace('\\n', ' ').replace("\\'", "'").replace('\\"', '"')).strip()
    # rinumera i segnaposto da 0
    m = {}
    t = re.sub(r'\{\d+\}', lambda x: '{%d}' % m.setdefault(x.group(0), len(m)), t)
    return t
items = {}
def add(t, where):
    t = norm(t)
    core = re.sub(r'\{\d+\}', '', t).strip(' ·:—-,()/•"\'.?!…')
    if len(core) < 2 or not IT.search(core): return
    if BAD.search(t): return
    if re.fullmatch(r'[\w.\-]+', core) and not re.search(r'[àèéìòù]', core) and core.lower() == core and len(core) < 4: return
    if '{' in t.replace('{0}','').replace('{1}','').replace('{2}','').replace('{3}','').replace('{4}','').replace('{5}',''): return
    items.setdefault(t, where)
for fn in sorted(os.listdir(UI)):
    if not fn.endswith('.js'): continue
    for kind, s in js_strings(open(os.path.join(UI, fn), encoding='utf-8').read()):
        for p in (segs(s) if (kind == 't' or '<' in s) else [s]):
            add(p, fn)
py = {}
for fn in sorted(os.listdir(PY)):
    if not fn.endswith('.py'): continue
    src = open(os.path.join(PY, fn), encoding='utf-8').read()
    for m in re.finditer(r'(?:ApiError|RuntimeError|warning"\]|"(?:message|msg|title|text|error|reason|warning|detail|label|why|s|t)":)\s*\(?\s*(f?)(["\'])(.+?)(?<!\\)\2', src):
        t = m.group(3)
        if m.group(1):
            k = [0]
            def sub(x):
                r = '{%d}' % k[0]; k[0] += 1; return r
            t = re.sub(r'\{[^{}]+\}', sub, t)
        t = norm(t)
        if IT.search(re.sub(r'\{\d+\}', '', t)) and ' ' in t and t not in items:
            py.setdefault(t, fn)
    for m in re.finditer(r'(?<![\w])(f?)(["\'])((?:(?!\2).){3,300}?)\2', src):
        t = m.group(3)
        if not re.search(r' (il|la|le|di|del|della|dei|non|un|una|in|per|con|da|è|al|alla|troppo|riuscit\w*) ', ' ' + t + ' '): continue
        if re.search(r'[<>=\\]|^\s|%[sd]|\.py\b|/usr/|/etc/', t): continue
        if m.group(1):
            k = [0]
            def sub2(x):
                r = '{%d}' % k[0]; k[0] += 1; return r
            t = re.sub(r'\{[^{}]+\}', sub2, t)
        t = norm(t)
        if t not in items: py.setdefault(t, fn)
allk = list(items) + [k for k in py if k not in items]
json.dump(allk, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys-nuove.json'), 'w'), ensure_ascii=False, indent=0)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys-nuove.txt'), 'w') as f:
    for i, k in enumerate(allk): f.write(f"{i}\t{k}\n")
print(len(items), len(py), len(allk), sum(map(len, allk)))
