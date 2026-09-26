"""Capture-quality guidance: tell the user *why* a photo should be retaken.

Every check is a local image measurement with an explainable threshold. The
output is guidance for the person holding the camera and context for the
reviewer; it never changes extracted field values.

Severity:
  retake  the photo is likely to hide or corrupt fields; ask for a new photo
  warn    reading may be degraded; review the affected fields carefully
  info    handled automatically (e.g. perspective corrected), shown for context
"""
import cv2
import numpy as np

# Thresholds live here so evaluation can tune them in one place (see docs/ARCHITECTURE.md).
MIN_SHORT_SIDE = 380          # px on the rectified document
BLUR_RETAKE, BLUR_WARN = 30, 70   # variance of Laplacian at 1000 px width
DARK_RETAKE, DARK_WARN = 55, 80   # mean luminance 0..255
BRIGHT_WARN = 228
LOW_CONTRAST = 26             # luminance standard deviation
GLARE_WARN, GLARE_RETAKE = .008, .035  # fraction of the document covered by one glare blob
EDGE_MARGIN = .006            # fraction of the source image treated as its border
TILT_WARN_DEG, KEYSTONE_WARN = 22, .72

MESSAGES = {
    'cut_off': ('جزء من المستمسك خارج إطار الصورة ({where})؛ أعد التصوير مع ترك هامش حول الحواف الأربع.',
                'Part of the document is outside the frame ({where}); retake with a margin around all four edges.'),
    'too_small': ('المستمسك صغير جدًا في الصورة؛ قرّب الكاميرا حتى يملأ المستمسك معظم الإطار.',
                  'The document is too small in the photo; move closer so it fills most of the frame.'),
    'blur': ('الصورة ضبابية؛ ثبّت الهاتف وانتظر التركيز قبل الالتقاط.',
             'The photo is blurry; hold the phone steady and let it focus before capturing.'),
    'too_dark': ('الإضاءة ضعيفة؛ صوّر قرب مصدر ضوء أو نافذة دون ظلال على المستمسك.',
                 'The lighting is too dark; photograph near a light source without shadows on the document.'),
    'overexposed': ('الصورة شديدة السطوع وقد تختفي الحروف الفاتحة؛ خفّف الإضاءة المباشرة.',
                    'The photo is overexposed and faint text may vanish; reduce direct light.'),
    'low_contrast': ('التباين ضعيف بين النص والخلفية؛ غيّر الإضاءة أو الخلفية.',
                     'Low contrast between text and background; change the lighting or background.'),
    'glare': ('يوجد انعكاس ضوء على المستمسك ({where}) قد يغطي بعض الحقول؛ غيّر زاوية الهاتف لإزالة اللمعان.',
              'Glare on the document ({where}) may hide fields; tilt the phone slightly to remove the reflection.'),
    'tilt': ('المستمسك مصوّر بزاوية مائلة؛ صُحّح المنظور آليًا، لكن التصوير من الأعلى مباشرة أدق.',
             'The document was photographed at an angle; perspective was corrected, but a straight top-down photo reads better.'),
    'edges_not_found': ('لم تُكتشف حواف المستمسك؛ استُخدمت الصورة كاملة. ضع المستمسك على خلفية داكنة وسادة.',
                        'Document edges were not found; the whole image was used. Place the document on a plain, darker background.'),
}
SEVERITY_ORDER = {'retake': 0, 'warn': 1, 'info': 2}
WHERE = {'top': ('الأعلى', 'top'), 'bottom': ('الأسفل', 'bottom'), 'left': ('اليسار', 'left'), 'right': ('اليمين', 'right'),
         'center': ('الوسط', 'center')}


def issue(code, severity, where=None, **measure):
    ar, en = MESSAGES[code]
    place = [WHERE[w] for w in (where or [])]
    return {'code': code, 'severity': severity,
            'message': ar.format(where='، '.join(p[0] for p in place) or 'غير محدد'),
            'message_en': en.format(where=', '.join(p[1] for p in place) or 'unknown'),
            'where': list(where or []), 'measure': {k: round(float(v), 4) for k, v in measure.items()}}


def standard_gray(image, width=1000):
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    scale = width / max(1, gray.shape[1])
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)


def sharpness(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def locate(mask_or_box, shape):
    """Name the part of the image where a region lies."""
    h, w = shape[:2]
    if isinstance(mask_or_box, tuple):
        x, y, bw, bh = mask_or_box
        cx, cy = x + bw / 2, y + bh / 2
    else:
        ys, xs = np.nonzero(mask_or_box)
        cx, cy = float(xs.mean()), float(ys.mean())
    parts = []
    if cy < h / 3: parts.append('top')
    elif cy > 2 * h / 3: parts.append('bottom')
    # Image coordinates: x grows to the viewer's right.
    if cx < w / 3: parts.append('left')
    elif cx > 2 * w / 3: parts.append('right')
    return parts or ['center']


def glare(image):
    """Largest compact, clipped highlight that is brighter than its surroundings.

    Plain white paper or a scanned page is excluded: its clipped area is either
    huge and connected, or not brighter than the paper around it.
    """
    small = cv2.resize(image, (640, max(1, round(image.shape[0] * 640 / image.shape[1]))), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 2] >= 246) & (hsv[:, :, 1] <= 45)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    total = small.shape[0] * small.shape[1]
    best = None
    value = hsv[:, :, 2].astype(np.float32)
    for i in range(1, count):
        area = stats[i, cv2.CC_STAT_AREA]
        if not .003 * total < area < .30 * total:
            continue
        blob = (labels == i).astype(np.uint8)
        ring = cv2.dilate(blob, np.ones((15, 15), np.uint8)) - blob
        if not ring.any() or value[ring > 0].mean() > 225:
            continue  # Blends into bright paper; not a specular highlight.
        if best is None or area > best[0]:
            best = (area, blob)
    if best is None:
        return 0.0, None
    return best[0] / total, locate(best[1], small.shape)


def border_contact(points, source_shape):
    """Sides of the source image that the detected document quad touches."""
    h, w = source_shape[:2]
    p = np.asarray(points, float)
    mx, my = EDGE_MARGIN * w + 1, EDGE_MARGIN * h + 1
    sides = set()
    for x, y in p:
        if x <= mx: sides.add('left')
        if x >= w - 1 - mx: sides.add('right')
        if y <= my: sides.add('top')
        if y >= h - 1 - my: sides.add('bottom')
    return sides


def foreground_contact(source):
    """Sides touched by the main light object, for photos where no quad was found.

    A document touching one to three sides extends beyond the frame; touching all
    four usually means a tight crop or a scan, which is acceptable.
    """
    gray = standard_gray(source, 500)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return set()
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    h, w = mask.shape
    if stats[i, cv2.CC_STAT_AREA] < .15 * h * w:
        return set()
    blob = labels == i
    # Require a real stretch of border contact, not a single noisy pixel.
    contact = {'top': blob[0].mean(), 'bottom': blob[-1].mean(), 'left': blob[:, 0].mean(), 'right': blob[:, -1].mean()}
    # The background must be visible somewhere, otherwise this is a tight crop.
    background = 1 - blob.mean()
    if background < .08:
        return set()
    return {side for side, share in contact.items() if share > .12}


def geometry(points):
    p = np.asarray(points, float)
    top, bottom = p[1] - p[0], p[2] - p[3]
    left, right = p[3] - p[0], p[2] - p[1]
    angle = abs(np.degrees(np.arctan2(top[1], top[0])))
    angle = min(angle, 180 - angle)
    widths = sorted([np.linalg.norm(top), np.linalg.norm(bottom)])
    heights = sorted([np.linalg.norm(left), np.linalg.norm(right)])
    keystone = min(widths[0] / max(1, widths[1]), heights[0] / max(1, heights[1]))
    return angle, keystone


def assess(document, points=None, source=None, method=None, reference_outside=None):
    """Guidance for one rectified document crop.

    points/source/method describe how the crop was found in the uploaded image,
    when available. reference_outside lists sides where a strong visual-reference
    match places the document's true corners outside the image.
    """
    issues = []
    h, w = document.shape[:2]
    sides = set(reference_outside or [])
    if source is not None and points is not None and method not in (None, 'manual'):
        if method in ('whole_page', 'seam'):
            sides |= foreground_contact(source)
        else:
            touching = border_contact(points, source.shape)
            if touching and len(touching) < 4:
                sides |= touching
    if sides:
        issues.append(issue('cut_off', 'retake', sorted(sides)))
    elif method == 'whole_page':
        issues.append(issue('edges_not_found', 'info'))
    if min(h, w) < MIN_SHORT_SIDE:
        issues.append(issue('too_small', 'retake' if min(h, w) < .6 * MIN_SHORT_SIDE else 'warn', short_side=min(h, w)))
    gray = standard_gray(document)
    sharp = sharpness(gray)
    if sharp < BLUR_WARN:
        issues.append(issue('blur', 'retake' if sharp < BLUR_RETAKE else 'warn', laplacian_variance=sharp))
    mean, std = float(gray.mean()), float(gray.std())
    if mean < DARK_WARN:
        issues.append(issue('too_dark', 'retake' if mean < DARK_RETAKE else 'warn', mean_luminance=mean))
    elif mean > BRIGHT_WARN:
        issues.append(issue('overexposed', 'warn', mean_luminance=mean))
    if std < LOW_CONTRAST:
        issues.append(issue('low_contrast', 'warn', luminance_std=std))
    share, where = glare(document)
    if share >= GLARE_WARN:
        issues.append(issue('glare', 'retake' if share >= GLARE_RETAKE else 'warn', where, area_share=share))
    if points is not None and method not in (None, 'whole_page', 'seam', 'manual'):
        angle, keystone = geometry(points)
        if angle > TILT_WARN_DEG or keystone < KEYSTONE_WARN:
            issues.append(issue('tilt', 'info', angle_degrees=angle, keystone=keystone))
    return sorted(issues, key=lambda i: SEVERITY_ORDER[i['severity']])


def needs_retake(issues):
    return any(i['severity'] == 'retake' for i in issues or [])


def check_upload(image):
    """Fast capture-time check (no OCR): find documents and report retake reasons."""
    from . import vision
    documents = []
    for region in vision.detect_regions(image):
        try:
            crop = vision.warp(image, region['points'])
        except ValueError:
            continue
        issues = assess(crop, region['points'], image, region['method'])
        documents.append({'points': region['points'], 'method': region['method'], 'issues': issues,
                          'retake': needs_retake(issues)})
    retake = any(d['retake'] for d in documents)
    reasons = [i for d in documents for i in d['issues'] if i['severity'] == 'retake']
    return {'documents': documents, 'retake': retake,
            'message': (reasons[0]['message'] if reasons else 'الصورة مناسبة للقراءة.'),
            'message_en': (reasons[0]['message_en'] if reasons else 'The photo is suitable for reading.')}
