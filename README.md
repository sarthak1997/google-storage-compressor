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

---

## Real-World Case Study

### The Problem

A personal Gmail account with **51.4 GB** used against a **15 GB** free limit. Account was locked — couldn't send emails, backup photos, or save to Drive.

**Storage breakdown:**
| Service | Size |
|---------|------|
| Google Photos | 42.8 GB |
| Google Drive | 8.6 GB (videos, photos, documents) |
| Gmail | ~0.25 GB |

### Step-by-Step Solution

#### Step 1: Audit (5 minutes)

```bash
python compressor.py audit
```

Output revealed Google Photos was 83% of the problem — years of iPhone photos/videos uploaded at original quality.

#### Step 2: Export via Google Takeout (30 minutes)

1. Went to https://takeout.google.com
2. Exported **Google Drive** (1 zip, 8.3 GB)
3. Exported **Google Photos** (21 zips × 2 GB each, 42.8 GB total)

#### Step 3: Compress Drive files (30 minutes)

```bash
# Extract
unzip takeout-drive.zip -d ~/drive_takeout

# Compress
python compressor.py compress ~/drive_takeout
```

Result: **8.3 GB → 1.8 GB** (78% reduction)

#### Step 4: Compress Photos (4 hours overnight)

Processed 21 zips one at a time (to conserve disk space):
- Extract zip → compress → delete zip → next

```bash
python compressor.py compress ~/photos_takeout
```

Result: **42.8 GB → 9.3 GB** (78% reduction)

**Final compressed sizes:**
| | Original | Compressed | Reduction |
|---|---|---|---|
| Drive | 8.3 GB | 1.8 GB | 78% |
| Photos | 42.8 GB | 9.3 GB | 78% |
| **Total** | **51.4 GB** | **11.1 GB** | **78%** |

#### Step 5: Delete originals from Google (10 minutes)

1. Google Photos → Select All → Delete → Empty Trash
2. Google Drive → Select All → Delete → Empty Trash
3. Waited ~10 minutes for quota to update

#### Step 6: Re-upload compressed files (2 hours)

```bash
# Drive (1.8 GB)
python compressor.py upload-drive ~/drive_takeout/Takeout/Drive

# Photos (9.3 GB)
python compressor.py upload-photos ~/photos_takeout/Takeout/Google\ Photos
```

#### Final Result

```
📊 FINAL STORAGE CHECK
  Total used:     6.62 GB / 15 GB
  Drive:          1.80 GB
  Gmail+Photos:   4.82 GB
  Free:           8.38 GB  ✅
```

Google further compressed our uploads (Photos "Storage saver" rules), bringing the final usage to just **6.62 GB** — well under the 15 GB limit.

### Key Learnings

1. **Google Photos is usually the culprit** — not Drive or Gmail. Always audit first.
2. **Google Takeout is the best way to bulk-download** — faster and more reliable than API downloads.
3. **H.265 CRF 32 is the sweet spot** — 50-70% smaller with no visible quality difference.
4. **Process zips one at a time** if disk space is limited — extract, compress, delete zip, repeat.
5. **Google applies additional compression** on upload — final cloud size may be smaller than local.
6. **Network resilience matters** — the upload took hours across WiFi changes, VPN switches, and commuting. Auto-pause/resume saved the day.
7. **iPhone HEIC files** don't need compression — they're already efficient. The script correctly skips them.

### Timeline

| Time | Action |
|------|--------|
| Day 1, 9:30 PM | Started — audited storage, identified Photos as the problem |
| Day 1, 10:00 PM | Began Takeout exports |
| Day 1, 10:30 PM | Compressed Drive takeout (8.3 GB → 1.8 GB) |
| Day 1, 11:00 PM | Started Photos compression, went to sleep |
| Day 2, 4:30 AM | Overnight job completed all 21 zips |
| Day 2, 10:00 AM | Verified data integrity, deleted originals from Google |
| Day 2, 11:00 AM | Started re-upload (Drive) |
| Day 2, 4:30 PM | Drive upload complete |
| Day 2, 5:00 PM | Started Photos upload |
| Day 2, 11:30 PM | Photos upload complete |
| Day 3, 10:30 AM | Final verification — **6.62 GB / 15 GB** ✅ |
