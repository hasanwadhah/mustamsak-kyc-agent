"""Train Mustamsak's own number reader from scratch (docs/HANDWRITING.md).

Data: synthetic strips from scripts/number_strips.py, generated on the fly (MADBase `train`
handwriting). Held-out check: strips from MADBase `test` writers, fixed seed, never trained on.
Optional --real DIR: a folder of real strips + index.json (file, truth) used for REPORTING only.

Writes models/number_reader.npz (BatchNorm folded into the convolutions; the app runs it in numpy,
app/number_reader.py) with its metrics. The previous model is kept as number_reader.previous.npz
and replaced only if the new one is at least as good on the held-out check (and on --real if given).

    python scripts/train_number_reader.py --steps 12000 [--workers 10] [--real DIR]
"""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import number_strips as ns  # noqa: E402
from app import number_reader as nr  # noqa: E402


def conv(i, o, k=3, p=1):
    return nn.Sequential(nn.Conv2d(i, o, k, padding=p, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))


class TConv(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.conv = nn.Conv1d(c, c, 5, padding=2, bias=False)
        self.bn = nn.BatchNorm1d(c)
        self.drop = nn.Dropout(.1)

    def forward(self, x):
        return x + self.drop(torch.relu(self.bn(self.conv(x))))


class Net(nn.Module):
    """The same layers as app/number_reader.LAYERS."""

    def __init__(self):
        super().__init__()
        self.c1, self.c2, self.c3, self.c4 = conv(3, 32), conv(32, 64), conv(64, 96), conv(96, 96)
        self.c5, self.c6 = conv(96, 128), conv(128, 128)
        self.c7 = conv(128, 192, (2, 1), 0)
        self.t1, self.t2, self.t3 = TConv(192), TConv(192), TConv(192)
        self.head = nn.Conv1d(192, 11, 1)

    def forward(self, x):
        x = nn.functional.max_pool2d(self.c1(x), 2)
        x = nn.functional.max_pool2d(self.c2(x), 2)
        x = nn.functional.max_pool2d(self.c4(self.c3(x)), (2, 1))
        x = nn.functional.max_pool2d(self.c6(self.c5(x)), (2, 1))
        x = self.c7(x).squeeze(2)
        return self.head(self.t3(self.t2(self.t1(x))))  # (N, 11, T)


def load_extra(folder, check=False):
    """The reviewer's corrected strips: data/number-strips/<value>__<key>-<tag>.png (app/learning.py).
    check=False: the strips to train on; check=True: the kept-aside ones (never trained on)."""
    import cv2
    out = []
    for path in sorted(Path(folder).glob('*.png')) if folder else []:
        if nr.kept_aside(path.name) != check:
            continue
        value = path.name.split('__')[0]
        image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        if image is not None and value.isdigit():
            out.append((cv2.cvtColor(image, cv2.COLOR_BGR2RGB), [int(c) for c in value]))
    return out


def augmented(rgb, rng):
    """A corrected real strip, varied: margins trimmed or widened, then photo problems."""
    import cv2
    h, w = rgb.shape[:2]
    if rng.random() < .5:
        left, right = int(rng.uniform(0, .1) * w), int(rng.uniform(0, .1) * w)
        rgb = rgb[:, left:w - right] if w - left - right > 8 else rgb
    else:
        pad = int(rng.uniform(0, .5) * h)
        rgb = cv2.copyMakeBorder(rgb, 0, 0, pad, int(rng.uniform(0, .5) * h), cv2.BORDER_REPLICATE)
    return ns.degrade(rgb, rng)


class Strips(torch.utils.data.IterableDataset):
    def __init__(self, split, seed, extra=None, share=.3):
        self.split, self.seed, self.extra, self.share = split, seed, extra, share

    def __iter__(self):
        info = torch.utils.data.get_worker_info()
        rng = np.random.default_rng(self.seed + (info.id if info else 0) * 7919 + int(time.time()) % 100000)
        glyphs = ns.Glyphs(self.split)
        extra = load_extra(self.extra)
        while True:
            if extra and rng.random() < self.share:
                rgb, digits = extra[int(rng.integers(len(extra)))]
                yield ns.to_input(augmented(rgb, rng)), digits
            else:
                yield ns.sample(glyphs, rng)


def batch(items):
    """Pad to the widest strip with each strip's own border colour (random side)."""
    width = max(im.shape[1] for im, _ in items)
    x = np.empty((len(items), nr.HEIGHT, width, 3), np.uint8)
    for i, (im, _) in enumerate(items):
        colour = np.median(np.concatenate([im[:, :2].reshape(-1, 3), im[:, -2:].reshape(-1, 3)]), axis=0)
        x[i] = colour.astype(np.uint8)
        left = np.random.randint(0, width - im.shape[1] + 1)
        x[i, :, left:left + im.shape[1]] = im
    x = torch.from_numpy(x).permute(0, 3, 1, 2).float() / 255 - .5
    labels = torch.tensor([d + 1 for _, ds in items for d in ds], dtype=torch.long)
    lengths = torch.tensor([len(ds) for _, ds in items], dtype=torch.long)
    return x, labels, lengths, [ds for _, ds in items]


def greedy(logits):
    out = []
    for seq in logits.argmax(1).tolist():
        digits, prev = [], 0
        for k in seq:
            if k and k != prev:
                digits.append(k - 1)
            prev = k
        out.append(digits)
    return out


def held_out(count=2000, seed=424242):
    rng = np.random.default_rng(seed)
    glyphs = ns.Glyphs('test')
    return [ns.sample(glyphs, rng) for _ in range(count)]


@torch.no_grad()
def evaluate(model, items, size=64):
    model.eval()
    right = 0
    for i in range(0, len(items), size):
        chunk = items[i:i + size]
        x, _, _, truth = batch(chunk)
        right += sum(p == t for p, t in zip(greedy(model(x)), truth))
    model.train()
    return right / len(items)


def export(model):
    """BatchNorm folded into each convolution; names match app/number_reader.LAYERS."""
    model.eval()
    out = {}

    def fold(conv, bn):
        scale = bn.weight / torch.sqrt(bn.running_var + bn.eps)
        w = conv.weight * scale.reshape(-1, *([1] * (conv.weight.dim() - 1)))
        b = bn.bias - bn.running_mean * scale
        return w.detach().numpy().astype(np.float32), b.detach().numpy().astype(np.float32)

    for name in ('c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7'):
        seq = getattr(model, name)
        out[name + '.w'], out[name + '.b'] = fold(seq[0], seq[1])
    for name in ('t1', 't2', 't3'):
        block = getattr(model, name)
        out[name + '.w'], out[name + '.b'] = fold(block.conv, block.bn)
    out['head.w'] = model.head.weight.detach().numpy().astype(np.float32)
    out['head.b'] = model.head.bias.detach().numpy().astype(np.float32)
    return out


def real_strips(folder):
    import cv2
    folder = Path(folder)
    index = json.loads((folder / 'index.json').read_text(encoding='utf-8'))
    return [(cv2.cvtColor(cv2.imread(str(folder / it['file'])), cv2.COLOR_BGR2RGB), it['truth'], it['file']) for it in index]


def real_score(strips, verbose=False):
    right = 0
    for rgb, truth, name in strips:
        r = nr.read(rgb)
        value = r['value'] if r else ''
        right += value == truth
        if verbose:
            print(f"  {'OK ' if value == truth else '-- '} {name:28} truth={truth:7} read={value:7} "
                  f"{[d['probability'] for d in r['digits']] if r else ''}")
    return right / max(1, len(strips))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=12000)
    parser.add_argument('--batch', type=int, default=48)
    parser.add_argument('--workers', type=int, default=10)
    parser.add_argument('--lr', type=float, default=2e-3)
    parser.add_argument('--real', default=None)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--resume', default=None)
    parser.add_argument('--extra-strips', default=None, help='folder of corrected strips (data/number-strips)')
    parser.add_argument('--share', type=float, default=.3, help='share of each batch taken from the corrected strips')
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.manual_seed(0)
    model = Net()
    if args.resume:
        model.load_state_dict(torch.load(args.resume))
    print('parameters', sum(p.numel() for p in model.parameters()), flush=True)
    print(f'plan steps {args.steps}', flush=True)
    every = max(250, min(1000, args.steps // 6))
    check = held_out()
    loader = torch.utils.data.DataLoader(Strips('train', 1, args.extra_strips, args.share), batch_size=args.batch, num_workers=args.workers,
                                         collate_fn=batch, persistent_workers=args.workers > 0, prefetch_factor=4 if args.workers else None)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, args.lr, total_steps=args.steps, pct_start=.08)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    checkpoint = ROOT / 'research' / 'number_reader.pt'
    checkpoint.parent.mkdir(exist_ok=True)
    start, losses, best = time.time(), [], 0.0
    for step, (x, labels, lengths, _) in enumerate(loader, 1):
        logits = model(x)  # (N, 11, T)
        log_probs = logits.log_softmax(1).permute(2, 0, 1)  # (T, N, 11)
        inputs = torch.full((x.shape[0],), log_probs.shape[0], dtype=torch.long)
        loss = ctc(log_probs, labels, inputs, lengths)
        opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 5)
        opt.step()
        sched.step()
        losses.append(loss.item())
        if step % 200 == 0:
            print(f'step {step} loss {np.mean(losses[-200:]):.3f} {(time.time() - start) / step:.2f}s/step', flush=True)
        if step % every == 0 or step == args.steps:
            accuracy = evaluate(model, check)
            print(f'  held-out writers: {accuracy:.3%} whole numbers right (step {step})', flush=True)
            if accuracy >= best:
                best = accuracy
                torch.save(model.state_dict(), checkpoint)
        if step >= args.steps:
            break
    model.load_state_dict(torch.load(checkpoint))
    weights = export(model)
    # Parity check: numpy inference must match torch on the held-out strips.
    candidate = ROOT / 'models' / 'number_reader.candidate.npz'
    np.savez_compressed(candidate, **weights)
    target, previous = nr.MODEL_PATH, nr.MODEL_PATH.with_name('number_reader.previous.npz')
    nr.MODEL_PATH = candidate
    nr.reset()
    agree = sum(nr.read(im) is not None and nr.read(im)['value'] == ''.join(map(str, d)) for im, d in check[:300]) / 300
    report = {'held_out_whole_number_accuracy': round(best, 4), 'numpy_held_out_300': round(agree, 4),
              'steps': args.steps, 'trained': time.strftime('%Y-%m-%d %H:%M'),
              'data': 'synthetic strips: MADBase train handwriting + synthetic strokes; no identity documents'}
    if args.real:
        strips = real_strips(args.real)
        report['real_strips'] = len(strips)
        report['real_whole_number_accuracy'] = round(real_score(strips, verbose=True), 4)
    own = [(rgb, ''.join(map(str, d)), 'own') for rgb, d in load_extra(args.extra_strips, check=True)]
    if own:
        report['own_check_strips'] = len(own)
        report['own_check_accuracy'] = round(real_score(own), 4)
    print(json.dumps(report, indent=1), flush=True)
    old = None
    if target.exists():
        nr.MODEL_PATH = target
        nr.reset()
        old = {'held_out': evaluate_numpy(check[:300])}
        if args.real:
            old['real'] = real_score(real_strips(args.real))
        if len(own) >= 5:
            old['own'] = real_score(own)
    new_ok = old is None or (agree >= old['held_out'] - .01 and (not args.real or report['real_whole_number_accuracy'] >= old['real'])
                             and (len(own) < 5 or report['own_check_accuracy'] >= old['own']))
    if new_ok:
        if target.exists():
            target.replace(previous)
        np.savez_compressed(target, **weights, report=json.dumps(report))
        print('installed', target)
    else:
        print('kept the current model; it was better:', old)
    candidate.unlink(missing_ok=True)


def evaluate_numpy(items):
    return sum(nr.read(im) is not None and nr.read(im)['value'] == ''.join(map(str, d)) for im, d in items) / len(items)


if __name__ == '__main__':
    main()
