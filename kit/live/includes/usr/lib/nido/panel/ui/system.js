// Interfaccia del NAS — Impostazioni: Generale, Notifiche, Aggiornamenti di sistema, Home Assistant e API
// Licenza GPL-3.0.
'use strict';

/* --- Generale ------------------------------------------------------------------------------ */

async function settingsGeneral() {
  let o, ps;
  try { [o, ps] = await Promise.all([api('GET', '/system/overview'), api('GET', '/system/power-schedule')]); } catch (e) { return pageError(e); }
  const kv = [['Nome', `${o.os.name} ${o.os.version}`], ['Sistema di base', S.about.base || o.os.pretty], ['Kernel', o.os.kernel],
    ['Nome in rete', `${o.os.hostname} · ${o.os.hostname}.local`], ['Indirizzi', o.ips.map(i => `${i.ip} (${i.iface})`).join(', ') || '—'],
    ['Acceso da', durText(o.uptime)], ['Processori', `${o.cpus} · carico ${o.load.map(x => nf(x, 2)).join(' ')}`],
    ['Memoria', `${bytes(o.memory.used)} usati su ${bytes(o.memory.total)}`], ['Temperatura', o.temperature != null ? nf(o.temperature, 0) + ' °C' : 'nessun sensore']];
  settingsShell('general', 'Impostazioni', `
    ${o.reboot_required ? `<div class="alert info">${ic('restart')}<div><b>Serve un riavvio</b> per completare gli ultimi aggiornamenti.</div></div>` : ''}
    <div class="card"><h3>${ic('server')}Il tuo NAS</h3><dl class="kv" style="grid-template-columns:150px 1fr">${kv.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl></div>
    <div class="card"><h3>${ic('globe')}Lingua</h3>
      <div class="list"><div class="item"><div class="grow"><div class="t">Lingua dell'interfaccia</div><div class="s">Vale per tutti gli account e anche per la pagina di accesso</div></div>
        <select class="input sm" id="uilang" style="width:150px">${Object.entries(LANG_NAMES).map(([k, n]) => `<option value="${k}" ${(S.about.lang || 'it') === k ? 'selected' : ''} class="notr">${n}</option>`).join('')}</select></div></div></div>
    <div class="card"><h3>${ic('disk')}Dischi</h3><div class="list">${o.disks.map(d => `<div class="item" style="padding:9px 0"><div class="grow"><div class="t">${esc(d.model || d.name)}</div><div class="s">${esc(d.role)} · ${bytes(d.size)}${d.used_percent != null ? ` · ${nf(d.used_percent, 0)}% usato` : ''}${d.temperature ? ` · ${d.temperature} °C` : ''}</div></div><span class="badge ${d.health === 'buono' ? 'ok' : d.health === 'guasto' ? 'bad' : d.health === 'attenzione' ? 'warn' : ''}">${esc(d.health)}</span></div>`).join('')}</div>
      <div style="margin-top:10px"><a class="btn sm" href="#disks">${ic('disk')}Vai a Dischi</a></div></div>
    <div class="card"><h3>${ic('restart')}Accensione</h3>
      <div class="row" style="flex-wrap:wrap"><button class="btn" id="reboot">${ic('restart')}Riavvia</button><button class="btn danger" id="poweroff">${ic('stop')}Spegni</button></div>
      <div class="subtle" style="margin-top:10px">Le app si fermano e ripartono da sole. Durante il riavvio il NAS non risponde per qualche minuto.</div></div>
    ${powerSchedCard(ps)}`);
  // Il valore va letto subito: act() mette la rotellina dentro l'elemento e con un <select> cancellerebbe le voci
  $('#uilang').onchange = e => { const sel = e.currentTarget, lang = sel.value; sel.disabled = true; act(null, () => api('POST', '/system/language', { lang })).then(r => {
    sel.disabled = false;
    if (r) { try { localStorage.setItem('nas.lang', JSON.stringify(r.lang)); } catch (x) { /* privata */ } location.reload(); }
  }); };
  $('#reboot').onclick = () => powerAction('reboot');
  const gr = $('.settings .grid');
  if (gr) {
    gr.insertAdjacentHTML('beforeend', `<div class="card"><div class="row" style="flex-wrap:wrap"><div class="grow"><h3 style="margin:0 0 4px">${ic('sliders')}Procedura guidata</h3><div class="subtle">Nome del NAS, fuso orario, dischi, cartella condivisa e sicurezza, passo per passo.</div></div><button class="btn" id="wzopen">${ic('play')}Apri la procedura guidata</button></div></div>`);
    $('#wzopen').onclick = wizardReopen;
  }
  $('#poweroff').onclick = () => powerAction('poweroff');
  wirePowerSched(ps);
}

/* Spegnimento e accensione programmati */
const PS_DAYS = ['L', 'M', 'M', 'G', 'V', 'S', 'D'];
const PS_NAMES = ['lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato', 'domenica'];

function powerSchedCard(ps) {
  const days = (k, sel) => `<div class="chips" data-psdays="${k}">${PS_DAYS.map((t, i) => `<span class="chip ${sel.includes(i) ? 'on' : ''}" data-d="${i}" title="${PS_NAMES[i]}" style="width:36px;justify-content:center;padding:0">${t}</span>`).join('')}</div>`;
  const last = ps.last && ps.last.t ? (ps.last.result === 'skipped' ? `Ultimo spegnimento programmato saltato (${ago(ps.last.t)}): ${ps.last.reason}` :
    `Ultimo spegnimento programmato ${ago(ps.last.t)}${ps.last.waited ? ` dopo ${ps.last.waited} min di attesa` : ''}${ps.last.wake_ok === false ? ' · accensione NON impostata' : ''}`) : '';
  return `<div class="card" id="pscard"><h3>${ic('clock')}Spegnimento e accensione programmati</h3>
    <div class="list">
      <div class="item" style="flex-wrap:wrap"><div class="grow"><div class="t">Spegni il NAS</div><div class="s">${ps.off.enabled && ps.next_off ? 'Prossimo spegnimento: ' + esc(ps.next_off) : 'Nei giorni scelti, all\'ora indicata'}</div></div>
        <input class="input sm" type="time" id="psofft" value="${esc(ps.off.time)}" style="width:116px"><button class="toggle ${ps.off.enabled ? 'on' : ''}" id="psoff" aria-label="Spegnimento programmato"></button>
        <div style="flex-basis:100%">${days('off', ps.off.days)}</div></div>
      <div class="item" style="flex-wrap:wrap"><div class="grow"><div class="t">Riaccendi il NAS</div><div class="s">${ps.on.enabled && ps.next_on ? 'Prossima accensione: ' + esc(ps.next_on) : 'Con la sveglia del PC (RTC), dopo ogni spegnimento'}</div></div>
        <input class="input sm" type="time" id="psont" value="${esc(ps.on.time)}" style="width:116px"><button class="toggle ${ps.on.enabled ? 'on' : ''}" id="pson" aria-label="Accensione programmata"></button>
        <div style="flex-basis:100%">${days('on', ps.on.days)}</div></div>
      <div class="item"><div class="grow"><div class="t">Aspetta backup e aggiornamenti</div><div class="s">Se sono in corso aspetta al massimo questi minuti, poi salta lo spegnimento</div></div>
        <input class="input sm" type="number" min="5" max="720" id="pswait" value="${ps.max_wait}" style="width:90px"></div>
      <div class="item"><div class="grow"><div class="t">Notifica prima di spegnere</div><div class="s">Con i canali di Impostazioni → Notifiche</div></div><button class="toggle ${ps.notify ? 'on' : ''}" id="psnot"></button></div>
    </div>
    ${!ps.rtc.available ? `<div class="alert warn" style="margin-top:12px">${ic('alert')}<div>Questo PC non ha una sveglia (RTC) utilizzabile: l'accensione programmata non funzionerà. Lo spegnimento sì.</div></div>` : ''}
    <div id="psmsg"></div>
    ${last ? `<div class="subtle" style="margin-top:10px">${esc(last)}</div>` : ''}
    <div class="row" style="margin-top:12px;flex-wrap:wrap"><button class="btn primary" id="pssave">${ic('check')}Salva</button><button class="btn" id="pstest" ${ps.rtc.available ? '' : 'disabled'}>${ic('clock')}Prova la sveglia del PC</button></div>
    <div class="subtle" style="margin-top:10px">L'accensione funziona solo se il PC lo permette (nel BIOS/UEFI l'opzione si chiama spesso "Wake on RTC" o "Power on by RTC") e se resta collegato alla corrente.</div></div>`;
}

function wirePowerSched(ps) {
  $$('#pscard [data-psdays] .chip').forEach(c => c.onclick = () => c.classList.toggle('on'));
  ['#psoff', '#pson', '#psnot'].forEach(id => { $(id).onclick = e => e.currentTarget.classList.toggle('on'); });
  const sel = k => $$(`[data-psdays="${k}"] .chip.on`).map(c => +c.dataset.d);
  $('#pssave').onclick = e => act(e.currentTarget, () => api('POST', '/system/power-schedule', {
    off: { enabled: $('#psoff').classList.contains('on'), time: $('#psofft').value, days: sel('off') },
    on: { enabled: $('#pson').classList.contains('on'), time: $('#psont').value, days: sel('on') },
    max_wait: +$('#pswait').value, notify: $('#psnot').classList.contains('on') }), 'Programma salvato').then(r => { if (r) settingsGeneral(); });
  $('#pstest').onclick = e => act(e.currentTarget, () => api('POST', '/system/power-schedule/test')).then(r => {
    if (r) $('#psmsg').innerHTML = `<div class="alert ${r.ok ? 'info' : 'bad'}" style="margin-top:12px">${ic(r.ok ? 'check' : 'alert')}<div>${esc(r.message)}</div></div>`; });
}

async function powerAction(what) {
  const reboot = what === 'reboot';
  if (!await ask(reboot ? 'Riavviare il NAS?' : 'Spegnere il NAS?', reboot ? 'Il NAS sarà irraggiungibile per qualche minuto, poi la pagina si ricarica da sola.' : 'Per riaccenderlo dovrai premere il pulsante di accensione.', reboot ? 'Riavvia' : 'Spegni', !reboot)) return;
  const r = await act(null, () => api('POST', '/system/' + what));
  if (!r) return;
  const wk = r.wake && r.wake.ok !== null && r.wake.ok !== undefined ? (r.wake.ok ? `Si riaccende da solo ${esc(r.wake.text)}.` : `Accensione programmata non impostata: ${esc(r.wake.text)}.`) : '';
  $('#root').innerHTML = `<div class="login-wrap"><div class="card login-card"><div class="empty">${cube(64)}<b>${reboot ? 'Riavvio in corso…' : 'Spegnimento in corso…'}</b><div>${reboot ? 'La pagina si ricarica da sola quando il NAS è di nuovo pronto.' : 'Puoi chiudere questa pagina. ' + wk}</div>${reboot ? '<span class="spin lg"></span>' : ''}</div></div></div>`;
  if (!reboot) return;
  await sleep(20000);
  for (;;) {
    try { const x = await fetch('/api/auth/state', { cache: 'no-store' }); if (x.ok) { location.reload(); return; } } catch (e) { /* ancora spento */ }
    await sleep(4000);
  }
}

/* --- Notifiche ----------------------------------------------------------------------------- */

const CHANNELS = {
  ntfy: ['Notifiche sul telefono (ntfy)', 'App gratuita ntfy per Android e iPhone', [['server', 'Server', 'https://ntfy.sh'], ['topic', 'Argomento (topic)', 'un nome difficile da indovinare'], ['token', 'Token (facoltativo)', '', 'password']]],
  telegram: ['Telegram', 'Messaggi da un tuo bot', [['token', 'Token del bot', 'da @BotFather', 'password'], ['chat_id', 'Chat ID', 'es. 123456789']]],
  email: ['Email', 'Con un server SMTP (es. Gmail con password per le app)', [['host', 'Server SMTP', 'smtp.gmail.com'], ['port', 'Porta', '587'], ['security', 'Sicurezza', '', 'select'], ['user', 'Utente', ''], ['password', 'Password', '', 'password'], ['from', 'Mittente', ''], ['to', 'Destinatario', 'tu@esempio.it']]],
  webhook: ['Webhook (Home Assistant)', 'Un JSON con title, message, level ed event', [['url', 'Indirizzo', 'http://homeassistant.local:8123/api/webhook/…']]],
};

async function settingsNotify() {
  let n;
  try { n = await api('GET', '/notify'); } catch (e) { return pageError(e); }
  const field = (ch, [k, label, ph, type]) => {
    const v = n.channels[ch][k] ?? '';
    if (type === 'select') return `<div class="field"><label>${label}</label><select class="input" data-ch="${ch}" data-k="${k}">${[['starttls', 'STARTTLS'], ['ssl', 'SSL/TLS'], ['none', 'Nessuna']].map(([a, b]) => `<option value="${a}" ${v === a ? 'selected' : ''}>${b}</option>`).join('')}</select></div>`;
    return `<div class="field"><label>${label}</label><input class="input" data-ch="${ch}" data-k="${k}" type="${type || 'text'}" value="${esc(v)}" placeholder="${esc(ph)}" autocomplete="off"></div>`;
  };
  settingsShell('notify', 'Impostazioni', `
    ${Object.entries(CHANNELS).map(([ch, [t, s, fields]]) => `<div class="card"><div class="row"><div class="grow"><h3 style="margin:0">${ic('bell')}${t}</h3><div class="subtle" style="margin-top:2px">${s}</div></div>
      <button class="btn sm" data-test="${ch}">Prova</button><button class="toggle ${n.channels[ch].enabled ? 'on' : ''}" data-en="${ch}" title="Attiva"></button></div>
      <div class="cols2" style="margin-top:12px" data-box="${ch}" ${n.channels[ch].enabled ? '' : 'hidden'}>${fields.map(f => field(ch, f)).join('')}</div></div>`).join('')}
    <div class="card"><h3>${ic('alert')}Quando avvisare</h3><div class="list">
      ${Object.entries(n.event_names).map(([k, t]) => `<div class="item" style="padding:9px 0"><div class="grow"><div class="t" style="font-weight:550">${esc(t)}</div></div><button class="toggle ${n.events[k] ? 'on' : ''}" data-ev="${k}"></button></div>`).join('')}
      <div class="item"><div class="grow"><div class="t" style="font-weight:550">Soglia dello spazio</div><div class="s">Avvisa quando un disco è pieno oltre</div></div><input class="input sm" type="number" min="50" max="99" id="nsp" value="${n.space_threshold}" style="width:80px"> %</div>
      <div class="item"><div class="grow"><div class="t" style="font-weight:550">Soglia di temperatura dei dischi</div></div><input class="input sm" type="number" min="35" max="80" id="ntp" value="${n.temp_threshold}" style="width:80px"> °C</div>
    </div><div class="subtle" style="margin-top:8px">Lo stesso avviso non viene ripetuto prima di 24 ore.</div></div>
    <div class="row"><span class="grow"></span><button class="btn primary" id="nsave">${ic('check')}Salva</button></div>`);
  $$('[data-en]').forEach(t => t.onclick = () => { t.classList.toggle('on'); $(`[data-box="${t.dataset.en}"]`).hidden = !t.classList.contains('on'); });
  $$('[data-ev]').forEach(t => t.onclick = () => t.classList.toggle('on'));
  const collect = () => {
    const body = { channels: {}, events: {}, space_threshold: +$('#nsp').value, temp_threshold: +$('#ntp').value };
    for (const ch of Object.keys(CHANNELS)) {
      body.channels[ch] = { enabled: $(`[data-en="${ch}"]`).classList.contains('on') };
      $$(`[data-ch="${ch}"]`).forEach(i => { body.channels[ch][i.dataset.k] = i.value; });
    }
    $$('[data-ev]').forEach(t => { body.events[t.dataset.ev] = t.classList.contains('on'); });
    return body;
  };
  $('#nsave').onclick = e => act(e.currentTarget, () => api('POST', '/notify', collect()), 'Notifiche salvate');
  $$('[data-test]').forEach(b => b.onclick = () => act(b, async () => {
    await api('POST', '/notify', collect());
    const r = await api('POST', '/notify/test', { channel: b.dataset.test });
    const v = r[b.dataset.test];
    if (v !== 'ok') throw new Error(v || 'Invio non riuscito');
    return r;
  }, 'Messaggio di prova inviato'));
}

/* --- Aggiornamenti di sistema ---------------------------------------------------------------- */

const GROUPS = [['security', 'Sicurezza', 'bad'], ['own', null, 'acc'], ['system', 'Sistema', '']];

async function settingsUpdates() {
  let u, sn;
  try { [u, sn] = await Promise.all([api('GET', '/updates'), api('GET', '/snapshots').catch(() => ({ available: false, snapshots: [] }))]); } catch (e) { return pageError(e); }
  const n = u.packages.length;
  const busy = u.checking || u.installing;
  const st = u.settings;
  const last = u.last || {};
  const head = busy ? (u.installing ? 'Aggiornamento in corso…' : 'Cerco aggiornamenti…')
    : n ? `${n} aggiornament${n === 1 ? 'o' : 'i'} disponibil${n === 1 ? 'e' : 'i'}` : 'Il sistema è aggiornato';
  const parts = [u.groups.security ? `${u.groups.security} di sicurezza` : '', u.groups.own ? `${u.groups.own} di ${S.about.name}` : '',
    u.checked_at ? 'ultimo controllo: ' + isoAgo(u.checked_at) : 'mai controllato', u.reboot_required ? 'serve un riavvio' : ''].filter(Boolean);
  const groups = GROUPS.map(([g, t, c]) => {
    const items = u.packages.filter(p => (p.group || (p.security ? 'security' : 'system')) === g);
    if (!items.length) return '';
    const show = items.slice(0, 40);
    return `<div class="section-t" style="margin:12px 0 4px">${t || esc(S.about.name)} <span class="badge ${c}" style="margin-left:6px">${items.length}</span></div><div class="list">${show.map(p => `<div class="item" style="padding:7px 0"><div class="grow"><div class="t mono" style="font-size:13px">${esc(p.name)}</div><div class="s mono">${esc(p.from)} → ${esc(p.to)}</div></div></div>`).join('')}
      ${items.length > show.length ? `<div class="item subtle" style="padding:7px 0">+ altri ${items.length - show.length} pacchetti</div>` : ''}</div>`;
  }).join('');
  settingsShell('updates', 'Impostazioni', `
    <div class="card"><div class="row" style="gap:16px;flex-wrap:wrap">
      <div class="dicon" style="background:color-mix(in srgb,#6366f1 14%,transparent);color:#6366f1;width:54px;height:54px">${busy ? '<span class="spin lg"></span>' : ic('refresh')}</div>
      <div class="grow" style="min-width:200px"><div style="font-size:18px;font-weight:700;letter-spacing:-.01em">${head}</div><div class="muted" style="font-size:13px">${esc(parts.join(' · '))}</div></div>
      <button class="btn" id="ucheck" ${busy ? 'disabled' : ''}>${ic('search')}Cerca aggiornamenti</button>
      <button class="btn primary" id="uinstall" ${busy || !n ? 'disabled' : ''}>${ic('dl')}Aggiorna ora</button></div></div>
    <div id="selfcard"></div>
    <div id="relcard"></div>
    ${u.reboot_required ? `<div class="alert info">${ic('restart')}<div style="flex:1"><b>Serve un riavvio</b> per usare il nuovo kernel o le nuove librerie. Le app ripartono da sole.</div><button class="btn sm" id="ureboot">${ic('restart')}Riavvia ora</button></div>` : ''}
    <div class="grid two-col" style="grid-template-columns:1fr 1fr;align-items:start">
      <div class="card"><h3>${ic('list')}Cosa verrà aggiornato</h3>${groups || '<div class="subtle">Niente da aggiornare. Premi "Cerca aggiornamenti" per controllare adesso.</div>'}</div>
      <div class="grid">
        <div class="card"><h3>${ic('shield')}Sicurezza dell'aggiornamento</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
          <div class="row">${ic(u.snapshots ? 'check' : 'info')}${u.snapshots ? 'Snapshot del sistema prima e dopo' : 'Snapshot non disponibili (disco di sistema non Btrfs)'}</div>
          <div class="row">${ic('check')}Le app restano accese durante l'aggiornamento</div>
          <div class="row">${ic('check')}Se qualcosa va storto: si torna allo snapshot precedente</div></div></div>
        <div class="card"><h3>${ic('gear')}Automatico</h3><div class="list">
          <div class="item"><div class="grow"><div class="t">Cerca aggiornamenti</div><div class="s">Ti avvisa con una notifica</div></div><select class="input sm" id="uschk" style="width:150px">${[['daily', 'Ogni giorno'], ['weekly', 'Ogni settimana'], ['off', 'Mai']].map(([v, t]) => `<option value="${v}" ${st.check === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
          <div class="item"><div class="grow"><div class="t">Installa quelli di sicurezza</div><div class="s">Da soli, di notte</div></div><button class="toggle ${st.security ? 'on' : ''}" id="ussec"></button></div>
          <div class="item"><div class="grow"><div class="t">Riavvia se serve</div><div class="s">Solo dopo un aggiornamento che lo richiede</div></div><input class="input sm" type="time" id="usrt" value="${esc(st.reboot_time)}" style="width:116px"><button class="toggle ${st.reboot ? 'on' : ''}" id="usrb"></button></div>
        </div></div>
      </div>
    </div>
    <div class="card" style="padding:0;overflow:hidden">
      <div class="row" style="padding:14px 18px;flex-wrap:wrap"><h3 style="margin:0">${ic('term')}Registro</h3><span class="grow"></span>${last.when ? `<span class="badge ${last.ok ? 'ok' : 'bad'}">${last.ok ? ic('check') : ''}${esc(new Date(last.when).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }))} · ${last.ok ? 'riuscito' : 'non riuscito'} · ${Math.floor(last.seconds / 60)} min ${last.seconds % 60} s</span>` : ''}</div>
      <pre class="logbox tall" id="ulog" style="border-radius:0;margin:0;max-height:340px;min-height:160px">…</pre></div>
    <div class="card"><div class="row" style="margin-bottom:8px"><h3 style="margin:0">${ic('backup')}Snapshot del sistema</h3><span class="grow"></span>${sn.available ? `<button class="btn sm" id="snnew">${ic('plus')}Crea snapshot</button>` : ''}</div>
      ${sn.available ? (sn.snapshots.length ? `<div class="list">${sn.snapshots.slice(0, 30).map(s => `<div class="item" style="padding:9px 0"><div class="grow"><div class="t" style="font-weight:550">#${s.number} ${esc(s.description || '')} ${s.important ? '<span class="badge acc">importante</span>' : ''}</div><div class="s">${esc(s.date || '')}${s.type === 'post' && s.pre ? ` · coppia con #${s.pre}` : ''}</div></div>
        <button class="btn sm" data-snr="${s.number}">${ic('undo')}<span class="hide-m">Ripristina</span></button><button class="btn sm ghost danger" data-snd="${s.number}">${ic('trash')}</button></div>`).join('')}</div>` : '<div class="subtle">Nessuno snapshot.</div>')
        : '<div class="subtle">Gli snapshot funzionano quando il disco di sistema è Btrfs (installazione standard). Il sistema di prova non lo è.</div>'}
      <div class="subtle" style="margin-top:8px">Uno snapshot riporta indietro solo il sistema: i tuoi file, le app e i loro dati non cambiano.</div></div>`);
  // registro in diretta
  let offset = 0, stop = false;
  S.cleanup.push(() => { stop = true; });
  (async () => {
    let wasRunning = busy;
    while (!stop) {
      const r = await api('GET', '/updates/log?from=' + offset).catch(() => null);
      const box = $('#ulog');
      if (!r || !box) return;
      if (offset === 0) box.textContent = '';
      offset = r.offset;
      if (r.text) {
        const atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
        box.textContent += r.text;
        if (atEnd || wasRunning) box.scrollTop = box.scrollHeight;
      }
      if (!box.textContent) box.textContent = 'Ancora nessun aggiornamento fatto da qui.';
      if (wasRunning && !r.running) { await sleep(800); if (!stop) settingsUpdates(); return; }
      wasRunning = r.running;
      await sleep(r.running ? 1500 : 6000);
    }
  })();
  selfUpdateCard();
  releaseCard();
  $('#ucheck').onclick = e => act(e.currentTarget, () => api('POST', '/updates/check')).then(r => r && settingsUpdates());
  $('#uinstall').onclick = async e => {
    if (!await ask('Aggiornare adesso?', `Verranno installati ${n} pacchetti${u.snapshots ? ', con uno snapshot del sistema prima e dopo' : ''}. Puoi continuare a usare il NAS mentre aggiorna.`, 'Aggiorna ora')) return;
    act(e.currentTarget, () => api('POST', '/updates/install')).then(r => r && settingsUpdates());
  };
  const rb = $('#ureboot');
  if (rb) rb.onclick = () => powerAction('reboot');
  const saveSet = () => act(null, () => api('POST', '/updates/settings', { check: $('#uschk').value, security: $('#ussec').classList.contains('on'), reboot: $('#usrb').classList.contains('on'), reboot_time: $('#usrt').value }), 'Impostazioni salvate');
  $('#uschk').onchange = saveSet;
  $('#usrt').onchange = saveSet;
  ['#ussec', '#usrb'].forEach(id => $(id).onclick = e => { e.currentTarget.classList.toggle('on'); saveSet(); });
  const sb = $('#snnew');
  if (sb) sb.onclick = async () => { const v = await prompt2('Nuovo snapshot', 'Descrizione', 'Prima delle modifiche', 'Crea'); if (v) act(null, () => api('POST', '/snapshots', { description: v }), 'Snapshot creato').then(r => r && settingsUpdates()); };
  $$('[data-snr]').forEach(b => b.onclick = async () => {
    if (await ask('Ripristinare lo snapshot?', `Il sistema torna com'era nello snapshot #${b.dataset.snr}. Prima viene creato uno snapshot dello stato attuale. Dopo serve un riavvio.`, 'Ripristina', true))
      act(b, () => api('POST', `/snapshots/${b.dataset.snr}/restore`), 'Sistema ripristinato: riavvia il NAS').then(r => r && settingsUpdates());
  });
  $$('[data-snd]').forEach(b => b.onclick = async () => { if (await ask('Eliminare lo snapshot?', `Lo snapshot #${b.dataset.snd} verrà eliminato.`, 'Elimina', true)) act(b, () => api('DELETE', '/snapshots/' + b.dataset.snd), 'Snapshot eliminato').then(r => r && settingsUpdates()); });
}

/* --- Home Assistant e API ------------------------------------------------------------------ */

async function settingsApi() {
  let k;
  try { k = await api('GET', '/apikey'); } catch (e) { return pageError(e); }
  const url = `${location.protocol}//${location.host}/api/v1/status`;
  const slug = (S.about.hostname || 'nas').replace(/[^a-z0-9_]/gi, '_').toLowerCase();
  const yaml = `# /config/packages/${slug}.yaml
rest:
  - resource: ${url}
    scan_interval: 60
    headers:
      X-API-Key: !secret ${slug}_api_key
    sensor:
      - name: "${S.about.name} CPU"
        value_template: "{{ value_json.cpu_percent }}"
        unit_of_measurement: "%"
      - name: "${S.about.name} Memoria"
        value_template: "{{ value_json.memory_percent }}"
        unit_of_measurement: "%"
      - name: "${S.about.name} Temperatura"
        value_template: "{{ value_json.temperature_c }}"
        unit_of_measurement: "°C"
        device_class: temperature
      - name: "${S.about.name} Aggiornamenti"
        value_template: "{{ value_json.updates }}"
    binary_sensor:
      - name: "${S.about.name} Riavvio richiesto"
        value_template: "{{ value_json.reboot_required }}"
      - name: "${S.about.name} Dischi OK"
        value_template: >
          {{ value_json.disks | selectattr('health', 'in', ['guasto', 'attenzione']) | list | count == 0 }}`;
  const secret = `# /config/secrets.yaml\n${slug}_api_key: "${k.key}"`;
  settingsShell('api', 'Impostazioni', `
    <div class="card"><h3>${ic('key')}Chiave API</h3>
      <div class="linkbox"><input class="input" type="password" id="akey" value="${esc(k.key)}" readonly><button class="btn" id="ashow">${ic('eye')}</button><button class="btn" id="acopy">${ic('copy')}Copia</button><button class="btn danger" id="aregen">${ic('refresh')}Rigenera</button></div>
      <div class="subtle" style="margin-top:8px">Va nell'intestazione <span class="mono">X-API-Key</span>. Dà accesso solo in lettura allo stato del NAS.</div></div>
    <div class="card"><div class="row" style="margin-bottom:8px"><h3 style="margin:0">${ic('code')}Sensori per Home Assistant</h3><span class="grow"></span><button class="btn sm" id="ycopy">${ic('copy')}Copia il package</button><button class="btn sm" id="scopy">${ic('copy')}Copia il secret</button></div>
      <div class="subtle" style="margin-bottom:8px">Un package nuovo in <span class="mono">/config/packages/</span> e la chiave in <span class="mono">secrets.yaml</span>, poi riavvia Home Assistant.</div>
      <pre class="logbox" style="max-height:380px">${esc(yaml)}\n\n${esc(secret.replace(k.key, '••••••••'))}</pre></div>
    <div class="card"><h3>${ic('link')}Indirizzo</h3><div class="mono" style="font-size:13px;overflow-wrap:anywhere">GET ${esc(url)}</div>
      <div class="subtle" style="margin-top:6px">Risponde in JSON con nome, CPU, memoria, temperatura, aggiornamenti, stato dei dischi e dei backup.</div></div>
    <div class="card"><h3>${ic('bell')}Avvisi verso Home Assistant</h3><div class="subtle">In <a href="#settings/notify">Notifiche</a> attiva il webhook: il NAS manda un JSON con <span class="mono">title</span>, <span class="mono">message</span>, <span class="mono">level</span> ed <span class="mono">event</span>.</div></div>`);
  $('#ashow').onclick = () => { const i = $('#akey'); i.type = i.type === 'password' ? 'text' : 'password'; };
  $('#acopy').onclick = () => copyText(k.key);
  $('#ycopy').onclick = () => copyText(yaml);
  $('#scopy').onclick = () => copyText(secret);
  $('#aregen').onclick = async () => { if (await ask('Rigenerare la chiave?', 'Chi usa la chiave attuale (es. Home Assistant) smetterà di funzionare finché non metti quella nuova.', 'Rigenera', true)) act(null, () => api('POST', '/apikey/regenerate'), 'Nuova chiave creata').then(r => r && settingsApi()); };
}

/* --- Accesso sicuro (HTTPS) ------------------------------------------------------------------ */

async function settingsHttps() {
  let h;
  try { h = await api('GET', '/https'); } catch (e) { return pageError(e); }
  let mode = h.mode;
  const exp = t => new Date(t * 1000).toLocaleDateString(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' });
  const on = h.mode !== 'off' && h.caddy;
  const cert = h.cert;
  const host = `${h.hostname}.local`;
  settingsShell('https', 'Impostazioni', `
    <div class="card">
      ${on ? `<div class="cert"><div class="lock">${ic('lock')}</div><div style="flex:1;min-width:0"><b>Connessione protetta attiva</b><div class="muted" style="font-size:12.5px">${h.urls.map(esc).join(' · ')}${cert ? ' · certificato valido fino al ' + exp(cert.not_after) : ''}</div></div>
        ${h.mode !== 'custom' ? `<a class="btn sm" href="/certificato-casa.crt" download>${ic('download')}Scarica certificato</a>` : ''}</div>`
        : `<div class="cert" style="background:color-mix(in srgb,var(--warn) 9%,transparent)"><div class="lock" style="background:var(--warn)">${ic('lock')}</div><div style="flex:1"><b>${h.mode === 'off' ? 'HTTPS spento' : 'Caddy non è attivo'}</b><div class="muted" style="font-size:12.5px">${h.mode === 'off' ? 'Il NAS risponde solo in HTTP (non cifrato)' : 'Riprova a salvare: se il problema resta controlla il registro di Caddy'}</div></div></div>`}
      ${location.protocol === 'http:' && on ? `<div class="alert info" style="margin-top:12px">${ic('info')}<div>Stai usando la connessione non protetta. Apri <a href="https://${esc(location.hostname)}">https://${esc(location.hostname)}</a> dopo aver installato il certificato.</div></div>` : ''}
    </div>
    <div class="card"><h3>Tipo di certificato</h3><div class="grid" style="gap:10px">
      ${[['home', 'Certificato di casa (consigliato)', `${esc(S.about.name)} crea la sua autorità per la rete locale. Installi il certificato una volta su ogni dispositivo e il browser non mostra più avvisi.`],
        ['letsencrypt', 'Let\'s Encrypt', 'Certificato pubblico riconosciuto ovunque, per accedere da fuori casa con un tuo dominio (es. nas.miodominio.it). Si rinnova da solo. Servono le porte 80 e 443 aperte sul router verso il NAS.'],
        ['custom', 'Carica il tuo certificato', 'Se ne hai già uno (file .crt e .key in formato PEM).'],
        ['off', 'Nessuno (solo HTTP)', 'Sconsigliato: password e file viaggiano in chiaro nella rete.']].map(([v, t, d]) => `<div class="opt ${mode === v ? 'on' : ''}" data-mode="${v}"><span class="radio"></span><div><b>${t}</b><span>${d}</span></div></div>`).join('')}
      <div id="hle" class="cols2" ${mode === 'letsencrypt' ? '' : 'hidden'}><div class="field"><label>Dominio</label><input class="input" id="hdom" value="${esc(h.domain)}" placeholder="nas.miodominio.it"></div>
        <div class="field"><label>Email per gli avvisi di Let's Encrypt</label><input class="input" id="hmail" value="${esc(h.email)}" placeholder="tu@esempio.it"></div></div>
      <div id="hcus" ${mode === 'custom' ? '' : 'hidden'} class="grid" style="gap:10px">
        ${h.custom_cert ? `<div class="subtle">Caricato: <b>${esc(h.custom_cert.subject)}</b> · ${esc(h.custom_cert.names.join(', '))} · fino al ${exp(h.custom_cert.not_after)}</div>` : ''}
        <div class="cols2"><div class="field"><label>Certificato (.crt / .pem)</label><input class="input" type="file" id="hcrt" accept=".crt,.pem,.cer"></div>
          <div class="field"><label>Chiave privata (.key)</label><input class="input" type="file" id="hkey" accept=".key,.pem"></div></div>
        <div><button class="btn sm" id="hup">${ic('upload')}Carica</button></div></div>
    </div></div>
    <div class="card"><div class="list">
      <div class="item"><div class="grow"><div class="t">Apri sempre in HTTPS</div><div class="s">Chi apre http://${esc(host)} viene portato su https://</div></div><button class="toggle ${h.redirect ? 'on' : ''}" id="hred"></button></div>
      <div class="item"><div class="grow"><div class="t">HTTPS anche per le app</div><div class="s">jellyfin.${esc(host)}, immich.${esc(host)}… senza numeri di porta</div></div><button class="toggle ${h.app_subdomains ? 'on' : ''}" id="hsub"></button></div>
      ${h.apps.length ? `<div class="item" style="display:block"><div class="subtle" style="margin-bottom:6px">Indirizzi delle app:</div>${h.apps.map(a => `<div class="mono" style="font-size:12.5px"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.url)}</a> → porta ${a.port}</div>`).join('')}</div>` : ''}
    </div><div class="row" style="margin-top:12px"><span class="subtle grow">Le modifiche si applicano subito: Caddy si ricarica senza interrompere le app.</span><button class="btn primary" id="hsave">${ic('check')}Salva e applica</button></div></div>
    ${h.ca ? `<div class="card"><h3>${ic('download')}Installare il certificato di casa</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px;line-height:1.5">
      <div><b>Windows</b>: apri il file scaricato › Installa certificato › Computer locale › "Autorità di certificazione radice attendibili".</div>
      <div><b>Mac</b>: apri il file (Accesso Portachiavi), poi doppio clic sul certificato › Attendibilità › "Fidati sempre".</div>
      <div><b>iPhone e iPad</b>: apri il file con Safari, installa il profilo da Impostazioni, poi Generali › Info › Impostazioni certificati › attivalo.</div>
      <div><b>Android</b>: Impostazioni › Sicurezza › Crittografia e credenziali › Installa un certificato › Certificato CA.</div>
      <div class="subtle mono" style="overflow-wrap:anywhere">${esc(h.ca.subject)} · SHA-256 ${esc(h.ca.sha256)}</div>
      <div class="row" style="flex-wrap:wrap"><a class="btn sm" href="/certificato-casa.crt" download>${ic('download')}Scarica certificato</a><button class="btn sm" id="hrenew">${ic('refresh')}Rinnova il certificato del NAS</button></div></div></div>` : ''}`);
  $$('[data-mode]').forEach(o => o.onclick = () => { mode = o.dataset.mode; $$('[data-mode]').forEach(x => x.classList.toggle('on', x === o)); $('#hle').hidden = mode !== 'letsencrypt'; $('#hcus').hidden = mode !== 'custom'; });
  ['#hred', '#hsub'].forEach(id => $(id).onclick = e => e.currentTarget.classList.toggle('on'));
  $('#hsave').onclick = e => act(e.currentTarget, () => api('POST', '/https', { mode, redirect: $('#hred').classList.contains('on'), app_subdomains: $('#hsub').classList.contains('on'), domain: $('#hdom').value, email: $('#hmail').value }))
    .then(r => {
      if (!r) return;
      if (r.applied) toast('HTTPS aggiornato'); else toast('Salvato, ma Caddy non è ripartito: ' + (r.error || ''), 'bad', 9000);
      S.about.app_domain = r.app_subdomains && r.mode !== 'off' ? `${r.hostname}.local` : null;
      settingsHttps();
    });
  $('#hup').onclick = async e => {
    const f1 = $('#hcrt').files[0], f2 = $('#hkey').files[0];
    if (!f1 || !f2) return toast('Scegli entrambi i file', 'bad');
    act(e.currentTarget, async () => api('POST', '/https/upload', { cert: await f1.text(), key: await f2.text() }), 'Certificato caricato: ora premi "Salva e applica"').then(r => r && settingsHttps().then(() => { const o = $('[data-mode="custom"]'); if (o) o.click(); }));
  };
  const rn = $('#hrenew');
  if (rn) rn.onclick = e => act(e.currentTarget, () => api('POST', '/https/renew'), 'Certificato del NAS rinnovato').then(r => r && settingsHttps());
}


/* --- passaggio alla versione nuova di Ubuntu ------------------------------------------------- */

async function releaseCard() {
  const box = $('#relcard');
  if (!box) return;
  let r;
  try { r = await api('GET', '/release'); } catch (e) { box.innerHTML = ''; return; }
  const cur = r.current, up = r.upgrade || {}, nx = r.next;
  const ltsTxt = x => x.lts ? '<span class="badge ok">LTS · 5 anni di supporto</span>' : '<span class="badge warn">non LTS · 9 mesi di supporto</span>';
  let body = '';
  if (r.running) {
    body = `<div class="row"><span class="spin"></span><b>Passaggio a Ubuntu ${esc((up.target || {}).version || '')} in corso</b><span class="subtle">puoi chiudere la pagina: continua sul NAS</span></div>
      <pre class="logbox tall" id="rellog" style="margin-top:10px;max-height:340px"></pre>`;
  } else {
    const verify = r.verify && up.state === 'upgraded' ? `<div class="alert ${r.verify.ok ? 'info' : 'bad'}" style="margin-top:10px">${ic(r.verify.ok ? 'check' : 'alert')}<div style="flex:1"><b>Controlli dopo il passaggio: ${r.verify.ok ? 'tutto a posto' : 'ci sono problemi'}</b>
        <div class="list" style="margin-top:6px">${r.verify.checks.map(c => `<div class="row" style="font-size:12.5px;gap:6px">${ic(c.ok ? 'check' : 'x')}<span>${esc(c.name)}</span>${c.detail ? `<span class="subtle">· ${esc(c.detail)}</span>` : ''}</div>`).join('')}</div></div></div>` : '';
    const pendingReboot = up.state === 'upgraded' && r.pending_verify;
    const rollback = up.pre && (up.state === 'failed' || (up.state === 'upgraded' && r.verify && !r.verify.ok) || pendingReboot || (up.state === 'upgraded'));
    body = `<div class="row" style="flex-wrap:wrap;gap:12px"><div class="grow" style="min-width:220px"><div style="font-weight:650">${esc(cur.pretty.replace(/\s+LTS\b/, ''))} ${cur.lts ? '<span class="badge ok">LTS</span>' : ''}</div>
        <div class="subtle">${r.checked ? 'Controllato ' + esc(new Date(r.checked * 1000).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })) : 'Non ancora controllato'}${r.error ? ' · ' + esc(r.error) : ''}</div></div>
        <button class="btn sm" id="relchk">${ic('search')}Controlla</button></div>
      ${nx ? `<div class="relnext"><div class="grow"><b>È disponibile Ubuntu ${esc(nx.version)}${nx.name ? ' "' + esc(nx.name) + '"' : ''}</b> ${ltsTxt(nx)}
          <div class="subtle" style="margin-top:4px">${nx.lts ? 'Versione a lungo supporto: aggiornamenti di sicurezza per 5 anni.' : 'Versione intermedia: riceve aggiornamenti per 9 mesi, poi bisogna passare di nuovo alla successiva. Per un NAS che deve solo funzionare conviene restare sulla LTS.'}${nx.notes ? ` <a href="${esc(nx.notes)}" target="_blank" rel="noopener">Note di rilascio</a>` : ''}</div></div>
          <button class="btn primary" id="relgo">${ic('up')}Passa a Ubuntu ${esc(nx.version)}…</button></div>`
        : r.checked && !r.error ? '<div class="subtle" style="margin-top:8px">Non ci sono versioni più nuove: sei sull\'ultima.</div>' : ''}
      ${pendingReboot ? `<div class="alert info" style="margin-top:10px">${ic('restart')}<div style="flex:1"><b>Passaggio completato: riavvia per finire.</b> Dopo il riavvio il NAS controlla da solo che tutto funzioni.</div><button class="btn sm" id="relreboot">${ic('restart')}Riavvia ora</button></div>` : ''}
      ${up.state === 'failed' ? `<div class="alert bad" style="margin-top:10px">${ic('alert')}<div>Passaggio non riuscito${up.error ? ': ' + esc(up.error) : ''}. Il registro è qui sotto.</div></div>` : ''}
      ${up.state === 'rolled-back' ? `<div class="alert info" style="margin-top:10px">${ic('undo')}<div>Il sistema è stato riportato allo snapshot di prima del passaggio: riavvia il NAS se non l'hai già fatto.</div></div>` : ''}
      ${verify}
      ${rollback && up.state !== 'rolled-back' ? `<div class="row" style="margin-top:10px;flex-wrap:wrap"><button class="btn sm danger" id="relback">${ic('undo')}Torna alla versione di prima (snapshot #${esc(up.pre)})</button><span class="subtle">Serve un riavvio. I tuoi file e i dati delle app non cambiano.</span></div>` : ''}
      ${r.log_size ? '<details style="margin-top:10px"><summary class="subtle" style="cursor:pointer">Registro dell\'ultimo passaggio</summary><pre class="logbox tall" id="rellog" style="margin-top:8px;max-height:300px"></pre></details>' : ''}`;
  }
  box.innerHTML = `<div class="card"><h3>${ic('up')}Versione di Ubuntu</h3>${body}</div>`;
  const chk = $('#relchk', box);
  if (chk) chk.onclick = e => act(e.currentTarget, () => api('POST', '/release/check')).then(x => x && releaseCard());
  const go = $('#relgo', box);
  if (go) go.onclick = () => releaseDialog(r);
  const rb = $('#relreboot', box);
  if (rb) rb.onclick = () => powerAction('reboot');
  const bk = $('#relback', box);
  if (bk) bk.onclick = async e => {
    if (!await ask('Torna alla versione di prima', `Il sistema viene riportato allo snapshot #${up.pre} (prima del passaggio). Poi va riavviato. File e dati delle app non cambiano.`, 'Torna indietro', true)) return;
    const x = await act(e.currentTarget, () => api('POST', '/release/rollback'), 'Sistema riportato allo snapshot: riavvia il NAS');
    if (x) releaseCard();
  };
  const lg = $('#rellog', box);
  if (lg) followReleaseLog(lg, r.running);
}

async function followReleaseLog(box, running) {
  let off = 0;
  for (;;) {
    if (!box.isConnected) return;
    const x = await api('GET', '/release/log?offset=' + off).catch(() => null);
    if (x) {
      off = x.offset;
      if (x.text) { const atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 30; box.textContent += x.text; if (atEnd || running) box.scrollTop = box.scrollHeight; }
      if (running && !x.running) { await sleep(1000); releaseCard(); return; }
      if (!x.running) return;
    }
    await sleep(2000);
  }
}

function releaseDialog(r) {
  const nx = r.next;
  const lowSpace = r.free < r.min_free;
  const m = modal(`${mhead(`<div class="dicon">${ic('up')}</div>`, `Passa a Ubuntu ${esc(nx.version)}`, nx.lts ? 'Versione LTS · 5 anni di supporto' : 'Versione NON LTS · 9 mesi di supporto')}
    <div class="mb">
      ${nx.lts ? '' : `<div class="alert bad">${ic('alert')}<div><b>Non è una versione LTS.</b> Riceve aggiornamenti per circa 9 mesi: poi il NAS dovrà passare alla versione successiva, e così via ogni 6 mesi, finché non arriva la prossima LTS. Decidi tu.</div></div>`}
      <div style="display:grid;gap:7px;font-size:13px;color:var(--ink-2)">
        <div class="row">${ic(r.snapshots ? 'check' : 'alert')}${r.snapshots ? 'Prima: snapshot del sistema, per tornare indietro se qualcosa non va' : 'Snapshot non disponibili: non si potrà tornare indietro da qui'}</div>
        <div class="row">${ic(lowSpace ? 'alert' : 'check')}Spazio libero sul disco di sistema: ${bytes(r.free)} (ne servono almeno ${bytes(r.min_free)})</div>
        <div class="row">${ic('clock')}Durata: da 30 minuti a qualche ora. Il registro si segue in diretta; puoi chiudere la pagina.</div>
        <div class="row">${ic('restart')}Alla fine serve un riavvio; poi il NAS controlla da solo nome, HTTPS, Docker, servizi e interfaccia.</div>
        <div class="row">${ic('info')}Le app possono riavviarsi durante il passaggio. I tuoi file e i dati delle app non vengono toccati.</div>
      </div>
      <div class="field" style="margin-top:12px"><label>Per confermare scrivi la versione <code class="k">${esc(nx.version)}</code></label><input class="input" id="relconf" autocomplete="off" spellcheck="false" placeholder="${esc(nx.version)}"></div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="relok" ${lowSpace ? 'disabled' : ''}>${ic('up')}Passa a Ubuntu ${esc(nx.version)}</button></div>`);
  $('#relok', m).onclick = e => act(e.currentTarget, () => api('POST', '/release/start', { codename: nx.codename, confirm: $('#relconf', m).value })).then(x => { if (x) { closeModal(); releaseCard(); } });
}


/* --- aggiornamento del sistema con un pacchetto locale (.deb firmato) -------------------------- */

async function selfUpdateCard() {
  const box = $('#selfcard');
  if (!box) return;
  let r;
  let on = null;
  try { [r, on] = await Promise.all([api('GET', '/selfupdate'), api('GET', '/selfupdate/online').catch(() => null)]); } catch (e) { box.innerHTML = ''; return; }
  const p = r.pending, last = r.last;
  const lastTxt = last ? `<div class="alert ${last.ok ? 'info' : 'bad'}" style="margin-top:10px">${ic(last.ok ? 'check' : 'alert')}<div>${last.rollback ? 'Ritorno alla versione precedente' : 'Ultimo aggiornamento'} (${esc(new Date(last.t * 1000).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }))}): ${last.ok ? `riuscito, ${esc(last.from || '—')} → ${esc(last.to || '')}` : `non riuscito${last.error ? ' (' + esc(last.error) + ')' : ''}${last.rolled_back ? ': rimessa la versione di prima' : ''}`}</div></div>` : '';
  let body;
  if (r.running) {
    body = `<div class="row"><span class="spin"></span><b>Installazione in corso…</b><span class="subtle">puoi chiudere la pagina: l'interfaccia si riavvia da sola alla fine</span></div><pre class="logbox" id="sulog" style="margin-top:10px;max-height:300px"></pre>`;
  } else if (p) {
    body = `<div class="supkg"><div class="grow"><b>${esc(p.title || p.file)}</b> <span class="badge ${p.signed ? 'ok' : 'bad'}">${p.signed ? 'firmato' : 'non firmato'}</span>
        <div class="subtle">Versione <span class="mono">${esc(p.version)}</span> · installata <span class="mono">${esc(p.current || 'nessuna')}</span> · ${bytes(p.size)}${p.signed ? ' · chiave ' + esc(p.signature) : ' · ' + esc(p.signature)}</div>
        ${!p.newer ? `<div class="subtle" style="color:var(--warn)">${p.same ? 'È la stessa versione già installata.' : 'È una versione più vecchia di quella installata.'}</div>` : ''}
        ${p.notes ? `<details style="margin-top:6px"><summary class="subtle" style="cursor:pointer">Novità</summary><pre class="logbox" style="margin-top:6px;max-height:220px;white-space:pre-wrap">${esc(p.notes)}</pre></details>` : ''}</div>
      <div class="row" style="gap:6px"><button class="btn sm ghost" id="sudisc">${ic('x')}Togli</button><button class="btn sm primary" id="suinst" ${p.allowed ? '' : 'disabled'}>${ic('dl')}Installa</button></div></div>
      ${p.allowed ? '' : `<div class="alert bad" style="margin-top:8px">${ic('alert')}<div>Senza una firma valida il pacchetto non si installa. Per le prove puoi attivare la modalità sviluppatore qui sotto.</div></div>`}`;
  } else {
    body = `<div class="row" style="flex-wrap:wrap;gap:12px"><div class="grow" style="min-width:220px"><div style="font-weight:650">${esc(r.name)} ${esc(r.version || '')}</div><div class="subtle">Pacchetto <span class="mono">${esc(r.package_version || 'non installato come pacchetto')}</span></div></div>
      <button class="btn sm primary" id="suup">${ic('upload')}Carica aggiornamento…</button></div>
      <div class="subtle" style="margin-top:8px">Scegli insieme il file <span class="mono">.deb</span> e la sua firma <span class="mono">.deb.sig</span>. Prima di installare vedi versione, firma e novità; dopo, se l'interfaccia non riparte, si torna da soli alla versione di prima.</div>`;
  }
  let onl = '';
  if (on && !r.running && !p) {
    const ol = on.last;
    let st;
    if (!on.url) st = `<span class="subtle">Indirizzo del canale non impostato: l'aggiornamento online è spento.</span>`;
    else if (!ol) st = `<span class="subtle">Non ancora controllato.</span>`;
    else if (!ol.ok) st = `<span class="subtle" style="color:var(--warn)">${ic('alert')} ${esc(ol.error || 'Controllo non riuscito')}</span>`;
    else if (ol.available) st = `<div class="grow"><b>Disponibile: ${esc(r.name)} ${esc(ol.version || ol.package_version)}</b> <span class="badge ok">firmato</span>
        <div class="subtle">Pacchetto <span class="mono">${esc(ol.package_version)}</span>${ol.size ? ' · ' + bytes(ol.size) : ''}</div>
        ${ol.notes ? `<details style="margin-top:6px"><summary class="subtle" style="cursor:pointer">Novità</summary><pre class="logbox" style="margin-top:6px;max-height:220px;white-space:pre-wrap">${esc(ol.notes)}</pre></details>` : ''}</div>
      <button class="btn sm primary" id="onup">${ic('dl')}Aggiorna ora</button>`;
    else st = `<span class="subtle">${ic('check')} Il sistema è aggiornato.</span>`;
    const when = ol && ol.checked ? new Date(ol.checked * 1000).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
    onl = `<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line)">
      <div class="row" style="gap:8px;font-weight:650;margin-bottom:6px">${ic('globe')}<span>Aggiornamenti online</span></div>
      <div class="row" style="flex-wrap:wrap;gap:10px">${st}</div>
      <div class="row" style="margin-top:10px;flex-wrap:wrap;gap:10px;font-size:12.5px">
        <label class="row subtle" style="gap:6px">Canale <select class="input sm" id="onch" style="width:auto"><option value="stable">Stabile</option><option value="beta">Beta (prove)</option></select></label>
        <label class="row subtle" style="gap:6px">Quando c'è una versione nuova <select class="input sm" id="onmode" style="width:auto"><option value="notify">Avvisami</option><option value="nightly">Installa di notte</option><option value="off">Non controllare</option></select></label>
        <span class="grow"></span>${when ? `<span class="subtle">Controllato ${esc(when)}</span>` : ''}
        <button class="btn sm ghost" id="onurl">${ic('pencil')}Indirizzo…</button>
        <button class="btn sm" id="onchk" ${on.url ? '' : 'disabled'}>${ic('refresh')}Controlla ora</button></div></div>`;
  }
  box.innerHTML = `<div class="card"><h3>${ic('upload')}Aggiornamento di ${esc(r.name)}</h3>${body}${onl}${lastTxt}
    <div class="row" style="margin-top:12px;flex-wrap:wrap;gap:14px;font-size:12.5px">
      ${r.previous && !r.running ? `<button class="btn sm ghost" id="suback">${ic('undo')}Torna alla versione precedente</button>` : ''}
      <span class="subtle">${r.keys.length ? `Chiavi per le firme: ${r.keys.map(k => esc(k.name) + ' <span class="mono">' + esc(k.fingerprint) + '</span>').join(', ')}` : 'Nessuna chiave per le firme installata.'}</span>
      <span class="grow"></span><label class="row subtle" style="cursor:pointer"><button class="toggle ${r.devmode ? 'on' : ''}" id="sudev"></button>Modalità sviluppatore</label></div>
    <input type="file" id="sufile" accept=".deb,.sig" multiple hidden></div>`;
  if (onl) {
    const ch = $('#onch', box), md = $('#onmode', box);
    ch.value = on.channel; md.value = on.mode;
    const save = (d, msg) => act(null, () => api('POST', '/selfupdate/online', d), msg).then(() => selfUpdateCard());
    ch.onchange = e => { e.currentTarget.disabled = true; save({ channel: ch.value }, 'Canale salvato'); };
    md.onchange = e => { e.currentTarget.disabled = true; save({ mode: md.value }, 'Salvato'); };
    $('#onurl', box).onclick = async () => {
      const u = await prompt2('Indirizzo degli aggiornamenti', `Sito con i manifesti firmati (stable.json, beta.json). Lascia vuoto per usare quello predefinito${on.default_url ? ' (' + on.default_url + ')' : ''}.`, on.url === on.default_url ? '' : on.url, 'Salva');
      if (u === null || u === undefined) return;
      save({ url: u }, 'Indirizzo salvato');
    };
    $('#onchk', box).onclick = e => act(e.currentTarget, () => api('POST', '/selfupdate/online/check')).then(() => selfUpdateCard());
    const ou = $('#onup', box);
    if (ou) ou.onclick = async () => {
      if (!await ask(`Installare ${esc(on.last.version || on.last.package_version)}?`, 'Il pacchetto viene scaricato e controllato (firma e sha256). Prima viene fatto uno snapshot del sistema; durante l\'installazione l\'interfaccia si riavvia (la pagina si ricarica da sola). Le app e le condivisioni restano accese.', 'Aggiorna ora')) return;
      const x = await act(ou, () => api('POST', '/selfupdate/online/install'));
      if (x) selfUpdateCard();
    };
  }
  const up = $('#suup', box), file = $('#sufile', box);
  if (up) up.onclick = () => file.click();
  file.onchange = async () => {
    const files = [...file.files].sort((a, b) => (a.name.endsWith('.deb') ? 0 : 1) - (b.name.endsWith('.deb') ? 0 : 1));
    if (!files.some(f => f.name.endsWith('.deb'))) return toast('Scegli il file .deb (e la sua firma .sig)', 'bad');
    box.querySelector('.card').insertAdjacentHTML('beforeend', '<div class="row subtle" id="suprog" style="margin-top:10px"><span class="spin"></span><span>Carico…</span></div>');
    try {
      for (const f of files) {
        let off = 0;
        do {
          const blob = f.slice(off, Math.min(off + 8 * 1024 * 1024, f.size));
          const res = await fetch(`/api/selfupdate/upload?name=${encodeURIComponent(f.name)}&offset=${off}&total=${f.size}`, { method: 'PUT', headers: { 'X-Nido': '1' }, body: blob, credentials: 'same-origin' });
          const j = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(j.error || 'Errore ' + res.status);
          off += blob.size;
          $('#suprog span:last-child', box) && ($('#suprog span:last-child', box).textContent = `Carico ${f.name} · ${Math.floor(100 * off / (f.size || 1))}%`);
        } while (off < f.size);
      }
      await api('POST', '/selfupdate/inspect');
    } catch (e) { toast(e.message, 'bad', 8000); }
    selfUpdateCard();
  };
  const disc = $('#sudisc', box); if (disc) disc.onclick = () => act(null, () => api('POST', '/selfupdate/discard')).then(() => selfUpdateCard());
  const inst = $('#suinst', box);
  if (inst) inst.onclick = async () => {
    let confirm;
    if (!p.newer) {
      confirm = await prompt2('Installare comunque?', `La versione ${p.version} non è più nuova di quella installata. Per installarla scrivi INSTALLA`, '', 'Installa');
      if (!confirm) return;
    } else if (!await ask(`Installare ${p.version}?`, `Prima viene fatto uno snapshot del sistema. Durante l'installazione l'interfaccia si riavvia (la pagina si ricarica da sola); le app e le condivisioni restano accese.${p.signed ? '' : '<br><b>Il pacchetto NON è firmato</b> (modalità sviluppatore).'}`, 'Installa')) return;
    const x = await act(inst, () => api('POST', '/selfupdate/install', { confirm }));
    if (x) selfUpdateCard();
  };
  const back = $('#suback', box);
  if (back) back.onclick = async () => {
    if (!await ask('Torna alla versione precedente', `Viene reinstallato il pacchetto precedente (${esc(r.previous)}). L'interfaccia si riavvia.`, 'Torna indietro', true)) return;
    act(back, () => api('POST', '/selfupdate/rollback')).then(x => x && selfUpdateCard());
  };
  $('#sudev', box).onclick = async e => {
    const on = !e.currentTarget.classList.contains('on');
    if (on && !await ask('Modalità sviluppatore', 'Con la modalità sviluppatore il NAS installa anche pacchetti <b>senza firma</b>. Usala solo per le prove con pacchetti che hai costruito tu, poi spegnila.', 'Attiva', true)) return;
    act(null, () => api('POST', '/selfupdate/devmode', { enabled: on }), on ? 'Modalità sviluppatore attiva' : 'Modalità sviluppatore spenta').then(() => selfUpdateCard());
  };
  const lg = $('#sulog', box);
  if (lg) followSelfLog(lg);
}

async function followSelfLog(box) {
  let off = 0, fails = 0;
  for (;;) {
    if (!box.isConnected) return;
    // Durante l'installazione l'interfaccia si riavvia: per qualche secondo il NAS non risponde
    const x = await api('GET', '/selfupdate/log?offset=' + off, undefined, { timeout: 8000 }).catch(() => null);
    if (x) {
      fails = 0;
      off = x.offset;
      if (x.text) { box.textContent += x.text; box.scrollTop = box.scrollHeight; }
      if (!x.running) { await sleep(1500); location.reload(); return; }
    } else if (++fails > 3 && !box.dataset.restart) {
      box.dataset.restart = '1';
      box.textContent += '\n… l\'interfaccia si sta riavviando con la versione nuova …\n';
    }
    await sleep(2500);
  }
}
