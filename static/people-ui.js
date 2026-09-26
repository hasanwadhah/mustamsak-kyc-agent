'use strict';
const peopleState={items:[],mode:'manual',detail:null,active:null,request:0,summaryRequest:0,selected:new Set(),available:[],bulkRefs:null};
const relationNames={owner:'مستمسك الشخص',father_household:'سكن باسم الأب / الأسرة',household:'مستمسك الأسرة',supporting:'مستمسك مرفق'};
function addPeopleDialog(id,html,className=''){
 const node=document.createElement('dialog');node.id=id;node.className=className;node.innerHTML=html;document.body.append(node);
 node.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>node.close());return node;
}
const peopleDialog=addPeopleDialog('peopleDialog',`
 <div class="dialog-heading"><div><p class="eyebrow">مستمسكات مرتبطة بالشخص، من كل الدفعات</p><h2>ملفات الأشخاص <span id="peopleTotal" class="count-pill"></span></h2></div><button class="icon-button" data-close aria-label="إغلاق ملفات الأشخاص">${icon('close')}</button></div>
 <div class="people-settings"><label>ربط بطاقة السكن<select id="peopleMode"><option value="manual">يدوي — اقتراح ثم تأكيد</option><option value="auto">تلقائي — تطابق فريد مع مراجعة</option></select></label><p id="peopleModeHelp"></p><button id="refreshPeople" class="secondary">تحديث الملفات</button></div>
 <p id="peopleMissing" class="notice" hidden></p><p id="peopleError" class="notice error" role="alert" hidden></p>
 <div class="people-layout"><aside class="people-sidebar"><label>البحث عن شخص<input id="peopleSearch" type="search" placeholder="الاسم أو الرقم الوطني" autocomplete="off"></label><div id="peopleList" class="people-list"></div></aside><section id="personDetail" class="person-detail" aria-live="polite"><div class="person-empty"><h3>ملف واحد لكل شخص</h3><p>اختر شخصًا لمراجعة بياناته ومستمسكاته واقتراحات السكن.</p></div></section></div>`, 'people-dialog');
addPeopleDialog('personAttachDialog',`
 <div class="dialog-heading"><h2 id="attachTitle">إضافة مستمسكات إلى الملف</h2><button class="icon-button" data-close aria-label="إلغاء الإضافة">${icon('close')}</button></div>
 <label id="attachPersonLabel" hidden>ملف الشخص<select id="attachPerson"></select></label>
 <label>علاقة المستمسكات بالشخص<select id="attachRelation">${Object.entries(relationNames).map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></label>
 <p class="field-help">اختر بطاقة السكن ووجهها الخلفي إن وُجد. الإضافة تحفظ العلاقة التي تختارها؛ لا تغيّر بيانات الموحدة.</p>
 <label id="attachSearchLabel">البحث في المستمسكات المحفوظة<input id="attachSearch" type="search" placeholder="اسم الدفعة أو نوع المستمسك أو بياناته"></label>
 <div id="attachList" class="attach-list"></div><p id="attachError" class="notice error" role="alert" hidden></p>
 <div class="dialog-actions"><button class="secondary" data-close>إلغاء</button><button class="primary" id="confirmAttach">إضافة المحدد إلى الملف</button></div>`, 'person-attach-dialog');
addPeopleDialog('personExportDialog',`
 <div class="dialog-heading"><h2>طباعة ملف الشخص وتصديره</h2><button class="icon-button" data-close aria-label="إغلاق التصدير">${icon('close')}</button></div>
 <p id="personExportSummary"></p><div class="form-grid"><label>صيغة التنزيل<select id="personExportFormat"><option value="pdf">PDF</option><option value="zip">صور + PDF + بيانات (ZIP)</option><option value="json">بيانات الملف (JSON)</option></select></label><label>ترتيب الصفحات<select id="personExportLayout"><option value="pairs">وجهان لكل صفحة حسب المستمسك</option><option value="single">كل مستمسك في صفحة</option><option value="grid4">٤ خانات · عمودان وصفّان</option><option value="grid6">٦ خانات · عمودان وثلاثة صفوف</option></select></label></div>
 <div class="print-board-entry"><button class="secondary" id="openPersonPrintBoard">لوحة ترتيب بالسحب</button><p id="personPrintStatus"></p></div>
 <label>حجم الطباعة<select id="personExportSize"><option value="fit">تكبير مناسب مع حفظ النسبة</option><option value="card">الموحدة بالحجم الفعلي</option></select></label>
 <label class="review-check"><input type="checkbox" id="personExportDraft">تصدير مسودة تشمل المستمسكات أو الروابط التي لم تُراجع</label>
 <p id="personExportError" class="notice error" role="alert" hidden></p><div class="dialog-actions"><button id="personPreview" class="secondary">معاينة وطباعة PDF</button><button id="personDownload" class="primary">تنزيل الملف</button></div>`);
const attachSelection=new Set();let attachRevision=null,personExportTarget=null;

function modeHelp(){
 $('#peopleMode').value=peopleState.mode;
 $('#peopleModeHelp').textContent=peopleState.mode==='auto'?
  'يضيف تطابق الأسماء الواضح والفريد فقط، ويضع علامة «يحتاج مراجعة». اعتمد الربط لتثبيته؛ التهجئة المتشابهة أو عدة أشخاص تبقى اقتراحات.':
  'يعرض بطاقات السكن المحتملة لتضيفها بنفسك. الروابط التلقائية غير المعتمدة تظهر هنا كاقتراحات عند العودة للوضع اليدوي.';
}
function renderPeopleList(){
 const query=$('#peopleSearch').value.trim();
 const items=peopleState.items.filter(p=>!query||`${p.name} ${p.extracted_name} ${p.national_number}`.includes(query)).sort((a,b)=>Number(b.batch_ids.includes(state.batch?.id))-Number(a.batch_ids.includes(state.batch?.id))||b.created.localeCompare(a.created));
 $('#peopleTotal').textContent=number(peopleState.items.length);
 $('#peopleList').innerHTML=items.length?items.map(p=>`<button class="person-list-item ${p.id===peopleState.active?'active':''}" data-person="${p.id}" aria-pressed="${p.id===peopleState.active}"><span class="person-initial">${escape(p.name.trim()[0]||'م')}</span><span><strong>${escape(p.name)}</strong><small>${number(p.document_count)} مستمسك${p.suggestion_count?' · '+number(p.suggestion_count)+' اقتراح سكن':''}</small><span class="badge ${p.needs_review?'':'ready'}">${p.needs_review?'بحاجة إلى مراجعة':'تمت مراجعة المستمسكات'}</span></span></button>`).join(''):
  '<p class="person-empty">لا توجد ملفات مطابقة. ينشأ الملف من وجه الموحدة الأمامي بعد قراءة الاسم؛ يمكنك تصحيح الاسم في محرر المستمسك.</p>';
 $$('[data-person]').forEach(b=>b.onclick=()=>loadPerson(b.dataset.person));
}
async function fetchPeopleList(){
 const result=await api('/api/people');peopleState.items=result.people;peopleState.mode=result.mode;
 modeHelp();renderPeopleList();$('#peopleMissing').hidden=!result.missing_names;
 $('#peopleMissing').textContent=`هناك ${number(result.missing_names)} وجه موحدة لم يُقرأ اسمه بما يكفي لإنشاء ملف. أعد القراءة أو صحّح الاسم ثم حدّث الملفات.`;
 return result;
}
async function refreshPeopleSummary(bid,openAfterUpload=false){
 const request=++peopleState.summaryRequest;
 try{
  const result=await api('/api/people');
  if(request!==peopleState.summaryRequest||state.batch?.id!==bid)return;
  peopleState.items=result.people;peopleState.mode=result.mode;
  const related=result.people.filter(p=>p.batch_ids.includes(bid));
  $('#peopleBanner').hidden=!related.length;
  $('#peopleBannerText').textContent=`${number(related.length)} ملف شخص مرتبط بهذه الدفعة · يجمع المستمسكات والبيانات من جميع الرفعات`;
  if(openAfterUpload&&related.length&&!document.querySelector('dialog[open]')){peopleState.active=related.length===1?related[0].id:null;await openPeople(peopleState.active);}
 }catch(error){$('#peopleBanner').hidden=false;$('#peopleBannerText').textContent='تعذر تحديث ملفات الأشخاص. افتح الملفات لإعادة المحاولة.';}
}
async function openPeople(pid=null){
 if(!peopleDialog.open)peopleDialog.showModal();
 $('#peopleError').hidden=true;
 try{
  await fetchPeopleList();
  const target=pid||peopleState.active;
  if(target&&peopleState.items.some(p=>p.id===target))await loadPerson(target);
  else if(peopleState.items.length===1)await loadPerson(peopleState.items[0].id);
  else if(!peopleState.items.some(p=>p.id===peopleState.active)){
   peopleState.active=null;peopleState.detail=null;$('#personDetail').innerHTML='<div class="person-empty"><h3>اختر ملف شخص</h3><p>ستظهر بياناته ومستمسكاته واقتراحات السكن هنا.</p></div>';
  }
 }catch(e){$('#peopleError').textContent=e.message;$('#peopleError').hidden=false;}
}
function fieldSource(ref){return `<button class="text-button" data-person-source="${escape(ref)}">عرض المصدر ↗</button>`;}
function acceptDetail(detail,reset=false){
 const previous=new Set(peopleState.detail?.id===detail.id?peopleState.detail.documents.map(e=>e.ref):[]);
 peopleState.detail=detail;peopleState.active=detail.id;
 if(reset)peopleState.selected=new Set(detail.recommended_refs);
 else peopleState.selected=new Set([...peopleState.selected].filter(r=>detail.documents.some(e=>e.ref===r)).concat(detail.documents.filter(e=>!previous.has(e.ref)&&detail.recommended_refs.includes(e.ref)).map(e=>e.ref)));
 renderPerson();renderPeopleList();
}
async function loadPerson(pid){
 const request=++peopleState.request;peopleState.active=pid;renderPeopleList();
 $('#personDetail').innerHTML='<p class="person-empty">جارٍ جمع بيانات الشخص ومستمسكاته…</p>';
 try{const detail=await api('/api/people/'+pid);if(request===peopleState.request)acceptDetail(detail,true);}
 catch(e){if(request===peopleState.request)$('#personDetail').innerHTML=`<p class="notice error">${escape(e.message)}</p>`;}
}
function renderPerson(){
 const p=peopleState.detail;if(!p)return;
 const linked=new Set(p.documents.map(e=>e.ref));
 $('#personDetail').innerHTML=`
 <div class="person-heading"><div><p class="eyebrow">ملف الشخص</p><h3>${escape(p.name)}</h3><p>${number(p.documents.length)} مستمسك · ${number(new Set(p.documents.map(e=>e.batch_id)).size)} دفعة</p></div><button class="primary" id="personExport">طباعة وتصدير الملف</button></div>
 ${p.needs_review?'<p class="notice">الملف يحتوي على بيانات أو روابط تحتاج مراجعة. افتح المصدر لتصحيح القراءة.</p>':''}
 <section class="person-section"><h4>بيانات البطاقة الموحدة</h4>${p.extracted_name&&p.display_name?`<p>الاسم في الموحدة: ${escape(p.extracted_name)}</p>`:''}
 <div class="person-fields">${p.fields.map(f=>`<div><span>${escape(f.label)}</span><strong dir="auto">${escape(f.value)}</strong><small>${f.verified?'تمت المراجعة':f.status==='conflict'?'قراءات متعارضة':f.status==='approximate'?'قراءة تقريبية تحتاج تدقيقًا':'قراءة آلية تحتاج مراجعة'}</small>${fieldSource(f.source_ref)}</div>`).join('')||'<p class="field-help">لا توجد بيانات موحدة متاحة في هذا الملف.</p>'}</div>
 ${p.conflicts.length?`<div class="notice error">بيانات مختلفة بين المستمسكات: ${p.conflicts.map(c=>`${escape(c.label)} (${c.values.map(f=>escape(f.value)).join(' / ')})`).join('، ')}. راجع المصادر.</div>`:''}</section>
 <section class="person-section"><h4>بيانات السكن في المستمسكات المرتبطة</h4><p class="person-help">الاسم المشابه يقترح ارتباطًا بالأسرة؛ لا يثبت القرابة أو الإقامة الحالية. تبقى بيانات رب الأسرة منفصلة عن بيانات الشخص.</p>
 ${p.housing.map(h=>`<article class="housing-summary"><div><strong>${escape(h.head_name||'اسم رب الأسرة غير مقروء')}</strong><span class="badge ${h.confirmed?'ready':''}">${h.confirmed?'الربط معتمد يدويًا':'ربط يحتاج مراجعة'}</span></div><p>${escape(h.relationship_label)}</p><dl>${h.fields.map(f=>`<div><dt>${escape(f.label)}</dt><dd>${escape(f.value)}${f.verified?'':f.status==='approximate'?' · قراءة تقريبية تحتاج تدقيقًا':' · قراءة تحتاج مراجعة'}</dd></div>`).join('')||'<p>العنوان غير مقروء؛ افتح المصدر لمراجعته.</p>'}</dl>${fieldSource(h.ref)}</article>`).join('')||'<p class="person-empty compact">لم تُضف بطاقة سكن لهذا الملف بعد.</p>'}</section>
 <section class="person-section"><div class="person-section-heading"><h4>اقتراحات ربط بطاقة السكن <span class="count-pill">${number(p.suggestions.length)}</span></h4></div>
 ${p.suggestions.map(s=>`<article class="housing-proposal"><button class="proposal-image" data-person-source="${escape(s.ref)}" aria-label="عرض بطاقة السكن المقترحة"><img src="/api/images/${s.document.image_id}" alt="بطاقة السكن المقترحة" loading="lazy"></button><div><span class="badge">${linked.has(s.ref)?'أضيف تلقائيًا · يحتاج اعتماد':'اقتراح للمراجعة'}</span><h5>${escape(s.head_name)}</h5><p>${escape(s.reason)}</p><p class="person-help">${escape(s.batch_name)} · ${s.relationship==='father_household'?'سكن محتمل باسم الأب':'بطاقة باسم الشخص'}${s.candidate_count>1?' · الاسم يناسب '+number(s.candidate_count)+' ملفات؛ اختر يدويًا':''}${!s.reliable?' · القراءة تحتاج تدقيقًا':''}</p><div class="person-actions"><button class="secondary" data-accept-proposal="${escape(s.ref)}">${linked.has(s.ref)?'اعتماد الربط':'إضافة إلى الملف'}</button><button class="text-button" data-dismiss-proposal="${escape(s.ref)}">تجاهل الاقتراح</button></div></div></article>`).join('')||'<p class="person-empty compact">لا توجد اقتراحات جديدة. يمكنك إضافة أي مستمسك يدويًا.</p>'}</section>
 <section class="person-section">${p.duplicate_count?`<p class="notice">هناك ${number(p.duplicate_count)} نسخة إضافية. يُحدّد افتراضيًا وجه واحد لكل رقم بطاقة مطابق للطباعة، وتبقى كل النسخ متاحة. اختيار «تحديد الكل» يطبع النسخ الإضافية أيضًا.</p>`:''}<div class="person-section-heading"><h4>مستمسكات الملف</h4><button class="secondary" id="personAttach">إضافة مستمسكات يدويًا</button></div><div class="person-selection"><label><input id="personSelectAll" type="checkbox">تحديد الكل للطباعة</label><span id="personSelectedCount"></span></div>
 <div class="person-documents">${p.documents.map(e=>`<article class="person-document"><label class="person-doc-select"><input type="checkbox" data-person-select="${escape(e.ref)}" ${peopleState.selected.has(e.ref)?'checked':''}>${escape(state.types[e.document.kind]||e.document.kind)} · ${escape(sideLabel[e.document.side])}</label><button class="person-doc-image" data-person-source="${escape(e.ref)}" aria-label="مراجعة المستمسك"><img src="/api/images/${e.document.image_id}" alt="${escape(state.types[e.document.kind])}" loading="lazy"></button><p>${escape(e.batch_name)}</p><span class="badge ${e.needs_review?'':'ready'}">${e.method==='auto_name'?'ربط تلقائي يحتاج اعتماد':e.method==='national_serial'?'رقم البطاقة متطابق':e.needs_review?'تغيّرت البيانات؛ راجع الربط':escape(e.relationship_label)}</span><div class="person-actions">${fieldSource(e.ref)}${!p.seed_refs.includes(e.ref)?`<button class="text-button" data-unlink-person="${escape(e.ref)}">فك الربط</button>${e.needs_review&&e.method==='manual'?`<button class="secondary" data-confirm-link="${escape(e.ref)}">إعادة اعتماد الربط</button>`:''}`:''}</div></article>`).join('')}</div></section>
 <details class="person-notes"><summary>اسم عرض الملف وملاحظاتك</summary><label>اسم عرض الملف (اختياري)<input id="personDisplayName" value="${escape(p.display_name)}" maxlength="160"></label><label>ملاحظات<textarea id="personNotes" rows="3" maxlength="3000">${escape(p.notes)}</textarea></label><button id="savePersonNotes" class="secondary">حفظ الملاحظات</button></details>`;
 $$('[data-person-source]').forEach(b=>b.onclick=()=>action(b,()=>openPersonSource(b.dataset.personSource)));
 $$('[data-accept-proposal]').forEach(b=>b.onclick=()=>profileAction(b,async()=>{
  const s=p.suggestions.find(s=>s.ref===b.dataset.acceptProposal);return mutateLinks('POST',[s.ref],s.relationship);
 }));
 $$('[data-dismiss-proposal]').forEach(b=>b.onclick=()=>profileAction(b,()=>mutateLinks('DELETE',[b.dataset.dismissProposal])));
 $$('[data-unlink-person]').forEach(b=>b.onclick=()=>profileAction(b,()=>mutateLinks('DELETE',[b.dataset.unlinkPerson])));
 $$('[data-confirm-link]').forEach(b=>b.onclick=()=>profileAction(b,()=>mutateLinks('POST',[b.dataset.confirmLink],p.documents.find(e=>e.ref===b.dataset.confirmLink).relationship)));
 $$('[data-person-select]').forEach(c=>c.onchange=()=>{c.checked?peopleState.selected.add(c.dataset.personSelect):peopleState.selected.delete(c.dataset.personSelect);personSelection();});
 $('#personSelectAll').onchange=e=>{peopleState.selected=e.target.checked?new Set(p.documents.map(d=>d.ref)):new Set();$$('[data-person-select]').forEach(c=>c.checked=e.target.checked);personSelection();};
 $('#personAttach').onclick=()=>openAttach();$('#personExport').onclick=openPersonExport;
 $('#savePersonNotes').onclick=()=>profileAction($('#savePersonNotes'),()=>api(`/api/people/${p.id}`,json('PATCH',{revision:p.revision,display_name:$('#personDisplayName').value,notes:$('#personNotes').value})));
 personSelection();
}
function personSelection(){
 const total=peopleState.detail?.documents.length||0;
 $('#personSelectedCount').textContent=`${number(peopleState.selected.size)} محدد للطباعة`;
 $('#personSelectAll').checked=!!total&&peopleState.selected.size===total;$('#personSelectAll').indeterminate=peopleState.selected.size>0&&peopleState.selected.size<total;
 $('#personExport').disabled=!peopleState.selected.size;
}
async function profileAction(button,fn){
 const pid=peopleState.active;
 await action(button,async()=>{const p=await fn();if(peopleState.active===pid)acceptDetail(p);await fetchPeopleList();toast('حُفظ تحديث ملف الشخص.');});
}
function mutateLinks(method,refs,relationship='supporting'){
 const p=peopleState.detail;return api(`/api/people/${p.id}/links`,json(method,{refs,relationship,revision:p.revision}));
}
async function openPersonSource(ref){
 const [bid,did]=ref.split(':');
 peopleDialog.close();if($('#personAttachDialog').open)$('#personAttachDialog').close();
 state.selected.clear();await refreshBatch(bid);localStorage.setItem('lastBatch',bid);
 const url=new URL(location.href);url.searchParams.set('batch',bid);history.replaceState(null,'',url);
 if(!currentDocs().some(d=>d.id===did))throw Error('المستمسك غير موجود. حدّث ملف الشخص.');
 await openEditor(did);
}
async function openAttach(bulkRefs=null){
 peopleState.bulkRefs=bulkRefs;attachSelection.clear();attachRevision=null;
 $('#attachError').hidden=true;$('#attachRelation').value='supporting';$('#attachSearch').value='';
 $('#attachPersonLabel').hidden=!bulkRefs;$('#attachSearchLabel').hidden=!!bulkRefs;
 $('#attachList').textContent='جارٍ تحميل المستمسكات…';$('#confirmAttach').disabled=true;
 $('#personAttachDialog').showModal();
 try{
  if(bulkRefs){
   await fetchPeopleList();$('#attachPerson').innerHTML=peopleState.items.map(p=>`<option value="${p.id}">${escape(p.name)}</option>`).join('');
   $('#attachList').textContent=`سيُضاف ${number(bulkRefs.length)} مستمسك محدد إلى الملف الذي تختاره.`;
   if(!peopleState.items.length)throw Error('لا يوجد ملف شخص بعد. راجع اسم صاحب الموحدة أولًا.');
   await loadAttachRevision();
  }else{
   const result=await api(`/api/people/${peopleState.active}/available`);attachRevision=result.revision;peopleState.available=result.documents;renderAttach();
  }
  $('#confirmAttach').disabled=false;
 }catch(e){$('#attachError').textContent=e.message;$('#attachError').hidden=false;}
}
async function loadAttachRevision(){
 attachRevision=null;$('#confirmAttach').disabled=true;
 const pid=$('#attachPerson').value;const p=await api('/api/people/'+pid);
 if($('#attachPerson').value===pid){attachRevision=p.revision;$('#confirmAttach').disabled=false;}
}
function renderAttach(){
 const query=$('#attachSearch').value.trim();
 const items=peopleState.available.filter(e=>!query||[e.batch_name,state.types[e.document.kind],...e.document.fields.map(f=>f.value)].join(' ').includes(query));
 $('#attachList').innerHTML=items.map(e=>`<label class="attach-item"><input type="checkbox" data-attach-ref="${escape(e.ref)}" ${attachSelection.has(e.ref)?'checked':''}><img src="/api/images/${e.document.image_id}" alt="" loading="lazy"><span><strong>${escape(state.types[e.document.kind]||e.document.kind)} · ${escape(sideLabel[e.document.side])}</strong><small>${escape(e.batch_name)}</small><small>${escape(e.document.fields.find(f=>f.key==='name')?.value||'')}</small></span></label>`).join('')||'<p>لا توجد مستمسكات متاحة بهذه التصفية. ارفع الملفات أولًا من مساحة المستمسكات.</p>';
 $$('[data-attach-ref]').forEach(c=>c.onchange=()=>{c.checked?attachSelection.add(c.dataset.attachRef):attachSelection.delete(c.dataset.attachRef);});
}
$('#confirmAttach').onclick=()=>action($('#confirmAttach'),async()=>{
 $('#attachError').hidden=true;
 try{
  const pid=peopleState.bulkRefs?$('#attachPerson').value:peopleState.active;
  const refs=peopleState.bulkRefs||[...attachSelection];if(!refs.length)throw Error('اختر مستمسكًا واحدًا على الأقل.');
  if(!attachRevision)throw Error('انتظر تحميل الملف.');
  const p=await api(`/api/people/${pid}/links`,json('POST',{refs,relationship:$('#attachRelation').value,revision:attachRevision}));
  $('#personAttachDialog').close();if(!peopleDialog.open)peopleDialog.showModal();acceptDetail(p,true);await fetchPeopleList();toast('أضيفت المستمسكات إلى ملف الشخص.');
 }catch(e){$('#attachError').textContent=e.message;$('#attachError').hidden=false;}
});
$('#attachPerson').onchange=()=>loadAttachRevision().catch(e=>{$('#attachError').textContent=e.message;$('#attachError').hidden=false;});
$('#attachSearch').oninput=renderAttach;
function openPersonExport(){
 const p=peopleState.detail;personExportTarget={pid:p.id,revision:p.revision,refs:[...peopleState.selected]};
 $('#personExportSummary').textContent=`ملف «${p.name}» · ${number(personExportTarget.refs.length)} مستمسك محدد من جميع الدفعات.`;
 PrintBoard.prepare(`person:${p.id}`,p.documents.filter(e=>peopleState.selected.has(e.ref)).map(e=>({key:e.ref,document:e.document,group:e.print_group})));
 refreshPersonPrintStatus();
 $('#personExportDraft').checked=false;$('#personExportError').hidden=true;$('#personExportDialog').showModal();
}
async function exportPerson(preview){
 const target=personExportTarget;if(!target)return;
 const win=preview?window.open('about:blank','_blank'):null;
 if(preview&&!win)throw Error('اسمح بفتح نافذة المعاينة أو نزّل PDF للطباعة.');
 if(win)win.opener=null;
 try{
  const format=preview?'pdf':$('#personExportFormat').value;
  const layout=$('#personExportLayout').value,plan=['pdf','zip'].includes(format)?PrintBoard.payload(`person:${target.pid}`,layout):null;
  const response=await api(`/api/people/${target.pid}/export`,json('POST',{revision:target.revision,refs:plan?.keys||target.refs,format,layout,size:$('#personExportSize').value,allow_unreviewed:$('#personExportDraft').checked,...(plan?{pages:plan.pages}:{})}));
  // JSON export is intentionally handled as data by api().
  const blob=response instanceof Response?await response.blob():new Blob([JSON.stringify(response,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  if(win){if(pdfUrl)URL.revokeObjectURL(pdfUrl);pdfUrl=url;win.location.replace(url);}
  else{const a=document.createElement('a');a.href=url;a.download=`person-${target.pid.slice(0,8)}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
  toast('تم تجهيز ملف الشخص للتصدير.');
 }catch(e){if(win&&!win.closed)win.close();$('#personExportError').textContent=e.message;$('#personExportError').hidden=false;}
}
$('#personPreview').onclick=()=>action($('#personPreview'),()=>exportPerson(true));
$('#personDownload').onclick=()=>action($('#personDownload'),()=>exportPerson(false));
$('#peopleNav').onclick=()=>openPeople();$('#openPeopleBanner').onclick=()=>openPeople();
$('#peopleSearch').oninput=renderPeopleList;
$('#refreshPeople').onclick=()=>action($('#refreshPeople'),()=>openPeople(peopleState.active));
$('#peopleMode').onchange=()=>action($('#peopleMode'),async()=>{await api('/api/people/settings',json('PATCH',{mode:$('#peopleMode').value}));await openPeople(peopleState.active);toast('تم تحديث وضع ربط بطاقة السكن.');});
$('#addSelectedToPerson').onclick=()=>{
 const refs=currentDocs().filter(d=>state.selected.has(d.id)).map(d=>`${state.batch.id}:${d.id}`);
 if(refs.length)openAttach(refs);
};
if(state.batch&&!['queued','processing'].includes(state.batch.status))refreshPeopleSummary(state.batch.id);
