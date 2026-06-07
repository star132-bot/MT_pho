from pathlib import Path
import json
from PIL import Image, ImageEnhance, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tmp" / "art-source"
OUT = ROOT / "assets" / "art"
OUT.mkdir(parents=True, exist_ok=True)


def crop_cover(image, size, anchor=(0.5, 0.5)):
    image = ImageOps.exif_transpose(image).convert("RGB")
    target_w, target_h = size
    source_w, source_h = image.size
    source_ratio = source_w / source_h
    target_ratio = target_w / target_h

    if source_ratio > target_ratio:
        crop_h = source_h
        crop_w = int(crop_h * target_ratio)
    else:
        crop_w = source_w
        crop_h = int(crop_w / target_ratio)

    max_left = source_w - crop_w
    max_top = source_h - crop_h
    left = int(max_left * anchor[0])
    top = int(max_top * anchor[1])

    image = image.crop((left, top, left + crop_w, top + crop_h))
    return image.resize(size, Image.Resampling.LANCZOS)


def resize_max(image, max_long_side=1800):
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    long_side = max(width, height)
    if long_side <= max_long_side:
        return image

    scale = max_long_side / long_side
    size = (int(width * scale), int(height * scale))
    return image.resize(size, Image.Resampling.LANCZOS)


def finish(image, name, *, monochrome=False, saturation=0.9, contrast=1.04, brightness=0.98):
    if monochrome:
        image = ImageOps.grayscale(image)
        image = ImageEnhance.Contrast(image).enhance(1.16)
        image = ImageEnhance.Brightness(image).enhance(0.96)
        image = ImageOps.autocontrast(image, cutoff=1)
        image = image.convert("RGB")
    else:
        image = ImageEnhance.Color(image).enhance(saturation)
        image = ImageEnhance.Contrast(image).enhance(contrast)
        image = ImageEnhance.Brightness(image).enhance(brightness)

    image.save(OUT / name, quality=88, optimize=True, progressive=True)


def ratio_name(width, height):
    ratio = width / height
    candidates = {
        "square": 1 / 1,
        "portrait": 4 / 5,
        "classic": 3 / 2,
        "wide": 16 / 9,
        "tall": 1 / 2,
    }
    return min(candidates, key=lambda key: abs(ratio - candidates[key]))


def save_and_describe(image, name, **kwargs):
    finish(image, name, **kwargs)
    width, height = image.size
    print(f"Wrote {OUT / name}")
    return {
        "src": f"assets/art/{name}",
        "width": width,
        "height": height,
        "recommendedRatio": ratio_name(width, height),
    }


def main():
    metadata = {}

    # Hero is a layout image and may be intentionally cropped.
    hero_image = Image.open(SOURCE / "hero-source.jpg")
    hero_image = crop_cover(hero_image, (1800, 2200), (0.46, 0.48))
    metadata["hero-ci-jian.jpg"] = save_and_describe(
        hero_image,
        "hero-ci-jian.jpg",
        monochrome=True,
        contrast=1.22,
        brightness=0.68,
    )

    assets = [
        ("abstract-01-source.jpg", "abstract-01.jpg", True, 0.0),
        ("abstract-02-source.jpg", "abstract-02.jpg", True, 0.0),
        ("abstract-03-source.jpg", "abstract-03.jpg", True, 0.0),
        ("concrete-01-source.jpg", "concrete-01.jpg", False, 0.78),
        ("concrete-02-source.jpg", "concrete-02.jpg", False, 0.78),
        ("concrete-03-source.jpg", "concrete-03.jpg", False, 0.78),
    ]

    for source_name, output_name, monochrome, saturation in assets:
        source_path = SOURCE / source_name
        if not source_path.exists():
            raise FileNotFoundError(f"Missing source image: {source_path}")
        image = Image.open(source_path)
        image = resize_max(image)
        metadata[output_name] = save_and_describe(image, output_name, monochrome=monochrome, saturation=saturation)

    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Wrote {OUT / 'metadata.json'}")


if __name__ == "__main__":
    main()
