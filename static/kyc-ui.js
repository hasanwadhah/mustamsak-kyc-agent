/* KYC decision panel, capture-time photo guidance and retake badges.
   The server decides (app/kyc.py); this file only displays it. It never edits field values. */
'use strict';
const kyc={result:null,signature:'',request:0,profile:'auto'};
try{kyc.profile=localStorage.getItem('kycProfile')||'auto';}catch{}
const kycStatus={pass:'متطابق',warn:'اختلاف طفيف',fail:'غير متطابق',unverifiable:'لا يمكن التأكيد'};
const pct=v=>`${number(Math.round((v||0)*100))}%`;

(function mountKyc(){
 const panel=document.createElement('section');panel.id='kycPanel';panel.className='kyc-panel';panel.hidden=true;
 panel.setAttribute('aria-live','polite');
 $('.workspace-section').before(panel);
 const dialog=document.createElement('dialog');dialog.id='captureDialog';dialog.className='capture-dialog';
 dialog.innerHTML=`<div class="dialog-heading"><h2>تحقق من جودة التصوير قبل الرفع</h2></div><p class="field-help">فُحصت الصور محليًا دون قراءة نصوصها. الصور التالية قد تُخفي حقولًا؛ إعادة التصوير توفر وقت المراجعة.</p><div id="captureList" class="capture-list"></div><div class="capture-actions"><button class="secondary" id="captureRetake">سأعيد التصوير</button><button class="primary" id="captureContinue">متابعة الرفع كما هي</button></div>`;
 document.body.append(dialog);
})();

function kycSignature(b){
 if(!b)return '';
 return b.id+'|'+b.status+'|'+b.documents.map(d=>[d.id,d.kind,d.side,d.reviewed,d.image_id,JSON.stringify(d.fields.map(f=>[f.key,f.value,f.status,f.verified]))].join(':')).join(';');
}

async function refreshKyc(force=false){
 const b=state.batch;
 if(!b||['queued','processing'].includes(b.status)||!b.documents.length){$('#kycPanel').hidden=true;kyc.result=null;return;}
 const signature=kycSignature(b)+'|'+kyc.profile;
 if(!force&&signature===kyc.signature)return;
 kyc.signature=signature;const request=++kyc.request;
 try{
  const result=await api(`/api/batches/${b.id}/kyc?profile=${encodeURIComponent(kyc.profile)}`);
  if(request!==kyc.request||state.batch?.id!==b.id)return;
  kyc.result=result;renderKyc();
 }catch(e){if(request===kyc.request){$('#kycPanel').hidden=false;$('#kycPanel').innerHTML=`<p class="notice error">${escape(e.message)}</p>`;}}
}

function renderKyc(){
 const r=kyc.result,panel=$('#kycPanel');if(!r)return;
 const decision={pass:['يمكن اعتماده','pass'],review:['يحتاج مراجعة بشرية','review'],pending:['قيد المعالجة','pending']}[r.decision];
 const blocks=r.reasons.filter(x=>x.severity==='block'),warns=r.reasons.filter(x=>x.severity==='warn'&&x.code!=='retake');
 const retakes=r.documents.filter(d=>d.retake);
 const reasonItem=x=>`<li class="${x.severity}"><span>${escape(x.message)}</span>${x.doc_id&&currentDocs().some(d=>d.id===x.doc_id)?`<button class="text-button" data-kyc-open="${escape(x.doc_id)}">فتح المستمسك</button>`:''}</li>`;
 panel.hidden=false;
 panel.innerHTML=`
 <div class="kyc-head">
  <div><p class="eyebrow">التحقق من المستمسكات · KYC</p><h2>قرار الملف <span class="kyc-decision ${decision[1]}">${decision[0]}</span></h2>
  <p class="kyc-meta">الحد الأدنى للثقة ${pct(r.threshold)} · ${r.calibration.fitted?'ثقة معايرة على بيانات اختبار منفصلة':'الثقة غير معايرة بعد'} · ${number(r.counts.critical_fields)} حقل أساسي، ${number(r.counts.routed_fields)} منها للمراجعة</p></div>
  <div class="kyc-controls"><label>نوع الملف<select id="kycProfile"><option value="auto">تحديد تلقائي</option><option value="individual">فرد (هوية فقط)</option><option value="merchant">تاجر (هوية وإجازة وبطاقة ضريبية)</option></select></label>
  <button class="secondary" id="kycCopy">نسخ الملخص</button></div>
 </div>
 <div class="kyc-requirements">${r.requirements.map(q=>`<span class="kyc-chip ${q.satisfied?'ok':'missing'}">${q.satisfied?'✓':'✗'} ${escape(q.label)}</span>`).join('')}</div>
 ${blocks.length?`<h3 class="kyc-sub">ما يحتاج تحققًا ولماذا</h3><ol class="kyc-reasons">${blocks.map(reasonItem).join('')}</ol>`:'<p class="kyc-ok">كل الحقول الأساسية مقروءة بثقة كافية، صالحة، ومتطابقة بين المستمسكات.</p>'}
 ${retakes.length?`<div class="kyc-retake"><strong>اطلب إعادة التصوير</strong><ul>${retakes.map(d=>`<li>${escape(d.label)}: ${d.capture.filter(i=>i.severity==='retake').map(i=>escape(i.message)).join(' ')}</li>`).join('')}</ul></div>`:''}
 ${r.cross_checks.length?`<h3 class="kyc-sub">المطابقة بين المستمسكات</h3><ul class="kyc-cross">${r.cross_checks.map(c=>`<li class="${c.status}"><b>${escape(kycStatus[c.status])}</b> ${escape(c.label)} — ${escape(c.message)}</li>`).join('')}</ul>`:''}
 ${warns.length?`<details class="kyc-details"><summary>ملاحظات غير مانعة (${number(warns.length)})</summary><ul class="kyc-reasons">${warns.map(reasonItem).join('')}</ul></details>`:''}
 <details class="kyc-details"><summary>الثقة لكل حقل</summary>${r.documents.map(d=>`<div class="kyc-doc"><h4>${escape(d.label)}${d.retake?' <span class="badge retake">أعد التصوير</span>':''}</h4><table class="kyc-table"><thead><tr><th>الحقل</th><th>القيمة</th><th>الثقة</th><th>الحالة</th></tr></thead><tbody>${d.fields.map(f=>`<tr class="${f.below_threshold?'low':''} ${f.critical?'critical':''}"><td>${escape(f.label)}${f.critical?' <small>أساسي</small>':''}</td><td dir="auto">${f.value?escape(f.value):'<em>فارغ — لم يُقرأ</em>'}</td><td><span class="kyc-bar" style="--v:${Math.round(f.confidence*100)}%"></span>${pct(f.confidence)}</td><td>${f.basis==='human'?'اعتمدها المستخدم':f.basis==='checksum'?'مؤكدة برقم التحقق':f.below_threshold?'للمراجعة':'مقبولة'}</td></tr>`).join('')}</tbody></table></div>`).join('')}</details>
 <details class="kyc-details" lang="en" dir="ltr"><summary>English summary</summary><pre>${escape(r.summary_en)}</pre></details>`;
 $('#kycProfile').value=kyc.profile;
 $('#kycProfile').onchange=e=>{kyc.profile=e.target.value;try{localStorage.setItem('kycProfile',kyc.profile);}catch{}refreshKyc(true);};
 $('#kycCopy').onclick=async()=>{try{await navigator.clipboard.writeText(r.summary+'\n\n'+r.summary_en);toast('نُسخ ملخص المراجعة.');}catch{toast('تعذر النسخ؛ حدّد النص يدويًا.',true);}};
 $$('[data-kyc-open]').forEach(b=>b.onclick=()=>openEditor(b.dataset.kycOpen));
}

function markRetakeCards(){
 for(const d of currentDocs()){
  const retake=(d.capture||[]).filter(i=>i.severity==='retake');
  const card=document.querySelector(`.document-card [data-open="${CSS.escape(d.id)}"]`)?.closest('.document-card');
  if(!card||!retake.length||card.querySelector('.badge.retake'))continue;
  const badge=document.createElement('span');badge.className='badge retake';badge.textContent='أعد التصوير';badge.title=retake.map(i=>i.message).join('\n');
  card.querySelector('.card-meta')?.append(badge);
 }
}

// Extend the workspace render without touching its template.
const kycBaseRender=render;
render=function(){kycBaseRender();markRetakeCards();refreshKyc();};
// app.js may have rendered a finished batch before this script ran.
markRetakeCards();refreshKyc();

// Capture-time guidance: check photos (not PDFs) before uploading them.
const kycBaseUpload=uploadFiles;
uploadFiles=async function(list){
 const files=[...(list||[])];
 const running=state.batch&&['queued','processing'].includes(state.batch.status);
 const images=files.filter(f=>/^image\//.test(f.type)&&f.size<=25*1024*1024).slice(0,20);
 if(!images.length||running)return kycBaseUpload(files);
 $('#progressPanel').hidden=false;$('#progressTitle').textContent='فحص جودة التصوير';$('#progressText').textContent='التحقق من الحواف والإضاءة والوضوح…';
 let checks=[];
 try{checks=await Promise.all(images.map(async f=>{const data=new FormData();data.append('file',f);return {file:f,result:await api('/api/capture-check',{method:'POST',body:data})};}));}
 catch{return kycBaseUpload(files);}  // Guidance is advisory; never block an upload on it.
 const flagged=checks.filter(c=>c.result.retake);
 if(!flagged.length)return kycBaseUpload(files);
 $('#progressPanel').hidden=true;
 $('#captureList').innerHTML=flagged.map(c=>`<article class="capture-item"><strong>${escape(c.file.name)}</strong><ul>${c.result.documents.flatMap(d=>d.issues).filter(i=>i.severity!=='info').map(i=>`<li class="${i.severity}">${escape(i.message)}</li>`).join('')}</ul></article>`).join('');
 return new Promise(resolve=>{
  const dialog=$('#captureDialog');
  const finish=async upload=>{dialog.close();if(upload)await kycBaseUpload(files);else{$('#fileInput').value='';toast('أعد تصوير المستمسك مع مراعاة الملاحظات ثم ارفعه.');}resolve();};
  $('#captureContinue').onclick=()=>finish(true);$('#captureRetake').onclick=()=>finish(false);
  dialog.oncancel=e=>{e.preventDefault();finish(false);};
  dialog.showModal();
 });
};
