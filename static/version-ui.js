/* Which update is running: reading version and last edit, under «مساحة خاصة على جهازك».
   Warns when the program files on disk are newer than the running server. */
'use strict';
(async function showVersion(){
 const box=document.createElement('p');box.id='versionInfo';box.className='version-info';
 const after=document.querySelector('.sidebar-bottom p');if(!after)return;after.after(box);
 try{
  const h=await api('/api/health');
  const version=String(h.reading_version||'').replace('local-fields-','');
  box.textContent=`الإصدار ${version} · آخر تحديث ${h.updated} · ${String(h.revision||'').slice(0,8)}`;
  if(!h.current){
   const warn=document.createElement('p');warn.className='version-info stale';
   warn.textContent='توجد نسخة أحدث على الجهاز: أغلق البرنامج وافتحه من «تشغيل.cmd».';
   box.after(warn);
  }
 }catch{box.textContent='تعذر قراءة رقم الإصدار.';}
})();
