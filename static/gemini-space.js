/* The Gemini space: upload a document, Gemini reads it, the result is shown here (docs/EXTERNAL_API.md).
   Private by design: the file is read in server memory only (POST /api/gemini/read) and never
   stored or added to a batch; the key is kept in page memory, or in this browser only if the user
   asks. Gemini's answer is untrusted text: it is only ever shown with textContent. */
'use strict';
(function geminiSpace(){
 const nav=document.createElement('button');nav.className='nav-item';nav.id='geminiNav';
 nav.innerHTML=`<span data-icon="scan"></span>مساحة Gemini`;$('#guideNav').after(nav);icons(nav);
 const dlg=document.createElement('dialog');dlg.id='geminiDialog';dlg.className='gemini-dialog';
 dlg.innerHTML=`<div class="dialog-heading"><div><p class="eyebrow">قراءة سحابية بمفتاحك</p><h2>مساحة Gemini الخاصة</h2></div><button class="icon-button" id="closeGemini" aria-label="إغلاق">${icon('close')}</button></div>
 <div class="gemini-grid">
  <section class="gemini-setup">
   <div class="local-ai-head"><div><h3>التشغيل</h3><p class="field-help">عند الإطفاء لا يُرسل أي ملف خارج الجهاز.</p></div>
    <label class="switch" title="تشغيل أو إطفاء القراءة السحابية"><input type="checkbox" id="gToggle" role="switch"><span class="switch-track" aria-hidden="true"></span><span class="sr-only">القراءة السحابية</span></label></div>
   <p id="gState" class="local-ai-state" aria-live="polite">جارٍ الفحص…</p>
   <label>مفتاح Gemini API<span class="gemini-key"><input id="gKey" type="password" autocomplete="off" placeholder="AIza…" spellcheck="false" dir="ltr"><button type="button" class="secondary" id="gShow">إظهار</button></span></label>
   <p class="field-help">مجاني من <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">Google AI Studio</a>. يبقى في ذاكرة الصفحة فقط، إلا إذا اخترت تذكّره.</p>
   <label class="review-check compact"><input type="checkbox" id="gRemember">تذكّر المفتاح في هذا المتصفح</label>
   <label>النموذج<input id="gModel" list="gModels" dir="ltr" spellcheck="false"><datalist id="gModels"></datalist></label>
   <button type="button" class="secondary wide" id="gCheck">تحقق من المفتاح (بدون إرسال صور)</button>
   <p class="notice cloud-warning"><b>قبل الإرسال:</b> الملف يُرسل إلى Google فقط، ولا يُحفظ على هذا الجهاز. مع المفتاح المجاني قد تستخدم Google الصور لتحسين خدماتها ويطّلع عليها مراجعون بشريون. تُحذف بيانات الموقع (GPS) واسم الملف قبل الإرسال.</p>
   <label class="review-check compact"><input type="checkbox" id="gConsent">أوافق على إرسال الملفات التي أختارها هنا إلى Google Gemini</label>
  </section>
  <section class="gemini-work">
   <label class="gemini-drop" id="gDrop"><input type="file" id="gFile" accept="image/*,.pdf,application/pdf" hidden>
    <span data-icon="upload"></span><b>اختر صورة أو PDF أو اسحبها هنا</b><small>تبدأ القراءة مباشرة · حتى 4 صفحات · 15 ميغابايت</small></label>
   <div id="gBusy" class="gemini-busy" hidden><span class="spinner"></span><span id="gBusyText">جارٍ الإرسال…</span></div>
   <div id="gError" class="notice error" hidden></div>
   <div id="gPreview" class="gemini-preview" hidden></div>
   <div id="gResult"></div>
   <div id="gActions" class="gemini-actions" hidden><button type="button" class="secondary" id="gCopy">نسخ النتيجة</button><button type="button" class="secondary" id="gJson">تنزيل JSON</button><button type="button" class="text-button" id="gClear">مسح</button></div>
  </section>
 </div>`;
 document.body.append(dlg);icons(dlg);

 const KEY='mustamsak.geminiKey',MODEL='mustamsak.geminiModel';
 const get=n=>{try{return localStorage.getItem(n)||'';}catch{return '';}};
 const put=(n,v)=>{try{v?localStorage.setItem(n,v):localStorage.removeItem(n);}catch{}};
 let on=false,last=null,previewUrl=null,running=false;
 const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};
 const setState=(text,kind)=>{$('#gState').textContent=text;$('#gState').dataset.kind=kind||'';};
 const model=()=>$('#gModel').value.trim()||$('#gModel').placeholder;
 function syncKey(v){const c=$('#cloudKey');if(c&&c.value!==v){c.value=v;}}
 function ready(){
  if(!on)return setState('مطفأة. شغّلها لاستخدام هذه المساحة.','off');
  if(!$('#gKey').value.trim())return setState('أدخل مفتاح Gemini API.','warn');
  if(!$('#gConsent').checked)return setState('فعّل الموافقة على الإرسال، ثم اختر الملف.','warn');
  if($('#gState').dataset.kind!=='ready')setState(`جاهزة · النموذج ${model()} · اختر ملفًا.`,'warn');
 }
 async function open(){
  $('#gKey').value=$('#gKey').value||$('#cloudKey')?.value||get(KEY);$('#gRemember').checked=!!get(KEY);
  $('#gModel').value=$('#gModel').value||get(MODEL);$('#gConsent').checked=false;
  if(!dlg.open)dlg.showModal();
  try{const s=await api('/api/cloud');on=!!s.enabled;$('#gToggle').checked=on;$('#gModel').placeholder=s.default_model;}catch(e){setState(e.message,'warn');}
  ready();
 }
 nav.onclick=open;$('#closeGemini').onclick=()=>dlg.close();
 $('#gToggle').onchange=async e=>{const t=e.target,want=t.checked;t.disabled=true;
  try{const s=await api('/api/cloud',json('PUT',{enabled:want}));on=!!s.enabled;$('#gState').dataset.kind='';ready();
   const c=$('#cloudToggle');if(c){c.checked=on;$('#cloudFields').hidden=!on;$('#cloudRead').hidden=!on;}}
  catch(err){t.checked=!want;toast(err.message,true);}finally{t.disabled=false;}};
 $('#gKey').oninput=()=>{const v=$('#gKey').value.trim();syncKey(v);if($('#gRemember').checked)put(KEY,v);$('#gState').dataset.kind='';ready();};
 $('#gRemember').onchange=e=>put(KEY,e.target.checked?$('#gKey').value.trim():'');
 $('#gModel').onchange=()=>{put(MODEL,$('#gModel').value.trim());$('#gState').dataset.kind='';ready();};
 $('#gConsent').onchange=ready;
 $('#gShow').onclick=()=>{const k=$('#gKey');k.type=k.type==='password'?'text':'password';$('#gShow').textContent=k.type==='password'?'إظهار':'إخفاء';};
 $('#gCheck').onclick=()=>action($('#gCheck'),async()=>{
  const key=$('#gKey').value.trim();if(!key)throw Error('أدخل مفتاح Gemini API أولًا.');setState('جارٍ التحقق من المفتاح…');
  try{const r=await api('/api/cloud/check',json('POST',{api_key:key}));
   $('#gModels').replaceChildren(...r.models.map(m=>Object.assign(document.createElement('option'),{value:m})));
   const ok=r.models.includes(model());
   setState(ok?`المفتاح صالح · ${model()} متاح.`:`المفتاح صالح، لكن ${model()} غير متاح له. المتاح: ${r.models.slice(0,6).join('، ')}`,ok?'ready':'warn');
   if(ok)ready();}
  catch(err){setState(err.message,'warn');throw err;}});

 function showPreview(file){
  if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;const box=$('#gPreview');box.replaceChildren();
  if(file.type.startsWith('image/')){previewUrl=URL.createObjectURL(file);const img=el('img');img.src=previewUrl;img.alt='المستمسك المرفوع';box.append(img);}
  else box.append(el('p','field-help',`📄 ${file.name}`));
  box.hidden=false;
 }
 const sides={front:'الوجه الأمامي',back:'الوجه الخلفي',page:'صفحة',unknown:'وجه غير محدد'};
 function render(r){
  const out=$('#gResult');out.replaceChildren();
  if(!r.documents.length)out.append(el('p','notice','لم تجد Gemini مستمسكًا مقروءًا في الملف.'));
  r.documents.forEach((d,i)=>{
   const card=el('article','gemini-doc');
   card.append(el('h3',null,`${r.documents.length>1?(i+1)+'. ':''}${d.kind_label} · ${sides[d.side]||d.side}`));
   if(d.fields.length){const table=el('table','gemini-fields');
    d.fields.forEach(f=>{const tr=el('tr');tr.append(el('th',null,f.label||f.key));const td=el('td');td.append(el('span',null,f.value));
     const b=el('button','icon-button gemini-copy','نسخ');b.type='button';b.onclick=()=>copy(f.value);td.append(b);tr.append(td);table.append(tr);});
    card.append(table);}
   else card.append(el('p','field-help','لا حقول مقروءة.'));
   d.warnings.forEach(w=>card.append(el('p','gemini-warning','⚠ '+w)));
   if(d.raw_text){const det=el('details');det.append(el('summary',null,'النص الكامل كما قرأته Gemini'),el('pre',null,d.raw_text));card.append(det);}
   out.append(card);
  });
  const meta=el('p','field-help',`قرأها النموذج ${r.model} · ${r.pages} صفحة · راجع القيم مع الصورة قبل استخدامها.`);out.append(meta);
  r.notes.forEach(n=>out.append(el('p','field-help','تجاوز: '+n)));
  $('#gActions').hidden=false;
 }
 async function copy(text){try{await navigator.clipboard.writeText(text);toast('نُسخ.');}catch{toast('تعذر النسخ.',true);}}
 function asText(r){return r.documents.map(d=>[`${d.kind_label} (${sides[d.side]||d.side})`,...d.fields.map(f=>`${f.label||f.key}: ${f.value}`),...d.warnings.map(w=>'⚠ '+w)].join('\n')).join('\n\n');}
 async function read(file){
  $('#gError').hidden=true;
  if(running)return;
  if(!on){$('#gError').textContent='القراءة السحابية مطفأة. شغّلها من المفتاح أعلاه.';$('#gError').hidden=false;return;}
  const key=$('#gKey').value.trim();
  if(!key){$('#gError').textContent='أدخل مفتاح Gemini API أولًا.';$('#gError').hidden=false;$('#gKey').focus();return;}
  if(!$('#gConsent').checked){$('#gError').textContent='فعّل الموافقة على إرسال الملف إلى Google Gemini، ثم اختر الملف مرة أخرى.';$('#gError').hidden=false;return;}
  showPreview(file);$('#gResult').replaceChildren();$('#gActions').hidden=true;last=null;
  const form=new FormData();form.append('file',file,'upload');form.append('api_key',key);form.append('model',model());form.append('consent','true');
  running=true;$('#gBusy').hidden=false;const started=Date.now();
  const tick=setInterval(()=>$('#gBusyText').textContent=`Gemini تقرأ المستمسك… ${Math.round((Date.now()-started)/1000)} ث`,500);
  try{last=await api('/api/gemini/read',{method:'POST',body:form});render(last);setState(`تعمل · آخر قراءة بالنموذج ${last.model}.`,'ready');}
  catch(err){$('#gError').textContent=err.message;$('#gError').hidden=false;}
  finally{clearInterval(tick);running=false;$('#gBusy').hidden=true;$('#gFile').value='';}
 }
 $('#gFile').onchange=e=>{const f=e.target.files[0];if(f)read(f);};
 const drop=$('#gDrop');
 drop.ondragover=e=>{e.preventDefault();drop.classList.add('dragging');};drop.ondragleave=()=>drop.classList.remove('dragging');
 drop.ondrop=e=>{e.preventDefault();drop.classList.remove('dragging');const f=e.dataTransfer.files[0];if(f)read(f);};
 $('#gCopy').onclick=()=>last&&copy(asText(last));
 $('#gJson').onclick=()=>{if(!last)return;const a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(last,null,2)],{type:'application/json'}));a.download='gemini-reading.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
 $('#gClear').onclick=()=>{last=null;$('#gResult').replaceChildren();$('#gPreview').replaceChildren();$('#gPreview').hidden=true;$('#gActions').hidden=true;$('#gError').hidden=true;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;};
 dlg.addEventListener('close',()=>{$('#gConsent').checked=false;});
})();
