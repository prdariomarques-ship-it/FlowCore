from pathlib import Path
from PIL import Image

root = Path('/home/ubuntu/teologos-chat/assets/images')
files = ['icon.png', 'splash-icon.png', 'favicon.png', 'android-icon-foreground.png']
for name in files:
    path = root / name
    image = Image.open(path).convert('RGB')
    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    image.save(path, format='PNG', optimize=True, compress_level=9)
    print(name, path.stat().st_size)
