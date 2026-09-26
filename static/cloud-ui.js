/* Optional cloud reading with Google Gemini (app/cloud.py, docs/EXTERNAL_API.md).
   Off by default; the switch is saved on the server, which refuses to send any image while it is off.
   The key stays in page memory unless the user ticks "remember in this browser" (localStorage only,
   never the data folder, which may sit in a cloud-synced folder). Every image still needs its own consent. */
'use strict';
const CLOUD_KEY_STORE='mustamsak.geminiKey',CLOUD_MODEL_STORE='mustamsak.geminiModel';
function cloudStored(name){try{return localStorage.getItem(name)||'';}catch{return '';}}
function cloudStore(name,value){try{value?localStorage.setItem(name,value):localStorage.removeItem(name);}catch{}}
let cloudOn=false;

$('#cloudSettings').className='local-ai-settings cloud-settings';
$('#cloudSettings').innerHTML=`<div class="local-ai-head"><div><h3>القراءة السحابية (Google Gemini)</h3>
 <p class="field-help">للمستمسكات الصعبة فقط. عند الطلب تُرسل صورة الوجه المعروض فقط إلى Google Gemini بمفتاحك، وبعد موافقتك في كل مرة. النتيجة اقتراح تراجعه قبل الحفظ.</p></div>
 <label class="switch" title="تشغيل أو إطفاء القراءة السحابية"><input type="checkbox" id="cloudToggle" role="switch" aria-describedby="cloudState"><span class="switch-track" aria-hidden="true"></span><span class="sr-only">القراءة السحابية</span></label></div>
 <p id="cloudState" class="local-ai-state" aria-live="polite">جارٍ الفحص…</p>
 <div id="cloudFields">
  <label>مفتاح Gemini API<input id="cloudKey" type="password" autocomplete="off" placeholder="AIza…" spellcheck="false" dir="ltr"></label>
  <p class="field-help">مفتاح مجاني من <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">Google AI Studio</a> ← Get API key.</p>
  <label class="review-check"><input type="checkbox" id="cloudRemember">تذكّر المفتاح في هذا المتصفح على هذا الجهاز</label>
  <label>اسم النموذج<input id="cloudModel" list="cloudModels" dir="ltr" spellcheck="false"><datalist id="cloudModels"></datalist></label>
  <button id="cloudCheck" class="text-button" type="button">تحقق من المفتاح (لا يُرسل أي صورة)</button>
  <p class="notice cloud-warning"><b>تنبيه المفتاح المجاني:</b> تنص شروط Google للاستخدام المجاني على أنها قد تستخدم الصور المرسلة لتحسين خدماتها، وقد يطّلع عليها مراجعون بشريون، وتطلب عدم إرسال معلومات شخصية. البطاقات الحقيقية معلومات شخصية. استخدمها فقط عند الحاجة وبعلم صاحب المستمسك، أو فعّل الفوترة على مشروع المفتاح لتسري شروط الخدمة المدفوعة.</p>
 </div>`;
$('#cloudModel').value=cloudStored(CLOUD_MODEL_STORE);
if(cloudStored(CLOUD_KEY_STORE)){$('#cloudKey').value=cloudStored(CLOUD_KEY_STORE);$('#cloudRemember').checked=true;}

const cloudButton=document.createElement('button');cloudButton.id='cloudRead';cloudButton.className='text-button';cloudButton.textContent='قراءة سحابية (Gemini)';cloudButton.hidden=true;$('.data-pane').append(cloudButton);
const cloudDialog=document.createElement('dialog');cloudDialog.id='cloudConsent';cloudDialog.innerHTML=`<div class="dialog-heading"><h2>إرسال هذا المستمسك إلى Google Gemini</h2><button class="icon-button" id="closeCloud" aria-label="إغلاق">${icon('close')}</button></div><p>سيُرسل الوجه المعروض فقط، بما فيه الصورة الشخصية والأرقام والبيانات المكتوبة، إلى Google Gemini لاقتراح قراءة. لن تُرسل بقية الدفعة.</p><p class="notice">مع المفتاح المجاني قد تستخدم Google الصورة لتحسين خدماتها وقد يراها مراجعون بشريون. القراءة السحابية قد تخطئ أيضًا؛ ستظهر النتيجة للمراجعة قبل الحفظ.</p><label class="review-check"><input type="checkbox" id="cloudConsentCheck">أوافق على إرسال هذه الصورة إلى Google Gemini لهذه القراءة</label><button id="confirmCloud" class="primary wide">إرسال الصورة وطلب القراءة</button>`;document.body.append(cloudDialog);

function cloudModel(){return $('#cloudModel').value.trim()||$('#cloudModel').placeholder;}
function showCloud(s){
 cloudOn=!!s.enabled;$('#cloudToggle').checked=cloudOn;$('#cloudModel').placeholder=s.default_model;
 $('#cloudFields').hidden=!cloudOn;cloudButton.hidden=!cloudOn;
 const el=$('#cloudState');
 if(!cloudOn){el.textContent='مطفأة. لا تُرسل أي صورة خارج الجهاز.';el.dataset.kind='off';}
 else if(!$('#cloudKey').value.trim()){el.textContent='مفعّلة، لكن أدخل مفتاح Gemini API ثم اضغط «تحقق من المفتاح».';el.dataset.kind='warn';}
 else if(el.dataset.kind!=='ready'){el.textContent=`مفعّلة · النموذج ${cloudModel()} · اضغط «تحقق من المفتاح» للتأكد.`;el.dataset.kind='warn';}
}
async function refreshCloud(){try{showCloud(await api('/api/cloud'));}catch(e){$('#cloudState').textContent=e.message;}}
$('#cloudToggle').onchange=async e=>{
 const toggle=e.target,wanted=toggle.checked;toggle.disabled=true;
 try{$('#cloudState').dataset.kind='';showCloud(await api('/api/cloud',json('PUT',{enabled:wanted})));toast(wanted?'تم تشغيل القراءة السحابية. لن تُرسل أي صورة إلا بموافقتك.':'تم إطفاء القراءة السحابية.');}
 catch(err){toggle.checked=!wanted;toast(err.message,true);}finally{toggle.disabled=false;}
};
$('#cloudKey').oninput=()=>{$('#cloudState').dataset.kind='';if($('#cloudRemember').checked)cloudStore(CLOUD_KEY_STORE,$('#cloudKey').value.trim());showCloud({enabled:cloudOn,default_model:$('#cloudModel').placeholder});};
$('#cloudRemember').onchange=e=>cloudStore(CLOUD_KEY_STORE,e.target.checked?$('#cloudKey').value.trim():'');
$('#cloudModel').onchange=()=>{cloudStore(CLOUD_MODEL_STORE,$('#cloudModel').value.trim());$('#cloudState').dataset.kind='';showCloud({enabled:cloudOn,default_model:$('#cloudModel').placeholder});};
$('#cloudCheck').onclick=()=>action($('#cloudCheck'),async()=>{
 const key=$('#cloudKey').value.trim();if(!key)throw Error('أدخل مفتاح Gemini API أولًا.');
 const el=$('#cloudState');el.textContent='جارٍ التحقق من المفتاح…';el.dataset.kind='';
 try{
  const r=await api('/api/cloud/check',json('POST',{api_key:key}));
  $('#cloudModels').replaceChildren(...r.models.map(m=>Object.assign(document.createElement('option'),{value:m})));
  const model=cloudModel(),found=r.models.includes(model);
  el.textContent=found?`المفتاح صالح · النموذج ${model} متاح · جاهزة للاستخدام.`:`المفتاح صالح، لكن النموذج ${model} غير متاح له. اختر من القائمة: ${r.models.slice(0,6).join('، ')}`;
  el.dataset.kind=found?'ready':'warn';
 }catch(err){el.textContent=err.message;el.dataset.kind='warn';throw err;}
});
$('#settingsNav').addEventListener('click',refreshCloud);refreshCloud();

cloudButton.onclick=()=>{if(!cloudOn)return;if(!$('#cloudKey').value.trim()){openDialog('#settingsDialog');toast('أدخل مفتاح Gemini API، ثم عد إلى المستمسك واختر القراءة السحابية.');return;}$('#cloudConsentCheck').checked=false;openDialog('#cloudConsent');};$('#closeCloud').onclick=()=>cloudDialog.close();
$('#confirmCloud').onclick=()=>action($('#confirmCloud'),async()=>{if(!$('#cloudConsentCheck').checked)throw Error('فعّل الموافقة الصريحة لإرسال هذه الصورة.');const bid=state.batch.id,did=state.editorId;const result=await api(`/api/batches/${bid}/documents/${did}/cloud`,json('POST',{api_key:$('#cloudKey').value.trim(),model:cloudModel(),consent:true}));if(state.batch?.id!==bid||state.editorId!==did){cloudDialog.close();return;}$('#docKind').value=result.kind;$('#docSide').value=result.side;$('#fieldList').replaceChildren(...result.fields.map(fieldRow));$('#ocrText').textContent=result.raw_text;$('#reviewNotice').textContent=['اقتراح قراءة سحابية (Gemini)؛ راجع الصورة والحقول ثم احفظ.',...result.warnings].join(' ');$('#docReviewed').checked=false;cloudDialog.close();toast('وصل اقتراح القراءة. راجعه قبل الحفظ.');});
