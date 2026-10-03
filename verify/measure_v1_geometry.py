"""Measure the v1 card's fiducial spacing against its own printed ruler.

The calibration app assumes the v1 fiducial centres are MARKER_SPAN_CM = 4.3 cm apart
in both directions and averages the two. This reads the v1 artwork
(reference/ABC_v1_stickermule.png) and reports what its own 0-5 cm ruler says.
Valid only if the printed sticker matches the artwork; confirm on a real photo.
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as nd

p = Path(__file__).resolve().parent.parent / "reference" / "ABC_v1_stickermule.png"
im = Image.open(p).convert("RGBA")
bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
rgb = np.asarray(bg.convert("RGB")).astype(int)
black = rgb.max(2) < 110

# ruler: the scan line crossing every 1 mm tick has 51 tick runs (0..50 mm)
best = None
for y in range(rgb.shape[0] // 2):
    xs = np.where(black[y])[0]
    runs = np.split(xs, np.where(np.diff(xs) > 1)[0] + 1) if len(xs) else []
    if len(runs) == 51:
        best = [r.mean() for r in runs]; break
assert best, "ruler not found"
px_per_cm = (best[-1] - best[0]) / 5

# fiducials: the four ~square solid blobs after hole filling
lab, n = nd.label(nd.binary_fill_holes(black))
cents = []
for sl in nd.find_objects(lab):
    h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
    if 40 < h < 120 and 0.85 < h / w < 1.18:
        cents.append(((sl[1].start + sl[1].stop - 1) / 2, (sl[0].start + sl[0].stop - 1) / 2))
assert len(cents) == 4, cents
xs, ys = sorted(c[0] for c in cents), sorted(c[1] for c in cents)
span_x = ((xs[2] + xs[3]) - (xs[0] + xs[1])) / 2 / px_per_cm
span_y = ((ys[2] + ys[3]) - (ys[0] + ys[1])) / 2 / px_per_cm
avg = (span_x + span_y) / 2
print(f"ruler: {px_per_cm:.1f} px/cm (0 cm at x={best[0]:.1f}, 5 cm at x={best[-1]:.1f})")
print(f"fiducial-centre span: x {span_x:.2f} cm, y {span_y:.2f} cm (mean {avg:.2f} cm)")
print(f"app assumes 4.30 cm for both -> scale error {100 * (avg / 4.3 - 1):+.1f}% (lengths reported {100 * (4.3 / avg - 1):+.1f}%)")
