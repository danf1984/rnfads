// Interfaccia del NAS — Condivisioni, Utenti, Backup
// Licenza GPL-3.0.
'use strict';

const sectionIcon = (icon, color) => `<div class="dicon" style="background:color-mix(in srgb,${color} 14%,transparent);color:${color}">${ic(icon)}</div>`;
const toggleOn = (id, on, attrs = '') => `<button type="button" class="toggle ${on ? 'on' : ''}" id="${id}" ${attrs}></button>`;
const isOn = (root, id) => $('#' + id, root).classList.contains('on');
function wireToggles(root) { $$('button.toggle:not([data-live])', root).forEach(t => { if (!t.onclick) t.onclick = () => t.classList.toggle('on'); }); }
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast('Copiato'); }
  catch (e) { toast('Il browser non permette di copiare: seleziona il testo e copialo a mano', 'bad'); }
}

/* ==========================================================================
   Condivisioni
   ========================================================================== */

async function pageShares() {
  let d;
  try { d = await api('GET', '/shares'); } catch (e) { return pageError(e); }
  const host = d.hostname || S.about.hostname || 'nas';
  const svc = (on, name) => on === null || on === undefined ? '' : `<span class="badge ${on ? 'ok' : ''}">${on ? '<span class="d"></span>' : ''}${name} ${on ? 'attivo' : 'spento'}</span>`;
  const accessText = s => {
    if (s.guest) return 'Tutti, anche senza password';
    const parts = [];
    if (s.all_users) parts.push(`tutti gli utenti (${s.all_users === 'rw' ? 'lettura e scrittura' : 'sola lettura'})`);
    const rw = Object.entries(s.access || {}).filter(([, a]) => a === 'rw').map(([u]) => u);
    const ro = Object.entries(s.access || {}).filter(([, a]) => a === 'ro').map(([u]) => u);
    if (rw.length) parts.push(rw.join(', ') + ' (lettura e scrittura)');
    if (ro.length) parts.push(ro.join(', ') + ' (sola lettura)');
    return parts.join(' · ') || 'Nessuno: scegli chi può entrare';
  };
  const rows = d.shares.map(s => `<div class="item clickable" data-edit="${esc(s.name)}">
    <div class="ficon folder share" style="width:46px;height:40px;transform:scale(.8)"></div>
    <div class="grow"><div class="t">${esc(s.name)} ${s.nfs ? '<span class="badge" style="margin-left:4px">NFS</span>' : ''}${s.recycle ? '<span class="badge" style="margin-left:4px">cestino</span>' : ''}${s.guest ? '<span class="badge warn" style="margin-left:4px">ospiti</span>' : ''}</div>
      <div class="s"><span class="mono">${esc(s.path)}</span> · ${esc(accessText(s))}</div></div>
    <span class="mono subtle hide-m">\\\\${esc(host)}\\${esc(s.name)}</span>
    <button class="btn sm ghost" data-smenu="${esc(s.name)}">${ic('more')}</button></div>`).join('');
  $('#root').innerHTML = shell('shares', 'Condivisioni', `${d.shares.length} cartelle condivise · ${esc('\\\\' + host)}`, `
    <div class="grid two-col" style="grid-template-columns:1fr 340px;align-items:start">
      <div class="card"><div class="row" style="margin-bottom:6px"><h3 style="margin:0">${ic('share')}Cartelle condivise</h3><span class="grow"></span><button class="btn sm primary" id="newshare">${ic('plus')}Nuova condivisione</button></div>
        ${rows ? `<div class="list">${rows}</div>` : `<div class="empty">${ic('share')}<div><b>Nessuna cartella condivisa</b></div><div>Condividi una cartella per vederla da Windows, Mac, telefono e TV.</div></div>`}
      </div>
      <div class="grid">
        <div class="card"><h3>${ic('globe')}Come collegarsi</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
          <div><b>Windows</b>: in Esplora file scrivi <code class="k">\\\\${esc(host)}</code></div>
          <div><b>Mac</b>: Finder › Vai › Connessione al server › <code class="k">smb://${esc(host)}.local</code></div>
          <div><b>Telefono e TV</b>: app con supporto SMB, oppure un'app DLNA dallo store (es. minidlna)</div>
          <div class="row" style="gap:6px;flex-wrap:wrap">${svc(d.services.samba, 'Samba')}${svc(d.services.nfs, 'NFS')}</div></div></div>
        <div class="card"><h3>${ic('users')}Cartelle personali</h3>
          <div class="list"><div class="item"><div class="grow"><div class="t">Una cartella per ogni utente</div><div class="s">Ognuno vede solo la sua, in <span class="mono">/DATA/Utenti</span></div></div>${toggleOn('homes', d.homes, 'data-live')}</div></div></div>
      </div>
    </div>`);
  wireShell();
  $('#homes').onclick = e => act(e.currentTarget, () => api('POST', '/shares-settings', { homes: !d.homes }), 'Salvato').then(r => r && pageShares());
  $('#newshare').onclick = () => shareDialog(null, d);
  $$('[data-edit]').forEach(r => r.onclick = e => { if (!e.target.closest('[data-smenu]')) shareDialog(d.shares.find(s => s.name === r.dataset.edit), d); });
  $$('[data-smenu]').forEach(b => b.onclick = e => {
    e.stopPropagation();
    const s = d.shares.find(x => x.name === b.dataset.smenu);
    popmenu(b, [
      { label: 'Modifica', icon: 'pencil', fn: () => shareDialog(s, d) },
      { label: 'Apri nei file', icon: 'folder', fn: () => { store.set('filesPath', s.path); go('files'); } },
      { label: 'Copia indirizzo', icon: 'copy', fn: () => copyText(`\\\\${host}\\${s.name}`) },
      '-',
      { label: 'Smetti di condividere', icon: 'trash', danger: true, fn: async () => {
        if (await ask('Smetti di condividere', `La cartella <b>${esc(s.name)}</b> non sarà più visibile in rete. I file restano dove sono.`, 'Smetti di condividere', true))
          act(null, () => api('DELETE', '/shares/' + encodeURIComponent(s.name)), 'Condivisione tolta').then(r => r && pageShares());
      } },
    ]);
  });
}

function shareDialog(s, d) {
  const edit = !!s;
  s = s || { name: '', path: '', comment: '', access: {}, guest: false, recycle: true, nfs: false, nfs_rw: true, nfs_hosts: '*', all_users: 'rw' };
  const access = { ...(s.access || {}) };
  const m = modal(`${mhead(sectionIcon('share', '#8b5cf6'), edit ? `Modifica "${esc(s.name)}"` : 'Nuova condivisione', 'Visibile da Windows, Mac e Linux (Samba)')}
    <div class="mb">
      <div class="cols2">
        <div class="field"><label>Nome in rete</label><input class="input" id="shn" value="${esc(s.name)}" maxlength="40" placeholder="es. Film"></div>
        <div class="field"><label>Cartella</label><div class="row" style="gap:6px"><input class="input mono" id="shp" value="${esc(s.path)}" placeholder="/DATA/…"><button class="btn" id="shpick">${ic('folder')}</button></div></div>
      </div>
      ${edit ? '' : `<div class="hint" style="margin-top:-4px">Le cartelle in /DATA stanno sul disco dove hai installato il NAS. Se la cartella non c'è ancora, viene creata.</div>`}
      <div class="field"><label>Descrizione (facoltativa)</label><input class="input" id="shc" value="${esc(s.comment || '')}" maxlength="80"></div>
      <div class="section-t">Chi può entrare</div>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">Tutti gli utenti del NAS</div><div class="s">Anche quelli che crei in futuro</div></div>
          <div class="seg" id="shall">${[['', 'No'], ['ro', 'Sola lettura'], ['rw', 'Lettura e scrittura']].map(([v, t]) => `<button type="button" data-v="${v}" class="${(s.all_users || '') === v ? 'on' : ''}">${t}</button>`).join('')}</div></div>
        ${d.users.map(u => `<div class="item"><div class="appicon sm" style="background:${tileColor(u)};border-radius:50%">${esc(u[0].toUpperCase())}</div><div class="grow"><div class="t">${esc(u)}</div></div>
          <div class="seg" data-u="${esc(u)}">${[['', 'No'], ['ro', 'Sola lettura'], ['rw', 'Lettura e scrittura']].map(([v, t]) => `<button type="button" data-v="${v}" class="${(access[u] || '') === v ? 'on' : ''}">${t}</button>`).join('')}</div></div>`).join('')}
        <div class="item"><div class="grow"><div class="t">Ospiti senza password</div><div class="s">Chiunque nella rete di casa può leggere</div></div>${toggleOn('shg', s.guest)}</div>
      </div>
      ${d.users.length ? '' : `<div class="alert info">${ic('info')}<div>Non ci sono ancora utenti: creali nella pagina <a href="#users">Utenti</a> per dare accesso con password.</div></div>`}
      <div class="section-t">Opzioni</div>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">Cestino di rete</div><div class="s">I file cancellati dal PC finiscono in .cestino invece di sparire</div></div>${toggleOn('shr', s.recycle)}</div>
        <div class="item"><div class="grow"><div class="t">Condividi anche con NFS</div><div class="s">Per altri computer Linux e alcuni lettori multimediali</div></div>${toggleOn('shnfs', s.nfs)}</div>
        <div class="item" id="nfsopts" ${s.nfs ? '' : 'hidden'}><div class="grow"><div class="t">Indirizzi ammessi (NFS)</div><div class="s">* = tutti, oppure es. 192.168.1.0/24</div></div><input class="input sm mono" id="shnh" value="${esc(s.nfs_hosts || '*')}" style="width:170px"><div class="seg" id="shnrw"><button type="button" data-v="1" class="${s.nfs_rw !== false ? 'on' : ''}">Lettura e scrittura</button><button type="button" data-v="0" class="${s.nfs_rw === false ? 'on' : ''}">Sola lettura</button></div></div>
      </div>
    </div>
    <div class="mf">${edit ? '' : '<span class="grow">La cartella viene resa scrivibile per il gruppo degli utenti</span>'}<span class="grow"></span><button class="btn" data-close>Annulla</button><button class="btn primary" id="shsave">${edit ? 'Salva' : 'Condividi'}</button></div>`);
  wireToggles(m);
  $$('.seg', m).forEach(sg => $$('button', sg).forEach(b => b.onclick = () => { $$('button', sg).forEach(x => x.classList.toggle('on', x === b)); }));
  $('#shnfs', m).addEventListener('click', () => { $('#nfsopts', m).hidden = !isOn(m, 'shnfs'); });
  if (!edit) {   // il nome propone la cartella sul disco di sistema (/DATA/<nome>) finché non la scegli tu
    let auto = true;
    $('#shp', m).addEventListener('input', () => { auto = false; });
    $('#shn', m).addEventListener('input', () => { if (auto) $('#shp', m).value = $('#shn', m).value.trim() ? '/DATA/' + $('#shn', m).value.trim().replace(/[\\/:*?"<>|]/g, '') : ''; });
  }
  $('#shpick', m).onclick = () => pickFolder($('#shp', m).value || '/DATA', p => {
    $('#shp', m).value = p;
    if (!$('#shn', m).value) $('#shn', m).value = p.split('/').pop();
  }, true);
  $('#shsave', m).onclick = e => {
    const acc = {};
    $$('[data-u]', m).forEach(sg => { const v = $('button.on', sg)?.dataset.v; if (v) acc[sg.dataset.u] = v; });
    act(e.currentTarget, () => api('POST', '/shares', {
      original: edit ? s.name : undefined, name: $('#shn', m).value.trim(), path: $('#shp', m).value.trim(), comment: $('#shc', m).value,
      access: acc, all_users: $('#shall button.on', m)?.dataset.v || '', guest: isOn(m, 'shg'), recycle: isOn(m, 'shr'),
      nfs: isOn(m, 'shnfs'), nfs_rw: $('#shnrw button.on', m)?.dataset.v !== '0', nfs_hosts: $('#shnh', m).value,
    }), edit ? 'Condivisione aggiornata' : 'Cartella condivisa').then(r => { if (r) { closeModal(); pageShares(); } });
  };
}

/* ==========================================================================
   Utenti
   ========================================================================== */

async function pageUsers() {
  let d;
  try { d = await api('GET', '/users'); } catch (e) { return pageError(e); }
  const rows = d.users.map(u => `<div class="item">
    <div class="appicon sm" style="background:${tileColor(u.name)};border-radius:50%">${esc(u.name[0].toUpperCase())}</div>
    <div class="grow"><div class="t">${esc(u.fullname || u.name)} ${u.admin ? '<span class="badge acc" style="margin-left:4px">amministratore</span>' : ''}${u.samba ? '' : '<span class="badge warn" style="margin-left:4px">senza accesso in rete</span>'}</div>
      <div class="s"><span class="mono">${esc(u.name)}</span> · cartella personale <span class="mono">${esc(u.home)}</span></div></div>
    <button class="btn sm" data-upw="${esc(u.name)}">${ic('key')}<span class="hide-m">Password</span></button>
    <button class="btn sm ghost" data-umenu="${esc(u.name)}">${ic('more')}</button></div>`).join('');
  $('#root').innerHTML = shell('users', 'Utenti', `${d.users.length} utent${d.users.length === 1 ? 'e' : 'i'} del NAS`, `
    <div class="grid two-col" style="grid-template-columns:1fr 340px;align-items:start">
      <div class="card"><div class="row" style="margin-bottom:6px"><h3 style="margin:0">${ic('users')}Utenti del NAS</h3><span class="grow"></span><button class="btn sm primary" id="newuser">${ic('plus')}Nuovo utente</button></div>
        ${rows ? `<div class="list">${rows}</div>` : `<div class="empty">${ic('users')}<div><b>Nessun utente</b></div><div>Crea un utente per ogni persona di casa: avrà la sua password e la sua cartella.</div></div>`}</div>
      <div class="grid">
        <div class="card"><h3>${ic('info')}A cosa servono</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
          <div>Con nome e password di un utente si entra nelle cartelle condivise da Windows, Mac e telefono.</div>
          <div>Gli <b>amministratori</b> possono entrare anche via SSH e usare <span class="mono">sudo</span>.</div></div></div>
        <div class="card"><h3>${ic('lock')}Account dell'interfaccia</h3>
          <div class="list">${(d.ui || []).map(u => `<div class="item" style="padding:8px 0"><div class="grow"><div class="t">${esc(u.name)}</div><div class="s">${u.admin ? 'Amministratore' : 'Utente'} dell'interfaccia</div></div></div>`).join('')}</div>
          <div class="subtle" style="margin-top:6px">Sono separati dagli utenti del NAS. Si gestiscono da <a href="#settings">Impostazioni › Account</a>.</div></div>
      </div>
    </div>`);
  wireShell();
  $('#newuser').onclick = () => userDialog();
  $$('[data-upw]').forEach(b => b.onclick = () => passwordDialog(b.dataset.upw));
  $$('[data-umenu]').forEach(b => b.onclick = () => {
    const u = d.users.find(x => x.name === b.dataset.umenu);
    popmenu(b, [
      { label: 'Modifica nome', icon: 'pencil', fn: async () => { const v = await prompt2('Nome completo', 'Nome e cognome', u.fullname || ''); if (v !== null) act(null, () => api('POST', '/users/' + u.name, { fullname: v }), 'Salvato').then(r => r && pageUsers()); } },
      { label: u.admin ? 'Togli amministratore' : 'Rendi amministratore', icon: 'shield', fn: () => act(null, () => api('POST', '/users/' + u.name, { admin: !u.admin }), 'Ruolo aggiornato').then(r => r && pageUsers()) },
      { label: 'Apri la cartella personale', icon: 'folder', fn: () => { store.set('filesPath', u.home); go('files'); } },
      '-',
      { label: 'Elimina utente', icon: 'trash', danger: true, fn: () => deleteUserDialog(u) },
    ]);
  });
}

function userDialog() {
  const m = modal(`${mhead(sectionIcon('users', '#22c55e'), 'Nuovo utente', 'Per entrare nelle cartelle condivise')}
    <div class="mb">
      <div class="cols2">
        <div class="field"><label>Nome utente</label><input class="input" id="un" placeholder="es. maria" autocapitalize="off" spellcheck="false"><span class="hint">Minuscole, numeri, _ e -</span></div>
        <div class="field"><label>Nome completo (facoltativo)</label><input class="input" id="uf" placeholder="es. Maria Rossi"></div>
      </div>
      <div class="cols2">
        <div class="field"><label>Password</label><input class="input" type="password" id="up" autocomplete="new-password"><span class="hint">Almeno 6 caratteri</span></div>
        <div class="field"><label>Ripeti la password</label><input class="input" type="password" id="up2" autocomplete="new-password"></div>
      </div>
      <div class="list"><div class="item"><div class="grow"><div class="t">Amministratore</div><div class="s">Può entrare via SSH e usare sudo</div></div>${toggleOn('ua', false)}</div></div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="usave">Crea utente</button></div>`, 'sm');
  wireToggles(m);
  $('#un', m).oninput = e => { e.target.value = e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''); };
  $('#usave', m).onclick = e => {
    if ($('#up', m).value !== $('#up2', m).value) return toast('Le due password non coincidono', 'bad');
    act(e.currentTarget, () => api('POST', '/users', { name: $('#un', m).value, fullname: $('#uf', m).value, password: $('#up', m).value, admin: isOn(m, 'ua') }), 'Utente creato')
      .then(r => { if (r) { closeModal(); pageUsers(); } });
  };
}

function passwordDialog(name) {
  const m = modal(`${mhead(`<div class="dicon">${ic('key')}</div>`, 'Nuova password', `Utente ${esc(name)} · vale per le condivisioni e per SSH`)}
    <div class="mb"><div class="field"><label>Nuova password</label><input class="input" type="password" id="pp" autocomplete="new-password"><span class="hint">Almeno 6 caratteri</span></div>
      <div class="field"><label>Ripeti</label><input class="input" type="password" id="pp2" autocomplete="new-password"></div></div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="ok">Cambia</button></div>`, 'sm');
  $('#ok', m).onclick = e => {
    if ($('#pp', m).value !== $('#pp2', m).value) return toast('Le due password non coincidono', 'bad');
    act(e.currentTarget, () => api('POST', '/users/' + name, { password: $('#pp', m).value }), 'Password cambiata').then(r => r && closeModal());
  };
}

function deleteUserDialog(u) {
  const m = modal(`${mhead(`<div class="dicon">${ic('alert')}</div>`, `Elimina "${esc(u.name)}"`)}
    <div class="mb"><div class="dialog-text">L'utente non potrà più entrare nelle condivisioni e verrà tolto dai loro permessi.</div>
      <div class="list"><div class="item"><div class="grow"><div class="t">Cancella anche la cartella personale</div><div class="s mono">${esc(u.home)}</div></div>${toggleOn('udf', false)}</div></div></div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn danger solid" id="ok">Elimina</button></div>`, 'sm');
  wireToggles(m);
  $('#ok', m).onclick = e => act(e.currentTarget, () => api('DELETE', `/users/${u.name}?files=${isOn(m, 'udf') ? 1 : 0}`), 'Utente eliminato').then(r => { if (r) { closeModal(); pageUsers(); } });
}

/* ==========================================================================
   Backup
   ========================================================================== */

const DAYS_IT = { lun: 'lunedì', mar: 'martedì', mer: 'mercoledì', gio: 'giovedì', ven: 'venerdì', sab: 'sabato', dom: 'domenica' };
function schedText(s) {
  if (!s || s.type === 'manual') return 'Solo a mano';
  if (s.type === 'daily') return `Ogni giorno alle ${s.time}`;
  return `Ogni ${DAYS_IT[s.day] || s.day} alle ${s.time}`;
}
const isoAgo = iso => iso ? ago(Date.parse(iso) / 1000) : '';
const destText = dst => dst.type === 'folder' ? dst.path : 'Cloud: ' + dst.remote;

async function pageBackup() {
  let d;
  try { d = await api('GET', '/backup'); } catch (e) { return pageError(e); }
  const rows = d.jobs.map(j => {
    const st = j.status || {};
    const badge = j.running ? '<span class="badge acc"><span class="spin" style="width:10px;height:10px;border-width:2px"></span>in corso</span>'
      : st.ok ? `<span class="badge ok">${ic('check')}riuscito ${esc(isoAgo(st.finished))}</span>`
        : st.finished ? `<span class="badge bad">non riuscito ${esc(isoAgo(st.finished))}</span>` : '<span class="badge">mai eseguito</span>';
    const sum = st.summary || {};
    return `<div class="item"><div class="dicon" style="width:42px;height:42px;background:color-mix(in srgb,#f97316 14%,transparent);color:#f97316">${ic(j.destination.type === 'rclone' ? 'globe' : 'backup')}</div>
      <div class="grow"><div class="t">${esc(j.name)} ${badge}</div>
        <div class="s">${esc(j.sources.join(', '))} → <span class="mono">${esc(destText(j.destination))}</span></div>
        <div class="s">${esc(schedText(j.schedule))}${sum.data_added != null && st.ok ? ` · ultimo: ${bytes(sum.data_added)} aggiunti, ${nf((sum.files_new || 0) + (sum.files_changed || 0))} file nuovi o cambiati` : ''}${st.error && !st.ok ? ` · <span style="color:var(--bad)">${esc(st.error)}</span>` : ''}${st.warning ? ` · <span style="color:var(--warn)">${esc(st.warning)}</span>` : ''}</div></div>
      <button class="btn sm" data-run="${esc(j.id)}" ${j.running ? 'disabled' : ''}>${ic('play')}<span class="hide-m">Esegui ora</span></button>
      <button class="btn sm ghost" data-bmenu="${esc(j.id)}">${ic('more')}</button></div>`;
  }).join('');
  $('#root').innerHTML = shell('backup', 'Backup', `${d.jobs.length} backup${d.jobs.some(j => j.running) ? ' · uno in corso' : ''}`, `
    ${d.restic ? '' : `<div class="alert bad" style="margin-bottom:16px">${ic('alert')}<div>Il programma dei backup (restic) non è installato.</div></div>`}
    <div class="grid two-col" style="grid-template-columns:1fr 340px;align-items:start">
      <div class="card"><div class="row" style="margin-bottom:6px"><h3 style="margin:0">${ic('backup')}I tuoi backup</h3><span class="grow"></span><button class="btn sm primary" id="newbk" ${d.restic ? '' : 'disabled'}>${ic('plus')}Nuovo backup</button></div>
        ${rows ? `<div class="list">${rows}</div>` : `<div class="empty">${ic('backup')}<div><b>Nessun backup</b></div><div>Salva le cartelle importanti su un altro disco, una chiavetta o il cloud.</div></div>`}</div>
      <div class="grid">
        <div class="card"><h3>${ic('shield')}Come funzionano</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
          <div class="row">${ic('check')}Incrementali: copia solo quello che è cambiato</div>
          <div class="row">${ic('check')}Cifrati con una chiave tua</div>
          <div class="row">${ic('check')}Versioni precedenti dei file, da ripristinare</div>
          <div class="row">${ic('check')}Avviso se un backup non riesce (Notifiche)</div></div></div>
        <div class="card"><h3>${ic('globe')}Backup nel cloud</h3><div style="font-size:13px;color:var(--ink-2);line-height:1.5">
          ${d.rclone ? `Collega un servizio (Google Drive, OneDrive, Dropbox, MEGA, B2, S3…) da <a href="#settings/cloud">Impostazioni → Servizi cloud</a>: poi lo trovi tra le destinazioni.` : 'rclone non è installato.'}</div></div>
      </div>
    </div>`);
  wireShell();
  $('#newbk').onclick = () => backupDialog(null, d);
  $$('[data-run]').forEach(b => b.onclick = () => act(b, () => api('POST', `/backup/${b.dataset.run}/run`), 'Backup avviato').then(r => { if (r) { backupLog(b.dataset.run, true); } }));
  $$('[data-bmenu]').forEach(b => b.onclick = () => {
    const j = d.jobs.find(x => x.id === b.dataset.bmenu);
    popmenu(b, [
      { label: 'Ripristina file', icon: 'undo', fn: () => restoreDialog(j) },
      { label: 'Registro', icon: 'term', fn: () => backupLog(j.id) },
      { label: 'Modifica', icon: 'pencil', fn: () => backupDialog(j, d) },
      { label: 'Mostra la chiave', icon: 'key', fn: () => showKey(j) },
      '-',
      { label: 'Elimina il backup', icon: 'trash', danger: true, fn: async () => {
        if (await ask('Elimina il backup', `Il backup <b>${esc(j.name)}</b> non verrà più eseguito. I dati già salvati in <span class="mono">${esc(destText(j.destination))}</span> restano e la chiave viene conservata nel NAS.`, 'Elimina', true))
          act(null, () => api('DELETE', '/backup/' + j.id), 'Backup eliminato').then(r => r && pageBackup());
      } },
    ]);
  });
  if (d.jobs.some(j => j.running)) every('bk', 5000, async () => { const x = await api('GET', '/backup').catch(() => null); if (x && !x.jobs.some(j => j.running) && !$('#scrim')) pageBackup(); });
}

async function backupDialog(j, d) {
  const edit = !!j;
  j = j || { name: '', sources: [], destination: { type: 'folder', path: '' }, schedule: { type: 'daily', time: '03:00', day: 'dom' }, keep: { daily: 7, weekly: 4, monthly: 6 }, stop_apps: false, notify_ok: false };
  let sources = [...j.sources];
  let dtype = j.destination.type;
  const remotes = d.rclone ? (await api('GET', '/backup/rclone').catch(() => ({ remotes: [] }))).remotes : [];
  const m = modal(`${mhead(sectionIcon('backup', '#f97316'), edit ? `Modifica "${esc(j.name)}"` : 'Nuovo backup', 'Incrementale e cifrato (restic)')}
    <div class="mb">
      <div class="field"><label>Nome</label><input class="input" id="bn" value="${esc(j.name)}" placeholder="es. Foto di famiglia" maxlength="40"></div>
      <div class="section-t">Cosa salvare</div>
      <div id="bsrc" style="display:grid;gap:6px"></div>
      <div><button class="btn sm" id="baddsrc">${ic('plus')}Aggiungi cartella</button></div>
      <div class="section-t">Dove salvarlo</div>
      <div class="seg" id="bdt"><button type="button" data-v="folder">${ic('disk')}Disco o cartella</button><button type="button" data-v="rclone" ${d.rclone ? '' : 'disabled'}>${ic('globe')}Cloud (rclone)</button></div>
      <div class="field" id="bdfolder"><div class="row" style="gap:6px"><input class="input mono" id="bdp" value="${esc(j.destination.path || '')}" placeholder="/media/Backup/nas"><button class="btn" id="bdpick">${ic('folder')}</button></div><span class="hint">Meglio un disco diverso da quello dei dati (un disco USB o un secondo disco)</span></div>
      <div class="field" id="bdcloud"><input class="input mono" id="bdr" list="bremotes" value="${esc(j.destination.remote || (remotes[0] ? remotes[0] + 'backup-nas' : ''))}" placeholder="gdrive:backup-nas"><datalist id="bremotes">${remotes.map(r => `<option value="${esc(r)}backup-nas">`).join('')}</datalist>
        <span class="hint">${remotes.length ? 'Servizi collegati: ' + remotes.map(esc).join(', ') : 'Nessun servizio collegato: collegalo da Impostazioni → Servizi cloud'}</span></div>
      <div class="section-t">Quando</div>
      <div class="row" style="flex-wrap:wrap;gap:8px">
        <select class="input" id="bst" style="width:160px"><option value="manual">Solo a mano</option><option value="daily">Ogni giorno</option><option value="weekly">Ogni settimana</option></select>
        <select class="input" id="bsd" style="width:140px">${Object.entries(DAYS_IT).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select>
        <input class="input" id="bsh" type="time" value="${esc(j.schedule.time || '03:00')}" style="width:120px">
      </div>
      <div class="section-t">Versioni da tenere</div>
      <div class="row" style="gap:10px;flex-wrap:wrap;font-size:13px">
        <label class="row" style="gap:6px"><input class="input sm" type="number" min="0" max="999" id="kd" value="${j.keep.daily}" style="width:70px">giornaliere</label>
        <label class="row" style="gap:6px"><input class="input sm" type="number" min="0" max="999" id="kw" value="${j.keep.weekly}" style="width:70px">settimanali</label>
        <label class="row" style="gap:6px"><input class="input sm" type="number" min="0" max="999" id="km" value="${j.keep.monthly}" style="width:70px">mensili</label>
      </div>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">Ferma le app durante il backup</div><div class="s">Per copiare i database delle app senza errori</div></div>${toggleOn('bstop', j.stop_apps)}</div>
        <div class="item"><div class="grow"><div class="t">Avvisami anche quando riesce</div><div class="s">Gli errori vengono sempre notificati</div></div>${toggleOn('bnok', j.notify_ok)}</div>
      </div>
      ${edit ? '' : `<div class="field"><label>Chiave di cifratura (facoltativa)</label><input class="input" type="password" id="bpw" autocomplete="new-password" placeholder="Lascia vuoto per crearne una a caso"><span class="hint">Senza la chiave i dati salvati non si possono leggere: la trovi poi nel menu del backup. Conservane una copia fuori dal NAS.</span></div>`}
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="bsave">${edit ? 'Salva' : 'Crea backup'}</button></div>`);
  wireToggles(m);
  const drawSrc = () => {
    $('#bsrc', m).innerHTML = sources.map((s, i) => `<div class="row" style="font-size:13px">${ic('folder')}<span class="mono grow">${esc(s)}</span><button class="btn sm ghost" data-rm="${i}">${ic('x')}</button></div>`).join('') || '<div class="subtle">Nessuna cartella scelta</div>';
    $$('[data-rm]', m).forEach(b => b.onclick = () => { sources.splice(+b.dataset.rm, 1); drawSrc(); });
  };
  drawSrc();
  const drawDest = () => {
    $$('#bdt button', m).forEach(b => b.classList.toggle('on', b.dataset.v === dtype));
    $('#bdfolder', m).hidden = dtype !== 'folder';
    $('#bdcloud', m).hidden = dtype !== 'rclone';
  };
  drawDest();
  $$('#bdt button', m).forEach(b => b.onclick = () => { dtype = b.dataset.v; drawDest(); });
  $('#bst', m).value = j.schedule.type || 'manual';
  $('#bsd', m).value = j.schedule.day || 'dom';
  const drawSched = () => { const t = $('#bst', m).value; $('#bsd', m).hidden = t !== 'weekly'; $('#bsh', m).hidden = t === 'manual'; };
  drawSched();
  $('#bst', m).onchange = drawSched;
  $('#baddsrc', m).onclick = () => pickFolder('/DATA', p => { if (!sources.includes(p)) sources.push(p); drawSrc(); });
  $('#bdpick', m).onclick = () => pickFolder('/media', p => { $('#bdp', m).value = p; }, true);
  $('#bsave', m).onclick = e => {
    const t = $('#bst', m).value;
    const body = {
      name: $('#bn', m).value.trim(), sources,
      destination: dtype === 'folder' ? { type: 'folder', path: $('#bdp', m).value.trim() } : { type: 'rclone', remote: $('#bdr', m).value.trim() },
      schedule: t === 'manual' ? { type: 'manual' } : { type: t, time: $('#bsh', m).value || '03:00', day: $('#bsd', m).value },
      keep: { daily: +$('#kd', m).value, weekly: +$('#kw', m).value, monthly: +$('#km', m).value },
      stop_apps: isOn(m, 'bstop'), notify_ok: isOn(m, 'bnok'),
    };
    if (!edit) body.password = $('#bpw', m).value;
    act(e.currentTarget, () => api('POST', edit ? '/backup/' + j.id : '/backup', body), edit ? 'Backup salvato' : 'Backup creato').then(r => { if (r) { closeModal(); pageBackup(); } });
  };
}

function backupLog(id, live) {
  const m = modal(`${mhead(`<div class="dicon">${ic('term')}</div>`, 'Registro del backup', '<span id="blst"></span>')}<div class="mb"><pre class="logbox tall" id="blog">…</pre></div>
    <div class="mf"><button class="btn" data-close>Chiudi</button></div>`, 'wide');
  let stop = false;
  S.onModalClose = () => { stop = true; pageBackup(); };
  (async () => {
    while (!stop) {
      const r = await api('GET', `/backup/${id}/log`).catch(() => null);
      if (!r || !$('#blog', m)) return;
      const box = $('#blog', m);
      const atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
      box.textContent = r.log || 'Registro vuoto';
      if (atEnd) box.scrollTop = box.scrollHeight;
      $('#blst', m).innerHTML = r.running ? '<span class="badge acc">in corso</span>' : 'concluso';
      if (!r.running && !live) return;
      if (!r.running) live = false;
      await sleep(2000);
    }
  })();
}

async function showKey(j) {
  const r = await act(null, () => api('GET', `/backup/${j.id}/key`));
  if (!r) return;
  const m = modal(`${mhead(`<div class="dicon">${ic('key')}</div>`, 'Chiave del backup', esc(j.name))}
    <div class="mb"><div class="alert info">${ic('info')}<div>Senza questa chiave i dati del backup non si possono leggere, nemmeno da un altro computer. Conservane una copia fuori dal NAS (es. nel gestore di password).</div></div>
      <div class="linkbox"><input class="input" id="bk" value="${esc(r.key)}" readonly><button class="btn" id="bkc">${ic('copy')}Copia</button></div></div>
    <div class="mf"><button class="btn" data-close>Chiudi</button></div>`, 'sm');
  $('#bkc', m).onclick = () => copyText(r.key);
}

async function restoreDialog(j) {
  const m = modal(`${mhead(`<div class="dicon">${ic('undo')}</div>`, 'Ripristina file', `${esc(j.name)} · scegli la versione`)}<div class="mb" id="rsb"><div class="loading-page" style="min-height:120px"><span class="spin lg"></span></div></div>
    <div class="mf"><span class="grow">I file vengono ripristinati in una cartella nuova: niente viene sovrascritto</span><button class="btn" data-close>Chiudi</button></div>`, 'wide');
  let r;
  try { r = await api('GET', `/backup/${j.id}/snapshots`); } catch (e) { $('#rsb', m).innerHTML = `<div class="alert bad">${ic('alert')}<div>${esc(e.message)}</div></div>`; return; }
  if (!$('#rsb', m)) return;
  $('#rsb', m).innerHTML = r.snapshots.length ? `<div class="list">${r.snapshots.map(s => `<div class="item"><div class="grow"><div class="t">${esc(new Date(s.time).toLocaleString(LOCALE, { dateStyle: 'full', timeStyle: 'short' }))}</div><div class="s mono">${esc(s.id)} · ${esc((s.paths || []).join(', '))}</div></div>
    <button class="btn sm" data-rs="${esc(s.id)}">${ic('undo')}Ripristina</button></div>`).join('')}</div>` : '<div class="empty">Il backup non è ancora stato eseguito: nessuna versione.</div>';
  $$('[data-rs]', m).forEach(b => b.onclick = () => {
    const n = new Date(), p2 = x => String(x).padStart(2, '0');
    const stamp = `${n.getFullYear()}-${p2(n.getMonth() + 1)}-${p2(n.getDate())}_${p2(n.getHours())}${p2(n.getMinutes())}`;
    const target = `/DATA/Ripristini/${j.name.replace(/[^A-Za-z0-9 _-]/g, '')}_${stamp}`;
    act(b, () => api('POST', `/backup/${j.id}/restore`, { snapshot: b.dataset.rs, target }), x => `Ripristino avviato in ${x.target}`).then(x => { if (x) { closeModal(); backupLog(j.id, true); } });
  });
}

ROUTES.shares = pageShares;
ROUTES.users = pageUsers;
ROUTES.backup = pageBackup;
