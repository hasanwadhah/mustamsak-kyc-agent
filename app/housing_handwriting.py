"""Local handwriting aids. Visible labels establish roles; dictionaries never supply digits."""
import re
import cv2
import numpy as np
from . import arabic_ocr


def ink_variants(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    background = cv2.GaussianBlur(gray, (0, 0), max(3, crop.shape[0] / 7))
    normalized = cv2.divide(gray, background, scale=230)
    binary = cv2.threshold(normalized, 145, 255, cv2.THRESH_BINARY)[1]
    return [('color', crop), ('normalized', cv2.cvtColor(normalized, cv2.COLOR_GRAY2RGB)),
            ('ink', cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB))]


def components(crop, threshold=130, background_fraction=1/7):
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    n = cv2.divide(g, cv2.GaussianBlur(g, (0, 0), max(3, crop.shape[0] * background_fraction)), scale=230)
    _, _, stats, _ = cv2.connectedComponentsWithStats((n < threshold).astype('uint8'))
    h, w = crop.shape[:2]
    return [tuple(map(int, row)) for row in stats[1:]
            if row[4] >= max(8, h*h*.0015) and row[3] >= max(4, h*.06)]


def clipped_rect(rect, shape):
    x1, y1, x2, y2 = rect
    h, w = shape[:2]
    return (max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2)))


def original_box(rect, region, crop):
    h, w = crop.shape[:2]
    matrix = cv2.getPerspectiveTransform(np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]), np.float32(region['box']))
    x1,y1,x2,y2=rect
    return cv2.perspectiveTransform(np.float32([[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]]), matrix)[0].round(2).tolist()


def trailing_zero_dot(ink, tall):
    """Return a visible round mark after the digits, not a manufactured zero.

    Arabic zero can be a substantial dot. Printed guide dots and marks above a
    letter are excluded by size, position and proximity. Still a hypothesis:
    retain the unextended number and require review whenever this is used.
    """
    if not tall:return None
    top=min(s[1] for s in tall);bottom=max(s[1]+s[3] for s in tall)
    right=max(s[0]+s[2] for s in tall);height=bottom-top
    dots=[s for s in ink if .02*height<=s[0]-right<=.40*height
          and .08*height<=s[3]<=.28*height and .6<=s[2]/s[3]<=1.6
          and s[4]/(s[2]*s[3])>=.40 and .12<=(s[1]+s[3]/2-top)/height<=.68]
    return dots[0] if len(dots)==1 else None


def address_markers(image, region, partial=False):
    """Locate the printed م / ز / د markers of the address line.

    Returns (crop, {'م': stats, 'ز': stats, 'د': stats}) in the rectified region
    crop, or (crop, None) when any marker is missing or ambiguous. With partial=True,
    the unambiguous markers that were recognised are returned even if some are missing.
    """
    from .focused_fields import crop_box, normalize
    crop = crop_box(image, region['box'])
    h,w=crop.shape[:2]
    stats=components(crop)
    possible=[s for s in stats if .12*h <= s[3] <= .48*h and s[2] < .09*w
              and .18*h < s[1]+s[3]/2 < .80*h and s[4]>=20]
    if len(possible)>32:return crop,None
    crops=[];metadata=[]
    for index,(x,y,cw,ch,area) in enumerate(possible):
        for view,padx,pady,padbottom in [('wide',.15*h,.20*h,.20*h),('narrow',.05*h,.28*h,.20*h),
                                         ('letter',.3*ch,.8*ch,.8*ch),('dotted',.2*ch,1.3*ch,ch)]:
            rect=clipped_rect((x-padx,y-pady,x+cw+padx,y+ch+padbottom),crop.shape)
            x1,y1,x2,y2=rect
            for variant,work in ink_variants(crop[y1:y2,x1:x2]):
                crops.append(work);metadata.append((index,view+'_'+variant))
    markers={}
    for (index,variant),read in zip(metadata,arabic_ocr.recognize_crops(crops)):
        label=normalize(read['text']).strip(' .:،ـ')
        if label in ('م','ز','د') and read['confidence']>=.60:
            markers.setdefault(label,{}).setdefault(index,[]).append(read)
    if set(markers)!=set(('م','ز','د')) and not partial:return crop,None
    chosen={}
    for label,readings in markers.items():
        ranked=sorted(readings.items(),key=lambda item:(len(item[1]),max(r['confidence'] for r in item[1])),reverse=True)
        if len(ranked)>1 and len(ranked[0][1])==len(ranked[1][1]):
            if partial:continue
            return crop,None
        chosen[label]=possible[ranked[0][0]]
    if partial and set(chosen)!=set(('م','ز','د')):return crop,chosen
    m,z,d=(chosen[k] for k in ('م','ز','د'))
    if not (m[0]-z[0]>.12*w and z[0]-d[0]>.12*w):return crop,None
    return crop,chosen


# Printed form template: centre of each marker as a fraction of the address strip
# (card's left edge → printed label). Measured on 6 development cards: م .956–.965,
# ز .702–.725, د .459–.501.
MARKER_TEMPLATE = {'م': .960, 'ز': .710, 'د': .470}


def template_markers(crop, known):
    """Complete partly recognised markers from the printed form's fixed layout.

    At least one marker must have been recognised as its letter: it anchors the template
    (roles never come from position alone). Each missing marker must then be found as a
    small printed shape close to its expected place; otherwise nothing is returned.
    """
    if not known:
        return None
    h, w = crop.shape[:2]
    shapes = [s for s in components(crop) if .08 * h <= s[3] <= .3 * h and s[2] < .09 * w
              and .18 * h < s[1] + s[3] / 2 < .80 * h and s[4] >= 12]
    shift = float(np.median([(v[0] + v[2] / 2) / w - MARKER_TEMPLATE[k] for k, v in known.items()]))
    found = dict(known)
    for key, ratio in MARKER_TEMPLATE.items():
        if key in found:
            continue
        expected = (ratio + shift) * w
        near = [s for s in shapes if abs(s[0] + s[2] / 2 - expected) < .035 * w
                and all(abs(s[0] - v[0]) > .05 * w for v in found.values())]
        if not near:
            return None
        x, y, sw, sh, area = min(near, key=lambda s: abs(s[0] + s[2] / 2 - expected))
        # The shape may be only part of the letter (ز's dot): give it at least the size of
        # the recognised markers, so the whole letter is blanked before digits are read.
        kw = max(sw, int(np.median([v[2] for v in known.values()])))
        kh = max(sh, int(np.median([v[3] for v in known.values()])))
        found[key] = (int(x + sw / 2 - kw / 2), min(y, int(np.median([v[1] for v in known.values()]))), kw, kh, area)
    m, z, d = (found[k] for k in ('م', 'ز', 'د'))
    if not (m[0] - z[0] > .12 * w and z[0] - d[0] > .12 * w):
        return None
    return found


def label_anchored_markers(crop):
    """Last resort when no marker letter can be recognised (blurred or washed-out photo).

    The strip is anchored by the printed label «عنوان السكن» that OCR did read, and the form
    places م / ز / د at fixed fractions of it. The dotted line is removed first (blurred, it
    fuses with the markers into one long stroke). The three markers are chosen together: close
    to their places, on one line, with similar ink (one font), spaced as on the form;
    otherwise nothing. Stress test: blurred and brightened copies of development cards lost whole
    addresses because no marker letter could be read.
    """
    from itertools import product
    h, w = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    ink = (cv2.divide(gray, cv2.GaussianBlur(gray, (0, 0), max(3, h / 7)), scale=230) < 150).astype(np.uint8) * 255
    line = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, w // 25), 1)))
    ink = cv2.subtract(ink, cv2.dilate(line, np.ones((3, 1), np.uint8)))
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
    shapes = [tuple(map(int, s)) for s in stats[1:] if .06 * h <= s[3] <= .3 * h and s[2] < .09 * w
              and .18 * h < s[1] + s[3] / 2 < .80 * h and s[4] >= 12]
    options = {key: [s for s in shapes if abs(s[0] + s[2] / 2 - ratio * w) < .05 * w] for key, ratio in MARKER_TEMPLATE.items()}
    if not all(options.values()):
        return None
    best = None
    for combo in product(*(options[k] for k in MARKER_TEMPLATE)):
        ys = [s[1] + s[3] / 2 for s in combo]
        areas = [s[4] for s in combo]
        typical = float(np.median(areas))
        if any(not .45 * typical <= a <= 2.2 * typical for a in areas):
            continue
        cost = sum(abs(s[0] + s[2] / 2 - r * w) / w for s, r in zip(combo, MARKER_TEMPLATE.values())) +             sum(abs(y - float(np.median(ys))) for y in ys) / h
        if best is None or cost < best[0]:
            best = (cost, combo)
    if best is None:
        return None
    found = dict(zip(MARKER_TEMPLATE, best[1]))
    m, z, d = (found[k] for k in ('م', 'ز', 'د'))
    if not (m[0] - z[0] > .12 * w and z[0] - d[0] > .12 * w):
        return None
    return found


def guide_line_markers(crop, mask, pen_width):
    """Find the printed م / ز / د by their place on the dotted address line, without OCR.

    The markers are the only small shapes that sit on the dotted guide line and are
    bigger than its dots; handwritten digits are much taller. Colour cannot be used:
    over the green seal the black dots are more saturated than the blue ink (card 8).
    Returns {'م': stats, 'ز': stats, 'د': stats} (x, y, w, h, area) in crop
    coordinates, or None unless exactly three well-separated markers are found.
    """
    from . import handwritten_digits as hd
    found = hd.pieces(mask, pen_width)
    dots = hd.guide_dots(found, pen_width)
    if len(dots) < 8:
        # Small, faint printed dots (low-resolution photo) are dropped by the pen mask;
        # look for the line in the dark print itself.
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        normalized = cv2.divide(gray, cv2.GaussianBlur(gray, (0, 0), max(3, crop.shape[0] / 7)), scale=230)
        mask = ((normalized < 150) * 255).astype(np.uint8)
        pen_width = 1.2  # keep dots of 1–3 px
        found = hd.pieces(mask, pen_width)
        dots = hd.guide_dots(found, pen_width)
    # The strip can also show the dotted line of the field above or below; keep the row
    # of dots nearest the strip's middle (the address line itself).
    rows = []
    for p in sorted(dots, key=lambda p: (p['box'][1] + p['box'][3]) / 2):
        cy = (p['box'][1] + p['box'][3]) / 2
        if rows and cy - rows[-1][-1][0] < 2.5 * max(1, p['box'][3] - p['box'][1]):
            rows[-1].append((cy, p))
        else:
            rows.append([(cy, p)])
    middle = crop.shape[0] / 2
    rows = [r for r in rows if len(r) >= 6 and .15 * crop.shape[0] < np.median([cy for cy, _ in r]) < .85 * crop.shape[0]]
    if not rows:
        return None
    dots = [p for _, p in min(rows, key=lambda r: abs(np.median([cy for cy, _ in r]) - middle))]
    centres = np.array([((p['box'][0] + p['box'][2]) / 2, (p['box'][1] + p['box'][3]) / 2) for p in dots])
    slope, offset = np.polyfit(centres[:, 0], centres[:, 1], 1)
    size = float(np.median([max(p['box'][2] - p['box'][0], p['box'][3] - p['box'][1]) for p in dots]))
    line_y = lambda x: slope * x + offset
    guide = {id(p) for p in dots}
    # Search the whole strip (it ends before the printed label): on faint photos only part
    # of the dotted line is detected, and ز / م can lie beyond the detected dots.
    x_min, x_max = 0, crop.shape[1]
    candidates = []
    for p in found:
        x1, y1, x2, y2 = p['box']
        w, h = x2 - x1, y2 - y1
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        # Markers are a few dots tall (4–6× the dot size; a small handwritten ٥ on card 8 is 6.9×);
        # handwritten digits are taller still.
        if id(p) in guide or not x_min <= cx <= x_max or max(w, h) > 6.5 * size or max(w, h) < 1.2 * size:
            continue
        # On the line: the shape reaches the dots' row (stamp fragments float above it).
        if not (y1 <= line_y(cx) + size and y2 >= line_y(cx) - .5 * size and cy - line_y(cx) >= -3 * size):
            continue
        candidates.append([x1, y1, x2, y2, p['area']])
    # A marker can break into two pieces (م with its tail): merge pieces that nearly touch.
    merged = []
    for c in sorted(candidates):
        if merged and c[0] - merged[-1][2] < 1.5 * size:
            m = merged[-1]
            merged[-1] = [min(m[0], c[0]), min(m[1], c[1]), max(m[2], c[2]), max(m[3], c[3]), m[4] + c[4]]
        else:
            merged.append(c)
    merged = [m for m in merged if max(m[2] - m[0], m[3] - m[1]) >= 1.8 * size]
    if len(merged) > 3:
        # The three markers are printed in one font, so they carry similar ink; a small
        # handwritten digit on the line (card 8: «٥», 2.5× a marker's ink) does not.
        typical = float(np.median([m[4] for m in merged]))
        merged = [m for m in merged if m[4] <= 2 * typical]
    if len(merged) != 3:
        return None
    typical = float(np.median([m[4] for m in merged]))
    if any(not .55 * typical <= m[4] <= 2 * typical for m in merged):
        return None  # not three glyphs of one font: a digit stroke was taken for a marker
    w = crop.shape[1]
    d, z, m = ((x1, y1, x2 - x1, y2 - y1, area) for x1, y1, x2, y2, area in merged)
    if not (m[0] - z[0] > .12 * w and z[0] - d[0] > .12 * w):
        return None
    return {'م': m, 'ز': z, 'د': d}


def find_address_markers(image, region, card_mask=None, pen_width=None, lines=()):
    """(crop, markers, region_mask, pen_width): the م / ز / د markers from the best evidence.

    1. all three recognised as letters by OCR;
    2. else the dotted guide line (three printed glyphs of one font on it);
    3. else the printed form's layout, anchored on at least one recognised letter;
    4. else, only when the full-line OCR of the address could not be split into its three
       numbers, the form's layout anchored on the printed label alone. (Real blurred card:
       this guess put the markers on digit strokes and «٤١ / ٣٥» came out «2 / 5», while
       the full line of digits already held the numbers.)
    Markers is None when none of these is conclusive (no roles from position alone).
    Both address readers (OCR per slot and the digit model) use the same markers.
    """
    from . import handwritten_digits as hd
    from .focused_fields import crop_box
    if card_mask is None:
        card_mask, pen_width = hd.pen_mask(image)
    crop, recognised = address_markers(image, region, partial=True)
    mask = ((crop_box(card_mask, region['box']) > 127) * 255).astype(np.uint8)
    markers = recognised if recognised and len(recognised) == 3 else None
    if not markers:
        markers = guide_line_markers(crop, mask, pen_width) or template_markers(crop, recognised)
    if not markers:
        from .address_layout import address_line_text, parse_address_digits
        if not parse_address_digits(address_line_text(lines, region)):
            markers = label_anchored_markers(crop)
    return crop, markers, mask, pen_width


def read_address_symbols(image, region, lines=()):
    """Read isolated م/ز/د, then OCR the ink between actual marker positions.

    No positional fallback: if the markers cannot be established, keep the full-line
    reading. This leaves unknown layouts for review instead of manufacturing roles.
    """
    from .focused_fields import normalize
    from .understanding import field
    crop,chosen,_,_=find_address_markers(image,region,lines=lines)
    if not chosen:return {}
    h,w=crop.shape[:2]
    stats=components(crop)
    m,z,d=(chosen[k] for k in ('م','ز','د'))
    # Read both strong and faint ink. Fixed dark thresholds erase broad pale
    # pen strokes; the second background scale preserves those strokes.
    results={};numbers=[];records=[]
    soft=components(crop,165,1/3)
    for key,left,right,marker in [('mahalla_number',z[0]+z[2],m[0],m),
                                  ('street',d[0]+d[2],z[0],z),('house_number',0,d[0],d)]:
        used=set()
        for mask,parts in [('dark',stats),('soft',soft)]:
            ink=[s for s in parts if s[0]>=left+3 and s[0]+s[2]<=right-3
                 and s[1]+s[3]/2>.22*h and s[3]>.07*h]
            tall=[s for s in ink if s[3]>.25*h]
            if not tall:continue
            ytop=min(s[1] for s in tall);ybottom=max(s[1]+s[3] for s in tall)
            ink=[s for s in ink if ytop-.05*h<s[1]+s[3]/2<ybottom]
            zero=trailing_zero_dot(ink,tall)
            x1=min(s[0] for s in ink);x2=max(s[0]+s[2] for s in ink)
            rect=clipped_rect((max(left+2,x1-.13*h),ytop-.09*h,min(right-2,x2+.13*h),ybottom+.08*h),crop.shape)
            if rect in used:continue
            used.add(rect);a,b,c,e=rect;work=crop[b:e,a:c]
            variants=ink_variants(work)
            if mask=='soft':
                gray=cv2.cvtColor(work,cv2.COLOR_RGB2GRAY)
                variants += [('gray',cv2.cvtColor(gray,cv2.COLOR_GRAY2RGB)),('contrast',cv2.cvtColor(cv2.createCLAHE(2,(4,4)).apply(gray),cv2.COLOR_GRAY2RGB))]
            for variant,work in variants:
                numbers.append(work);records.append((key,mask+'_'+variant,rect,marker,zero))
    for (key,variant,rect,marker,zero),reading in zip(records,arabic_ocr.recognize_crops(numbers)):
        value=normalize(reading['text']).strip(' .:،')
        if not re.fullmatch(r'\d{1,6}(?:/\d{1,6})?',value) or reading['confidence']<.38:continue
        results.setdefault(key,[]).append(dict(value=value,confidence=reading['confidence'],variant=variant,
                                             engine='ppocr_v5_arabic',box=original_box(rect,region,crop),
                                             zero_box=original_box((zero[0],zero[1],zero[0]+zero[2],zero[1]+zero[3]),region,crop) if zero else None,
                                             marker_box=original_box((marker[0],marker[1],marker[0]+marker[2],marker[1]+marker[3]),region,crop)))
    output={}
    for key,reads in results.items():
        groups={}
        for r in reads:groups.setdefault(r['value'],[]).append(r)
        candidates=sorted([dict(max(rs,key=lambda r:r['confidence']),support=len(rs)) for rs in groups.values()],
                          key=lambda r:(r['support'],r['confidence']),reverse=True)
        best=candidates[0]
        strongest=max(candidates,key=lambda r:r['confidence'])
        if strongest['confidence']-best['confidence']>.10:
            best=strongest
            candidates=[best]+[c for c in candidates if c is not best]
        note='قراءة رقم معزول من الحبر بعد التعرف على رمزه م/ز/د. راجع النقاط التي قد تكون أصفارًا؛ البدائل لا تُعتمد تلقائيًا.'
        if (best.get('zero_box') and re.fullmatch(r'[0-9]{1,5}',best['value']) and not best['value'].endswith('0')
                and len({r['value'] for r in candidates})==1):
            base=best
            best=dict(base,value=base['value']+'0',observed_value=base['value'],confidence=None,engine='visible_zero_dot',support=0,
                      note='صفر محتمل من نقطة حبر واضحة تلي الرقم؛ قد تكون علامة فصل، لذا تبقى القراءة دون الصفر بديلًا.')
            candidates=[best]+candidates
            note+=' أضيف صفر محتمل بسبب نقطة حبر مرئية بعد الرقم؛ هذه قراءة تقريبية وليست نتيجة OCR مؤكدة.'
        output[key]=field(key,best['value'],best['confidence'],best['box'],'housing_ink_components',
                          'conflict' if len(candidates)>1 else 'approximate',approximate=True,candidates=candidates,
                          marker_box=best['marker_box'],raw_text=best.get('observed_value',best['value']),
                          note=note)
    return output


NUMBER_KEYS = ('mahalla_number', 'street', 'house_number', 'form_number')


def digit_model_readings(image, regions, lines=()):
    """Independent second reader for handwritten Eastern Arabic numbers.

    Reads each address slot between the printed markers (م … ز … د) and the form
    number with app/handwritten_digits. Returns {key: reading}; nothing when the
    markers or the model are missing (roles are never assigned by position alone).
    Numbers the normal ink mask finds nothing in get a second pass that also takes
    faded coloured ink (development card: pale red digits on a low-resolution photo).
    """
    from . import handwritten_digits as hd
    if not hd.available():
        return {}
    slots = {}
    out = _digit_readings(image, regions, lines, *hd.pen_mask(image), slots)
    sequences = sequence_readings(slots)
    found = set(out) | set((out.get('_layout') or {}))
    if any(k not in found for k in NUMBER_KEYS):
        faint = _digit_readings(image, regions, lines, *hd.pen_mask(image, faint=True))
        for key in NUMBER_KEYS:
            if key not in found and key in faint:
                out[key] = dict(faint[key], faint_ink=True)
        layout = faint.get('_layout') or {}
        for key, r in layout.items():
            if key not in found:
                out.setdefault('_layout', {})[key] = r
    other_views(image, lines, out)
    if sequences:
        out['_sequence'] = sequences
    # The strips themselves, for learning from the reviewer's corrections (app/learning.py).
    out['_strips'] = {key: s[4][:, s[2]:s[3]].copy() for key, s in slots.items()}
    return out


def sequence_readings(slots):
    """The same number strips read whole by Mustamsak's own number reader (app/number_reader.py)."""
    from . import number_reader
    if not number_reader.available():
        return {}
    out = {}
    for key, (region, mask, x1, x2, crop, marker, _) in slots.items():
        r = number_reader.read(crop[:, x1:x2])
        if r and (key != 'form_number' or len(r['value']) >= 3):
            out[key] = dict(r, box=original_box((x1, 0, x2, crop.shape[0]), region, crop))
    return out


def _unsettled(reading):
    """Missing, fused with a stamp, or leaving most of its strip's ink unexplained."""
    return not reading or reading.get('occluded') or (reading.get('clutter') or 0) > .5


def other_views(image, lines, out):
    """Read unsettled numbers again on standardised views of the card: its lighting evened out,
    and the card at the standard width. A view's reading is used only when it is clean (every
    digit ≥ 80%, most of the ink explained); numbers read well at the photo's own size and
    lighting are never touched. Stress test on development cards: standard width alone helped ×1.5
    photos (18→23/32) and brighter ones (11→16/32) but cost the original photos 30→28/32.
    """
    from . import handwritten_digits as hd, vision
    from .focused_fields import housing_regions
    unsettled = lambda: [k for k in NUMBER_KEYS if _unsettled(out.get(k)) and not (out.get('_layout') or {}).get(k)]
    views = [('even_lighting', lambda: (vision.even_lighting(image), list(lines), 1.0)),
             ('sharpened', lambda: (vision.sharpened(image), list(lines), 1.0)),
             ('standard_width', lambda: vision.standard_card(image, lines)),
             ('standard_width_even_lighting', lambda: vision.standard_card(vision.even_lighting(image), lines))]
    for name, make in views:
        keys = unsettled()
        if not keys:
            return
        view, view_lines, factor = make()
        if name.startswith('standard') and factor == 1.0:
            continue
        readings = _digit_readings(view, housing_regions(view, view_lines, 'front'), view_lines, *hd.pen_mask(view))
        for key in keys:
            r = readings.get(key)
            if not r or _doubtful(r) or r.get('occluded') or (key == 'form_number' and len(r['value']) < 3):
                continue
            if factor != 1.0:  # boxes back to the photo's own coordinates
                r = dict(r, box=(np.asarray(r['box']) / factor).round(2).tolist(),
                         marker_box=None if r.get('marker_box') is None else (np.asarray(r['marker_box']) / factor).round(2).tolist())
            old = out.get(key)
            out[key] = dict(r, view=name, replaced=old['value'] if old else None)


def _digit_readings(image, regions, lines, card_mask, pen_width, slots_out=None):
    from . import handwritten_digits as hd
    from .focused_fields import crop_box
    out = {}
    slots = {}  # key -> (region, mask, x1, x2, crop, marker): lets a doubtful number be re-read

    def read(region, mask, x1, x2, crop, marker=None, width=None):
        line_y = marker[1] + marker[3] / 2 if marker else None  # the printed م / ز / د sits on the number's line
        r = hd.read_digits(rgb=crop[:, x1:x2], mask=mask[:, x1:x2], pen_width=width or pen_width, line_y=line_y)
        if not r:
            return None
        xs = [d['box'][0] for d in r['digits']] + [d['box'][2] for d in r['digits']]
        ys = [d['box'][1] for d in r['digits']] + [d['box'][3] for d in r['digits']]
        box = original_box((x1 + min(xs), min(ys), x1 + max(xs), max(ys)), region, crop)
        return dict(r, box=box, marker_box=original_box((marker[0], marker[1], marker[0] + marker[2], marker[1] + marker[3]),
                                                        region, crop) if marker else None)

    address = next((r for r in regions if r['key'] == 'address'), None)
    if address:
        crop, markers, mask, _ = find_address_markers(image, address, card_mask, pen_width, lines)
        if not markers:
            from .address_layout import read_by_layout
            out['_layout'] = read_by_layout(image, address, lines, pen_width)
        if markers:
            h, w = mask.shape
            m, z, d = (markers[k] for k in ('م', 'ز', 'د'))
            blanks = []
            for x, y, mw, mh, _ in (m, z, d):
                # Blank each printed marker with its dot (ز) so it is never read as a digit.
                blanks.append((max(0, int(y - 1.2 * mh)), min(h, int(y + 1.4 * mh)), max(0, int(x - .5 * mh)), min(w, int(x + mw + .5 * mh))))
            for y1, y2, bx1, bx2 in blanks:
                mask[y1:y2, bx1:bx2] = 0
            for key, x1, x2, marker in [('mahalla_number', z[0] + z[2] + .25 * z[3], m[0] - .25 * m[3], m),
                                        ('street', d[0] + d[2] + .25 * d[3], z[0] - .25 * z[3], z),
                                        ('house_number', 0, d[0] - .25 * d[3], d)]:
                x1, x2 = int(max(0, x1)), int(min(w, x2))
                if x2 - x1 >= 6:
                    reading = read(address, mask, x1, x2, crop, marker)
                    slots[key] = (address, mask, x1, x2, crop, marker, blanks)
                    if reading:
                        out[key] = reading
    form = next((r for r in regions if r['key'] == 'form_number'), None)
    if form:
        crop = crop_box(image, form['box'])
        mask = ((crop_box(card_mask, form['box']) > 127) * 255).astype(np.uint8)
        reading = read(form, mask, 0, mask.shape[1], crop)
        slots['form_number'] = (form, mask, 0, mask.shape[1], crop, None, [])
        if reading and len(reading['value']) >= 3:
            out['form_number'] = reading
    if slots_out is not None:  # the number strips, for the sequence reader (app/number_reader.py)
        slots_out.update(slots)
    mark_occluded(out)
    reread_by_ink(out, slots, read)
    reread_locally(out, slots, read)
    return out


def _doubtful(reading):
    return (reading.get('occluded') or (reading.get('clutter') or 0) > .3
            or min((d['probability'] for d in reading['digits']), default=0) < .8)


def reread_by_ink(readings, slots, read):
    """Re-read doubtful numbers from the pen layer only, separated from the stamp by ink darkness.

    The pen's lightness is measured on this card's own clean numbers, so every card, pen
    and stamp is handled from its own evidence. A re-reading counts only when every digit
    is ≥ 80% and of normal digit size. It replaces a reading only when that reading is
    unusable (a digit fused with a stamp, or nothing read); a merely weak reading keeps
    its value and gets the re-reading as a suggestion (on development cards, «٤٠» and «٤٢» were
    right and their colour re-readings wrong). Either way it stays a single-reader value.
    """
    from . import handwritten_digits as hd
    clean = [(k, r) for k, r in readings.items() if k != '_layout' and k in slots and not _doubtful(r)]
    lightness = []
    for key, r in clean:
        region, mask, x1, x2, crop = slots[key][:5]
        lab_l = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)[:, :, 0]
        for d in r['digits']:
            bx1, by1, bx2, by2 = d['box']
            ink = mask[by1:by2, x1 + bx1:x1 + bx2] > 0
            lightness.extend(lab_l[by1:by2, x1 + bx1:x1 + bx2][ink].tolist())
    pen_lightness = float(np.median(lightness)) if len(lightness) > 50 else None
    for key, (region, mask, x1, x2, crop, marker, _) in slots.items():
        old = readings.get(key)
        if old and not _doubtful(old):
            continue
        layer = hd.pen_layer(crop[:, x1:x2], mask[:, x1:x2], pen_lightness)
        if layer is None:
            continue
        separated = mask.copy()
        separated[:, x1:x2] = layer
        fresh = read(region, separated, x1, x2, crop, marker)
        if not fresh or _doubtful(fresh) or (key == 'form_number' and len(fresh['value']) < 3):
            continue
        trial = {k: v for k, v in readings.items() if k != key} | {key: fresh}
        mark_occluded(trial)
        if trial[key].get('occluded'):
            continue
        if old and not old.get('occluded'):
            old.setdefault('ink_alternative', fresh['value'])
            continue
        fresh.update(ink_separated=True, replaced=old['value'] if old else None)
        readings[key] = fresh


def reread_locally(readings, slots, read):
    """Re-read doubtful numbers from a mask built on their own strip (own background and pen width).

    Replaces a reading only when it was missing, fused with a stamp, or left most of the
    strip's ink unexplained (clutter > 50%: it missed digits, as a three-digit reading of a five-digit number did);
    a merely weak reading keeps its value and gets the re-reading as a suggestion.
    """
    from . import handwritten_digits as hd
    for key, (region, mask, x1, x2, crop, marker, blanks) in slots.items():
        old = readings.get(key)
        if old and not _doubtful(old):
            continue
        local, width = hd.local_mask(crop)
        for y1, y2, bx1, bx2 in blanks:
            local[y1:y2, bx1:bx2] = 0
        fresh = read(region, local, x1, x2, crop, marker, width)
        if not fresh or _doubtful(fresh) or (key == 'form_number' and len(fresh['value']) < 3):
            continue
        trial = {k: v for k, v in readings.items() if k != key} | {key: fresh}
        mark_occluded(trial)
        if trial[key].get('occluded') or (old and fresh['value'] == old['value']):
            continue
        if old and not old.get('occluded') and (old.get('clutter') or 0) <= .5:
            old.setdefault('ink_alternative', fresh['value'])
            continue
        fresh.update(local_mask=True, replaced=old['value'] if old else None)
        readings[key] = fresh


def mark_occluded(readings):
    """Flag numbers where one "digit" is far bigger than the card's digits in both directions.

    That is a digit fused with stamp lettering (development card: «١» of «١٥» merged with the
    office stamp and read «9»). The shape is not one digit, so its reading cannot be trusted.
    """
    sizes = [(d['box'][2] - d['box'][0], d['box'][3] - d['box'][1]) for k, r in readings.items() if k != '_layout'
             for d in r['digits'] if d['digit'] != 0]
    if len(sizes) < 4:
        return
    typical = float(np.median([h for _, h in sizes]))
    for key, r in readings.items():
        if key != '_layout' and any(d['digit'] != 0 and d['box'][2] - d['box'][0] > 1.6 * typical
                                    and d['box'][3] - d['box'][1] > 1.6 * typical for d in r['digits']):
            r['occluded'] = True


def combine_digit_readings(fields, readings):
    """Compare the digit model with the existing OCR reading of the same number.

    Agreement between the two independent readers raises confidence; disagreement
    becomes a visible conflict with both candidates. A value is only ever one of
    the readings; nothing is completed or invented.
    """
    from .focused_fields import normalize
    from .understanding import field
    readings = dict(readings)
    sequences = readings.pop('_sequence', None) or {}
    readings.pop('_strips', None)
    layout = readings.pop('_layout', None)
    if layout is not None:
        from .address_layout import layout_fields
        layout_fields(fields, layout)
    for key, r in readings.items():
        if r.get('ink_alternative') and r['ink_alternative'] != r['value']:
            ink_candidate = {'value': r['ink_alternative'], 'confidence': None, 'engine': 'pen_ink_layer',
                             'note': 'قراءة بعد فصل حبر القلم عن الختم؛ اقتراح فقط.'}
        else:
            ink_candidate = None
        candidate = {'value': r['value'], 'confidence': r['confidence'], 'engine': 'eastern_digit_model', 'box': r['box'],
                     'digits': [{'digit': d['digit'], 'probability': round(d['probability'], 3),
                                 'alternatives': d['alternatives']} for d in r['digits']]}
        f = fields.get(key)
        if f and (f.get('verified') or f.get('method') == 'manual' or f.get('status') == 'manual'):
            continue
        old = normalize(str((f or {}).get('value') or '')).strip()
        others = [c for c in (f or {}).get('candidates', []) if c.get('engine') not in ('eastern_digit_model', 'pen_ink_layer')]
        if ink_candidate:
            others.append(ink_candidate)
        if f and old and f.get('status') != 'unreadable':
            if old == r['value']:
                f.update(confidence=round(max(f.get('confidence') or 0, r['confidence']), 3), status='uncertain',
                         approximate=False, agreement=True, candidates=[candidate] + others,
                         note='قرأ محركان مستقلان الرقم المكتوب باليد نفسه؛ راجعه مع الصورة قبل الاعتماد.')
            elif digit_vote(r, old) == old:
                # Same length; every digit where they differ was the model's 2nd/3rd choice.
                f.update(confidence=round(min(f.get('confidence') or 0, r['confidence']) * .9, 3), status='uncertain',
                         approximate=True, agreement=True, candidates=others + [candidate],
                         note='اختلف القارئان في رقم أو أكثر، والرقم المختار كان بديلًا ثانيًا لقارئ الأرقام الهندية؛ راجعه مع الصورة.')
            else:
                # The model wins a disagreement only when it is sure of every digit: one weak
                # digit (a stroke fragment read as a digit) must not overrule the other reader.
                use_model = (r['confidence'] >= .75 and min(d['probability'] for d in r['digits']) >= .8
                             and not r.get('occluded'))
                f.update(value=r['value'] if use_model else f['value'],
                         confidence=r['confidence'] if use_model else f.get('confidence'),
                         method='eastern_digit_model' if use_model else f.get('method'), status='conflict',
                         approximate=True, candidates=([candidate] + others) if use_model else others + [candidate],
                         note='اختلف قارئ الأرقام الهندية عن القراءة العامة؛ قارن البدائل بالصورة.')
        else:
            # Only one reader saw this number: it stays approximate (and at most 80%)
            # until a second, independent reader agrees. A stamp over the digits can
            # make a single reader confidently wrong.
            cluttered = (r.get('clutter') or 0) > .5
            if r.get('ink_separated'):
                fields[key] = field(key, r['value'], round(min(r['confidence'], .8), 3), r['box'], 'eastern_digit_model',
                                    'approximate', approximate=True, single_reader=True, ink_separated=True,
                                    candidates=[candidate] + others, marker_box=r.get('marker_box'),
                                    note='الرقم متداخل مع ختم؛ فُصل حبر القلم عن حبر الختم بدرجة اللون ثم قُرئ. '
                                         'قراءة من قارئ واحد؛ قارنها بالصورة قبل الاعتماد.')
                continue
            if r.get('occluded'):
                # Blank and flagged beats a wrong number: keep the reading only as a suggestion.
                fields[key] = field(key, '', None, r['box'], 'eastern_digit_model', 'unreadable', single_reader=True,
                                    candidates=[candidate] + others, marker_box=r.get('marker_box'),
                                    note='ختم أو كتابة أخرى تلتصق بأحد الأرقام فلا يمكن قراءته آليًا. الاقتراح '
                                         f'«{r["value"]}» غير موثوق؛ اقرأ الرقم من الصورة وأدخله.')
                continue
            fields[key] = field(key, r['value'], round(min(r['confidence'], .8), 3), r['box'], 'eastern_digit_model',
                                'approximate', approximate=True, single_reader=True,
                                candidates=[candidate] + others, marker_box=r.get('marker_box'),
                                note=('يتداخل ختم أو كتابة أخرى مع الرقم؛ قد تكون الأرقام مشوهة، راجعها مع الصورة.'
                                      if cluttered else 'قراءة رقم مكتوب باليد بالأرقام الهندية، رقمًا رقمًا؛ راجع كل رقم مع الصورة.'))
    sequence_votes(fields, sequences)
    return fields


SEQUENCE_SURE = .9  # every digit at least this probable for the number reader to move a value


def sequence_votes(fields, sequences):
    """Mustamsak's own number reader votes on each handwritten number (docs/HANDWRITING.md).

    - It agrees with the current value: two independent readers now agree.
    - It agrees with a reading that lost (another engine's candidate) and is sure of every
      digit: that reading wins 2 to 1, still marked approximate.
    - Otherwise (including a number no other reader could read) it is one more candidate for
      the reviewer; a blank field stays blank (blank and flagged beats invented).
    Manual and verified fields are never touched.
    """
    from .focused_fields import normalize
    for key, r in sequences.items():
        f = fields.get(key)
        if not f or f.get('verified') or f.get('method') == 'manual' or f.get('status') == 'manual':
            continue
        sure = min(d['probability'] for d in r['digits']) >= SEQUENCE_SURE
        candidate = {'value': r['value'], 'confidence': r['confidence'], 'engine': 'number_reader', 'box': r['box'],
                     'digits': r['digits'], 'note': 'قراءة قارئ الأرقام الخاص بمستمسك للرقم كاملًا.'}
        others = [c for c in f.get('candidates', []) if c.get('engine') != 'number_reader']
        current = normalize(str(f.get('value') or '')).strip()
        if current and current == r['value']:
            f.update(candidates=others + [candidate], agreement=True, sequence_agrees=True,
                     confidence=round(max(f.get('confidence') or 0, min(.9, r['confidence'])), 3))
            if f.get('single_reader') and sure and not f.get('ink_separated'):
                f.update(single_reader=False, approximate=False, status='uncertain',
                         note='قرأ قارئان مستقلان الرقم نفسه (قارئ الأرقام الهندية وقارئ الأرقام الخاص)؛ راجعه مع الصورة.')
            continue
        backed = [c for c in others if normalize(str(c.get('value') or '')).strip() == r['value']]
        if current and backed and sure:
            loser = {'value': f['value'], 'confidence': f.get('confidence'), 'engine': f.get('method')}
            f.update(value=r['value'], confidence=round(min(.8, r['confidence']), 3), method='number_reader',
                     status='conflict', approximate=True, agreement=True,
                     candidates=[candidate] + [c for c in others if c not in backed] + backed + [loser],
                     note='قرأ قارئان الرقم نفسه واختلف معهما قارئ ثالث؛ اخترنا قراءة الأغلبية. راجعه مع الصورة.')
            continue
        f['candidates'] = others + [candidate]


def digit_vote(reading, other):
    """Per-digit vote between the digit model and another reading of the same length.

    Returns `other` when, at every position where the two differ, the other
    reader's digit is among the model's own alternatives for that digit; else None.
    """
    digits = reading.get('digits') or []
    if not other or len(other) != len(digits) or not other.isdigit():
        return None
    for d, o in zip(digits, other):
        if str(d['digit']) == o:
            continue
        # Only overrule a digit the model itself was unsure about.
        if d.get('probability', 0) >= .8 or int(o) not in [a['digit'] for a in d.get('alternatives', [])]:
            return None
    return other
