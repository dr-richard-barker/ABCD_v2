// Bundles detect.ts against the calibration app's colorcalib.ts with the app's
// esbuild, resolving Vite-style `?raw` imports. APP defaults to the sibling checkout.
import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath, pathToFileURL } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const app = path.resolve(process.env.APP ?? path.join(here, '../../AstroBotany_calibration_image_sharing_and_analysis'));
const nm = path.join(app, 'node_modules');
const esbuild = await import(pathToFileURL(path.join(nm, 'esbuild/lib/main.js')).href);
await esbuild.build({ entryPoints: [path.join(here, 'detect.ts')], bundle: true, platform: 'node', format: 'esm',
  outfile: path.join(here, 'detect.mjs'), nodePaths: [nm], logLevel: 'warning',
  alias: { APP_COLORCALIB: path.join(app, 'src/lib/colorcalib.ts') },
  plugins: [{ name: 'raw', setup(b) {
    b.onResolve({ filter: /\?raw$/ }, a => ({ path: path.resolve(nm, a.path.replace(/\?raw$/, '')), namespace: 'raw' }));
    b.onLoad({ filter: /.*/, namespace: 'raw' }, a => ({ contents: fs.readFileSync(a.path, 'utf8'), loader: 'text' }));
  } }] });
