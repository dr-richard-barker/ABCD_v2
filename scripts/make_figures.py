#!/usr/bin/env python3
"""Figures for the site and deck (written to figures/).

  card_anatomy.png   ABCD v2 preview with numbered callouts for each feature
  versions_to_scale.png  v1, v1.5 draft and v2 drawn at the same px/cm

Scales are measured from each artwork's own ruler (not assumed):
  v1   reference/ABC_v1_stickermule.png  ruler 0 cm at x=63.0, 5 cm at x=534.5  -> 94.3 px/cm
  v1.5 reference/ABCD_v1.5.png           ruler 0 cm at x=172.5, 10 cm at x=849.5 -> 67.7 px/cm
  v2   card/abcd_v2_preview.png          300 dpi                                 -> 118.1 px/cm
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
FIG = REPO / "figures"
FIG.mkdir(exist_ok=True)
K = 300 / 25.4  # v2 preview px per mm


def font(px, bold=False):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", px, index=1 if bold else 0)
    except OSError:
        return ImageFont.load_default()


def flatten(path):
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


# --- card anatomy -------------------------------------------------------------
spec = json.loads((REPO / "card" / "abcd_v2_chips.json").read_text())
g = spec["geometry"]
card = flatten(REPO / "card" / "abcd_v2_preview.png")
pad_r = 760
W, H = card.width + pad_r + 60, card.height + 80
im = Image.new("RGB", (W, H), "white")
im.paste(card, (40, 40))
d = ImageDraw.Draw(im)
P = lambda x, y: (40 + x * K, 40 + y * K)  # noqa: E731  mm -> figure px

chips = spec["chips"]
grid = [c for c in chips if c["group"] != "neutral ramp"]
ramp = [c for c in chips if c["group"] == "neutral ramp"]
x0 = min(c["x_mm"] for c in grid); x1 = max(c["x_mm"] + c["size_mm"][0] for c in grid)
row_y = lambda r: (min(c["y_mm"] for c in grid if c["row"] == r), max(c["y_mm"] + c["size_mm"][1] for c in grid if c["row"] == r))  # noqa: E731
fc = g["fiducial_centres_mm"]; fe = g["fiducial_edge_mm"]
callouts = [
    ("Corner markers: ArUco DICT_4X4_50 IDs 0-3 (v1 used 46-49)", [(fc[k][0] - fe / 2, fc[k][1] - fe / 2, fc[k][0] + fe / 2, fc[k][1] + fe / 2) for k in fc]),
    ("Ruler 0-10 cm, 1 mm ticks", [(g["ruler_h"]["origin_mm"][0] - 1, 3, g["ruler_h"]["origin_mm"][0] + 101, 17)]),
    ("Vertical ruler 0-5 cm (checks x/y scale)", [(2, 19, 15, 72)]),
    ("Row A - calibration: white, black, 8 hues", [(x0, *row_y(1))[0:1] + (row_y(1)[0], x1, row_y(1)[1])]),
    ("Rows B-C - plant tissue (20 chips)", [(x0, row_y(2)[0], x1, row_y(3)[1])]),
    ("Rows D-E - soil, Munsell soil-book chips (20)", [(x0, row_y(4)[0], x1, row_y(5)[1])]),
    ("Neutral ramp N9.5 -> N1.5 (12 steps)", [(ramp[0]["x_mm"], ramp[0]["y_mm"], ramp[-1]["x_mm"] + ramp[-1]["size_mm"][0], ramp[0]["y_mm"] + ramp[0]["size_mm"][1])]),
    ("5 mm checker: distortion, focus, scale", [(g["checker"]["origin_mm"][0], g["checker"]["origin_mm"][1], g["checker"]["origin_mm"][0] + 15, g["checker"]["origin_mm"][1] + 50)]),
    ("Version + batch code (3 + 5 bits)", [(g["id_code"]["origin_mm"][0] - 0.5, g["id_code"]["origin_mm"][1] - 0.5, g["id_code"]["origin_mm"][0] + 20.5, g["id_code"]["origin_mm"][1] + 3)]),
]
COL = (220, 40, 120)
f_num, f_txt = font(30, True), font(27)
lx = card.width + 70
for i, (text, boxes) in enumerate(callouts, 1):
    for (a, b, c, e) in boxes:
        d.rectangle([P(a, b), P(c, e)], outline=COL, width=4)
    bx, by = P(boxes[0][0], boxes[0][1])
    d.ellipse([bx - 20, by - 20, bx + 20, by + 20], fill=COL)
    d.text((bx, by), str(i), fill="white", font=f_num, anchor="mm")
    ty = 70 + (i - 1) * 108
    d.ellipse([lx, ty, lx + 40, ty + 40], fill=COL)
    d.text((lx + 20, ty + 20), str(i), fill="white", font=f_num, anchor="mm")
    words, line, lines = text.split(" "), "", []
    for w_ in words:
        if d.textlength(line + " " + w_, font=f_txt) > pad_r - 90:
            lines.append(line); line = w_
        else:
            line = (line + " " + w_).strip()
    lines.append(line)
    for j, ln in enumerate(lines):
        d.text((lx + 56, ty + 4 + j * 32), ln, fill=(30, 30, 30), font=f_txt)
im.save(FIG / "card_anatomy.png")

# --- versions to scale ----------------------------------------------------------
target = 40.0  # px per cm in the figure
v1 = flatten(REPO / "reference" / "ABC_v1_stickermule.png")
v15 = flatten(REPO / "reference" / "ABCD_v1.5.png")
v2 = card
items = [("v1 (StickerMule, 5 cm ruler)", v1, 94.3), ("v1.5 draft (10 cm ruler)", v15, 67.7), ("v2 (140 x 90 mm)", v2, K * 10)]
scaled = [(t, i.resize((round(i.width * target / s), round(i.height * target / s)), Image.LANCZOS)) for t, i, s in items]
gap, top = 50, 70
tf = font(26, True)
meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))
colw = [max(i.width, round(meas.textlength(t, font=tf))) for t, i in scaled]  # column fits its title
W = sum(colw) + gap * (len(scaled) + 1)
H = max(i.height for _, i in scaled) + top + 90
im = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(im)
x = gap
for (t, i), cw in zip(scaled, colw):
    im.paste(i, (x, top + (H - top - 90 - i.height)))
    d.text((x, 20), t, fill=(30, 30, 30), font=tf)
    x += cw + gap
# 5 cm scale bar
d.rectangle([gap, H - 50, gap + 5 * target, H - 40], fill="black")
d.text((gap + 5 * target + 12, H - 45), "5 cm (all three drawn at the same scale, from each card's own ruler)", fill=(60, 60, 60), font=font(22), anchor="lm")
im.save(FIG / "versions_to_scale.png")
print("wrote", FIG / "card_anatomy.png", FIG / "versions_to_scale.png")
