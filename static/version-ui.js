/* Which version is running, under «مساحة خاصة على جهازك»: the GitHub commit and whether it is current
   (same source as the agent screen's footer, GET /api/version). */
'use strict';
(async function showVersion(){
 const box=document.createElement('p');box.id='versionInfo';box.className='version-info';
 const after=document.querySelector('.sidebar-bottom p');if(!after)return;after.after(box);
 try{
  const v=await api('/api/version'), g=v.git;
  if(!g){box.textContent='نسخة منزَّلة غير مرتبطة بـ GitHub';return;}
  box.textContent=`الإصدار ${g.commit} · ${g.date}`;
  const note=v.restart_needed?'تغيّرت الملفات أثناء عمل البرنامج: افتحه مجددًا من «Start KYC Agent».'
   :g.changed?'عُدّلت ملفات هنا، فأُوقف التحديث التلقائي.'
   :g.behind?`تحديثات جديدة على GitHub: ${g.behind}. افتح البرنامج مجددًا من «Start KYC Agent» لتثبيتها.`:'';
  if(note){const warn=document.createElement('p');warn.className='version-info stale';warn.textContent=note;box.after(warn);}
 }catch{box.textContent='تعذر قراءة رقم الإصدار.';}
})();
