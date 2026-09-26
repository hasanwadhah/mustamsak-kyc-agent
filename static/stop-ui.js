/* "Stop the app" in the sidebar: the server runs in the background without a window, so closing
   the browser never stops it (POST /api/shutdown; إيقاف.cmd does the same from Windows). */
'use strict';
(function stopButton(){
 paths.power='M12 3v9 M6.3 6.3a8 8 0 1 0 11.4 0';
 const b=document.createElement('button');b.className='text-button stop-app';b.id='stopApp';b.type='button';
 b.innerHTML='<span data-icon="power"></span>إيقاف البرنامج';$('#settingsNav').after(b);icons(b);
 async function stop(force){
  const r=await fetch('/api/shutdown',json('POST',{force}));
  if(r.status===409){const d=await r.json();
   if(confirm(d.detail+'\n\nإيقاف البرنامج الآن على أي حال؟ (التدريب الجاري يتوقف ولا يُثبّت منه شيء)'))return stop(true);return;}
  if(!r.ok)throw Error(`تعذر الإيقاف (${r.status}).`);
  document.body.innerHTML=`<main class="stopped-page"><h1>تم إيقاف البرنامج</h1><p>يمكنك إغلاق هذه الصفحة. لتشغيله مرة أخرى افتح «تشغيل.cmd».</p></main>`;
 }
 b.onclick=async()=>{if(!confirm('إيقاف برنامج مستمسك؟ ستُغلق الصفحة ويتوقف الخادم على جهازك.'))return;
  try{await stop(false);}catch(e){toast(e.message,true);}};
})();
