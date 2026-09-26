import io
import json
import csv
import zipfile
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from PIL import Image
from .storage import image_path

def export_pdf(documents, layout='pairs', size='fit', sheets=None):
    from .print_layout import automatic_sheets, grid_spec
    stream = io.BytesIO()
    c = Canvas(stream, pagesize=A4)
    c.setTitle('Mustamsak - Iraqi documents')
    sheets = automatic_sheets(documents, layout) if sheets is None else sheets
    grid = grid_spec(layout) if layout in ('grid4', 'grid6') else None
    for index, sheet in enumerate(sheets):
        for slot, d in enumerate(sheet):
            if d is None:
                continue
            with Image.open(image_path(d['image_id'])) as im:
                iw, ih = im.size
                if grid:
                    box = grid['slots'][slot]
                    maxw, maxh = box['width'] * mm, box['height'] * mm
                    center_x = (box['x'] + box['width'] / 2) * mm
                    center_y = A4[1] - (box['y'] + box['height'] / 2) * mm
                else:
                    maxw, maxh = 180 * mm, (116 if layout == 'pairs' else 252) * mm
                    center_x = A4[0] / 2
                    center_y = (216 if slot == 0 else 83) * mm if layout == 'pairs' else A4[1] / 2
                if size == 'card' and d['kind'] == 'national_id':
                    maxw, maxh = min(maxw, 85.6 * mm), min(maxh, 54 * mm)
                scale = min(maxw / iw, maxh / ih)
                w, h = iw * scale, ih * scale
                c.drawImage(ImageReader(im), center_x - w / 2, center_y - h / 2, width=w, height=h, mask='auto')
        # Grid templates print only document images, as in the supplied examples.
        if not grid:
            c.setFont('Helvetica', 8)
            c.setFillColorRGB(.4, .45, .5)
            c.drawCentredString(A4[0] / 2, 9 * mm, f'{index + 1} / {len(sheets)}')
        c.showPage()
    c.save()
    return stream.getvalue()

def export_json(documents):
    return json.dumps({'schema_version':1,'documents':documents},ensure_ascii=False,indent=2).encode('utf-8')

def export_csv(documents):
    s=io.StringIO(newline='');w=csv.writer(s);w.writerow(['group','type','side','source','page','field','value','reviewed','field_status','field_verified','date_precision','note'])
    def safe(v):
        text=str(v)
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    for d in documents:
        for f in d['fields'] or [{'label':'','value':''}]:w.writerow([safe(v) for v in [d['group'],d['kind'],d['side'],d['source_name'],d['page'],f['label'],f['value'],d['reviewed'],f.get('status',''),f.get('verified',False),f.get('date_precision',''),f.get('note','')]])
    return ('\ufeff'+s.getvalue()).encode('utf-8')

def export_zip(documents,layout='pairs',size='fit',sheets=None):
    s=io.BytesIO()
    with zipfile.ZipFile(s,'w',zipfile.ZIP_DEFLATED) as z:
        for i,d in enumerate(documents):z.write(image_path(d['image_id']),f'{i+1:03}_{d["kind"]}_{d["side"]}.png')
        z.writestr('data.json',export_json(documents));z.writestr('print.pdf',export_pdf(documents,layout,size,sheets))
    return s.getvalue()
