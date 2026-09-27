/* Reviewer workspace sidebar: the illustrated icon family (static/icons/nav/, built by
   scripts/make_nav_icons.py), the two-line link back to the agent screen and the «أدوات» group.
   Items added later by other scripts (Gemini, training, stop) are upgraded as they appear, and the
   teal "active" tile follows whichever item carries the .active class. */
'use strict';
(function navIcons(){
 const side=document.querySelector('.sidebar');if(!side)return;
 const DIR='/static/icons/nav/';
 const KEYS={workspaceNav:'documents',peopleNav:'people',historyNav:'archive',guideNav:'guide',geminiNav:'gemini',trainingNav:'training'};
 const tile=(key,active)=>`${DIR}nav-${key}-${active?'active':'idle'}.svg`;
 const setTile=item=>{
  const key=KEYS[item.id];if(!key)return;
  let img=item.querySelector(':scope > img.nav-tile');
  if(!img){
   item.querySelector(':scope > svg, :scope > [data-icon]')?.remove();
   img=document.createElement('img');img.className='nav-tile';img.alt='';img.width=img.height=32;item.prepend(img);
  }
  const src=tile(key,item.classList.contains('active'));if(img.getAttribute('src')!==src)img.src=src;
 };
 // The brand mark: the same tile family at hero size.
 const symbol=side.querySelector('.brand-symbol');
 if(symbol&&!symbol.querySelector('img')){symbol.replaceChildren();const b=document.createElement('img');b.src=DIR+'brand-mark.svg';b.alt='';symbol.append(b);symbol.classList.add('has-art');}
 // Tools get their own caption, after the file sections (Gemini and training are inserted after the guide).
 const guide=side.querySelector('#guideNav');
 if(guide&&!side.querySelector('.nav-caption.tools')){const c=document.createElement('p');c.className='nav-caption tools';c.textContent='أدوات';guide.before(c);}
 const upgradeBack=a=>{
  if(a.dataset.upgraded)return;a.dataset.upgraded='1';
  const img=document.createElement('img');img.className='nav-tile';img.alt='';img.width=img.height=32;img.src=DIR+'nav-agent-idle.svg';
  const text=document.createElement('span');text.className='back-text';
  const title=document.createElement('b');title.textContent='شاشة الوكيل';
  const sub=document.createElement('small');sub.textContent='القرار والنتائج';text.append(title,sub);
  const arrow=document.createElementNS('http://www.w3.org/2000/svg','svg');arrow.setAttribute('viewBox','0 0 24 24');arrow.setAttribute('class','back-arrow');arrow.setAttribute('aria-hidden','true');
  const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d','M19 12H5M11 6l-6 6 6 6');arrow.append(p);
  a.replaceChildren(img,text,arrow);
 };
 const scan=()=>{
  side.querySelectorAll('.nav-item[id]').forEach(setTile);
  const back=side.querySelector('.back-to-agent');if(back)upgradeBack(back);
 };
 scan();
 new MutationObserver(scan).observe(side,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
})();
