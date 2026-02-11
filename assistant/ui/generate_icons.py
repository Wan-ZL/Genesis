#!/usr/bin/env python3
"""Generate PWA icons for Genesis.

Creates PNG icons at various sizes required for PWA manifest.
Uses PIL (Pillow) to generate icons programmatically.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]


def create_genesis_icon(size: int, maskable: bool = False) -> Image.Image:
    """Create Genesis icon with 'G' branding.

    Args:
        size: Icon size in pixels (square)
        maskable: If True, add safe zone padding for maskable icons

    Returns:
        PIL Image object
    """
    # Calculate padding for maskable icons (safe zone = 80% of total)
    padding = int(size * 0.1) if maskable else 0
    inner_size = size - (2 * padding)

    # Create image with transparency
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw gradient background circle
    center = size // 2
    radius = inner_size // 2

    # Create gradient effect with multiple circles
    for i in range(radius, 0, -2):
        # Gradient from blue (#3b82f6) to purple (#764ba2)
        ratio = i / radius
        r = int(59 + (118 - 59) * (1 - ratio))
        g = int(130 + (75 - 130) * (1 - ratio))
        b = int(246 + (162 - 246) * (1 - ratio))

        draw.ellipse(
            [center - i, center - i, center + i, center + i],
            fill=(r, g, b, 255)
        )

    # Draw 'G' letter in white
    # Use a large font size relative to icon size
    font_size = int(inner_size * 0.5)

    try:
        # Try to use system font
        font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', font_size)
    except:
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', font_size)
        except:
            # Fallback to default font
            font = ImageFont.load_default()

    # Draw 'G'
    text = 'G'

    # Get text bounding box for centering
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    text_x = center - text_width // 2
    text_y = center - text_height // 2 - int(font_size * 0.1)  # Slight adjustment

    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    return img


def generate_all_icons():
    """Generate all required icon sizes."""
    icons_dir = Path(__file__).parent / 'icons'
    icons_dir.mkdir(exist_ok=True)

    sizes = [72, 96, 128, 144, 152, 192, 384, 512]

    print('Generating PWA icons...')

    for size in sizes:
        icon = create_genesis_icon(size)
        icon_path = icons_dir / f'icon-{size}x{size}.png'
        icon.save(icon_path, 'PNG')
        print(f'✓ Generated {icon_path.name}')

    # Generate maskable icon (512x512 with safe zone)
    maskable = create_genesis_icon(512, maskable=True)
    maskable_path = icons_dir / 'icon-512x512-maskable.png'
    maskable.save(maskable_path, 'PNG')
    print(f'✓ Generated {maskable_path.name} (maskable)')

    # Generate badge icon (smaller, for notifications)
    badge = create_genesis_icon(72)
    badge_path = icons_dir / 'badge-72x72.png'
    badge.save(badge_path, 'PNG')
    print(f'✓ Generated {badge_path.name} (badge)')

    # Generate apple-touch-icon (180x180)
    apple_icon = create_genesis_icon(180)
    apple_icon_path = icons_dir / 'apple-touch-icon.png'
    apple_icon.save(apple_icon_path, 'PNG')
    print(f'✓ Generated {apple_icon_path.name} (iOS)')

    print(f'\n✓ All icons generated in {icons_dir}')


if __name__ == '__main__':
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print('Error: Pillow is required to generate icons.')
        print('Install with: pip install Pillow')
        exit(1)

    generate_all_icons()
