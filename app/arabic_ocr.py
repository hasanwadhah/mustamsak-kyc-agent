"""Offline PP-OCRv5 Arabic/English, with batched reading of individual fields."""
from pathlib import Path
import re
import threading
import cv2
import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[1] / 'models' / 'ppocr'
FILES = ['ch_PP-OCRv5_det_mobile.onnx', 'arabic_PP-OCRv5_rec_mobile.onnx',
         'en_PP-OCRv5_rec_mobile.onnx', 'ch_ppocr_mobile_v2.0_cls_mobile.onnx']
_engines = {}
LOCK = threading.RLock()

def available():
    return all((MODEL_DIR / name).is_file() for name in FILES)

def engine(language='arabic'):
    if language not in _engines:
        if not available():
            raise RuntimeError('شغّل scripts/setup_arabic_v5.py لتثبيت القراءة العربية المحسنة.')
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from rapidocr import RapidOCR, EngineType, LangRec, ModelType, OCRVersion
        params = {
            'Global.log_level': 'error', 'Global.use_cls': False,
            'Global.text_score': .3, 'Global.model_root_dir': str(MODEL_DIR),
            'EngineConfig.onnxruntime.intra_op_num_threads': 4,
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
            'Det.model_path': str(MODEL_DIR / FILES[0]),
            'Det.ocr_version': OCRVersion.PPOCRV5, 'Det.model_type': ModelType.MOBILE,
            'Det.limit_side_len': 960, 'Det.limit_type': 'max',
            'Cls.model_path': str(MODEL_DIR / FILES[3]),
            'Rec.model_path': str(MODEL_DIR / FILES[1 if language == 'arabic' else 2]),
            'Rec.lang_type': LangRec.ARABIC if language == 'arabic' else LangRec.EN,
            'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
            'Rec.engine_type': EngineType.ONNXRUNTIME,
        }
        _engines[language] = RapidOCR(params=params)
    return _engines[language]

ARABIC_LETTER = re.compile('[ء-ي]')
EASTERN_DIGIT = re.compile('[٠-٩۰-۹]')
LATIN_TOKEN = re.compile(r'[A-Z0-9](?:[A-Z0-9<]|[/.\-](?=[A-Z0-9<]))+')
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
MIN_SCORE = .3


def latin_tokens(text):
    """Numbers, dates, serials and MRZ runs from an English reading.

    Letter-only tokens are rejected: the English model renders Arabic script as
    plausible-looking Latin words ("الاسم" -> "AWLL").
    """
    return [t for t in LATIN_TOKEN.findall(str(text).upper()) if len(t) >= 3 and VALUE_SHAPE.fullmatch(t)]


# Shapes of values printed in Latin script on Iraqi documents. Anything else from the
# English model on an Arabic line (e.g. "06LWOLOAW") is treated as noise.
VALUE_SHAPE = re.compile(r'\d[\d/.\-]*\d'                 # numbers and dates
                         r'|[A-Z]{1,3}-?\d{3,}'           # licence / registration numbers (BL-93262)
                         r'|[A-Z]{1,2}\d{6,9}'            # card serials
                         r'|[A-Z0-9<]*<[A-Z0-9<]*<[A-Z0-9<]*')  # MRZ runs


def merge_readings(arabic, english):
    """Combine the Arabic and English recognizers for one detected text box.

    The Arabic model drops Latin letters and digits, the English model drops
    Arabic, and printed documents put both on one line ("رقم الإجازة  BL-93262").
    Keep the Arabic reading and add only the Latin/number tokens it is missing.
    Nothing is invented: every token comes from one of the two recognizers.
    """
    a_text, a_score = arabic['text'].strip(), float(arabic['confidence'])
    e_text, e_score = english['text'].strip(), float(english['confidence'])
    # Arabic-Indic digits (٠-٩) are Arabic-script content too: a handwritten «٦٧٣»
    # must never be replaced by the English model's reading of it («7ur»).
    arabic_letters = len(ARABIC_LETTER.findall(a_text)) + len(EASTERN_DIGIT.findall(a_text))
    if arabic_letters < 2:
        # No real Arabic here (MRZ, serials, national numbers, Latin words).
        if e_text and (e_score >= a_score or e_score >= .6) and e_score >= MIN_SCORE:
            return {'text': e_text, 'confidence': round(e_score, 3), 'engine': 'ppocr_v5_en',
                    'alternatives': [{'text': a_text, 'confidence': round(a_score, 3), 'engine': 'ppocr_v5_arabic'}] if a_text else []}
        if a_text and a_score >= MIN_SCORE:
            return {'text': a_text, 'confidence': round(a_score, 3), 'engine': 'ppocr_v5_arabic'}
        return None
    if a_score < MIN_SCORE:
        return None
    line = {'text': a_text, 'confidence': round(a_score, 3), 'engine': 'ppocr_v5_arabic'}
    # Below ~.8 the English model is often reading Arabic letters as digits (الداخلية -> 1189).
    # Only when the box also holds Arabic words (a label next to a Latin value).
    # A box of Arabic-Indic digits alone is one number; the English model is just
    # reading the same ink again («٣٨٢٧٥» vs «18272») and must not be appended.
    if e_score >= .80 and len(ARABIC_LETTER.findall(a_text)) >= 2:
        present = re.sub(r'\D', '', a_text.translate(DIGITS))
        added = [t for t in latin_tokens(e_text) if not (re.sub(r'\D', '', t) and re.sub(r'\D', '', t) in present)]
        if added:
            # Right-to-left layout: the value sits after (to the left of) the label.
            line.update(text=a_text + ' ' + ' '.join(added), confidence=round(min(a_score, e_score), 3),
                        engine='ppocr_v5_arabic+en', merged_tokens=added, arabic_text=a_text)
    return line


def read(image):
    from rapidocr.utils.process_img import get_rotate_crop_image
    from rapidocr.ch_ppocr_rec import TextRecInput
    with LOCK:
        h, w = image.shape[:2]
        scale = min(3, max(1, 1100 / max(h, w)))
        work = cv2.resize(cv2.cvtColor(image, cv2.COLOR_RGB2BGR), None,
                          fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        detected = engine()(work, use_rec=False)
        if detected.boxes is None or not len(detected.boxes):
            return []
        crops = [get_rotate_crop_image(work, np.asarray(box, np.float32)) for box in detected.boxes]
        arabic = engine('arabic').text_rec(TextRecInput(img=crops))
        english = engine('en').text_rec(TextRecInput(img=crops))
        lines = []
        for box, a_text, a_score, e_text, e_score in zip(detected.boxes, arabic.txts, arabic.scores, english.txts, english.scores):
            line = merge_readings({'text': a_text, 'confidence': a_score}, {'text': e_text, 'confidence': e_score})
            if line:
                lines.append(dict(line, box=(np.asarray(box) / scale).round(1).tolist()))
        return lines

def recognize_crops(crops, language='arabic'):
    if not crops:
        return []
    from rapidocr.ch_ppocr_rec import TextRecInput
    with LOCK:
        result = engine(language).text_rec(TextRecInput(img=[cv2.cvtColor(c, cv2.COLOR_RGB2BGR) for c in crops]))
        return [{'text': t, 'confidence': round(float(s), 3)} for t, s in zip(result.txts, result.scores)]
