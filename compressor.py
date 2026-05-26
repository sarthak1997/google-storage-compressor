#!/usr/bin/env python3
"""
Google Storage Compressor — Reduce Google Drive & Photos storage without visible quality loss.

Usage:
    python compressor.py audit                    # Check what's using your storage
    python compressor.py compress <path>          # Compress a local folder (from Takeout)
    python compressor.py upload-drive <path>      # Upload folder to Google Drive
    python compressor.py upload-photos <path>     # Upload folder to Google Photos
"""

import os, sys, subprocess, time, json, zipfile, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import requests

# === CONFIG ===
CRF = os.environ.get('CRF', '32')
JPEG_QUALITY = int(os.environ.get('JPEG_QUALITY', '70'))
MAX_PX = int(os.environ.get('MAX_PX', '2048'))
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp'}
PHOTO_EXTS = {'.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.webp', '.heic'}
SKIP_EXTS = {'.json', '.html'}
SCOPES_DRIVE = ['https://www.googleapis.com/auth/drive']
SCOPES_PHOTOS = ['https://www.googleapis.com/auth/photoslibrary.appendonly']


def fmt(b):
    if b > 1024**3: return f"{b/1024**3:.2f} GB"
    if b > 1024**2: return f"{b/1024**2:.1f} MB"
    return f"{b/1024:.0f} KB"


def wait_for_network():
    """Pause until Google APIs are reachable."""
    import urllib.request
    attempts = 0
    while True:
        try:
            urllib.request.urlopen('https://photoslibrary.googleapis.com', timeout=5)
            return
        except:
            attempts += 1
            if attempts % 6 == 0:
                print(f"\n   ⏸️  Offline ({attempts*10}s)... Ctrl+C to stop", flush=True)
            else:
                print("   ⏸️  Waiting for connection...", end='\r', flush=True)
            time.sleep(10)
            if attempts > 30:
                resp = input("\n   Can't reach Google for 5 min. Retry? (y/n): ").strip().lower()
                if resp != 'y':
                    raise KeyboardInterrupt
                attempts = 0


# === AUTH ===
def auth_drive():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists('token_drive.json'):
        creds = Credentials.from_authorized_user_file('token_drive.json', SCOPES_DRIVE)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES_DRIVE)
            creds = flow.run_local_server(port=0)
        with open('token_drive.json', 'w') as f:
            f.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)


def auth_photos():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if os.path.exists('token_photos.json'):
        creds = Credentials.from_authorized_user_file('token_photos.json', SCOPES_PHOTOS)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES_PHOTOS)
            creds = flow.run_local_server(port=0)
        with open('token_photos.json', 'w') as f:
            json.dump({'token': creds.token, 'refresh_token': creds.refresh_token,
                       'token_uri': creds.token_uri, 'client_id': creds.client_id,
                       'client_secret': creds.client_secret, 'scopes': list(creds.scopes)}, f)
    return creds


# === AUDIT ===
def cmd_audit():
    """Show storage breakdown and largest files."""
    service = auth_drive()
    about = service.about().get(fields='storageQuota').execute()
    q = about['storageQuota']
    usage, limit = int(q['usage']), int(q['limit'])
    drive = int(q['usageInDrive'])

    print("=" * 50)
    print("📊 GOOGLE STORAGE AUDIT")
    print("=" * 50)
    print(f"  Total used:     {fmt(usage)} / {fmt(limit)}")
    print(f"  Drive:          {fmt(drive)}")
    print(f"  Gmail+Photos:   {fmt(usage - drive)}")
    print(f"  Free:           {fmt(limit - usage)}")
    print()

    # Top files
    resp = service.files().list(q="trashed=false", spaces='drive',
        fields='files(name, size, mimeType)', orderBy='quotaBytesUsed desc', pageSize=20).execute()
    print("📁 TOP 20 LARGEST FILES:")
    for i, f in enumerate(resp.get('files', []), 1):
        size = int(f.get('size', 0))
        print(f"  {i:2}. {f['name'][:45]:<45} {fmt(size):>10}")


# === COMPRESS ===
def compress_video(src, dst):
    cmd = ['ffmpeg', '-y', '-i', str(src), '-c:v', 'libx265', '-crf', CRF,
           '-preset', 'medium', '-tag:v', 'hvc1', '-c:a', 'aac', '-b:a', '128k',
           '-movflags', '+faststart', str(dst)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def compress_photo(src, dst):
    img = Image.open(src)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.thumbnail((MAX_PX, MAX_PX))
    img.save(dst, 'JPEG', quality=JPEG_QUALITY, optimize=True)
    return True


def do_photo(args):
    src, = args
    try:
        orig_size = src.stat().st_size
        dst = src.with_suffix('.tmp.jpg')
        img = Image.open(src)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail((MAX_PX, MAX_PX))
        img.save(dst, 'JPEG', quality=JPEG_QUALITY, optimize=True)
        new_size = dst.stat().st_size
        if new_size < orig_size * 0.90:
            os.remove(src)
            dst.rename(src.with_suffix('.jpg'))
            return orig_size - new_size
        else:
            os.remove(dst)
            return 0
    except:
        dst = src.with_suffix('.tmp.jpg')
        if dst.exists(): os.remove(dst)
        return 0


def do_video(args):
    src, = args
    orig_size = src.stat().st_size
    dst = src.with_suffix('.tmp.mp4')
    if compress_video(src, dst):
        new_size = dst.stat().st_size
        if new_size < orig_size * 0.95:
            os.remove(src)
            dst.rename(src.with_suffix('.mp4'))
            return orig_size - new_size
        os.remove(dst)
    elif dst.exists():
        os.remove(dst)
    return 0


def cmd_compress(path):
    """Compress all media in a folder in-place."""
    path = Path(path).expanduser()
    if not path.exists():
        print(f"❌ Path not found: {path}")
        return

    videos, photos = [], []
    for f in path.rglob('*'):
        if not f.is_file(): continue
        ext = f.suffix.lower()
        if ext in VIDEO_EXTS: videos.append(f)
        elif ext in PHOTO_EXTS: photos.append(f)

    total_before = sum(f.stat().st_size for f in videos + photos)
    print(f"📂 {path}")
    print(f"   {len(videos)} videos, {len(photos)} photos ({fmt(total_before)})")
    print(f"   Settings: CRF={CRF}, JPEG_QUALITY={JPEG_QUALITY}, MAX_PX={MAX_PX}\n")

    saved = 0

    if photos:
        print(f"📷 Compressing {len(photos)} photos (8 threads)...")
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            for result in pool.map(do_photo, [(p,) for p in photos]):
                saved += result
                done += 1
                if done % 100 == 0 or done == len(photos):
                    print(f"   {done}/{len(photos)} | saved {fmt(saved)}", flush=True)

    if videos:
        print(f"\n🎬 Compressing {len(videos)} videos (4 threads)...")
        done = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(do_video, [(v,) for v in videos]):
                saved += result
                done += 1
                if done % 5 == 0 or done == len(videos):
                    print(f"   {done}/{len(videos)} | saved {fmt(saved)}", flush=True)

    total_after = total_before - saved
    print(f"\n{'='*50}")
    print(f"✅ Compression complete")
    print(f"   Before: {fmt(total_before)}")
    print(f"   After:  {fmt(total_after)}")
    print(f"   Saved:  {fmt(saved)} ({100*saved//total_before}%)")


# === UPLOAD DRIVE ===
def cmd_upload_drive(path):
    """Upload a folder to Google Drive preserving structure."""
    from googleapiclient.http import MediaFileUpload
    path = Path(path).expanduser()
    service = auth_drive()

    files = [f for f in path.rglob('*') if f.is_file() and f.suffix.lower() not in SKIP_EXTS]
    print(f"📁 Uploading {len(files)} files ({fmt(sum(f.stat().st_size for f in files))}) to Drive\n")

    folder_cache = {}
    uploaded = 0

    for f in files:
        rel = f.relative_to(path)
        folder_id = None
        for i, part in enumerate(rel.parts[:-1]):
            key = '/'.join(rel.parts[:i+1])
            if key not in folder_cache:
                q = f"name='{part}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                if folder_id: q += f" and '{folder_id}' in parents"
                try:
                    existing = service.files().list(q=q, fields='files(id)', pageSize=1).execute().get('files', [])
                except:
                    wait_for_network()
                    existing = service.files().list(q=q, fields='files(id)', pageSize=1).execute().get('files', [])
                if existing:
                    folder_cache[key] = existing[0]['id']
                else:
                    meta = {'name': part, 'mimeType': 'application/vnd.google-apps.folder'}
                    if folder_id: meta['parents'] = [folder_id]
                    folder_cache[key] = service.files().create(body=meta, fields='id').execute()['id']
            folder_id = folder_cache[key]

        # Skip if exists
        q_check = f"name='{f.name}' and trashed=false"
        if folder_id: q_check += f" and '{folder_id}' in parents"
        try:
            existing = service.files().list(q=q_check, fields='files(id)', pageSize=1).execute().get('files', [])
        except:
            wait_for_network()
            existing = service.files().list(q=q_check, fields='files(id)', pageSize=1).execute().get('files', [])
        if existing:
            uploaded += 1
            if uploaded % 20 == 0: print(f"   {uploaded}/{len(files)} (skipped existing)", flush=True)
            continue

        meta = {'name': f.name}
        if folder_id: meta['parents'] = [folder_id]
        media = MediaFileUpload(str(f), resumable=True)
        try:
            service.files().create(body=meta, media_body=media, fields='id').execute()
            uploaded += 1
            if uploaded % 20 == 0 or uploaded == len(files):
                print(f"   {uploaded}/{len(files)} uploaded", flush=True)
        except Exception as e:
            print(f"\n   ⏸️  Connection lost, waiting...")
            wait_for_network()
            try:
                media = MediaFileUpload(str(f), resumable=True)
                service.files().create(body=meta, media_body=media, fields='id').execute()
                uploaded += 1
            except:
                print(f"   ❌ Failed: {rel}")

    print(f"\n✅ Drive upload complete: {uploaded}/{len(files)}")


# === UPLOAD PHOTOS ===
def cmd_upload_photos(path):
    """Upload media files to Google Photos."""
    from google.auth.transport.requests import Request
    path = Path(path).expanduser()
    creds = auth_photos()

    media_exts = PHOTO_EXTS | VIDEO_EXTS
    files = [f for f in path.rglob('*') if f.is_file() and f.suffix.lower() in media_exts]
    print(f"📷 Uploading {len(files)} files ({fmt(sum(f.stat().st_size for f in files))}) to Photos\n")

    # Resume support
    progress_file = 'photos_upload_progress.txt'
    uploaded_set = set()
    if os.path.exists(progress_file):
        with open(progress_file) as pf:
            uploaded_set = set(pf.read().splitlines())
    remaining = [f for f in files if str(f) not in uploaded_set]
    if uploaded_set:
        print(f"   Resuming — skipping {len(uploaded_set)} already uploaded\n")

    uploaded = 0
    failed = []
    BATCH = 20

    for i in range(0, len(remaining), BATCH):
        batch = remaining[i:i+BATCH]
        upload_tokens = []

        for f in batch:
            safe_name = f.name.encode('ascii', 'ignore').decode('ascii') or 'file'
            headers = {'Authorization': f'Bearer {creds.token}', 'Content-Type': 'application/octet-stream',
                       'X-Goog-Upload-File-Name': safe_name, 'X-Goog-Upload-Protocol': 'raw'}
            try:
                with open(f, 'rb') as fp:
                    resp = requests.post('https://photoslibrary.googleapis.com/v1/uploads', headers=headers, data=fp)
                if resp.status_code == 200:
                    upload_tokens.append({'simpleMediaItem': {'uploadToken': resp.text, 'fileName': safe_name}})
                elif resp.status_code == 401:
                    creds.refresh(Request())
                    failed.append(f.name)
                else:
                    failed.append(f.name)
            except:
                wait_for_network()
                failed.append(f.name)

        if upload_tokens:
            resp = requests.post('https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate',
                headers={'Authorization': f'Bearer {creds.token}', 'Content-Type': 'application/json'},
                json={'newMediaItems': upload_tokens})
            if resp.status_code == 200:
                results = resp.json().get('newMediaItemResults', [])
                success = sum(1 for r in results if r.get('status', {}).get('message') == 'Success')
                uploaded += success
                with open(progress_file, 'a') as pf:
                    for f in batch[:len(upload_tokens)]:
                        pf.write(str(f) + '\n')

        if (i + BATCH) % 100 < BATCH or i + BATCH >= len(remaining):
            print(f"   {min(i+BATCH, len(remaining))}/{len(remaining)} | uploaded: {uploaded}", flush=True)
        time.sleep(1)

    print(f"\n✅ Photos upload complete: {uploaded}/{len(remaining)}")
    if failed:
        print(f"   ❌ Failed: {len(failed)} (see upload_failed.txt)")
        with open('upload_failed.txt', 'w') as f:
            f.write('\n'.join(failed))


# === MAIN ===
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == 'audit':
        cmd_audit()
    elif cmd == 'compress' and len(sys.argv) > 2:
        cmd_compress(sys.argv[2])
    elif cmd == 'upload-drive' and len(sys.argv) > 2:
        cmd_upload_drive(sys.argv[2])
    elif cmd == 'upload-photos' and len(sys.argv) > 2:
        cmd_upload_photos(sys.argv[2])
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
