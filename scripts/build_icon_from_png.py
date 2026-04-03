#!/usr/bin/env python3
"""Generate all macOS icon sizes from the crystal-star source PNG."""
from pathlib import Path
from PIL import Image

SOURCE = Path("/Users/krishtyagi/.gemini/antigravity/brain/0d493a1a-557d-4266-8e45-606dd726e227/magic_crystal_star_1775082720474.png")
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
RESOURCES = ROOT / "Magic.app" / "Contents" / "Resources"
ICONSET = RESOURCES / "Magic.iconset"

STATIC.mkdir(parents=True, exist_ok=True)
RESOURCES.mkdir(parents=True, exist_ok=True)
ICONSET.mkdir(parents=True, exist_ok=True)

base = Image.open(SOURCE).convert("RGBA")
print(f"Source: {base.size[0]}x{base.size[1]}")

# Static PNGs for web
for sz in [1024, 256, 128]:
    out = STATIC / f"magic-icon-{sz}.png"
    base.resize((sz, sz), Image.Resampling.LANCZOS).save(out)
    print(f"  Saved {out.name}")

# macOS iconset
sizes = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}
for name, icon_size in sizes.items():
    base.resize((icon_size, icon_size), Image.Resampling.LANCZOS).save(ICONSET / name)
    print(f"  Saved iconset/{name}")

print("\nDone! Now run:")
print(f"  iconutil -c icns {ICONSET} -o {RESOURCES / 'Magic.icns'}")
print("  killall Dock")
