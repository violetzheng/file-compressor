# File Squasher

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

Open http://localhost:5000, upload a file to squash. Pick a target file size and click **Compress & download**.

## How it works

- **Analyze** (`POST /api/analyze`): compresses the file at maximum settings once to find the floor, and returns `{original_size, min_size, file_type}`.
- **Compress** (`POST /api/compress`, fields `file` + `target` in bytes):
  - **JPEG / WebP** — binary-searches the quality setting (1–95) for the highest quality that fits under the target.
  - **PNG** — PNG is lossless, so the search runs over palette size (8–256 colors) with optimized encoding instead.
  - **PDF** — tries Ghostscript.  
  - If the file is already under the target size, it's returned untouched.

The result is streamed back as `<name>-compressed.<ext>` with the original type preserved.

## Notes
- Upload cap is 100 MB (`MAX_CONTENT_LENGTH` in `app.py`).
