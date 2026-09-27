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
  renderStatic(); renderDemos(); renderPrecheck();
  if (state.kyc) renderDecision();
  if (state.evaluation) renderEvaluation();
}
$('#langToggle').onclick = () => { lang = lang === 'ar' ? 'en' : 'ar'; try { localStorage.setItem('agentLang', lang); } catch {} applyLanguage(); };
function showView(view) {
  $$('.view').forEach(v => (v.hidden = v.id !== `view-${view}`));
  $$('.view-tab').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  if (view === 'eval' && !state.evaluation) loadEvaluation();
  if (location.hash !== `#${view}`) history.replaceState(null, '', view === 'onboard' ? location.pathname : `#${view}`);
}
$$('.view-tab').forEach(b => (b.onclick = () => showView(b.dataset.view)));
function showStage(stage) {
  ['upload', 'read', 'decide'].forEach(s => ($(`#stage-${s}`).hidden = s !== stage));
  const order = ['upload', 'read', 'decide'];
  $$('.stepper li').forEach(li => {
    const i = order.indexOf(li.dataset.step), current = order.indexOf(stage);
    li.classList.toggle('current', i === current); li.classList.toggle('done', i < current);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function renderStatic() {
  const tips = $('#tips'); tips.replaceChildren();
  t('tips').forEach(([title, text], i) => { const li = el('li'); li.append(el('b', null, title), el('span', null, text)); li.dataset.n = i + 1; tips.append(li); });
  const pipe = $('#pipeline'); pipe.replaceChildren();
  t('pipeline').forEach(([title, text], i) => { const li = el('li'); li.append(el('span', 'num', String(i + 1)), el('b', null, title), el('p', null, text)); pipe.append(li); });
  for (const [id, key] of [['#rules', 'rules'], ['#scope', 'scope']]) { const ul = $(id); ul.replaceChildren(...t(key).map(x => el('li', null, x))); }
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
  await startReading(() => api('/api/batches', { method: 'POST', body: form }));
};

/* ---------------------------------------------------------------- demo files */
async function loadDemos() {
  try { state.demos = (await api('/api/demo/cases')).cases; } catch { state.demos = []; }
  renderDemos();
}
function curatedDemos() {
  const cases = state.demos, out = [];
  const consistent = cases.find(c => !c.problem && c.worst_level !== 'worst') || cases.find(c => !c.problem);
  const flawed = cases.find(c => c.problem && c.worst_level !== 'worst') || cases.find(c => c.problem);
  const pile = cases.find(c => c.pile && !c.problem) || cases.find(c => c.pile);
  const worst = cases.find(c => c.worst_level === 'worst' && ![consistent, flawed, pile].includes(c)) || cases.find(c => c.worst_level === 'worst' && c !== consistent && c !== flawed);
  if (consistent) out.push({ c: consistent, mode: 'separate', title: t('demoConsistent'), sub: t('demoFour'), tone: 'good' });
  if (flawed) out.push({ c: flawed, mode: 'separate', title: t('demoFlawed'), sub: t('problems')[flawed.problem] || flawed.problem, tone: 'bad' });
  if (pile) out.push({ c: pile, mode: 'pile', title: t('demoPile'), sub: t('demoOnePhoto'), tone: 'info' });
  if (worst) out.push({ c: worst, mode: 'separate', title: t('demoWorst'), sub: t('demoWorstSub'), tone: 'warn' });
  return out;
}
function renderDemos() {
  const box = $('#demos'); if (!box) return; box.replaceChildren();
  const demos = curatedDemos();
  if (!demos.length) { box.append(el('p', 'muted', 'No demo files. Run scripts/synthetic_kyc.py --split demo --clean-copies and scripts/demo_pile.py.')); return; }
  demos.forEach(d => {
    const b = el('button', `demo-card tone-${d.tone}`); b.type = 'button';
    const img = el('img'); img.alt = ''; img.loading = 'lazy'; img.src = `/api/demo/files/${encodeURIComponent(d.mode === 'pile' ? d.c.pile : d.c.files[0])}`;
    const text = el('span', 'demo-text'); text.append(el('b', null, d.title), el('small', null, d.sub), el('small', 'case-id', d.c.id));
    b.append(img, text);
    b.onclick = () => (state.expected = d.mode === 'pile' ? 1 : d.c.files.length) && startReading(() => api(`/api/demo/cases/${encodeURIComponent(d.c.id)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: d.mode }) }));
    box.append(b);
  });
}

/* ---------------------------------------------------------------- reading (live) */
async function startReading(start) {
  showStage('read'); setReading(t('readingStart'), 3, 0); $('#foundDocs').replaceChildren();
  try { state.batch = await start(); } catch (e) { toast(e.message, true); showStage('upload'); return; }
  clearInterval(state.poll);
  state.poll = setInterval(poll, 1200); poll();
}
function setReading(message, progress, step) {
  $('#readingMessage').textContent = message; $('#readingProgress').value = progress;
  $$('#agentSteps li').forEach((li, i) => { li.classList.toggle('done', i < step); li.classList.toggle('now', i === step); });
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
    clearInterval(state.poll); toast(t('readFailed'), true); showStage('upload'); return;
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
  box.replaceChildren(...docs.map(d => {
    const f = el('figure', 'found-doc'); const img = el('img'); img.alt = ''; img.src = `/api/images/${d.image_id}`;
    f.append(img, el('figcaption', null, kindName(d))); return f;
  }));
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
  const icon = el('span', 'decision-icon'); icon.setAttribute('aria-hidden', 'true'); icon.textContent = k.decision === 'pass' ? '✓' : k.decision === 'review' ? '⚑' : '…';
  const blocking = (k.reasons || []).filter(r => r.severity === 'block').length;
  const others = (k.reasons || []).length - blocking;
  const text = el('div', 'grow');
  text.append(el('p', 'eyebrow', `${t('threshold')}: ${pct(k.threshold)} · ${k.calibration?.fitted ? 'calibrated' : 'uncalibrated'}`),
              el('h1', null, k.decision === 'pass' ? t('pass') : k.decision === 'review' ? t('review') : t('pending')),
              el('p', 'lead', k.decision === 'pass' ? t('passText') : k.decision === 'review' ? t('reviewText', blocking, others) : t('pendingText')));
  const c = counts(k), stats = el('div', 'stats');
  [[c.docs, 'statDocs'], [c.read, 'statFields'], [c.accepted, 'statAccepted', 'good'], [c.human, 'statHuman', 'warn'], [c.blank, 'statBlank', 'muted']]
    .forEach(([n, key, tone]) => { const s = el('div', `stat ${tone || ''}`); s.append(el('b', null, String(n)), el('span', null, t(key))); stats.append(s); });
  text.append(stats); hero.append(icon, text);

  const reasons = $('#reasons'); reasons.replaceChildren();
  [...(k.reasons || [])].sort((a, b) => (a.severity === 'block' ? 0 : 1) - (b.severity === 'block' ? 0 : 1)).forEach(r => {
    const li = el('li', `reason ${r.severity}`); li.tabIndex = 0;
    li.append(el('span', 'sev', r.severity === 'block' ? '!' : 'i'), el('span', null, pick(r, 'message')));
    li.onclick = li.onkeydown = e => { if (e.type === 'keydown' && e.key !== 'Enter') return; focusField(r.doc_id, r.field_key); };
    reasons.append(li);
  });
  if (!k.reasons?.length) reasons.append(el('li', 'reason ok', t('noReasons')));

  const docs = [...k.documents].sort((a, b) => rank(a) - rank(b));
  const box = $('#documents'); box.replaceChildren();
  docs.forEach((d, i) => box.append(documentCard(d, i, docs.length, k.threshold)));

  const cross = $('#crossChecks'); cross.replaceChildren();
  (k.cross_checks || []).forEach(x => {
    const row = el('div', `check ${x.status}`);
    const head = el('div', 'check-head'); head.append(el('span', 'badge', { pass: t('statusPass'), fail: t('statusFail'), warn: t('statusWarn') }[x.status] || t('statusUnverifiable')), el('b', null, pick(x, 'label')));
    row.append(head, el('p', 'small', pick(x, 'message')));
    const vals = el('ul', 'check-values');
    (x.values || []).forEach(v => { const li = el('li'); li.append(el('span', 'muted', pick(v, 'document') + ': ')); const b = el('bdi', null, v.value || '—'); li.append(b); vals.append(li); });
    row.append(vals); cross.append(row);
  });
  if (!k.cross_checks?.length) cross.append(el('p', 'muted', '—'));

  const reqs = $('#requirements'); reqs.replaceChildren();
  (k.requirements || []).forEach(r => { const li = el('li', r.satisfied ? 'ok' : 'missing'); li.append(el('span', 'mark', r.satisfied ? '✓' : '✗'), el('span', null, `${pick(r, 'label')} — ${r.satisfied ? t('satisfied') : t('missingDoc')}`)); reqs.append(li); });
  $('#summary').textContent = lang === 'en' ? k.summary_en : k.summary;
  $('#openWorkspace').href = $('#workspaceLink').href = `/workspace?batch=${encodeURIComponent(state.batch.id)}`;
  $('#thresholdValue').textContent = pct($('#threshold').value);
}
function documentCard(d, i, n, threshold) {
  const card = el('article', 'panel doc-card'); card.id = `doc-${d.id}`;
  const head = el('div', 'doc-head');
  const title = el('div'); title.append(el('p', 'eyebrow', t('docOf', i + 1, n)), el('h2', null, pick(d, 'label') || t('unidentified')));
  head.append(title);
  if (d.retake) head.append(el('span', 'chip bad', t('retake')));
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
  const value = String(f.value || '').trim();
  const blocked = (f.checks || []).some(c => c.severity === 'block');
  const status = !value ? 'blank' : f.below_threshold || blocked ? 'human' : 'auto';
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
  const chip = el('span', `chip ${status === 'auto' ? 'good' : status === 'human' ? 'warn' : 'neutral'}`, status === 'auto' ? t('autoAccepted') : status === 'human' ? t('toHuman') : t('notRead'));
  const notes = el('div', 'field-notes');
  (f.checks || []).forEach(c => notes.append(el('span', `chip ${c.severity === 'block' ? 'bad' : 'warn'}`, pick(c, 'message'))));
  if (f.corroborated_by) notes.append(el('span', 'chip info', `✓ ${t('matches', pick(f, 'corroborated_by'))}`));
  row.append(name, val, score, chip);
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
$('#copySummary').onclick = async () => { try { await navigator.clipboard.writeText($('#summary').textContent); toast(t('copied')); } catch {} };
$('#downloadReport').onclick = () => {
  const a = el('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(state.kyc, null, 2)], { type: 'application/json' }));
  a.download = `kyc-decision-${state.batch.id.slice(0, 8)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};
$('#printFile').onclick = async () => {
  const ids = [...state.kyc.documents].sort((a, b) => rank(a) - rank(b)).map(d => d.id);
  toast(t('printing'));
  try {
    const r = await api(`/api/batches/${state.batch.id}/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, format: 'pdf', layout: 'pairs', size: 'fit', allow_unreviewed: true }) });
    window.open(URL.createObjectURL(await r.blob()), '_blank');
  } catch (e) { toast(e.message, true); }
};
$('#newFile').onclick = () => { state.kyc = null; state.batch = null; $('#clearFiles').click(); showStage('upload'); };

/* ---------------------------------------------------------------- evaluation */
async function loadEvaluation() {
  try { state.evaluation = await api('/api/evaluation'); } catch { state.evaluation = {}; }
  renderEvaluation();
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
    tile(pct1(o.accuracy_of_auto_accepted), t('tAutoAcc'), '', 'good'),
    tile(`${k.false_pass_on_flawed_cases ?? '—'}`, t('tFalsePass'), t('tFalsePassSub', k.flawed_cases ?? '—'), k.false_pass_on_flawed_cases === 0 ? 'good' : 'bad'),
    tile((cal.ece_calibrated ?? 0).toFixed(3), t('tEce'), t('tEceSub', (cal.ece_raw ?? 0).toFixed(3)), 'info'),
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
    [pct1(v.read_rate), pct1(v.auto_accepted_rate), pct1(v.accuracy_of_auto_accepted) + (auto && auto < 30 ? ` (${right}/${auto})` : ''), pct1(v.routed_to_human_rate)]
      .forEach(x => tr.append(el('td', null, x))); tb.append(tr); });
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
// Coming back from the reviewer workspace (/?batch=<id>): reopen that file's decision (read before
// showView tidies the address bar).
{ const back = new URLSearchParams(location.search).get('batch');
  const v = location.hash.slice(1); showView(['onboard', 'how', 'eval'].includes(v) ? v : 'onboard');
  if (back && /^[a-f0-9]{32}$/.test(back)) { state.batch = { id: back }; loadDecision(); } }
