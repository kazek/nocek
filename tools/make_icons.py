"""Draw the application icon and write it in each operating system's format.

The files it writes are kept in the repository; run this again only to
change the icon. Needs Pillow:

    .venv/bin/python tools/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PACKAGE = Path(__file__).parents[1] / "src" / "nyctalus"
OUT = PACKAGE / "icons"
ACCENT = "#6a3fa0"
SIZE = 1024
SCALE = 4  # drawn larger, then reduced, for smooth edges

# The right half of the bat, from the top of the head round to the tail, in a
# 100 by 100 box; the left half is its mirror image.
# fmt: off
RIGHT_HALF = [
    (50, 37), (52, 36), (54.5, 26), (57, 38), (60, 41),
    (67, 37), (77, 31), (89, 27), (87, 38), (84, 47),
    (79, 45), (74, 53), (69, 48), (64, 58), (60, 54),
    (55, 62), (50, 68),
]
# fmt: on


def draw() -> Image.Image:
    size = SIZE * SCALE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.22, fill=ACCENT)
    left_half = [(100 - x, y) for x, y in reversed(RIGHT_HALF[1:-1])]
    outline = [*RIGHT_HALF, *left_half]
    # Centre the bat vertically: its box runs from y=26 to y=68.
    pen.polygon([(x / 100 * size, (y + 3) / 100 * size) for x, y in outline], fill="white")
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon = draw()
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(OUT / "nyctalus.png")
    icon.resize((64, 64), Image.Resampling.LANCZOS).save(PACKAGE / "web" / "static" / "favicon.png")
    icon.save(OUT / "nyctalus.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    icon.save(OUT / "nyctalus.icns")


if __name__ == "__main__":
    main()
