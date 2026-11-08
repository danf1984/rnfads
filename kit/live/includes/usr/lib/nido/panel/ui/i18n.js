'use strict';
/* =============================================================================
   Traduzioni dell'interfaccia (italiano di base; inglese, spagnolo, tedesco).
   L'interfaccia è scritta in italiano: questo file traduce i testi mentre compaiono
   nella pagina (MutationObserver), usando i dizionari in /static/lang/<lingua>.json:
     exact: {"testo italiano": "traduzione"}
     pats:  [["testo con {0} e {1}", "translation with {0} and {1}"]]
   Non vengono toccati: nomi di file e cartelle, campi da compilare, terminale, registri,
   testi in carattere a spaziatura fissa (.mono) e tutto ciò che è dentro .notr.
   ============================================================================= */
const I18N = { lang: 'it', exact: new Map(), pats: [], on: false };
const LOCALES = { it: 'it-IT', en: 'en-GB', es: 'es-ES', de: 'de-DE' };
const LANG_NAMES = { it: 'Italiano', en: 'English', es: 'Español', de: 'Deutsch' };
let LOCALE = 'it-IT';
const I18N_SKIP = 'script,style,textarea,pre,code,kbd,.xterm,.notr,.logbox,.mono,[contenteditable],.file-it .n,.file-it .nm,[data-open],.crumbs';
const I18N_ATTRS = ['placeholder', 'title', 'aria-label'];

function i18nEsc(s) { return s.replace(/[.*+?^$()|[\]\\]/g, '\\$&'); }

function i18nLoad(lang, data) {
  I18N.lang = lang;
  LOCALE = LOCALES[lang] || 'it-IT';
  I18N.exact = new Map(Object.entries((data && data.exact) || {}));
  I18N.pats = [];
  for (const [it, tr, suffix] of ((data && data.pats) || [])) {
    // {0}, {1}… diventano gruppi; "suffix" = l'ultima parola italiana ha un finale variabile (attiv{o|a|e})
    let re = i18nEsc(it).replace(/\{(\d+)\}/g, '(.+?)');
    if (suffix) re += '[a-zà-ù]{0,3}';
    I18N.pats.push({ re: new RegExp('^' + re + '$', 'i'), tr, len: it.length });
    // "Testo {0}" senza niente dopo (il resto è in un altro elemento): anche il solo testo
    const m = /^(.*?[a-zà-ù.…)])\s*\{\d+\}$/i.exec(it), mt = /^(.*?)\s*\{\d+\}$/.exec(tr);
    if (m && mt && !/\{\d+\}/.test(m[1]) && !/\{\d+\}/.test(mt[1]) && !I18N.exact.has(m[1])) I18N.exact.set(m[1], mt[1]);
  }
  I18N.pats.sort((a, b) => b.len - a.len);
}

function trCore(core) {
  let out = I18N.exact.get(core);
  if (out != null) return out;
  for (const p of I18N.pats) {
    const m = p.re.exec(core);
    if (m) return p.tr.replace(/\{(\d+)\}/g, (_, i) => {
      const g = m[+i + 1];
      if (g == null) return '';
      const t = I18N.exact.get(g.trim());   // anche il pezzo variabile, se è un testo noto (es. un errore)
      return t != null ? t : g;
    });
  }
  return null;
}

function tr(s) {
  if (I18N.lang === 'it' || !s || typeof s !== 'string') return s;
  const core = s.replace(/\s+/g, ' ').trim();
  if (!core || !/[a-zà-ù]{2}/i.test(core)) return s;
  let out = trCore(core);
  if (out == null) {
    // punteggiatura all'inizio o alla fine (". Testo", "Testo.", ": testo")
    const pm = /^([.,:;·—–-]\s*)?(.*?)(\s*[.:;…])?$/.exec(core);
    if (pm && (pm[1] || pm[3]) && pm[2]) {
      const withEnd = pm[3] ? trCore(pm[2] + pm[3].trim()) : null;
      if (withEnd != null) out = (pm[1] || '') + withEnd;
      else { const t = trCore(pm[2]); if (t != null) out = (pm[1] || '') + t + (pm[3] || ''); }
    }
  }
  if (out == null && core.includes(' · ')) {
    // pezzi separati da " · " (es. "3 dischi · 1,2 TB", "mai controllato · serve un riavvio")
    const parts = core.split(' · ');
    const t = parts.map(x => { const y = trCore(x); return y != null ? y : x; });
    if (t.some((x, i) => x !== parts[i])) out = t.join(' · ');
  }
  if (out == null) return s;
  return s.match(/^\s*/)[0] + out + s.match(/\s*$/)[0];
}

function i18nText(n) {
  const p = n.parentElement;
  if (!p || p.closest(I18N_SKIP)) return;
  const v = n.nodeValue;
  if (n.__tr === v) return;
  const t = tr(v);
  if (t !== v) n.nodeValue = t;
  n.__tr = n.nodeValue;
}

function i18nAttrs(el) {
  for (const a of I18N_ATTRS) {
    const v = el.getAttribute(a);
    if (!v) continue;
    const t = tr(v);
    if (t !== v) el.setAttribute(a, t);
  }
}

function i18nNode(n) {
  if (I18N.lang === 'it' || !n) return;
  if (n.nodeType === 3) return i18nText(n);
  if (n.nodeType !== 1) return;
  if (n.matches && n.matches('[placeholder],[title],[aria-label]')) i18nAttrs(n);
  n.querySelectorAll('[placeholder],[title],[aria-label]').forEach(i18nAttrs);
  const w = document.createTreeWalker(n, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) i18nText(w.currentNode);
}

const i18nObs = new MutationObserver(muts => {
  for (const m of muts) {
    if (m.type === 'childList') m.addedNodes.forEach(i18nNode);
    else if (m.type === 'characterData') i18nText(m.target);
    else if (m.type === 'attributes') i18nAttrs(m.target);
  }
});

async function i18nInit(lang) {
  lang = LOCALES[lang] ? lang : 'it';
  if (lang === I18N.lang && (lang === 'it' || I18N.exact.size)) return;
  if (lang === 'it') { i18nLoad('it', null); }
  else {
    try {
      const r = await fetch('/static/lang/' + lang + '.json', { cache: 'no-cache' });
      if (!r.ok) throw new Error(r.status);
      i18nLoad(lang, await r.json());
    } catch (e) { i18nLoad('it', null); lang = 'it'; }
  }
  document.documentElement.lang = lang;
  try { localStorage.setItem('nas.lang', JSON.stringify(lang)); } catch (e) { /* navigazione privata */ }
  if (lang !== 'it' && !I18N.on) {
    I18N.on = true;
    i18nObs.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: I18N_ATTRS });
  }
  if (lang !== 'it') i18nNode(document.body);
}
