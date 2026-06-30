#!/usr/bin/env python3
"""
build_ondas.py
--------------
Packages PCA34 session files into .onda bundles and uploads them to Xano.

Usage:
    python build_ondas.py --captures <path> --transcripts <path> [--dry-run]

Where:
  --captures    folder containing the .mp3 audio files
  --transcripts folder containing the .txt and .json files
  --dry-run     build .onda files locally but skip Xano upload

Output:
  - .onda files written to ./onda_output/
  - sessions.json patched with onda_url for each successfully uploaded session
"""

import argparse
import json
import os
import re
import sys
import time
import zipfile
import io
import requests
from pathlib import Path

XANO_UPLOAD_URL = 'https://xrxm-29on-xlyt.n7e.xano.io/api:uZtI4amS/onda_share/upload'
SESSIONS_JSON   = Path(__file__).parent / 'sessions.json'
OUTPUT_DIR      = Path(__file__).parent / 'onda_output'

# Map Drive file title prefixes -> sessions.json title
# Drive uses fullwidth colon ： (U+FF1A); sessions.json uses normal colon
def normalize_title(s: str) -> str:
    """Normalize a file title for matching: strip extension, normalize colons/dashes."""
    s = s.strip()
    # Remove file extension
    for ext in ('.mp3', '.txt', '.json'):
        if s.endswith(ext):
            s = s[:-len(ext)]
    # Replace fullwidth colon and other unicode variants with regular colon
    s = s.replace('：', ':').replace('–', '-').replace('—', '-')
    # Normalize whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    # Truncate titles that were cut off (Drive truncates long filenames)
    return s.lower()


def match_sessions(captures_dir: Path, transcripts_dir: Path):
    """Match up mp3 + txt + json files by normalized title prefix."""
    mp3s  = {normalize_title(f.name): f for f in captures_dir.glob('*.mp3')}
    txts  = {normalize_title(f.name): f for f in transcripts_dir.glob('*.txt')}
    jsons = {normalize_title(f.name): f for f in transcripts_dir.glob('*.json')}

    matched = []
    for key, mp3_path in mp3s.items():
        txt_path  = txts.get(key)
        json_path = jsons.get(key)
        if not txt_path or not json_path:
            # Try prefix match (Drive truncates long filenames)
            for k, v in txts.items():
                if k.startswith(key[:40]) or key.startswith(k[:40]):
                    txt_path = v
                    break
            for k, v in jsons.items():
                if k.startswith(key[:40]) or key.startswith(k[:40]):
                    json_path = v
                    break
        matched.append({
            'key':      key,
            'mp3':      mp3_path,
            'txt':      txt_path,
            'json':     json_path,
            'complete': bool(txt_path and json_path),
        })
    return matched


def convert_word_timings(raw: list) -> list:
    """Convert Whisper format {word, start, end} (seconds) to .onda compact {p,w,s,e} (ms)."""
    result = []
    for i, w in enumerate(raw):
        result.append({
            'p': i,
            'w': w.get('word', '').strip(),
            's': int(round(w.get('start', 0) * 1000)),
            'e': int(round(w.get('end',   0) * 1000)),
        })
    return result


def build_onda(session: dict, label: str, output_dir: Path) -> Path:
    """Build a .onda ZIP bundle from matched files."""
    mp3_path  = session['mp3']
    txt_path  = session['txt']
    json_path = session['json']

    # Load content
    audio_bytes     = mp3_path.read_bytes()
    transcript_text = txt_path.read_text(encoding='utf-8')
    raw_timings     = json.loads(json_path.read_text(encoding='utf-8'))
    word_timings    = convert_word_timings(raw_timings)

    # Derive duration from last word timing
    duration_ms = word_timings[-1]['e'] if word_timings else 0

    # meta.json
    meta = {
        'version':     1,
        'label':       label,
        'notes':       '',
        'created_at':  1749340800,  # 2025-06-08 approximate PCA34 date
        'duration_ms': duration_ms,
    }

    # Safe filename
    safe = re.sub(r'[^\w\s-]', '', label).strip().replace(' ', '_')[:60]
    out_path = output_dir / f'{safe}.onda'

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('meta.json',     json.dumps(meta, ensure_ascii=False))
        zf.writestr('audio.mp3',     audio_bytes)
        zf.writestr('transcript.txt', transcript_text)
        zf.writestr('words.json',    json.dumps(word_timings, ensure_ascii=False))

    out_path.write_bytes(buf.getvalue())
    print(f'  [OK] Built {out_path.name} ({len(buf.getvalue())//1024} KB)')
    return out_path


def upload_to_xano(onda_path: Path, label: str) -> str | None:
    """Upload .onda to Xano onda_share/upload. Returns download_url or None."""
    filename = f"{label[:60]}.onda"
    with open(onda_path, 'rb') as f:
        resp = requests.post(
            XANO_UPLOAD_URL,
            files={'file': (filename, f, 'application/octet-stream')},
            data={'filename': filename},
            timeout=120,
        )
    if resp.status_code == 200:
        data = resp.json()
        url  = data.get('download_url', '')
        uuid = data.get('uuid', '')
        print(f'  [OK] Uploaded -> {url}')
        return url
    else:
        print(f'  [FAIL] Upload failed: {resp.status_code} {resp.text[:200]}')
        return None


def patch_sessions_json(updates: dict[str, str]):
    """Patch sessions.json: set onda_url for sessions whose title matches."""
    sessions = json.loads(SESSIONS_JSON.read_text(encoding='utf-8'))
    patched  = 0
    for s in sessions:
        title_norm = normalize_title(s.get('title', ''))
        for key, url in updates.items():
            # Match if the session title starts with or contains the key
            if title_norm.startswith(key[:40]) or key.startswith(title_norm[:40]):
                if not s.get('onda_url'):
                    s['onda_url'] = url
                    patched += 1
                    print(f'  [OK] Patched: {s["title"][:60]}')
                break
    SESSIONS_JSON.write_text(json.dumps(sessions, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nPatched {patched} sessions in sessions.json')


def find_label_for_key(key: str, sessions_json: list) -> str:
    """Find the canonical title from sessions.json for a given normalized key."""
    for s in sessions_json:
        title_norm = normalize_title(s.get('title', ''))
        if title_norm.startswith(key[:40]) or key.startswith(title_norm[:40]):
            return s['title']
    # Fallback: convert key back to title case
    return key.replace('：', ':').title()


def main():
    parser = argparse.ArgumentParser(description='Build and upload PCA .onda bundles')
    parser.add_argument('--captures',     required=True, help='Folder with .mp3 files')
    parser.add_argument('--transcripts',  required=True, help='Folder with .txt and .json files')
    parser.add_argument('--dry-run',      action='store_true', help='Build .onda locally, skip upload')
    parser.add_argument('--event',        default='PCA34', help='Event filter for sessions.json (default: PCA34)')
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    captures_dir    = Path(args.captures)
    transcripts_dir = Path(args.transcripts)
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not captures_dir.exists():
        sys.exit(f'Captures folder not found: {captures_dir}')
    if not transcripts_dir.exists():
        sys.exit(f'Transcripts folder not found: {transcripts_dir}')

    sessions = json.loads(SESSIONS_JSON.read_text(encoding='utf-8'))
    event_sessions = [s for s in sessions if s.get('event') == args.event]
    print(f'Found {len(event_sessions)} {args.event} sessions in sessions.json')

    matched = match_sessions(captures_dir, transcripts_dir)
    complete = [m for m in matched if m['complete']]
    print(f'Found {len(matched)} audio files, {len(complete)} with full transcript+timings\n')

    updates = {}
    for m in complete:
        label = find_label_for_key(m['key'], sessions)
        print(f'Processing: {label[:70]}')
        try:
            onda_path = build_onda(m, label, OUTPUT_DIR)
            if not args.dry_run:
                time.sleep(0.5)  # gentle rate limiting
                url = upload_to_xano(onda_path, label)
                if url:
                    updates[m['key']] = url
        except Exception as e:
            print(f'  FAIL Error: {e}')
        print()

    if updates:
        print(f'Patching sessions.json with {len(updates)} new onda_urls...')
        patch_sessions_json(updates)
    elif not args.dry_run:
        print('No uploads succeeded — sessions.json not modified.')
    else:
        print('Dry run complete. Run without --dry-run to upload to Xano.')

    print('\nDone.')


if __name__ == '__main__':
    main()
