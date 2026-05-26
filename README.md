# Google Storage Compressor

Reduce your Google Drive & Photos storage from 50GB+ to under 15GB without visible quality loss.

Uses H.265/HEVC for videos and optimized JPEG with resize for photos. Handles the full pipeline: audit → download (via Takeout) → compress → re-upload.

## Results

| | Before | After |
|---|---|---|
| Storage used | 51.4 GB | 6.6 GB |
| Quality | Original | Visually identical |

## Prerequisites

- **Python 3.10+**
- **FFmpeg** — `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Linux)
- **Google Cloud Project** with OAuth2 credentials

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create Google Cloud OAuth2 credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable these APIs:
   - **Google Drive API**
   - **Photos Library API**
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON
5. Rename to `credentials.json` and place in this folder
6. Go to **APIs & Services → OAuth consent screen**
   - Add your email as a test user, or publish the app

## Usage

### Audit your storage

```bash
python compressor.py audit
```

Shows breakdown of what's using your Google storage (Drive vs Gmail vs Photos) and lists largest files.

### Compress local files

Download your data via [Google Takeout](https://takeout.google.com), then compress:

```bash
python compressor.py compress ~/path/to/takeout/folder
```

This compresses in-place:
- **Videos** → H.265, CRF 32, medium preset (4 parallel threads)
- **Photos** → JPEG quality 70, max 2048px (8 parallel threads)

### Upload to Google Drive

```bash
python compressor.py upload-drive ~/path/to/drive/folder
```

Preserves folder structure. Skips already-uploaded files (safe to re-run). Auto-pauses on network disconnect.

### Upload to Google Photos

```bash
python compressor.py upload-photos ~/path/to/photos/folder
```

Uploads in batches of 20. Tracks progress for resume. Auto-pauses on disconnect.

## Configuration

Override defaults via environment variables:

```bash
CRF=28 JPEG_QUALITY=82 MAX_PX=4096 python compressor.py compress ~/folder
```

| Variable | Default | Description |
|----------|---------|-------------|
| `CRF` | 32 | Video quality (23=high, 28=good, 32=compact, 35=low) |
| `JPEG_QUALITY` | 70 | Photo quality (50-95, higher=better) |
| `MAX_PX` | 2048 | Max photo dimension in pixels |

## Recommended Workflow

1. **Audit** — `python compressor.py audit` to see what's eating storage
2. **Export** — Use [Google Takeout](https://takeout.google.com) to download Drive and/or Photos
3. **Compress** — `python compressor.py compress ~/takeout_folder`
4. **Delete from Google** — Manually delete originals from Drive/Photos and empty trash
5. **Wait** — ~10 minutes for quota to update
6. **Re-upload** — Use `upload-drive` and `upload-photos` commands

## How it works

- **Videos**: Re-encoded with H.265/HEVC codec at CRF 32. This is the "visually transparent" sweet spot — 50-70% smaller with no perceptible quality difference.
- **Photos**: Resized to max 2048px and saved as optimized JPEG at quality 70. Indistinguishable on screens, only matters if printing large posters.
- **Other files** (PDFs, docs, etc.): Uploaded as-is, no compression needed.
- **Network resilience**: Scripts auto-pause on disconnect and resume when back online.
- **Resume support**: Safe to interrupt and re-run — skips already-uploaded files.

## License

MIT
