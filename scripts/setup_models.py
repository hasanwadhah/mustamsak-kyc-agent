"""One-time download of pretrained local OCR weights, never user documents."""
from pathlib import Path
import easyocr
root=Path(__file__).resolve().parents[1]
target=root/'models'/'easyocr'
target.mkdir(parents=True,exist_ok=True)
easyocr.Reader(['ar','en'],gpu=False,model_storage_directory=str(target),verbose=False)
print('Arabic + English OCR models installed locally.')
