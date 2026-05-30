#!/usr/bin/env python3
"""Normalize EXIF orientation for cloud-log JPEGs.

By default this script only reports images with non-standard orientation tags.
Run with --write to rotate pixels into the displayed orientation and reset the
EXIF orientation tag to 1. Originals are copied to the backup directory first.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import ExifTags, Image, ImageOps


IMAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = IMAGE_DIR.parents[2]
DEFAULT_BACKUP_DIR = REPO_ROOT / "_backups" / "cloud_image_orientation"
ORIENTATION_TAG = next(key for key, value in ExifTags.TAGS.items() if value == "Orientation")
IMAGE_EXTENSIONS = {".jpg", ".jpeg"}


def iter_images(image_dir: Path):
    for path in sorted(image_dir.iterdir()):
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def get_orientation(path: Path) -> int:
    with Image.open(path) as image:
        return image.getexif().get(ORIENTATION_TAG, 1)


def normalize_image(path: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / path.name
    if not backup_path.exists():
        shutil.copy2(path, backup_path)

    with Image.open(path) as image:
        exif = image.getexif()
        normalized = ImageOps.exif_transpose(image)
        exif[ORIENTATION_TAG] = 1
        normalized.save(path, quality=95, exif=exif.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=IMAGE_DIR,
        help="Directory containing cloud images.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help="Directory for original images when using --write.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite files in place after creating backups.",
    )
    args = parser.parse_args()

    candidates = []
    for path in iter_images(args.image_dir):
        orientation = get_orientation(path)
        if orientation != 1:
            candidates.append((path, orientation))

    if not candidates:
        print("No images with non-standard EXIF orientation tags found.")
        return 0

    action = "Normalizing" if args.write else "Would normalize"
    for path, orientation in candidates:
        print(f"{action}: {path} (orientation={orientation})")
        if args.write:
            normalize_image(path, args.backup_dir)

    if not args.write:
        print("\nRun again with --write to update these files.")
    else:
        print(f"\nBackups saved in {args.backup_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
