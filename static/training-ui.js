/* AI training dashboard: see, track and guide the readers (app/training_center.py, /api/training).
   Everything shown here is on this computer. Text from the server is always set with textContent/escape. */
'use strict';
(function trainingDashboard(){
 paths.chart='M3 20h18 M6 16v-4 M11 16V7 M16 16v-6 M21 16V4';
 const nav=document.createElement('button');nav.className='nav-item';nav.id='trainingNav';
 nav.innerHTML='<span data-icon="chart"></span>لوحة التدريب';($('#geminiNav')||$('#guideNav')).after(nav);icons(nav);
 const dlg=document.createElement('dialog');dlg.id='trainingDialog';dlg.className='training-dialog';
 dlg.innerHTML=`<div class="dialog-heading"><div><p class="eyebrow">تُدرَّب على جهازك فقط</p><h2>لوحة تدريب الذكاء الاصطناعي</h2></div><button class="icon-button" id="closeTraining" aria-label="إغلاق">${icon('close')}</button></div>
 <div class="tabs training-tabs" role="tablist">
  <button class="tab active" data-tab="overview" role="tab">نظرة عامة</button><button class="tab" data-tab="data" role="tab">البيانات</button>
  <button class="tab" data-tab="train" role="tab">التدريب</button><button class="tab" data-tab="history" role="tab">السجل</button></div>
 <section class="training-pane" data-pane="overview">
  <div id="tAdvice" class="training-advice"></div>
  <div id="tModels" class="training-cards"></div>
  <div class="training-cards">
   <article class="training-card"><h3>أرقام مفردة من تصحيحاتك</h3><div id="tDigitChart"></div><p id="tDigitNote" class="field-help"></p></article>
   <article class="training-card"><h3>أرقام كاملة وأسماء من تصحيحاتك</h3><div id="tStrips"></div></article>
  </div>
  <article class="training-card"><div class="training-row"><h3>تقييم النماذج على بياناتك</h3><button class="secondary" id="tEvaluate" type="button">قيّم الآن</button></div>
   <p class="field-help">«المحجوزة» عينات لم يُدرَّب عليها النموذج أبدًا: هي الاختبار الصادق. «المدرَّب عليها» تبيّن ما حفظه.</p>
   <div id="tEval"></div><div id="tEvalChart"></div></article>
 </section>
 <section class="training-pane" data-pane="data" hidden>
  <div class="training-row"><div class="segmented"><button class="active" data-kind="strips" type="button">أرقام كاملة</button><button data-kind="digits" type="button">أرقام مفردة</button></div>
   <label class="inline">التصنيف<select id="tLabel"><option value="">الكل</option></select></label><span id="tCount" class="field-help"></span></div>
  <p class="field-help">هنا توجّه التدريب: صحّح التصنيف الخاطئ أو احذف العينة السيئة. عينة بتصنيف خاطئ تعلّم النموذج الخطأ.</p>
  <div id="tSamples" class="sample-grid"></div><button id="tMore" class="text-button" type="button" hidden>عرض المزيد</button>
 </section>
 <section class="training-pane" data-pane="train" hidden>
  <div class="training-cards">
   <article class="training-card"><h3>ماذا تدرّب؟</h3>
    <label class="review-check compact"><input type="checkbox" id="tTrainNumbers" checked>قارئ الأرقام الخاص (الرقم كاملًا)</label>
    <label class="review-check compact"><input type="checkbox" id="tTrainDigits">قارئ الأرقام رقمًا رقمًا</label>
    <label>عدد الخطوات لقارئ الأرقام الخاص<input type="number" id="tSteps" min="200" max="20000" step="100" value="1500"></label>
    <p id="tEstimate" class="field-help"></p>
    <label>نسبة شرائحك في كل دفعة: <b id="tShareText">30%</b><input type="range" id="tShare" min="0" max="80" value="30"></label>
    <p class="field-help">نسبة أعلى تجعله أقرب لخطوط مكاتبكم، لكن مع عينات قليلة قد يحفظها بدل أن يتعلم. لا يُثبّت أي نموذج إلا إذا لم تنخفض دقته.</p>
    <div class="training-row"><button class="primary" id="tStart" type="button">ابدأ التدريب</button><button class="secondary" id="tStop" type="button" hidden>إيقاف</button></div>
   </article>
   <article class="training-card"><h3>التقدم</h3><p id="tState" class="local-ai-state">—</p><progress id="tProgress" max="1" value="0"></progress>
    <div id="tLossChart"></div><div id="tHeldChart"></div></article>
  </div>
  <details><summary>سجل التدريب المباشر</summary><pre id="tLog" dir="ltr"></pre></details>
 </section>
 <section class="training-pane" data-pane="history" hidden><div id="tHistChart"></div><div id="tHistory"></div></section>`;
 document.body.append(dlg);

 const pct=v=>v==null?'—':`${(v*100).toFixed(1)}%`;
 const STATE={idle:'لم يبدأ أي تدريب بعد.',running:'يجري التدريب…',installed:'انتهى: ثُبّت نموذج جديد.',rejected:'انتهى: بقي النموذج الحالي (الجديد لم يكن أفضل).',
  failed:'فشل التدريب.',interrupted:'توقف قبل اكتماله.',stopped:'أوقفته أنت.',rollback:'رجوع إلى نسخة سابقة.'};
 const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};
 let data=null,kind='strips',offset=0,poll=null;

 function chart(series,{title,percent=false,height=150}={}){
  // series: [{name,points:[[x,y]],colour}]
  const all=series.flatMap(s=>s.points);if(!all.length)return '';
  const W=520,H=height,P=34,xs=all.map(p=>p[0]),ys=all.map(p=>p[1]);
  let x0=Math.min(...xs),x1=Math.max(...xs),y0=percent?Math.min(...ys,1)*.98:Math.min(...ys),y1=percent?1:Math.max(...ys);
  if(percent)y0=Math.max(0,Math.floor(Math.min(...ys)*20)/20);if(x1===x0)x1=x0+1;if(y1===y0)y1=y0+1;
  const X=x=>P+(x-x0)/(x1-x0)*(W-P-10),Y=y=>H-22-(y-y0)/(y1-y0)*(H-34);
  const fmt=v=>percent?`${Math.round(v*100)}%`:(Math.abs(v)<10?v.toFixed(2):Math.round(v));
  let svg=`<svg viewBox="0 0 ${W} ${H}" class="training-chart" role="img" aria-label="${escape(title||'')}">`;
  for(const t of [0,.5,1]){const v=y0+(y1-y0)*t;svg+=`<line x1="${P}" x2="${W-10}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/><text x="${P-4}" y="${Y(v)+4}" text-anchor="end">${fmt(v)}</text>`;}
  svg+=`<text x="${P}" y="${H-5}">${escape(String(x0))}</text><text x="${W-10}" y="${H-5}" text-anchor="end">${escape(String(x1))}</text>`;
  series.forEach(s=>{if(!s.points.length)return;const d=s.points.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('');
   svg+=`<path d="${d}" fill="none" stroke="${s.colour}" stroke-width="2"/>`+s.points.map(p=>`<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="2.5" fill="${s.colour}"><title>${escape(s.name)}: ${fmt(p[1])}</title></circle>`).join('');});
  svg+='</svg>';
  const legend=series.length>1?`<div class="chart-legend">${series.map(s=>`<span><i style="background:${s.colour}"></i>${escape(s.name)}</span>`).join('')}</div>`:'';
  return `<figure class="chart-box"><figcaption>${escape(title||'')}</figcaption>${svg}${legend}</figure>`;
 }
 function bars(counts,min){
  const keys=Object.keys(counts),max=Math.max(min*2,...Object.values(counts)),W=520,H=150,bw=(W-40)/keys.length;
  let svg=`<svg viewBox="0 0 ${W} ${H}" class="training-chart" role="img" aria-label="عدد العينات لكل رقم">`;
  const y=v=>H-24-v/max*(H-40);
  svg+=`<line x1="30" x2="${W-6}" y1="${y(min)}" y2="${y(min)}" class="min-line"/><text x="${W-6}" y="${y(min)-4}" text-anchor="end" class="min-text">الحد الأدنى المقترح ${min}</text>`;
  keys.forEach((k,i)=>{const v=counts[k],x=34+i*bw;svg+=`<rect x="${x}" y="${y(v)}" width="${bw*.62}" height="${H-24-y(v)}" rx="3" class="${v<min?'bar weak':'bar'}"><title>${escape(k)}: ${v}</title></rect>
   <text x="${x+bw*.31}" y="${H-8}" text-anchor="middle">${k==='noise'?'ليس رقمًا':'٠١٢٣٤٥٦٧٨٩'[+k]}</text><text x="${x+bw*.31}" y="${y(v)-3}" text-anchor="middle">${v}</text>`;});
  return svg+'</svg>';
 }

 async function load(){
  try{data=await api('/api/training');}catch(e){toast(e.message,true);return;}
  const adv=$('#tAdvice');adv.replaceChildren(el('h3',null,'ما الذي يحتاجه التدريب الآن؟'));
  const ul=el('ul');data.advice.forEach(t=>ul.append(el('li',null,t)));adv.append(ul);
  if(!data.learning_enabled)adv.append(el('p','notice','التعلم من التصحيحات مطفأ؛ شغّله من إعدادات القراءة لتُحفظ العينات.'));
  const box=$('#tModels');box.replaceChildren();
  data.models.forEach(m=>{const c=el('article','training-card model-card');
   c.append(el('h3',null,m.name),el('p','field-help',`${m.kind} · ${m.exists?'آخر تحديث '+m.updated:'غير مثبّت'}${m.steps?` · ${number(m.steps)} خطوة`:''}`));
   Object.entries(m.metrics).forEach(([k,v])=>{const row=el('div','metric');row.append(el('span',null,k),el('b',null,pct(v)));
    const bar=el('i');bar.style.width=v==null?'0':`${Math.round(v*100)}%`;const track=el('span','metric-bar');track.append(bar);row.append(track);c.append(row);});
   if(m.previous){const b=el('button','text-button','الرجوع إلى النسخة السابقة ('+m.previous+')');b.type='button';b.onclick=()=>rollback(m.id,m.name);c.append(b);}
   box.append(c);});
  const d=data.data;$('#tDigitChart').innerHTML=bars(Object.fromEntries(Object.entries(d.digits)),5);
  $('#tDigitNote').textContent=`المجموع ${number(Object.values(d.digits).reduce((a,b)=>a+b,0))} (منها ${number(d.digits_kept_aside)} محجوزة للاختبار) · يلزم ${number(d.min_samples)} للتدريب.`;
  const s=$('#tStrips');s.replaceChildren();
  const strip=el('p',null,`شرائح أرقام كاملة: ${number(d.strips)} (منها ${number(d.strips_kept_aside)} محجوزة) · يلزم ${number(d.min_strips)} لضبط القارئ الخاص على خطوطكم.`);
  const prog=el('progress');prog.max=d.min_strips;prog.value=Math.min(d.strips,d.min_strips);
  const fields=el('p','field-help',Object.entries(d.strips_by_field).map(([k,v])=>`${k}: ${v}`).join(' · '));
  s.append(strip,prog,fields,el('p',null,`أسماء تعلّمها من تصحيحاتك: ${number(d.name_words)}`));
  if(d.top_names.length){const chips=el('div','chips');d.top_names.forEach(n=>chips.append(el('span','chip',n)));s.append(chips);}
  showEval(data.evaluations);showHistory(data.history);showState(data.training);
  $('#tTrainDigits').disabled=Object.values(d.digits).reduce((a,b)=>a+b,0)<d.min_samples;
  $('#tTrainNumbers').disabled=!data.models.find(m=>m.id==='numbers').exists;
 }
 function showEval(list){
  const last=list[list.length-1],box=$('#tEval');box.replaceChildren();
  if(!last){box.append(el('p','field-help','لم يُقيَّم بعد. اضغط «قيّم الآن».'));$('#tEvalChart').innerHTML='';return;}
  box.append(el('p','field-help','آخر تقييم: '+last.when));
  const table=el('table','training-table');const head=el('tr');['النموذج','المحجوزة (اختبار صادق)','المدرَّب عليها','أكثر الأخطاء'].forEach(h=>head.append(el('th',null,h)));table.append(head);
  [['numbers','قارئ الأرقام الخاص'],['digits','قارئ الأرقام رقمًا رقمًا']].forEach(([k,n])=>{const r=last[k];const tr=el('tr');
   tr.append(el('td',null,n));
   if(!r){tr.append(el('td',null,'لا عينات بعد'),el('td',null,'—'),el('td',null,'—'));}
   else tr.append(el('td',null,`${pct(r.kept_aside_accuracy)} (${r.kept_aside})`),el('td',null,`${pct(r.trained_on_accuracy)} (${r.trained_on})`),
    el('td',null,(r.confusions||[]).slice(0,3).map(([p,c])=>{const [w,g]=p.split('→');return `${w} قُرئ ${g==='noise'?'ليس رقمًا':g} ×${c}`;}).join('، ')||'—'));table.append(tr);});
  box.append(table);
  const m=last.numbers?.mistakes||[];
  if(m.length){box.append(el('h4',null,'أخطاء قارئ الأرقام الخاص على شرائحك'));const g=el('div','sample-grid small');
   m.slice(0,12).forEach(x=>g.append(sampleCard('strips',{id:x.id,label:x.label,kept_aside:x.kept_aside,read:x.read})));box.append(g);}
  const series=[['numbers','قارئ الأرقام الخاص','#12675d'],['digits','رقمًا رقمًا','#946622']].map(([k,n,c])=>({name:n,colour:c,
   points:list.map((e,i)=>[i+1,e[k]?.kept_aside_accuracy]).filter(p=>p[1]!=null)}));
  $('#tEvalChart').innerHTML=chart(series,{title:'دقة العينات المحجوزة عبر التقييمات',percent:true});
 }
 async function evaluate(){
  await action($('#tEvaluate'),async()=>{$('#tEval').textContent='جارٍ التقييم…';const r=await api('/api/training/evaluate',{method:'POST'});await load();toast(`انتهى التقييم (${r.seconds} ث).`);});
 }
 async function rollback(model,name){
  if(!confirm(`الرجوع إلى النسخة السابقة من «${name}»؟ يمكنك التراجع بالزر نفسه.`))return;
  try{await api('/api/training/rollback',json('POST',{model}));toast('تم الرجوع إلى النسخة السابقة.');load();}catch(e){toast(e.message,true);}
 }

 function sampleCard(k,item){
  const c=el('figure','sample-card'+(item.kept_aside?' kept':''));
  const img=el('img');img.loading='lazy';img.alt=item.label;img.src=`/api/training/samples/${k}/image?id=${encodeURIComponent(item.id)}`;c.append(img);
  const cap=el('figcaption');
  const input=el('input');input.value=item.label==='noise'?'noise':item.label;input.dir='ltr';input.setAttribute('aria-label','التصنيف');input.inputMode=k==='strips'?'numeric':'text';
  const save=el('button','text-button','حفظ');save.type='button';
  save.onclick=async()=>{try{const r=await api(`/api/training/samples/${k}?id=${encodeURIComponent(item.id)}`,json('PATCH',{label:input.value.trim()}));item.id=r.id;item.label=input.value.trim();toast('صُحّح التصنيف.');}catch(e){toast(e.message,true);}};
  const del=el('button','text-button danger','حذف');del.type='button';
  del.onclick=async()=>{if(!confirm('حذف هذه العينة من بيانات التدريب؟'))return;try{await api(`/api/training/samples/${k}?id=${encodeURIComponent(item.id)}`,{method:'DELETE'});c.remove();toast('حُذفت العينة.');}catch(e){toast(e.message,true);}};
  cap.append(input,save,del);
  const meta=[item.field,item.kept_aside?'محجوزة للاختبار':'',item.read!=null?`قرأها: ${item.read||'لا شيء'}`:''].filter(Boolean).join(' · ');
  if(meta)cap.append(el('small',null,meta));
  c.append(cap);return c;
 }
 async function samples(reset=true){
  if(reset){offset=0;$('#tSamples').replaceChildren();}
  const label=$('#tLabel').value;
  try{const r=await api(`/api/training/samples/${kind}?offset=${offset}&limit=60${label?`&label=${encodeURIComponent(label)}`:''}`);
   r.items.forEach(i=>$('#tSamples').append(sampleCard(kind,i)));offset+=r.items.length;
   $('#tCount').textContent=`${number(r.total)} عينة`;$('#tMore').hidden=offset>=r.total;
   if(!r.total)$('#tSamples').append(el('p','field-help',kind==='strips'?'لا شرائح بعد: تُحفظ عندما تصحّح أو تعتمد رقم محلة أو زقاق أو دار أو استمارة وتحفظ البطاقة.':'لا عينات بعد.'));}
  catch(e){toast(e.message,true);}
 }
 function labelOptions(){
  const sel=$('#tLabel');sel.replaceChildren(el('option',null,'الكل'));sel.firstChild.value='';
  if(kind==='digits')['1','2','3','4','5','6','7','8','9','noise'].forEach(v=>{const o=el('option',null,v==='noise'?'ليس رقمًا':'٠١٢٣٤٥٦٧٨٩'[+v]);o.value=v;sel.append(o);});
  sel.disabled=kind!=='digits';
 }

 function showState(t){
  const s=t||{};$('#tState').textContent=(STATE[s.state]||s.state||'—')+(s.message&&s.state!=='running'?' '+s.message:'')+(s.finished?` (${s.finished})`:'');
  $('#tState').dataset.kind=s.state==='installed'?'ready':s.state==='running'?'':['failed','rejected','stopped','interrupted'].includes(s.state)?'warn':'off';
  const running=s.state==='running';$('#tStart').disabled=running;$('#tStop').hidden=!running;
  if(running&&!poll)poll=setInterval(progress,3000);
  if(!running&&poll){clearInterval(poll);poll=null;}
 }
 async function progress(){
  let p;try{p=await api('/api/training/progress');}catch{return;}
  showState(p.state);
  const n=p.numbers,total=p.total_steps||p.state.steps;
  const step=n.steps[n.steps.length-1]||0;
  $('#tProgress').max=total||1;$('#tProgress').value=p.phase==='numbers'?step:0;
  if(p.state.state==='running')$('#tState').textContent=`يجري التدريب · ${p.phase==='digits'?'قارئ الأرقام رقمًا رقمًا':p.phase==='numbers'?`قارئ الأرقام الخاص: الخطوة ${number(step)} من ${number(total||0)}`:'يبدأ…'}`;
  $('#tLossChart').innerHTML=chart([{name:'الخسارة',colour:'#946622',points:n.steps.map((s,i)=>[s,n.loss[i]])}],{title:'خسارة التدريب (كلما قلّت كان أفضل)'});
  $('#tHeldChart').innerHTML=chart([{name:'كتّاب لم يرهم',colour:'#12675d',points:n.held_out}],{title:'الدقة على كتّاب لم يرهم',percent:true})
   +chart([{name:'أرقام مولّدة',colour:'#946622',points:p.digits.epochs}],{title:'قارئ الأرقام رقمًا رقمًا: الدقة بعد كل دورة',percent:true});
  $('#tLog').textContent=p.tail.join('\n');
  if(p.state.state!=='running'&&data&&p.state.finished&&data.training?.finished!==p.state.finished)load();
 }
 function estimate(){const s=+$('#tSteps').value||0;const mins=Math.round(s*1.1/60)+($('#tTrainDigits').checked?20:0);
  $('#tEstimate').textContent=`المدة التقريبية: ${number(mins)} دقيقة (بأولوية منخفضة؛ يمكنك متابعة العمل).`;}
 async function start(){
  const models=[...($('#tTrainNumbers').checked&&!$('#tTrainNumbers').disabled?['numbers']:[]),...($('#tTrainDigits').checked&&!$('#tTrainDigits').disabled?['digits']:[])];
  if(!models.length)return toast('اختر نموذجًا واحدًا على الأقل.',true);
  try{await api('/api/training/start',json('POST',{models,steps:+$('#tSteps').value,share:+$('#tShare').value/100}));toast('بدأ التدريب في الخلفية.');progress();}
  catch(e){toast(e.message,true);}
 }
 function showHistory(runs){
  const box=$('#tHistory');box.replaceChildren();
  if(!runs.length){box.append(el('p','field-help','لا يوجد سجل بعد.'));$('#tHistChart').innerHTML='';return;}
  const table=el('table','training-table');const head=el('tr');['البداية','النماذج','النتيجة','التفاصيل'].forEach(h=>head.append(el('th',null,h)));table.append(head);
  runs.slice().reverse().forEach(r=>{const tr=el('tr');const names={digits:'رقمًا رقمًا',numbers:'الخاص'};
   const nm=r.results?.numbers?.metrics||{};
   const detail=[r.steps&&r.models?.includes('numbers')?`${number(r.steps)} خطوة`:'',nm.held_out_whole_number_accuracy!=null?`كتّاب لم يرهم ${pct(nm.held_out_whole_number_accuracy)}`:'',
    nm.own_check_accuracy!=null?`شرائحك المحجوزة ${pct(nm.own_check_accuracy)}`:'',r.message||''].filter(Boolean).join(' · ');
   const badge=el('span','badge '+(r.state==='installed'?'ready':''),STATE[r.state]||r.state);
   const td=el('td');td.append(badge);
   tr.append(el('td',null,r.started||''),el('td',null,(r.models||[]).map(m=>names[m]||m).join('، ')),td,el('td',null,detail));table.append(tr);});
  box.append(table);
  const pts=runs.map((r,i)=>[i+1,r.results?.numbers?.metrics?.held_out_whole_number_accuracy]).filter(p=>p[1]!=null);
  $('#tHistChart').innerHTML=chart([{name:'قارئ الأرقام الخاص',colour:'#12675d',points:pts}],{title:'دقة قارئ الأرقام الخاص عبر جولات التدريب',percent:true});
 }

 $$('.training-tabs .tab').forEach(b=>b.onclick=()=>{$$('.training-tabs .tab').forEach(x=>x.classList.toggle('active',x===b));
  $$('.training-pane').forEach(p=>p.hidden=p.dataset.pane!==b.dataset.tab);
  if(b.dataset.tab==='data')samples();if(b.dataset.tab==='train')progress();});
 $$('.segmented button').forEach(b=>b.onclick=()=>{$$('.segmented button').forEach(x=>x.classList.toggle('active',x===b));kind=b.dataset.kind;labelOptions();samples();});
 $('#tLabel').onchange=()=>samples();$('#tMore').onclick=()=>samples(false);
 $('#tEvaluate').onclick=evaluate;$('#tStart').onclick=start;
 $('#tStop').onclick=async()=>{if(!confirm('إيقاف التدريب؟ لن يُثبّت أي نموذج من هذه الجولة.'))return;try{await api('/api/training/stop',{method:'POST'});toast('يجري الإيقاف…');}catch(e){toast(e.message,true);}};
 $('#tShare').oninput=()=>$('#tShareText').textContent=$('#tShare').value+'%';
 $('#tSteps').oninput=estimate;$('#tTrainDigits').onchange=estimate;estimate();
 nav.onclick=()=>{if(!dlg.open)dlg.showModal();labelOptions();load();};
 $('#closeTraining').onclick=()=>dlg.close();
 dlg.addEventListener('close',()=>{if(poll){clearInterval(poll);poll=null;}});
})();
