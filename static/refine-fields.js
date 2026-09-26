/* Refresh targeted document fields; the server preserves manual and reviewed values. */
$('#refineFields').onclick=async()=>{
 const bid=state.batch?.id;if(!bid||state.refiningFields)return;
 state.refiningFields=true;render();
 const button=$('#refineFields');button.setAttribute('aria-busy','true');
 button.textContent='جارٍ تحسين قراءة الحقول…';
 toast('قراءة محلية لاسم رب الأسرة ورموز السكن، والجنس وجهة الإصدار والتواريخ. تبقى التعديلات اليدوية محفوظة.');
 try{
  const result=await api(`/api/batches/${bid}/refine-fields`,{method:'POST'});
  if(state.batch?.id!==bid)return;
  state.batch=result.batch;render();
  if(typeof refreshPeopleSummary==='function')refreshPeopleSummary();
  toast(`اكتمل التحسين في ${number(result.updated_documents)} مستمسك. بقي ${number(result.skipped_reviewed)} مستمسك معتمد دون تغيير.`);
 }catch(e){toast(e.message,true);}
 finally{state.refiningFields=false;button.textContent='تحسين قراءة الحقول';button.removeAttribute('aria-busy');render();}
};
