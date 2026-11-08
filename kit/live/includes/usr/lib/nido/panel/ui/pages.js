// Interfaccia del NAS — Impostazioni, informazioni e licenze, donazioni
// Licenza GPL-3.0.
'use strict';

const SUBNAV = [
  ['account', 'users', 'Account'],
  ['store', 'bag', 'App store'],
  ['general', 'server', 'Generale'],
  ['https', 'lock', 'Accesso sicuro (HTTPS)'],
  ['network', 'lan', 'Rete'],
  ['screen', 'monitor', 'Schermo del NAS'],
  ['remote', 'globe', 'Accesso remoto'],
  ['cloud', 'cloud', 'Servizi cloud'],
  ['notify', 'bell', 'Notifiche'],
  ['updates', 'refresh', 'Aggiornamenti di sistema'],
  ['api', 'link', 'Home Assistant e API'],
  ['about', 'info', 'Informazioni e licenze'],
  ['donate', 'heart', 'Sostieni il progetto'],
];

function settingsShell(active, title, body) {
  const nav = SUBNAV.filter(([id]) => S.admin || ['account', 'about', 'donate'].includes(id)).map(([id, i, t, ext]) => ext ? `<a href="${ext}" target="_blank" rel="noopener" class="ext">${ic(i)}${t}</a>`
    : ext === null ? `<a data-later="${id}">${ic(i)}${t}<span class="badge" style="margin-left:auto">1B</span></a>`
      : `<a href="#${id === 'about' || id === 'donate' ? id : 'settings/' + id}" class="${active === id ? 'on' : ''}">${ic(i)}${t}</a>`).join('');
  $('#root').innerHTML = shell(active === 'donate' ? 'donate' : active === 'about' ? 'about' : 'settings', title, null,
    `<div class="settings"><div class="subnav">${nav}</div><div class="grid">${body}</div></div>`, { noSearch: true });
  wireShell();
  $$('[data-later]').forEach(a => a.onclick = () => toast('In arrivo con la fase 1B', 'info'));
}

async function pageSettings(sub = 'account') {
  if (!S.admin && sub !== 'account') { location.hash = 'settings'; return; }
  const subs = { store: settingsStore, general: settingsGeneral, https: settingsHttps, remote: settingsRemote, cloud: settingsCloud, network: settingsNetwork, screen: settingsScreen, notify: settingsNotify, updates: settingsUpdates, api: settingsApi };
  if (subs[sub]) return subs[sub]();
  settingsShell('account', 'Impostazioni', `
    <div class="card"><h3>${ic('users')}Il tuo account</h3>
      <div class="list">
        <div class="item"><div class="appicon sm" style="background:var(--brand);border-radius:50%">${esc((S.user || '?')[0].toUpperCase())}</div><div class="grow"><div class="t">${esc(S.user)}</div><div class="s">${S.admin ? 'Amministratore' : 'Utente'} dell'interfaccia</div></div>
          <button class="btn sm" id="cpw">${ic('key')}Cambia password</button><button class="btn sm" id="lo">${ic('logout')}Esci</button></div>
      </div>
      <div class="subtle" style="margin-top:10px">Gli account dell'interfaccia sono separati dagli utenti delle condivisioni (Samba). Una password dimenticata si reimposta via SSH con <span class="mono">sudo nido-ui-user ${esc(S.user)}</span>.</div>
    </div>
    <div class="card"><h3>${ic('shield')}Sicurezza dell'accesso</h3>
      <div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
        <div class="row">${ic('check')}Password salvate con scrypt, mai in chiaro</div>
        <div class="row">${ic('check')}Dopo 5 tentativi sbagliati l'accesso si blocca per un po'</div>
        <div class="row">${ic('check')}Sessione in un cookie protetto (HttpOnly, SameSite)</div>
        <div class="row">${ic(location.protocol === 'https:' ? 'check' : 'info')}${location.protocol === 'https:' ? 'Connessione cifrata (HTTPS)' : 'Connessione non cifrata: attiva l\'HTTPS in <a href="#settings/https">Accesso sicuro</a>'}</div>
        <div class="row muted">${ic('info')}Verifica in due passaggi: in arrivo</div>
      </div></div>
`);
  $('#cpw').onclick = changePassword;
  $('#lo').onclick = logout;
  if (S.admin) accountsCard();
}

// Account dell'interfaccia (solo amministratori): ruoli Amministratore e Utente
async function accountsCard() {
  let r;
  try { r = await api('GET', '/accounts'); } catch (e) { return; }
  const grid = $('.settings .grid');
  if (!grid) return;
  const old = $('#accts'); if (old) old.remove();
  const when = t => t ? new Date(t * 1000).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'mai';
  grid.insertAdjacentHTML('beforeend', `<div class="card" id="accts"><div class="row" style="margin-bottom:8px"><h3 style="margin:0">${ic('users')}Account dell'interfaccia</h3><span class="grow"></span><button class="btn sm primary" id="acnew">${ic('plus')}Nuovo account</button></div>
    <div class="list">${r.accounts.map(a => `<div class="item"><div class="appicon sm" style="background:${a.admin ? 'var(--brand)' : '#94a3b8'};border-radius:50%">${esc(a.name[0].toUpperCase())}</div>
      <div class="grow"><div class="t">${esc(a.name)}${a.name === r.me ? ' <span class="badge">sei tu</span>' : ''}</div><div class="s">${a.admin ? 'Amministratore' : 'Utente'} · ultimo accesso: ${esc(when(a.last_login))}</div></div>
      <select class="input sm" data-role="${esc(a.name)}" style="width:150px" ${a.name === r.me ? 'disabled' : ''}><option value="1" ${a.admin ? 'selected' : ''}>Amministratore</option><option value="0" ${a.admin ? '' : 'selected'}>Utente</option></select>
      <button class="btn sm ghost" data-pw="${esc(a.name)}" title="Nuova password">${ic('key')}</button>
      ${a.name === r.me ? '' : `<button class="btn sm ghost danger" data-del="${esc(a.name)}" title="Elimina">${ic('trash')}</button>`}</div>`).join('')}</div>
    <div class="subtle" style="margin-top:10px"><b>Amministratore</b>: tutto. <b>Utente</b>: Home, app e store in consultazione, il proprio account; niente file, dischi, impostazioni del sistema e installazioni.</div></div>`);
  $('#acnew').onclick = () => {
    const m = modal(`${mhead(`<div class="dicon">${ic('users')}</div>`, 'Nuovo account dell\'interfaccia')}
      <div class="mb"><div class="field"><label>Nome</label><input class="input" id="nan" autocomplete="off" placeholder="es. mario"></div>
        <div class="field"><label>Password (almeno 8 caratteri)</label><input class="input" type="password" id="nap" autocomplete="new-password"></div>
        <div class="field"><label>Ruolo</label><div class="seg" id="nar"><button data-r="0" class="on">Utente</button><button data-r="1">Amministratore</button></div></div></div>
      <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="nago">${ic('plus')}Crea</button></div>`, 'sm');
    let adm = false;
    $$('[data-r]', m).forEach(b => b.onclick = () => { adm = b.dataset.r === '1'; $$('[data-r]', m).forEach(x => x.classList.toggle('on', x === b)); });
    $('#nago', m).onclick = e => act(e.currentTarget, () => api('POST', '/accounts', { user: $('#nan', m).value.trim(), password: $('#nap', m).value, admin: adm }), 'Account creato').then(x => { if (x) { closeModal(); accountsCard(); } });
  };
  $$('[data-role]').forEach(sel => sel.onchange = () => act(null, () => api('POST', '/accounts/' + sel.dataset.role, { admin: sel.value === '1' }), 'Ruolo cambiato').then(x => accountsCard()));
  $$('[data-pw]').forEach(b => b.onclick = async () => {
    const pw = await prompt2(`Nuova password per ${b.dataset.pw}`, 'Password (almeno 8 caratteri)', '', 'Cambia');
    if (pw) act(null, () => api('POST', '/accounts/' + b.dataset.pw, { password: pw }), 'Password cambiata: le sessioni aperte di quell\'account sono state chiuse');
  });
  $$('[data-del]').forEach(b => b.onclick = async () => {
    if (await ask('Elimina account', `L'account <b>${esc(b.dataset.del)}</b> dell'interfaccia viene eliminato (gli utenti delle condivisioni non cambiano).`, 'Elimina', true))
      act(null, () => api('DELETE', '/accounts/' + b.dataset.del), 'Account eliminato').then(() => accountsCard());
  });
}

async function settingsStore() {
  let d;
  try { d = await api('GET', '/store/sources'); } catch (e) { return pageError(e); }
  const fmt = s => s.ok === false ? `<span class="err">Errore: ${esc(s.error || '')}</span>` : s.count != null ? `${nf(s.count)} app${s.updated ? ' · ' + new Date(s.updated).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}` : 'non ancora scaricata';
  settingsShell('store', 'Impostazioni', `
    <div class="card"><h3>${ic('bag')}Fonti delle app <span class="more">${d.built ? 'catalogo del ' + new Date(d.built).toLocaleString(LOCALE) : ''}</span></h3>
      <div>${d.sources.map(s => `<div class="srcrow"><span class="srcdot" style="background:${esc(s.color)};width:10px;height:10px"></span>
        <div style="min-width:0"><b>${esc(s.name)}</b>${s.optional ? ' <span class="badge">facoltativa</span>' : ''}${s.custom ? ' <span class="badge">aggiunta da te</span>' : ''}<div class="s">${s.enabled ? fmt(s) : 'spenta'}</div><div class="s mono">${esc(s.url)}</div></div>
        <span class="row" style="gap:4px">${s.enabled ? `<button class="btn sm ghost" data-one="${esc(s.id)}" title="Aggiorna ora questa fonte" ${d.building ? 'disabled' : ''}>${ic('refresh')}</button>` : ''}${s.custom ? `<button class="btn sm ghost danger" data-rm="${esc(s.id)}" title="Togli">${ic('trash')}</button>` : ''}</span>
        <button class="toggle ${s.enabled ? 'on' : ''}" data-tg="${esc(s.id)}" title="${s.enabled ? 'Spegni' : 'Accendi'}"></button></div>`).join('')}</div>
      <div class="row" style="margin-top:14px;flex-wrap:wrap"><button class="btn" id="addsrc2">${ic('plus')}Aggiungi fonte</button><button class="btn" id="rebuild" ${d.building ? 'disabled' : ''}>${ic('refresh')}${d.building ? 'Aggiornamento in corso…' : 'Aggiorna tutto'}</button></div>
      <div class="subtle" style="margin-top:10px">Un'app presente in più fonti compare una volta sola. Se una fonte non risponde resta valido il suo ultimo catalogo buono.</div>
    </div>
    <div class="card"><h3>${ic('clock')}Aggiornamento automatico delle fonti</h3>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">All'accensione</div><div class="s">Qualche minuto dopo l'avvio, quando la rete è pronta</div></div><button class="toggle ${d.schedule.boot ? 'on' : ''}" id="schboot"></button></div>
        <div class="item"><div class="grow"><div class="t">Poi ogni</div><div class="s">Aggiornamento automatico a intervalli</div></div>
          <select class="input sm" id="schev" style="width:170px">${[['6h', '6 ore'], ['12h', '12 ore'], ['24h', '24 ore'], ['weekly', 'settimana'], ['never', 'mai']].map(([v, t]) => `<option value="${v}" ${d.schedule.every === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      </div></div>
    ${d.log && d.log.length ? `<div class="card"><h3>${ic('term')}Registro dell'ultimo aggiornamento</h3><pre class="logbox">${esc(d.log.join('\n'))}</pre></div>` : ''}
    <div class="card"><h3>${ic('info')}Note</h3><div style="font-size:12.5px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
      <div>I cataloghi vengono scaricati dai siti dei loro autori. Puoi aggiungere altre fonti: zip di app in formato compose, come quelli di Big Bear.</div>
      ${S.about.stores_extra ? `<div>Le fonti ZimaOS e Unraid sono cataloghi di terzi convertiti in automatico nel formato delle app: alcune app potrebbero richiedere ritocchi dopo l'installazione.</div>
      <div>CasaOS e ZimaOS sono marchi di IceWhale Technology, Unraid di Lime Technology: ${esc(S.about.name)} è solo compatibile con il formato dei loro cataloghi e non è affiliato a loro.</div>` : ''}
      <div>${esc(S.about.name)} non è affiliato agli autori delle fonti né a quelli delle app.</div></div></div>`);
  $$('[data-tg]').forEach(b => b.onclick = () => act(b, () => api('POST', '/store/sources/' + b.dataset.tg, { enabled: !b.classList.contains('on') }), 'Fonte aggiornata: scarico il catalogo').then(r => r && settingsStore()));
  $$('[data-rm]').forEach(b => b.onclick = async () => { if (await ask('Togli fonte', 'Le app di questa fonte spariscono dal catalogo (quelle installate restano).', 'Togli', true)) act(b, () => api('DELETE', '/store/sources/' + b.dataset.rm), 'Fonte tolta').then(r => r && settingsStore()); });
  $('#addsrc2').onclick = addSourceDialog;
  $$('[data-one]').forEach(b => b.onclick = () => act(b, () => api('POST', '/store/refresh/' + b.dataset.one), 'Aggiorno la fonte').then(r => r && settingsStore()));
  const saveSch = () => act(null, () => api('POST', '/store/schedule', { boot: $('#schboot').classList.contains('on'), every: $('#schev').value }), 'Frequenza salvata');
  $('#schboot').onclick = e => { e.currentTarget.classList.toggle('on'); saveSch(); };
  $('#schev').onchange = saveSch;
  $('#rebuild').onclick = e => act(e.currentTarget, () => api('POST', '/store/refresh'), 'Aggiornamento del catalogo avviato').then(r => r && settingsStore());
  if (d.building) every('srcs', 4000, async () => { const x = await api('GET', '/store/sources').catch(() => null); if (x && !x.building) settingsStore(); });
  hubCard();
}

// Account Docker Hub (facoltativo): alza i limiti di download e di ricerca
async function hubCard(h) {
  if (!h) { try { h = await api('GET', '/registry/account'); } catch (e) { return; } }
  const grid = $('.settings .grid');
  if (!grid) return;
  const old = $('#hubacct'); if (old) old.remove();
  const lim = h.limits && h.limits.limit != null
    ? `Download rimasti: <b>${nf(h.limits.remaining)}</b> su ${nf(h.limits.limit)}${h.limits.window_hours ? ` ogni ${h.limits.window_hours} ore` : ''}`
    : 'Download rimasti: non ancora controllato';
  const when = h.checked ? ' · controllato il ' + new Date(h.checked * 1000).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
  const html = `<div class="card" id="hubacct"><h3>${ic('container')}Account Docker Hub</h3>
    ${h.configured ? `<div class="list"><div class="item"><div class="dicon">${ic('users')}</div><div class="grow"><div class="t">${esc(h.user)}</div>
        <div class="s">${h.docker_login ? 'Usato anche da Docker per scaricare le app' : 'Salvato (Docker non ha ancora fatto l\'accesso)'}</div></div>
        <button class="btn sm" id="hubchk">${ic('refresh')}Controlla</button><button class="btn sm danger" id="hubrm">${ic('logout')}Esci</button></div></div>
      <div class="subtle" style="margin-top:10px">${lim}${when}</div>`
    : `<div style="font-size:13px;color:var(--ink-2);line-height:1.5;margin-bottom:12px">Facoltativo. Senza account Docker Hub permette pochi download ogni 6 ore per indirizzo di casa; con il tuo account (anche gratuito) il limite sale. Usa un <b>token di accesso</b> creato su hub.docker.com → Account settings → Personal access tokens (permesso "Public Repo Read-only").</div>
      <div class="grid2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px">
        <div class="field"><label for="hubu">Nome utente</label><input class="input" id="hubu" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
        <div class="field"><label for="hubt">Token di accesso</label><input class="input mono" id="hubt" type="password" autocomplete="new-password"></div></div>
      <div class="row" style="margin-top:6px;flex-wrap:wrap"><button class="btn primary" id="hubsave">${ic('key')}Accedi e salva</button><button class="btn" id="hubchk">${ic('refresh')}Controlla i download rimasti</button></div>
      <div class="subtle" style="margin-top:10px">${lim}${when}</div>`}
    <div class="subtle" style="margin-top:8px">Il token è salvato cifrato sul NAS e non compare nei registri.</div></div>`;
  const note = [...$$('.settings .grid .card')].find(c => /Note/.test(($('h3', c) || {}).textContent || ''));
  if (note) note.insertAdjacentHTML('beforebegin', html); else grid.insertAdjacentHTML('beforeend', html);
  const chk = $('#hubchk');
  if (chk) chk.onclick = e => act(e.currentTarget, () => api('POST', '/registry/account/check'), 'Docker Hub controllato').then(r => r && hubCard(r));
  const rm = $('#hubrm');
  if (rm) rm.onclick = e => act(e.currentTarget, () => api('POST', '/registry/account/remove'), 'Account Docker Hub tolto').then(r => r && hubCard(r));
  const sv = $('#hubsave');
  if (sv) sv.onclick = e => {
    const user = $('#hubu').value.trim(), token = $('#hubt').value;
    if (!user || !token) { toast('Scrivi nome utente e token', 'bad'); return; }
    act(e.currentTarget, () => api('POST', '/registry/account', { user, token })).then(r => {
      if (!r) return;
      toast(r.warning || 'Account Docker Hub salvato', r.warning ? 'info' : 'ok', r.warning ? 8000 : 3000);
      hubCard(r);
    });
  };
}

async function pageAbout() {
  let n = { text: '', license: '' };
  try { n = await api('GET', '/about/notices'); } catch (e) { /* facoltativo */ }
  const a = S.about;
  const comp = [
    ['Ubuntu 26.04 LTS', 'Sistema di base · licenze dei singoli pacchetti (GPL, LGPL, MIT, BSD…)', 'Varie'],
    ['Linux', 'Kernel', 'GPL-2.0'],
    ['Docker Engine e Docker Compose', 'Motore delle app', 'Apache-2.0'],
    ['Samba · NFS · Avahi · davfs2', 'Condivisioni e cartelle di rete', 'GPL-3.0 · GPL-2.0 · LGPL-2.1'],
    ['Python · PyYAML · cryptography', 'Servizio dell\'interfaccia', 'PSF · MIT · Apache-2.0/BSD'],
    ['Caddy', 'HTTPS e certificati', 'Apache-2.0'],
    ['xterm.js', 'Terminale nel browser (incluso nell\'interfaccia)', 'MIT'],
    ['OpenSSH · smartmontools · hdparm', 'Accesso SSH, salute e standby dei dischi', 'BSD · GPL-2.0 · BSD'],
    ['restic · rclone', 'Backup e cloud', 'BSD-2-Clause · MIT'],
    ['Inter', 'Font dell\'interfaccia', 'SIL OFL 1.1'],
    ['Orbitron e JetBrains Mono', 'Font della scritta del marchio', 'SIL OFL 1.1'],
    ['shim · GRUB (firmati)', 'Avvio con Secure Boot, non modificati', 'BSD-2 · GPL-3.0'],
    ['Firmware e microcodice', 'Driver dell\'hardware', 'Licenze dei produttori'],
  ];
  settingsShell('about', 'Informazioni e licenze', `
    <div class="card"><div class="row" style="gap:16px;flex-wrap:wrap">${cube(56)}<div class="grow"><div class="word" style="font-size:26px">${word()}</div>
      <div class="muted" style="font-size:13px;margin-top:4px">Versione ${esc(a.version || '—')} · ${esc(a.base || 'basato su Ubuntu')} · progetto indipendente</div></div>
      ${a.project_url ? `<a class="btn sm" href="${esc(safeUrl(a.project_url))}" target="_blank" rel="noopener">${ic('external')}Sito del progetto</a>` : ''}</div></div>
    <div class="grid two-col" style="grid-template-columns:1.25fr 1fr;align-items:start">
      <div class="card"><h3>${ic('grid')}Software incluso</h3><div class="list">
        ${comp.map(([nn, d, l]) => `<div class="item" style="padding:9px 0"><div class="grow"><div class="t" style="font-weight:600">${nn}</div><div class="s">${d}</div></div><span class="badge">${l}</span></div>`).join('')}
      </div><div class="subtle" style="margin-top:8px">Elenco completo dei pacchetti con versioni e licenze nelle note legali qui sotto e in <span class="mono">/usr/share/doc/nido/</span>.</div></div>
      <div class="grid">
        <div class="card"><h3>${ic('code')}Il codice di ${esc(a.name)}</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
          <div>L'interfaccia e gli strumenti di ${esc(a.name)} sono software libero, distribuito con licenza <b>GNU GPL versione 3</b>: puoi usarlo, studiarlo, modificarlo e ridistribuirlo alle stesse condizioni.</div>
          <div>I programmi con licenza GPL e LGPL inclusi sono accompagnati dal loro codice sorgente, pubblicato insieme a ogni versione.</div></div></div>
        <div class="card"><h3>${ic('shield')}Marchi</h3><div style="font-size:12.5px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
          <div>Ubuntu e Canonical sono marchi di Canonical Ltd. ${esc(a.name)} è basato su Ubuntu ma non è un prodotto Canonical.</div>
          <div>Docker and the Docker logo are trademarks or registered trademarks of Docker, Inc. in the United States and/or other countries. Docker Hub è indicato solo per compatibilità.</div>
          <div>${a.stores_extra ? `CasaOS e ZimaOS sono marchi di IceWhale Technology, Unraid di Lime Technology: ${esc(a.name)} è solo compatibile con il formato dei loro cataloghi di app e non è affiliato a loro.` : `CasaOS è un marchio di IceWhale Technology: ${esc(a.name)} legge soltanto il formato pubblico dei cataloghi di app e non è affiliato a loro.`}</div>
          <div>Tailscale, ZeroTier e Runtipi sono marchi o progetti dei rispettivi proprietari, WireGuard è un marchio registrato di Jason A. Donenfeld: ${esc(a.name)} non è affiliato a loro.</div>
          <div>Caddy e xterm.js sono usati come componenti con le loro licenze (Apache-2.0 e MIT): ${esc(a.name)} non è affiliato ai loro progetti.</div>
          <div>Nomi e icone delle app appartengono ai rispettivi proprietari.</div></div></div>
      </div>
    </div>
    ${n.text ? `<div class="card"><h3>${ic('file')}Note legali</h3><pre class="licbox">${esc(n.text)}</pre></div>` : ''}
    ${n.license ? `<div class="card"><h3>${ic('file')}Licenza (GPL-3.0)</h3><pre class="licbox">${esc(n.license)}</pre></div>` : ''}`);
}

function pageDonate() {
  const d = S.about.donate || [];
  settingsShell('donate', 'Sostieni il progetto', `
    <div class="card donate-card">
      <div class="row" style="gap:16px"><div class="heart">${ic('heart')}</div><div><div style="font-size:18px;font-weight:700;letter-spacing:-.01em">${esc(S.about.name)} è gratuito e lo resterà</div>
        <div class="muted" style="font-size:13px">Nessuna pubblicità, nessun abbonamento, nessun dato inviato a nessuno.</div></div></div>
      <div class="dialog-text" style="font-size:13.5px;line-height:1.6">Se il tuo NAS ti è utile e vuoi aiutare lo sviluppo (tempo, prove su hardware vero, nuovi dischi per i test), puoi fare una donazione libera. Anche un caffè aiuta. Grazie!</div>
      ${d.length ? `<div class="donate-btns">${d.map(x => `<a class="btn ${x.label === 'PayPal' ? 'primary' : ''}" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${ic('heart')}${esc(x.label)}</a>`).join('')}</div>`
        : `<div class="alert info">${ic('info')}<div>I link per le donazioni non sono ancora impostati.${S.admin ? ' Chi costruisce la ISO li aggiunge in <span class="mono">config.env</span> (<span class="mono">NIDO_DONATE_PAYPAL</span>, <span class="mono">NIDO_DONATE_KOFI</span>, <span class="mono">NIDO_DONATE_GITHUB</span>, <span class="mono">NIDO_DONATE_LIBERAPAY</span>).' : ''}</div></div>`}
      <div class="subtle">Le donazioni sono facoltative e non sbloccano funzioni: tutto il NAS funziona allo stesso modo per tutti.</div>
    </div>
    <div class="card"><h3>${ic('users')}Altri modi per aiutare</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
      <div class="row">${ic('check')}Segnala i problemi che trovi e come riprodurli</div>
      <div class="row">${ic('check')}Racconta il progetto ad amici e sui social</div>
      <div class="row">${ic('check')}Traduci l'interfaccia o migliora i testi</div></div></div>`);
}

ROUTES.settings = pageSettings;
ROUTES.about = pageAbout;
ROUTES.donate = pageDonate;

/* ==========================================================================
   Procedura guidata al primo avvio
   ========================================================================== */

async function maybeWizard() {
  if (S.wizardShown) return;
  let w;
  try { w = await api('GET', '/wizard'); } catch (e) { return; }
  if (w.done) return;
  S.wizardShown = true;
  wizardDialog(w);
}

function wizardDialog(w) {
  let step = Math.min(w.step || 0, 5);
  const st = { hostname: w.hostname, timezone: w.timezone, share: !w.shares.includes('Condivisa'), security: w.security_updates !== false };
  const STEPS = ['Benvenuto', 'Nome e fuso orario', 'Dischi', 'Cartella condivisa', 'Sicurezza', 'Fatto'];
  const m = modal(`<div class="mh"><div class="dicon">${cube(30)}</div><div style="flex:1"><h2 id="wzt"></h2><div class="muted" style="font-size:13px" id="wzs"></div></div></div>
    <div class="wzdots" id="wzd"></div><div class="mb" id="wzb"></div>
    <div class="mf"><button class="btn ghost" id="wzskip">Salta la procedura</button><span class="grow"></span><button class="btn" id="wzback">Indietro</button><button class="btn primary" id="wznext">Avanti</button></div>`);
  m.parentNode.dataset.lock = '1';
  const save = body => api('POST', '/wizard', body);
  function draw() {
    $('#wzt', m).textContent = STEPS[step];
    $('#wzs', m).textContent = `Passo ${step + 1} di ${STEPS.length}`;
    $('#wzd', m).innerHTML = STEPS.map((_, i) => `<i class="${i === step ? 'on' : i < step ? 'ok' : ''}"></i>`).join('');
    $('#wzback', m).style.visibility = step ? 'visible' : 'hidden';
    $('#wznext', m).textContent = step === 5 ? 'Inizia a usare il NAS' : 'Avanti';
    const b = $('#wzb', m);
    if (step === 0) b.innerHTML = `<div class="dialog-text">Benvenuto in <b>${esc(S.about.name)}</b>! In pochi passi scegli il nome del NAS, prepari i dischi dei dati e una cartella condivisa. Puoi saltare e rifare tutto dopo da <b>Impostazioni → Generale</b>.</div>`;
    if (step === 1) {
      b.innerHTML = `<div class="field"><label>Nome del NAS in rete</label><div class="row" style="gap:6px"><input class="input mono" id="wzh" value="${esc(st.hostname)}" style="max-width:240px"><span class="muted mono">.local</span></div><span class="hint">Lettere minuscole, numeri e trattini. Lo apri da <span class="mono">https://&lt;nome&gt;.local</span>.</span></div>
        <div class="field"><label>Fuso orario</label><select class="input" id="wztz" style="max-width:320px">${w.timezones.map(z => `<option ${z === st.timezone ? 'selected' : ''}>${esc(z)}</option>`).join('')}</select></div>`;
    }
    if (step === 2) {
      const d = w.disks;
      b.innerHTML = d.length ? `<div class="dialog-text">Dischi dei dati trovati (il disco di sistema non si tocca):</div><div class="list">${d.map(x => `<div class="item"><div class="dicon" style="width:38px;height:38px">${ic('disk')}</div><div class="grow"><div class="t">${esc(x.name)}</div><div class="s">${bytes(x.size || 0)} · ${x.mounted ? 'pronto (montato)' : x.empty ? 'vuoto: va formattato' : x.formatted ? 'formattato, non montato' : 'da preparare'}</div></div></div>`).join('')}</div>
        <div class="row" style="margin-top:10px"><a class="btn sm" href="#disks" id="wzdisk">${ic('disk')}Apri Dischi</a><span class="subtle">Monta o formatta i dischi, poi torna qui da Impostazioni → Generale → Procedura guidata.</span></div>`
        : `<div class="dialog-text">Non ho trovato dischi oltre a quello di sistema. Puoi usare il NAS così (i dati vanno in /DATA) e aggiungere dischi quando vuoi da <b>Dischi</b>.</div>`;
      const dl = $('#wzdisk', m); if (dl) dl.onclick = () => { save({ step: 2 }); S.onModalClose = null; delete m.parentNode.dataset.lock; closeModal(); };
    }
    if (step === 3) b.innerHTML = `<label class="row" style="cursor:pointer;gap:10px"><button class="toggle ${st.share ? 'on' : ''}" id="wzsh"></button><div><b>Crea la cartella "Condivisa"</b><div class="subtle">In /DATA/Condivisa, visibile in rete da Windows, Mac e telefoni a tutti gli utenti (lettura e scrittura), con il cestino di rete.</div></div></label>
      ${w.shares.length ? `<div class="subtle" style="margin-top:10px">Condivisioni che esistono già: ${w.shares.map(esc).join(', ')}</div>` : ''}<div class="subtle" style="margin-top:10px">Gli utenti per accedere si creano in <b>Utenti</b>.</div>`;
    if (step === 4) b.innerHTML = `<label class="row" style="cursor:pointer;gap:10px"><button class="toggle ${st.security ? 'on' : ''}" id="wzsec"></button><div><b>Installa da solo gli aggiornamenti di sicurezza</b><div class="subtle">Di notte, con uno snapshot del sistema.</div></div></label>
      <div class="alert info" style="margin-top:12px">${ic('lock')}<div>Per la connessione protetta scarica il <b>certificato di casa</b> da <a href="#settings/https">Impostazioni → Accesso sicuro</a> e installalo sui tuoi dispositivi.</div></div>`;
    if (step === 5) b.innerHTML = `<div class="dialog-text">Tutto pronto. Da qui puoi installare app dallo <b>App store</b>, caricare file in <b>File</b> e impostare i <b>Backup</b>.</div>`;
    const sh = $('#wzsh', m); if (sh) sh.onclick = () => { st.share = !st.share; sh.classList.toggle('on', st.share); };
    const sc = $('#wzsec', m); if (sc) sc.onclick = () => { st.security = !st.security; sc.classList.toggle('on', st.security); };
  }
  $('#wzback', m).onclick = () => { step = Math.max(0, step - 1); draw(); };
  $('#wzskip', m).onclick = async () => { await save({ skip: true }).catch(() => null); S.onModalClose = null; delete m.parentNode.dataset.lock; closeModal(); toast('Procedura saltata: la trovi in Impostazioni → Generale', 'info'); };
  $('#wznext', m).onclick = async e => {
    const btn = e.currentTarget;
    let body = { step: step + 1 };
    if (step === 1) {
      st.hostname = $('#wzh', m).value.trim().toLowerCase(); st.timezone = $('#wztz', m).value;
      if (st.hostname !== w.hostname) body.hostname = st.hostname;
      if (st.timezone !== w.timezone) body.timezone = st.timezone;
    }
    if (step === 3 && st.share) body.share = true;
    if (step === 4) body.security_updates = st.security;
    if (step === 5) body = { done: true };
    const r = await act(btn, () => save(body));
    if (!r) return;
    w = { ...w, ...r };
    if (body.hostname) toast(`Nome cambiato: il NAS ora è ${body.hostname}.local (se l'indirizzo non risponde subito, aspetta qualche secondo)`, 'info', 8000);
    if (step === 5) { S.onModalClose = null; delete m.parentNode.dataset.lock; closeModal(); toast('Buon lavoro con il tuo NAS!'); return; }
    step++;
    draw();
  };
  draw();
}

async function wizardReopen() {
  const w = await act(null, () => api('POST', '/wizard', { reopen: true }));
  if (w) { S.wizardShown = true; wizardDialog(w); }
}


/* ==========================================================================
   Accesso remoto: Tailscale e ZeroTier (installati su richiesta dagli archivi dei produttori)
   ========================================================================== */
async function settingsRemote() {
  let d;
  try { d = await api('GET', '/remote'); } catch (e) { return pageError(e); }
  const ts = d.tailscale, zt = d.zerotier;
  const badge = (ok, on, off) => `<span class="badge ${ok ? 'ok' : ''}">${ok ? on : off}</span>`;
  const install = (what, name, note) => `<div class="s" style="margin:4px 0 12px;line-height:1.5">${note}</div>
    <button class="btn primary" data-install="${what}" ${d.installing ? 'disabled' : ''}>${ic('dl')}Installa ${name}</button>`;
  let tsBody;
  if (!ts.installed) tsBody = install('tailscale', 'Tailscale', 'Rete privata tra i tuoi dispositivi (PC, telefono, NAS) che funziona anche fuori casa, senza aprire porte sul router. Serve un account Tailscale gratuito.');
  else if (ts.state === 'Running') {
    tsBody = `<div class="list">
      <div class="item"><div class="grow"><div class="t">Collegato ${ts.tailnet ? 'alla rete ' + esc(ts.tailnet) : ''}</div>
        <div class="s"><span class="notr mono">${esc((ts.ips || []).join(' · '))}</span>${ts.dns ? ` · <span class="notr mono">${esc(ts.dns)}</span>` : ''} · ${nf(ts.peers || 0)} dispositivi online</div></div>${badge(true, 'attivo', '')}</div>
      <div class="item"><div class="grow"><div class="t">Rendi raggiungibile la rete di casa</div>
        <div class="s">${ts.lan ? `Dai tuoi dispositivi Tailscale raggiungi anche la rete <span class="notr mono">${esc(ts.lan)}</span> (stampante, router…). Va approvato una volta nella console di Tailscale.` : 'Rete di casa non trovata'}</div></div>
        <button class="toggle ${(ts.advertised || []).length ? 'on' : ''}" id="tsroutes" ${ts.lan ? '' : 'disabled'}></button></div></div>
      <div class="subtle" style="margin-top:10px">Dagli altri dispositivi apri <span class="notr mono">https://${esc((ts.ips || [''])[0])}</span>${ts.dns ? ` oppure <span class="notr mono">http://${esc(ts.dns.split('.')[0])}</span>` : ''}.</div>
      <div class="row" style="margin-top:12px;flex-wrap:wrap"><button class="btn" id="tsoff">${ic('logout')}Scollega</button><button class="btn danger" data-uninstall="tailscale">${ic('trash')}Disinstalla</button></div>`;
  } else {
    tsBody = `<div class="s" style="margin-bottom:12px;line-height:1.5">${ts.auth_url ? 'Apri il link qui sotto, accedi con il tuo account Tailscale e approva il NAS. Questa pagina si aggiorna da sola.' : 'Il NAS non è collegato a nessuna rete Tailscale.'}</div>
      ${ts.auth_url ? `<a class="btn primary" href="${esc(safeUrl(ts.auth_url))}" target="_blank" rel="noopener">${ic('external')}Accedi a Tailscale</a>` : `<button class="btn primary" id="tson">${ic('link')}Collega a Tailscale</button>`}
      <button class="btn danger" data-uninstall="tailscale" style="margin-left:6px">${ic('trash')}Disinstalla</button>`;
  }
  let ztBody;
  if (!zt.installed) ztBody = install('zerotier', 'ZeroTier', 'Rete virtuale tra i tuoi dispositivi: crei una rete gratuita su my.zerotier.com e ci fai entrare il NAS con il suo ID.');
  else {
    const st = s => ({ OK: badge(true, 'collegato', ''), ACCESS_DENIED: '<span class="badge warn">da autorizzare</span>', REQUESTING_CONFIGURATION: '<span class="badge">in attesa</span>', NOT_FOUND: '<span class="badge warn">rete non trovata</span>' }[s] || `<span class="badge">${esc(s || '')}</span>`);
    ztBody = `<div class="s" style="margin-bottom:10px">Indirizzo del NAS: <span class="notr mono">${esc(zt.address || '—')}</span> · ${zt.online ? 'online' : 'non in linea'}</div>
      <div class="list">${(zt.networks || []).map(n => `<div class="item"><div class="grow"><div class="t"><span class="notr">${esc(n.name || n.id)}</span></div>
          <div class="s"><span class="notr mono">${esc(n.id)}</span>${(n.ips || []).length ? ` · <span class="notr mono">${esc(n.ips.join(' · '))}</span>` : ''}</div>
          ${n.status === 'ACCESS_DENIED' ? '<div class="s">Autorizza il NAS nella pagina della rete su my.zerotier.com (spunta "Auth").</div>' : ''}</div>
          ${st(n.status)}<button class="btn sm ghost danger" data-leave="${esc(n.id)}" title="Esci dalla rete">${ic('logout')}</button></div>`).join('') || '<div class="subtle">Il NAS non è in nessuna rete ZeroTier.</div>'}</div>
      <div class="row" style="margin-top:12px;flex-wrap:wrap"><input class="input mono" id="ztnet" placeholder="ID della rete (16 caratteri)" maxlength="16" style="max-width:240px"><button class="btn primary" id="ztjoin">${ic('plus')}Entra nella rete</button>
        <button class="btn danger" data-uninstall="zerotier">${ic('trash')}Disinstalla</button></div>`;
  }
  settingsShell('remote', 'Impostazioni', `
    <div class="card"><h3>${ic('globe')}Tailscale</h3>${tsBody}</div>
    <div class="card"><h3>${ic('globe')}ZeroTier</h3>${ztBody}</div>
    ${d.installing || d.log ? `<div class="card"><h3>${ic('term')}Registro dell'installazione</h3><pre class="logbox">${esc(d.log || '…')}</pre></div>` : ''}
    <div class="card"><h3>${ic('info')}Note</h3><div style="font-size:12.5px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
      <div>Tailscale e ZeroTier non sono inclusi nel sistema: vengono installati dagli archivi ufficiali dei produttori quando premi "Installa", e i loro servizi online hanno le loro condizioni d'uso.</div>
      <div>L'accesso SSH "solo dalla rete di casa" accetta anche gli indirizzi di Tailscale e delle reti private di ZeroTier.</div>
      <div>Tailscale e ZeroTier sono marchi dei rispettivi proprietari: ${esc(S.about.name)} non è affiliato a loro. WireGuard è un marchio registrato di Jason A. Donenfeld.</div></div></div>`);
  $$('[data-install]').forEach(b => b.onclick = () => act(b, () => api('POST', `/remote/${b.dataset.install}/install`), 'Installazione avviata').then(r => r && settingsRemote()));
  $$('[data-uninstall]').forEach(b => b.onclick = async () => {
    const name = b.dataset.uninstall === 'tailscale' ? 'Tailscale' : 'ZeroTier';
    if (await ask('Disinstallare ' + name + '?', 'Il NAS esce dalla rete e non sarà più raggiungibile da fuori casa in questo modo.', 'Disinstalla', true))
      act(b, () => api('POST', `/remote/${b.dataset.uninstall}/uninstall`), name + ' disinstallato').then(r => r && settingsRemote());
  });
  const on = $('#tson'); if (on) on.onclick = () => act(on, () => api('POST', '/remote/tailscale/connect')).then(r => r && settingsRemote());
  const off = $('#tsoff'); if (off) off.onclick = () => act(off, () => api('POST', '/remote/tailscale/disconnect'), 'Tailscale scollegato').then(r => r && settingsRemote());
  const rt = $('#tsroutes'); if (rt) rt.onclick = () => act(rt, () => api('POST', '/remote/tailscale/routes', { enabled: !rt.classList.contains('on') }), 'Impostazione salvata').then(r => r && settingsRemote());
  const jn = $('#ztjoin'); if (jn) jn.onclick = () => act(jn, () => api('POST', '/remote/zerotier/join', { network: $('#ztnet').value }), 'Richiesta inviata: autorizza il NAS su my.zerotier.com').then(r => r && settingsRemote());
  $$('[data-leave]').forEach(b => b.onclick = () => act(b, () => api('POST', '/remote/zerotier/leave', { network: b.dataset.leave }), 'Uscito dalla rete').then(r => r && settingsRemote()));
  // Aggiornamento automatico mentre si installa o si aspetta l'accesso a Tailscale
  if (d.installing || (ts.installed && ts.state !== 'Running' && ts.auth_url) || (zt.networks || []).some(n => n.status !== 'OK'))
    every('remote', 4000, async () => { if (S.page !== 'settings' || !$('#tsroutes, #tson, [data-install], #ztjoin, #tsoff')) return clearInterval(S.timers.remote);
      const x = await api('GET', '/remote').catch(() => null);
      if (x && JSON.stringify([x.installing, x.tailscale.state, x.tailscale.auth_url, (x.zerotier.networks || []).map(n => n.status), x.log]) !== JSON.stringify([d.installing, ts.state, ts.auth_url, (zt.networks || []).map(n => n.status), d.log])) settingsRemote(); });
}


/* --- Servizi cloud (rclone): Google Drive, OneDrive, Dropbox, MEGA, WebDAV, S3… -------------------------- */

async function settingsCloud() {
  let d;
  try { d = await api('GET', '/cloud'); } catch (e) { return pageError(e); }
  const rows = d.remotes.map(r => `<div class="item"><div class="dicon" style="width:40px;height:40px;background:color-mix(in srgb,${esc(r.color)} 14%,transparent);color:${esc(r.color)}">${ic('cloud')}</div>
      <div class="grow"><div class="t"><span class="notr">${esc(r.name)}</span> <span class="badge">${esc(r.provider)}</span>${r.mounted ? ' <span class="badge ok">nei File</span>' : ''}</div>
        <div class="s" data-space="${esc(r.name)}">${r.mounted ? `Cartella <span class="notr mono">${esc(r.mountpoint)}</span>${r.autoboot ? ' · ricollegata all\'avvio' : ''}` : 'Disponibile per i backup'}</div></div>
      <button class="btn sm ghost" data-ctest="${esc(r.name)}" title="Prova e spazio">${ic('refresh')}Prova</button>
      <label class="row subtle" style="gap:6px;font-size:12.5px;cursor:pointer" title="Mostra il servizio come cartella in File (anche per le app)">Nei File<button class="toggle ${r.mounted ? 'on' : ''}" data-cmount="${esc(r.name)}"></button></label>
      <button class="btn sm ghost danger" data-cdel="${esc(r.name)}" title="Rimuovi">${ic('trash')}</button></div>`).join('');
  settingsShell('cloud', 'Impostazioni', `
    <div class="card"><h3>${ic('cloud')}Servizi cloud collegati</h3>
      ${!d.available ? '<div class="alert bad">' + ic('alert') + '<div>rclone non è installato.</div></div>' : d.error ? `<div class="alert bad">${ic('alert')}<div>${esc(d.error)}</div></div>` : ''}
      <div class="list">${rows || '<div class="subtle">Nessun servizio collegato.</div>'}</div>
      <div class="row" style="margin-top:12px"><button class="btn primary" id="cadd" ${d.available ? '' : 'disabled'}>${ic('plus')}Collega un servizio</button></div></div>
    <div class="card"><h3>${ic('info')}Come si usano</h3><div style="font-size:12.5px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
      <div>Nei File: il servizio diventa una cartella in /media/cloud, visibile nella barra di File (sezione Rete), nelle condivisioni e nelle app.</div>
      <div>Backup: in Backup → Nuovo backup scegli "Cloud" e il servizio: i dati vanno nel cloud cifrati con restic.</div>
      <div>Le credenziali restano sul NAS, nel file di configurazione di rclone (solo amministratore). Google Drive, OneDrive, Dropbox e Box si collegano dal browser con il tuo account: il NAS non vede la tua password.</div>
      <div>Google Drive, OneDrive, Dropbox, Box, MEGA, Backblaze e gli altri sono marchi dei rispettivi proprietari: ${esc(S.about.name)} non è affiliato a loro. Il collegamento usa rclone (licenza MIT).</div></div></div>`);
  const add = $('#cadd'); if (add) add.onclick = () => cloudDialog(d.providers);
  $$('[data-ctest]').forEach(b => b.onclick = async () => {
    const x = await act(b, () => api('POST', `/cloud/remotes/${b.dataset.ctest}/test`, {}, { timeout: 180000 }));
    if (!x) return;
    const s = $(`[data-space="${CSS.escape(b.dataset.ctest)}"]`);
    if (!x.ok) return toast(x.error, 'bad', 8000);
    const sp = x.space || {};
    const txt = sp.total ? `Spazio: ${bytes(sp.used || 0)} usati di ${bytes(sp.total)} (liberi ${bytes(sp.free || 0)})` : `Collegato · ${nf(x.folders || 0)} cartelle nella radice`;
    if (s) s.textContent = txt;
    toast('Collegamento riuscito', 'ok');
  });
  $$('[data-cmount]').forEach(b => b.onclick = () => {
    const on = !b.classList.contains('on');
    act(b, () => api('POST', `/cloud/remotes/${b.dataset.cmount}/mount`, { enabled: on, autoboot: true }, { timeout: 180000 }),
      on ? 'Cartella collegata: la trovi in File' : 'Cartella scollegata').then(r => r && settingsCloud());
  });
  $$('[data-cdel]').forEach(b => b.onclick = async () => {
    if (!await ask('Rimuovi servizio', `"${esc(b.dataset.cdel)}" viene scollegato e dimenticato dal NAS (anche le credenziali). I file nel cloud non vengono toccati. I backup che lo usano smettono di funzionare.`, 'Rimuovi', true)) return;
    act(b, () => api('DELETE', `/cloud/remotes/${b.dataset.cdel}`), 'Servizio rimosso').then(r => r && settingsCloud());
  });
}

function cloudDialog(providers) {
  const ids = Object.keys(providers);
  const m = modal(`${mhead(`<div class="dicon">${ic('cloud')}</div>`, 'Collega un servizio cloud', 'Scegli il servizio')}
    <div class="mb"><div class="cloudgrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px">
      ${ids.map(t => `<button class="btn" data-ct="${t}" style="justify-content:flex-start;height:auto;padding:10px 12px;text-align:left"><span style="width:10px;height:10px;border-radius:50%;background:${esc(providers[t].color)};flex:none"></span><span class="notr">${esc(providers[t].name)}</span></button>`).join('')}
    </div></div>
    <div class="mf"><button class="btn" data-close>Annulla</button></div>`);
  $$('[data-ct]', m).forEach(b => b.onclick = () => { closeModal(); cloudForm(b.dataset.ct, providers[b.dataset.ct]); });
}

function cloudForm(type, p) {
  const defName = type === 'drive' ? 'gdrive' : type.replace(/[^a-z0-9]/g, '');
  const field = f => {
    const [k, label, kind, req, def, choices] = f;
    const inp = kind === 'select'
      ? `<select class="input" data-cf="${k}">${choices.map(([v, t]) => `<option value="${esc(v)}" ${v === def ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`
      : `<input class="input ${kind === 'password' ? '' : 'mono'}" data-cf="${k}" type="${kind === 'password' ? 'password' : 'text'}" value="${esc(def || '')}" autocomplete="off" spellcheck="false">`;
    return `<div class="field"><label>${esc(label)}</label>${req ? '' : '<span class="hint">facoltativo</span>'}${inp}</div>`;
  };
  const oauthBody = `<div class="s" style="line-height:1.6;margin-bottom:10px;display:grid;gap:4px">
      <div>1. Premi "Apri la pagina di accesso" e accedi con il tuo account ${esc(p.name)} nella scheda che si apre.</div>
      <div>2. Alla fine il browser va su una pagina che non si apre (l'indirizzo inizia con http://127.0.0.1:53682 o http://localhost:53682): è normale.</div>
      <div>3. Copia tutto l'indirizzo dalla barra del browser e incollalo qui sotto.</div></div>
    <button class="btn primary" id="coopen">${ic('external')}Apri la pagina di accesso</button>
    <div class="field" style="margin-top:12px"><label>Indirizzo copiato dalla barra del browser</label><input class="input mono" id="courl" placeholder="http://127.0.0.1:53682/?state=…&code=…" autocomplete="off" spellcheck="false" disabled></div>`;
  const m = modal(`${mhead(`<div class="dicon">${ic('cloud')}</div>`, `Collega ${esc(p.name)}`, p.oauth ? 'Accesso con il tuo account, dal browser' : 'Dati di accesso')}
    <div class="mb">
      <div class="field"><label>Nome sul NAS</label><input class="input mono" id="cname" value="${esc(defName)}" maxlength="31" autocomplete="off" spellcheck="false"><span class="hint">Lettere, numeri, - e _. Sarà la cartella /media/cloud/&lt;nome&gt;.</span></div>
      ${p.oauth ? oauthBody : p.fields.map(field).join('')}
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="cok" ${p.oauth ? 'disabled' : ''}>${ic('link')}Collega</button></div>`);
  const ok = $('#cok', m);
  if (p.oauth) {
    const url = $('#courl', m);
    $('#coopen', m).onclick = async e => {
      // la scheda si apre subito (i browser bloccano le finestre aperte dopo un'attesa), poi riceve l'indirizzo
      const w = window.open('about:blank', '_blank');
      const x = await act(e.currentTarget, () => api('POST', '/cloud/oauth/start', { type }, { timeout: 60000 }));
      if (!x) { if (w) w.close(); return; }
      if (w) w.location = x.url; else toast('Il browser ha bloccato la nuova scheda: consenti i popup per questa pagina', 'bad', 8000);
      url.disabled = false; ok.disabled = false; url.focus();
    };
    ok.onclick = async () => {
      const x = await act(ok, () => api('POST', '/cloud/oauth/finish', { name: $('#cname', m).value.trim(), url: url.value.trim() }, { timeout: 180000 }));
      if (!x) return;
      closeModal(); toast(x.ok ? `${p.name} collegato` : `${p.name} collegato, ma la prova non è riuscita: ${x.error}`, x.ok ? 'ok' : 'bad', 8000); settingsCloud();
    };
  } else {
    ok.onclick = async () => {
      const fields = {};
      $$('[data-cf]', m).forEach(i => { fields[i.dataset.cf] = i.value; });
      const x = await act(ok, () => api('POST', '/cloud/remotes', { type, name: $('#cname', m).value.trim(), fields }, { timeout: 180000 }));
      if (!x) return;
      closeModal(); toast(`${p.name} collegato`, 'ok'); settingsCloud();
    };
  }
}


/* --- Rete (NetworkManager): indirizzo automatico o fisso, DNS, Wi-Fi, con ritorno automatico ------------ */

let netTimer = null;
async function settingsNetwork() {
  clearInterval(netTimer);
  let d;
  try { d = await api('GET', '/network'); } catch (e) { return pageError(e); }
  if (!d.available) return settingsShell('network', 'Impostazioni', `<div class="card"><h3>${ic('lan')}Rete</h3><div class="subtle">NetworkManager non è disponibile su questo sistema.</div></div>`);
  const pend = d.pending ? `<div class="card" style="border-color:var(--warn)"><h3>${ic('alert')}Conferma le impostazioni di rete</h3>
      <div class="s" style="line-height:1.6">Se il NAS si raggiunge, premi Conferma. Altrimenti tornano da sole le impostazioni di prima.</div>
      <div class="s" style="margin-top:4px">Tempo rimasto: <b id="netleft" class="notr">${d.pending.seconds}</b> s</div>
      <div class="row" style="margin-top:10px;gap:8px"><button class="btn primary" id="netok">${ic('check')}Conferma</button><button class="btn" id="netback">${ic('undo')}Torna come prima</button></div></div>` : '';
  const devs = d.devices.map(x => {
    const auto = (x.method || 'auto') === 'auto';
    return `<div class="card"><h3>${ic(x.type === 'wifi' ? 'globe' : 'lan')}${x.type === 'wifi' ? 'Wi-Fi' : 'Rete cablata'} <span class="notr mono subtle" style="font-weight:500;font-size:12.5px">${esc(x.device)}</span>
        <span class="badge ${x.connected ? 'ok' : ''}" style="margin-left:auto">${x.connected ? 'collegata' : 'non collegata'}</span></h3>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">Indirizzo attuale</div><div class="s"><span class="notr mono">${esc(x.addresses.join(' · ') || '—')}</span></div></div></div>
        <div class="item"><div class="grow"><div class="t">Gateway e DNS</div><div class="s"><span class="notr mono">${esc(x.gateway || '—')}</span> · DNS <span class="notr mono">${esc(x.dns.join(', ') || '—')}</span></div></div></div>
        <div class="item"><div class="grow"><div class="t">Scheda</div><div class="s"><span class="notr mono">${esc(x.mac || '')}</span>${x.connection ? ` · <span class="notr">${esc(x.connection)}</span>` : ''}</div></div></div>
      </div>
      ${x.uuid ? `<div class="seg" data-netm="${esc(x.device)}" style="margin-top:12px"><button type="button" data-v="auto" class="${auto ? 'on' : ''}">Automatico (DHCP)</button><button type="button" data-v="manual" class="${auto ? '' : 'on'}">Indirizzo fisso</button></div>
      <div data-netf="${esc(x.device)}" style="margin-top:10px;display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(200px,1fr))">
        <div class="field" data-man><label>Indirizzo / prefisso</label><input class="input mono" data-k="address" value="${esc(x.set_addresses[0] || x.addresses[0] || '')}" placeholder="192.168.1.50/24"></div>
        <div class="field" data-man><label>Gateway (router)</label><input class="input mono" data-k="gateway" value="${esc(x.set_gateway || x.gateway || '')}" placeholder="192.168.1.1"></div>
        <div class="field"><label>DNS (separati da virgola)</label><input class="input mono" data-k="dns" value="${esc((x.set_dns || []).join(', '))}" placeholder="${auto ? 'quelli del router' : '192.168.1.1'}"></div>
      </div>
      <div class="row" style="margin-top:10px"><button class="btn primary" data-netapply="${esc(x.device)}" ${d.pending ? 'disabled' : ''}>${ic('check')}Applica</button>
        <span class="subtle" style="font-size:12.5px">Dopo la modifica hai 3 minuti per confermare, altrimenti torna tutto come prima.</span></div>` : '<div class="subtle" style="margin-top:8px">Nessuna connessione attiva su questa scheda.</div>'}
      ${x.type === 'wifi' ? `<div class="row" style="margin-top:12px;gap:8px"><button class="btn" data-wifiscan>${ic('search')}Cerca reti Wi-Fi</button><button class="btn ghost" data-wifihidden>${ic('plus')}Rete nascosta…</button>${x.uuid && x.connection ? `<button class="btn ghost danger" data-wififorget="${esc(x.uuid)}">${ic('trash')}Dimentica questa rete</button>` : ''}</div><div class="list" id="wifilist" style="margin-top:8px"></div>` : ''}
    </div>`;
  }).join('');
  settingsShell('network', 'Impostazioni', `${pend}${devs || `<div class="card"><div class="subtle">Nessuna scheda di rete trovata.</div></div>`}
    <div class="card"><h3>${ic('info')}Note</h3><div style="font-size:12.5px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
      <div>Con l'indirizzo fisso scegli un indirizzo fuori dall'intervallo DHCP del router (o prenotalo nel router).</div>
      <div>Se cambi l'indirizzo, apri il NAS al nuovo indirizzo e conferma da questa pagina. Dallo schermo del NAS la pagina resta sempre raggiungibile.</div>
      <div>Il nome del NAS in rete si cambia in Impostazioni → Generale.</div></div></div>`);
  if (d.pending) {
    let left = d.pending.seconds;
    netTimer = setInterval(() => { left--; const e = $('#netleft'); if (!e) return clearInterval(netTimer); e.textContent = Math.max(0, left); if (left <= 0) { clearInterval(netTimer); setTimeout(settingsNetwork, 4000); } }, 1000);
    $('#netok').onclick = e => act(e.currentTarget, () => api('POST', '/network/confirm'), 'Impostazioni di rete confermate').then(r => r && settingsNetwork());
    $('#netback').onclick = e => act(e.currentTarget, () => api('POST', '/network/rollback'), 'Impostazioni di prima rimesse').then(() => setTimeout(settingsNetwork, 4000));
  }
  $$('[data-netm]').forEach(seg => {
    const f = $(`[data-netf="${CSS.escape(seg.dataset.netm)}"]`);
    const upd = () => { const man = $('button.on', seg).dataset.v === 'manual'; $$('[data-man]', f).forEach(x => { x.hidden = !man; }); };
    $$('button', seg).forEach(b => b.onclick = () => { $$('button', seg).forEach(x => x.classList.toggle('on', x === b)); upd(); });
    upd();
  });
  $$('[data-netapply]').forEach(b => b.onclick = async () => {
    const dev = b.dataset.netapply, f = $(`[data-netf="${CSS.escape(dev)}"]`);
    const method = $(`[data-netm="${CSS.escape(dev)}"] button.on`).dataset.v;
    const v = k => $(`[data-k="${k}"]`, f).value.trim();
    const body = { device: dev, method, dns: v('dns').split(/[\s,;]+/).filter(Boolean) };
    if (method === 'manual') { body.address = v('address'); body.gateway = v('gateway'); if (body.address && !body.address.includes('/')) body.address += '/24'; }
    if (!await ask('Applica le impostazioni di rete', method === 'manual'
      ? `Il NAS passa all'indirizzo ${esc(body.address.split('/')[0])}. Se lo stai usando da un altro indirizzo la pagina smette di rispondere: apri http://${esc(body.address.split('/')[0])} e conferma entro 3 minuti, altrimenti torna tutto come prima.`
      : 'Il NAS chiede l\'indirizzo al router (DHCP). Potrebbe cambiare indirizzo: se la pagina smette di rispondere cercalo nel router o usa il nome .local, e conferma entro 3 minuti.', 'Applica')) return;
    const r = await act(b, () => api('POST', '/network/apply', body));
    if (!r) return;
    toast('Impostazioni applicate: conferma entro 3 minuti', 'info', 8000);
    setTimeout(settingsNetwork, 4000);
  });
  const ws = $('[data-wifiscan]');
  if (ws) ws.onclick = async () => {
    const r = await act(ws, () => api('GET', '/network/wifi', undefined, { timeout: 60000 }));
    if (!r) return;
    const box = $('#wifilist');
    box.innerHTML = r.networks.map((n, i) => `<div class="item"><div class="grow"><div class="t"><span class="notr">${esc(n.ssid)}</span>${n.active ? ' <span class="badge ok">in uso</span>' : ''}</div><div class="s">Segnale ${n.signal}%${n.secure ? ' · protetta' : ' · aperta'}</div></div>${n.active ? '' : `<button class="btn sm" data-wifi="${i}">${ic('link')}Collega</button>`}</div>`).join('') || '<div class="subtle">Nessuna rete trovata.</div>';
    $$('[data-wifi]', box).forEach(b => b.onclick = async () => {
      const n = r.networks[+b.dataset.wifi];
      let password = '';
      if (n.secure) { password = await prompt2('Password del Wi-Fi', n.ssid, '', 'Collega'); if (password === null) return; }
      act(b, () => api('POST', '/network/wifi', { ssid: n.ssid, password }, { timeout: 90000 }), 'Wi-Fi collegato').then(x => x && settingsNetwork());
    });
  };
  const wh = $('[data-wifihidden]');
  if (wh) wh.onclick = () => {
    const m = modal(`${mhead(`<div class="dicon">${ic('globe')}</div>`, 'Rete Wi-Fi nascosta', 'Rete che non compare nella ricerca')}
      <div class="mb"><div class="field"><label>Nome della rete (SSID)</label><input class="input" id="whs" autocomplete="off" spellcheck="false"></div>
        <div class="field"><label>Password</label><input class="input" id="whp" type="password" autocomplete="off"></div><span class="hint">Vuota per una rete aperta</span></div>
      <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="whok">${ic('link')}Collega</button></div>`);
    $('#whok', m).onclick = e => act(e.currentTarget, () => api('POST', '/network/wifi', { ssid: $('#whs', m).value, password: $('#whp', m).value, hidden: true }, { timeout: 90000 }), 'Wi-Fi collegato').then(x => { if (x) { closeModal(); settingsNetwork(); } });
  };
  $$('[data-wififorget]').forEach(b => b.onclick = async () => {
    if (!await ask('Dimentica la rete Wi-Fi', 'Il NAS si scollega da questa rete Wi-Fi e ne dimentica la password.', 'Dimentica', true)) return;
    act(b, () => api('DELETE', '/network/wifi/' + b.dataset.wififorget), 'Rete dimenticata').then(x => x && settingsNetwork());
  });
}

/* --- Schermo del NAS: l'interfaccia sul monitor collegato al NAS ------------------------------------------- */

async function settingsScreen() {
  let d;
  try { d = await api('GET', '/screen'); } catch (e) { return pageError(e); }
  let body;
  if (d.installing) body = `<div class="row"><span class="spin"></span><b>Installazione in corso…</b></div><pre class="logbox" style="margin-top:10px;max-height:240px">${esc(d.log || '…')}</pre>`;
  else if (!d.installed) body = `<div class="s" style="line-height:1.6;margin-bottom:12px">Mostra questa interfaccia sul monitor collegato al NAS, da usare con tastiera e mouse del NAS: utile se la rete non funziona o per configurare il NAS senza un altro dispositivo. Servono alcuni componenti (circa 100 MB, dagli archivi di Ubuntu).</div>
      ${d.install_failed ? `<div class="alert bad" style="margin-bottom:10px">${ic('alert')}<div>L'installazione non è riuscita: controlla la connessione a internet e riprova.</div></div><pre class="logbox" style="max-height:200px;margin-bottom:10px">${esc(d.log || '')}</pre>` : ''}
      <button class="btn primary" id="scrinst">${ic('dl')}Installa i componenti</button>`;
  else body = `<div class="list">
      <div class="item"><div class="grow"><div class="t">Mostra l'interfaccia sul monitor del NAS</div><div class="s">${d.running ? 'Attivo adesso sul monitor' : d.enabled ? (d.graphics ? 'Attivo: parte all\'accensione' : 'Attivo, ma senza scheda video con driver resta la console di testo') : 'Spento: sul monitor c\'è la console di testo'}</div></div>
        <button class="toggle ${d.enabled ? 'on' : ''}" id="scron"></button></div>
      <div class="item"><div class="grow"><div class="t">Scheda video</div><div class="s">${d.graphics ? 'Trovata' : 'Nessuna scheda video con driver (es. VMSVGA di VirtualBox: scegli VBoxSVGA)'}</div></div><span class="badge ${d.graphics ? 'ok' : 'warn'}">${d.graphics ? 'ok' : 'manca'}</span></div></div>`;
  settingsShell('screen', 'Impostazioni', `
    <div class="card"><h3>${ic('monitor')}Schermo del NAS</h3>${body}</div>
    <div class="card"><h3>${ic('info')}Come funziona</h3><div style="font-size:12.5px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
      <div>Sul monitor compare la stessa interfaccia del browser: si entra con un account dell'interfaccia. Da lì hai tutto, compresi Rete, Terminale e il pulsante di spegnimento.</div>
      <div>Si aprono solo le pagine del NAS: niente siti esterni.</div>
      <div>Ctrl+Alt+F2 apre sempre una console di testo (login con l'utente del sistema); Ctrl+Alt+F1 torna allo schermo.</div>
      <div>Componenti: cage (MIT) e WebKitGTK (LGPL), dagli archivi di Ubuntu.</div></div></div>`);
  const ins = $('#scrinst'); if (ins) ins.onclick = () => act(ins, () => api('POST', '/screen/install'), 'Installazione avviata').then(r => r && settingsScreen());
  const on = $('#scron'); if (on) on.onclick = () => { const v = !on.classList.contains('on'); act(on, () => api('POST', '/screen/enabled', { enabled: v }), v ? 'Schermo del NAS attivato' : 'Schermo del NAS spento').then(() => settingsScreen()); };
  if (d.installing) setTimeout(() => { if (location.hash === '#settings/screen') settingsScreen(); }, 4000);
}
