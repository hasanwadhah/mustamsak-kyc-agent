# Handwritten Arabic-Indic numbers

Some Iraqi documents carry numbers written by hand, in Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩): the housing card's
neighbourhood (mahalla), street and house numbers and its form number. General OCR and general
vision-language models read these poorly. Two small models were trained **in this project** to read them.
Both run in plain numpy, with no GPU and no deep-learning library at run time.

## 1. Digit reader (`app/handwritten_digits.py`, `models/eastern_digits_cnn.npz`)

- A small CNN that classifies one digit (١–٩, or "not a digit"). ٠ is a dot and is found by a size rule.
- Pipeline: pen-ink mask → digit pieces on the dotted guide line → CNN per piece.
- Trained on **MADBase**: public handwritten Arabic-Indic digits from 700 writers (El-Sherif &
  Abdelazeem, 2007; research use with citation). It also uses synthetic Iraqi-style strokes, with 40% of
  the digits drawn under stamp or signature strokes.
- Results on MADBase's held-out writers: **99.1%**, and **93.5%** under stamps and signatures.
- Retrain: `python scripts/train_digit_cnn.py` (about 20 minutes on CPU; MADBase is fetched by
  `scripts/fetch_madbase.py`).

## 2. Whole-number reader (`app/number_reader.py`, `models/number_reader.npz`)

Most errors came from **cutting a number into digits**: a digit split in two, two digits merged, the ٠
dot lost, or a stamp stroke counted as a digit. This model reads the whole number strip at once, with no
cutting.

- **Architecture:** a fully convolutional CRNN (the CNN collapses the height, then three residual 1-D
  convolutions run along the strip) with **CTC**, over 11 symbols (blank + 0–9). 1.0 M parameters.
- **Training data** (generated on the fly by `scripts/number_strips.py`): numbers of 1–6 digits built
  from MADBase handwriting, rescaled to real relative sizes (٠ a dot, ٥ a small loop). The digits are
  drawn on card-like colour backgrounds with dotted guide lines, clipped text from the rows above and
  below, printed marker letters at the edges, stamps and signatures over the digits, faint ink, blur,
  low resolution and JPEG.
- **Held-out check:** strips built from MADBase's *test* writers only, never trained on. **86.8%** of whole
  numbers are read exactly, including the deliberately unreadable strips.
- **Use:** a **third, independent voter**. When it agrees with the value, the field is marked "two readers
  agree". When it sides with a reading that lost, and is sure of every digit (≥ 0.9), that reading wins
  2 to 1 but stays approximate. Otherwise its reading is only a suggestion. It never fills a blank field
  and never touches a manual or verified value.
- **Train from scratch:** `python scripts/train_number_reader.py --steps 10000` (about 2.3 hours on a
  laptop CPU). The new model is installed only if it is no worse on held-out writers. The previous one is
  kept as `number_reader.previous.npz`.

## 3. Learning from corrections

When a reviewer corrects or confirms a handwritten number and saves, the app keeps the evidence on this
computer only, in the git-ignored `data/` folder:
- the digit crops → `data/digit-samples/`;
- the whole-number strip, named by its value → `data/number-strips/`.

The training dashboard in the reviewer workspace (sidebar → «لوحة التدريب») shows these samples. There
you can fix a wrong label or delete a bad sample, evaluate both readers on the kept-aside samples, start
or stop a retrain, and roll back to the previous model.

One sample in five is kept aside and never trained on, so the reported score stays honest. A new model
is installed only if it is no worse on held-out writers and on the kept-aside samples.
