'use strict';
// The board uses the same millimetre rectangles as the PDF renderer.
const PrintBoard=(()=>{
 const sessions=new Map();let specs,items=[],pages=[],picked=null,undo=[],options,scope;
 const dialog=document.createElement('dialog');dialog.id='printBoard';dialog.className='print-board-dialog';
 dialog.setAttribute('aria-labelledby','printBoardTitle');
 dialog.innerHTML=`<div class="dialog-heading"><div><p class="eyebrow">رتّب نسختك قبل الطباعة</p><h2 id="printBoardTitle">لوحة ترتيب المستمسكات</h2></div><button class="icon-button" id="closePrintBoard" aria-label="إغلاق لوحة الترتيب">${icon('close')}</button></div>
 <div class="print-board-toolbar"><label>قالب الورقة<select id="boardLayout"><option value="grid4">٤ خانات · عمودان وصفّان</option><option value="grid6">٦ خانات · عمودان وثلاثة صفوف</option></select></label><label>حجم الصور<select id="boardSize"><option value="fit">ملء الخانة مع حفظ النسبة</option><option value="card">الموحدة ضمن 85.6 × 54 مم</option></select></label><button id="boardAuto" class="secondary">ترتيب تلقائي</button><button id="boardUndo" class="secondary" disabled>تراجع</button></div>
 <p class="print-board-help">اسحب المستمسك إلى خانة. أو اختره بالنقر ثم اضغط الخانة؛ تعمل الطريقة نفسها بلوحة المفاتيح واللمس. نقل صورة فوق أخرى يبدّل مكانيهما.</p>
 <div class="print-board-workspace"><aside class="print-tray"><h3>المستمسكات المتاحة</h3><p id="boardCounts"></p><div id="boardTray" class="print-tray-list"></div></aside><section class="print-canvas"><div class="print-page-nav"><button id="boardPrevious" class="secondary" aria-label="الصفحة السابقة">السابق</button><label>الصفحة<select id="boardPage"></select></label><button id="boardNext" class="secondary" aria-label="الصفحة التالية">التالي</button></div><div id="boardSheet" class="print-sheet" aria-label="معاينة ترتيب ورقة A4"></div><div class="print-page-actions"><button id="boardAddPage" class="secondary">إضافة صفحة</button><button id="boardDeletePage" class="secondary">إزالة الصفحة الفارغة</button></div></section></div>
 <p id="boardMessage" class="print-board-message" role="status" aria-live="polite"></p><p id="boardError" class="notice error" role="alert" hidden></p>
 <p class="print-board-help">الورق A4. الخانات والأرقام إرشادية ولا تُطبع. اختر مقياس 100% عند الطباعة. يُحفظ الترتيب خلال هذه الجلسة.</p>
 <div class="dialog-actions"><button id="boardPreview" class="secondary">معاينة وطباعة PDF</button><button id="boardApply" class="primary">اعتماد الترتيب</button></div>`;
 document.body.append(dialog);
 const q=s=>dialog.querySelector(s),clone=x=>JSON.parse(JSON.stringify(x));let pageIndex=0;
 const layout=()=>q('#boardLayout').value;
 function label(item){const d=item.document;return `${state.types[d.kind]||d.kind} · ${sideLabel[d.side]||''} · ${d.group||d.source_name||''}`;}
 function prepare(key,entries){
  const signature=JSON.stringify(entries.map(e=>[e.key,e.document.image_id,e.group]));
  const previous=sessions.get(key);
  sessions.set(key,{items:entries,signature,plan:previous?.signature===signature?previous.plan:null});
 }
 function automatic(entries,name){
  const groups=new Map();entries.forEach(e=>{const g=e.group||e.key;if(!groups.has(g))groups.set(g,[]);groups.get(g).push(e);});
  const flat=[];
  groups.forEach(group=>{group.sort((a,b)=>({front:0,back:1}[a.document.side]??2)-({front:0,back:1}[b.document.side]??2)||(a.document.order||0)-(b.document.order||0));
   for(let i=0;i<group.length;i+=2)flat.push(group[i].key,group[i+1]?.key||null);
  });
  const count=specs[name].slots.length,result=[];for(let i=0;i<flat.length;i+=count)result.push(Array.from({length:count},(_,j)=>flat[i+j]||null));
  return result.length?result:[Array(count).fill(null)];
 }
 function remember(){undo.push({pages:clone(pages),layout:layout(),pageIndex});if(undo.length>30)undo.shift();}
 function message(text){q('#boardMessage').textContent=text;q('#boardError').hidden=true;}
 function find(key){for(let p=0;p<pages.length;p++){const s=pages[p].indexOf(key);if(s>=0)return[p,s];}return null;}
 function select(key){const slot=document.activeElement?.dataset.slot;picked=picked===key?null:key;render();(slot!==undefined?q(`[data-slot="${slot}"]`):[...q('#boardTray').querySelectorAll('[data-print-key]')].find(e=>e.dataset.printKey===key))?.focus();message(picked?'اختر الخانة المطلوبة لوضع المستمسك.':'أُلغي الاختيار.');}
 function place(key,slot){
  if(!items.some(e=>e.key===key))return;
  const old=find(key);if(old?.[0]===pageIndex&&old[1]===slot){picked=null;render();return;}
  remember();const displaced=pages[pageIndex][slot];
  if(old)pages[old[0]][old[1]]=displaced;
  pages[pageIndex][slot]=key;picked=null;render();q(`[data-slot="${slot}"]`)?.focus();message(displaced?'تم تبديل الموضعين؛ الصورة المستبدلة متاحة في القائمة إن لم يكن لها موضع سابق.':'وُضع المستمسك في الخانة.');
 }
 function wireDrag(element,key){element.draggable=true;element.addEventListener('dragstart',e=>{e.dataTransfer.setData('application/x-mustamsak-document',key);e.dataTransfer.effectAllowed='move';});}
 function render(){
  const spec=specs[layout()],used=new Set(pages.flat().filter(Boolean));
  q('#boardCounts').textContent=`${number(used.size)} من ${number(items.length)} في اللوحة · ${number(items.length-used.size)} خارج الطباعة`;
  q('#boardTray').innerHTML=items.map(item=>{const placed=find(item.key);return `<button class="print-tray-item ${picked===item.key?'picked':''}" data-print-key="${escape(item.key)}" aria-pressed="${picked===item.key}" title="${escape(label(item))}"><img src="/api/images/${escape(item.document.image_id)}" alt="" loading="lazy"><span><strong>${escape(state.types[item.document.kind]||item.document.kind)}</strong><small>${escape(sideLabel[item.document.side])} · ${escape(item.document.group||item.document.source_name||'')}</small><small>${placed?`صفحة ${number(placed[0]+1)} · خانة ${number(placed[1]+1)}`:'متاح للإضافة'}</small></span></button>`;}).join('');
  q('#boardTray').querySelectorAll('[data-print-key]').forEach(el=>{el.onclick=()=>select(el.dataset.printKey);wireDrag(el,el.dataset.printKey);});
  q('#boardSheet').innerHTML=spec.slots.map((rect,i)=>{
   const key=pages[pageIndex][i],item=items.find(e=>e.key===key),d=item?.document;
   let image='';if(d){const maxw=q('#boardSize').value==='card'&&d.kind==='national_id'?85.6:rect.width,maxh=q('#boardSize').value==='card'&&d.kind==='national_id'?54:rect.height;
    const w=d.width||2,h=d.height||1,scale=Math.min(maxw/w,maxh/h);
    image=`<img src="/api/images/${escape(d.image_id)}" alt="${escape(label(item))}" draggable="false" style="width:${w*scale/rect.width*100}%;height:${h*scale/rect.height*100}%">`;
   }
   return `<div class="print-slot ${picked===key&&key?'picked':''}" style="left:${rect.x/spec.width*100}%;top:${rect.y/spec.height*100}%;width:${rect.width/spec.width*100}%;height:${rect.height/spec.height*100}%"><span class="print-slot-number">${number(i+1)}</span><button data-slot="${i}" class="print-slot-target" aria-label="خانة ${number(i+1)}${item?'، '+escape(label(item)):'، فارغة'}">${image||'<span>اسحب هنا<br>أو اختر مستمسكًا ثم اضغط</span>'}</button>${item?`<button class="print-slot-remove" data-remove="${i}" aria-label="إفراغ الخانة ${number(i+1)}">${icon('close')}</button>`:''}</div>`;
  }).join('');
  q('#boardSheet').querySelectorAll('[data-slot]').forEach(el=>{const i=Number(el.dataset.slot),key=pages[pageIndex][i];if(key)wireDrag(el,key);
   el.onclick=()=>{if(picked)place(picked,i);else if(key)select(key);else message('اختر مستمسكًا من القائمة أولًا، ثم اضغط هذه الخانة.');};
   el.ondragover=e=>{if([...e.dataTransfer.types].includes('application/x-mustamsak-document')){e.preventDefault();el.classList.add('drop-target');e.dataTransfer.dropEffect='move';}};
   el.ondragleave=()=>el.classList.remove('drop-target');
   el.ondrop=e=>{e.preventDefault();el.classList.remove('drop-target');place(e.dataTransfer.getData('application/x-mustamsak-document'),i);};
  });
  q('#boardSheet').querySelectorAll('[data-remove]').forEach(el=>el.onclick=()=>{remember();pages[pageIndex][Number(el.dataset.remove)]=null;picked=null;render();message('أُفرغت الخانة؛ المستمسك باقٍ في القائمة ويمكن إضافته مجددًا.');});
  q('#boardPage').innerHTML=pages.map((_,i)=>`<option value="${i}">صفحة ${number(i+1)} من ${number(pages.length)}</option>`).join('');q('#boardPage').value=pageIndex;
  q('#boardPrevious').disabled=pageIndex===0;q('#boardNext').disabled=pageIndex===pages.length-1;q('#boardUndo').disabled=!undo.length;
  q('#boardDeletePage').disabled=pages.length===1||pages[pageIndex].some(Boolean);q('#boardAddPage').disabled=pages.length>=200;
  q('#boardApply').disabled=q('#boardPreview').disabled=!used.size;
 }
 async function open(key,settings){
  specs=specs||await api('/api/print-layouts');scope=key;options=settings;items=sessions.get(key)?.items||[];
  if(!items.length)throw Error('اختر مستمسكات للطباعة أولًا.');
  const preset=['grid4','grid6'].includes(settings.layout)?settings.layout:'grid4',saved=sessions.get(key).plan;
  q('#boardLayout').value=preset;q('#boardSize').value=settings.size;
  pages=saved?.layout===preset?clone(saved.pages):automatic(items,preset);pageIndex=0;picked=null;undo=[];
  message('الأمام يمين الصف والخلف يساره عند التجميع. تستطيع تغيير كل المواضع.');render();dialog.showModal();
 }
 function apply(close=true){
  if(pages.some(p=>!p.some(Boolean)))throw Error('أزل الصفحات الفارغة قبل اعتماد الترتيب؛ يمكن إبقاء خانات فارغة داخل الصفحة.');
  const plan={layout:layout(),pages:clone(pages)};sessions.get(scope).plan=plan;options.onApply(plan,q('#boardSize').value);
  if(close)dialog.close();return plan;
 }
 function guarded(fn){try{return fn();}catch(e){q('#boardError').textContent=e.message;q('#boardError').hidden=false;}}
 q('#closePrintBoard').onclick=()=>dialog.close();
 q('#boardLayout').onchange=()=>{const old=pages[0].length===4?'grid4':'grid6',next=layout();q('#boardLayout').value=old;remember();q('#boardLayout').value=next;
  // Preserve manual reading order and every placed document when changing capacity.
  const flat=pages.flat().filter(Boolean),count=specs[next].slots.length;pages=[];for(let i=0;i<flat.length;i+=count)pages.push(Array.from({length:count},(_,j)=>flat[i+j]||null));if(!pages.length)pages=[Array(count).fill(null)];pageIndex=0;render();message('تغيّر القالب مع حفظ ترتيب الصور الموضوعة؛ راجع مواضعها قبل الطباعة.');};
 q('#boardSize').onchange=render;
 q('#boardAuto').onclick=()=>{remember();pages=automatic(items,layout());pageIndex=0;picked=null;render();message('تم توزيع كل المستمسكات حسب مجموعاتها. يمكنك التراجع لاستعادة ترتيبك.');};
 q('#boardUndo').onclick=()=>{const prev=undo.pop();if(prev){pages=prev.pages;pageIndex=prev.pageIndex;q('#boardLayout').value=prev.layout;picked=null;render();message('تم التراجع عن آخر تغيير.');}};
 q('#boardPrevious').onclick=()=>{pageIndex--;render();};q('#boardNext').onclick=()=>{pageIndex++;render();};q('#boardPage').onchange=e=>{pageIndex=Number(e.target.value);render();};
 q('#boardAddPage').onclick=()=>{remember();pages.push(Array(specs[layout()].slots.length).fill(null));pageIndex=pages.length-1;render();message('أضيفت صفحة فارغة. انقل إليها المستمسكات من القائمة.');};
 q('#boardDeletePage').onclick=()=>{if(pages.length===1||pages[pageIndex].some(Boolean))return;remember();pages.splice(pageIndex,1);pageIndex=Math.min(pageIndex,pages.length-1);render();};
 q('#boardApply').onclick=()=>guarded(()=>apply());
 q('#boardPreview').onclick=()=>guarded(()=>{apply(false);return action(q('#boardPreview'),()=>options.onPreview());});
 return {prepare,open,payload(key,name){const plan=sessions.get(key)?.plan;return plan?.layout===name?{pages:clone(plan.pages),keys:plan.pages.flat().filter(Boolean)}:null;}};
})();

let batchExportTarget=null;
function printStatusText(plan,total,dataOnly){
 if(dataOnly)return 'تنزيل البيانات يشمل كل المستمسكات المحددة؛ ترتيب الخانات يخص PDF داخل المعاينة أو ZIP.';
 if(!plan)return 'توزيع تلقائي حسب القالب المختار. افتح اللوحة لتحديد موضع كل مستمسك.';
 const count=plan.keys.length;
 return `ترتيب مخصص محفوظ: ${number(plan.pages.length)} صفحة · ${number(count)} مستمسك للطباعة · ${number(total-count)} خارج الطباعة. افتح اللوحة لتعديل الاختيار.`;
}
function refreshBatchPrintStatus(){
 if(!batchExportTarget)return;
 const plan=PrintBoard.payload(`batch:${batchExportTarget.bid}`,$('#exportLayout').value);
 $('#batchPrintStatus').textContent=printStatusText(plan,batchExportTarget.ids.length,!['pdf','zip'].includes($('#exportFormat').value));
}
function refreshPersonPrintStatus(){
 if(!personExportTarget)return;
 const plan=PrintBoard.payload(`person:${personExportTarget.pid}`,$('#personExportLayout').value);
 $('#personPrintStatus').textContent=printStatusText(plan,personExportTarget.refs.length,!['pdf','zip'].includes($('#personExportFormat').value));
}
$('#exportLayout').addEventListener('change',refreshBatchPrintStatus);$('#exportFormat').addEventListener('change',refreshBatchPrintStatus);
$('#personExportLayout').addEventListener('change',refreshPersonPrintStatus);$('#personExportFormat').addEventListener('change',refreshPersonPrintStatus);
function prepareBatchPrint(){
 const ids=exportIds(),documents=currentDocs().filter(d=>ids.includes(d.id));batchExportTarget={bid:state.batch.id,ids};
 PrintBoard.prepare(`batch:${state.batch.id}`,documents.map(d=>({key:d.id,document:d,group:d.group})));
 refreshBatchPrintStatus();
}
$('#openBatchPrintBoard').onclick=()=>action($('#openBatchPrintBoard'),()=>PrintBoard.open(`batch:${batchExportTarget.bid}`,{
 layout:$('#exportLayout').value,size:$('#exportSize').value,
 onApply(plan,size){$('#exportLayout').value=plan.layout;$('#exportSize').value=size;refreshBatchPrintStatus();},
 onPreview:()=>makeExport(true)
}));
$('#openPersonPrintBoard').onclick=()=>action($('#openPersonPrintBoard'),()=>PrintBoard.open(`person:${personExportTarget.pid}`,{
 layout:$('#personExportLayout').value,size:$('#personExportSize').value,
 onApply(plan,size){$('#personExportLayout').value=plan.layout;$('#personExportSize').value=size;refreshPersonPrintStatus();},
 onPreview:()=>exportPerson(true)
}));
