#!/bin/sh
# Rebuild the card and regenerate every file in results/ that the site and deck quote.
#
#   PY=python3 APP=../AstroBotany_calibration_image_sharing_and_analysis sh scripts/run_all.sh
#
# PY   python with colour-science, reportlab, Pillow, numpy<2, opencv-python-headless
# APP  checkout of the calibration app (its node_modules must be installed); detection
#      is run against its working tree. APP_BEFORE (optional) is a second checkout at
#      the pre-fix commit, giving the "before" column.
set -eu
cd "$(dirname "$0")/.."
PY=${PY:-python3}
APP=${APP:-../AstroBotany_calibration_image_sharing_and_analysis}
TMP=$(mktemp -d)
mkdir -p results

echo "== card + chip spec"
$PY scripts/make_abcd_v2.py --ts-out "$APP/src/lib/abcd_v2_chips.ts" 2>/dev/null | tee results/generator_log.txt

echo "== ArUco IDs (OpenCV)"
$PY verify/check_aruco_ids.py 2>/dev/null | tee results/aruco_ids.txt

echo "== v1 geometry"
$PY verify/measure_v1_geometry.py 2>/dev/null | tee results/v1_geometry.txt

echo "== Werth cross-check"
$PY verify/crosscheck_werth.py 2>/dev/null | tee results/werth_crosscheck.txt

V1FPX='[[233.75,237.875],[1416.25,237.875],[1414.875,1193.5],[233.75,1193.5]]'
$PY verify/make_test_images.py card/abcd_v2_preview.png v2_ "$TMP" >/dev/null 2>&1
SCALE=2.75 FPX=$V1FPX $PY verify/make_test_images.py reference/ABC_v1_stickermule.png v1_ "$TMP" >/dev/null 2>&1

run_detect() {  # $1 app checkout, $2 output file
  (cd verify && APP="$1" node build.mjs)
  { echo "# app: AstroBotany_calibration_image_sharing_and_analysis @ $(git -C "$1" rev-parse --short HEAD)$(git -C "$1" diff --quiet -- src || echo ' + uncommitted changes')"
    node verify/detect.mjs "$TMP" v1_; node verify/detect.mjs "$TMP" v2_; } | tee "$2"
  rm -f verify/detect.mjs
}
echo "== detection (app with fix)"
run_detect "$(cd "$APP" && pwd)" results/detection_after.txt
if [ -n "${APP_BEFORE:-}" ]; then
  echo "== detection (app before fix)"
  run_detect "$(cd "$APP_BEFORE" && pwd)" results/detection_before.txt
fi
rm -rf "$TMP"
