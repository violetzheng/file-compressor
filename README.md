# Squash — minimal file compressor

Compress JPG, PNG, WebP, and PDF files down to a size you choose, keeping the same file type.

## Setup

```bash
pip install -r requirements.txt
```

PDF compression uses Ghostscript, so install it if you want PDF support:

```bash
# macOS
brew install ghostscript

# Debian / Ubuntu
sudo apt install ghostscript

# Windows: download from https://ghostscript.com/releases/gsdnld.html
```

Images work with no extra installs.

## Run

```bash
python app.py
```

Open http://localhost:5000, drop a file in, and the app shows the smallest size it can reach. Pick a target with the slider (or type a KB value) and click **Compress & download**.

## How it works

- **Analyze** (`POST /api/analyze`): compresses the file at maximum settings once to find the floor, and returns `{original_size, min_size, file_type}`.
- **Compress** (`POST /api/compress`, fields `file` + `target` in bytes):
  - **JPEG / WebP** — binary-searches the quality setting (1–95) for the highest quality that fits under the target.
  - **PNG** — PNG is lossless, so the search runs over palette size (8–256 colors) with optimized encoding instead.
  - **PDF** — tries Ghostscript presets from `/prepress` down to `/screen` and returns the highest-quality result that fits; if none fit, you get the smallest achievable.
  - If the file is already under the target, it's returned untouched.

The result is streamed back as `<name>-compressed.<ext>` with the original type preserved.

## Notes

- The target is a ceiling: results land at or just under it, never over (unless the target is below the achievable floor, in which case you get the floor).
- Upload cap is 100 MB (`MAX_CONTENT_LENGTH` in `app.py`).
- This is a dev server setup; put it behind gunicorn/nginx for real deployment.
