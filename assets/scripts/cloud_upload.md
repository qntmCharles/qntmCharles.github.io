# Cloud Upload Script

Use `publish_cloud_entry.py` after your webserver has authenticated the user.
The script trusts its caller; GitHub OAuth should happen in the web app before
this script is invoked.

## Local Dry Run

```bash
python3 assets/scripts/publish_cloud_entry.py \
  --image /path/to/cloud.jpeg \
  --cloud "Cirrus" \
  --location "Cambridge" \
  --date 2026-05-30 \
  --dry-run
```

This validates the upload, builds the caption, chooses the destination filename,
and prints the planned change without touching the repo.

## Local Write Without Git

```bash
python3 assets/scripts/publish_cloud_entry.py \
  --image /path/to/cloud.jpeg \
  --cloud "Cirrus" \
  --location "Cambridge" \
  --date 2026-05-30
```

This writes a normalized image into `assets/img/clouds/` and inserts a new entry
at the top of `_data/clouds.yml`. JPEG uploads are rotated according to EXIF
orientation and EXIF metadata is stripped by default. Use `--keep-exif` if you
want to preserve metadata.

## Authenticated Server Publish

From a clean server clone with Git credentials configured:

```bash
python3 assets/scripts/publish_cloud_entry.py \
  --image /tmp/uploaded-cloud.jpeg \
  --cloud "Cirrus" \
  --location "Cambridge" \
  --date 2026-05-30 \
  --push
```

`--push` runs `git pull --rebase`, writes the media/data changes, commits them,
and pushes to the configured remote. If the clone has uncommitted changes, the
script refuses to publish.

You can also pass a complete caption instead of separate fields:

```bash
python3 assets/scripts/publish_cloud_entry.py \
  --image /tmp/uploaded-cloud.jpeg \
  --caption "Cirrus. Cambridge. 30th May 2026." \
  --date 2026-05-30 \
  --push
```
