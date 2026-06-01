// ═══ NABIRANJE ZALOGE — logika ═══
let ITEMS = [];           // vse postavke iz seje
let SESSION = null;       // celotna seja
let MARKET = 'slo';       // aktivni trg: 'slo' | 'rs'
const EXPANDED_KEY = 'zaloga_expanded';  // localStorage: kateri zavihki odprti (per naprava)

// market query suffix za fetch klice
function mq(extra) {
  const sep = extra && extra.includes('?') ? '&' : '?';
  return (extra || '') + sep + 'market=' + MARKET;
}

// ── Preklop trga ──
function switchMarket(m) {
  if (m === MARKET) return;
  MARKET = m;
  document.getElementById('mtab-slo').classList.toggle('active', m === 'slo');
  document.getElementById('mtab-rs').classList.toggle('active', m === 'rs');
  setExpanded({});  // počisti odprte zavihke ob preklopu
  lastUpdate = null;
  loadSession();
}

// ── Skupine ──
const GROUP_ORDER = (g) => {
  if (g.startsWith('Polica ')) return [0, g];
  if (/^P\d+$/.test(g)) return [1, parseInt(g.slice(1))];
  if (g === 'Paleta') return [2, 0];
  if (g === 'Pod Mizo') return [2, 1];
  if (g === 'Ikonka') return [2, 2];
  if (g === 'Amio') return [2, 3];
  if (g === 'Ni podatka') return [3, 0];
  return [2, g];
};

function getExpanded() {
  try { return JSON.parse(localStorage.getItem(EXPANDED_KEY) || '{}'); }
  catch(e) { return {}; }
}
function setExpanded(map) {
  try { localStorage.setItem(EXPANDED_KEY, JSON.stringify(map)); } catch(e) {}
}

// ── Nalaganje seje ──
async function loadSession() {
  try {
    const r = await fetch(mq('/zaloga-current'));
    const data = await r.json();
    if (data.ok && data.items && data.items.length) {
      SESSION = data;
      ITEMS = data.items;
      render();
      document.getElementById('archiveBtn').style.display = '';
      document.getElementById('globalStat').style.display = '';
    } else {
      showEmpty();
    }
  } catch(e) {
    showEmpty();
  }
}

function showEmpty() {
  ITEMS = [];
  document.getElementById('wrap').innerHTML = `
    <div class="empty-state" id="emptyState">
      <div class="icon">📋</div>
      <h2 style="color:var(--text-dim);font-weight:700">Ni aktivnega seznama</h2>
      <p style="margin-top:8px;font-size:13px">Naloži CSV izvoz za začetek nabiranja.</p>
    </div>`;
  document.getElementById('archiveBtn').style.display = 'none';
  document.getElementById('globalStat').style.display = 'none';
}

// ── Upload CSV ──
document.getElementById('csvInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  toast('⏳ Nalagam in obdelujem...');
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch(mq('/zaloga-upload'), { method: 'POST', body: fd });
    const data = await r.json();
    if (data.ok) {
      toast(`✓ Naloženih ${data.count} postavk`);
      await loadSession();
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(err) {
    toast('✗ ' + err.message);
  }
  e.target.value = '';
});

// ── Grupiraj postavke ──
function groupItems() {
  const groups = {};
  ITEMS.forEach(it => {
    (groups[it.group] = groups[it.group] || []).push(it);
  });
  // sortiraj postavke znotraj skupine po poziciji
  Object.values(groups).forEach(arr => arr.sort((a,b) => (a.poz||'').localeCompare(b.poz||'', 'sl', {numeric:true})));
  return groups;
}

// ── Render ──
function render() {
  const groups = groupItems();
  const expanded = getExpanded();
  const groupNames = Object.keys(groups).sort((a,b) => {
    const ga = GROUP_ORDER(a), gb = GROUP_ORDER(b);
    if (ga[0] !== gb[0]) return ga[0] - gb[0];
    if (typeof ga[1] === 'number' && typeof gb[1] === 'number') return ga[1] - gb[1];
    return String(ga[1]).localeCompare(String(gb[1]), 'sl', {numeric:true});
  });

  let html = '<div class="shelves">';
  groupNames.forEach(g => {
    const items = groups[g];
    const isOpen = !!expanded[g];
    const stat = groupStat(items);
    html += `
      <div class="shelf ${isOpen ? 'open' : ''}" id="shelf-${cssId(g)}">
        <div class="shelf-head" onclick="toggleShelf('${jsStr(g)}')">
          <span class="shelf-chevron">▶</span>
          <span class="shelf-name">${esc(g)}</span>
          <span class="shelf-count">${items.length} postavk</span>
          <div class="shelf-head-spacer"></div>
          <div class="shelf-prog">
            <div class="shelf-prog-bar prog-seg-wrap">${progBarSegments(stat)}</div>
            <span class="shelf-prog-pct" style="color:${stat.pctOk===100?'var(--ok)':'var(--text)'}">${stat.pctOk}%</span>
          </div>
        </div>
        <div class="shelf-body">
          <div class="item-head">
            <span>ID naročila</span><span>SKU</span><span>Pozicija</span>
            <span>Naziv</span><span class="h-qty">Količina</span><span class="h-status">Status</span>
          </div>
          ${items.map(it => itemRow(it)).join('')}
        </div>
      </div>`;
  });
  html += '</div>';

  // Sidebar (manjko + skupna statistika)
  html += renderSidebar();

  document.getElementById('wrap').innerHTML = html;
  updateGlobalStat();
}

function itemRow(it) {
  const cls = it.status === 'ok' ? 'ok' : it.status === 'ni' ? 'ni' : '';
  const mismatch = it.picked !== it.qty ? 'qty-mismatch' : '';
  return `
    <div class="item ${cls}" id="item-${it.idx}">
      <span class="id-col">${esc(it.id || '—')}</span>
      <div class="item-mobile-top">
        <span class="sku">${esc(it.sku)}</span>
        <span class="poz">${esc(it.poz)}</span>
      </div>
      <span class="naziv" title="${esc(it.naziv)}">${esc(it.naziv)}${it.low ? '<span class="tag-low">Nizka zaloga</span>' : ''}</span>
      <div class="item-bottom">
        <div class="qty-step ${mismatch}">
          <button class="qty-btn" onclick="changeQty(${it.idx}, -1)">−</button>
          <div style="display:flex;flex-direction:column;align-items:center" onclick="editQty(${it.idx})" title="Klikni za vnos števila">
            <span class="qty-val" id="qtyval-${it.idx}">${it.picked}</span>
            <span class="qty-need">/ ${it.qty}</span>
          </div>
          <button class="qty-btn" onclick="changeQty(${it.idx}, 1)">+</button>
        </div>
        <div class="item-actions">
          <button class="act-btn act-ok ${it.status==='ok'?'active':''}" onclick="setStatus(${it.idx}, 'ok')" title="Nabrano">✓</button>
          <button class="act-btn act-ni ${it.status==='ni'?'active':''}" onclick="setStatus(${it.idx}, 'ni')" title="Ni na zalogi">✕</button>
        </div>
      </div>
    </div>`;
}

// ── Direkten vnos količine (klik na cifro) ──
function editQty(idx) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  const span = document.getElementById('qtyval-' + idx);
  if (!span || span.querySelector('input')) return;  // že v urejanju
  const cur = it.picked;
  // Zamenjaj span vsebino z inputom
  span.innerHTML = `<input type="number" inputmode="numeric" value="${cur}" min="0"
    style="width:64px;text-align:center;font-size:20px;font-weight:800;padding:4px;border:2px solid var(--accent);border-radius:8px;background:var(--panel);color:var(--text);font-family:inherit"
    onclick="event.stopPropagation()" onkeydown="if(event.key==='Enter')this.blur()" onblur="commitQty(${idx}, this.value)">`;
  const inp = span.querySelector('input');
  inp.focus();
  inp.select();
}

function commitQty(idx, val) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  let n = parseInt(val);
  if (isNaN(n) || n < 0) n = 0;
  it.picked = n;
  refreshItem(it);
  refreshSidebarAndStats();
  saveItem(idx, { picked: it.picked });
}

// ── Statistika skupine ──
function groupStat(items) {
  const total = items.length;
  const ok = items.filter(it => it.status === 'ok').length;
  const ni = items.filter(it => it.status === 'ni').length;
  const todo = total - ok - ni;
  const done = ok + ni;
  // odstotki (zaokroženi tako da vsota = 100)
  const pctOk = total ? Math.round(ok / total * 100) : 0;
  const pctNi = total ? Math.round(ni / total * 100) : 0;
  const pctTodo = total ? (100 - pctOk - pctNi) : 0;
  const pct = total ? Math.round(done / total * 100) : 0;  // skupno obdelano (compat)
  return { total, done, ok, ni, todo, pct, pctOk, pctNi, pctTodo };
}

// ── Tekstovni razrez (npr. "90% nabrano · 5% ni najdeno · 5% še nabirajo") ──
function statBreakdownText(s) {
  if (!s.total) return '';
  const parts = [];
  if (s.pctOk > 0) parts.push(`${s.pctOk}% nabrano`);
  if (s.pctNi > 0) parts.push(`${s.pctNi}% ni najdeno`);
  if (s.pctTodo > 0) parts.push(`${s.pctTodo}% še nabirajo`);
  return parts.join(' · ');
}

// ── Segmentiran bar (zeleno / rdeče / sivo) ──
function progBarSegments(s) {
  return `
    <div class="prog-seg prog-seg-ok" style="width:${s.pctOk}%"></div>
    <div class="prog-seg prog-seg-ni" style="width:${s.pctNi}%"></div>
    <div class="prog-seg prog-seg-todo" style="width:${s.pctTodo}%"></div>`;
}

// ── Sidebar ──
function renderSidebar() {
  const manko = ITEMS.filter(it => it.status === 'ni' || (it.status === 'ok' && it.picked < it.qty));
  const totalOk = ITEMS.filter(it => it.status === 'ok').length;
  const totalNi = ITEMS.filter(it => it.status === 'ni').length;
  const totalDone = totalOk + totalNi;
  const totalQtyNeed = ITEMS.reduce((s,it) => s + it.qty, 0);
  const totalQtyPicked = ITEMS.filter(it=>it.status==='ok').reduce((s,it) => s + it.picked, 0);

  let mankoHtml;
  if (manko.length === 0) {
    mankoHtml = '<div class="manko-empty">Zaenkrat ni manjkajočih postavk 🎉</div>';
  } else {
    mankoHtml = manko.map(it => {
      const missingQty = it.status === 'ni' ? it.qty : (it.qty - it.picked);
      return `
        <div class="manko-item">
          <div class="top">
            <span class="msku">${esc(it.sku)}</span>
            <span class="mqty">manjka ${missingQty}${it.status==='ni'?' (cela)':''}</span>
          </div>
          <div class="mnaziv" title="${esc(it.naziv)}">${esc(it.naziv)}</div>
          <div class="mpoz-badge">📍 ${esc(it.poz)}</div>
          <div class="mpoz-detail">potrebno ${it.qty} · nabrano ${it.status==='ni'?0:it.picked}</div>
        </div>`;
    }).join('');
  }

  return `
    <div class="sidebar">
      <div class="side-card">
        <h3>📊 Skupna statistika</h3>
        <div class="stat-rows">
          <div class="stat-row"><span class="lbl">Vseh postavk</span><span class="val">${ITEMS.length}</span></div>
          <div class="stat-row"><span class="lbl">Obdelanih</span><span class="val">${totalDone}</span></div>
          <div class="stat-row"><span class="lbl">Nabrano (OK)</span><span class="val ok">${totalOk}</span></div>
          <div class="stat-row"><span class="lbl">Manjka (NI)</span><span class="val ni">${totalNi}</span></div>
          <div class="stat-row" style="border-top:1px solid var(--border);padding-top:10px;margin-top:2px">
            <span class="lbl">Kosov nabrano</span><span class="val">${totalQtyPicked} / ${totalQtyNeed}</span></div>
        </div>
      </div>
      <div class="side-card">
        <h3>⚠️ Manjko ${manko.length ? `<span class="badge">${manko.length}</span>` : ''}</h3>
        <div class="manko-list">${mankoHtml}</div>
      </div>
    </div>`;
}

// ── Global stat (top ring) ──
function updateGlobalStat() {
  const stat = groupStat(ITEMS);
  const ring = document.getElementById('globalRing');
  const circ = 2 * Math.PI * 18; // 113
  // ring kaže delež NABRANO (zeleno)
  if (ring) ring.style.strokeDashoffset = circ * (1 - stat.pctOk/100);
  const pctEl = document.getElementById('globalPct');
  if (pctEl) {
    pctEl.textContent = stat.pctOk + '%';
    pctEl.style.color = stat.pctOk===100 ? 'var(--ok)' : 'var(--text)';
  }
  const doneEl = document.getElementById('globalDone');
  if (doneEl) doneEl.textContent = `${stat.done} / ${stat.total}`;
  const breakEl = document.getElementById('globalBreak');
  if (breakEl) breakEl.textContent = statBreakdownText(stat) || 'skupna uspešnost';
}

// ── Toggle zavihek (persist per naprava) ──
function toggleShelf(g) {
  const expanded = getExpanded();
  expanded[g] = !expanded[g];
  if (!expanded[g]) delete expanded[g];
  setExpanded(expanded);
  const el = document.getElementById('shelf-' + cssId(g));
  if (el) el.classList.toggle('open');
}

// ── Spremeni količino ──
function changeQty(idx, delta) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  it.picked = Math.max(0, it.picked + delta);
  // posodobi samo to vrstico (brez polnega re-renderja, da ne zapre zavihka)
  refreshItem(it);
  refreshSidebarAndStats();
  saveItem(idx, { picked: it.picked });
}

// ── Status OK/NI ──
function setStatus(idx, status) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  // toggle: če že isti status, prekliči
  it.status = (it.status === status) ? '' : status;
  refreshItem(it);
  refreshShelfProgress(it.group);
  refreshSidebarAndStats();
  updateGlobalStat();
  saveItem(idx, { status: it.status });
}

// ── Osveži eno vrstico (in-place) ──
function refreshItem(it) {
  const el = document.getElementById('item-' + it.idx);
  if (!el) return;
  el.outerHTML = itemRow(it);
}

// ── Osveži progress bar zavihka ──
function refreshShelfProgress(group) {
  const groups = groupItems();
  const items = groups[group] || [];
  const stat = groupStat(items);
  const shelf = document.getElementById('shelf-' + cssId(group));
  if (!shelf) return;
  const bar = shelf.querySelector('.shelf-prog-bar');
  const pct = shelf.querySelector('.shelf-prog-pct');
  if (bar) bar.innerHTML = progBarSegments(stat);
  if (pct) { pct.textContent = stat.pctOk + '%'; pct.style.color = stat.pctOk===100 ? 'var(--ok)' : 'var(--text)'; }
}

// ── Osveži sidebar ──
function refreshSidebarAndStats() {
  const sb = document.querySelector('.sidebar');
  if (sb) {
    const tmp = document.createElement('div');
    tmp.innerHTML = renderSidebar();
    sb.replaceWith(tmp.firstElementChild);
  }
}

// ── Live save na disk ──
async function saveItem(idx, patch) {
  try {
    await fetch('/zaloga-update-item', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ idx, market: MARKET, ...patch })
    });
  } catch(e) { /* tiho — nabiralec ne sme biti moten */ }
}

// ── Arhiviraj ──
async function archiveSession() {
  if (!confirm('Arhiviram trenutno nabiranje?\n\nSeznam se zaključi in shrani v zgodovino. Nov CSV lahko naložiš za novo nabiranje.')) return;
  try {
    const r = await fetch('/zaloga-archive', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ market: MARKET })
    });
    const data = await r.json();
    if (data.ok) {
      toast('✓ Arhivirano');
      setExpanded({});  // počisti odprte zavihke
      showEmpty();
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(e) { toast('✗ ' + e.message); }
}

// ── Pomožne ──
function esc(s) { return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function jsStr(s) { return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }
function cssId(s) { return String(s).replace(/[^a-zA-Z0-9]/g, '_'); }

let toastTimer;
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

// ── Auto-refresh (sync med napravami) — vsakih 15s preberi disk ──
let lastUpdate = null;
async function pollSync() {
  if (!ITEMS.length) return;
  try {
    const r = await fetch(mq('/zaloga-current'));
    const data = await r.json();
    if (data.ok && data.updated_at && data.updated_at !== lastUpdate) {
      lastUpdate = data.updated_at;
      // posodobi samo statuse/picked (ne uniči odprtih zavihkov)
      let changed = false;
      data.items.forEach(srv => {
        const local = ITEMS.find(x => x.idx === srv.idx);
        if (local && (local.status !== srv.status || local.picked !== srv.picked)) {
          local.status = srv.status; local.picked = srv.picked;
          refreshItem(local); changed = true;
        }
      });
      if (changed) {
        // osveži vse progress bare + sidebar
        [...new Set(ITEMS.map(i=>i.group))].forEach(refreshShelfProgress);
        refreshSidebarAndStats();
        updateGlobalStat();
      }
    }
  } catch(e) {}
}

// ═══ ZGODOVINA ═══
async function openHistory() {
  const ov = document.getElementById('histOverlay');
  ov.classList.add('show');
  const body = document.getElementById('histBody');
  body.innerHTML = '<div class="hist-empty">⏳ Nalagam...</div>';
  try {
    const r = await fetch(mq('/zaloga-history'));
    const data = await r.json();
    if (!data.ok || !data.sessions || !data.sessions.length) {
      body.innerHTML = '<div class="hist-empty">Ni arhiviranih nabiranj.</div>';
      return;
    }
    body.innerHTML = data.sessions.map(histSessRow).join('');
  } catch(e) {
    body.innerHTML = '<div class="hist-empty">✗ Napaka pri nalaganju.</div>';
  }
}

function closeHistory() {
  document.getElementById('histOverlay').classList.remove('show');
}

function histDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('sl-SI', {day:'2-digit',month:'2-digit',year:'numeric'}) +
      ' · ' + d.toLocaleTimeString('sl-SI', {hour:'2-digit',minute:'2-digit'});
  } catch(e) { return iso; }
}

function histSessRow(s) {
  return `
    <div class="hist-sess" id="hsess-${cssId(s.filename)}">
      <div class="hist-sess-top">
        <span class="hist-sess-date">${histDate(s.archived_at)}</span>
        <div class="hist-sess-prog"><div style="width:${s.pct}%"></div></div>
        <span class="hist-sess-pct" style="color:${s.pct===100?'var(--ok)':'var(--text)'}">${s.pct}%</span>
      </div>
      <div class="hist-sess-meta">
        <span>Postavk: <b>${s.total}</b></span>
        <span class="ok">Nabrano: <b>${s.ok}</b></span>
        <span class="ni">Manjka: <b>${s.ni}</b></span>
        <span>Kosov: <b>${s.qty_picked} / ${s.qty_need}</b></span>
      </div>
      <div class="hist-sess-actions">
        <button class="open" onclick="histToggleDetail('${jsStr(s.filename)}')">📋 Podrobnosti</button>
        <button class="del" onclick="histDelete('${jsStr(s.filename)}')">🗑 Izbriši</button>
      </div>
      <div class="hist-detail" id="hdet-${cssId(s.filename)}" style="display:none"></div>
    </div>`;
}

async function histToggleDetail(filename) {
  const det = document.getElementById('hdet-' + cssId(filename));
  if (!det) return;
  if (det.style.display !== 'none') { det.style.display = 'none'; det.innerHTML = ''; return; }
  det.style.display = 'block';
  det.innerHTML = '<div style="padding:10px 0;color:var(--text-dim);font-size:12px">⏳ Nalagam...</div>';
  try {
    const r = await fetch(mq('/zaloga-history/' + encodeURIComponent(filename)));
    const data = await r.json();
    if (!data.ok || !data.items) { det.innerHTML = '<div style="padding:8px 0;color:var(--text-dim)">Ni podatkov.</div>'; return; }
    det.innerHTML = data.items.map(it => {
      const st = it.status === 'ok' ? '<span class="hst-ok">✓ OK</span>'
        : it.status === 'ni' ? '<span class="hst-ni">✕ NI</span>' : '—';
      return `<div class="hist-detail-row">
        <span class="hsku">${esc(it.sku)}</span>
        <span class="hnaziv" title="${esc(it.naziv)}">${esc(it.naziv)}</span>
        <span class="hpoz">${esc(it.poz)}</span>
        <span class="hqty">${it.status==='ok'?it.picked:0} / ${it.qty}</span>
        <span>${st}</span>
      </div>`;
    }).join('');
  } catch(e) {
    det.innerHTML = '<div style="padding:8px 0;color:var(--ni)">✗ Napaka.</div>';
  }
}

async function histDelete(filename) {
  if (!confirm('Izbrišem to arhivirano nabiranje?\n\nDejanje je nepovratno.')) return;
  try {
    const r = await fetch(mq('/zaloga-history/' + encodeURIComponent(filename)), { method: 'DELETE' });
    const data = await r.json();
    if (data.ok) {
      const el = document.getElementById('hsess-' + cssId(filename));
      if (el) el.remove();
      toast('✓ Izbrisano');
      const body = document.getElementById('histBody');
      if (body && !body.querySelector('.hist-sess')) {
        body.innerHTML = '<div class="hist-empty">Ni arhiviranih nabiranj.</div>';
      }
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(e) { toast('✗ ' + e.message); }
}

// ── Init ──
loadSession();
setInterval(pollSync, 15000);
