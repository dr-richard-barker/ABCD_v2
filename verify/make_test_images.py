"""Render synthetic 'photos' of a card for detect.ts: flat, mild/strong perspective,
15 deg and 180 deg rotation, each plain and with a warm colour cast + noise + blur.

Usage: python make_test_images.py <card.png> <tag> <out-dir>
  Expected fiducial centres default to ABCD v2 (mm -> 300 dpi px). For another card
  set FPX to a JSON list of 4 [x,y] px centres (TL,TR,BR,BL, after SCALE). v1:
  SCALE=2.75 FPX='[[233.75,237.875],[1416.25,237.875],[1414.875,1193.5],[233.75,1193.5]]'
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

src, tag, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
card = Image.open(src).convert("RGBA")
white = Image.new("RGBA", card.size, (255, 255, 255, 255))
white.alpha_composite(card)
card = white.convert("RGB")  # transparent margins -> white, like a printed sticker
sc = float(os.environ.get("SCALE", "1"))
if sc != 1:
    card = card.resize((round(card.width * sc), round(card.height * sc)), Image.LANCZOS)
w, h = card.size
W, H = 2400, 1800
k = 300 / 25.4
F = json.loads(os.environ["FPX"]) if "FPX" in os.environ else \
    [(x * k, y * k) for x, y in [(10.5, 10.5), (129.5, 10.5), (129.5, 79.5), (10.5, 79.5)]]


def homography(pa, pb):
    A = []
    for p1, p2 in zip(pa, pb):
        A.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
        A.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
    return np.linalg.solve(np.array(A, float), np.array(pb, float).reshape(8)).tolist()


def rotated(deg):
    cx, cy, t = W / 2, H / 2, math.radians(deg)
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return [(cx + x * math.cos(t) - y * math.sin(t), cy + x * math.sin(t) + y * math.cos(t)) for x, y in pts]


x0, y0 = (W - w) / 2, (H - h) / 2
cases = {
    "flat": [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)],
    "persp_mild": [(450, 400), (1950, 330), (1990, 1330), (420, 1420)],
    "persp_strong": [(520, 380), (1950, 250), (2050, 1350), (400, 1500)],
    "rot15": rotated(15),
    "rot180": rotated(180),
}
names = []
rect = [(0, 0), (w, 0), (w, h), (0, h)]
for name, dst in cases.items():
    a, b, c, d, e, f, g, hh = homography(rect, dst)  # card px -> photo px
    expected = [((a * x + b * y + c) / (g * x + hh * y + 1), (d * x + e * y + f) / (g * x + hh * y + 1)) for x, y in F]
    base = card.transform((W, H), Image.PERSPECTIVE, homography(dst, rect), Image.BICUBIC, fillcolor=(70, 90, 60))
    for fx in ("plain", "cast_blur"):
        im = base
        if fx == "cast_blur":
            arr = np.asarray(im).astype(float) * np.array([1.08, 0.97, 0.82])
            arr += np.random.default_rng(0).normal(0, 4, arr.shape)
            im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
        n = f"{tag}{name}_{fx}"
        names.append(n)
        np.asarray(im.convert("RGBA")).tofile(f"{out}/{n}.rgba")
        json.dump({"w": W, "h": H, "expected": expected}, open(f"{out}/{n}.json", "w"))
json.dump(names, open(f"{out}/{tag}names.json", "w"))
print(f"wrote {len(names)} test images to {out}")
