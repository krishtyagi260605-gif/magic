#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
RESOURCES = ROOT / "Magic.app" / "Contents" / "Resources"
ICONSET = RESOURCES / "Magic.iconset"

# Premium Dark Cyberpunk palette
BG_TOP = (15, 15, 20)
BG_BOTTOM = (5, 5, 8)
FACE = (22, 22, 28)
RING_A = (0, 238, 255)    # Neon Cyan
RING_B = (255, 0, 128)    # Neon Pink
RING_C = (138, 43, 226)   # Deep Purple
ACCENT_SUN = (255, 255, 255) # Pure White


def make_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Soft shadow under tile
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        [size * 0.09, size * 0.11, size * 0.91, size * 0.93],
        radius=int(size * 0.22),
        fill=(0, 0, 0, 120),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.035))
    image.alpha_composite(shadow)

    # Vertical gradient face
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    for i in range(size):
        t = i / max(1, size - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t * 0.85)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        bg_draw.line([(0, i), (size, i)], fill=(r, g, b, 255))

    bg_draw.rounded_rectangle(
        [size * 0.08, size * 0.08, size * 0.92, size * 0.92],
        radius=int(size * 0.22),
        fill=None,
        outline=(167, 139, 250, 55),
        width=max(2, size // 160),
    )

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [size * 0.12, size * 0.1, size * 0.88, size * 0.62],
        fill=(45, 212, 191, 45),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.07))
    bg.alpha_composite(glow)
    image.alpha_composite(bg)

    draw = ImageDraw.Draw(image)

    # Hexagon frame (stroke approximation with wide polygon outline)
    cx, cy = size / 2, size / 2
    r_outer = size * 0.34
    pts_outer = []
    for k in range(6):
        ang = math.radians(-90 + k * 60)
        pts_outer.append((cx + r_outer * math.cos(ang), cy + r_outer * math.sin(ang)))
    for i in range(6):
        a, b = pts_outer[i], pts_outer[(i + 1) % 6]
        draw.line([a, b], fill=(*RING_B, 240), width=max(4, size // 85))

    r_in = size * 0.22
    inner = []
    for k in range(6):
        ang = math.radians(-90 + k * 60)
        inner.append((cx + r_in * math.cos(ang), cy + r_in * math.sin(ang)))
    draw.polygon(inner, fill=(*FACE, 235), outline=(*RING_A, 100))

    # Center gem + sparkles
    gem = size * 0.055
    draw.ellipse(
        [cx - gem, cy - gem * 0.3, cx + gem, cy + gem * 1.1],
        fill=(*RING_A, 255),
    )
    draw.ellipse(
        [cx - gem * 0.55, cy - gem * 0.85, cx + gem * 0.55, cy - gem * 0.35],
        fill=(*ACCENT_SUN, 255),
    )

    def sparkle(cx_: float, cy_: float, rad: float, fill: tuple[int, int, int, int]) -> None:
        points = [
            (cx_, cy_ - rad),
            (cx_ + rad * 0.34, cy_ - rad * 0.34),
            (cx_ + rad, cy_),
            (cx_ + rad * 0.34, cy_ + rad * 0.34),
            (cx_, cy_ + rad),
            (cx_ - rad * 0.34, cy_ + rad * 0.34),
            (cx_ - rad, cy_),
            (cx_ - rad * 0.34, cy_ - rad * 0.34),
        ]
        draw.polygon(points, fill=fill)

    sparkle(size * 0.72, size * 0.28, size * 0.09, (*RING_A, 250))
    sparkle(size * 0.26, size * 0.42, size * 0.055, (*RING_C, 230))
    draw.ellipse(
        [size * 0.18, size * 0.2, size * 0.24, size * 0.26],
        fill=(*ACCENT_SUN, 235),
    )

    haze = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    haze_draw = ImageDraw.Draw(haze)
    haze_draw.ellipse(
        [size * 0.14, size * 0.58, size * 0.86, size * 0.92],
        fill=(139, 92, 246, 32),
    )
    haze = haze.filter(ImageFilter.GaussianBlur(size * 0.06))
    image.alpha_composite(haze)
    return image


def save_icon_pngs() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)
    ICONSET.mkdir(parents=True, exist_ok=True)

    base = make_icon(1024)
    base.save(STATIC / "magic-icon-1024.png")
    base.resize((256, 256), Image.Resampling.LANCZOS).save(STATIC / "magic-icon-256.png")
    base.resize((128, 128), Image.Resampling.LANCZOS).save(STATIC / "magic-icon-128.png")

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
        print(f"Generating {name}...")
        base.resize((icon_size, icon_size), Image.Resampling.LANCZOS).save(ICONSET / name)


if __name__ == "__main__":
    save_icon_pngs()
