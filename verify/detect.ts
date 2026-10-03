// Runs the calibration app's own detectMarkerCorners on images from make_test_images.py.
// Usage: APP=<path to AstroBotany_calibration_image_sharing_and_analysis> node build.mjs
//        node detect.mjs <out-dir> <tag>
import { detectMarkerCorners } from 'APP_COLORCALIB';
import * as fs from 'node:fs';
(async () => {
  const [dir, tag] = [process.argv[2], process.argv[3]];
  let fails = 0;
  for (const n of JSON.parse(fs.readFileSync(`${dir}/${tag}names.json`, 'utf8'))) {
    const meta = JSON.parse(fs.readFileSync(`${dir}/${n}.json`, 'utf8'));
    const buf = fs.readFileSync(`${dir}/${n}.rgba`);
    const r = await detectMarkerCorners(new Uint8ClampedArray(buf.buffer, buf.byteOffset, buf.length), meta.w, meta.h);
    const err = r.corners ? Math.max(...r.corners.map((p, i) => Math.hypot(p.x - meta.expected[i][0], p.y - meta.expected[i][1]))) : Infinity;
    if (!(err < 5)) fails++;
    console.log(n.padEnd(30), `card ${r.card ?? '-'}`, `ids verified ${r.verified ?? 0}/4`, `max corner error ${err.toFixed(1)} px`, err < 5 ? 'OK' : 'FAIL');
  }
  console.log(fails ? `${fails} FAILED` : 'all OK');
})();
