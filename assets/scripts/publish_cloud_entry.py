#!/usr/bin/env python3
"""Add a cloud entry, normalize media, and optionally commit/push it.

This script is intended to be called by an authenticated web endpoint, but it is
also safe to test locally. By default it writes files only; use --commit or
--push when running from a clean server clone with Git credentials configured.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError


REPO_ROOT = Path(__file__).resolve().parents[2]
CLOUD_DATA_PATH = Path("_data/clouds.yml")
CLOUD_MEDIA_DIR = Path("assets/img/clouds")
LOCK_PATH = Path(".cloud-upload.lock")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
ORIENTATION_TAG = next(key for key, value in ExifTags.TAGS.items() if value == "Orientation")

DATA_HEADER = [
    "# Cloudspotting log entries rendered by _pages/cloud_log.md.",
    "# Each row can contain one or more image/video items.",
]


class CloudPublishError(Exception):
    """Raised for expected upload/publish failures."""


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.handle = self.path.open("w")
        fcntl.flock(self.handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.handle is None:
            return
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def posix_path(path: Path) -> str:
    return PurePosixPath(path.as_posix()).as_posix()


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def load_cloud_entries(data_path: Path) -> list[dict[str, Any]]:
    if not data_path.exists():
        return []

    with data_path.open() as handle:
        entries = yaml.safe_load(handle) or []

    if not isinstance(entries, list):
        raise CloudPublishError(f"{data_path} must contain a YAML list")

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or not isinstance(entry.get("caption"), str):
            raise CloudPublishError(f"Entry {index} in {data_path} is missing a caption")
        rows = entry.get("rows")
        if not isinstance(rows, list) or not rows:
            raise CloudPublishError(f"Entry {index} in {data_path} is missing rows")

    return entries


def write_cloud_entries(data_path: Path, entries: list[dict[str, Any]]) -> None:
    lines = list(DATA_HEADER)
    for entry in entries:
        lines.append(f"- caption: {yaml_quote(entry['caption'])}")
        lines.append("  rows:")
        for row in entry["rows"]:
            for index, media in enumerate(row):
                prefix = "    -" if index == 0 else "     "
                lines.append(f"{prefix} - path: {yaml_quote(media['path'])}")
                lines.append(f"        type: {yaml_quote(media['type'])}")

    data_path.write_text("\n".join(lines) + "\n")


def ordinal_suffix(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_display_date(date: dt.date) -> str:
    return f"{date.day}{ordinal_suffix(date.day)} {date:%B} {date.year}"


def strip_sentence_stop(value: str) -> str:
    return value.strip().rstrip(".").strip()


def build_caption(args: argparse.Namespace) -> str:
    if args.caption:
        caption = args.caption.strip()
    else:
        if not args.cloud or not args.location or not args.date:
            raise CloudPublishError("Provide --caption, or provide --cloud, --location, and --date")
        date = parse_date(args.date)
        caption = (
            f"{strip_sentence_stop(args.cloud)}. "
            f"{strip_sentence_stop(args.location)}. "
            f"{format_display_date(date)}."
        )

    if not caption:
        raise CloudPublishError("Caption must not be empty")
    return caption


def parse_date(value: str) -> dt.date:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CloudPublishError(f"Date must use YYYY-MM-DD format: {value}") from exc


def infer_media_type(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    raise CloudPublishError(
        f"Unsupported upload type {extension!r}; use one of "
        f"{sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)}"
    )


def output_extension(source: Path, media_type: str) -> str:
    extension = source.suffix.lower()
    if media_type == "image" and extension in JPEG_EXTENSIONS:
        return ".jpeg"
    return extension


def next_media_path(
    cloud_media_dir: Path,
    date: dt.date | None,
    source: Path,
    media_type: str,
    reserved_paths: set[Path],
) -> Path:
    extension = output_extension(source, media_type)
    stem = date.isoformat() if date else source.stem

    for suffix in [""] + [f"-{index}" for index in range(2, 1000)]:
        candidate = cloud_media_dir / f"{stem}{suffix}{extension}"
        if not candidate.exists() and candidate not in reserved_paths:
            return candidate

    raise CloudPublishError(f"Could not find an unused filename for {stem}{extension}")


def normalize_image(source: Path, destination: Path, keep_exif: bool) -> None:
    try:
        with Image.open(source) as image:
            icc_profile = image.info.get("icc_profile")
            normalized = ImageOps.exif_transpose(image)

            save_kwargs: dict[str, Any] = {}
            if destination.suffix.lower() in JPEG_EXTENSIONS:
                if normalized.mode not in {"RGB", "L"}:
                    normalized = normalized.convert("RGB")
                save_kwargs.update({"quality": 95, "optimize": True})

            if keep_exif:
                exif = image.getexif()
                if ORIENTATION_TAG in exif:
                    exif[ORIENTATION_TAG] = 1
                save_kwargs["exif"] = exif.tobytes()
            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

            normalized.save(destination, **save_kwargs)
    except UnidentifiedImageError as exc:
        raise CloudPublishError(f"Could not read image file: {source}") from exc


def copy_media(source: Path, destination: Path, media_type: str, keep_exif: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if media_type == "image":
        normalize_image(source, destination, keep_exif)
    else:
        shutil.copy2(source, destination)


def run_git(args: list[str], repo_root: Path, dry_run: bool) -> None:
    command = ["git", *args]
    if dry_run:
        print("$ " + " ".join(command))
        return
    subprocess.run(command, cwd=repo_root, check=True)


def git_output(args: list[str], repo_root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def ensure_clean_worktree(repo_root: Path) -> None:
    status = git_output(["status", "--porcelain"], repo_root)
    if status:
        raise CloudPublishError(
            "Git worktree is not clean. Commit/stash local changes before using --commit or --push."
        )


def git_publish(
    repo_root: Path,
    changed_paths: list[Path],
    message: str,
    push: bool,
    dry_run: bool,
) -> None:
    run_git(["add", *[posix_path(path) for path in changed_paths]], repo_root, dry_run)
    run_git(["commit", "-m", message], repo_root, dry_run)
    if push:
        run_git(["push"], repo_root, dry_run)


def build_entry(media_paths: list[Path], media_types: list[str], repo_root: Path) -> dict[str, Any]:
    row = []
    for media_path, media_type in zip(media_paths, media_types):
        row.append(
            {
                "path": posix_path(media_path.relative_to(repo_root)),
                "type": media_type,
            }
        )
    return {"rows": [row]}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        action="append",
        type=Path,
        required=True,
        help="Image or video file to publish. Repeat to add multiple media files to one entry.",
    )
    parser.add_argument("--caption", help="Complete caption to place under the media.")
    parser.add_argument("--cloud", help="Cloud description, used with --location and --date.")
    parser.add_argument("--location", help="Location text, used with --cloud and --date.")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format, used in caption and destination filename.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Website repository root.",
    )
    parser.add_argument(
        "--keep-exif",
        action="store_true",
        help="Keep EXIF metadata after normalizing orientation. Default strips EXIF for privacy.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show planned changes without writing files or running Git.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit the new media and YAML update after writing them.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Pull, commit, and push. Intended for the authenticated server path.",
    )
    parser.add_argument(
        "--message",
        help="Git commit message. Defaults to a date-based cloud-photo message.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    data_path = repo_path(CLOUD_DATA_PATH, repo_root)
    cloud_media_dir = repo_path(CLOUD_MEDIA_DIR, repo_root)
    lock_path = repo_path(LOCK_PATH, repo_root)
    date = parse_date(args.date) if args.date else None
    caption = build_caption(args)

    if args.push:
        args.commit = True

    if args.commit and not args.dry_run:
        ensure_clean_worktree(repo_root)

    with FileLock(lock_path):
        if args.push:
            run_git(["pull", "--rebase"], repo_root, args.dry_run)

        entries = load_cloud_entries(data_path)

        destination_paths: list[Path] = []
        reserved_paths: set[Path] = set()
        media_types: list[str] = []
        for source in args.image:
            source = source.resolve()
            if not source.exists():
                raise CloudPublishError(f"Upload file does not exist: {source}")
            media_type = infer_media_type(source)
            destination = next_media_path(cloud_media_dir, date, source, media_type, reserved_paths)
            reserved_paths.add(destination)
            destination_paths.append(destination)
            media_types.append(media_type)

        new_entry = build_entry(destination_paths, media_types, repo_root)
        new_entry["caption"] = caption

        print("Prepared cloud entry:")
        print(f"  caption: {caption}")
        for source, destination in zip(args.image, destination_paths):
            print(f"  media: {source} -> {destination.relative_to(repo_root)}")

        if args.dry_run:
            print("\nDry run only; no files were changed.")
        else:
            for source, destination, media_type in zip(args.image, destination_paths, media_types):
                copy_media(source.resolve(), destination, media_type, args.keep_exif)
            entries.insert(0, new_entry)
            write_cloud_entries(data_path, entries)
            print(f"\nUpdated {data_path.relative_to(repo_root)}")

        changed_paths = [path.relative_to(repo_root) for path in destination_paths]
        changed_paths.append(CLOUD_DATA_PATH)

        if args.commit:
            commit_message = args.message
            if not commit_message:
                label = date.isoformat() if date else destination_paths[0].stem
                commit_message = f"Add cloud photo for {label}"
            git_publish(repo_root, changed_paths, commit_message, args.push, args.dry_run)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except CloudPublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
