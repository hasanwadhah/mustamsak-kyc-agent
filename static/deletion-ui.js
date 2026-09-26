'use strict';
let deleteTarget=null, deleteBusy=false, historyRequest=0;

async function loadHistory(){
 const request=++historyRequest;
 $('#historyList').textContent='جارٍ تحميل الدفعات…';
 try{
  const batches=await api('/api/batches');
  if(request!==historyRequest)return;
  $('#historyList').innerHTML=batches.length?batches.map(b=>{
   const running=['queued','processing'].includes(b.status);
   return `<div class="history-row"><div><strong>${escape(b.name)}</strong><p>${new Date(b.created).toLocaleString('ar-IQ')} · ${number(b.count)} مستمسك · ${escape(b.message)}</p></div><div class="history-actions"><button class="secondary" data-batch="${b.id}">فتح</button><button class="danger" data-delete-batch="${b.id}" aria-label="حذف دفعة ${escape(b.name)}" ${running?'disabled title="انتظر اكتمال المعالجة"':''}>حذف</button></div></div>`;
  }).join(''):'لا توجد دفعات محفوظة.';
  $$('[data-batch]').forEach(button=>button.onclick=()=>action(button,async()=>{
   state.selected.clear();
   await refreshBatch(button.dataset.batch);
   localStorage.setItem('lastBatch',button.dataset.batch);
   const url=new URL(location.href);url.searchParams.set('batch',button.dataset.batch);history.replaceState(null,'',url);
   $('#historyDialog').close();
  }));
  $$('[data-delete-batch]').forEach(button=>button.onclick=()=>{
   const batch=batches.find(b=>b.id===button.dataset.deleteBatch);
   requestDeletion({bid:batch.id,name:batch.name,count:batch.count});
  });
 }catch(error){if(request===historyRequest)$('#historyList').textContent=error.message;}
}

function requestDeletion(target){
 if(deleteBusy)return;
 deleteTarget=target;
 $('#deleteTitle').textContent=target.ids?'حذف المستمسكات المحددة؟':'حذف الدفعة كاملة؟';
 $('#deleteDescription').textContent=target.ids?
  `سيُحذف ${number(target.ids.length)} مستمسك محدد من «${target.name}»، بما فيها أي تحديد خارج نتائج البحث الحالية.`:
  `ستُحذف دفعة «${target.name}» كاملة، وتحتوي على ${number(target.count)} مستمسك.`;
 $('#deleteScope').textContent=target.ids?
  'يشمل الحذف الصور المفصولة المحددة وبياناتها. تبقى صفحات المصدر في «الصور الأصلية والفصل». لحذفها أيضًا، احذف الدفعة كاملة.':
  'يشمل الحذف مستمسكات هذه الدفعة وبياناتها وصفحات المصدر المحفوظة داخل التطبيق. تبقى الصور التي تستخدمها دفعات أخرى.';
 $('#deleteError').hidden=true;
 $('#confirmDelete').disabled=false;
 openDialog('#deleteDialog');
 $('#cancelDelete').focus();
}

function clearDeletedBatch(bid){
 if(localStorage.getItem('lastBatch')===bid)localStorage.removeItem('lastBatch');
 const url=new URL(location.href);
 if(url.searchParams.get('batch')===bid){url.searchParams.delete('batch');history.replaceState(null,'',url);}
 if(state.batch?.id!==bid)return;
 ++batchRequest;clearTimeout(pollTimer);
 state.batch=null;state.selected.clear();state.editorId=null;state.source=null;
 state.image=null;state.points=[];state.canvasRequest=Symbol();state.fieldEvidenceRequest=Symbol();
 state.filter='all';state.search='';$('#searchInput').value='';$('#bulkGroup').value='';
 $$('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));
 ['#editor','#sourcesDialog','#exportDialog'].forEach(id=>{if($(id).open)$(id).close();});
 $('#sourcesList').replaceChildren();$('#fieldList').replaceChildren();
 if(pdfUrl){URL.revokeObjectURL(pdfUrl);pdfUrl=null;}
 render();
}

$('#historyNav').onclick=()=>{openDialog('#historyDialog');loadHistory();};
$('#deleteBatch').onclick=()=>{
 if(state.batch)requestDeletion({bid:state.batch.id,name:state.batch.name,count:currentDocs().length});
};
$('#deleteSelected').onclick=()=>{
 const ids=currentDocs().filter(d=>state.selected.has(d.id)).map(d=>d.id);
 if(ids.length)requestDeletion({bid:state.batch.id,name:state.batch.name,ids});
};
$('#cancelDelete').onclick=()=>{if(!deleteBusy)$('#deleteDialog').close();};
$('#deleteDialog').addEventListener('cancel',event=>{if(deleteBusy)event.preventDefault();});
$('#deleteDialog').addEventListener('close',()=>{if(!deleteBusy)deleteTarget=null;});
$('#confirmDelete').onclick=async()=>{
 if(!deleteTarget||deleteBusy)return;
 const target=deleteTarget;
 deleteBusy=true;$('#confirmDelete').disabled=true;$('#cancelDelete').disabled=true;
 $('#confirmDelete').setAttribute('aria-busy','true');$('#deleteError').hidden=true;
 try{
  const result=await api(`/api/batches/${target.bid}${target.ids?'/documents':''}`,
   target.ids?json('DELETE',{ids:target.ids}):{method:'DELETE'});
  if(target.ids){
   if(state.batch?.id===target.bid){
    ++batchRequest;clearTimeout(pollTimer);
    state.batch=result.batch;target.ids.forEach(id=>state.selected.delete(id));render();if(typeof refreshPeopleSummary==='function')refreshPeopleSummary(target.bid);
   }
  }else clearDeletedBatch(target.bid);
  $('#deleteDialog').close();deleteTarget=null;
  toast(result.cleanup_warning||(target.ids?`حُذف ${number(result.deleted_count)} مستمسك.`:'حُذفت الدفعة.'),!!result.cleanup_warning);
  if($('#historyDialog').open)await loadHistory();
 }catch(error){$('#deleteError').textContent=error.message;$('#deleteError').hidden=false;}
 finally{
  deleteBusy=false;$('#confirmDelete').disabled=false;$('#cancelDelete').disabled=false;
  $('#confirmDelete').removeAttribute('aria-busy');
 }
};
