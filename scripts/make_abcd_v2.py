#!/usr/bin/env python3
"""Generate the ABCD v2 calibration card: artwork (SVG/PDF/PNG) + chip spec.

Every chip is defined by a Munsell notation. Colours are computed from the
Munsell renotation data (colour-science, Illuminant C) and adapted (Bradford) to
D50 for print / D65 for sRGB. Each chip is round-tripped through a CMYK press
profile; chips that fall out of gamut (dE2000 > GAMUT_DE) have their chroma
reduced on the same hue page until they fit, and the swap is logged.

Notations come only from pages that exist:
  * soil chips  - the six hue diagrams in the Munsell Soil-Color Charts scan
                  (10R, 2.5YR, 5YR, 7.5YR, 10YR, 2.5Y; soils.uga.edu Munsell.pdf),
                  using the chip and colour name printed on that diagram.
  * plant chips - hues from the 17 pages of the Munsell Plant Tissue Color Book
                  (2.5R 5R 10R 2.5YR 5YR 7.5YR 2.5Y 5Y 2.5GY 5GY 7.5GY 2.5G 5G
                  7.5G 5BG 2.5B 5RP). Value/chroma are design targets, not
                  confirmed chips on those pages.

Usage:  python make_abcd_v2.py [--batch N] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import colour  # noqa: E402
from PIL import Image, ImageCms, ImageDraw, ImageFont  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CMYK_PROFILE = "/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc"
GAMUT_DE = 3.0

# --- card geometry (mm) -------------------------------------------------------
CARD_W, CARD_H = 140.0, 90.0
BLEED = 3.0
FID = 16.0            # fiducial edge (6x6 cells)
FID_INSET = 2.5       # cut edge -> fiducial edge
CHIP = 9.0
GUTTER = 1.0
COLS, ROWS = 10, 5
CHIP_X0, CHIP_Y0 = 20.5, 19.5
RULER_X0, RULER_LEN = 20.0, 100.0   # 0..10 cm, horizontal
VRULER_Y0, VRULER_LEN = 20.0, 50.0  # 0..5 cm, vertical (left column)
CHECK = 5.0                          # checker pitch
CHECK_X0, CHECK_Y0, CHECK_NX, CHECK_NY = 121.5, 20.0, 3, 10
RAMP_Y0, RAMP_H = 70.0, 7.5
DPI = 300

# Corner fiducials are standard ArUco markers from OpenCV's DICT_4X4_50
# (6x6 cells: black border + 4x4 code; '#' = black, as printed, unrotated).
# v1 used IDs 46-49 (BL, TL, TR, BR). v2 uses IDs 0-3 so any ArUco reader can
# tell the two cards apart by ID alone. IDs 0-3 differ from every v1 marker by
# >= 5 of 16 bits and from their own rotations by 8 bits. Bit grids were taken
# from cv2.aruco.generateImageMarker; verify/check_aruco_ids.py re-checks them.
ARUCO_DICT = "DICT_4X4_50"
FIDUCIAL_IDS = {"TL": 0, "TR": 1, "BR": 2, "BL": 3}
V1_FIDUCIAL_IDS = {"TL": 47, "TR": 48, "BR": 49, "BL": 46}
FIDUCIALS = {
    "TL": ["######", "#.#..#", "##.#.#", "###..#", "###.##", "######"],  # id 0
    "TR": ["######", "######", "#....#", "#.##.#", "#.#.##", "######"],  # id 1
    "BR": ["######", "###..#", "###..#", "###.##", "#..#.#", "######"],  # id 2
    "BL": ["######", "#.##.#", "#.##.#", "##.###", "##..##", "######"],  # id 3
}
V1_FIDUCIALS = {  # as printed on v1 (reference/ABC_v1_stickermule.png)
    "TL": ["######", "##.###", "#.#..#", "##..##", "##.###", "######"],  # id 47
    "TR": ["######", "##.#.#", "######", "###.##", "#...##", "######"],  # id 48
    "BR": ["######", "##.#.#", "######", "####.#", "###..#", "######"],  # id 49
    "BL": ["######", "###.##", "#..#.#", "###..#", "#....#", "######"],  # id 46
}

# --- chip definitions ---------------------------------------------------------
# (group, munsell, label)
CAL = [
    ("calibration", "N9.5", "white anchor"),
    ("calibration", "5R 4/12", "red"),
    ("calibration", "5YR 6/12", "orange"),
    ("calibration", "5Y 8/12", "yellow"),
    ("calibration", "2.5G 5/10", "green"),
    ("calibration", "5B 5/8", "cyan"),
    ("calibration", "7.5PB 3/12", "blue"),
    ("calibration", "5P 3/10", "purple"),
    ("calibration", "2.5RP 5/12", "magenta"),
    ("calibration", "N2", "black anchor"),
]
PLANT = [
    # row 2 - foliage greens and chlorosis
    ("plant", "5G 3/4", "deep green leaf"),
    ("plant", "2.5G 4/6", "dark green leaf"),
    ("plant", "7.5GY 3/4", "dark leaf green"),
    ("plant", "5GY 4/6", "leaf green"),
    ("plant", "7.5GY 5/8", "bright leaf green"),
    ("plant", "5GY 6/8", "light green leaf"),
    ("plant", "2.5GY 7/8", "chlorotic yellow-green"),
    ("plant", "5Y 8/6", "pale chlorotic yellow"),
    ("plant", "5BG 5/4", "glaucous blue-green"),
    ("plant", "7.5G 5/6", "green stem"),
    # row 3 - senescence, anthocyanin, necrosis, roots
    ("plant", "2.5Y 7/10", "senescent yellow"),
    ("plant", "7.5YR 6/10", "senescent orange"),
    ("plant", "2.5R 4/10", "anthocyanin red"),
    ("plant", "2.5R 3/8", "dark anthocyanin red"),
    ("plant", "5RP 3/8", "anthocyanin purple-red"),
    ("plant", "5RP 5/10", "pink-purple petiole/petal"),
    ("plant", "5YR 3/4", "necrotic brown"),
    ("plant", "7.5YR 4/4", "browned tissue"),
    ("plant", "2.5Y 9/2", "white root / mycelium"),
    ("plant", "7.5YR 7/4", "tan root"),
]
SOIL = [
    # row 4 (hue order, then value) - names as printed on the soil-chart diagrams
    ("soil", "10R 3/6", "dark red"),
    ("soil", "10R 4/8", "red"),
    ("soil", "2.5YR 3/4", "dark reddish brown"),
    ("soil", "2.5YR 4/6", "red"),
    ("soil", "2.5YR 6/4", "light reddish brown"),
    ("soil", "5YR 2.5/1", "black"),
    ("soil", "5YR 4/4", "reddish brown"),
    ("soil", "5YR 5/8", "yellowish red"),
    ("soil", "7.5YR 2.5/2", "very dark brown"),
    ("soil", "7.5YR 4/2", "brown"),
    # row 5
    ("soil", "7.5YR 5/6", "strong brown"),
    ("soil", "10YR 2/1", "black"),
    ("soil", "10YR 3/2", "very dark grayish brown"),
    ("soil", "10YR 4/1", "dark gray"),
    ("soil", "10YR 5/3", "brown"),
    ("soil", "10YR 6/1", "gray"),
    ("soil", "10YR 6/8", "brownish yellow"),
    ("soil", "10YR 7/3", "very pale brown"),
    ("soil", "2.5Y 6/6", "olive yellow"),
    ("soil", "2.5Y 7/1", "light gray"),
]
RAMP = [9.5, 9, 8, 7, 6, 5, 4, 3.5, 3, 2.5, 2, 1.5]
# Black surround for chips/ramp (replaces v1's red frame): crisp chip edges for
# automatic chip localisation, the ColorChecker convention, and it keeps the N5
# ramp step visible (an N5 panel swallowed it). NOTE: the chip grid forms a 2-D
# lattice of squares whatever the surround colour, and detectQuadCV
# (src/lib/colorcalib.ts) can prefer it over the corner fiducials under
# perspective. v2 needs the detector to verify the fiducial bit patterns
# (FIDUCIALS, exported in the spec) before it can be used in the app.
PANEL_HEX = "#000000"

# --- colour maths -------------------------------------------------------------
OBS = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]
WP_C = colour.xy_to_XYZ(OBS["C"])
WP_D50 = colour.xy_to_XYZ(OBS["D50"])


def munsell_xyY(notation: str) -> np.ndarray:
    return np.asarray(colour.munsell_colour_to_xyY(notation), dtype=float)


def xyY_to_lab_d50(xyY: np.ndarray) -> np.ndarray:
    XYZ_c = colour.xyY_to_XYZ(xyY)
    XYZ_d50 = colour.adaptation.chromatic_adaptation_VonKries(XYZ_c, WP_C, WP_D50, transform="Bradford")
    return colour.XYZ_to_Lab(XYZ_d50, OBS["D50"])


def xyY_to_srgb(xyY: np.ndarray) -> tuple[np.ndarray, bool]:
    XYZ = colour.xyY_to_XYZ(xyY)
    rgb = colour.XYZ_to_sRGB(XYZ, illuminant=OBS["C"], chromatic_adaptation_transform="Bradford")
    in_gamut = bool(np.all(rgb >= -1e-3) and np.all(rgb <= 1 + 1e-3))
    return np.clip(rgb, 0, 1), in_gamut


class CmykGate:
    """Lab(D50) -> CMYK -> Lab round trip through a press profile (relative colorimetric)."""

    def __init__(self, profile_path: str):
        lab = ImageCms.createProfile("LAB", colorTemp=5000)
        cmyk = ImageCms.getOpenProfile(profile_path)
        intent = ImageCms.Intent.RELATIVE_COLORIMETRIC
        self.fwd = ImageCms.buildTransform(lab, cmyk, "LAB", "CMYK", renderingIntent=intent)
        self.back = ImageCms.buildTransform(cmyk, lab, "CMYK", "LAB", renderingIntent=intent)

    @staticmethod
    def _enc(L, a, b):
        # Pillow LAB mode through littleCMS: L 0..255 <-> 0..100, a/b offset by +128
        # (verified: Lab(50,0,0) = (128,128,128) round-trips to itself).
        return (round(L * 255 / 100), round(a) + 128, round(b) + 128)

    @staticmethod
    def _dec(px):
        L, a, b = px
        return np.array([L * 100 / 255, a - 128, b - 128], float)

    def roundtrip(self, lab: np.ndarray):
        im = Image.new("LAB", (1, 1), self._enc(*np.clip(lab, [0, -128, -128], [100, 127, 127])))
        c = ImageCms.applyTransform(im, self.fwd)
        cmyk = c.getpixel((0, 0))
        lab2 = self._dec(ImageCms.applyTransform(c, self.back).getpixel((0, 0)))
        return lab2, [round(v / 255 * 100, 1) for v in cmyk]


def parse(notation: str):
    if notation.startswith("N"):
        return None
    hue, vc = notation.split(" ")
    v, c = vc.split("/")
    return hue, float(v), float(c)


def fit_chip(notation: str, gate: CmykGate, log: list):
    """Return colour record for a notation, reducing chroma until it fits the gamut."""
    original = notation
    while True:
        try:
            xyY = munsell_xyY(notation)
        except Exception as e:  # outside renotation data -> step chroma down
            p = parse(notation)
            if p is None or p[2] <= 2:
                raise
            notation = f"{p[0]} {p[1]:g}/{p[2] - 2:g}"
            log.append(f"{original}: not in renotation data ({type(e).__name__}); trying {notation}")
            continue
        lab = xyY_to_lab_d50(xyY)
        lab_rt, cmyk = gate.roundtrip(lab)
        de = float(colour.delta_E(lab, lab_rt, method="CIE 2000"))
        rgb, srgb_ok = xyY_to_srgb(xyY)
        p = parse(notation)
        # The artwork is delivered as sRGB, so a chip must fit BOTH the press
        # gamut and sRGB, or the file value is silently clipped.
        if (de <= GAMUT_DE and srgb_ok) or p is None or p[2] <= 2:
            break
        nxt = f"{p[0]} {p[1]:g}/{p[2] - 2:g}"
        why = f"out of CMYK gamut (dE2000 {de:.1f})" if de > GAMUT_DE else "outside sRGB"
        log.append(f"{notation}: {why}; chroma -> {nxt}")
        notation = nxt
    return {
        "munsell": notation,
        "munsell_requested": original,
        "xyY_C": [round(float(v), 5) for v in xyY],
        "Lab_D50": [round(float(v), 2) for v in lab],
        "sRGB_D65": "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in rgb),
        "sRGB_in_gamut": srgb_ok,
        "CMYK_generic_pct": cmyk,
        "gamut_dE2000": round(de, 2),
    }


# --- layout -------------------------------------------------------------------
def fid_centres():
    c = FID_INSET + FID / 2
    return {"TL": (c, c), "TR": (CARD_W - c, c), "BL": (c, CARD_H - c), "BR": (CARD_W - c, CARD_H - c)}


def quad_uv(x, y):
    f = fid_centres()
    (x0, y0), (x1, _), (_, y1) = f["TL"], f["TR"], f["BL"]
    return round((x - x0) / (x1 - x0), 4), round((y - y0) / (y1 - y0), 4)


class Canvas:
    """Primitive list in mm, rendered to SVG, PDF and PNG."""

    def __init__(self):
        self.items = []

    def rect(self, x, y, w, h, fill, stroke=None, sw=0.0, r=0.0):
        self.items.append(("rect", x, y, w, h, fill, stroke, sw, r))

    def line(self, x1, y1, x2, y2, stroke="#000000", sw=0.2):
        self.items.append(("line", x1, y1, x2, y2, stroke, sw))

    def text(self, x, y, s, size, fill="#000000", anchor="middle", bold=False):
        self.items.append(("text", x, y, s, size, fill, anchor, bold))

    # SVG ---------------------------------------------------------------------
    def svg(self, w, h, off=0.0):
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">']
        for it in self.items:
            if it[0] == "rect":
                _, x, y, rw, rh, fill, stroke, sw, r = it
                s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
                rr = f' rx="{r}"' if r else ""
                f = fill if fill else "none"
                out.append(f'<rect x="{x+off:.3f}" y="{y+off:.3f}" width="{rw:.3f}" height="{rh:.3f}" fill="{f}"{s}{rr}/>')
            elif it[0] == "line":
                _, x1, y1, x2, y2, st, sw = it
                out.append(f'<line x1="{x1+off:.3f}" y1="{y1+off:.3f}" x2="{x2+off:.3f}" y2="{y2+off:.3f}" stroke="{st}" stroke-width="{sw}"/>')
            else:
                _, x, y, s, size, fill, anchor, bold = it
                a = {"middle": "middle", "start": "start", "end": "end"}[anchor]
                wgt = ' font-weight="bold"' if bold else ""
                out.append(f'<text x="{x+off:.3f}" y="{y+off:.3f}" font-family="Helvetica, Arial, sans-serif" font-size="{size}"{wgt} text-anchor="{a}" fill="{fill}">{s}</text>')
        out.append("</svg>")
        return "\n".join(out)

    # PDF ---------------------------------------------------------------------
    def pdf(self, path, w, h, off=0.0):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl

        c = rl.Canvas(str(path), pagesize=(w * mm, h * mm))
        c.setTitle("ABCD v2 calibration card")
        Y = lambda y: (h - y) * mm  # noqa: E731  (SVG y-down -> PDF y-up)
        for it in self.items:
            if it[0] == "rect":
                _, x, y, rw, rh, fill, stroke, sw, r = it
                if fill:
                    c.setFillColor(fill)
                if stroke:
                    c.setStrokeColor(stroke)
                    c.setLineWidth(sw * mm)
                args = ((x + off) * mm, Y(y + off + rh), rw * mm, rh * mm)
                if r:
                    c.roundRect(*args, r * mm, stroke=1 if stroke else 0, fill=1 if fill else 0)
                else:
                    c.rect(*args, stroke=1 if stroke else 0, fill=1 if fill else 0)
            elif it[0] == "line":
                _, x1, y1, x2, y2, st, sw = it
                c.setStrokeColor(st)
                c.setLineWidth(sw * mm)
                c.line((x1 + off) * mm, Y(y1 + off), (x2 + off) * mm, Y(y2 + off))
            else:
                _, x, y, s, size, fill, anchor, bold = it
                c.setFillColor(fill)
                c.setFont("Helvetica-Bold" if bold else "Helvetica", size * mm / 0.3528 * 0.3528)
                fn = {"middle": c.drawCentredString, "start": c.drawString, "end": c.drawRightString}[anchor]
                fn((x + off) * mm, Y(y + off), s)
        c.showPage()
        c.save()

    # PNG ---------------------------------------------------------------------
    def png(self, path, w, h, dpi=DPI, off=0.0):
        k = dpi / 25.4
        im = Image.new("RGB", (round(w * k), round(h * k)), "white")
        d = ImageDraw.Draw(im)
        P = lambda v: v * k  # noqa: E731
        for it in self.items:
            if it[0] == "rect":
                _, x, y, rw, rh, fill, stroke, sw, r = it
                box = [P(x + off), P(y + off), P(x + off + rw) - 1, P(y + off + rh) - 1]
                width = max(1, round(P(sw))) if stroke else 0
                if r:
                    d.rounded_rectangle(box, radius=P(r), fill=fill, outline=stroke, width=width)
                else:
                    d.rectangle(box, fill=fill, outline=stroke, width=width)
            elif it[0] == "line":
                _, x1, y1, x2, y2, st, sw = it
                d.line([P(x1 + off), P(y1 + off), P(x2 + off), P(y2 + off)], fill=st, width=max(1, round(P(sw))))
            else:
                _, x, y, s, size, fill, anchor, bold = it
                font = load_font(round(P(size)), bold)
                a = {"middle": "ms", "start": "ls", "end": "rs"}[anchor]
                d.text((P(x + off), P(y + off)), s, fill=fill, font=font, anchor=a)
        im.save(path, dpi=(dpi, dpi))
        return im


def load_font(px, bold):
    for p in ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"]:
        try:
            return ImageFont.truetype(p, px, index=1 if (bold and p.endswith(".ttc")) else 0)
        except Exception:
            continue
    return ImageFont.load_default()


def version_bits(version: int, batch: int):
    """8 cells: 3-bit version + 5-bit batch, MSB first."""
    if not (0 <= version < 8 and 0 <= batch < 32):
        raise ValueError("version must be 0-7 and batch 0-31")
    return [int(b) for b in f"{version:03b}{batch:05b}"]


def build(batch: int, outdir: Path):
    gate = CmykGate(CMYK_PROFILE)
    log: list[str] = []
    chips = []
    for idx, (group, notation, label) in enumerate(CAL + PLANT + SOIL):
        row, col = divmod(idx, COLS)
        rec = fit_chip(notation, gate, log)
        x = CHIP_X0 + col * (CHIP + GUTTER)
        y = CHIP_Y0 + row * (CHIP + GUTTER)
        cx, cy = x + CHIP / 2, y + CHIP / 2
        u, v = quad_uv(cx, cy)
        chips.append({"id": f"{'ABCDE'[row]}{col + 1}", "group": group, "row": row + 1, "col": col + 1,
                      "label": label, **rec, "x_mm": round(x, 2), "y_mm": round(y, 2),
                      "centre_mm": [round(cx, 2), round(cy, 2)], "u": u, "v": v, "size_mm": [CHIP, CHIP]})
    ramp_w = (COLS * CHIP + (COLS - 1) * GUTTER - (len(RAMP) - 1) * 0.5) / len(RAMP)
    for i, val in enumerate(RAMP):
        rec = fit_chip(f"N{val:g}", gate, log)
        x = CHIP_X0 + i * (ramp_w + 0.5)
        cx, cy = x + ramp_w / 2, RAMP_Y0 + RAMP_H / 2
        u, v = quad_uv(cx, cy)
        chips.append({"id": f"G{i + 1}", "group": "neutral ramp", "row": 6, "col": i + 1,
                      "label": f"neutral value {val:g}", **rec, "x_mm": round(x, 2), "y_mm": RAMP_Y0,
                      "centre_mm": [round(cx, 2), round(cy, 2)], "u": u, "v": v,
                      "size_mm": [round(ramp_w, 3), RAMP_H]})

    # --- draw ---------------------------------------------------------------
    cv = Canvas()
    cv.rect(-BLEED, -BLEED, CARD_W + 2 * BLEED, CARD_H + 2 * BLEED, "#FFFFFF")
    # black panel behind chips + ramp (1 mm surround and gutters)
    cv.rect(CHIP_X0 - GUTTER, CHIP_Y0 - GUTTER, COLS * CHIP + (COLS + 1) * GUTTER,
            ROWS * CHIP + (ROWS + 1) * GUTTER, PANEL_HEX)
    cv.rect(CHIP_X0 - GUTTER, RAMP_Y0 - GUTTER, COLS * CHIP + (COLS + 1) * GUTTER, RAMP_H + 2 * GUTTER,
            PANEL_HEX)
    for c in chips:
        cv.rect(c["x_mm"], c["y_mm"], c["size_mm"][0], c["size_mm"][1], c["sRGB_D65"])
    # fiducials
    cell = FID / 6
    for name, (fx, fy) in fid_centres().items():
        x0, y0 = fx - FID / 2, fy - FID / 2
        cv.rect(x0, y0, FID, FID, "#FFFFFF")
        for r, line in enumerate(FIDUCIALS[name]):
            for cidx, ch in enumerate(line):
                if ch == "#":
                    cv.rect(x0 + cidx * cell, y0 + r * cell, cell, cell, "#000000")
    # horizontal ruler 0..10 cm (ticks hang from the top)
    top = 4.0
    cv.line(RULER_X0, top, RULER_X0 + RULER_LEN, top, sw=0.25)
    for mmv in range(0, int(RULER_LEN) + 1):
        x = RULER_X0 + mmv
        ln = 5.0 if mmv % 10 == 0 else 3.5 if mmv % 5 == 0 else 2.0
        cv.line(x, top, x, top + ln, sw=0.2 if mmv % 10 else 0.3)
        if mmv % 10 == 0:
            # "10" sits flush-right of its tick so it clears the TR fiducial
            if mmv == RULER_LEN:
                cv.text(x + 0.4, top + 9.3, str(mmv // 10), 3.6, anchor="end", bold=True)
            else:
                cv.text(x, top + 9.3, str(mmv // 10), 3.6, bold=True)
    cv.text(RULER_X0 + 5, top + 9.0, "cm", 2.4)
    # vertical ruler 0..5 cm on the left column (ticks from the left edge of the column)
    left = 3.0
    cv.line(left, VRULER_Y0, left, VRULER_Y0 + VRULER_LEN, sw=0.25)
    for mmv in range(0, int(VRULER_LEN) + 1):
        y = VRULER_Y0 + mmv
        ln = 5.0 if mmv % 10 == 0 else 3.5 if mmv % 5 == 0 else 2.0
        cv.line(left, y, left + ln, y, sw=0.2 if mmv % 10 else 0.3)
        if mmv % 10 == 0:
            cv.text(left + 9.5, y + 1.2, str(mmv // 10), 3.2, bold=True)
    # checker (right column)
    for j in range(CHECK_NY):
        for i in range(CHECK_NX):
            if (i + j) % 2 == 0:
                cv.rect(CHECK_X0 + i * CHECK, CHECK_Y0 + j * CHECK, CHECK, CHECK, "#000000")
    cv.rect(CHECK_X0, CHECK_Y0, CHECK_NX * CHECK, CHECK_NY * CHECK, None, "#000000", 0.2)
    # ID strip: text + 8-cell version/batch code between the bottom fiducials
    bits = version_bits(2, batch)
    bx, by, bw = 21.0, 81.0, 2.5
    cv.rect(bx - 0.4, by - 0.4, 8 * bw + 0.8, bw + 0.8, None, "#000000", 0.25)
    for i, b in enumerate(bits):
        if b:
            cv.rect(bx + i * bw, by, bw, bw, "#000000")
    cv.text(bx + 8 * bw + 3, by + 2.3, f"ABCD v2  ·  batch {batch:02d}", 3.0, anchor="start", bold=True)
    cv.text(119.5, by + 2.3, "chips: Munsell renotation · spec abcd_v2_chips.csv", 2.0, anchor="end",
            fill="#555555")
    # trim keyline (preview only; not in the print PDF)
    cv_preview = Canvas()
    cv_preview.items = list(cv.items)
    cv_preview.rect(0, 0, CARD_W, CARD_H, None, "#BBBBBB", 0.2, r=3.0)

    # --- outputs ------------------------------------------------------------
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "abcd_v2.svg").write_text(cv_preview.svg(CARD_W, CARD_H))
    cv.pdf(outdir / "abcd_v2_print.pdf", CARD_W + 2 * BLEED, CARD_H + 2 * BLEED, off=BLEED)
    im = cv_preview.png(outdir / "abcd_v2_preview.png", CARD_W, CARD_H)

    f = fid_centres()
    geometry = {
        "card_mm": [CARD_W, CARD_H], "bleed_mm": BLEED, "corner_radius_mm": 3.0,
        "fiducial_edge_mm": FID, "fiducial_centres_mm": f,
        "fiducial_aruco": {"dictionary": ARUCO_DICT, "ids": FIDUCIAL_IDS, "v1_ids": V1_FIDUCIAL_IDS},
        "fiducial_bits": {k: v for k, v in FIDUCIALS.items()},
        "fiducial_bits_v1": {k: v for k, v in V1_FIDUCIALS.items()},
        "fiducial_bits_note": "6x6 cells, '#'=black, row-major from the top-left, as printed (unrotated)",
        "corner_span_cm": {"x": round((f["TR"][0] - f["TL"][0]) / 10, 3),
                            "y": round((f["BL"][1] - f["TL"][1]) / 10, 3)},
        "quad_uv_convention": "u: TL->TR, v: TL->BL across fiducial centres (as ASTRO_CHIPS in src/lib/colorcalib.ts)",
        "ruler_h": {"origin_mm": [RULER_X0, top], "length_cm": RULER_LEN / 10},
        "ruler_v": {"origin_mm": [left, VRULER_Y0], "length_cm": VRULER_LEN / 10},
        "checker": {"origin_mm": [CHECK_X0, CHECK_Y0], "pitch_mm": CHECK, "nx": CHECK_NX, "ny": CHECK_NY},
        "id_code": {"origin_mm": [bx, by], "cell_mm": bw, "bits": bits, "encoding": "3-bit version + 5-bit batch, MSB first, black=1"},
        "panel": {"colour": "black (K100 / sRGB #000000)", "sRGB": PANEL_HEX,
                  "why": "crisp chip edges, ColorChecker convention, keeps the N5 ramp step visible"},
        "colour_pipeline": "Munsell renotation (colour-science %s, Illuminant C, 2deg) -> Bradford -> Lab D50 / sRGB D65; gamut gate: %s, relative colorimetric, dE2000 <= %.1f" % (colour.__version__, Path(CMYK_PROFILE).name, GAMUT_DE),
    }
    (outdir / "abcd_v2_chips.json").write_text(json.dumps({"version": 2, "batch": batch, "geometry": geometry,
                                                            "chips": chips, "gamut_log": log}, indent=1))
    cols = ["id", "group", "row", "col", "label", "munsell", "munsell_requested", "xyY_C", "Lab_D50",
            "sRGB_D65", "sRGB_in_gamut", "CMYK_generic_pct", "gamut_dE2000", "centre_mm", "u", "v", "size_mm"]
    with open(outdir / "abcd_v2_chips.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for c in chips:
            w.writerow([" ".join(map(str, c[k])) if isinstance(c.get(k), list) else c.get(k, "") for k in cols])
    # Spectrophotometer readings live in their own file so re-running this script
    # can never overwrite them. The template is written only if it doesn't exist.
    tmpl = outdir.parent / "measurements" / "batch_template.csv"
    if not tmpl.exists():
        tmpl.parent.mkdir(exist_ok=True)
        with open(tmpl, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "munsell", "measured_L", "measured_a", "measured_b", "n_stickers", "max_inter_sticker_dE2000"])
            for c in chips:
                w.writerow([c["id"], c["munsell"], "", "", "", "", ""])

    # --- self-checks ----------------------------------------------------------
    k = DPI / 25.4
    ruler_px = RULER_LEN * k
    assert abs(ruler_px - 1181.1) < 0.1, ruler_px
    assert abs(im.width - CARD_W * k) <= 1 and abs(im.height - CARD_H * k) <= 1
    boxes = [(c["x_mm"], c["y_mm"], c["x_mm"] + c["size_mm"][0], c["y_mm"] + c["size_mm"][1]) for c in chips]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] + 1e-6 or b[2] <= a[0] + 1e-6 or a[3] <= b[1] + 1e-6 or b[3] <= a[1] + 1e-6, (a, b)
    for c in chips:
        assert 0 < c["u"] < 1 and 0 < c["v"] < 1, c["id"]
    fid_boxes = [(fx - FID / 2, fy - FID / 2, fx + FID / 2, fy + FID / 2) for fx, fy in f.values()]
    for a in boxes:
        for b in fid_boxes:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], ("chip overlaps fiducial", a)
    area_ratio = FID ** 2 / CHIP ** 2
    assert area_ratio > 2.0, area_ratio  # keeps fiducials out of the chip size-cluster in detectQuadCV

    swapped = [c for c in chips if c["munsell"] != c["munsell_requested"]]
    print(f"chips: {len(chips)} ({len(CAL)} calibration, {len(PLANT)} plant, {len(SOIL)} soil, {len(RAMP)} neutral)")
    print(f"ruler 10 cm = {ruler_px:.1f} px @ {DPI} dpi; fiducial/chip area ratio {area_ratio:.2f}")
    print(f"gamut: {len(swapped)} chips chroma-reduced; max dE2000 after gate "
          f"{max(c['gamut_dE2000'] for c in chips):.2f}; sRGB out-of-gamut: "
          f"{[c['id'] + ' ' + c['munsell'] for c in chips if not c['sRGB_in_gamut']]}")
    for line in log:
        print("  ", line)
    print("corner span cm:", geometry["corner_span_cm"])
    return chips, geometry


def measured_std(path: Path) -> dict:
    """id -> sRGB 0-1 from a filled-in measurements CSV (Lab D50 -> sRGB D65)."""
    out = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            if row.get("measured_L"):
                lab = np.array([float(row["measured_L"]), float(row["measured_a"]), float(row["measured_b"])])
                XYZ = colour.Lab_to_XYZ(lab, OBS["D50"])
                rgb = colour.XYZ_to_sRGB(XYZ, illuminant=OBS["D50"], chromatic_adaptation_transform="Bradford")
                out[row["id"]] = [float(v) for v in np.clip(rgb, 0, 1)]
    return out


def write_ts(chips, geometry, path: Path, measured: Path | None):
    """Emit the app's v2 chip table (src/lib/abcd_v2_chips.ts in the calibration app)."""
    meas = measured_std(measured) if measured else {}
    src = "design sRGB targets (unmeasured)" if not meas else f"measured Lab from {measured.name} ({len(meas)} chips), design sRGB for the rest"
    lines = [
        "// GENERATED by make_abcd_v2.py in the ABCD_v2 repo - do not edit by hand.",
        f"// Reference colours: {src}.",
        "import type { AstroChip } from './colorcalib';",
        "",
        "// Fiducial-centre spans of the ABCD v2 card (TL->TR, TL->BL).",
        f"export const ABCD_V2_SPAN_CM = {{ x: {geometry['corner_span_cm']['x']}, y: {geometry['corner_span_cm']['y']} }};",
        "// Chip edge in cm (sampling radius is derived from it).",
        f"export const ABCD_V2_CHIP_CM = {CHIP / 10};",
        "",
        "export const ABCD_V2_CHIPS: AstroChip[] = [",
    ]
    for i, c in enumerate(chips):
        std = meas.get(c["id"]) or [int(c["sRGB_D65"][j:j + 2], 16) / 255 for j in (1, 3, 5)]
        name = f"{c['id']} {c['munsell']} {c['label']}".replace("'", "")
        lines.append(f"  {{ id: {i + 1}, u: {c['u']}, v: {c['v']}, std: [{std[0]:.4f}, {std[1]:.4f}, {std[2]:.4f}], name: '{name}' }},")
    lines += ["];", ""]
    path.write_text("\n".join(lines))
    print("wrote", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--out", type=Path, default=REPO / "card")
    ap.add_argument("--ts-out", type=Path, help="write the app chip table, e.g. ../AstroBotany_calibration_image_sharing_and_analysis/src/lib/abcd_v2_chips.ts")
    ap.add_argument("--measured", type=Path, help="filled-in measurements CSV; its Lab values replace design targets in --ts-out")
    a = ap.parse_args()
    chips, geometry = build(a.batch, a.out)
    if a.ts_out:
        write_ts(chips, geometry, a.ts_out, a.measured)
    sys.exit(0)
