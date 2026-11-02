"""Rebuild the code-drawn LiveMinutes waveform icon (Pillow is build-only)."""
from pathlib import Path
from PIL import Image, ImageDraw

destination = Path(__file__).resolve().parent.parent / 'assets'
destination.mkdir(exist_ok=True)
scale = 4
image = Image.new('RGBA', (256*scale, 256*scale))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((0, 0, 256*scale-1, 256*scale-1), radius=60*scale, fill='#3933D8')
for x, height in zip((65, 96, 128, 160, 191), (46, 94, 142, 94, 46)):
    draw.rounded_rectangle(((x-8)*scale, (128-height/2)*scale,
                            (x+8)*scale, (128+height/2)*scale), radius=8*scale, fill='white')
image = image.resize((256, 256), Image.Resampling.LANCZOS)
image.save(destination / 'liveminutes.png')
image.save(destination / 'liveminutes.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
