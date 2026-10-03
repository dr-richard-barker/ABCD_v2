"""Check the corner markers with OpenCV's own ArUco detector (DICT_4X4_50).

Confirms that (1) the bit grids in make_abcd_v2.py are exactly OpenCV's markers
and (2) a rendered card reads as the expected IDs in the expected corners.

Usage: python verify/check_aruco_ids.py   (needs opencv-python-headless)
"""
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from make_abcd_v2 import FIDUCIALS, FIDUCIAL_IDS, V1_FIDUCIALS, V1_FIDUCIAL_IDS  # noqa: E402

d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
ok = True
for label, grids, ids in (("v2", FIDUCIALS, FIDUCIAL_IDS), ("v1", V1_FIDUCIALS, V1_FIDUCIAL_IDS)):
    for corner, grid in grids.items():
        img = cv2.aruco.generateImageMarker(d, ids[corner], 60)
        cv_grid = ["".join("#" if v < 128 else "." for v in row) for row in img[5::10, 5::10]]
        match = cv_grid == grid
        ok &= match
        print(f"{label} {corner}: id {ids[corner]} bit grid matches OpenCV: {match}")

# Separation: minimum bit distance (over all rotations) between v2 and v1 markers,
# within v2, and between each v2 marker and its own rotations.
def inner(i):
    img = cv2.aruco.generateImageMarker(d, i, 60)
    return (img[15::10, 15::10][:4, :4] < 128).astype(int)


def dist(a, b):
    return min(int((np.rot90(inner(a), r) != inner(b)).sum()) for r in range(4))


v2, v1 = list(FIDUCIAL_IDS.values()), list(V1_FIDUCIAL_IDS.values())
print("min bits v2 vs v1:", min(dist(a, b) for a in v2 for b in v1))
print("min bits within v2:", min(dist(a, b) for a in v2 for b in v2 if a != b))
print("min bits v2 vs own rotations:", min(int((np.rot90(inner(a), r) != inner(a)).sum()) for a in v2 for r in (1, 2, 3)))

det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())


def read(path, expect):
    global ok
    img = cv2.imread(str(path))
    corners, ids, _ = det.detectMarkers(img)
    h, w = img.shape[:2]
    got = {}
    for c, i in zip(corners, (ids.flatten() if ids is not None else [])):
        cx, cy = c[0].mean(0)
        got[("T" if cy < h / 2 else "B") + ("L" if cx < w / 2 else "R")] = int(i)
    good = got == expect
    ok &= good
    print(f"{path.name}: read {got}  expected {expect}  {'OK' if good else 'MISMATCH'}")


read(HERE.parent / "card" / "abcd_v2_preview.png", FIDUCIAL_IDS)
read(HERE.parent / "reference" / "ABC_v1_stickermule.png", V1_FIDUCIAL_IDS)
sys.exit(0 if ok else 1)
