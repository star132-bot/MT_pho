#!/usr/bin/env python3
"""Verify the loading contract for the public static image surfaces."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
STATIC_ART_PREFIX = "assets/art/"


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        if image.read(2) != b"\xff\xd8":
            raise AssertionError(f"{path} is not a JPEG image")
        while True:
            byte = image.read(1)
            if not byte:
                raise AssertionError(f"{path} has no JPEG dimensions")
            if byte != b"\xff": continue
            marker = image.read(1)
            while marker == b"\xff": marker = image.read(1)
            if marker in (b"\x00", b"\xd8"): continue
            length = struct.unpack(">H", image.read(2))[0]
            if marker[0] in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
                _precision, height, width = struct.unpack(">BHH", image.read(5))
                return width, height
            image.seek(length - 2, 1)


class ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        self.images.append({key: value or "" for key, value in attrs})


def read_images(relative_path: str) -> list[dict[str, str]]:
    parser = ImageParser()
    parser.feed((ROOT / relative_path).read_text(encoding="utf-8"))
    return parser.images


def assert_static_dimensions(images: list[dict[str, str]], label: str) -> None:
    static_images = [
        image for image in images if image.get("src", "").startswith(STATIC_ART_PREFIX)
    ]
    if not static_images:
        raise AssertionError(f"{label} has no static art images")
    for image in static_images:
        width, height = jpeg_dimensions(ROOT / image["src"])
        for key, expected in {"width": str(width), "height": str(height)}.items():
            if image.get(key) != expected:
                raise AssertionError(
                    f"{label} image {image.get('src')} has {key}={image.get(key)!r}; "
                    f"expected {expected!r}"
                )


def main() -> None:
    index_images = read_images("index.html")
    assert_static_dimensions(index_images, "index.html")

    marquee_images = [
        image
        for image in index_images
        if image.get("src", "").startswith(STATIC_ART_PREFIX)
        and "data-home-statement-image" not in image
    ]
    if not marquee_images:
        raise AssertionError("index.html marquee image contract is missing")
    for image in marquee_images:
        if image.get("loading") != "lazy" or image.get("decoding") != "async":
            raise AssertionError(
                f"index.html marquee image {image.get('src')} must be lazy and async"
            )

    statement_images = [
        image for image in index_images if "data-home-statement-image" in image
    ]
    if not statement_images:
        raise AssertionError("index.html statement image contract is missing")
    for image in statement_images:
        if image.get("loading") != "lazy" or image.get("decoding") != "async":
            raise AssertionError(
                f"index.html statement image {image.get('src')} must be lazy and async"
            )

    about_images = read_images("about.html")
    assert_static_dimensions(about_images, "about.html")
    about_image = next(
        (
            image
            for image in about_images
            if image.get("src", "").startswith(STATIC_ART_PREFIX)
        ),
        None,
    )
    if about_image is None or about_image.get("decoding") != "async":
        raise AssertionError("about.html hero image must use async decoding")
    if about_image.get("loading") == "lazy":
        raise AssertionError("about.html hero image must remain eager")

    print("public_image_dimensions=yes")
    print("public_home_images_lazy_async=yes")
    print("public_about_hero_async_eager=yes")


if __name__ == "__main__":
    main()
