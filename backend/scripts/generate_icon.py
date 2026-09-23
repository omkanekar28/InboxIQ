"""
Generate high-quality icon files (ICO and PNG) for InboxIQ.
"""
from PIL import Image, ImageDraw
from pathlib import Path


def create_inboxiq_icon(size: int = 256) -> Image.Image:
    scale = size / 40.0
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Colors
    bg_fill = (17, 22, 17, 255)         # #111611
    green_stroke = (0, 255, 65, 230)    # #00FF41
    env_fill = (10, 10, 10, 255)        # #0A0A0A
    node_glow = (0, 255, 65, 90)        # Glow ring

    stroke_w = max(2, int(1.8 * scale))

    # 1. Outer rounded container badge
    pad = int(2 * scale)
    corner_r = int(8 * scale)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=corner_r,
        fill=bg_fill,
        outline=green_stroke,
        width=stroke_w,
    )

    # 2. Mail envelope shape
    env_x1 = int(9 * scale)
    env_y1 = int(12 * scale)
    env_x2 = int(31 * scale)
    env_y2 = int(28 * scale)
    env_r = max(2, int(2.5 * scale))
    draw.rounded_rectangle(
        [env_x1, env_y1, env_x2, env_y2],
        radius=env_r,
        fill=env_fill,
        outline=green_stroke,
        width=stroke_w,
    )

    # Envelope flap lines
    center_x = size // 2
    flap_peak_y = int(22 * scale)
    draw.line([(env_x1, env_y1 + int(1.5 * scale)), (center_x, flap_peak_y)], fill=green_stroke, width=stroke_w)
    draw.line([(center_x, flap_peak_y), (env_x2, env_y1 + int(1.5 * scale))], fill=green_stroke, width=stroke_w)

    # 3. Intelligence pulse node in center
    pulse_cx = center_x
    pulse_cy = int(20 * scale)

    # Outer glow ring
    ring_r = int(4.5 * scale)
    draw.ellipse(
        [pulse_cx - ring_r, pulse_cy - ring_r, pulse_cx + ring_r, pulse_cy + ring_r],
        outline=node_glow,
        width=max(1, int(scale)),
    )

    # Inner solid green core
    core_r = max(2, int(2.0 * scale))
    draw.ellipse(
        [pulse_cx - core_r, pulse_cy - core_r, pulse_cx + core_r, pulse_cy + core_r],
        fill=green_stroke,
    )

    return image


def main():
    packaging_dir = Path(__file__).resolve().parents[2] / "packaging"
    packaging_dir.mkdir(parents=True, exist_ok=True)

    img_256 = create_inboxiq_icon(256)
    png_path = packaging_dir / "icon.png"
    img_256.save(png_path, format="PNG")
    print(f"Saved PNG to {png_path}")

    ico_path = packaging_dir / "icon.ico"
    # Create multi-size ICO
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    icon_images = [create_inboxiq_icon(s[0]) for s in sizes]
    icon_images[0].save(
        ico_path,
        format="ICO",
        sizes=sizes,
        append_images=icon_images[1:],
    )
    print(f"Saved multi-resolution ICO to {ico_path}")


if __name__ == "__main__":
    main()
