/* Guided tour: one fictional customer file, from upload to the reviewer who receives the data.
   Press Next and the tour drives the app itself, dimming the screen around the part it explains.
   Runs on the agent screen (/) and continues on the reviewer workspace (/workspace?tour=ws).
   The spotlight and the card are popovers, so they stay above open dialogs (top layer). */
'use strict';
(function guidedTour(){
 const onAgent = !!document.getElementById('stage-upload');
 const params = typeof START_PARAMS !== 'undefined' ? START_PARAMS : new URLSearchParams(location.search);
 const tourLang = () => (onAgent && typeof lang !== 'undefined') ? lang : (params.get('lang') === 'en' ? 'en' : 'ar');
 const TXT = {
  en: {next:'Next', back:'Back', exit:'Exit tour', finish:'Finish', start:'Guided tour', of:(i,n)=>`Step ${i} of ${n}`,
       waiting:(d,n)=>n?`Reading… ${d} of ${n} documents`:'Reading…', busy:'Other files are being read; the tour will use them when ready.',
       toWorkspace:'Continue in the reviewer’s screen', home:'Back to the main screen'},
  ar: {next:'التالي', back:'السابق', exit:'إنهاء الجولة', finish:'إنهاء', start:'جولة تعريفية', of:(i,n)=>`الخطوة ${i} من ${n}`,
       waiting:(d,n)=>n?`جارٍ القراءة… ${d} من ${n}`:'جارٍ القراءة…', busy:'هناك ملفات أخرى قيد القراءة؛ ستكمل الجولة عند انتهائها.',
       toWorkspace:'تابِع في شاشة المراجِع', home:'العودة إلى الشاشة الرئيسية'},
 };
 const tx = (k, ...a) => { const v = TXT[tourLang()][k]; return typeof v === 'function' ? v(...a) : v; };
 const S = (en, ar) => () => (tourLang() === 'en' ? en : ar);  // bilingual step text
 const wait = ms => new Promise(r => setTimeout(r, ms));
 async function until(test, ms = 15000) { const end = Date.now() + ms; while (Date.now() < end) { const v = test(); if (v) return v; await wait(150); } return null; }

 /* ------------------------------------------------ the tour file (agent screen) */
 let tourBatch = null, preparing = null;
 async function prepareFile() {
  // Reuse the fictional "all in one photo" file if it was already read; otherwise start reading it now,
  // so it is ready by the time the tour reaches the decision.
  const cases = (await api('/api/demo/cases')).cases;
  const c = cases.find(x => x.pile && !x.problem) || cases.find(x => x.pile);
  if (!c) throw Error('No demo files');
  const name = `Demo ${c.id} · one photo`;
  const list = await api('/api/batches');
  const done = (Array.isArray(list) ? list : list.batches || []).find(b => b.name === name && b.status === 'ready');
  tourBatch = done ? await api(`/api/batches/${done.id}`) :
    await api(`/api/demo/cases/${encodeURIComponent(c.id)}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mode: 'pile'})});
  tourBatch.caseFile = c.pile;
  return tourBatch;
 }
 async function refresh() { tourBatch = Object.assign(await api(`/api/batches/${tourBatch.id}`), {caseFile: tourBatch.caseFile}); return tourBatch; }

 const agentSteps = [
  {title: S('A guided tour of one customer file', 'جولة مع ملف عميل واحد'),
   text: S('We follow one fictional onboarding file from the moment the customer uploads it to the reviewer who receives the data. Just press Next — the app moves by itself.',
           'سنتابع ملف فتح حساب وهمي من لحظة رفع العميل له حتى يصل إلى الموظف الذي يستلم البيانات. اضغط «التالي» فقط، والبرنامج يتحرك وحده.'),
   before: async () => { showView('onboard'); showStage('upload'); preparing = preparing || prepareFile().catch(e => { toast(e.message, true); }); }},
  {target: '.awareness', title: S('1 · Awareness before upload', '١ – التوعية قبل الرفع'),
   text: S('Before sharing anything, the customer sees how to do it safely: official channels only, beware of fake links, four corners visible, no glare.',
           'قبل مشاركة أي شيء يرى العميل كيف يرفع مستمسكاته بأمان: القنوات الرسمية فقط، الحذر من الروابط المزيفة، ظهور الزوايا الأربع، بلا لمعان.')},
  {target: '#dropzone', title: S('2 · Upload everything at once', '٢ – رفع كل شيء مرة واحدة'),
   text: S('The customer drops photos or PDFs here, in any order. Each photo is checked for quality first, and a bad one gets “retake” advice before anything is read.',
           'يرفع العميل الصور أو ملفات PDF هنا وبأي ترتيب. تُفحص جودة كل صورة أولًا، والصورة السيئة تحصل على نصيحة «أعد التصوير» قبل أي قراءة.')},
  {target: '.demo-card.tone-info', title: S('3 · Our example: one photo, four documents', '٣ – مثالنا: صورة واحدة فيها أربعة مستمسكات'),
   text: S('For this tour we use this fictional file: the ID (both sides), business licence and tax card, all on a desk in one shot.',
           'نستخدم في هذه الجولة هذا الملف الوهمي: الهوية بوجهيها والإجازة والبطاقة الضريبية، كلها على مكتب في لقطة واحدة.')},
  {target: '#stage-read .reading', title: S('4 · The agent reads the file', '٤ – النظام يقرأ الملف'),
   text: S('It finds each document in the photo, cuts it out and straightens it, identifies its type and side, and reads every field in Arabic, English and handwriting.',
           'يجد كل مستمسك في الصورة، ويقصّه ويعدّل استقامته، ويتعرف على نوعه ووجهه، ثم يقرأ كل الحقول بالعربية والإنكليزية وخط اليد.'),
   before: async () => {
     showStage('read'); $('#foundDocs').replaceChildren();
     await (preparing || (preparing = prepareFile()));
     if (!tourBatch) return;
     clearInterval(state.poll); state.batch = tourBatch;
     const done = await followReading();
     if (done) { renderFound(tourBatch.documents); setReading(t('readingFinish'), 100, 4); }
   }},
  {target: '#foundDocs', title: S('5 · Separated and identified', '٥ – مفصولة ومعروفة النوع'),
   text: S('Four documents came out of one photo, each straightened and labelled. Next, they are validated, compared with each other and scored.',
           'خرجت أربعة مستمسكات من صورة واحدة، كل منها معدّل ومسمّى. بعدها تُدقَّق وتُطابق مع بعضها وتُعطى درجات ثقة.')},
  {target: '#decision', title: S('6 · The decision', '٦ – القرار'),
   text: S('Pass, or hand over to a person. The file is never rejected by the machine — at worst a reviewer checks only the listed items.',
           'قبول الملف أو تحويله إلى موظف. النظام لا يرفض أي ملف؛ في أسوأ الأحوال يتحقق الموظف فقط من البنود المذكورة.'),
   before: async () => { state.batch = tourBatch; await loadDecision(); }},
  {target: '#decision .stats', title: S('7 · At a glance', '٧ – نظرة سريعة'),
   text: S('How many documents and fields were read, accepted automatically, below the threshold, or left blank. Nothing is ever invented: an unreadable field stays blank.',
           'عدد المستمسكات والحقول المقروءة، وما قُبل تلقائيًا، وما كان أقل من الحد، وما تُرك فارغًا. لا يختلق النظام أي قيمة: الحقل غير المقروء يبقى فارغًا.')},
  {target: '.controls', title: S('8 · The confidence threshold', '٨ – الحد الأدنى للثقة'),
   text: S('Every field has a calibrated confidence. Anything below this line goes to a person. Drag it and the decision updates live.',
           'لكل حقل درجة ثقة معايَرة، وكل ما يقل عن هذا الحد يُحوَّل إلى موظف. حرّكه وسيتغير القرار مباشرة.')},
  {target: '#reasonsPanel', title: S('9 · What the reviewer must check', '٩ – ما يجب أن يتحقق منه الموظف'),
   text: S('A short list: each item says which field, on which document, its value and confidence, and why. Clicking an item jumps to that field.',
           'قائمة قصيرة: كل بند يذكر الحقل والمستمسك والقيمة ودرجة الثقة والسبب. الضغط على البند ينقلك إلى الحقل نفسه.')},
  {target: '.doc-card .doc-image', title: S('10 · Each document, cut out', '١٠ – كل مستمسك مقصوص'),
   text: S('The document as cut from the photo and straightened, with any photo problems noted under it.',
           'المستمسك كما قُصّ من الصورة وعُدّلت استقامته، مع ملاحظات جودة التصوير تحته.')},
  {target: '.doc-card .field', title: S('11 · One field', '١١ – حقل واحد'),
   text: S('The value as read, a confidence bar with the threshold mark, and the result: accepted automatically, to a person, or not read (left blank). A match on another document is shown too.',
           'القيمة كما قُرئت، وشريط الثقة مع علامة الحد، والنتيجة: قُبل تلقائيًا، أو يحتاج موظفًا، أو لم يُقرأ فتُرك فارغًا. ويظهر أيضًا إن طابق مستمسكًا آخر.')},
  {target: () => $('#crossChecks').closest('.panel'), title: S('12 · Documents checked against each other', '١٢ – مطابقة المستمسكات مع بعضها'),
   text: S('The name on the ID must match the licence owner and the taxpayer; the ID front and back must be one card; business names must agree.',
           'الاسم في الهوية يجب أن يطابق صاحب الإجازة والمكلف الضريبي، ووجها الهوية لبطاقة واحدة، والاسم التجاري نفسه في الإجازة والبطاقة الضريبية.')},
  {target: () => $('#summary').closest('.panel'), title: S('13 · The note the reviewer receives', '١٣ – الملاحظة التي يستلمها الموظف'),
   text: S('A short, human-readable summary of what needs checking and why — ready to copy into any case system.',
           'ملخص قصير واضح بما يحتاج تحققًا وسببه، جاهز للنسخ إلى أي نظام متابعة.')},
  {target: '.actions', title: S('14 · Handing the file over', '١٤ – تسليم الملف'),
   text: S('Print the sorted file (ID front and back together), download the decision report, or open the file in the reviewer’s screen.',
           'طباعة الملف مرتبًا (وجها الهوية معًا)، أو تنزيل تقرير القرار، أو فتح الملف في شاشة الموظف المراجِع.')},
  {target: '#openWorkspace', title: S('15 · To the person who receives the data', '١٥ – إلى الموظف الذي يستلم البيانات'),
   text: S('The tour now continues in the reviewer’s screen, with the same file.', 'تكمل الجولة الآن في شاشة المراجِع، مع الملف نفسه.'),
   nextLabel: () => tx('toWorkspace'),
   next: () => { location.href = `/workspace?batch=${encodeURIComponent(tourBatch.id)}&tour=ws&lang=${tourLang()}`; }},
 ];

 async function followReading() {
  // Live progress while the tour waits on the reading step (Next stays disabled meanwhile).
  let last = -1;
  while (true) {
   await refresh();
   const docs = tourBatch.documents || [];
   if (docs.length !== last) { renderFound(docs); last = docs.length; }
   const m = /(\d+)\s*من\s*(\d+)/.exec(tourBatch.message || '');
   setNextWaiting(tx('waiting', m ? +m[1] : docs.length, m ? +m[2] : 0));
   if (tourBatch.status === 'ready') return true;
   if (['failed', 'interrupted'].includes(tourBatch.status)) { toast(t('readFailed'), true); return false; }
   setReading(m ? t('readingDoc', +m[1], +m[2]) : t('readingFind'), Math.min(95, 10 + docs.length * 20), docs.length ? 2 : 0);
   await wait(1200);
  }
 }

 /* ------------------------------------------------ reviewer workspace */
 const firstDoc = () => document.querySelector('.document-card');
 // Each step sets the editor itself, so Back and Next both land on a visible target.
 async function editor(open) {
  if (!open) { if ($('#editor').open) { $('#editor').close(); await wait(200); } return; }
  const id = state.batch?.documents?.[0]?.id;
  if (id && !$('#editor').open) openEditor(id);
  await until(() => $('#editor').open); await wait(300);
 }
 const workspaceSteps = [
  {target: '#documents', title: S('16 · The reviewer receives the file', '١٦ – الموظف يستلم الملف'),
   text: S('The same four documents arrive here, sorted and grouped as one customer file, each with its reading status.',
           'تصل المستمسكات الأربعة نفسها إلى هنا مرتبة ومجمّعة كملف عميل واحد، ولكل منها حالة قراءتها.'),
   before: async () => { await editor(false); await until(firstDoc); }},
  {target: firstDoc, title: S('17 · Open a document', '١٧ – فتح مستمسك'),
   text: S('The reviewer opens any document to compare the fields with the image.', 'يفتح الموظف أي مستمسك ليقارن الحقول بالصورة.'),
   before: () => editor(false)},
  {target: '#fieldList', title: S('18 · Correct what needs correcting', '١٨ – تصحيح ما يحتاج تصحيحًا'),
   text: S('Every field can be corrected by hand. A human correction is final: automation never overwrites it, and it counts as fully certain.',
           'يمكن تصحيح أي حقل يدويًا. تصحيح الموظف نهائي: لا يغيّره النظام أبدًا، ويُعدّ مؤكدًا بالكامل.'),
   before: () => editor(true)},
  {target: () => $('#docReviewed').closest('label') || $('#docReviewed'), title: S('19 · Approve', '١٩ – الاعتماد'),
   text: S('Tick “reviewed” and save: the document is now human-verified.', 'ضع علامة «تمت المراجعة» واحفظ: أصبح المستمسك موثّقًا من الموظف.'),
   before: () => editor(true)},
  {target: '#exportBtn', title: S('20 · Export or print the verified file', '٢٠ – تصدير الملف الموثّق أو طباعته'),
   text: S('The approved file leaves as a PDF for printing, a ZIP of images, or JSON / CSV data for other systems.',
           'يخرج الملف المعتمد بصيغة PDF للطباعة، أو ملف ZIP للصور، أو بيانات JSON وCSV للأنظمة الأخرى.'),
   before: () => editor(false)},
  {title: S('That’s the whole journey', 'هذه الرحلة كاملة'),
   text: S('Upload → separate → read → validate → cross-check → decide → a person receives a clear list, corrects and approves → print or export. Every document here was fictional.',
           'الرفع ← الفصل ← القراءة ← التحقق ← المطابقة ← القرار ← يستلم الموظف قائمة واضحة فيصحح ويعتمد ← الطباعة أو التصدير. كل المستمسكات هنا وهمية.'),
   finish: true},
 ];

 /* ------------------------------------------------ the engine */
 const spot = document.createElement('div'); spot.className = 'tour-spot'; spot.popover = 'manual';
 const card = document.createElement('div'); card.className = 'tour-card'; card.popover = 'manual';
 card.setAttribute('role', 'dialog'); card.setAttribute('aria-live', 'polite');
 document.body.append(spot, card);
 let steps = [], index = 0, running = false, busy = false;

 // A modal dialog (e.g. the document editor) makes everything outside it unclickable, so while one is
 // open the card and the spotlight live inside it. Re-opening a popover also brings it back on top.
 function show(el) {
  const host = document.querySelector('dialog:modal') || document.body;
  try { el.hidePopover(); } catch {}
  if (el.parentElement !== host) host.append(el);
  try { el.showPopover(); } catch {}
 }
 function hide(el) { try { el.hidePopover(); } catch {} }
 function resolveTarget(step) {
  if (!step.target) return null;
  const el = typeof step.target === 'function' ? step.target() : document.querySelector(step.target);
  return el && el.getClientRects().length ? el : null;
 }
 function place(target) {
  const vw = innerWidth, vh = innerHeight, pad = 8, gap = 14;
  const cw = Math.min(400, vw - 24); card.style.width = cw + 'px';
  if (!target) {
   spot.style.cssText = 'left:50%;top:50%;width:0;height:0';
   card.style.left = `${(vw - cw) / 2}px`; card.style.top = `${Math.max(16, (vh - card.offsetHeight) / 2)}px`; return;
  }
  const r = target.getBoundingClientRect();
  const top = Math.max(4, r.top - pad), left = Math.max(4, r.left - pad);
  spot.style.cssText = `left:${left}px;top:${top}px;width:${Math.min(vw - 8, r.width + pad * 2)}px;height:${Math.min(vh - 8, r.height + pad * 2)}px`;
  const ch = card.offsetHeight;
  const clampX = x => Math.max(12, Math.min(vw - cw - 12, x));
  const clampY = y => Math.max(12, Math.min(vh - ch - 12, y));
  let x = clampX(r.left + r.width / 2 - cw / 2), y;
  if (r.bottom + pad + gap + ch <= vh - 12) y = r.bottom + pad + gap;              // below
  else if (r.top - pad - gap - ch >= 12) y = r.top - pad - gap - ch;               // above
  else if (vw - r.right - pad - gap >= cw + 12) { x = r.right + pad + gap; y = clampY(r.top); }   // beside, right
  else if (r.left - pad - gap >= cw + 12) { x = r.left - pad - gap - cw; y = clampY(r.top); }     // beside, left
  else y = vh - ch - 16;                                                            // over it, at the bottom
  card.style.left = `${x}px`; card.style.top = `${y}px`;
 }
 function setNextWaiting(text) { const b = card.querySelector('.tour-next'); if (b) { b.disabled = true; b.textContent = text; } }
 function render(step) {
  const n = steps.length, rtl = tourLang() === 'ar';
  card.dir = rtl ? 'rtl' : 'ltr'; card.lang = tourLang();
  card.innerHTML = '';
  const head = document.createElement('div'); head.className = 'tour-head';
  const count = document.createElement('span'); count.className = 'tour-count';
  count.textContent = tx('of', (onAgent ? index : agentSteps.length + index) + 1, agentSteps.length + workspaceSteps.length);
  const close = document.createElement('button'); close.type = 'button'; close.className = 'tour-x'; close.setAttribute('aria-label', tx('exit')); close.textContent = '×';
  close.onclick = stop; head.append(count, close);
  const h = document.createElement('h3'); h.textContent = step.title();
  const p = document.createElement('p'); p.textContent = step.text();
  const bar = document.createElement('div'); bar.className = 'tour-progress';
  const fill = document.createElement('i'); fill.style.width = `${Math.round(((onAgent ? index : agentSteps.length + index) + 1) / (agentSteps.length + workspaceSteps.length) * 100)}%`; bar.append(fill);
  const nav = document.createElement('div'); nav.className = 'tour-nav';
  const back = document.createElement('button'); back.type = 'button'; back.className = 'tour-back'; back.textContent = tx('back');
  back.disabled = index === 0; back.onclick = () => go(index - 1);
  const next = document.createElement('button'); next.type = 'button'; next.className = 'tour-next';
  next.textContent = step.finish ? tx('finish') : step.nextLabel ? step.nextLabel() : tx('next');
  next.onclick = () => step.finish ? stop() : step.next ? step.next() : go(index + 1);
  nav.append(back, next);
  if (step.finish && !onAgent) {
   const home = document.createElement('a'); home.className = 'tour-home'; home.textContent = tx('home');
   home.href = state.batch ? `/?batch=${encodeURIComponent(state.batch.id)}` : '/'; nav.prepend(home);
  }
  card.append(head, h, p, bar, nav);
 }
 async function go(i) {
  if (busy || i < 0 || i >= steps.length) return;
  busy = true; index = i; const step = steps[i];
  render(step); show(spot); show(card); place(null);
  setNextWaiting('…');
  try { if (step.before) await step.before(); } catch (e) { console.error(e); }
  if (!running) { busy = false; return; }
  const target = resolveTarget(step);
  if (target) {
   const tall = target.getBoundingClientRect().height > innerHeight * .6;
   const block = tall ? 'start' : 'center';
   target.scrollIntoView({block, behavior: 'smooth'});
   await wait(450);
   // Smooth scrolling can stall (e.g. a background tab): finish it instantly.
   const r = target.getBoundingClientRect();
   if (tall ? Math.abs(r.top - 80) > 40 : (r.top < 60 || r.bottom > innerHeight - 10)) target.scrollIntoView({block, behavior: 'instant'});
   if (tall) scrollBy({top: -80, behavior: 'instant'});  // clear the sticky top bar
  }
  render(step); show(spot); show(card); place(target);
  spot.classList.toggle('none', !target);
  busy = false;
  card.querySelector('.tour-next')?.focus();
 }
 function start(list, at = 0) { steps = list; running = true; document.documentElement.classList.add('touring'); go(at); }
 function stop() {
  running = false; hide(card); hide(spot); document.documentElement.classList.remove('touring');
  if (!onAgent) history.replaceState(null, '', location.pathname + (state.batch ? `?batch=${encodeURIComponent(state.batch.id)}` : ''));
 }
 addEventListener('resize', () => { if (running && !busy) place(resolveTarget(steps[index])); });
 addEventListener('scroll', () => { if (running && !busy) place(resolveTarget(steps[index])); }, {passive: true});
 addEventListener('keydown', e => {
  if (!running) return;
  const rtl = tourLang() === 'ar';
  if (e.key === 'Escape') { e.preventDefault(); stop(); }
  else if (e.key === (rtl ? 'ArrowLeft' : 'ArrowRight')) { const b = card.querySelector('.tour-next'); if (b && !b.disabled) b.click(); }
  else if (e.key === (rtl ? 'ArrowRight' : 'ArrowLeft')) { if (index > 0) go(index - 1); }
 });

 /* ------------------------------------------------ entry points */
 if (onAgent) {
  const button = document.createElement('button'); button.type = 'button'; button.id = 'tourStart'; button.className = 'tour-launch';
  const label = () => { button.textContent = '▶ ' + tx('start'); };
  label(); $('.top-actions').prepend(button);
  button.onclick = () => start(agentSteps);
  // ?tour=<step> opens the tour at that step (1-based), e.g. to show one part to someone.
  const at = parseInt(params.get('tour'), 10);
  if (at >= 1 && at <= agentSteps.length) (async () => {
   await until(() => typeof state !== 'undefined');
   if (at > 6) {  // steps after the reading need the file read and its decision shown
    preparing = preparing || prepareFile();
    await preparing;
    if (tourBatch) {
     for (let k = 0; k < 150 && (await refresh()).status !== 'ready'; k++) await wait(1200);
     state.batch = tourBatch; await loadDecision();
    }
   }
   start(agentSteps, at - 1);
  })();
  $('#langToggle').addEventListener('click', () => setTimeout(() => { label(); if (running) go(index); }, 0));
 } else if (params.get('tour') === 'ws') {
  const at = Math.max(1, parseInt(params.get('step'), 10) || 1);
  until(() => typeof state !== 'undefined' && state.batch).then(async () => {
   if (at >= 4) { const id = state.batch.documents?.[0]?.id; if (id) { openEditor(id); await until(() => $('#editor').open); } }
   start(workspaceSteps, Math.min(at, workspaceSteps.length) - 1);
  });
 }
 window.startGuidedTour = () => onAgent && start(agentSteps);
})();
