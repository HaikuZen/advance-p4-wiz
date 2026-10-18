#!/usr/bin/env python3
"""train_digit_model.py - train the AI module's handwritten-digit CNN and export it for
ESP-DL (int8, ESP32-P4): template/modules/ai/models/digit.espdl.

  uv venv -p 3.12 ~/.cache/p4wiz-venv
  VIRTUAL_ENV=~/.cache/p4wiz-venv uv pip install -r tools/requirements-ai.txt \
      --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
  ~/.cache/p4wiz-venv/bin/python tools/train_digit_model.py [--data DIR] [--epochs N]

MNIST is pen on paper, the board gets a finger on glass: thicker, wobblier strokes.
The training data is augmented toward that (random stroke dilation, rotation, scale,
shear), and the board feeds the model MNIST-style input: the ink cropped, scaled into
a 20x20 box and centred by mass in 28x28 (main/digit_prep.c).

One input channel, so the NCHW (torch) and NHWC (ESP-DL) layouts are the same bytes:
the board writes the 28x28 image row by row.
"""
import argparse, os, random
import torch, torch.nn as nn, torch.nn.functional as F
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(W, "template", "modules", "ai", "models", "digit.espdl")


class DigitNet(nn.Module):
    """3 conv + 1 dense, ~27k parameters: well under a millisecond's worth of P4"""
    def __init__(self):
        super().__init__()
        self.c1 = nn.Conv2d(1, 16, 3, padding=1)    # 28 -> pool 14
        self.c2 = nn.Conv2d(16, 32, 3, padding=1)   # 14 -> pool 7
        self.c3 = nn.Conv2d(32, 32, 3)              # 7 -> 5 -> pool 2
        self.fc = nn.Linear(32 * 2 * 2, 10)

    def forward(self, x):
        x = F.max_pool2d(F.relu(self.c1(x)), 2)
        x = F.max_pool2d(F.relu(self.c2(x)), 2)
        x = F.max_pool2d(F.relu(self.c3(x)), 2)
        return self.fc(torch.flatten(x, 1))         # logits; the board takes the softmax


class Thicken:
    """a finger draws fatter than a pen: dilate the strokes, sometimes twice"""
    def __call__(self, x):
        for _ in range(random.choice((0, 1, 1, 2))):
            x = F.max_pool2d(x.unsqueeze(0), 3, 1, 1).squeeze(0)
        return x


def accuracy(fn, loader):
    ok = n = 0
    with torch.no_grad():
        for x, y in loader:
            ok += (fn(x).argmax(1) == y).sum().item(); n += len(y)
    return ok / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/.cache/p4wiz-mnist"), help="MNIST download dir")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    torch.manual_seed(0); random.seed(0)

    aug = transforms.Compose([
        transforms.ToTensor(),
        transforms.RandomAffine(degrees=12, translate=(0.06, 0.06), scale=(0.85, 1.1), shear=10),
        Thicken(),
    ])
    train = datasets.MNIST(a.data, train=True, download=True, transform=aug)
    test = datasets.MNIST(a.data, train=False, download=True, transform=transforms.ToTensor())
    test_thick = datasets.MNIST(a.data, train=False, transform=transforms.Compose([transforms.ToTensor(), Thicken()]))
    tl = DataLoader(train, batch_size=128, shuffle=True, num_workers=2)
    vl = DataLoader(test, batch_size=500)
    vl_thick = DataLoader(test_thick, batch_size=500)

    model = DigitNet()
    opt = torch.optim.Adam(model.parameters(), 2e-3)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 4e-3, total_steps=a.epochs * len(tl))
    for ep in range(a.epochs):
        model.train()
        for x, y in tl:
            opt.zero_grad(); F.cross_entropy(model(x), y).backward(); opt.step(); sched.step()
        model.eval()
        print(f"epoch {ep + 1}: test {accuracy(model, vl):.4f}, thickened {accuracy(model, vl_thick):.4f}")
    torch.save(model.state_dict(), os.path.join(a.data, "digitnet.pth"))

    # int8 for the P4. Calibration batches must not be shuffled (esp-ppq walks them repeatedly)
    from esp_ppq.api import espdl_quantize_torch
    from esp_ppq.executor.torch import TorchExecutor
    calib = DataLoader(Subset(train, range(2048)), batch_size=32, shuffle=False)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    graph = espdl_quantize_torch(
        model=model, espdl_export_file=a.out, calib_dataloader=calib, calib_steps=64,
        input_shape=[1, 1, 28, 28], target="esp32p4", quant_type="w8a8",
        collate_fn=lambda b: b[0], device="cpu", error_report=False,
        export_test_values=False, verbose=0)
    ex = TorchExecutor(graph=graph, device="cpu")
    one = DataLoader(test, batch_size=1)   # the graph was exported for batch 1
    q = lambda x: ex(x)[0]
    print(f"int8 model: test {accuracy(q, first(one, 2000)):.4f} (first 2000)")
    for ext in (".info", ".json", ".onnx"):   # esp-ppq's side files: not needed on the board
        p = os.path.splitext(a.out)[0] + ext
        if os.path.exists(p):
            os.remove(p)
    print(f"wrote {a.out} ({os.path.getsize(a.out)} bytes)")


def first(loader, n):
    """the first n batches of a loader"""
    for i, b in enumerate(loader):
        if i == n:
            return
        yield b


if __name__ == "__main__":
    main()
