import cv2
import numpy as np
from app import capture, storage


def card(width=800, height=505, background=(214, 226, 218)):
    """A synthetic card with printed-text texture (fictional, no real data)."""
    image = np.zeros((height, width, 3), np.uint8)
    image[:] = background
    rng = np.random.default_rng(3)
    for y in range(40, height - 30, 34):
        x = 30
        while x < width - 60:
            word = int(rng.integers(30, 90))
            cv2.putText(image, 'ABC 123'[: max(1, word // 14)], (x, y), cv2.FONT_HERSHEY_SIMPLEX, .8, (25, 30, 35), 2)
            x += word + 25
    return image


def scene(document, top_left=(200, 170), size=(1400, 1000), desk=48):
    frame = np.full((size[1], size[0], 3), desk, np.uint8)
    x, y = top_left
    h, w = document.shape[:2]
    x2, y2 = min(size[0], x + w), min(size[1], y + h)
    frame[y:y2, x:x2] = document[:y2 - y, :x2 - x]
    return frame


def codes(result):
    return {i['code'] for d in result['documents'] for i in d['issues']}


def test_well_framed_document_needs_no_retake():
    result = capture.check_upload(scene(card()))
    assert result['documents'] and not result['retake'], result


def test_corner_outside_frame_asks_for_retake():
    result = capture.check_upload(scene(card(), top_left=(900, 650)))
    assert result['retake'] and 'cut_off' in codes(result)
    assert 'retake' in result['message_en'] or 'frame' in result['message_en']


def test_blur_dark_and_small_are_explained():
    blurred = cv2.GaussianBlur(card(), (0, 0), 6)
    assert 'blur' in {i['code'] for i in capture.assess(blurred)}
    dark = (card() * .22).astype(np.uint8)
    assert 'too_dark' in {i['code'] for i in capture.assess(dark)}
    small = cv2.resize(card(), (200, 126))
    issues = capture.assess(small)
    assert 'too_small' in {i['code'] for i in issues} and capture.needs_retake(issues)


def test_glare_is_detected_and_located_but_white_paper_is_not_glare():
    image = card(background=(150, 170, 160)).astype(np.float32)
    yy, xx = np.mgrid[:image.shape[0], :image.shape[1]]
    spot = np.exp(-(((xx - 600) / 90) ** 2 + ((yy - 120) / 60) ** 2))
    image = np.clip(image + spot[..., None] * 400, 0, 255).astype(np.uint8)
    glare = next(i for i in capture.assess(image) if i['code'] == 'glare')
    assert 'right' in glare['where'] and 'top' in glare['where']
    paper = card(background=(255, 255, 255))
    assert 'glare' not in {i['code'] for i in capture.assess(paper)}


def test_save_retries_when_windows_holds_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    (tmp_path / 'batches').mkdir()
    original = type(tmp_path).replace
    calls = {'n': 0}

    def flaky(self, target):
        calls['n'] += 1
        if calls['n'] <= 2:
            raise PermissionError(5, 'Access is denied')
        return original(self, target)
    monkeypatch.setattr(type(tmp_path), 'replace', flaky)
    batch = {'id': storage.uid(), 'documents': []}
    storage.save_batch(batch)
    assert storage.get_batch(batch['id']) == batch and calls['n'] == 3
