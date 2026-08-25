from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "assets" / "images"
TARGETS = {
    "icon.png": 512,
    "splash-icon.png": 512,
    "favicon.png": 192,
    "android-icon-foreground.png": 432,
}

for filename, size in TARGETS.items():
    path = ROOT / filename
    with Image.open(path) as image:
        image = image.convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image.save(path, format="PNG", optimize=True)
        print(f"{filename}: {image.width}x{image.height}")
