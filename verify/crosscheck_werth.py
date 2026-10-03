"""Compare chip sRGB values with Andrew Werth's Virtual Munsell Color Wheel CSS.

Usage: python crosscheck_werth.py   (downloads the CSS; prints max per-channel difference)
"""
import json, re, urllib.request
from pathlib import Path
CSS = "https://werth-color.pages.dev/munsellC-20250219.css"
css = urllib.request.urlopen(urllib.request.Request(CSS, headers={"User-Agent": "Mozilla/5.0"})).read().decode()
spec = json.loads((Path(__file__).parent.parent / "card" / "abcd_v2_chips.json").read_text())
hexrgb = lambda h: [int(h[i:i + 2], 16) for i in (1, 3, 5)]
diffs, missing = [], []
for ch in spec["chips"]:
    if ch["munsell"].startswith("N"):
        continue
    h, vc = ch["munsell"].split(" "); v, c = vc.split("/")
    cls = "h" + h.replace(".", "_") + "v" + v.replace(".", "_") + "c" + c
    m = re.search(r"\." + re.escape(cls) + r"\s*\{[^}]*?background(?:-color)?\s*:\s*(#[0-9a-fA-F]{6})", css)
    if not m:
        missing.append(ch["munsell"]); continue
    d = max(abs(a - b) for a, b in zip(hexrgb(m.group(1)), hexrgb(ch["sRGB_D65"])))
    diffs.append(d); print(f"{ch['id']:4} {ch['munsell']:11} ours {ch['sRGB_D65']}  werth {m.group(1).upper()}  max diff {d}")
print(f"\n{len(diffs)} compared, max per-channel diff {max(diffs)}/255; not in tool: {missing}")
