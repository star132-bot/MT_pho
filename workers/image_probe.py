#!/usr/bin/env python3
"""Credential-free Pillow probe for one downloaded scanner asset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import warnings


MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class ProbeFailure(RuntimeError):
    def __init__(self, code: str, width: int | None = None, height: int | None = None):
        super().__init__(code)
        self.code = code
        self.width = width
        self.height = height


def emit(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
    sys.stdout.flush()


def oriented_size(width: int, height: int, orientation: int) -> tuple[int, int]:
    return (height, width) if orientation in {5, 6, 7, 8} else (width, height)


def inspect(path: Path, max_pixels: int, max_edge: int) -> dict[str, object]:
    try:
        from PIL import Image, ImageFile, UnidentifiedImageError, __version__
    except ImportError as error:
        raise RuntimeError("pillow_unavailable") from error

    Image.MAX_IMAGE_PIXELS = max_pixels
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    width: int | None = None
    height: int | None = None
    image_format = ""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path, formats=("JPEG", "PNG", "WEBP")) as image:
                image_format = str(image.format or "").upper()
                raw_width, raw_height = image.size
                if raw_width < 1 or raw_height < 1:
                    raise ProbeFailure("image_size_limit_exceeded")
                if raw_width > max_edge or raw_height > max_edge or raw_width * raw_height > max_pixels:
                    raise ProbeFailure("image_size_limit_exceeded", raw_width, raw_height)
                if int(getattr(image, "n_frames", 1)) != 1:
                    raise ProbeFailure("multiple_frames_not_allowed", raw_width, raw_height)
                orientation = int(image.getexif().get(0x0112, 1) or 1)
                width, height = oriented_size(raw_width, raw_height, orientation)

            with Image.open(path, formats=("JPEG", "PNG", "WEBP")) as image:
                image.verify()

            with Image.open(path, formats=("JPEG", "PNG", "WEBP")) as image:
                if str(image.format or "").upper() != image_format:
                    raise ProbeFailure("decoded_format_mismatch", width, height)
                if int(getattr(image, "n_frames", 1)) != 1:
                    raise ProbeFailure("multiple_frames_not_allowed", width, height)
                image.load()
    except ProbeFailure:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ProbeFailure("decompression_bomb", width, height) from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise ProbeFailure("image_decode_failed", width, height) from error

    mime_type = MIME_BY_FORMAT.get(image_format)
    if mime_type is None or width is None or height is None:
        raise ProbeFailure("decoded_format_mismatch", width, height)
    return {
        "status": "ok",
        "mime_type": mime_type,
        "width": width,
        "height": height,
        "engine_version": str(__version__)[:120],
    }


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--max-pixels", type=int, required=True)
    parser.add_argument("--max-edge", type=int, required=True)
    parser.add_argument("path")
    return parser


def main() -> int:
    try:
        arguments = argument_parser().parse_args()
        path = Path(arguments.path)
        if not path.is_file() or path.is_symlink():
            raise ProbeFailure("image_decode_failed")
        payload = inspect(path, max(1, arguments.max_pixels), max(1, arguments.max_edge))
        emit(payload)
        return 0
    except ProbeFailure as error:
        emit({
            "status": "failed",
            "result_code": error.code,
            "width": error.width,
            "height": error.height,
        })
        return 2
    except Exception:
        emit({"status": "error", "result_code": "image_probe_unavailable"})
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
