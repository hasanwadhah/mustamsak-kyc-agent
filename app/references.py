"""SIFT reference feature index. This is not a newly trained OCR model."""
from pathlib import Path
import json
import cv2
import numpy as np

DIRECTORY=Path(__file__).resolve().parents[1]/'models'/'references'
_cache=None

def features(image):
    image=cv2.resize(image,(700,max(80,int(image.shape[0]*700/image.shape[1]))))
    gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
    return cv2.SIFT_create(nfeatures=1000).detectAndCompute(gray,None)

def match_reference(image):
    global _cache
    if _cache is None:
        _cache=[]
        manifest=DIRECTORY/'manifest.json'
        if manifest.exists():
            for item in json.loads(manifest.read_text(encoding='utf-8')):
                data=np.load(DIRECTORY/item['features'],allow_pickle=False)
                _cache.append((item,data['points'],data['descriptors']))
    if not _cache:return None
    kp,desc=features(image)
    if desc is None or len(desc)<6:return None
    best=None
    for item,pts,ref in _cache:
        if len(ref)<6:continue
        pairs=cv2.BFMatcher().knnMatch(ref,desc,k=2)
        good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.69*p[1].distance]
        if len(good)<9:continue
        src=np.float32([pts[m.queryIdx] for m in good]); dst=np.float32([kp[m.trainIdx].pt for m in good])
        matrix,mask=cv2.findHomography(src,dst,cv2.RANSAC,5)
        inliers=int(mask.sum()) if mask is not None else 0
        if inliers>=8 and inliers/len(good)>.5:
            score=min(.92,.56+inliers*.009)
            if not best or score>best['score']:
                corners=np.float32([[0,0],[item['width']-1,0],[item['width']-1,item['height']-1],[0,item['height']-1]])
                projected=cv2.perspectiveTransform(corners.reshape(1,4,2),matrix)[0]*(image.shape[1]/700)
                best={'kind':item['kind'],'side':item['side'],'score':score,'projected_corners':projected.round(1).tolist(),'inliers':inliers}
    return best
