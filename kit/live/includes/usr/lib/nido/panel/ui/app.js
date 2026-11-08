// Interfaccia del NAS — struttura comune, accesso, Home
// Licenza GPL-3.0. Nessuna libreria esterna: tutto è incluso nel sistema.
'use strict';

/* ==========================================================================
   Utilità
   ========================================================================== */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = (n, d = 0) => Number(n || 0).toLocaleString(LOCALE, { minimumFractionDigits: d, maximumFractionDigits: d });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const safeUrl = u => /^https?:\/\//i.test(u || '') ? u : '';

function bytes(n, dec) {
  n = Number(n || 0);
  const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0;
  while (n >= 1000 && i < u.length - 1) { n /= 1000; i++; }
  const d = dec ?? (i === 0 ? 0 : n < 10 ? 1 : 0);
  return nf(n, d) + ' ' + u[i];
}
const rate = n => bytes(n, n >= 1e6 && n < 1e8 ? 1 : undefined).replace(/ (\w+)$/, ' $1/s');

function ago(t) {
  if (!t) return '';
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 60) return 'adesso';
  if (s < 3600) return `${Math.floor(s / 60)} min fa`;
  if (s < 86400) return `${Math.floor(s / 3600)} ore fa`;
  const d = Math.floor(s / 86400);
  return d === 1 ? 'ieri' : `${d} giorni fa`;
}
const dateIt = t => new Date(t * 1000).toLocaleString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
// Durata leggibile: "3 g 4 h 12 min", "5 h 3 min", "12 min"
function durText(s) {
  s = Math.max(0, Math.floor(s));
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  if (d) return `${d} g ${h} h ${m} min`;
  if (h) return `${h} h ${m} min`;
  return `${m} min`;
}
function uptimeText(s) {
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600);
  if (d >= 1) return `acceso da ${d} ${d === 1 ? 'giorno' : 'giorni'}`;
  if (h >= 1) return `acceso da ${h} ${h === 1 ? 'ora' : 'ore'}`;
  return 'acceso da poco';
}

const store = {
  get(k, d) { try { const v = localStorage.getItem('nas.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('nas.' + k, JSON.stringify(v)); } catch (e) { /* navigazione privata */ } },
};

/* ==========================================================================
   Icone (tratti SVG, nessuna immagine esterna)
   ========================================================================== */

const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  bag: '<path d="M6 7h12l1 14H5L6 7z"/><path d="M9 7a3 3 0 0 1 6 0"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  disk: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 14h18"/><circle cx="17" cy="17" r=".6" fill="currentColor"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
  users: '<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><path d="M16 3.5a4 4 0 0 1 0 9M22 21a7 7 0 0 0-4-6.3"/>',
  backup: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>',
  term: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3M12 15h5"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  ram: '<rect x="2" y="7" width="20" height="10" rx="2"/><path d="M6 11v2M10 11v2M14 11v2M18 11v2M6 17v3M18 17v3"/>',
  net: '<path d="M12 3v14M7 8l5-5 5 5"/><path d="M5 21h14"/>',
  temp: '<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  newfolder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v5M9.5 13.5h5"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  back: '<path d="m15 6-6 6 6 6"/>',
  up: '<path d="m6 15 6-6 6 6"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
  dl: '<path d="M12 4v12M7 11l5 5 5-5"/>',
  check: '<path d="m5 12 5 5L20 7"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  play: '<path d="M7 4v16l13-8z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  restart: '<path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  lan: '<rect x="9" y="3" width="6" height="5" rx="1"/><rect x="3" y="16" width="6" height="5" rx="1"/><rect x="15" y="16" width="6" height="5" rx="1"/><path d="M12 8v4M6 16v-2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2"/>',
  monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  cloud: '<path d="M7 18.5h10.5a4 4 0 0 0 .4-7.98A6 6 0 0 0 6.3 9.6 4.5 4.5 0 0 0 7 18.5z"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  usb: '<path d="M12 2v14"/><circle cx="12" cy="18" r="3"/><path d="M8 7v3l4 2 4-2V6"/><rect x="15" y="4" width="2" height="2"/><circle cx="8" cy="6" r="1"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.3-9.3M17 6l3 3M14 9l2 2"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  move: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  container: '<path d="M3 8 12 4l9 4v8l-9 4-9-4z"/><path d="M3 8l9 4 9-4M12 12v8M7.5 10v7.5M16.5 10v7.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  power: '<path d="M12 3v9"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9"/><path d="M10 13h4"/>',
  sort: '<path d="M7 4v16M3 16l4 4 4-4M17 20V4M13 8l4-4 4 4"/>',
  heart: '<path d="M12 20s-7-4.4-9.2-9A5 5 0 0 1 12 6a5 5 0 0 1 9.2 5c-2.2 4.6-9.2 9-9.2 9z"/>',
  logout: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 17l-5-5 5-5M5 12h11"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  scan: '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  code: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>',
  sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
};
const ic = (n, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;

// Icona di un'app: immagine dallo store se c'è, altrimenti tessera colorata con le iniziali
const TILE_COLORS = [['#7c3aed', '#06b6d4'], ['#f43f5e', '#f59e0b'], ['#38bdf8', '#0284c7'], ['#3b82f6', '#1d4ed8'], ['#ef4444', '#991b1b'],
  ['#334155', '#0f172a'], ['#60a5fa', '#2563eb'], ['#4ade80', '#15803d'], ['#64748b', '#334155'], ['#fbbf24', '#b45309'], ['#22c55e', '#166534'],
  ['#a78bfa', '#5b21b6'], ['#fb923c', '#c2410c'], ['#84cc16', '#3f6212'], ['#ec4899', '#9d174d'], ['#14b8a6', '#0f766e']];
function tileColor(name) {
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const [a, b] = TILE_COLORS[h % TILE_COLORS.length];
  return `linear-gradient(140deg,${a},${b})`;
}
function initials(name) {
  const w = String(name || '?').replace(/[^A-Za-z0-9 ]/g, ' ').trim().split(/\s+/);
  return (w.length > 1 ? w[0][0] + w[1][0] : (w[0] || '?').slice(0, 2)).replace(/^./, c => c.toUpperCase());
}
function appIcon(a, size = '') {
  const url = safeUrl(a.icon);
  const img = url ? `<img src="${esc(url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '';
  return `<div class="appicon ${size}" style="background:${tileColor(a.title || a.name)}">${esc(initials(a.title || a.name))}${img}</div>`;
}

/* Logo: arco di una caverna con la sfumatura del marchio e tre dischi dentro */
let _cid = 0;
function cube(size = 34) {
  const k = 'c' + (_cid++);
  const cols = [['#22d3ee', '#6366f1'], ['#f472b6', '#8b5cf6'], ['#fb923c', '#facc15']];
  let defs = '', body = '';
  cols.forEach(([a, b], i) => {
    defs += `<linearGradient id="${k}d${i}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>`;
    const y = 31 + i * 8.4;
    body += `<rect x="21" y="${y}" width="22" height="6.2" rx="1.74" fill="url(#${k}d${i})"/>`;
    body += `<circle cx="39.16" cy="${y + 3.1}" r="1.05" fill="#fff"/>`;
    body += `<path d="M24.41 ${y + 3.1}h9.24" stroke="#fff" stroke-width="1" stroke-linecap="round" opacity=".8"/>`;
  });
  return `<svg width="${size}" height="${size}" viewBox="0 0 64 64" style="flex:none" aria-hidden="true"><defs>
    <linearGradient id="${k}a" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#06b6d4"/><stop offset=".4" stop-color="#6366f1"/><stop offset=".75" stop-color="#ec4899"/><stop offset="1" stop-color="#f97316"/></linearGradient>${defs}</defs>
    <path d="M11 56V33a21 21 0 0 1 42 0v23" fill="none" stroke="url(#${k}a)" stroke-width="7" stroke-linecap="round"/>${body}</svg>`;
}

/* ==========================================================================
   Stato globale, API, finestre, notifiche
   ========================================================================== */

const S = {
  about: { name: 'NAS', wordmark: '', hostname: location.hostname, donate: [] },
  user: null, admin: false, page: null, timers: {}, cleanup: [], badges: {},
};

// Scritta del marchio, pezzi separati da "|": i pezzi dispari (1°, 3°, 5°…) scuri in Orbitron, quelli pari
// con la sfumatura in JetBrains Mono. "R|N|F|A|D|S" -> R, F, D in Orbitron; N, A, S in JetBrains Mono.
function word() {
  const wm = S.about.wordmark || '';
  if (wm.includes('|')) return wm.split('|').map((x, i) => i % 2 ? `<span class="wm-b grad-t">${esc(x)}</span>` : `<span class="wm-a">${esc(x)}</span>`).join('');
  const n = (S.about.name || 'nas').toLowerCase();
  const cut = Math.max(1, n.length - 3);
  return `${esc(n.slice(0, cut))}<span class="grad-t">${esc(n.slice(cut))}</span>`;
}
const host = () => (S.about.hostname ? S.about.hostname + '.local' : location.hostname);

class HttpError extends Error { constructor(msg, status) { super(msg); this.status = status; } }

async function api(method, path, body, opts = {}) {
  const o = { method, headers: { 'X-Nido': '1' }, credentials: 'same-origin' };
  if (body !== undefined) { o.body = JSON.stringify(body); o.headers['Content-Type'] = 'application/json'; }
  // Tempo massimo: senza, una richiesta bloccata lasciava la pagina sulla rotellina per sempre
  const ctl = typeof AbortController === 'function' ? new AbortController() : null;
  const limit = opts.timeout ?? (method === 'GET' ? 45000 : 180000);
  const timer = ctl && limit ? setTimeout(() => ctl.abort(), limit) : null;
  if (ctl) o.signal = ctl.signal;
  let r;
  try { r = await fetch('/api' + path, o); } catch (e) {
    throw new HttpError(e && e.name === 'AbortError' ? 'Il NAS non ha risposto in tempo: riprova tra poco' : 'Il NAS non risponde: controlla la connessione', 0);
  } finally { if (timer) clearTimeout(timer); }
  let j = {};
  try { j = await r.json(); } catch (e) { /* vuota */ }
  if (r.status === 401 && !opts.noAuthRedirect && !path.startsWith('/auth/')) { showLogin(); throw new HttpError(j.error || 'Accesso scaduto', 401); }
  if (!r.ok) throw new HttpError(j.error || `Errore ${r.status}`, r.status);
  return j;
}

function toast(msg, kind = 'ok', ms = 4200) {
  let box = $('#toasts');
  if (!box) { box = document.createElement('div'); box.id = 'toasts'; box.className = 'toasts'; document.body.appendChild(box); }
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.innerHTML = ic(kind === 'bad' ? 'alert' : kind === 'info' ? 'info' : 'check') + `<div>${esc(msg)}</div>`;
  box.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

// Esegue un'azione su un pulsante: rotellina durante l'attesa, messaggio d'errore se fallisce
async function act(btn, fn, okMsg) {
  const old = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>' + (btn.textContent.trim() ? `<span>${esc(btn.textContent.trim())}</span>` : ''); }
  try {
    const r = await fn();
    if (okMsg) toast(typeof okMsg === 'function' ? okMsg(r) : okMsg);
    return r;
  } catch (e) {
    toast(e.message, 'bad', 7000);
    return null;
  } finally {
    if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = old; }
  }
}

function modal(html, cls = '') {
  closeModal();
  const s = document.createElement('div');
  s.className = 'scrim';
  s.id = 'scrim';
  s.innerHTML = `<div class="modal ${cls}" role="dialog" aria-modal="true">${html}</div>`;
  s.addEventListener('mousedown', e => { if (e.target === s && !s.dataset.lock) closeModal(); });
  document.body.appendChild(s);
  $$('[data-close]', s).forEach(b => b.onclick = closeModal);
  const first = $('input:not([type=hidden]):not([disabled]),textarea,select', s);
  if (first && !('ontouchstart' in window)) setTimeout(() => first.focus(), 30);
  return $('.modal', s);
}
function closeModal() { const s = $('#scrim'); if (s) { s.remove(); if (S.onModalClose) { const f = S.onModalClose; S.onModalClose = null; f(); } } }
const mhead = (icon, title, sub) => `<div class="mh">${icon}<div style="flex:1;min-width:0"><h2>${title}</h2>${sub ? `<div class="muted" style="font-size:13px">${sub}</div>` : ''}</div><button class="iconbtn x" data-close title="Chiudi">${ic('x')}</button></div>`;

function ask(title, text, okLabel = 'OK', danger = false) {
  return new Promise(res => {
    const m = modal(`${mhead(`<div class="dicon">${ic(danger ? 'alert' : 'info')}</div>`, esc(title))}
      <div class="mb"><div class="dialog-text">${text}</div></div>
      <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn ${danger ? 'danger solid' : 'primary'}" id="ok">${esc(okLabel)}</button></div>`, 'sm');
    S.onModalClose = () => res(false);
    $('#ok', m).onclick = () => { S.onModalClose = null; closeModal(); res(true); };
  });
}
function prompt2(title, label, value = '', okLabel = 'OK') {
  return new Promise(res => {
    const m = modal(`${mhead(`<div class="dicon">${ic('pencil')}</div>`, esc(title))}
      <div class="mb"><div class="field"><label>${esc(label)}</label><input class="input" id="pv" value="${esc(value)}"></div></div>
      <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="ok">${esc(okLabel)}</button></div>`, 'sm');
    S.onModalClose = () => res(null);
    const inp = $('#pv', m);
    const dot = value.lastIndexOf('.');
    setTimeout(() => { inp.focus(); inp.setSelectionRange(0, dot > 0 ? dot : value.length); }, 40);
    const ok = () => { const v = inp.value.trim(); S.onModalClose = null; closeModal(); res(v || null); };
    $('#ok', m).onclick = ok;
    inp.onkeydown = e => { if (e.key === 'Enter') ok(); };
  });
}

// Menu a comparsa vicino a un pulsante
function popmenu(anchor, items) {
  $$('.menu').forEach(m => m.remove());
  // Niente separatori doppi o in cima/in fondo (le voci possono mancare)
  items = items.filter(Boolean).filter((it, k, a) => it !== '-' || (k > 0 && k < a.length - 1 && a[k - 1] !== '-'));
  const m = document.createElement('div');
  m.className = 'menu';
  m.innerHTML = items.map((it, k) => it === '-' ? '<hr>' : `<button data-k="${k}" class="${it.danger ? 'danger' : ''}" ${it.disabled ? 'disabled' : ''}>${ic(it.icon || 'chevron')}<span class="ml">${esc(it.label)}</span>${it.kbd ? `<kbd>${esc(it.kbd)}</kbd>` : ''}</button>`).join('');
  document.body.appendChild(m);
  const w = m.offsetWidth, h = m.offsetHeight;
  if (anchor && anchor.x != null && !anchor.getBoundingClientRect) {
    // Menu del tasto destro: si apre dove si trova il puntatore
    m.style.left = Math.max(8, Math.min(anchor.x, innerWidth - w - 8)) + 'px';
    m.style.top = Math.max(8, anchor.y + h + 8 > innerHeight ? anchor.y - h : anchor.y) + 'px';
  } else {
    const r = anchor.getBoundingClientRect();
    m.style.left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + 'px';
    m.style.top = (r.bottom + h + 8 > innerHeight ? Math.max(8, r.top - h - 6) : r.bottom + 6) + 'px';
  }
  m.oncontextmenu = e => e.preventDefault();
  $$('button', m).forEach(b => b.onclick = () => { m.remove(); items[b.dataset.k].fn(); });
  setTimeout(() => document.addEventListener('mousedown', function off(e) { if (!m.contains(e.target)) { m.remove(); document.removeEventListener('mousedown', off); } }), 0);
}

// Segue un'operazione lunga del NAS (installazione, aggiornamento, copia...)
async function followJob(id, onTick) {
  for (;;) {
    let j;
    try { j = await api('GET', '/jobs/' + id); } catch (e) { if (e.status === 404) throw e; await sleep(2000); continue; }
    if (onTick) onTick(j);
    if (j.state !== 'running' && j.state !== 'queued') return j;
    await sleep(1200);
  }
}

function every(key, ms, fn) {
  clearInterval(S.timers[key]);
  S.timers[key] = setInterval(() => { if (!document.hidden) fn(); }, ms);
}
function stopTimers() { Object.values(S.timers).forEach(clearInterval); S.timers = {}; S.cleanup.forEach(f => f()); S.cleanup = []; }

/* ==========================================================================
   Tema chiaro / scuro
   ========================================================================== */

function applyTheme() {
  const t = store.get('theme', 'auto');
  if (t === 'auto') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
}
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
}
function toggleTheme() {
  store.set('theme', isDark() ? 'light' : 'dark');
  applyTheme();
  $$('[data-theme-btn]').forEach(b => b.innerHTML = ic(isDark() ? 'sun' : 'moon'));
}

/* ==========================================================================
   Struttura della pagina
   ========================================================================== */

const NAV = [
  ['home', 'home', 'Home', '#3b82f6'], ['store', 'bag', 'App store', '#ec4899'], ['files', 'folder', 'File', '#f59e0b'],
  ['disks', 'disk', 'Dischi', '#14b8a6'], ['shares', 'share', 'Condivisioni', '#8b5cf6'], ['users', 'users', 'Utenti', '#22c55e'],
  ['backup', 'backup', 'Backup', '#f97316'], ['term', 'term', 'Terminale', '#64748b'], ['settings', 'gear', 'Impostazioni', '#6366f1'],
];
const SECTION_OF = { apps: 'store', hub: 'store', donate: 'settings', about: 'settings' };

function shell(route, title, sub, body, opts = {}) {
  const active = SECTION_OF[route] || route;
  // Gli account "Utente" vedono solo Home, App store (in consultazione) e Impostazioni
  const USER_PAGES = ['home', 'store', 'settings'];
  const navLink = ([id, i, t, c]) => `<a class="${active === id ? 'on' : ''}" href="#${id}" style="--c:${c}"><span class="ni">${ic(i)}</span>${t}${id === 'store' && S.badges.apps ? `<span class="badge acc">${S.badges.apps}</span>` : ''}</a>`;
  const visible = NAV.filter(([id]) => S.admin || USER_PAGES.includes(id));
  const nav = visible.map((n, k) => (S.admin && (k === 3 || k === 7) ? '<div class="sep"></div>' : '') + navLink(n)).join('');
  const tabs = [['home', 'home', 'Home'], ['store', 'bag', 'App'], ['files', 'folder', 'File'], ['apps', 'grid', 'Le mie app']];
  return `<div class="app">
  <aside class="side">
    <a class="brand" href="#home" style="text-decoration:none;color:inherit">${cube(36)}<div><b class="word">${word()}</b><span>${esc(host())}</span></div></a>
    <nav class="nav">${nav}</nav>
    <a class="donate" href="#donate">${ic('heart')}Sostieni il progetto</a>
    <a class="foot" href="#settings" id="sysfoot"><span class="dot"></span><div><b style="color:var(--ink-2)">Tutto a posto</b><br><span id="sysfoot-s">${esc(S.about.name)} ${esc(S.about.version || '')}</span></div></a>
  </aside>
  <main class="main">
    <div class="top">
      <div style="min-width:0"><h1>${title}</h1>${sub ? `<div class="sub" id="subtitle">${sub}</div>` : ''}</div>
      <div class="grow"></div>
      ${opts.noSearch ? '' : `<label class="search hide-m" id="gsearch">${ic('search')}<input placeholder="Cerca app, file, impostazioni…" readonly><kbd>Ctrl K</kbd></label>`}
      ${S.admin ? `<button class="iconbtn" id="powermenu" title="Riavvia o spegni il NAS" aria-label="Riavvia o spegni il NAS">${ic('power')}</button>` : ''}
      <button class="iconbtn" data-theme-btn title="Tema chiaro o scuro">${ic(isDark() ? 'sun' : 'moon')}</button>
      <button class="iconbtn" id="usermenu" title="${esc(S.user || '')}" style="border-radius:50%;padding:0;border:0;background:var(--brand);color:#fff;font-weight:700">${esc((S.user || 'A')[0].toUpperCase())}</button>
    </div>
    ${body}
  </main>
  <nav class="tabbar">
    ${tabs.map(([id, i, t]) => `<a class="${route === id || (id === 'store' && route === 'hub') ? 'on' : ''}" href="#${id}">${ic(i)}${t}</a>`).join('')}
    <a id="moretab" class="${['disks', 'shares', 'users', 'backup', 'term', 'settings', 'donate', 'about'].includes(route) ? 'on' : ''}">${ic('menu')}Altro</a>
  </nav>
</div>`;
}

function wireShell() {
  $$('[data-theme-btn]').forEach(b => b.onclick = toggleTheme);
  const pm = $('#powermenu');
  if (pm) pm.onclick = () => popmenu(pm, [
    { icon: 'restart', label: 'Riavvia il NAS', fn: () => powerAction('reboot') },
    { icon: 'stop', label: 'Spegni il NAS', danger: true, fn: () => powerAction('poweroff') }]);
  const gs = $('#gsearch');
  if (gs) gs.onclick = () => palette();
  const um = $('#usermenu');
  if (um) um.onclick = () => popmenu(um, [
    { label: `Account: ${S.user}`, icon: 'users', fn: () => go('settings') },
    { label: 'Cambia password', icon: 'key', fn: changePassword },
    { label: 'Informazioni e licenze', icon: 'info', fn: () => go('about') },
    '-',
    { label: 'Esci', icon: 'logout', fn: logout },
  ]);
  const mt = $('#moretab');
  if (mt) mt.onclick = e => {
    e.preventDefault();
    if ($('.sheet')) { $('.sheet').remove(); return; }
    const sh = document.createElement('div');
    sh.className = 'sheet';
    sh.innerHTML = NAV.slice(3).map(([id, i, t, c]) => `<a href="#${id}" style="--c:${c}"><span class="ni">${ic(i)}</span>${t}</a>`).join('') +
      `<a href="#donate" style="--c:#ec4899"><span class="ni">${ic('heart')}</span>Sostieni</a>`;
    document.body.appendChild(sh);
    setTimeout(() => document.addEventListener('click', function off() { sh.remove(); document.removeEventListener('click', off); }), 0);
  };
}

function go(route) { if (location.hash === '#' + route) render(); else location.hash = route; }

/* ==========================================================================
   Accesso e prima configurazione
   ========================================================================== */

function showLogin() {
  stopTimers();
  closeModal();
  S.user = null;
  const setup = S.setup;
  $('#root').innerHTML = `<div class="login-wrap"><form class="card login-card" id="lf" autocomplete="on">
    <div style="display:grid;justify-items:center;gap:6px">${cube(72)}<div class="word" style="font-size:30px">${word()}</div></div>
    <h2>${setup ? 'Benvenuto' : 'Bentornato'}</h2>
    <div class="muted" style="margin-bottom:22px">${setup ? 'Crea l\'account amministratore del NAS' : esc(host())}</div>
    <div class="grid" style="gap:12px">
      <div class="field"><label for="lu">Utente</label><input class="input" id="lu" name="username" autocomplete="username" value="${setup ? 'admin' : esc(store.get('lastUser', ''))}" autocapitalize="off" spellcheck="false" required></div>
      <div class="field"><label for="lp">Password</label><input class="input" id="lp" type="password" name="password" autocomplete="${setup ? 'new-password' : 'current-password'}" required>${setup ? '<span class="hint">Almeno 8 caratteri</span>' : ''}</div>
      ${setup ? `<div class="field"><label for="lp2">Ripeti la password</label><input class="input" id="lp2" type="password" autocomplete="new-password" required></div>` :
        `<label class="row" style="font-size:13px;cursor:pointer"><button type="button" class="toggle ${store.get('remember', true) ? 'on' : ''}" id="rem" aria-label="Ricordami"></button>Ricordami su questo dispositivo</label>`}
      <div class="err" id="lerr" hidden></div>
      <button class="btn primary" style="justify-content:center;height:42px" id="lgo">${setup ? 'Crea account ed entra' : 'Accedi'}</button>
    </div>
    <div class="muted" style="font-size:12px;margin-top:18px;display:flex;gap:6px;justify-content:center;align-items:center">${ic('lock')} ${location.protocol === 'https:' ? 'Connessione protetta' : 'Rete di casa'}</div>
    ${S.local ? `<div class="muted" style="font-size:12.5px;margin-top:10px;text-align:center;line-height:1.6">${ic('monitor')} Schermo del NAS<br>${S.local.length ? `Dagli altri dispositivi: <span class="notr mono">${S.local.map(a => 'http://' + esc(a)).join(' · ')}</span>` : 'Nessun indirizzo di rete: controlla il cavo o le impostazioni di rete'}</div>` : ''}
  </form></div>`;
  const rem = $('#rem');
  if (rem) rem.onclick = () => rem.classList.toggle('on');
  $(setup || !store.get('lastUser', '') ? '#lu' : '#lp').focus();
  $('#lf').onsubmit = async e => {
    e.preventDefault();
    const err = $('#lerr'), btn = $('#lgo');
    err.hidden = true;
    const user = $('#lu').value.trim().toLowerCase(), password = $('#lp').value;
    if (setup && password !== $('#lp2').value) { err.textContent = 'Le due password non coincidono'; err.hidden = false; return; }
    btn.disabled = true;
    try {
      if (setup) await api('POST', '/auth/setup', { user, password });
      else await api('POST', '/auth/login', { user, password, remember: rem.classList.contains('on') });
      store.set('lastUser', user);
      if (rem) store.set('remember', rem.classList.contains('on'));
      await boot();
      if (location.hash === '#login') location.hash = 'home';
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false;
      $('#lp').select();
    } finally { btn.disabled = false; }
  };
}

async function logout() {
  try { await api('POST', '/auth/logout'); } catch (e) { /* già uscito */ }
  S.setup = false;
  showLogin();
}

function changePassword() {
  const m = modal(`${mhead(`<div class="dicon">${ic('key')}</div>`, 'Cambia password', `Account ${esc(S.user)}`)}
    <div class="mb">
      <div class="field"><label>Password attuale</label><input class="input" type="password" id="po" autocomplete="current-password"></div>
      <div class="field"><label>Nuova password</label><input class="input" type="password" id="pn" autocomplete="new-password"><span class="hint">Almeno 8 caratteri. Le altre sessioni aperte verranno chiuse.</span></div>
      <div class="field"><label>Ripeti la nuova password</label><input class="input" type="password" id="pn2" autocomplete="new-password"></div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="ok">Cambia</button></div>`, 'sm');
  $('#ok', m).onclick = e => {
    if ($('#pn', m).value !== $('#pn2', m).value) return toast('Le due password non coincidono', 'bad');
    act(e.currentTarget, () => api('POST', '/auth/password', { old: $('#po', m).value, new: $('#pn', m).value }), 'Password cambiata').then(r => { if (r) closeModal(); });
  };
}

/* ==========================================================================
   Grafici
   ========================================================================== */

function pathFor(vals, w, h, max, close) {
  if (vals.length < 2) vals = [vals[0] || 0, vals[0] || 0];
  const step = w / (vals.length - 1);
  const pts = vals.map((v, i) => [i * step, h - (Math.min(v, max) / max) * (h - 4) - 2]);
  let d = 'M' + pts.map(p => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' L');
  if (close) d += ` L${w} ${h} L0 ${h} Z`;
  return d;
}
function spark(vals, max, color) {
  const w = 240, h = 42, id = 'g' + Math.random().toString(36).slice(2, 7);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".28"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
    <path d="${pathFor(vals, w, h, max, 1)}" fill="url(#${id})"/><path d="${pathFor(vals, w, h, max)}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}
function niceMax(v) {
  const steps = [125e3, 250e3, 500e3, 1e6, 2.5e6, 5e6, 10e6, 25e6, 50e6, 100e6, 125e6, 250e6, 500e6, 1.25e9];
  return steps.find(s => s >= v * 1.1) || v * 1.2;
}
function netChart(down, up) {
  const w = 640, h = 190, max = niceMax(Math.max(...down, ...up, 1));
  const grid = [0, .25, .5, .75].map(f => `<line x1="0" x2="${w}" y1="${(h * f).toFixed(0)}" y2="${(h * f).toFixed(0)}" stroke="var(--line)"/>`).join('');
  const lbl = [1, .75, .5, .25].map((f, i) => `<text x="4" y="${h * i / 4 + 13}" font-size="10.5" fill="var(--ink-3)">${esc(rate(max * f))}</text>`).join('');
  return `<svg class="netchart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${grid}
    <defs><linearGradient id="nd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--net-down)" stop-opacity=".25"/><stop offset="1" stop-color="var(--net-down)" stop-opacity="0"/></linearGradient></defs>
    <path d="${pathFor(down, w, h, max, 1)}" fill="url(#nd)"/>
    <path d="${pathFor(down, w, h, max)}" fill="none" stroke="var(--net-down)" stroke-width="2.2" vector-effect="non-scaling-stroke"/>
    <path d="${pathFor(up, w, h, max)}" fill="none" stroke="var(--net-up)" stroke-width="2.2" vector-effect="non-scaling-stroke"/>
    ${lbl}</svg>`;
}

/* ==========================================================================
   Home
   ========================================================================== */

function appUrl(a) {
  const w = a.web || {};
  if (!w.port) return '';
  // Con "HTTPS anche per le app": https://<app>.<nome>.local senza numero di porta
  if (S.about.app_domain && /\.local$/.test(location.hostname)) {
    const sub = String(a.name || '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
    if (sub) return `${location.protocol}//${sub}.${S.about.app_domain}${w.index || '/'}`;
  }
  return `${w.scheme || 'http'}://${location.hostname}:${w.port}${w.index || '/'}`;
}
function stateBadge(st) {
  return { attiva: '<span class="badge ok"><span class="d"></span>attiva</span>', ferma: '<span class="badge">ferma</span>',
    parziale: '<span class="badge warn"><span class="d"></span>in parte</span>', riavvio: '<span class="badge warn"><span class="d"></span>si riavvia</span>',
    assente: '<span class="badge bad">non trovata</span>' }[st] || `<span class="badge">${esc(st)}</span>`;
}

async function pageHome() {
  const root = $('#root');
  let d;
  try { d = await api('GET', '/home'); } catch (e) { return pageError(e); }
  const H = { t: d.history.map(x => x[0]), cpu: d.history.map(x => x[1]), mem: d.history.map(x => x[2]),
    down: d.history.map(x => x[3]), up: d.history.map(x => x[4]), temp: d.history.map(x => x[5] ?? 0) };
  const hour = new Date().getHours();
  const hello = hour < 13 ? 'Buongiorno' : hour < 18 ? 'Buon pomeriggio' : 'Buonasera';
  const today = new Date().toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long' });
  const name = S.user ? S.user[0].toUpperCase() + S.user.slice(1) : '';
  const upd = d.updates.apps + d.updates.system;
  const subParts = [today.replace(/^./, c => c.toUpperCase())];
  subParts.push(d.reboot ? 'serve un riavvio' : upd ? `${upd} aggiornament${upd === 1 ? 'o' : 'i'} disponibil${upd === 1 ? 'e' : 'i'}` : 'tutto funziona');
  S.badges.apps = d.updates.apps || 0;

  const stat = (id, c, icon, k) => `<div class="card stat" style="--c:${c}" id="st-${id}"><div class="k">${ic(icon)}${k}</div><div class="v"></div><div class="s"></div><div class="sp"></div></div>`;
  const pendingApps = d.apps == null, pendingDisks = d.disks == null;
  d.apps = d.apps || []; d.disks = d.disks || [];
  const tiles = pendingApps ? '<div class="muted row" style="padding:10px 0"><span class="spin"></span>Leggo lo stato delle app…</div>' : d.apps.map(a => {
    const url = appUrl(a);
    const st = a.state === 'attiva' ? '' : a.state === 'parziale' || a.state === 'riavvio' ? 'part' : 'off';
    return `<a class="apptile" ${url && a.state === 'attiva' ? `href="${esc(url)}" target="_blank" rel="noopener"` : 'href="#apps"'} title="${esc(a.title)}${url ? ' — ' + esc(url) : ''}">
      <div class="ico">${appIcon(a)}<span class="st ${st}"></span></div><div class="nm">${esc(a.title)}</div></a>`;
  }).join('') + `<a class="apptile add" href="#store"><div class="appicon">${ic('plus')}</div><div class="nm muted">Aggiungi</div></a>`;
  const on = d.apps.filter(a => a.state === 'attiva').length, off = d.apps.length - on;

  const disks = d.disks.map(x => {
    const pct = x.size ? 100 * x.used / x.size : 0;
    const warn = pct >= 85;
    return `<a class="disk" href="#files" data-path="${esc(x.path)}" style="text-decoration:none;color:inherit">
      <div class="row"><b>${esc(x.name)}</b><span class="muted">${esc(x.kind)} ${bytes(x.size)}${x.fstype ? ' · ' + esc(x.fstype) : ''}</span><span class="grow"></span><span>${bytes(x.used)}</span></div>
      <div class="bar ${warn ? 'warn' : ''}"><i style="width:${Math.max(1, pct).toFixed(1)}%"></i></div>
      ${warn ? `<div class="s" style="font-size:12px;color:var(--warn)">Quasi pieno: restano ${bytes(x.free)}</div>` : ''}</a>`;
  }).join('') || (pendingDisks ? '<div class="muted row"><span class="spin"></span>Leggo lo spazio dei dischi…</div>' : '<div class="muted">Nessun disco trovato</div>');

  root.innerHTML = shell('home', `${hello}${name ? ', ' + esc(name) : ''}`, esc(subParts.join(' · ')), `
  <div class="hero">
    ${stat('cpu', '#6366f1', 'cpu', 'Processore')}${stat('mem', '#ec4899', 'ram', 'Memoria')}${stat('net', '#06b6d4', 'net', 'Rete')}${stat('temp', '#f97316', 'temp', 'Temperatura')}
  </div>
  ${uptimeStrip(d)}
  <div class="dash2">
    <div class="card">
      <h3>${ic('net')}Traffico di rete <span class="more">ultima ora</span></h3>
      <div class="legend" style="margin-bottom:10px">
        <div><span class="sw" style="background:var(--net-down)"></span>Download<b id="lg-down"></b></div>
        <div><span class="sw" style="background:var(--net-up)"></span>Upload<b id="lg-up"></b></div>
        <div style="margin-left:auto;text-align:right">Oggi<b id="lg-today"></b></div>
      </div>
      <div id="netchart"></div>
    </div>
    <div class="card">
      <h3>${ic('disk')}Spazio <a class="more" href="#files" style="text-decoration:none">File ›</a></h3>
      ${disks}
    </div>
  </div>
  <div class="card">
    <h3>${ic('grid')}Le tue app ${d.apps.length ? `<span class="badge ok"><span class="d"></span>${on} attiv${on === 1 ? 'a' : 'e'}</span>${off ? `<span class="badge">${off} ferm${off === 1 ? 'a' : 'e'}</span>` : ''}` : ''}<a class="more" href="#apps" style="text-decoration:none">Gestisci ›</a></h3>
    ${d.docker !== false ? '' : `<div class="alert bad" style="margin-bottom:12px">${ic('alert')}<div>Il motore delle app (Docker) non risponde.</div></div>`}
    <div class="apps">${tiles}</div>
  </div>`);
  wireShell();
  $$('.disk[data-path]').forEach(a => a.onclick = () => store.set('filesPath', a.dataset.path));
  const foot = $('#sysfoot-s');
  if (foot) foot.textContent = `${uptimeText(d.uptime)}`;

  const cpu = d.cpu;
  function paint(live) {
    const set = (id, v, s, sp) => { const c = $('#st-' + id); if (!c) return; $('.v', c).innerHTML = v; $('.s', c).textContent = s; $('.sp', c).innerHTML = sp; };
    set('cpu', `${nf(live.cpu, 0)}<small>%</small>`, [cpu.model, cpu.cores ? `${cpu.cores} core` : '', cpu.mhz ? `${nf(cpu.mhz / 1000, 1)} GHz` : ''].filter(Boolean).join(' · '), spark(H.cpu.slice(-40), 100, '#6366f1'));
    const m = live.mem;
    set('mem', `${nf(m.used / 2 ** 30, 1)}<small> / ${nf(m.total / 2 ** 30, 0)} GB</small>`, `${nf(m.percent, 0)}% · cache ${nf(m.cache / 2 ** 30, 1)} GB`, spark(H.mem.slice(-40), 100, '#ec4899'));
    const tot = live.down + live.up;
    const nmax = niceMax(Math.max(...H.down.slice(-40), ...H.up.slice(-40), 1));
    set('net', `${rate(tot).replace(/ (\S+)$/, '<small> $1</small>')}`, `↓ ${rate(live.down)}  ↑ ${rate(live.up)}${d.link ? ` · ${d.link >= 1000 ? nf(d.link / 1000, d.link % 1000 ? 1 : 0) + ' Gbit/s' : d.link + ' Mbit/s'}` : ''}`,
      spark(H.down.slice(-40).map((v, i) => v + (H.up.slice(-40)[i] || 0)), nmax, '#06b6d4'));
    const t = live.temp || {};
    set('temp', t.cpu != null ? `${nf(t.cpu, 0)}<small> °C</small>` : '<small>non disponibile</small>',
      [t.cpu != null ? 'CPU' : '', t.disks ? `dischi ${nf(t.disks[0], 0)}${t.disks[1] !== t.disks[0] ? '–' + nf(t.disks[1], 0) : ''} °C` : ''].filter(Boolean).join(' · ') || 'Nessun sensore trovato',
      t.cpu != null ? spark(H.temp.slice(-40), 100, '#f59e0b') : '');
    $('#lg-down').textContent = rate(live.down);
    $('#lg-up').textContent = rate(live.up);
    $('#lg-today').textContent = bytes(live.today);
    $('#netchart').innerHTML = netChart(H.down, H.up);
  }
  paint(d.live);
  // Tempo dall'ultimo avvio, aggiornato dal vivo
  const t0 = Date.now(), up0 = (d.uptime_stats || {}).since_boot ?? d.uptime;
  const tick = () => { const el = $('#upnow'); if (el) el.textContent = durText(up0 + (Date.now() - t0) / 1000); };
  every('uptime', 20000, tick);
  if (pendingApps || pendingDisks) {
    // Docker o i dischi non hanno ancora risposto: ridisegno la Home appena sono pronti
    let tries = 0;
    every('homefill', 2500, async () => {
      if (S.page !== 'home' || ++tries > 40) return clearInterval(S.timers.homefill);
      const x = await api('GET', '/home').catch(() => null);
      if (x && x.apps != null && x.disks != null) { clearInterval(S.timers.homefill); if (S.page === 'home') pageHome(); }
    });
  }
  let lastT = d.live.t;
  every('home', 3000, async () => {
    try {
      const live = await api('GET', '/home/live');
      if (live.t !== lastT) {
        lastT = live.t;
        H.cpu.push(live.cpu); H.mem.push(live.mem.percent); H.down.push(live.down); H.up.push(live.up); H.temp.push((live.temp || {}).cpu ?? 0);
        // Il grafico grande mostra l'ultima ora con 120 punti: un punto ogni 30 s
        const keep = 160;
        for (const k of ['cpu', 'mem', 'down', 'up', 'temp']) if (H[k].length > keep) H[k].splice(0, H[k].length - keep);
      }
      paint(live);
    } catch (e) { /* la prossima volta */ }
  });
}

function uptimeStrip(d) {
  const u = d.uptime_stats;
  if (!u) return '';
  const ls = u.last_shutdown;
  const when = t => new Date(t * 1000).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const since = u.counting_since ? new Date(u.counting_since * 1000).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  return `<div class="card upstrip">
    <div class="up1">${ic('power')}<div><div class="k">Acceso da</div><b id="upnow">${durText(u.since_boot)}</b><div class="s">dal ${esc(when(u.boot_time))}</div></div></div>
    <div><div class="k">Ore di accensione</div><b>${nf(u.total_hours, u.total_hours < 100 ? 1 : 0)} h</b><div class="s" title="Contate dal NAS ogni minuto">${since ? 'dal ' + esc(since) : 'in totale'}</div></div>
    <div><div class="k">Avvii</div><b>${nf(u.boots)}</b><div class="s">${u.unclean ? `${nf(u.unclean)} spegniment${u.unclean === 1 ? 'o improvviso' : 'i improvvisi'}` : 'nessuno spegnimento improvviso'}</div></div>
    <div><div class="k">Ultimo spegnimento</div>${ls ? `<b class="${ls.clean ? '' : 'warnt'}">${ls.clean ? 'Regolare' : 'Improvviso'}</b><div class="s">${esc(when(ls.time))}${ls.clean ? '' : ' · mancanza di corrente o blocco'}</div>` : '<b>—</b><div class="s">primo avvio</div>'}</div>
  </div>`;
}

function pageError(e) {
  $('#root').innerHTML = shell(S.page, 'Errore', null, `<div class="card"><div class="empty">${ic('alert')}<div><b>Qualcosa non ha funzionato</b></div><div>${esc(e.message)}</div><button class="btn" data-retry>${ic('refresh')}Riprova</button></div></div>`);
  wireShell();
}

/* ==========================================================================
   Ricerca globale (Ctrl+K)
   ========================================================================== */

async function palette() {
  const m = modal(`<div class="pin">${ic('search')}<input id="pq" placeholder="Cerca app, pagine, impostazioni…" autocomplete="off"><kbd class="muted" style="font:11px var(--mono)">Esc</kbd></div><div class="res" id="pres"></div>`, 'palette');
  const pages = [...NAV.map(([id, i, t]) => ({ t, i, h: '#' + id })), { t: 'Le mie app', i: 'grid', h: '#apps' }, { t: 'Cerca su Docker Hub', i: 'container', h: '#hub' },
    { t: 'Fonti dell\'app store', i: 'link', h: '#settings/store' }, { t: 'Cambia password', i: 'key', fn: changePassword },
    { t: 'Informazioni e licenze', i: 'info', h: '#about' }, { t: 'Sostieni il progetto', i: 'heart', h: '#donate' }, { t: 'Cestino', i: 'trash', h: '#files/trash' },
    { t: 'Collega una cartella di rete', i: 'globe', h: '#files/net' }];
  let installed = [], catalog = [];
  api('GET', '/apps').then(r => { installed = r.apps; draw(); }).catch(() => {});
  api('GET', '/store/apps').then(r => { catalog = r.apps; draw(); }).catch(() => {});
  let sel = 0, items = [];
  function draw() {
    const q = $('#pq', m).value.trim().toLowerCase();
    const match = s => !q || s.toLowerCase().includes(q);
    const groups = [
      ['Pagine', pages.filter(p => match(p.t)).slice(0, 6).map(p => ({ html: `${ic(p.i)}${esc(p.t)}`, run: () => p.fn ? p.fn() : (location.hash = p.h) }))],
      ['Le tue app', installed.filter(a => match(a.title)).slice(0, 6).map(a => ({ html: `${appIcon(a)}${esc(a.title)}<span class="grow"></span>${stateBadge(a.state)}`, run: () => { const u = appUrl(a); if (u && a.state === 'attiva') open(u, '_blank', 'noopener'); else location.hash = 'apps'; } }))],
      ['App store', q ? catalog.filter(a => match(a.title)).slice(0, 8).map(a => ({ html: `${appIcon(a)}${esc(a.title)}<span class="muted" style="font-size:12px">${esc(a.category)}</span>`, run: () => { location.hash = 'store'; setTimeout(() => appDetail(a.id), 300); } })) : []],
    ];
    if (q.length >= 2) groups.push(['Docker Hub', [{ html: `${ic('container')}Cerca "${esc(q)}" su Docker Hub`, run: () => { store.set('hubq', q); location.hash = 'hub'; } }]]);
    items = [];
    $('#pres', m).innerHTML = groups.filter(g => g[1].length).map(([g, list]) => `<div class="g">${g}</div>` + list.map(it => { items.push(it); return `<a data-i="${items.length - 1}">${it.html}</a>`; }).join('')).join('') || '<div class="empty">Nessun risultato</div>';
    sel = Math.min(sel, items.length - 1);
    $$('#pres a', m).forEach(a => { a.classList.toggle('on', +a.dataset.i === sel); a.onclick = () => { closeModal(); items[+a.dataset.i].run(); }; });
  }
  $('#pq', m).oninput = () => { sel = 0; draw(); };
  $('#pq', m).onkeydown = e => {
    if (e.key === 'ArrowDown') { sel = Math.min(items.length - 1, sel + 1); draw(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    if (e.key === 'Enter' && items[sel]) { closeModal(); items[sel].run(); }
  };
  $('#pq', m).focus();
  draw();
}

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && S.user) { e.preventDefault(); palette(); }
  if (e.key === 'Escape') { if ($('.menu')) $$('.menu').forEach(m => m.remove()); else if ($('#scrim') && !$('#scrim').dataset.lock) closeModal(); }
});

/* ==========================================================================
   Navigazione
   ========================================================================== */

const ROUTES = {};   // riempito dagli altri file (store.js, files.js, pages.js)
ROUTES.home = pageHome;

async function render() {
  stopTimers();
  closeModal();
  $$('.menu,.sheet').forEach(m => m.remove());
  const [route, ...rest] = location.hash.slice(1).split('/');
  if (route === 'login') { if (S.user) location.hash = 'home'; else showLogin(); return; }
  if (!S.user) return showLogin();
  S.page = route || 'home';
  S.args = rest;
  const fn = ROUTES[S.page] || pageHome;
  if (!$('#root .app')) $('#root').innerHTML = '<div class="loading-page"><span class="spin lg"></span></div>';
  try { await fn(...rest); } catch (e) {
    console.error(e);
    // Un errore nella pagina non deve lasciare la rotellina: si mostra con "Riprova"
    pageError(e instanceof HttpError ? e : new Error('Errore nella pagina: ' + (e && e.message || e)));
  }
  window.scrollTo(0, 0);
}

async function boot() {
  applyTheme();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (store.get('theme', 'auto') === 'auto') $$('[data-theme-btn]').forEach(b => b.innerHTML = ic(isDark() ? 'sun' : 'moon')); });
  let st;
  await i18nInit(store.get('lang', 'it'));
  try { st = await api('GET', '/auth/state'); } catch (e) {
    $('#root').innerHTML = `<div class="login-wrap"><div class="card login-card"><div class="empty">${ic('alert')}<b>Il NAS non risponde</b><div>${esc(e.message)}</div><button class="btn" data-retry-boot>Riprova</button></div></div></div>`;
    return;
  }
  S.about = st.about || S.about;
  await i18nInit(S.about.lang || 'it');
  document.title = S.about.name || 'NAS';
  S.setup = st.setup;
  S.local = st.local_screen ? (st.addresses || []) : null;
  S.user = st.user;
  S.admin = st.admin;
  if (!S.user) return showLogin();
  if (!S.booted) { S.booted = true; addEventListener('hashchange', render); }
  await render();
  if (S.admin && typeof maybeWizard === 'function') maybeWizard();
}

// Icone delle app: quando l'immagine arriva si toglie la tessera, se non arriva resta la tessera
document.addEventListener('load', e => { if (e.target.tagName === 'IMG' && e.target.parentNode.classList.contains('appicon')) e.target.parentNode.classList.add('img-ok'); }, true);
document.addEventListener('error', e => { if (e.target.tagName === 'IMG' && e.target.parentNode && e.target.parentNode.classList.contains('appicon')) e.target.remove(); }, true);
document.addEventListener('click', e => {
  if (e.target.closest('[data-retry]')) render();
  if (e.target.closest('[data-retry-boot]')) boot();
});
document.addEventListener('DOMContentLoaded', boot);
