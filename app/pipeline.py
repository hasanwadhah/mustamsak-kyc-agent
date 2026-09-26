from datetime import datetime,timezone
import io
import cv2
import numpy as np
from PIL import Image,ImageOps
import pypdfium2 as pdfium
from . import vision,storage
from .focused_fields import VERSION as EXTRACTION_VERSION

def pages_from_bytes(data,name):
    if data.startswith(b'%PDF-'):
        try:pdf=pdfium.PdfDocument(data)
        except Exception as e:raise ValueError('تعذر فتح PDF؛ قد يكون تالفًا أو محميًا بكلمة مرور.') from e
        try:
            if len(pdf)>40:raise ValueError('الحد الأقصى 40 صفحة لكل ملف PDF.')
            for i in range(len(pdf)):
                page=pdf[i]; w,h=page.get_size()
                if w<=0 or h<=0:raise ValueError('أبعاد صفحة PDF غير صالحة.')
                scale=min(2.5,3500/max(w,h))
                bitmap=page.render(scale=scale)
                yield np.array(bitmap.to_pil().convert('RGB')),i+1
                bitmap.close();page.close()
        finally:pdf.close()
    else:
        try:
            with Image.open(io.BytesIO(data)) as im:
                if getattr(im,'n_frames',1)>40:raise ValueError('الحد الأقصى 40 إطارًا.')
                for i in range(getattr(im,'n_frames',1)):
                    im.seek(i)
                    if im.width*im.height>45_000_000:raise ValueError('الصورة أكبر من 45 مليون بكسل.')
                    yield np.array(ImageOps.exif_transpose(im).convert('RGB')),i+1
        except (OSError,Image.DecompressionBombError) as e:raise ValueError('صيغة الصورة غير مدعومة أو الملف تالف.') from e

def make_document(image,source,region,index):
    cropped=vision.warp(image,region['points'])
    from .references import match_reference
    match=match_reference(cropped)
    outside=[]
    # 20 matched printed features are enough when they project a card-shaped frame (a small,
    # blurred photo gave 25, fitting the card exactly; 30 had been required).
    card_shaped=False
    if match:
        q=np.asarray(match['projected_corners'],np.float32)
        side_w=(np.linalg.norm(q[1]-q[0])+np.linalg.norm(q[2]-q[3]))/2;side_h=(np.linalg.norm(q[3]-q[0])+np.linalg.norm(q[2]-q[1]))/2
        card_shaped=cv2.isContourConvex(q.astype(np.int32)) and side_h>0 and 1.2<side_w/side_h<1.9
    if match and (match['inliers']>=30 or (match['inliers']>=20 and card_shaped)):
        corners=np.asarray(match['projected_corners'],np.float32)
        ch,cw=cropped.shape[:2]
        inside=(corners.min()>=-2 and corners[:,0].max()<=cw+2 and corners[:,1].max()<=ch+2)
        # A confident reference match whose corners fall beyond the photo means
        # part of the card was not captured (a strong cut-off signal).
        mx,my=.03*cw,.03*ch
        outside=[side for side,beyond in [('left',corners[:,0].min()<-mx),('right',corners[:,0].max()>cw+mx),
                                          ('top',corners[:,1].min()<-my),('bottom',corners[:,1].max()>ch+my)] if beyond]
        area=abs(cv2.contourArea(corners))
        # Also when the card is small in a busy photo (on a table, in a plastic sleeve): the
        # match of printed features locates it better than edges do.
        if inside and .06*cw*ch<area<.94*cw*ch:
            corners=np.clip(corners,[0,0],[cw-1,ch-1]).astype(np.float32)
            mapping=cv2.getPerspectiveTransform(np.float32([[0,0],[cw-1,0],[cw-1,ch-1],[0,ch-1]]),vision.ordered(region['points']))
            region=dict(region,points=cv2.perspectiveTransform(corners.reshape(1,4,2),mapping)[0].tolist(),method='reference_geometry')
            cropped=vision.warp(image,region['points'])
    cropped=vision.readable_size(cropped)
    from . import capture
    guidance=capture.assess(cropped,region['points'],image,region['method'],outside)
    notices=[i['message'] for i in guidance if i['severity'] in ('retake','warn')];lines=[]
    try:lines=vision.ocr(cropped)
    except Exception as e:notices.append(str(e) if isinstance(e,RuntimeError) else 'تعذرت القراءة الآلية؛ يمكنك إعادة المحاولة أو إدخال البيانات يدويًا.')
    result=vision.classify(lines,cropped)
    angle=vision.text_angle(lines,cropped.shape[1])
    if 1.5<=abs(angle)<=15 and result['kind']!='unknown':
        # The card filled the photo but was tilted: straighten it by its printed text and read again.
        straight=vision.straighten(cropped,angle)
        try:
            again=vision.ocr(straight)
            if abs(vision.text_angle(again,straight.shape[1]))<abs(angle):
                cropped,lines=straight,again;result=vision.classify(lines,cropped)
        except Exception:pass
    original=storage.uid(); current=storage.uid()
    vision.save_image(storage.image_path(original),cropped);vision.save_image(storage.image_path(current),cropped)
    if region['method'] in ['seam','whole_page']:notices.append('حدود الفصل مقترحة؛ راجع القص قبل اعتماد المستمسك.')
    if result['kind']=='unknown':notices.append('لا توجد أدلة كافية لتحديد النوع تلقائيًا.')
    return {'id':storage.uid(),'source_id':source['id'],'source_name':source['name'],'page':source['page'],
      'image_id':current,'original_id':original,'points':region['points'],'segmentation':region['method'],'capture':guidance,
      **result,'field_image_id':current,'extraction_version':EXTRACTION_VERSION,'fields':vision.extract_fields(lines,result['kind'],cropped,result['side']),'ocr':lines,'notices':notices,
      'reviewed':False,'group':'','group_reason':'','order':index,'width':cropped.shape[1],'height':cropped.shape[0]}

from .grouping import group_documents

def process_batch(batch,files):
    try:
        batch['status']='processing';storage.save_batch(batch)
        for fi,(name,data) in enumerate(files):
            try:
                for image,page in pages_from_bytes(data,name):
                    source={'id':storage.uid(),'name':name,'page':page,'width':image.shape[1],'height':image.shape[0]}
                    vision.save_image(storage.image_path(source['id']),image);batch['sources'].append(source)
                    regions=vision.detect_regions(image)
                    for ri,region in enumerate(regions):
                        batch['message']=f'قراءة {name} · الصفحة {page} · المستمسك {ri+1} من {len(regions)}'
                        storage.save_batch(batch)
                        batch['documents'].append(make_document(image,source,region,len(batch['documents'])))
                        storage.save_batch(batch)
                batch['progress']=int((fi+1)/len(files)*95)
            except Exception as e:batch['errors'].append({'file':name,'message':str(e)[:400]})
        group_documents(batch['documents'])
        from .paired_fields import reconcile
        reconcile(batch['documents'])
        batch['status']='ready' if batch['documents'] else 'failed'
        batch['progress']=100;batch['message']='اكتملت المعالجة؛ راجع المستمسكات قبل الطباعة.'
    except Exception:
        batch['status']='failed';batch['message']='توقفت المعالجة. أعد رفع الملف بعد التحقق من صيغته.'
    finally:storage.save_batch(batch)

def new_batch(name):
    return {'id':storage.uid(),'name':name,'created':datetime.now(timezone.utc).isoformat(),'status':'queued','progress':0,'message':'في انتظار المعالجة المحلية…','sources':[],'documents':[],'errors':[]}
