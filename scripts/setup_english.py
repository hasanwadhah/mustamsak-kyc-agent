from pathlib import Path
import easyocr
target=Path(__file__).resolve().parents[1]/'models'/'easyocr'
easyocr.Reader(['en'],gpu=False,model_storage_directory=str(target),detector=False,verbose=False,quantize=False)
print('Specialist English/MRZ model installed.')
