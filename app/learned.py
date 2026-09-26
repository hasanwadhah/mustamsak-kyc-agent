"""Small supervised reference classifier. Its output is only a review suggestion."""
from pathlib import Path
import cv2
import numpy as np

MODEL=Path(__file__).resolve().parents[1]/'models'/'reference_classifier.npz'

def vector(image):
    small=cv2.resize(image,(48,32),interpolation=cv2.INTER_AREA)
    lab=cv2.cvtColor(small,cv2.COLOR_RGB2LAB).astype(np.float32)/255
    gray=cv2.cvtColor(small,cv2.COLOR_RGB2GRAY)
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0);gy=cv2.Sobel(gray,cv2.CV_32F,0,1)
    grad=cv2.resize(cv2.magnitude(gx,gy),(16,12))/1024
    return np.concatenate([cv2.resize(lab,(16,12)).ravel(),grad.ravel()])

def suggest(image):
    if not MODEL.exists():return None
    with np.load(MODEL,allow_pickle=False) as m:
        x=(vector(image)-m['mean'])/m['scale'];scores=m['coef']@x+m['intercept']
        idx=int(scores.argmax())
        return str(m['classes'][idx])
