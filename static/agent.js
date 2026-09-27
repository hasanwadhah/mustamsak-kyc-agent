/* The KYC agent screen: capture check → upload (or a fictional demo file) → live reading →
   decision with confidence, cross-document checks and a reviewer summary; plus "How it works" and
   the evaluation report. Uses the app's API only (app/main.py, app/agent_api.py, app/kyc.py).
   Every text from the server is set with textContent (never as HTML). */
'use strict';
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
// The address as opened (?batch=, ?lang=, ?tour=), kept before showView tidies the address bar.
const START_PARAMS = new URLSearchParams(location.search);
let lang = (() => {
  const asked = new URLSearchParams(location.search).get('lang');  // ?lang=ar opens the Arabic screen
  if (asked === 'ar' || asked === 'en') return asked;
  try { return localStorage.getItem('agentLang') || 'en'; } catch { return 'en'; }
})();
const t = (key, ...args) => { const v = I18N[lang][key] ?? I18N.en[key]; return typeof v === 'function' ? v(...args) : v; };
const pick = (obj, key) => (lang === 'en' ? obj[key + '_en'] : obj[key]) ?? obj[key] ?? obj[key + '_en'] ?? '';
const pct = v => (v == null ? '—' : `${Math.round(v * 100)}%`);
const pct1 = v => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
// One stroke icon set (24×24, Lucide-style outlines drawn for this app). Status is never shown by colour alone.
const ICONS = {
  check: 'M20 6 9 17l-5-5', x: 'M18 6 6 18M6 6l12 12', minus: 'M5 12h14', plus: 'M12 5v14M5 12h14',
  alert: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4',
  lock: 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4', users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8',
  userCheck: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM16 11l2 2 4-4',
  userX: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM17 8l5 5M22 8l-5 5',
  calendarX: 'M3 5h18v16H3zM16 3v4M8 3v4M3 10h18M10 13l4 4M14 13l-4 4',
  calendarCheck: 'M3 5h18v16H3zM16 3v4M8 3v4M3 10h18M9 15l2 2 4-4',
  card: 'M2 5h20v14H2zM6 10h5M6 14h8M15 9h3v5h-3z', camera: 'M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  layers: 'M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5', scan: 'M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 12h10',
  crop: 'M6 2v14a2 2 0 0 0 2 2h14M18 22V8a2 2 0 0 0-2-2H2', text: 'M4 7V4h16v3M9 20h6M12 4v16',
  link: 'M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7',
  unlink: 'M18.8 13.3l1.4-1.4a4 4 0 0 0-5.7-5.7l-1.4 1.4M5.2 10.7l-1.4 1.4a4 4 0 0 0 5.7 5.7l1.4-1.4M8 2v3M2 8h3M16 22v-3M22 16h-3',
  gauge: 'M12 14l4-4M3.3 19a10 10 0 1 1 17.4 0z', landmark: 'M3 22h18M6 18v-7M10 18v-7M14 18v-7M18 18v-7M12 2l9 5H3z',
  sun: 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4',
  hand: 'M9 11V5.5a1.5 1.5 0 0 1 3 0V10M12 10V4.5a1.5 1.5 0 0 1 3 0V10M15 10V6.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-7 7h-.5a6 6 0 0 1-5-2.7L3.3 15a1.5 1.5 0 0 1 2.5-1.7L9 16',
  fileCheck: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 15l2 2 4-4',
  printer: 'M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z',
  download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3', copy: 'M9 9h12v12H9zM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1',
  arrow: 'M5 12h14M13 6l6 6-6 6', target: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  flask: 'M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3M7 15h10', clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2',
};
function icon(name, cls = '') {
  const NS = 'http://www.w3.org/2000/svg', svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('class', `i ${cls}`.trim()); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(NS, 'path'); path.setAttribute('d', ICONS[name] || ICONS.info); svg.append(path);
  return svg;
}
// Static markup marks icon spots with <span data-icon="name">; they are filled once on load.
$$('[data-icon]').forEach(s => s.replaceWith(icon(s.dataset.icon, s.dataset.icon === 'arrow' ? 'flip-rtl' : '')));
// Loading state for a button that starts slow work: keeps its size, shows a spinner, blocks double clicks.
function busy(btn, on) { if (on) btn.setAttribute('aria-busy', 'true'); else btn.removeAttribute('aria-busy'); btn.disabled = on; }
function chipIcon(cls, iconName, text) { const c = el('span', `chip ${cls}`); c.append(icon(iconName), el('span', null, text)); return c; }
async function api(path, options) {
  const r = await fetch(path, options);
  if (!r.ok) { let d; try { d = await r.json(); } catch {} throw Error(typeof d?.detail === 'string' ? d.detail : `${t('uploadFailed')} (${r.status})`); }
  return (r.headers.get('content-type') || '').includes('json') ? r.json() : r;
}
let toastTimer;
function toast(text, error = false) {
  const box = $('#toast'); box.textContent = text; box.className = error ? 'error' : ''; box.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (box.hidden = true), 5000);
}
const state = { files: [], checks: [], batch: null, kyc: null, demos: [], evaluation: null, poll: null };

/* ---------------------------------------------------------------- language & views */
function applyLanguage() {
  document.documentElement.lang = lang; document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  $$('[data-t]').forEach(e => { e.textContent = t(e.dataset.t); });
  $('#langToggle').textContent = lang === 'ar' ? 'English' : 'عربي';
  $('#langToggle').lang = lang === 'ar' ? 'en' : 'ar';
  document.title = `${t('brand')} · ${t('brandSub')}`;
  renderStatic(); renderDemos(); renderPrecheck(); renderProof();
  if (state.kyc) renderDecision();
  if (state.evaluation) renderEvaluation();
}
$('#langToggle').onclick = () => { lang = lang === 'ar' ? 'en' : 'ar'; try { localStorage.setItem('agentLang', lang); } catch {} applyLanguage(); };
function showView(view) {
  $$('.view').forEach(v => (v.hidden = v.id !== `view-${view}`));
  $$('.view-tab').forEach(b => { b.classList.toggle('active', b.dataset.view === view); b.toggleAttribute('aria-current', b.dataset.view === view); });
  if (view === 'eval' && !state.evaluation) loadEvaluation();
  // A tab click adds a history entry, so Back returns to the previous view.
  if (location.hash !== `#${view}` && !(view === 'onboard' && !location.hash)) {
    if (view === 'onboard') history.pushState(null, '', location.pathname); else history.pushState(null, '', `#${view}`);
  }
  if (location.search) history.replaceState(null, '', location.pathname + location.hash);
}
$$('.view-tab').forEach(b => (b.onclick = () => showView(b.dataset.view)));
// Deep links and the Back button: #how and #eval open those views.
addEventListener('hashchange', () => { const v = location.hash.slice(1); showView(['how', 'eval'].includes(v) ? v : 'onboard'); });
function showStage(stage) {
  ['upload', 'read', 'decide'].forEach(s => ($(`#stage-${s}`).hidden = s !== stage));
  const order = ['upload', 'read', 'decide'];
  $$('.stepper li').forEach(li => {
    const i = order.indexOf(li.dataset.step), current = order.indexOf(stage);
    li.classList.toggle('current', i === current); li.classList.toggle('done', i < current);
    if (i === current) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function renderStatic() {
  const tips = $('#tips'); tips.replaceChildren();
  const tipIcons = ['landmark', 'unlink', 'scan', 'sun', 'hand', 'layers', 'fileCheck'];
  t('tips').forEach(([title, text], i) => {
    const li = el('li'), badge = el('span', 'tip-icon'); badge.append(icon(tipIcons[i] || 'info'));
    li.append(badge, el('b', null, title), el('span', null, text)); tips.append(li);
  });
  const pipe = $('#pipeline'); pipe.replaceChildren();
  const pipeIcons = ['camera', 'crop', 'card', 'text', 'calendarCheck', 'link', 'gauge', 'userCheck'];
  t('pipeline').forEach(([title, text], i) => {
    const li = el('li'), top = el('div', 'pipe-top'), badge = el('span', 'pipe-icon'); badge.append(icon(pipeIcons[i] || 'info'));
    top.append(badge, el('span', 'num', String(i + 1).padStart(2, '0'))); li.append(top, el('b', null, title), el('p', null, text)); pipe.append(li);
  });
  for (const [id, key, mark] of [['#rules', 'rules', 'check'], ['#scope', 'scope', 'minus']]) {
    $(id).replaceChildren(...t(key).map(x => { const li = el('li'); li.append(icon(mark), el('span', null, x)); return li; }));
  }
}

/* ---------------------------------------------------------------- choosing files + capture check */
const drop = $('#dropzone');
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); chooseFiles([...e.dataTransfer.files]); });
$('#fileInput').onchange = e => { chooseFiles([...e.target.files]); e.target.value = ''; };
$('#clearFiles').onclick = () => { state.files.forEach(f => f.url && URL.revokeObjectURL(f.url)); state.files = []; renderPrecheck(); };

async function chooseFiles(files) {
  files = files.filter(f => /^image\//.test(f.type) || /\.pdf$/i.test(f.name)).slice(0, 20);
  if (!files.length) return;
  state.files.forEach(f => f.url && URL.revokeObjectURL(f.url));
  state.files = files.map(file => ({ file, url: /^image\//.test(file.type) ? URL.createObjectURL(file) : null, check: null }));
  renderPrecheck();
  await Promise.all(state.files.map(async item => {
    const form = new FormData(); form.append('file', item.file);
    try { item.check = await api('/api/capture-check', { method: 'POST', body: form }); } catch (e) { item.check = { error: e.message }; }
    renderPrecheck();
  }));
}
function renderPrecheck() {
  const box = $('#precheck'), list = $('#precheckList');
  box.hidden = !state.files.length; list.replaceChildren();
  state.files.forEach(item => {
    const li = el('li', 'file-item');
    const thumb = el('div', 'thumb');
    if (item.url) { const img = el('img'); img.src = item.url; img.alt = ''; thumb.append(img); } else thumb.textContent = 'PDF';
    const info = el('div', 'grow'); info.append(el('b', null, item.file.name));
    const c = item.check;
    let chip;
    if (!c) chip = el('span', 'chip neutral', t('checking'));
    else if (c.error) chip = el('span', 'chip bad', c.error);
    else {
      const issues = (c.documents || []).flatMap(d => d.issues || []);
      const warn = issues.some(i => i.severity === 'warn');
      chip = el('span', `chip ${c.retake ? 'bad' : warn ? 'warn' : 'good'}`, c.retake ? t('photoRetake') : warn ? t('photoWarn') : t('photoOk'));
      info.append(el('small', 'muted', t('docsInPhoto', (c.documents || []).length)));
      const advice = [...new Set(issues.filter(i => i.severity !== 'info').map(i => pick(i, 'message')))].slice(0, 3);
      if (advice.length) { const ul = el('ul', 'advice'); advice.forEach(a => ul.append(el('li', null, a))); info.append(ul); }
    }
    li.append(thumb, info, chip); list.append(li);
  });
}
$('#readFiles').onclick = async () => {
  if (!state.files.length) return;
  const form = new FormData(); state.files.forEach(f => form.append('files', f.file, f.file.name));
  state.expected = state.files.length;
  busy($('#readFiles'), true);
  try { await startReading(() => api('/api/batches', { method: 'POST', body: form })); } finally { busy($('#readFiles'), false); }
};

/* ---------------------------------------------------------------- demo files */
async function loadDemos() {
  try { state.demos = (await api('/api/demo/cases')).cases; } catch { state.demos = []; }
  renderDemos();
}
// Every demo case is one scripted story (scripts/synthetic_kyc.py DEMO_PLAN). The card says what was
// planted in it, never what the agent will decide: the decision is always computed live.
const PROBLEM_ICON = { name_mismatch: 'userX', expired_license: 'calendarX', serial_mismatch: 'card' };
function scenario(c) {
  if (c.problem) return { tone: 'bad', title: t('scn')[c.problem] || c.problem, sub: t('scnPlantedSub'), chip: ['bad', PROBLEM_ICON[c.problem] || 'alert', t('planted', t('problems')[c.problem] || c.problem)] };
  if (c.worst_level === 'worst') return { tone: 'warn', title: t('demoWorst'), sub: t('demoWorstSub'), chip: ['warn', 'camera', t('nothingPlanted')] };
  if (c.worst_level === 'poor') return { tone: 'warn', title: t('scnPoor'), sub: t('scnPoorSub'), chip: ['neutral', 'minus', t('nothingPlanted')] };
  return { tone: 'good', title: t('demoConsistent'), sub: t('scnGoodSub'), chip: ['good', 'check', t('nothingPlanted')] };
}
function startDemo(c, mode) {
  state.expected = mode === 'pile' ? 1 : c.files.length;
  startReading(() => api(`/api/demo/cases/${encodeURIComponent(c.id)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) }));
}
function demoCard(cls, file, onclick) {
  const b = el('button', `demo-card ${cls}`); b.type = 'button'; b.onclick = onclick;
  const thumb = el('span', 'demo-thumb'), img = el('img'); img.alt = ''; img.loading = 'lazy'; img.src = `/api/demo/files/${encodeURIComponent(file)}`;
  thumb.append(img); b.append(thumb); return b;
}
function renderDemos() {
  const box = $('#demos'); if (!box) return; box.replaceChildren();
  const cases = state.demos;
  if (!cases.length) { box.append(el('p', 'muted', 'No demo files. Run scripts/synthetic_kyc.py --split demo --clean-copies and scripts/demo_pile.py.')); return; }
  // Featured: the whole file in one photo (the tour points at this card: .demo-card.tone-info).
  const pile = cases.find(c => c.pile && !c.problem) || cases.find(c => c.pile);
  if (pile) {
    const b = demoCard('featured tone-info', pile.pile, () => startDemo(pile, 'pile'));
    const text = el('span', 'demo-text'); text.append(el('b', null, t('demoPile')), el('small', null, t('demoOnePhoto')));
    const steps = el('span', 'featured-steps');
    [['scan', 0], ['crop', 1], ['layers', 2]].forEach(([name, i]) => { const s = el('span'); s.append(icon(name), el('span', null, t('pileSteps')[i])); steps.append(s); });
    text.append(steps, el('small', 'case-id', pile.id)); b.append(text); box.append(b);
  }
  cases.forEach(c => {
    const s = scenario(c), b = demoCard(`tone-${s.tone}`, c.files[0], () => startDemo(c, 'separate'));
    const text = el('span', 'demo-text');
    text.append(el('b', null, s.title), el('small', null, s.sub), chipIcon(...s.chip), el('small', 'case-id', c.id));
    b.append(text); box.append(b);
  });
}

/* ---------------------------------------------------------------- proof strip (live held-out results) */
function renderProof() {
  const box = $('#proof'); if (!box) return;
  const r = state.evaluation?.heldout;
  box.hidden = !r; if (!r) return;
  box.replaceChildren();
  const o = r.fields.overall, k = r.kyc || {};
  [['target', pct1(o.accuracy_of_auto_accepted), t('proofAcc')],
   ['shield', t('ofN', k.false_pass_on_flawed_cases ?? 0, k.flawed_cases ?? 0), t('proofFalse')],
   ['userCheck', pct1(o.auto_accepted_rate), t('proofAuto')],
   ['lock', t('proofLocalValue'), t('proofLocal')]].forEach(([name, value, label]) => {
    const item = el('div', 'proof-item'), badge = el('span', 'proof-icon'); badge.append(icon(name));
    const text = el('div'); text.append(el('b', null, value), el('span', null, label)); item.append(badge, text); box.append(item);
  });
  const foot = el('div', 'proof-foot'); foot.append(el('span', null, t('proofFoot', r.images)));
  const more = el('button', 'link-btn'); more.type = 'button'; more.append(el('span', null, t('seeEval')), icon('arrow', 'flip-rtl')); more.onclick = () => showView('eval');
  foot.append(more); box.append(foot);
}

/* ---------------------------------------------------------------- reading (live) */
async function startReading(start) {
  showStage('read'); setReading(t('readingStart'), 3, 0); $('#foundDocs').replaceChildren(); $('#foundCount').textContent = '0';
  $('#foundEmpty').hidden = false;
  const started = Date.now(); clearInterval(state.clock);
  const tick = () => { $('#readingElapsed').textContent = t('elapsed', Math.round((Date.now() - started) / 1000)); };
  tick(); state.clock = setInterval(tick, 1000);
  try { state.batch = await start(); } catch (e) { clearInterval(state.clock); toast(e.message, true); showStage('upload'); return; }
  clearInterval(state.poll);
  state.poll = setInterval(poll, 1200); poll();
}
function setReading(message, progress, step) {
  $('#readingMessage').textContent = message; $('#readingProgress').value = progress; $('#readingPercent').textContent = `${Math.round(progress)}%`;
  $$('#agentSteps li').forEach((li, i) => { li.classList.toggle('done', i < step); li.classList.toggle('now', i === step); });
  if (progress >= 100) clearInterval(state.clock);
}
async function poll() {
  let b;
  try { b = await api(`/api/batches/${state.batch.id}`); } catch { return; }
  state.batch = b;
  const docs = b.documents || [];
  renderFound(docs);
  if (b.status === 'ready') {
    clearInterval(state.poll); setReading(t('readingFinish'), 100, 4);
    await loadDecision(); return;
  }
  if (b.status === 'failed' || b.status === 'interrupted') {
    clearInterval(state.poll); clearInterval(state.clock); toast(t('readFailed'), true); showStage('upload'); return;
  }
  // The server's message says which document it is on ("… المستمسك 2 من 4"): the file has been separated.
  const m = /(\d+)\s*من\s*(\d+)/.exec(b.message || '');
  const photos = state.expected || 1, photo = Math.max(1, (b.sources || []).length);
  const text = !m ? (docs.length ? t('readingDocs', docs.length) : t('readingFind'))
    : photos > 1 ? t('readingPhoto', photo, photos, docs.length) : t('readingDoc', +m[1], +m[2]);
  const share = !m ? 0 : photos > 1 ? (photo - 1 + (+m[1] - 1) / +m[2]) / photos : (+m[1] - 1) / +m[2];
  setReading(text, Math.max(b.progress || 0, Math.round(8 + share * 80)), m ? 2 : 0);
}
function kindName(d) {
  const k = t('kinds')[d.kind] || t('unidentified'), s = t('sides')[d.side] || '';
  return s ? `${k} · ${s}` : k;
}
function renderFound(docs) {
  const box = $('#foundDocs');
  if (box.childElementCount === docs.length) return;
  $('#foundCount').textContent = String(docs.length); $('#foundEmpty').hidden = docs.length > 0;
  // Only the new documents are added, so earlier cards do not flash again.
  docs.slice(box.childElementCount).forEach((d, i) => {
    const f = el('figure', 'found-doc'); f.style.animationDelay = `${i * 70}ms`;
    const img = el('img'); img.alt = ''; img.src = `/api/images/${d.image_id}`;
    const cap = el('figcaption'); cap.append(icon(d.kind && d.kind !== 'unknown' ? 'check' : 'info'), el('span', null, kindName(d)));
    f.append(img, cap); box.append(f);
  });
}

/* ---------------------------------------------------------------- decision */
const ORDER = { 'national_id:front': 0, 'national_id:back': 1, 'passport:page': 2, 'business_license:page': 3, 'tax_card:page': 4 };
const rank = d => ORDER[`${d.kind}:${d.side}`] ?? 9;
async function loadDecision() {
  const threshold = +$('#threshold').value, profile = $('#profile').value;
  try { state.kyc = await api(`/api/batches/${state.batch.id}/kyc?profile=${profile}&threshold=${threshold}`); }
  catch (e) { toast(e.message, true); return; }
  renderDecision(); showStage('decide');
}
function counts(k) {
  const fields = k.documents.flatMap(d => d.fields);
  const filled = fields.filter(f => String(f.value || '').trim());
  return { docs: k.documents.length, read: filled.length, accepted: filled.filter(f => !f.below_threshold && !(f.checks || []).some(c => c.severity === 'block')).length,
           human: filled.filter(f => f.below_threshold || (f.checks || []).some(c => c.severity === 'block')).length, blank: fields.length - filled.length };
}
function renderDecision() {
  const k = state.kyc; if (!k) return;
  const hero = $('#decision'); hero.replaceChildren(); hero.className = `decision ${k.decision}`;
  // The emblem animates once when it first appears (draws its check); moving the threshold re-renders the
  // hero, so the same <img> is reused while the verdict is unchanged instead of replaying the animation.
  const verdict = k.decision === 'pass' ? 'pass' : k.decision === 'review' ? 'review' : 'pending';
  if (state.emblem?.verdict !== verdict) {
    const img = el('img'); img.src = `/static/emblems/verdict-${verdict}.svg`; img.width = img.height = 76; img.alt = '';
    state.emblem = { verdict, img };
  }
  const badge = el('span', 'decision-icon'); badge.setAttribute('aria-hidden', 'true'); badge.append(state.emblem.img);
  const blocking = (k.reasons || []).filter(r => r.severity === 'block').length;
  const others = (k.reasons || []).length - blocking;
  const text = el('div', 'grow');
  text.append(el('p', 'eyebrow', `${t('threshold')}: ${pct(k.threshold)} · ${k.calibration?.fitted ? t('calibrated') : t('uncalibrated')}`),
              el('h1', null, k.decision === 'pass' ? t('pass') : k.decision === 'review' ? t('review') : t('pending')),
              el('p', 'lead', k.decision === 'pass' ? t('passText') : k.decision === 'review' ? t('reviewText', blocking, others) : t('pendingText')));
  const c = counts(k);
  // One bar for the whole file: accepted / to a person / blank, with the numbers as its legend.
  const compose = el('div', 'compose'), bar = el('div', 'compose-bar');
  bar.setAttribute('role', 'img'); bar.setAttribute('aria-label', `${c.accepted} ${t('statAccepted')}, ${c.human} ${t('statHuman')}, ${c.blank} ${t('statBlank')}`);
  [[c.accepted, 'c-good'], [c.human, 'c-warn'], [c.blank, 'c-muted']].forEach(([n, cls]) => { if (n) { const seg = el('i', cls); seg.style.flexGrow = n; bar.append(seg); } });
  const stats = el('div', 'stats');
  [[c.docs, 'statDocs'], [c.read, 'statFields'], [c.accepted, 'statAccepted', 'good'], [c.human, 'statHuman', 'warn'], [c.blank, 'statBlank', 'muted']]
    .forEach(([n, key, tone]) => { const s = el('div', `stat ${tone || ''}`); if (tone) s.append(el('i', 'sw')); s.append(el('b', null, String(n)), el('span', null, t(key))); stats.append(s); });
  compose.append(bar, stats); text.append(compose); hero.append(badge, text);

  const reasons = $('#reasons'); reasons.replaceChildren();
  [...(k.reasons || [])].sort((a, b) => (a.severity === 'block' ? 0 : 1) - (b.severity === 'block' ? 0 : 1)).forEach(r => {
    const li = el('li', `reason ${r.severity}`), btn = el('button', 'reason-btn'); btn.type = 'button';
    const sev = el('span', 'sev'); sev.append(icon(r.severity === 'block' ? 'alert' : 'info'));
    btn.append(sev, el('span', null, pick(r, 'message')));
    if (r.doc_id) btn.append(icon('arrow', 'go flip-rtl'));
    btn.onclick = () => focusField(r.doc_id, r.field_key);
    li.append(btn); reasons.append(li);
  });
  if (!k.reasons?.length) { const ok = el('li', 'reason ok'); ok.append(icon('check'), el('span', null, t('noReasons'))); reasons.append(ok); }

  const docs = [...k.documents].sort((a, b) => rank(a) - rank(b));
  const box = $('#documents'); box.replaceChildren();
  docs.forEach((d, i) => box.append(documentCard(d, i, docs.length, k.threshold)));
  renderRail(docs, k.threshold);

  const cross = $('#crossChecks'); cross.replaceChildren();
  (k.cross_checks || []).forEach(x => {
    const row = el('div', `check ${x.status}`);
    const label = { pass: t('statusPass'), fail: t('statusFail'), warn: t('statusWarn') }[x.status] || t('statusUnverifiable');
    const b = el('span', 'badge'); b.append(icon({ pass: 'check', fail: 'x' }[x.status] || 'alert'), el('span', null, label));
    const head = el('div', 'check-head'); head.append(b, el('b', null, pick(x, 'label')));
    row.append(head, el('p', 'small', pick(x, 'message')));
    const vals = el('ul', 'check-values');
    (x.values || []).forEach(v => { const li = el('li'); li.append(el('span', 'muted', pick(v, 'document') + ': ')); const b = el('bdi', null, v.value || '—'); li.append(b); vals.append(li); });
    row.append(vals); cross.append(row);
  });
  if (!k.cross_checks?.length) cross.append(el('p', 'muted', '—'));

  const reqs = $('#requirements'); reqs.replaceChildren();
  (k.requirements || []).forEach(r => {
    const li = el('li', r.satisfied ? 'ok' : 'missing'), mark = el('span', 'mark'); mark.append(icon(r.satisfied ? 'check' : 'x'));
    li.append(mark, el('span', null, `${pick(r, 'label')} — ${r.satisfied ? t('satisfied') : t('missingDoc')}`)); reqs.append(li);
  });
  $('#summary').textContent = lang === 'en' ? k.summary_en : k.summary;
  $('#openWorkspace').href = $('#workspaceLink').href = `/workspace?batch=${encodeURIComponent(state.batch.id)}`;
  $('#thresholdValue').textContent = pct($('#threshold').value);
}
function fieldStatus(f) {
  const value = String(f.value || '').trim();
  const blocked = (f.checks || []).some(c => c.severity === 'block');
  return !value ? 'blank' : f.below_threshold || blocked ? 'human' : 'auto';
}
function docTally(d) {
  const tally = { auto: 0, human: 0, blank: 0 };
  d.fields.forEach(f => { tally[fieldStatus(f)]++; });
  const criticalOpen = d.fields.some(f => f.critical && fieldStatus(f) !== 'auto');
  return { ...tally, state: d.kind === 'unknown' || criticalOpen ? 'bad' : tally.human || tally.blank ? 'check' : 'ok' };
}
let railObserver;
function renderRail(docs) {
  const rail = $('#docRail'); rail.replaceChildren();
  rail.hidden = docs.length < 2;
  docs.forEach(d => {
    const tally = docTally(d), b = el('button', `rail-item ${tally.state}`); b.type = 'button';
    const dot = el('span', 'rail-dot'); dot.append(icon(tally.state === 'ok' ? 'check' : tally.state === 'bad' ? 'alert' : 'minus'));
    const open = tally.human + tally.blank;
    const text = el('span', 'rail-text'); text.append(el('b', null, kindName(d)), el('small', null, open ? t('railCheck', open) : t('railOk')));
    b.append(dot, text);
    b.dataset.doc = d.id; b.onclick = () => focusField(d.id); rail.append(b);
  });
  // "You are here": the rail marks the document that fills most of the screen.
  railObserver?.disconnect();
  const seen = new Map();
  railObserver = new IntersectionObserver(entries => {
    entries.forEach(e => seen.set(e.target.id.slice(4), e.intersectionRatio));
    const [top] = [...seen].sort((a, b) => b[1] - a[1]);
    $$('.rail-item').forEach(b => b.toggleAttribute('aria-current', !!top && top[1] > 0 && b.dataset.doc === top[0]));
  }, { threshold: [0, .15, .3, .5, .75, 1], rootMargin: '-120px 0px -30% 0px' });
  $$('.doc-card').forEach(card => railObserver.observe(card));
}
function documentCard(d, i, n, threshold) {
  const card = el('article', 'panel doc-card'); card.id = `doc-${d.id}`;
  const head = el('div', 'doc-head');
  const title = el('div'); title.append(el('p', 'eyebrow', t('docOf', i + 1, n)), el('h2', null, pick(d, 'label') || t('unidentified')));
  const tally = docTally(d), summary = el('div', 'doc-summary');
  if (tally.auto) summary.append(chipIcon('good', 'check', t('docAuto', tally.auto)));
  if (tally.human) summary.append(chipIcon('warn', 'userCheck', t('docHuman', tally.human)));
  if (tally.blank) summary.append(chipIcon('neutral', 'minus', t('docBlank', tally.blank)));
  if (d.retake) summary.append(chipIcon('bad', 'camera', t('retake')));
  head.append(title, summary);
  const body = el('div', 'doc-body');
  const figure = el('a', 'doc-image'); figure.href = `/api/images/${d.image_id}`; figure.target = '_blank'; figure.rel = 'noopener';
  const img = el('img'); img.alt = pick(d, 'label'); img.loading = 'lazy'; img.src = `/api/images/${d.image_id}`; figure.append(img);
  const issues = (d.capture || []).filter(c => c.severity !== 'info');
  if (issues.length) { const ul = el('ul', 'capture-issues'); issues.slice(0, 3).forEach(c => ul.append(el('li', c.severity, pick(c, 'message')))); figure.append(ul); }
  const table = el('div', 'fields');
  d.fields.forEach(f => table.append(fieldRow(d, f, threshold)));
  body.append(figure, table); card.append(head, body);
  return card;
}
function fieldRow(d, f, threshold) {
  const value = String(f.value || '').trim(), status = fieldStatus(f);
  const row = el('div', `field ${status}`); row.id = `f-${d.id}-${f.key}`;
  const name = el('div', 'field-name'); name.append(el('span', null, pick(f, 'label')));
  if (f.critical) name.append(el('span', 'tag small-tag', t('critical')));
  const val = el('div', 'field-value'); const bdi = el('bdi', null, value || '—'); bdi.dir = 'auto'; val.append(bdi);
  const meter = el('div', 'meter'); meter.title = `${t('confidence')} ${pct1(f.confidence)}`;
  const fill = el('i'); fill.style.width = `${Math.round((f.confidence || 0) * 100)}%`;
  const mark = el('b', 'mark'); mark.style.insetInlineStart = `${Math.round(threshold * 100)}%`;
  meter.append(fill, mark);
  const conf = el('span', 'conf', value ? pct(f.confidence) : '—');
  const score = el('div', 'score'); score.append(meter, conf);
  const chip = { auto: ['good', 'check', t('autoAccepted')], human: ['warn', 'userCheck', t('toHuman')], blank: ['neutral', 'minus', t('notRead')] }[status];
  const notes = el('div', 'field-notes');
  (f.checks || []).forEach(c => notes.append(chipIcon(c.severity === 'block' ? 'bad' : 'warn', 'alert', pick(c, 'message'))));
  if (f.corroborated_by) notes.append(chipIcon('info', 'link', t('matches', pick(f, 'corroborated_by'))));
  row.append(name, val, score, chipIcon(...chip));
  if (notes.childElementCount) row.append(notes);
  return row;
}
function focusField(docId, key) {
  const target = (key && document.getElementById(`f-${docId}-${key}`)) || document.getElementById(`doc-${docId}`);
  if (!target) return;
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash');
}
let thresholdTimer;
$('#threshold').oninput = () => { $('#thresholdValue').textContent = pct($('#threshold').value); clearTimeout(thresholdTimer); thresholdTimer = setTimeout(loadDecision, 250); };
$('#profile').onchange = loadDecision;
// Copy confirms in place (icon and label turn into "Copied" for a moment), not only in a toast.
$('#copySummary').onclick = async e => {
  const btn = e.currentTarget;
  try { await navigator.clipboard.writeText($('#summary').textContent); } catch { toast(t('copyFailed'), true); return; }
  const before = [...btn.childNodes];
  btn.classList.add('is-done'); btn.replaceChildren(icon('check'), el('span', null, t('copyDone')));
  clearTimeout(btn._reset); btn._reset = setTimeout(() => { btn.classList.remove('is-done'); btn.replaceChildren(...before); }, 1800);
};
$('#downloadReport').onclick = () => {
  const a = el('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(state.kyc, null, 2)], { type: 'application/json' }));
  a.download = `kyc-decision-${state.batch.id.slice(0, 8)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};
$('#printFile').onclick = async () => {
  const ids = [...state.kyc.documents].sort((a, b) => rank(a) - rank(b)).map(d => d.id);
  const btn = $('#printFile'); busy(btn, true);
  try {
    const r = await api(`/api/batches/${state.batch.id}/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, format: 'pdf', layout: 'pairs', size: 'fit', allow_unreviewed: true }) });
    window.open(URL.createObjectURL(await r.blob()), '_blank');
  } catch (e) { toast(e.message, true); } finally { busy(btn, false); }
};
$('#newFile').onclick = () => { state.kyc = null; state.batch = null; $('#clearFiles').click(); showStage('upload'); };

/* ---------------------------------------------------------------- evaluation */
async function loadEvaluation() {
  try { state.evaluation = await api('/api/evaluation'); } catch { state.evaluation = {}; }
  renderEvaluation(); renderProof();
}
function tile(value, label, sub, tone) {
  const d = el('div', `tile ${tone || ''}`); d.append(el('b', null, value), el('span', null, label)); if (sub) d.append(el('small', null, sub)); return d;
}
function renderEvaluation() {
  const r = state.evaluation?.heldout, tiles = $('#evalTiles');
  tiles.replaceChildren(); $('#reliability').replaceChildren(); $('#levels').replaceChildren(); $('#kinds').replaceChildren();
  if (!r) { $('#evalLead').textContent = t('evalMissing'); return; }
  const cases = r.kyc?.cases ?? '—';
  $('#evalLead').textContent = t('evalLead', r.images, cases);
  const o = r.fields.overall, k = r.kyc || {}, cal = r.calibration || {};
  tiles.append(
    tile(pct1(o.accuracy_of_auto_accepted), t('tAutoAcc'), '', 'good hero'),
    tile(`${k.false_pass_on_flawed_cases ?? '—'}`, t('tFalsePass'), t('tFalsePassSub', k.flawed_cases ?? '—'), `${k.false_pass_on_flawed_cases === 0 ? 'good' : 'bad'} hero`),
    tile(pct1(o.auto_accepted_rate), t('tAuto'), '', 'info hero'),
    tile((cal.ece_calibrated ?? 0).toFixed(3), t('tEce'), t('tEceSub', (cal.ece_raw ?? 0).toFixed(3)), 'hero'),
    tile(pct1(r.fields.by_level?.worst?.routed_to_human_rate), t('tWorst'), '', 'warn'),
    tile(pct1(o.read_rate), t('tRead')), tile(pct1(o.accuracy_when_read), t('tAccRead')),
    tile(r.seconds_per_image != null ? r.seconds_per_image.toFixed(1) : '—', t('tSpeed')));
  $('#reliability').append(reliabilityChart(cal.reliability || []));
  $('#levels').append(table(['clean', 'poor', 'worst'].map(l => [t('levels')[l], r.fields.by_level?.[l]]), t('colLevel')));
  $('#kinds').append(table(Object.entries(r.fields.by_kind || {}).map(([kind, v]) => [t('kinds')[kind] || kind, v]), t('colKind')));
}
function table(rows, first) {
  const tb = el('table', 'data-table'); const head = el('tr');
  [first, t('colRead'), t('colAuto'), t('colAccAuto'), t('colHuman')].forEach(h => head.append(el('th', null, h))); tb.append(head);
  rows.forEach(([name, v]) => { if (!v) return; const tr = el('tr'); tr.append(el('th', null, name));
    const auto = Math.round((v.fields || 0) * (v.auto_accepted_rate || 0)), right = Math.round(auto * (v.accuracy_of_auto_accepted || 0));
    [[v.read_rate], [v.auto_accepted_rate], [v.accuracy_of_auto_accepted, auto && auto < 30 ? ` (${right}/${auto})` : ''], [v.routed_to_human_rate]]
      .forEach(([rate, extra = '']) => {
        const td = el('td', null, pct1(rate) + extra), bar = el('span', 'cell-bar'), fill = el('i');
        fill.style.width = `${Math.round((rate || 0) * 100)}%`; bar.append(fill); td.append(bar); tr.append(td);
      }); tb.append(tr); });
  return tb;
}
function reliabilityChart(bins) {
  const W = 360, H = 300, P = 42, NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'chart'); svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', t('calTitle'));
  const lo = .5, X = v => P + (v - lo) / (1 - lo) * (W - P - 14), Y = v => H - P + 10 - (v - lo) / (1 - lo) * (H - P - 20);
  const add = (tag, attrs, text) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([a, b]) => n.setAttribute(a, b)); if (text != null) n.textContent = text; svg.append(n); return n; };
  for (const v of [.5, .6, .7, .8, .9, 1]) {
    add('line', { x1: X(lo), x2: X(1), y1: Y(v), y2: Y(v), class: 'grid' });
    add('text', { x: P - 6, y: Y(v) + 4, 'text-anchor': 'end' }, `${Math.round(v * 100)}%`);
    add('text', { x: X(v), y: H - 12, 'text-anchor': 'middle' }, `${Math.round(v * 100)}%`);
  }
  add('line', { x1: X(lo), y1: Y(lo), x2: X(1), y2: Y(1), class: 'diagonal' });
  const pts = bins.filter(b => b.mean_confidence >= lo);
  if (pts.length) add('polyline', { points: pts.map(b => `${X(b.mean_confidence)},${Y(Math.max(lo, b.accuracy))}`).join(' '), class: 'curve' });
  pts.forEach(b => { const c = add('circle', { cx: X(b.mean_confidence), cy: Y(Math.max(lo, b.accuracy)), r: 3 + Math.sqrt(b.n) / 2, class: 'point' });
    const tt = document.createElementNS(NS, 'title'); tt.textContent = `${b.bin}: ${b.n} · ${pct(b.mean_confidence)} → ${pct(b.accuracy)}`; c.append(tt); });
  const wrap = el('figure', 'chart-wrap'); wrap.append(svg);
  const legend = el('figcaption', 'legend'); const a = el('span', 'l-diag', t('perfect')), b = el('span', 'l-agent', t('agent')); legend.append(a, b); wrap.append(legend);
  return wrap;
}

/* ---------------------------------------------------------------- start */
applyLanguage();
loadDemos();
loadEvaluation();  // the proof strip on the first screen shows the held-out results
// Coming back from the reviewer workspace (/?batch=<id>): reopen that file's decision (read before
// showView tidies the address bar).
{ const back = new URLSearchParams(location.search).get('batch');
  const v = location.hash.slice(1); showView(['onboard', 'how', 'eval'].includes(v) ? v : 'onboard');
  if (back && /^[a-f0-9]{32}$/.test(back)) { state.batch = { id: back }; loadDecision(); } }
