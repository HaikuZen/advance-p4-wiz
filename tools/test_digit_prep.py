#!/usr/bin/env python3
"""test_digit_prep.py - the AI module's board-side preprocessing (digit_prep.c), on the host.

Compiles template/modules/ai/digit_prep.c with gcc, redraws MNIST test digits the
way the board's pad sees them (240 x 240, a random size and place, strokes about a
finger wide), runs them through digit_prep() and scores the float model on the
result, against the plain MNIST images. A big gap means the preprocessing, not
the model, is losing digits.

  ~/.cache/p4wiz-venv/bin/python tools/test_digit_prep.py [--data DIR] [-n 2000]
(after tools/train_digit_model.py, which leaves digitnet.pth in DIR)
"""
import argparse, ctypes, os, random, subprocess, sys, tempfile
import numpy as np, torch, torch.nn.functional as F
from torchvision import datasets, transforms

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "tools"))
from train_digit_model import DigitNet

PAD = 240   # digit.c's PAD


def build_lib(tmp):
    so = os.path.join(tmp, "digit_prep.so")
    subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-Wall", "-Werror", "-o", so,
                    os.path.join(W, "template", "modules", "ai", "digit_prep.c"), "-lm"], check=True)
    lib = ctypes.CDLL(so)
    lib.digit_prep.restype = ctypes.c_bool
    return lib


def as_drawn(img28, rng):
    """an MNIST digit as a finger would leave it on the pad: binary ink, 120..220 px tall"""
    size = rng.randint(120, 220)
    big = F.interpolate(img28[None], size=(size, size), mode="bilinear", align_corners=False)[0, 0]
    ink = (big > 0.35).numpy().astype(np.uint8) * 255
    pad = np.zeros((PAD, PAD), np.uint8)
    x, y = rng.randint(0, PAD - size), rng.randint(0, PAD - size)
    pad[y:y + size, x:x + size] = ink
    return pad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/.cache/p4wiz-mnist"))
    ap.add_argument("-n", type=int, default=2000)
    a = ap.parse_args()
    model = DigitNet()
    model.load_state_dict(torch.load(os.path.join(a.data, "digitnet.pth")))
    model.eval()
    test = datasets.MNIST(a.data, train=False, transform=transforms.ToTensor())
    rng = random.Random(0)
    with tempfile.TemporaryDirectory() as tmp:
        lib = build_lib(tmp)
        out = (ctypes.c_uint8 * (28 * 28))()
        plain = drawn = empty = 0
        with torch.no_grad():
            for i in range(a.n):
                img, label = test[i]
                plain += model(img[None]).argmax(1).item() == label
                pad = np.ascontiguousarray(as_drawn(img, rng))
                if not lib.digit_prep(pad.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), PAD, PAD, out):
                    empty += 1
                    continue
                x = torch.tensor(np.frombuffer(out, np.uint8).reshape(1, 1, 28, 28) / 255.0, dtype=torch.float32)
                drawn += model(x).argmax(1).item() == label
    print(f"{a.n} MNIST test digits: plain {plain / a.n:.4f}, redrawn on the pad + digit_prep {drawn / a.n:.4f}"
          f"{f', {empty} came out empty' if empty else ''}")
    if drawn / a.n < 0.95:
        sys.exit("FAIL: under 95% through the board's preprocessing")


if __name__ == "__main__":
    main()
