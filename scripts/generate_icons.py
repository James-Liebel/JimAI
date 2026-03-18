"""Generates PWA icons — requires pillow: pip install pillow"""
from PIL import Image, ImageDraw, ImageFont
import os


def create_icon(size: int, path: str):
    img = Image.new('RGB', (size, size), color='#0a0a0c')
    draw = ImageDraw.Draw(img)

    margin = size // 8
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        outline='#4f8ef7',
        width=size // 20,
    )

    font_size = size // 3
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    text = "AI"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2
    y = (size - text_h) // 2
    draw.text((x, y), text, fill='#4f8ef7', font=font)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    print(f"Created {path}")


if __name__ == "__main__":
    create_icon(192, 'frontend/public/icons/icon-192.png')
    create_icon(512, 'frontend/public/icons/icon-512.png')
