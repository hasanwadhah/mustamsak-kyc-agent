"""Manual labelling loop for the digit reader: export digit ink, label by folder, learn from it."""
import importlib.util
from pathlib import Path

import cv2
import numpy as np

from app import handwritten_digits as hd
from test_housing_digits import needs_model, written

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@needs_model
def test_collector_sees_each_digit_only_while_switched_on():
    hd.collector = []
    try:
        hd.read_digits(mask=written('42'), pen_width=6)
        seen = [p['digit'] for p in hd.collector]
    finally:
        hd.collector = None
    assert seen == [4, 2]
    assert hd.read_digits(mask=written('42'), pen_width=6)['value'] == '42'  # off again: nothing collected, same reading


@needs_model
def test_export_writes_black_on_white_ink_sorted_by_the_models_reading(monkeypatch, tmp_path):
    exporter = script('export_digit_samples')
    monkeypatch.setattr(exporter, 'housing_regions', lambda image, lines, side: [])
    monkeypatch.setattr(exporter, 'digit_model_readings', lambda image, regions, lines: hd.read_digits(mask=written('15'), pen_width=6))
    assert exporter.export('card', None, [], tmp_path) == 2 and hd.collector is None
    files = sorted(tmp_path.glob('*/*.png'))
    assert [f.parent.name for f in files] == ['1', '5']
    image = cv2.imdecode(np.fromfile(str(files[0]), np.uint8), cv2.IMREAD_GRAYSCALE)
    assert image.mean() > 127 and set(np.unique(image)) <= {0, 255}


def test_own_samples_keep_every_fifth_aside_and_read_ink_back_exactly(tmp_path):
    trainer = script('train_digit_cnn')
    ink = written('4')
    ys, xs = np.nonzero(ink)
    ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    (tmp_path / '4').mkdir()
    (tmp_path / 'noise').mkdir()
    for i in range(5):
        cv2.imencode('.png', 255 - ink)[1].tofile(str(tmp_path / '4' / f'{i}.png'))
    cv2.imencode('.png', 255 - ink[:10])[1].tofile(str(tmp_path / 'noise' / 'scrap.png'))
    samples = trainer.own_samples(tmp_path)
    assert [(label, aside) for _, label, aside in samples] == [(3, False)] * 4 + [(3, True), (9, False)]
    assert np.array_equal(samples[0][0], ink)
    (X, y), (Xc, yc) = trainer.own_images(samples, repeat=3, seed=1, overlap=.5)
    assert X.shape == (15, 1, 28, 28) and list(yc) == [3] and Xc.shape == (1, 1, 28, 28)
    assert 0 <= X.min() and X.max() <= 1
