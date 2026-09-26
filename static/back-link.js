/* Hackathon build: a way back from the reviewer workspace to the main agent screen (/),
   reopening the file being reviewed. */
'use strict';
(function backToAgent(){
 const a=document.createElement('a');a.className='nav-item back-to-agent';a.href='/';
 a.innerHTML='<span data-icon="grid"></span><span>العودة إلى الشاشة الرئيسية</span>';
 // Keep the address on the file shown here, so coming back reopens its decision.
 const sync=()=>{const id=typeof state!=='undefined'&&state.batch&&state.batch.id;a.href=id?'/?batch='+encodeURIComponent(id):'/';};
 sync();setInterval(sync,700);
 const caption=document.querySelector('.sidebar .nav-caption');
 caption.before(a);icons(a);
})();
