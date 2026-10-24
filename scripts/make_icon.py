#!/usr/bin/env python3
"""Generate packaging/icon.ico from the game logo for the Windows build.

Optional: builds use the committed packaging/icon.ico, and running this
replaces it with one made from the logo. Requires Pillow. Best-effort: if the logo or Pillow is missing it exits 0 so the build
still succeeds with the default icon.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "assets" / "images" / "others" / "logo.png"
OUT = ROOT / "packaging" / "icon.ico"

# Sizes Windows expects inside a multi-resolution .ico.
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — skipping icon generation.")
        return 0

    if not LOGO.exists():
        print(f"Logo not found at {LOGO} — skipping icon generation.")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(LOGO).convert("RGBA")

    # Fit the (likely non-square) logo onto a transparent square canvas.
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))

    canvas.save(OUT, format="ICO", sizes=SIZES)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
