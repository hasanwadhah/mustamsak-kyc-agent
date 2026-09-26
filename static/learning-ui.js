/* "Learn from my corrections": corrected/confirmed handwritten numbers become training samples
   for the digit reader, and a button retrains it (app/learning.py). */
'use strict';
(function mountLearning(){
 const box=document.createElement('section');box.id='learningSettings';box.className='local-ai-settings';
 box.innerHTML=`<div class="local-ai-head"><div><h3>التعلم من تصحيحاتك</h3>
  <p class="field-help">عندما تصحّح رقم المحلة أو الزقاق أو الدار أو الاستمارة في بطاقة السكن أو تعتمده، تُحفظ صور أرقامه مع قيمتك لتدريب قارئ الأرقام على خطوط مكاتبكم. الصور تبقى على هذا الجهاز فقط.</p></div>
  <label class="switch" title="تشغيل أو إيقاف التعلم من التصحيحات"><input type="checkbox" id="learningToggle" role="switch" aria-describedby="learningState"><span class="switch-track" aria-hidden="true"></span><span class="sr-only">التعلم من التصحيحات</span></label></div>
  <p id="learningState" class="local-ai-state" aria-live="polite">جارٍ الفحص…</p>
  <p id="learningTraining" class="field-help" aria-live="polite"></p>
  <button type="button" id="learningTrain" class="secondary">تدريب قارئ الأرقام الآن</button>
  <p class="field-help">التدريب يعمل في الخلفية بأولوية منخفضة نحو 20 دقيقة. لا يُثبّت النموذج الجديد إلا إذا لم تنخفض دقته في الاختبارات القياسية، ويُحفظ النموذج السابق للرجوع إليه.</p>`;
 const anchor=$('#localAISettings')||$('#cloudSettings');anchor.after?anchor.after(box):anchor.before(box);
})();

const LEARNING_STATES={idle:'لم يُدرَّب بعد من تصحيحاتك.',running:'يجري التدريب الآن…',installed:'آخر تدريب: ثُبّت نموذج جديد.',
 rejected:'آخر تدريب: لم يُثبّت (لم يتحسن).',failed:'آخر تدريب: فشل.',interrupted:'آخر تدريب: توقف قبل اكتماله.'};
function showLearning(s){
 $('#learningToggle').checked=!!s.enabled;
 const el=$('#learningState');
 el.textContent=(s.enabled?'مفعّل':'معطّل')+` · العينات المحفوظة: ${number(s.total)}`+(s.total<s.min_samples?` (يلزم ${number(s.min_samples)} على الأقل للتدريب)`:'');
 el.dataset.kind=s.enabled?'ready':'off';
 const t=s.training||{};
 $('#learningTraining').textContent=(LEARNING_STATES[t.state]||'')+(t.message&&t.state!=='idle'?' '+t.message:'')+(t.finished?` (${t.finished})`:'');
 $('#learningTrain').disabled=t.state==='running'||s.total<s.min_samples;
}
async function refreshLearning(){
 try{showLearning(await api('/api/learning'));}catch(e){$('#learningState').textContent=e.message;}
}
$('#learningToggle').onchange=async e=>{
 const toggle=e.target,wanted=toggle.checked;toggle.disabled=true;
 try{showLearning(await api('/api/learning',json('PUT',{enabled:wanted})));toast(wanted?'سيتعلم البرنامج من تصحيحاتك.':'أُوقف التعلم من التصحيحات.');}
 catch(err){toggle.checked=!wanted;toast(err.message,true);}
 finally{toggle.disabled=false;}
};
$('#learningTrain').onclick=async()=>{
 $('#learningTrain').disabled=true;
 try{showLearning(await api('/api/learning/train',{method:'POST'}));toast('بدأ التدريب في الخلفية.');}
 catch(err){toast(err.message,true);refreshLearning();}
};
$('#settingsNav').addEventListener('click',refreshLearning);
