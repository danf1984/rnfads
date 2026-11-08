# Estrae i testi italiani visibili dai file JS (stringhe e parti fisse dei template) e dai messaggi Python
import json, re, sys, os
IT = re.compile(r"[a-zàèéìòù]{2,}", re.I)
def frags_from_template(t):
    # toglie ${...} (anche annidati) e i tag HTML, divide in pezzi di testo
    out, depth, buf, i = [], 0, '', 0
    res = ''
    while i < len(t):
        if t.startswith('${', i):
            d = 1; i += 2
            while i < len(t) and d:
                if t[i] == '{': d += 1
                elif t[i] == '}': d -= 1
                i += 1
            res += '\x00'; continue
        res += t[i]; i += 1
    res = re.sub(r'<[^<>]*>', '\x00', res)
    return [p for p in res.split('\x00')]
def js_strings(src):
    toks = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith('//', i) and (i == 0 or src[i-1] != ':'):
            j = src.find('\n', i); i = n if j < 0 else j; continue
        if src.startswith('/*', i):
            j = src.find('*/', i); i = n if j < 0 else j + 2; continue
        if c in "'\"":
            j = i + 1; s = ''
            while j < n and src[j] != c:
                if src[j] == '\\': s += src[j:j+2]; j += 2; continue
                s += src[j]; j += 1
            toks.append(('s', s)); i = j + 1; continue
        if c == '`':
            j = i + 1; d = 0; s = ''
            while j < n:
                if src[j] == '\\': s += src[j:j+2]; j += 2; continue
                if src.startswith('${', j):
                    k = j + 2; dd = 1
                    while k < n and dd:
                        if src[k] == '{': dd += 1
                        elif src[k] == '}': dd -= 1
                        elif src[k] == '`':  # template annidato
                            kk = k + 1
                            while kk < n and src[kk] != '`':
                                kk += 2 if src[kk] == '\\' else 1
                            toks.append(('t', src[k+1:kk])); k = kk
                        elif src[k] in "'\"":
                            q = src[k]; kk = k + 1; ss = ''
                            while kk < n and src[kk] != q:
                                if src[kk] == '\\': ss += src[kk:kk+2]; kk += 2; continue
                                ss += src[kk]; kk += 1
                            toks.append(('s', ss)); k = kk
                        k += 1
                    s += '${}'; j = k; continue
                if src[j] == '`': break
                s += src[j]; j += 1
            toks.append(('t', s)); i = j + 1; continue
        i += 1
    return toks
