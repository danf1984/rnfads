// Interfaccia del NAS — Terminale nel browser (xterm.js, incluso nel sistema) e accesso SSH
// Licenza GPL-3.0. xterm.js: licenza MIT (vedi vendor/xterm/LICENSE-xterm.txt).
'use strict';

const TERM = { tabs: [], active: null, loaded: null, font: 14, seq: 0, ctrl: false, alt: false };
const TERM_THEME = {
  background: '#0d0e16', foreground: '#d7dae8', cursor: '#d7dae8', cursorAccent: '#0d0e16', selectionBackground: 'rgba(129,140,248,.35)',
  black: '#1c1e2b', red: '#f87171', green: '#4ade80', yellow: '#fbbf24', blue: '#818cf8', magenta: '#f472b6', cyan: '#67e8f9', white: '#d7dae8',
  brightBlack: '#5b6078', brightRed: '#fca5a5', brightGreen: '#86efac', brightYellow: '#fde68a', brightBlue: '#a5b4fc', brightMagenta: '#f9a8d4', brightCyan: '#a5f3fc', brightWhite: '#ffffff',
};

// xterm.js si carica solo quando serve (circa 290 KB)
function loadXterm() {
  if (TERM.loaded) return TERM.loaded;
  TERM.loaded = new Promise((res, rej) => {
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = '/static/vendor/xterm/xterm.css';
    document.head.appendChild(css);
    const add = src => new Promise((ok, ko) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = () => ko(new Error('Non riesco a caricare ' + src)); document.head.appendChild(s); });
    add('/static/vendor/xterm/xterm.js').then(() => add('/static/vendor/xterm/addon-fit.js')).then(res, rej);
  });
  return TERM.loaded;
}

async function pageTerm() {
  let t, ssh;
  try { [t, ssh] = await Promise.all([api('GET', '/term/targets'), api('GET', '/ssh')]); } catch (e) { return pageError(e); }
  TERM.targets = t.targets;
  $('#root').innerHTML = shell('term', 'Terminale', 'Nel browser, senza programmi da installare', `
    <div class="grid termgrid" style="grid-template-columns:minmax(0,1fr) 320px;align-items:start">
      <div class="term">
        <div class="tt"><div class="tabs" id="ttabs"></div><button class="tab add" id="tnew" title="Nuovo terminale">${ic('plus')}</button><span style="flex:1"></span>
          <button class="tab" id="tcopy" title="Copia la selezione">${ic('copy')}</button><button class="tab" id="tpaste" title="Incolla">${ic('file')}</button>
          <button class="tab" id="tminus" title="Testo più piccolo">A−</button><button class="tab" id="tplus" title="Testo più grande">A+</button></div>
        <div class="termhost" id="thost"><div class="termempty" id="tempty">${ic('term')}<div>Nessun terminale aperto</div><button class="btn sm primary" id="tfirst">${ic('plus')}Apri un terminale</button></div></div>
        <div class="kbdbar" id="kbd">${[['Esc', '\x1b'], ['Tab', '\t'], ['Ctrl', 'ctrl'], ['Alt', 'alt'], ['↑', '\x1b[A'], ['↓', '\x1b[B'], ['←', '\x1b[D'], ['→', '\x1b[C'], ['Ctrl+C', '\x03'], ['Ctrl+D', '\x04']].map(([l, k]) => `<button type="button" data-key="${esc(k)}">${l}</button>`).join('')}</div>
      </div>
      <div class="grid" id="sshcol"></div>
    </div>`);
  wireShell();
  $('#tnew').onclick = e => targetMenu(e.currentTarget);
  $('#tfirst').onclick = e => targetMenu(e.currentTarget);
  $('#tcopy').onclick = () => { const x = curTab(); if (x && x.term.hasSelection()) copyText(x.term.getSelection()); else toast('Seleziona prima del testo nel terminale', 'info'); };
  $('#tpaste').onclick = async () => {
    const x = curTab();
    if (!x) return;
    try { const txt = await navigator.clipboard.readText(); if (txt) x.term.paste(txt); x.term.focus(); }
    catch (e) { toast('Il browser non permette di leggere gli appunti: usa Ctrl+Maiusc+V nel terminale', 'info'); }
  };
  $('#tminus').onclick = () => setFont(-1);
  $('#tplus').onclick = () => setFont(1);
  $$('#kbd [data-key]').forEach(b => b.onclick = () => {
    const x = curTab();
    if (!x) return;
    const k = b.dataset.key;
    if (k === 'ctrl' || k === 'alt') { TERM[k] = !TERM[k]; b.classList.toggle('on', TERM[k]); x.term.focus(); return; }
    sendKeys(x, k);
    x.term.focus();
  });
  drawSsh(ssh);
  // Le schede restano aperte anche cambiando pagina: qui le rimetto al loro posto
  for (const x of TERM.tabs) $('#thost').appendChild(x.el);
  drawTabs();
  if (TERM.active) showTab(TERM.active);
  else if (!TERM.tabs.length) {
    const first = t.targets.find(x => x.id === 'user') || t.targets[0];
    if (first) openTab(first);
  }
  const ro = new ResizeObserver(() => fitActive());
  ro.observe($('#thost'));
  S.cleanup.push(() => { ro.disconnect(); for (const x of TERM.tabs) x.el.remove(); });
}

const curTab = () => TERM.tabs.find(x => x.id === TERM.active);

function targetMenu(btn) {
  const host = TERM.targets.filter(x => x.kind === 'host'), cont = TERM.targets.filter(x => x.kind === 'container');
  popmenu(btn, [
    ...host.map(x => ({ label: x.id === 'root' ? `Come root (${x.label})` : `Come ${x.label}`, icon: 'term', fn: () => openTab(x) })),
    ...(cont.length ? ['-', ...cont.slice(0, 20).map(x => ({ label: `Dentro ${x.label}`, icon: 'container', fn: () => openTab(x) }))] : [{ label: 'Nessuna app accesa', icon: 'container', disabled: true, fn: () => {} }]),
  ]);
}

function sendKeys(x, k) {
  if (TERM.ctrl && k.length === 1) { k = String.fromCharCode(k.toUpperCase().charCodeAt(0) & 31); }
  if (TERM.alt) k = '\x1b' + k;
  if (TERM.ctrl || TERM.alt) { TERM.ctrl = TERM.alt = false; $$('#kbd .on').forEach(b => b.classList.remove('on')); }
  if (x.ws && x.ws.readyState === 1) x.ws.send('0' + k);
}

async function openTab(target) {
  try { await loadXterm(); } catch (e) { return toast(e.message, 'bad'); }
  const id = 't' + (++TERM.seq);
  const el = document.createElement('div');
  el.className = 'termview';
  $('#thost').appendChild(el);
  const term = new window.Terminal({ fontFamily: "ui-monospace, 'JetBrains Mono', 'Cascadia Mono', Menlo, Consolas, monospace", fontSize: TERM.font,
    cursorBlink: true, theme: TERM_THEME, scrollback: 5000, allowProposedApi: false, macOptionIsMeta: true });
  const fit = new window.FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(el);
  const x = { id, target, term, fit, el, ws: null, title: target.label, state: 'connecting' };
  TERM.tabs.push(x);
  showTab(id);
  term.onData(d => {
    if (TERM.ctrl || TERM.alt) return sendKeys(x, d);
    if (x.ws && x.ws.readyState === 1) x.ws.send('0' + d);
    else if (x.state === 'closed' && d === '\r') reconnect(x);
  });
  term.onTitleChange(t => { x.title = t || target.label; drawTabs(); });
  term.onResize(sz => { if (x.ws && x.ws.readyState === 1) x.ws.send('1' + JSON.stringify(sz)); });
  // Ctrl+Maiusc+C / V come nei terminali di Linux
  term.attachCustomKeyEventHandler(ev => {
    if (ev.type === 'keydown' && ev.ctrlKey && ev.shiftKey && ev.code === 'KeyC') { if (term.hasSelection()) copyText(term.getSelection()); return false; }
    return true;
  });
  connect(x);
}

function connect(x) {
  x.fit.fit();
  const q = new URLSearchParams({ target: x.target.id, cols: x.term.cols, rows: x.term.rows });
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/term/ws?${q}`);
  ws.binaryType = 'arraybuffer';
  x.ws = ws;
  x.state = 'connecting';
  drawTabs();
  ws.onopen = () => { x.state = 'open'; drawTabs(); x.term.focus(); };
  ws.onmessage = ev => x.term.write(typeof ev.data === 'string' ? ev.data : new Uint8Array(ev.data));
  ws.onclose = ev => {
    if (x.ws !== ws) return;
    x.state = 'closed';
    drawTabs();
    x.term.write(`\r\n\x1b[90m— Sessione chiusa${ev.code === 1013 ? ': troppi terminali aperti' : ''}. Premi Invio per riaprirla. —\x1b[0m\r\n`);
  };
}

function reconnect(x) { x.term.reset(); connect(x); }

function closeTab(id) {
  const i = TERM.tabs.findIndex(x => x.id === id);
  if (i < 0) return;
  const x = TERM.tabs[i];
  try { x.ws && x.ws.close(); } catch (e) { /* già chiuso */ }
  x.term.dispose();
  x.el.remove();
  TERM.tabs.splice(i, 1);
  if (TERM.active === id) TERM.active = null;
  const next = TERM.tabs[Math.min(i, TERM.tabs.length - 1)];
  if (next) showTab(next.id); else drawTabs();
}

function showTab(id) {
  TERM.active = id;
  for (const x of TERM.tabs) x.el.hidden = x.id !== id;
  const e = $('#tempty');
  if (e) e.hidden = !!TERM.tabs.length;
  drawTabs();
  fitActive();
  const x = curTab();
  if (x) setTimeout(() => x.term.focus(), 30);
}

function fitActive() {
  const x = curTab();
  if (!x || !x.el.isConnected || x.el.hidden) return;
  try { x.fit.fit(); } catch (e) { /* elemento non visibile */ }
}

function setFont(d) {
  TERM.font = Math.max(10, Math.min(24, TERM.font + d));
  for (const x of TERM.tabs) x.term.options.fontSize = TERM.font;
  fitActive();
}

function drawTabs() {
  const box = $('#ttabs');
  if (!box) return;
  box.innerHTML = TERM.tabs.map(x => `<span class="tab ${x.id === TERM.active ? 'on' : ''}" data-tab="${x.id}" title="${esc(x.title)}">
    <span class="tdot ${x.state}"></span>${ic(x.target.kind === 'container' ? 'container' : 'term')}<span class="tl">${esc(x.target.kind === 'container' ? x.target.label : x.title)}</span>
    <button class="tx" data-tclose="${x.id}" title="Chiudi">${ic('x')}</button></span>`).join('');
  $$('[data-tab]', box).forEach(t => t.onclick = e => { if (e.target.closest('[data-tclose]')) closeTab(e.target.closest('[data-tclose]').dataset.tclose); else showTab(t.dataset.tab); });
  const e = $('#tempty');
  if (e) e.hidden = !!TERM.tabs.length;
}

/* --- Accesso SSH ------------------------------------------------------------------------------ */

function drawSsh(s) {
  const col = $('#sshcol');
  if (!col) return;
  const host = `${s.hostname}.local`;
  const keys = s.users.flatMap(u => u.keys.map(k => ({ ...k, user: u.name })));
  col.innerHTML = `
    <div class="card"><h3>${ic('key')}Accesso SSH</h3>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">Server SSH</div><div class="s mono">ssh ${esc((s.users[0] || {}).name || 'utente')}@${esc(host)}${s.port !== 22 ? ' -p ' + s.port : ''}</div></div><button class="toggle ${s.enabled || s.active ? 'on' : ''}" data-ssh="enabled"></button></div>
        <div class="item"><div class="grow"><div class="t">Accesso con password</div><div class="s">Disattivalo dopo aver aggiunto una chiave</div></div><button class="toggle ${s.password ? 'on' : ''}" data-ssh="password"></button></div>
        <div class="item"><div class="grow"><div class="t">Solo dalla rete di casa</div><div class="s">Blocca i collegamenti da internet</div></div><button class="toggle ${s.lan_only ? 'on' : ''}" data-ssh="lan_only"></button></div>
        <div class="item"><div class="grow"><div class="t">Porta</div><div class="s">22 è quella standard</div></div><input class="input sm" id="sshport" type="number" min="22" max="65535" value="${s.port}" style="width:90px"></div>
      </div>
      <div class="subtle" style="margin-top:8px">Entrano solo gli utenti amministratori del NAS, mai root.</div></div>
    <div class="card"><h3>${ic('key')}Chiavi autorizzate <a class="more" id="addkey">+ Aggiungi</a></h3>
      ${keys.length ? `<div class="list">${keys.map(k => `<div class="item"><div class="grow" style="min-width:0"><div class="t">${esc(k.comment || 'Chiave senza nome')}</div><div class="s mono" style="overflow:hidden;text-overflow:ellipsis">${esc(k.user)} · ${esc(k.type.toLowerCase())} · ${esc(k.fingerprint.slice(0, 22))}…</div></div>
        <button class="btn sm ghost" data-delkey="${esc(k.fingerprint)}" data-u="${esc(k.user)}" title="Togli">${ic('trash')}</button></div>`).join('')}</div>`
        : `<div class="subtle">${s.users.length ? 'Nessuna chiave. Con una chiave entri senza password, in modo più sicuro.' : 'Crea prima un utente amministratore nella pagina Utenti.'}</div>`}</div>`;
  $$('[data-ssh]', col).forEach(t => t.onclick = () => {
    const k = t.dataset.ssh, v = !t.classList.contains('on');
    act(null, () => api('POST', '/ssh', { [k]: v }), k === 'enabled' ? (v ? 'Server SSH acceso' : 'Server SSH spento') : 'Impostazione salvata').then(r => r && drawSsh(r));
  });
  $('#sshport', col).onchange = e => +e.target.value === s.port ? null : act(null, () => api('POST', '/ssh', { port: +e.target.value }), 'Porta cambiata').then(r => r ? drawSsh(r) : (e.target.value = s.port));
  $('#addkey', col).onclick = () => keyDialog(s);
  $$('[data-delkey]', col).forEach(b => b.onclick = async () => {
    if (await ask('Togliere la chiave?', 'Da quel dispositivo non si potrà più entrare con la chiave.', 'Togli', true))
      act(b, () => api('POST', '/ssh/keys/delete', { user: b.dataset.u, fingerprint: b.dataset.delkey }), 'Chiave tolta').then(r => r && api('GET', '/ssh').then(drawSsh));
  });
}

function keyDialog(s) {
  if (!s.users.length) return toast('Crea prima un utente amministratore nella pagina Utenti', 'info');
  const m = modal(`${mhead(`<div class="dicon">${ic('key')}</div>`, 'Aggiungi una chiave SSH', 'Contenuto del file .pub del tuo computer o telefono')}
    <div class="mb">
      <div class="cols2"><div class="field"><label>Utente</label><select class="input" id="ku">${s.users.map(u => `<option>${esc(u.name)}</option>`).join('')}</select></div>
        <div class="field"><label>Nome del dispositivo</label><input class="input" id="kn" placeholder="es. PC studio"></div></div>
      <div class="field"><label>Chiave pubblica</label><textarea class="input code" id="kk" style="min-height:110px" placeholder="ssh-ed25519 AAAA… nome@pc"></textarea>
        <span class="hint">Sul PC: <span class="mono">ssh-keygen -t ed25519</span>, poi copia il file <span class="mono">~/.ssh/id_ed25519.pub</span></span></div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="kok">Aggiungi</button></div>`);
  $('#kok', m).onclick = e => act(e.currentTarget, () => api('POST', '/ssh/keys', { user: $('#ku', m).value, name: $('#kn', m).value, key: $('#kk', m).value }), 'Chiave aggiunta')
    .then(r => { if (r) { closeModal(); api('GET', '/ssh').then(drawSsh); } });
}

ROUTES.term = pageTerm;
