/* On/off switch for the optional local AI reader (Ollama), in the reading-settings dialog.
   The server saves the choice and applies it immediately (app/vision_llm.py). */
'use strict';
(function mountLocalAI(){
 const box=document.createElement('section');box.id='localAISettings';box.className='local-ai-settings';
 box.innerHTML=`<div class="local-ai-head"><div><h3>القارئ الذكي المحلي (Ollama)</h3>
  <p class="field-help">نموذج ذكاء اصطناعي يعمل على جهازك فقط، ويضيف <b>اقتراحًا</b> للحقول المكتوبة باليد المشكوك فيها. لا يغيّر أي قيمة ولا يرسل الصور خارج الجهاز.</p></div>
  <label class="switch" title="تشغيل أو إطفاء القارئ الذكي المحلي"><input type="checkbox" id="localAIToggle" role="switch" aria-describedby="localAIState"><span class="switch-track" aria-hidden="true"></span><span class="sr-only">القارئ الذكي المحلي</span></label></div>
  <p id="localAIState" class="local-ai-state" aria-live="polite">جارٍ الفحص…</p>
  <p class="field-help">تنبيه: في الاختبار على بطاقات سكن حقيقية كانت قراءته للأرقام المكتوبة باليد ضعيفة، وقد يقترح أسماء غير صحيحة. قارن أي اقتراح منه بالصورة. التشغيل يبطئ القراءة بضع ثوانٍ لكل حقل مشكوك فيه.</p>`;
 $('#cloudSettings').before(box);
})();

function localAIText(s){
 if(!s.enabled)return ['معطّل. القراءة تعمل بالمحركات المحلية المعتادة.','off'];
 if(s.ready)return [`مفعّل وجاهز · النموذج ${s.model}`,'ready'];
 if(!s.installed)return ['مفعّل، لكن Ollama غير مثبّت على هذا الجهاز (ollama.com).','warn'];
 if(!s.running)return ['مفعّل، لكن تعذر تشغيل Ollama. شغّله من قائمة البرامج ثم أعد المحاولة.','warn'];
 return [`مفعّل، لكن النموذج ${s.model} غير منزّل. نفّذ: ollama pull ${s.model}`,'warn'];
}
const LOCAL_AI_NOTE=' قارئ ذكي محلي (Ollama) مفعّل للحقول المشكوك فيها.';
function showLocalAI(s){
 const [text,kind]=localAIText(s);
 $('#localAIToggle').checked=!!s.enabled;
 const el=$('#localAIState');el.textContent=text;el.dataset.kind=kind;
 // Keep the engine summary at the top of the dialog in step with the switch.
 const details=$('#engineDetails'),base=details.textContent.replace(LOCAL_AI_NOTE,'');
 details.textContent=s.ready?base.replace('مرجع بصري مفهرس.','مرجع بصري مفهرس.'+LOCAL_AI_NOTE):base;
}
async function refreshLocalAI(){
 try{showLocalAI(await api('/api/local-ai'));}catch(e){$('#localAIState').textContent=e.message;}
}
$('#localAIToggle').onchange=async e=>{
 const toggle=e.target,wanted=toggle.checked;
 toggle.disabled=true;$('#localAIState').textContent=wanted?'جارٍ التشغيل وفحص Ollama…':'جارٍ الإطفاء…';
 try{const s=await api('/api/local-ai',json('PUT',{enabled:wanted}));showLocalAI(s);toast(s.enabled?(s.ready?'تم تشغيل القارئ الذكي المحلي.':'فُعّل القارئ الذكي، لكنه غير جاهز بعد.'):'تم إطفاء القارئ الذكي المحلي.');}
 catch(err){toggle.checked=!wanted;toast(err.message,true);}
 finally{toggle.disabled=false;}
};
$('#settingsNav').addEventListener('click',refreshLocalAI);
