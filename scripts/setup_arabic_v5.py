"""Download only public pretrained models; never uploads document images."""
from pathlib import Path
import hashlib
import httpx
import yaml
import rapidocr

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'models' / 'ppocr'

def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    catalog = yaml.safe_load((Path(rapidocr.__file__).parent / 'default_models.yaml').read_text())['onnxruntime']
    choices = [('PP-OCRv5', 'det', 'ch_PP-OCRv5_det_mobile'),
               ('PP-OCRv5', 'rec', 'arabic_PP-OCRv5_rec_mobile'),
               ('PP-OCRv5', 'rec', 'en_PP-OCRv5_rec_mobile'),
               ('PP-OCRv4', 'cls', 'ch_ppocr_mobile_v2.0_cls_mobile')]
    # Use the package's exact orientation-model key (versioned upstream manifest).
    choices[-1] = ('PP-OCRv4', 'cls', next(iter(catalog['PP-OCRv4']['cls'])))
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for version, task, name in choices:
            spec = catalog[version][task][name]
            path = TARGET / (name + '.onnx')
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == spec['SHA256']:
                print('Ready:', name, flush=True)
                continue
            print('Downloading:', name, flush=True)
            data = client.get(spec['model_dir']).raise_for_status().content
            if hashlib.sha256(data).hexdigest() != spec['SHA256']:
                raise RuntimeError('Model checksum mismatch: ' + name)
            path.write_bytes(data)
            print('Verified:', name, len(data), flush=True)

if __name__ == '__main__':
    main()
