"""Builds the GitHub social preview image: docs/design/social-preview.png (1280x640, GitHub's 2:1).

A center crop of the HUD-hidden screenshot with the logo on a dark band. This is a stopgap until
the store banner (#174) exists; remake the preview from that art then. GitHub has no API for the
image: upload it by hand in Settings > Social preview.

    uv run --group dev python scripts/make_social_preview.py
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHOT = ROOT / "docs" / "screenshots" / "17_hud_hidden.png"
LOGO = ROOT / "assets" / "images" / "branding" / "logo.png"
OUT = ROOT / "docs" / "design" / "social-preview.png"
SIZE = (1280, 640)
LOGO_WIDTH_SHARE = 0.78
BAND_COLOR = (10, 14, 24, 170)


def main() -> None:
    width, height = SIZE
    shot = Image.open(SHOT).convert("RGB")
    # The 1920x1080 screenshot cropped to 2:1 (full width), then scaled to the preview size.
    crop_height = round(shot.width / 2)
    top = (shot.height - crop_height) // 2
    top = max(0, min(top, shot.height - crop_height))
    base = (
        shot.crop((0, top, shot.width, top + crop_height))
        .resize(SIZE, Image.LANCZOS)
        .convert("RGBA")
    )

    logo = Image.open(LOGO).convert("RGBA")
    logo_width = int(width * LOGO_WIDTH_SHARE)
    logo = logo.resize(
        (logo_width, round(logo.height * logo_width / logo.width)), Image.LANCZOS
    )
    band = Image.new("RGBA", (width, logo.height + 70), BAND_COLOR)
    y = (height - band.height) // 2
    base.alpha_composite(band, (0, y))
    base.alpha_composite(logo, ((width - logo_width) // 2, y + 35))
    base.convert("RGB").save(OUT, optimize=True)
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
