/* Local field evidence: no remote assets or document requests. */
const fieldStatusLabels={approximate:'قراءة تقريبية · تحتاج تدقيقًا',read:'قراءة واضحة · راجعها',uncertain:'قراءة غير مؤكدة',conflict:'قراءات مختلفة',missing:'لم يُقرأ',unreadable:'غير مقروء بثقة',manual:'إدخال يدوي'};
async function showFieldEvidence(f){
 const d=editorDocument();if(!d||!f.box)return;
 const token=Symbol();state.fieldEvidenceRequest=token;
 const im=new Image();im.src=`/api/images/${f.source_image_id||d.field_image_id||d.image_id}`;await im.decode();
 if(state.fieldEvidenceRequest!==token||state.editorId!==d.id)return;
 const xs=f.box.map(p=>p[0]),ys=f.box.map(p=>p[1]);
 const x=Math.max(0,Math.min(...xs)-4),y=Math.max(0,Math.min(...ys)-4);
 const w=Math.min(im.width-x,Math.max(...xs)-x+4),h=Math.min(im.height-y,Math.max(...ys)-y+4);
 if(w<=0||h<=0)return;
 const c=$('#fieldEvidenceCanvas'),scale=Math.min(5,700/w,200/h);
 c.width=Math.round(w*scale);c.height=Math.round(h*scale);c.getContext('2d').drawImage(im,x,y,w,h,0,0,c.width,c.height);
 $('#fieldEvidenceTitle').textContent=f.label;$('#fieldEvidence').hidden=false;
 $('#fieldEvidence').scrollIntoView({block:'nearest',behavior:'smooth'});
}
function decorateFieldRow(row,f){
 row.dataset.method=f.method||'';
 const status=f.verified?'تمت المراجعة':fieldStatusLabels[f.status]||'تحتاج مراجعة';
 const detail=document.createElement('div');detail.className='field-detail';
 detail.innerHTML=`<div class="field-detail-head"><span class="field-state ${escape(f.status||'uncertain')}">${escape(status)}</span>${f.box?'<button type="button" class="text-button evidence-button">موضع النص ↗</button>':''}</div>${f.note?`<p>${escape(f.note)}</p>`:''}`;
 const sources=[f.source,...(f.candidates||[]).map(c=>c.source)].filter(Boolean);
 const linked=new Set();for(const source of sources){try{const url=new URL(source.url);if(!['https:','http:'].includes(url.protocol)||linked.has(url.href))continue;linked.add(url.href);const p=document.createElement('p'),a=document.createElement('a');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';a.textContent=`مرجع الاقتراح${source.observation_year?' · بيانات '+source.observation_year:''}`;a.title=source.title||'';p.append(a);detail.append(p);}catch{}}
 if(f.box)detail.querySelector('.evidence-button').onclick=()=>showFieldEvidence(f).catch(()=>toast('تعذر عرض موضع النص.',true));
 if(f.status==='missing'||f.status==='unreadable')row.querySelector('.field-value').placeholder='أدخل القيمة بعد مراجعة الصورة';
 const candidates=(f.candidates||[]).filter(c=>c.value&&(!f.value||c.value!==f.value));
 if(candidates.length){
  const list=document.createElement('div');list.className='field-candidates';
  const label=document.createElement('small');label.textContent='اقتراحات غير معتمدة:';list.append(label);
  candidates.slice(0,4).forEach(c=>{const b=document.createElement('button');b.type='button';b.className='candidate-button';b.textContent=c.value;b.title='استخدام هذه القراءة بعد مقارنتها بالصورة';b.onclick=()=>{row.querySelector('.field-value').value=c.value;row.querySelector('.field-value').dispatchEvent(new Event('input'));};list.append(b);});
  detail.append(list);
 }
 row.querySelector('.field-value').addEventListener('input',()=>{if(f.key==='name')row.dataset.method='manual';refreshAssembledName(f.key);const label=detail.querySelector('.field-state');label.textContent='تعديل غير محفوظ';label.className='field-state manual';$('#docReviewed').checked=false;});
 row.append(detail);
}

function refreshAssembledName(changedKey){
 const keys=['first_name','father_name','grandfather_name','surname'];if(!keys.includes(changedKey))return;
 const rows=$$('#fieldList .field-row');const full=rows.find(r=>r.dataset.key==='name'&&r.dataset.method==='assembled_visible_names');if(!full)return;
 const values=keys.map(k=>rows.find(r=>r.dataset.key===k)?.querySelector('.field-value').value.trim()||'');
 full.querySelector('.field-value').value=values.every(Boolean)?values.join(' '):'';
 const label=full.querySelector('.field-state');label.textContent='مجمّع من تعديلك · غير محفوظ';label.className='field-state manual';
}
