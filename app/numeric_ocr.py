"""Specialist Latin OCR pass on existing number/MRZ text boxes."""
import re
from pathlib import Path
import cv2
from . import mrz

_english=None

def improve(image,lines,model_dir):
    global _english
    if not (model_dir/'english_g2.pth').exists():return lines
    candidates=[l for l in lines if l['text'].count('<')>=3 or (re.search(r'[A-Z^]\s*[A-Z]?\d{6,}',l['text']) and not re.search(r'[\u0600-\u06ff]',l['text']))]
    if not candidates:return lines
    if _english is None:
        import easyocr
        _english=easyocr.Reader(['en'],gpu=False,model_storage_directory=str(model_dir),detector=False,download_enabled=False,verbose=False,quantize=False)
    h,w=image.shape[:2]
    for line in candidates:
        box=line['box'];xs=[p[0] for p in box];ys=[p[1] for p in box]
        crop=image[max(0,int(min(ys))-2):min(h,int(max(ys))+3),max(0,int(min(xs))-3):min(w,int(max(xs))+4)]
        if not crop.size:continue
        gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
        gray=cv2.resize(gray,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
        result=_english.recognize(gray,allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<',detail=1,batch_size=1)
        if result:
            _,text,confidence=result[0]
            if confidence>.25:
                line['initial_text']=line['text'];line['text']=text;line['confidence']=float(confidence);line['engine']='english_specialist'
    return lines
