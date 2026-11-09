from pathlib import Path

from PIL import Image, ImageOps

BUILD_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILD_DIR.parents[1]
SOURCE_IMAGE = PROJECT_ROOT / "logo.png"
OUTPUT_ICON = BUILD_DIR / "FECArcade.ico"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main():
    source = Image.open(SOURCE_IMAGE).convert("RGBA")
    canvas = Image.new("RGBA", (256, 256), (24, 26, 45, 255))
    logo = ImageOps.contain(source, (224, 224), Image.Resampling.LANCZOS)
    position = ((256 - logo.width) // 2, (256 - logo.height) // 2)
    canvas.alpha_composite(logo, position)
    canvas.save(OUTPUT_ICON, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    print(OUTPUT_ICON)


if __name__ == "__main__":
    main()
